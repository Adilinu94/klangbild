"""Tests fuer die Torlogik aus Phase 0.1.

Geprueft wird, dass die Auswertung genau die Bedingungen anwendet, die in der
Roadmap stehen – inklusive Baseline-Abstand und Unfallquote.
"""

from __future__ import annotations

import argparse

import numpy as np

from klangbild import config, db, evaluate, report


def _datenbank_mit_vektoren(tmp_path, anzahl: int = 12):
    pfad = tmp_path / "t.db"
    conn = db.verbinden(pfad)
    rng = np.random.default_rng(0)
    for index in range(anzahl):
        track_id, _ = db.track_eintragen(
            conn, f"t{index}.mp3", 1000, 1.0, f"hash-{index}", "mp3", 0, 1000
        )
        for position in config.AUSSCHNITTE:
            vektor = rng.standard_normal(config.EINBETTUNG_DIM).astype(np.float32)
            vektor /= np.linalg.norm(vektor)
            db.embedding_speichern(conn, track_id, position, "pseudo", vektor, f"t{index}.mp3", 0.0, 20.0)
    conn.commit()
    return conn, pfad


def _bewerte(conn, aufgabe_id: str, tracks: list[int], urteil: str, unfall: bool = False):
    for rang, track_id in enumerate(tracks, 1):
        db.bewertung_speichern(conn, aufgabe_id, track_id, rang, urteil, unfall, "test")


def test_nachbarn_werden_gebaut(tmp_path):
    conn, pfad = _datenbank_mit_vektoren(tmp_path)
    args = argparse.Namespace(
        n=5, k=3, datenbank=str(pfad), cache=str(tmp_path / "cache"),
        ergebnisse=str(tmp_path / "ergebnisse"), bibliothek=None,
    )
    assert evaluate.bauen_nachbarn(args) == 0
    aufgaben = db.aufgaben(conn, "nachbarn")
    assert len(aufgaben) == 5
    import json

    for aufgabe in aufgaben:
        assert len(json.loads(aufgabe["tracks_json"])) == 3
    conn.close()


def test_tor_erfuellt_wenn_klar_ueber_baseline(tmp_path):
    conn, _ = _datenbank_mit_vektoren(tmp_path)
    db.aufgabe_speichern(conn, "nachbarn-1", "nachbarn", 1, None, [2, 3, 4])
    db.aufgabe_speichern(conn, "baseline-1", "baseline", 1, None, [5, 6, 7])
    db.aufgabe_speichern(conn, "text-0", "text", None, "ruhig", [8, 9])
    db.aufgabe_speichern(conn, "unsinn-0", "unsinn", None, "xyz", [10, 11])
    _bewerte(conn, "nachbarn-1", [2, 3, 4], "passt")
    _bewerte(conn, "baseline-1", [5, 6, 7], "passt_nicht")
    _bewerte(conn, "text-0", [8, 9], "passt")
    _bewerte(conn, "unsinn-0", [10, 11], "passt_nicht")
    conn.commit()
    ergebnis = evaluate.auswerten(conn)
    assert ergebnis["tor_nachbarn"] is True
    assert ergebnis["tor_text"] is True
    assert ergebnis["tor_gesamt"] is True
    conn.close()


def test_tor_faellt_bei_zu_vielen_unfaellen(tmp_path):
    conn, _ = _datenbank_mit_vektoren(tmp_path)
    db.aufgabe_speichern(conn, "nachbarn-1", "nachbarn", 1, None, [2, 3, 4])
    db.aufgabe_speichern(conn, "baseline-1", "baseline", 1, None, [5, 6, 7])
    _bewerte(conn, "nachbarn-1", [2, 3, 4], "passt", unfall=True)  # 100 % Unfall
    _bewerte(conn, "baseline-1", [5, 6, 7], "passt_nicht")
    conn.commit()
    ergebnis = evaluate.auswerten(conn)
    assert ergebnis["tor_nachbarn"] is False
    conn.close()


def test_tor_faellt_ohne_baseline_abstand(tmp_path):
    conn, _ = _datenbank_mit_vektoren(tmp_path)
    db.aufgabe_speichern(conn, "nachbarn-1", "nachbarn", 1, None, [2, 3, 4])
    db.aufgabe_speichern(conn, "baseline-1", "baseline", 1, None, [5, 6, 7])
    _bewerte(conn, "nachbarn-1", [2, 3, 4], "passt")
    _bewerte(conn, "baseline-1", [5, 6, 7], "passt")  # Zufall genauso gut -> kein Abstand
    conn.commit()
    ergebnis = evaluate.auswerten(conn)
    assert ergebnis["tor_nachbarn"] is False
    conn.close()


def test_bericht_wird_geschrieben(tmp_path):
    conn, _ = _datenbank_mit_vektoren(tmp_path)
    einstellungen = config.Einstellungen(
        ergebnisse=tmp_path / "ergebnisse", cache=tmp_path / "cache",
        datenbank=tmp_path / "t.db",
    )
    ziel = report.schreiben(conn, einstellungen)
    assert ziel.exists()
    assert "Phase 0.1" in ziel.read_text(encoding="utf-8")
    conn.close()
