"""Phase 0.4 - Echtes Gold-Tor fuer die Tonart gegen FMAK.

Warum das (Nutzerwunsch 08.10.2026, ROADMAP Phase 0.4): Phase 0.3 misst nur die
*Uebereinstimmung zwischen Modellen* (Silber). Um zu pruefen, ob unser Weg die
Tonart *wirklich richtig* trifft, braucht es **Gold**: Labels, die von
Menschen-Expert:innen bestimmt wurden.

Der Korpus ist **FMAK** (Wong & Hernandez, ISMIR 2023): 5.489 Lieder (340 h,
17 Genres), Tonart von einem Konzertpianisten mit absolutem Gehoer bestimmt,
kreuzannotiert. Die Labels stehen unter **CC BY 4.0**, das Audio stammt aus der
Free Music Archive (Lizenz je Kuenstler gewaehlt, fuer Forschung frei).

Lizenz-Einordnung (ADR-012): Das Gate regelt die *Auslieferung*, nicht die
**interne Auswertung**. Dieser Lader laedt FMAK lokal, rechnet unsere Tonart
dagegen und notiert nur eine Trefferquote. Es wird nichts ausgeliefert, kein
GPL-Werk gebuendelt, keine Audiodatei ins Repo. Genau so arbeitet MIREX.

Datenformat (empirisch am echten Download belegt, mirdata `fma_keys.py`):
- Labels `fmakv2.csv`: Spalten `key_and_mode` (z. B. "F# Major", "Bb minor"),
  `track_id` (Integer), `spotify_uri`. Kein separates Key/Mode - wird per
  `key_and_mode.split(" ")` geparst.
- Audio-Zuordnung `fma_keys_index.json`: `track_id -> "<3 Ziffern>/<6-stellig
  zero-padded>.mp3"` + md5. Audio liegt in Zenodo-Zips je ID-Bereich; das
  Subset wird lokal erwartet (Pfad konfigurierbar).

Ohne die FMAK-Dateien bleibt der Lauf gueltig, meldet aber ehrlich, dass das
Gold-Tor nicht laufen kann (Meldung statt erfundener Zahl).
"""

from __future__ import annotations

import csv
import io
import json
import time
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from . import audioio, config, keyestimate, metrics

# Quellen (Zenodo, stabil). Labels + Index sind klein (293 kB / 622 kB).
QUELLE_LABELS = "https://zenodo.org/records/12759100/files/fmakv2.csv?download=1"
QUELLE_INDEX = ("https://zenodo.org/records/16757314/files/"
                "fma_keys_index_1.0.json?download=1")
NAME_LABELS = "fmakv2.csv"
NAME_INDEX = "fma_keys_index.json"

# FMA-Audio liegt als EINE grosse ZIP64-Datei (7,6 GB). Statt sie komplett zu
# laden, lesen wir einzelne Tracks per HTTP-Range aus der ZIP-Struktur (empirisch
# belegt 09.10.2026): die zentrale Directory-Offsets werden via Range-Requests
# gelesen, dann nur die Bytes des gewuenschten Tracks. Eintraege tragen das
# Praefix 'fma_small/'. Grosse wird per HEAD bestimmt, damit kein Hardcode
# veraltet.
FMA_AUDIO_URL = "https://os.unil.cloud.switch.ch/fma/fma_small.zip"
FMA_PRAEFIX = "fma_small/"

# FMAK nutzt Bb/Eb/... - auf die scharfe Entsprechung bringen, damit es zu den
# Camelot-Tabellen in keyestimate passt (dort A#/D#).
_BB_ZU_SHARP = {"Bb": "A#", "Eb": "D#", "Ab": "G#", "Db": "C#", "Gb": "F#"}


def _log(text: str) -> None:
    print(text, flush=True)


@dataclass(frozen=True)
class GoldTrack:
    """Ein FMAK-Track: Experten-Label plus lokal erwarteter Audio-Pfad."""

    track_id: str
    key: str            # z. B. "F#" / "Bb"
    modus: str          # "dur" | "moll"
    audio_rel: str      # z. B. "000/000010.mp3"


def _keymode_zu_camelot(key: str, modus_wort: str) -> str:
    """'F#' + 'Major' -> '2B'; 'Bb' + 'minor' -> '3A'. Leer wenn unbekannt."""
    key = _BB_ZU_SHARP.get(key, key)
    tabelle = keyestimate.CAMELOT_MINOR if modus_wort.lower() == "minor" \
        else keyestimate.CAMELOT_MAJOR
    return tabelle.get(key, "")


# --- Daten beschaffen ---------------------------------------------------------


def _hole_datei(ziel: Path, url: str) -> bool:
    """Laedt eine kleine Quelldatei, falls nicht vorhanden. True wenn vorliegt."""
    if ziel.exists() and ziel.stat().st_size > 0:
        return True
    _log(f"Lade {ziel.name} von {url} ...")
    try:
        urllib.request.urlretrieve(url, ziel)
        return ziel.exists() and ziel.stat().st_size > 0
    except OSError as fehler:
        _log(f"Download fehlgeschlagen ({fehler}). Bitte manuell nach {ziel}.")
        return False


def _lade_labels(pfad: Path) -> dict[str, tuple[str, str]]:
    """CSV -> {track_id: (key, modus_wort)}. Robust gegen Kopfzeilen-Spalten."""
    labels: dict[str, tuple[str, str]] = {}
    with pfad.open(encoding="utf-8", newline="") as f:
        for zeile in csv.DictReader(f):
            km = (zeile.get("key_and_mode") or "").strip()
            tid = (zeile.get("track_id") or "").strip()
            if not km or not tid or " " not in km:
                continue
            key, modus_wort = km.split(" ", 1)
            labels[tid] = (key.strip(), modus_wort.strip())
    return labels


def _lade_index(pfad: Path) -> dict[str, str]:
    """Index-JSON -> {track_id: audio_rel} (audio_rel = '000/000010.mp3')."""
    with pfad.open(encoding="utf-8") as f:
        roh = json.load(f)
    return {tid: next(iter(eintrag["audio"])) for tid, eintrag in roh["tracks"].items()}


# --- Remote-ZIP64-Leser (Range-Requests statt 7,6-GB-Download) -----------------


class _RemoteDatei(io.RawIOBase):
    """Eine entfernte Datei, die per HTTP-Range seekbar/lesbar ist.

    Erlaubt `zipfile.ZipFile`, die zentrale Struktur einer grossen ZIP zu lesen,
    ohne sie herunterzuladen. Nur die tatsaechlich gelesenen Bytes werden ueber
    das Netz geholt.
    """

    def __init__(self, url: str, groesse: int) -> None:
        self._url = url
        self._groesse = groesse
        self._pos = 0

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_SET:
            self._pos = offset
        elif whence == io.SEEK_CUR:
            self._pos += offset
        elif whence == io.SEEK_END:
            self._pos = self._groesse + offset
        return self._pos

    def tell(self) -> int:
        return self._pos

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            n = self._groesse - self._pos
        if n <= 0 or self._pos >= self._groesse:
            return b""
        ende = min(self._pos + n, self._groesse) - 1
        anfrage = urllib.request.Request(
            self._url, headers={"Range": f"bytes={self._pos}-{ende}"}
        )
        with urllib.request.urlopen(anfrage, timeout=120) as antwort:
            daten = antwort.read()
        self._pos += len(daten)
        return daten


_FERN_ZIP: zipfile.ZipFile | None = None


def _fern_zip() -> zipfile.ZipFile:
    """Oeffnet die grosse FMA-ZIP einmal per Range-Reader und haelt sie offen.

    Die zentrale Verzeichnisstruktur wird so nur EINMAL gelesen (nicht je Track);
    einzelne Tracks holt `_fma_audio_bytes` dann per Range.
    """
    global _FERN_ZIP
    if _FERN_ZIP is None:
        anfrage = urllib.request.Request(FMA_AUDIO_URL, method="HEAD")
        with urllib.request.urlopen(anfrage, timeout=60) as antwort:
            groesse = int(antwort.headers["Content-Length"])
        _FERN_ZIP = zipfile.ZipFile(_RemoteDatei(FMA_AUDIO_URL, groesse))
    return _FERN_ZIP


def _fma_audio_bytes(audio_rel: str) -> bytes | None:
    """Liest einen einzelnen Track ('000/000010.mp3') per Range aus der FMA-ZIP.

    None wenn der Track fehlt oder das Netz nicht mitspielt. Die ganze ZIP wird
    nie geladen - nur die Directory-Struktur und der eine Track.
    """
    ziel = FMA_PRAEFIX + audio_rel
    try:
        return _fern_zip().read(ziel)
    except (OSError, KeyError, zipfile.BadZipFile) as fehler:
        _log(f"  Audio per Range nicht lesbar ({audio_rel}): {fehler}")
        return None


_FERN_NAMEN: set[str] | None = None


def _fern_vorhanden() -> set[str]:
    """Menge der Track-Relativpfade ('000/000010.mp3'), die es in fma_small gibt.

    Die zentrale Verzeichnisstruktur wird nur EINMAL gelesen (ueber `_fern_zip`)
    und in ein Set umgewandelt. Damit filtert `_sammle_paare` schon vorab die
    ~4700 FMAK-Tracks heraus, die nicht im fma_small-Subset liegen - statt sie
    teuer per Range anzufragen und dann an einem KeyError zu scheitern.
    """
    global _FERN_NAMEN
    if _FERN_NAMEN is None:
        praefix_laenge = len(FMA_PRAEFIX)
        _FERN_NAMEN = {
            name[praefix_laenge:]
            for name in _fern_zip().namelist()
            if name.startswith(FMA_PRAEFIX) and name.endswith(".mp3")
        }
    return _FERN_NAMEN


def _finde_audio(wurzel: Path, audio_rel: str) -> Path | None:
    """Sucht die Audiodatei unter einer FMA-Ablage. None wenn nicht vorhanden.

    `audio_rel` ist 'NNN/NNNNNN.mp3'; die Datei kann direkt unter `wurzel`
    liegen (fma_small-Ablage) oder in einem Unterordner 'fma_small'.
    """
    kandidaten = (
        wurzel / audio_rel,
        wurzel / "fma_small" / audio_rel,
    )
    for k in kandidaten:
        if k.exists():
            return k
    return None


def _schreibe_cache(audio_pfad: Path, daten: bytes) -> Path:
    """Legt per Range geholte Bytes lokal ab, damit ein Lauf sie nur einmal zieht."""
    audio_pfad.parent.mkdir(parents=True, exist_ok=True)
    audio_pfad.write_bytes(daten)
    return audio_pfad



def lade_korpus(datenordner: Path) -> tuple[dict[str, tuple[str, str]], dict[str, str]] | None:
    """Stellt Labels + Index bereit (laedt bei Bedarf). None wenn nicht moeglich."""
    labels_pfad = datenordner / config.FMAK_LABELS
    index_pfad = datenordner / config.FMAK_INDEX
    if not _hole_datei(labels_pfad, QUELLE_LABELS):
        return None
    if not _hole_datei(index_pfad, QUELLE_INDEX):
        return None
    return _lade_labels(labels_pfad), _lade_index(index_pfad)


# --- Auswertung gegen Gold ----------------------------------------------------


@dataclass
class GoldVergleich:
    """Ein Track: Experten-Camelot, eigener geschaetzter Camelot, Treffer-Flags."""

    track_id: str
    gold: str
    schaetzung: str
    vertrauen: float
    exakt: bool
    nachbar: bool


def track_vergleichen(track_id: str, gold_camelot: str, signal, rate: int) -> GoldVergleich:
    """Eigenen Schaetzer gegen das Experten-Label rechnen."""
    tonart = keyestimate.tonart_schaetzen(signal, rate)
    nachbarn = keyestimate.camelot_nachbarn(gold_camelot)
    return GoldVergleich(
        track_id=track_id,
        gold=gold_camelot,
        schaetzung=tonart.camelot,
        vertrauen=tonart.vertrauen,
        exakt=tonart.camelot == gold_camelot,
        nachbar=tonart.camelot == gold_camelot or tonart.camelot in nachbarn,
    )


def _fehlerklasse(gold: str, schaetzung: str) -> str:
    """Ordnet einen Treffer/Fehler auf dem Camelot-Rad einer Klasse zu.

    'exakt'     gold == schaetzung
    'modus'     gleiche Nummer, anderer Buchstabe (relative Dur/Moll - sehr nah)
    'quint'     gleicher Buchstabe, Nummer +/-1 (Nachbar im Quintenzirkel)
    'diagonal'  Nummer +/-1 und anderer Buchstabe (nah, aber kein Camelot-Nachbar)
    'weit'      alles andere (mind. zwei Schritte weg)

    So laesst sich messen, *wo* der Schaetzer danebenliegt - statt zu raten.
    'modus'+'quint' sind genau die Faelle, die der Nachbar-Tor als Treffer zaehlt.
    """
    if gold == schaetzung:
        return "exakt"
    if len(gold) < 2 or len(schaetzung) < 2:
        return "weit"
    g_num, g_mod = gold[:-1], gold[-1]
    s_num, s_mod = schaetzung[:-1], schaetzung[-1]
    if not (g_num.isdigit() and s_num.isdigit()):
        return "weit"
    abstand = (int(g_num) - int(s_num)) % 12
    abstand = min(abstand, 12 - abstand)  # kreisfoermiger Abstand 0..6
    if abstand == 0 and g_mod != s_mod:
        return "modus"
    if abstand == 1 and g_mod == s_mod:
        return "quint"
    if abstand == 1 and g_mod != s_mod:
        return "diagonal"
    return "weit"


def auswerten(vergleiche: list[GoldVergleich]) -> dict:
    """Quoten exakt / Nachbar mit Wilson-Intervall und Tor-Entscheid (0.2-Schwelle).

    Zaehlt zusaetzlich die Fehlerklassen (exakt/modus/quint/diagonal/weit), damit
    der Bericht zeigt, *wo* der Schaetzer danebenliegt - nicht bloss wie oft.
    """
    n = len(vergleiche)
    exakt = sum(v.exakt for v in vergleiche)
    nachbar = sum(v.nachbar for v in vergleiche)
    exakt_ki = metrics.wilson(exakt, n)
    nachbar_ki = metrics.wilson(nachbar, n)
    # Tor gilt als erreicht, wenn die UNTERGRENZE des Intervalls die Schwelle packt
    # (belastbare Aussage, nicht bloss der Punktwert).
    exakt_tor = exakt_ki[0] >= config.TOR_02_TONART_EXAKT_MIN
    nachbar_tor = nachbar_ki[0] >= config.TOR_02_TONART_NACHBAR_MIN
    klassen: dict[str, int] = {}
    for v in vergleiche:
        k = _fehlerklasse(v.gold, v.schaetzung)
        klassen[k] = klassen.get(k, 0) + 1
    hart = [
        {"track_id": v.track_id, "gold": v.gold, "schaetzung": v.schaetzung,
         "klasse": _fehlerklasse(v.gold, v.schaetzung)}
        for v in vergleiche if not v.exakt
    ]
    mittel_vertrauen = sum(v.vertrauen for v in vergleiche) / n if n else 0.0
    return {
        "tracks": n,
        "exakt": {"treffer": exakt, "quote": exakt / n if n else 0.0,
                  "wilson_unten": exakt_ki[0], "wilson_oben": exakt_ki[1],
                  "tor": config.TOR_02_TONART_EXAKT_MIN, "erreicht": exakt_tor},
        "nachbar": {"treffer": nachbar, "quote": nachbar / n if n else 0.0,
                    "wilson_unten": nachbar_ki[0], "wilson_oben": nachbar_ki[1],
                    "tor": config.TOR_02_TONART_NACHBAR_MIN, "erreicht": nachbar_tor},
        "mittel_vertrauen": mittel_vertrauen,
        "klassen": klassen,
        "hart": {"gesamt": len(hart), "tracks": hart[:50]},
    }



# --- Bericht ------------------------------------------------------------------


def _bericht_schreiben(ordner: Path, z: dict, dauer: float, gesamt_verfuegbar: int) -> Path:
    nl = "\n"
    einleitung = (
        "Echter Gold-Vergleich: unsere Tonart gegen von Expert:innen bestimmte "
        "Labels (FMAK, CC BY 4.0). Interne Auswertung, nichts ausgeliefert "
        "(Lizenz-Gate ADR-012 regelt die Auslieferung)."
    )
    hinweis_tor = (
        "**Tor-Entscheid:** erfuellt, wenn die *Untergrenze* des Wilson-Intervalls "
        "die Schwelle erreicht (nicht bloss der Punktwert) - so bleibt die Aussage "
        "bei kleinem Subset belastbar."
    )

    def _zeile_ergebnis(name: str, teil: dict) -> str:
        return (
            f"| {name} | {teil['treffer']}/{z['tracks']} | "
            f"{teil['quote'] * 100:0.1f} % | "
            f"{teil['wilson_unten'] * 100:0.1f}-{teil['wilson_oben'] * 100:0.1f} % | "
            f"{teil['tor'] * 100:0.0f} % | "
            f"{'JA' if teil['erreicht'] else 'NEIN'} |"
        )

    zeilen = [
        "# Phase 0.4 - Gold-Tor Tonart gegen FMAK",
        "",
        einleitung,
        "",
        f"- Dauer: {dauer:.1f} s",
        f"- FMAK-Tracks geprueft (Label + Audio-Anforderung): {gesamt_verfuegbar}",
        f"- davon ausgewertet: {z['tracks']}",
        "",
        "## Ergebnis gegen das Phase-0.2-Tor",
        "",
        "| Kennzahl | Treffer/N | Quote | Wilson 95 % | Tor | erreicht? |",
        "|---|---|---|---|---|---|",
        _zeile_ergebnis("exakt gleich", z["exakt"]),
        _zeile_ergebnis("inkl. Camelot-Nachbar", z["nachbar"]),
        "",
        f"- mittleres Schaetzer-Vertrauen: {z['mittel_vertrauen']:.3f}",
        "",
        hinweis_tor,
        "",
    ]
    # Fehlerklassen: zeigt, WO der Schaetzer danebenliegt (nicht bloss wie oft).
    klassen = z.get("klassen") or {}
    if klassen:
        reihenfolge = ("exakt", "modus", "quint", "diagonal", "weit")
        n = z["tracks"]
        zeilen += [
            "## Fehlerklassen (wo liegt der Schaetzer daneben?)",
            "",
            "| Klasse | N | Anteil | Bedeutung |",
            "|---|---|---|---|",
        ]
        bedeutung = {
            "exakt": "Tonart exakt getroffen",
            "modus": "relative Dur/Moll-Verwechslung (gleiche Ziffer, A<->B) - sehr nah",
            "quint": "Nachbar im Quintenzirkel (gleicher Modus, Ziffer +/-1)",
            "diagonal": "Ziffer +/-1 und Modus anders (nah, aber kein Camelot-Nachbar)",
            "weit": "sonstiges (mind. zwei Schritte weg)",
        }
        for name in reihenfolge:
            anz = klassen.get(name, 0)
            zeilen.append(
                f"| {name} | {anz} | {anz / n * 100:0.1f} % | {bedeutung[name]} |"
            )
        zeilen.append("")
    if z["hart"]["gesamt"]:
        zeilen += ["## Harte Faelle (exakt daneben)", "",
                   "| Track-ID | Gold | geschaetzt |", "|---|---|---|"]
        for e in z["hart"]["tracks"][:50]:
            zeilen.append(f"| {e['track_id']} | {e['gold']} | {e['schaetzung']} |")
        zeilen.append("")
    zeilen.append(
        "> Gold ist die absolute Wahrheit (Experten). Anders als Phase 0.3 "
        "(Modelluebereinstimmung) sagt diese Zahl: *trifft unser Weg die "
        "richtige Tonart?* Fuer ein MIREX-Vergleich (Phase 0.2) ist das der "
        "fehlende Beleg.")
    zeilen.append(
        "> Jeder einzelne Track steht in `phase04-gold-tracks.csv` "
        "(track_id, gold, schaetzung, exakt, nachbar, klasse, vertrauen) "
        "- vollstaendig nachvollziehbar, nicht nur die harten Faelle.")
    p = ordner / "phase04-gold.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(nl.join(zeilen) + nl, encoding="utf-8")
    return p


def _json_schreiben(ordner: Path, z: dict) -> Path:
    p = ordner / "phase04-gold.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(z, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def _csv_schreiben(ordner: Path, vergleiche: list[GoldVergleich]) -> Path:
    """Vollstaendiger Per-Track-Export (MIREX-Stil) - ALLE Vergleiche, nicht 50.

    Der Bericht zeigt nur die ersten harten Faelle; fuer eine 100%-Nachvollziehbarkeit
    („99,9 % richtig") schreiben wir jede einzelne Zeile: Gold, eigene Schaetzung,
    Treffer-Flags, Fehlerklasse und Schaetzer-Vertrauen. Eine Zeile je Track.
    """
    p = ordner / "phase04-gold-tracks.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as f:
        schreiber = csv.writer(f)
        schreiber.writerow([
            "track_id", "gold", "schaetzung", "exakt", "nachbar",
            "klasse", "vertrauen",
        ])
        for v in vergleiche:
            schreiber.writerow([
                v.track_id, v.gold, v.schaetzung,
                int(v.exakt), int(v.nachbar),
                _fehlerklasse(v.gold, v.schaetzung),
                f"{v.vertrauen:.4f}",
            ])
    return p

# --- Ablauf -------------------------------------------------------------------


def _sammle_paare(labels, index, audio_wurzel, remote, limit):
    """Tracks mit Label + gueltigem Gold -> [(tid, gold, audio_rel, lokalpfad)].

    `lokalpfad` ist der Pfad, falls das Audio schon entpackt vorliegt, sonst None.
    Bei `remote=False` werden nur Tracks mit lokaler Datei geliefert (Default,
    ohne Netz). Bei `remote=True` auch Tracks ohne lokale Datei - deren Bytes
    holt `laufen` dann per Range. `limit` begrenzt die Zahl (schneller Testlauf).
    """
    paare: list[tuple[str, str, str, Path | None]] = []
    # Bei remote einmal prüfen, welche Tracks es im fma_small-Subset überhaupt
    # gibt, damit wir nur vorhandene anfragen (die anderen scheitern am KeyError).
    vorhanden = _fern_vorhanden() if remote else None
    for tid, (key, modus_wort) in labels.items():
        audio_rel = index.get(tid)
        if not audio_rel:
            continue
        gold = _keymode_zu_camelot(key, modus_wort)
        if not gold:
            continue
        lokalpfad = _finde_audio(audio_wurzel, audio_rel)
        if lokalpfad is None:
            if not remote:
                continue
            if audio_rel not in vorhanden:
                continue
        paare.append((tid, gold, audio_rel, lokalpfad))
        if limit and len(paare) >= limit:
            break
    return paare


def _audio_pfad_holen(tid, audio_rel, lokalpfad, audio_wurzel, remote):
    """Liefert einen dekodierbaren Pfad: lokal, sonst per Range geholt + gecacht."""
    if lokalpfad is not None:
        return lokalpfad
    if not remote:
        return None
    daten = _fma_audio_bytes(audio_rel)
    if daten is None:
        return None
    return _schreibe_cache(audio_wurzel / audio_rel, daten)


def laufen(args) -> int:
    """Gold-Tor gegen FMAK laufen lassen (Labels/Index werden bei Bedarf geladen).

    Audio kommt entweder lokal (--fmak-audio, entpackte fma_small) oder, mit
    --fmak-remote, Track fuer Track per HTTP-Range aus der FMA-Small-ZIP (nur die
    benoetigten Bytes, zentrales Verzeichnis einmal gelesen). Gecacht wird unter
    <audio>/... damit ein Lauf dieselbe Datei nicht zweimal zieht.
    """
    einstellungen = config.vorbereiten(config.aus_argumenten(args))
    datenordner = Path(getattr(args, "datenordner", None) or (config.DATEN / "fmak"))
    audio_wurzel = Path(getattr(args, "fmak_audio", None) or (config.DATEN / "fmak" / "audio"))
    remote = bool(getattr(args, "fmak_remote", False))
    limit = int(getattr(args, "limit", 0) or 0)
    ordner = einstellungen.ergebnisse

    korpus = lade_korpus(datenordner)
    if korpus is None:
        _log("FMAK-Labels/Index nicht verfuegbar (Download fehlgeschlagen?).")
        return 2
    labels, index = korpus

    paare = _sammle_paare(labels, index, audio_wurzel, remote, limit)
    gesamt = len(paare)
    if gesamt == 0:
        _log("Keine passenden FMAK-Tracks gefunden.")
        _log(f"Labels+Index liegen bereit ({len(labels)} Labels, {len(index)} Pfade).")
        _log("Lokales Audio: fma_small.zip nach <--fmak-audio> entpacken,")
        _log(f"oder on demand holen mit --fmak-remote (Cache unter {audio_wurzel}).")
        return 1

    modus_text = "lokal + per Range" if remote else "lokal"
    _log(f"Werte {gesamt} FMAK-Tracks aus ({modus_text}) ...")
    start = time.time()
    vergleiche: list[GoldVergleich] = []
    for i, (tid, gold, audio_rel, lokalpfad) in enumerate(paare, 1):
        audio_pfad = _audio_pfad_holen(tid, audio_rel, lokalpfad, audio_wurzel, remote)
        if audio_pfad is None:
            continue
        try:
            audio = audioio.decodieren(audio_pfad, config.ABTASTRATE_ANALYSE)
        except Exception as fehler:  # noqa: BLE001 - ein kaputter Track stoppt nicht
            _log(f"  uebersprungen ({tid}): {fehler}")
            continue
        vergleiche.append(track_vergleichen(tid, gold, audio.daten, audio.rate))
        if i % 50 == 0 or i == gesamt:
            _log(f"  {i}/{gesamt} ...")
    dauer = time.time() - start

    z = auswerten(vergleiche)
    _json_schreiben(ordner, z)
    csv_pfad = _csv_schreiben(ordner, vergleiche)
    bericht = _bericht_schreiben(ordner, z, dauer, gesamt)
    _log(f"Exakt:   {z['exakt']['quote'] * 100:0.1f} % "
         f"({z['exakt']['treffer']}/{z['tracks']}) -> "
         f"Tor {'erreicht' if z['exakt']['erreicht'] else 'NICHT erreicht'}")
    _log(f"Nachbar: {z['nachbar']['quote'] * 100:0.1f} % "
         f"({z['nachbar']['treffer']}/{z['tracks']}) -> "
         f"Tor {'erreicht' if z['nachbar']['erreicht'] else 'NICHT erreicht'}")
    _log(f"JSON: {ordner / 'phase04-gold.json'}")
    _log(f"CSV (alle {len(vergleiche)} Tracks): {csv_pfad}")
    _log(f"Bericht: {bericht}")
    return 0


