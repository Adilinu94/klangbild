# ADR-020 · Vinyl-Angleich auf ±1 % begrenzen, bis Keylock kommt

**Status:** angenommen (10.10.2026, verifiziert durch Gegenmessung)
**Datum:** 10.10.2026
**Ergänzt:** ADR-014 (dort ±3 %)

## Kontext

ADR-014 erlaubt in Version 1 einen Tempoangleich per Resampling bis ±3 %. Dabei
ändert sich die Tonhöhe mit: Bei 3 % sind es 12·log2(1,03) = 0,51 Halbtöne, also
ein Wert genau zwischen zwei Tonarten. Bei 1 % sind es 0,17 Halbtöne (17 Cent).
Echte DJs lassen Keylock fast immer an. Nur 2,5 % der Titel werden transponiert
(Kim et al., ISMIR 2020, siehe `WISSEN-DJ-TECHNIKEN-UND-REPOS.md` §2.2). Der
Planer wählt nach Camelot-Harmonie. Ein Vinyl-Versatz um einen halben Halbton
macht genau diese Wahl zunichte.

## Messung an der eigenen Bibliothek (10.10.2026, Analyse 0.3.0)

490 mischbare Tracks (ohne Dubletten). Partner je Track innerhalb des
Tempo-Gates:

| Gate | Partner je Track (Median) | Tracks ohne Partner |
|---|---|---|
| ±3 % | 188 | 6 |
| ±1 % | 67 | 14 |

Nachtrag (Dubletten, 11.10.2026): Die Bibliothek enthält 166 echte MP3+FLAC-
Dubletten derselben Aufnahme (gleicher normalisierter Titel + gleiches Tempo).
Nach Abzug: 332 mischbare Tracks. Die Partner-Zählung oben ist vor Abzug
gemessen; die Set-Längen unten danach — beide tragen ±1 %.

Die Bibliothek gibt ±1 % also her. Im ersten Hörtest-Render läuft Paar 1 mit
+2,36 % (0,40 Halbtöne), die anderen beiden Paare bleiben unter 1 %.

## Entscheidung

`resample.TEMPO_MAX_ABWEICHUNG` von 0,03 auf **0,01**, bis Keylock (Signalsmith,
ADR-003) im Prototyp läuft. Danach gilt wieder ±3 %, dann mit gleicher Tonhöhe.

## Gegenmessung: echte Set-Längen (10.10.2026, Nachtrag zur Annahme)

Partner-Median allein sagt nicht, wie lang Sets werden. Darum je Start-Track ein
Set mit `plan.baue_set` (49 Starts, jeder 10. mischbare Track, 490 Tracks):

| Gate | Set-Länge Median | p10 | min | Sets < 3 Songs |
|---|---|---|---|---|
| ±3 % | 189 | 26 | 1 | 1 |
| ±1 % | 71 | 10 | 1 | 2 |

Auch bei ±1 % trägt das längste Set 71 Songs; selbst das 10-%-Quantil hat 10.
Der Hörtest braucht 4 Songs je Paar — das gibt die Bibliothek überall her.

## Alternativen

1. **±3 % lassen.** Mehr Auswahl, aber hörbar verstimmte Übergänge.
2. **±1 % (Vinyl).** Vorgeschlagen.
3. **Keylock sofort im PC-Prototyp.** Am besten klingend, aber der teuerste
   Schritt. Er lohnt sich erst, wenn der Hörtest zeigt, dass die Übergänge an
   sich tragen.

## Konsequenzen

- Kürzere Sets in dünn besetzten Tempobereichen (14 statt 6 Tracks ohne
  Partner).
- Phase-1.0-Messung und Tests, die ±3 % voraussetzen, müssen angepasst werden.

## Belege

- `prototyp/ergebnisse/hoertest/_paar1-autodj.json` (Tempofaktor 1,02362)
- `WISSEN-DJ-TECHNIKEN-UND-REPOS.md` §2.2, §10
