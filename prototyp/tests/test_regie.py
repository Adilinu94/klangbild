"""Tests fuer profil.py und regie.py (Auto-DJ V2) mit synthetischen Takt-Profilen."""

from __future__ import annotations

import numpy as np
import pytest

from klangbild import profil, regie
from klangbild import uebergang as u
from klangbild.einstellungen import Einstellungen
from klangbild.profil import PHRASE, Profil

TAKT = 2.0   # 120 BPM


def _profil(abschnitte: list[tuple[str, int]], gesang: set[int] = frozenset(), stems: bool = True) -> Profil:
    """Profil aus [(etikett, phrasen)], Gesang in den angegebenen Phrasen."""
    pegel = {"intro": -22.0, "aufbau": -18.0, "drop": -9.0, "haupt": -10.0, "break": -16.0, "outro": -22.0}
    drums = {"intro": -14.0, "aufbau": -16.0, "drop": -11.0, "haupt": -12.0, "break": -40.0, "outro": -24.0}
    zeilen = [(et, ph) for et, n in abschnitte for ph in range(n)]
    n = len(zeilen) * PHRASE
    gesamt = np.repeat([pegel[et] for et, _ in zeilen], PHRASE)
    st = None
    if stems:
        voc = np.full(n, -60.0)
        for p in gesang:
            voc[p * PHRASE:(p + 1) * PHRASE] = gesamt[p * PHRASE] - 3.0
        st = {"vocals": voc, "drums": np.repeat([drums[et] for et, _ in zeilen], PHRASE),
              "bass": gesamt - 4.0, "other": gesamt - 6.0}
    baender = np.stack([gesamt - 3, gesamt - 4, gesamt - 8], axis=1)
    return Profil(np.arange(n) * TAKT, baender, gesamt, st, np.ones(n, bool), n * TAKT)


def test_etiketten_aus_energie_und_drums():
    p = _profil([("intro", 2), ("drop", 4), ("break", 2), ("drop", 4), ("outro", 2)])
    assert p.etiketten() == ["intro"] * 2 + ["drop"] + ["haupt"] * 3 + ["break"] * 2 + ["drop"] + ["haupt"] * 3 \
        + ["outro"] * 2


def test_profil_aus_audio_speichern_laden(tmp_path):
    rng = np.random.default_rng(0)
    t = np.arange(60 * u.RATE) / u.RATE
    lauter = (t > 30)[:, None]
    audio = (rng.standard_normal((len(t), 2)) * np.where(lauter, 0.3, 0.03)).astype(np.float32)
    e = u.Eintrag(id=5, pfad="/x/5.flac", bpm=120.0, camelot="8A", downbeats=list(np.arange(0, 60, 2.0)))
    p = profil.berechnen(e, audio)
    assert abs(p.n - 30) <= 1 and p.gesamt[20] - p.gesamt[5] > 15 and p.raster_ok.all()
    profil.speichern(5, p, tmp_path)
    q = profil.gespeichert(5, tmp_path)
    assert np.allclose(q.gesamt, p.gesamt, atol=0.01) and q.stems is None
    assert profil.passt(q, e)   # gerundet gespeichert: sonst bei jedem Laden neu gerechnet


def _planen(pa, pb, **e):
    einst = Einstellungen(**{"modus": "ausgewogen", "spielanteil": "lang", **e})
    return regie.planen(None, pa, None, pb, einst, ab_s=0.0, sync=True, harmonisch=True, stems_da=True)


SONG = [("intro", 2), ("drop", 4), ("break", 2), ("drop", 4), ("outro", 2)]   # 14 Phrasen


def test_lang_spielt_bis_ins_outro_und_b_von_vorn():
    plan = _planen(_profil(SONG), _profil(SONG))[0]
    assert plan.aus_s >= 11 * PHRASE * TAKT - 1e-6      # Ausstieg nach dem letzten Drop-Block ...
    assert plan.aus_s / TAKT + plan.takte >= 13 * PHRASE   # ... und A spielt bis ins letzte Outro
    assert plan.ein_s == 0.0                            # B mit dem Intro
    assert plan.einst.art in ("drums_zuerst", "eigen") and plan.grund


def test_schnell_wechselt_nach_dem_drop_der_zweiten_haelfte():
    plan = _planen(_profil(SONG), _profil(SONG), spielanteil="schnell")[0]
    assert 9 * PHRASE * TAKT <= plan.aus_s <= 11 * PHRASE * TAKT    # kurz nach dem 2. Drop
    assert plan.aus_s < _planen(_profil(SONG), _profil(SONG))[0].aus_s


def test_kein_gesang_gegen_gesang():
    # A singt im Outro, B im Intro: die Regie muss das Ueberlappen vermeiden
    pa = _profil(SONG, gesang={13})
    pb = _profil([("intro", 1), ("aufbau", 1), ("drop", 4), ("haupt", 4)], gesang={0})
    plan = _planen(pa, pb)[0]
    i, j, n = int(plan.aus_s / TAKT), int(plan.ein_s / TAKT), plan.takte
    ga, gb = pa.gesang(), pb.gesang()
    beide = sum(ga[i + k] * gb[j + k] for k in range(n) if i + k < pa.n and j + k < pb.n)
    assert beide == 0


@pytest.mark.parametrize("modus,laengen", [("kurz", (16,)), ("ausgewogen", (16, 24, 32)), ("lang", (24, 32))])
def test_stil_bestimmt_die_laenge(modus, laengen):
    assert regie.laengen(modus, TAKT) == laengen          # 120 BPM: 1 Takt = 2 s
    plan = _planen(_profil(SONG), _profil(SONG), modus=modus)[0]
    assert plan.takte in laengen


def test_blendenlaenge_folgt_dem_tempo():
    """Gleiche Zeit statt gleicher Takte: DnB (174 BPM) bekommt mehr Takte als Hip-Hop (90 BPM)."""
    dnb, hiphop = 240 / 174, 240 / 90
    assert regie.laengen("kurz", dnb) == (16,) and regie.laengen("kurz", hiphop) == (8,)
    assert all(28.0 <= L * dnb <= 64.0 for L in regie.laengen("ausgewogen", dnb))
    assert regie.laengen("kurz", TAKT, sofort=True) == (8,)   # WEITER nicht mehr 4 Takte (8 s)


def test_breakdown_blendet_a_ueber_die_ganze_blende_aus():
    """Uebergangstest: "breakdown" nahm A im ersten Viertel weg -> 10 von 10 Mal "zu abrupt"."""
    pa = _profil([("intro", 2), ("drop", 4), ("break", 2), ("outro", 1)])
    lage = regie._Lage(6 * PHRASE, 0, 16, 0.0, [])
    name, felder, _ = regie._rezept(lage, pa, _profil(SONG, gesang=set()), Einstellungen(modus="ausgewogen"),
                                    True, True, False, None)
    assert name == "profi_eq"                       # 14 Runden: breakdown 1,93 -> nur noch Notnagel
    h = u._huellen(Einstellungen(**{k: v for k, v in felder.items() if k in Einstellungen.__dataclass_fields__}),
                   16, 800, 0.01)
    assert h["a_vol"][400] > 0.5                    # A ist in der Mitte der Blende noch deutlich da


def test_abrupt_nur_in_einen_drop():
    """Kurz: Echo-in-den-Drop und Loop-Rolle nur, wenn B nach der Blende mit dem Drop uebernimmt."""
    pa = _profil(SONG)
    mit_drop = _profil([("intro", 2), ("drop", 4), ("haupt", 4)])     # Drop ab Takt 16
    ohne_drop = _profil([("intro", 4), ("haupt", 6)])
    e = Einstellungen(modus="kurz", spielanteil="schnell")
    lage = regie._Lage(9 * PHRASE, 0, 16, 0.0, [])
    rezepte = lambda pb: {regie._rezept(lage, pa, pb, e, True, True, False, v)[0]   # noqa: E731
                          for v in (None, "echo_drop", "rolle", "outro_loop")}
    assert {"echo_drop", "rolle"} & rezepte(mit_drop)
    assert not {"echo_drop", "rolle"} & rezepte(ohne_drop)


def test_ohne_tempo_echo_und_abwechslung():
    pa, pb = _profil(SONG), _profil(SONG)
    einst = Einstellungen(modus="ausgewogen", max_bpm=0.0)   # kein Tempo-Angleich, auch kein Vorlauf
    ohne = regie.planen(None, pa, None, pb, einst, 0.0, sync=False, harmonisch=True)[0]
    assert ohne.einst.art == "echo"
    erst = regie.planen(None, pa, None, pb, einst, 0.0, sync=True, harmonisch=True, stems_da=True)[0]
    dann = regie.planen(None, pa, None, pb, einst, 0.0, sync=True, harmonisch=True, stems_da=True,
                        vorher=erst.rezept)[0]
    assert dann.rezept != erst.rezept


def test_weiter_sofort_auf_der_naechsten_taktgruppe():
    pa, pb = _profil(SONG), _profil(SONG)
    einst = Einstellungen(modus="kurz")
    plan = regie.planen(None, pa, None, pb, einst, ab_s=21.0, sync=True, harmonisch=True, sofort=True)[0]
    # Takt 12 (naechste 4er-Gruppe nach Takt 10,5) oder hoechstens 8 Takte spaeter, wenn die Stelle klar
    # besser ist (Runde 3: WEITER soll in B's Drop enden, A nicht mitten im Wort abschneiden)
    assert plan.aus_s in (24.0, 32.0, 40.0) and plan.takte == 8
    # WEITER haelt A im Loop statt es abzuschneiden - oder A geht ins Echo und B's Drop schlaegt ein
    assert plan.einst.loop != "keiner" or plan.rezept == "echo_drop", plan.rezept


def test_lang_verlaengert_kurzes_outro_mit_loop():
    pa = _profil([("intro", 2), ("drop", 6), ("outro", 1)])   # A endet abrupt
    plaene = regie.planen(None, pa, None, _profil(SONG), Einstellungen(modus="lang"), 0.0,
                          sync=True, harmonisch=True)
    endet_in_blende = [p for p in plaene if p.aus_s / TAKT + p.takte > pa.n]
    assert all(p.einst.loop != "keiner" for p in endet_in_blende)


def test_profi_eq_reihenfolge_hoehen_mitten_bass():
    e = Einstellungen(art="eigen", eq="profi", bass_takt=12)
    h = u._huellen(e, 16, 1600, 0.01)
    erst = lambda k: int(np.argmax(h[k] > 0.5))   # noqa: E731
    assert erst("b_hoch") < erst("b_mitte") < erst("b_tief")
    assert abs(erst("b_tief") / 1600 - 12 / 16) < 0.02                 # Bass-Tausch auf Takt 12
    assert np.allclose(h["a_tief"] ** 2 + h["b_tief"] ** 2, 1.0, atol=1e-5)   # nie zwei Baesse, nie keiner
    beide = np.sum((h["a_tief"] > 0.1) & (h["b_tief"] > 0.1))
    assert beide <= 1600 / 16 / 4                                       # Tausch in hoechstens einem Schlag
    assert h["b_vol"][100] == pytest.approx(1.0) and h["a_vol"][1400] == pytest.approx(1.0)


def test_pruefen_findet_buckel():
    pa, pb = _profil(SONG), _profil(SONG)
    rate = 1000
    laut = np.full((8 * int(TAKT * rate), 2), 1.0, np.float32)            # 0 dB statt ~ -22 dB
    assert "zu laut" in regie.pruefen(laut, rate, 8, pa, pb, 12 * PHRASE * TAKT, 0.0, 0.0, 0.0, "profi_eq")
    leise = np.full_like(laut, 10 ** (-22 / 20))
    assert regie.pruefen(leise, rate, 8, pa, pb, 12 * PHRASE * TAKT, 0.0, 0.0, 0.0, "profi_eq") is None


def test_lang_loopt_b_intro_damit_kein_gesang_gegeneinander():
    pa = _profil(SONG, gesang={11, 12, 13})                    # A singt bis zum Ende
    pb = _profil([("intro", 2), ("drop", 4), ("haupt", 4)], gesang={1, 2, 3})   # B singt ab Takt 8
    e = Einstellungen(modus="lang")
    natuerlich, _, _ = regie._bewerten(pa, pb, 96, 0, 16, e)
    geloopt, teile, _ = regie._bewerten(pa, pb, 96, 0, 16, e, 8, 1)   # B's 8 Intro-Takte zweimal
    assert geloopt > natuerlich + 3 and "kein Gesang gegeneinander" in teile
    assert (8, 1) in regie._intro_loops(pb, 0, 16)
    lage = regie._Lage(96, 0, 16, geloopt, teile, 8, 1)
    name, felder, _ = regie._rezept(lage, pa, pb, e, True, True, False, None)
    assert name == "intro_loop_b" and felder["loop_ein"] == 8 and felder["loop_ein_mal"] == 1


def test_tonvorrat_im_fenster_entscheidet_ueber_harmonie():
    pa, pb = _profil(SONG), _profil(SONG)
    dur = np.array([1, 0, .5, 0, 1, .6, 0, 1, 0, .5, 0, .3])      # C-Dur-artig
    fremd = np.roll(dur, 6)                                        # Tritonus weg
    pa.chroma = np.tile(dur, (pa.n, 1))
    pb.chroma = np.tile(fremd, (pb.n, 1))
    plan = _planen(pa, pb, modus="ausgewogen")[0]                  # Camelot sagt "passt"
    assert plan.rezept in ("filter_blend", "loop_filter") and plan.einst.filter == "hp_aus"
    pb.chroma = np.tile(dur, (pb.n, 1))
    assert _planen(pa, pb, modus="ausgewogen")[0].einst.filter != "hp_aus"


def test_gelerntes_meidet_oft_abgebrochene_rezepte():
    pa, pb = _profil(SONG), _profil(SONG)
    einst = Einstellungen(modus="ausgewogen")
    erst = regie.planen(None, pa, None, pb, einst, 0.0, sync=True, harmonisch=True, stems_da=True)[0]
    dann = regie.planen(None, pa, None, pb, einst, 0.0, sync=True, harmonisch=True, stems_da=True,
                        vorlieben={erst.rezept: -3.0})[0]
    assert dann.rezept != erst.rezept


def test_effekt_rezepte_halten_a_bis_zum_schnitt():
    # Abstimmung: wo ein Effekt auf A liegt, ist A's Fader bis kurz vor dem Ende oben
    for modus, spiel in (("kurz", "schnell"), ("ausgewogen", "schnell"), ("lang", "lang")):
        for plan in _planen(_profil(SONG), _profil(SONG), modus=modus, spielanteil=spiel):
            e = plan.einst
            if e.art == "eigen" and e.effekt != "keiner" and e.effekt.endswith("ende_aus"):
                h = u._huellen(e, e.takte, 800, 0.01)
                assert h["a_vol"][int(800 * (1 - 1.5 / e.takte))] > 0.9, plan.rezept


def test_kein_effekt_auf_ein_ausklingendes_outro():
    pa = _profil(SONG)
    pa.gesamt[-16:] = -45.0                                   # A ist am Ende fast still
    for modus, spiel in (("kurz", "schnell"), ("ausgewogen", "schnell"), ("lang", "lang")):
        for plan in _planen(pa, _profil(SONG), modus=modus, spielanteil=spiel):
            ende = plan.aus_s / TAKT + plan.takte
            if ende > pa.n - 16:   # die Blende reicht in den leisen Teil (endet sie davor, klingt A noch)
                assert plan.einst.effekt == "keiner", plan.rezept


@pytest.mark.parametrize("modus,spielanteil", [("kurz", "lang"), ("ausgewogen", "lang"), ("ausgewogen", "schnell"),
                                              ("lang", "lang"), ("lang", "schnell")])
def test_loops_gehoeren_in_jeden_stil(modus, spielanteil):
    """Auf einem normalen Paar (A mit Drums im Fenster) kommt in jedem Stil ein Loop vor:
    A loopt eine saubere Stelle, oder B's Intro laeuft im Loop - nicht erst bei Sonderfaellen."""
    p = _profil(SONG)
    einst = Einstellungen(modus=modus, spielanteil=spielanteil)
    plaene = [x for v in (None, "profi_eq", "outro_loop", "breakdown")
              for x in regie.planen(None, p, None, p, einst, 0.0, True, True, vorher=v)[:3]]
    assert any(x.einst.loop != "keiner" or x.einst.loop_ein for x in plaene), [x.rezept for x in plaene]


def test_endet_a_in_der_blende_gibt_es_immer_einen_loop():
    kurz_a = [("intro", 2), ("drop", 4), ("outro", 1)]   # 7 Phrasen, ab Phrase 6 nur noch 1 (8 Takte)
    pa, pb = _profil(kurz_a, stems=False), _profil(SONG, stems=False)
    for modus in ("kurz", "ausgewogen", "lang"):
        for p in regie.planen(None, pa, None, pb, Einstellungen(modus=modus), 6 * PHRASE * TAKT, True, True):
            if pa.n - pa.takt_bei(p.aus_s) < p.takte:
                assert p.einst.loop != "keiner", (modus, p.rezept)


def test_profil_ableitungen_werden_nur_einmal_gerechnet():
    p = _profil(SONG)
    assert p.etiketten() is p.etiketten() and p.drums() is p.drums() and p.gesang() is p.gesang()


def test_a_endet_in_der_blende_ohne_drums_loopt_trotzdem():
    """Ohne Drums im A-Rest ("Break") darf trotzdem kein Rezept ohne Loop gewaehlt werden: A ist
    in der Blende zu Ende, dahinter waere Stille (gemessen: -70 dB-Loch bei drums_zuerst)."""
    a = _profil([("intro", 2), ("drop", 4), ("break", 1)], stems=True)   # Ende = Break ohne Drums
    b = _profil(SONG)
    for modus in ("kurz", "ausgewogen", "lang"):
        plaene = regie.planen(None, a, None, b, Einstellungen(modus=modus), 5 * PHRASE * TAKT, True, True,
                              stems_da=True)
        for p in plaene:
            if a.n - a.takt_bei(p.aus_s) < p.takte:
                assert p.einst.loop != "keiner" or p.einst.loop_ein, (modus, p.rezept)
                assert p.einst.art == "eigen", (modus, p.rezept)


def test_nach_einem_loop_kommt_ein_anderes_rezept():
    p = _profil(SONG)
    einst = Einstellungen(modus="ausgewogen", spielanteil="lang")
    erst = regie.planen(None, p, None, p, einst, 0.0, True, True)[0]
    assert erst.einst.loop != "keiner" or erst.einst.loop_ein
    dann = regie.planen(None, p, None, p, einst, 0.0, True, True, vorher=erst.rezept)[0]
    assert dann.rezept not in regie.LOOP_REZEPTE, dann.rezept


def test_weiter_ab_takt_beginnt_am_naechsten_takt():
    p = _profil(SONG)
    einst = Einstellungen(modus="kurz", weiter_ab="takt")
    plan = regie.planen(None, p, None, p, einst, 10 * TAKT + 0.1, True, True, sofort=True)[0]
    assert abs(plan.aus_s - 11 * TAKT) < 1e-6
    einst = Einstellungen(modus="kurz", weiter_ab="phrase")
    plan = regie.planen(None, p, None, p, einst, 10 * TAKT + 0.1, True, True, sofort=True)[0]
    assert plan.aus_s % (4 * TAKT) < 1e-6   # auf der naechsten 4-Takt-Gruppe


def _gesang_im_fenster(p: Profil, von: int, n: int) -> np.ndarray:
    return regie._fenster(p.gesang(), von, n) > 0


def test_a_singt_ueber_b_weiter_statt_auszublenden():
    """Stems: A's Musik geht, A's letzte Zeile laeuft ueber B's Instrumental - B singt erst danach."""
    pa = _profil(SONG, gesang={11})                       # A singt in Phrase 11 (Takt 88-95)
    pb = _profil(SONG)                                     # B ohne Gesang am Anfang
    plan = _planen(pa, pb)[0]
    assert plan.rezept == "acapella" and plan.einst.art == "acapella", plan.grund
    i, j, g = int(plan.aus_s / TAKT), int(plan.ein_s / TAKT), plan.einst.gesang_takt
    assert 0 < g <= plan.takte                            # g = Fensterende: A's Zeile endet mit der Blende
    a = _gesang_im_fenster(pa, i, plan.takte)
    assert a[:g].any() and not a[g:].any()                 # A's Zeile endet am Uebergabe-Takt
    assert not _gesang_im_fenster(pb, j, g + 1).any()      # solange A singt, schweigt B
    ohne = regie.planen(None, pa, None, pb, Einstellungen(modus="ausgewogen"), 0.0, True, True, stems_da=False)[0]
    assert ohne.rezept != "acapella"                       # ohne Stem-Vorrat keine Gesangs-Uebergabe


def test_b_singt_zuerst_ueber_a_instrumental():
    pa = _profil(SONG)                                     # A instrumental
    pb = _profil([("intro", 2), ("drop", 4), ("haupt", 4)], gesang={0, 1})   # B singt sofort
    plan = _planen(pa, pb)[0]
    assert plan.rezept == "gesang_zuerst", plan.grund
    i, j, g = int(plan.aus_s / TAKT), int(plan.ein_s / TAKT), plan.einst.gesang_takt
    assert not _gesang_im_fenster(pa, i, plan.takte).any()
    assert _gesang_im_fenster(pb, j, g).sum() >= 4        # B singt mindestens 4 Takte vor seiner Musik


def test_gesangs_uebergabe_nie_gegen_fremden_gesang():
    pa = _profil(SONG, gesang={11, 12, 13})                 # A singt ab Takt 88 bis zum Ende
    pb = _profil(SONG, gesang={0, 1, 2})                    # B singt ab Takt 0
    assert regie._gesang_uebergabe(pa, pb, 88, regie._b_index(0, 16)) is None   # beide singen im Fenster
    assert regie._gesang_uebergabe(pa, pb, 72, regie._b_index(0, 16))[0] == "gesang_zuerst"   # A noch still
    for plan in _planen(pa, pb):                            # was die Regie waehlt, prallt nie aufeinander
        if plan.rezept in ("acapella", "gesang_zuerst"):
            i, j = int(plan.aus_s / TAKT), int(plan.ein_s / TAKT)
            assert not (_gesang_im_fenster(pa, i, plan.takte) & _gesang_im_fenster(pb, j, plan.takte)).any()


def test_b_loopt_sein_intro_damit_der_drop_nach_der_blende_kommt():
    pb = _profil([("intro", 1), ("drop", 4), ("haupt", 4)])   # Drop schon ab Takt 8
    assert (4, 1) in regie._intro_loops(pb, 0, 16)
    lage = regie._Lage(96, 0, 16, 0.0, [], 8, 1)
    name, felder, _ = regie._rezept(lage, _profil(SONG), pb, Einstellungen(modus="lang"), True, True, False, None)
    assert name == "intro_loop_b" and felder["filter"] == "tp_ein"   # langer Loop: B oeffnet sich ...
    assert felder["eq"] == "bass_mitte"   # ... nie mit dem EQ-Swap (B haette nur Hoehen, der Tiefpass nimmt sie weg)
    # Runde 5: A- und B-Loop zugleich "zu viel auf einmal" - die Alternative loopt A nicht
    _, felder, _ = regie._rezept(lage, _profil(SONG), pb, Einstellungen(modus="lang"), True, True, False,
                                 "intro_loop_b")
    assert felder["loop"] == "keiner"


def test_weiter_schneidet_a_nicht_mitten_im_wort():
    pa = _profil(SONG, gesang={1})                      # A singt Takt 8-15
    plan = regie.planen(None, pa, None, _profil(SONG), Einstellungen(modus="kurz"), ab_s=4 * TAKT + 0.1,
                        sync=True, harmonisch=True, sofort=True)[0]
    ende = int(plan.aus_s / TAKT) + plan.takte
    assert not (pa.gesang()[ende - 1] and pa.gesang()[ende])


def test_lange_gesangsuebergabe_ueber_eine_minute():
    """B ohne Gesang: A's Gesang darf weit ueber die Stil-Laenge hinaus ueber B's Musik laufen."""
    pa = _profil([("intro", 2), ("drop", 4), ("haupt", 4), ("outro", 2)], gesang={6, 7, 8})   # Takt 48-71
    pb = _profil([("intro", 2), ("drop", 4), ("haupt", 4)])
    plaene = regie.planen(None, pa, None, pb, Einstellungen(modus="kurz"), 0.0, True, True, stems_da=True)
    lang = [p for p in plaene if p.rezept == "acapella" and p.takte * TAKT > 60]
    assert lang, [(p.rezept, p.takte) for p in plaene]
    ohne_harmonie = regie.planen(None, pa, None, pb, Einstellungen(modus="kurz"), 0.0, True, False, stems_da=True)
    pa.chroma = np.tile(np.array([1, 0, .5, 0, 1, .6, 0, 1, 0, .5, 0, .3]), (pa.n, 1))
    pb.chroma = np.roll(pa.chroma, 6, axis=1)          # Tonvorrat beisst sich
    beissend = regie.planen(None, pa, None, pb, Einstellungen(modus="kurz"), 0.0, True, True, stems_da=True)
    assert all(p.takte <= 16 for p in beissend), [(p.rezept, p.takte) for p in beissend]


def test_a_singt_bis_zum_songende_ueber_b_weiter():
    """Runde 4 (TUSA): A singt bis zum letzten Takt - das Songende beendet die Zeile."""
    pa = _profil([("intro", 2), ("drop", 4), ("haupt", 4)], gesang={4, 5, 6, 7, 8, 9})   # bis Takt 79 = Ende
    pb = _profil(SONG)
    assert regie._gesang_uebergabe(pa, pb, 64, regie._b_index(0, 16))[0] == "acapella"
    # singt A ueber das Fenster hinaus, endet seine Stimme an der letzten Phrasengrenze (Fade + Echo)
    art, g, _ = regie._gesang_uebergabe(pa, pb, 56, regie._b_index(0, 16))
    assert art == "acapella" and (56 + g) % PHRASE == 0


def test_weiter_mit_stems_laesst_a_weitersingen():
    pa = _profil(SONG, gesang={8, 9, 10})                 # A singt Takt 64-87
    plan = regie.planen(None, pa, None, _profil(SONG), Einstellungen(modus="ausgewogen"), ab_s=70 * TAKT,
                        sync=True, harmonisch=True, sofort=True, stems_da=True)[0]
    assert plan.rezept == "acapella" and plan.takte <= regie.WEITER_GESANG_MAX, (plan.rezept, plan.grund)


def test_frueher_ausstieg_nur_fuer_gesangsuebergabe():
    pa = _profil(SONG, gesang={6})                        # A singt nur in Phrase 6; B singt ueberall
    pb = _profil(SONG, gesang=set(range(14)))
    for lage in regie._rangliste(pa, pb, Einstellungen(modus="lang"), 0, False, True):
        assert regie.FRUEH_GESANG not in lage.teile or set(lage.teile) & set(regie.GESANG_TEILE)


def test_experimente_drop_tricks_nur_mit_drop_danach_und_nicht_klassisch():
    pa = _profil(SONG)
    mit_drop = _profil([("intro", 2), ("drop", 4), ("haupt", 4)])     # Drop ab Takt 16
    lage = regie._Lage(9 * PHRASE, 0, 16, 0.0, [])
    wahl = lambda pb, stufe: regie._rezept(lage, pa, pb, Einstellungen(modus="ausgewogen", experimente=stufe),  # noqa: E731
                                           True, True, False, None)
    name, felder, _ = wahl(mit_drop, "wild")
    assert name in regie.DROP_TRICKS and felder["lautstaerke"] == "drop" and felder["trick"] != "keiner"
    assert wahl(mit_drop, "klassisch")[0] not in regie.DROP_TRICKS
    assert wahl(_profil([("intro", 4), ("haupt", 6)]), "wild")[0] not in regie.DROP_TRICKS
    # Runde 11: ein "Drop" ohne Sprung in Pegel/Bass/Drums (Drum-Aufbau, Bass kommt spaeter) ist kein Ziel
    flach = _profil([("intro", 2), ("drop", 4), ("haupt", 4)])
    for x in [flach.gesamt] + list(flach.stems.values()):
        x[12:20] = x[20]
    assert regie._einsatz(flach, 16) < regie.DROP_EINSATZ <= regie._einsatz(mit_drop, 16)
    assert wahl(flach, "wild")[0] not in regie.DROP_TRICKS


def test_drop_cuts_nur_bei_gleich_starken_drops():
    """Runde 12: Drop-Cuts zwischen unterschiedlich starken Drops 3x Note 2."""
    p = _profil([("intro", 2), ("drop", 4), ("haupt", 4)])
    laut = _profil([("intro", 2), ("drop", 4), ("haupt", 4)])
    laut.gesamt[16:24] += 3.0
    assert regie._drop_gleich(p, p, 16, 16) and not regie._drop_gleich(p, laut, 16, 16)


def test_double_drop_legt_die_drops_auf_denselben_takt():
    pa = _profil(SONG)                                          # A's zweiter Drop ab Takt 64
    pb = _profil([("intro", 2), ("drop", 4), ("outro", 2)])     # B's Drop ab Takt 16
    plan = _planen(pa, pb, experimente="wild")[0]
    assert plan.rezept == "double_drop", plan.rezept
    k = plan.einst.gesang_takt                                 # gemeinsamer Drop (Stems)
    assert (plan.aus_s / TAKT + k, plan.ein_s / TAKT + k) == (64, 16) and plan.einst.art == "double_drop"
    assert plan.einst.eq == "bass_takt" and plan.einst.bass_takt == plan.takte - 1   # Bass-Switch am Ende
    assert _planen(pa, pb)[0].rezept != "double_drop"           # klassisch: nie


def test_phrasenraster_mit_versatz_und_drop_auf_den_takt():
    """Runde 8/9: echte Phrasen liegen oft neben dem Raster ab Takt 0 - Etiketten, Drops und Einstiege folgen."""
    p = _profil(SONG)
    for k in ("bass", "drums"):
        p.stems[k] = np.roll(p.stems[k], 2)        # alles 2 Takte spaeter
    p.gesamt = np.roll(p.gesamt, 2)
    assert p.versatz() == 6 and p.drops() == [18, 66]                # Drops = Einsatz von Bass und Drums
    assert p.phrase_start(p.phrase_von(66)) == 66 and p.grenzen()[:3] == [0, 10, 18]   # 2-Takt-Rest am Anfang verschmilzt
    drops = [p.phrase_start(q) for q, x in enumerate(p.etiketten()) if x == "drop"]
    assert 66 in drops and regie._drop_takt(p, 66) == 66
    b_ein = [t for t, _ in regie._b_kandidaten(p, Einstellungen(), None)]
    assert 10 in b_ein and 8 not in b_ein                     # B steigt auf seinen Phrasen ein
    assert _profil(SONG).versatz() == 0


def test_profi_eq_swap_auf_4er_grenzen():
    h = u._huellen(Einstellungen(art="eigen", eq="profi"), 16, 1600, 0.01)
    tausch = lambda k: int(np.argmax(h[k] > 0.5)) / 100   # noqa: E731  (Takt)
    assert abs(tausch("b_mitte") - 8) < 0.2 and abs(tausch("b_tief") - 12) < 0.2
    assert abs(int(np.argmax(h["a_hoch"] < 0.5)) / 100 - 4) < 0.2      # Hoehen tauschen auf Takt 4
    assert 0 < h["b_hoch"][50] < 0.1                                    # B's Hi-Hats vorher leise dabei


def test_pegel_reparieren_hebt_loch_statt_verwerfen():
    pa, pb = _profil(SONG), _profil(SONG)
    rate, tn = 1000, int(TAKT * 1000)
    blende = np.full((8 * tn, 2), 10 ** (-22 / 20), np.float32)
    blende[3 * tn:4 * tn] *= 10 ** (-12 / 20)                           # 12 dB Loch in Takt 4
    args = (rate, 8, pa, pb, 12 * PHRASE * TAKT, 0.0, 0.0, 0.0, "profi_eq")
    assert "Loch" in regie.pruefen(blende, *args)
    assert regie.pegel_reparieren(blende, *args) and regie.pruefen(blende, *args) is None
    assert blende[0, 0] == pytest.approx(10 ** (-22 / 20), rel=1e-3)   # Anfang unveraendert


def test_drop_auf_den_ersten_vollen_takt():
    p = _profil([("break", 2), ("drop", 4)])            # Drop auf Takt 16
    k = 2 * PHRASE - 1                                  # Auftakt: Bass/Drums nur halb (Runde 15, Fall 17/37)
    p.stems["bass"][k], p.stems["drums"][k], p.gesamt[k] = -22.0, -20.0, -14.0
    assert p.drops()[0] == 2 * PHRASE


def test_double_drop_b_leiser_in_mitten_und_hoehen_bis_zum_switch():
    e = Einstellungen(art="eigen", lautstaerke="doppel", eq="bass_takt", bass_takt=15)
    h = u._huellen(e, 16, 1600, 0.01)
    assert h["b_tief"][800] == 0 and h["b_mitte"][800] == pytest.approx(0.7) and h["b_hoch"][800] == pytest.approx(0.4)
    assert h["b_hoch"][1599] == pytest.approx(1.0) and h["a_tief"][800] == pytest.approx(1.0)


def test_strukturregeln_drop_nicht_in_der_blende():
    p = _profil(SONG)                                            # Drops auf Takt 16 und 64
    bi = lambda j, L: regie._b_index(j, L)                       # noqa: E731
    assert "A's Drop" in regie._strukturfehler(p, p, 56, bi(0, 16), 16, False)     # A droppt bei 64 in der Blende
    assert "B's Drop" in regie._strukturfehler(p, p, 96, bi(8, 16), 16, False)     # B droppt bei 16 mittendrin
    assert "16 Takte" in regie._strukturfehler(p, p, 72, bi(0, 16), 16, False)     # A's Drop erst 8 Takte alt
    assert regie._strukturfehler(p, p, 96, bi(0, 16), 16, False) is None          # Outro -> B's Drop danach


def test_schnell_laesst_platz_fuer_die_blende_wenn_der_drop_bis_ans_ende_geht():
    p = _profil([("intro", 2), ("drop", 4), ("break", 2), ("drop", 6)])   # 2. Drop-Abschnitt bis zum Ende (112)
    kandidaten = regie._a_kandidaten(p, 0, Einstellungen(spielanteil="schnell"), False)
    assert any(p.n - t >= 16 for t, _, _ in kandidaten)   # ohne: nur Ausstiege, bei denen A in der Blende endet


def test_b_filter_oeffnet_hoechstens_ueber_16_takte():
    h = u._huellen(Einstellungen(art="eigen", filter="tp_ein"), 32, 3200, 0.01)
    assert h["b_tp"][0] == pytest.approx(1.0) and h["b_tp"][1600] == 0.0   # Runde 17: B kam bei 32 Takten zu spaet
    assert h["b_tp"][800] == pytest.approx(0.5, abs=0.01)


def test_unsauberer_loop_nur_zur_not(monkeypatch):
    monkeypatch.setattr(regie, "_loop_guete", lambda *a: 0.0)   # nirgends ein sauberer Loop
    pa = _profil(SONG[:-1] + [("outro", 1)])                     # kurzes Outro: spaete Ausstiege enden in der Blende
    plaene = regie.planen(None, pa, None, _profil(SONG), Einstellungen(modus="lang", spielanteil="lang"), 0.0,
                          True, False, stems_da=True, anzahl=6, a_audio=np.zeros((10, 2), np.float32))
    ohne = [p.einst.loop == "keiner" for p in plaene]
    assert ohne[0] and ohne == sorted(ohne, reverse=True)       # Loop-Plaene (A endet) erst ganz hinten
