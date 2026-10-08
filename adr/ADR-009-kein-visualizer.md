# ADR-009 · Kein Visualizer (EGL/GL)

**Status:** angenommen
**Datum:** 06.10.2026

## Kontext

Poweramp liefert einen Milkdrop-Visualizer (EGL/OpenGL, EEL2-Presets, LuaJIT).
Das ist technisch eindrucksvoll, aber teuer.

## Entscheidung

Wir bauen **keinen** Visualizer.

## Alternativen

1. Eigener Milkdrop-Klon. Verworfen.
2. Fertige Bibliothek (projectM, LGPL) einbinden. Verworfen.
3. Kein Visualizer. **Gewählt.**

## Begründung

- Der Visualizer trägt keinen Verkaufsgrund. Der Nutzer wählt den Player wegen
  Auswahl, Übergängen und Vertrauen, nicht wegen Effekten.
- EGL/GL, Shader-Übersetzung und Preset-Sprachen sind ein eigenes Großprojekt
  (Architektur-Dokument Abschnitt 28.4 zeigt den Umfang: `ShaderEngine`,
  `ShaderTranslator`, `EelParser`, LuaJIT).
- Jede Sekunde, die in den Visualizer geht, fehlt beim Kern (Auto-DJ).

## Konsequenzen

- Keine GPU-Abhängigkeit. Weniger Abstürze auf schwachen Geräten.
- Nur eine einfache Fortschritts-/Wellenform-Anzeige (Architektur-Dokument
  Abschnitt 25).
- Falls später gewünscht, ist der Einstieg eine eigene Entscheidung mit eigener
  Nummer.

## Belege

- `WISSEN-POWERAMP-ARCHITEKTUR.md` Abschnitt 26, 28.4
- `PROTOKOLLE.md` Abschnitt 3 (Status „nicht übernehmen")
