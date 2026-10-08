"""Tests fuer die Metriken der Tore (Phase 0.2)."""

from __future__ import annotations

import numpy as np

from klangbild import metrics


def test_wilson_randwerte():
    assert metrics.wilson(0, 20)[0] == 0.0
    oben = metrics.wilson(20, 20)[1]
    assert abs(oben - 1.0) < 1e-9
    assert metrics.wilson(0, 0) == (0.0, 0.0)


def test_wilson_bei_zwanzig_faellen():
    """Ein Fehler bei 20 Faellen = 5 Punkte: das Intervall muss das zeigen."""
    unten, oben = metrics.wilson(19, 20)
    assert unten < 0.95 < oben
    assert oben - unten > 0.15


def test_beat_f1_perfekt_und_leer():
    zeiten = [0.5, 1.0, 1.5, 2.0]
    assert metrics.beat_f1(zeiten, zeiten) == 1.0
    assert metrics.beat_f1([0.0], [10.0]) == 0.0


def test_beat_f1_toleranz():
    ref = [1.00, 2.00, 3.00]
    nah = [1.05, 2.04, 2.96]   # innerhalb 70 ms
    weit = [1.20, 2.20, 3.20]  # ausserhalb
    assert metrics.beat_f1(ref, nah) == 1.0
    assert metrics.beat_f1(ref, weit) == 0.0


def test_bpm_mit_oktavtoleranz():
    assert metrics.bpm_richtig(128.0, 128.0)
    assert metrics.bpm_richtig(128.0, 64.0)   # halbes Tempo
    assert metrics.bpm_richtig(128.0, 256.0)  # doppeltes Tempo
    assert not metrics.bpm_richtig(128.0, 100.0)


def test_downbeat_toleranz():
    referenz = [10.0, 12.0, 14.0]
    assert metrics.downbeat_richtig(referenz, [10.3], beat_periode=0.5)
    assert not metrics.downbeat_richtig(referenz, [11.0], beat_periode=0.5)


def test_bpm_aus_beats():
    beats = np.arange(0.0, 8.0, 0.5)  # 120 BPM
    assert abs(metrics.bpm_aus_beats(beats) - 120.0) < 1e-6


def test_tonart_genauigkeit_exakt_und_nachbar():
    referenz = ["C", "Am", "G", "F#m"]
    schaetzung = ["C", "C", "G", "F#m"]  # Am vs. C: gleiche Vorzeichen, aber anderer Code
    ergebnis = metrics.tonart_genauigkeit(referenz, schaetzung)
    assert ergebnis.exakt == 3
    # Am (8A) und C (8B) sind Camelot-Nachbarn -> zaehlt als Nachbar-Treffer
    assert ergebnis.nachbar == 4
