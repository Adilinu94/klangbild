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
        "Die Beschaffung der Referenzdaten haengt an einem **Lizenz-Gate** (ADR-012): "
        "Harmonix liefert nur Mel-Spektren (kein Audio) und keine Tonart-Labels, GTZAN nur "
        "Genre bei umstrittener Herkunft, GiantSteps-Audio sind kommerzielle Beatport-"
        "Ausschnitte. Bis ein Lizenz-freies Referenz-Korpus belegt ist, prueft "
        "`python -m klangbild metronom` die Messkette auf synthetischer Ground-Truth.\n"
    )
    zeilen.append(_analyse_uebersicht(conn, einstellungen.analyse_version))
    zeilen.append(_konsens_uebersicht(einstellungen.ergebnisse))

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


def _konsens_uebersicht(ergebnisse: Path) -> str:
    """Phase-0.3-Konsensergebnis einbetten, falls schon erzeugt."""
    z = Path(ergebnisse) / "phase03-konsens.json"
    if not z.exists():
        return ("\n## Phase 0.3 · Konsens (eigene Bibliothek)\n\n"
                "Noch kein Lauf. Erzeugen: `python -m klangbild konsens`.\n")
    try:
        daten = json.loads(z.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "\n## Phase 0.3 · Konsens (eigene Bibliothek)\n\nBericht nicht lesbar.\n"
    zeilen = ["\n## Phase 0.3 · Konsens (eigene Bibliothek)\n"]
    zeilen.append(
        "Uebereinstimmung **zwischen** freien Modellen (kein Gold-Tor, "
        "Lizenz-Gate ADR-012). Details: `ergebnisse/phase03-konsens.md`.\n")
    zeilen.append("| Kennzahl | Wert |\n|---|---|")
    zeilen.append(f"| aktive Schaetzer | {', '.join(daten.get('aktive_schaetzer', [])) or '–'} |")
    zeilen.append(f"| Tracks gesamt | {daten.get('tracks_gesamt', 0)} |")
    zeilen.append(f"| mehrere Schaetzer | {daten.get('tracks_mehrere_schaetzer', 0)} |")
    n = daten.get("tracks_mehrere_schaetzer", 0)
    if n:
        streng = daten.get("einig_streng", {})
        nachbar = daten.get("einig_nachbar", {})
        zeilen.append(f"| alle exakt gleich | {streng.get('gesamt', 0)}/{n} "
                      f"({streng.get('quote', 0) * 100:0.1f} %) |")
        zeilen.append(f"| alle im Camelot-Umfeld | {nachbar.get('gesamt', 0)}/{n} "
                      f"({nachbar.get('quote', 0) * 100:0.1f} %) |")
        zeilen.append(f"| harte Faelle | {daten.get('hart', {}).get('gesamt', 0)} |")
    else:
        zeilen.append("| Hinweis | nur ein Schaetzer aktiv – kein Konsens messbar |")
    return "\n".join(zeilen)
