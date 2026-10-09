"""Tests fuer Phase 0.3 · Konsens-Pseudo-Labeling (klangbild/phase03.py).

Alles ohne torch/librosa/av: nur die reine Konsens-Logik und der Camelot-Umbau
werden geprueft. Die optionalen Schwer-Schaetzer (skey/openkeyscan) sind faul
eingebunden und hier nicht noetig.
"""

from __future__ import annotations

import numpy as np

from klangbild import keyestimate, phase03

# --- Camelot-Umbau -----------------------------------------------------------


def test_tonartname_zu_camelot_major_minor():
    assert phase03._tonartname_zu_camelot("C") == "8B"          # C major
    assert phase03._tonartname_zu_camelot("A") == "11B"         # A major
    assert phase03._tonartname_zu_camelot("Am") == "8A"         # A minor
    assert phase03._tonartname_zu_camelot("A minor") == "8A"
    assert phase03._tonartname_zu_camelot("C major") == "8B"
    # CAMELOT_MINOR liefert bereits den vollstaendigen Code inkl. "A".
    assert phase03._tonartname_zu_camelot("F#m") == keyestimate.CAMELOT_MINOR["F#"] == "11A"


def test_tonartname_leer_fuer_unbekannt():
    assert phase03._tonartname_zu_camelot("H") == ""


# --- Konsens-Auswertung ------------------------------------------------------


def _s(camelot: str, quelle: str = "test") -> phase03.Schaetzung:
    return phase03.Schaetzung(camelot=camelot, modus="dur", quelle=quelle)


def test_einig_streng_nur_bei_identischen_codes():
    gleich = phase03.Konsens("x", [_s("8A"), _s("8A", "b"), _s("8A", "c")])
    assert gleich.einig_streng() is True
    gemischt = phase03.Konsens("x", [_s("8A"), _s("9A", "b")])
    assert gemischt.einig_streng() is False


def test_mehrheit_zahlt_stimmen():
    k = phase03.Konsens("x", [_s("8A"), _s("9A", "b"), _s("8A", "c")])
    code, anzahl = k.mehrheit()
    assert code == "8A"
    assert anzahl == 2


def test_einig_nachbar_toleriert_camelot_umfeld():
    # Im Camelot-Rad zaehlen Nummer +/-1 (7A, 8A, 9A) plus Moduswechsel (8B).
    nachbarn = keyestimate.camelot_nachbarn("8A")
    assert {"9A", "7A", "8B"}.issubset(nachbarn)
    nebenan = phase03.Konsens("x", [_s("8A"), _s("9A", "b")])
    assert nebenan.einig_nachbar() is True
    # Gegenueber (8A vs 5A, halbes Rad entfernt) ist kein Nachbar.
    weit = phase03.Konsens("x", [_s("8A"), _s("5A", "b")])
    assert weit.einig_nachbar() is False


def test_einzelschaetzung_ist_trivial_einig():
    k = phase03.Konsens("x", [_s("8A")])
    assert k.einig_streng() is True
    assert k.einig_nachbar() is True


def test_leer_ist_nicht_einig():
    k = phase03.Konsens("x", [])
    assert k.einig_streng() is False
    assert k.einig_nachbar() is False


# --- Zusammenfassung ---------------------------------------------------------


def test_auswerten_zaehlt_einigung_und_harte_faelle():
    konsense = [
        phase03.Konsens("a", [_s("8A"), _s("8A", "b")]),      # streng einig
        phase03.Konsens("b", [_s("8A"), _s("9A", "b")]),      # nur Nachbar
        phase03.Konsens("c", [_s("8A"), _s("5A", "b")]),      # hart (weit weg)
        phase03.Konsens("d", [_s("5A")]),                      # nur eigener
    ]
    z = phase03.auswerten(konsense)
    assert z["tracks_gesamt"] == 4
    assert z["tracks_mehrere_schaetzer"] == 3
    assert z["tracks_nur_eigener"] == 1
    assert z["einig_streng"]["treffer"] == 1
    assert z["einig_streng"]["gesamt"] == 3        # Nenner = Tracks mit >=2 Schaetzern
    assert z["einig_nachbar"]["treffer"] == 2      # streng + nachbar
    assert z["hart"]["treffer"] == 1
    # Wilson-Spanne liegt um den Anteil.
    assert 0.0 <= z["einig_streng"]["wilson_unten"] <= z["einig_streng"]["quote"] \
        <= z["einig_streng"]["wilson_oben"] <= 1.0
    # Der harte Fall taucht namentlich auf.
    assert any(e["codes"] == ["8A", "5A"] for e in z["schwierige_tracks"])


def test_auswerten_ohne_mehrfach_schaetzer():
    z = phase03.auswerten([phase03.Konsens("a", [_s("8A")])])
    assert z["tracks_mehrere_schaetzer"] == 0
    assert z["einig_streng"]["quote"] == 0.0
    assert z["schwierige_tracks"] == []


# --- Eigener Schaetzer + Fallback --------------------------------------------


def test_schaetzer_eigen_liefert_camelot():
    signal = np.sin(2 * np.pi * 220.0 * np.arange(22050) / 22050.0).astype(np.float32)
    s = phase03.schaetzer_eigen(signal, 22050)
    assert s is not None
    assert s.camelot and s.quelle == "eigen/chroma"


def test_verfuegbare_schaetzer_hat_immer_eigenen():
    namen = [f.__name__ for f in phase03.verfuegbare_schaetzer()]
    assert "schaetzer_eigen" in namen
