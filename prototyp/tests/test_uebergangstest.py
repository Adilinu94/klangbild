import json

import numpy as np
import pytest

from klangbild import uebergangstest as ut


def test_faelle_reproduzierbar_mit_varianten_und_weiter():
    f1 = ut.faelle_planen(list(range(100)), 30, seed=7)
    assert f1 == ut.faelle_planen(list(range(100)), 30, seed=7)
    assert sorted(f["reihe"] for f in f1) == list(range(len(f1)))   # blind gemischt, jede Stelle einmal
    varianten = [f for f in f1 if f["rang"] > 0]
    assert varianten and all(f1[f["paar"]]["rang"] == 0 and f1[f["paar"]]["a"] == f["a"] for f in varianten)
    assert any(f["weiter"] for f in f1) and not any(f["weiter"] for f in varianten)
    kurz = ut.faelle_planen(list(range(100)), 30, seed=7, stile=("kurz",))
    assert {f["stil"] for f in kurz} == {"kurz"} and any(f["weiter"] for f in kurz)
    assert {f["stil"] for f in f1} == set(ut.STILE)


def test_clip_schneidet_um_die_blende_und_blendet_weich():
    a = np.ones((20 * ut.RATE, 2), np.float32)
    b = np.ones((40 * ut.RATE, 2), np.float32)
    x, von = ut.clip(a, 15 * ut.RATE, b, blende_s=10.0)
    assert von == ut.VOR_S
    assert len(x) == int((ut.VOR_S + 10.0 + ut.NACH_S) * ut.RATE)
    assert x[0, 0] == 0.0 and x[-1, 0] == 0.0 and x[len(x) // 2, 0] == 1.0
    x, von = ut.clip(a, 2 * ut.RATE, b, blende_s=10.0)   # Blende kurz nach Songanfang
    assert von == 2.0


def _test_mit_fall(tmp_path, n=3):
    faelle = ut.faelle_planen(list(range(10)), n, seed=1)
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "faelle.json").write_text(json.dumps(faelle), encoding="utf-8")
    t = ut.Test(tmp_path)
    for f in faelle:
        t._meta_schreiben(f["nr"], {"nr": f["nr"], "a": {"titel": "A"}, "b": {"titel": "B"}, "stil": f["stil"],
                                    "spielanteil": f["spielanteil"], "weiter": f["weiter"], "rang": f["rang"],
                                    "info": {"rezept": "profi_eq", "plan": f["rang"] + 1, "takte": 16, "grund": "x"},
                                    "blende_von_s": 8.0, "blende_bis_s": 20.0, "dauer_s": 26.0})
    return t


def test_bewertung_bleibt_ueber_neustart_erhalten(tmp_path):
    t = _test_mit_fall(tmp_path)
    t.bewerten(0, {"note": 4, "stichworte": ["Zu lang", "erfunden"], "kommentar": "ok"})
    t.bewerten(1, {"spaeter": True})
    neu = ut.Test(tmp_path)   # Stopp + Neustart
    assert neu.bewertungen["0"]["note"] == 4 and neu.bewertungen["0"]["stichworte"] == ["Zu lang"]
    z = {f["nr"]: f for f in neu.zustand()["reihe"]}
    assert z[0]["note"] == 4 and z[1]["spaeter"] and z[2]["note"] is None
    assert "info" not in neu.fall(0)   # blind: Rezept und Grund erst in der Auswertung
    with pytest.raises(ValueError):
        neu.bewerten(2, {"note": 9})


def test_auswertung_je_rezept_und_schlechteste(tmp_path):
    t = _test_mit_fall(tmp_path)
    t.bewerten(0, {"note": 2, "stichworte": ["Loop fällt auf"]})
    t.bewerten(1, {"note": 5})
    text = ut.auswerten(tmp_path)
    assert "Je Rezept" in text and "profi_eq" in text and "Fall 0" in text and "Loop fällt auf" in text
    assert (tmp_path / "auswertung.md").exists()


def test_auswertung_vergleicht_mit_der_runde_davor(tmp_path):
    vor = _test_mit_fall(tmp_path / "uebergangstest-20261014")
    vor.bewerten(0, {"note": 1})
    jetzt = _test_mit_fall(tmp_path / "uebergangstest")
    jetzt.bewerten(0, {"note": 4})
    text = ut.auswerten(tmp_path / "uebergangstest")
    assert "Vergleich mit der Runde davor" in text and "1.00 → 4.00" in text


def test_neue_runde_kennt_die_lieder_der_runden_davor(tmp_path):
    alt = tmp_path / "uebergangstest-runde1" / "clips"
    alt.mkdir(parents=True)
    (alt / "000.json").write_text(json.dumps({"a": {"id": 3}, "b": {"id": 7}}), encoding="utf-8")
    (alt / "001.json").write_text(json.dumps({"nr": 1, "fehler": "kein passender Partner"}), encoding="utf-8")
    assert ut._bekannte_ids(tmp_path / "uebergangstest") == {3, 7}
    assert ut.Test(tmp_path / "uebergangstest").bekannt == {3, 7}


def test_set_faelle_und_clip_mit_pause():
    f = ut.set_faelle_planen(list(range(20)), 3, 1, ("lang",), ("kreativ",))
    assert len(f) == 3 and all(x["set"] and x["experimente"] == "kreativ" for x in f)
    stuecke = [np.ones((ut.RATE, 2), np.float32), np.ones((2 * ut.RATE, 2), np.float32)]
    x = ut.set_clip(stuecke)
    rand = int(ut.SET_PAUSE_S * ut.RATE)
    assert len(x) == 3 * ut.RATE and x[ut.RATE - 1, 0] == 0.0 and x[ut.RATE, 0] == 0.0   # Pause an der Naht
    assert x[0, 0] == 1.0 and x[-1, 0] == 1.0 and x[ut.RATE + rand, 0] == 1.0          # Raender des Sets bleiben


def test_stil_und_experiment_unabhaengig_und_ordner_je_zeile(tmp_path):
    f = ut.faelle_planen(list(range(100)), 9, seed=3, experimente=("klassisch", "kreativ", "wild"))
    basis = [x for x in f if x["rang"] == 0]
    assert len({(x["stil"], x["experimente"]) for x in basis}) == 9
    (tmp_path / "nur_ordner.txt").write_text("D:\\Music\\Chill\nD:\\Music\\DJ Playlist\\Hard UKG\n", encoding="utf-8")
    liste = ut.wurzeln(tmp_path)
    assert ut.wurzel(r"D:\Music\DJ Playlist\Hard UKG\a.mp3", liste) == liste[1]
    assert ut.wurzel(r"D:\Music\Chill\Neuer Ordner\b.mp3", liste) == liste[0]
    assert ut.wurzel(r"D:\Music\DnB\c.mp3", liste) is None
