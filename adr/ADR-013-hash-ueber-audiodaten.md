# ADR-013 · Hash nur über die Audiodaten

**Status:** angenommen
**Datum:** 08.10.2026
**Ergänzt:** ADR-007

## Kontext

ADR-007 bindet Analyse und Vektoren an einen Inhalts-Hash der Datei. Zwei
Folgen waren nicht bedacht:

1. **Tags schreiben** ändert die Datei und damit den Hash. Jede Korrektur eines
   Titels würde die ganze Analyse neu auslösen.
2. Ein Hash über die **ganze Datei** liest bei großen Sammlungen (8.000 Titel,
   FLAC) zig Gigabyte.

## Entscheidung

Der Hash läuft nur über den **Audio-Datenbereich**, nicht über Tag-Blöcke
(ID3, Vorbis-Kommentare, MP4-Metadaten, Cover). Gehasht wird eine
**Stichprobe**: Länge des Audio-Bereichs plus feste Blöcke am Anfang, in der
Mitte und am Ende (z. B. je 64 KB).

Größe + Änderungszeit bleiben der billige Vorfilter (ADR-007).

## Alternativen

1. **Ganze Datei hashen.** Verworfen: Tag-Änderungen lösen Neuanalyse aus,
   hohe Lesekosten.
2. **Audio-Bereich vollständig hashen.** Sicherer, aber teuer. Als Rückfall,
   falls die Stichprobe Kollisionen zeigt.
3. **Stichprobe über den Audio-Bereich.** **Gewählt.**
4. **Akustischer Fingerabdruck.** Verworfen: braucht Decodierung, teurer als
   nötig.

## Konsequenzen

- Pro Containerformat wird der Audio-Bereich bestimmt (der Tag-Leser kennt die
  Grenzen ohnehin).
- Retagging behält die Analyse. Neu encodierte Dateien bekommen einen neuen
  Hash und werden neu analysiert. Das ist gewollt.

## Belege

- ADR-007
- `PRODUKT-KLANGBILD.md` §5a (Tags schreiben)

## Ergänzung 08.10.2026 · Prüfung statt Annahme

Der Hash ist nur so gut wie die Grenzziehung. Deshalb **Testpflicht** im
Prototyp (`prototyp/tests/test_hashutil.py`):

1. **Retagging-Test:** 30 echte Dateien (MP3 mit ID3v2 vorne, ID3v1/APE hinten;
   FLAC mit Vorbis-Kommentaren) werden neu getaggt – der Hash **muss** gleich
   bleiben.
2. **Kollisions-Check:** der Hash aller 501 Dateien der Testsammlung muss
   eindeutig sein; jede Kollision ist ein Fund, keine Randnotiz.
3. **Container-Abdeckung:** MP3, FLAC und WAV werden exakt bestimmt. Bei
   Formaten, deren Audio-Bereich nicht sicher ermittelbar ist (z. B. M4A/MP4),
   wird auf den Hash der ganzen Datei zurückgefallen und das im Datensatz
   **markiert** – nicht verschwiegen.

Zusätzlich (aus ADR-007): Neben dem Hash braucht die Datenbank ein
`analysis_version`-Feld. Wechselt das Verfahren oder das Modell, wird **alles**
neu gerechnet – sonst vergleicht der Hörtest nach einem Wechsel alte mit neuen
Werten.
