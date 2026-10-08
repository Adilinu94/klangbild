"""Tests fuer die Lautheit (BS.1770-4) – eigene Implementierung.

Absolute Kalibrierung wird spaeter gegen libebur128/pyebur128 geprueft (ADR-012);
hier werden die Eigenschaften getestet, die ein Fehler zuerst kaputt macht:
Skalierung, Torsetzung, Stille, True Peak.
"""

from __future__ import annotations

import numpy as np

from klangbild import lufs


def _sinus(sekunden: float = 10.0, amplitude: float = 0.05, rate: int = 22050) -> np.ndarray:
    t = np.arange(int(sekunden * rate)) / rate
    return (amplitude * np.sin(2 * np.pi * 997.0 * t)).astype(np.float32)


def test_stille_ist_negativ_unendlich():
    assert lufs.integrierte_lautheit(np.zeros(22050, dtype=np.float32), 22050) == float("-inf")


def test_pegelunterschied_ist_zwanzig_lu():
    laut = _sinus(amplitude=0.2)
    leise = _sinus(amplitude=0.02)
    unterschied = lufs.integrierte_lautheit(laut, 22050) - lufs.integrierte_lautheit(leise, 22050)
    assert abs(unterschied - 20.0) < 0.2


def test_stille_bloecke_werden_ausgeblendet():
    ton = _sinus(sekunden=8.0)
    pause = np.zeros(22050 * 8, dtype=np.float32)
    zusammen = np.concatenate([ton, pause])
    nur_ton = lufs.integrierte_lautheit(ton, 22050)
    mit_pause = lufs.integrierte_lautheit(zusammen, 22050)
    assert abs(nur_ton - mit_pause) < 0.3


def test_absolute_sanity():
    """Mono-1-kHz-Sinus bei -20 dBFS liegt in der Naehe von -20 LUFS."""
    signal = _sinus(amplitude=10 ** (-20 / 20))
    wert = lufs.integrierte_lautheit(signal, 22050)
    assert -24.0 < wert < -18.0


def test_true_peak_vollaussteuerung():
    signal = _sinus(amplitude=0.999)
    assert abs(lufs.true_peak_dbtp(signal, 22050) - 0.0) < 0.3
