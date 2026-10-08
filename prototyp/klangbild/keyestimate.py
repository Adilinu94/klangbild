"""Tonart-Schaetzung aus Chroma und Key-Profilen (ADR-012).

Bewusst eigene Implementierung: die naheliegenden Bibliotheken (libKeyFinder GPL,
Essentia AGPL) sind fuer eine geschlossene App unbrauchbar, und das Verfahren
(Chroma + Profil-Korrelation) ist seit Jahrzehnten bekannt und frei.

Referenzpapiere (Lizenz frei, kein Code uebernommen):
- Krumhansl & Kessler, „A cognitive approach to the perception of pitch"
- O'Brien & Lerch, „Genre-specific key profiles" (offen zugaenglich)
- Peeters, „Chroma-based estimation of musical key" (IRCAM, offen)

Exakte Trefferquote wird in Phase 0.2 gemessen (`ROADMAP-KLANGBILD.md`, Tor:
exakt >= 50 %, inkl. Camelot-Nachbar >= 70 %). Die Beschaffung der Referenzdaten
haengt an einem Lizenz-Gate (siehe report.py, Phase 0.2): Harmonix liefert nur
Mel-Spektren und keine Tonart, GTZAN nur Genre bei umstrittener Herkunft,
GiantSteps-Audio sind kommerzielle Beatport-Ausschnitte.

Erste Messung 08.10.2026 (8 Tracks, Chroma + Krumhansl-Profil): die niedrige
Tonart-Sicherheit (6/8 unter 0,3) ist eine Eigenschaft der Musik, nicht der
Chroma-Aufloesung – Fein-Chroma, log-Kompression, Frame-Normierung und ein
Stimmungsschaetzer wurden probiert und veraenderten die mittlere Sicherheit
nicht (0,165). Ohne externe Labels prueft die synthetische Transpositionsprobe
(tests/test_keyestimate.py) alle 12 Tonarten.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Key-Profile: Gewichte der 12 Tonstufen, beginnend mit C.
# Reihenfolge: Dur, dann natuerliches Moll (Krumhansl-Kessler).
KRUMHANSL_MAJOR = np.array(
    [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
)
KRUMHANSL_MINOR = np.array(
    [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
)
AARDEN_MAJOR = np.array(
    [17.7661, 0.1456, 14.9265, 0.1602, 19.8722, 11.7655, 0.2912,
     25.0960, 0.1459, 9.0306, 0.3200, 10.9661]
)
AARDEN_MINOR = np.array(
    [18.2648, 0.7376, 14.1370, 16.1760, 0.5710, 17.5384, 1.9588,
     15.0119, 0.7911, 16.8725, 4.3542, 11.8864]
)
TEMPERLEY_MAJOR = np.array(
    [5.0, 2.0, 3.5, 2.0, 4.5, 4.0, 2.0, 4.5, 2.0, 3.5, 1.5, 4.0]
)
TEMPERLEY_MINOR = np.array(
    [5.0, 2.0, 3.5, 4.5, 2.0, 4.0, 2.0, 4.5, 3.5, 2.0, 3.5, 1.5]
)

TONNAMEN = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")

# Camelot-Notation: Dur = B-Nummern, Moll = A-Nummern, Quintenzirkel aufwaerts.
CAMELOT_MAJOR = {
    "C": "8B", "G": "9B", "D": "10B", "A": "11B", "E": "12B", "B": "1B",
    "F#": "2B", "C#": "3B", "G#": "4B", "D#": "5B", "A#": "6B", "F": "7B",
}
CAMELOT_MINOR = {
    "A": "8A", "E": "9A", "B": "10A", "F#": "11A", "C#": "12A", "G#": "1A",
    "D#": "2A", "A#": "3A", "F": "4A", "C": "5A", "G": "6A", "D": "7A",
}


@dataclass(frozen=True)
class Tonart:
    name: str          # z. B. "C" oder "Am"
    camelot: str        # z. B. "8B" oder "8A"
    vertrauen: float    # 0..1, Abstand beste zu zweitbeste Loesung
    punkte: float       # Korrelationswert der besten Loesung


def chroma(signal: np.ndarray, rate: int, frame: int = 8192, hop: int = 2048) -> np.ndarray:
    """Mittleres Chroma ueber das Signal (12 Klassen, summiert auf 1).

    Bewusst die einfache Variante (Leistungsspektrum auf Halbton-Klassen
    gerundet). Feinere Chroma-Varianten (log-Kompression, Frame-Normierung,
    Hochton-Absenkung, eigener Stimmungsschaetzer) wurden 08.10.2026 geprueft
    und bewusst **nicht** uebernommen – ohne gespeichertes Messartefakt, deshalb
    hier nur als Entscheidung vermerkt, nicht als belegtes Ergebnis:

    - `vertrauen` ist ein **Eigenvertrauen** (Abstand zum zweitbesten Profil),
      keine Trefferquote gegen Ground-Truth. Es blieb auf den Beispiel-Tracks
      niedrig, ob einfaches oder feines Chroma – das sagt nichts darueber,
      welche Variante die Tonart *richtiger* bestimmt. Die niedrige Sicherheit
      ist damit ein Hinweis auf die Musik (viele Toene, flaches Chroma), nicht
      zwingend auf die Chroma-Aufloesung.
    - Ein eigener Stimmungsschaetzer produzierte auf reinen, wenigen Toenen
      Phantom-Korrekturen (falsche Stimmung aus wenig Spektralenergie) und ist
      ohne echte Referenzdaten riskant.

    Der belastbare Weg zur Trefferquote bleibt Phase 0.2 in
    `ROADMAP-KLANGBILD.md`. Bis ein Lizenz-freies Referenz-Korpus belegt ist,
    pruefen zwei Dinge OHNE fremde Daten: die Transpositionsprobe
    (`tests/test_keyestimate.py`, alle 12 Dur- und Moll-Tonarten auf bekannten
    Dreiklaengen) fuer die Tonart und `python -m klangbild metronom`
    (`klangbild/phase02.py`) fuer Tempo/Beat/Downbeat.
    """
    if len(signal) < frame:
        signal = np.pad(signal, (0, frame - len(signal)))
    fenster = np.hanning(frame).astype(np.float32)
    anzahl = 1 + (len(signal) - frame) // hop
    if anzahl <= 0:
        anzahl = 1
    summe = np.zeros(12, dtype=np.float64)
    for index in range(anzahl):
        start = index * hop
        block = signal[start:start + frame]
        if len(block) < frame:
            block = np.pad(block, (0, frame - len(block)))
        spektrum = np.abs(np.fft.rfft(block * fenster))
        frequenzen = np.fft.rfftfreq(frame, 1.0 / rate)
        # nur den praktisch relevanten Bereich betrachten (C2 bis C7)
        gueltig = (frequenzen >= 65.0) & (frequenzen <= 2100.0)
        if not np.any(gueltig):
            continue
        leistung = spektrum[gueltig] ** 2
        midi = 69.0 + 12.0 * np.log2(np.maximum(frequenzen[gueltig], 1e-9) / 440.0)
        klassen = np.rint(midi).astype(np.int64) % 12
        summe += np.bincount(klassen, weights=leistung, minlength=12)
    if summe.sum() <= 0:
        return np.full(12, 1.0 / 12.0)
    return summe / summe.sum()


def _korrelation(a: np.ndarray, b: np.ndarray) -> float:
    a = a - a.mean()
    b = b - b.mean()
    nenner = np.sqrt((a * a).sum() * (b * b).sum())
    if nenner <= 0:
        return 0.0
    return float((a * b).sum() / nenner)


def _rotiert(profil: np.ndarray, halbtoene: int) -> np.ndarray:
    return np.roll(profil, halbtoene)


def tonart_schaetzen(
    signal: np.ndarray,
    rate: int,
    profile: str = "krumhansl",
) -> Tonart:
    """Schaetzt Tonart und Modus. Liefert ein Vertrauensmass mit."""
    chroma_wert = chroma(signal, rate)
    profile_paare = {
        "krumhansl": (KRUMHANSL_MAJOR, KRUMHANSL_MINOR),
        "aarden": (AARDEN_MAJOR, AARDEN_MINOR),
        "temperley": (TEMPERLEY_MAJOR, TEMPERLEY_MINOR),
    }[profile]

    ergebnisse: list[tuple[float, str, str]] = []
    for halbtoene, name in enumerate(TONNAMEN):
        for modus, prof, tabelle in (
            ("dur", profile_paare[0], CAMELOT_MAJOR),
            ("moll", profile_paare[1], CAMELOT_MINOR),
        ):
            wert = _korrelation(chroma_wert, _rotiert(prof, halbtoene))
            bezeichnung = name if modus == "dur" else f"{name}m"
            ergebnisse.append((wert, bezeichnung, tabelle[name]))
    ergebnisse.sort(reverse=True)
    bester, zweiter = ergebnisse[0], ergebnisse[1]
    abstand = max(0.0, bester[0] - zweiter[0])
    # Skala so gewaehlt, dass 0,5 Korrelationsabstand etwa "sicher" heisst.
    vertrauen = float(min(1.0, abstand / 0.5))
    return Tonart(
        name=bester[1],
        camelot=bester[2],
        vertrauen=vertrauen,
        punkte=float(bester[0]),
    )


def camelot_nachbarn(code: str) -> set[str]:
    """Nachbarn auf dem Camelot-Rad: gleiche Nummer (+/-1) in beiden Modi,
    plus der Moduswechsel derselben Nummer (relativer Major/Minor)."""
    if not code or len(code) < 2 or not code[:-1].isdigit():
        return {code}
    nummer = int(code[:-1])
    modus = code[-1]
    anderer = "A" if modus == "B" else "B"
    nachbarn = set()
    for abstand in (-1, 0, 1):
        n = ((nummer - 1 + abstand) % 12) + 1
        nachbarn.add(f"{n}{modus}")
    nachbarn.add(f"{nummer}{anderer}")
    return nachbarn
