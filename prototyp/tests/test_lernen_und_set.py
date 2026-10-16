"""Tests fuer BAUPLAN-UEBERGAENGE §2 (Datensatz, Kritiker), §7 (Daumen, Vorhoeren) und §8 (Set-Planung)."""

from __future__ import annotations

import io
import json
import threading
import urllib.error
import urllib.request

import numpy as np
import pytest
import soundfile as sf

from klangbild import datensatz, kritiker, live, mixer, paarnoten, plan
from klangbild.profil import Profil

RATE = live.RATE
TAKT = 2.0


def _profil(n=64, seed=0) -> Profil:
    rng = np.random.default_rng(seed)
    g = rng.normal(-12.0, 3.0, n)
    return Profil(np.arange(n) * TAKT, np.stack([g, g, g], axis=1), g, None, np.ones(n, bool), n * TAKT)


def test_b_einsatz_aus_dem_clip_auf_den_takt_genau():
    rng = np.random.default_rng(1)
    hop = RATE // datensatz.HUELLE_HZ
    huelle = np.repeat(np.exp(rng.normal(0, 1, 64 * 2 * datensatz.HUELLE_HZ)), hop)   # 64 Takte a 2 s
    song = (rng.standard_normal(len(huelle)) * huelle * 0.05).astype(np.float32)
    j, takte = 12, 8
    ende = (j + takte) * int(TAKT * RATE)                              # Blendenende in B
    clip = np.concatenate([rng.standard_normal(10 * RATE) * 0.05, song[ende:ende + 8 * RATE]]).astype(np.float32)
    m = {"info": {"sync": True, "takte": takte, "blende_s": 16.0}, "blende_bis_s": 10.0}
    assert abs(datensatz.b_einsatz(m, clip, RATE, song, RATE, _profil()) - j) <= 1
    stumm = {"info": m["info"], "blende_bis_s": 10.0}
    zufall = np.concatenate([clip[:10 * RATE], rng.standard_normal(8 * RATE).astype(np.float32)])
    assert datensatz.b_einsatz(stumm, zufall, RATE, song, RATE, _profil()) is None   # nichts gefunden: offen


def test_merkmale_einer_zeile():
    m = {"nr": 3, "a": {"id": 1, "camelot": "8A"}, "b": {"id": 2, "camelot": "9A"}, "stil": "lang",
         "spielanteil": "lang", "weiter": False, "experimente": "wild",
         "info": {"rezept": "profi_eq", "takte": 16, "sync": True, "stems": False, "bpm_a": 120.0, "bpm_b": 122.0,
                  "aus_takt": 40}}
    z = datensatz.zeile("uebergangstest-x", m, {"note": 4}, _profil(), _profil(seed=2), 8,
                        {"lautheit_spanne_db": 3.0, "loch_db": -2.0})
    mm = z["merkmale"]
    assert mm["rezept=profi_eq"] == 1.0 and mm["experimente"] == 2.0 and mm["bpm_abstand"] == 2.0
    assert "a_pegel" in mm and "b_einsatz" in mm and "harmonie" not in mm and mm["loch_db"] == -2.0
    assert z["gewicht"] == 1.0 and z["ein_takt_rekonstruiert"]   # info ohne ein_takt: wie Runde 1-11


def _zeilen(n=160, seed=0, zufall=False):
    rng = np.random.default_rng(seed)
    aus = []
    for k in range(n):
        x = rng.normal(size=4)
        note = int(rng.integers(1, 6)) if zufall else int(np.clip(round(3 + 1.2 * x[0] - 0.8 * x[1]), 1, 5))
        mm = {"a": float(x[0]), "b": float(x[1]), "c": float(x[2]) if k % 7 else float("nan"),
              f"rezept=r{k % 3}": 1.0, "loch_db": float(x[3])}
        aus.append({"runde": f"uebergangstest-r{k % 8:02d}", "nr": k, "note": note, "gewicht": 1.0, "merkmale": mm})
    return aus


def test_kritiker_json_rechnet_wie_sklearn():
    zeilen = _zeilen()
    namen = sorted({k for z in zeilen for k in z["merkmale"]})
    model = kritiker._modell(zeilen, namen)
    exp = json.loads(json.dumps(kritiker.exportieren(model, namen)))
    for z in zeilen[:50]:
        roh = exp["basis"] + sum(kritiker._baum(b, [z["merkmale"].get(n, 0.0 if "=" in n else np.nan) for n in namen])
                                 for b in exp["baeume"])
        assert abs(roh - model.predict(kritiker._x([z], namen))[0]) < 1e-6


def test_kritiker_tor_greift_bei_zufallsnoten():
    zeilen = _zeilen(zufall=True)
    namen = sorted({k for z in zeilen for k in z["merkmale"]})
    assert not kritiker.tor(kritiker.messen(zeilen, namen))


def _wiedergabe(tmp_path):
    a = live.Eintrag(id=1, pfad="/x/A.flac", bpm=120.0, camelot="8A", downbeats=[0.0, 2.0])
    b = live.Eintrag(id=2, pfad="/x/B.flac", bpm=120.0, camelot="8A", downbeats=[0.0, 2.0])
    w = live.Wiedergabe({1: a, 2: b}, laden=lambda e: np.full((RATE * 20, 2), 0.1 * e.id, np.float32))
    w.bewertung_ordner = tmp_path / "live-bewertungen"
    return w, a, b


def test_daumen_speichert_im_hoertest_format(tmp_path, monkeypatch):
    w, a, b = _wiedergabe(tmp_path)
    with pytest.raises(ValueError):
        w.daumen(True)                                                 # noch keine Blende
    w.play(1)
    info = {"rezept": "profi_eq", "takte": 8, "blende_s": 4.0, "sync": True, "stems": False, "stil": "lang",
            "spielanteil": "lang", "weiter": False, "experimente": "klassisch",
            "art": "eigen", "a_orig_start": 0.0, "a_orig_pro_s": 1.0}
    w._naechste = (w.pos + 10, live.Spur.roh(b, np.zeros((RATE * 10, 2), np.float32)), info)
    w.fuellen(20)                                                      # Umschalten -> Blende laeuft
    assert w.zustand()["bewertbar"]["bewertet"] is None
    w.daumen(False, "Zu früh")
    assert w.vorlieben["profi_eq"] < 0 and w.zustand()["bewertbar"]["bewertet"] is False
    with pytest.raises(ValueError):
        w.daumen(True)                                                 # schon bewertet
    monkeypatch.setattr(datensatz, "LIVE", w.bewertung_ordner)
    [(ordner, m, note)] = datensatz.live_faelle()
    assert ordner.startswith("live-") and note == {"note": 2, "stichworte": ["Zu früh"], "daumen": True}
    assert m["info"]["rezept"] == "profi_eq" and m["a"]["id"] == 1 and m["b"]["id"] == 2


@pytest.fixture
def server(tmp_path):
    w, a, b = _wiedergabe(tmp_path)
    m = mixer.Mixer(w, tmp_path / "k.db", "0.3.0", tmp_path / "upload", tmp_path / "einst.json")
    srv = mixer.server(m, "127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", w, b
    srv.shutdown()
    srv.server_close()


def test_api_daumen_prueft_den_body_und_vorhoeren(server):
    url, w, b = server
    for body in ({"gut": "ja"}, {"gut": True, "stichwort": "Quatsch"}):
        req = urllib.request.Request(url + "/api/daumen", data=json.dumps(body).encode(), method="POST")
        with pytest.raises(urllib.error.HTTPError) as fehler:
            urllib.request.urlopen(req, timeout=5)
        assert fehler.value.code == 400
    with pytest.raises(urllib.error.HTTPError) as fehler:
        urllib.request.urlopen(url + "/api/vorhoeren", timeout=5)
    assert fehler.value.code == 404                                     # noch nichts gebacken
    w.play(1)
    w._naechste = (RATE * 10, live.Spur.roh(b, np.full((RATE * 10, 2), 0.2, np.float32)), {"blende_s": 2.0})
    with urllib.request.urlopen(url + "/api/vorhoeren", timeout=5) as r:
        x, rate = sf.read(io.BytesIO(r.read()))
    assert rate == RATE and abs(len(x) - 10 * RATE) <= 1                # 4 s A + 2 s Blende + 4 s B


def _tracks():
    return [plan.Track(id=i, pfad=str(i), bpm=120.0, camelot="8A", energie_db=-10.0) for i in range(8)]


def test_set_planen_folgt_den_paarnoten_und_2opt_verbessert():
    gut = {(k, k + 1) for k in range(7)}                              # 0 -> 1 -> ... -> 7 ist die beste Kette
    note = lambda a, b: 5.0 if (a, b) in gut else 2.0                  # noqa: E731
    t = _tracks()
    folge = plan.sortiere_alle(t, 5.0, start_id=0, paarnote=note)
    assert folge == list(range(8)) and folge == plan.sortiere_alle(t, 5.0, start_id=0, paarnote=note)
    index, ziel = {x.id: x for x in t}, plan.bogen_ziel([-10.0] * 8, 8, "gleichmaessig")
    schlecht = [0, 1, 2, 6, 5, 4, 3, 7]
    besser = plan._zwei_opt(schlecht, index, ziel, note, None)
    assert plan._set_kosten(besser, index, ziel, note, None) < plan._set_kosten(schlecht, index, ziel, note, None)


def test_paarnoten_cache_verfaellt_mit_neuer_version(tmp_path):
    pn = paarnoten.Paarnoten("0.3.0", tmp_path / "p.json")
    pn.daten["1_2"] = [4.2, "profi_eq", 1.0]
    pn.speichern()
    assert paarnoten.Paarnoten("0.3.0", tmp_path / "p.json").note(1, 2) == 4.2
    assert paarnoten.Paarnoten("0.4.0", tmp_path / "p.json").note(1, 2) is None
