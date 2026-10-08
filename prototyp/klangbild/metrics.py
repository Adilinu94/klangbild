"""Metriken fuer die Tore aus Phase 0.2 – selbst gerechnet (kein mir_eval).

Grund: mir_eval ist ein Testwerkzeug und wird nicht ausgeliefert, seine
Lizenzlage ist aber nicht eindeutig belegt. Die benoetigten Metriken sind
ueberschaubar und hier transparent implementiert:

- Wilson-Konfidenzintervall (bei 20 Faellen ist ein Fehler 5 Punkte – ohne
  Intervall wird das Tor ueberinterpretiert)
- Beat-F1 mit fester Toleranz (Standard: +-70 ms)
- BPM-Korrektheit mit Oktav-Toleranz (halbes/doppeltes Tempo zaehlt als richtig)
- Downbeat-Korrektheit innerhalb +-1 Takt
- Tonart-Genauigkeit exakt und inklusive Camelot-Nachbar
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .keyestimate import camelot_nachbarn, CAMELOT_MAJOR, CAMELOT_MINOR

STANDARD_TOLERANZ_S = 0.070


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson-Score-Intervall fuer einen Anteil. Leeres n -> (0, 0)."""
    if n <= 0:
        return (0.0, 0.0)
    p = k / n
    nenner = 1.0 + z * z / n
    mitte = (p + z * z / (2.0 * n)) / nenner
    spanne = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n)) / nenner
    return (max(0.0, mitte - spanne), min(1.0, mitte + spanne))


def beat_f1(
    referenz: np.ndarray | list[float],
    schaetzung: np.ndarray | list[float],
    toleranz: float = STANDARD_TOLERANZ_S,
) -> float:
    """F1 der Schlagzeiten mit fester Toleranz, jeder Treffer nur einmal."""
    ref = np.sort(np.asarray(referenz, dtype=float))
    est = np.sort(np.asarray(schaetzung, dtype=float))
    if ref.size == 0 and est.size == 0:
        return 1.0
    if ref.size == 0 or est.size == 0:
        return 0.0
    getroffen = 0
    belegt = np.zeros(est.size, dtype=bool)
    for zeit in ref:
        abstaende = np.abs(est - zeit)
        abstaende[belegt] = np.inf
        naechster = int(np.argmin(abstaende))
        if abstaende[naechster] <= toleranz:
            belegt[naechster] = True
            getroffen += 1
    praezision = getroffen / est.size
    erinnerung = getroffen / ref.size
    if praezision + erinnerung == 0:
        return 0.0
    return 2 * praezision * erinnerung / (praezision + erinnerung)


def bpm_richtig(referenz_bpm: float, geschaetzte_bpm: float, toleranz: float = 0.04) -> bool:
    """Tempo gilt als richtig, wenn es im Toleranzband liegt oder exakt halb/doppelt ist."""
    if referenz_bpm <= 0 or geschaetzte_bpm <= 0:
        return False
    kandidaten = (geschaetzte_bpm, geschaetzte_bpm * 2.0, geschaetzte_bpm / 2.0)
    return any(abs(kandidat - referenz_bpm) / referenz_bpm <= toleranz for kandidat in kandidaten)


def downbeat_richtig(
    referenz_downbeats: np.ndarray | list[float],
    geschaetzte_downbeats: np.ndarray | list[float],
    beat_periode: float,
    toleranz_in_beats: int = 1,
) -> bool:
    """Richtig, wenn der erste geschaetzte Downbeat nahe am ersten Referenz-Downbeat liegt."""
    ref = np.asarray(referenz_downbeats, dtype=float)
    est = np.asarray(geschaetzte_downbeats, dtype=float)
    if ref.size == 0 or est.size == 0 or beat_periode <= 0:
        return False
    toleranz = toleranz_in_beats * beat_periode
    return bool(np.min(np.abs(est - ref[0])) <= toleranz)


def bpm_aus_beats(beats: np.ndarray | list[float]) -> float:
    """Tempo als Median der Schlagabstaende (robuster als Mittelwert)."""
    b = np.sort(np.asarray(beats, dtype=float))
    if b.size < 2:
        return 0.0
    abstaende = np.diff(b)
    abstaende = abstaende[abstaende > 0]
    if abstaende.size == 0:
        return 0.0
    return float(60.0 / np.median(abstaende))


@dataclass(frozen=True)
class TonartErgebnis:
    exakt: int
    nachbar: int
    gesamt: int

    @property
    def quote_exakt(self) -> float:
        return self.exakt / self.gesamt if self.gesamt else 0.0

    @property
    def quote_nachbar(self) -> float:
        return self.nachbar / self.gesamt if self.gesamt else 0.0


def _normalisiere_tonart(name: str) -> str:
    """Zerlegt 'Am' oder 'C#' und liefert den Camelot-Code."""
    name = name.strip()
    if name.endswith("m"):
        grundton = name[:-1]
        tabelle = CAMELOT_MINOR
    else:
        grundton = name
        tabelle = CAMELOT_MAJOR
    return tabelle.get(grundton, "")


def tonart_genauigkeit(
    referenz: list[str], schaetzung: list[str], erlaube_nachbar: bool = True
) -> TonartErgebnis:
    """Vergleicht Tonarten exakt und – optional – ueber den Camelot-Nachbarn."""
    exakt = nachbar = 0
    for ref_name, est_name in zip(referenz, schaetzung):
        ref_code = _normalisiere_tonart(ref_name)
        est_code = _normalisiere_tonart(est_name)
        if not ref_code or not est_code:
            continue
        if ref_code == est_code:
            exakt += 1
            nachbar += 1
        elif erlaube_nachbar and est_code in camelot_nachbarn(ref_code):
            nachbar += 1
    return TonartErgebnis(exakt=exakt, nachbar=nachbar, gesamt=len(referenz))
