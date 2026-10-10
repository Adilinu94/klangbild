"""SQLite-Schema und Zugriffe des Prototyps.

Das Schema ist absichtlich **nah an der spaeteren Android-Datenbank** (ADR-007,
ADR-013): `analysis_version` und `modell_version` gehoeren dazu, sonst vergleicht
der Hoehrtest nach einem Modellwechsel alte mit neuen Werten.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (
    id            INTEGER PRIMARY KEY,
    pfad          TEXT NOT NULL UNIQUE,
    groesse       INTEGER NOT NULL,
    mtime         REAL NOT NULL,
    audio_hash    TEXT,
    container     TEXT,
    hash_von      INTEGER,
    hash_bis      INTEGER,
    hinzugefuegt  TEXT
);

CREATE TABLE IF NOT EXISTS features (
    track_id         INTEGER NOT NULL,
    analyse_version  TEXT NOT NULL,
    bpm              REAL,
    beats_json       TEXT,
    downbeats_json   TEXT,
    key_name         TEXT,
    key_camelot      TEXT,
    key_vertrauen    REAL,
    lufs             REAL,
    true_peak        REAL,
    energie_json     TEXT,
    abschnitte_json  TEXT,
    status           TEXT,
    hinzugefuegt     TEXT,
    PRIMARY KEY (track_id, analyse_version)
);

CREATE TABLE IF NOT EXISTS embeddings (
    track_id        INTEGER NOT NULL,
    position        TEXT NOT NULL,
    modell_version  TEXT NOT NULL,
    dim             INTEGER NOT NULL,
    vektor          BLOB NOT NULL,
    clip_pfad       TEXT,
    start_s         REAL,
    ende_s          REAL,
    hinzugefuegt    TEXT,
    PRIMARY KEY (track_id, position, modell_version)
);

CREATE TABLE IF NOT EXISTS aufgaben (
    id             TEXT PRIMARY KEY,
    art            TEXT NOT NULL,
    seed_track_id  INTEGER,
    text           TEXT,
    tracks_json    TEXT NOT NULL,
    erstellt       TEXT
);

CREATE TABLE IF NOT EXISTS bewertungen (
    id          INTEGER PRIMARY KEY,
    aufgabe_id  TEXT NOT NULL,
    track_id    INTEGER,
    rang        INTEGER,
    urteil      TEXT,
    unfall      INTEGER DEFAULT 0,
    rater       TEXT,
    zeit        TEXT
);

CREATE INDEX IF NOT EXISTS idx_bewertungen_aufgabe ON bewertungen(aufgabe_id);
CREATE INDEX IF NOT EXISTS idx_embeddings_version ON embeddings(modell_version);
"""


def _jetzt() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def verbinden(pfad: str | Path) -> sqlite3.Connection:
    pfad = Path(pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    # timeout: ein paralleler Leser (report, serve) darf einen langen Lauf nicht abbrechen.
    conn = sqlite3.connect(str(pfad), check_same_thread=False, timeout=60)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


@dataclass(frozen=True)
class TrackZeile:
    id: int
    pfad: str
    audio_hash: str | None


def track_eintragen(
    conn: sqlite3.Connection,
    pfad: str | Path,
    groesse: int,
    mtime: float,
    audio_hash: str,
    container: str,
    hash_von: int,
    hash_bis: int,
) -> tuple[int, bool]:
    """Traegt einen Track ein. Liefert (track_id, wurde_neu_oder_geaendert)."""
    pfad = str(pfad)
    vorhanden = conn.execute(
        "SELECT id, audio_hash FROM tracks WHERE pfad = ?", (pfad,)
    ).fetchone()
    if vorhanden is None:
        cur = conn.execute(
            "INSERT INTO tracks(pfad, groesse, mtime, audio_hash, container, hash_von,"
            " hash_bis, hinzugefuegt) VALUES (?,?,?,?,?,?,?,?)",
            (pfad, groesse, mtime, audio_hash, container, hash_von, hash_bis, _jetzt()),
        )
        return int(cur.lastrowid), True
    geaendert = vorhanden["audio_hash"] != audio_hash
    conn.execute(
        "UPDATE tracks SET groesse=?, mtime=?, audio_hash=?, container=?, hash_von=?,"
        " hash_bis=? WHERE id=?",
        (groesse, mtime, audio_hash, container, hash_von, hash_bis, vorhanden["id"]),
    )
    if geaendert:
        # Anderer Inhalt -> alte Analyse und Vektoren entfernen (ADR-007).
        conn.execute("DELETE FROM features WHERE track_id=?", (vorhanden["id"],))
        conn.execute("DELETE FROM embeddings WHERE track_id=?", (vorhanden["id"],))
    return int(vorhanden["id"]), geaendert


def tracks_mit_status(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT t.id, t.pfad, t.audio_hash,
               f.status          AS analyse_status,
               (SELECT COUNT(*) FROM embeddings e WHERE e.track_id = t.id) AS vektoren
        FROM tracks t
        LEFT JOIN features f ON f.track_id = t.id AND f.analyse_version = ?
        ORDER BY t.pfad
        """,
        (config.ANALYSE_VERSION,),
    ).fetchall()


def fehlende_features(conn: sqlite3.Connection, version: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT t.id, t.pfad FROM tracks t
        LEFT JOIN features f ON f.track_id = t.id AND f.analyse_version = ?
        WHERE f.track_id IS NULL
        ORDER BY t.id
        """,
        (version,),
    ).fetchall()


def fehlende_vektoren(
    conn: sqlite3.Connection, version: str, positionen: tuple[str, ...]
) -> list[sqlite3.Row]:
    platzhalter = ",".join("?" for _ in positionen)
    return conn.execute(
        f"""
        SELECT t.id, t.pfad,
               (SELECT COUNT(*) FROM embeddings e
                 WHERE e.track_id = t.id AND e.modell_version = ?
                   AND e.position IN ({platzhalter})) AS vorhanden
        FROM tracks t
        WHERE vorhanden < ?
        ORDER BY t.id
        """,
        (version, *positionen, len(positionen)),
    ).fetchall()


def features_speichern(conn: sqlite3.Connection, track_id: int, version: str, werte: dict) -> None:
    conn.execute(
        """
        INSERT INTO features(track_id, analyse_version, bpm, beats_json, downbeats_json,
            key_name, key_camelot, key_vertrauen, lufs, true_peak, energie_json,
            abschnitte_json, status, hinzugefuegt)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(track_id, analyse_version) DO UPDATE SET
            bpm=excluded.bpm, beats_json=excluded.beats_json,
            downbeats_json=excluded.downbeats_json, key_name=excluded.key_name,
            key_camelot=excluded.key_camelot, key_vertrauen=excluded.key_vertrauen,
            lufs=excluded.lufs, true_peak=excluded.true_peak,
            energie_json=excluded.energie_json, abschnitte_json=excluded.abschnitte_json,
            status=excluded.status, hinzugefuegt=excluded.hinzugefuegt
        """,
        (
            track_id,
            version,
            werte.get("bpm"),
            json.dumps(werte.get("beats", [])),
            json.dumps(werte.get("downbeats", [])),
            werte.get("key_name"),
            werte.get("key_camelot"),
            werte.get("key_vertrauen"),
            werte.get("lufs"),
            werte.get("true_peak"),
            json.dumps(werte.get("energie", [])),
            json.dumps(werte.get("abschnitte", [])),
            werte.get("status", "ok"),
            _jetzt(),
        ),
    )


def features_laden(conn: sqlite3.Connection, version: str) -> list[sqlite3.Row]:
    """Alle analysierten Tracks (status 'ok') mit ihren Merkmalen zuruecklesen.

    Der Planer (Phase 1) braucht BPM, Camelot, Beats/Downbeats und Energie als
    Merkmal-Struct, nicht als Rohtabellen-Zeile. `status='ok'` haelt fehlerhafte
    oder zu kurze Analysen aus dem Set heraus - sonst plant der Auto-DJ auf
    kaputten Merkmalen. Sortiert nach id, damit die Reihenfolge reproduzierbar ist.
    """
    return conn.execute(
        "SELECT t.id, t.pfad, f.bpm, f.beats_json, f.downbeats_json,"
        "       f.key_name, f.key_camelot, f.key_vertrauen, f.lufs,"
        "       f.energie_json, f.status"
        " FROM tracks t JOIN features f ON f.track_id = t.id AND f.analyse_version = ?"
        " WHERE f.status = 'ok' ORDER BY t.id",
        (version,),
    ).fetchall()


def embedding_speichern(
    conn: sqlite3.Connection,
    track_id: int,
    position: str,
    version: str,
    vektor: np.ndarray,
    clip_pfad: str | None,
    start_s: float | None,
    ende_s: float | None,
) -> None:
    conn.execute(
        """
        INSERT INTO embeddings(track_id, position, modell_version, dim, vektor,
            clip_pfad, start_s, ende_s, hinzugefuegt)
        VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT(track_id, position, modell_version) DO UPDATE SET
            dim=excluded.dim, vektor=excluded.vektor, clip_pfad=excluded.clip_pfad,
            start_s=excluded.start_s, ende_s=excluded.ende_s, hinzugefuegt=excluded.hinzugefuegt
        """,
        (
            track_id,
            position,
            version,
            int(vektor.size),
            vektor.astype(np.float32).tobytes(),
            clip_pfad,
            start_s,
            ende_s,
            _jetzt(),
        ),
    )


def vektoren_laden(
    conn: sqlite3.Connection, version: str, position: str
) -> tuple[list[int], np.ndarray, list[str]]:
    """Liefert (track_ids, Matrix [n x dim], clip_pfade) fuer eine Position."""
    zeilen = conn.execute(
        "SELECT track_id, dim, vektor, clip_pfad FROM embeddings"
        " WHERE modell_version=? AND position=? ORDER BY track_id",
        (version, position),
    ).fetchall()
    ids: list[int] = []
    pfade: list[str] = []
    vektoren = []
    for zeile in zeilen:
        ids.append(int(zeile["track_id"]))
        pfade.append(zeile["clip_pfad"] or "")
        vektoren.append(np.frombuffer(zeile["vektor"], dtype=np.float32))
    if not vektoren:
        return [], np.zeros((0, 0), dtype=np.float32), []
    return ids, np.vstack(vektoren), pfade


def alle_vektoren(conn: sqlite3.Connection, version: str) -> tuple[list[int], np.ndarray, list[str]]:
    """Mittelt die drei Ausschnitte je Track zu einem Vektor (fuer Nachbarsuche)."""
    ids, matrix, _ = vektoren_laden(conn, version, "anfang")
    if not ids:
        return [], np.zeros((0, 0), dtype=np.float32), []
    gesamt = np.zeros_like(matrix)
    anzahl = np.zeros((matrix.shape[0], 1), dtype=np.float32)
    for position in ("anfang", "mitte", "ende"):
        pids, pmatrix, _ = vektoren_laden(conn, version, position)
        index = {tid: i for i, tid in enumerate(ids)}
        for zeile, tid in enumerate(pids):
            if tid in index:
                gesamt[index[tid]] += pmatrix[zeile]
                anzahl[index[tid]] += 1
    normen = np.linalg.norm(gesamt, axis=1, keepdims=True)
    return ids, (gesamt / np.maximum(normen, 1e-9)).astype(np.float32), [""] * len(ids)


def aufgabe_speichern(
    conn: sqlite3.Connection,
    aufgabe_id: str,
    art: str,
    seed_track_id: int | None,
    text: str | None,
    tracks: list[int],
) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO aufgaben(id, art, seed_track_id, text, tracks_json, erstellt)"
        " VALUES (?,?,?,?,?,?)",
        (aufgabe_id, art, seed_track_id, text, json.dumps(tracks), _jetzt()),
    )


def aufgaben(conn: sqlite3.Connection, art: str | None = None) -> list[sqlite3.Row]:
    if art:
        return conn.execute(
            "SELECT * FROM aufgaben WHERE art=? ORDER BY id", (art,)
        ).fetchall()
    return conn.execute("SELECT * FROM aufgaben ORDER BY id").fetchall()


def bewertung_speichern(
    conn: sqlite3.Connection,
    aufgabe_id: str,
    track_id: int,
    rang: int,
    urteil: str,
    unfall: bool,
    rater: str,
) -> None:
    conn.execute(
        "INSERT INTO bewertungen(aufgabe_id, track_id, rang, urteil, unfall, rater, zeit)"
        " VALUES (?,?,?,?,?,?,?)",
        (aufgabe_id, track_id, rang, urteil, 1 if unfall else 0, rater, _jetzt()),
    )


def bewertungen(conn: sqlite3.Connection, art: str | None = None) -> list[sqlite3.Row]:
    if art:
        return conn.execute(
            "SELECT b.* FROM bewertungen b JOIN aufgaben a ON a.id = b.aufgabe_id"
            " WHERE a.art=? ORDER BY b.id",
            (art,),
        ).fetchall()
    return conn.execute("SELECT * FROM bewertungen ORDER BY id").fetchall()


def status(conn: sqlite3.Connection, analyse_version: str, modell_version: str) -> dict:
    def zaehler(sql: str, *werte) -> int:
        return int(conn.execute(sql, werte).fetchone()[0])

    return {
        "tracks": zaehler("SELECT COUNT(*) FROM tracks"),
        "features": zaehler(
            "SELECT COUNT(*) FROM features WHERE analyse_version=?", analyse_version
        ),
        "vektoren": zaehler(
            "SELECT COUNT(*) FROM embeddings WHERE modell_version=?", modell_version
        ),
        "aufgaben": zaehler("SELECT COUNT(*) FROM aufgaben"),
        "bewertungen": zaehler("SELECT COUNT(*) FROM bewertungen"),
    }
