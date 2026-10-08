"""Energie-Kurve und Struktur (Neuheits-Kurve) – eigene Implementierung.

Aus ADR-012: Energie und Abschnitte sind eigene Implementierung (RMS bzw.
Neuheits-Kurve). Der Auto-DJ braucht beides, um die Energie-Reise zu planen und
den Uebergang vor einen Drop zu setzen. Fuer Phase 1 genuegt die Energie-Kurve;
die Struktur ist die Vorarbeit fuer spaeter.
"""

from __future__ import annotations

import numpy as np


def _gleitende_summe(werte: np.ndarray, fenster: int) -> np.ndarray:
    """Summe ueber gleitende Fenster in O(n) (Praefixsummen, kein convolve)."""
    fenster = max(1, min(fenster, len(werte)))
    kumuliert = np.concatenate(([0.0], np.cumsum(werte, dtype=np.float64)))
    return kumuliert[fenster:] - kumuliert[:-fenster]


def rms_kurve(
    signal: np.ndarray,
    samplerate: int,
    fenster_sekunden: float = 1.0,
    hop_sekunden: float = 0.5,
) -> tuple[np.ndarray, np.ndarray]:
    """Energie-Kurve (RMS in dBFS) ueber die Zeit.

    Liefert (zeiten, werte_db). Stille wird auf -80 dB begrenzt, damit sich
    spaetere Log-Operationen nicht in -inf verlieren.
    """
    if signal.size == 0:
        return np.zeros(0), np.zeros(0)
    fenster = max(1, int(fenster_sekunden * samplerate))
    hop = max(1, int(hop_sekunden * samplerate))
    anzahl = 1 + max(0, len(signal) - fenster) // hop
    quadrate = signal.astype(np.float64) ** 2
    summe = _gleitende_summe(quadrate, min(fenster, len(quadrate)))
    stellen = np.arange(anzahl) * hop
    mittel = np.maximum(summe[stellen] / fenster, 1e-12)
    werte = 10.0 * np.log10(mittel)
    werte = np.clip(werte, -80.0, 0.0)
    zeiten = (stellen + fenster / 2.0) / samplerate
    return zeiten, werte


def _merkmale(signal: np.ndarray, samplerate: int, frame: int = 2048, hop: int = 1024) -> np.ndarray:
    """Log-Mel-aehnliche Merkmale je Frame, L2-normalisiert (fuer die Aehnlichkeitsmatrix)."""
    if len(signal) < frame:
        signal = np.pad(signal, (0, frame - len(signal)))
    fenster = np.hanning(frame).astype(np.float32)
    anzahl = 1 + (len(signal) - frame) // hop
    anzahl = max(1, anzahl)
    spektren = np.empty((anzahl, frame // 2 + 1), dtype=np.float32)
    for index in range(anzahl):
        start = index * hop
        block = signal[start:start + frame]
        if len(block) < frame:
            block = np.pad(block, (0, frame - len(block)))
        spektren[index] = np.abs(np.fft.rfft(block * fenster))
    # grobe Mel-Baender: 32 logarithmisch verteilte Baender
    grenzen = np.geomspace(40.0, samplerate / 2.0, 33)
    frequenzen = np.fft.rfftfreq(frame, 1.0 / samplerate)
    baender = np.empty((anzahl, 32), dtype=np.float32)
    for band in range(32):
        maske = (frequenzen >= grenzen[band]) & (frequenzen < grenzen[band + 1])
        baender[:, band] = spektren[:, maske].mean(axis=1) if np.any(maske) else 0.0
    baender = np.log1p(baender)
    normen = np.linalg.norm(baender, axis=1, keepdims=True)
    return baender / np.maximum(normen, 1e-9)


def neuheits_kurve(
    signal: np.ndarray,
    samplerate: int,
    kern_sekunden: float = 8.0,
    hop: int = 1024,
) -> tuple[np.ndarray, np.ndarray]:
    """Foote-Neuheit: Selbstaehnlichkeit der Merkmale, dann Schachbrett-Kern.

    Liefert (zeiten, neuheit). Hohe Werte markieren Abschnittsgrenzen.
    """
    merkmale = _merkmale(signal, samplerate, hop=hop)
    aehnlichkeit = merkmale @ merkmale.T
    np.fill_diagonal(aehnlichkeit, 0.0)
    rahmen_hop = hop / samplerate
    halb = max(1, int(kern_sekunden / 2.0 / rahmen_hop))
    kern = np.ones((2 * halb, 2 * halb), dtype=np.float32)
    kern[:halb, :halb] = -1.0
    kern[halb:, halb:] = -1.0

    n = aehnlichkeit.shape[0]
    neuheit = np.zeros(n, dtype=np.float32)
    for index in range(halb, n - halb):
        fenster = aehnlichkeit[index - halb:index + halb, index - halb:index + halb]
        neuheit[index] = float((fenster * kern).sum())
    zeiten = np.arange(n) * rahmen_hop
    return zeiten, neuheit


def abschnitte(
    signal: np.ndarray,
    samplerate: int,
    mindest_abstand_sekunden: float = 10.0,
    schwelle_anteil: float = 0.6,
) -> list[float]:
    """Abschnittsgrenzen aus der Neuheits-Kurve (einfaches Peak-Picking)."""
    zeiten, neuheit = neuheits_kurve(signal, samplerate)
    if neuheit.size == 0:
        return []
    positiv = neuheit - neuheit.min()
    spitze = positiv.max()
    if spitze <= 0:
        return []
    schwelle = schwelle_anteil * spitze
    grenzen: list[float] = []
    letzte = -1e9
    for index in range(1, len(positiv) - 1):
        if positiv[index] < schwelle:
            continue
        if positiv[index] < positiv[index - 1] or positiv[index] < positiv[index + 1]:
            continue
        if zeiten[index] - letzte < mindest_abstand_sekunden:
            continue
        grenzen.append(float(zeiten[index]))
        letzte = zeiten[index]
    return grenzen
