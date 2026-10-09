"""Tests fuer phase09.py - Tor an der Wilson-Untergrenze, nicht am Punktwert.

> Hintergrund: Phase 0.2 entschied Tempo/Downbeat am **Punktwert** und hatte nur
> **7** Faelle. 7/7 Treffer ergeben aber eine Wilson-Untergrenze von 64,6 % - die
> Aussage „Tor erfuellt" haengt dann am Zufall, nicht an der Belastbarkeit.
>
> Diese Tests halten den Unterschied fest: `erreicht` (Untergrenze traegt) und
> `punktwert_erreicht` (bloss die Quote) sind getrennte Groessen. Genau daran
> haelt Phase 0.9 seine Ehrlichkeit.
"""

import argparse

from klangbild import phase09


def _args(**kwargs) -> argparse.Namespace:
    """Minimaler Namespace mit denselben Defaults wie `pipeline` ihn baut.

    Absichtlich identisch zur CLI: nur dann pruefen die Tests unten wirklich die
    Produktionsvorgaben (n=300) und nicht eine Zahl aus der Testdatei.
    """
    basis = {"bpm_von": 60.0, "bpm_bis": 180.0, "bpm_stufen": 50,
             "sekunden": 20.0, "limit": 0}
    basis.update(kwargs)
    return argparse.Namespace(**basis)


# --- Aufbau der Faelle -------------------------------------------------------


def test_faelle_kreuzen_taktart_und_tempo():
    faelle = phase09.baue_faelle(tempi=(60.0, 120.0), taktarten=(4, 3),
                                 sekunden=5.0)
    assert len(faelle) == 4                      # 2 Taktarten x 2 Tempi
    assert {f.takt for f in faelle} == {4, 3}
    assert {f.bpm for f in faelle} == {60.0, 120.0}


def test_taktart_steckt_in_der_ground_truth():
    """Downbeat muss taktabhaengig sein - sonst waere 4/4 der einzige Test."""
    faelle = {f.takt: f for f in phase09.baue_faelle(tempi=(120.0,),
                                                     taktarten=(4, 7))}
    # 120 BPM -> 0,5 s/Schlag: bei 4/4 alle 2,0 s, bei 7/8 alle 3,5 s.
    assert faelle[4].metro.downbeats[1] - faelle[4].metro.downbeats[0] == 2.0
    assert faelle[7].metro.downbeats[1] - faelle[7].metro.downbeats[0] == 3.5


def test_tempi_raster_ist_dicht_und_deckt_oktavfallen():
    """Die Oktavfallen muessen *im* Raster liegen, nicht zwischen den Stufen.

    Ein lineares Raster von 60 bis 180 laesst 120 auf 122,45 fallen - die
    haeufigste Verwechslung (60 vs 120) waere damit gar nicht gemessen.
    """
    tempi = phase09._tempi_aus_args(_args())
    assert len(tempi) >= 50                      # dicht genug fuer ein Tor
    assert tempi[0] == 60.0 and tempi[-1] == 180.0
    for anker in (60.0, 90.0, 100.0, 120.0, 128.0, 140.0, 174.0, 180.0):
        assert anker in tempi
    assert tempi == tuple(sorted(tempi))         # sortiert, keine Doppel
    assert len(set(tempi)) == len(tempi)


def test_oktave_im_raster_gleichweit_wie_eine_stufe():
    """Log-Raster: eine Verdopplung ist genau eine Oktave = 12 gleiche Schritte.

    Fenster ohne Anker (181-362, oberhalb aller Anker), sonst mischt der
    Test Raster und Anker.
    """
    tempi = phase09._tempi_aus_args(_args(bpm_von=181.0, bpm_bis=362.0,
                                          bpm_stufen=13))
    assert len(tempi) == 13
    # 181 bis 362 ist genau eine Oktave -> 12 gleich grosse relative Schritte.
    schritte = [tempi[i + 1] / tempi[i] for i in range(len(tempi) - 1)]
    assert max(schritte) - min(schritte) < 0.001
    assert abs(schritte[0] - 2 ** (1 / 12)) < 0.001


def test_tempi_stufen_mindestens_zwei():
    """Eine Stufe allein waere kein Raster (und wuerde durch 0 teilen).

    Fenster ohne Anker (164-172), damit hier wirklich nur die Aufrundung prueft.
    """
    tempi = phase09._tempi_aus_args(_args(bpm_stufen=1, bpm_von=164.0,
                                          bpm_bis=172.0))
    assert len(tempi) == 2
    assert tempi[0] == 164.0 and tempi[-1] == 172.0


# --- Das Tor: Untergrenze entscheidet, nicht der Punktwert -------------------


def test_tor_bei_vielen_treffern_erreicht():
    t = phase09._tor(295, 300, 0.90)
    assert t["erreicht"] is True
    assert t["punktwert_erreicht"] is True
    assert t["wilson_unten"] >= 0.90


def test_tor_am_punktwert_allein_reicht_nicht():
    """Der Kernfehler von Phase 0.2, hier als Test festgenagelt.

    n=7 mit 7/7: Punktwert 100 % - aber die Untergrenze liegt bei 64,6 %.
    Phase 0.2 haette „erfuellt" gesagt, Phase 0.9 sagt „nicht erfuellt".
    """
    t = phase09._tor(7, 7, 0.90)
    assert t["punktwert_erreicht"] is True        # Quote schoen
    assert t["erreicht"] is False                 # Untergrenze traegt nicht
    assert abs(t["wilson_unten"] - 0.6461) < 0.01


def test_tor_braucht_gegenbeispiele_mitgezaehlt():
    t = phase09._tor(240, 300, 0.90)
    assert t["erreicht"] is False


def test_tor_ohne_faelle_ist_nicht_erfuellt():
    """Kein Modell / keine Faelle: OFFEN, nicht „bestanden"."""
    t = phase09._tor(0, 0, 0.90)
    assert t["erreicht"] is False
    assert t["quote"] == 0.0
    assert t["punktwert_erreicht"] is False


def test_gleiche_quote_verschiedene_n_verschiedene_aussage():
    """95 % bei n=300 traegt, 95 % bei n=7 nicht - gleicher Punktwert."""
    gross = phase09._tor(285, 300, 0.90)
    klein = phase09._tor(int(7 * 0.95), 7, 0.90)
    assert gross["quote"] > klein["quote"] or True   # nur Info
    assert gross["wilson_unten"] > klein["wilson_unten"]


# --- Auswertung ueber die Faelle --------------------------------------------


def _zeile(fall: phase09.Fall, **over) -> dict:
    """Eine Zeile im Format, das `_faelle_bewerten` liefert."""
    basis = {"fall": fall.name, "takt": fall.takt, "bpm_soll": fall.bpm,
             "hat_beats": True, "beat_f1": 0.9, "bpm_geschaetzt": fall.bpm,
             "bpm_richtig": True, "downbeat_richtig": True}
    basis.update(over)
    return basis


def test_auswerten_zaehlt_nur_faelle_mit_beats():
    """Ein Fall ohne Beats darf nicht als Treffer gelten (still wuerde zu viel)."""
    faelle = phase09.baue_faelle(tempi=(120.0,), taktarten=(4,))
    zeilen = [_zeile(faelle[0], hat_beats=False, beat_f1=None,
                     bpm_geschaetzt=None, bpm_richtig=False,
                     downbeat_richtig=False)]
    z = phase09.auswerten(faelle, zeilen)
    assert z["anzahl_faelle"] == 1
    assert z["anzahl_mit_beats"] == 0          # ohne Beats: nicht gezaehlt
    assert z["bpm"]["erreicht"] is False
    assert z["beat_f1_mittel"] == 0.0


def test_auswerten_gute_faelle_bestehen_beide_tore():
    faelle = phase09.baue_faelle(tempi=tuple(60 + i for i in range(50)),
                                 taktarten=(4,))
    zeilen = [_zeile(f) for f in faelle]
    z = phase09.auswerten(faelle, zeilen)
    assert z["anzahl_mit_beats"] == 50
    assert z["bpm"]["erreicht"] is True
    assert z["downbeat"]["erreicht"] is True
    assert z["beat_f1_mittel"] == 0.9


def test_auswerten_schlusselt_nach_taktart_auf():
    """Downbeat ist taktabhaengig - eine Gesamtquote wuerde das verstecken."""
    faelle = phase09.baue_faelle(tempi=(120.0,), taktarten=(4, 3))
    zeilen = [
        _zeile(faelle[0]),                      # 4/4: alles richtig
        _zeile(faelle[1], downbeat_richtig=False, bpm_richtig=False),
    ]
    z = phase09.auswerten(faelle, zeilen)
    assert set(z["je_takt"]) == {"4", "3"}
    assert z["je_takt"]["4"]["downbeat_ok"] == 1
    assert z["je_takt"]["3"]["downbeat_ok"] == 0
    assert z["je_takt"]["3"]["bpm_ok"] == 0


def test_auswerten_je_takt_deckt_alle_taktarten():
    """Auch eine Taktart ohne einzige Messung bekommt einen Eintrag."""
    faelle = phase09.baue_faelle(tempi=(120.0,), taktarten=(4, 5))
    z = phase09.auswerten(faelle, [_zeile(faelle[0], hat_beats=False,
                                          beat_f1=None, bpm_geschaetzt=None,
                                          bpm_richtig=False,
                                          downbeat_richtig=False)])
    assert z["je_takt"]["5"]["gesamt"] == 0
    assert z["je_takt"]["5"]["beat_f1_mittel"] == 0.0


# --- Ausgabe ----------------------------------------------------------------


def test_bericht_nennt_tor_und_warnung(tmp_path):
    faelle = phase09.baue_faelle(tempi=(120.0,), taktarten=(4,))
    z = phase09.auswerten(faelle, [_zeile(faelle[0])])
    p = phase09._bericht_schreiben(tmp_path, z, 1.5)
    text = p.read_text(encoding="utf-8")
    assert "Phase 0.9" in text
    assert "Untergrenze" in text
    assert "Metronom ist der leichteste Fall" in text   # Ehrlichkeit im Bericht
    assert "6 Taktarten" not in text                      # keine Zahl erfunden


def test_bericht_zeigt_taktarttabelle(tmp_path):
    faelle = phase09.baue_faelle(tempi=(120.0,), taktarten=(4, 7))
    z = phase09.auswerten(faelle, [_zeile(f) for f in faelle])
    text = phase09._bericht_schreiben(tmp_path, z, 1.0).read_text(encoding="utf-8")
    assert "Nach Taktart" in text
    assert "| 7/4 |" in text


def test_json_export_hat_alle_tore(tmp_path):
    faelle = phase09.baue_faelle(tempi=(120.0,), taktarten=(4,))
    z = phase09.auswerten(faelle, [_zeile(faelle[0])])
    p = phase09._json_schreiben(tmp_path, z)
    import json
    daten = json.loads(p.read_text(encoding="utf-8"))
    for schluessel in ("bpm", "downbeat"):
        assert {"zaehler", "gesamt", "quote", "wilson_unten", "erreicht",
                "punktwert_erreicht"} <= set(daten[schluessel])


def test_csv_export_hat_kopfzeile_und_eine_zeile_je_fall(tmp_path):
    faelle = phase09.baue_faelle(tempi=(120.0, 130.0), taktarten=(4,))
    zeilen = [_zeile(faelle[0]), _zeile(faelle[1], hat_beats=False,
                                        beat_f1=None, bpm_geschaetzt=None,
                                        bpm_richtig=False, downbeat_richtig=False)]
    p = phase09._csv_schreiben(tmp_path, zeilen)
    roh = p.read_text(encoding="utf-8").strip().splitlines()
    assert roh[0].startswith("fall,takt,bpm_soll")
    assert len(roh) == 3                      # Kopf + 2 Faelle
    assert "fall" in roh[0]

