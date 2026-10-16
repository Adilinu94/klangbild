# ADR-026 · Analyse und Stems vom PC importieren, nicht auf dem Handy rechnen

**Status:** vorgeschlagen
**Datum:** 15.10.2026
**Ergänzt:** ADR-005, ADR-012, ADR-013, ADR-018

## Kontext

Der Desktop-Prototyp hat 332 mischbare Titel bereits analysiert: BPM,
Downbeats, Tonart (Camelot), Lautheit, Energie, Abschnitte – und je Titel ein
Takt-Profil (`profil.py`) **mit Stem-Pegeln** (Gesang, Drums, Bass, Rest).

Auf Android müsste dieselbe Analyse erst gebaut werden (M10): Decoder,
Chroma/Key, LUFS, Energie, Abschnitte, Wellenform, Beat This! ONNX, Profil. Das
ist viel Arbeit und bringt eine zweite Fehlerquelle (Android-Decoder ≠
ffmpeg/librosa, anderes Beat-Modell).

Die Regie braucht vor allem die **Stem-Pegel** aus dem Profil: ohne sie ist
`Profil.gesang()` `None` und die Gesangs-Prüfung entfällt. Sie kommt damit
sofort auf das Handy.

## Entscheidung

**M3: PC-Import zuerst.** Ein Export der Desktop-Analyse wird auf das Handy
gebracht und über den Datei-Hash (ADR-007/013) zugeordnet. Erst danach (M10)
analysiert das Handy selbst.

1. **Export (Python, T3.1):** `python -m klangbild export-android <ziel.zip>`.
   Je mischbarem Titel: `audio_hash`, Dateiname, Größe, `features` (Zeile mit
   `analyse_version="0.3.0"`), Profil-JSON aus `cache/profil/` **mit
   Stem-Pegeln** (Stufe S1; fehlen sie, vorher mit Stem-Vorrat rechnen),
   Wellenform als `.bin`, Cover-JPEG. Dazu eine `index.json` mit Versionen und
   der Zahl der Profile mit Stems.
2. **Import (App, T3.3):** Einstellungen > Diagnose > „Analyse vom PC
   importieren" (SAF `ACTION_OPEN_DOCUMENT`, zip). Zuordnung über den Hash.
   Importierte Daten behalten `analyse_version="0.3.0"`.
3. **Eigene Android-Analyse (M10)** bekommt die eigene Kennung
   `"android-0.3.0"`, weil Decoder und Beat-Modell anders sind. Beide
   Versionen liegen nebeneinander; nichts wird still überschrieben.

## Alternativen

1. **Gleich auf dem Handy analysieren (M10 zuerst).** Verworfen: hält die Regie
   lange ohne Stem-Profile, verdoppelt die Analyse-Implementierung.
2. **PC-Import zuerst, eigene Analyse später.** **Gewählt.** Nutzt das, was
   fertig und gehört ist; entkoppelt die Engine (M1–M9) von der ML-Portierung.
3. **Nur importieren, nie on-device analysieren.** Verworfen: neue Titel auf
   dem Handy (ohne PC-Lauf) hätten keine Analyse.

## Konsequenzen

- Ab M3 gibt es echte Musik mit echter Analyse auf dem Handy; die Regie kennt
  den Gesang über die importierten Stem-Pegel (Stufe S1).
- Der Zuordnungs-Hash muss bitgleich zum Desktop sein: T3.2 portiert
  `hashutil.py` nach `HashUtil.kt` (Golden: 20 Dateien, Hash identisch). Die
  Analyse hängt an der Datei, nicht am Pfad (ADR-013).
- Zwei Analyse-Versionen koexistieren; `status` und Dubletten-Filter (F22)
  müssen beide kennen.
- Der Import ist ein Dateiaustausch, kein Netzwerkvorgang: das Abnahmekriterium
  „kein Netzwerkverkehr" bleibt erfüllt (der Nutzer bewegt die Datei selbst).
- Ohne PC-Lauf bleiben neue Titel bis M10 unanalysiert (im Bericht als offener
  Punkt).

## Belege

- ADR-005, ADR-012, ADR-013, ADR-018
- `prototyp/klangbild/hashutil.py`, `profil.py` (Version 2, Stem-Pegel)
- `BAUPLAN-ANDROID.md` M3 (§11), §4.2, §9.3 (Stufe S1)
