"""Tests fuer das SQLite-Schema und die Zugriffe."""

from __future__ import annotations

import numpy as np

from klangbild import db


def _track(conn, pfad: str, audio_hash: str, n: int = 1):
    return db.track_eintragen(conn, pfad, 1000, 1234.0, audio_hash, "mp3", 0, 1000)


def test_track_eintragen_neu_und_wiedererkannt(tmp_path):
    conn = db.verbinden(tmp_path / "t.db")
    id1, neu1 = _track(conn, "a.mp3", "hash-a")
    id2, neu2 = _track(conn, "a.mp3", "hash-a")
    assert neu1 is True and neu2 is False and id1 == id2
    conn.close()


def test_hashwechsel_loescht_analyse(tmp_path):
    conn = db.verbinden(tmp_path / "t.db")
    track_id, _ = _track(conn, "a.mp3", "hash-a")
    db.features_speichern(conn, track_id, "0.1.0", {"status": "ok", "lufs": -14.0})
    db.embedding_speichern(conn, track_id, "mitte", "v1", np.ones(8, dtype=np.float32), "a.mp3", 0.0, 1.0)
    assert db.fehlende_features(conn, "0.1.0") == []
    # Anderer Inhalt -> alte Analyse und Vektoren verschwinden (ADR-007).
    _, geaendert = _track(conn, "a.mp3", "hash-b")
    assert geaendert is True
    assert db.fehlende_features(conn, "0.1.0") != []
    assert db.vektoren_laden(conn, "v1", "mitte")[0] == []
    conn.close()


def test_fehlende_vektoren_zaehlt_positionen(tmp_path):
    conn = db.verbinden(tmp_path / "t.db")
    track_id, _ = _track(conn, "a.mp3", "hash-a")
    for position in ("anfang", "mitte", "ende"):
        db.embedding_speichern(conn, track_id, position, "v1", np.ones(4, dtype=np.float32), "a.mp3", 0.0, 1.0)
    offen = db.fehlende_vektoren(conn, "v1", ("anfang", "mitte", "ende"))
    assert offen == []
    fehlt = db.fehlende_vektoren(conn, "v2", ("anfang", "mitte", "ende"))
    assert len(fehlt) == 1
    conn.close()


def test_alle_vektoren_mittelt(tmp_path):
    conn = db.verbinden(tmp_path / "t.db")
    track_id, _ = _track(conn, "a.mp3", "hash-a")
    db.embedding_speichern(conn, track_id, "anfang", "v1", np.array([1.0, 0.0], dtype=np.float32), "a.mp3", 0.0, 1.0)
    db.embedding_speichern(conn, track_id, "mitte", "v1", np.array([0.0, 1.0], dtype=np.float32), "a.mp3", 1.0, 2.0)
    db.embedding_speichern(conn, track_id, "ende", "v1", np.array([1.0, 0.0], dtype=np.float32), "a.mp3", 2.0, 3.0)
    ids, matrix, _ = db.alle_vektoren(conn, "v1")
    assert ids == [track_id]
    assert matrix.shape == (1, 2)
    assert abs(float(np.linalg.norm(matrix[0])) - 1.0) < 1e-6
    conn.close()


def test_aufgaben_und_bewertungen(tmp_path):
    conn = db.verbinden(tmp_path / "t.db")
    db.aufgabe_speichern(conn, "nachbarn-1", "nachbarn", 1, None, [2, 3, 4])
    db.bewertung_speichern(conn, "nachbarn-1", 2, 1, "passt", False, "test")
    db.bewertung_speichern(conn, "nachbarn-1", 3, 2, "passt_nicht", True, "test")
    assert len(db.aufgaben(conn, "nachbarn")) == 1
    zeilen = db.bewertungen(conn, "nachbarn")
    assert len(zeilen) == 2
    assert sum(1 for z in zeilen if z["unfall"]) == 1
    conn.close()
