"""Tests fuer stems.py und die Stem-Uebergaenge - mit Fake-Trenner statt Demucs."""

from __future__ import annotations

import numpy as np

from klangbild import stems
from klangbild import uebergang as u
from klangbild.einstellungen import Einstellungen

RATE = u.RATE


def _fake_trenner(audio):
    # Absichtlich unvollstaendig: drums = halbes Signal, vocals = Viertel, Rest fehlt.
    return {"drums": audio * 0.5, "bass": audio * 0.0, "other": audio * 0.0, "vocals": audio * 0.25}


def test_rest_trick_summe_ist_original_und_cache(tmp_path):
    audio = np.random.default_rng(0).normal(0, 0.1, (RATE, 2)).astype(np.float32)
    aufrufe = []

    def trenner(x):
        aufrufe.append(1)
        return _fake_trenner(x)

    s = stems.trennen(audio, "t1", trenner=trenner, cache=tmp_path)
    assert np.allclose(sum(s.values()), audio, atol=1e-6)
    s2 = stems.trennen(audio, "t1", trenner=trenner, cache=tmp_path)   # aus dem Cache
    assert len(aufrufe) == 1
    assert np.allclose(sum(s2.values()), audio, atol=2e-3)              # float16-Cache


def _stems_konstant(wert: float, n: int, vocals: float = 0.0):
    s = {k: np.full((n, 2), wert, np.float32) for k in stems.NAMEN}
    s["vocals"] = np.full((n, 2), vocals, np.float32)
    return s


def test_gesangsschutz_nie_zwei_stimmen_gleichzeitig():
    n = RATE * 4
    a, b = _stems_konstant(0.1, n, vocals=0.3), _stems_konstant(0.1, n, vocals=0.3)
    nur_a = u.mischen_stems("gesangsschutz", a, {**b, "vocals": np.zeros((n, 2), np.float32)})
    nur_b = u.mischen_stems("gesangsschutz", {**a, "vocals": np.zeros((n, 2), np.float32)}, b)
    leer = u.mischen_stems("gesangsschutz", {**a, "vocals": 0 * a["vocals"]}, {**b, "vocals": 0 * b["vocals"]})
    gesang_a, gesang_b = np.abs(nur_a - leer)[:, 0], np.abs(nur_b - leer)[:, 0]
    assert np.max(np.minimum(gesang_a, gesang_b)) < 1e-6      # nie beide hoerbar


def test_acapella_haelt_gesang_von_a_bis_kurz_vor_schluss():
    n = RATE * 4
    a = _stems_konstant(0.0, n, vocals=0.3)
    b = _stems_konstant(0.0, n)
    y = u.mischen_stems("acapella", a, b)
    assert abs(y[int(0.8 * n), 0] - 0.3) < 1e-6 and abs(y[-1, 0]) < 0.02


def _eintrag(tid, bpm=120.0, dauer=90.0):
    return u.Eintrag(id=tid, pfad=f"/x/{tid}.flac", bpm=bpm, camelot="8A",
                     downbeats=list(np.arange(0.0, dauer, 240.0 / bpm)))


def _quelle(gesang: float):
    def q(audio, _schluessel):
        s = _stems_konstant(0.0, len(audio))
        s["drums"], s["vocals"] = audio * (1 - gesang), audio * gesang
        return s
    return q


def test_backen_auto_mit_stems_waehlt_gesangsschutz_wenn_beide_singen():
    a = u.Spur.roh(_eintrag(1), np.full((90 * RATE, 2), 0.2, np.float32))
    e = Einstellungen(takte=4, art="auto", ausstieg="phrase")
    g = u.backen(a, _eintrag(2), np.full((90 * RATE, 2), 0.2, np.float32), e, ab_s=1.0,
                 stem_quelle=_quelle(0.5), jetzt_s=0.0)
    assert g.info["stems"] and g.info["art"] == "gesangsschutz"
    g = u.backen(a, _eintrag(2), np.full((90 * RATE, 2), 0.2, np.float32), e, ab_s=1.0,
                 stem_quelle=_quelle(0.0), jetzt_s=0.0)
    assert g.info["stems"] and g.info["art"] == "eq"


def test_backen_stems_zu_knapp_faellt_auf_eq():
    a = u.Spur.roh(_eintrag(1), np.full((90 * RATE, 2), 0.2, np.float32))
    e = Einstellungen(takte=16, art="drums_zuerst", ausstieg="phrase")
    jetzt = 60.0   # Blende beginnt bei ~64 s: keine 2 Minuten fuer Demucs
    g = u.backen(a, _eintrag(2), np.full((90 * RATE, 2), 0.2, np.float32), e, ab_s=jetzt + 3,
                 stem_quelle=_quelle(0.5), jetzt_s=jetzt)
    assert not g.info["stems"] and g.info["art"] == "eq" and "knapp" in g.info["hinweis"]


def test_vorrechnen_fuellt_cache_und_trennen_wartet_darauf(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    pool = ThreadPoolExecutor(max_workers=1)
    monkeypatch.setattr(stems, "_pool", lambda: pool)
    monkeypatch.setattr(stems, "_trenne", _fake_trenner)
    audio = np.random.default_rng(1).normal(0, 0.1, (RATE // 2, 2)).astype(np.float32)
    stems.vorrechnen(audio, "v1", cache=tmp_path)
    nie = lambda _x: (_ for _ in ()).throw(AssertionError("doppelt getrennt"))  # noqa: E731
    s = stems.trennen(audio, "v1", trenner=nie, cache=tmp_path)   # wartet bzw. liest Cache
    assert np.allclose(sum(s.values()), audio, atol=2e-3)
    pool.shutdown(wait=True)
    assert stems.bereit("v1", cache=tmp_path)
