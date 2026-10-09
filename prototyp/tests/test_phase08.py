"""Tests fuer Phase 0.8 (skey gegen denselben FMAK-Goldsatz).

Laeuft ohne skey-Checkpoint/Audio: geprueft werden die skey-Ausgabe-Kontrolle
(`_ist_gueltiges_wort`), die Camelot-Uebersetzung der skey-Rohausgabe (wiederverwendet
phase04s `_keymode_zu_camelot`, identische Umrechnung wie im Gold-Lauf) sowie die
Per-Track-CSV/JSON-Ausgabe. Das trainierte Modell selbst haengt am Checkpoint und
wird hier nicht geladen - genau wie phase04 den Audio-Download ausspart.
"""


import json

from klangbild import phase04, phase08

# --- skey-Ausgabekontrolle -----------------------------------------------------


def test_ist_gueltiges_wort_erkennt_form():
    assert phase08._ist_gueltiges_wort("A Major") is True
    assert phase08._ist_gueltiges_wort("Bb minor") is True
    assert phase08._ist_gueltiges_wort("F# Minor") is True


def test_ist_gueltiges_wort_lehnt_unform_ab():
    assert phase08._ist_gueltiges_wort("") is False
    assert phase08._ist_gueltiges_wort("error") is False
    assert phase08._ist_gueltiges_wort("AMajor") is False  # kein Leerzeichen


# --- Camelot-Uebersetzung (identisch zum Gold-Lauf) ----------------------------


def test_camelot_aus_skey_major():
    # skey gibt "A Major" -> wir splitten in ("A", "Major") wie phase04 es erwartet.
    assert phase08._camelot_aus_skey("A Major") == "11B"
    assert phase08._camelot_aus_skey("C Major") == "8B"
    assert phase08._camelot_aus_skey("Bb Major") == "6B"   # Bb -> A# -> 6B


def test_camelot_aus_skey_minor():
    assert phase08._camelot_aus_skey("A minor") == "8A"
    assert phase08._camelot_aus_skey("Eb minor") == "2A"   # Eb -> D# -> 2A


def test_camelot_aus_skey_leer_bei_unform():
    assert phase08._camelot_aus_skey("") == ""
    assert phase08._camelot_aus_skey("error") == ""


# --- Per-Track-CSV-Export (gleiches Format wie phase04) ------------------------


def _vergleich(track_id, gold, schaetzung, exakt, nachbar):
    return phase04.GoldVergleich(
        track_id=track_id, gold=gold, schaetzung=schaetzung,
        vertrauen=0.08, exakt=exakt, nachbar=nachbar,
    )


def test_csv_schreiben_vollstaendig(tmp_path):
    v = [_vergleich("a", "8A", "8A", True, True),
         _vergleich("b", "8A", "9B", False, False)]
    p = phase08._csv_schreiben(tmp_path, v)
    zeilen = p.read_text(encoding="utf-8").strip().splitlines()
    assert len(zeilen) == 1 + len(v)
    assert zeilen[0].split(",")[0] == "track_id"
    felder = zeilen[1].split(",")
    assert felder[0] == "a" and felder[1] == "8A" and felder[2] == "8A"
    assert felder[3] == "1" and felder[4] == "1" and felder[5] == "exakt"


# --- JSON-Ausgabe (Kennzahlen aus auswerten landen unverändert drin) -----------


def test_json_schreiben_uebernimmt_kennzahlen(tmp_path):
    v = [_vergleich("a", "8A", "8A", True, True),
         _vergleich("b", "8A", "9B", False, False)]
    z = phase04.auswerten(v)
    p = phase08._json_schreiben(tmp_path, z)
    zurueck = json.loads(p.read_text(encoding="utf-8"))
    assert zurueck["tracks"] == 2
    assert zurueck["exakt"]["treffer"] == 1
