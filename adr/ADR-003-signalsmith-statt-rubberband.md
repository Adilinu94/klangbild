# ADR-003 · Signalsmith Stretch statt Rubber Band

**Status:** angenommen · ergänzt durch [ADR-014](ADR-014-vinyl-angleich-in-v1.md) (08.10.2026)
**Datum:** 06.10.2026

## Kontext

Für Beatmatching und Keylock brauchen wir Tempostrecken ohne Tonhöhenänderung.
Die naheliegenden Bibliotheken sind lizenzkritisch.

## Entscheidung

**Signalsmith Stretch (MIT)** als Standard. **SoundTouch (LGPL)** als Rückfall.

## Alternativen

| Bibliothek | Lizenz | Folge |
|---|---|---|
| Rubber Band | GPL v2+ oder Kauf | ❌ ohne Kauf nicht nutzbar |
| zplane élastique | proprietär, Royalty | ❌ Kosten pro Stück |
| SoundTouch | LGPL-2.1 | ⚠️ nutzbar, schwächere Qualität |
| **Signalsmith Stretch** | **MIT** | ✅ frei, gut bei 0,75–1,5 fach |

## Begründung

- Signalsmith ist **MIT**, aktiv gepflegt und klingt im relevanten Dehnbereich
  (0,75 bis 1,5 fach) am besten. Genau dort spielt Beatmatching.
- Kein Kauf, keine Offenlegungspflicht, kein Royalty.
- SoundTouch als Rückfall, falls ein Gerät Probleme macht.

## Konsequenzen

- Wir binden Signalsmith per NDK ein (header-only, C++11).
- Der Dehnungsfaktor bleibt klein; der Auto-DJ-Planer soll ähnliche Tempi
  bevorzugen (`sync_rate` in Architektur-Dokument Abschnitt 15.2).
- SoundTouch nur als Absicherung, damit wir bei Qualitätsproblemen wechseln
  können.

## Belege

- `ANDROID-AUTODJ-TOOLCHAIN-2026.md` (Lizenzen, Qualität)
- Lizenzprüfung: Rubber Band GPL, Signalsmith MIT
