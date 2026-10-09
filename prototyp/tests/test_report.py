"""Tests fuer report.py - Phase-0.8-Abschnitt und Rauchtest-Schutz.

Hintergrund: Der konsolidierte Bericht (`python -m klangbild report`) bettete
Phase 0.3 und 0.4 ein, aber **nicht** Phase 0.8 - er behauptete damit weiter den
alten Stand. Diese Tests halten zwei Dinge fest:

1. der Phase-0.8-Abschnitt erscheint und liest seine Zahlen aus den Artefakten;
2. die Baseline im Direktvergleich wird **aus phase04-gold.json gelesen**, nicht
   in den Text getippt - sonst driftet der Vergleich bei jedem Neulauf auseinander.

Ausserdem der Schutz gegen ein Missverstaendnis: ein `--limit`-Rauchtest (n=3)
darf keine Delta-Spalte zeigen, denn bei drei Faellen ist ein einzelner Treffer
Dutzende Zehntelpunkte wert. Genau daran scheiterte die Nachvollziehbarkeit, als
ein n=3-Lauf die n=400-Basislinie ueberschrieben hatte.
"""

import json

from klangbild import report


def _phase08(n=400, exakt=235, nachbar=329):
    """Artefakt-Form wie phase08 sie schreibt (via phase04.auswerten)."""
    return {
        "tracks": n,
        "exakt": {"treffer": exakt, "quote": exakt / n,
                   "wilson_unten": 0.539, "wilson_oben": 0.634,
                   "tor": 0.5, "erreicht": True},
        "nachbar": {"treffer": nachbar, "quote": nachbar / n,
                     "wilson_unten": 0.782, "wilson_oben": 0.857,
                     "tor": 0.7, "erreicht": True},
        "mittel_vertrauen": 0.0801,
        "klassen": {"exakt": exakt, "quint": 62, "modus": 32,
                     "diagonal": 27, "weit": 44},
        "hart": {"gesamt": n - exakt, "tracks": []},
    }


def _phase04(n=400, exakt=193, nachbar=294):
    return {
        "tracks": n,
        "exakt": {"treffer": exakt, "quote": exakt / n,
                   "wilson_unten": 0.434, "wilson_oben": 0.530,
                   "tor": 0.5, "erreicht": False},
        "nachbar": {"treffer": nachbar, "quote": nachbar / n,
                     "wilson_unten": 0.690, "wilson_oben": 0.775,
                     "tor": 0.7, "erreicht": False},
        "klassen": {"exakt": exakt, "quint": 95, "modus": 167,
                     "diagonal": 30, "weit": 45},
    }


def _vorbereiten(tmp_path, skey=None, gold=None):
    """Legt die Artefakte ab, die _skey_uebersicht liest."""
    if skey is not None:
        (tmp_path / "phase08-skey.json").write_text(
            json.dumps(skey, ensure_ascii=False), encoding="utf-8")
    if gold is not None:
        (tmp_path / "phase04-gold.json").write_text(
            json.dumps(gold, ensure_ascii=False), encoding="utf-8")
    return tmp_path


# --- Abschnitt erscheint (die Luecke, die Phase 0.8 hinterliess) -------------


def test_skey_abschnitt_fehlt_hinweis_ohne_lauf(tmp_path):
    text = report._skey_uebersicht(_vorbereiten(tmp_path))
    assert "Phase 0.8" in text
    assert "python -m klangbild phase08" in text


def test_skey_abschnitt_zeigt_quote_und_tor(tmp_path):
    text = report._skey_uebersicht(_vorbereiten(tmp_path, skey=_phase08()))
    assert "235/400" in text
    assert "58.8 %" in text
    assert "erfuellt" in text


# --- Baseline wird aus dem Artefakt gelesen, nicht getippt -------------------


def test_delta_kommt_aus_beiden_artefakten(tmp_path):
    """Delta = skey-Quote minus phase04-Quote, beide aus JSON."""
    text = report._skey_uebersicht(
        _vorbereiten(tmp_path, skey=_phase08(), gold=_phase04())
    )
    # 58,75 - 48,25 = 10,5 pp ; 82,25 - 73,5 = 8,8 pp
    assert "48.2 %" in text        # Baseline aus phase04-gold.json
    assert "58.8 %" in text        # skey aus phase08-skey.json
    assert "+10.5 pp" in text
    assert "+8.8 pp" in text


def test_delta_verschiebt_sich_mit_der_baseline(tmp_path):
    """Wird die Baseline neu gerechnet, verschiebt sich das Delta mit.

    Genau das ist der Punkt: die Zahl steht nicht im Quelltext, sonst wuerde der
    Bericht nach einem Neulauf von Phase 0.4 eine falsche Differenz behaupten.
    """
    besseres_gold = _phase04(exakt=249)   # z. B. verbessertes Chroma-Profil
    text = report._skey_uebersicht(
        _vorbereiten(tmp_path, skey=_phase08(), gold=besseres_gold)
    )
    # 58,75 - 62,25 = -3,5 pp: die Chroma-Basis liegt dann vor skey, und das
    # Vorzeichen muss es zeigen (sonst ist die Spalte Augenwischerei).
    assert "-3.5 pp" in text
    assert "+10.5 pp" not in text


# --- Rauchtest-Schutz (n=3 darf keine Delta-Aussage machen) ------------------


def test_rauchtest_zeigt_kein_delta(tmp_path):
    text = report._skey_uebersicht(
        _vorbereiten(tmp_path,
                     skey=_phase08(n=3, exakt=2, nachbar=3),
                     gold=_phase04(n=3, exakt=1, nachbar=2))
    )
    assert "Direktvergleich nicht berechnet" in text
    assert "Rauchtest" in text
    assert "pp |" not in text       # keine Delta-Spalte


def test_delta_fehlt_ohne_basislauf(tmp_path):
    text = report._skey_uebersicht(_vorbereiten(tmp_path, skey=_phase08()))
    assert "Direktvergleich nicht berechnet" in text
    assert "python -m klangbild gold" in text


def test_delta_fehlt_bei_ungleichem_n(tmp_path):
    """Goldsaetze unterschiedlicher Groesse sind nicht 1:1 vergleichbar."""
    text = report._skey_uebersicht(
        _vorbereiten(tmp_path, skey=_phase08(n=400), gold=_phase04(n=200))
    )
    assert "Direktvergleich nicht berechnet" in text
    assert "kein Phase-0.4-Lauf auf n=400" in text


# --- Robustheit -------------------------------------------------------------


def test_kaputtes_json_bricht_nicht(tmp_path):
    (tmp_path / "phase08-skey.json").write_text("{kein json", encoding="utf-8")
    text = report._skey_uebersicht(tmp_path)
    assert "Phase 0.8" in text       # sauberer Hinweis statt Traceback


def test_gold_abschnitt_warnt_bei_rauchtest(tmp_path):
    """Phase 0.4 muss ebenso kennzeichnen, wenn nur ein --limit-Lauf vorliegt."""
    (tmp_path / "phase04-gold.json").write_text(
        json.dumps(_phase04(n=3, exakt=1, nachbar=2)), encoding="utf-8")
    text = report._gold_uebersicht(tmp_path)
    assert "Rauchtest" in text
    assert "33.3 %" not in text      # die irrefuehrende Quote wird nicht gezeigt


def test_fehlerklassen_werden_mitgenannt(tmp_path):
    text = report._skey_uebersicht(_vorbereiten(tmp_path, skey=_phase08()))
    for klasse in ("quint", "modus", "diagonal", "weit"):
        assert klasse in text
    assert "15.5 %" in text          # quint 62/400
