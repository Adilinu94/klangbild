# ADR-025 · PCM-Cache auf der Platte statt Songs im RAM

**Status:** vorgeschlagen
**Datum:** 15.10.2026
**Ergänzt:** ADR-001, ADR-010, ADR-024

## Kontext

Der Desktop hält jeden geladenen Song als float32 im RAM: rund 85 MB für vier
Minuten (44 100 Hz, Stereo, float32). Auf dem Handy ist das zu viel. Der
Desktop braucht drei Songs gleichzeitig (aktuell, nächster, übernächster). Als
float32 wären das ~255 MB nur für Audio, dazu Cover, Wellenformen, Profile und
die App selbst.

Der Desktop dekodiert außerdem vollständig, bevor der Song klingt. Auf dem Handy
soll ein angetippter Titel nach ~150 ms starten, nicht erst nach dem ganzen
Dekodieren.

## Entscheidung

Jeder Song, der gespielt oder gebacken wird, wird **einmal** in eine PCM-Datei
dekodiert. Gespeichert wird genau das, was `live.laden()` liefert:

1. dekodieren, auf 44 100 Hz Stereo bringen,
2. mit `gain_db` multiplizieren (nur wenn `settings.lautheit`, sonst 0 dB),
3. `_begrenzen` (Limiter, Decke 0,966) nur, wenn ein Sample über 0,966 liegt,
4. als int16 speichern (`round(x · 32767)`; nach Schritt 3 kann nichts mehr
   übersteuern).

Details:

- **Kopf (16 Byte):** Magic `KBPC`, Version u16, Kanäle u16 (=2), Rate u32
  (=44 100), Frames u32.
- **Zugriff per `mmap` (read-only).** Feeder und Baker lesen daraus.
- **Größe ~42 MB je 4 min.** Höchstens **4 Dateien** behalten (aktuell,
  nächster, übernächster, zuletzt); älteste zuerst löschen. Bei < 500 MB frei
  nur 2.
- **Fortschreitendes Schreiben:** Der Decoder schreibt in Blöcken von 1 s und
  erhöht danach einen atomaren Zähler `framesReady`. Der Feeder liest nie über
  `framesReady`. So startet ein Titel schnell.
- **Limiter blockweise** mit 2 × 20 ms Vorlauf, wie `_begrenzen`; ein Block wird
  erst freigegeben, wenn der Vorlauf dahinter dekodiert ist.
- **Abtastraten-Wandlung** (48 → 44,1 kHz) über Oboes
  `resampler::MultiChannelResampler` (Qualität `High`), keine zusätzliche
  Bibliothek.

## Alternativen

1. **Songs als float32 im RAM wie am Desktop.** Verworfen: ~85 MB je Song,
   mehrere gleichzeitig.
2. **PCM-Cache als int16-Datei auf der Platte (mmap).** **Gewählt.** Halbiert
   die Größe gegenüber float32 und entkoppelt Dekodieren von Wiedergabe.
3. **Erst on demand dekodieren, nichts speichern.** Verworfen: Seek und
   Wiederholung dekodieren dann erneut; der Feeder bekäme Datei-I/O im Pfad.

## Konsequenzen

- Dekodieren, Limiter und Lautheitsskalierung passieren **einmal** je Titel,
  nicht bei jedem Play.
- Der Cache ist Wegwerf-Material (`cacheDir`): jederzeit löschbar, wird neu
  erzeugt. Kein Backup, keine Migration.
- 4 × 42 MB = bis zu 168 MB Cache; die LRU-Grenze hält den Speicher frei.
- `framesReady` erlaubt Wiedergabe vor Abschluss der Dekodierung; ein Seek
  hinter `framesReady` wartet (kurze Stille, kein Absturz).
- Android-Version `analysisVersion = "android-0.3.0"`; importierte
  Desktop-Daten behalten `"0.3.0"` (ADR-012/013 bleiben gültig, weil der
  PCM-Cache nicht die Analyse ist).

## Belege

- ADR-001, ADR-010 (zwei Decoder-Slots), ADR-024
- `prototyp/klangbild/live.py` (`laden`, `_begrenzen`)
- `BAUPLAN-ANDROID.md` §4.3, §5.5, §5.10
