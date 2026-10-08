"""Tests fuer Energie-Kurve und Struktur."""

from __future__ import annotations

import numpy as np

from klangbild import energy


def _sinus(amplitude: float, sekunden: float = 10.0, rate: int = 22050) -> np.ndarray:
    t = np.arange(int(sekunden * rate)) / rate
    return (amplitude * np.sin(2 * np.pi * 220.0 * t)).astype(np.float32)


def test_rms_unterschied_ist_zwanzig_db():
    _, leise = energy.rms_kurve(_sinus(0.02), 22050)
    _, laut = energy.rms_kurve(_sinus(0.2), 22050)
    assert abs(float(laut.mean() - leise.mean()) - 20.0) < 0.5


def test_rms_bleibt_im_rahmen():
    _, werte = energy.rms_kurve(_sinus(0.1), 22050)
    assert werte.min() >= -80.0 and werte.max() <= 0.0


def test_neuheits_kurve_hat_gleiche_laenge():
    zeiten, neuheit = energy.neuheits_kurve(_sinus(0.2), 22050)
    assert len(zeiten) == len(neuheit)


def test_abschnitte_bei_texturwechsel():
    rate = 22050
    ruhig = _sinus(0.1, sekunden=8.0)
    rng = np.random.default_rng(0)
    rausch = (0.3 * rng.standard_normal(rate * 8)).astype(np.float32)
    stueck = np.concatenate([ruhig, rausch])
    grenzen = energy.abschnitte(stueck, rate, mindest_abstand_sekunden=4.0)
    assert isinstance(grenzen, list)
