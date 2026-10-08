# ADR-012 · Analyse mit permissiven Modellen statt librosa

**Status:** angenommen
**Datum:** 08.10.2026
**Löst ab:** ADR-005

## Kontext

ADR-005 wollte BPM, Beat-Raster und Tonart „offline per librosa" rechnen. Zwei
Probleme:

1. librosa ist Python. Auf dem Handy des Nutzers läuft es nicht, und ein
   Desktop-Werkzeug widerspricht „alles lokal, kein Konto, kein PC nötig".
2. librosa liefert **keine Tonart-Erkennung** und **keine Downbeats**. Genau
   die braucht der Auto-DJ.

## Entscheidung

| Wert | Werkzeug | Lizenz |
|---|---|---|
| Beats + Downbeats | **Beat This!** (JKU Linz), auf Android über ONNX/LiteRT | MIT (Code und Gewichte laut Ports; vor Release im Original-Repo prüfen) |
| Tempo (BPM) | aus den Beat-Abständen abgeleitet | eigen |
| Tonart + Camelot | **eigene Implementierung**: Chroma + Key-Profile (z. B. Krumhansl) | eigen |
| Lautheit (LUFS) | **libebur128** (Android), pyloudnorm (PC) | MIT |
| Energie-Kurve, Abschnitte | eigene Implementierung (RMS, Neuheits-Kurve) | eigen |

Im PC-Prototyp (ADR-011) laufen dieselben Verfahren in Python. Auf Android
laufen sie on-device, im Hintergrund, am Hash gebunden (ADR-007, ADR-013).

## Alternativen

| Option | Folge |
|---|---|
| librosa offline (ADR-005) | ❌ kein Key, kein Downbeat, nicht on-device |
| Essentia, aubio, libKeyFinder, QM-DSP | ❌ AGPL/GPL |
| madmom | ❌ Modelle CC BY-NC-SA, DBN-Nachbearbeitung nicht kommerziell |
| **Beat This! + Eigenbau** | ✅ |

## Begründung

- Beat This! ist aktueller Stand der Technik für Beat- und Downbeat-Erkennung
  und braucht keine madmom-Nachbearbeitung (nur Peak-Picking).
- Tonart-Schätzung aus Chroma und Profilen ist ein bekanntes Verfahren.
  Verfahren sind frei, nur fremder Code wäre es nicht.
- Dieselben Werkzeuge auf PC und Android: Die Genauigkeit, die wir im Prototyp
  messen, gilt auch für die App.

## Konsequenzen

- Lizenzprüfung Beat This! (README zu Trainingsdaten) vor dem Release.
- Genauigkeit wird in Phase 0.2 gemessen. Tracks mit niedrigem Vertrauen werden
  nur überblendet.
- Die Analysezeit auf dem Handy ist unbekannt und wird in Phase 3 gemessen.

## Belege

- Beat This!: https://huggingface.co/papers/2407.21658 · Code und Gewichte:
  https://github.com/CPJKU/beat_this
- libebur128: https://github.com/jiixyj/libebur128
- `ANDROID-AUTODJ-TOOLCHAIN-2026.md` §3 (Lizenzlage der Analyse-Tools)

## Ergänzung 08.10.2026 · Belege und Plan B/C

**Belege (Recherche 08.10.2026):**
- Beat This!: **Code und veröffentlichte Gewichte stehen unter MIT** (README,
  LICENSE). Modelle: `final0` ~78 MB, **`small0` ~8,1 MB** – letzteres der
  Kandidat für das Handy. Einschränkung im Repo: einzelne **Trainingsdateien**
  sind urheberrechtlich geschützt oder stehen unter eingeschränkten
  CC-Lizenzen; das ist nicht das Gewicht, aber vor dem Release zu dokumentieren.
- Vorverarbeitung ist Teil der Genauigkeit: **mono 22 kHz** und die Spektrogramm-
  Parameter des Repros müssen auf PC und Android gleich sein.
- libebur128: reines C, **MIT** – läuft unverändert im NDK.
- Portierung: `mosynthkey/beat_this_cpp` (MIT, C++ mit **ONNX**-Gewichten,
  chunked Inference); daneben ein Rust-Port (ONNX Runtime, MIT).

**Plan B/C (neu):** Fällt EmbeddingGemma 2 in Phase 0.1 durch, gilt:
1. **Plan B** – anderer Encoder (CLAP). **Lizenz vor Einsatz belegen**: MuQ und
   MuQ-MuLan sind CC-BY-**NC** 4.0, OpenL3-Gewichte sind nicht-kommerziell,
   musicnn ist unklar – alle drei scheiden aus, solange nichts anderes belegt ist.
2. **Plan C** – **kein** Text-Encoder: „klingt ähnlich" über eigene Merkmale
   (MFCC/Timbre-Statistik, Spektralmerkmale, Energie). „Suche mit Worten" und
   „Stimmung" (ADR-015) entfallen dann; das Produkt ändert sich, also braucht es
   ein eigenes ADR und einen Roadmap-Eintrag.
3. **Plan B'** – eigenes Modell auf permissiven Gewichten (eigener ADR).

Kein stiller Wechsel: Jeder Weg bekommt eine eigene Nummer.
