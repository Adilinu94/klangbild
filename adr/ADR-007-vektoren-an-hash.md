# ADR-007 · Vektoren an den Datei-Hash gebunden

**Status:** angenommen · ergänzt durch [ADR-013](ADR-013-hash-ueber-audiodaten.md) (08.10.2026)
**Datum:** 06.10.2026

## Kontext

Analyse (BPM, Key, Struktur) und Einbettung (Klang-Vektor) sind teuer. Sie dürfen
nicht bei jedem Start neu laufen.

## Entscheidung

Analyse-Ergebnisse und Vektoren hängen an einem **Inhalts-Hash** der Datei. Ist
der Hash gleich, wird nichts neu gerechnet.

## Alternativen

1. **Pfad als Schlüssel.** Verworfen: Umbenennen würde alles neu rechnen.
2. **Größe + Änderungszeit (wie der Scanner).** Schwächer als ein Hash, aber
   billig. Als Vorfilter brauchbar.
3. **Inhalts-Hash.** **Gewählt** (zusammen mit Größe/mtime als Vorfilter).

## Begründung

- Derselbe Inhalt soll dieselben Ergebnisse bekommen, unabhängig vom Pfad.
- Poweramp macht dasselbe Muster beim Wellenform-Worker: nur rechnen, wenn
  `f0.r == null` (Architektur-Dokument Abschnitt 17.2).
- Der Scanner nutzt Größe plus Änderungszeit für den schnellen Vergleich
  (Abschnitt 21.7); der Hash ist die sichere Stufe.

## Konsequenzen

- Die Datenbank braucht eine Hash-Spalte mit Index.
- Beim Verschieben einer Datei bleibt das Ergebnis erhalten.
- Eine geänderte Datei (anderer Hash) löst gezielt neue Analyse aus.

## Belege

- `WISSEN-POWERAMP-ARCHITEKTUR.md` Abschnitt 16.9, 17.2, 21.7
