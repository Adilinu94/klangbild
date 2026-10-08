# ADR-016 · Oboe im geteilten Stromsparmodus statt Low-Latency/Exclusive

**Status:** angenommen
**Datum:** 08.10.2026
**Ergänzt:** ADR-001

## Kontext

ADR-001 und die Toolchain-Recherche nennen `PerformanceMode::LowLatency`,
`SharingMode::Exclusive` und AAudio MMAP. Das ist die Einstellung für
Instrumente und Spiele, bei denen der Nutzer live etwas auslöst.

Der Auto-DJ plant Übergänge **im Voraus**. Sample-genau wird der Mix durch den
**einen** Callback, der beide Decks im selben Raster mischt, nicht durch eine
kleine Latenz.

## Entscheidung

Oboe läuft mit `PerformanceMode::PowerSaving` (Rückfall `None`),
`SharingMode::Shared`, `Usage::Media`, `ContentType::Music`. Die Puffergröße
richtet sich nach Stabilität, nicht nach Latenz.

## Alternativen

1. **LowLatency + Exclusive.** Verworfen: höherer Akkuverbrauch im
   Hintergrund, blockiert andere Apps, MMAP gibt es über Bluetooth nicht.
2. **PowerSaving + Shared.** **Gewählt.**

## Konsequenzen

- Der Messplan (`PROTOKOLLE.md` §12) misst nicht mehr „Gesamtlatenz unter
  30/60 ms", sondern die **Positionsgenauigkeit** (`getTimestamp`) für die
  Anzeige und die Zahl der Aussetzer.
- Bluetooth-Latenz (oft über 150 ms) ist für den Mix egal, nur die Anzeige muss
  sie verrechnen.

## Belege

- ADR-001, `WISSEN-POWERAMP-ARCHITEKTUR.md` §11
- Oboe: https://github.com/google/oboe

## Ergänzung 08.10.2026

**Vorlagenstudie für Phase 3:** Googles Beispiel `samples/OboeDJ` im Oboe-Repo
(Apache-2.0) zeigt genau die vorgesehene Engine: einen C++-`DJEngine`, der die
Oboe-Ströme verwaltet und mischt, zwei Decks, Crossfader, Geschwindigkeitsfaktor
0,5×–2,0× mit linearer Interpolation, BPM-Sync per Geschwindigkeitsmultiplikator.
Es nutzt allerdings `LowLatency` – unsere Abweichung nach dieser ADR ist
bewusst und muss im Spike begründet bleiben. Zusätzlich prüfen: Oboe bietet
PCM-Offload-Wiedergabe zur Stromersparnis; ob die mit unserem Mischen im Callback
verträglich ist, ist eine Phase-3-Frage.
