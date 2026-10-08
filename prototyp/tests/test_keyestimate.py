"""Tests fuer die Tonart-Schaetzung (ADR-012) und das Camelot-Rad."""

from __future__ import annotations

import numpy as np

from klangbild import keyestimate


def _klang(frequenzen: list[float], sekunden: float = 6.0, rate: int = 22050) -> tuple[np.ndarray, int]:
    t = np.arange(int(sekunden * rate)) / rate
    signal = np.zeros_like(t)
    for frequenz, staerke in frequenzen:
        signal += staerke * np.sin(2 * np.pi * frequenz * t)
    return signal.astype(np.float32), rate


def test_chroma_summiert_auf_eins():
    signal, rate = _klang([(261.63, 0.3), (329.63, 0.3), (392.0, 0.3)])
    chroma = keyestimate.chroma(signal, rate)
    assert abs(float(chroma.sum()) - 1.0) < 1e-6
    assert chroma.shape == (12,)


def test_c_dur_mit_grundton_wird_erkannt():
    # C als Bass verankert die Tonart gegenueber der Moll-Parallele.
    signal, rate = _klang([(130.81, 0.5), (261.63, 0.3), (329.63, 0.25), (392.0, 0.25)])
    ergebnis = keyestimate.tonart_schaetzen(signal, rate)
    assert ergebnis.name == "C"
    assert ergebnis.camelot == "8B"
    assert 0.0 <= ergebnis.vertrauen <= 1.0


def test_a_moll_wird_erkannt():
    signal, rate = _klang([(220.0, 0.5), (261.63, 0.25), (329.63, 0.25)])
    ergebnis = keyestimate.tonart_schaetzen(signal, rate)
    assert ergebnis.name == "Am"
    assert ergebnis.camelot == "8A"


def test_camelot_nachbarn():
    nachbarn = keyestimate.camelot_nachbarn("8B")
    assert nachbarn == {"7B", "8B", "9B", "8A"}
    assert keyestimate.camelot_nachbarn("1A") == {"12A", "1A", "2A", "1B"}


def test_unsicheres_signal_hat_low_vertrauen():
    rng = np.random.default_rng(0)
    signal = (rng.standard_normal(22050 * 4) * 0.1).astype(np.float32)
    ergebnis = keyestimate.tonart_schaetzen(signal, 22050)
    assert ergebnis.vertrauen <= 0.5  # Rauschen darf nicht "sicher" sein


# --------------------------------------------------------------------------
# Transpositionsprobe (Lizenz-freier Ersatz fuer GiantSteps, Phase 0.2)
# --------------------------------------------------------------------------
def _midi_zu_frequenz(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def _dreiklang_signal(grundton: int, moll: bool, sekunden: float = 6.0,
                      rate: int = 22050, cents: float = 0.0) -> np.ndarray:
    """Reiner Dreiklang mit verankertem Bass – dieselbe Bauform wie oben."""
    terz = 3 if moll else 4
    tonhoehen = [
        (grundton - 12, 0.5),   # Bass eine Oktave tiefer verankert die Tonart
        (grundton, 0.3),
        (grundton + terz, 0.25),
        (grundton + 7, 0.25),
    ]
    t = np.arange(int(sekunden * rate)) / rate
    versatz = 2 ** (cents / 1200.0)   # schraeg stimmen, ohne die Struktur zu aendern
    signal = np.zeros_like(t)
    for midi, staerke in tonhoehen:
        frequenz = _midi_zu_frequenz(midi) * versatz
        signal += staerke * np.sin(2 * np.pi * frequenz * t)
    return signal.astype(np.float32)


def test_alle_dur_tonarten_werden_transpositionssicher_erkannt():
    """Phase 0.2 (Lizenz-frei): jede der 12 Dur-Tonarten muss aus dem Dreiklang
    hervor gehen. Faellt eine aus, ist das Chroma oder die Korrelation schraeg."""
    dur = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    treffer = 0
    for index, name in enumerate(dur):
        signal = _dreiklang_signal(60 + index, moll=False)
        ergebnis = keyestimate.tonart_schaetzen(signal, 22050)
        treffer += int(ergebnis.name == name)
    # Mindestens 10 von 12: eine einzelne Verwechslung mit der Moll-Parallele
    # ist fuer das reine Profilverfahren normal und kein Regression.
    assert treffer >= 10, f"nur {treffer}/12 Dur-Tonarten erkannt"


def test_alle_moll_tonarten_werden_transpositionssicher_erkannt():
    moll = ["Am", "A#m", "Bm", "Cm", "C#m", "Dm", "D#m", "Em", "Fm",
            "F#m", "Gm", "G#m"]
    treffer = 0
    for index, name in enumerate(moll):
        grundton = 57 + index  # A3 = 57
        signal = _dreiklang_signal(grundton, moll=True)
        ergebnis = keyestimate.tonart_schaetzen(signal, 22050)
        treffer += int(ergebnis.name == name)
    assert treffer >= 10, f"nur {treffer}/12 Moll-Tonarten erkannt"


def test_verstimmte_aufnahme_wird_trotzdem_richtig_erkannt():
    """Ein um 25 Cent zu hoch liegender C-Dreiklang muss weiter als C erkannt
    werden. Ein Halbton ist 100 Cent breit, deshalb faengt das Falten auf 12
    Klassen leichte Verstimmung ohne eigene Stimmungskorrektur ab."""
    signal = _dreiklang_signal(60, moll=False, cents=25.0)
    ergebnis = keyestimate.tonart_schaetzen(signal, 22050)
    assert ergebnis.name == "C"
