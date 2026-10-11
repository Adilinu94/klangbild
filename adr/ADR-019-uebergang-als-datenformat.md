# ADR-019 · Übergänge als Datenformat statt fest im Renderer

**Status:** angenommen (11.10.2026: mit den einstellbaren Übergangsarten gibt es jetzt sechs Rezepte)
**Datum:** 10.10.2026
**Ergänzt:** ADR-014, ADR-017

## Kontext

Heute steckt genau ein Rezept fest in `prototyp/klangbild/mix.py`: EQ-Blend mit
Bass-Tausch. Geplant sind die Rezepte R1–R11 und S1–S8, ein Editor wie bei
Spotify Mix und dieselben Übergänge auf PC und Android. Wenn jedes Rezept Code
ist, muss jede Änderung zweimal geschrieben werden (Python und C++), und der
Editor kann nichts speichern.

## Entscheidung (Vorschlag)

Ein Übergang ist ein **Datensatz** (JSON-Format aus
`WISSEN-DJ-TECHNIKEN-UND-REPOS.md` §6). Er enthält die Cue-Punkte, die Länge in
Takten, das Tempo-Verhalten und je Spur (Original oder Stem) Hüllkurven für
Pegel, EQ und Filter auf dem Taktraster. **Ein** Renderer setzt den Datensatz
um, auf beiden Plattformen gleich. Planer und Editor ändern nur Daten.

## Alternativen

1. **Rezepte als Code.** Für ein Rezept heute in Ordnung, ab dem zweiten
   doppelte Arbeit.
2. **Datenformat.** Vorgeschlagen.

## Konsequenzen

- Erst einführen, wenn das zweite Rezept kommt. Vorher wäre es Abstraktion auf
  Vorrat.
- Tests prüfen den Renderer gegen Datensätze. Die Rezepte selbst sind
  Testdaten.
- Gespeicherte Playlists enthalten ihre Übergänge und sind editierbar.

## Belege

- `WISSEN-DJ-TECHNIKEN-UND-REPOS.md` §6, §9, §10

## Umsetzung 11.10.2026

- Das Rezept sind die Mixer-Einstellungen (`prototyp/klangbild/einstellungen.py`):
  Art, Länge in Takten, Ausstieg, Einstieg, Tempo-Modus, Tempo-Grenze, Keylock.
  Gespeichert werden sie als JSON.
- Ein einziger Renderer setzt sie um: `prototyp/klangbild/uebergang.py`
  (`backen`, `mischen`).
- Noch nicht umgesetzt: ein eigenes Rezept je Übergang in einer gespeicherten
  Playlist.
