"""Tests fuer plan.py - den Auto-DJ-Planer (Phase 1).

Geprueft wird, was ein Fehler zuerst kaputt macht: das **Tempo-Gate** (hart,
ADR-014, kein Gewicht), die Harmonie-Noten (exakt/Nachbar/fremd), die
Neugewichtung, wenn kein Klang-Vektor vorliegt, und der Determinismus der
gierigen Auswahl. Der Planer liest nur Merkmale - kein Audio -, also laufen
diese Tests ohne Sounddatei.
"""

from __future__ import annotations

from klangbild import plan
from klangbild.keyestimate import camelot_nachbarn


def _track(track_id: int, bpm: float | None, camelot: str | None,
           energie_db: float | None = None, vektor=None) -> plan.Track:
    return plan.Track(id=track_id, pfad=f"t{track_id}", bpm=bpm,
                      camelot=camelot, energie_db=energie_db, vektor=vektor)


# --- Harmonie-Noten ---------------------------------------------------------


def test_harmonie_exakt_nachbar_fremd():
    assert plan.harmonie_note("8A", "8A") == (1.0, "gleiche Tonart")
    nachbarn = camelot_nachbarn("8A")
    assert "9A" in nachbarn                       # relativer Nachbar
    assert plan.harmonie_note("8A", "9A") == (0.6, "Camelot-Nachbar")
    assert plan.harmonie_note("8A", "4B") == (0.0, "fremd")


def test_harmonie_ohne_camelot_ist_fremd():
    note, grund = plan.harmonie_note("", "8A")
    assert note == 0.0 and grund == "fremd"
    note, grund = plan.harmonie_note("8A", None)
    assert note == 0.0


# --- Energie-Note -----------------------------------------------------------


def test_energie_kein_sprung_ist_eins():
    assert plan.energie_note(-10.0, -10.0, 12.0)[0] == 1.0


def test_energie_grosser_sprung_ist_null():
    assert plan.energie_note(-10.0, -30.0, 12.0)[0] == 0.0
    assert plan.energie_note(-10.0, 5.0, 12.0)[0] == 0.0   # auch positiv


def test_energie_mittelwert_bei_fehlendem_wert():
    assert plan.energie_note(None, -10.0, 12.0)[0] == 0.5
    assert plan.energie_note(-10.0, None, 12.0)[0] == 0.5


def test_energie_linear_im_bereich():
    # Halber Maximalsprung -> Note 0,5.
    assert abs(plan.energie_note(-10.0, -16.0, 12.0)[0] - 0.5) < 1e-9


# --- Uebergangsnote inkl. hartem Tempo-Gate ---------------------------------


def test_uebergang_note_gewicht_ohne_vektor():
    # Ohne Klang-Vektor faellt sein 0,35-Anteil heraus: Harmonie (0,40) und
    # Energie (0,25) werden auf 1 neu normiert. Gleiche Tonart, kein Sprung:
    # note = (0,40*1,0 + 0,25*1,0)/(0,40+0,25) = 0,65/0,65 = 1,0.
    a = _track(1, 120.0, "8A", -10.0)
    b = _track(2, 120.0, "8A", -10.0)
    u = plan.uebergang_note(a, b, energie_gewichtet=True)
    assert u.note == 1.0
    assert u.tempo_faktor == 1.0


def test_uebergang_tempo_gate_ist_hart():
    # 120 vs 160 BPM: 33 % auseinander, jenseits +-3 % -> Note 0, Faktor geklemmt.
    # Faktor = deck/kandidat = 120/160 = 0,75, geklemmt auf 0,97: das zieht B
    # *langsamer*, also in Richtung Deck (resample_linear wuerde B verlaengern).
    # 1,03 wuerde B weiter vom Deck wegbeschleunigen - deshalb ist 0,97 richtig.
    a = _track(1, 120.0, "8A", -10.0)
    b = _track(2, 160.0, "8A", -10.0)
    u = plan.uebergang_note(a, b, energie_gewichtet=True)
    assert u.note == 0.0
    assert abs(u.tempo_faktor - 0.97) < 1e-9        # Klemmung zur Deck-Seite
    assert "Tempo-Gate" in u.grund


def test_uebergang_tempo_knapp_drin_bleibt_offen():
    # 120 vs 123 BPM: +2,5 %, innerhalb des Gates -> Note nicht weggeworfen.
    # Faktor = deck/kandidat = 120/123 = 0,9756: B wird leicht verlangsamt, damit
    # ihre Beats auf dem 120er-Deckraster landen (123 * 0,9756 = 120, ADR-014).
    a = _track(1, 120.0, "8A", -10.0)
    b = _track(2, 123.0, "8A", -10.0)
    u = plan.uebergang_note(a, b, energie_gewichtet=True)
    assert u.note > 0.0
    assert abs(u.tempo_faktor - (120.0 / 123.0)) < 1e-3


def test_uebergang_vektor_erhoeht_den_klanganteil():
    import numpy as np

    # Identische Vektoren -> Kosinus 1,0. Mit Energie aus (nur 1./2. Song):
    # note = (0,40*1,0 + 0,35*1,0 + 0,25*1,0)/1,0 = 1,0.
    v = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    a = _track(1, 120.0, "8A", -10.0, vektor=v)
    b = _track(2, 120.0, "8A", -10.0, vektor=v.copy())
    u = plan.uebergang_note(a, b, energie_gewichtet=True)
    assert u.klang == 1.0
    assert u.note == 1.0


# --- Set-Aufbau (gierig, deterministisch) -----------------------------------


def test_baue_set_kappt_tempo_gate_statt_unfall_zu_erzwingen():
    # B (121 BPM) passt zu A (120), C (200 BPM) nicht. Ein erzwungener Uebergang
    # auf C wuerde galoppieren und im Hoertest als Unfall markiert (ADR-014;
    # Tor Phase 1: *kein* Uebergang ist ein Unfall). Deshalb wird C **nicht**
    # angehaengt, sondern als uebersprungen gemeldet - lieber ein kuerzeres,
    # sauberes Set als ein kaputter Uebergang (docstring baue_set).
    a = _track(1, 120.0, "8A", -10.0)
    b = _track(2, 121.0, "8A", -11.0)
    c = _track(3, 200.0, "3B", -12.0)
    p = plan.baue_set([a, b, c])
    assert p.reihenfolge == [1, 2]                # c wird nicht erzwungen
    assert "t3" in p.uebersprungen                # ...sondern gemeldet
    assert len(p.uebergaenge) == 1                # nur der offene Uebergang 1->2
    assert p.uebergaenge[0].note > 0.0


def test_baue_set_deterministisch_ohne_seed():
    tracks = [_track(i, 120.0 + (i % 2), "8A", -10.0) for i in range(1, 7)]
    p1 = plan.baue_set(tracks)
    p2 = plan.baue_set(tracks)
    assert p1.reihenfolge == p2.reihenfolge


def test_baue_set_start_id_wird_respektiert():
    tracks = [_track(i, 120.0, "8A") for i in range(1, 6)]
    p = plan.baue_set(tracks, start_id=3)
    assert p.reihenfolge[0] == 3
    assert len(p.reihenfolge) == 5


def test_baue_set_laenge_begrenzt_und_zaehlt_uebersprungen():
    tracks = [_track(i, 120.0, "8A") for i in range(1, 6)]
    p = plan.baue_set(tracks, laenge=3)
    assert len(p.reihenfolge) == 3
    assert len(p.uebersprungen) == 2
    assert len(p.uebergaenge) == 2


def test_baue_set_leer_ist_leer():
    p = plan.baue_set([])
    assert p.reihenfolge == [] and p.uebergaenge == []


def test_baue_set_ein_track_allein():
    p = plan.baue_set([_track(1, 120.0, "8A")])
    assert p.reihenfolge == [1] and p.uebergaenge == []
