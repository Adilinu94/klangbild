# Entscheidungsprotokoll (ADR) — Klangbild

Jede architektonische Entscheidung als eigene, verlinkbare Datei. Format nach
dem üblichen ADR-Muster: Kontext, Entscheidung, Alternativen, Begründung,
Konsequenzen.

| Nr | Titel | Status |
|---|---|---|
| [ADR-001](ADR-001-eigene-engine-statt-media3.md) | Eigene native Engine statt Media3 für den Mixer | angenommen, ergänzt durch ADR-016 |
| [ADR-002](ADR-002-media3-fuer-den-player.md) | Media3 für den normalen Player | angenommen, ergänzt durch ADR-017 |
| [ADR-003](ADR-003-signalsmith-statt-rubberband.md) | Signalsmith Stretch statt Rubber Band | angenommen, ergänzt durch ADR-014 |
| [ADR-004](ADR-004-feste-tabelle-statt-reflection.md) | Feste Tabelle statt Reflection für Plugins | angenommen |
| [ADR-005](ADR-005-analyse-offline-librosa.md) | Analyse offline per librosa statt on-device | **abgelöst durch ADR-012** |
| [ADR-006](ADR-006-litert-statt-mediapipe-llm.md) | LiteRT/MediaPipe statt MediaPipe LLM Inference | angenommen, ergänzt durch ADR-015 |
| [ADR-007](ADR-007-vektoren-an-hash.md) | Vektoren an den Datei-Hash gebunden | angenommen, ergänzt durch ADR-013 |
| ADR-008 | Archiv bleibt ohne Zahlung lesbar | **ausgelagert** (gehört zum Produkt Belegkasten, liegt jetzt unter `G:\AI Agentur\`) |
| [ADR-009](ADR-009-kein-visualizer.md) | Kein Visualizer (EGL/GL) | angenommen |
| [ADR-010](ADR-010-zwei-decoder-slots.md) | Zwei Decoder-Slots | angenommen |
| [ADR-011](ADR-011-pc-prototyp-zuerst.md) | PC-Prototyp zuerst, Android später | angenommen, Offline-Wahl **abgelöst durch ADR-021** |
| [ADR-012](ADR-012-analyse-mit-permissiven-modellen.md) | Analyse mit permissiven Modellen statt librosa | angenommen, löst ADR-005 ab |
| [ADR-013](ADR-013-hash-ueber-audiodaten.md) | Hash nur über die Audiodaten | angenommen |
| [ADR-014](ADR-014-vinyl-angleich-in-v1.md) | Tempoangleich per Resampling in Version 1 | angenommen |
| [ADR-015](ADR-015-stimmung-per-zero-shot.md) | Stimmung per Zero-Shot, Gemma 4 optional | angenommen |
| [ADR-016](ADR-016-oboe-shared-statt-exclusive.md) | Oboe im geteilten Stromsparmodus | angenommen |
| [ADR-017](ADR-017-engine-als-media3-player.md) | Eigene Engine als Media3-Player | angenommen |
| [ADR-018](ADR-018-stems-im-uebergangsfenster.md) | Stems als Kern, nur im Übergangsfenster getrennt | angenommen (PC), Android offen |
| [ADR-019](ADR-019-uebergang-als-datenformat.md) | Übergänge als Datenformat statt fest im Renderer | angenommen (11.10.2026, Einstellungen = Rezept) |
| [ADR-020](ADR-020-vinyl-angleich-auf-1-prozent.md) | Vinyl-Angleich auf ±1 % begrenzen, bis Keylock kommt | angenommen, ergänzt ADR-014; mit Keylock ergänzt durch ADR-022 |
| [ADR-021](ADR-021-pc-mixer-in-echtzeit.md) | PC-Prototyp als Echtzeit-DJ-Mixer, keine Landingpage | angenommen |
| [ADR-022](ADR-022-keylock-und-tempo-als-einstellung.md) | Keylock jetzt, Tempo-Grenze als Einstellung, Taktraster aus dem Tempo | angenommen |

Die Nummer 008 bleibt vergeben und wird nicht neu belegt.

**Regel:** Eine angenommene Entscheidung wird nicht still geändert. Eine neue
Entscheidung, die eine alte ablöst, bekommt eine eigene Nummer und verweist auf
die abgelöste.

---

## Recherche-Belege 08.10.2026

Für die Ergänzungen in ADR-006, 012, 014, 015 und 016:

| Quelle | Was belegt ist |
|---|---|
| [EmbeddingGemma-2-Modellkarte](https://huggingface.co/google/embeddinggemma-2) | Apache 2.0; 740 M = 270 M Text + 170 M Bild + 300 M Audio; Stufen 270/440/570/740 M; MRL 768/512/256/128; Audio mono 16 kHz, 25 Token/s, ~327 s; Audio-Trainingsdaten: Sprache, Umweltklänge, akustische Events (Musik nicht genannt); Rechengenauigkeit bfloat16/float32; nach Kürzen normalisieren |
| [EmbeddingGemma 2: Developer Guide](https://developers.googleblog.com/embeddinggemma-2-the-developer-guide/) | Apache 2.0; Task-Präfixe nur für Text; Medien ohne Präfix; 256 d empfohlener Boden für Audio |
| [CPJKU/beat_this](https://github.com/CPJKU/beat_this) | Code und Gewichte MIT; `final0` ~78 MB, `small0` ~8,1 MB; mono 22 kHz + Spektrogramm-Parameter; Hinweis zu Trainingsdaten-Lizenzen |
| [google-ai-edge/litert-lm](https://github.com/google-ai-edge/litert-lm) | v0.18.0: EmbeddingGemma 2 multimodal inkl. Audio für Python, Kotlin, Swift, Web, C++; `litert-lm import`, `/v1/embeddings` |
| [google/oboe · samples/OboeDJ](https://github.com/google/oboe/tree/main/samples/OboeDJ) | Zwei Decks, Crossfader, Geschwindigkeitsmultiplikator, lineare Interpolation (Apache-2.0, nutzt LowLatency) |
| [mosynthkey/beat_this_cpp](https://github.com/mosynthkey/beat_this_cpp) | C++-Port mit ONNX-Gewichten, chunked Inference, MIT |
| [jiixyj/libebur128](https://github.com/jiixyj/libebur128) | MIT, reines C |
| Muse, MuQ/MuQ-MuLan, OpenL3, musicnn, CLAP | Lizenzlage für Plan B: CC-BY-NC bzw. nicht-kommerziell bzw. unklar bzw. im Original zu prüfen |
