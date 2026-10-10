# ADR-018 · Stems als Kern, nur im Übergangsfenster getrennt

**Status:** vorgeschlagen (Entscheidung nach dem A/B/C-Hörtest)
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
