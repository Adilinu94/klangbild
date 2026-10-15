"""Tests fuer live.py - Echtzeit-Wiedergabe ohne Soundkarte (Phase 2, ADR-021)."""

from __future__ import annotations

import numpy as np

from klangbild import live
from klangbild.einstellungen import Einstellungen

RATE = live.RATE


def _eintrag(tid: int, bpm: float = 120.0, sekunden: float = 40.0, camelot: str = "8A") -> live.Eintrag:
    return live.Eintrag(id=tid, pfad=f"/x/song{tid}.flac", bpm=bpm, camelot=camelot,
                        downbeats=list(np.arange(0.0, sekunden, 240.0 / bpm)))


def _wiedergabe(*eintraege: live.Eintrag, **einst) -> live.Wiedergabe:
    bib = {e.id: e for e in eintraege}
    # Track-ID als Pegel: so sieht man im Ausgang, welcher Song gerade klingt.
    return live.Wiedergabe(bib, laden=lambda e: np.full((40 * RATE, 2), e.id / 10, np.float32),
                           einst=Einstellungen(**{"modus": "manuell", "takte": 4, "ausstieg": "phrase", **einst}))


def test_gain_auf_ziel_und_true_peak_gedeckelt():
    assert live.gain_db(-20.0, -10.0) == 6.0          # -20 -> -14 LUFS
    assert live.gain_db(-20.0, -4.0) == 3.0           # TP -4 + 3 = -1 dBTP Deckel
    assert live.gain_db(None, None) == 0.0


def test_fuellen_ohne_autodj_schneidet_am_songende_auf_den_naechsten():
    w = _wiedergabe(_eintrag(1), _eintrag(2))
    w.play(1)
    w.einreihen(2)
    assert w.vorbereiten()
    assert w.warteschlange == [2]          # erst beim Wechsel entnommen
    block = w.fuellen(40 * RATE + 100)
    assert abs(block[0, 0] - 0.1) < 1e-6 and abs(block[-1, 0] - 0.2) < 1e-6
    assert w.zustand()["aktuell"]["id"] == 2 and w.warteschlange == []


def test_fuellen_endet_still_ohne_naechsten():
    w = _wiedergabe(_eintrag(1))
    w.play(1)
    block = w.fuellen(41 * RATE)
    assert not w.spielt
    assert np.all(block[-RATE // 2:] == 0.0)


def test_autodj_mischt_und_wechselt_vor_songende():
    w = _wiedergabe(_eintrag(1), _eintrag(2, 122.0), art="eq", max_bpm=5.0)
    w.autodj_setzen(True)
    w.play(1)
    assert w.vorbereiten()
    naechster = w.zustand()["naechster"]
    assert naechster["id"] == 2 and naechster["art"] == "eq" and naechster["sync"]
    w.fuellen(int(naechster["in_s"] * RATE) + 10)
    z = w.zustand()
    assert z["aktuell"]["id"] == 2
    assert z["verlauf"][-1]["art"] == "eq"


def test_autodj_ueber_der_tempogrenze_echo():
    w = _wiedergabe(_eintrag(1), _eintrag(2, 140.0), art="eq", max_bpm=5.0)
    w.autodj_setzen(True)
    w.play(1)
    w.einreihen(2)
    assert w.vorbereiten()
    assert w.zustand()["naechster"]["art"] == "echo"


def test_bedienung_verwirft_gebackenen_uebergang():
    w = _wiedergabe(_eintrag(1), _eintrag(2))
    w.play(1)
    w.einreihen(2)
    w.vorbereiten()
    w.seek(5.0)
    assert w.zustand()["naechster"] is None
    assert abs(w.zustand()["aktuell"]["pos_s"] - 5.0) < 1e-3


def test_verworfener_uebergang_verliert_den_eingereihten_titel_nicht():
    w = _wiedergabe(_eintrag(1), _eintrag(2))
    w.autodj_setzen(True)
    w.play(1)
    w.einreihen(2)
    w.vorbereiten()
    w.weiter()                              # verwirft den gebackenen Uebergang
    assert w.warteschlange == [2]


def test_sortieren_fuellt_warteschlange_ohne_aktuellen():
    w = _wiedergabe(_eintrag(1), _eintrag(2, 121.0), _eintrag(3, 135.0))
    w.play(1)
    w.sortieren()
    assert w.warteschlange == [2, 3]        # Tempo-Nachbar zuerst


def test_verschieben_tauscht_nachbarn():
    w = _wiedergabe(_eintrag(1), _eintrag(2), _eintrag(3))
    w.einreihen(2)
    w.einreihen(3)
    w.verschieben(1, -1)
    assert w.warteschlange == [3, 2]


def test_play_nimmt_den_titel_aus_der_warteschlange():
    w = _wiedergabe(_eintrag(1), _eintrag(2))
    w.einreihen(1)
    w.einreihen(2)
    w.play(1)
    assert w.warteschlange == [2]


def test_vorheriger_song_bleibt_bis_zum_blendenende_sichtbar():
    w = _wiedergabe(_eintrag(1), _eintrag(2, 121.0), art="crossfade", max_bpm=5.0)
    w.autodj_setzen(True)
    w.play(1)
    assert w.vorbereiten()
    n = w.zustand()["naechster"]
    assert n["kurven"]["b"]["lautstaerke"][-1] > 0.95 and n["blende_s"] > 0
    w.fuellen(int(n["in_s"] * RATE) + RATE)          # 1 s in die Blende
    z = w.zustand()
    assert z["aktuell"]["id"] == 2 and z["vorher"]["id"] == 1
    assert abs(z["vorher"]["seit_s"] - 1.0) < 0.05 and "kurven" not in z["verlauf"][-1]
    w.fuellen(int(n["blende_s"] * RATE))             # Blende vorbei
    assert "vorher" not in w.zustand()


def test_auto_dj_regie_plant_begruendet_und_wechselt(tmp_path, monkeypatch):
    from klangbild import profil, stems

    monkeypatch.setattr(profil, "CACHE", tmp_path / "profil")
    monkeypatch.setattr(stems, "VORRAT", tmp_path / "vorrat")
    w = _wiedergabe(_eintrag(1), _eintrag(2, 121.0), modus="ausgewogen", spielanteil="lang")
    w.autodj_setzen(True)
    w.play(1)
    w.einreihen(2)
    assert w.vorbereiten()
    nx = w.zustand()["naechster"]
    assert nx["rezept"] and nx["grund"] and nx["plan"] == 1 and nx["sync"]
    assert (tmp_path / "profil" / "1.json").exists()
    w.anders()                                  # naechstbester Plan
    assert w.vorbereiten() and w.zustand()["naechster"]["plan"] == 2
    w.fuellen(int(w.zustand()["naechster"]["in_s"] * RATE) + 10)
    assert w.zustand()["aktuell"]["id"] == 2 and w.verlauf[-1]["rezept"]


def test_lernen_weiter_in_der_blende_ist_minus_durchhoeren_plus(tmp_path, monkeypatch):
    from klangbild import profil, stems

    monkeypatch.setattr(profil, "CACHE", tmp_path / "profil")
    monkeypatch.setattr(stems, "VORRAT", tmp_path / "vorrat")
    w = _wiedergabe(_eintrag(1), _eintrag(2), _eintrag(3), modus="ausgewogen")
    w.lern_pfad = tmp_path / "lernen.json"
    w.autodj_setzen(True)
    w.play(1)
    w.einreihen(2)
    w.einreihen(3)
    assert w.vorbereiten()
    rezept = w.zustand()["naechster"]["rezept"]
    w.fuellen(int(w.zustand()["naechster"]["in_s"] * RATE) + 10)     # Blende laeuft
    assert w.vorher is not None
    w.weiter()                                                         # mitten in der Blende
    assert w.vorlieben[rezept] == -1.0 and (tmp_path / "lernen.json").exists()


def test_autodj_waehlt_den_besser_mischbaren_titel(tmp_path, monkeypatch):
    from klangbild import profil, stems

    monkeypatch.setattr(profil, "CACHE", tmp_path / "profil")
    monkeypatch.setattr(stems, "VORRAT", tmp_path / "vorrat")
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
    from test_regie import SONG, _profil

    a, gut, schlecht = _eintrag(1), _eintrag(2), _eintrag(3)
    profil.speichern(1, _profil(SONG, gesang={12, 13}), tmp_path / "profil")
    profil.speichern(2, _profil(SONG), tmp_path / "profil")                         # B ohne Gesang am Anfang
    profil.speichern(3, _profil(SONG, gesang={0, 1, 2}), tmp_path / "profil")       # B singt sofort
    w = _wiedergabe(a, gut, schlecht, modus="ausgewogen")
    w.play(1)
    assert w._autodj_wahl(w.spur, 120.0, 10.0, {1}, w.einst) == 2


def test_stem_fenster_cache_bleibt_unter_der_grenze(tmp_path):
    from klangbild import stems

    for k in range(5):
        (tmp_path / f"{k}.npz").write_bytes(b"x" * 1000)
    stems._cache_begrenzen(tmp_path, grenze=2500)
    assert len(list(tmp_path.glob("*.npz"))) == 2


def test_automatisch_im_stil_manuell_nutzt_die_regie(tmp_path, monkeypatch):
    from klangbild import profil, stems

    monkeypatch.setattr(profil, "CACHE", tmp_path / "profil")
    monkeypatch.setattr(stems, "VORRAT", tmp_path / "vorrat")
    w = _wiedergabe(_eintrag(1), _eintrag(2, 121.0), art="auto", takte=4)   # modus bleibt "manuell"
    w.autodj_setzen(True)
    w.play(1)
    w.einreihen(2)
    assert w.vorbereiten()
    nx = w.zustand()["naechster"]
    assert nx["rezept"] and nx["grund"], nx            # die Regie hat geplant, nicht die Festregel
    w2 = _wiedergabe(_eintrag(1), _eintrag(2, 121.0), art="eq", takte=4)    # explizite Art: wie gehabt
    w2.autodj_setzen(True)
    w2.play(1)
    w2.einreihen(2)
    assert w2.vorbereiten() and "rezept" not in w2.zustand()["naechster"]


def test_vorschau_zeigt_titel_und_plan_vor_dem_backen(tmp_path, monkeypatch):
    from klangbild import profil, stems

    monkeypatch.setattr(profil, "CACHE", tmp_path / "profil")
    monkeypatch.setattr(stems, "VORRAT", tmp_path / "vorrat")
    w = _wiedergabe(_eintrag(1), _eintrag(2, 121.0), modus="ausgewogen")
    w.autodj_setzen(True)
    w.play(1)
    w.einreihen(2)
    gesehen = []
    echt = w._backen_ergebnis
    w._backen_ergebnis = lambda *a, **k: (gesehen.append(w.zustand().get("vorschau")), echt(*a, **k))[1]
    assert w.vorbereiten()
    assert gesehen[0]["id"] == 2 and gesehen[0]["titel"]
    z = w.zustand()
    assert "vorschau" not in z and z["naechster"]["id"] == 2     # fertig: aus der Vorschau wird NÄCHSTER


def test_geladene_titel_clippen_nicht():
    """Dekoder-Ueberschwinger (>1,0 nach dem Pegelangleich) werden begrenzt: sonst clippt die Soundkarte."""
    from dataclasses import replace

    e = replace(_eintrag(1), gain_db=-2.0)
    w = live.Wiedergabe({1: e}, laden=lambda x: np.full((RATE, 2), 1.3, np.float32),
                        einst=Einstellungen(modus="manuell"))
    assert float(np.abs(w.laden(e)).max()) <= 0.9661
    assert float(np.abs(w.roh(e)).max()) == np.float32(1.3)   # der Zwischenspeicher bleibt unberuehrt


def test_autodj_waehlt_nicht_dieselbe_aufnahme_nochmal():
    from dataclasses import replace

    assert live._gleicher_titel("Baby Come Over - Tobiahs, Feat X", "Baby Come Over-Tobiahs")
    assert not live._gleicher_titel("Baby Come Over - Tobiahs", "Pain Away - Atura")
    assert not live._gleicher_titel("Go", "Go Go")   # zu kurz fuer einen sicheren Vergleich
    a = replace(_eintrag(1), pfad="/x/Baby Come Over - Tobiahs, Feat X.flac")
    dup = replace(_eintrag(2), pfad="/x/Baby Come Over-Tobiahs.flac")
    anderer = replace(_eintrag(3, 124.0), pfad="/x/Pain Away - Atura.flac")
    w = live.Wiedergabe({1: a, 2: dup, 3: anderer}, laden=lambda e: np.zeros((RATE, 2), np.float32),
                        einst=Einstellungen(modus="manuell", art="eq"))
    w.play(1)
    assert w._autodj_wahl(w.spur, 120.0, 0.0, {1}, w.einst) == 3
