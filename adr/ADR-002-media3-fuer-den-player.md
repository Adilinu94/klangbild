# ADR-002 · Media3 für den normalen Player

**Status:** angenommen · ergänzt durch [ADR-017](ADR-017-engine-als-media3-player.md) (08.10.2026)
**Datum:** 06.10.2026

## Kontext

Der normale Betrieb (Bibliothek, Antippen, Abspielen, Widget, Android Auto) ist
Standardarbeit und braucht keine eigene Engine.

## Entscheidung

Der normale Player nutzt **AndroidX Media3 / ExoPlayer 1.11.x**.

## Alternativen

1. Alles über die eigene Oboe-Engine. Verworfen.
2. Media3 für den Standard, eigene Engine nur für den Mixer. **Gewählt.**

## Begründung

- Media3 ist ausgereift, Apache-2.0 und unterstützt **Gapless**, MediaSession,
  Android Auto und Benachrichtigungen out of the box.
- Es wäre Verschwendung, das nachzubauen. Poweramp hat das aus historischen
  Gründen selbst, aber wir haben diesen Zwang nicht.
- Der Nutzer merkt keinen Unterschied, solange der Übergang in den Auto-DJ-Modus
  sauber ist.

## Konsequenzen

- Zwei Wiedergabewege im selben Produkt (Media3 im Normalmodus, eigene Engine im
  Auto-DJ). Der Wechsel muss nahtlos sein (Position, Lautstärke, Gerät).
- Wir pflegen zwei Pfade; die Schnittstelle zwischen ihnen muss klar sein.

## Belege

- `ANDROID-AUTODJ-TOOLCHAIN-2026.md` (Media3 1.11.x, Gapless)
- `PRODUKT-KLANGBILD.md` Abschnitt 8a
