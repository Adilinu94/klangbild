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

from .keyestimate import CAMELOT_MAJOR, CAMELOT_MINOR, camelot_nachbarn

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
    """Tempo als **Regression ueber alle Beats** (Raster aus dem Haupt-Cluster).

    Beat This! setzt Einschlaege auf ein 50-fps-Raster (20-ms-Stufen). Die
    Abstaende sind damit gequantelt, und ihr **Median** klebt an einer Stufe -
    er laeu systematisch daneben (gemessen bis ~2 %, im Mittel ~1,1 %). Fuer
    Beatmatching braucht es aber etwa +-0,1 %.

    Das Haupt-Cluster liefert die Rasterperiode; die Regression mittelt die +-10-ms-Quantelung heraus
    (Teleskop-Effekt: die Randfehler der Stufen heben sich ueber viele
    Abstaende auf) und trifft das echte Tempo. Doppelte/fehlende Einschlaege
    erzeugen Oktav-Ausreisser (Faktor ~0,5 bzw. ~2); die fallen aus dem Cluster,
    weil nur Abstaeende nahe der Median-Periode zaehlen.
    """
    b = np.sort(np.asarray(beats, dtype=float))
    if b.size < 2:
        return 0.0
    abstaende = np.diff(b)
    abstaende = abstaende[abstaende > 0]
    if abstaende.size == 0:
        return 0.0
    periode = float(np.median(abstaende))
    # Haupt-Cluster: Abstände innerhalb ±40 % der Median-Periode. Das lässt
    # Microtiming/Jitter zu, lässt aber Oktav-Ausreisser (0,5x/2x) draußen.
    kern = abstaende[np.abs(abstaende - periode) <= 0.40 * periode]
    if kern.size == 0:
        kern = abstaende
    periode = _lokale_periode(b, float(np.mean(kern)))
    # Eine Gerade durch ALLE Beats (Index gegen Zeit) mittelt das 20-ms-Raster weg;
    # der Mittelwert allein haengt nur am ersten und letzten Beat (Teleskopsumme).
    # Rasterphase aus dem Kreismittel aller Beats, nicht aus b[0]: ein Auftakt-
    # oder Offbeat-Start wuerde sonst das ganze Raster um einen halben Schlag kippen.
    phase = float(np.angle(np.mean(np.exp(2j * np.pi * b / periode)))) / (2 * np.pi)
    lage = b / periode - phase
    index = np.round(lage)
    auf_raster = np.abs(lage - index) < 0.25  # doppelte Einschlaege fallen heraus
    index, zeiten = index[auf_raster], b[auf_raster]
    if zeiten.size >= 3 and np.ptp(index) > 0:
        steigung = float(np.polyfit(index, zeiten, 1)[0])
        if steigung > 0:
            return 60.0 / steigung
    return 60.0 / periode


def _lokale_periode(b: np.ndarray, referenz: float, fenster: int = 16) -> float:
    """Median lokaler Regressionsperioden (Fenster von `fenster` Beats).

    Genau genug (~0,05 %), dass ein globaler Beat-Index ueber einen ganzen Song
    nicht verrutscht; robust gegen Tempo-Abschnitte und einzelne Doppel-Einschlaege.
    Schritte zaehlen gegen die Cluster-`referenz` (nicht den Fenster-Median, der bei
    wenigen Beats zwischen zwei Oktaven landet). Weicht das Ergebnis mehr als 5 %
    von der Referenz ab, gilt die Referenz.
    """
    perioden = []
    for anfang in range(0, max(1, b.size - fenster + 1), max(1, fenster // 2)):
        z = b[anfang:anfang + fenster]
        d = np.diff(z)
        if z.size < 4 or referenz <= 0:
            continue
        k = np.concatenate([[0.0], np.cumsum(np.round(d / referenz))])
        if np.ptp(k) > 0:
            perioden.append(float(np.polyfit(k, z, 1)[0]))
    perioden = [x for x in perioden if x > 0]
    if not perioden:
        return referenz
    lokal = float(np.median(perioden))
    return lokal if abs(lokal - referenz) <= 0.05 * referenz else referenz


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
