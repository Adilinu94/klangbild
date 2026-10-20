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


def test_fein_findet_den_abschnittsweisen_versatz_und_taktraster_legt_ihn_auf():
    from klangbild import uebergang

    schlag, takte = 0.5, 64           # 120 BPM, 128 s: erste Haelfte auf dem Raster, zweite 30 ms spaeter
    y = np.zeros(int(takte * 4 * schlag * RATE) + RATE)
    t = np.arange(int(0.08 * RATE)) / RATE
    ton = np.sin(2 * np.pi * 60 * t) * np.exp(-t * 40)
    for k in range(takte * 4):
        i = int((k * schlag + (0.03 if k >= takte * 2 else 0.0)) * RATE)
        y[i:i + len(ton)] += ton
    raster = np.arange(takte + 1) * 4 * schlag
    knoten = anker.fein(y, RATE, raster)
    assert len(knoten) > 10
    assert abs(np.interp(20, *np.array(knoten).T)) < 0.004 and abs(np.interp(110, *np.array(knoten).T) - 0.03) < 0.004
    e = uebergang.Eintrag(id=1, pfad="x.mp3", bpm=120.0, camelot=None, downbeats=list(raster), fein=knoten)
    r = uebergang.taktraster(e, 128.0)
    assert abs(r[10] - raster[10]) < 0.004 and abs(r[55] - raster[55] - 0.03) < 0.004
    assert anker.fein(np.zeros_like(y), RATE, raster) == []
