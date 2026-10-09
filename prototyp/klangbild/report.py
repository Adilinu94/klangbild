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
    zeilen.append(_gold_uebersicht(einstellungen.ergebnisse))
    zeilen.append(_skey_uebersicht(einstellungen.ergebnisse))
    zeilen.append(_phase09_uebersicht(einstellungen.ergebnisse))

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


def _gold_uebersicht(ergebnisse: Path) -> str:
    """Phase-0.4-Goldtor gegen FMAK einbetten, falls schon erzeugt."""
    z = Path(ergebnisse) / "phase04-gold.json"
    if not z.exists():
        return ("\n## Phase 0.4 · Gold-Tor Tonart (FMAK)\n\n"
                "Noch kein Lauf. Erzeugen: `python -m klangbild gold`. "
                "Details: `ergebnisse/phase04-gold.md`.\n")
    try:
        daten = json.loads(z.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "\n## Phase 0.4 · Gold-Tor Tonart (FMAK)\n\nBericht nicht lesbar.\n"
    n = daten.get("tracks", 0)
    zeilen = ["\n## Phase 0.4 · Gold-Tor Tonart (FMAK)\n"]
    zeilen.append(
        "Experten-annotierte Tonart (FMAK, CC BY 4.0) gegen unseren eigenen "
        "Schaetzer – echte Trefferquote, nicht Modell-Uebereinstimmung. "
        "Tor prueft die **Untergrenze** des Wilson-Intervalls (ADR-012, Phase 0.2).\n")
    if not n:
        zeilen.append(
            "| Hinweis | keine Tracks ausgewertet (FMAK-Audio holen: "
            "`python -m klangbild gold --fmak-remote`) |")
        return "\n".join(zeilen)
    if n < 30:
        zeilen.append(
            f"| Hinweis | nur n={n} ausgewertet - **Rauchtest**, die Quoten "
            "sind nicht belastbar (Wilson-Untergrenze weit offen). Fuer das Tor: "
            "`python -m klangbild gold` ohne `--limit` |")
        return "\n".join(zeilen)
    zeilen.append("| Kennzahl | Treffer/N | Quote | Wilson 95 % | erreicht? |")
    zeilen.append("|---|---|---|---|---|")
    for name, schluessel in (("exakt gleiche Tonart", "exakt"),
                             ("inkl. Camelot-Nachbar", "nachbar")):
        t = daten.get(schluessel, {})
        wilson = f"{t.get('wilson_unten', 0) * 100:0.1f}-{t.get('wilson_oben', 0) * 100:0.1f} %"
        erreicht = "erfuellt" if t.get("erreicht") else "nicht erfuellt"
        zeilen.append(
            f"| {name} | {t.get('treffer', 0)}/{n} "
            f"| {t.get('quote', 0) * 100:0.1f} % | {wilson} | {erreicht} |")
    zeilen.append(f"| harte Faelle | {daten.get('hart', {}).get('gesamt', 0)} | – | – | – |")
    klassen = daten.get("klassen") or {}
    if klassen:
        zeilen.append("")
        zeilen.append("Wo der Schaetzer danebenliegt (Fehlerklassen):")
        for name in ("exakt", "modus", "quint", "diagonal", "weit"):
            anz = klassen.get(name, 0)
            zeilen.append(f"- {name}: {anz} ({anz / n * 100:0.1f} %)")
    zeilen.append("")
    zeilen.append("Vollstaendiger Per-Track-Export (alle Tracks): "
                  "`ergebnisse/phase04-gold-tracks.csv`.")
    return "\n".join(zeilen)


def _json_laden(pfad: Path) -> dict | None:
    """JSON einlesen; None bei fehlender/unlesbarer Datei (nie werfen)."""
    if not pfad.exists():
        return None
    try:
        return json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _skey_uebersicht(ergebnisse: Path) -> str:
    """Phase-0.8-Ergebnis (skey, trainiertes CNN) gegen den Goldsatz einbetten.

    Entscheidend fuer die Belastbarkeit des Vergleichs: die Baseline
    (**unser Chroma-Profil**) wird **nicht** als Zahl in diesen Text geschrieben,
    sondern aus `phase04-gold.json` gelesen. Beide Zeilen stammen also aus
    Artefakten desselben Goldsatzes - wer eine Seite neu rechnet, rechnet den
    Vergleich mit. Genau das haelt Phase 0.8 vergleichbar statt anekdotisch.
    """
    skey = _json_laden(Path(ergebnisse) / "phase08-skey.json")
    titel = "\n## Phase 0.8 · skey (trainiertes CNN) gegen denselben Goldsatz\n"
    if skey is None:
        return titel + (
            "Noch kein Lauf. Erzeugen: `python -m klangbild phase08` "
            "(braucht skey: torch, torchaudio, nnAudio). "
            "Details: `ergebnisse/phase08-skey.md`.\n"
        )

    n = skey.get("tracks", 0)
    zeilen = [titel]
    zeilen.append(
        "Dasselbe FMAK-Gold, dieselbe Metrik, dieselben Tore, dasselbe "
        "Wilson-Intervall wie Phase 0.4 – **nur der Schaetzer ist getauscht**: "
        "statt handgeschriebener Chroma-Profile ein trainiertes CNN "
        "(`deezer/skey`, MIT → passiert das Lizenz-Gate ADR-012). Tor prueft die "
        "**Untergrenze** des Wilson-Intervalls.\n"
    )
    if not n:
        zeilen.append("| Hinweis | keine Tracks ausgewertet |")
        return "\n".join(zeilen)

    zeilen.append("| Kennzahl | Treffer/N | Quote | Wilson 95 % | erreicht? |")
    zeilen.append("|---|---|---|---|---|")
    for name, schluessel in (("exakt gleiche Tonart", "exakt"),
                             ("inkl. Camelot-Nachbar", "nachbar")):
        t = skey.get(schluessel, {})
        wilson = f"{t.get('wilson_unten', 0) * 100:0.1f}-{t.get('wilson_oben', 0) * 100:0.1f} %"
        erreicht = "erfuellt" if t.get("erreicht") else "nicht erfuellt"
        zeilen.append(
            f"| {name} | {t.get('treffer', 0)}/{n} "
            f"| {t.get('quote', 0) * 100:0.1f} % | {wilson} | {erreicht} |")

    # Direktvergleich: Baseline aus dem Phase-0.4-Artefakt, nicht getippt.
    # Mindestumfang, sonst waere ein Delta aus einem --limit-Rauchtest eine
    # Zahl ohne Aussage (bei wenigen Faellen ist ein einziger Treffer hunderte
    # Zehntelpunkte wert - dieselbe Warnung, die die Roadmap fuer Phase 0.1 gibt).
    gold = _json_laden(Path(ergebnisse) / "phase04-gold.json")
    MIN_DELTA_N = 30
    zeilen.append("")
    if gold and gold.get("tracks") == n and n >= MIN_DELTA_N:
        zeilen.append("**Direktvergleich (gleicher Goldsatz, nur Schaetzer getauscht):**\n")
        zeilen.append("| Kennzahl | Chroma-Profil (0.4) | skey (0.8) | Delta |")
        zeilen.append("|---|---|---|---|")
        for name, schluessel in (("exakt", "exakt"), ("inkl. Nachbar", "nachbar")):
            a = gold.get(schluessel, {}).get("quote", 0.0)
            b = skey.get(schluessel, {}).get("quote", 0.0)
            zeilen.append(
                f"| {name} | {a * 100:0.1f} % | {b * 100:0.1f} % "
                f"| {(b - a) * 100:+0.1f} pp |")
    else:
        grund = (
            f"n={n} unter {MIN_DELTA_N} (Rauchtest)"
            if n < MIN_DELTA_N
            else f"kein Phase-0.4-Lauf auf n={n}"
        )
        zeilen.append(
            f"| Hinweis | Direktvergleich nicht berechnet ({grund}; "
            "`python -m klangbild gold` erzeugt die Baseline) |")

    klassen = skey.get("klassen") or {}
    if klassen:
        zeilen.append("")
        zeilen.append("Wo skey danebenliegt (Fehlerklassen):")
        for name in ("exakt", "modus", "quint", "diagonal", "weit"):
            anz = klassen.get(name, 0)
            zeilen.append(f"- {name}: {anz} ({anz / n * 100:0.1f} %)")

    zeilen.append("")
    zeilen.append(
        "> Das Softmax-Max ist ein **roher, unkalibrierter** Wert (Mittel nahe "
        "1/24): gegated wird nur ueber Trefferquote + Wilson-Untergrenze, "
        "niemals ueber diesen Rohwert.")
    zeilen.append(
        "> Vollstaendiger Per-Track-Export (alle Tracks): "
        "`ergebnisse/phase08-skey-tracks.csv`.")
    return "\n".join(zeilen)


def _phase09_uebersicht(ergebnisse: Path) -> str:
    """Phase-0.9-Ergebnis (Beat This!) einbetten - Tempo und Downbeat.

    Liest `phase09-beats.json`. Ohne Lauf: ehrliches OFFEN, nicht „gescheitert" -
    ohne Modell ist nichts gemessen, und „nicht gemessen" ist kein Fehlschlag.
    """
    titel = "\n## Phase 0.9 · Beat This! auf Tempo und Downbeat\n"
    daten = _json_laden(Path(ergebnisse) / "phase09-beats.json")
    if daten is None:
        return titel + (
            "Noch kein Lauf. Erzeugen: `python -m klangbild phase09` "
            "(braucht beat-this + lokalen Checkpoint). "
            "Details: `ergebnisse/phase09-beats.md`.\n"
        )
    if not daten.get("anzahl_mit_beats"):
        return titel + (
            "Lauf ohne messbare Faelle (Modell fehlte) - **Tor OFFEN**, "
            "nicht gescheitert.\n"
        )

    zeilen = [titel]
    zeilen.append(
        "Dieselbe Messkette wie Phase 0.2, aber mit **n gross genug fuer ein "
        "belastbares Tor** und mit mehreren Taktarten (Downbeat ist "
        "taktabhaengig). Tor entscheidet an der **Untergrenze** des "
        "Wilson-Intervalls, nicht am Punktwert - Phase 0.2 entschied am "
        "Punktwert und hatte nur 7 Faelle.\n"
    )
    zeilen.append("| Kennzahl | Treffer/N | Quote | Wilson 95 % | erreicht? |")
    zeilen.append("|---|---|---|---|---|")
    namen = {"bpm": "Tempo richtig", "downbeat": "Downbeat richtig"}
    for schluessel, label in namen.items():
        t = daten.get(schluessel, {})
        zeilen.append(
            f"| {label} | {t.get('zaehler', 0)}/{t.get('gesamt', 0)} "
            f"| {t.get('quote', 0) * 100:0.1f} % | "
            f"{t.get('wilson_unten', 0) * 100:0.1f}-"
            f"{t.get('wilson_oben', 0) * 100:0.1f} % | "
            f"{'erfuellt' if t.get('erreicht') else 'nicht erfuellt'} |")
    zeilen.append("")
    zeilen.append(f"- mittlere Beat-F1: {daten.get('beat_f1_mittel', 0.0):0.3f}")

    je_takt = daten.get("je_takt") or {}
    if je_takt:
        zeilen.append("")
        zeilen.append("Nach Taktart:")
        zeilen.append("")
        zeilen.append("| Takt | Faelle | Tempo ok | Downbeat ok | Beat-F1 |")
        zeilen.append("|---|---|---|---|---|")
        for takt, t in je_takt.items():
            zeilen.append(
                f"| {takt}/4 | {t.get('gesamt', 0)} | {t.get('bpm_ok', 0)} "
                f"| {t.get('downbeat_ok', 0)} "
                f"| {t.get('beat_f1_mittel', 0.0):0.3f} |")

    zeilen.append("")
    zeilen.append(
        "> **Grenze der Aussage:** die Faelle sind **synthetische Metronome** "
        "(starres Tempo, ein Klang, kein Groove) - der leichteste Fall. Das Tor "
        "belegt Messkette *und* Modell auf bekannten Signalen, nicht die "
        "Genauigkeit auf echter Musik. Dafuer braucht es ein lizenzfreies "
        "Korpus mit Beat-Labels (offen wie fuer Tonart, Lizenz-Gate ADR-012).")
    zeilen.append(
        "> Vollstaendiger Per-Fall-Export: "
        "`ergebnisse/phase09-beats-tracks.csv`.")
    return "\n".join(zeilen)
