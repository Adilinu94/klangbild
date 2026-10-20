"""Tests fuer BAUPLAN-UEBERGAENGE §3-§6: Drop-Ausrichtung, Passung, Tempo-Bruecken, Rezept-Fixes."""

from __future__ import annotations

import numpy as np

from klangbild import plan, profil, regie
from klangbild import uebergang as u
from klangbild.einstellungen import Einstellungen
from klangbild.profil import PHRASE, Profil

RATE = u.RATE
TAKT = 2.0   # 120 BPM


def _kicks(zeiten, dauer_s: float) -> np.ndarray:
    """Tiefe Kicks (60 Hz, 80 ms) an den Zeiten, Stereo."""
    x = np.zeros(int(dauer_s * RATE), np.float32)
    n = int(0.08 * RATE)
    k = (np.sin(2 * np.pi * 60 * np.arange(n) / RATE) * np.exp(-np.arange(n) / (0.03 * RATE))).astype(np.float32)
    for t in zeiten:
        i = int(t * RATE)
        x[i:i + n] += k[:len(x[i:i + n])]
    return np.stack([x, x], axis=1)


def test_kick_kontrolle_vergleicht_die_kick_lage_von_a_und_b():
    viertel = np.arange(0, 8 * TAKT, TAKT / 4)
    raster = np.arange(9) * TAKT
    a = _kicks(viertel, 8 * TAKT)
    assert abs(regie.kick_lage(a, RATE, raster, 2)) < 0.003
    assert regie.kicks_versetzt(a, raster, 2, _kicks(viertel + 0.005, 8 * TAKT), raster, 2, RATE) is None
    assert regie.kicks_versetzt(a, raster, 2, _kicks(viertel + 0.025, 8 * TAKT), raster, 2, RATE) is not None
    # B's Raster hat denselben Fehler wie seine Kicks: passt; ein Takt daneben liegt wieder im Raster (faengt _drop_schlag)
    assert regie.kicks_versetzt(a, raster, 2, _kicks(viertel + 0.025, 8 * TAKT), raster + 0.025, 2, RATE) is None
    assert regie.kicks_versetzt(a, raster, 2, a, raster, 3, RATE) is None


def _drop_profil(n=16) -> Profil:
    t = np.arange(n) * TAKT
    g = np.full(n, -10.0)
    return Profil(t, np.stack([g, g, g], axis=1), g, None, np.ones(n, bool), n * TAKT)


def test_drop_schlag_findet_um_zwei_schlaege_verschobenen_drop():
    p = _drop_profil()
    drop_s = 8 * TAKT + 2 * TAKT / 4                       # zwei Schlaege nach Takt 8
    t = np.arange(16 * int(TAKT * RATE)) / RATE
    bass = (0.3 * np.sin(2 * np.pi * 55 * t) * (t >= drop_s)).astype(np.float32)[:, None]
    audio = _kicks(np.arange(drop_s, 16 * TAKT, TAKT / 4), 16 * TAKT) + bass
    takt, versatz, sicher = regie._drop_schlag(p, audio, RATE, 8)
    assert takt == 8 and versatz == 4 and sicher > regie.DROP_SICHER_DB
    assert not regie._drop_ok(p, 8, audio, RATE)
    genau = _kicks(np.arange(8 * TAKT, 16 * TAKT, TAKT / 4), 16 * TAKT) +         (0.3 * np.sin(2 * np.pi * 55 * t) * (t >= 8 * TAKT)).astype(np.float32)[:, None]
    assert regie._drop_schlag(p, genau, RATE, 8)[1] == 0 and regie._drop_ok(p, 8, genau, RATE)


def _profil(abschnitte, pegel_plus=0.0, beatlos_intro=False):
    pegel = {"intro": -22.0, "aufbau": -18.0, "drop": -9.0, "haupt": -10.0, "break": -16.0, "outro": -22.0}
    drums = {"intro": -40.0 if beatlos_intro else -14.0, "aufbau": -16.0, "drop": -11.0, "haupt": -12.0,
             "break": -40.0, "outro": -24.0}
    zeilen = [(et, ph) for et, n in abschnitte for ph in range(n)]
    n = len(zeilen) * PHRASE
    gesamt = np.repeat([pegel[et] for et, _ in zeilen], PHRASE) + pegel_plus
    st = {"vocals": np.full(n, -60.0), "drums": np.repeat([drums[et] for et, _ in zeilen], PHRASE),
          "bass": gesamt - 4.0, "other": gesamt - 6.0}
    return Profil(np.arange(n) * TAKT, np.stack([gesamt - 3, gesamt - 4, gesamt - 8], axis=1), gesamt, st,
                  np.ones(n, bool), n * TAKT)


SONG = [("intro", 2), ("drop", 4), ("break", 2), ("drop", 4), ("outro", 2)]


def test_passung_eins_bei_gleichen_null_ab_vier_db():
    p, q = _profil(SONG), _profil(SONG, pegel_plus=4.0)
    assert regie._passung(p, p, 16, 16) == 1.0
    assert regie._passung(p, q, 16, 16) == 0.0


def test_double_drop_nur_bei_passender_energie():
    e = Einstellungen(modus="ausgewogen", experimente="wild")
    pa = _profil(SONG)
    passt = regie._double_drops(pa, _profil(SONG), e, 0)
    laut = regie._double_drops(pa, _profil(SONG, pegel_plus=3.0), e, 0)   # Passung 0,25
    assert passt and not laut


def test_bruecke_beatlos_bei_tempo_sprung():
    pa, pb = _profil(SONG), _profil(SONG, beatlos_intro=True)
    e = Einstellungen(modus="ausgewogen", max_bpm=0.0)
    p0 = regie.planen(None, pa, None, pb, e, 0.0, sync=False, harmonisch=True)[0]
    assert p0.rezept == "bruecke_beatlos" and p0.einst.art == "echo"
    j = pb.takt_bei(p0.ein_s)
    assert regie._beatlos(pb)[j:j + 4].all()


def test_vorlauf_regie_und_backen():
    pa, pb = _profil(SONG), _profil(SONG)
    p0 = regie.planen(None, pa, None, pb, Einstellungen(modus="ausgewogen"), 0.0, sync=False, harmonisch=True)[0]
    assert p0.einst.tempo_modus == "vorlauf" and pa.takt_bei(p0.aus_s) >= regie.VORLAUF_TAKTE

    def eintrag(tid, bpm):
        return u.Eintrag(id=tid, pfad=f"/x/{tid}.flac", bpm=bpm, camelot="8A",
                         downbeats=list(np.arange(0.0, 120.0, 240.0 / bpm)))
    a, b = eintrag(1, 120.0), eintrag(2, 126.0)                     # 5 %: ueber max_bpm, unter VORLAUF_MAX
    t = np.arange(120 * RATE) / RATE
    ton = np.stack([np.sin(2 * np.pi * 440 * t)] * 2, axis=1).astype(np.float32) * 0.2
    e = Einstellungen(modus="manuell", art="eq", takte=8, ausstieg="vor_ende", vor_ende_takte=20,
                      tempo_modus="vorlauf", max_bpm=2.0)
    g = u.backen(u.Spur.roh(a, ton), b, ton.copy(), e, ab_s=1.0)
    assert g.info["sync"] and g.info["vorlauf_takte"] == 16
    r = np.asarray(g.info["raster_s"])
    v = g.info["vorlauf_takte"] and 0   # Raster beginnt an der Blende (nach dem Vorlauf)
    assert abs(r[v + 1] - r[v] - 240.0 / 126.0) < 0.005 * 240.0 / 126.0   # am Ende des Vorlaufs: B's Takt
    vor = g.spur.puffer[:int(g.info["vorlauf_s"] * RATE)]
    spitze = np.argmax(np.abs(np.fft.rfft(vor[-RATE:, 0]))) * RATE / RATE
    assert abs(spitze - 440.0) < 3.0                                       # Keylock: Tonhoehe bleibt


def test_tempo_mal_hin_und_zurueck():
    p = _profil(SONG)
    d = profil.tempo_mal(p, 2.0)
    assert d.n == 2 * p.n and np.allclose(np.diff(d.takte), TAKT / 2)
    assert np.allclose(profil.tempo_mal(d, 0.5).takte, p.takte) and np.allclose(profil.tempo_mal(d, 0.5).gesamt, p.gesamt)


def test_rangliste_kennt_halbtempo():
    a = plan.Track(id=1, pfad="a", bpm=170.0, camelot="8A", energie_db=-10.0)
    halb = plan.Track(id=2, pfad="b", bpm=85.5, camelot="8A", energie_db=-10.0)
    fremd = plan.Track(id=3, pfad="c", bpm=128.0, camelot="8A", energie_db=-10.0)
    assert [k.id for k in plan.rangliste(a, [fremd, halb], 2.0)] == [2]


def test_gesang_zuerst_b_hihats_vor_der_uebergabe():
    n, takte, g = RATE * 16, 16, 8
    rng = np.random.default_rng(0)
    still = {k: np.zeros((n, 2), np.float32) for k in ("drums", "bass", "other", "vocals")}
    b = dict(still, drums=(rng.standard_normal((n, 2)) * 0.1).astype(np.float32))
    y = u.mischen_stems("gesang_zuerst", still, b, takte, g)
    pegel = lambda x: 10 * np.log10(np.mean(np.square(x, dtype=np.float64)) + 1e-12)   # noqa: E731
    vorher = y[int(n * (g / 2 + 1) / takte):int(n * g / takte)]
    assert -15.0 < pegel(vorher) - pegel(b["drums"]) < -9.0
    assert pegel(y[:int(n * (g / 2 - 0.5) / takte)]) < -60


def test_vorlauf_prueft_das_tempo_an_ausstieg_und_einsatz():
    # A wird nach dem ersten Drittel langsamer (110 BPM), B 128 BPM: am Songanfang passt der Vorlauf (6 %), am
    # Ausstieg nicht mehr (16 %) - dann kein Sync-Rezept, das backen ohne Angleich rendern muesste
    from dataclasses import replace

    pa, pb = _profil(SONG), _profil(SONG)
    d = np.diff(pa.takte)
    d[len(d) // 3:] *= 120 / 110
    pa, pb = replace(pa, takte=np.concatenate([[0.0], np.cumsum(d)])), replace(pb, takte=pb.takte * 120 / 128)
    ps = regie.planen(None, pa, None, pb, Einstellungen(modus="ausgewogen"), 0.0, sync=False, harmonisch=True)
    assert ps and all(p.einst.art not in u.SYNC_ARTEN for p in ps)
