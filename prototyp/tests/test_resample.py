"""Tests fuer resample.py - die Vinyl-Tempoangleich (ADR-014, Gate ADR-020).

Geprueft wird die Mathe, die ein Fehler zuerst kaputt macht: Richtung des
Faktors, die +-1 %-Klemme, exakte Laengen- und Tonhoehen-Aenderung der
linearen Referenz sowie die Gleichwertigkeit von soxr und linear im Raster.
"""

from __future__ import annotations

import numpy as np

from klangbild import resample


def _sinus(frequenz: float, sekunden: float = 1.0, rate: int = 22050) -> np.ndarray:
    t = np.arange(int(sekunden * rate)) / rate
    return (0.5 * np.sin(2 * np.pi * frequenz * t)).astype(np.float32)


def _dominante_frequenz(signal: np.ndarray, rate: int) -> float:
    if signal.size < 4:
        return 0.0
    spektrum = np.abs(np.fft.rfft(signal * np.hanning(signal.size)))
    return float(np.fft.rfftfreq(signal.size, 1.0 / rate)[int(np.argmax(spektrum))])


# --- Taktfaktor und Klemmung -------------------------------------------------


def test_faktor_richtung_und_klemmung():
    assert resample.tempo_faktor(100.0, 120.0) > 1.0      # schneller werden
    assert resample.tempo_faktor(120.0, 100.0) < 1.0      # langsamer werden
    assert resample.tempo_faktor(100.0, 100.0) == 1.0
    # +-1 %-Klemme (ADR-020): 100 -> 120 waere +20 %, wird auf 1.01 geklemmt.
    assert abs(resample.tempo_faktor(100.0, 120.0) - 1.01) < 1e-9
    assert abs(resample.tempo_faktor(100.0, 80.0) - 0.99) < 1e-9


def test_faktor_unplausible_tempi_sind_neutral():
    assert resample.tempo_faktor(0.0, 120.0) == 1.0
    assert resample.tempo_faktor(120.0, 0.0) == 1.0
    assert resample.tempo_faktor(-5.0, 120.0) == 1.0


def test_tempo_passt_respektiert_grenze():
    assert resample.tempo_passt(100.0, 101.0) is True
    assert resample.tempo_passt(100.0, 101.1) is False
    assert resample.tempo_passt(100.0, 99.0) is True
    assert resample.tempo_passt(0.0, 120.0) is False


# --- Laenge und Tonhoehe der linearen Referenz -------------------------------


def test_resample_linear_halbiert_laenge_bei_faktor_zwei():
    x = _sinus(440.0, sekunden=2.0)
    y = resample.resample_linear(x, 2.0)
    assert abs(len(y) - len(x) / 2) <= 1
    assert abs(resample.schrittzeit(1.0, 2.0) - 0.5) < 1e-9


def test_resample_linear_verdoppelt_tonhoehe_bei_faktor_zwei():
    rate = 22050
    x = _sinus(500.0, sekunden=1.0, rate=rate)
    y = resample.resample_linear(x, 2.0)
    dom = _dominante_frequenz(y, rate)
    assert 900.0 < dom < 1100.0                       # ~1000 Hz = doppelt


def test_resample_faktor_eins_ist_identisch():
    x = _sinus(440.0)
    y = resample.resample_linear(x, 1.0)
    assert np.array_equal(x, y)


def test_resample_leer_bleibt_leer():
    assert resample.resample_linear(np.zeros(0, np.float32), 2.0).size == 0


# --- Gleichwertigkeit der Kern-Methoden im Raster ----------------------------


def test_soxr_faellt_ohne_soxr_auf_linear_zurueck_und_bleibt_im_raster():
    """Ohne soxr (oder mit) muss die Laenge der Vinyl-Mathematik folgen."""
    rate = 22050
    x = _sinus(440.0, sekunden=1.0, rate=rate)
    y = resample.resample_soxr(x, rate, 1.5)
    erwartet = len(x) / 1.5
    assert abs(len(y) - erwartet) <= max(2, int(0.01 * erwartet))


def test_resample_methode_linear_ist_standard():
    x = _sinus(440.0)
    assert np.array_equal(resample.resample(x, 22050, 1.0), x)


def test_resample_stereo_je_kanal():
    x = np.stack([np.arange(100, dtype=np.float32), -np.arange(100, dtype=np.float32)], axis=1)
    y = resample.resample(x, 22050, 2.0)
    assert y.shape == (50, 2)
    assert np.allclose(y[:, 0], -y[:, 1])
