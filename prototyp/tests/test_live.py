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
                           einst=Einstellungen(**{"takte": 4, "ausstieg": "phrase", **einst}))


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
