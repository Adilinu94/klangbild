"""Schlag- und Downbeat-Erkennung ueber Beat This! (ADR-012).

Beat This! ist MIT (Code und Gewichte). Vorgabe der Vorverarbeitung: mono
22,05 kHz und die Spektrogramm-Parameter des Original-Repos. Der Prototyp ruft
das Originalpaket auf, damit spaeter auf Android dieselben Zahlen herauskommen
(`mosynthkey/beat_this_cpp`, ONNX, `small0` ~8,1 MB).

Das Paket ist optional: fehlt es, laeuft der Rest des Prototyps weiter, und der
Track wird als "ohne Schlaganalyse" markiert.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import config

_MODELL = None
_LADEFEHLER: Exception | None = None


class SchlagFehler(RuntimeError):
    pass


@dataclass(frozen=True)
class SchlagAnalyse:
    beats: np.ndarray
    downbeats: np.ndarray

    @property
    def verfuegbar(self) -> bool:
        return self.beats.size > 0


def verfuegbar() -> bool:
    try:
        import beat_this.inference  # noqa: F401
    except ImportError:
        return False
    return True


def checkpoint_pfad() -> Path:
    """Lokalen Checkpoint liefern, falls vorhanden, sonst den Kurznamen.

    Der lokale Pfad (config.BEAT_THIS_CHECKPOINT) hat Vorrang: beat_this wuerde
    bei einem Kurznamen selbst laden, und genau das scheitert hier still -
    ein angefangener, nie abgeschlossener Download, je Track erneut versucht.
    """
    lokal = config.BEAT_THIS_CHECKPOINT
    return lokal if lokal.exists() else Path("final0")


def _modell_laden():
    global _MODELL
    if _MODELL is None:
        try:
            # Audio2Beats nimmt (signal, sr) - File2Beats dagegen einen *Pfad*
            # und wuerde ein Array als Dateinamen lesen (\"Could not load audio\").
            # Wir fuettern grundsaetzlich Arrays (auch die synthetischen
            # Metronome der Phase 0.2 haben keine Datei), darum Audio2Beats.
            from beat_this.inference import Audio2Beats
        except ImportError as fehler:
            raise SchlagFehler(
                "beat-this fehlt. Installation: python -m pip install beat-this "
                "(zieht torch nach)."
            ) from fehler
        # final0 ist das Hauptmodell; fuer das Handy ist small0 vorgesehen.
        # Vorrangig der lokale Pfad (siehe checkpoint_pfad), damit der Lauf nicht
        # still an einem Download haengt. Ein Fehler hier darf nicht je Track
        # wiederholt werden: _MODELL bleibt None, der Fehler wird gemerkt.
        try:
            _MODELL = Audio2Beats(checkpoint_path=str(checkpoint_pfad()),
                                  device="cpu", dbn=False)
        except Exception as fehler:  # Ursache an den Aufrufer
            global _LADEFEHLER
            _LADEFEHLER = fehler
            raise SchlagFehler(
                f"beat-this-Checkpoint nicht ladbar ({fehler}). Erwartet unter "
                f"{config.BEAT_THIS_CHECKPOINT} oder per KLANGBILD_BEAT_CKPT."
            ) from fehler
    return _MODELL


def analysieren_signal(signal: np.ndarray) -> SchlagAnalyse:
    """Beats und Downbeats eines bereits dekodierten Mono-Signals (22,05 kHz).

    Getrennt von `analysieren`, damit der Phase-0.2-Vergleichslauf synthetische
    Signale (Metronom mit bekannter Ground-Truth) ohne Datei-Umweg pruefen kann.
    """
    modell = _modell_laden()
    # Audio2Beats will (signal, sr); ohne Abtastrate geht es von etwas Falschem aus.
    beats_arr, downbeats_arr = modell(
        signal.astype(np.float32), config.ABTASTRATE_ANALYSE
    )
    return SchlagAnalyse(
        beats=np.asarray(beats_arr, dtype=float),
        downbeats=np.asarray(downbeats_arr, dtype=float),
    )


def analysieren(pfad: str | Path) -> SchlagAnalyse:
    """Beats und Downbeats einer Datei. Liest selbst und wandelt auf 22,05 kHz."""
    from .audioio import decodieren

    audio = decodieren(pfad, config.ABTASTRATE_ANALYSE)
    return analysieren_signal(audio.daten)
