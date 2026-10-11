"""Einstellungen des Auto-Mix (Phase 2, ADR-019: Uebergang als Daten).

Eine Dataclass mit Standardwerten, gespeichert als JSON. `aus_dict` prueft jeden
Wert gegen seine erlaubten Auswahlen/Grenzen - die Oberflaeche ist eine
Vertrauensgrenze, kaputte Werte duerfen den Mixer nicht stoppen.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

ARTEN = ("auto", "eq", "crossfade", "filter", "echo", "schnitt",
         "drums_zuerst", "acapella", "gesangsschutz")
AUSWAHL = {
    "art": ARTEN,
    "ausstieg": ("outro", "phrase", "vor_ende"),
    "einstieg": ("intro", "drop"),
    "tempo_modus": ("b_an_a", "a_an_b", "rampe"),
    "harmonie": ("streng", "locker", "aus"),
    "weiter_ab": ("takt", "phrase"),
}
TAKTE = (1, 2, 4, 8, 16, 24, 32)
GRENZEN = {"max_bpm": (0.0, 10.0), "vor_ende_takte": (1, 64)}


@dataclass
class Einstellungen:
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
