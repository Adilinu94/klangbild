"""Raster-Anker: das Beat-Raster jedes Songs auf seine echten Drum-Anschlaege setzen (nach Runde 14).

Beat This! legt das Raster bei manchen Songs einen halben Schlag (Offbeat) oder 25-80 ms neben die Kicks:
gemessen an 85 Titeln aus Hard UKG/DnB 13 um ~200 ms, 6 um 25-80 ms. Zwei solche Raster aufeinander gelegt
klingen "nicht im Takt" (Runde 14, Fall 35: The Days +77 ms -> Ride the Bass +204 ms, Note 1).

Messung: Anschlagstaerke der Drum-Spur (Kick < 100 Hz plus Snare-Koerper 150-400 Hz) auf die Beats gefaltet
(192 Stufen je Schlag); die Spitze der Faltung ist der Versatz. Liegt sie um einen halben Schlag daneben, ist
offen, ob die Eins davor oder danach liegt: dort, wo die Kick stark und die Snare (1,5-5 kHz) schwach ist.

    python -m klangbild anker    # alle Titel mit Stem-Vorrat; Profile der verschobenen Titel neu

Cache: cache/anker.json {id: Versatz in s}; angewendet in mixer.bibliothek_laden (Downbeats + Versatz).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from . import config

CACHE = config.CACHE / "anker.json"
VERSION = 1
STUFEN = 192          # je Schlag
MIN_S = 0.012         # darunter: Messgenauigkeit von Beat This!, nichts verschieben
KLAR_MIN = 1.25       # Spitze / Median der Faltung; darunter kein klares Muster
HOP = 64


def _anschlag(y: np.ndarray, rate: int, lo: float, hi: float) -> np.ndarray:
    from scipy.signal import butter, sosfilt

    sos = butter(4, hi, "low", fs=rate, output="sos") if not lo else butter(4, [lo, hi], "band", fs=rate, output="sos")
    z = sosfilt(sos, y)
    n = len(z) // HOP * HOP
    e = np.sqrt((z[:n] ** 2).reshape(-1, HOP).mean(axis=1) + 1e-12)
    return np.maximum(0.0, np.diff(np.log(e + 1e-4), prepend=0.0))


def _staerke(x: np.ndarray, t: np.ndarray, rate: int) -> float:
    """Mittlere Anschlagstaerke +-15 ms um die Zeitpunkte t."""
    i = np.round(np.asarray(t) * rate / HOP).astype(int)
    w = int(0.015 * rate / HOP) + 1
    i = i[(i >= w) & (i < len(x) - w)]
    return float(np.mean([x[k - w:k + w].max() for k in i])) if len(i) else 0.0


def versatz(drums: np.ndarray, rate: int, beats: np.ndarray, downbeats: np.ndarray) -> tuple[float, float]:
    """(Versatz in s, Klarheit): um so viel liegen die Anschlaege hinter dem Raster (Downbeats + Versatz =
    Anschlaege). 0, wenn kein klares Muster oder der Versatz unter MIN_S liegt."""
    beats = np.asarray(beats, float)
    if drums.ndim > 1:
        drums = drums.mean(axis=1)
    if len(beats) < 16:
        return 0.0, 0.0
    kick, snare = _anschlag(drums, rate, 0, 100), _anschlag(drums, rate, 1500, 5000)
    f = kick + _anschlag(drums, rate, 150, 400)
    t = np.arange(len(f)) * HOP / rate
    k = np.searchsorted(beats, t) - 1
    ok = (k >= 0) & (k < len(beats) - 1)
    ph = (t[ok] - beats[k[ok]]) / (beats[k[ok] + 1] - beats[k[ok]])
    h, _ = np.histogram((ph + 0.5) % 1.0 - 0.5, bins=STUFEN, range=(-0.5, 0.5), weights=f[ok] ** 2)
    glatt = np.hanning(7) / np.hanning(7).sum()
    h = np.convolve(np.r_[h[-3:], h, h[:3]], glatt, "valid")
    i = int(np.argmax(h))
    klar = float(h[i] / max(np.median(h), 1e-12))
    schlag = float(np.median(np.diff(beats)))
    v = ((i + 0.5) / STUFEN - 0.5) * schlag
    if klar < KLAR_MIN or abs(v) < MIN_S:
        return 0.0, klar
    if abs(v) > 0.3 * schlag:   # halber Schlag daneben: Eins davor oder danach? Kick stark, Snare schwach
        db = np.asarray(downbeats, float)
        andere = v - np.sign(v) * schlag

        def eins(s):
            return _staerke(kick, db + s, rate) - _staerke(snare, db + s, rate)

        if eins(andere) > eins(v):
            v = andere
    return float(v), klar


def laden(pfad: Path = CACHE) -> dict[int, float]:
    try:
        roh = json.loads(pfad.read_text(encoding="utf-8"))
        return {int(k): float(v) for k, v in roh["werte"].items()} if roh.get("version") == VERSION else {}
    except (OSError, ValueError, KeyError):
        return {}


def anwenden(downbeats: list[float], v: float) -> list[float]:
    return [round(d + v, 4) for d in downbeats] if v else list(downbeats)


def kommando(args) -> int:
    import sqlite3

    import soundfile as sf

    from . import audioio, db, live, mixer, profil, stems

    e = config.vorbereiten(config.aus_argumenten(args))
    conn = db.verbinden(e.datenbank)
    try:
        bib = mixer.bibliothek_laden(conn, e.analyse_version, anker_an=False)
        beats = {int(z["track_id"]): json.loads(z["beats_json"] or "[]") for z in conn.execute(
            "SELECT track_id, beats_json FROM features WHERE analyse_version=?", (e.analyse_version,))}
    except sqlite3.Error as fehler:
        print(fehler)
        return 1
    finally:
        conn.close()
    werte = laden()
    alt = dict(werte)
    for n, (tid, x) in enumerate(sorted(bib.items())):
        datei = stems.VORRAT / f"{tid}_0.ogg"
        if not stems.vorrat_fertig(tid) or not datei.exists() or tid in werte:
            continue
        with sf.SoundFile(datei) as f:
            drums = f.read(dtype="float32", always_2d=True)[:, 0:2]   # stems.NAMEN: drums zuerst
        v, klar = versatz(drums, f.samplerate, np.asarray(beats.get(tid, [])), np.asarray(x.downbeats))
        werte[tid] = round(v, 4)
        if v:
            print(f"{tid:>5} {v * 1000:+6.0f} ms (Klarheit {klar:.1f})  {x.titel}", flush=True)
        if n % 25 == 0:
            CACHE.write_text(json.dumps({"version": VERSION, "werte": werte}), encoding="utf-8")
    CACHE.write_text(json.dumps({"version": VERSION, "werte": werte}), encoding="utf-8")
    # Profile der verschobenen Titel neu (ihr Taktraster hat sich verschoben)
    neu = [tid for tid, v in werte.items() if v and alt.get(tid) != v and tid in bib]
    print(f"{sum(1 for v in werte.values() if v)} von {len(werte)} Titeln verschoben; {len(neu)} Profile neu", flush=True)
    for tid in neu:
        x = replace_downbeats(bib[tid], werte[tid])
        profil.laden(x, lambda x=x: audioio.decodieren_stereo(x.pfad, live.RATE).daten, neu=True)
    return 0


def replace_downbeats(x, v: float):
    from dataclasses import replace

    return replace(x, downbeats=anwenden(x.downbeats, v))
