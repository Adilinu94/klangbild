# ADR-001 · Eigene native Engine statt Media3 für den Mixer

**Status:** angenommen · ergänzt durch [ADR-016](ADR-016-oboe-shared-statt-exclusive.md) (08.10.2026)
**Datum:** 06.10.2026

## Kontext

Der Auto-DJ muss zwei Tracks sample-genau mischen, das Tempo angleichen und
Beats ausrichten. Wir brauchen dafür einen Ausgabeweg mit niedriger Latenz und
zwei unabhängigen Tonspuren, die in **einem** Takt laufen.

## Entscheidung

Für den Mixer bauen wir eine **eigene native Engine auf Oboe**. Für den normalen
Player (ADR-002) nutzen wir Media3.

## Alternativen

1. **Media3/ExoPlayer für alles.** Verworfen.
2. **Superpowered SDK.** Verworfen (proprietär, Kosten, 1000-Install-Limit).
3. **Eigene Engine auf Oboe.** Gewählt.

## Begründung

- Media3 `DefaultAudioSink` hat über **250 ms** Puffer und **keine Zwei-Deck-API**
  (belegt: ExoPlayer-Issue #8970). Beat-genaue Übergänge sind damit unmöglich.
- Oboe ist Apache-2.0, latenzarm (`LowLatency`, `Exclusive`, AAudio MMAP) und
  erlaubt **einen** Callback, der beide Decks aus eigenen Puffern mischt.
- Damit gibt es nur **eine Uhr** und keinen Versatz (siehe Architektur-Dokument
  Abschnitt 15.10).

## Konsequenzen

- Wir müssen die Engine selbst bauen (großer Aufwand, Kern des Produkts).
- Decoding läuft über MediaCodec (Plattform) separat; nicht über Media3.
- Media3 bleibt für Bibliothek und Wiedergabe im Nicht-Mixer-Modus.
- Ein Decoder-Slot-Konzept ist Voraussetzung (ADR-010).

## Belege

- `WISSEN-POWERAMP-ARCHITEKTUR.md` Abschnitt 15, 27
- `ANDROID-AUTODJ-TOOLCHAIN-2026.md` (Oboe, Media3-Grenzen)
