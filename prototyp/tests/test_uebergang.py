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


@pytest.mark.parametrize("art", ["eq", "crossfade", "filter", "echo", "schnitt",
                                 "drums_zuerst", "acapella", "gesangsschutz"])
def test_kurven_a_geht_b_kommt(art):
    k = u.kurven(art, 4)
    assert k["b"]["lautstaerke"][-1] > 0.95
    assert k["a"]["lautstaerke"][-1] < 0.1 or art == "acapella"   # Acapella: A-Instrumente sind schon weg
    assert all(len(v) == u.KURVEN_PUNKTE for seite in k.values() for v in seite.values())


def test_kurven_passen_zum_ton_crossfade():
    # Lautstaerke-Kurve = tatsaechlicher Pegelverlauf der Blende (konstante Signale)
    n = u.KURVEN_PUNKTE * 1000
    y = u.mischen("crossfade", np.full((n, 2), 1.0, np.float32), np.zeros((n, 2), np.float32), 4)
    kurve = u.kurven("crossfade", 4)["a"]["lautstaerke"]
    assert np.allclose(y[::1000, 0], kurve, atol=0.01)


def test_kurven_eq_bass_tausch_in_der_mitte():
    bass_a = u.kurven("eq", 8)["a"]["bass"]
    assert bass_a[u.KURVEN_PUNKTE // 2 - 1] == 1.0 and bass_a[u.KURVEN_PUNKTE // 2] == 0.0


# --- Knack-Fix: keine Spruenge beim Keylock-Dehnen, kein Uebersteuern ------------------------

def _sinus(dauer_s: float, hz: float = 220.0) -> np.ndarray:
    t = np.arange(int(dauer_s * RATE)) / RATE
    s = (0.5 * np.sin(2 * np.pi * hz * t)).astype(np.float32)
    return np.stack([s, s], axis=1)


def test_warp_keylock_rampe_ohne_spruenge_auch_an_den_raendern():
    # Frueher: python-stretch-Aufrufe je 4096 Samples -> Sprung an jeder Stueckgrenze.
    audio = _sinus(30.0)
    quell = 2.0 + np.arange(9) * 1.875                                    # 128 BPM
    ziel = quell[0] + np.concatenate([[0], np.cumsum(1.875 + (240 / 123 - 1.875) * (np.arange(8) + .5) / 8)])
    y = u.warp(audio, quell, ziel, True, rand_vorn=True, rand_hinten=True)
    i0, i1 = int(quell[0] * RATE), int(round(quell[-1] * RATE))
    ganz = np.concatenate([audio[i0 - 500:i0], y, audio[i1:i1 + 500]])   # mit Original davor/danach
    d2 = np.abs(np.diff(ganz[:, 0], 2))
    assert d2.max() < 3 * 0.5 * (2 * np.pi * 220 / RATE) ** 2           # nur die Kruemmung des Sinus
    assert np.abs(y[RATE:-RATE, 0]).max() > 0.45                        # kein Pegelloch an den Naehten


def test_dehn_pool_liefert_dasselbe_wie_lokal():
    audio = _sinus(6.0)
    quell, ziel = np.array([0.5, 2.5, 4.5]), np.array([0.5, 2.4, 4.3])
    lokal = u.warp(audio, quell, ziel, True)
    u.dehn_pool_starten()
    try:
        im_pool = u.warp(audio, quell, ziel, True)
    finally:
        u._DEHN_POOL.shutdown()
        u._DEHN_POOL = None
    assert np.allclose(lokal, im_pool, atol=1e-6)


def test_begrenzen_haelt_die_decke_und_laesst_leises_in_ruhe():
    x = np.concatenate([_sinus(2.0) * 0.5, _sinus(2.0) * 3.0, _sinus(2.0) * 0.5])
    leise = x[:RATE].copy()
    u._begrenzen(x, len(x))
    assert np.abs(x).max() <= u.DECKE + 1e-6
    assert np.allclose(x[:RATE], leise)


# --- Art "eigen": jede Auswahl ergibt einen anderen Uebergang ---------------------------------

from klangbild import einstellungen as einst_mod  # noqa: E402

_TAKT_N = np.round(np.arange(9) * RATE * 0.5).astype(int)   # 8 Takte a 0,5 s


def _ab():
    rng = np.random.default_rng(1)
    a = (rng.standard_normal((4 * RATE, 2)) * 0.2).astype(np.float32)
    b = (rng.standard_normal((4 * RATE, 2)) * 0.2).astype(np.float32)
    a[::RATE // 8] += 0.6   # Schlaege, damit Loops/Echos etwas zu wiederholen haben
    return a, b


@pytest.mark.parametrize("feld,auswahl", [("lautstaerke", einst_mod.LAUTSTAERKE), ("eq", einst_mod.EQ),
                                          ("filter", einst_mod.FILTER), ("effekt", einst_mod.EFFEKT),
                                          ("effekt_ein", einst_mod.EFFEKT_EIN), ("loop", einst_mod.LOOP),
                                          ("trick", einst_mod.TRICK)])
def test_eigen_jede_auswahl_klingt_anders(feld, auswahl):
    a, b = _ab()
    ergebnisse = []
    # "auto" waehlt backen (loop_waehlen); ein Loop so lang wie das Fenster ist das Original selbst
    auswahl = [w for w in auswahl if w != "auto" and not (w.isdigit() and int(w) >= 4 * 8)
               and w not in ("bass_takt", "wechsel")]   # brauchen Bass-/Drop-Takt (setzt die Regie)
    for wert in auswahl:
        y, fahne = u.mischen_eigen(a, b, Einstellungen(art="eigen", **{feld: wert}), _TAKT_N)
        assert y.shape == a.shape and np.isfinite(y).all() and np.isfinite(fahne).all()
        if feld != "effekt" or wert.endswith("_ab") or wert == "keiner":
            assert abs(y[-1, 0] - b[-1, 0]) < 0.05 or feld in ("effekt_ein", "trick")   # am Ende nur B
        ergebnisse.append(np.concatenate([y, fahne]))
    for i in range(len(ergebnisse)):
        for j in range(i):
            n = min(len(ergebnisse[i]), len(ergebnisse[j]))
            unterschied = np.abs(ergebnisse[i][:n] - ergebnisse[j][:n]).max()
            assert unterschied > 1e-3 or len(ergebnisse[i]) != len(ergebnisse[j]), (auswahl[i], auswahl[j])


def test_eigen_fahne_klingt_nach_oder_wird_abgeschnitten():
    a, b = _ab()
    _, nach = u.mischen_eigen(a, b, Einstellungen(art="eigen", effekt="hall_ende_aus"), _TAKT_N)
    _, ab = u.mischen_eigen(a, b, Einstellungen(art="eigen", effekt="hall_ende_ab"), _TAKT_N)
    assert len(nach) > RATE and np.abs(nach).max() > 0.01
    assert len(ab) == 0


def test_eigen_loop_wiederholt_den_schlag():
    t = np.arange(4 * RATE) / RATE
    chirp = (0.5 * np.sin(2 * np.pi * (200 + 100 * t) * t)).astype(np.float32)   # nie gleich
    a = np.stack([chirp, chirp], axis=1)
    takt = RATE // 2
    # 4-Beat-Loop: ab Blendenbeginn wird Takt 1 wiederholt (Outro festhalten)
    y = u._loopen(a, _TAKT_N, u._loop_plan(Einstellungen(art="eigen", loop="4"), 8))
    for k in (1, 5, 7):
        assert np.allclose(y[k * takt + 300:(k + 1) * takt - 300], a[300:takt - 300], atol=1e-5)
    # 1-Beat-Loop: erst 2 Takte bevor A leise wird (nahtlos: bei 2/3), davor Original
    plan = u._loop_plan(Einstellungen(art="eigen", loop="1"), 8)
    assert plan == [(24, 64, 2)]
    y = u._loopen(a, _TAKT_N, plan)
    assert np.allclose(y[:3 * takt], a[:3 * takt])
    schlag = takt // 4
    assert np.allclose(y[4 * takt + 300:4 * takt + schlag - 300], a[3 * takt + 300:3 * takt + schlag - 300], atol=1e-5)


def test_loop_info_fuer_die_anzeige():
    e = Einstellungen(art="eigen", loop="rolle", lautstaerke="hart_aus")
    info = u.loop_info(e, np.arange(9) * 0.5)
    assert info[0]["von"] == 2.0 and info[-1]["bis"] == 4.0          # 4 Takte vor dem Ende bis zum Ende
    assert [round(i["laenge"], 4) for i in info] == [0.5, 0.25, 0.125, 0.0625]   # 4 Takte: 1 je Groesse
    assert u.loop_info(Einstellungen(art="eq", loop="4"), np.arange(9) * 0.5) == []


def test_backen_eigen_mit_hall_fahne_und_kurven():
    a, b = _eintrag(1, 120.0), _eintrag(2, 120.0)
    e = Einstellungen(takte=4, art="eigen", ausstieg="phrase", effekt="hall_ende_aus", filter="tp_aus")
    g = u.backen(_spur(a), b, np.full((60 * RATE, 2), 0.2, np.float32), e, ab_s=1.0)
    assert g.info["art"] == "eigen"
    assert {"lautstaerke", "filter", "hall"} <= set(g.info["kurven"]["a"])
    assert all(len(v) == u.KURVEN_PUNKTE for v in g.info["kurven"]["a"].values())


# --- Abstimmung: Effekte hoerbar, Loops sauber, kein Buckel ------------------------------------

def _musik(sekunden: float, takt_s: float = 0.5, seed: int = 3) -> np.ndarray:
    """Synthetischer 4-Takt-Groove: Kick je Schlag, Akkord je Takt wechselnd (4er-Muster)."""
    n = int(sekunden * RATE)
    t = np.arange(n) / RATE
    x = np.zeros(n, np.float32)
    schlag = takt_s / 4
    for s0 in np.arange(0, sekunden, schlag):
        i = int(s0 * RATE)
        k = np.arange(min(int(0.08 * RATE), n - i))
        x[i:i + len(k)] += 0.6 * np.sin(2 * np.pi * 60 * k / RATE) * np.exp(-k / (0.03 * RATE))
    for takt in range(int(sekunden / takt_s)):
        f = (220, 262, 330, 294)[takt % 4]
        i0, i1 = int(takt * takt_s * RATE), int((takt + 1) * takt_s * RATE)
        x[i0:i1] += 0.15 * np.sin(2 * np.pi * f * t[i0:i1])
    return np.stack([x, x], axis=1)


def test_effekt_ist_hoerbar_auch_wenn_der_eq_a_schon_wegdreht():
    a = _musik(8.0)
    b = (np.random.default_rng(2).standard_normal((8 * RATE, 2)) * 0.05).astype(np.float32)
    takt_n = np.round(np.arange(17) * 0.5 * RATE).astype(int)
    ohne, _ = u.mischen_eigen(a, b, Einstellungen(art="eigen", eq="profi"), takt_n)
    mit, fahne = u.mischen_eigen(a, b, Einstellungen(art="eigen", eq="profi", effekt="echo75_ende_aus"), takt_n)
    letzte = slice(14 * RATE // 2, 16 * RATE // 2)                    # die letzten 2 Takte
    nass = np.sqrt(np.mean((mit[letzte] - ohne[letzte]) ** 2))
    assert nass > 0.25 * np.sqrt(np.mean(mit[letzte] ** 2))            # Echo deutlich zu hoeren
    assert np.allclose(mit[:10 * RATE // 2], ohne[:10 * RATE // 2], atol=1e-4)   # vorher: kein Effekt
    assert np.sqrt(np.mean(fahne[:RATE] ** 2)) > 0.01                   # Fahne klingt ueber B aus


def test_loop_waehlen_findet_das_4er_muster_und_meidet_gesang():
    a = _musik(8.0)                                                    # 16 Takte a 0,5 s, Muster 4 Takte
    takt_n = np.round(np.arange(17) * 0.5 * RATE).astype(int)
    s0, laenge, guete = u.loop_waehlen(a, takt_n)
    assert laenge in (4, 8) and s0 % 4 == 0 and guete > 0.9            # ganze Muster, keine halben
    meiden = np.zeros(16, bool)
    meiden[8:] = True
    s1, l1, _ = u.loop_waehlen(a, takt_n, meiden)
    assert s1 + l1 <= 8                                                # Loop ohne Gesang


def test_intro_loop_von_b_wiederholt_den_anfang_und_rechnet_zurueck():
    b = _musik(20.0)
    bbar = np.arange(0, 20.0, 0.5)
    v, raster, rueck = u._intro_loop(b, bbar, 0, 4, 2)                # 4 Takte, 2x zusaetzlich
    assert len(v) == len(b) + 2 * 4 * RATE // 2
    i = 4 * RATE // 2
    assert np.allclose(v[i + 300:2 * i], b[300:i], atol=1e-6)          # zweiter Durchgang = Anfang
    assert np.allclose(v[3 * i:3 * i + 1000], b[i:i + 1000], atol=1e-6)  # danach geht es weiter
    assert abs(rueck(np.array([6.0 + 1.0]))[0] - 3.0) < 1e-6           # nach dem Loop: Original
    assert np.all(np.diff(raster) > 0)


def test_deckel_nimmt_buckel_raus_laesst_ausblenden_in_ruhe():
    r = np.full((4 * RATE, 2), 0.3, np.float32)
    takt_n = np.round(np.arange(5) * RATE).astype(int)
    doppelt = u._deckeln(r + r, r, r, takt_n)
    assert np.sqrt(np.mean(doppelt[RATE:3 * RATE] ** 2)) < 0.3 * 10 ** (1.6 / 20)
    leise = r * 0.1
    assert np.allclose(u._deckeln(leise, r, r, takt_n), leise)


def test_backen_mit_auto_loop_behaelt_die_blendenlaenge():
    a, b = _eintrag(1, 120.0), _eintrag(2, 120.0)
    e = Einstellungen(takte=8, art="eigen", eq="profi", loop="auto")
    g = u.backen(u.Spur.roh(a, _musik(60.0, takt_s=2.0)), b, np.full((60 * RATE, 2), 0.2, np.float32), e,
                 ab_s=1.0, aus_s=40.0, ein_s=0.0)
    assert abs(g.info["blende_s"] - 16.0) < 0.1 and g.info["loop_wahl"]["schlaege"] in (4, 8, 16, 32)


def test_drop_tricks_tape_stop_backspin_riser_teaser():
    """Experimente: A endet mit dem Trick, B's Aufbau kommt in den letzten 4 Takten dazu, sein Drop danach."""
    a, b = _ab()
    schlag, haelfte = int(_TAKT_N[1] / 4), int(_TAKT_N[4])
    roh, _ = u.mischen_eigen(a, b, Einstellungen(art="eigen", lautstaerke="drop", eq="keiner"), _TAKT_N)
    assert np.allclose(roh[:haelfte], a[:haelfte], atol=1e-4)                    # erst nur A
    assert not np.allclose(roh[-3 * schlag:-schlag], a[-3 * schlag:-schlag], atol=1e-2)   # dann B darunter
    for trick in ("bremse", "spinback"):
        y, _ = u.mischen_eigen(a, b, Einstellungen(art="eigen", lautstaerke="drop", eq="keiner", trick=trick), _TAKT_N)
        ende = y[-2 * schlag:]
        assert np.isfinite(y).all() and not np.allclose(ende, a[-2 * schlag:], atol=1e-2)   # A dreht/bremst
        assert np.abs(ende[-schlag // 8:]).max() < np.abs(a).max()                          # und laeuft aus
    y, _ = u.mischen_eigen(a, b, Einstellungen(art="eigen", lautstaerke="drop", eq="keiner", trick="riser"), _TAKT_N)
    rauschen = y - roh
    assert np.std(rauschen[-schlag:]) > 4 * np.std(rauschen[:schlag])                       # wird lauter
    h = u._huellen(Einstellungen(art="eigen", lautstaerke="drop", trick="teaser"), 8, 800, 0.001)
    assert h["b_vol"][int(800 * 2.9 / 8)] > 0.99 and h["a_vol"][int(800 * 2.9 / 8)] < 0.01   # Cut auf B (vor B's Aufbau)
    assert h["b_vol"][int(800 * 2.5 / 8)] < 0.01


def test_double_drop_bass_tausch_auf_dem_drop():
    h = u._huellen(Einstellungen(art="eigen", lautstaerke="doppel", eq="bass_takt", bass_takt=4), 8, 800, 0.001)
    assert h["b_vol"][150] > 0.99 and h["a_vol"][600] > 0.99          # beide voll im Drop
    assert h["b_tief"][380] < 0.01 and h["b_tief"][420] > 0.99 and h["a_tief"][420] < 0.01   # ein Schlag


def test_gate_rueckhall_pingpong():
    a = np.full((4 * RATE, 2), 0.5, np.float32)
    y = u._gate(a, _TAKT_N)
    achtel = int(_TAKT_N[1] / 8)
    t6 = int(_TAKT_N[6])
    assert y[t6 + achtel // 2, 0] > 0.49 and y[t6 + achtel + achtel // 2, 0] < 0.01 and y[t6 - 10, 0] > 0.49
    b = np.zeros((4 * RATE, 2), np.float32)
    p = 2 * RATE
    b[p:] = 0.5
    r = u._rueckhall(b, p, RATE / 4)
    assert np.abs(r[p - RATE // 10:p]).max() > np.abs(r[:RATE // 2]).max() and not r[p:].any()   # schwillt an
    send = np.zeros((RATE, 2), np.float32)
    send[:100] = 1.0
    nass = u._nass("pingpong50", send, 1000)
    assert nass[500:600, 1].max() > 0.1 and nass[500:600, 0].max() == 0     # 1. Wiederholung rechts
    assert nass[1000:1100, 0].max() > 0.1 and nass[1000:1100, 1].max() == 0  # 2. links


def test_drop_cuts_wechseln_in_2_takt_stuecken_und_enden_auf_b():
    h = u._huellen(Einstellungen(art="eigen", trick="wechsel", gesang_takt=2), 12, 1200, 0.001)
    mitte = lambda t: int((t + 0.5) * 100)   # noqa: E731 - Mitte von Takt t
    assert [round(float(h["b_vol"][mitte(t)])) for t in range(12)] == [0, 0, 0, 0, 1, 1, 0, 0, 1, 1, 1, 1]
    assert np.allclose(h["a_vol"] + h["b_vol"], 1.0)        # immer genau ein Song


def test_regulaer_ein_raster_je_song_trotz_springender_eins():
    """Runde 17: die Eins sprang abschnittsweise um 2 Schlaege, Planung (Songmitte) und Backen (Ausstieg) lagen
    bis zu 2 Schlaege auseinander. Jetzt: Mehrheit der Downbeats, unabhaengig von bis_s."""
    db = np.arange(0.0, 200.0, 2.0)                      # 120 BPM, Eins auf 0
    falsch = (db > 60) & (db < 100)                      # dort setzt Beat This! die Eins einen halben Takt daneben
    d = np.where(falsch, db + 1.0, db)
    r = u.regulaer(list(d), 120.0, 210.0)
    assert np.allclose(r[:100], db, atol=1e-6)
    assert np.allclose(u.regulaer(list(d), 120.0, 400.0)[:len(r)], r)


def test_regulaer_folgt_langsamer_drift():
    db = np.arange(0.0, 200.0, 2.0) + np.linspace(0.0, 0.06, 100)   # 60 ms Drift ueber den Song
    r = u.regulaer(list(db), 120.0, 200.0)
    assert np.max(np.abs(r[:100] - db)) < 0.01
