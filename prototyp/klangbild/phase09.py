"""Phase 0.9 · Beat This! auf Tempo/Beat/Downbeat messen – n gross genug fuer ein Tor.

Warum Phase 0.2 kein tragfaehiges Tor liefern konnte
-----------------------------------------------------
Phase 0.2 mass Beat-F1, BPM und Downbeat an **7** Metronomen. Sieben Faelle sind
kein Tor: 7/7 Treffer ergeben eine Wilson-Untergrenze von **64,6 %** – die
Aussage „erfuellt" haengt dann am Punktwert, nicht an der Belastbarkeit. Genau
davor warnt `metrics.wilson` („bei 20 Faellen ist ein Fehler 5 Punkte").
Diese Phase nimmt denselben Satz, aber so gross, dass die Untergrenze traegt.

Was dazukommt gegenueber Phase 0.2
----------------------------------
1. **n**: 6 Taktarten × ein **logarithmisches** Tempo-Raster mit festen Ankern
   (60-180 BPM). Tempo-Verwechslung ist eine Oktavfrage (60 vs 120) - im
   Log-Raum liegen die gleich weit weg, in einem linearen faellt 120 zwischen
   die Stufen. Auf CPU ~0,7 s/Clip, der Lauf liegt bei wenigen Minuten.
2. **Taktarten** (3/4, 4/4, 5/4, 6/8, 7/8, 9/8): Downbeat ist taktabhaengig.
   Wer nur 4/4 prueft, prueft den leichtesten Fall und haelt ihn fuer das Ganze.
3. **Tor auf der Wilson-Untergrenze** wie Phase 0.4/0.8 – nicht auf dem Punktwert.

Was das NICHT ist
-----------------
Ein **Metronom ist der leichteste Fall**: starres Tempo, ein Klang, kein Groove.
Diese Zahlen belegen, dass die Messkette *und* das Modell auf bekannten Signalen
richtig liegen – nicht, dass Beat This! auf echter Musik 90 % trifft. Fuer echtes
Musik-Gold braucht es ein lizenzfreies Korpus mit Beat-Labels; das ist fuer Tempo
genauso offen wie fuer Tonart (Lizenz-Gate ADR-012, siehe Phase 0.2). Dieser Lauf
schliesst die Kette, nicht das Produkt.

Alles Wiederverwendete (Ground-Truth-Bau, `beat_f1`, `bpm_richtig`,
`downbeat_richtig`, `wilson`) kommt aus `phase02`/`metrics` – die Zahlen sind
untereinander vergleichbar, nur n und die Taktarten wachsen.
"""

from __future__ import annotations

import csv
import json
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import beats, config, metrics
from .phase02 import TEMPI, Metronom, baue_metronome


def _log(text: str) -> None:
    print(text, flush=True)


# Taktarten: Schlaege pro Takt. 4/4 ist der Normalfall, der Rest ist die Stelle,
# an der Downbeat-Erkennung tatsaechlich arbeiten muss.
TAKTARTEN = (4, 3, 6, 5, 7, 9)


@dataclass(frozen=True)
class Fall:
    """Ein pruefbarer Fall: synthetisches Signal mit bekannter Ground-Truth."""

    name: str           # z. B. \"4/4 @ 128\"
    takt: int
    bpm: float
    metro: Metronom

    @property
    def signal(self) -> np.ndarray:
        return self.metro.signal


def baue_faelle(tempi: tuple[float, ...], taktarten: tuple[int, ...] = TAKTARTEN,
                sekunden: float = 20.0,
                rate: int = config.ABTASTRATE_ANALYSE) -> list[Fall]:
    """Jede Taktart × jedes Tempo = ein Fall mit bekannter Ground-Truth."""
    faelle: list[Fall] = []
    for takt in taktarten:
        metronome = baue_metronome(tempi=tempi, takt=takt, sekunden=sekunden,
                                   rate=rate)
        for metro in metronome:
            faelle.append(Fall(name=f"{takt}/4 @ {metro.bpm:.0f}", takt=takt,
                               bpm=metro.bpm, metro=metro))
    return faelle


def _faelle_bewerten(faelle: list[Fall], modell_da: bool) -> list[dict]:
    """Jeden Fall messen. Ein kaputter Fall stoppt nicht den Lauf.

    Genau wie Phase 0.2/0.4: ein Fehler wird gezaehlt, nicht geschluckt –
    sonst wuerde ein stiller Totalausfall wie „alles bestanden" aussehen.
    """
    ergebnisse: list[dict] = []
    for index, fall in enumerate(faelle, 1):
        schlag = None
        fehler = None
        if modell_da:
            try:
                schlag = beats.analysieren_signal(fall.signal)
            except Exception as ausnahme:  # noqa: BLE001 - ein Fall darf scheitern
                fehler = f"{type(ausnahme).__name__}: {ausnahme}"
        hat_beats = schlag is not None and schlag.verfuegbar
        zeile: dict = {"fall": fall.name, "takt": fall.takt, "bpm_soll": fall.bpm}
        if not hat_beats:
            zeile["hat_beats"] = False
            if fehler:
                zeile["fehler"] = fehler
            ergebnisse.append(zeile)
        else:
            periode = 60.0 / fall.bpm
            geschaetzt = metrics.bpm_aus_beats(schlag.beats)
            zeile.update({
                "hat_beats": True,
                "beat_f1": round(metrics.beat_f1(fall.metro.beats, schlag.beats), 4),
                "bpm_geschaetzt": round(geschaetzt, 2),
                "bpm_richtig": bool(metrics.bpm_richtig(
                    fall.bpm, geschaetzt, config.TOR_02_BPM_TOLERANZ)),
                "bpm_praezise": bool(metrics.bpm_richtig(
                    fall.bpm, geschaetzt, config.TOR_09_BPM_PRAEZISION)),
                "downbeat_richtig": bool(metrics.downbeat_richtig(
                    fall.metro.downbeats, schlag.downbeats, periode,
                    config.TOR_02_DOWNBEAT_TAKTE)),
            })
            if fehler:
                zeile["fehler"] = fehler
            ergebnisse.append(zeile)
        if index % 25 == 0 or index == len(faelle):
            _log(f"  {index}/{len(faelle)} ...")
    return ergebnisse


def _tor(zaehler: int, gesamt: int, schwelle: float) -> dict:
    """Quote + Wilson-Intervall + **Entscheidung an der Untergrenze**.

    Phase 0.2 entschied am Punktwert (`zaehler/n >= schwelle`). Das ist der
    Fehler, den diese Phase korrigiert: bei n=7 ist 7/7 „bestanden", die
    Untergrenze liegt aber bei 64,6 % – die Aussage haengt dann am Zufall.
    Hier zaehlt allein `wilson_unten >= schwelle`, wie in Phase 0.4/0.8.
    """
    unten, oben = metrics.wilson(zaehler, gesamt)
    return {
        "zaehler": zaehler,
        "gesamt": gesamt,
        "quote": (zaehler / gesamt) if gesamt else 0.0,
        "wilson_unten": unten,
        "wilson_oben": oben,
        "schwelle": schwelle,
        "erreicht": bool(gesamt and unten >= schwelle),
        # Punktwert nur zur Information – er entscheidet nicht mehr.
        "punktwert_erreicht": bool(gesamt and zaehler / gesamt >= schwelle),
    }


def auswerten(faelle: list[Fall], ergebnisse: list[dict]) -> dict:
    """Quoten je Kennzahl, aufgeschluesselt nach Taktart."""
    mit_beats = [e for e in ergebnisse if e.get("hat_beats")]
    n = len(mit_beats)
    bpm_ok = sum(1 for e in mit_beats if e["bpm_richtig"])
    praezise_ok = sum(1 for e in mit_beats if e.get("bpm_praezise"))
    downbeat_ok = sum(1 for e in mit_beats if e["downbeat_richtig"])
    f1 = [e["beat_f1"] for e in mit_beats]

    je_takt: dict[int, dict] = {}
    for takt in sorted({f.takt for f in faelle}):
        teil = [e for e in mit_beats if e["takt"] == takt]
        je_takt[str(takt)] = {
            "gesamt": len(teil),
            "bpm_ok": sum(1 for e in teil if e["bpm_richtig"]),
            "downbeat_ok": sum(1 for e in teil if e["downbeat_richtig"]),
            "beat_f1_mittel": (round(sum(e["beat_f1"] for e in teil) / len(teil), 4)
                               if teil else 0.0),
        }

    return {
        "anzahl_faelle": len(faelle),
        "anzahl_mit_beats": n,
        "bpm": _tor(bpm_ok, n, config.TOR_02_BPM_MIN),
        "bpm_praezision": _tor(praezise_ok, n, config.TOR_09_BPM_PRAEZISION_MIN),
        "downbeat": _tor(downbeat_ok, n, config.TOR_02_DOWNBEAT_MIN),
        "beat_f1_mittel": round(sum(f1) / len(f1), 4) if f1 else 0.0,
        "je_takt": je_takt,
    }


# --- Ausgabe ----------------------------------------------------------------


def _tor_zeile(text: str, t: dict) -> str:
    return (f"| {text} | {t['zaehler']}/{t['gesamt']} "
            f"| {t['quote'] * 100:0.1f} % | {t['wilson_unten'] * 100:0.1f}-"
            f"{t['wilson_oben'] * 100:0.1f} % | "
            f"{'erfuellt' if t['erreicht'] else 'nicht erfuellt'} |")


def _bericht_schreiben(ordner: Path, z: dict, dauer: float) -> Path:
    nl = "\n"
    zeilen = [
        "# Phase 0.9 - Beat This! auf Tempo/Beat/Downbeat (n gross, Tor an der Untergrenze)",
        "",
        "Interner Messlauf, nichts ausgeliefert (Lizenz-Gate ADR-012).",
        "",
        "**Warum diese Phase existiert:** Phase 0.2 hatte nur **7** Metronome. Sieben",
        "Faelle sind kein Tor - 7/7 Treffer ergeben eine Wilson-Untergrenze von 64,6 %,",
        "die Aussage haengt dann am Punktwert statt an der Belastbarkeit. Dieser Lauf",
        "nimmt dieselbe Messkette, aber mit n gross genug, dass die Untergrenze traegt,",
        "und mit mehreren Taktarten (Downbeat ist taktabhaengig).",
        "",
        f"- Faelle: {z['anzahl_faelle']} (davon mit Beats: {z['anzahl_mit_beats']})",
        f"- Dauer: {dauer:0.1f} s",
        "",
        "## Ergebnis gegen die Phase-0.2-Tore",
        "",
        "Tor entscheidet an der **Untergrenze** des Wilson-Intervalls, nicht am Punktwert.",
        "",
        "| Kennzahl | Treffer/N | Quote | Wilson 95 % | erreicht? |",
        "|---|---|---|---|---|",
    ]
    zeilen.append(_tor_zeile(
        f"Tempo richtig (+-{config.TOR_02_BPM_TOLERANZ * 100:0.0f} %)", z["bpm"]))
    zeilen.append(_tor_zeile(
        f"Tempo mischgenau (+-{config.TOR_09_BPM_PRAEZISION * 100:0.1f} %)",
        z["bpm_praezision"]))
    zeilen.append(_tor_zeile(
        f"Downbeat richtig (+-{config.TOR_02_DOWNBEAT_TAKTE} Takt)", z["downbeat"]))
    zeilen.append("")
    zeilen.append(f"- mittlere Beat-F1: {z['beat_f1_mittel']:0.3f}")
    zeilen.append("")
    if z["je_takt"]:
        zeilen.append("## Nach Taktart (wo liegt Beat This! daneben?)")
        zeilen.append("")
        zeilen.append("| Takt | Faelle | Tempo ok | Downbeat ok | Beat-F1 |")
        zeilen.append("|---|---|---|---|---|")
        for takt, t in z["je_takt"].items():
            zeilen.append(f"| {takt}/4 | {t['gesamt']} | {t['bpm_ok']} "
                          f"| {t['downbeat_ok']} | {t['beat_f1_mittel']:0.3f} |")
        zeilen.append("")
    zeilen.append(
        "> **Was diese Zahlen nicht belegen:** ein Metronom ist der leichteste Fall "
        "(starres Tempo, ein Klang, kein Groove). Sie zeigen, dass Messkette *und* "
        "Modell auf bekannten Signalen richtig liegen - nicht, dass Beat This! auf "
        "echter Musik so trifft. Echtes Musik-Gold mit Beat-Labels braucht ein "
        "lizenzfreies Korpus (offen wie fuer Tonart, Lizenz-Gate ADR-012).")
    zeilen.append("")
    zeilen.append("> Jeder Fall steht in `phase09-beats-tracks.csv`.")
    p = ordner / "phase09-beats.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(nl.join(zeilen) + nl, encoding="utf-8")
    return p


def _json_schreiben(ordner: Path, z: dict) -> Path:
    p = ordner / "phase09-beats.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(z, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def _csv_schreiben(ordner: Path, ergebnisse: list[dict]) -> Path:
    """Vollstaendiger Per-Fall-Export - wie Phase 0.4/0.8, jede Zeile nachvollziehbar."""
    p = ordner / "phase09-beats-tracks.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    felder = ["fall", "takt", "bpm_soll", "hat_beats", "beat_f1",
              "bpm_geschaetzt", "bpm_richtig", "bpm_praezise", "downbeat_richtig",
              "fehler"]
    with p.open("w", encoding="utf-8", newline="") as f:
        schreiber = csv.DictWriter(f, fieldnames=felder, extrasaction="ignore")
        schreiber.writeheader()
        for e in ergebnisse:
            schreiber.writerow(e)
    return p


# --- Ablauf -----------------------------------------------------------------


def _tempi_aus_args(args) -> tuple[float, ...]:
    """Tempo-Raster: logarithmisch verteilt, plus feste Anker im Bereich.

    **Warum nicht einfach gleichmaessig?** Ein lineares Raster von 60 bis 180
    trifft die charakteristischen Tempi nicht: 120 faellt zwischen zwei Stufen
    (…118, 122,45…). Damit waeren genau die Halb-/Doppel-Tempo-Fallen - 60 gegen
    120, 90 gegen 180, die haeufigste Verwechslung ueberhaupt - *zwischen* den
    Messpunkten. Ein Raster, das die schwierigen Faelle ausspart, kann sie nicht
    finden.

    Darum: logarithmische Verteilung (im Tempo messen Oktaven, also
    Vielfache - im Log-Raum sind die gleich weit weg) **und** die Anker aus
    `phase02.TEMPI` sowie typische DJ-Tempi explizit dazugenommen. Zusammen
    ergeben sich mit den 6 Taktarten einige hundert Faelle.
    """
    von = float(getattr(args, "bpm_von", 0) or 60.0)
    bis = float(getattr(args, "bpm_bis", 0) or 180.0)
    anzahl = max(int(getattr(args, "bpm_stufen", 0) or 50), 2)
    if bis <= von:
        return (von,)

    # Log-Raster: gleicher *relativer* Abstand (Oktavlogik).
    raster = [von * (bis / von) ** (i / (anzahl - 1)) for i in range(anzahl)]

    # Anker dazunehmen - die Tempi, an denen sich Tempo-Verwechslung zeigt.
    anker = list(TEMPI) + [70.0, 75.0, 80.0, 96.0, 100.0, 105.0, 110.0,
                           132.0, 135.0, 145.0, 150.0, 160.0]
    raster += [bpm for bpm in anker if von <= bpm <= bis]

    # Aufrunden und entdoppeln (log-Werte landen sonst knapp neben den Ankern).
    bereinigt = sorted({round(bpm, 2) for bpm in raster})
    return tuple(bereinigt)


def laufen(args) -> int:
    einstellungen = config.vorbereiten(config.aus_argumenten(args))
    ordner = einstellungen.ergebnisse

    if not beats.verfuegbar():
        # Ehrlich: ohne Modell ist das Tor OFFEN, nicht gescheitert (wie Phase 0.2).
        _log("Phase 0.9 · beat-this fehlt - Tor bleibt OFFEN (nicht gescheitert).")
        _log(f"Erwarteter Checkpoint: {config.BEAT_THIS_CHECKPOINT}")
        _log("Ueberschreiben mit KLANGBILD_BEAT_CKPT=<pfad>.")
        return 2

    tempi = _tempi_aus_args(args)
    sekunden = float(getattr(args, "sekunden", 0) or 20.0)
    faelle = baue_faelle(tempi=tempi, sekunden=sekunden)
    limit = int(getattr(args, "limit", 0) or 0)
    if limit and limit < len(faelle):
        _log(f"  (Rauchtest: nur die ersten {limit} von {len(faelle)} Faellen)")
        faelle = faelle[:limit]
    _log(f"Phase 0.9 · {len(faelle)} Faelle "
         f"({len(TAKTARTEN)} Taktarten x {len(tempi)} Tempi, {sekunden:0.0f} s/Clip)")

    beginn = time.time()
    ergebnisse = _faelle_bewerten(faelle, modell_da=True)
    dauer = time.time() - beginn

    z = auswerten(faelle, ergebnisse)
    z["dauer_s"] = round(dauer, 2)
    z["grenzen"] = {
        "bpm_min": config.TOR_02_BPM_MIN,
        "bpm_toleranz": config.TOR_02_BPM_TOLERANZ,
        "bpm_praezision": config.TOR_09_BPM_PRAEZISION,
        "bpm_praezision_min": config.TOR_09_BPM_PRAEZISION_MIN,
        "downbeat_min": config.TOR_02_DOWNBEAT_MIN,
        "downbeat_takte": config.TOR_02_DOWNBEAT_TAKTE,
    }

    for name, t in (("Tempo", z["bpm"]), ("Tempo mischgenau", z["bpm_praezision"]),
                    ("Downbeat", z["downbeat"])):
        _log(f"  {name}: {t['quote'] * 100:0.1f} % ({t['zaehler']}/{t['gesamt']}) "
             f"UG {t['wilson_unten'] * 100:0.1f} % -> "
             f"{'Tor erreicht' if t['erreicht'] else 'Tor NICHT erreicht'}")
    _log(f"  Beat-F1 Mittel: {z['beat_f1_mittel']:0.3f}")

    _json_schreiben(ordner, z)
    _csv_schreiben(ordner, ergebnisse)
    _bericht_schreiben(ordner, z, dauer)
    _log(f"JSON:   {ordner / 'phase09-beats.json'}")
    _log(f"CSV:    {ordner / 'phase09-beats-tracks.csv'}")
    _log(f"Bericht: {ordner / 'phase09-beats.md'}")
    return 0

