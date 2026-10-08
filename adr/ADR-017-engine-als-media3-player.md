# ADR-017 · Eigene Engine als Media3-Player

**Status:** angenommen
**Datum:** 08.10.2026
**Ergänzt:** ADR-002

## Kontext

ADR-002 führt zwei Wiedergabewege: Media3/ExoPlayer im Normalmodus, die eigene
Engine im Auto-DJ. Benachrichtigung, Sperrbildschirm, Kopfhörertasten und
Android Auto hängen an der MediaSession. Mit zwei Playern müsste die Session
beim Moduswechsel umgehängt werden. Das ist eine dauerhafte Fehlerquelle.

## Entscheidung

Die eigene Engine wird hinter der Media3-Schnittstelle `Player` gekapselt
(`SimpleBasePlayer`). Es gibt **eine** MediaSession. Der Moduswechsel tauscht
nur, was hinter dem `Player` arbeitet.

## Alternativen

1. **Zwei Player, Session umhängen.** Verworfen: Bruchstelle bei jedem Wechsel.
2. **Engine als Media3-Player.** **Gewählt.**
3. **Alles über die eigene Engine, ExoPlayer ganz weglassen.** Möglich, sobald
   die Engine Gapless kann. Spätere Entscheidung mit eigener Nummer.

## Konsequenzen

- UI, Benachrichtigung und Android Auto sehen nur einen Player.
- Die Engine muss Zustände und Positionen in Media3-Begriffen melden.
- Option 3 bleibt offen, ohne dass sich die UI ändert.

## Belege

- ADR-001, ADR-002
- Media3 `SimpleBasePlayer`: https://developer.android.com/reference/androidx/media3/common/SimpleBasePlayer
