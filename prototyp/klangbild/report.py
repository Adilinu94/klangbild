"""Ergebnisbericht schreiben (Markdown, nach `prototyp/ergebnisse/`)."""

from __future__ import annotations

import json
from pathlib import Path

from . import config, db, evaluate


def _prozent(wert: float) -> str:
    return f"{wert * 100:0.1f} %"


def _quote_zeile(name: str, block: dict) -> str:
    return (
        f"| {name} | {block['gesamt']} | {_prozent(block['quote'])} "
        f"| {_prozent(block['wilson_unten'])}–{_prozent(block['wilson_oben'])} |"
    )


def schreiben(conn, einstellungen: config.Einstellungen) -> Path:
    zaehler = db.status(conn, einstellungen.analyse_version, einstellungen.modell_version)
    ergebnis = evaluate.auswerten(conn)
    grenzen = ergebnis["grenzen"]
    arten = ergebnis["arten"]

    zeilen: list[str] = []
    zeilen.append("# Klangbild-Prototyp · Bericht Phase 0\n")
    zeilen.append(f"Stand: automatisch erzeugt · Analyse-Version {einstellungen.analyse_version}"
                  f" · Modell-Version {einstellungen.modell_version}\n")
    zeilen.append("## Umfang\n")
    zeilen.append("| Groesse | Zahl |\n|---|---|")
    for name, wert in zaehler.items():
        zeilen.append(f"| {name} | {wert} |")

    zeilen.append("\n## Phase 0.1 · Taugt EmbeddingGemma 2 fuer Musik?\n")
    if arten["nachbarn"]["stichprobe"] == 0:
        zeilen.append("Noch keine Bewertungen. Oberflaeche: `python -m klangbild serve`.\n")
    else:
        zeilen.append("| Aufgabenart | Bewertungen | passt/geht | Wilson 95 % |")
        zeilen.append("|---|---|---|---|")
        for art, titel in (
            ("nachbarn", "Nachbarn"),
            ("baseline", "Baseline (Zufall)"),
            ("text", "Textsuche"),
            ("unsinn", "Kontrolle (Unsinn)"),
        ):
            zeilen.append(_quote_zeile(titel, arten[art]["passt_geht"]))
        zeilen.append("")
        zeilen.append("| Aufgabenart | Unfallquote | Wilson 95 % |")
        zeilen.append("|---|---|---|")
        for art, titel in (("nachbarn", "Nachbarn"), ("baseline", "Baseline")):
            zeilen.append(_quote_zeile(titel, arten[art]["unfall"]))
        zeilen.append("")
        unterschied = ergebnis["unterschied_zu_baseline"]
        zeilen.append(
            f"- Abstand zu Baseline (passt/geht): **{unterschied * 100:0.1f} Prozentpunkte** "
            f"(Schwelle {grenzen['baseline_abstand'] * 100:0.0f} pp)"
        )
        zeilen.append(
            f"- Unfallquote Nachbarn **{_prozent(arten['nachbarn']['unfall']['quote'])}** "
            f"(Schwelle {grenzen['unfall_max'] * 100:0.0f} %)"
        )
        zeilen.append(
            f"- Textsuche passt/geht **{_prozent(arten['text']['passt_geht']['quote'])}** "
            f"(Schwelle {grenzen['text_passt'] * 100:0.0f} %), "
            f"Unsinn **{_prozent(arten['unsinn']['passt_geht']['quote'])}** "
            f"(Schwelle {grenzen['unsinn_max'] * 100:0.0f} %)"
        )
        zeilen.append("")
        zeilen.append(f"**Tor Nachbarn:** {'erfuellt' if ergebnis['tor_nachbarn'] else 'nicht erfuellt'}  ")
        zeilen.append(f"**Tor Textsuche:** {'erfuellt' if ergebnis['tor_text'] else 'nicht erfuellt'}  ")
        zeilen.append(f"**Tor Phase 0.1 gesamt:** {'ERFUELLT' if ergebnis['tor_gesamt'] else 'NICHT ERFUELLT'}")

    zeilen.append("\n## Phase 0.2 · Analysegenauigkeit\n")
    zeilen.append(
        "Braucht Referenzdaten (Harmonix-Set, GTZAN, GiantSteps). Bis dahin hier nur die "
        "Abdeckung aus der eigenen Analyse:\n"
    )
    zeilen.append(_analyse_uebersicht(conn, einstellungen.analyse_version))

    pfad = einstellungen.ergebnisse / "phase0-bericht.md"
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text("\n".join(zeilen) + "\n", encoding="utf-8")
    return pfad


def _analyse_uebersicht(conn, analyse_version: str) -> str:
    zeilen = ["| Kennzahl | Wert |", "|---|---|"]
    gesamt = conn.execute(
        "SELECT COUNT(*) FROM features WHERE analyse_version=?", (analyse_version,)
    ).fetchone()[0]
    mit_beats = conn.execute(
        "SELECT COUNT(*) FROM features WHERE analyse_version=? AND beats_json NOT IN ('[]','null')",
        (analyse_version,),
    ).fetchone()[0]
    mit_tonart = conn.execute(
        "SELECT COUNT(*) FROM features WHERE analyse_version=? AND key_camelot IS NOT NULL",
        (analyse_version,),
    ).fetchone()[0]
    unsicher = conn.execute(
        "SELECT COUNT(*) FROM features WHERE analyse_version=? AND key_vertrauen < 0.3",
        (analyse_version,),
    ).fetchone()[0]
    lufs_zeilen = conn.execute(
        "SELECT lufs FROM features WHERE analyse_version=? AND lufs IS NOT NULL",
        (analyse_version,),
    ).fetchall()
    lufs_werte = [zeile["lufs"] for zeile in lufs_zeilen]
    zeilen.append(f"| analysierte Tracks | {gesamt} |")
    zeilen.append(f"| davon mit Beats | {mit_beats} |")
    zeilen.append(f"| davon mit Tonart | {mit_tonart} |")
    zeilen.append(f"| davon Tonart unsicher (< 0,3) | {unsicher} |")
    if lufs_werte:
        mittel = sum(lufs_werte) / len(lufs_werte)
        zeilen.append(f"| mittlere Lautheit | {mittel:0.1f} LUFS |")
    untersuchung = conn.execute(
        "SELECT container, COUNT(*) AS n FROM tracks GROUP BY container ORDER BY n DESC"
    ).fetchall()
    if untersuchung:
        zeilen.append("")
        zeilen.append("| Container | Tracks |")
        zeilen.append("|---|---|")
        for zeile in untersuchung:
            zeilen.append(f"| {zeile['container']} | {zeile['n']} |")
    return "\n".join(zeilen)
