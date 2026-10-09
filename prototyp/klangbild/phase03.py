"""Phase 0.3 - Konsens-Pseudo-Labeling auf der eigenen Bibliothek.

Warum das (Recherche 08.10.2026, ROADMAP-KLANGBILD.md Phase 0.2): Die drei
klassischen Referenzdatensaetze liefern fuer eine **geschlossene** App kein
lizenzfreies Audio mit Tonart-/Takt-Labels (Harmonix nur Mel-Spektren ohne
Tonart, GTZAN nur Genre, GiantSteps-Audio kommerzielle Beatport-Ausschnitte).
Ein Lader dagegen bliebe am Lizenz-Gate (ADR-012) haengen.

Statt blockierter Fremddaten nutzen wir die **eigene** Sammlung: mehrere
methodisch **verschiedene**, freie Modelle schaetzen dieselbe Datei unabhaengig.
Wo sie sich einig sind, entsteht ein belastbares Silber-Label; wo sie
abweichen, sind genau die harten Faelle, die Phase 0.2 sucht. Das ist die
etablierte **Weak-Supervision**-Methode ohne Gold-Labels.

Lizenz-Einschaetzung (ADR-012, Gate regelt die *Auslieferung*, nicht die interne
Auswertung): Interne Auswertung/Kalibrierung auf eigenen Dateien verletzt das
Gate nicht. Pseudo-Labels ("8A") sind Fakten, kein urheberrechtlich geschuetzter
Inhalt; es wird kein Audio ausgeliefert und kein GPL-Werk gebuendelt.

Alle Schwer-Werkzeuge sind **faul** eingebunden: fehlen torch/librosa/av, laufen
Tests und Bericht trotzdem - der fehlende Schaetzer wird einfach uebersprungen
und im Bericht vermerkt. Genau das Muster wie `embeddings.py`/`beats.py`.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from . import audioio, config, keyestimate, metrics


@dataclass(frozen=True)
class Schaetzung:
    """Ein einzelnes Modell-Ergebnis als Camelot-Code plus Modus."""

    camelot: str          # z. B. "8A" / "11B"
    modus: str            # "dur" | "moll"
    quelle: str           # Modellname
    vertrauen: float = 0.0


@dataclass
class Konsens:
    """Ergebnis des Vergleichs aller verfuegbaren Schaetzer fuer einen Track."""

    pfad: str
    schaetzungen: list[Schaetzung]

    @property
    def anzahl(self) -> int:
        return len(self.schaetzungen)

    def _codes(self) -> list[str]:
        return [s.camelot for s in self.schaetzungen]

    def mehrheit(self) -> tuple[str | None, int]:
        """Haeufigster Camelot-Code und wie viele dafuer stimmen."""
        if not self.schaetzungen:
            return None, 0
        codes = self._codes()
        return max(set(codes), key=codes.count), max(codes.count(c) for c in set(codes))

    def einig_streng(self) -> bool:
        """Alle Schaetzer liefern **exakt** denselben Camelot-Code."""
        return self.anzahl > 0 and len(set(self._codes())) == 1

    def einig_nachbar(self) -> bool:
        """Alle Codes liegen innerhalb der Camelot-Nachbarschaft des Mehrheits-Codes."""
        if self.anzahl == 0:
            return False
        if self.anzahl == 1:
            return True
        code, _ = self.mehrheit()
        nachbarn = keyestimate.camelot_nachbarn(code)
        return all(c in nachbarn for c in self._codes())


# --- verfuegbare Schaetzer (faul eingebunden) --------------------------------


def schaetzer_eigen(signal, rate: int) -> Schaetzung | None:
    """Unser eigener Chroma+Profil-Schaetzer (immer verfuegbar, reines numpy)."""
    tonart: keyestimate.Tonart = keyestimate.tonart_schaetzen(signal, rate)
    modus = "moll" if tonart.name.endswith("m") else "dur"
    return Schaetzung(
        camelot=tonart.camelot, modus=modus, quelle="eigen/chroma",
        vertrauen=tonart.vertrauen,
    )


def schaetzer_skey(signal, rate: int) -> Schaetzung | None:
    """deezer/skey (MIT, selbstueberwacht). Optional: nur wenn importierbar.

    Schnittstelle je Version unterschiedlich; hier defensiv. Fehlt skey, ist das
    kein Fehler - der Schaetzer wird einfach uebersprungen.
    """
    try:
        import skey  # type: ignore
    except Exception:  # noqa: BLE001 - optional
        return None
    try:
        ergebnis = skey.predict(signal, rate)  # schnittstelle je version
        name = str(getattr(ergebnis, "key", ergebnis))
        modus = "moll" if "minor" in name.lower() or name.strip().endswith("m") else "dur"
        return Schaetzung(camelot=_tonartname_zu_camelot(name), modus=modus,
                          quelle="skey")
    except Exception:  # noqa: BLE001 - schnittstelle variiert, dann ueberspringen
        return None


def schaetzer_openkeyscan(signal, rate: int) -> Schaetzung | None:
    """rekordcloud/openkeyscan (MIT, CNN nach Korzeniowski). Optional.

    Liefert bereits Camelot/Open-Key. Fehlt das Werkzeug, wird uebersprungen.
    """
    try:
        import openkeyscan_analyzer  # type: ignore
    except Exception:  # noqa: BLE001 - optional
        return None
    try:
        ergebnis = openkeyscan_analyzer.analyze(signal, rate)  # schnittstelle je version
        code = str(ergebnis.get("camelot") or ergebnis.get("openkey"))
        modus = "moll" if code.strip().endswith("A") else "dur"
        return Schaetzung(camelot=code, modus=modus, quelle="openkeyscan")
    except Exception:  # noqa: BLE001
        return None


# Camelot-Tabellen aus keyestimate wiederverwerten (Name -> Code).
_NUMMER_MAJOR = keyestimate.CAMELOT_MAJOR
_NUMMER_MINOR = keyestimate.CAMELOT_MINOR


def _tonartname_zu_camelot(name: str) -> str:
    """Tonartname ("A", "F#m", "A minor", "C major") -> Camelot-Code ("8A", ...)."""
    text = name.strip()
    moll = "minor" in text.lower() or (text.endswith("m") and len(text) > 1)
    text = text.replace("major", "").replace("minor", "").strip()
    if text.endswith("m") and len(text) > 1:
        text = text[:-1].strip()
    tabelle = _NUMMER_MINOR if moll else _NUMMER_MAJOR
    return tabelle.get(text.title(), "")


def verfuegbare_schaetzer() -> list:
    """Nur die Schaetzer, deren Abhaengigkeit gerade importierbar ist.

    Unser eigener ist immer dabei; skey/openkeyscan nur, wenn ihre Pakete
    vorhanden sind. So bleibt der Lauf ohne torch/librosa lauffaehig.
    """
    import os
    import sys

    gefunden = [schaetzer_eigen]
    gespraechig = os.environ.get("KLANGBILD_VERBOSE") == "1"
    for modulname, fn in (("skey", schaetzer_skey),
                          ("openkeyscan_analyzer", schaetzer_openkeyscan)):
        try:
            __import__(modulname)
            gefunden.append(fn)
        except Exception:  # noqa: BLE001 - optional, fehlend ist okay und schweigt
            if gespraechig:
                print(f"phase03: optionaler Schaetzer '{modulname}' nicht verfuegbar",
                      file=sys.stderr)
    return gefunden



# --- Auswertung --------------------------------------------------------------


def _quote_block(zaehler: int, gesamt: int) -> dict:
    quote = zaehler / gesamt if gesamt else 0.0
    unten, oben = metrics.wilson(zaehler, gesamt)
    return {
        "quote": quote,
        "wilson_unten": unten,
        "wilson_oben": oben,
        "gesamt": gesamt,     # Stichprobengroesse (Nenner), wie in report.py
        "treffer": zaehler,   # wie oft erfuellt (Zaehler)
    }


def auswerten(konsense: list[Konsens]) -> dict:
    """Fasst alle Track-Konsense zu einer Bibliotheks-Aussage zusammen.

    Gemessen wird die **Uebereinstimmung zwischen Modellen** (kein Gold-Tor):
    Wie oft sind alle aktiven Modelle einig (streng / Nachbar), und wie oft
    weichen sie ab (die harten Faelle). Jeder Wert mit Wilson-Intervall.
    """
    mehrfach = [k for k in konsense if k.anzahl >= 2]
    einstimmig_streng = [k for k in mehrfach if k.einig_streng()]
    einstimmig_nachbar = [k for k in mehrfach if k.einig_nachbar()]
    ein_quellen = [k for k in konsense if k.anzahl == 1]
    # Harte Faelle: mehrere Modelle, aber nicht einmal Nachbarschafts-Einigkeit.
    hart = [k for k in mehrfach if not k.einig_nachbar()]

    gesamt = len(konsense)
    n = len(mehrfach)
    return {
        "tracks_gesamt": gesamt,
        "tracks_mehrere_schaetzer": n,
        "tracks_nur_eigener": len(ein_quellen),
        "einig_streng": _quote_block(len(einstimmig_streng), n),
        "einig_nachbar": _quote_block(len(einstimmig_nachbar), n),
        "hart": _quote_block(len(hart), n),
        "schwierige_tracks": [
            {"pfad": k.pfad, "codes": [s.camelot for s in k.schaetzungen]}
            for k in hart
        ],
        "aktive_schaetzer": sorted(
            {s.quelle for k in konsense for s in k.schaetzungen}
        ),
    }


def track_konsensieren(pfad: str | Path, signal, rate: int,
                       schaetzer: list | None = None) -> Konsens:
    """Laeesst alle verfuegbaren Schaetzer ueber ein bereits dekodiertes Signal."""
    schaetzer = schaetzer or verfuegbare_schaetzer()
    ergebnisse: list[Schaetzung] = []
    for fn in schaetzer:
        schaetzung = fn(signal, rate)
        if schaetzung is not None and schaetzung.camelot:
            ergebnisse.append(schaetzung)
    return Konsens(pfad=str(pfad), schaetzungen=ergebnisse)



# --- Ausgabe -----------------------------------------------------------------


def _bericht_schreiben(ordner: Path, zusammen: dict, dauer_s: float) -> Path:
    z = ordner / "phase03-konsens.md"
    z.parent.mkdir(parents=True, exist_ok=True)
    nl = "\n"
    zeilen = ["# Phase 0.3 - Konsens-Pseudo-Labeling (eigene Bibliothek)", ""]
    zeilen.append(
        "Uebereinstimmung **zwischen** freien Modellen (kein Gold-Tor, "
        "Lizenz-Gate ADR-012). Wo Modelle einig sind, entsteht ein belastbares "
        "Silber-Label; Abweichungen sind die harten Faelle fuer Phase 0.2.")
    zeilen.append("")
    zeilen.append(f"- Dauer: {dauer_s:0.1f} s")
    zeilen.append(f"- Aktive Schaetzer: {', '.join(zusammen['aktive_schaetzer']) or 'keine'}")
    zeilen.append("")
    zeilen.append("## Umfang")
    zeilen.append("")
    zeilen.append("| Groesse | Zahl |")
    zeilen.append("|---|---|")
    zeilen.append(f"| Tracks gesamt | {zusammen['tracks_gesamt']} |")
    zeilen.append(f"| davon mehrere Schaetzer | {zusammen['tracks_mehrere_schaetzer']} |")
    zeilen.append(f"| davon nur eigener Schaetzer | {zusammen['tracks_nur_eigener']} |")
    zeilen.append("")
    zeilen.append("## Uebereinstimmung (nur Tracks mit >= 2 Schaetzern)")
    zeilen.append("")
    zeilen.append("| Kennzahl | Treffer/N | Anteil | Wilson 95 % |")
    zeilen.append("|---|---|---|---|")
    for schluessel, titel in (
        ("einig_streng", "alle exakt gleich"),
        ("einig_nachbar", "alle im Camelot-Umfeld"),
        ("hart", "darueber hinaus unstimmig"),
    ):
        block = zusammen[schluessel]
        zeilen.append(
            f"| {titel} | {block['treffer']}/{block['gesamt']} "
            f"| {block['quote'] * 100:0.1f} % "
            f"| {block['wilson_unten'] * 100:0.1f}-{block['wilson_oben'] * 100:0.1f} % |")
    if zusammen["schwierige_tracks"]:
        zeilen.append("")
        zeilen.append("## Harte Faelle (Modelle uneinig)")
        zeilen.append("")
        zeilen.append("| Track | Codes |")
        zeilen.append("|---|---|")
        for eintrag in zusammen["schwierige_tracks"][:50]:
            name = Path(eintrag["pfad"]).name
            zeilen.append(f"| {name} | {', '.join(eintrag['codes'])} |")
    zeilen.append("")
    zeilen.append(
        "> Hinweis: Silber- ist nicht Gold-Labeling. Der Wert misst die "
        "*Uebereinstimmung der Modelle*, nicht die absolute Wahrheit. Fuer ein "
        "echtes MIREX-Tor braucht es weiterhin einen belegten, freien Korpus "
        "(ROADMAP Phase 0.2).")
    z.write_text(nl.join(zeilen) + nl, encoding="utf-8")
    return z


def _json_schreiben(ordner: Path, zusammen: dict) -> Path:
    z = ordner / "phase03-konsens.json"
    z.parent.mkdir(parents=True, exist_ok=True)
    z.write_text(json.dumps(zusammen, ensure_ascii=False, indent=2), encoding="utf-8")
    return z


def _sammle_dateien(quelle: Path) -> list[Path]:
    if quelle.is_file():
        return [quelle]
    dateien: list[Path] = []
    for endung in config.AUDIO_ENDUNGEN:
        dateien.extend(sorted(quelle.rglob(f"*{endung}")))
    return dateien


def laufen(args) -> int:
    """Konsens ueber die gescannte Bibliothek laufen lassen.

    Jeder Track wird frisch dekodiert und von allen verfuegbaren Schaetzern
    bewertet. Ohne schwere Abhaengigkeiten bleibt der Lauf gueltig (dann nur mit
    dem eigenen Schaetzer), und der Bericht sagt das offen.
    """
    einstellungen = config.vorbereiten(config.aus_argumenten(args))
    quelle = einstellungen.bibliothek
    ordner = einstellungen.ergebnisse

    def _log(text: str) -> None:
        print(text)

    schaetzer = verfuegbare_schaetzer()
    _log(f"Aktive Schaetzer: {len(schaetzer)} "
         f"({', '.join(f.__name__ for f in schaetzer)})")
    if len(schaetzer) < 2:
        _log("Hinweis: Nur der eigene Schaetzer verfuegbar. Fuer Konsens braucht "
             "es >= 2. Optional installieren, z. B.:\\n"
             "  python -m pip install torch && "
             "pip install git+https://github.com/deezer/skey")

    if not quelle.exists():
        _log(f"Sammlung nicht gefunden: {quelle}")
        return 2
    dateien = _sammle_dateien(quelle)
    if not dateien:
        _log("Keine Audiodateien gefunden.")
        return 1

    start = time.time()
    konsense: list[Konsens] = []
    for i, pfad in enumerate(dateien, 1):
        try:
            audio = audioio.decodieren(pfad, config.ABTASTRATE_ANALYSE)
        except Exception as fehler:  # noqa: BLE001 - ein kaputter Track stoppt nicht
            _log(f"  uebersprungen ({pfad.name}): {fehler}")
            continue
        konsense.append(track_konsensieren(pfad, audio.daten, audio.rate, schaetzer))
        if i % 50 == 0 or i == len(dateien):
            _log(f"  {i}/{len(dateien)} Tracks ...")
    dauer = time.time() - start

    zusammen = auswerten(konsense)
    _json_schreiben(ordner, zusammen)
    bericht = _bericht_schreiben(ordner, zusammen, dauer)
    n = zusammen["tracks_mehrere_schaetzer"]
    if n:
        _log(f"Einigung streng: {zusammen['einig_streng']['quote'] * 100:0.1f} % "
             f"({zusammen['einig_streng']['gesamt']}/{n})")
        _log(f"Einigung Nachbar: {zusammen['einig_nachbar']['quote'] * 100:0.1f} % "
             f"({zusammen['einig_nachbar']['gesamt']}/{n})")
        _log(f"Harte Faelle: {zusammen['hart']['gesamt']}")
    _log(f"JSON: {ordner / 'phase03-konsens.json'}")
    _log(f"Bericht: {bericht}")
    return 0

