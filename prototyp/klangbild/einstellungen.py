"""Einstellungen des Auto-Mix (Phase 2, ADR-019: Uebergang als Daten).

Eine Dataclass mit Standardwerten, gespeichert als JSON. `aus_dict` prueft jeden
Wert gegen seine erlaubten Auswahlen/Grenzen - die Oberflaeche ist eine
Vertrauensgrenze, kaputte Werte duerfen den Mixer nicht stoppen.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path

ARTEN = ("auto", "eigen", "eq", "crossfade", "filter", "echo", "schnitt",
         "drums_zuerst", "acapella", "gesangsschutz", "gesang_zuerst", "double_drop")
# Bausteine der Art "eigen" (wie im DJ.Studio-Transition-Editor kombinierbar):
LAUTSTAERKE = ("nahtlos", "linear", "ueberlappung", "hart_ein", "hart_aus", "hart_beide",
               "mitte", "frueh", "spaet", "letzter_takt", "drop", "doppel", "mitte_weich")
EQ = ("keiner", "profi", "bass_mitte", "bass_anfang", "bass_ende", "drei_band", "bass_schnell", "bass_lang",
      "bass_takt")
FILTER = ("keiner", "tp_aus", "tp_ein", "tp_beide", "hp_aus", "hp_ein", "hp_beide",
          "tp_ein_hp_aus", "hp_ein_tp_aus", "hp_aus_reso", "tp_aus_reso")   # _reso: resonanter Sweep
EFFEKT_TYPEN = ("hall", "echo50", "echo75", "echo100", "delay50", "delay75", "delay100", "pingpong50", "pingpong75")
EFFEKT_MODI = ("mitte_aus", "ende_ab", "ende_aus")   # deaktivieren (Mitte) / abschneiden / deaktivieren (Ende)
EFFEKT = ("keiner",) + tuple(f"{t}_{m}" for t in EFFEKT_TYPEN for m in EFFEKT_MODI)
EFFEKT_EIN = ("keiner", "hall", "rueckhall")   # rueckhall: Reverse-Reverb schwillt in B's Einsatz
LOOP = ("keiner", "auto", "1", "2", "4", "8", "16", "32", "rolle")
# DJ-Tricks auf dem ausgehenden Song (Recherche DnB/Club-DJs): Tape-Stop, Backspin, Noise-Riser, Flanger,
# Teaser = B blitzt auf dem letzten Schlag der Takte vor dem Drop auf (Crossfader-Cuts)
TRICK = ("keiner", "bremse", "spinback", "riser", "flanger", "teaser", "phaser", "gate", "crush", "wechsel")
# wechsel = Drop-Cuts: ab dem gemeinsamen Drop (gesang_takt) taktweise A/B hin und her, die letzten 2 Takte B
# gate = Trans (A zerhackt in Achteln, im letzten Takt in Sechzehnteln), crush = Bitcrusher
EXPERIMENTE = ("klassisch", "kreativ", "wild")
MODI = ("manuell", "kurz", "ausgewogen", "lang")
AUSWAHL = {
    "modus": MODI,
    "spielanteil": ("schnell", "lang"),
    "art": ARTEN,
    "lautstaerke": LAUTSTAERKE,
    "eq": EQ,
    "filter": FILTER,
    "effekt": EFFEKT,
    "effekt_ein": EFFEKT_EIN,
    "loop": LOOP,
    "trick": TRICK,
    "experimente": EXPERIMENTE,
    "ausstieg": ("outro", "phrase", "vor_ende"),
    "einstieg": ("intro", "drop"),
    "tempo_modus": ("b_an_a", "a_an_b", "rampe"),
    "harmonie": ("streng", "locker", "aus"),
    "weiter_ab": ("takt", "phrase"),
    "stems_vorrat": ("aus", "upload", "alle"),
}
TAKTE = (1, 2, 4, 8, 16, 24, 32)
GRENZEN = {"max_bpm": (0.0, 10.0), "vor_ende_takte": (1, 64), "bass_takt": (-1, 32),
           "loop_start": (-1, 64), "loop_ein": (0, 16), "loop_ein_mal": (0, 8), "gesang_takt": (-1, 96)}


@dataclass
class Einstellungen:
    # Auto-DJ V2: ausser "manuell" waehlt die Regie (regie.py) alle Uebergangs-Felder je Paar
    modus: str = "ausgewogen"    # manuell / kurz / ausgewogen / lang (Mix-Stil)
    spielanteil: str = "lang"    # schnell: Wechsel nach dem Drop der 2. Haelfte; lang: bis zum Ende
    experimente: str = "klassisch"   # klassisch / kreativ / wild: wie oft die Regie Double Drops und Tricks nimmt
    takte: int = 16              # Blendenlaenge in Takten
    art: str = "auto"            # Uebergangsart (siehe ARTEN)
    ausstieg: str = "outro"      # wo A die Blende beginnt
    vor_ende_takte: int = 16     # fuer ausstieg="vor_ende"
    einstieg: str = "intro"      # ab wo B einsetzt
    tempo_modus: str = "rampe"   # wie die Tempi angeglichen werden
    max_bpm: float = 5.0         # groesster erlaubter Tempo-Angleich in BPM
    keylock: bool = True         # Tonhoehe halten beim Dehnen
    harmonie: str = "locker"     # Tonart beim Sortieren
    weiter_takte: int = 8        # Blende nach "Weiter"
    weiter_ab: str = "phrase"    # "Weiter" startet am naechsten Takt/Phrase
    lautheit: bool = True        # Pegel je Song auf -14 LUFS
    stems: bool = True           # Stem-Trennung (Demucs) fuer Auto/Stem-Uebergaenge
    stems_vorrat: str = "alle"  # Stems vorab: aus / Uploads + Warteschlange / ganze Bibliothek
    # Art "eigen": je Kategorie ein Baustein (siehe Auswahllisten oben)
    lautstaerke: str = "nahtlos"
    eq: str = "bass_mitte"
    filter: str = "keiner"
    effekt: str = "keiner"       # auf dem ausgehenden Song
    effekt_ein: str = "keiner"   # auf dem eingehenden Song
    loop: str = "keiner"         # Loop des ausgehenden Songs, Groesse in Schlaegen
    trick: str = "keiner"        # DJ-Trick (siehe TRICK)
    bass_takt: int = -1          # Takt des Bass-Tauschs bei EQ "profi" (-1 = Mitte; setzt die Regie)
    loop_start: int = -1         # Takt in der Blende, ab dem A loopt (-1 = Blendenbeginn)
    loop_ein: int = 0            # Intro-Loop von B: Laenge in Takten (0 = aus; setzt die Regie)
    loop_ein_mal: int = 0        # ... so oft zusaetzlich wiederholt
    gesang_takt: int = -1        # Stem-Gesangsuebergabe: Takt der Uebergabe (-1 = fest; setzt die Regie)


def regie_einst(e: Einstellungen) -> Einstellungen | None:
    """Einstellungen fuer die Regie (Auto-DJ V2) oder None, wenn der Nutzer alles selbst vorgibt.

    "Automatisch" als Uebergangsart ist auch im Stil "Manuell" die Regie (Stil ausgewogen):
    die alte Festregel (EQ/Echo/Schnitt) kennt weder Loops noch Effekte.
    """
    if e.modus != "manuell":
        return e
    return replace(e, modus="ausgewogen") if e.art == "auto" else None


def aus_dict(roh: dict, basis: Einstellungen | None = None) -> Einstellungen:
    """Uebernimmt nur gueltige Werte; Unbekanntes und Ungueltiges wird ignoriert."""
    e = basis or Einstellungen()
    werte = asdict(e)
    for f in fields(Einstellungen):
        if f.name not in roh:
            continue
        v = roh[f.name]
        try:
            if f.name in AUSWAHL:
                if v in AUSWAHL[f.name]:
                    werte[f.name] = v
            elif f.name in ("takte", "weiter_takte"):
                if int(v) in TAKTE:
                    werte[f.name] = int(v)
            elif f.name in GRENZEN:
                lo, hi = GRENZEN[f.name]
                werte[f.name] = type(lo)(min(max(float(v), lo), hi))
            elif isinstance(werte[f.name], bool):
                werte[f.name] = bool(v)
        except (TypeError, ValueError):
            continue
    return Einstellungen(**werte)


def laden(pfad: Path) -> Einstellungen:
    try:
        return aus_dict(json.loads(pfad.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return Einstellungen()


def speichern(pfad: Path, e: Einstellungen) -> None:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(asdict(e), indent=2), encoding="utf-8")
