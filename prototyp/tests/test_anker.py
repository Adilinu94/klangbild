"""Raster-Anker: Taktphase (die Eins einen oder mehrere Schlaege neben dem Raster)."""

import numpy as np

from klangbild import anker

RATE = 22050


def _drums(kick_auf: int, takte: int = 24, schlag: float = 0.5) -> np.ndarray:
    """Kick (60 Hz, kurz) auf jedem Schlag sehr leise, auf Schlag `kick_auf` (0..3) jedes Takts laut."""
    y = np.zeros(int(takte * 4 * schlag * RATE) + RATE)
    t = np.arange(int(0.08 * RATE)) / RATE
    ton = np.sin(2 * np.pi * 60 * t) * np.exp(-t * 40)
    for k in range(takte * 4):
        i = int(k * schlag * RATE)
        y[i:i + len(ton)] += ton * (1.0 if k % 4 == kick_auf else 0.03)
    return y


def test_taktphase_findet_die_verschobene_eins():
    db = np.arange(24) * 2.0
    assert anker.taktphase(_drums(3), RATE, db)[0] == 3       # Eins liegt auf "Schlag 4" des Rasters
    assert anker.taktphase(_drums(0), RATE, db)[0] == 0


def test_taktphase_laesst_four_on_the_floor_in_ruhe():
    y = _drums(0)
    t = np.arange(int(0.08 * RATE)) / RATE
    ton = np.sin(2 * np.pi * 60 * t) * np.exp(-t * 40)
    for k in range(24 * 4):   # alle Kicks gleich laut
        i = int(k * 0.5 * RATE)
        y[i:i + len(ton)] = ton
    assert anker.taktphase(y, RATE, np.arange(24) * 2.0)[0] == 0
