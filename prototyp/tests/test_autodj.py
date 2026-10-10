"""Tests fuer autodj.py - den Hoertest-Renderer (Phase 1.1).

Geprueft wird, was den Hoertest-Vertrauen bricht, wenn es falsch ist: die
Merkmals-Uebersetzung aus der DB (Energie/Downbeats robust gegen kaputte Werte),
die Wahl des Master-Takts (groesster Tempo-Cluster = laengstes Set), die
Tempo-Faktoren auf den Master (ADR-014, erster Song = Master) und die
Blendenlaenge in ganzen Takten. Rein Merkmale/Mathe - kein Audio, kein Hoeren.
"""

from __future__ import annotations

import sqlite3

from klangbild import autodj, plan, resample

VERSION = "v1"


# --- Merkmals-Uebersetzung (robust gegen kaputte DB-Werte) -------------------


def test_energie_db_mittel_der_kurve():
    roh = "[[0.0, -10.0], [1.0, -20.0]]"
    assert autodj._energie_db(roh) == -15.0


def test_energie_db_akzeptiert_schon_geparste_liste():
    assert autodj._energie_db([[0.0, -6.0], [1.0, -8.0]]) == -7.0


def test_energie_db_leer_oder_kaputt_ist_none():
    assert autodj._energie_db("[]") is None
    assert autodj._energie_db(None) is None
    assert autodj._energie_db("kein json") is None


def test_downbeats_geparst_und_kaputt_abgefedert():
    assert autodj._downbeats("[0.0, 0.5, 1.0]") == [0.0, 0.5, 1.0]
    assert autodj._downbeats(None) == []
    assert autodj._downbeats("kaputt") == []


# --- Master-Takt, Faktoren, Blende (ADR-014) ---------------------------------


def _track(track_id: int, bpm: float | None, camelot: str | None = "8A"):
    from klangbild import plan

    return plan.Track(id=track_id, pfad=f"t{track_id}", bpm=bpm,
                      camelot=camelot, vektor=None)


def test_master_bpm_ist_der_start_song():
    index = {1: _track(1, 128.0), 2: _track(2, 120.0)}
    assert autodj._master_bpm([1, 2], index) == 128.0


def test_faktoren_erster_song_ist_master():
    index = {1: _track(1, 120.0), 2: _track(2, 120.0), 3: _track(3, 123.0)}
    faktoren = autodj._faktoren([1, 2, 3], index, master_bpm=120.0)
    assert faktoren[1] == 1.0                      # Master selbst
    assert faktoren[2] == 1.0                      # gleiches Tempo
    assert abs(faktoren[3] - resample.tempo_faktor(123.0, 120.0)) < 1e-12


def test_faktoren_werden_geklemmt_wie_resample():
    index = {1: _track(1, 120.0), 2: _track(2, 200.0)}  # weit ausserhalb +-1 %
    faktoren = autodj._faktoren([1, 2], index, master_bpm=120.0)
    assert faktoren[2] == resample.tempo_faktor(200.0, 120.0)  # geklemmt 0.99
    assert abs(faktoren[2] - 0.99) < 1e-9


def test_blende_s_sind_ganze_takte_des_masters():
    # 120 BPM -> Takt = 4*(60/120) = 2.0 s -> 8 Takte = 16.0 s.
    assert abs(autodj._blende_s(120.0) - 16.0) < 1e-9
    # 130 BPM -> Takt = 4*(60/130); 8 Takte darum.
    takt = 4 * (60.0 / 130.0)
    assert abs(autodj._blende_s(130.0) - 8 * takt) < 1e-9


# --- lade_tracks: Filter + Tempo-Cluster (mit echter In-Memory-DB) -----------


def _db_mit_features(rows):
    """rows: (id, bpm, downbeats_json, camelot, status[, pfad]).

    Spiegelt db.verbinden: row_factory = sqlite3.Row, damit autodj ueber
    Spaltennamen (z["bpm"]) liest wie in Produktion.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE tracks (id INTEGER PRIMARY KEY, pfad TEXT)")
    conn.execute(
        "CREATE TABLE features (track_id INTEGER, analyse_version TEXT, bpm REAL,"
        " beats_json TEXT, downbeats_json TEXT, key_name TEXT, key_camelot TEXT,"
        " key_vertrauen REAL, lufs REAL, energie_json TEXT, status TEXT)"
    )
    for zeile in rows:
        tid, bpm, downbeats, camelot, status = zeile[:5]
        pfad = zeile[5] if len(zeile) > 5 else f"t{tid}"
        conn.execute("INSERT INTO tracks (id, pfad) VALUES (?, ?)",
                     (tid, pfad))
        conn.execute(
            "INSERT INTO features (track_id, analyse_version, bpm, beats_json,"
            " downbeats_json, key_name, key_camelot, key_vertrauen, lufs,"
            " energie_json, status) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (tid, VERSION, bpm, "[]", downbeats, "C", camelot, 1.0, -10.0,
             "[[0,-10]]", status),
        )
    conn.commit()
    return conn


def test_lade_tracks_wirft_halbe_merkmale_raus():
    conn = _db_mit_features([
        (1, 120.0, "[0.0, 2.0]", "8A", "ok"),   # komplett -> bleibt
        (2, None, "[0.0, 2.0]", "8A", "ok"),    # kein bpm -> faellt raus
        (3, 120.0, "[]", "8A", "ok"),           # kein downbeat -> faellt raus
        (4, 120.0, "[0.4]", "8A", "fehler"),    # status nicht ok -> raus
    ])
    tracks, downbeats, pfade, _ = autodj.lade_tracks(
        conn, VERSION, start=None, laenge=0)
    assert [t.id for t in tracks] == [1]
    assert downbeats[1] == [0.0, 2.0]
    assert pfade[1] == "t1"
    conn.close()


def test_lade_tracks_waehlt_den_groessten_tempo_cluster():
    conn = _db_mit_features([
        (1, 100.0, "[0.1]", "8A", "ok"),
        (2, 120.0, "[0.2]", "8A", "ok"),
        (3, 121.0, "[0.3]", "9A", "ok"),   # rundet auf 120 -> gleicher Cluster
        (4, 120.0, "[0.4]", "8A", "ok"),
    ])
    _, _, _, start_id = autodj.lade_tracks(
        conn, VERSION, start=None, laenge=0)
    # Cluster 120 hat drei Mitglieder -> Start ist der erste davon (id 2).
    assert start_id == 2
    conn.close()


def test_lade_tracks_start_wird_respektiert():
    conn = _db_mit_features([
        (1, 120.0, "[0.1]", "8A", "ok"),
        (2, 100.0, "[0.2]", "9A", "ok"),
    ])
    _, _, _, start_id = autodj.lade_tracks(
        conn, VERSION, start=2, laenge=0)
    assert start_id == 2
    conn.close()


def test_lade_tracks_ohne_mischbare_ist_leer():
    conn = _db_mit_features([(1, None, "[]", "8A", "ok")])
    tracks, downbeats, pfade, start_id = autodj.lade_tracks(
        conn, VERSION, start=None, laenge=0)
    assert tracks == [] and downbeats == {} and pfade == {} and start_id is None
    conn.close()


def test_cluster_starts_meiden_ueberlappende_tempi():
    def t(i, bpm):
        return plan.Track(id=i, pfad="", bpm=bpm, camelot=None, energie_db=None, vektor=None)

    tracks = [t(1, 128.0), t(2, 128.2), t(3, 129.0), t(4, 140.0), t(5, 100.0)]
    # 129 liegt im 3-%-Gate von 128 -> kein eigenes Paar.
    assert autodj.cluster_starts(tracks, 3) == [1, 4, 5]


def test_lade_tracks_ueberspringt_dubletten():
    # Gleiche Aufnahme als MP3 und FLAC: identische Downbeats -> nur einmal ins Set.
    conn = _db_mit_features([
        (1, 120.0, "[0.0, 2.0]", "8A", "ok"),
        (2, 120.0, "[0.0, 2.0]", "8A", "ok"),
        (3, 121.0, "[0.5, 2.5]", "8A", "ok"),
    ])
    tracks, _, _, _ = autodj.lade_tracks(conn, VERSION, start=None, laenge=0)
    assert [t.id for t in tracks] == [1, 3]
    conn.close()


def test_lade_tracks_ueberspringt_dubletten_mit_anderem_schnitt():
    # Dieselbe Aufnahme, anders geschnitten (MP3 vs FLAC): Downbeats
    # verschieden, aber normalisierter Titel gleich -> nur einmal ins Set.
    conn = _db_mit_features([
        (1, 131.0, "[0.0, 2.0]", "8A", "ok",
         "I Feel Better - Oscar Farrell Remix-DJ SeinfeldOscar Farrell.mp3"),
        (2, 131.0, "[0.1, 2.1]", "8A", "ok",
         "I Feel Better - Oscar Farrell Remix - DJ Seinfeld, Oscar Farrell.flac"),
        (3, 132.0, "[0.5, 2.5]", "8A", "ok", "Anderer Song.mp3"),
    ])
    tracks, _, _, _ = autodj.lade_tracks(conn, VERSION, start=None, laenge=0)
    assert [t.id for t in tracks] == [1, 3]
    conn.close()
