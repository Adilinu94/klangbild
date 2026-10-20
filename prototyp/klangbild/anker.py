"""Raster-Anker: das Beat-Raster jedes Songs auf seine echten Drum-Anschlaege setzen (nach Runde 14).

Beat This! legt das Raster bei manchen Songs einen halben Schlag (Offbeat) oder 25-80 ms neben die Kicks:
gemessen an 85 Titeln aus Hard UKG/DnB 13 um ~200 ms, 6 um 25-80 ms. Zwei solche Raster aufeinander gelegt
klingen "nicht im Takt" (Runde 14, Fall 35: The Days +77 ms -> Ride the Bass +204 ms, Note 1).

Messung: Anschlagstaerke der Drum-Spur (Kick < 100 Hz plus Snare-Koerper 150-400 Hz) auf die Beats gefaltet
(192 Stufen je Schlag); die Spitze der Faltung ist der Versatz. Liegt sie um einen halben Schlag daneben, ist
offen, ob die Eins davor oder danach liegt: dort, wo die Kick stark und die Snare (1,5-5 kHz) schwach ist.

Taktphase (nach Runde 16): Beat This! setzt bei manchen Songs die Eins einen oder zwei Schlaege daneben
(Ride the Bass, Wouldn't Believe: staerkste Kick auf Schlag 4; VOLCA: auf Schlag 3). Der Versatz oben findet
nur Fehler bis zu einem halben Schlag. Die Eins ist der Schlag mit dem staerksten Kick-Anschlag im Takt
(Drops, Crashes und die Kick auf der Eins); deutlich staerker als die bisherige Eins -> das Raster um so
viele Schlaege verschieben (im Versatz enthalten).

Fein-Anker (nach Runde 18): auch mit festem Versatz liegt das Raster abschnittsweise 20-45 ms neben den Kicks
(Arachnids -40 ms vorn, +38 ms hinten; Love Me Less +27 ms am Drop). Ein Double Drop legte so zwei Kick-Zuege
versetzt uebereinander (5 von 13 fielen durch die Kick-Kontrolle). `fein` misst dieselbe Faltung in Fenstern von
+-FEIN_S gegen das fertige Taktraster; `uebergang.taktraster` legt die Knoten auf `regulaer`.

    python -m klangbild anker    # alle Titel mit Stem-Vorrat; Profile der verschobenen Titel neu

Cache: cache/anker.json {"werte": {id: Versatz in s}, "fein": {id: [[t, dt], ...]}}; angewendet in
mixer.bibliothek_laden (Downbeats + Versatz, Eintrag.fein).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from . import config

CACHE = config.CACHE / "anker.json"
VERSION = 2           # 2: mit Taktphase
STUFEN = 192          # je Schlag
MIN_S = 0.012         # darunter: Messgenauigkeit von Beat This!, nichts verschieben
KLAR_MIN = 1.25       # Spitze / Median der Faltung; darunter kein klares Muster
# Kick auf einem anderen Schlag mindestens doppelt so stark wie auf der Eins und 1,5-mal staerker als auf allen
# uebrigen Schlaegen: an 67 UKG/DnB-Titeln 7 so verschoben; Uebergaenge mit ihnen 2,86 (n = 49) gegen 3,26 (n = 211)
PHASE_MIN, PHASE_VOR = 2.0, 1.5
HOP = 64
FEIN_S, FEIN_SCHRITT = 8.0, 4.0   # Halbbreite des Fensters, Abstand der Knoten (s)
FEIN_MAX, FEIN_MAX_S = 0.15, 0.06  # Schlaege bzw. s; mehr ist kein Feinfehler (halber Schlag/Taktphase: `versatz`)


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
    i, klar = _faltung(f[ok], (ph + 0.5) % 1.0 - 0.5)
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


def _faltung(f: np.ndarray, ph: np.ndarray) -> tuple[int, float]:
    """(Spitze der Faltung in Stufen, Klarheit): Anschlagstaerke f je Phase ph (-0,5..0,5 Schlag)."""
    h, _ = np.histogram(ph, bins=STUFEN, range=(-0.5, 0.5), weights=f ** 2)
    glatt = np.hanning(7) / np.hanning(7).sum()
    h = np.convolve(np.r_[h[-3:], h, h[:3]], glatt, "valid")
    i = int(np.argmax(h))
    return i, float(h[i] / max(np.median(h), 1e-12))


def fein(drums: np.ndarray, rate: int, raster: np.ndarray) -> list[list[float]]:
    """[[t, dt], ...]: um dt liegen die Anschlaege um t (Fenster +-FEIN_S) hinter dem Taktraster `raster`.
    Nur Fenster mit klarem Muster und |dt| <= FEIN_MAX Schlag/FEIN_MAX_S (Halbtempo-Titel: ein Schlag ist dort lang);
    Ausreisser per Median aus fuenf Knoten, auch am Rand (Outros: einzelne Fenster bis -67 ms).
    Leer, wenn nirgends mehr als MIN_S daneben."""
    if drums.ndim > 1:
        drums = drums.mean(axis=1)
    raster = np.asarray(raster, float)
    if len(raster) < 4:
        return []
    beats = np.interp(np.arange(4 * (len(raster) - 1) + 1) / 4, np.arange(len(raster)), raster)
    f = _anschlag(drums, rate, 0, 100) + _anschlag(drums, rate, 150, 400)
    t = np.arange(len(f)) * HOP / rate
    k = np.searchsorted(beats, t) - 1
    ok = (k >= 0) & (k < len(beats) - 1)
    t, f, k = t[ok], f[ok], k[ok]
    if not len(t):
        return []
    ph = ((t - beats[k]) / (beats[k + 1] - beats[k]) + 0.5) % 1.0 - 0.5
    schlag = float(np.median(np.diff(beats)))
    knoten = []
    for c in np.arange(t[0], t[-1] + FEIN_SCHRITT, FEIN_SCHRITT):
        lo, hi = np.searchsorted(t, [c - FEIN_S, c + FEIN_S])
        if hi - lo < 1000:
            continue
        i, klar = _faltung(f[lo:hi], ph[lo:hi])
        dt = ((i + 0.5) / STUFEN - 0.5) * schlag
        if klar >= KLAR_MIN and abs(dt) <= min(FEIN_MAX * schlag, FEIN_MAX_S):
            knoten.append([round(float(c), 2), dt])
    y = [k[1] for k in knoten]
    for j in range(len(knoten)):
        knoten[j][1] = float(np.median(y[max(0, j - 2):j + 3]))
    if not knoten or max(abs(k[1]) for k in knoten) < MIN_S:
        return []
    return [[c, round(dt, 4)] for c, dt in knoten]


def _kick_fluss(drums: np.ndarray, rate: int) -> tuple[np.ndarray, np.ndarray]:
    """(Zeiten, Kick-Fluss): spektraler Anstieg 30-100 Hz (STFT, 6 ms Schritt)."""
    from scipy.signal import stft

    f, t, z = stft(drums, rate, nperseg=1024, noverlap=1024 - 256)
    m = np.log1p(100 * np.abs(z[(f >= 30) & (f < 100)]))
    return t, np.maximum(0, np.diff(m, axis=1, prepend=m[:, :1])).sum(axis=0)


def taktphase(drums: np.ndarray, rate: int, downbeats: np.ndarray) -> tuple[int, np.ndarray]:
    """(p, Kick je Schlag): die echte Eins liegt p Schlaege nach dem Raster (0 = passt). Kick-Fluss je
    Schlagposition (Spitze +-30 ms, gemittelt ueber alle Takte); p nur, wenn dort klar staerker (PHASE_MIN/VOR)."""
    if drums.ndim > 1:
        drums = drums.mean(axis=1)
    db = np.asarray(downbeats, float)
    if len(db) < 8:
        return 0, np.ones(4)
    t, k = _kick_fluss(drums, rate)
    w = int(0.03 / (t[1] - t[0])) + 1
    stark = np.zeros(4)
    for b in range(4):
        i = np.searchsorted(t, db[:-1] + np.diff(db) * b / 4)
        i = i[(i > w) & (i < len(t) - w)]
        stark[b] = np.mean([k[j - w:j + w].max() for j in i]) if len(i) else 0.0
    p = int(np.argmax(stark))
    klar = p and stark[p] >= PHASE_MIN * max(stark[0], 1e-9) and stark[p] >= PHASE_VOR * np.delete(stark, p).max()
    return (p if klar else 0), stark


def laden(pfad: Path = CACHE) -> dict[int, float]:
    try:
        roh = json.loads(pfad.read_text(encoding="utf-8"))
        return {int(k): float(v) for k, v in roh["werte"].items()} if roh.get("version") == VERSION else {}
    except (OSError, ValueError, KeyError):
        return {}


def fein_laden(pfad: Path = CACHE) -> dict[int, list]:
    try:
        roh = json.loads(pfad.read_text(encoding="utf-8"))
        return {int(k): v for k, v in roh.get("fein", {}).items()} if roh.get("version") == VERSION else {}
    except (OSError, ValueError, KeyError):
        return {}


def _speichern(werte: dict, feine: dict) -> None:
    CACHE.write_text(json.dumps({"version": VERSION, "werte": werte, "fein": feine}), encoding="utf-8")


def anwenden(downbeats: list[float], v: float) -> list[float]:
    return [round(d + v, 4) for d in downbeats if d + v >= 0] if v else list(downbeats)


def kommando(args) -> int:
    import sqlite3

    import soundfile as sf

    from . import db, mixer, profil, stems

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
    from .uebergang import regulaer

    werte, feine = laden(), fein_laden()
    for n, (tid, x) in enumerate(sorted(bib.items())):
        datei = stems.VORRAT / f"{tid}_0.ogg"
        if not stems.vorrat_fertig(tid) or not datei.exists() or (tid in werte and tid in feine):
            continue
        with sf.SoundFile(datei) as f:
            drums = f.read(dtype="float32", always_2d=True)[:, 0:2]   # stems.NAMEN: drums zuerst
            rate = f.samplerate
        if tid not in werte:
            v, klar = versatz(drums, rate, np.asarray(beats.get(tid, [])), np.asarray(x.downbeats))
            p, _ = taktphase(drums, rate, np.asarray(anwenden(x.downbeats, v)))
            if p:   # 1-2 Schlaege spaeter, 3 = einen frueher
                v += (p if p <= 2 else p - 4) * float(np.median(np.diff(x.downbeats))) / 4
            werte[tid] = round(v, 4)
            if v:
                print(f"{tid:>5} {v * 1000:+6.0f} ms (Klarheit {klar:.1f}, Taktphase {p})  {x.titel}", flush=True)
        feine[tid] = fein(drums, rate, regulaer(anwenden(x.downbeats, werte[tid]), x.bpm, len(drums) / rate))
        if feine[tid]:
            print(f"{tid:>5} fein {min(k[1] for k in feine[tid]) * 1000:+4.0f}..{max(k[1] for k in feine[tid]) * 1000:+4.0f} ms"
                  f"  {x.titel}", flush=True)
        if n % 25 == 0:
            _speichern(werte, feine)
    _speichern(werte, feine)
    # Profile, deren Taktraster sich verschoben hat (Versatz oder Fein-Anker), neu
    neu = []
    for tid, x in sorted(bib.items()):
        x, p = mit_anker(x, werte.get(tid, 0.0), feine.get(tid, [])), profil.gespeichert(tid)
        if p is not None and not profil.passt(p, x):
            neu.append(x)
    print(f"{sum(1 for v in werte.values() if v)} von {len(werte)} Titeln verschoben, "
          f"{sum(1 for v in feine.values() if v)} mit Fein-Anker; {len(neu)} Profile neu", flush=True)
    from concurrent.futures import ProcessPoolExecutor

    with ProcessPoolExecutor(4) as pool:   # ~13 s je Profil: alle 417 Titel sonst ueber eine Stunde
        for k, _ in enumerate(pool.map(_profil_neu, neu), 1):
            if k % 25 == 0:
                print(f"{k}/{len(neu)} Profile", flush=True)
    return 0


def _profil_neu(x) -> None:
    from . import audioio, live, profil

    profil.laden(x, lambda: audioio.decodieren_stereo(x.pfad, live.RATE).daten, neu=True)


def mit_anker(x, v: float, knoten: list):
    from dataclasses import replace

    return replace(x, downbeats=anwenden(x.downbeats, v), fein=knoten)
