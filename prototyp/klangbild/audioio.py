"""Audiodateien lesen, Raten wandeln, Ausschnitte schneiden.

Regel (ADR-012, Roadmap Phase 1): **einmal dekodieren**, dann die zwei benoetigten
Raten teilen – 22,05 kHz fuer die Schlaganalyse, 16 kHz fuer die Einbettung.
Doppelte Resampling-Ketten Verschieben die Ergebnisse, ohne dass man es hoert.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:
    import soundfile as sf
except ImportError as aufruf:  # pragma: no cover - nur zur Laufzeit relevant
    sf = None
    _IMPORT_FEHLER = aufruf

try:
    import soxr
except ImportError as aufruf:  # pragma: no cover
    soxr = None
    _SOXR_FEHLER = aufruf

from . import config


class Lesefehler(RuntimeError):
    pass


@dataclass(frozen=True)
class Audio:
    """Mono-Signal als float32 im Bereich [-1, 1]."""

    daten: np.ndarray
    rate: int

    @property
    def sekunden(self) -> float:
        return len(self.daten) / float(self.rate)


def _pruefe_abhaengigkeiten() -> None:
    if sf is None:
        raise Lesefehler(
            "soundfile fehlt. Installation: python -m pip install soundfile "
            f"(Ursache: {_IMPORT_FEHLER})"
        )


def decodieren_stereo(pfad: str | Path, ziel_rate: int) -> Audio:
    """Liest eine Datei als **Stereo (Kanaele erhalten)** und wandelt nur die Rate.

    Fuer den Hoertest-Render (autodj): der Mix soll in Originalqualitaet und mit
    Stereobild entstehen, nicht als Analyse-Mono. Die Zeitpunkte (Sekunden) sind
    ratenunabhaengig und lassen sich direkt auf das Downbeat-Raster uebertragen.

    Rueckgabe: `Audio.daten` ist (n_samples, n_channels). `soxr.resample`
    resampled **je Kanal** (axis=0), damit L/R getrennt bleiben.
    """
    _pruefe_abhaengigkeiten()
    pfad = Path(pfad)
    try:
        daten, rate = sf.read(str(pfad), dtype="float32", always_2d=True)
    except Exception as fehler:  # soundfile wirft je nach Backend Unterschiedliches
        raise Lesefehler(f"Kann {pfad.name} nicht lesen: {fehler}") from fehler
    if daten.shape[1] == 1:
        daten = np.repeat(daten, 2, axis=1)  # Mono-Quelle -> sauberes Stereo
    if rate != ziel_rate:
        if soxr is None:
            raise Lesefehler(
                "soxr fehlt (wird fuer die Ratenwandlung gebraucht): "
                "python -m pip install soxr"
            )
        daten = soxr.resample(daten, rate, ziel_rate).astype(np.float32)
        rate = ziel_rate
    return Audio(daten=np.ascontiguousarray(daten), rate=int(rate))


def decodieren(pfad: str | Path, ziel_rate: int) -> Audio:
    """Liest eine Datei und wandelt sie nach mono mit der gewuenschten Rate."""
    _pruefe_abhaengigkeiten()
    pfad = Path(pfad)
    try:
        daten, rate = sf.read(str(pfad), dtype="float32", always_2d=True)
    except Exception as fehler:  # soundfile wirft je nach Backend Unterschiedliches
        raise Lesefehler(f"Kann {pfad.name} nicht lesen: {fehler}") from fehler

    mono = daten.mean(axis=1, dtype=np.float32) if daten.shape[1] > 1 else daten[:, 0]
    if rate != ziel_rate:
        if soxr is None:
            raise Lesefehler(
                "soxr fehlt (wird fuer die Ratenwandlung gebraucht): "
                "python -m pip install soxr"
            )
        mono = soxr.resample(mono, rate, ziel_rate).astype(np.float32)
        rate = ziel_rate
    return Audio(daten=np.ascontiguousarray(mono), rate=int(rate))


def ausschnitte_planen(audio: Audio) -> list[tuple[str, int, int]]:
    """Positionen fuer Anfang/Mitte/Ende.

    Bei kurzen Titern koennen sich die Ausschnitte ueberlappen – das ist gewollt
    und wird im Bericht ausgewiesen, damit die Auswertung es weiss.
    """
    gesamt = len(audio.daten)
    laenge = min(int(config.AUSSCHNITT_SEKUNDEN * audio.rate), gesamt)
    if gesamt <= 0:
        return []
    stellen = {
        "anfang": 0,
        "mitte": (gesamt - laenge) // 2,
        "ende": gesamt - laenge,
    }
    return [(name, start, start + laenge) for name, start in stellen.items()]


def ausschnitt_schneiden(
    audio: Audio, start: int, ende: int, ziel: str | Path
) -> Path:
    """Schreibt einen Ausschnitt als 16-bit-WAV in den Cache."""
    _pruefe_abhaengigkeiten()
    ziel = Path(ziel)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    block = audio.daten[start:ende]
    block = np.clip(block, -1.0, 1.0)
    sf.write(str(ziel), (block * 32767.0).astype(np.int16), audio.rate, subtype="PCM_16")
    return ziel
