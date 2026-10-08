# ADR-010 · Zwei Decoder-Slots

**Status:** angenommen
**Datum:** 06.10.2026

## Kontext

Nahtlose Übergänge und der Auto-DJ brauchen zwei Tonspuren gleichzeitig: Deck A
spielt, Deck B wird vorbereitet. Poweramp hat dafür belegbar **zwei Slots**
(`slot_0`, `slot_1`) mit je eigener Seek-Nummer.

## Entscheidung

Wir bauen **zwei Decoder-Slots** (Deck A, Deck B), jeder mit eigener
Seek-Seriennummer und eigenem Zustand.

## Alternativen

1. **Ein Slot, Umschalten.** Verworfen: kein nahtloser Übergang möglich.
2. **Zwei Slots.** **Gewählt.**

## Begründung

- Ohne zweiten Slot gibt es Lücken oder ein hartes Umschalten.
- Belegter Poweramp-Fehlertext: `failed to seek serial=%d, slot_0.serial=%d,
  slot_1.serial=%d` zeigt, dass **jeder Slot seine eigene Seek-Nummer** hat.
  So kann Slot B springen, während Slot A ungestört weiterspielt.
- Dasselbe Muster erklärt Gapless und Crossfade (Postfade-Blöcke).

## Konsequenzen

- Doppelter Decoder-Zustand, doppelte Puffer (Speicher).
- Die Seek-Seriennummer gehört **pro Slot**, nicht global.
- Der Ausgabe-Callback mischt beide Slots (Architektur-Dokument Abschnitt 15.10).
- Der Auto-DJ-Planer lädt Deck B, während Deck A läuft.

## Belege

- `WISSEN-POWERAMP-ARCHITEKTUR.md` Abschnitt 3.4, 15.10
- `native/key-strings.txt` (slot_0/slot_1)
