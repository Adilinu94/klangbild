# ADR-022 · Keylock jetzt, Tempo-Grenze als Einstellung, Taktraster aus dem Tempo

**Status:** angenommen (Entscheidung des Nutzers, 11.10.2026)
**Datum:** 11.10.2026
**Ergänzt:** ADR-003 (Signalsmith), ADR-014 und ADR-020 (Vinyl ±1 %)

## Kontext

Der Nutzer will die BPM-Anpassung selbst einstellen, bis ±5 oder ±10 BPM, an
den aktuellen oder an den nächsten Song. Ohne Keylock verstimmt das hörbar:
+10 BPM bei 128 BPM sind etwa 1,3 Halbtöne. ADR-020 hatte Vinyl deshalb auf
±1 % begrenzt, „bis Keylock kommt".

## Entscheidung

1. **Keylock im PC-Prototyp:** `python-stretch` 0.3.1 (MIT, Bindung an
   Signalsmith Stretch, ADR-003). Schalter „Tonhöhe halten" in den
   Einstellungen, Standard an. Ohne Keylock gilt weiter Vinyl (`resample`).
2. **Tempo-Grenze als Einstellung:** `max_bpm` 0 bis 10 BPM, Standard 5. Liegt
   der Abstand darüber, gibt es einen Echo-Out ohne Tempoangleich statt eines
   Mixes im Takt.
3. **Beat-Warp:** Jeder Song wird Takt für Takt auf ein Zielraster gedehnt
   (`uebergang.warp`). Die Tempo-Modi sind nur verschiedene Zielraster:
   - „Nächster an aktuellen"
   - „Aktueller an nächsten"
   - „Gleitend": die Taktlänge gleitet über die Blende. Danach spielt B im
     Originaltempo, es bleibt also kein Drift über das Set.
4. **Taktraster aus dem Song-Tempo:** Das Raster ist gleichmäßig und kommt
   aus der BPM-Regression (±0,1 %, Phase 0.9). Die Downbeats liefern nur die
   Phase, als Kreismittel im Umkreis von ±30 s um die Übergangsstelle.
   Grund: Beat This! setzt in Breakdowns und Intros stellenweise grob falsche
   Downbeats (bei etwa 5 % der Bibliothek lag das lokale Tempo daneben).
   Taktweises Dehnen darauf hätte genau dort das Audio verzerrt.

## Belege (gemessen 11.10.2026)

- Warp mit Keylock: Klicks liegen nach dem Dehnen auf 0,8 ms genau im
  Zielraster. Die Tonhöhe eines 440-Hz-Sinus bleibt bei 10 % Dehnung erhalten
  (`tests/test_uebergang.py`).
- Rechenzeit für eine 24-Takt-Blende mit Keylock: 2,5 bis 4,7 s auf dem
  Entwicklungs-PC.
- Signalsmith hält während des Rechnens den GIL. Am Stück gerechnet waren das
  bis zu 54 ms, und live gab es 14 Aussetzer. Jetzt rechnet es in Stücken von
  4096 Samples, und der Audio-Stream läuft mit `latency="high"`. Danach gab es
  live 0 Aussetzer.
- Raster gegen Downbeats (alle 332 Tracks, um 100 s): Median 8,8 ms Abstand,
  77 % unter 30 ms. Der Rest sind falsche Downbeats oder Tempo-Wechsel im Song.

## Konsequenzen

- ADR-020 (±1 % Vinyl) gilt nur noch bei ausgeschaltetem Keylock als
  sinnvolle Grenze.
- Grenze: Ein Song mit echtem Tempo-Wechsel bekommt ein falsches Raster
  (Shortcut im Code markiert). Upgrade wäre ein abschnittsweises Raster.
- Für Android bleibt Signalsmith (C++) gesetzt, die Mathematik ist dieselbe.
