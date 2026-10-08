# ADR-011 · PC-Prototyp zuerst, Android später

**Status:** angenommen
**Datum:** 08.10.2026

## Kontext

Die bisherigen Fahrpläne beginnen mit „Phase A · Player wie Poweramp". Das ist
der größte Aufwand und unterscheidet uns von niemandem. Die eigentlichen
Unbekannten sind andere: Taugen die Klang-Vektoren für Musik? Stimmt die
Analyse? Klingen die Übergänge gut genug? Diese Fragen lassen sich ohne Android
beantworten.

## Entscheidung

Wir bauen zuerst einen **PC-Prototyp in Python**, der Analyse, Auswahl und
Übergänge prüft und einen Mix **offline rendert**. Die Android-App beginnt erst,
wenn der Prototyp seine Tore bestanden hat (`ROADMAP-KLANGBILD.md`).

## Alternativen

1. **Android zuerst (Player, dann Auto-DJ).** Verworfen: Monate Arbeit, bevor
   die Kernwette geprüft ist.
2. **PC-Prototyp als Echtzeit-Desktop-App.** Verworfen für den Anfang: Für
   Hörtest und Hörprobe genügt ein gerenderter Mix.
3. **PC-Prototyp, offline rendernd.** **Gewählt.**

## Begründung

- Die Lehre aus dem Projekt (Produkt §14): erst messen, dann bauen.
- Ein gerenderter Mix ist gleichzeitig Test der Auswahl, Test der Übergänge
  und Hörprobe für die Landingpage.
- Python hat alle Bausteine fertig; auf Android müsste jeder erst portiert
  werden.

## Konsequenzen

- Der Prototyp wird **nicht** ausgeliefert. Nur gerenderte Mixe verlassen den
  Rechner.
- Er nutzt trotzdem nur Werkzeuge, die auch auf Android erlaubt sind
  (ADR-012), damit die Ergebnisse übertragbar bleiben.
- Code des Prototyps ist Wegwerf-Code. Übertragen werden Verfahren, Schwellen
  und Modelle, nicht der Python-Code.
- Die Android-ADRs (001, 002, 006, 010, 016, 017) bleiben gültig, greifen aber
  erst ab Phase 3.

## Belege

- `ROADMAP-KLANGBILD.md`
- `PRODUKT-KLANGBILD.md` §14, §15
