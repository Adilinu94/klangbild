"""Kommandozeile des Prototyps.

Aufruf (Beispiele):
    python -m klangbild status
    python -m klangbild scan
    python -m klangbild analyze
    python -m klangbild embed               # braucht Modell (Download ~1,5 GB)
    python -m klangbild embed --pseudo      # nur zum Testen der Mechanik
    python -m klangbild neighbors --n 20
    python -m klangbild baseline  --n 20
    python -m klangbild serve               # Bewertungsoberflaeche im Browser
    python -m klangbild report

Alles ist wiederaufsetzbar: eine erneute Ausfuehrung laesst fertige Tracks aus.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

from . import (
    audioio,
    beats,
    config,
    db,
    embeddings,
    energy,
    hashutil,
    keyestimate,
    lufs,
    metrics,
)


def _log(text: str) -> None:
    print(text, flush=True)


# --------------------------------------------------------------------------
# scan
# --------------------------------------------------------------------------
def kommandos_scan(args: argparse.Namespace) -> int:
    einstellungen = config.vorbereiten(config.aus_argumenten(args))
    quelle = einstellungen.bibliothek
    if not quelle.exists():
        _log(f"Sammlung nicht gefunden: {quelle}")
        return 2
    dateien = sorted(
        pfad
        for pfad in quelle.rglob("*")
        if pfad.is_file() and pfad.suffix.lower() in config.AUDIO_ENDUNGEN
    )
    _log(f"{len(dateien)} Audiodateien in {quelle}")
    conn = db.verbinden(einstellungen.datenbank)
    neu_oder_geaendert = 0
    beginn = time.time()
    for nummer, pfad in enumerate(dateien, 1):
        stat = pfad.stat()
        audio_hash, bereich = hashutil.datei_hash(pfad)
        _, ist_neu = db.track_eintragen(
            conn, pfad, stat.st_size, stat.st_mtime, audio_hash,
            bereich.container, bereich.start, bereich.ende,
        )
        neu_oder_geaendert += ist_neu
        if nummer % 50 == 0 or nummer == len(dateien):
            conn.commit()
            _log(f"  {nummer}/{len(dateien)} · {time.time() - beginn:0.1f}s")
    conn.commit()
    _log(f"fertig: {neu_oder_geaendert} neu/geaendert von {len(dateien)}")
    conn.close()
    return 0


# --------------------------------------------------------------------------
# analyze
# --------------------------------------------------------------------------
def track_analysieren(pfad: Path, schlag_da: bool) -> dict:
    """Tonart, Lautheit, Energie, Abschnitte und (falls da) Beats einer Datei.

    Geteilt von `analyze` (CLI) und dem Upload im Mixer. Wirft nie: jede Datei darf
    einzeln scheitern, der Fehler steht dann im Status.
    """
    werte: dict = {}
    try:
        audio = audioio.decodieren(pfad, config.ABTASTRATE_ANALYSE)
        if audio.sekunden < config.MIN_SEKUNDEN:
            werte["status"] = "zu_kurz"
        else:
            tonart = keyestimate.tonart_schaetzen(audio.daten, audio.rate)
            werte.update(
                key_name=tonart.name,
                key_camelot=tonart.camelot,
                key_vertrauen=tonart.vertrauen,
            )
            werte["lufs"] = lufs.integrierte_lautheit(audio.daten, audio.rate)
            werte["true_peak"] = lufs.true_peak_dbtp(audio.daten, audio.rate)
            zeiten, db_werte = energy.rms_kurve(audio.daten, audio.rate)
            werte["energie"] = [[round(float(t), 2), round(float(v), 1)] for t, v in zip(zeiten, db_werte)]
            werte["abschnitte"] = [round(float(t), 2) for t in energy.abschnitte(audio.daten, audio.rate)]
            if schlag_da:
                try:
                    schlag = beats.analysieren(pfad)
                    werte["beats"] = [round(float(t), 4) for t in schlag.beats]
                    werte["downbeats"] = [round(float(t), 4) for t in schlag.downbeats]
                    werte["bpm"] = round(metrics.bpm_aus_beats(schlag.beats), 2)
                except Exception as fehler:  # noqa: BLE001
                    werte["status"] = f"schlagfehler: {fehler}"
            werte.setdefault("status", "ok")
    except Exception as fehler:  # noqa: BLE001 - jede Datei darf einzeln scheitern
        werte = {"status": f"fehler: {fehler}"}
    return werte


def kommandos_analyze(args: argparse.Namespace) -> int:
    einstellungen = config.vorbereiten(config.aus_argumenten(args))
    conn = db.verbinden(einstellungen.datenbank)
    offen = db.fehlende_features(conn, einstellungen.analyse_version)
    if args.limit:
        offen = offen[: args.limit]
    _log(f"{len(offen)} Tracks ohne Analyse")
    schlag_da = beats.verfuegbar()
    if not schlag_da and not getattr(args, "ohne_beats", False):
        # Fail-Fast statt stiller Zeilen ohne Beats: wer analyze ohne beat-this
        # startet (z. B. System-Python statt venv), bekommt sonst 498 Zeilen mit
        # leerem beats_json, die spaeter wie echte Analysen aussehen. Abbruch mit
        # Anleitung; nur --ohne-beats geht bewusst weiter (z. B. nur Tonart/LUFS).
        _log("ABBRUCH: beat-this fehlt - ohne Schlaganalyse entstuenden Zeilen ohne Beats.")
        _log("Installation: python -m pip install beat-this (zieht torch nach).")
        _log("Checkpoint: daten/modelle/torchhub/checkpoints/beat_this-final0.ckpt")
        _log("Nur wenn Beats bewusst entfallen sollen: analyze --ohne-beats.")
        conn.close()
        return 2
    if not schlag_da:
        _log("Hinweis: beat-this fehlt - Schlaganalyse wird uebersprungen (Rest laeuft).")
    beginn = time.time()
    for nummer, zeile in enumerate(offen, 1):
        werte = track_analysieren(Path(zeile["pfad"]), schlag_da)
        db.features_speichern(conn, int(zeile["id"]), einstellungen.analyse_version, werte)
        if nummer % 10 == 0 or nummer == len(offen):
            conn.commit()
            _log(f"  {nummer}/{len(offen)} · {time.time() - beginn:0.1f}s")
    conn.commit()
    conn.close()
    return 0


# --------------------------------------------------------------------------
# embed
# --------------------------------------------------------------------------
def kommandos_embed(args: argparse.Namespace) -> int:
    einstellungen = config.vorbereiten(config.aus_argumenten(args))
    version = "pseudo" if args.pseudo else einstellungen.modell_version
    conn = db.verbinden(einstellungen.datenbank)
    offen = db.fehlende_vektoren(conn, version, config.AUSSCHNITTE)
    if args.limit:
        offen = offen[: args.limit]
    _log(f"{len(offen)} Tracks ohne vollstaendige Vektoren (Version {version})")
    if args.pseudo:
        _log("ACHTUNG: --pseudo schreibt Zufallsvektoren. Niemals fuer ein Tor verwenden.")
    beginn = time.time()
    zaehler = 0
    for nummer, zeile in enumerate(offen, 1):
        pfad = Path(zeile["pfad"])
        try:
            audio = audioio.decodieren(pfad, config.ABTASTRATE_EINBETTUNG)
            for position, start, ende in audioio.ausschnitte_planen(audio):
                # Rohe Mono-Samples direkt schneiden (kein Temp-WAV): vermeidet den
                # load_audio/librosa-Weg, haelt die Dekodierung bei soundfile (ADR-012).
                proben = np.ascontiguousarray(audio.daten[start:ende], dtype=np.float32)
                vektor = (
                    embeddings.pseudo_vektor(f"{zeile['id']}:{position}")
                    if args.pseudo
                    else embeddings.audio_einbetten(proben, audio.rate)
                )
                db.embedding_speichern(
                    conn, int(zeile["id"]), position, version, vektor,
                    str(pfad), start / audio.rate, ende / audio.rate,
                )
                zaehler += 1
            conn.commit()
        except Exception as fehler:  # noqa: BLE001
            _log(f"  Fehler bei {pfad.name}: {fehler}")
        if nummer % 10 == 0 or nummer == len(offen):
            _log(f"  {nummer}/{len(offen)} · {zaehler} Vektoren · {time.time() - beginn:0.1f}s")
    conn.commit()
    conn.close()
    return 0


# --------------------------------------------------------------------------
# status / report
# --------------------------------------------------------------------------
def kommandos_status(args: argparse.Namespace) -> int:
    einstellungen = config.vorbereiten(config.aus_argumenten(args))
    conn = db.verbinden(einstellungen.datenbank)
    werte = db.status(conn, einstellungen.analyse_version, einstellungen.modell_version)
    pseudo = conn.execute(
        "SELECT COUNT(DISTINCT track_id) FROM embeddings WHERE modell_version='pseudo'"
    ).fetchone()[0]
    werte["tracks_mit_pseudo_vektoren"] = int(pseudo)
    _log(json.dumps(werte, indent=2, ensure_ascii=False))
    conn.close()
    return 0


def kommandos_report(args: argparse.Namespace) -> int:
    from . import report

    einstellungen = config.vorbereiten(config.aus_argumenten(args))
    conn = db.verbinden(einstellungen.datenbank)
    ziel = report.schreiben(conn, einstellungen)
    _log(f"Bericht geschrieben: {ziel}")
    conn.close()
    return 0


def kommandos_all(args: argparse.Namespace) -> int:
    for schritt in (kommandos_scan, kommandos_analyze, kommandos_embed):
        ergebnis = schritt(args)
        if ergebnis != 0:
            return ergebnis
    return kommandos_status(args)


# --------------------------------------------------------------------------
# Aufbau
# --------------------------------------------------------------------------
def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="klangbild", description="Klangbild-Prototyp (Phase 0)")
    pfade = argparse.ArgumentParser(add_help=False)
    pfade.add_argument("--bibliothek", default=None, help="Pfad zur Sammlung")
    pfade.add_argument("--datenbank", default=None, help="Pfad zur SQLite-Datei")
    pfade.add_argument("--cache", default=None, help="Pfad fuer Zwischendateien")
    pfade.add_argument("--ergebnisse", default=None, help="Pfad fuer Berichte")

    unter = parser.add_subparsers(dest="befehl", required=True)

    p_scan = unter.add_parser("scan", parents=[pfade], help="Sammlung einlesen und hashen")
    p_scan.set_defaults(funktion=kommandos_scan)

    p_analyze = unter.add_parser("analyze", parents=[pfade], help="Tonart, Lautheit, Energie, Beats")
    p_analyze.add_argument("--limit", type=int, default=0)
    p_analyze.add_argument(
        "--ohne-beats", action="store_true",
        help="Bewusst ohne Schlaganalyse laufen (nur Tonart/Lautheit/Energie)."
             " Ohne diese Option bricht analyze ab, wenn beat-this fehlt.",
    )
    p_analyze.set_defaults(funktion=kommandos_analyze)

    p_embed = unter.add_parser("embed", parents=[pfade], help="Ausschnitte einbetten")
    p_embed.add_argument("--limit", type=int, default=0)
    p_embed.add_argument("--pseudo", action="store_true", help="Zufallsvektoren (nur Test)")
    p_embed.set_defaults(funktion=kommandos_embed)

    p_all = unter.add_parser("all", parents=[pfade], help="scan + analyze + embed + status")
    p_all.add_argument("--limit", type=int, default=0)
    p_all.add_argument("--pseudo", action="store_true")
    p_all.add_argument(
        "--ohne-beats", action="store_true",
        help="Wie bei analyze: bewusst ohne Schlaganalyse laufen.",
    )
    p_all.set_defaults(funktion=kommandos_all)

    p_status = unter.add_parser("status", parents=[pfade], help="Zaehler anzeigen")
    p_status.set_defaults(funktion=kommandos_status)

    p_report = unter.add_parser("report", parents=[pfade], help="Ergebnisbericht schreiben")
    p_report.set_defaults(funktion=kommandos_report)

    # Bewertung
    p_n = unter.add_parser("neighbors", parents=[pfade], help="Nachbar-Aufgaben bauen")
    p_n.add_argument("--n", type=int, default=config.TOR_01_STICHPROBE)
    p_n.add_argument("--k", type=int, default=5)
    p_n.set_defaults(funktion=None)

    p_b = unter.add_parser("baseline", parents=[pfade], help="Zufalls-Aufgaben bauen")
    p_b.add_argument("--n", type=int, default=config.TOR_01_STICHPROBE)
    p_b.add_argument("--k", type=int, default=5)
    p_b.set_defaults(funktion=None)

    p_t = unter.add_parser("text", parents=[pfade], help="Text-Anfragen bauen")
    p_t.add_argument("--queries", required=True, help="Datei mit je einer Anfrage je Zeile")
    p_t.add_argument("--k", type=int, default=5)
    p_t.set_defaults(funktion=None)

    p_u = unter.add_parser("unsinn", parents=[pfade], help="Unsinn-Anfragen (Kontrollsatz) bauen")
    p_u.add_argument("--queries", required=True)
    p_u.add_argument("--k", type=int, default=5)
    p_u.set_defaults(funktion=None)

    p_s = unter.add_parser("serve", parents=[pfade], help="Bewertungsoberflaeche im Browser")
    p_s.add_argument("--host", default="127.0.0.1")
    p_s.add_argument("--port", type=int, default=8765)
    p_s.set_defaults(funktion=None)

    p_m = unter.add_parser(
        "metronom", parents=[pfade],
        help="Phase 0.2 · Vergleichslauf auf Metronomen (Messkette ohne Fremddaten)",
    )
    p_m.set_defaults(funktion=None)

    p_k = unter.add_parser(
        "konsens", parents=[pfade],
        help="Phase 0.3 · Konsens-Pseudo-Labeling über die eigene Bibliothek",
    )
    p_k.set_defaults(funktion=None)

    p_g = unter.add_parser(
        "gold", parents=[pfade],
        help="Phase 0.4 · echtes Tonart-Tor gegen FMAK (interne Auswertung)",
    )
    p_g.add_argument(
        "--fmak-audio", default=None,
        help="Ordner mit entpackten FMAK-Audiodateien (Default: daten/fmak/audio)",
    )
    p_g.add_argument(
        "--datenordner", default=None,
        help="Ordner mit fmakv2.csv + fma_keys_index.json (Default: daten/fmak)",
    )
    p_g.add_argument(
        "--fmak-remote", action="store_true",
        help="Fehlendes Audio Track fuer Track per HTTP-Range aus der FMA-Small-ZIP holen",
    )
    p_g.add_argument(
        "--limit", type=int, default=0,
        help="Nur die ersten N Tracks auswerten (0 = alle verfuegbaren)",
    )
    p_g.set_defaults(funktion=None)

    p_p8 = unter.add_parser(
        "phase08", parents=[pfade],
        help="Phase 0.8 · skey (ML, MIT) gegen denselben FMAK-Goldsatz messen",
    )
    p_p8.add_argument(
        "--fmak-audio", default=None,
        help="Ordner mit entpackten FMAK-Audiodateien (Default: daten/fmak/audio)",
    )
    p_p8.add_argument(
        "--datenordner", default=None,
        help="Ordner mit fmakv2.csv + fma_keys_index.json (Default: daten/fmak)",
    )
    p_p8.add_argument(
        "--fmak-remote", action="store_true",
        help="Fehlendes Audio Track fuer Track per HTTP-Range aus der FMA-Small-ZIP holen",
    )
    p_p8.add_argument(
        "--limit", type=int, default=0,
        help="Nur die ersten N Tracks auswerten (0 = alle verfuegbaren)",
    )
    p_p8.set_defaults(funktion=None)

    p_p9 = unter.add_parser(
        "phase09", parents=[pfade],
        help="Phase 0.9 · Beat This! auf Tempo/Downbeat messen "
             "(n gross, Tor an der Wilson-Untergrenze)",
    )
    p_p9.add_argument(
        "--bpm-von", type=float, default=60.0,
        help="Tiefstes Tempo im Raster (Default: 60)",
    )
    p_p9.add_argument(
        "--bpm-bis", type=float, default=180.0,
        help="Hoechstes Tempo im Raster (Default: 180)",
    )
    p_p9.add_argument(
        "--bpm-stufen", type=int, default=50,
        help="Tempi im Log-Raster (Default: 50; dazu kommen feste Anker)",
    )
    p_p9.add_argument(
        "--sekunden", type=float, default=20.0,
        help="Laenge eines synthetischen Clips in Sekunden (Default: 20)",
    )
    p_p9.add_argument(
        "--limit", type=int, default=0,
        help="Nur die ersten N Faelle auswerten (0 = alle; Rauchtest)",
    )
    p_p9.set_defaults(funktion=None)

    p_p10 = unter.add_parser(
        "phase10", parents=[pfade],
        help="Phase 1.0 · Auto-DJ-Engine gegen bekannte Ground-Truth messen "
             "(Beat-Kontinuitaet, Tempo-Gate, Lautheit; Tor an der Wilson-UG)",
    )
    p_p10.add_argument(
        "--trials", type=int, default=0,
        help="Anzahl Trials (Default aus phase10.TRIALS; fuer die Wilson-UG >= 35)",
    )
    p_p10.add_argument(
        "--limit", type=int, default=0,
        help="Nur die ersten N Trials ausfuehren (0 = alle; Rauchtest)",
    )
    p_p10.set_defaults(funktion=None)

    p_mix = unter.add_parser(
        "mix", parents=[pfade],
        help="Phase 1.1 · echten Auto-DJ-Mix aus der Bibliothek rendern (Hoertest)",
    )
    p_mix.add_argument(
        "--start", type=int, default=None,
        help="Start-Track-ID (Default: groesster Tempo-Cluster = laengstes Set)",
    )
    p_mix.add_argument(
        "--laenge", type=int, default=0,
        help="Maximale Songanzahl im Set (0 = so viele das Tempo-Gate erlaubt)",
    )
    p_mix.add_argument(
        "--aus", default=None,
        help="Ziel-WAV-Datei (Default: ergebnisse/hoertest-mix.wav)",
    )
    p_mix.set_defaults(funktion=None)

    p_ht = unter.add_parser(
        "hoertest", parents=[pfade],
        help="Blinde Paare Auto-DJ vs. Shuffle rendern (Phase 1, Hoertest-Design)",
    )
    p_ht.add_argument("--paare", type=int, default=3, help="Anzahl Paare (je ein Tempo-Cluster)")
    p_ht.add_argument("--laenge", type=int, default=3, help="Songs je Set (3: A+B unter 30 min)")
    p_ht.add_argument("--seed", type=int, default=None, help="Zufall reproduzierbar machen")
    p_ht.add_argument("--aus", default=None, help="Zielordner (Default: ergebnisse/hoertest)")
    p_ht.set_defaults(funktion=None)

    p_mx = unter.add_parser("mixer", parents=[pfade],
                            help="Phase 2 · PC-DJ-Mixer: Player + Auto-DJ live im Browser")
    p_mx.add_argument("--host", default="127.0.0.1")
    p_mx.add_argument("--port", type=int, default=8766)
    p_mx.set_defaults(funktion=None)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)

    if args.befehl in {"neighbors", "baseline", "text", "unsinn", "serve"}:
        from . import evaluate

        if args.befehl == "neighbors":
            return evaluate.bauen_nachbarn(args)
        if args.befehl == "baseline":
            return evaluate.bauen_baseline(args)
        if args.befehl == "text":
            return evaluate.bauen_text(args, unsinn=False)
        if args.befehl == "unsinn":
            return evaluate.bauen_text(args, unsinn=True)
        if args.befehl == "serve":
            return evaluate.serve(args)

    if args.befehl == "metronom":
        from . import phase02

        return phase02.laufen(args)

    if args.befehl == "konsens":
        from . import phase03

        return phase03.laufen(args)

    if args.befehl == "gold":
        from . import phase04

        return phase04.laufen(args)

    if args.befehl == "phase08":
        from . import phase08

        return phase08.laufen(args)

    if args.befehl == "phase09":
        from . import phase09

        return phase09.laufen(args)

    if args.befehl == "phase10":
        from . import phase10

        return phase10.laufen(args)

    if args.befehl == "mix":
        from . import autodj

        return autodj.laufen(args)

    if args.befehl == "hoertest":
        from . import autodj

        return autodj.laufen_hoertest(args)

    if args.befehl == "mixer":
        from . import mixer

        return mixer.laufen(args)

    return int(args.funktion(args))


if __name__ == "__main__":
    sys.exit(main())
