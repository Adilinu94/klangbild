"""Integrationstest der Bewertungsoberflaeche (ohne Browser)."""

from __future__ import annotations

import threading
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

import numpy as np
import soundfile as sf

from klangbild import blindui, config, db


def _wav(pfad, sekunden: float = 30.0, rate: int = 44100):
    t = np.arange(int(sekunden * rate)) / rate
    sf.write(str(pfad), (0.2 * np.sin(2 * np.pi * 440.0 * t)).astype(np.float32), rate)
    return pfad


def test_oberflaeche_von_liste_bis_bewertung(tmp_path):
    conn = db.verbinden(tmp_path / "t.db")
    wav = _wav(tmp_path / "a.wav")
    track_id, _ = db.track_eintragen(conn, str(wav), 1, 1.0, "h", "wav", 0, 1)
    vektor = np.ones(config.EINBETTUNG_DIM, dtype=np.float32)
    vektor /= np.linalg.norm(vektor)
    for position in config.AUSSCHNITTE:
        db.embedding_speichern(conn, track_id, position, "pseudo", vektor, str(wav), 0.0, 5.0)
    db.aufgabe_speichern(conn, "nachbarn-1", "nachbarn", track_id, None, [track_id])
    conn.commit()

    blindui._ZUSTAND = blindui.Zustand(conn, tmp_path / "cache")
    server = ThreadingHTTPServer(("127.0.0.1", 0), blindui._Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    basis = f"http://127.0.0.1:{port}"

    try:
        liste = urllib.request.urlopen(basis + "/").read().decode("utf-8")
        assert "Phase 0.1" in liste

        seite = urllib.request.urlopen(basis + "/task/nachbarn-1").read().decode("utf-8")
        assert "Treffer 1" in seite and "passt nicht" in seite

        audio = urllib.request.urlopen(basis + f"/audio/{track_id}/mitte").read()
        assert audio[:4] == b"RIFF"

        daten = urllib.parse.urlencode(
            {"aufgabe": "nachbarn-1", "rater": "test", f"urteil-{track_id}": "passt"}
        ).encode("utf-8")
        urllib.request.urlopen(urllib.request.Request(basis + "/rate", data=daten, method="POST"))
        assert len(db.bewertungen(conn)) == 1
    finally:
        server.shutdown()
        server.server_close()
        conn.close()
