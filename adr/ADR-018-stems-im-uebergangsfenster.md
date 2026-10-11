# ADR-018 · Stems als Kern, nur im Übergangsfenster getrennt

**Status:** angenommen für den PC-Prototyp (11.10.2026); für die Android-App erst nach Lizenzklärung der Gewichte und Messung auf dem Handy
**Datum:** 10.10.2026
**Ergänzt:** ADR-001, ADR-010, `PRODUKT-KLANGBILD.md` §5c (dort „Kann", Phase 6)

## Kontext

Einfache Übergänge (Crossfade, EQ-Blend, Bass-Tausch) bieten Spotify Mix und
Apple AutoMix inzwischen selbst an. Unterscheiden kann sich Klangbild nur über
das, was ein Profi-DJ mit Stems macht: Drums von B unter den Gesang von A legen,
Gesang von A über die Blende halten, zwei Gesänge nie gleichzeitig laufen
lassen (`WISSEN-DJ-TECHNIKEN-UND-REPOS.md` §4, Rezepte S1–S8).

Den ganzen Song in Stems zu trennen, ist auf dem Handy zu teuer: Demucs läuft
dort etwa in Echtzeit, und jeder Song bräuchte rund 4 × seine Größe an
Speicher.

## Entscheidung (Vorschlag)

1. Stems werden ab Phase 1 Teil des Kerns, nicht mehr „Kann" in Phase 6.
2. Getrennt wird **nur das Übergangsfenster**, also z. B. die letzten 45 s von
   A und die ersten 45 s von B. Das passiert, während A noch läuft. Das
   Ergebnis wird kurz zwischengespeichert, ältere Fenster werden gelöscht.
3. **Exakte Rekonstruktion:** Der Rest r = Original − Summe der Stems wird zum
   Stem „other" addiert. Stehen alle Stems auf 1, ergibt ihre Summe exakt das
   Original. Der Wechsel zwischen Original und Stems ist dann nicht zu hören.
4. **Rückfall ohne Stems:** die Rezepte R1–R7. Ist ein Fenster nicht rechtzeitig
   fertig, nimmt der Planer ein Rezept ohne Stems. Der Audio-Callback wartet nie.

## Alternativen

1. **Ganze Songs offline trennen.** Verworfen: Speicher und Akku zu teuer.
2. **Keine Stems.** Verworfen: Dann gibt es kein Alleinstellungsmerkmal mehr
   gegenüber dem Streaming-Standard.
3. **Fenster just in time trennen.** Vorgeschlagen.

## Offen vor „angenommen"

- Gewichte-Lizenz von HTDemucs ist ungeklärt (der Code ist MIT, das Repo
  archiviert). Ohne geklärte Lizenz gibt es keine Auslieferung, auch wenn der
  Prototyp funktioniert.
- Phase 3 muss die Demucs-Zeit für ein 90-s-Fenster auf einem
  Mittelklasse-Handy messen (ONNX/ExecuTorch, Vorlage demixr).
- Erst ein A/B/C-Hörtest (Crossfade, EQ-Blend, Stems) zeigt, ob Stems hörbar
  besser sind. Werkzeug für die Paare: `python -m klangbild hoertest`.

## Konsequenzen

- Speicher: 4 Stems × 90 s × 44,1 kHz × Stereo × 16 Bit ≈ 64 MB Rohdaten je
  Fenster.
- Die Engine braucht je Deck das Original plus 4 Stems (ADR-001/010 ergänzen).

## Belege

- `WISSEN-DJ-TECHNIKEN-UND-REPOS.md` §4, §7, §10

## Umsetzung im PC-Prototyp (11.10.2026)

- `prototyp/klangbild/stems.py`: Demucs 4.1.0 `htdemucs` (Code MIT). Die
  Gewichte liegen auf HuggingFace `adefossez/HTDemucs` und nennen **keine
  Lizenz**. Für den lokalen Prototyp ist das in Ordnung, vor einer
  Auslieferung muss es geklärt werden.
- **Eigener Prozess** mit niedriger Priorität und halben Kernen. Im selben
  Prozess hielt torch den GIL bis etwa 90 ms am Stück, das hätte die
  Wiedergabe aussetzen lassen.
- **Messung auf dem Entwicklungs-PC:** etwa 1,4-fache Echtzeit mit allen
  Kernen, etwa 2,3-fach nachrangig. Just in time reicht das bei kurzen Songs
  nicht: Das Outro beginnt nach etwa 2:20 min, zwei Fenster brauchen rund
  140 s.
- **Darum Vorrechnen:** Sobald ein Übergang gebacken ist, trennt der
  Hintergrundprozess schon das Outro des nächsten und das Intro des
  übernächsten Songs. Läuft eine Trennung bereits, wird sie nicht doppelt
  gestartet.
- **Cache:** float16-npz unter `prototyp/cache/stems/`, etwa 21 MB je
  16-Takt-Fenster.
- **Übergänge:** „Drums zuerst", „Acapella-Übergabe", „Gesangsschutz" (es
  singen nie zwei Stimmen gleichzeitig). „Automatisch" nimmt Gesangsschutz,
  wenn im Fenster beide Songs singen (Gesang ≥ 15 % des Pegels).
- **Rückfall:** Reicht die Zeit nicht (Trennzeit plus Dehnen der 8
  Stem-Spuren), wird ohne Stems gemischt und der Grund protokolliert. Nach
  WEITER werden nie Stems benutzt.
- **Live-Test (10 min Auto-DJ, 16 Takte, gleitend, Keylock):** 4 Übergänge,
  0 Aussetzer. Der erste lief ohne Stems (zu knapp), die übrigen mit Stems
  aus der Vorrechnung. Backzeit mit Stems 1,6 bis 13,5 s.
- **Noch offen:** der A/B/C-Hörtest (Crossfade, EQ, Stems) als Beleg, dass
  Stems hörbar besser sind.
