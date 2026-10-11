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


def bedarf_s(samples: int) -> float:
    """Geschaetzte Trennzeit (s) fuer `samples` Audio (gemessen ~2,3x Echtzeit bei
    niedriger Prioritaet und halben Kernen) plus Modell-Ladezeit."""
    return 0.0 if samples <= 0 else 2.6 * samples / RATE + 15.0


def bereit(schluessel: str, cache: Path | None = None) -> bool:
    """Liegt das Fenster schon im Cache?"""
    return ((cache or CACHE) / f"{schluessel}.npz").exists()


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

    _SEP = demucs.api.Separator("htdemucs", progress=False)


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
    return stems


_LAUFEND: dict[str, object] = {}   # Schluessel -> Future einer Vorrechnung


def vorrechnen(audio: np.ndarray, schluessel: str, cache: Path | None = None) -> None:
    """Trennt ein Fenster im Hintergrund in den Cache (blockiert nicht)."""
    datei = (cache or CACHE) / f"{schluessel}.npz"
    if datei.exists() or schluessel in _LAUFEND:
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
