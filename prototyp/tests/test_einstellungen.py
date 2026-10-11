"""Tests fuer einstellungen.py - Grenzen, Auswahl, Speichern."""

from __future__ import annotations

from klangbild import einstellungen as es


def test_ungueltiges_wird_ignoriert_grenzen_geklemmt():
    e = es.aus_dict({"takte": 7, "art": "x", "max_bpm": -3, "keylock": 0, "unbekannt": 1})
    assert e.takte == 16 and e.art == "auto" and e.max_bpm == 0.0 and e.keylock is False


def test_speichern_und_laden(tmp_path):
    pfad = tmp_path / "e.json"
    es.speichern(pfad, es.Einstellungen(takte=24, tempo_modus="b_an_a"))
    assert es.laden(pfad) == es.Einstellungen(takte=24, tempo_modus="b_an_a")
    assert es.laden(tmp_path / "fehlt.json") == es.Einstellungen()
