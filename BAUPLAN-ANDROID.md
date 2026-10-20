# Bauplan · Klangbild für Android (Parität mit dem Desktop-Mixer)

Stand 2026-10-14 · Grundlagen:
- Desktop-Mixer `prototyp/klangbild/` (Stand nach Runde 3, 308 Tests grün)
- djay-Analyse `D:\rev-tools\rea-main\docs\djay-automix-reverse-engineering.md` (Teile 2–6)
- `ui/UI-KONZEPT-KLANGBILD.md`, `ui/DIRECTION.md`, `ui/mockups/klangbild.html`
- ADR-001 … ADR-022, `ROADMAP-KLANGBILD.md` (Phasen 3–6), `PLAN-AUTODJ-V2.md`

Dieses Dokument ist für eine umsetzende KI geschrieben, auch für eine schwächere.
Jede Aufgabe nennt Ziel, Dateien, die Python-Vorlage, die Schritte und den Test,
mit dem sie fertig ist. Wer eine Aufgabe umsetzt, liest zuerst §0 und §12.

---

## 0 · Arbeitsregeln für die umsetzende KI (Pflicht)

1. **Python ist die Spezifikation.** Jede Funktion, die portiert wird, hat eine
   Vorlage in `prototyp/klangbild/*.py`. Bei Widerspruch zwischen diesem Plan und
   dem Python-Code gilt der Python-Code. Bei Unklarheit: Python-Code lesen, nicht raten.
2. **Golden-Tests statt Augenmaß.** Für jede portierte Rechenfunktion erzeugt
   Python Referenzdaten (§12.2). Die Portierung ist erst fertig, wenn ihr Test
   gegen diese Daten grün ist. Toleranzen stehen in §12.3. Eine Toleranz nur
   lockern, wenn der Grund im Code als Kommentar steht und im Fortschrittsbericht.
3. **Nur bauen, was hier steht.** Keine zusätzlichen Features, Optionen,
   Abstraktionen „für später". Fehlt etwas, das für eine Aufgabe nötig ist: im
   Bericht nennen, nicht still erfinden.
4. **Audio-Callback ist heilig** (djay-Regel, §1): kein `new/malloc`, kein Lock,
   kein Datei-I/O, kein Log, kein JNI, keine Exception im Oboe-Callback.
5. **Eine Aufgabe = ein Commit.** Erst wenn Build und Tests grün sind. Commit-Text
   auf Deutsch: was und warum.
6. **Kein Netzwerk.** Das Manifest bekommt keine `INTERNET`-Berechtigung. Keine
   Bibliothek einbauen, die Netzwerk braucht (auch kein Crash-SDK).
7. **Namen:** Code-Bezeichner auf Englisch (Android-Konvention), Oberflächentexte
   auf Deutsch. Die Zuordnung der deutschen Python-Namen steht in §14.
8. **Fortschrittsbericht** nach jeder Aufgabe: was gebaut, welcher Test grün,
   was offen oder unsicher ist.

---

## 1 · Was aus der djay-Analyse für uns wichtig ist

Die djay-Analyse hat sechs Teile. Für Klangbild zählt vor allem die
**Engine- und Performance-Disziplin** (Teile 2, 4, 5). Den Auto-DJ selbst kann
Klangbild bereits besser als djay: Regie mit Takt-Profilen, Rezepte,
Selbstkontrolle und Lernen.

### 1.1 Übernehmen (belegt bei djay, passt zu uns)

| djay-Befund | Wo im Dokument | Was wir daraus machen |
|---|---|---|
| Ein Render-Callback, Matrix-Summe, Oboe statisch eingebaut | §11.4, §61, §84.1 | Ein Oboe-Callback. Er kopiert nur aus einem Ringpuffer (§5.3). |
| Audio-Thread RT-sicher, Datenaustausch lockfrei (`farbot`) | §40, §42 | SPSC-Ringpuffer und `std::atomic`. Keine Sperre im Callback (§0 Regel 4). |
| Gain-Rampen statt Sprüngen (`ar_applyChannelVolumesToBuffer`) | §22.4 | 10-ms-Rampe bei Pause, Start, Seek und Flush (§5.3). |
| XRun-Zähler, Latenz messen (`getXRunCount`, `calculateLatencyMillis`) | §41.3, §49 | Underflow-Zähler im Zustand, wie Desktop `underflows`. |
| Ausgabelatenz in der Uhr verrechnen (`updateAsyncLatency`) | §41.6 | Position aus `oboe::AudioStream::getTimestamp` (ADR-016, §5.4). |
| Stream-Neustart serialisieren („Restart … already in progress") | §47 | Ein Neustart zur Zeit. Beim Gerätewechsel (`onErrorAfterClose`) neu öffnen. |
| Audio-Fokus, Kopfhörer abgezogen (`ARJavaAudioFocusHandler`, `BecomingNoisy`) | §47, §70 | `AudioFocusRequest` und `ACTION_AUDIO_BECOMING_NOISY` in Kotlin (§6.4). |
| Analyse offline und gecacht (`analysedBits`, `forceReanalysis`) | §43.6 | Hash plus `analysis_version` (ADR-007/013). Nie im Abspielpfad rechnen. |
| Stems offline und im Disk-Cache (`AUMCacheManager`) | §27.4, §43.5 | Gilt für M11 (Stems). Nie im Callback, nie warten (ADR-018). |
| Modelle quantisiert, kleines Modell fest, großes optional | §66 | Beat This! `small0` im APK. Stem-Modell nur nach Lizenzklärung (§9). |
| Adaptive Qualität bei Last und Hitze | §48 | Backzeit messen. Bei Hitze Hintergrund-Analyse pausieren (§10.3). |
| Denormals aus, `-O3`, NEON | §50 | Compiler-Flags in `CMakeLists.txt` (§3.3). |
| Equal-Power `cos/sin(p·π/2)` | §22.6 | Schon im Desktop (`mix.equal_power_blende`). 1:1 portieren. |
| Analyse-Raten 22 050 und 44 100 Hz | §11.3 | Wie Desktop: Analyse mono 22 050 Hz, Wiedergabe stereo 44 100 Hz. |
| Wellenform vorberechnet, kompakt, Farbe je Band | §23.8, §30 | Desktop `welle.py` (3 Bänder, uint8). Nur für gespielte Titel speichern (§4.4). |
| Automix-Bereiche auf der Übersichts-Wellenform (`OverviewWaveformWithAutomixRanges`) | §30.2 | Geplanten Ausstieg und Blende als Markierung auf der Wellenform (§8). |
| Auto-Fill-Quelle (Queue, aktuelle Playlist, Match) | §25.3 | Warteschlange zuerst, sonst wählt der Auto-DJ aus der aktuellen Liste (§6.2). |

### 1.2 Bewusst anders als djay

| djay | Klangbild | Grund |
|---|---|---|
| Echtzeit-Signalgraph je Deck (Stretch, EQ, FX im Callback) | **Vorausbacken**: Blende im Hintergrund fertig rechnen, Callback kopiert nur | So läuft der Desktop bereits, getestet und gehört. CPU im Callback ≈ 0. Ergebnis ist mit Python vergleichbar (Golden-Tests). Djay braucht Echtzeit für manuelle Decks und Scratchen, die wir nicht haben. |
| `LowLatency` + `Exclusive` + MMAP mit Geräte-Quirks | `PowerSaving` + `Shared` (ADR-016) | Der Auto-DJ plant im Voraus. Latenz ist egal, Akku nicht. MMAP fällt weg und damit die Quirk-Liste. |
| zplane Elastique | Signalsmith Stretch (MIT, ADR-003) | Lizenz. Gleiche Bibliothek wie im Desktop (`python-stretch`). |
| TFLite-Beat-Tracker + DBN + Segmentmodell | Beat This! ONNX (`small0`) + eigene BPM-Regression + Profil-Etiketten | Gemessen genau (Tempo 100 %, Downbeat 96,3 %). Abschnitte kommen aus dem Profil. |
| Qt/QML, GNUstep, ObjC unter Android | Kotlin + Jetpack Compose, C++ nur für Audio/DSP | Kernlogik plattformneutral halten (djay-Lehre §64), aber ohne ObjC-Exotik. |
| Thread-Affinität manuell setzen | Nicht setzen | Oboe gibt dem Callback schon hohe Priorität. Manuelle Affinität ist geräteabhängig und fehleranfällig. Nur nachrüsten, wenn M12 Aussetzer misst. |
| Sentry (Crash-Upload) | Lokale Absturzdatei, kein Upload | Abnahmekriterium „kein Netzwerkverkehr". |
| Verschlüsselte Modelle | Unverschlüsselt | Beat This! ist MIT. Schutz bringt nichts. |

### 1.3 Ignorieren (kein Desktop-Gegenstück)

DVS/Vinyl/Turntables, MIDI-Controller, Sampler/Looper-Packs, FX-Bank
(Macro-FX), Streaming-Dienste, Mikrofon, Aufnahme, manuelle Decks mit
Crossfader. Der Desktop hat nichts davon, also gehört es nicht zur Parität.

### 1.4 Was der Teil 6 der djay-Analyse veraltet beschreibt

Teil 6 kennt den Stand vom 11.10. Seitdem gilt:
- Regie, Profil, Loops, Effekte, Selbstkontrolle und Lernen sind fertig (`regie.py`, `profil.py`).
- Stems liegen auf dem PC für ganze Songs vor (Ogg Vorbis, ~24 MB je Titel).
  Für 8 000 Titel auf dem Handy wären das ~190 GB. Darum ist Stem-Vorrat auf
  Android ausgeschlossen. Nur Fenster oder nur Profil-Werte (§9).
- Die Regie arbeitet auch ohne Stems: `Profil.gesang()` ist dann `None`, die
  Gesangs-Prüfung entfällt. Mit dem PC-Import (M3) kommen aber die Profile
  **mit** Stem-Pegeln je Takt aufs Handy. Dann kennt die Regie den Gesang auch
  ohne ein Stem-Modell auf dem Handy (Stufe S1 in §9).
- Der Desktop-Mixer nutzt **keine** Einbettungen (`vektor=None`). Für die
  Parität braucht Android also kein EmbeddingGemma. Es bleibt Phase 6.

---

## 2 · Zielbild und Funktionsumfang

Die Android-App kann alles, was der Desktop-Mixer kann, mit der Oberfläche aus
dem UI-Konzept. Dazu kommt, was eine Android-Musik-App braucht.

### 2.1 Funktionsliste (Parität)

| # | Desktop-Funktion | Python-Vorlage | Android | Screen | Meilenstein |
|---|---|---|---|---|---|
| F1 | Bibliothek mit Anzahl, Suche nach Titel oder Tonart | `mixer.html` `ladeBibliothek`, `/api/bibliothek` | MediaStore-Scan statt Upload | 01, 02, 07 | M3, M10 |
| F2 | Analyse neuer Titel mit Fortschritt | `mixer.Mixer._worker`, `pipeline.track_analysieren` | WorkManager + Statuszeile `[3/12 ANALYSIERT]` | 01, 08 | M10 |
| F3 | Abspielen, Pause, Springen per Wellenform | `live.play/pause/seek` | Engine + Media3-Fassade | 03, 09 | M2, M4 |
| F4 | WEITER (Übergang ab nächstem Takt oder nächster Phrase) | `live.weiter`, `regie._a_kandidaten(sofort)` | Knopf im Player, Kopfhörer „Next" | 03, 04 | M8 |
| F5 | AUTO-DJ an/aus | `live.autodj_setzen` | Roter Schalter | 04, 05 | M8 |
| F6 | Mix-Stil (Manuell/Kurz/Ausgewogen/Lang), Spielanteil | `einstellungen`, `regie` | Einstellungen + Konsole | 05, 08 | M7, M9 |
| F7 | Regie: Ausstieg, Einsatz, Länge, Rezept je Paar | `regie.planen` | Kotlin-Port | — | M7 |
| F8 | „Anderer Übergang (n/3)" | `live.anders` | Pill in der Konsole | 05 | M8 |
| F9 | Vorschau „WIRD GEBACKEN …" mit Titel, Rezept, Grund | `live._vorschau` | Konsole + Player-Zusatz | 04, 05 | M8 |
| F10 | NÄCHSTER-Zeile mit Grund, Takte, Tonart, BPM | `zustand()["naechster"]` | Player + Konsole | 04, 05 | M9 |
| F11 | Deck-Ansicht: beide Wellen während der Blende, Kurven (Lautstärke, Bass, Mitten, Höhen, Filter, Echo, Hall, Loop, Gesang, Drums), Legende | `mixer.html` Canvas `decks`, `uebergang.kurven` | Compose-Canvas | 05 | M9 |
| F12 | Farb-Wellenform des ganzen Songs, Phrasen, Abschnitte (Intro/Drop/…) | `welle.py`, `/api/track` | Waveform-Seekbar | 03, 04 | M9 |
| F13 | Cover-Scheibe, BPM, Tonart, LUFS | `cover.py` | Scheibe + Datenzeile | 03 | M9, M10 |
| F14 | Warteschlange: einreihen, entfernen, hoch/runter, leeren | `live.einreihen/entfernen/verschieben/leeren` | Queue-Sheet | 06 | M8, M9 |
| F15 | „Perfekte Reihenfolge" | `live.sortieren`, `plan.sortiere_alle` | Knopf im Queue-Sheet | 06 | M7, M8 |
| F16 | Verlauf der Übergänge (Protokoll) | `zustand()["verlauf"]` | Konsole | 05 | M9 |
| F17 | Alle Einstellungen inkl. Manuell-Bausteine | `einstellungen.Einstellungen` | Einstellungen + Unterseite „Übergang manuell" | 08 | M7, M9 |
| F18 | Lernen (Vorlieben je Rezept) | `live._lernen` | JSON-Datei im App-Speicher | — | M8 |
| F19 | Energiebogen bei der Titelwahl | `live._autodj_wahl` | Kotlin-Port | — | M8 |
| F20 | Selbstkontrolle, 3 Pläne, Sicherheits-Blend | `live._auto_backen`, `regie.pruefen` | Kotlin + Native | — | M8 |
| F21 | Lautheit −14 LUFS, TP ≤ −1 dBTP, Limiter | `live.gain_db`, `live.laden`, `uebergang._begrenzen` | PCM-Cache (§4.3) | — | M2 |
| F22 | Dubletten-Filter (gleiche Aufnahme) | `live._gleicher_titel` | Kotlin-Port | — | M8 |
| F23 | Stems (Gesangsschutz, Drums zuerst, Acapella) | `stems.py`, `uebergang.mischen_stems` | **gesperrt bis M11** | — | M11 |
| F24 | Underflow-Zähler, Statuszeile | `zustand()["underflows"]` | Einstellungen > Diagnose | 08 | M1, M9 |
| F25 | Playlists anlegen und bearbeiten (wie Poweramp) | — (neu) | Bibliothek > Wiedergabelisten | 01, 02 | M9 |
| F26 | „Optimale Reihenfolge" je Playlist | `live.sortieren`, `plan.sortiere_alle` | Playlist-Toolbar | 02 | M7, M9 |
| F27 | Auto-DJ an/aus überall: Player, Playlist, Mini-Player, Benachrichtigung | `live.autodj_setzen` | Schalter + eigener Session-Befehl | 03, 04, 09 | M4, M9 |
| F28 | Cover wischen = nächster/voriger Titel, 3D-Ausblendung | — (neu) | Player | 03 | M9 |
| F29 | Wellenform wischen = Position ändern, Play-Knopf in der Mitte | — (neu) | Player | 03 | M9 |

### 2.2 Dazu für Android (kein Desktop-Gegenstück, aber Pflicht)

| # | Funktion | Umsetzung | Meilenstein |
|---|---|---|---|
| A1 | Hintergrundwiedergabe, Benachrichtigung, Sperrbildschirm | `MediaSessionService` + Media3 `DefaultMediaNotificationProvider` | M4 |
| A2 | Kopfhörertasten, Bluetooth, Android Auto | eine `MediaSession` über `SimpleBasePlayer` (ADR-017) | M4 |
| A3 | Audio-Fokus, Kopfhörer abgezogen → Pause | `AudioFocusRequest`, `BecomingNoisyReceiver` | M4 |
| A4 | Bibliothek: Kategorien, Ordner, Interpreten, Playlists | Room + MediaStore (UI-Konzept §3.1) | M9 |
| A5 | Analyse nur am Ladegerät (Einstellung) | WorkManager `setRequiresCharging` | M10 |

### 2.3 Bewusst nicht im Umfang

Tags schreiben, Widget, Sleep-Timer, 10-Band-EQ, Energie-Reise über Stunden,
Wunsch in Worten, Gemma, Einbettungen, Stem-Vorrat für ganze Songs. Das sind
Roadmap-Phase-6-Themen. Sie werden erst gebaut, wenn der Nutzer sie anfordert.

---

## 3 · Architektur

### 3.1 Grundsatz: Vorausbacken wie im Desktop

Der Desktop (`live.py`) arbeitet so:
1. Ein **Back-Thread** wählt den nächsten Titel, plant den Übergang und rendert
   die ganze Blende als fertigen Puffer (`uebergang.backen`).
2. Der **Audio-Callback** (`Wiedergabe.fuellen`) kopiert nur Samples. An der
   Wechselstelle schaltet er die Referenz auf den Puffer von B um.

Android übernimmt genau das. Neu ist nur, dass Songs nicht ganz im RAM liegen,
sondern als PCM-Datei (§4.3), und dass zwischen Datei und Callback ein
Zuführ-Thread (Feeder) und ein Ringpuffer sitzen.

```
                    Kotlin (app, core)                                  C++ (engine, libklangbild.so)
 ┌───────────────────────────────────────────────┐        ┌──────────────────────────────────────────────┐
 │ UI (Compose) ── StateFlow ◄── AutoDjController │  JNI   │ Baker-Pool (N Threads, niedrige Prio)         │
 │      │                         │  (Port live.py)│◄──────►│  backen(): Warp(Signalsmith), DSP, Limiter    │
 │      ▼                         ▼                │        │       │ schreibt Blende in RAM (BakedBuffer)  │
 │ KlangbildPlayer (SimpleBasePlayer, Media3)      │        │       ▼                                       │
 │      │                    Regie / SetPlanner    │        │ Timeline (Spuren aus Segmenten)               │
 │ MediaSessionService       (Port regie/plan.py)  │        │       │                                       │
 │                                                 │        │ Feeder-Thread ── liest Segmente ──► OutputRing│
 │ Analyse-Worker (WorkManager) ── PcmCache ───────┼───────►│ Decoder (AMediaCodec) → PCM-Cache-Datei       │
 │ Room-DB, Profile, Wellen, Cover                 │        │                                  │ SPSC        │
 └───────────────────────────────────────────────┘        │ Oboe-Callback ◄──────────────────┘ (kopiert)  │
                                                            └──────────────────────────────────────────────┘
```

### 3.2 Module (Gradle)

| Modul | Art | Inhalt | Warum getrennt |
|---|---|---|---|
| `:core` | reines Kotlin/JVM | Einstellungen, Profil, Regie, SetPlanner, Kurven-Daten, Lernen, Camelot, Golden-Test-Leser | Tests laufen auf dem PC in Sekunden, ohne Gerät |
| `:engine` | Android-Library mit CMake | C++: Oboe, Decoder, PCM-Cache, Timeline, Feeder, Baker, DSP, Analyse-DSP. Kotlin: `NativeEngine` (JNI-Fassade), ONNX-Aufruf für Beat This! | Ein natives Modul `libklangbild.so` (djay-Lehre §74: wenige große Libs laden schneller) |
| `:app` | Android-App | Compose-UI, `MediaSessionService`, `KlangbildPlayer`, `AutoDjController`, Room, WorkManager | Android-Oberfläche und Lebenszyklus |

### 3.3 Technische Eckdaten

| Punkt | Wert | Begründung |
|---|---|---|
| Projektordner | `G:\AI Agentur\Audioplayer\android\` | neben `prototyp/` |
| Paket | `de.klangbild` (Platzhalter, vor Store-Eintrag festlegen) | — |
| Erzeugung | Android Studio „Empty Activity (Compose)". Versionen aus der Vorlage übernehmen, dann in `gradle/libs.versions.toml` pflegen | Aktuelle, zueinander passende Versionen ohne Raten |
| minSdk | **29** (Android 10) | AAudio vorhanden, Scoped Storage einheitlich. Weniger Sonderfälle. |
| target/compileSdk | aktuellste stabile | Play-Vorgabe |
| ABI | `arm64-v8a`; zusätzlich `x86_64` nur für Emulator-Tests | djay §62: 64 Bit Pflicht |
| NDK | **r28 oder neuer** | Play verlangt 16-KB-Seitenausrichtung nativer Libs. Ab r28 Standard. Prüfen: `zipalign -c -P 16 -v 4 app.apk`. |
| C++ | C++20, `-O3 -ffp-contract=fast`, kein `-ffast-math` (würde NaN-Prüfungen der Analyse kippen) | djay §50 |
| Denormals | im Callback und in Baker-Threads FTZ setzen: `fesetenv`/`__builtin_aarch64_set_fpcr` (FZ-Bit 24) | djay §50 |
| Abhängigkeiten C++ | Oboe **als Quellcode** (Git-Submodul unter `engine/src/main/cpp/third_party/oboe`, Apache-2.0, statisch gelinkt wie bei djay §61; so ist auch Oboes Resampler `oboe::resampler::MultiChannelResampler` nutzbar, der im Prefab-Paket nicht öffentlich ist), Signalsmith Stretch (MIT, header-only, **selber Commit wie python-stretch 0.3.1**), KissFFT (BSD-3) | Lizenzen kommerziell frei |
| Abhängigkeiten Kotlin | Compose (BOM), Media3 `session` + `common` 1.11.x (kein ExoPlayer nötig, §3.4), Room, WorkManager, DataStore nicht nötig (JSON-Datei), Coil 3 (Cover-Bilder aus Dateien), ONNX Runtime Android (MIT) | — |
| Netz | keine `INTERNET`-Berechtigung | Abnahmekriterium |

### 3.4 Eine Engine für alles (neues ADR-023, vorgeschlagen)

ADR-017 lässt offen, ob ExoPlayer ganz entfällt („Option 3"). Der Plan nimmt
Option 3: **Auch der normale Modus läuft über die eigene Engine.** Ohne Auto-DJ
ist der Übergang ein nahtloser Schnitt am Songende, genau wie im Desktop
(`_backen_ergebnis`, `autodj_an=False`).

Gründe:
- Kein Zustandswechsel zwischen zwei Playern (Risiko aus djay-Analyse §88).
- Der Desktop macht es genauso und ist getestet.
- Gapless gibt es geschenkt (die Timeline schließt Segmente direkt aneinander).

Media3 dient nur als Fassade (`SimpleBasePlayer`) für Session, Benachrichtigung
und Android Auto. Die Entscheidung als ADR-023 festhalten (Aufgabe T0.4).

### 3.5 Threads

| Thread | Sprache | Priorität | Aufgabe | Darf |
|---|---|---|---|---|
| Oboe-Callback | C++ | hoch (Oboe) | Ring lesen, Rampen, Zähler | nur Atomics, nur vorab allokierte Puffer |
| Feeder | C++ | `-16` (`THREAD_PRIORITY_AUDIO`) | Segmente → OutputRing, Wechselstelle, Position-Journal | Mutex mit Kotlin-Befehlen, mmap lesen |
| Decoder | C++ | `0` | Datei → PCM-Cache | Datei-I/O |
| Baker-Pool | C++ | `10` (`setpriority`) | `backen`, Warp-Aufträge parallel | alles außer Audio-Callback berühren |
| Planer | Kotlin (1 Thread, Coroutine-Dispatcher) | Hintergrund | Port der Back-Schleife `live.starten.schleife` (alle 250 ms `vorbereiten`) | JNI-Aufrufe in den Baker |
| UI | Kotlin Main | — | Compose | nur StateFlow lesen |
| Analyse | WorkManager | Hintergrund | Decode, Beat This!, Key, LUFS, Profil | pausiert bei Hitze (§10.3) |

---

## 4 · Daten und Formate

### 4.1 Room-Datenbank (Port von `db.py`)

```kotlin
@Entity(tableName = "tracks", indices = [Index("audioHash"), Index(value = ["uri"], unique = true)])
data class TrackEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val uri: String,            // content://media/external/audio/media/123
    val displayName: String,    // Dateiname ohne Endung = Titel wie Desktop Eintrag.titel
    val title: String?, val artist: String?, val album: String?,   // MediaStore-Tags (nur Anzeige)
    val relativePath: String?,  // fuer die Ordner-Ansicht
    val sizeBytes: Long, val mtime: Long, val durationMs: Long,
    val audioHash: String?, val container: String?, val hashFrom: Long?, val hashTo: Long?,
    val addedAt: Long,
)

@Entity(tableName = "features", primaryKeys = ["trackId", "analysisVersion"])
data class FeaturesEntity(
    val trackId: Long, val analysisVersion: String,
    val bpm: Double?, val beatsJson: String?, val downbeatsJson: String?,
    val keyName: String?, val keyCamelot: String?, val keyConfidence: Double?,
    val lufs: Double?, val truePeak: Double?,
    val energyJson: String?,       // [[t, dB], ...] wie energie_json
    val sectionsJson: String?,     // [t, ...] wie abschnitte_json
    val status: String,            // "ok", "zu_kurz", "fehler: ..."
    val addedAt: Long,
)
```

```kotlin
@Entity(tableName = "playlists")
data class PlaylistEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val name: String,
    val createdAt: Long, val updatedAt: Long,
    val autoDj: Boolean = true,          // beim Abspielen dieser Playlist Auto-DJ an
    val sortedAt: Long? = null,          // zuletzt "Optimale Reihenfolge"
    val previousOrderJson: String? = null,   // Reihenfolge davor (fuer "Rueckgaengig")
)

@Entity(tableName = "playlist_entries", primaryKeys = ["playlistId", "position"],
        indices = [Index("trackId")])
data class PlaylistEntryEntity(val playlistId: Long, val position: Int, val trackId: Long)
```

- `analysisVersion` auf Android: `"android-0.3.0"` (eigene Kennung, weil
  Decoder und Beat-Modell anders sind als im Desktop). Importierte Desktop-Daten
  (M3) behalten `"0.3.0"`.
- Tabellen `embeddings`, `aufgaben`, `bewertungen` werden **nicht** portiert.
- Die Eintragsliste für den Mixer entspricht `mixer.bibliothek_laden` und
  `autodj.lade_tracks`. Lies beide, bevor du `LibraryRepository.mixable()` baust:
  nur Titel mit `status="ok"`, BPM und Downbeats, ohne Dubletten.

### 4.2 Dateien im App-Speicher (`context.filesDir` bzw. `cacheDir`)

| Pfad | Inhalt | Format | Vorlage |
|---|---|---|---|
| `files/settings.json` | Einstellungen | **dieselben Schlüssel wie** `ergebnisse/mixer-einstellungen.json` | `einstellungen.speichern` |
| `files/regie-lernen.json` | Vorlieben je Rezept | `{"outro_loop": 0.3, ...}` | `live._lernen` |
| `files/profil/<trackId>.json` | Takt-Profil | wie `Profil.als_dict` (Version 2) | `profil.speichern` |
| `files/cover/<trackId>.jpg` | Cover 256 px | JPEG | `cover.vorschau` |
| `cache/welle/<trackId>.bin` | Wellenform | 4 × uint8 je Spalte (peak, r, g, b), Kopf 8 Byte (Spaltenzahl u32, HOP u16, Version u16) | `welle.berechnen` |
| `cache/pcm/<trackId>_<gainMilliDb>.pcm` | dekodierter Song nach `laden()` | int16 stereo interleaved, 44 100 Hz, Kopf 16 Byte (§4.3) | `live.laden` |
| `files/crash.txt` | letzter Absturz | Text | — |

Alle JSON-Formate sind identisch zum Desktop. Dann können Golden-Tests und der
PC-Import (M3) dieselben Dateien lesen.

### 4.3 PCM-Cache (neues ADR-025, vorgeschlagen)

Problem: Der Desktop hält jeden Song als float32 im RAM (~85 MB für 4 min).
Auf dem Handy sind drei davon zu viel.

Lösung: Jeder Song, der gespielt oder gebacken wird, wird **einmal** in eine
Datei dekodiert. Gespeichert wird genau das, was `live.laden()` liefert:
1. dekodieren, auf 44 100 Hz stereo bringen,
2. mit `gain_db` multiplizieren (nur wenn `settings.lautheit`, sonst 0 dB),
3. `_begrenzen` (Limiter mit Decke 0,966) nur wenn ein Sample über 0,966 liegt,
4. als int16 speichern (`round(x * 32767)`, nach Schritt 3 kann nichts mehr
   übersteuern).

- Kopf (16 Byte): Magic `KBPC`, Version u16, Kanäle u16 (=2), Rate u32 (=44100), Frames u32.
- Zugriff per `mmap` (read-only). Der Feeder und der Baker lesen daraus.
- Größe ~42 MB je 4 min. Höchstens **4 Dateien** behalten (aktuell, nächster,
  übernächster, zuletzt). Älteste zuerst löschen.
- **Fortschreitendes Schreiben:** Der Decoder schreibt in Blöcken von 1 s und
  erhöht danach einen atomaren Zähler `framesReady`. Der Feeder liest nie über
  `framesReady`. So startet ein angetippter Song nach ~150 ms, nicht erst nach
  dem ganzen Dekodieren.
- Limiter beim fortschreitenden Schreiben: Blöcke mit 2 × 20 ms Vorlauf wie in
  `_begrenzen` (der Python-Code arbeitet schon blockweise mit Rand). Der Block
  wird erst freigegeben, wenn der Vorlauf dahinter dekodiert ist.
- Abtastraten-Wandlung (48 → 44,1 kHz): `oboe::resampler::MultiChannelResampler`
  (liegt im Oboe-Quellcode unter `src/flowgraph/resampler/`, Qualität `High`).
  Keine weitere Bibliothek. Falls der Header in der gewählten Oboe-Version
  woanders liegt: im Oboe-Repo suchen, nicht nachbauen.

### 4.4 Wellenform-Speicher

`welle.berechnen` liefert ~100 Spalten je Sekunde, das sind ~96 KB je Titel.
Für 8 000 Titel wären das 770 MB. Darum:
- Die Wellenform wird beim Anlegen des PCM-Caches mitgerechnet (aus dem
  22-kHz-Mono, §7.2) und unter `cache/welle/` gespeichert. LRU-Grenze 200 MB.
- Für die Track-Liste und die 64-Balken-Seekbar reicht die Energiekurve aus
  `features.energyJson` (UI-Konzept §3.2 Punkt 5). Sie ist schon in der DB.

### 4.5 Übergangsplan (ADR-019) zwischen Kotlin und C++

Kotlin plant, C++ rendert. Die Übergabe ist **ein JSON-Objekt**, dessen
Einstellungsfelder exakt die Felder von `einstellungen.Einstellungen` sind
(nach `replace(e, **felder)` in `regie.plan_aus`). Beispiel:

```json
{
  "gen": 17,
  "a": {"spur": 5, "trackId": 12, "bpm": 124.0, "camelot": "8A",
        "downbeats": [0.51, 2.45, ...], "fein": [[4.0, 0.012], ...], "abschnitte": [190.2], "gainDb": -2.1},
  "b": {"trackId": 40, "pcmPath": ".../40_-3100.pcm", "bpm": 125.1, "camelot": "9A",
        "downbeats": [...], "fein": [...], "abschnitte": [...], "gainDb": -3.1},
  "abS": 182.4, "jetztS": 179.1, "weiter": false,
  "ausS": 190.2, "einS": 0.48,
  "aGesang": [0,0,0,1, ...] ,
  "einst": { "modus": "ausgewogen", "art": "eigen", "takte": 16, "lautstaerke": "nahtlos",
             "eq": "profi", "filter": "keiner", "effekt": "keiner", "effekt_ein": "keiner",
             "loop": "auto", "loop_start": -1, "loop_ein": 0, "loop_ein_mal": 0,
             "bass_takt": 8, "tempo_modus": "rampe", "max_bpm": 5.0, "keylock": true, "...": "..." }
}
```

Antwort des Bakers (`BakeResult`):

```json
{
  "handle": 991,            // nativer Speicher der neuen Spur B
  "startN": 8043520,        // Blendenbeginn im Puffer von A (Frames)
  "orig": [...], "buf": [...],   // Spur.orig / Spur.buf von B
  "info": { "art": "eigen", "takte": 16, "sync": true, "bpm_a": 124.0, "bpm_b": 125.1,
            "modus": "rampe", "stems": false, "blende_s": 30.97, "a_orig_start": 182.39,
            "a_orig_pro_s": 1.00433, "kurven": {"a": {...}, "b": {...}},
            "a_loop": [...], "loop_wahl": {"start_takt": 4, "schlaege": 16, "guete": 0.88} }
}
```

`info` hat exakt die Schlüssel von `uebergang.backen` (Zeile `info = {...}`).
Kotlin ergänzt `rezept`, `grund`, `plan`, `energie_schritt`, `zeiten`, wie
`live._auto_backen` es tut.

---

## 5 · Native Engine (C++) im Detail

Ordner `android/engine/src/main/cpp/`:

```
CMakeLists.txt
jni_bridge.cpp          // alle JNI-Funktionen, nichts sonst
engine/AudioEngine.{h,cpp}     // Oboe-Stream, Callback
engine/OutputRing.h            // SPSC float stereo
engine/Timeline.{h,cpp}        // Spuren, Segmente, Wechselstelle
engine/Feeder.{h,cpp}          // Thread: Segmente -> OutputRing
engine/PositionJournal.h       // Ausgabe-Frame -> (Spur, Frame)
decode/Decoder.{h,cpp}         // AMediaExtractor/AMediaCodec -> float
decode/PcmCache.{h,cpp}        // Datei schreiben, mmap lesen, framesReady
bake/Baker.{h,cpp}             // Port uebergang.backen
bake/Warp.{h,cpp}              // Port warp, _warp_keylock, WSOLA-Naht
bake/Mixing.{h,cpp}            // Port mischen, mischen_eigen, _huellen, kurven
bake/Filters.{h,cpp}           // band_teilen (sosfiltfilt), _sweep, Biquads
bake/Effects.{h,cpp}           // _echo, _nass (Echo/Delay/Hall), Hall-IR aus Asset
bake/Loops.{h,cpp}             // _loop_plan, _loopen, loop_waehlen, _intro_loop
bake/Limiter.{h,cpp}           // _begrenzen
bake/ThreadPool.{h,cpp}        // Baker-Pool, niedrige Prioritaet
analysis/...                   // M10: Mel, Chroma/Key, LUFS, Energie, Abschnitte, Welle, Profil
third_party/signalsmith-stretch/, third_party/kissfft/
```

### 5.1 Spur und Segmente

Eine **Spur** entspricht `uebergang.Spur`: ein abspielbarer Puffer plus die
Taktachsen `orig`/`buf`. Auf Android ist der Puffer eine Liste von Segmenten:

```cpp
struct Segment {
  enum class Kind { Pcm, Baked } kind;
  // Pcm: Frames [from, to) aus einer PCM-Cache-Datei (Song im Original)
  std::shared_ptr<PcmCache> pcm; int64_t from = 0, to = 0;
  // Baked: fertig gerechnete Frames im RAM (Blende, ggf. gedehnter Rest)
  std::shared_ptr<BakedBuffer> baked;   // float stereo interleaved
  int64_t length() const;
};
struct Spur {
  int32_t id;              // fortlaufend, von Kotlin vergeben
  int64_t trackId;
  std::vector<Segment> segments;
  int64_t length;          // Summe der Segmentlaengen
  int64_t read(int64_t pos, int64_t n, float* out) const;  // liest ueber Segmentgrenzen, hinter dem Ende 0
};
```

So entstehen die Spuren:

| Fall (Desktop) | Segmente der Spur B |
|---|---|
| `Spur.roh(e, audio)` (play, Schnitt am Ende) | `[Pcm(0, N)]` |
| `backen`, nicht sync (`puffer = blende + b_audio[start+len(blende):]`) | `[Baked(blende+Fahne), Pcm(start+len(blende), N)]` |
| `backen`, sync `rampe`/`a_an_b` (`puffer = blende + rest`, `rest = b_audio[rest_orig[0]:]`) | `[Baked(blende+Fahne+1 s Limiter-Rand), Pcm(...)]` |
| `backen`, sync `b_an_a` (Rest wird gedehnt) | **Stufe 2 (T6.6):** `[Baked(blende+ganzer gedehnter Rest)]` |
| `_intro_loop` von B | wie oben; die Blende enthält die Wiederholungen schon |

Wichtig: Der Desktop addiert die Effektfahne (`nachlauf`) auf B hinter der
Blende und limitiert danach bis `len(blende) + n_fahne + RATE`. Das Baked-Segment
muss darum bis genau dorthin reichen. Danach geht es mit `Pcm` weiter.

`b_an_a` dehnt den ganzen Rest von B. Das sind bis zu 85 MB float im RAM.
Darum Stufe 2: Der Baker legt den gedehnten Rest als int16-Datei im PCM-Cache
ab (`<trackId>_warp_<gen>.pcm`) und hängt sie als `Pcm`-Segment an. `b_an_a`
gibt es nur als manuelle Einstellung; die Regie setzt immer `rampe`.

### 5.2 Timeline und Feeder (Port von `Wiedergabe.fuellen` und `_umschalten`)

Zustand (nur der Feeder schreibt, Befehle laufen über einen `std::mutex`, weil
der Feeder **kein** Echtzeit-Thread ist):

```cpp
struct TimelineState {
  std::shared_ptr<Spur> current;  int64_t pos = 0;      // Feeder-Leseposition in current
  std::shared_ptr<Spur> next;     int64_t switchAt = -1; int32_t nextGen = 0;
  bool playing = false;
  uint32_t serial = 0;            // steigt bei play/seek: Ring wird geleert (ADR-010)
};
```

Feeder-Schleife (Port von `fuellen`):
1. Warte, bis im OutputRing Platz für 1 024 Frames ist (Bedingungsvariable oder
   2-ms-Schlaf).
2. Unter dem Mutex: `grenze = next ? switchAt : current->length`.
   `n = min(1024, grenze - pos)`. Lies `n` Frames aus `current` ab `pos`.
3. Wenn `pos == grenze`: hat es `next`, dann **umschalten**: `current = next`,
   `pos = 0`, `next = null`, und ein Ereignis `Switched{spurId, gen,
   outputFrame}` in die Ereignis-Queue an Kotlin legen. Sonst `playing = false`
   und Ereignis `Ended`.
4. Schreibe die Frames in den Ring. Trage `(outputFrameIndex, spurId, pos)` ins
   Positions-Journal ein (Ringpuffer mit 256 Einträgen).

`setNext(spur, switchAt, gen)` gibt `false` zurück, wenn `switchAt < pos`.
Das ist genau die Prüfung `ergebnis[0] < self.pos` aus `live._uebernehmen`:
Der Übergang kam zu spät und wird verworfen.

`pos` des Feeders liegt bis zu 1 s vor dem, was man hört. Für Planung und
„zu spät" zählt `pos` (dahinter kann nichts mehr geändert werden). Für die
Anzeige zählt die gehörte Position (§5.4).

### 5.3 OutputRing und Oboe-Callback

- `OutputRing`: SPSC, float stereo, Kapazität **44 100 Frames (1 s)**, Größe
  Zweierpotenz (65 536 Frames), Indizes `std::atomic<uint64_t>` mit
  `memory_order_acquire/release`. Vorab allokiert.
- Oboe-Stream: `Direction::Output`, `PerformanceMode::PowerSaving`,
  `SharingMode::Shared`, `Format::Float`, `ChannelCount 2`, `SampleRate 44100`,
  `SampleRateConversionQuality::Medium`, `Usage::Media`,
  `ContentType::Music`. Callback-Klasse `AudioStreamDataCallback` plus
  `AudioStreamErrorCallback`.
- Callback (pseudocode, **nichts anderes darin**):

```cpp
DataCallbackResult onAudioReady(AudioStream*, void* data, int32_t n) {
  float* out = static_cast<float*>(data);
  uint32_t want = flushSerial.load(acquire);
  if (want != seenSerial) {                 // play/seek: Altes weg, mit 10-ms-Rampe aus
    ring.discardAll(); seenSerial = want; ramp.startIn();
  }
  if (!playing.load(acquire)) { ramp.toZero(out, n, lastFrame); return Continue; }
  int32_t got = ring.read(out, n);          // kopiert hoechstens n Frames
  if (got < n) { std::fill(out + 2*got, out + 2*n, 0.f); underflows.fetch_add(1); }
  ramp.apply(out, n);                       // Ein-/Ausblendrampen, 441 Frames
  framesPlayed.fetch_add(got, release);
  return DataCallbackResult::Continue;
}
```

- Pause: Kotlin setzt `playing=false`. Der Callback blendet die nächsten 441
  Frames (10 ms) aus und gibt dann Stille. Weiter: Rampe ein. Der Feeder füllt
  bei Pause nicht nach. Das entspricht dem Desktop, wo `fuellen` bei
  `spielt=False` Nullen liefert.
- `underflows` zählt wie im Desktop nur echte Lücken bei laufender Wiedergabe.
- Fehler-Callback `onErrorAfterClose` (Gerät gewechselt, Bluetooth weg): Stream
  neu öffnen. Ein Neustart zur Zeit (atomares Flag). Ring und Timeline bleiben.

### 5.4 Position (gehört, nicht gelesen)

1. `framesPlayed` (Callback) minus Ausgabelatenz ergibt den Ausgabe-Frame, der
   gerade hörbar ist. Latenz aus `stream->getTimestamp(CLOCK_MONOTONIC)`:
   `latencyFrames = framesWritten - timestamp.position - (now - timestamp.time)·rate`.
   Wenn `getTimestamp` fehlschlägt: `calculateLatencyMillis()`, sonst 0.
2. Im Positions-Journal den Eintrag mit diesem Ausgabe-Frame suchen. Ergebnis:
   `(spurId, framesInSpur)`.
3. Kotlin rechnet `framesInSpur / 44100` mit `Spur.zu_original` in
   Originalsekunden um (wie `zustand()["aktuell"]["pos_s"]`).

`NativeEngine.poll(LongArray)` liefert in einem Aufruf: gehörte `spurId`,
gehörte `frameInSpur`, Feeder-`spurId`, Feeder-`pos`, `playing`, `underflows`,
`latencyFrames`. Kotlin ruft das 10-mal pro Sekunde (kein JNI pro Frame).

### 5.5 Decoder

- Kotlin öffnet die Datei: `contentResolver.openFileDescriptor(uri, "r")`,
  übergibt `fd`, Offset und Länge an C++ (`AMediaExtractor_setDataSourceFd`).
- `AMediaCodec` dekodiert nach PCM16 oder float. Kanäle: mono → beide Kanäle
  gleich, >2 → die ersten zwei.
- Rate ≠ 44 100: `MultiChannelResampler` (§4.3).
- Formate: MP3, AAC/M4A, FLAC, OGG/Vorbis, Opus, WAV. Was `AMediaExtractor`
  nicht kann, bekommt Status `fehler: format` und wird in der Bibliothek
  ausgegraut (Desktop: `UPLOAD_ENDUNGEN`).
- Encoder-Verzögerung (MP3/AAC): `AMediaFormat` `encoder-delay` und
  `encoder-padding` auswerten und am Anfang/Ende abschneiden. Sonst liegen alle
  Beats ~25 ms daneben gegenüber der Analyse, wenn die Analyse anders dekodiert
  hätte. Weil Analyse und Wiedergabe auf Android **denselben** Decoder nutzen,
  ist es konsistent, solange beide gleich verfahren.

### 5.6 Baker (Port von `uebergang.backen`)

Eingang und Ausgang siehe §4.5. Ablauf exakt wie `backen` (Zeilen 1034–1188).
Unterfunktionen und ihre Python-Vorlagen:

| C++ | Python-Vorlage | Hinweise |
|---|---|---|
| `regulaer()` | `uebergang.regulaer` | Seit Runde 17 ohne Ankerpunkt: Schlag-Lage = häufigste von 16 Stufen (±1 geglättet), Kreismittel der Downbeats in ±¼ Schlag darum (`atan2(mean(sin), mean(cos))`), Eins = Schlag mit den meisten Downbeats (`bincount`), Drift = Median der Reste in ±16 s (`np.median`), `np.interp`. `np.round` = Banker's Rounding (`std::nearbyint` mit `FE_TONEAREST`). |
| `taktraster()` | `uebergang.taktraster` | Seit Runde 19: `regulaer` + `np.interp` der Fein-Anker-Knoten (`Eintrag.fein`, aus `cache/anker.json` → Import M3). Alle Raster (Profil, Regie, Backen, Anzeige) laufen hierüber. |
| `raster()` | `uebergang.raster` | — |
| `periode()` | `uebergang._periode` | Median wie numpy (gerade Anzahl: Mittel der beiden mittleren). |
| `ausstieg()`, `einstieg()` | `uebergang.ausstieg`, `einstieg` | `abar` aus `Spur.buf` von A. |
| `warp()` | `uebergang.warp`, `_warp_keylock` | §5.7 |
| `mischen()` | `uebergang.mischen` | Arten `eq`, `filter`, `echo`, `schnitt`, `crossfade`. `eq` ruft `mix._fade_segment(basstausch=True)` mit `_bass_rampen`. |
| `huellen()` | `uebergang._huellen` | Alle Kurven, auch `profi` mit `db_ein/db_aus`. |
| `mischenEigen()` | `uebergang.mischen_eigen` | Reihenfolge: Loop → Sweep (TP, HP) → `_trocken` (Bänder × Fader, `_deckeln`) → Effekt-Sends. |
| `sweep()` | `uebergang._sweep` | Koeffizienten je 1 024-Block, Zustand läuft durch, Start eingeschwungen (§5.8). |
| `bandSplit()` | `mix.band_teilen` | Nullphasig wie `sosfiltfilt` (§5.8). |
| `nass()` | `uebergang._nass` | Hall: FFT-Faltung mit der IR aus dem Asset `hall_ir.f32` (§5.9). Echo-Verzögerung seit Runde 19 aus dem Schlag dort, wo der Send endet (`_schlag_bei`, `_send_ende`; auch `mischen_stems` mit `takt_n`), nicht aus dem Schnitt über die Blende. |
| `echoArt()` | `uebergang._echo` | — |
| `loopPlan()`, `loopen()`, `achtel()` | `_loop_plan`, `_loopen`, `_achtel` | Seit Runde 19: weicht die Länge eines Loop-Stücks um > 0,2 % von der Quelle ab (Tempo-Rampe), wird es mit `warp` (Keylock wie eingestellt) auf seinen Platz gedehnt. |
| `loopWaehlen()` | `uebergang.loop_waehlen`, `_beat_merkmale`, `_aehnlich` | FFT 4 096 mit Hann-Fenster, 16 log. Bänder 40 Hz–16 kHz. |
| `introLoop()` | `uebergang._intro_loop` | gibt Audio, Raster und Rückrechnung zurück |
| `deckeln()`, `taktDb()`, `trocken()` | `_deckeln`, `_takt_db`, `_trocken` | — |
| `begrenzen()` | `uebergang._begrenzen` | §5.10 |
| `kurven()` | `uebergang.kurven`, `kurven_eigen` | 64 Punkte, auf 3 Stellen gerundet, ins `info`-JSON |
| `loopInfo()` | `uebergang.loop_info` | — |

**Stems in M6 ausgeschaltet:** `stem_quelle` ist `null`. Damit gilt der Zweig
`stem_grund = "Stems aus/nicht installiert"`. Stem-Arten fallen auf `eq`
(Manuell) bzw. `eigen` (Regie) zurück, genau wie im Python-Code.

Parallelität: Der Desktop dehnt A und B (und Stem-Spuren) gleichzeitig
(`_parallel`). Der Baker gibt die Warp-Aufträge an den Pool (`ThreadPool`,
`max(2, cores - 2)` Threads, Priorität 10).

### 5.7 Warp mit Signalsmith Stretch

Vorlage: `uebergang._dehnen`, `_warp_keylock`, `warp`. Konstanten:
`NAHT = 1024`, `SUCHE = 441`, `KONTEXT = 8192`, `MAX_LAUF = 30 * 44100`.

- **Signalsmith-Version:** denselben Commit nutzen, den `python-stretch` 0.3.1
  einbindet (im GitHub-Repo von python-stretch unter `extern/` bzw. als
  Submodul nachsehen). Sonst weichen die Golden-Tests ab.
- **Ein Aufruf = ein eigenständiges Stück** (Docstring von `_dehnen`).
  `python-stretch` macht je `process()`-Aufruf: `presetDefault(2, 44100)`,
  Zeitfaktor setzen, Eingang einspeisen, `flush`, danach `reset`. Den genauen
  Ablauf (Länge der Ausgabe, wie `seek` den Anfang vorlädt) **aus dem Quellcode
  von python-stretch übernehmen** (Datei mit der Bindung von `Stretch.process`).
  Die Ausgabelänge muss `round(len(eingang) / faktor)` entsprechen, sonst passt
  die Rechnung `basis = round(links / f)` in `_warp_keylock` nicht.
- `faktor` = Eingangslänge / Ausgangslänge (wie `timeFactor` im Python-Code).
- Unter 0,2 % Abweichung kein Signalsmith, sondern lineares Resampling je Takt
  (`resample.resample_linear` + `_auffuellen`), wie in `warp`.
- WSOLA-Naht (`_ausrichten`): Korrelation über ±441 Samples. Für die Suche die
  normierte Kreuzkorrelation direkt rechnen (881 Verschiebungen × 1 024 Samples
  ≈ 0,9 Mio. Multiplikationen, schnell genug).

### 5.8 Filter exakt wie scipy

**`band_teilen` (nullphasig, `sosfiltfilt`):**
- Koeffizienten: Butterworth 4. Ordnung als SOS. **Nicht selbst entwerfen.** Das
  Golden-Werkzeug (T0.2) exportiert die SOS-Matrizen für alle benötigten
  Frequenzen bei 44 100 Hz (Tiefpass 200, 2 000, 2 500; dazu 3 000 und 5 000 für
  `_nass`) und bei 22 050 Hz (für die Analyse). Als `constexpr`-Tabellen
  einbauen.
- `sosfiltfilt` nachbauen (scipy, `padtype="odd"`):
  1. `padlen = 3 * (2 * nSections + 1)` (für diese Filter: 15). Ist das Signal
     ≤ `padlen` lang: kausal filtern wie `sosfilt` (Python-Rückfall in `mix._filtern`).
  2. Ungerade Erweiterung: links `2*x[0] - x[padlen..1]`, rechts
     `2*x[n-1] - x[n-2..n-1-padlen]`.
  3. Anfangszustand `zi = sosfilt_zi(sos) * xext[0]`, vorwärts filtern.
  4. Umdrehen, `zi * y[-1]`, filtern, wieder umdrehen, Ränder abschneiden.
  5. Rechnen in `double`, Ergebnis float.
- `sosfilt_zi` für Direktform II transponiert: je Abschnitt mit Gleichstromgewinn
  `G = (b0+b1+b2)/(1+a1+a2)`: `z1 = b2 - a2·G`, `z0 = b1 - a1·G + z1`. Für die
  Kaskade wird der Zustand von Abschnitt k mit dem Produkt der Gewinne der
  Abschnitte davor multipliziert.
- `high = signal - low` (komplementär), wie im Python-Code.

**`_sweep` (kausal, zeitvariabel):** RBJ-Biquads je 1 024-Block mit
Q 0,5412 und 1,3066 (Formeln in `_biquads`), Grenzfrequenz Tiefpass
`20000 · 0,01^menge`, Hochpass `20 · 100^menge`. Startzustand eingeschwungen
(`sosfilt_zi(sos[0]) * x[0]`). 10-ms-Übernahme am Anfang/Ende, wenn offen.

### 5.9 Hall-IR als Asset

`_hall_ir()` nutzt `np.random.default_rng(7)`. Diesen Zufallsgenerator nicht
nachbauen. Das Golden-Werkzeug speichert die fertige IR als
`engine/src/main/assets/hall_ir.f32` (float32 stereo, ~0,85 MB). Die Faltung
(`oaconvolve`) als FFT-Overlap-Add mit KissFFT, Blockgröße 16 384.

### 5.10 Limiter (`_begrenzen`)

Decke 0,966 (−0,3 dBFS). Algorithmus wie Python: Spitze je Frame
(max |L|,|R|), Fenster 20 ms (ungerade, `int(0.02*44100) | 1` = 883),
`g = min(1, decke / maxfilter(spitze))`, dann `minfilter`, dann
Mittelwertfilter (alle mit derselben Fenstergröße, Randbehandlung wie
`scipy.ndimage` Modus `reflect`). Nur Blöcke mit Spitzen über der Decke
bearbeiten (Blockgröße 65 536, Rand 2 × Fenster).

`scipy.ndimage`-Ränder: Modus `reflect` heißt `d c b a | a b c d | d c b a`
(Randwert wird wiederholt). Das ist **nicht** numpy `reflect`. Golden-Test
prüft genau den Rand.

### 5.11 JNI-Schnittstelle (`NativeEngine.kt`)

```kotlin
object NativeEngine {
    init { System.loadLibrary("klangbild") }
    external fun start(assetManager: AssetManager, cacheDir: String): Boolean
    external fun stop()
    // PCM-Cache: dekodiert (fortschreitend) und liefert sofort ein Handle
    external fun openPcm(trackId: Long, fd: Int, offset: Long, length: Long,
                         gainDb: Float, cachePath: String): Long
    external fun pcmFramesReady(pcm: Long): Long          // -1 = Fehler
    external fun pcmTotalFrames(pcm: Long): Long          // -1 = noch unbekannt
    external fun pcmReadMono22k(pcm: Long, out: FloatArray): Int   // fuer Analyse/Profil (M10)
    external fun releasePcm(pcm: Long)
    // Spuren
    external fun createRawSpur(spurId: Int, pcm: Long): Long        // Spur.roh
    external fun play(spur: Long, startFrame: Long)                 // serial++, current=spur
    external fun setNext(spur: Long, switchAt: Long, gen: Int): Boolean   // false = zu spaet
    external fun clearNext()
    external fun setPlaying(playing: Boolean)
    external fun seek(frame: Long)                                  // in der aktuellen Spur
    external fun releaseSpur(spur: Long)
    // Backen (blockiert den aufrufenden Planer-Thread, nie den Main-Thread)
    external fun bake(requestJson: String, aSpur: Long, bPcm: Long): String   // BakeResult-JSON
    external fun loopQuality(aPcm: Long, takteS: DoubleArray, i: Int, L: Int,
                             gesang: IntArray?): Double            // regie._loop_guete
    external fun checkBlend(spur: Long, frames: Long, nTakte: Int): DoubleArray   // Pegel je Takt fuer regie.pruefen
    // Zustand und Ereignisse
    external fun poll(out: LongArray)        // §5.4
    external fun pollEvents(): String?       // JSON-Liste: Switched/Ended/Error
}
```

Regeln: JNI-Aufrufe nie aus dem Callback. Handles sind `Long` (Zeiger in eine
Tabelle, nicht roh). Jedes `open`/`create` hat ein `release`. Kotlin ruft
`release*` in `finally`.

---

## 6 · Kotlin-Seite im Detail

### 6.1 `:core` — reine Logik (Ports)

| Kotlin-Datei | Python-Vorlage | Inhalt |
|---|---|---|
| `Settings.kt` | `einstellungen.py` | Data class mit denselben Feldern und Standardwerten, `ARTEN`, `AUSWAHL`, `TAKTE`, `GRENZEN`, `fromJson(roh, basis)` = `aus_dict` (ungültige Werte ignorieren, Grenzen klemmen), `toJson`, `regieSettings(e)` = `regie_einst` |
| `Profile.kt` | `profil.py` | `Profile` mit `takte, baender, gesamt, stems, rasterOk, dauer, chroma`, abgeleitete Reihen mit Memo (`lazy`), `etiketten()`, `phraseVon`, `taktBei`, JSON lesen/schreiben (Version 2) |
| `Regie.kt` | `regie.py` | `planen`, `_rangliste`, `_bewerten`, `_rezept`, `_bass_takt`, `_intro_loops`, `pruefen` (bekommt Pegel je Takt von `NativeEngine.checkBlend`), `LOOP_GUETE_MIN`, `LAENGEN`, `WEITER_LAENGE`, `LOOP_REZEPTE` |
| `SetPlanner.kt` | `plan.py` | `harmonie_note`, `energie_note`, `rangliste`, `naechster`, `sortiere_alle` |
| `Camelot.kt` | `keyestimate.camelot_nachbarn`, `uebergang._harmonisch` | — |
| `Curves.kt` | — | nur Datentypen für `info.kurven` (Anzeige) |
| `NumpyCompat.kt` | — | Hilfen mit numpy-Semantik (§13): `percentile`, `median`, `searchsorted`, `interp`, `roundHalfEven`, `floorDiv` |

**`sortiere_alle` bei 8 000 Titeln:** Der Python-Code ist O(n²) gierig (siehe
`shortcut`-Kommentar). Bei 8 000 Titeln sind das 32 Mio. Notenberechnungen. In
Kotlin dauert das einige Sekunden. Erlaubte Abkürzung: Titel einmal nach BPM
sortieren und je Schritt nur Kandidaten im Fenster `aktuell ± max_bpm` prüfen
(Binärsuche). Das Ergebnis bleibt identisch, weil `rangliste` alles außerhalb
der Grenze sowieso verwirft, solange es Kandidaten in der Grenze gibt. Den Fall
„keiner in der Grenze" mit dem vollen Pool behandeln. Golden-Test gegen
Python auf 332 Titeln.

### 6.2 `AutoDjController` (Port von `live.Wiedergabe`)

Liegt in `:app`, weil er Engine und DB braucht. Er ist die einzige Stelle, die
Wiedergabe-Zustand hält. UI und `KlangbildPlayer` rufen nur ihn.

Felder (1:1 aus `Wiedergabe.__init__`): `bibliothek`, `einst`, `spur`
(aktuelle Spur mit `orig/buf`), `autodj`, `warteschlange`, `verlauf`,
`gespielt`, `naechste`, `vorschau`, `backt`, `frueh`, `gen`, `backzeit = 2.0`,
`vorher`, `rang`, `letztesRezept`, `vorlieben`, `lernOffen`,
`energieSchritte`.

Methoden und Vorlagen:

| Kotlin | Python | Besonderheit Android |
|---|---|---|
| `play(trackId)` | `play` | `openPcm` → `createRawSpur` → `NativeEngine.play`. Wartet nicht auf das ganze Dekodieren. |
| `pause()` | `pause` | `setPlaying(!spielt)` |
| `seek(origS)` | `seek` | `spur.zuPuffer(origS) * 44100` → `NativeEngine.seek`. Ist die Stelle noch nicht dekodiert, wartet der Feeder (Ring läuft leer = kurze Stille, kein Absturz). |
| `weiter()`, `anders()`, `einreihen()`, `entfernen()`, `leeren()`, `verschieben()`, `sortieren()`, `autodjSetzen()`, `einstellungenSetzen()` | gleichnamig | jede Bedienung ruft `verwerfen()` (`gen++`, `naechste = null`, `NativeEngine.clearNext()`) |
| `vorbereiten()` | `vorbereiten` | läuft auf dem Planer-Thread alle 250 ms (Schleife wie `starten.schleife`); `abS = feederPos/44100 + max(VORLAUF_S, 1.5*backzeit + 1)` |
| `autodjWahl()` | `_autodj_wahl` | Kandidatenpool: alle mischbaren Titel der **aktuellen Liste** (Playlist/Ordner, aus der gestartet wurde), sonst ganze Bibliothek. Sonst identisch inkl. Energiebogen und `_gleicher_titel`. |
| `backenErgebnis()` | `_backen_ergebnis` | Auto aus: `Spur.roh` von B, Wechsel bei `len(a)` |
| `autoBacken()` | `_auto_backen` | Profile laden, `Regie.planen`, Vorschau setzen, bis 3 Pläne (WEITER: 2) backen und prüfen, sonst Sicherheits-Blend `profi_eq` |
| `uebernehmen()` | `_uebernehmen` | `setNext` liefert `false` → verwerfen und protokollieren |
| `onSwitched(event)` | `_umschalten` | Ereignis aus `pollEvents`: Verlauf, Warteschlange, Lernen, Energieschritt, `gen++` |
| `lernen()` | `_lernen` | +0,3 / −1, Grenzen −5…+3, JSON schreiben |
| `zustand()` | `zustand` | wird zu `StateFlow<MixerState>` (gleiche Felder wie das Desktop-JSON) |

Konstanten: `VORLAUF_S = 2.0`, Backzeit gleitend `0.7·alt + 0.3·neu`.
Höchstens 3 PCM-Caches gleichzeitig offen (Desktop: 3 dekodierte Songs).

Stems: `stemsDa = false`, bis M11 fertig ist.

### 6.3 `KlangbildPlayer` (Media3-Fassade, ADR-017)

`class KlangbildPlayer(looper, controller) : SimpleBasePlayer(looper)`

- `getState()`: aus `MixerState` bauen. Playlist = aktueller Titel +
  Warteschlange als `MediaItemData`. Position über
  `PositionSupplier { controller.positionMs() }`.
- Befehle: `COMMAND_PLAY_PAUSE`, `COMMAND_SEEK_IN_CURRENT_MEDIA_ITEM`,
  `COMMAND_SEEK_TO_NEXT` (= `weiter()`), `COMMAND_SET_MEDIA_ITEM`,
  `COMMAND_GET_METADATA`. Kein „Zurück" im Auto-DJ (Desktop hat keins);
  außerhalb des Auto-DJ: „Zurück" = Titelanfang.
- `handleSetPlayWhenReady` → `controller.pause()/play`; `handleSeek` →
  `controller.seek()`.
- Nach jeder Änderung von `MixerState`: `invalidateState()` (höchstens 4×/s,
  sonst bremst die Session).

### 6.4 Service, Fokus, Kopfhörer

- `PlaybackService : MediaSessionService`, `foregroundServiceType="mediaPlayback"`.
- Audio-Fokus selbst anfordern (SimpleBasePlayer macht das nicht):
  `AudioFocusRequest(AUDIOFOCUS_GAIN)` mit `AudioAttributes(USAGE_MEDIA,
  CONTENT_TYPE_MUSIC)`. Verlust → Pause. Kurzer Verlust mit „ducking" → Pause
  (ein DJ-Mix wird nicht leise weitergespielt).
- `ACTION_AUDIO_BECOMING_NOISY` → Pause.
- Engine-Start beim ersten `play`, Stopp, wenn der Service endet.

### 6.5 Bibliothek und Import

- Berechtigung `READ_MEDIA_AUDIO` (API 33+), `READ_EXTERNAL_STORAGE` (≤ 32).
- `MediaStore.Audio.Media` abfragen: `_ID, DISPLAY_NAME, TITLE, ARTIST, ALBUM,
  RELATIVE_PATH, SIZE, DATE_MODIFIED, DURATION`. Neue oder geänderte Einträge
  (Größe/Zeit) → Hash berechnen (Port `hashutil.datei_hash`, liest über
  `openFileDescriptor`) → Analyse-Auftrag.
- Gleicher Hash wie ein bekannter Titel → Analyse übernehmen (ADR-007/013).

### 6.6 Playlists, „Optimale Reihenfolge", Auto-DJ je Playlist

So arbeitet der Nutzer (Wunsch vom 14.10.): Er legt wie in Poweramp Playlists
an, drückt **OPTIMALE REIHENFOLGE** und spielt sie mit oder ohne Auto-DJ ab.

**Anlegen und Bearbeiten**
- Bibliothek > WIEDERGABELISTEN > `+` (Name eingeben).
- Titel hinzufügen: Long-Press auf einen Titel → „Zu Playlist …", oder
  AUSWÄHLEN (Mehrfachauswahl) in „Alle Titel" → „Zu Playlist …".
- In der Playlist: Reihenfolge per Ziehen am Griff ändern (`LazyColumn` mit
  Drag-Griff; Bibliothek `sh.calvin.reorderable`, Apache-2.0), Wischen nach
  links = entfernen (mit „RÜCKGÄNGIG" im Inline-Status, kein Toast).
- Playlists liegen nur in Room (§4.1). Kein Import/Export von M3U (nicht gefordert).

**Optimale Reihenfolge**
- Knopf in der Playlist-Toolbar. Rechnet auf dem Planer-Thread, zeigt
  `[SORTIERE … 12/40]`.
- Algorithmus = Desktop `live.sortieren` beschränkt auf die Titel der Playlist:
  `SetPlanner.sortAll(tracks, max_bpm, harmonie, start, bonus)` mit demselben
  Bonus für gesangsfreie Enden/Anfänge aus den Profilen (Code in `live.sortieren`).
  Start: der Titel, der gerade läuft, falls er in der Playlist ist, sonst der
  erste Titel der Playlist (Nutzer kann ihn vorher nach oben ziehen).
- **Verbesserung für Playlists (klein):** Playlists sind kurz (≤ 500 Titel).
  Nach der gierigen Reihenfolge läuft eine 2-opt-Verbesserung über dieselbe
  Paarnote (`rangliste.note`, als Kosten `1 − note`), höchstens 2 s Rechenzeit.
  Test: Summe der Paarnoten ≥ gierig auf 50 Zufalls-Playlists.
- Ergebnis wird sofort gespeichert. Die alte Reihenfolge landet in
  `previousOrderJson`; „RÜCKGÄNGIG" stellt sie wieder her.
- Zwischen den Zeilen zeigt die Liste je Übergang einen Chip:
  `8A→9A · +1,2 BPM` (grün = harmonisch und in der Tempo-Grenze, gelb =
  über `max_bpm` → wird Echo/Schnitt).

**Abspielen**
- Play in der Playlist: Warteschlange = Playlist ab dem gewählten Titel.
  `autoDj` der Playlist schaltet den Auto-DJ (Schalter in der Toolbar, Wert
  wird je Playlist gespeichert).
- Mit Auto-DJ: Der Controller mischt die Titel **in Playlist-Reihenfolge**
  (Warteschlange hat Vorrang vor der Auto-Wahl, wie im Desktop `vorbereiten`).
- Ende der Playlist: Einstellung „Nach der Playlist" = `stoppen` (Standard) oder
  `passend weiter` (Auto-DJ wählt aus der ganzen Bibliothek, §6.2).

**Auto-DJ ein/aus von überall** (F27): Schalter in Player, Konsole,
Playlist-Toolbar, Mini-Player (Long-Press) und als eigener Befehl in der
Benachrichtigung (`SessionCommand("AUTODJ_TOGGLE")` mit
`CommandButton`; in Media3 1.11 über `MediaSession.setMediaButtonPreferences`,
das ältere `setCustomLayout` ist veraltet). Alle rufen
`controller.autodjSetzen()`.

---

## 7 · Analyse auf dem Gerät (M10)

Bis M10 kommen alle Analysedaten vom PC (M3). Das entkoppelt die Engine von der
ML-Portierung. Erst danach analysiert das Handy selbst.

### 7.1 Schritte je Titel (Port von `pipeline.track_analysieren` + `profil.berechnen`)

| Schritt | Vorlage | Umsetzung | Rate |
|---|---|---|---|
| Dekodieren | `audioio.decodieren` | `Decoder` (§5.5), Mono = Mittel L/R | 22 050 mono und 44 100 stereo in einem Durchgang |
| Mindestlänge 25 s | `config.MIN_SEKUNDEN` | sonst `status="zu_kurz"` | — |
| Tonart | `keyestimate.tonart_schaetzen` (Ensemble-Profil) | C++-Port, Golden-Test | 22 050 |
| LUFS, True Peak | `lufs.integrierte_lautheit`, `lufs.true_peak_dbtp` | C++-Port von `lufs.py` (Filter-Koeffizienten aus dem Python-Code) | 22 050 |
| Energie, Abschnitte | `energy.rms_kurve`, `energy.abschnitte` | C++-Port | 22 050 |
| Beats, Downbeats | `beats.analysieren` (Beat This!) | ONNX Runtime + Vorverarbeitung nach `mosynthkey/beat_this_cpp` (MIT) | 22 050 |
| BPM | `metrics.bpm_aus_beats` (Regression) | Kotlin-Port | — |
| Wellenform | `welle.berechnen` | C++-Port | 22 050 |
| Profil | `profil.berechnen` (ohne Stems) | C++ für Bänder/Chroma (`_db_je_takt`, `_chroma_je_takt`), Kotlin für den Rest | 44 100 |
| Cover | `cover.vorschau` | `MediaMetadataRetriever.embeddedPicture`, auf 256 px, JPEG | — |

### 7.2 Beat This! auf Android

- Modell: `small0` als ONNX (~8 MB) im APK (`assets/beat_this_small0.onnx`).
  Konvertierung mit den Skripten aus `beat_this_cpp` (einmalig am PC).
- Vorverarbeitung (Mel-Spektrogramm) exakt wie Beat This!. Golden-Test: Python
  exportiert für 10 Titel das Spektrogramm, die Modellausgabe und die Beats.
- **Achtung Modellwechsel:** Der Desktop nutzt `final0`. Darum Tor G-A in
  §11: Auf den 332 Desktop-Titeln (aufs Handy kopiert) müssen die
  Android-Werte zu den Desktop-Werten passen. Fällt `small0` durch, wird
  `final0` (78 MB) ins APK gelegt. Diese Entscheidung trifft der Nutzer.
- Ausführung: ONNX Runtime mit XNNPACK-Execution-Provider, 2 Threads. NNAPI
  nicht verwenden (wird von Google abgekündigt; Ergebnisse geräteabhängig).

### 7.3 Arbeitsweise

- `AnalysisWorker : CoroutineWorker`. Ein Titel je Schritt, Fortschritt in der DB.
- Bedingungen: Einstellung „Analyse nur am Ladegerät" (Standard an) →
  `setRequiresCharging(true)`. Manuell gestartet: als Expedited Work mit
  Benachrichtigung `[3/120 ANALYSIERT]`.
- Hitze: `PowerManager.getCurrentThermalStatus() >= THERMAL_STATUS_MODERATE` →
  nach dem aktuellen Titel pausieren, später fortsetzen.
- Läuft die Wiedergabe, analysiert der Worker mit 1 Thread, sonst mit 2.
- Ein Fehler stoppt nie die Warteschlange (wie `Mixer._worker`).

---

## 8 · Oberfläche (Compose)

Grundlage: `ui/UI-KONZEPT-KLANGBILD.md` Rev. 2 und `ui/mockups/klangbild.html`
(Screens 01–09). Tokens aus `ui/DIRECTION.md`. Fonts Doto, Space Grotesk,
Space Mono (lokal im APK, keine Google-Fonts-Abfrage zur Laufzeit).

### 8.1 Desktop-Funktionen auf die Screens verteilt

| Screen (Mockup) | Desktop-Funktionen |
|---|---|
| 01 Bibliothek | Anzahl (F1), Analysefortschritt als Inline-Status (F2) |
| 02 Alle Titel | Liste, Suche, Einreihen per Long-Press oder `+` (F1, F14), Meta-Zeile BPM/Key |
| 03 Player | Scheibe mit Wisch-Pager und 3D (F28), Titel, Datenzeile `BPM · KEY · LUFS` (F13), laufende Wellenform mit Play-Knopf in der Mitte, wischbar (F12, F29), WEITER (F4), Auto-DJ-Schalter (F27) |
| 04 Player Auto-DJ an | NÄCHSTER-Zeile mit Grund (F10), Countdown-Segmente `TAKT n/N`, Vorschau „WIRD GEBACKEN …" (F9), Markierung des Ausstiegs auf der Wellenform |
| 05 Auto-DJ-Konsole | Schalter (F5), Mix-Stil (F6), Deck-Ansicht mit Kurven und Legende (F11), ANDERER ÜBERGANG n/3 (F8), Verlauf/Protokoll (F16), Doppel-Welle des Fensters |
| 06 Queue | Liste, hoch/runter/entfernen, ALLE ENTFERNEN, PERFEKTE REIHENFOLGE (F14, F15), `[AUTO]`-Chips mit Grund |
| 07 Suche | Titel oder Tonart (F1) |
| 08 Einstellungen | Gruppen wie Desktop `GRUPPEN` (F17), Diagnose: Underflows, Latenz, Backzeiten (F24) |
| 09 Mini-Player | normal / Blende (rot) |

### 8.2 Einstellungen: schlank oben, vollständig darunter

Das UI-Konzept will schlanke Einstellungen, der Desktop hat viele. Lösung:
- **Hauptseite** (≤ 12 Zeilen): Mix-Stil, Spielanteil, Max. BPM, Keylock,
  Tonart beim Sortieren, Lautheit, Analyse nur am Ladegerät, Stems (ausgegraut
  bis M11), Diagnose.
- **Unterseite „Übergang manuell"**: alle übrigen Felder (Art, Takte, Ausstieg,
  Einstieg, WEITER-Länge/-Start, Tempo-Modus, Lautstärke, EQ, Filter, Effekt,
  Effekt ein, Loop) mit den deutschen Texten aus `mixer.html` (`NAMEN`,
  `FX_TYP`, `FX_MODUS`, `DETAIL_HINWEIS`).
- Sperrlogik wie `mixer.html` `feld()`/`regieAn()`: Wenn die Regie plant, sind
  die Felder aus `AUTO_FELDER` ausgegraut. Eine Detail-Auswahl setzt `art` auf
  `eigen` (wie im Desktop).
- Jede Änderung: `Settings.fromJson` (prüft) → speichern → `controller.einstellungenSetzen`.

### 8.3 Deck-Ansicht und Wellenform (Leistung)

- Wellenform je Titel **einmal** in ein `ImageBitmap` zeichnen (aus
  `cache/welle`), danach nur verschoben zeichnen. Nie pro Frame Balken neu
  berechnen.
- Animationen mit `withFrameNanos` und einem `Animatable`/`mutableLongStateOf`
  für die interpolierte Position. Interpolation wie Desktop: zuletzt gemeldete
  Position + `orig_pro_s` × vergangene Zeit.
- Kurven (`info.kurven`, 64 Punkte) einmal je Übergang in `Path` umwandeln.
- Scheibe: `Modifier.graphicsLayer { rotationZ = … }`. Keine Recomposition
  pro Frame. Low-RAM-Geräte (`ActivityManager.isLowRamDevice`): keine Rotation.
- Listen: `LazyColumn` mit `key = trackId` und `contentType`. Cover über Coil
  aus `files/cover/`.
- Ziel: 60 fps im Player während einer Blende, gemessen mit
  `JankStats`/Macrobenchmark (§11).

---

### 8.4 Player-Gesten (Wunsch vom 14.10., Vorbild Poweramp-Screenshots)

Referenzbilder: `ui/referenz/player-wischen-1-ruhe.jpg` (Ruhe),
`…-2-mitte.jpg` (mitten im Wisch), `…-3-ende.jpg` (nächster Titel fast da).
Dieser Abschnitt **ersetzt** UI-Konzept §3.2 Punkte 1, 5 und 6 (Play-Kreis
links, Wellenform statisch). Farben und Schriften bleiben Nothing (§DIRECTION);
das Poweramp-Blau und die Spiegelung der Balken werden **nicht** übernommen.

**A · Laufende Wellenform mit Play-Knopf in der Mitte**

Aufbau wie in den Screenshots: Der Abspielpunkt steht fest in der
Bildschirmmitte. Die Wellenform läuft darunter von rechts nach links. Der
Play-Kreis (72 dp) sitzt **genau mittig auf dem Abspielpunkt**. Links unten die
Position (`0:58`), rechts die Gesamtdauer (`4:41`), Space Mono 12.

| Punkt | Festlegung |
|---|---|
| Balken | **1 Balken = 1 Takt** aus dem Profil (`Profile.takte`, Höhe aus `gesamt` dB, auf den Titel normiert). Dann fallen Phrasen-Ticks (jeder 8. Takt, rot, 1 px unter der Nulllinie) genau auf Balken. Ohne Profil: Energiekurve `energyJson`, 1 Balken je 2 s. |
| Maße | Balken 3 dp breit, 2 dp Abstand, Höhe max. 96 dp, untere Kante bündig. **Keine** Spiegelung (UI-Konzept: kein Gloss). |
| Farben | gespielt (links vom Abspielpunkt) = `#FFFFFF`, offen (rechts) = `#333333`. Auto-DJ an: geplante Blende als roter Bereich (Balken `#D71921` mit 60 % Deckkraft) ab `aus_s` über `blende_s`. |
| Lauf | Verschiebung je Frame = interpolierte Position × Pixel je Sekunde (§8.3). Die Wellenform liegt einmal als zwei `ImageBitmap`-Streifen vor (weiß und grau, je ganze Songbreite). Gezeichnet wird mit `clipRect` an der Mitte: links der weiße, rechts der graue Streifen. Pro Frame nur zwei `drawImage` mit Verschiebung. |
| Zeit lesen | Die Verschiebung wird **im Draw-Lambda** gelesen (`Modifier.drawWithCache { onDrawBehind { … } }`), nicht in der Komposition. Dann gibt es keine Recomposition pro Frame. |

**Gesten auf der Wellenform** (`Modifier.pointerInput` mit
`detectHorizontalDragGestures` und `VelocityTracker`):

1. **Ziehen:** Die Wellenform folgt dem Finger 1:1 (Finger nach links = vorwärts
   im Song). Während des Ziehens läuft die Wiedergabe unverändert weiter; die
   Anzeige zeigt die Zielzeit groß in Space Mono (`1:42`) über dem Play-Knopf.
2. **Loslassen:** Mit Schwung läuft die Wellenform mit `exponentialDecay()`
   aus (`Animatable.animateDecay`). Erst wenn sie steht, wird **einmal**
   `controller.seek(zielS)` gerufen. Grund: Jeder Seek verwirft den gebackenen
   Übergang (Desktop `seek` → `_verwerfen`). Laufende Seeks während des Ziehens
   würden ständig neu backen lassen.
3. **Grenzen:** Ziel auf `[0, dauer − 1 s]` klemmen. Am Rand stoppt die
   Wellenform weich (kein Gummiband, DIRECTION: kein Bounce).
4. **Haptik:** `HapticFeedbackType.SegmentTick` (bzw. `TextHandleMove` auf
   älteren Compose-Versionen) bei jedem Phrasenanfang, den der Abspielpunkt beim
   Ziehen überquert. Nicht bei jedem Takt (zu oft).
5. **Tippen** auf einen Balken (nicht auf den Play-Knopf): springt zu diesem
   Takt (gleiche Seek-Logik).
6. **Konflikt mit Systemgesten:** Die Wellenform liegt nicht am Bildschirmrand;
   zusätzlich `Modifier.systemGestureExclusion()` auf der Wellenform-Fläche,
   damit die Zurück-Geste am Rand nicht greift.
7. **Barrierefreiheit:** `Modifier.semantics { progressBarRangeInfo …;
   setProgress { … } }`, damit TalkBack die Position ändern kann.

Test: Compose-UI-Test zieht 200 dp nach links → `seek` wird genau einmal mit
`ziel = start + 200 dp / pxProSekunde` gerufen.

**B · Cover wischen = Titel wechseln, mit 3D-Ausblendung**

Wie im zweiten und dritten Screenshot: Beim Wischen dreht sich die Scheibe
leicht um die senkrechte Achse weg und blendet aus. Das nächste Cover kommt
gedreht und blass von rechts und richtet sich auf. Titel und Interpret unter
der Scheibe gehören zur Seite und kippen mit.

| Punkt | Festlegung |
|---|---|
| Baustein | `HorizontalPager` (Compose Foundation). Seiten: `[vorheriger, aktueller, nächster]`, `key = trackId`. |
| Nächster | Auto-DJ: der gebackene/geplante nächste Titel (`naechster` bzw. `vorschau`), sonst `warteschlange[0]`. Ohne bekannten Nachfolger: Platzhalter-Scheibe mit `[AUTO-DJ WÄHLT …]`. |
| Vorheriger | letzter Titel aus `verlauf`. Fehlt er: keine Seite links (Pager startet bei Index 0). |
| 3D je Seite | im `graphicsLayer`-Lambda, `o = pagerState.getOffsetDistanceInPages(page).coerceIn(-1f, 1f)`: `rotationY = o * -28f`, `cameraDistance = 12f * density`, `transformOrigin = TransformOrigin(if (o < 0) 1f else 0f, 0.5f)` (dreht um die Kante zur Mitte, wie eine Walze), `alpha = 1f - 0.55f * abs(o)`, `scaleX = scaleY = 1f - 0.08f * abs(o)` |
| Text | Titel/Interpret sind Teil der Seite, bekommen also dasselbe `graphicsLayer`. Lange Titel: `basicMarquee()` nur auf der aktiven Seite. |
| Rotation der Scheibe | 8 s/Umdrehung (UI-Konzept) als **inneres** `graphicsLayer { rotationZ }`; das äußere trägt den 3D-Effekt. Beide nur im Layer-Lambda lesen. |
| Einrasten | `PagerDefaults.flingBehavior(state, snapAnimationSpec = tween(320, easing = CubicBezierEasing(0.25f, 0.1f, 0.25f, 1f)))`. Kein Federnachschwingen (DIRECTION). Haptik `GestureEnd` beim Einrasten. |
| Bilder | Cover über Coil mit fester Größe (`size(560)`), `crossfade(false)` (der Pager blendet selbst). Nächstes Cover vorladen, sobald der Nachfolger feststeht. |
| Reduced Motion | `Settings.Global.ANIMATOR_DURATION_SCALE == 0` → kein 3D, nur Überblendung. |
| Feinschliff | Winkel, Drehpunkt und Ausblendung am Gerät gegen die drei Screenshots vom 14.10. abstimmen (Zielbild: aktuelles Cover kippt ~25–30° weg und wird blass, nächstes kommt blass und gedreht). Werte als Konstanten in `PlayerMotion.kt`. |

**Was ein Wisch auslöst:**

| Geste | Auto-DJ aus | Auto-DJ an |
|---|---|---|
| nach links (nächster) | `play(nächster)` sofort, harter Start | `weiter()`: Blende ab nächstem Takt/Phrase (Einstellung `weiter_ab`). Die Seite bleibt beim neuen Cover stehen, darunter Inline-Status `[BLENDE IN 4 S]` mit Countdown-Segmenten. |
| nach rechts (voriger) | `play(voriger)` harter Start | ebenfalls `play(voriger)` (Desktop kennt kein „zurück im Mix"); Auto-DJ bleibt an und plant ab dort neu |
| kein Nachfolger bekannt | Pager rastet zurück, Haptik `Reject` | wie links: `weiter()` ist trotzdem möglich (Auto-DJ wählt) |

**Falle Rückkopplung (wichtig für die umsetzende KI):** Der Pager ändert die
Seite durch den Nutzer **und** durch neue Daten (Titelwechsel nach einer
Blende). Regeln:
1. Nur `settledPage`-Änderungen, die aus einer **Nutzergeste** kommen, rufen den
   Controller. Erkennen: `pagerState.interactionSource` meldete eine
   `DragInteraction.Start` seit dem letzten Einrasten.
2. Ändert sich der aktuelle Titel durch den Controller, wird die Seitenliste neu
   gebaut und der Pager **ohne Animation** (`scrollToPage`) auf die Seite des
   aktuellen Titels gesetzt. Weil `key = trackId`, springt dabei nichts sichtbar.
3. Ein Titelwechsel durch die Blende (Auto-DJ) wird dagegen animiert:
   `animateScrollToPage(aktuell)` mit 600 ms, damit die Scheibe beim Wechsel
   sichtbar weiterdreht. Startpunkt der Animation: das Ereignis `Switched` wird
   **hörbar** (§5.4), nicht wenn der Feeder umschaltet.

Test: UI-Test wischt nach links → bei Auto-DJ an genau ein Aufruf `weiter()`,
kein zweiter durch die nachfolgende Datenänderung.

**C · Weitere Animationen** bleiben wie UI-Konzept §5. Neu: Wechselt der Titel,
bauen sich die Wellenform-Balken in 150 ms von unten auf (nur die sichtbaren,
per `Animatable` 0→1 als Höhenfaktor im Draw-Lambda).

---

## 9 · Stems auf Android

### 9.1 Recherche (Stand 14.10.2026)

| Frage | Befund | Quelle |
|---|---|---|
| Wie macht es djay? | Neural Mix nutzt Technik von **AudioShake**, Trennung in Echtzeit. djay wählt die Qualitätsstufe nach Gerät; auf Android ab 64-Bit-Geräten. Auch in djay ist ein Teil davon kein „live", sondern rechnet mit (Analyse §27, §43.4). | [AudioShake × Algoriddim](https://www.audioshake.ai/case-studies/algoriddim), [djay Qualitätsstufen](https://help.algoriddim.com/hc/en-us/articles/11640778952220), [MusicTech](https://www.musictech.com/news/gear/algoriddim-free-update-djay-pro-improved-stem-separation-audioshake/) |
| Gibt es das als Baustein? | **AudioShake SDK**: läuft lokal, nativ für Android, iOS, Windows, macOS, Echtzeit. Preis nur auf Anfrage (info@audioshake.ai). | [AudioShake SDK](https://www.audioshake.ai/products/sdk), [SDK-Doku](https://developer.audioshake.ai/sdk/overview.md) |
| Andere Android-Apps | z. B. Stemify trennt auf dem Gerät, braucht aber **2–8 min je Song**. Also Vorbereitung, nicht live. | [Stemify (Play)](https://play.google.com/store/apps/details?id=com.stemify.app) |
| HTDemucs auf dem Handy | ONNX-Fassung: 166 MB (fp16), ~1,1 GB RAM, 7,8-s-Stücke, auf Apple M4 Pro CPU 0,2× Echtzeit. Ein Mittelklasse-Handy ist grob 4–8× langsamer, also etwa Echtzeit (Schätzung, nicht gemessen). | [htdemucs-onnx](https://huggingface.co/adowu/htdemucs-onnx) |
| Lizenz HTDemucs-Gewichte | **strittig**: Model-Card nennt MIT, der Autor nannte sie früher „research purpose"; Trainingsdaten (MUSDB18-HQ + eigene) schränken ein. Für ein Bezahlprodukt nicht ohne schriftliche Zusage. | [HF-Diskussion](https://huggingface.co/adefossez/HTDemucs/discussions/1), [unblend](https://huggingface.co/Ryan5453/unblend) |
| Andere freie Modelle | Open-Unmix `umxl`: nur nicht-kommerziell (CC BY-NC-SA). Spleeter: Code MIT, Gewichte ohne eigene Lizenzangabe. | [openunmix (PyPI)](https://pypi.org/project/openunmix/), [Spleeter JOSS](https://joss.theoj.org/papers/10.21105/joss.02154.pdf) |
| Leichte neue Modelle | Band-SCNet (2,59 Mio. Parameter, kausal, ~92 ms Latenz, SDR 7,79 dB), Moises-Light (4 Stems, bis 13× weniger Parameter), RT-STT. Forschung; Gewichte/Lizenzen nicht veröffentlicht bzw. unklar. Eignen sich als **Architektur** für ein eigenes Modell. | [Band-SCNet](https://www.isca-archive.org/interspeech_2025/yang25d_interspeech.html), [Moises-Light](https://awesomepapers.io/speech-audio/papers/2510.06785), [RT-STT](https://arxiv.org/abs/2511.13146v1) |
| Beschleuniger | LiteRT hat seit 2026 produktive NPU-Anbindung für Qualcomm und MediaTek, > 2× schneller als GPU; Modelle je Chip über Play AI Packs. Konvertierung PyTorch → LiteRT mit `litert-torch`. | [LiteRT + NPU](https://developers.googleblog.com/building-real-world-on-device-ai-with-litert-and-npu/), [LiteRT](https://developers.googleblog.com/en/litert-the-universal-framework-for-on-device-ai/) |

### 9.2 Was Klangbild wirklich braucht

Klangbild braucht keine Echtzeit-Stems wie ein Live-DJ, der Spuren stummschaltet.
Es braucht zwei Dinge, beide **vorher** berechenbar:
1. **Stem-Pegel je Takt im Profil** (Gesang, Drums, Bass): Damit vermeidet die
   Regie Gesang gegen Gesang, findet Breaks und den Bass-Tausch-Takt. Das sind
   ~10 KB je Titel.
2. **Stem-Audio nur in den Übergangsfenstern** (Outro von A, Intro von B, je
   ~45 s) für die Rezepte Gesangsschutz, Drums zuerst, Acapella.

Und der Ablauf des Nutzers macht das planbar: **Playlist → Optimale
Reihenfolge → abspielen.** Danach steht jeder Übergang fest. Die Fenster lassen
sich also vorab rechnen, nur für diese Playlist, nicht für 2 000 Titel.

### 9.3 Stufenplan

**S1 · Stem-Profile vom PC (sofort, kein Modell auf dem Handy)**
- Der PC hat den Stem-Vorrat bereits (`cache/stem_vorrat`, alle 332 Titel), die
  Profile in `cache/profil/` enthalten die Stem-Pegel (`stems` ≠ null).
- M3 importiert diese Profile mit. Die Regie auf dem Handy kennt dann den
  Gesang für alle importierten Titel. Stem-**Rezepte** bleiben aus
  (`stemsDa = false`), weil das Audio fehlt.
- Für neue Titel: „Neue Titel am PC vorbereiten" = der PC-Mixer rechnet sie
  (er kann das schon), der nächste Import bringt sie mit.
- Grenze: Für die eigene Nutzung gut. Für Kunden ohne PC kein Weg (→ S3).

**S2 · Fenster auf dem Handy für die aktive Playlist („Set vorbereiten")**
- Knopf **SET VORBEREITEN** in der Playlist (erscheint nach „Optimale
  Reihenfolge"). Für jedes Paar plant die Regie den Übergang schon jetzt
  (`Regie.planen` mit Profil), daraus folgen die genauen Fenster: A ab
  `aus_s − 4 s` über `takte` + 8 Takte, B ab `ein_s − 4 s` über `takte`.
- Ein `StemWorker` (WorkManager, `setRequiresCharging` wenn > 10 Fenster)
  trennt diese Fenster und legt sie unter `cache/stems/<trackId>@<startFrame>_<frames>.pcm`
  ab (4 Stems, int16 stereo). Der Schlüssel ist derselbe wie im Desktop
  (`fenster_a`/`fenster_b`, „id@start_n"), damit `backen` sie findet.
- Keine Teilprofile: Die Regie nutzt Gesang nur aus vollständigen Profilen
  (S1). Fenster-Stems dienen nur den Stem-Rezepten (sonst plant die Regie mit
  Daten, die es nur für ihre eigene alte Wahl gibt).
- Speicher: ~16 MB je Fenster (4 Stems × 45 s int16 stereo). 40 Titel ≈ 1,3 GB.
  Grenze 2 GB, älteste Playlist zuerst weg. Upgrade, falls zu viel: Fenster als
  Opus über `MediaCodec` speichern (~10× kleiner).
- Fortschritt in der Playlist: je Übergangs-Chip ein `S` (Stems bereit).
- Spielt die Playlist, nimmt `backen` die Stem-Rezepte, wenn beide Fenster
  bereit sind und die Regie sie wählt. Nach Umsortieren oder WEITER passen die
  Fenster nicht mehr → Rezept ohne Stems (wie Desktop: „Fenster nicht bereit").
- Ohne Playlist (Auto-DJ wählt selbst) zusätzlich **just in time** wie
  `live._stems_vorrechnen`, aber nur, wenn die gemessene Trennzeit für ein
  90-s-Fenster < 50 % der Restspielzeit von A ist.
- Modell und Rechenweg: zuerst HTDemucs ONNX fp16 mit ONNX Runtime (XNNPACK),
  danach dasselbe Modell über LiteRT mit NPU messen. Das schnellere gewinnt
  (djay-Muster `AUMModelSelectionStrategy(InferenceTime)`). Rechnen in 7,8-s-Stücken
  mit Überlappung wie `stems._in_stuecken`, Rest-Trick (Original − Summe →
  „other") wie `stems._fertigstellen`.

**S3 · Auslieferung an Kunden (Entscheidung nötig)**

| Weg | Vorteil | Nachteil | Aufwand |
|---|---|---|---|
| a) **AudioShake SDK lizenzieren** | Profi-Qualität, Echtzeit, auf Android erprobt (djay) | Kosten unbekannt (Anfrage), Abhängigkeit von einem Anbieter | Anfrage + Einbau 1–2 Wochen |
| b) **Eigenes kleines Modell trainieren** (Architektur wie Band-SCNet/Moises-Light, ~2–3 Mio. Parameter) | eigene Rechte, klein und schnell, NPU-tauglich | braucht Trainingsdaten mit kommerziellen Rechten (MUSDB18/MoisesDB sind nicht-kommerziell) und GPU-Zeit; Qualität unter HTDemucs | Wochen bis Monate |
| c) **HTDemucs mit schriftlicher Freigabe** | Modell und Code sind fertig (S2) | Freigabe ungewiss; 166 MB groß, 1,1 GB RAM | Anfrage beim Autor/Meta |
| d) **Nur Gesangs-Erkennung** (kleiner Klassifikator „singt/singt nicht" je Takt) | viel billiger als Trennen, reicht für Regie-Punkt 1 | keine Stem-Rezepte; Trainingsdaten-Frage wie b) | 1–2 Wochen |

Empfehlung: **S1 jetzt**, **S2 bauen und messen** (für den Prototyp auf dem
eigenen Handy), parallel **AudioShake anfragen** (Preis klären). Danach
entscheidet der Nutzer zwischen a), b) und c). d) nur, falls a) bis c)
scheitern.

### 9.4 Tore

- **Tor G-S1** (S1 fertig): ≥ 95 % der importierten Titel haben ein Profil mit
  Stems; Regie-Golden-Tests mit Stem-Profilen grün (T7.3 deckt das ab).
- **Tor G-S2** (Messung, vor dem Einbau von S2 in die App): HTDemucs fp16 auf dem
  Testgerät, 90-s-Fenster: Zeit, RAM-Spitze, Temperatur nach 10 Fenstern.
  Weiter, wenn ≤ 60 s je Fenster am Ladegerät und RAM-Spitze < 1,5 GB. Sonst:
  S2 nur „über Nacht am Ladegerät" anbieten.
- **Tor G-S3** (Auslieferung): Lizenz schriftlich geklärt. Ohne G-S3 bleibt S2
  ein Entwickler-Schalter, der im Release-Build fehlt.

---

## 10 · Performance

### 10.1 Budget

| Messgröße | Ziel | Gemessen wie |
|---|---|---|
| CPU im Callback | < 2 % eines Kerns | Perfetto, Thread des Callbacks |
| Aussetzer (Underflows) | **0** in 1 h Auto-DJ | Zähler im Zustand |
| Startzeit Song antippen → Ton | < 300 ms | Log-Zeitstempel |
| Plan sichtbar nach Songbeginn | < 3 s (Desktop 0–3 s) | `zeiten.plan` im Info |
| Backzeit Profi-Blend 16 Takte mit Keylock | < 6 s Mittelklasse | `zeiten.backen` |
| Bedienung reagiert | < 300 ms | Roadmap-Tor Phase 2 |
| UI im Player | 60 fps, < 1 % Jank | Macrobenchmark |
| RAM gesamt im Auto-DJ | < 300 MB | `dumpsys meminfo` |
| Analyse je Titel | ≤ 2 s Ziel, ≤ 6 s Pflicht (Mittelklasse) | Worker-Log |
| Akku 1 h Auto-DJ, Bildschirm aus | < 8 % | Battery Historian |

### 10.2 Regeln (aus djay Teil 4, angepasst)

1. Callback: nur Ring lesen und Rampen (§5.3).
2. Alles Schwere im Baker-Pool mit Priorität 10, nie auf dem Main-Thread.
3. Keine Allokation in Schleifen des Bakers: Puffer je Auftrag einmal anlegen.
4. Profile, Wellen, Cover: einmal rechnen, auf Platte, Memo im Speicher
   (Desktop `_einmal`).
5. Planen vor dem Backen: Die Regie liest nur Profile (≈ 0,03 s), das Audio
   erst für `loopQuality`.
6. Ausgabelatenz nur in der Anzeige verrechnen, nie in der Mischung.

### 10.3 Adaptive Qualität (klein gehalten)

- Ist die gemessene Backzeit (`backzeit`) > 15 s: Regie-Längen eine Stufe
  kürzer (`LAENGEN[kurz]`) und Hinweis in der Diagnose.
- Thermal-Status ≥ `SEVERE`: Keylock-Dehnen nur noch für die Blende, Rest
  ohne Dehnen (`rampe` macht das ohnehin), Analyse pausiert.
- Mehr Stufen nur, wenn M12 sie per Messung verlangt.

---

## 11 · Meilensteine und Aufgaben

Reihenfolge ist Pflicht. Jeder Meilenstein endet mit einem Tor. Fällt ein Tor,
nicht weiterbauen, sondern dem Nutzer berichten.

### M0 · Gerüst und Golden-Werkzeug

**T0.1 Android-Projekt anlegen.** Android Studio → Empty Activity (Compose) in
`android/`. Module `:core` (Kotlin JVM library), `:engine` (Android library,
„Native C++"), `:app`. `ndkVersion` r28+. `abiFilters "arm64-v8a", "x86_64"`.
Manifest ohne `INTERNET`. Test: `./gradlew assembleDebug test` grün, App startet
leer.

**T0.2 Golden-Export (Python).** Neue Datei
`prototyp/klangbild/golden.py`, Befehl `python -m klangbild golden <ziel>`
(in `__main__.py` eintragen wie die anderen Befehle). Ziel:
`android/testdata/golden/`. Format: je Fall eine `<name>.json` (Eingaben,
Skalare, kurze Arrays) und `<name>.f32` (lange Arrays, float32 little endian,
interleaved). Fälle in §12.2. Dazu exportiert es `sos_44100.json`,
`sos_22050.json`, `hall_ir.f32`. Test: zweimal laufen lassen → identische
Dateien (deterministisch).

**T0.3 Golden-Leser.** `:core/src/test/.../Golden.kt` (lädt JSON + f32) und
`engine/src/test/cpp/golden.h` (C++-Test mit GoogleTest, läuft auf dem Host
über CMake, nicht auf dem Gerät). Test: ein Dummy-Fall wird gelesen.

**T0.4 ADRs anlegen.** `adr/ADR-023-eine-engine-fuer-alles.md`,
`ADR-024-vorausbacken-auf-android.md`, `ADR-025-pcm-cache.md`,
`ADR-026-analyse-import-vom-pc.md` im Stil der vorhandenen ADRs, Status
„vorgeschlagen". Inhalt aus §3.4, §3.1, §4.3, M3.

**Tor M0:** Build grün, Golden-Daten liegen vor, ADRs geschrieben.

### M1 · Engine-Spike: Ton ohne Aussetzer (Roadmap Phase 3, Teil 1)

**T1.1 Oboe-Stream + OutputRing + Callback** (§5.3). Test: Sinus 440 Hz
aus dem Feeder, 10 min, `underflows == 0`.

**T1.2 Rampen und Pause** (§5.3). Test (Host): Rampe 441 Frames, kein Sprung
größer als 0,01 zwischen zwei Samples beim Pausieren eines vollen Sinus.

**T1.3 Fehler-Callback, Neustart, Bluetooth.** Test (Gerät): während der
Wiedergabe Bluetooth-Kopfhörer verbinden/trennen → Ton läuft weiter oder pausiert
sauber, kein Absturz.

**T1.4 Diagnose-Ausgabe**: `poll()` liefert Underflows und Latenz; einfacher
Debug-Screen zeigt sie.

**Tor M1:** 1 h Sinus und 1 h Rauschen ohne Aussetzer auf einem
Mittelklasse-Gerät, Bildschirm aus, App im Hintergrund (Foreground-Service).

### M2 · Decoder, PCM-Cache, Timeline

**T2.1 Decoder** (§5.5). Test: je eine MP3, FLAC, OGG, Opus, WAV, M4A aus
`D:\Music\Chill` → Länge ±1 Frame wie Python `audioio.decodieren_stereo`
(Golden: Länge und RMS je Sekunde ±0,5 dB; bitgleich geht nicht, die Decoder
unterscheiden sich).

**T2.2 PCM-Cache mit `gain_db` und Limiter** (§4.3, §5.10). Test Golden
`limiter_*`: Ausgabe ±1e-4 zu Python `_begrenzen`.

**T2.3 Timeline, Feeder, Wechselstelle** (§5.2). Tests (Host, ohne Oboe, Feeder
direkt aufgerufen): Port der Desktop-Tests aus `tests/test_live.py` für
`fuellen` und `_umschalten` (Wechsel genau an `switchAt`, Songende ohne Next →
`Ended`, `setNext` zu spät → `false`).

**T2.4 Positions-Journal und gehörte Position** (§5.4). Test: Sinus mit Klick
jede Sekunde, Anzeige-Position gegen Klickzeit ±20 ms (Kabelkopfhörer).

**Tor M2:** Zwei Songs hintereinander gapless, Seek auf beliebige Stelle ohne
Knacken, 1 h Wiedergabe ohne Aussetzer.

### M3 · PC-Import (Analyse vom Desktop)

**T3.1 Export (Python).** `python -m klangbild export-android <ziel.zip>`:
je mischbarem Titel `audio_hash`, Dateiname, Größe, `features` (Zeile mit
`analyse_version="0.3.0"`), Profil-JSON aus `cache/profil/` **mit Stem-Pegeln**
(Stufe S1, §9.3; fehlen sie, vorher `profil.laden` mit Stem-Vorrat rechnen),
Wellenform als `.bin` (§4.2), Cover-JPEG, Raster-Anker aus `cache/anker.json`
(Versatz auf die Downbeats gerechnet wie `mixer.bibliothek_laden`, dazu die
Fein-Knoten `fein`). Eine `index.json` mit Versionen und der Zahl der Profile
mit Stems.

**T3.2 Hash-Port** (`hashutil.py` → `HashUtil.kt`). Golden: 20 Dateien,
Hash identisch zu Python.

**T3.3 Import (App).** Einstellungen > Diagnose > „Analyse vom PC importieren"
(SAF `ACTION_OPEN_DOCUMENT`, zip). Zuordnung über Hash. Test: 332 Titel aus
`D:\Music\Chill` aufs Handy kopiert → ≥ 330 zugeordnet (Rest: Dateien
anders kodiert, im Bericht nennen).

**T3.4 MediaStore-Scan und Room** (§6.5, §4.1). Test: Liste zeigt alle Titel,
analysierte mit BPM/Key.

**Tor M3:** Bibliothek mit Desktop-Analyse auf dem Handy, Titel abspielbar.

### M4 · Media3, Service, Fokus

**T4.1 `PlaybackService` + `KlangbildPlayer`** (§6.3, §6.4). Test: Benachrichtigung
mit Titel, Play/Pause aus der Benachrichtigung, Kopfhörertaste, Sperrbildschirm.

**T4.2 Audio-Fokus und Becoming-Noisy.** Test: Anruf/anderer Player → Pause;
Kabel ziehen → Pause.

**Tor M4:** App spielt im Hintergrund 1 h, bedienbar über Benachrichtigung und
Kopfhörer.

### M5 · DSP-Port mit Golden-Tests (C++, Host-Tests)

Jede Aufgabe: Funktion portieren, Golden-Test grün. Reihenfolge so, dass jede
Aufgabe nur fertige Teile braucht.

| Aufgabe | Funktion(en) | Golden-Fälle |
|---|---|---|
| T5.1 | `equal_power_blende`, `_rampe`, `_bass_rampen` | `kurven_basis` |
| T5.2 | `band_teilen` (sosfiltfilt, §5.8) | `band_200`, `band_2000`, `band_2500`, kurzes Signal (Rückfall) |
| T5.3 | `_fade_segment`, `mischen` (eq, filter, echo, schnitt, crossfade) | `mischen_<art>_<takte>` |
| T5.4 | `_huellen` (alle Lautstärke-, EQ-, Filter-, Effekt-Varianten) | `huellen_<variante>` (alle Kombinationen aus `AUSWAHL`, je 1 000 Punkte) |
| T5.5 | `_biquads`, `_sweep` | `sweep_tp`, `sweep_hp`, `sweep_offen_rand` |
| T5.6 | `_echo`, `_nass` (echo/delay 50/75/100), Hall (IR-Asset, FFT-Faltung) | `nass_<typ>` |
| T5.7 | `_takt_db`, `_deckeln`, `_trocken` | `deckeln_*` |
| T5.8 | `_loop_plan`, `_achtel`, `_loopen`, `loop_info` | `loop_<groesse>`, `loop_rolle` |
| T5.9 | `_beat_merkmale`, `_aehnlich`, `loop_waehlen` | `loopwahl_*` (5 echte Outros) |
| T5.10 | `_intro_loop` | `introloop_*` |
| T5.11 | `mischen_eigen` (gesamt) | `eigen_<rezept>` für jedes Regie-Rezept aus `_rezept` |
| T5.12 | `kurven`, `kurven_eigen` | `kurven_<art>` (JSON-Vergleich, 3 Stellen) |

**Tor M5:** alle Golden-Tests grün, Toleranzen nach §12.3.

### M6 · Warp und `backen`

**T6.1 Signalsmith einbinden** (§5.7). Test: 440-Hz-Sinus um 10 % gedehnt →
FFT-Spitze bei 440 Hz ±1 Hz (Port aus `tests/test_uebergang.py`).

**T6.2 `warp` ohne Keylock** (lineares Resampling je Takt). Golden `warp_vinyl`.

**T6.3 `_warp_keylock` mit WSOLA-Naht.** Tests: Klickspur nach dem Dehnen auf
dem Zielraster ±1 ms (Desktop 0,8 ms), Länge exakt `ziel[-1]` Frames,
Golden `warp_keylock` mit Toleranz für Signalsmith (§12.3).

**T6.4 `regulaer`, `taktraster`, `raster`, `_periode`, `ausstieg`, `einstieg`, `Spur`
(`zu_puffer`, `zu_original`, `bpm_bei`).** Golden mit 20 echten Titeln.

**T6.5 `backen` komplett** (§5.6), ohne Stems, ohne `b_an_a`-Rest.
Golden-Fälle: je Art (`crossfade`, `eq`, `filter`, `echo`, `schnitt`, `eigen`
mit jedem Regie-Rezept), sync und nicht sync, WEITER, Intro-Loop von B,
A endet in der Blende. Verglichen werden: `startN` exakt, `orig/buf` ±1e-6 s,
`info` (ohne `kurven`) exakt, Audio nach §12.3.

**T6.6 `b_an_a`-Rest (Stufe 2)** (§5.1). Test: Golden `backen_b_an_a`.

**T6.7 Baker-Pool.** A- und B-Warp parallel. Test: Backzeit 16 Takte mit
Keylock auf dem Gerät messen, ins Protokoll.

**Tor M6:** Ein manueller Übergang (Stil Manuell, Art EQ, 16 Takte) zwischen
zwei echten Titeln klingt auf dem Handy wie der Desktop-Render desselben Paars
(Nutzer hört A/B).

### M7 · Regie, Planer, Einstellungen (Kotlin `:core`, JVM-Tests)

**T7.1 `Settings`** inkl. `fromJson`-Prüfung. Port `tests/test_einstellungen.py`.

**T7.2 `Profile`** inkl. `etiketten`, Memo. Golden: 50 Profile aus
`cache/profil/` → `gesang/drums/bass/dichte/etiketten` identisch.

**T7.3 `Regie.planen`** ohne Audio-Teil (`a_audio = null`). Port
`tests/test_regie.py`. Golden: 200 echte Paare × 4 Stile × 2 Spielanteile →
dieselben 3 Pläne (`aus_s`, `ein_s`, `takte`, `rezept`, `einst`) wie Python.

**T7.4 `loopQuality`** über JNI (`regie._loop_guete`) und Einbau in `planen`.
Golden: 30 Paare mit Loop-Rezept.

**T7.5 `Regie.pruefen`** (Pegel je Takt kommen von `NativeEngine.checkBlend`).
Golden: 20 gebackene Blenden.

**T7.6 `SetPlanner`** (`rangliste`, `sortiere_alle` mit BPM-Fenster, §6.1).
Golden: Reihenfolge der 332 Titel identisch zu Python.

**Tor M7:** alle JVM-Tests grün.

### M8 · Auto-DJ-Controller

**T8.1 Grundbedienung** (`play`, `pause`, `seek`, Warteschlange, Auto aus =
Schnitt am Ende). Port der passenden Tests aus `tests/test_live.py` mit einer
Fake-Engine (Interface `EngineApi`, das `NativeEngine` und die Fake-Engine
implementieren).

**T8.2 `vorbereiten`, `autodjWahl`, `autoBacken`, `uebernehmen`, Selbstkontrolle,
Sicherheits-Blend.** Tests mit Fake-Engine + echten Profilen.

**T8.3 WEITER und „anderer Übergang", Lernen, Energiebogen,
`_gleicher_titel`.** Tests wie Desktop.

**T8.4 Vorschau (`vorschau`) und `MixerState`.** Gleiche Felder wie
`zustand()`.

**Tor M8 (Roadmap Phase 3/4-Tor):** 1 h Auto-DJ auf dem Handy, Stil
Ausgewogen, Bildschirm aus: `underflows == 0`, kein verworfener Übergang wegen
„zu spät" ohne Bedienung, alle Übergänge auf dem Phrasenraster (Protokoll),
WEITER und „anderer Übergang" je 5× ohne Abbruch.

### M9 · Oberfläche

**T9.1 Theme, Fonts, Tokens** (DIRECTION.md). **T9.2 Bibliothek + Alle Titel +
Mini-Player.** **T9.3a Laufende Wellenform mit Play-Knopf in der Mitte und
Wisch-Seek** (§8.4 A). **T9.3b Cover-Pager mit 3D-Ausblendung** (§8.4 B,
inkl. Rückkopplungs-Regeln). **T9.4 Auto-DJ-Konsole mit
Deck-Ansicht und Kurven.** **T9.5 Queue-Sheet.** **T9.6 Suche.** **T9.7
Einstellungen + Unterseite manuell + Diagnose.** **T9.8 Animationen** nach
UI-Konzept §5 und §8.4 C (inkl. reduced motion). **T9.9 Playlists**: anlegen,
hinzufügen, umsortieren, entfernen, OPTIMALE REIHENFOLGE mit Rückgängig und
Übergangs-Chips, Auto-DJ-Schalter je Playlist, „Nach der Playlist"
(§6.6). **T9.10 Auto-DJ-Befehl in der Benachrichtigung** (§6.6).

T9.3a und T9.3b: Zusätzlich zum Mockup-Vergleich ein Bildschirmvideo neben die
Referenzbilder in `ui/referenz/` legen und dem Nutzer zeigen; Ziel 60 fps beim
Wischen (Macrobenchmark `FrameTimingMetric`, P90 < 16 ms).

Je Aufgabe: Screenshot-Vergleich mit dem Mockup (`ui/mockups/klangbild.html`,
gleicher Screen) und Compose-UI-Test für die Bedienung (Knopf löst die
Controller-Methode aus).

**Tor M9:** Jede Funktion aus §2.1 ist über die Oberfläche erreichbar
(Checkliste abhaken). 60 fps im Player während einer Blende.

### M10 · Analyse auf dem Gerät

**T10.1 Mono-22k-Ausgabe des Decoders.** **T10.2 Key** (Golden 50 Titel:
gleiches Camelot ≥ 95 % gegenüber Python mit denselben Samples). **T10.3 LUFS/TP**
(±0,1 LU). **T10.4 Energie, Abschnitte.** **T10.5 Wellenform.** **T10.6 Beat
This! ONNX + BPM-Regression** (§7.2). **T10.7 Profil ohne Stems** (Golden: aus
denselben Samples ±0,05 dB). **T10.8 Cover.** **T10.9 `AnalysisWorker`** (§7.3).

**Tor G-A (Analyse-Gleichheit):** Die 332 Desktop-Titel auf dem Handy neu
analysiert:
- BPM: |Android − Desktop| ≤ 0,1 % bei ≥ 99 % der Titel,
- Downbeat-Phase (Kreismittel um die Songmitte): ≤ 30 ms bei ≥ 95 %,
- Camelot gleich bei ≥ 90 % (Rest: Decoder-Unterschiede),
- Analysezeit je Titel im Median ≤ 6 s auf dem Mittelklasse-Gerät.
Fällt es durch: Bericht an den Nutzer (Modell `final0`? andere Vorverarbeitung?).

### M11 · Stems (Stufen aus §9.3)

S1 ist schon in M3 (Import der Stem-Profile) enthalten.

**T11.1 Messung (Tor G-S2):** HTDemucs fp16 ONNX (ONNX Runtime, XNNPACK) und
dieselbe Fassung über LiteRT mit NPU auf dem Testgerät; 90-s-Fenster, Zeit,
RAM, Temperatur. Ergebnis in `PROTOKOLLE.md`.
**T11.2 `StemSeparator`** (Port `stems._in_stuecken`, `_fertigstellen` mit
Rest-Trick). Golden: Summe der Stems = Original ±1e-4.
**T11.3 „Set vorbereiten"** für eine Playlist: Fenster aus den Regie-Plänen,
`StemWorker`, Cache mit Desktop-Schlüsseln, Fortschritt je Übergang.
**T11.4 Stem-Zweig in `backen`** (`mischen_stems`, `STEM_PLAN`, `_singt`,
Endnaht ins Original) und `stemsDa` im Controller. Golden `backen_stems_*`.
**T11.5 Just-in-time** für den Auto-DJ ohne Playlist (nur wenn T11.1 schnell genug).
**Release-Build:** S2/T11.3–11.5 hinter dem Schalter `BuildConfig.STEMS_ON_DEVICE`,
der erst nach Tor G-S3 (Lizenz) auf `true` geht.

### M12 · Härtung

**T12.1 Langlauf:** 4 h Auto-DJ, Speicher konstant (±20 MB), 0 Aussetzer.
**T12.2 Bedienung unter Last:** 25 Eingriffe in 10 s während des Backens (wie
Desktop-Härtetest), kein Absturz, kein Aussetzer.
**T12.3 Kein Netzwerk:** `aapt2 dump permissions` ohne `INTERNET`; zusätzlich
`adb shell dumpsys netstats` vor/nach 1 h → 0 Byte für die App-UID.
**T12.4 16-KB-Ausrichtung, R8** (Keep-Regeln für JNI-Klassen, keine Reflection).
**T12.5 Absturzdatei** (`Thread.setDefaultUncaughtExceptionHandler` +
`std::set_terminate`/Signal-Handler schreibt `files/crash.txt`).
**T12.6 Messung aller Ziele aus §10.1** auf zwei Geräten (Mittelklasse,
Oberklasse), Tabelle in `PROTOKOLLE.md`.

---

## 12 · Tests und Abnahme

### 12.1 Testarten

| Art | Wo | Läuft auf | Wofür |
|---|---|---|---|
| Golden-Tests C++ | `engine/src/test/cpp/` (GoogleTest, Host-Build) | PC | DSP, Warp, Baker |
| Golden-/Unit-Tests Kotlin | `core/src/test/` (JUnit 5) | PC | Regie, Profil, Planer, Einstellungen |
| Controller-Tests | `app/src/test/` mit Fake-Engine | PC | Ablauf wie `test_live.py` |
| Instrumentierte Tests | `app/src/androidTest/` | Gerät | Decoder, Oboe, Service, UI |
| Langlauf | Skript `android/tools/langlauf.sh` (adb, liest Diagnose per `dumpsys`/Logcat) | Gerät | Aussetzer, Speicher |
| Hörtest | Nutzer | Gerät | Klang, wie Desktop |

### 12.2 Golden-Fälle (Liste für T0.2)

Jeder Fall nutzt **feste Eingaben**: synthetische Signale (Sinus, Rauschen mit
festem Seed, Klickspur) und Ausschnitte aus 5–20 echten Titeln (ihre Samples
werden mit exportiert, damit Decoder-Unterschiede nicht stören).

`kurven_basis`, `band_200/2000/2500`, `band_kurz`, `mischen_<art>_<takte>`
(art ∈ eq, filter, echo, schnitt, crossfade; takte ∈ 1, 4, 16),
`huellen_<feld>_<wert>` (jede Auswahl aus `LAUTSTAERKE`, `EQ`, `FILTER`,
`EFFEKT`, `EFFEKT_EIN`, `LOOP`), `sweep_*`, `nass_<typ>`, `hall_ir`,
`deckeln_*`, `loop_*`, `loopwahl_*`, `introloop_*`, `eigen_<rezept>`,
`kurven_<art>`, `limiter_*`, `warp_vinyl`, `warp_keylock`, `regulaer_*`,
`ausstieg_*`, `einstieg_*`, `backen_<fall>`, `profil_<id>`,
`regie_<paar>_<stil>_<spielanteil>`, `loopguete_*`, `pruefen_*`,
`sortiere_332`, `rangliste_*`, `einstellungen_*`, `hash_*`, `key_*`, `lufs_*`,
`energie_*`, `welle_*`, `beatthis_*`.

### 12.3 Toleranzen

| Bereich | Toleranz | Grund |
|---|---|---|
| Kurven, Hüllkurven, Planwerte | ±1e-6 (exakt bei Ganzzahlen und Strings) | reine Rechnung |
| Filter, Mischen, Limiter, Loops | max. Abweichung ±1e-4, RMS-Differenz < −80 dBFS | float vs. double, Reihenfolge der Summation |
| Hall (FFT-Faltung) | RMS-Differenz < −70 dBFS | FFT-Rundung |
| Signalsmith-Warp | Länge exakt; Klicks ±1 ms im Zielraster; RMS je Takt ±0,2 dB; Korrelation mit Python ≥ 0,99 | Compiler und SIMD verändern Signalsmith minimal |
| `backen` gesamt | `startN`, Längen exakt; Audio wie Warp | — |
| Decoder (Android vs. ffmpeg) | Länge ±1 Frame je 10 s nach Encoder-Delay-Korrektur; RMS je Sekunde ±0,5 dB | verschiedene Decoder |

### 12.4 Definition of Done je Aufgabe

- Build grün (`./gradlew assembleDebug`), alle Tests grün (`./gradlew test`,
  Host-C++-Tests).
- Neuer Code hat seinen Test (Golden oder Unit).
- Keine neuen Lint-Fehler, keine Warnungen im C++-Build (`-Wall -Wextra`).
- Callback-Regeln eingehalten (Review: kein `new`, `std::vector`-Wachstum,
  `std::mutex`, `__android_log_print` im Callback-Pfad).
- Fortschrittsbericht geschrieben (§0 Regel 8).

---

## 13 · numpy → Kotlin/C++: Fallen, die Golden-Tests rot machen

| numpy/Python | Falle | Richtig in Kotlin/C++ |
|---|---|---|
| `np.round(x)`, `round(x)` | Banker's Rounding (0,5 → 0, 1,5 → 2) | Kotlin `Math.rint(x)`, C++ `std::nearbyint` (Standard-Rundung) — **nicht** `Math.round` |
| `int(x)` | schneidet zur Null ab | `x.toInt()` ist gleich; `floor` nur, wo Python `//` nutzt |
| `a // b` bei negativen Zahlen | rundet ab (−7 // 8 = −1) | `Math.floorDiv(a, b)`; Python-Trick `-(-a // b)` = Aufrunden → `-Math.floorDiv(-a, b)` |
| `%` bei negativen Zahlen | Ergebnis hat Vorzeichen des Divisors | `Math.floorMod` |
| `np.percentile(x, p)` | lineare Interpolation, Rang `p/100·(n−1)` | genau so nachbauen (`NumpyCompat.percentile`) |
| `np.median` | gerade Anzahl: Mittel der zwei mittleren | — |
| `np.searchsorted(a, v, side)` | `left`: erster Index mit `a[i] >= v`; `right`: `a[i] > v` | eigene Binärsuche, beide Varianten |
| `np.argmin/argmax` | erster Treffer bei Gleichstand | Schleife mit `<` (nicht `<=`) |
| `np.interp` | klemmt außerhalb auf Randwerte | `uebergang._ext` dagegen setzt linear fort — zwei verschiedene Funktionen |
| `np.linspace(a, b, n, endpoint=False)` | Schritt `(b−a)/n` | auf `endpoint` achten |
| `np.mean([])` | NaN mit Warnung | prüfen, ob der Python-Code den Fall erreicht; sonst wie Python NaN |
| `x[a:b]` mit `b > len` | wird stillschweigend gekürzt | Grenzen klemmen |
| `x[-n:]` | negative Indizes | ausrechnen |
| `sorted(..., key)` / `list.sort` | stabil | Kotlin `sortedBy`/`sortedWith` ist stabil; C++ `std::stable_sort` |
| `max(d, key=d.get)` | erster größter Schlüssel in Einfügereihenfolge | `LinkedHashMap` und Schleife mit `>` |
| `dict.fromkeys(liste)` | Reihenfolge bleibt, Duplikate raus | `LinkedHashSet` |
| float32 vs. float64 | numpy rechnet oft in float32 (Arrays `np.float32`), Skalare in float64 | Typ je Ausdruck aus dem Python-Code ablesen |
| `np.clip` mit `a_min > a_max` | — | kommt nicht vor; nicht abfangen |
| `np.random.default_rng(7)` | nicht nachbaubar | Werte als Asset exportieren (§5.9) |

---

## 14 · Namen: Python (Deutsch) → Android (Englisch)

| Python | Kotlin/C++ |
|---|---|
| `Wiedergabe` | `AutoDjController` |
| `Spur` | `Spur` (C++) / `SpurInfo` (Kotlin, mit `orig`, `buf`) |
| `Eintrag` | `LibraryEntry` |
| `Einstellungen` | `Settings` (Feldnamen bleiben **deutsch**, wegen JSON-Gleichheit) |
| `Profil` | `Profile` |
| `regie.planen` | `Regie.plan` |
| `Plan` (Regie) | `TransitionPlan` |
| `backen` / `Gebacken` | `Baker::bake` / `BakeResult` |
| `warp` | `Warp::warp` |
| `mischen`, `mischen_eigen` | `Mixing::mix`, `Mixing::mixCustom` |
| `_huellen` | `Mixing::envelopes` |
| `_begrenzen` | `Limiter::limit` |
| `band_teilen` | `Filters::bandSplit` |
| `vorbereiten` | `prepareNext` |
| `_umschalten` | `onSwitched` |
| `weiter`, `anders` | `skipNext`, `otherTransition` |
| `einreihen`, `entfernen`, `verschieben`, `leeren`, `sortieren` | `enqueue`, `remove`, `move`, `clearQueue`, `sortAll` |
| `zustand` | `MixerState` |
| `vorlieben`, `_lernen` | `preferences`, `learn` |

Die **Werte** in Einstellungen, Rezeptnamen, Etiketten und `info` bleiben
deutsch (`"ausgewogen"`, `"outro_loop"`, `"drop"`). Sie sind Datenformat, und
die Golden-Tests vergleichen sie wörtlich.

---

## 15 · Risiken und offene Entscheidungen

| # | Risiko / Frage | Wirkung | Gegenmaßnahme / wer entscheidet |
|---|---|---|---|
| R1 | Ohne Stem-Profil kennt die Regie keinen Gesang | mehr Gesang-gegen-Gesang als am PC | S1: Profile mit Stems vom PC importieren (§9.3). Betrifft dann nur neue Titel ohne PC-Lauf. |
| R9 | Wisch-Gesten kollidieren (Wellenform zieht beim Cover-Wischen, Systemgeste am Rand) | Fehlbedienung wie bei Poweramp-Nutzern berichtet | getrennte Flächen, `systemGestureExclusion`, Seek erst beim Loslassen (§8.4) |
| R10 | Stem-Fenster je Playlist brauchen viel Speicher (~16 MB je Fenster) | Speicher voll | Grenze 2 GB, Opus-Upgrade (§9.3 S2) |
| R2 | `small0` weicht von `final0` ab | Raster daneben, Übergänge „galoppieren" | Tor G-A. Notfalls `final0` im APK (Nutzer entscheidet: +70 MB). |
| R3 | Signalsmith weicht trotz gleichem Commit ab | Golden-Tests rot | Toleranzen §12.3 sind auf Hörbarkeit gesetzt, nicht auf Bitgleichheit. |
| R4 | Backzeit auf Mittelklasse > Vorlauf | Übergänge kommen eine Phrase später | `backzeit`-Regel aus dem Desktop (`1,5·backzeit + 1`) gilt; §10.3 kürzt Längen. |
| R5 | MediaCodec-Seek ungenau bei MP3 | — | Umgangen: Es wird nie gesucht, der PCM-Cache ist sample-genau. |
| R6 | Speicher für PCM-Cache (bis 4 × 42 MB) | voller Speicher | Grenze 4 Dateien; bei < 500 MB frei nur 2. |
| R7 | HTDemucs-Gewichte ohne Lizenz | keine Stems | Tor G-S; Nutzer klärt Lizenz. |
| R8 | Sortieren von 8 000 Titeln | Wartezeit | BPM-Fenster (§6.1), auf dem Planer-Thread mit Fortschritt. |
| E1 | ADR-023 (eine Engine für alles) annehmen? | Architektur | **Nutzer** |
| E2 | Paketname und App-ID | Store | **Nutzer** |
| E3 | Testgeräte (Mittelklasse + Oberklasse), welche Modelle? | Messwerte | **Nutzer** |
| E4 | Auto-DJ-Quelle „aktuelle Liste" statt ganze Bibliothek (§6.2) | Verhalten | Vorschlag; **Nutzer** bestätigt |
| E5 | AudioShake wegen SDK-Preis anfragen (info@audioshake.ai) | Weg zu Stems für Kunden | **Nutzer** schreibt die Anfrage |
| E6 | Stem-Weg für Kunden: AudioShake, eigenes Modell, HTDemucs mit Freigabe oder nur Gesangs-Erkennung (§9.3 S3) | Produkt, Kosten | **Nutzer**, nach E5 und Tor G-S2 |
| E7 | Wisch nach rechts im Auto-DJ = voriger Titel mit hartem Start (§8.4 B) | Verhalten | Vorschlag; **Nutzer** bestätigt |

---

## 16 · Kurzfassung für den Start

1. M0: Projekt, Golden-Export, ADRs.
2. M1–M2: Ton ohne Aussetzer, gapless, Seek. **Erst messen, dann weiter.**
3. M3: Desktop-Analyse importieren, inklusive Stem-Profilen (Stufe S1). Ab hier
   gibt es echte Musik auf dem Handy, und die Regie kennt den Gesang.
4. M5–M6: DSP und `backen` in C++, Stück für Stück gegen Python geprüft.
5. M7–M8: Regie und Controller in Kotlin. Ab hier läuft der Auto-DJ.
6. M9: Oberfläche nach Mockups, Player-Gesten (§8.4) und Playlists mit
   „Optimale Reihenfolge" (§6.6).
7. M10: Analyse auf dem Handy.
8. M11: Stems auf dem Handy erst messen, dann „Set vorbereiten" für Playlists;
   Auslieferung an Kunden nur nach Lizenz. M12 Härtung.

Der wichtigste Satz: **Nichts schätzen, alles gegen den Desktop prüfen.** Der
Desktop klingt gut und hat 308 Tests. Android ist fertig, wenn es dieselben
Zahlen liefert und 1 h ohne Aussetzer läuft.

---

## 17 · Stand der Portierung (20.10.2026)

### 17.1 Kurzfassung

Android kann noch **keinen Auto-DJ**. Fertig sind der Abspielkern (T1.1/T1.2)
und sechs DSP-Bausteine (T5.1 bis T5.6), alle gegen Python-Golden geprüft.
Alles darüber fehlt: `mischen_eigen`, Loops, `_trocken`/`_deckeln`, Limiter,
Warp, `backen`, Regie, Titelwahl, Oberfläche, Analyse, Stems.

Die App selbst ist weiterhin der Diagnose-Screen „GERÜST · M0" und spielt einen
440-Hz-Testsinus. Es gibt fünf Kotlin-Dateien, keine Bibliothek, keinen Service,
keine Playlist.

### 17.2 Fertig und geprüft

| Aufgabe | Inhalt | Dateien |
|---|---|---|
| T1.1/T1.2 | Oboe-Stream, OutputRing, Callback, 10-ms-Rampen, Flush, Unterläufe | `oboe_output.*`, `output_ring.h`, `playback_core.h`, `jni_bridge.cpp` |
| T5.1 | `equal_power_blende`, `_rampe`, `_bass_rampen` | `dsp/curves.h` |
| T5.2 | Butterworth, `sosfilt`, `sosfiltfilt`, `band_teilen` | `dsp/filters.*` |
| T5.3 | `_fade_segment`, `mischen` (eq, filter, echo, schnitt, crossfade) | `dsp/mixing.*` |
| T5.4 | `_huellen`, alle 83 Varianten aus `AUSWAHL` | `dsp/envelopes.*` |
| T5.5 | `_biquads`, `_sweep`, `_baender_gewichten` | `dsp/sweep.*` |
| T5.6 | `_nass` (Hall, Echo, Delay, Ping-Pong), FFT, Hall-IR als Asset | `dsp/effects.*`, `dsp/fft.*`, `assets/hall_ir.f32` |

**Teststand 20.10.2026:** `dsp_golden_test` 24/24 grün, `playback_core_test`
18/18 grün, `klangbild_hosttest` (Golden-Leser) 6/6 grün.

### 17.3 Offen

| Aufgabe | Python-Vorlage | Golden-Fälle |
|---|---|---|
| T5.7 | `_takt_db`, `_deckeln`, `_trocken` | `deckeln_*` |
| T5.8 | `_loop_plan`, `_achtel`, `_loopen`, `loop_info` | `loop_*` |
| T5.9 | `_beat_merkmale`, `_aehnlich`, `loop_waehlen` | `loopwahl_*` |
| T5.10 | `_intro_loop` | `introloop_*` |
| T5.11 | `mischen_eigen` **und die Trick-Audio-Pfade** (`_bremse`, `_spinback`, `_flanger`, `_phaser`, `_gate`, `_crush`, `_rueckhall`, `_riser`) | `eigen_*` (14) |
| T5.12 | `kurven`, `kurven_eigen` | `kurven_*` (19) |
| M6 | Signalsmith, `warp`, `_warp_keylock`, `backen` | `warp_*`, `backen_*` |
| M7 | `regie.planen`, `_rezept`, `_rangliste`, `pruefen`, `plan.sortiere_alle`, `paarnoten` | `regie_*`, `pruefen_*`, `rangliste_*`, `sortiere_332` |
| M8 | `live._auto_backen`, `_autodj_wahl`, Energiebogen, Lernen, Dubletten | — |
| M10 | `beats`, `anker.versatz`/`fein`/`taktphase`, `profil`, `keyestimate`, `lufs`, `energy`, `welle` | `key_*`, `lufs_*`, `energie_*`, `welle_*`, `profil_*`, `beatthis_synthetic` |
| M11 | Stems | — |

**Wichtig für T5.11:** `envelopes.cpp` kennt nur die Tricks `wechsel` und
`teaser`. Alle anderen Trick-Strings laufen dort ohne Wirkung durch. Die
eigentliche Klangwirkung steckt im Desktop in `mischen_eigen` (Audio-Ebene) und
muss mit portiert werden. Ebenso sind `loop`, `loopStart`, `loopIn`,
`loopInTimes` in `settings.h` noch ein toter Vertrag: keine DSP-Funktion liest
sie.

### 17.4 Golden-Satz

- **362 Fälle**, 484 Dateien (mit `.f32`). Erzeugt aus dem Desktop-Stand
  `040887f` (Runden 18/19).
- In C++ wirklich nachgerechnet werden **rund 120**: `reader_dummy`,
  `kurven_basis`, `band_*` (7), `mischen_*` (15), `huellen_*` (83), `sweep_*`
  (4), `nass_*` (9). Der Rest, **rund 242 Fälle**, wird nur geparst.
  Besonders betroffen: `einstellungen_*` (129), `key_*` (12), `eigen_*` (14),
  `kurven_*` (19), `regie_*` (6), `loop_*` (7), `limiter_*` (5),
  `regulaer_*`/`ausstieg_*`/`einstieg_*` (9), `backen_*` (4).
- Die `.f32`-Referenzarrays sind per `.gitignore` ausgeschlossen (118 Dateien
  lokal, 1 im Repo). **In einem frischen Clone überspringen sich die meisten
  DSP-Tests selbst.** Vor dem Testlauf einmal exportieren:

  ```
  cd prototyp
  .venv/Scripts/python -m klangbild golden ../android/testdata/golden
  ```

- Der Export verlangt einen **leeren** Zielordner. Vorher die `.json` und
  `.f32` löschen, `.gitignore` behalten.
- `sos_44100.json` und `sos_22050.json` sind keine Manifest-Fälle, werden aber
  vom DSP-Test direkt gelesen.
- Zwei verwaiste Dateien entfernt: `huellen_eq_profi_expected_a_mitte.f32` und
  `..._b_mitte.f32` (im Manifest nicht referenziert).

### 17.5 Gefundene Abweichungen, bereits behoben

| Abweichung | Befund | Korrektur |
|---|---|---|
| Hall-Pegel | C++ `wetSignal` nutzte `0.8`, der Desktop seit Runde 16 aber `0.55` (`NASS["hall"]`). `nass_hall` fiel mit RMS −6,85 dB durch. | `dsp/effects.cpp` auf `0.55` gesetzt, Test grün. |
| Manifest-Quellhash | `sources["paarnoten.py"]` war veraltet (Export vor der letzten Änderung). | Golden-Satz neu erzeugt, Manifest übernommen. |
| Golden-Zeilenenden | Der Arbeitsstand hatte CRLF, der Export schreibt LF. | Inhaltlich identisch, kein Handlungsbedarf. |

Nach der Korrektur: **keine weiteren Abweichungen in den portierten Modulen.**
Alle Golden-Tests der sechs Bausteine sind grün.

### 17.6 Desktop ist eingefroren

Der Desktop gilt als fertig und wird **nicht mehr geändert**. Portier-Basis ist
Commit `040887f` („Runden 18/19: Fein-Anker, Kick-Kontrolle, Loop und Echo mit
der Rampe").

Golden-Daten werden nur neu erzeugt, wenn sich der Desktop ändert. Android-Code
wird **nie** angepasst, um einen Test zu bestehen, ohne dass die Ursache geklärt
ist.

### 17.7 Zwei Fälle ohne Golden-Referenz

`anker.fein` und `uebergang.taktraster` sind mit Runde 18/19 neu dazugekommen
und haben **keinen** Golden-Fall. Damit fehlt dem Android-Port der Zielwert für
den Fein-Anker.

Der Fall kann nur auf der Desktop-Seite ergänzt werden (`golden.py`, Funktionen
`anker.fein`, `anker.versatz`, `anker.taktphase`, `uebergang.taktraster` mit
einem synthetischen Kick-Signal). Bis dahin gilt: nicht blind nachbauen, sondern
den Desktop einfrieren und den Fall nachziehen. Ein brauchbares Testsignal ist
eine Kick-Folge bei 120 BPM (Schlag 0,5 s, Takt 2 s), erste Hälfte auf dem
Raster, zweite Hälfte 30 ms später.

### 17.8 Messlatte „exakt gleich"

Es gibt **keinen einzigen Golden-Fall mit einer echten Musikdatei**
(`manifest.json`: `"real_tracks": []`). Parität lässt sich damit nur für
Bausteine belegen, nicht für den ganzen Übergang. Für den Beweis „klingt wie der
Desktop" fehlen Aufnahmen mindestens je einer pro Übergangsart und pro Trick,
erzeugt über `python -m klangbild golden <ziel> --mit-echten-titeln` in den
separaten, ignorierten Ordner `<ziel>-real`.
