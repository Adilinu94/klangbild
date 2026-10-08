# ADR-004 · Feste Tabelle statt Reflection für Plugins

**Status:** angenommen
**Datum:** 06.10.2026

## Kontext

Poweramp lädt Plugins über einen Namenszauber per **Reflection**: aus
`paket/decoder.ffmpeg` wird die Klasse `…FfmpegPluginService`. Für viele
austauschbare Module ist das elegant.

## Entscheidung

Wir nutzen eine **feste Tabelle** (Name → Factory), keine Reflection.

## Alternativen

1. Reflection wie Poweramp. Verworfen.
2. Feste Tabelle mit Fabriken. **Gewählt.**
3. Dependency Injection (z. B. Hilt). Überlegt, für unseren Umfang zu schwer.

## Begründung

- Reflection ist teuer und fehleranfällig. Poweramp muss dafür drei Fehlerfälle
  abfangen (Klasse fehlt → Null-Plugin, Paket passt nicht, Definition fehlt).
- Wir haben **wenige** Module (Decks, Ausgabe, DSP-Stufen). Eine Tabelle ist
  lesbar, testbar und zur Compile-Zeit prüfbar.
- Fehler werden zu Compile-Fehlern statt zu Laufzeitfehlern.

## Konsequenzen

- Ein neues Plugin braucht eine Zeile in der Tabelle, keine Namenskonvention.
- Externe Plugins (eigene APKs) sind damit nicht möglich. Das ist gewollt; wir
  bauen kein Plugin-Ökosystem.

## Belege

- `WISSEN-POWERAMP-ARCHITEKTUR.md` Abschnitt 22.2, 22.6
