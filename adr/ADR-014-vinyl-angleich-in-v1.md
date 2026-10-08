# ADR-014 · Tempoangleich per Resampling in Version 1

**Status:** angenommen
**Datum:** 08.10.2026
**Ergänzt:** ADR-003

## Kontext

Die erste Version sollte „nur überblenden, Songs mit nahem Tempo, ohne
Tempostrecken" und trotzdem „auf der Taktgrenze" sitzen. Das geht nicht:
Schon 1 % Tempounterschied lässt zwei Songs über 8 Takte bei 125 BPM (15,4 s)
um etwa 150 ms auseinanderlaufen, ein Drittel Beat. Das hört man als
„Galoppieren". Bei 0,5 % sind es noch etwa 77 ms.

## Entscheidung

In Version 1 wird Song B per **einfachem Resampling** (Vinyl-Prinzip) auf das
Tempo von A gezogen. Die Tonhöhe ändert sich dabei mit. Der Planer erlaubt nur
Tempounterschiede bis **±3 %** (etwa ein halber Halbton).

**Keylock** (Tempo ändern bei gleicher Tonhöhe) mit Signalsmith Stretch kommt
erst in Phase 5 (ADR-003 bleibt gültig).

## Alternativen

1. **Ohne Angleich überblenden.** Verworfen: hörbares Auseinanderlaufen, außer
   bei sehr kurzen Blenden.
2. **Keylock von Anfang an.** Verworfen für V1: der teuerste Teil, und die
   Qualität hängt am Gerät.
3. **Resampling (Vinyl).** **Gewählt.**

## Begründung

- DJs haben jahrzehntelang genau so gearbeitet. Kleine Tonhöhenänderungen
  stören kaum.
- Einen Resampler braucht die Engine ohnehin (44,1 und 48 kHz mischen).
- Kein Phasenvokoder, keine Artefakte, kaum Rechenlast.

## Konsequenzen

- Der Planer begrenzt Tempo-Sprünge auf ±3 %. Größere Sprünge nur über harten
  Schnitt oder kurze Blende auf beatlosen Abschnitten.
- Song B kann nach dem Übergang langsam auf sein Originaltempo zurückgleiten.
- Der Wechsel auf Keylock in Phase 5 ändert nur die Dehnungsstufe, nicht den
  Planer.

## Belege

- Rechnung: 0,01 × 15,36 s = 154 ms Versatz nach 8 Takten bei 125 BPM
- ADR-003, `ARCHITEKTUR-KLANGBILD.md` §10

## Ergänzung 08.10.2026

Google beschreibt das Prinzip im Oboe-Beispiel `samples/OboeDJ`: Geschwindigkeits-
multiplikator je Deck, `SoundPlayer` mit **linearer Interpolation** für gleich-
mäßige Geschwindigkeitswechsel und Rückwärtswiedergabe, BPM-Sync durch Setzen
des Multiplikators. Für den Prototyp gilt dasselbe Verfahren in numpy
(`prototyp/klangbild/resample.py`), damit Phase 1 und Phase 5 dieselbe
Zahlenbasis haben.
