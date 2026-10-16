# ADR-024 · Vorausbacken auf Android statt Echtzeit-Signalgraph

**Status:** vorgeschlagen
**Datum:** 15.10.2026
**Ergänzt:** ADR-001, ADR-016, ADR-021

## Kontext

Der Desktop-Mixer (`live.py`, ADR-021) arbeitet nach dem Prinzip
**Vorausbacken**: Ein Back-Thread wählt den nächsten Titel, plant den Übergang
und rendert die ganze Blende als fertigen Puffer (`uebergang.backen`). Der
Audio-Callback kopiert nur Samples aus dem Puffer und schaltet an der
Wechselstelle die Referenz auf Spur B um.

Djay macht es anders: echter Signalgraph je Deck im Callback (Stretch, EQ, FX).
Das braucht `LowLatency`/`Exclusive` und eine Quirk-Liste; es ist die richtige
Wahl für manuelle Decks und Scratchen. Klangbild hat keine manuellen Decks.

Der Desktop läuft bereits nach dem Vorausbacken, ist gehört und hat 308 Tests.
Die Übergangs-Mathematik (`uebergang.py`) ist damit erprobt.

## Entscheidung

Android übernimmt das Vorausbacken **unverändert**:

1. Der **Baker-Pool** (C++, niedrige Priorität) rendert die Blende im
   Hintergrund (`uebergang.backen` als Port).
2. Der **Audio-Callback** kopiert nur aus einem SPSC-Ringpuffer; an der
   Wechselstelle wechselt er die Spur. CPU im Callback ≈ 0.
3. Der **Feeder-Thread** liest Segmente und füllt den Ring (kein Echtzeit-Thread,
   deshalb ist dort ein Mutex für Kotlin-Befehle erlaubt).
4. Oboe läuft `PowerSaving` + `Shared` (ADR-016); Latenz ist für den Auto-DJ
   ohne Belang, Akku nicht.

## Alternativen

1. **Echtzeit-Signalgraph im Callback (wie djay).** Verworfen: braucht
   `LowLatency`/`Exclusive` und die Geräte-Quirks; der Auto-DJ plant voraus und
   gewinnt dadurch nichts.
2. **Vorausbacken.** **Gewählt.** Gleiche Bibliothek wie der Desktop
   (Signalsmith Stretch, ADR-003), gleiche Zahlen (Golden-Tests).
3. **Mischform** (Echtzeit nur für die Blende). Verworfen: zwei Wege für dieselbe
   Mathematik, kein Nutzen ohne manuelle Decks.

## Konsequenzen

- Der Audio-Callback bleibt heilig: kein `new`/`malloc`, kein Lock, kein
  Datei-I/O, kein Log, kein JNI, keine Exception (Bauplan §0 Regel 4).
- Speicher: Ein Songs-Puffer liegt nicht mehr komplett im RAM, sondern als
  PCM-Cache-Datei (ADR-025). Nur die Blende liegt fertig gerechnet im RAM.
- Backzeit ist eine Planungsgröße: `vorbereiten` plant mit
  `max(VORLAUF_S, 1.5·backzeit + 1)`; bei Hitze kürzt ADR/§10.3 die Längen.
- Das Ergebnis ist mit Python vergleichbar (Golden-Tests, §12.3).

## Belege

- ADR-001, ADR-016, ADR-021, ADR-003
- djay-Analyse Teile 2/4/5 (§40, §42, §50, §61)
- `prototyp/klangbild/live.py` (`_backen_ergebnis`, `_auto_backen`)
- `BAUPLAN-ANDROID.md` §3.1, §5.2, §5.3
