"""Tests fuer den Fail-Fast in `analyze` (kein beat-this -> Abbruch statt Zeilen ohne Beats).

Hintergrund: ein Lauf mit dem System-Python (ohne beat-this) schrieb 498 Zeilen
mit leerem beats_json, die spaeter wie echte Analysen aussahen. `analyze` bricht
jetzt mit Rueckgabe 2 ab, wenn beat-this fehlt - ausser mit --ohne-beats.
"""

from __future__ import annotations

import argparse

from klangbild import beats, db, pipeline


def _args(tmp_path, ohne_beats: bool = False):
    return argparse.Namespace(
        datenbank=str(tmp_path / "t.db"),
        cache=str(tmp_path / "cache"),
        ergebnisse=str(tmp_path / "ergebnisse"),
        bibliothek=None,
        limit=0,
        ohne_beats=ohne_beats,
    )


def test_analyze_bricht_ab_wenn_beat_this_fehlt(tmp_path, monkeypatch):
    monkeypatch.setattr(beats, "verfuegbar", lambda: False)
    ergebnis = pipeline.kommandos_analyze(_args(tmp_path))
    assert ergebnis == 2


def test_analyze_ohne_beats_laueft_bewusst_weiter(tmp_path, monkeypatch):
    # Mit --ohne-beats darf der Lauf weitergehen (nur Tonart/Lautheit/Energie);
    # bei leerer DB ist das sofort fertig.
    monkeypatch.setattr(beats, "verfuegbar", lambda: False)
    ergebnis = pipeline.kommandos_analyze(_args(tmp_path, ohne_beats=True))
    assert ergebnis == 0


def test_keine_zeilen_ohne_beats_bei_abbruch(tmp_path, monkeypatch):
    monkeypatch.setattr(beats, "verfuegbar", lambda: False)
    pipeline.kommandos_analyze(_args(tmp_path))
    conn = db.verbinden(tmp_path / "t.db")
    try:
        anzahl = conn.execute("SELECT COUNT(*) FROM features").fetchone()[0]
    finally:
        conn.close()
    assert anzahl == 0
