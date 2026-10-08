# Werkzeug- & Repo-Recherche: Android-Musikplayer mit Profi-Auto-DJ (Stand 2026)

Kriterium überall: **Ist kommerzielle Nutzung ohne Kauf erlaubt?**
Legende: ✅ = ja, kostenlos kommerziell nutzbar · ⚠️ = ja, aber mit Bedingungen (LGPL/Copyleft-Kleinigkeiten, Attribution) · ❌ = nein, Lizenzkauf nötig oder Copyleft blockiert geschlossene App · „unsicher" = nicht sicher verifiziert.

---

## 1. Echtzeit-Audio-Engine auf Android (niedrige Latenz)

**Oboe (Google)** — https://github.com/google/oboe
- Was: C++-Wrapper, der auf Android automatisch **AAudio (API 27+, bevorzugt)** und darunter **OpenSL ES** nutzt. Persistenter Streaming-Audio-I/O mit High-Priority-Callback.
- Plattform: Android native (C++/JNI), API 16+. Teil der AGDK Libraries.
- Lizenz: **Apache-2.0** → ✅ kommerziell frei.
- Reife: sehr aktiv, von Google gepflegt; ADC 2025-Talk zu AAudio MMAP/Oboe.
- Echtzeit: **ja** — `PerformanceMode::LowLatency` + `SharingMode::Exclusive` + AAudio MMAP für minimale Latenz.
- Quellen: https://developer.android.com/games/sdk/oboe · https://source.android.com/docs/core/audio/latency/app

**AAudio** — Android-Plattform-API (AOSP)
- Was: Native Low-Latency-API ab Android 8.1 (API 27); MMAP-Pfad für Extra-Latenzarmut.
- Lizenz: Teil von AOSP → ✅ (Gratis, kommerziell frei).
- Echtzeit: ja.

**OpenSL ES** — Legacy (ab API 9)
- Was: Ältere native Audio-API. Wird von Oboe als Fallback genutzt.
- Lizenz: Plattform-API → ✅.
- Echtzeit: ja, aber **nicht mehr empfohlen** für neue Projekte (Google empfiehlt Oboe/AAudio).

**Superpowered Audio SDK** — https://superpowered.com / https://docs.superpowered.com
- Was: Kommerzielles C++-SDK: Player, Decoder (MP3/AAC/…), Echtzeit-Time-Stretch, FX, BPM-/Key-/Beat-Detection, Offline-Extraktion, Mixing.
- Plattform: Android/iOS/macOS/tvOS/Windows/Linux (C++).
- Lizenz: **proprietär** → ❌ **kommerziell nur mit Kauf**. Evaluation-Lizenz: nur intern/R&D, max. **1.000 App-Installs**, danach deaktiviert das SDK.
- Preis: offiziell nur auf Anfrage; ein Community-Gist nennt **$6.000/Jahr (1 Plattform)** bzw. **$10.000/Jahr (Android+iOS)** → *unsicher* (nicht offiziell bestätigt).
- Reife: aktiv, etabliert.
- Echtzeit: **ja** (Kernkompetenz).
- Quellen: https://docs.superpowered.com/getting-started/licensing/ · https://superpowered.com/pricing · https://gist.github.com/bananasmoothii/43ac485b4aafb508e0a79900389b271d

**JUCE** — https://github.com/juce-framework/JUCE
- Was: C++-App-/Audio-Framework (inkl. Android), primär Plugins/Apps.
- Plattform: Android/Desktop/iOS.
- Lizenz: **dual — AGPLv3 ODER kommerzielle JUCE-Lizenz** → für eine **geschlossene kommerzielle App: ❌ kostenlos** (AGPL zwingt zur Quelloffenlegung) → kommerzielle Lizenz kostenpflichtig.
- Reife: sehr aktiv (JUCE 8, EULA-Änderungen).
- Echtzeit: ja.
- Quelle: https://juce.com/legal/juce-8-licence/

### Sample-genaues Mischen zweier Tracks — was nimmt man?
Nicht ExoPlayer. Man baut eine **eigene Native-Engine auf Oboe/AAudio**, in der **ein einziger Audio-Callback** beide Decks aus eigenen Puffern liest und im gleichen Sample-Raster mischt (gemeinsame Uhr). Decoding dann z. B. per MediaCodec (oder nativen Decodern) → PCM in Ring-Puffer pro Deck. Crossfade/Beat-Alignment/EQ rechnet man selbst.

### Grenzen von ExoPlayer/Media3 für beat-synchrones Mischen
- `DefaultAudioSink` nutzt AudioTrack mit **>250 ms Puffer** (bewusst gegen Underruns) → für latenzkritische, sample-genaue Mischung unbrauchbar. Siehe https://github.com/google/ExoPlayer/issues/8970
- Es gibt **keine Zwei-Deck-/Beat-Match-API**. Man kann nur `AudioProcessor`-Ketten (Effekte) in die Render-Pipeline hängen und einen eigenen `AudioSink` bauen — für Beatmatching-Ansätze (Community-Frage seit 2017) ist das der falsche Layer.
- **Gapless**: Media3 kann gapless (Encoder-Delay/Padding-Metadaten), auch für Playlists im compressed-offload-Modus — das ist aber „nacheinander ohne Lücke", kein Beatmatching.
- Quellen: https://stackoverflow.com/questions/44779628/beat-matching-crossfade-with-exoplayer · https://github.com/google/ExoPlayer/issues/6180

---

## 2. Time-Stretch / Pitch-Shift (Tempostrecken ohne Tonhöhenänderung)

**Rubber Band Library** — https://github.com/breakfastquay/rubberband
- Was: Sehr hochwertiges Time-Stretch/Pitch-Shift (R2/R3-Engines), Echtzeit-Streaming.
- Plattform: C++ (portabel, Android via NDK).
- Lizenz: **GPL v2+ ODER kommerzielle Lizenz** → ❌ **kommerziell ohne Kauf: NEIN**. Breakfast Quay verlangt für proprietäre Distribution (inkl. Apple App Store) eine kostenpflichtige Lizenz.
- Reife: aktiv, Referenz-Qualität.
- Echtzeit: **ja**.
- Quelle: https://breakfastquay.com/rubberband/license.html

**SoundTouch** — https://www.surina.net/soundtouch/
- Was: Etablierte Time-Stretch/Pitch-Shift-Bibliothek (WSOLA-artig), viele Android-Ports.
- Plattform: C++ (NDK), Java-Ports existieren (z. B. qingmei2/soundtouch-android).
- Lizenz: **LGPL v2.1** → ⚠️ **kommerziell JA** (bei dynamischem Linken + Änderungen offenlegen).
- Reife: stabil/ausgereift, aber kaum neue Entwicklung.
- Echtzeit: ja, aber **Qualität/Audioarteakte schlechter** als Rubber Band/Signalsmith (Mixxx nutzt es als „schnellere" Option).

**zplane élastique (Pro / Efficient / Pitch)** — https://licensing.zplane.de/licensing
- Was: De-facto-Industriestandard für Time-Stretch/Pitch (Pro = höchste Qualität, Efficient = sparsamer).
- Plattform: Multi-Plattform-SDK (C++), u. a. mobil.
- Lizenz: **proprietär**, typischerweise **Royalty pro verkauftem Stück** + Vertrag → ❌ **kommerziell nur mit Kauf**.
- Reife: aktiv, „in den meisten DAWs".
- Echtzeit: **ja** (zplane bewirbt „realtime … perfect for DJing").
- Quellen: https://licensing.zplane.de/licensing · https://www.licensing.zplane.de/uploads/SDK/ELASTIQUE-PRO/V3/manual/elastique_pro_v3_sdk_documentation.pdf

**Signalsmith Stretch** — https://github.com/Signalsmith-Audio/signalsmith-stretch
- Was: C++11 **header-only** Pitch/Time-Stretch (transient-aware Phase-Vocoder), auch polyphon.
- Plattform: überall (C++11), auch Android; in Qt6 als Drittanbieter-Bibliothek enthalten.
- Lizenz: **MIT** → ✅ **kommerziell frei**.
- Reife: **aktiv** (Updates 2026).
- Echtzeit: ja; klingt am besten bei moderaten Dehnungen (≈0.75×–1.5×).
- Quellen: https://signalsmith-audio.co.uk/code/stretch/ · https://doc.qt.io/qt-6/qtmultimedia-attribution-signalsmith-stretch.html

**Sonic (Bill Cox)** — https://github.com/waywardgeek/sonic
- Was: ANSI-C-Bibliothek zum Schneller/Langsamer-Abspielen (Tempo) + Pitch; **Java-Port (Sonic.java)** und **NDK-Wrapper (sonic-ndk)** enthalten.
- Lizenz: **Apache-2.0** → ✅ kommerziell frei.
- Reife: **dormant** (letzte Änderung 2017).
- Echtzeit: Streaming-API ja; **optimiert für Sprache/Speed-up >2×**, für Musik nur begrenzte Qualität.

**Was nutzen Traktor/Serato/Mixxx/VirtualDJ?**
- **Traktor**: zplane élastique (HiQ-Modus). Quelle: https://djtechtools.com/2009/11/09/time-stretching-comparison-torq-1-5-vs-ableton-live-8/
- **Mixxx**: umschaltbar **SoundTouch** („faster") oder **Rubber Band** (Keylock/Pitch-Bending Engine). Quelle: Mixxx-Manual „Preferences".
- **Serato**: eigene Algorithmen / Serato „Pitch 'n Time" → *unsicher*, ob zplane (nicht verifiziert).
- **VirtualDJ**: *unsicher* (üblich wird zplane élastique vermutet, nicht bestätigt).

---

## 3. Beat-/Tempo-/Downbeat-/Tonart-Erkennung

**Essentia (MTG)** — https://github.com/MTG/essentia
- Was: Umfangreiche C++-MIR-Bibliothek (Rhythm/Tonal/Spectral, ML-Modelle), Python-Bindings.
- Plattform: C++/Python. **Android**: cross-compile grundsätzlich möglich (Community-Repo `USCombo/essentia-for-android`); kein offizieller Android-Build/Java-Bindings.
- Lizenz: **AGPLv3** → ❌ **kommerziell ohne Kauf: NEIN**. Zusätzlich: **Modelle CC BY-NC-ND 4.0** (nicht-kommerziell); kommerzielle Lizenz auf Anfrage.
- Reife: aktiv in Forschung.
- Echtzeit: teils (Streaming-Algos), Musik-Extraktor eher Batch/offline.
- Quellen: https://essentia.upf.edu/licensing_information.html · https://github.com/USCombo/essentia-for-android

**aubio** — https://github.com/aubio/aubio
- Was: Onset-/Pitch-/Tempo-/Beat-Detection in C, Python-Bindings.
- Plattform: C. **Android**: offizielle Build-Skripte (`scripts/build_android`) + NFT-Modul `adamski/aubio-android`.
- Lizenz: **GPLv3** → ❌ **kommerziell ohne Kauf: NEIN**.
- Reife: gewartet, aber langsam.
- Echtzeit: **ja** (onset/tempo live).
- Quellen: https://aubio.org/manual/latest/installing.html · https://github.com/adamski/aubio-android

**madmom (CPJKU)** — https://github.com/CPJKU/madmom
- Was: Python-MIR, State-of-the-Art Beat/Downbeat/Tempo/Onset/Chords (RNN/DBN).
- Plattform: **Python** → nicht on-device. Für Android nur als Offline-/Server-Schritt oder via Portierung/Export.
- Lizenz: **Quellcode BSD-2-Clause (✅ kommerziell)** — **ABER Modelle/Daten CC BY-NC-SA 4.0** → eine Distribution mit Modellen ist **❌ nicht kommerziell**. Gemischt!
- Reife: weitgehend dormant (letzte große Releases ~2018/0.16).
- Echtzeit: nein (praktikabel).
- Quellen: https://github.com/CPJKU/madmom/blob/main/LICENSE · https://arxiv.org/html/1605.07008v1

**librosa** — https://github.com/librosa/librosa
- Was: Python-Audioanalyse (Beats, Tempo, Spektral, Chroma).
- Plattform: Python → Offline/Precompute (Bibliothek scannen, Tags schreiben) oder Server.
- Lizenz: **ISC** → ✅ **kommerziell frei**.
- Reife: sehr aktiv.
- Echtzeit: nein.

**libKeyFinder (Mixxx)** — https://github.com/mixxxdj/libKeyFinder
- Was: C++11-Tonart-Erkennung (Krumhansl-Schmuckler-Varianten).
- Plattform: C++ (NDK-fähig), keine offiziellen Java-Bindings.
- Lizenz: **GPL v3+** → ❌ **kommerziell ohne Kauf: NEIN**.
- Reife: gepflegt (Mixxx-Umfeld).
- Echtzeit: schnell genug (~near-realtime/offline).

**QM-DSP (Queen Mary, C4DM)** — https://github.com/c4dm/qm-dsp
- Was: C++-DSP/MIR inkl. **Beat-Tracker** (Onset → Resonator-Bank → Viterbi → DP) — von Mixxx genutzt.
- Plattform: C++ (NDK möglich).
- Lizenz: **GPL v2+** → ❌ **kommerziell ohne Kauf: NEIN**.
- Reife: gepflegt (Vamp-Umfeld); von Mixxx produktiv eingesetzt.
- Echtzeit: ja-ish (Analyse).
- Quellen: https://github.com/gigawhitlocks/queen-mary-beat-detector · https://github.com/mixxxdj/mixxx/wiki/Developer-Guide-Analysers

**BeatRoot** — historische Java-Beat-Tracking-Referenz.
- Lizenz: **GPL** (Version nicht verifiziert) → ❌ kommerziell **unsicher/nein**.
- Android: Java → theoretisch, aber veraltet.

**Fazit Java/Kotlin-Bindings:** Für die brauchbaren Analyse-Tools gibt es praktisch **keine** offiziellen Java/Kotlin-Bindings (aubio hat JNI-Wrapper; Essentia nur C++/Python). Für eine kommerzielle App heißt das: **eigene Analyse implementieren, kommerzielle Lizenz kaufen (zplane/Superpowered) oder offline/precompute** mit permissiv lizenzierten Tools (librosa ISC, madmom-Code BSD).

---

## 4. Open-Source-DJ-Software zum Studieren/Reusen

**Mixxx** — https://github.com/mixxxdj/mixxx
- Was: Vollwertige OSS-DJ-Software. **Engine-Architektur**: drei Threads (Audio/Engine, GUI, Library-Scan), Audio-Callback alle **5–20 ms**; Per-Deck-Playback, Time-Stretch (SoundTouch/Rubber Band), Rate-Kontrolle, BPM-Sync, Cueing, Looping, FX.
- Genutzte Bibliotheken: **SoundTouch** + **Rubber Band** (Keylock), **QM-DSP** (Queen Mary Beat-Detector), **libKeyFinder** (Key, optional), **libebur128** (ReplayGain/Loudness-Analyse).
- **Stems**: GSoC 2024 = Playback von `.stem.mp4` mit Fader pro Stem (Mixxx 2.6); GSoC 2025 = **Demucs v4 → ONNX** Konvertierung.
- Lizenz: **GPL v2** → ❌ Übernahme von Code in eine **geschlossene kommerzielle App problematisch** (Copyleft). Studieren ja, Code-Reuse nur mit Vorsicht.
- Reife: sehr aktiv.
- Quellen: https://deepwiki.com/mixxxdj/mixxx/4-audio-engine · https://mixxx.org/news/2024-08-26-stem-mixing/ · https://mixxx.org/news/tag/stems/

**DJ Sugar** — https://github.com/winnerspiros/djsugar
- Was: **Mixxx-Fork mit Android-Support** (+YouTube-Suche). GPL (Fork). Reifegrad: Community-Projekt.

**MWEngine (igorski)** — https://github.com/igorski/MWEngine
- Was: **Audio-Engine/DSP für Android in C++ mit Java/Kotlin-API**, sample-genaues Scheduling von Audio-Events, Effekte.
- Plattform: Android (C++ + JNI → Java/Kotlin).
- Lizenz: **unsicher** (in dieser Recherche nicht bestätigt — vor Nutzung prüfen!).
- Echtzeit: ja (Musik-Kontext).

**Weitere konkrete Projekte**
- `loretoparisi/Low-Latency-Android-Audio-iOS-Audio-Engine` — Referenz-Architektur (Superpowered-basiert).
- `Fr4nKB/SpleeterAndroidPort` — Kotlin/TFLite-Stem-Trennung auf Android.
- `StemSplit/demucs-onnx` + HF `nsosu/demucs-onnx` — **on-device Stem-Trennung, genutzt von der Android-App „DJNed"**.
- `sevagh/ElectroPARTYogram` — native C++ Android-App mit Echtzeit-Beat-Detection (Studienobjekt).
- Achtung: `rayocta303/UNX-DJ-ENGINE` (nennt Mixxx/Rubber Band/SoundTouch) — Herkunft/Qualität unklar, nur als Ideensammlung.

---

## 5. Effekte (Reverb, Echo, Filter, 3-Band-EQ) in Echtzeit

**Android AudioEffect (Framework)** — `android.media.audiofx.*`
- Klassen: **Equalizer, BassBoost, Virtualizer, PresetReverb, EnvironmentalReverb, DynamicsProcessing (API 28+), LoudnessEnhancer**.
- Was: Systemeffekte, an eine **AudioSessionId** (AudioTrack/MediaPlayer) gebunden.
- Lizenz: AOSP → ✅ **gratis/kommerziell frei**.
- Echtzeit: ja, **aber**: geräteabhängiges Verhalten, teils Latenzprobleme beim Anhängen an bereits laufende Streams, begrenzte Kontrolle, Preset-Reverbs sind schlicht. Für einen DJ-Mix zweier Decks zu unflexibel.
- Für 3-Band-EQ/Filter: `DynamicsProcessing` (Multi-Band-EQ + Kompressor + Limiter) oder ein `Equalizer` mit N Bändern (für Custom nicht ideal).
- Quellen: https://developer.android.com/reference/android/media/audiofx/AudioEffect · https://source.android.com/docs/core/audio/audio-effects

**Superpowered FX** — https://docs.superpowered.com
- Was: **Echo/Delay, Reverb, Filter (LP/HP/Shelf/Bandpass/Notch/Parametric), 3-Band- & N-Band-EQ, Flanger, Bitcrusher, Gate, Kompressor, Limiter**.
- Lizenz: proprietär → ❌ **Kauf nötig**. Echtzeit: ja.
- Quellen: https://superpowered.com/echo · https://superpowered.com/js-audio-library-sdk

**Signalsmith dsp** — https://github.com/Signalsmith-Audio/dsp
- Was: C++-header-only Basis-DSP-Klassen (Filter, Delay etc.), MIT → ✅ kommerziell frei, Echtzeit ja.

**Custom-DSP (Empfehlung)**
- Für eine kommerzielle, voll kontrollierte FX-Kette: **eigene Biquad-/SVF-Filter, eigener Delay/Echo, eigener 3-Band-EQ**, kombiniert mit MIT-Bausteinen (Signalsmith DSP, `q`-Library etc.). Praktikabel und lizenzfrei.
- **Praktikabelste Kombination**: Systemaudio-Effekte (gratis) für „einfache" Fälle, sonst **Custom-DSP**; Superpowered-FX nur mit Budget.

---

## 6. On-Device-KI-Laufzeit (Embedding-Modell + Sprachmodell)

**LiteRT (früher TensorFlow Lite)** — https://developers.google.com/edge/litert
- Was: Googles On-Device-ML-Runtime (Nachfolger von TFLite), Basis für ML Kit, MediaPipe, Gallery.
- Lizenz: **Apache-2.0** → ✅ kommerziell frei. Reife: aktiv, Standard.

**LiteRT-LM** — https://github.com/google-ai-edge/LiteRT-LM
- Was: Production-Ready-Inferenz-Framework für **LLMs auf Edge** (lädt `.litertlm`-Bundles; CPU/GPU/NPU). Läuft in Chrome, Chromebook Plus, Pixel Watch.
- Lizenz: **Apache-2.0** → ✅ kommerziell frei.
- Reife: aktiv (6k+ Stars, Releases 2026).
- **2026 der empfohlene Weg für Production auf Android** (Google-Doku + Blog „Blazing fast on-device GenAI with LiteRT-LM", Mai 2026).

**MediaPipe LLM Inference API** — https://developers.google.com/edge/mediapipe/solutions/genai/llm_inference
- Status: **maintenance-only / für Android & iOS deprecated** → **zu LiteRT-LM migrieren**. Web bleibt GA.
- Nicht mehr für neue Android-Projekte.

**MediaPipe Tasks (Universal Embedder / Semantic Retriever / Decision)** — https://developers.google.com/edge/mediapipe/solutions/tasks
- **Universal Embedder**: multimodale Embeddings (Text/Bild/Audio), 768-dim, per MRL auf 128–512d kürzbar.
- **Semantic Retriever**: on-device ANN-Vektorsuche.
- Lizenz: Apache-2.0 → ✅. Android-Support vorhanden.

**EmbeddingGemma 2** — https://ai.google.dev/gemma/docs/embeddinggemma/model_card_2 / https://blog.google/innovation-and-ai/technology/developers-tools/embeddinggemma-2/
- Was: **740M-Parameter, multimodales** Open-Weight-Embedding-Modell (Text/Code/Bild/Video/Audio) in **einem** Vektorraum; **768-dim** (MRL-slicebar); **~191 MB** aktiv für Text-only, **~567 MB** multimodal (Pixel 11 Pro). Release **6. Okt 2026**.
- Deployment: LiteRT (`.litertlm`, INT4/INT8-QAT) ODER MediaPipe Tasks (Universal Embedder/Semantic Retriever); ML-Kit-Integration „in den kommenden Wochen".
- Lizenz: *unsicher* — ein Sekundärbericht nennt **Apache-2.0** (kommerziell frei), offiziell läuft die Gemma-Familie aber unter **Gemma Terms of Use** (kommerziell erlaubt **mit** Nutzungsbeschränkungen). **Modellkarte prüfen.**

**Gemma 4** — https://ai.google.dev/gemma/docs/core
- Was: Google Open-Weights-LLM-Familie, **Text+Audio+Bild**, bis **256K Kontext**; Größen **E2B/E4B/12B/26B-A4B/31B**. Release April 2026.
- Lizenz: **Gemma-Lizenz (custom, nicht OSI-Open-Source)** → kommerzielle Nutzung erlaubt, aber Prohibited-Use-Policy + Weitergabepflicht der Terms. Nicht „Open Source" i. e. S.

**ONNX Runtime Mobile** — https://onnxruntime.ai/docs/tutorials/mobile/
- Lizenz: **MIT** → ✅ kommerziell frei. Android-AAR verfügbar (`com.microsoft.onnxruntime:onnxruntime-android`).
- Reife: aktiv. Echtzeit: ja (kleine Modelle).

**llama.cpp** — https://github.com/ggml-org/llama.cpp
- Lizenz: **MIT** → ✅ kommerziell frei. Android: NDK/JNI-Builds, OpenCL-Backend für Adreno-GPUs.
- Reife: sehr aktiv. Echtzeit: eingeschränkt (CPU/GPU-Tokens).

**MLC-LLM** — https://github.com/mlc-ai/mlc-llm
- Was: Compiler-gestützte LLM-Inferenz (TVM), inkl. Android/iOS.
- Lizenz: Apache-2.0 (**in dieser Recherche nicht verifiziert → unsicher**).

**Google AI Edge Gallery** — https://github.com/google-ai-edge/gallery
- Was: **Quellcode-Referenz-App** (LiteRT-LM + Gemma 4 + EmbeddingGemma-2-Demos: „Instant Media Search", „Video Moments Finder"). Cross-platform.
- Lizenz: **Apache-2.0** → ✅ kommerziell als Referenz nutzbar.

**Empfehlung 2026 (Production, Android):**
- **Embeddings + Suche:** MediaPipe Tasks — **Universal Embedder (EmbeddingGemma 2) + Semantic Retriever**; alternativ direkt LiteRT mit `.litertlm`.
- **Sprachmodell:** **LiteRT-LM mit Gemma 4** (E2B/E4B fürs Phone). Auf Pixel-Geräten zusätzlich „Android AI Core / Gemini Nano" als managed Pfad.
- **Fallbacks** für maximale Kontrolle: ONNX Runtime Mobile (MIT) oder llama.cpp (MIT).

---

## 7. Vektor-Suche auf dem Gerät

**sqlite-vec (asg017)** — https://github.com/asg017/sqlite-vec
- Was: SQLite-Extension für Vektorsuche (Brute-Force/KNN), reines C.
- Plattform: **Android + iOS** (vorkompilierte Loadable-Libs ab v0.1.2 in Releases; läuft „anywhere", auch WASM).
- Lizenz: **MIT/Apache-2.0 dual** → ✅ kommerziell frei. Reife: aktiv (Mozilla Builders).
- Echtzeit: ja (kleine Datenmengen).
- Quelle: https://alexgarcia.xyz/sqlite-vec/android-ios.html

**USearch (unum-cloud)** — https://github.com/unum-cloud/USearch
- Was: Single-File-C++ **HNSW**-ANN, Bindings für viele Sprachen.
- Plattform: C++ → Android via NDK möglich.
- Lizenz: **Apache-2.0** → ✅ kommerziell frei. Reife: aktiv (v2.26.x, 2026). Echtzeit: ja.

**hnswlib** — https://github.com/nmslib/hnswlib
- Was: **Header-only C++** HNSW (ANN).
- Plattform: C++ → Android via NDK.
- Lizenz: **Apache-2.0** → ✅ kommerziell frei. Reife: stabil/wartungsarm. Echtzeit: ja.

**FAISS (Meta)** — https://github.com/facebookresearch/faiss
- Was: Hochperformante ANN/Vektor-Suche (HNSW/IVF/PQ, GPU).
- Plattform: **nicht offiziell mobil**; ARM-aarch64 läuft (Server/getestet), Android-Cross-Compile möglich, aber schwer/überdimensioniert.
- Lizenz: **MIT** → ✅ kommerziell frei. Echtzeit: ja (Desktop/Server).

**ObjectBox Vector Search** — https://github.com/objectbox/objectbox-java
- Was: On-Device-Objekt-DB **mit Vektor-Suche (HNSW)** neben normalen Daten; Java/Kotlin-API.
- Plattform: **Android/Kotlin-nativ** (+ JVM/iOS/…).
- Lizenz: Core-DB **Apache-2.0, gratis** (Vektor-Suche im kostenlosen Core) → ✅ **kommerziell frei**; **Sync/Enterprise** = kaufpflichtig.
- Reife: aktiv. Echtzeit: ja.
- Quellen: https://docs.objectbox.io/on-device-vector-search · https://objectbox.io/android-database/

**MediaPipe Semantic Retriever** — https://developers.google.com/edge/mediapipe/solutions/retrieval/semantic_retriever
- Was: Edge-optimierte **on-device ANN**-Suche über Embeddings; „single-digit milliseconds".
- Plattform: Android/iOS/Web/Desktop (MediaPipe Tasks). Lizenz: **Apache-2.0** → ✅.
- Ideal in Kombination mit **EmbeddingGemma 2 / Universal Embedder**.

**Zusatz:** `sqliteai/sqlite-vector` — cross-platform SQLite-Vektor-Extension, ~30 MB Default-Speicher, Android/iOS. Lizenz: vor Nutzung prüfen (**unsicher**).

---

## 8. Stem-Trennung auf dem Gerät

**Demucs (v4 / HT-Demucs)** — https://github.com/facebookresearch/demucs
- Was: State-of-the-Art-Quellentrennung (Drums/Bass/Vocals/Other; 6-stem mit Gitarre/Klavier); v5 mit besseren Transformern in Arbeit.
- Lizenz: **MIT** (Code; Gewichte MIT) → ✅ kommerziell frei.
- On-Device-Ports: **`StemSplit/demucs-onnx`** (HT-Demucs/Demucs-ONNX, numpy+onnxruntime, models auf HF), **genutzt von der Android-App „DJNed"**; Mixxx-GSoC2025 = Demucs v4 → ONNX.
- Rechenintensität: **hoch** — auf dem Phone **nicht echtzeitfähig**, pro Song Sekunden bis ~Minuten (CPU); am besten **offline/vorab**, gecacht, quantisiert (INT8/fp16).
- Modellgröße: htdemucs ~tens of MB, htdemucs_ft als Bündel größer (**exakte MB: unsicher**).
- Quellen: https://github.com/StemSplit/demucs-onnx · https://huggingface.co/nsosu/demucs-onnx

**Spleeter (Deezer)** — https://github.com/deezer/spleeter
- Was: Ältere TF-basierte Trennung (2/4/5 stems), sehr schnell auf GPU/Desktop.
- Lizenz: **MIT** → ✅ kommerziell frei.
- Android: **TFLite-Ports existieren** (`Fr4nKB/SpleeterAndroidPort`, `jinay1991`-tflite-Modell). **Aber**: TFLite-Binary/Modell groß (Community meldet ~23 MB+ bzw. Größenprobleme bis ~1,5 GB), Qualität schlechter als Demucs/RoFormer.
- Rechenintensität: hoch. Echtzeit on-device: **nein**.
- Quelle: https://github.com/deezer/spleeter/issues/518

**MDX-Net (via Ultimate Vocal Remover / UVR5)** — https://github.com/Anjok07/ultimatevocalremovergui
- Was: MDX-Net-Vocal-Separation (ONNX), in UVR integriert.
- Lizenz: **App/GUI MIT**; **Modelle einzeln prüfen** — `UVR_MDXNET_Main` ist **MIT**, andere UVR-Modelle können abweichen → **unsicher** bei einzelnen Modellen (kommerzielle Nutzung von Modell zu Modell unterschiedlich; es gibt GitHub-Diskussionen zur kommerziellen Redistribution).
- On-device: ONNX → Android via onnxruntime-mobile möglich, aber schwer. Echtzeit: nein.
- Quellen: https://huggingface.co/notabilia/uvr5-models/blob/main/UVR_MDXNET_Main.LICENSE · https://github.com/Anjok07/ultimatevocalremovergui/discussions/2307

**BS-RoFormer / Mel-Band-RoFormer** — https://github.com/lucidrains/BS-RoFormer
- Was: Aktuell beste Vocal-/Source-Separation (Band-Split + RoPE-Transformer).
- Lizenz: **Architektur-Code MIT** (lucidrains, ZFTurbo/Music-Source-Separation-Training) → ✅ Code. **Trainierte Gewichte je Repo unterschiedlich** (teils MIT, teils unklar) → **unsicher, einzeln prüfen**.
- On-device: derzeit **nicht praktikabel** (schwer). Echtzeit: nein.
- Quellen: https://arxiv.org/html/2310.01809v1 · https://huggingface.co/lumabeat/bs-roformer-sw

**Open-Unmix (sigsep)** — https://github.com/sigsep/open-unmix-pytorch
- Was: Leichtgewichtige Referenzimplementierung (4 stems), PyTorch.
- Lizenz: **MIT** (Code + umxhq-Zenodo-Modell) → ✅ kommerziell frei. Qualität < Demucs/RoFormer; On-device via ONNX denkbar.

**Ultimate Vocal Remover (UVR)** — https://ultimatevocalremover.com
- App: **MIT** ✅; nutzt fremde Modelle mit jeweils eigener Lizenz.

**Echtzeit-Fazit:** On-Device-Stem-Trennung in **Echtzeit ist 2026 nicht realistisch** (auch Serato/VirtualDJ lösen „Stems" mit Vorab-/Cloud- oder Desktop-Verarbeitung bzw. speziellen Dateien). Pragmatisch: **Vorab-Demixing (Demucs-ONNX, INT8) im Hintergrund**, Ergebnis cachen, dann Stems abspielen/mischen.

---

## 9. Audio-Metadaten / Tags

**jaudiotagger (JThink / RouHim-Fork)** — https://github.com/JThink/jaudiotagger
- Was: Java-Tag-Library (MP3/Ogg/FLAC/MP4/WMA/WAV/…), Lesen+Schreiben.
- Plattform: Java → **Android** über Fork (`hexise/jaudiotagger-android`, JDK-nio ⇒ **API 26+** nötig).
- Lizenz: **LGPL 2.1** → ⚠️ **kommerziell JA** (dynamisch linken/Änderungen offenlegen).
- Reife: alt, geringe Aktivität.

**TagLib** — https://taglib.org / https://github.com/taglib/taglib
- Was: C++-Tag-Library (MP3, FLAC, MP4, Ogg, WAV, …), sehr breite Formatabdeckung.
- Plattform: C++ → Android via NDK; **JNI-Bindings: `AmanRajAryan/AndroidTagLib`**.
- Lizenz: **LGPL v2.1 ODER MPL** (dual) → ⚠️ **kommerziell JA** (Änderungen an TagLib offenlegen).
- Reife: aktiv (v2.3.x). Emfpehlung für maximale Format-/Tag-Abdeckung.

**Android MediaMetadataRetriever** — `android.media.MediaMetadataRetriever`
- Was: Plattform-API zum **Auslesen** von Metadaten (Titel, Artist, Dauer, Cover) aus Dateien/Streams.
- Lizenz: AOSP → ✅ gratis/kommerziell frei.
- Grenzen: **kein Schreiben**, weniger Tags/Formate. Media3 ergänzt neuerdings `androidx.media3.inspector.MetadataRetriever`.

---

## 10. Playback-Basis: AndroidX Media3 / ExoPlayer

**Media3 / ExoPlayer** — https://github.com/androidx/media
- Was: Standard-Player-Stack (Playback, MediaSession, Android Auto, HLS/DASH, Transformer).
- Version 2026: **1.11.x** (Media3 1.10 = Mrz 2026, 1.11 = Aug 2026).
- Lizenz: **Apache-2.0** → ✅ kommerziell frei. Reife: aktiv, de-facto Standard.
- **Gapless**: ja (Encoder-Delay/Padding; gapless-Playlists auch im compressed-offload-Modus).
- **ReplayGain**: **kein eingebautes ReplayGain-Feature gefunden → unsicher**. Workaround: eigener `AudioProcessor`/Loudness-Anpassung; Android 15 `LoudnessCodecController` wird ab Media3 1.5.0 unterstützt (Systemlautheit).
- **Beatmatching**: nein (>250 ms AudioSink-Latenz, keine Zwei-Deck-API). Media3 → **nur** für die „normale" Wiedergabe/Bibliothek/MediaSession nutzen, **nicht** für den Auto-DJ-Mixer.
- Quellen: https://developer.android.com/jetpack/androidx/releases/media3 · https://android-developers.googleblog.com/2026/08/media3-1-11-whats-new.html

---

## Empfohlener Werkzeug-Stack (konkret)

| Baustein | Empfehlung | Lizenz | Kommerziell |
|---|---|---|---|
| **Player-Basis / UX** | AndroidX **Media3/ExoPlayer 1.11.x** für Bibliothek, „normale" Wiedergabe, MediaSession, Android Auto, gapless | Apache-2.0 | ✅ |
| **Audio-Engine (Auto-DJ-Mixer)** | Eigene C++-Engine auf **Oboe** (AAudio MMAP/Exclusive), **ein** Callback mischt beide Decks sample-genau | Apache-2.0 | ✅ |
| **Decoding** | MediaCodec (Plattform) oder native Decoder; **Achtung: FFmpeg-Build = LGPL/GPL wählen** | plattformabhängig | ⚠️ |
| **Time-Stretch / Keylock** | **Signalsmith Stretch (MIT)** als Default (0.75–1.5×); optional **SoundTouch (LGPL)** als Fallback | MIT / LGPL | ✅/⚠️ |
| **Analyse (BPM/Beat/Key)** | Lizenzkritisch → **offline/precompute mit librosa (ISC)** + Tags; on-device nur Eigen-/Kauf-Lösung | ISC + eigen | ✅ (Kauf bei on-device) |
| **Effekte** | **Custom-DSP** (Biquad/SVF-EQ, Delay, Filter) + **Signalsmith dsp (MIT)**; System-AudioEffects gratis für einfache Fälle | MIT / AOSP | ✅ |
| **Stem-Trennung** | **Demucs v4 → ONNX (MIT)** offline (INT8, gecacht), z. B. `demucs-onnx` | MIT | ✅ |
| **Vektor-Suche** | **MediaPipe Semantic Retriever** (wenn EmbeddingGemma 2) **oder** **sqlite-vec / USearch** | Apache-2.0 | ✅ |
| **Embeddings** | **EmbeddingGemma 2** via MediaPipe Universal Embedder / LiteRT | Gemma-Terms (kommerziell m. Auflagen) | ⚠️ |
| **Sprachmodell** | **LiteRT-LM + Gemma 4 (E2B/E4B)** | Apache-2.0 Runtime; Gemma-4-Lizenz für Gewichte | ⚠️ |
| **KI-Fallback** | ONNX Runtime Mobile (MIT), llama.cpp (MIT) | MIT | ✅ |
| **Tags** | **TagLib (LGPL/MPL)** via NDK/JNI; Read-only: MediaMetadataRetriever | LGPL/MPL | ⚠️/✅ |

---

## Die 3 größten Lizenzfallen

1. **GPL/AGPL-Copyleft in der Analyse-Schicht.** Essentia (**AGPLv3**), aubio (**GPLv3**), libKeyFinder (**GPLv3**), QM-DSP (**GPLv2**), Rubber Band (**GPLv2**) — in einer **geschlossenen kommerziellen App nicht ohne Kauf/Quelloffenlegung** nutzbar. Besonders tückisch: **AGPL (Essentia)** greift auch bei reinem Netzwerk-Betrieb. → Diese Tools eignen sich zum **Prototypen/Studieren**, produktiv aber nur mit Lizenzkauf oder eigener Implementierung.

2. **Creative-Commons-„NC"-Modelle.** **Essentia-Modelle = CC BY-NC-ND 4.0**, **madmom-Modelle = CC BY-NC-SA 4.0** → **nicht kommerziell**, auch wenn der Code permissiv ist (madmom-Code = BSD!). Ebenso: **Gemma/Gemma 4** sind „open weights", aber **kein OSI-Open-Source** (Prohibited-Use-Policy, Weitergabepflicht); **EmbeddingGemma 2** ist laut Sekundärquelle Apache-2.0, offiziell aber Gemma-Terms → **ungeklärt**.
   Zusatzfalle: **Superpowered-Evaluation-Lizenz** erlaubt nur **1.000 Installs** — eine versehentlich ausgelieferte Eval-Version deaktiviert sich.

3. **Versteckte Kosten / „kostenlos" ist relativ.** **Superpowered** (≈ $6k–10k/Jahr je Plattform, offiziell undurchsichtig) und **zplane élastique** (Royalty pro Stück) sind reine **Bezahl-SDKs**; **JUCE** ist dual (AGPL ⇒ für geschlossene App kaufpflichtig); **Rubber Band** verlangt für proprietäre/iOS-Distribution eine kostenpflichtige Lizenz. Und **einzelne Stem-Modelle** (UVR/MDX-Net, BS-RoFormer-Gewichte) haben von Modell zu Modell **abweichende** Lizenzen — immer das konkrete Gewicht prüfen.

---

## Quellen (Auswahl)
- Oboe: https://github.com/google/oboe · https://developer.android.com/games/sdk/oboe · https://source.android.com/docs/core/audio/latency/app
- Superpowered: https://docs.superpowered.com/getting-started/licensing/ · https://superpowered.com/pricing
- JUCE: https://juce.com/legal/juce-8-licence/ · https://github.com/juce-framework/JUCE/blob/master/LICENSE.md
- Rubber Band: https://breakfastquay.com/rubberband/license.html · https://github.com/breakfastquay/rubberband
- SoundTouch: https://www.surina.net/soundtouch/
- zplane élastique: https://licensing.zplane.de/licensing · https://licensing.zplane.de/technology
- Signalsmith Stretch: https://github.com/Signalsmith-Audio/signalsmith-stretch · https://doc.qt.io/qt-6/qtmultimedia-attribution-signalsmith-stretch.html
- Sonic: https://github.com/waywardgeek/sonic · https://github.com/waywardgeek/sonic-ndk
- Essentia: https://essentia.upf.edu/licensing_information.html · https://github.com/MTG/essentia
- aubio: https://aubio.org/ · https://aubio.org/manual/latest/installing.html
- madmom: https://github.com/CPJKU/madmom/blob/main/LICENSE
- librosa: https://github.com/librosa/librosa/blob/main/LICENSE.md
- libKeyFinder: https://github.com/mixxxdj/libKeyfinder
- QM-DSP: https://github.com/c4dm/qm-dsp · https://github.com/gigawhitlocks/queen-mary-beat-detector
- Mixxx: https://github.com/mixxxdj/mixxx · https://deepwiki.com/mixxxdj/mixxx/4-audio-engine · https://mixxx.org/news/2024-08-26-stem-mixing/
- MWEngine: https://github.com/igorski/MWEngine
- Android AudioEffect: https://developer.android.com/reference/android/media/audiofx/AudioEffect
- LiteRT / LiteRT-LM: https://developers.google.com/edge/litert · https://github.com/google-ai-edge/LiteRT-LM · https://developers.googleblog.com/blazing-fast-on-device-genai-with-litert-lm/
- EmbeddingGemma 2: https://developers.googleblog.com/en/google-ai-edge-with-embeddinggemma-2/ · https://blog.google/innovation-and-ai/technology/developers-tools/embeddinggemma-2/
- Gemma 4 & Terms: https://ai.google.dev/gemma/docs/core · https://ai.google.dev/gemma/terms
- MediaPipe LLM Deprecation: https://developers.google.com/edge/mediapipe/solutions/genai/llm_inference
- ONNX Runtime Mobile: https://onnxruntime.ai/docs/tutorials/mobile/ · llama.cpp: https://github.com/ggml-org/llama.cpp
- sqlite-vec: https://github.com/asg017/sqlite-vec · https://alexgarcia.xyz/sqlite-vec/android-ios.html
- USearch: https://github.com/unum-cloud/USearch · hnswlib: https://github.com/nmslib/hnswlib · FAISS: https://github.com/facebookresearch/faiss
- ObjectBox Vector Search: https://docs.objectbox.io/on-device-vector-search
- Demucs / ONNX: https://github.com/facebookresearch/demucs · https://github.com/StemSplit/demucs-onnx
- Spleeter: https://github.com/deezer/spleeter · UVR: https://github.com/Anjok07/ultimatevocalremovergui
- Open-Unmix: https://github.com/sigsep/open-unmix-pytorch · BS-RoFormer: https://github.com/lucidrains/BS-RoFormer
- TagLib: https://taglib.org/ · jaudiotagger: https://github.com/JThink/jaudiotagger
- Media3: https://github.com/androidx/media · https://developer.android.com/jetpack/androidx/releases/media3
