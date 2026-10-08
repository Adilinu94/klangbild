"""Tests fuer den Phase-0.2-Metronom-Vergleichslauf (Messkette ohne Fremddaten).

Der Lauf prueft die Messkette auf bekannter Ground-Truth. Damit das unabhaengig
von beat-this (das erst spaeter installiert wird) laeuft, wird hier mit einer
perfekten und einer bewusst versetzten Schaetzung gegen die Metronom-Wahrheit
gerechnet.
"""

from __future__ import annotations

import numpy as np

from klangbild import beats, phase02


def test_metronom_hat_korrekte_ground_truth():
    metro = phase02.baue_metronome((120.0,), takt=4, sekunden=10.0)[0]
    # 120 BPM -> Beat alle 0,5 s; ueber 10 s sind das 20 Schlaege.
    assert len(metro.beats) == 20
    assert abs(metro.beats[1] - metro.beats[0] - 0.5) < 1e-9
    # Downbeats jeder 4. Schlag -> 5 Taktanfaenge (inkl. t=0).
    assert len(metro.downbeats) == 5
    assert metro.downbeats[1] == metro.beats[4]


def test_metronom_signal_ist_endlich_und_klebt():
    metro = phase02.baue_metronome((128.0,))[0]
    signal = metro.signal
    assert signal.size > 0
    assert np.isfinite(signal).all()
    assert float(np.abs(signal).max()) <= 1.0


def _perfekte_schaetzung(metro: phase02.Metronom) -> beats.SchlagAnalyse:
    """Gibt exakt die Ground-Truth als Schaetzung zurueck (Ideal-Schaetzer)."""
    return beats.SchlagAnalyse(beats=metro.beats.copy(), downbeats=metro.downbeats.copy())


def test_perfekte_schaetzung_besteht_alle_tore():
    metro = phase02.baue_metronome((120.0,))[0]
    ergebnis = phase02._ein_metronom_bewerten(metro, _perfekte_schaetzung(metro))
    assert ergebnis["hat_beats"]
    assert ergebnis["beat_f1"] == 1.0
    assert ergebnis["bpm_richtig"]
    assert abs(ergebnis["bpm_geschätzt"] - 120.0) < 1e-6
    assert ergebnis["downbeat_richtig"]


def test_falsches_tempo_wird_erkannt():
    """BPM kann per Oktavtoleranz richtig zaehlen, obwohl die Zeiten daneben liegen.

    Hier ist das Tempo exakt gleich, aber jeder Schlag um eine halbe Beat-Periode
    verschoben – weit jenseits der 70-ms-Toleranz. Genau deshalb darf man BPM und
    Beat-F1 nicht vermischen: bpm_richtig ist wahr, beat_f1 aber niedrig.
    """
    metro = phase02.baue_metronome((128.0,))[0]
    halbe_periode = metro.beat_periode / 2.0
    verschoben = beats.SchlagAnalyse(
        beats=metro.beats + halbe_periode,
        downbeats=metro.downbeats + halbe_periode,
    )
    ergebnis = phase02._ein_metronom_bewerten(metro, verschoben)
    assert ergebnis["bpm_richtig"]    # Tempo stimmt (Verschiebung aendert es nicht)
    assert ergebnis["beat_f1"] < 0.1  # aber kein Schlag trifft (Toleranz 70 ms)


def test_ohne_modell_wird_markiert():
    metro = phase02.baue_metronome((90.0,))[0]
    ergebnis = phase02._ein_metronom_bewerten(metro, None)
    assert ergebnis == {"bpm": 90.0, "hat_beats": False}


def test_zusammenfassung_zaehlt_tore():
    metronome = phase02.baue_metronome((90.0, 120.0))
    einzel = [phase02._ein_metronom_bewerten(m, _perfekte_schaetzung(m)) for m in metronome]
    bericht = phase02.auswerten(metronome, einzel)
    assert bericht["anzahl_mit_beats"] == 2
    assert bericht["bpm"]["quote"] == 1.0
    assert bericht["downbeat"]["quote"] == 1.0
    assert bericht["tor_bpm_erfuellt"]
    assert bericht["tor_downbeat_erfuellt"]


def test_wilson_spanne_wird_mitgeliefert():
    metronome = phase02.baue_metronome((100.0,))
    einzel = [phase02._ein_metronom_bewerten(metronome[0], _perfekte_schaetzung(metronome[0]))]
    bericht = phase02.auswerten(metronome, einzel)
    assert bericht["bpm"]["wilson_oben"] >= bericht["bpm"]["quote"]
    assert bericht["bpm"]["wilson_unten"] <= bericht["bpm"]["quote"]
