"""Aufgaben bauen, Bewertungen einsammeln und die Tore auswerten (Phase 0.1).

Vier Aufgabenarten:
- `nachbarn`  – die k naechsten Nachbarn eines Ausgangssongs
- `baseline`  – k Zufallssongs zum selben Ausgangssong (Vergleichsmassstab)
- `text`      – Top-k zu einer sinnvollen Anfrage
- `unsinn`    – Top-k zu einer unsinnigen Anfrage (Kontrollsatz)

Ohne Baseline ist eine Prozentzahl nicht lesbar: 60 % „passt" kann gut oder
schlecht sein, je nachdem, wie oft Zufallssongs „passten".
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import numpy as np

from . import config, db, embeddings, metrics


def _log(text: str) -> None:
    print(text, flush=True)


def aktive_vektor_version(conn) -> str:
    """Welche Vektor-Version ausgewertet wird (Modell bevorzugt, sonst pseudo)."""
    zeilen = conn.execute(
        "SELECT modell_version, COUNT(*) AS anzahl FROM embeddings GROUP BY modell_version"
    ).fetchall()
    if not zeilen:
        return ""
    versionen = {zeile["modell_version"]: zeile["anzahl"] for zeile in zeilen}
    if config.MODELL_VERSION in versionen:
        return config.MODELL_VERSION
    return max(versionen, key=versionen.get)


def _nachbarn(matrix: np.ndarray, seed_index: int, k: int) -> list[int]:
    aehnlichkeit = matrix @ matrix[seed_index]
    aehnlichkeit[seed_index] = -np.inf
    return list(np.argsort(-aehnlichkeit)[:k])


def bauen_nachbarn(args: argparse.Namespace) -> int:
    einstellungen = config.vorbereiten(config.aus_argumenten(args))
    conn = db.verbinden(einstellungen.datenbank)
    version = aktive_vektor_version(conn)
    if not version:
        _log("Keine Vektoren vorhanden. Zuerst `python -m klangbild embed` ausfuehren.")
        return 2
    ids, matrix, _ = db.alle_vektoren(conn, version)
    if len(ids) < args.k + 1:
        _log(f"Zu wenige Tracks mit Vektoren ({len(ids)}).")
        return 2
    rng = np.random.default_rng(42)
    anzahl = min(args.n, len(ids))
    seeds = rng.choice(len(ids), size=anzahl, replace=False)
    for seed_index in seeds:
        nachbarn = _nachbarn(matrix, int(seed_index), args.k)
        db.aufgabe_speichern(
            conn, f"nachbarn-{ids[int(seed_index)]}", "nachbarn",
            ids[int(seed_index)], None, [ids[i] for i in nachbarn],
        )
    conn.commit()
    _log(f"{anzahl} Nachbar-Aufgaben gebaut (Version {version}).")
    conn.close()
    return 0


def bauen_baseline(args: argparse.Namespace) -> int:
    einstellungen = config.vorbereiten(config.aus_argumenten(args))
    conn = db.verbinden(einstellungen.datenbank)
    version = aktive_vektor_version(conn)
    ids, matrix, _ = db.alle_vektoren(conn, version)
    if len(ids) < args.k + 1:
        _log("Zu wenige Tracks mit Vektoren.")
        return 2
    rng = np.random.default_rng(1337)
    seeds = rng.choice(len(ids), size=min(args.n, len(ids)), replace=False)
    for seed_index in seeds:
        moeglich = [i for i in range(len(ids)) if i != int(seed_index)]
        ziehung = rng.choice(moeglich, size=args.k, replace=False)
        db.aufgabe_speichern(
            conn, f"baseline-{ids[int(seed_index)]}", "baseline",
            ids[int(seed_index)], None, [ids[i] for i in ziehung],
        )
    conn.commit()
    _log(f"{len(seeds)} Baseline-Aufgaben gebaut.")
    conn.close()
    return 0


def _anfragen_lesen(pfad: str | Path) -> list[str]:
    zeilen = Path(pfad).read_text(encoding="utf-8").splitlines()
    return [zeile.strip() for zeile in zeilen if zeile.strip() and not zeile.startswith("#")]


def bauen_text(args: argparse.Namespace, unsinn: bool) -> int:
    einstellungen = config.vorbereiten(config.aus_argumenten(args))
    conn = db.verbinden(einstellungen.datenbank)
    version = aktive_vektor_version(conn)
    if version == "" or version == "pseudo":
        _log("Text-Aufgaben brauchen echte Vektoren (Modell). Zuerst `embed` ohne --pseudo.")
        return 2
    ids, matrix, _ = db.alle_vektoren(conn, version)
    anfragen = _anfragen_lesen(args.queries)
    art = "unsinn" if unsinn else "text"
    for nummer, anfrage in enumerate(anfragen):
        try:
            vektor = embeddings.text_einbetten(anfrage)
        except embeddings.EinbettungFehler as fehler:
            _log(str(fehler))
            return 2
        rang = matrix @ vektor
        treffer = list(np.argsort(-rang)[: args.k])
        db.aufgabe_speichern(
            conn, f"{art}-{nummer:02d}", art, None, anfrage, [ids[i] for i in treffer]
        )
    conn.commit()
    _log(f"{len(anfragen)} {art}-Aufgaben gebaut.")
    conn.close()
    return 0


def serve(args: argparse.Namespace) -> int:
    from . import blindui

    einstellungen = config.vorbereiten(config.aus_argumenten(args))
    conn = db.verbinden(einstellungen.datenbank)
    return blindui.starten(conn, einstellungen.cache, args.host, args.port)


# --------------------------------------------------------------------------
# Auswertung
# --------------------------------------------------------------------------
def _quote(zaehler: int, gesamt: int) -> dict:
    unten, oben = metrics.wilson(zaehler, gesamt)
    return {
        "zaehler": zaehler,
        "gesamt": gesamt,
        "quote": (zaehler / gesamt) if gesamt else 0.0,
        "wilson_unten": unten,
        "wilson_oben": oben,
    }


def auswerten(conn) -> dict:
    """Rechnet je Aufgabenart die Quoten und prueft die Tore."""
    ergebnis: dict[str, dict] = {}
    for art in ("nachbarn", "baseline", "text", "unsinn"):
        zeilen = conn.execute(
            "SELECT b.urteil, b.unfall FROM bewertungen b JOIN aufgaben a ON a.id=b.aufgabe_id"
            " WHERE a.art=?",
            (art,),
        ).fetchall()
        gesamt = len(zeilen)
        passt_geht = sum(1 for z in zeilen if z["urteil"] in ("passt", "geht"))
        unfall = sum(1 for z in zeilen if z["unfall"])
        ergebnis[art] = {
            "stichprobe": gesamt,
            "passt_geht": _quote(passt_geht, gesamt),
            "unfall": _quote(unfall, gesamt),
        }

    nachbarn = ergebnis["nachbarn"]
    baseline = ergebnis["baseline"]
    text = ergebnis["text"]
    unsinn = ergebnis["unsinn"]

    unterschied = nachbarn["passt_geht"]["quote"] - baseline["passt_geht"]["quote"]
    tor_nachbarn = (
        nachbarn["stichprobe"] > 0
        and baseline["stichprobe"] > 0
        and nachbarn["unfall"]["quote"] <= config.TOR_01_NACHBARN_UNFALL_MAX
        and unterschied >= config.TOR_01_NACHBARN_UEBER_BASELINE
    )
    tor_text = (
        text["stichprobe"] > 0
        and unsinn["stichprobe"] > 0
        and text["passt_geht"]["quote"] >= config.TOR_01_TEXT_PASST
        and unsinn["passt_geht"]["quote"] <= config.TOR_01_TEXT_UNSINN_MAX
    )
    return {
        "arten": ergebnis,
        "unterschied_zu_baseline": unterschied,
        "tor_nachbarn": bool(tor_nachbarn),
        "tor_text": bool(tor_text),
        "tor_gesamt": bool(tor_nachbarn and tor_text),
        "grenzen": {
            "unfall_max": config.TOR_01_NACHBARN_UNFALL_MAX,
            "baseline_abstand": config.TOR_01_NACHBARN_UEBER_BASELINE,
            "text_passt": config.TOR_01_TEXT_PASST,
            "unsinn_max": config.TOR_01_TEXT_UNSINN_MAX,
        },
    }
