# ADR-021 · PC-Prototyp als Echtzeit-DJ-Mixer, keine Landingpage

**Status:** angenommen (Entscheidung des Nutzers, 11.10.2026)
**Datum:** 11.10.2026
**Löst ab:** ADR-011, Alternative 3 (offline rendernd). ADR-011 Alternative 2 gilt jetzt.

## Kontext

ADR-011 hat den PC-Prototyp bewusst offline gebaut: Für Hörtest und Hörprobe
reichte ein gerenderter Mix. Dieser Teil ist fertig (Phase 0 und 1, Analyse,
Planer, Übergangs-Engine, blinder Hörtest). Der Nutzer will vor der Android-App
einen **bedienbaren** Mixer auf dem PC: Musik live hören, Auto-DJ ein- und
ausschalten, eingreifen. Eine Landingpage mit Warteliste (Roadmap Phase 2)
entfällt.

## Entscheidung

1. Der PC-Prototyp wird zu einem **Echtzeit-DJ-Mixer**: zwei Decks, Live-
   Wiedergabe, Bibliothek, Warteschlange, Auto-DJ-Schalter.
2. Die Übergangs-Mathematik bleibt die vorhandene (`mix.py`, `resample.py`,
   `plan.py`). Es entsteht kein zweiter Mix-Algorithmus.
3. **Roadmap Phase 2 (Landingpage, Warteliste) entfällt.** Damit gibt es auch
   keine öffentliche Hörprobe und keine Lizenzpflicht für CC-Musik.

## Alternativen

1. **Offline bleiben (ADR-011).** Verworfen vom Nutzer: kein bedienbares Produkt.
2. **Echtzeit-Mixer auf dem PC.** Gewählt.
3. **Direkt Android.** Verworfen: Der Mixer soll erst auf dem PC stimmen.

## Konsequenzen

- Der Prototyp wird weiterhin **nicht** ausgeliefert (ADR-011 Konsequenz bleibt).
- **Stack (11.10.2026 festgelegt):**
  - Ausgabe über **sounddevice** (MIT, bringt PortAudio mit, MIT).
  - Oberfläche **lokal im Browser** (`python -m klangbild mixer`), Server aus
    der Standardbibliothek wie `blindui.py`.
  - Umfang V1: Player + Auto-DJ, keine manuellen Decks.
  - Keine GPL-Bausteine; Titel kommen aus dem Dateinamen, weil mutagen GPL ist.
- Die Android-Engine (Oboe, C++) bleibt eine eigene Implementierung. Der PC-Mixer
  ist ihr Vorbild für Verhalten, nicht ihr Code.
