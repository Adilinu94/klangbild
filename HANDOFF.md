# Handoff: nächster Chat

Stand: 20.10.2026, Branch `main`, letzter Commit `9c1e3ae`.

## Ziel

Auto-DJ-App (Klangbild): Android-App, die Titel analysiert und Übergänge wie ein DJ plant.
Analyse (M10) ist fast fertig, die Konsole ist angefangen.

## Stand auf einen Blick

- `./gradlew :core:test` grün, **58 Tests**.
- App baut und läuft auf dem Gerät (Pixel, Android, per adb verbunden).
- Analyse je Titel funktioniert und wird gespeichert; sie erscheint im Player.

## Was fertig ist

**Analyse-Kette (Kotlin, `android/core`)**

| Baustein | Datei | Prüfung |
|---|---|---|
| Taktraster | `Taktraster.kt` | 4 Golden-Fälle |
| Bandtrennung, Pegel, Chroma je Takt | `ProfilBau.kt` | Golden `profil_berechnen` |
| Tonart + Camelot | `TonartSchaetzung.kt` | 12 Goldens + Kammerton |
| Welle | `Welle.kt` | 3 Goldens |
| Lautheit (LUFS) | `Lautheit.kt` | 3 Goldens + Cache-Test |
| Mel für Beat This! | `Mel.kt` | Golden 151×128, 1e-4 |
| Cache → 22,05 kHz mono | `Abtastung.kt` | 2 Tests |
| Analyse-Datei | `TitelAnalyse.kt` | 8 Tests |
| Cache-Grenze (4 Dateien, 800 MB) | `PcmCache.kt` | 2 Tests |

**Engine (`android/engine`)**

- `BeatThis.kt`: final0-ONNX aus dem Asset, Chunks 1500/6, Nachbearbeitung wie der C++-Port.
  Gerätetest mit 120-BPM-Metronom grün.
- `Player.spiele(..., nurDekodieren = true)`: füllt nur den Cache, startet nichts.

**App (`android/app`)**

- `Spielmodell` rechnet nach dem Dekodieren Tonart, LUFS, Beats, Downbeats, Raster und Profil
  und speichert sie unter `filesDir/analyse/<id>.json`.
- Player zeigt `Am · 8A · 71 BPM · −5.2 LUFS · 32 Takte`.
- Knöpfe: PAUSE/PLAY, NAECHST, STOPP, PLAN, WEG.

## Offen, in dieser Reihenfolge

1. **PLAN nutzt die falsche Liste.** `planeNaechsten()` nimmt den nächsten Eintrag aus `liste`.
   Beim Öffnen über die Suche ist das nur der eine Treffer, also derselbe Titel, und die
   Funktion bricht still ab. Lösung: das Spielmodell braucht zusätzlich die vollständige
   Bibliotheksliste; PLAN nimmt daraus den nächsten Titel. Ohne Ziel kurzen Hinweis zeigen
   („KEIN ZIEL").
2. **Rückmeldung während der Vorbereitung prüfen.** `bereitetVor` und die Zeile
   „ZIEL WIRD ANALYSIERT …" sind eingebaut, auf dem Gerät aber noch nie sichtbar geworden,
   weil Punkt 1 den Aufruf verhindert hat.
3. **Übergang starten.** Aus `RegiePlanung.Plan` die gebackene Blende über `AutoDjPlayer`
   starten (Backen über `AutoDjController`, dann `AutoDjPlayer` mit `abS`/`einS`).
   Danach zwei Titel analysieren und den Übergang auf dem Gerät hören.

## Befehle

```powershell
cd "G:\AI Agentur\Audioplayer\android"
.\gradlew.bat :core:test                     # 58 Tests
.\gradlew.bat :app:assembleDebug             # App bauen
.\gradlew.bat :engine:connectedDebugAndroidTest   # Beat-This-Test auf dem Gerät
```

Installieren und prüfen (Pfad zu adb anpassen):

```powershell
$adb = "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe"
& $adb install -r app\build\outputs\apk\debug\app-debug.apk
& $adb shell "run-as de.klangbild cat files/analyse/<id>.json"
```

## Fallstricke

- **Modell nicht im Repo:** `*.onnx` ist in `.gitignore`. Nach dem Klonen einmal
  `powershell -ExecutionPolicy Bypass -File werkzeuge/hole_beat_this.ps1` laufen lassen
  (79,2 MB, prüft SHA-256 `c5c1466e…9ccbd`).
- **Gerätespeicher:** Die APK ist durch das Modell groß. Der PCM-Cache ist auf 4 Dateien
  und 800 MB begrenzt; vor dieser Grenze wuchs er auf 1,7 GB und blockierte die Installation.
- **Speicher beim Profil:** `ProfilBau.profil` braucht den ganzen Titel als Stereo-Float.
  Deshalb wird ab 15 Mio Frames (rund 6 Minuten) kein Profil gerechnet, nur Raster und Beats.
- **BPM:** Beat This! liefert bei dem Testtitel 71 BPM (halbes Tempo). Das ist die Ausgabe
  desselben Modells wie am Desktop, also kein Fehler. Der Desktop-Vergleich (Tor G-A) steht
  noch aus.
- **Raster beginnt vor dem Titel** (erster Wert −0,22 s). Unschädlich, aber beim Rechnen
  beachten.
- **Deutsche Namen:** Code und Kommentare sind durchgehend deutsch, ohne Umlaute in
  Bezeichnern. Bitte beibehalten.

## Wichtigste Dateien

```
android/core/src/main/kotlin/de/klangbild/core/    Analyse und Planung
android/engine/src/main/kotlin/de/klangbild/engine/BeatThis.kt, Player.kt
android/app/src/main/kotlin/de/klangbild/wiedergabe/Spielmodell.kt
android/app/src/main/kotlin/de/klangbild/ui/Bildschirme.kt
BAUPLAN-ANDROID.md                                  §7.2 Beat This!, Analysetabelle ab Zeile 1676
```
