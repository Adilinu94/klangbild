"""HTTP-Smoke-Test fuer den Klangbild-Mixer (Phase 2) - ohne Soundkarte."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

import numpy as np
import pytest

from klangbild import live, mixer


def _get(url: str):
    with urllib.request.urlopen(url, timeout=5) as r:
        return json.loads(r.read())


def _post(url: str, daten, roh: bool = False):
    body = daten if roh else json.dumps(daten).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


@pytest.fixture
def basis(tmp_path):
    eintrag = live.Eintrag(id=7, pfad="/x/Song - Kuenstler.flac", bpm=128.0, camelot="8A",
                           downbeats=[0.0, 1.875], energie=[-20.0, -10.0])
    w = live.Wiedergabe({7: eintrag}, laden=lambda e: np.zeros((live.RATE * 5, 2), np.float32))
    m = mixer.Mixer(w, tmp_path / "k.db", "0.3.0", tmp_path / "upload", tmp_path / "einst.json")
    srv = mixer.server(m, "127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", m, tmp_path
    srv.shutdown()
    srv.server_close()


def test_api_bibliothek_play_und_zustand(basis, monkeypatch):
    from klangbild import stems

    url, _, tmp = basis
    monkeypatch.setattr(stems, "VORRAT", tmp / "vorrat")
    assert _get(url + "/api/bibliothek") == [
        {"id": 7, "titel": "Song - Kuenstler", "bpm": 128.0, "camelot": "8A", "stems": False}]
    z = _post(url + "/api/play", {"id": 7})
    assert z["spielt"] and z["aktuell"]["id"] == 7 and z["analyse"]["offen"] == 0
    assert _post(url + "/api/autodj", {"an": True})["autodj"] is True
    track = _get(url + "/api/track/7")
    assert abs(track["phrasen"][0]) < 1e-6 and abs(track["takte"][1] - 1.875) < 1e-6
    with urllib.request.urlopen(url + "/", timeout=5) as r:
        assert b"Klangbild Mixer" in r.read()


def test_einstellungen_werden_geprueft_und_gespeichert(basis):
    url, m, tmp = basis
    neu = _post(url + "/api/einstellungen", {"takte": 24, "max_bpm": 99, "art": "quatsch"})
    assert neu["takte"] == 24 and neu["max_bpm"] == 10.0 and neu["art"] == "auto"
    assert json.loads((tmp / "einst.json").read_text())["takte"] == 24
    assert m.w.einst.takte == 24


def test_upload_schreibt_nur_erlaubte_dateien(basis):
    url, m, tmp = basis
    antwort = _post(url + "/api/upload?name=..%2F..%2Fboese%20Datei.mp3", b"ID3abc", roh=True)
    assert antwort["datei"] == "boese Datei.mp3"
    assert (tmp / "upload" / "boese Datei.mp3").read_bytes() == b"ID3abc"
    assert m.offen == [tmp / "upload" / "boese Datei.mp3"]
    with pytest.raises(urllib.error.HTTPError) as fehler:
        _post(url + "/api/upload?name=virus.exe", b"MZ", roh=True)
    assert fehler.value.code == 400


def test_sicherer_name():
    assert mixer.sicherer_name("C:\\pfad\\Song <1>.flac") == "Song _1_.flac"
    assert mixer.sicherer_name("song.m4a") is None
    assert mixer.sicherer_name(".mp3") is None


def test_leeren_entfernt_alle(basis):
    url, m, _ = basis
    m.w.einreihen(7)
    m.w.einreihen(7)
    assert _post(url + "/api/leeren", {})["warteschlange"] == []


def test_zweiter_server_auf_demselben_port_scheitert():
    """Windows liess zwei Server auf 8767 zu; der Browser sprach mit dem alten Uebergangstest."""
    erster = mixer.EinzelServer(("127.0.0.1", 0), mixer._Handler)
    try:
        with pytest.raises(OSError):
            mixer.EinzelServer(("127.0.0.1", erster.server_address[1]), mixer._Handler)
    finally:
        erster.server_close()
