"""Tests fuer uebergang.py - Beat-Warp, Uebergangsarten, Backen (Phase 2)."""

from __future__ import annotations

import numpy as np
import pytest

from klangbild import uebergang as u
from klangbild.einstellungen import Einstellungen

RATE = u.RATE


def _klicks(takte_s, dauer_s: float) -> np.ndarray:
    x = np.zeros(int(dauer_s * RATE), np.float32)
    k = (np.hanning(200) * np.sin(2 * np.pi * 3000 * np.arange(200) / RATE)).astype(np.float32)
    for t in takte_s:
        i = int(t * RATE)
        x[i:i + 200] += k[: len(x[i:i + 200])]
    return np.stack([x, x], axis=1)


def _onsets(y: np.ndarray) -> np.ndarray:
    e = np.abs(y[:, 0])
    schwelle, aus, i = 0.3 * e.max(), [], 0
    while i < len(e):
        if e[i] > schwelle:
            aus.append(i / RATE)
            i += int(0.2 * RATE)
        else:
            i += 1
    return np.array(aus)


def _eintrag(tid=1, bpm=120.0, dauer=60.0, abschnitte=()):
    periode = 240.0 / bpm
    return u.Eintrag(id=tid, pfad=f"/x/{tid}.flac", bpm=bpm, camelot="8A",
                     downbeats=list(np.arange(0.0, dauer, periode)), abschnitte=list(abschnitte))


@pytest.mark.parametrize("keylock", [True, False])
def test_warp_legt_takte_aufs_zielraster(keylock):
    quell = np.arange(0.5, 20.0, 2.0)                 # 120 BPM (Takte)
    ziel = 0.5 + np.arange(len(quell)) * 1.92          # 125 BPM
    y = u.warp(_klicks(quell, 21.0), quell, ziel, keylock)
    assert abs(len(y) - (ziel[-1] - ziel[0]) * RATE) <= 1
    treffer = _onsets(y)
    assert np.max(np.abs(treffer - (ziel[:len(treffer)] - ziel[0]))) < 0.005


def test_keylock_haelt_die_tonhoehe():
    t = np.arange(RATE * 4) / RATE
    sinus = np.stack([np.sin(2 * np.pi * 440 * t)] * 2, axis=1).astype(np.float32)
    y = u.warp(sinus, np.array([0.0, 4.0]), np.array([0.0, 3.6]), keylock=True)
    spitze = np.argmax(np.abs(np.fft.rfft(y[:, 0]))) * RATE / len(y)
    assert abs(spitze - 440.0) < 3.0


@pytest.mark.parametrize("art", ["eq", "crossfade", "filter", "echo", "schnitt"])
def test_mischen_kein_pegelloch_und_richtige_enden(art):
    n = RATE * 8
    a = np.full((n, 2), 0.3, np.float32)
    b = np.full((n, 2), 0.3, np.float32)
    y = u.mischen(art, a, b, takte=4)
    assert y.shape == (n, 2)
    assert abs(y[-1, 0] - 0.3) < 0.05             # am Ende nur B
    if art in ("crossfade", "eq", "filter"):
        rms = np.sqrt(np.mean(y[: n // 2, 0] ** 2))
        assert rms > 0.25                          # kein Loch in der Blende


def _spur(e: u.Eintrag, dauer=60.0, wert=0.2):
    return u.Spur.roh(e, np.full((int(dauer * RATE), 2), wert, np.float32))


def test_backen_rampe_endet_im_originaltempo_von_b():
    a, b = _eintrag(1, 120.0), _eintrag(2, 124.0)
    e = Einstellungen(takte=8, art="eq", ausstieg="phrase", tempo_modus="rampe", max_bpm=5.0)
    g = u.backen(_spur(a), b, np.full((60 * RATE, 2), 0.4, np.float32), e, ab_s=1.0)
    assert g.info["sync"] and g.info["art"] == "eq" and g.info["takte"] == 8
    # Blendenbeginn in A auf einem Phrasenanfang:
    assert abs(g.start_n / RATE % (8 * 2.0)) < 1e-3
    # Nach der Blende laeuft B im Originaltempo (124 BPM):
    assert abs(g.spur.bpm_bei(len(g.spur.puffer) / RATE - 5) - 124.0) < 0.5


def test_backen_b_an_a_behaelt_das_tempo_von_a():
    a, b = _eintrag(1, 120.0), _eintrag(2, 124.0)
    e = Einstellungen(takte=8, art="eq", ausstieg="phrase", tempo_modus="b_an_a", max_bpm=5.0)
    g = u.backen(_spur(a), b, np.full((60 * RATE, 2), 0.4, np.float32), e, ab_s=1.0, )
    assert abs(g.spur.bpm_bei(30.0) - 120.0) < 0.5
    # Originalzeit von B laesst sich zurueckrechnen (Anzeige/Springen):
    assert abs(g.spur.zu_original(g.spur.zu_puffer(40.0)) - 40.0) < 1e-6


def test_backen_ueber_der_tempogrenze_faellt_auf_echo():
    a, b = _eintrag(1, 120.0), _eintrag(2, 140.0)
    e = Einstellungen(takte=16, art="eq", ausstieg="phrase", max_bpm=5.0)
    g = u.backen(_spur(a), b, np.full((60 * RATE, 2), 0.4, np.float32), e, ab_s=1.0)
    assert not g.info["sync"] and g.info["art"] == "echo" and g.info["takte"] == 4


def test_backen_weiter_startet_am_naechsten_phrasenanfang():
    a, b = _eintrag(1, 120.0), _eintrag(2, 120.0)
    e = Einstellungen(weiter_takte=4, weiter_ab="phrase")
    g = u.backen(_spur(a), b, np.full((60 * RATE, 2), 0.4, np.float32), e, ab_s=5.0, weiter=True)
    assert abs(g.start_n / RATE - 16.0) < 1e-3       # erste Phrase ab 5 s = Takt 8 = 16 s
    assert g.info["takte"] == 4


def test_backen_outro_und_drop():
    a = _eintrag(1, 120.0, abschnitte=[10.0, 30.0, 47.0])   # Outro ab ~48 s
    b = _eintrag(2, 120.0, abschnitte=[15.0, 40.0])         # Drop ab ~16 s
    e = Einstellungen(takte=4, art="crossfade", ausstieg="outro", einstieg="drop")
    g = u.backen(_spur(a), b, np.full((60 * RATE, 2), 0.4, np.float32), e, ab_s=1.0)
    assert abs(g.start_n / RATE - 48.0) < 1e-3
    assert abs(g.spur.zu_original(0.0) - 16.0) < 1e-3


def test_periode_robust_gegen_intro_ausreisser_und_raster():
    takte = np.round(np.arange(0.0, 60.0, 240.0 / 130.0) / 0.02) * 0.02   # 20-ms-Raster
    takte = np.concatenate([[0.0, 0.9, 2.5], takte[3:]])                 # wirres Intro
    assert abs(240.0 / u._periode(takte, 0) - 130.0) < 1.0
    assert abs(240.0 / u._periode(takte, 15) - 130.0) < 0.3
