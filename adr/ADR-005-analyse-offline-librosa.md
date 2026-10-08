# ADR-005 · Analyse offline per librosa statt on-device

**Status:** abgelöst durch [ADR-012](ADR-012-analyse-mit-permissiven-modellen.md) (08.10.2026)
**Datum:** 06.10.2026

## Kontext

Der Auto-DJ braucht pro Track BPM, Beat-Raster, Tonart und Struktur. Die
naheliegenden Analyse-Bibliotheken sind fast alle Copyleft.

## Entscheidung

BPM/Beat/Tonart werden **offline (beim Einlesen, per librosa, ISC)** berechnet
und in der lokalen Datenbank gespeichert. On-device läuft nur das Einbetten
(EmbeddingGemma 2).

## Alternativen

| Bibliothek | Lizenz | Folge |
|---|---|---|
| Essentia | AGPLv3 | ❌ greift auch im Netz |
| aubio | GPLv3 | ❌ |
| libKeyFinder | GPLv3 | ❌ |
| QM-DSP | GPLv2+ | ❌ |
| madmom (Code) | BSD | ✅, aber Modelle CC BY-NC-SA ❌ |
| **librosa** | **ISC** | ✅ offline |

## Begründung

- AGPL/GPL-Bausteine in einer geschlossenen App sind ohne Kauf oder
  Quelloffenlegung nicht nutzbar. AGPL greift sogar bei Netzbetrieb.
- librosa ist ISC (frei) und für Batch-Analyse gemacht.
- Die Analyse ist **einmalig** pro Datei und hängt am Datei-Hash (ADR-007). Sie
  muss nicht in Echtzeit laufen, also darf sie offline sein.

## Konsequenzen

- Die Analyse läuft außerhalb der App (Werkzeug) oder als Teil einer
  Einlese-Pipeline; das Ergebnis kommt in die DB.
- Wir müssen eine eigene, kleine Analyse-Kette bauen bzw. librosa portieren.
- Kein AGPL/GPL-Code im Produkt.

## Belege

- `ANDROID-AUTODJ-TOOLCHAIN-2026.md` (Lizenzfallen)
- `PROTOKOLLE.md` Abschnitt 2.3
