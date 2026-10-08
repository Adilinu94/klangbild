"""Phase 0.2 · Vergleichslauf fuer Tempo, Beats und Downbeats – ohne fremde Daten.

Warum synthetisch (und nicht Harmonix/GTZAN/GiantSteps): Recherche 08.10.2026
zeigt, dass keiner der drei Datensaetze fuer eine geschlossene App **Lizenz-freies
Audio mit Takt-Labels** liefert – Harmonix nur Mel-Spektren, GTZAN nur Genre bei
umstrittener Herkunft, GiantSteps-Audio sind kommerzielle Beatport-Ausschnitte.
Einen Lader dagegen zu bauen wuerde das eigene Lizenz-Gate (ADR-012) brechen.

Was hier trotzdem geprueft wird: die **Messkette**. Ein Metronom mit bekannter
Ground-Truth zeigt, ob Beat-F1, BPM-Oktavtoleranz und Downbeat innerhalb +-1 Takt
die richtigen Zahlen liefern. Faellt das auf perfekt bekannten Signalen schon
durch, liegt der Fehler in unserer Kette, nicht in den Daten. Die Tonart-Treffer-
quote gegen echte Musik bleibt – wie in der Roadmap vermerkt – an ein Lizenz-freies
Referenz-Korpus gebunden; dieses Modul liefert dafuer nur das Geruest.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import beats, config, metrics


def _log(text: str) -> None:
    print(text, flush=True)


@dataclass(frozen=True)
class Metronom:
    """Ein synthetischer Klick-Track mit bekannter Ground-Truth."""

    bpm: float
    takt: int                 # Schlaege pro Takt (4/4-Takt -> takt=4)
    sekunden: float
    rate: int
    beats: np.ndarray         # Soll-Schlagzeiten
    downbeats: np.ndarray     # Soll-Taktanfaenge

    @property
    def beat_periode(self) -> float:
        return 60.0 / self.bpm

    @property
    def signal(self) -> np.ndarray:
        """Klick-Spur: jeder Schlag ein kurzer Impuls, Taktanfaenge etwas lauter."""
        anzahl = int(self.sekunden * self.rate)
        signal = np.zeros(anzahl, dtype=np.float32)
        for index, zeit in enumerate(self.beats):
            start = int(zeit * self.rate)
            if start >= anzahl:
                break
            laenge = min(int(0.05 * self.rate), anzahl - start)
            huell = np.exp(-np.arange(laenge) / (0.008 * self.rate))
            betont = 1.0 if index % self.takt == 0 else 0.6
            signal[start:start + laenge] += betont * huell
        return np.clip(signal, -1.0, 1.0)


# Tempi, die der Auto-DJ realistischerweise sieht (von langsam bis schnell).
TEMPI = (70.0, 90.0, 100.0, 120.0, 128.0, 140.0, 174.0)


def baue_metronome(tempi: tuple[float, ...] = TEMPI, takt: int = 4,
                   sekunden: float = 30.0,
                   rate: int = config.ABTASTRATE_ANALYSE) -> list[Metronom]:
    """Baut fuer jedes Tempo ein Metronom mit Soll-Beats und Soll-Downbeats."""
    liste: list[Metronom] = []
    for bpm in tempi:
        periode = 60.0 / bpm
        soll_beats = np.arange(0.0, sekunden, periode)
        soll_downbeats = soll_beats[::takt]
        liste.append(
            Metronom(bpm=bpm, takt=takt, sekunden=sekunden, rate=rate,
                     beats=soll_beats, downbeats=soll_downbeats)
        )
    return liste


def _ein_metronom_bewerten(metro: Metronom, schlag: beats.SchlagAnalyse | None) -> dict:
    """Bewertet ein Metronom gegen die eigene Schaetzung (oder ohne Modell)."""
    if schlag is None or not schlag.verfuegbar:
        return {"bpm": metro.bpm, "hat_beats": False}
    beat_periode = metro.beat_periode
    geschaetztes_bpm = metrics.bpm_aus_beats(schlag.beats)
    return {
        "bpm": metro.bpm,
        "hat_beats": True,
        "beat_f1": round(metrics.beat_f1(metro.beats, schlag.beats), 4),
        "bpm_geschätzt": round(geschaetztes_bpm, 2),
        "bpm_richtig": bool(metrics.bpm_richtig(metro.bpm, geschaetztes_bpm,
                                                 config.TOR_02_BPM_TOLERANZ)),
        "downbeat_richtig": bool(metrics.downbeat_richtig(
            metro.downbeats, schlag.downbeats, beat_periode, config.TOR_02_DOWNBEAT_TAKTE
        )),
    }


def _quote(zaehler: int, gesamt: int) -> dict:
    unten, oben = metrics.wilson(zaehler, gesamt)
    return {"zaehler": zaehler, "gesamt": gesamt,
            "quote": (zaehler / gesamt) if gesamt else 0.0,
            "wilson_unten": unten, "wilson_oben": oben}


def auswerten(metronome: list[Metronom], ergebnisse: list[dict]) -> dict:
    """Fasst die Einzelergebnisse zu Quoten mit Wilson-Intervall zusammen."""
    mit_beats = [e for e in ergebnisse if e.get("hat_beats")]
    n = len(mit_beats)
    bpm_ok = sum(1 for e in mit_beats if e["bpm_richtig"])
    downbeat_ok = sum(1 for e in mit_beats if e["downbeat_richtig"])
    f1 = [e["beat_f1"] for e in mit_beats]
    return {
        "tempi": [m.bpm for m in metronome],
        "anzahl_metronome": len(metronome),
        "anzahl_mit_beats": n,
        "bpm": _quote(bpm_ok, n),
        "downbeat": _quote(downbeat_ok, n),
        "beat_f1_mittel": round(sum(f1) / len(f1), 4) if f1 else 0.0,
        "tor_bpm_erfuellt": (bpm_ok / n >= config.TOR_02_BPM_MIN) if n else False,
        "tor_downbeat_erfuellt": (downbeat_ok / n >= config.TOR_02_DOWNBEAT_MIN) if n else False,
    }


def _tor_text(erfuellt: bool, gemessen: bool) -> str:
    """Ehrliche Tor-Formulierung: ohne Messung ist das Tor *offen*, nicht gescheitert."""
    if not gemessen:
        return "OFFEN (Modell fehlt)"
    return "ERFUELLT" if erfuellt else "NICHT ERFUELLT"


def laufen(args: argparse.Namespace) -> int:
    einstellungen = config.vorbereiten(config.aus_argumenten(args))
    metronome = baue_metronome()
    _log(f"Phase 0.2 · Vergleichslauf ueber {len(metronome)} Metronome "
         f"(BPM {', '.join(str(int(m.bpm)) for m in metronome)})")

    modell_da = beats.verfuegbar()
    if not modell_da:
        _log("Hinweis: beat-this fehlt – nur die Messkette ohne Modell pruefbar. "
             "Fuer den echten Lauf: python -m pip install beat-this")

    ergebnisse: list[dict] = []
    beginn = time.time()
    for metro in metronome:
        schlag = None
        if modell_da:
            try:
                schlag = beats.analysieren_signal(metro.signal)
            except Exception as fehler:  # noqa: BLE001 - ein Tempo darf scheitern
                _log(f"  Beat-Fehler bei {int(metro.bpm)} BPM: {fehler}")
        zeile = _ein_metronom_bewerten(metro, schlag)
        ergebnisse.append(zeile)
        status = ""
        if zeile.get("hat_beats"):
            status = (f"F1 {zeile['beat_f1']:.2f} · BPM {zeile['bpm_geschätzt']:.0f}"
                      f" ({'ok' if zeile['bpm_richtig'] else 'x'}) · "
                      f"Downbeat {'ok' if zeile['downbeat_richtig'] else 'x'}")
        _log(f"  {int(metro.bpm):>3} BPM · {status or 'keine Beats'}")

    bericht = auswerten(metronome, ergebnisse)
    bericht["modell_vorhanden"] = modell_da
    bericht["dauer_s"] = round(time.time() - beginn, 2)
    bericht["grenzen"] = {
        "bpm_min": config.TOR_02_BPM_MIN,
        "bpm_toleranz": config.TOR_02_BPM_TOLERANZ,
        "downbeat_min": config.TOR_02_DOWNBEAT_MIN,
        "downbeat_takte": config.TOR_02_DOWNBEAT_TAKTE,
    }

    json_pfad = einstellungen.ergebnisse / "phase02-metronom.json"
    json_pfad.parent.mkdir(parents=True, exist_ok=True)
    json_pfad.write_text(json.dumps({"zusammenfassung": bericht, "einzel": ergebnisse},
                                    indent=2, ensure_ascii=False), encoding="utf-8")
    md_pfad = _bericht_schreiben(einstellungen.ergebnisse, bericht, ergebnisse)
    _log(f"JSON: {json_pfad}")
    _log(f"Bericht: {md_pfad}")
    gemessen = bericht["anzahl_mit_beats"] > 0
    _log(f"Tor Tempo: {_tor_text(bericht['tor_bpm_erfuellt'], gemessen)} · "
         f"Tor Downbeat: {_tor_text(bericht['tor_downbeat_erfuellt'], gemessen)}")
    return 0


def _quote_zeile(name: str, block: dict) -> str:
    return (f"| {name} | {block['gesamt']} | {block['quote'] * 100:0.1f} % "
            f"| {block['wilson_unten'] * 100:0.1f}–{block['wilson_oben'] * 100:0.1f} % |")


def _bericht_schreiben(ordner: Path, bericht: dict, einzel: list[dict]) -> Path:
    z = ordner / "phase02-bericht.md"
    z.parent.mkdir(parents=True, exist_ok=True)
    zeilen = ["# Phase 0.2 · Metronom-Vergleichslauf\n"]
    zeilen.append("Synthetische Ground-Truth, ohne fremde Datensaetze (Lizenz-Gate, ADR-012). "
                  "Prueft die Messkette: Beat-F1, BPM mit Oktavtoleranz, Downbeat innerhalb "
                  "+-1 Takt.\n")
    zeilen.append(f"- Modell (beat-this): **{'vorhanden' if bericht['modell_vorhanden'] else 'fehlt'}**")
    zeilen.append(f"- Dauer: {bericht['dauer_s']} s")
    zeilen.append(f"- Tempi: {', '.join(str(int(t)) for t in bericht['tempi'])}\n")
    zeilen.append("## Ergebnisse\n")
    zeilen.append("| Kennzahl | n | Trefferquote | Wilson 95 % |")
    zeilen.append("|---|---|---|---|")
    zeilen.append(_quote_zeile("BPM (Oktavtoleranz)", bericht["bpm"]))
    zeilen.append(_quote_zeile("Downbeat (+-1 Takt)", bericht["downbeat"]))
    zeilen.append(f"\n- Beat-F1 im Mittel: **{bericht['beat_f1_mittel']:.2f}**")
    gemessen = bericht["anzahl_mit_beats"] > 0
    zeilen.append(f"- Tor Tempo (>= {bericht['grenzen']['bpm_min'] * 100:0.0f} %): "
                  f"**{_tor_text(bericht['tor_bpm_erfuellt'], gemessen)}**")
    zeilen.append(f"- Tor Downbeat (>= {bericht['grenzen']['downbeat_min'] * 100:0.0f} %): "
                  f"**{_tor_text(bericht['tor_downbeat_erfuellt'], gemessen)}**\n")
    if not gemessen:
        zeilen.append("> Hinweis: beat-this fehlt, daher liegen keine Messwerte vor. "
                      "Die Tore sind **offen**, nicht gescheitert. Für den echten Lauf: "
                      "`python -m pip install beat-this` (zieht torch nach).\n")
    zeilen.append("## Einzelwerte\n")
    zeilen.append("| BPM | Beat-F1 | BPM geschaetzt | BPM ok | Downbeat ok |")
    zeilen.append("|---|---|---|---|---|")
    for e in einzel:
        if not e.get("hat_beats"):
            zeilen.append(f"| {e['bpm']:.0f} | – | – | – | – |")
        else:
            zeilen.append(f"| {e['bpm']:.0f} | {e['beat_f1']:.2f} | {e['bpm_geschätzt']:.1f} "
                          f"| {'ja' if e['bpm_richtig'] else 'nein'} "
                          f"| {'ja' if e['downbeat_richtig'] else 'nein'} |")
    zeilen.append("\n> Die Tonart-Trefferquote gegen echte Musik bleibt an ein Lizenz-freies "
                  "Referenz-Korpus gebunden (siehe ROADMAP Phase 0.2). Dieses Modul deckt "
                  "nur den Tempo/Beat/Downbeat-Teil der Kette ab.")
    z.write_text("\n".join(zeilen) + "\n", encoding="utf-8")
    return z


