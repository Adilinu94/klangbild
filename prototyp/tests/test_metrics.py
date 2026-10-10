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


def test_bpm_aus_beats_leer_und_einzeln():
    assert metrics.bpm_aus_beats([]) == 0.0
    assert metrics.bpm_aus_beats([1.0]) == 0.0


def test_bpm_aus_beats_128_mit_20ms_jitter_trifft_128():
    # Der Kern-Bug: Beat This! quantelt auf 20 ms (50 fps). Der Median klebt an
    # einer Stufe und lief bis ~2 % daneben; der Mittelwert ueber das Haupt-
    # Cluster mittelt die +-10-ms-Quantelung heraus und muss 128,0 +- 0,1 treffen.
    rng = np.random.default_rng(1234)
    periode = 60.0 / 128.0                       # echte Beat-Periode
    n = 64                                        # ~30 s Musik
    echte = np.arange(n) * periode
    # auf 20-ms-Raster quanteln (wie Beat This!) mit symmetrischem Jitter davor
    jitter = rng.uniform(-0.01, 0.01, size=n)
    gerastert = np.round((echte + jitter) / 0.02) * 0.02
    assert abs(metrics.bpm_aus_beats(gerastert) - 128.0) < 0.1


def test_bpm_aus_beats_ignoriert_oktav_ausreisser():
    # Ein fehlender und ein doppelter Einschlag erzeugen 2x- bzw. 0,5x-Abstaende.
    # Sie duerfen das Tempo nicht reissen (Haupt-Cluster haelt die Wahrheit).
    basis = np.arange(0.0, 8.0, 0.5)             # 120 BPM
    ausreisser = np.array([basis[-1] + 1.0,       # Luecke: 2x-Periode
                           basis[-1] + 1.25])     # halbe Periode
    beats = np.concatenate([basis, ausreisser])
    assert abs(metrics.bpm_aus_beats(beats) - 120.0) < 0.5


def test_tonart_genauigkeit_exakt_und_nachbar():
    referenz = ["C", "Am", "G", "F#m"]
    schaetzung = ["C", "C", "G", "F#m"]  # Am vs. C: gleiche Vorzeichen, aber anderer Code
    ergebnis = metrics.tonart_genauigkeit(referenz, schaetzung)
    assert ergebnis.exakt == 3
    # Am (8A) und C (8B) sind Camelot-Nachbarn -> zaehlt als Nachbar-Treffer
    assert ergebnis.nachbar == 4
