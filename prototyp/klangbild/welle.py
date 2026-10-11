"""Farbige Wellenform wie Serato/VirtualDJ: Bass rot, Mitten gruen, Hoehen blau.

Serato beschreibt es so: Bass raus -> kein Rot, Hoehen raus -> kein Blau, Mitten
raus -> kein Gruen. Die Mischfarben (Bass + Mitten = gelb/orange) ergeben sich
von selbst. Umsetzung: STFT (1024er Hann-Fenster, ~100 Spalten/s auf 22,05 kHz
Mono), Energie je Band (< 200 Hz, 200-2000 Hz, > 2000 Hz), alle Baender mit
einem gemeinsamen Bezug. Die Farbe ergibt sich aus dem Verhaeltnis der Baender
(die Oberflaeche normiert auf das staerkste). Hoehe = Spitzenwert je Spalte.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from . import audioio, config

CACHE = config.CACHE / "welle"
RATE = config.ABTASTRATE_ANALYSE
HOP = 220                     # ~100,2 Spalten je Sekunde
FENSTER = 1024
GRENZEN_HZ = (200.0, 2000.0)


def berechnen(mono: np.ndarray, rate: int = RATE) -> dict[str, np.ndarray]:
    """Spalten (uint8): peak, r (Bass), g (Mitten), b (Hoehen)."""
    x = np.asarray(mono, dtype=np.float32).reshape(-1)
    if x.size < FENSTER:
        x = np.pad(x, (0, FENSTER - x.size))
    n = 1 + (x.size - FENSTER) // HOP
    rahmen = np.lib.stride_tricks.sliding_window_view(x, FENSTER)[::HOP][:n]
    spektrum = np.abs(np.fft.rfft(rahmen * np.hanning(FENSTER).astype(np.float32), axis=1)) ** 2
    frequenzen = np.fft.rfftfreq(FENSTER, 1.0 / rate)
    tief, hoch = GRENZEN_HZ
    baender = [spektrum[:, (frequenzen >= lo) & (frequenzen < hi)].sum(axis=1)
               for lo, hi in ((20.0, tief), (tief, hoch), (hoch, rate / 2))]
    amps = [np.sqrt(band) for band in baender]
    # Ein gemeinsamer Bezug fuer alle Baender (nicht je Band): so bleiben die echten
    # Verhaeltnisse erhalten - Bass-Passagen werden rot/orange, Mitten gruen/gelb,
    # wie bei Serato. Je Band normiert waere fast alles gruen/tuerkis (verglichen
    # an echten Tracks: 18 % statt 32 % der Spalten bass-dominant).
    bezug = float(np.percentile(np.max(amps, axis=0), 99)) or 1.0
    aus = {name: np.clip(a / bezug * 255, 0, 255).astype(np.uint8) for name, a in zip("rgb", amps)}
    peak = np.abs(rahmen).max(axis=1)
    aus["peak"] = np.clip(peak / (float(np.percentile(peak, 99.5)) or 1.0) * 255, 0, 255).astype(np.uint8)
    return aus


def laden(track_id: int, pfad: str | Path, cache: Path | None = None) -> dict:
    """Wellenform aus dem Cache bzw. neu berechnet; als JSON-taugliches dict."""
    cache = cache or CACHE
    datei = cache / f"{track_id}.npz"
    if datei.exists():
        with np.load(datei) as d:
            spalten = {k: d[k] for k in ("peak", "r", "g", "b")}
    else:
        spalten = berechnen(audioio.decodieren(pfad, RATE).daten)
        cache.mkdir(parents=True, exist_ok=True)
        np.savez(datei, **spalten)
    return {"spalten_pro_s": RATE / HOP, **{k: v.tolist() for k, v in spalten.items()}}
