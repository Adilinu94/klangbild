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


def _modell_laden():
    global _MODELL
    if _MODELL is None:
        try:
            from beat_this.inference import File2Beats
        except ImportError as fehler:
            raise SchlagFehler(
                "beat-this fehlt. Installation: python -m pip install beat-this "
                "(zieht torch nach)."
            ) from fehler
        # final0 ist das Hauptmodell; fuer das Handy ist small0 vorgesehen.
        _MODELL = File2Beats(checkpoint_path="final0", device="cpu", dbn=False)
    return _MODELL


def analysieren(pfad: str | Path) -> SchlagAnalyse:
    """Beats und Downbeats einer Datei. Liest selbst und wandelt auf 22,05 kHz."""
    from .audioio import decodieren

    audio = decodieren(pfad, config.ABTASTRATE_ANALYSE)
    modell = _modell_laden()
    beats, downbeats = modell(audio.daten.astype(np.float32))
    return SchlagAnalyse(
        beats=np.asarray(beats, dtype=float),
        downbeats=np.asarray(downbeats, dtype=float),
    )
