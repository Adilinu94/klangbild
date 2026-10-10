"""Gemeinsame Einstellungen des Prototyps.

Alles, was ein Tor beeinflusst, steht hier – nicht verstreut im Code. Wer einen
Wert aendert, aendert das Tor und muss das im Ergebnisbericht vermerken.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJEKT_WURZEL = Path(__file__).resolve().parents[2]
PROTOTYP_WURZEL = Path(__file__).resolve().parents[1]


def _pfad_aus_umgebung(name: str, vorgabe: Path) -> Path:
    wert = os.environ.get(name)
    return Path(wert) if wert else vorgabe


# --- Sammlung ---------------------------------------------------------------
BIBLIOTHEK: Path = _pfad_aus_umgebung(
    "KLANGBILD_BIBLIOTHEK", Path(r"D:\Music\Chill")
)
AUDIO_ENDUNGEN = {".mp3", ".flac", ".wav", ".m4a", ".aac", ".ogg", ".opus"}

# --- Ablage -----------------------------------------------------------------
ERGEBNISSE: Path = _pfad_aus_umgebung("KLANGBILD_ERGEBNISSE", PROTOTYP_WURZEL / "ergebnisse")
CACHE: Path = _pfad_aus_umgebung("KLANGBILD_CACHE", PROTOTYP_WURZEL / "cache")
DATEN: Path = _pfad_aus_umgebung("KLANGBILD_DATEN", PROTOTYP_WURZEL / "daten")
DATENBANK: Path = ERGEBNISSE / "klangbild.db"

# --- Analyse-Parameter (ADR-012) --------------------------------------------
ABTASTRATE_ANALYSE = 22050   # mono 22,05 kHz: Vorgabe von Beat This!
ABTASTRATE_EINBETTUNG = 16000  # mono 16 kHz: Vorgabe von EmbeddingGemma 2
ABTASTRATE_HOERTEST = 44100   # Hoertest-Render in Originalqualitaet (statt 22,05 kHz)
AUSSCHNITTE = ("anfang", "mitte", "ende")
AUSSCHNITT_SEKUNDEN = 20.0
MIN_SEKUNDEN = 25.0          # darunter wird ein Track nicht ausgewertet

# --- Einbettung (ADR-015) ---------------------------------------------------
EINBETTUNG_MODELL = "google/embeddinggemma-2"
EINBETTUNG_DIM = 256          # MRL-Kuerzung, danach wird neu normalisiert
EINBETTUNG_TRAINIERTEXT_PRAEFIX = "SentenceSimilarity"
# Nur Text- und Audio-Encoder laden: 570 M statt 740 M Parameter.
EINBETTUNG_DEAKTIVIERTE_ENCODER = {"vision_config": None}

# --- Versionierung ----------------------------------------------------------
ANALYSE_VERSION = "0.3.0"    # wechselt das Verfahren, wird ALLES neu gerechnet (0.3.0: BPM per Regression ueber alle Beats)
MODELL_VERSION = "embeddinggemma-2/256d@2026-10-08"

# --- Lautheit ---------------------------------------------------------------
LUFS_ZIEL = -14.0
TRUE_PEAK_GRENZE = -1.0

# --- Tore (ROADMAP-KLANGBILD.md, festgelegt 08.10.2026) --------------------
TOR_01_NACHBARN_UNFALL_MAX = 0.05      # hoechstens 5 % "Unfall"
TOR_01_NACHBARN_UEBER_BASELINE = 0.10  # mindestens 10 Prozentpunkte ueber Zufall
TOR_01_TEXT_PASST = 0.60               # 60 % "passt/geht" bei sinnvollen Anfragen
TOR_01_TEXT_UNSINN_MAX = 0.20          # hoechstens 20 % bei Unsinn
TOR_01_STICHPROBE = 20                 # Aufgaben je Kategorie
TOR_02_BPM_TOLERANZ = 0.04             # +-4 %
TOR_02_BPM_MIN = 0.90
TOR_02_DOWNBEAT_TAKTE = 1              # +-1 Takt
TOR_02_DOWNBEAT_MIN = 0.80
# Phase 0.9: Mischgenauigkeit. +-4 % prueft nur "richtiges Tempo"; Beatmatching
# braucht ~+-0,1 % (1 % laeuft ueber 8 Takte ~150 ms auseinander, ADR-014).
TOR_09_BPM_PRAEZISION = 0.001          # +-0,1 %
TOR_09_BPM_PRAEZISION_MIN = 0.90
TOR_02_TONART_EXAKT_MIN = 0.50
TOR_02_TONART_NACHBAR_MIN = 0.70

# --- Gold-Tor Tonart (ROADMAP Phase 0.4, FMAK) -----------------------------
# Untergrenze des Wilson-Intervalls muss das Tor erreichen (nicht bloss der
# Mittelwert), damit die Aussage bei kleinem Subset belastbar bleibt.
FMAK_LABELS = "fmakv2.csv"             # FMAKv2-Expertenlabels (CC BY 4.0)
FMAK_INDEX = "fma_keys_index.json"     # track_id -> Audio-Pfad + md5
FMAK_AUDIOZIP = "https://os.unil.cloud.switch.ch/fma/fma_small.zip"

# --- Beat This! (Phase 0.2/0.9) --------------------------------------------
# beat_this laedt seinen Checkpoint per Kurznamen (\"final0\") selbst ueber
# torch.hub. Das scheitert hier still: der Download startet, wird aber nicht
# abgeschlossen, und beat_this wirft je Track erneut \"Could not load the
# checkpoint\". Ein Kurzname ist daher keine belastbare Quelle.
# Darum: ein **lokaler Pfad**, der vorrangig benutzt wird (liegt auf G:, wie die
# uebrigen Modelle - C: bleibt frei). Nur wenn er fehlt, faellt beats.py auf den
# Kurznamen zurueck und meldet das als Modell-fehlt statt still 0 Beats zu liefern.
BEAT_THIS_CHECKPOINT: Path = _pfad_aus_umgebung(
    "KLANGBILD_BEAT_CKPT",
    DATEN / "modelle" / "torchhub" / "checkpoints" / "beat_this-final0.ckpt",
)


# --- Planer (Phase 1, Auto-DJ, ROADMAP Phase 1 / Architektur Abschnitt 4) ------
# Gewichte der Uebergangsnote. Kein Tor, nur Verhalten - deshalb hier sichtbar.
# Tempo ist KEIN Gewicht, sondern ein hartes Gate (resample.tempo_passt, ADR-020).
PLANER_GEWICHT_HARMONIE = 0.40   # Camelot: exakt / Nachbar / fremd
PLANER_GEWICHT_KLANG = 0.35      # Klang-Vektor: Kosinus-Aehnlichkeit (0..1)
PLANER_GEWICHT_ENERGIE = 0.25    # Energie-Reise: grosse Spruenge bestrafen
PLANER_HARMONIE_EXAKT = 1.0
PLANER_HARMONIE_NACHBAR = 0.6
PLANER_HARMONIE_FREMD = 0.0
# Ab diesem Lautstaerke-Sprung (dBFS, mittlere Energie) ist die Energie-Note 0.
PLANER_ENERGIE_MAX_SPRUNG_DB = 12.0
# Crossfade-Laenge in Takten (ADR-014 nennt 8 oder 16).
PLANER_BLENDE_TAKTE = 16

# Phase 1.0 (phase10): Vorab-Tore der Auto-DJ-Engine gegen bekannte Ground-Truth.
# Kontinuitaet = Anteil Sets, deren Beat-Raster im ganzen Mix nicht galoppiert
# (Variationskoeffizient der Onset-Abstaende <= phase10.TOR_GALOPP_CV_MAX).
TOR_10_KONTINUITAET_MIN = 0.90
# Tempo-Gate = Anteil Sets, in denen jeder geplante Uebergang innerhalb +-1 % des
# Master-Takts bleibt (ADR-020). In diesem Vorab-Lauf sind alle Tempi absichtlich
# innerhalb +-1 %, damit das Gate trifft - der Lauf prueft Resampling und
# Ausrichtung, nicht die Gate-Logik (die ist in test_plan.py unit-getestet).
TOR_10_GATE_MIN = 0.90
# Lautheit = Anteil Sets innerhalb +-0,5 dB von -14 LUFS UND True Peak <= -1 dBTP.
TOR_10_LAUTHEIT_MIN = 0.90


@dataclass(frozen=True)
class Einstellungen:
    bibliothek: Path = BIBLIOTHEK
    ergebnisse: Path = ERGEBNISSE
    cache: Path = CACHE
    datenbank: Path = DATENBANK
    analyse_version: str = ANALYSE_VERSION
    modell_version: str = MODELL_VERSION
    zusatz: dict = field(default_factory=dict)


def vorbereiten(einstellungen: Einstellungen | None = None) -> Einstellungen:
    """Legt die Ablageordnung an und liefert die gueltigen Pfade zurueck."""
    e = einstellungen or Einstellungen()
    e.ergebnisse.mkdir(parents=True, exist_ok=True)
    e.cache.mkdir(parents=True, exist_ok=True)
    return e


def aus_argumenten(args) -> Einstellungen:
    """Baut Einstellungen aus Kommandozeilen-Argumenten (Pfade ueberschreibbar).

    Damit laufen Tests und mehrere Sammlungen nebeneinander, ohne dass etwas im
    Projektordner liegen bleibt.
    """
    def wert(name: str, vorgabe: Path) -> Path:
        roh = getattr(args, name, None)
        return Path(roh) if roh else vorgabe

    ergebnisse = wert("ergebnisse", ERGEBNISSE)
    datenbank = wert("datenbank", ergebnisse / "klangbild.db")
    return Einstellungen(
        bibliothek=wert("bibliothek", BIBLIOTHEK),
        ergebnisse=ergebnisse,
        cache=wert("cache", CACHE),
        datenbank=datenbank,
    )
