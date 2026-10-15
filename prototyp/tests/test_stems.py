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
    e = Einstellungen(modus="manuell", takte=16, art="drums_zuerst", ausstieg="phrase")
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


# --- Stem-Vorrat (Ogg Vorbis, Kopf + Ende) ----------------------------------------------------

def _verlauf(sekunden: float) -> np.ndarray:
    t = np.arange(int(sekunden * RATE)) / RATE
    s = 0.3 * np.sin(2 * np.pi * (220 + 20 * t) * t)                 # aendert sich staendig
    return np.stack([s, 0.8 * s], axis=1).astype(np.float32)


def test_in_stuecken_ohne_naht(monkeypatch):
    monkeypatch.setattr(stems, "STUECK_S", 1.0)
    monkeypatch.setattr(stems, "RAND_S", 0.1)
    for laenge in (4.5, 4.05):                                         # auch mit sehr kurzem letztem Stueck
        x = _verlauf(laenge)
        teile = stems._in_stuecken(x, _fake_trenner)
        assert np.allclose(teile["drums"], 0.5 * x, atol=1e-6)        # Naehte unsichtbar


def test_vorrat_kopf_und_ende_springt_genau_und_summe_bleibt(tmp_path, monkeypatch):
    monkeypatch.setattr(stems, "VORRAT", tmp_path)
    monkeypatch.setattr(stems, "STUECK_S", 1.0)
    monkeypatch.setattr(stems, "RAND_S", 0.1)
    roh = _verlauf(10.0)
    teile = stems.vorrat_anlegen(7, roh, trenner=_fake_trenner)
    assert stems.vorrat_fertig(7) and np.allclose(sum(teile.values()), roh, atol=1e-6)
    assert stems.vorrat_bereiche(10.0) == [(0.0, 10.0)]
    # Fenster im Ende, mit Lautheitsangleich (x0.5) wie live.laden
    start = int(8.5 * RATE)
    fenster = 0.5 * roh[start:start + RATE]
    s = stems.aus_vorrat(7, 8.5, fenster)
    assert np.allclose(sum(s.values()), fenster, atol=1e-5)           # Rest-Trick: exakt
    erwartet = 0.5 * fenster                                           # Fake: drums = halbes Signal
    korr = np.corrcoef(s["drums"][:, 0], erwartet[:, 0])[0, 1]
    assert korr > 0.99 and abs(np.std(s["drums"]) / np.std(erwartet) - 1) < 0.05
    assert stems.aus_vorrat(7, 9.5, fenster) is None                   # ueber das Songende hinaus
    assert stems.bereit(f"7@{start}_{RATE}") and not stems.bereit(f"7@{int(9.5 * RATE)}_{RATE}")
    s2 = stems.trennen(fenster, f"7@{start}_{RATE}", trenner=lambda _x: 1 / 0)   # nie Demucs
    assert np.allclose(sum(s2.values()), fenster, atol=1e-5)


def test_acapella_mit_uebergabe_takt_haelt_a_gesang_bis_zur_letzten_zeile():
    n, takte, g = RATE * 16, 16, 10
    a = {**_stems_konstant(0.1, n, vocals=0.3)}
    b = {**_stems_konstant(0.1, n, vocals=0.3)}
    leer = lambda s: {**s, "vocals": 0 * s["vocals"]}   # noqa: E731
    gesang_a = np.abs(u.mischen_stems("acapella", a, leer(b), takte, g) - u.mischen_stems("acapella", leer(a), leer(b), takte, g))[:, 0]
    gesang_b = np.abs(u.mischen_stems("acapella", leer(a), b, takte, g) - u.mischen_stems("acapella", leer(a), leer(b), takte, g))[:, 0]
    takt = n // takte
    assert gesang_a[(g - 1) * takt] > 0.29                 # A singt bis zum Uebergabe-Takt voll
    assert np.max(np.minimum(gesang_a, gesang_b)) < 1e-3    # nie beide Stimmen (auch A's Echo ist verklungen)
    instr_a = u.mischen_stems("acapella", leer(a), {k: 0 * v for k, v in b.items()}, takte, g)
    assert np.abs(instr_a[5 * takt, 0]) < 1e-6             # A's Musik ist da schon weg


def test_acapella_bis_zum_fensterende_blendet_nicht_im_letzten_wort_aus():
    """Runde 6 "endet zu abrupt": singt A bis ans Fensterende, bleibt die Stimme voll, das Echo klingt danach."""
    n, takte = RATE * 8, 8
    a = _stems_konstant(0.0, n, vocals=0.3)
    leer = _stems_konstant(0.0, n)
    y, fahne = u.mischen_stems("acapella", a, leer, takte, takte, mit_fahne=True)
    assert y[-n // takte // 2:, 0].min() > 0.29            # letzter Takt: A singt voll (plus Echo)
    assert len(fahne) > RATE and np.abs(fahne[:RATE]).max() > 0.05


def test_gesang_zuerst_b_singt_vor_seiner_musik():
    n, takte, g = RATE * 16, 16, 8
    a = _stems_konstant(0.0, n)
    b = _stems_konstant(0.1, n, vocals=0.3)
    y = u.mischen_stems("gesang_zuerst", a, b, takte, g)
    takt = n // takte
    assert abs(y[4 * takt, 0] - 0.3) < 1e-6                # vor der Uebergabe: nur B's Gesang
    assert abs(y[-1, 0] - 0.6) < 1e-3                      # danach ganz B
    k = u.kurven("gesang_zuerst", takte, Einstellungen(art="gesang_zuerst", gesang_takt=g))
    assert k["b"]["gesang"][16] > 0.99 and k["b"]["drums"][16] < 0.01
