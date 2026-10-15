"""Stems just in time im Uebergangsfenster (Phase 2, ADR-018).

Demucs `htdemucs` trennt nur das Fenster, das ein Stem-Uebergang braucht (die
Blende von A und von B), nicht den ganzen Song. Gemessen auf dem Entwicklungs-PC:
~1,4x Echtzeit auf der CPU.

Demucs laeuft in einem **eigenen Prozess**: im selben Prozess sperrt torch den
GIL bis ~90 ms am Stueck, das liesse den Audio-Callback aussetzen. Der Prozess
laeuft mit niedriger Prioritaet und halben Kernen, damit Wiedergabe und
Oberflaeche Luft haben.

Rest-Trick: Original minus Summe der Stems wird zu "other" addiert. Alle Stems
auf 1 ergeben dann exakt das Original, der Wechsel Original <-> Stems ist unhoerbar.
Ergebnisse liegen als float16-npz im Cache (Schluessel = Track + Fensterlage).

Lizenz: Demucs-Code MIT; die htdemucs-Gewichte (HuggingFace adefossez/HTDemucs)
nennen keine Lizenz -> fuer den lokalen Prototyp ok, vor Auslieferung klaeren.
"""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from . import config

RATE = config.ABTASTRATE_HOERTEST
NAMEN = ("drums", "bass", "other", "vocals")
CACHE = config.CACHE / "stems"
_POOL: ProcessPoolExecutor | None = None
_SEP = None


def verfuegbar() -> bool:
    try:
        import demucs.api  # noqa: F401
    except ImportError:
        return False
    return True


_GERAET: str | None = None


def geraet() -> str:
    """"cuda", wenn eine NVIDIA-Grafikkarte mit CUDA-torch da ist, sonst "cpu" (einmal ermittelt)."""
    global _GERAET
    if _GERAET is None:
        try:
            import torch

            _GERAET = "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            _GERAET = "cpu"
    return _GERAET


# Sekunden Rechenzeit je Sekunde Audio (gemessen: CPU ~2,3x bei halben Kernen)
FAKTOR = {"cpu": 2.6, "cuda": 0.05}   # RTX 2070: 0,033 gemessen, plus Prozess-Overhead


def bedarf_s(samples: int) -> float:
    """Geschaetzte Trennzeit (s) fuer `samples` Audio plus Modell-Ladezeit."""
    return 0.0 if samples <= 0 else FAKTOR[geraet()] * samples / RATE + 15.0


def bereit(schluessel: str, cache: Path | None = None) -> bool:
    """Liegt das Fenster schon im Cache oder im Vorrat?"""
    if ((cache or CACHE) / f"{schluessel}.npz").exists():
        return True
    lage = _vorrat_schluessel(schluessel)
    return lage is not None and cache is None and _vorrat_deckt(*lage) is not None


def _init() -> None:
    global _SEP
    import torch

    if os.name == "nt":   # Demucs nachrangig: Wiedergabe und Oberflaeche gehen vor
        import ctypes

        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
    else:
        os.nice(10)
    torch.set_num_threads(max(1, (os.cpu_count() or 4) // 2))
    import demucs.api

    _SEP = demucs.api.Separator("htdemucs", device=geraet(), progress=False)


def _trenne(audio: np.ndarray) -> dict[str, np.ndarray]:
    import torch

    _, stems = _SEP.separate_tensor(torch.from_numpy(np.ascontiguousarray(audio.T)), RATE)
    return {k: v.numpy().T.astype(np.float32) for k, v in stems.items()}


def _pool() -> ProcessPoolExecutor:
    global _POOL
    if _POOL is None:
        _POOL = ProcessPoolExecutor(max_workers=1, initializer=_init)
    return _POOL


def _im_prozess(audio: np.ndarray) -> dict[str, np.ndarray]:
    return _pool().submit(_trenne, audio).result()


def _fertigstellen(audio: np.ndarray, roh: dict, datei: Path) -> dict[str, np.ndarray]:
    n = len(audio)
    stems = {k: np.asarray(roh[k], np.float32)[:n] for k in NAMEN}
    stems = {k: np.pad(v, ((0, n - len(v)), (0, 0))) for k, v in stems.items()}
    stems["other"] = stems["other"] + (audio - sum(stems.values()))   # Rest-Trick
    datei.parent.mkdir(parents=True, exist_ok=True)
    np.savez(datei, **{k: v.astype(np.float16) for k, v in stems.items()})
    _cache_begrenzen(datei.parent)
    return stems


CACHE_MAX_BYTES = 2 * 1024 ** 3   # Fenster-Cache (gedehnte Fenster ohne Vorrat): aelteste zuerst weg


def _cache_begrenzen(ordner: Path, grenze: int = CACHE_MAX_BYTES) -> None:
    dateien = sorted(ordner.glob("*.npz"), key=lambda f: f.stat().st_mtime)
    gesamt = sum(f.stat().st_size for f in dateien)
    for f in dateien:
        if gesamt <= grenze:
            break
        gesamt -= f.stat().st_size
        f.unlink(missing_ok=True)


_LAUFEND: dict[str, object] = {}   # Schluessel -> Future einer Vorrechnung


def vorrechnen(audio: np.ndarray, schluessel: str, cache: Path | None = None) -> None:
    """Trennt ein Fenster im Hintergrund in den Cache (blockiert nicht)."""
    datei = (cache or CACHE) / f"{schluessel}.npz"
    if datei.exists() or schluessel in _LAUFEND or bereit(schluessel, cache):
        return
    zukunft = _pool().submit(_trenne, audio)
    _LAUFEND[schluessel] = zukunft

    def fertig(f):
        try:
            _fertigstellen(audio, f.result(), datei)
        except Exception as fehler:  # noqa: BLE001 - Vorrechnen ist nur Beschleunigung
            print(f"Stem-Vorrechnung {schluessel} fehlgeschlagen: {fehler}", flush=True)
        finally:
            _LAUFEND.pop(schluessel, None)

    zukunft.add_done_callback(fertig)


def trennen(audio: np.ndarray, schluessel: str, trenner=_im_prozess,
            cache: Path | None = None) -> dict[str, np.ndarray]:
    """Stems eines Fensters (n, 2) -> {drums, bass, other, vocals}, Summe = Original."""
    lage = _vorrat_schluessel(schluessel)
    if lage is not None and cache is None:
        vorrat = aus_vorrat(lage[0], lage[1], audio)
        if vorrat is not None:
            return vorrat
    cache = cache or CACHE
    datei = cache / f"{schluessel}.npz"
    if datei.exists():
        try:
            with np.load(datei) as d:
                return {k: d[k].astype(np.float32) for k in NAMEN}
        except (OSError, ValueError, KeyError):
            datei.unlink(missing_ok=True)
    laufend = _LAUFEND.get(schluessel)
    if laufend is not None:   # Vorrechnung laeuft schon: auf sie warten statt doppelt rechnen
        return _fertigstellen(audio, laufend.result(), datei)
    return _fertigstellen(audio, trenner(audio), datei)


# --- Stem-Vorrat: ganze Songs vorab getrennt (Upload/Warteschlange/Bibliothek) -----------------
# Der Auto-DJ waehlt Ausstieg und Einsatz frei im Song; liegt der ganze Song als Stems vor, sind
# Stem-Uebergaenge ueberall sofort moeglich - auch nach WEITER - und das Titel-Profil (Gesang,
# Drums je Takt) faellt nebenbei ab. Speicher: Ogg Vorbis, 8 Kanaele (4 Stems stereo), ~6 MB
# je Minute (Stufe 0,3: 27 dB SNR statt 20 dB beim Standard). Codec-Fehler stoeren kaum:
# beim Lesen landet "Original minus Summe" in "other" (Rest-Trick), die Summe bleibt exakt.
VORRAT = config.CACHE / "stem_vorrat"
STUECK_S = 30.0      # je Demucs-Auftrag: dringende Fenster warten hoechstens ein Stueck ab
RAND_S = 2.0         # Ueberlappung der Stuecke, linear ueberblendet


def vorrat_bereiche(dauer_s: float) -> list[tuple[float, float]]:
    return [(0.0, dauer_s)]


def _vorrat_meta(track_id: int, cache: Path | None = None) -> Path:
    return (cache or VORRAT) / f"{track_id}.json"


def vorrat_fertig(track_id: int, cache: Path | None = None) -> bool:
    """Ganzer Song im Vorrat? (Aeltere Vorraete mit nur Kopf und Ende werden neu angelegt.)"""
    return len(_vorrat_bereiche_gespeichert(track_id, cache) or []) == 1


def _vorrat_bereiche_gespeichert(track_id: int, cache: Path | None = None) -> list | None:
    import json

    meta = _vorrat_meta(track_id, cache)
    try:
        return json.loads(meta.read_text(encoding="utf-8"))["bereiche"] if meta.exists() else None
    except (OSError, ValueError, KeyError):
        return None


def _vorrat_deckt(track_id: int, orig_s: float, n: int, cache: Path | None = None) -> int | None:
    """Index des Vorrat-Bereichs, der [orig_s, orig_s + n Samples] ganz enthaelt."""
    for i, (s, e) in enumerate(_vorrat_bereiche_gespeichert(track_id, cache) or []):
        if orig_s >= s - 1e-3 and orig_s + n / RATE <= e + 1e-3:
            return i
    return None


def _in_stuecken(x: np.ndarray, trenner) -> dict[str, np.ndarray]:
    n, st, rand = len(x), int(STUECK_S * RATE), int(RAND_S * RATE)
    if n <= st + 2 * rand:
        return {k: np.asarray(v, np.float32)[:n] for k, v in trenner(x).items()}
    aus = {k: np.zeros_like(x) for k in NAMEN}
    gewicht = np.zeros((n, 1), np.float32)
    for s in range(0, n, st):
        a, e = max(0, s - rand), min(n, s + st + rand)
        teil = trenner(x[a:e])
        w = np.ones(e - a, np.float32)
        r2 = min(2 * rand, (e - a) // 2)   # letztes Stueck kann kuerzer sein als die Ueberblendung
        if a > 0:
            w[:r2] = np.linspace(0, 1, r2, dtype=np.float32)
        if e < n:
            w[-r2:] = np.linspace(1, 0, r2, dtype=np.float32)
        for k in NAMEN:
            v = np.asarray(teil[k], np.float32)[:e - a]
            aus[k][a:a + len(v)] += v * w[:len(v), None]
        gewicht[a:e, 0] += w
    return {k: v / np.maximum(gewicht, 1e-6) for k, v in aus.items()}


def vorrat_anlegen(track_id: int, roh: np.ndarray, trenner=None, cache: Path | None = None
                   ) -> dict[str, np.ndarray]:
    """Trennt den ganzen Song `roh` (ohne Lautheitsangleich) in den Vorrat; gibt die Stems zurueck."""
    import json

    import soundfile as sf

    trenner = trenner or _im_prozess
    ordner = cache or VORRAT
    ordner.mkdir(parents=True, exist_ok=True)
    bereiche = vorrat_bereiche(len(roh) / RATE)
    for i, (s, e) in enumerate(bereiche):
        x = np.ascontiguousarray(roh[int(round(s * RATE)):int(round(e * RATE))], dtype=np.float32)
        teile = _in_stuecken(x, trenner)
        teile["other"] = teile["other"] + (x - sum(teile.values()))   # Summe = Original (Faktor beim Lesen)
        daten = np.concatenate([teile[k] for k in NAMEN], axis=1)
        # Blockweise: libsndfile (Vorbis) stuerzt bei grossen Schreibbloecken ohne Meldung ab.
        with sf.SoundFile(ordner / f"{track_id}_{i}.ogg", "w", RATE, daten.shape[1],
                          format="OGG", subtype="VORBIS", compression_level=0.3) as f:
            for k in range(0, len(daten), 16384):
                f.write(daten[k:k + 16384])
        del daten
    # Zuletzt: die Meta-Datei markiert den Vorrat als vollstaendig.
    _vorrat_meta(track_id, cache).write_text(json.dumps({"bereiche": bereiche}), encoding="utf-8")
    return teile


def aus_vorrat(track_id: int, orig_s: float, audio: np.ndarray, cache: Path | None = None
               ) -> dict[str, np.ndarray] | None:
    """Stems fuer `audio` (beginnt bei Originalsekunde orig_s) aus dem Vorrat, sonst None."""
    import soundfile as sf

    n = len(audio)
    i = _vorrat_deckt(track_id, orig_s, n, cache)
    if i is None:
        return None
    s = _vorrat_bereiche_gespeichert(track_id, cache)[i][0]
    try:
        with sf.SoundFile((cache or VORRAT) / f"{track_id}_{i}.ogg") as f:
            f.seek(max(0, int(round((orig_s - s) * RATE))))
            daten = f.read(n, dtype="float32", always_2d=True)
    except (OSError, RuntimeError):
        return None
    daten = np.pad(daten, ((0, n - len(daten)), (0, 0)))
    roh = {k: daten[:, 2 * j:2 * j + 2] for j, k in enumerate(NAMEN)}
    summe = sum(roh.values())
    # Vorrat ist ohne Lautheitsangleich getrennt; den Faktor liefert das Fenster selbst.
    g = float(np.sum(audio * summe) / max(float(np.sum(summe * summe)), 1e-12))
    stems = {k: v * np.float32(g) for k, v in roh.items()}
    stems["other"] = stems["other"] + (audio - sum(stems.values()))   # Rest-Trick
    return stems


def _vorrat_schluessel(schluessel: str) -> tuple[int, float, int] | None:
    """Schluessel "id@startsample_n" (Fenster im ungedehnten Original) -> (id, Startsekunde, n)."""
    if "@" not in schluessel:
        return None
    tid, rest = schluessel.split("@", 1)
    start, n = rest.split("_")
    return int(tid), int(start) / RATE, int(n)
