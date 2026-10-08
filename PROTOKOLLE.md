# Protokolle und Register — Klangbild und Poweramp-Analyse

**Stand: 06.10.2026 · Ergänzung zu `WISSEN-POWERAMP-ARCHITEKTUR.md` und
`PRODUKT-KLANGBILD.md`**

Dieses Dokument sammelt alles, was **nachschlagbar** sein muss: Quellen,
Lizenzen, Zahlen, Namen, Entscheidungen, Geräte, Messverfahren. Es ist bewusst
ein Register, kein Fließtext.

**Leseregel:** Jede Aussage trägt einen **Sicherheitsgrad** (Abschnitt 10):
`belegt`, `geschlossen` oder `vermutet`. Wer eine Zahl ohne Kennzeichnung
findet, darf sie als `belegt` lesen, sofern eine Quelle steht.

---

## 1 · Provenienz-Register (Fakt → Quelle)

Jede wichtige Aussage aus der Poweramp-Analyse mit ihrer Quelle. Die Quellen
liegen im privaten Handover-Repo (`Ady`-Klon, nur Studium).

### 1.1 Struktur und Binärdateien

| Fakt | Quelle |
|---|---|
| ELF64, AArch64, DYN, 27 Sektionen | `native/elf-headers.txt` |
| `.text` 2.292.076 B, `.bss` 5.693.360 B | `native/elf-headers.txt` |
| 16 Exporte | `native/exports-defined.txt` |
| 524 dynamische Symbole | `native/exports-all.txt` |
| Datei ca. 3,59 MB | `native/elf-headers.txt` (Sektionsköpfe bei 3588784) |

### 1.2 Engines

| Fakt | Quelle |
|---|---|
| Zwei Threads („Poweramp Decoder Thread", „Poweramp DSP Thread") | `native/strings.txt` |
| 189 verankerte Funktionen | `native/ghidra/key-functions.c` (Zählung) |
| 17.122 Funktionen gesamt | `README.md` des Handovers |
| Puffergrenzen (1 bis 10 Blöcke usw.) | `key-functions.c`, `create_output_and_buffers` |
| `MIN_BUF_FRAMES_SAFE = 1024` | `key-functions.c`, Zeile 13628 |
| `MAX_TIME_TO_SCAN_NS = 2 s` | `key-functions.c`, `scan_with_decoder` |
| `MAX_SUBSYSTEM_CONTEXTS = 8` | `key-functions.c`, `msg_router.c` |
| nice -8 und -14 | `all-functions.c`, `setpriority`-Aufrufe |
| AudioTrack-ABI-Varianten über `dlsym` | `key-functions.c`, Zeilen 351–409 |
| Decoder-Slots `slot_0`/`slot_1` | `native/key-strings.txt` |

### 1.3 Verbindliche Zuordnungsquelle

| Quelle | Was sie liefert |
|---|---|
| `native/ghidra/string-xrefs.tsv` | 335 Strings → referenzierende Funktion. **Beste Einzelquelle.** |
| `native/strings.txt` | 14.814 Strings (Dateinamen, Meldungen) |
| `native/key-strings.txt` | 294 gefilterte Engine-Strings |
| `native/ghidra/all-functions.c` | alle 17.122 Funktionen (Aufrufer-Suche) |
| `native/ghidra/key-functions.c` | 189 Funktionen im Volltext |

### 1.4 Fremdbibliotheken

| Fakt | Quelle |
|---|---|
| FFmpeg-Version `Lavf/58.27.103 Poweramp` | `native/strings.txt`, Zeile 1515 |
| 130 FFmpeg-Exporte | `native/ffmpeg-exports-defined.txt` |
| libopenmpt, TagLib, Milkdrop, LuaJIT, WavPack, Musepack eingebaut | `native/strings.txt` (Dateinamen) |
| Build-Pfad `/Users/maksimpetrov/.../thirdparty/` | `native/strings.txt`, Zeilen 2629/5510 |
| LuaJIT 2.1.0-beta3 | `native/strings.txt`, Zeile 1855 |

---

## 2 · Lizenz-Register

Zwei Teile: **A** die in Poweramp eingebauten Fremdbibliotheken (nur zur
Kenntnis, wir übernehmen keinen Code). **B** die von uns gewählten Bausteine
(das ist der Teil, der für unser Produkt zählt).

### 2.1 Teil A — in Poweramp eingebaut (nur Kenntnis)

| Bibliothek | Lizenz | Pflicht bei eigener Nutzung |
|---|---|---|
| **libopenmpt** | **BSD-3-Clause** | Namensnennung, keine Namenswerbung |
| **WavPack** | **BSD-3-Clause** | Namensnennung |
| **Musepack (libmpcdec)** | **BSD** | Namensnennung |
| **FFmpeg** (`libffmpeg_neon.so`) | **LGPL-2.1+** oder GPL (je Build) | Quelloffenlegung der Bibliothek, dynamisches Linken |
| **mbedTLS** | **Apache-2.0** | Namensnennung, Patentklausel |
| **zlib** | **zlib-Lizenz** | Namensnennung |
| **LuaJIT 2.1.0-beta3** | **MIT** | Namensnennung |
| **TagLib** | **LGPL-2.1 oder MPL-1.1** | bei LGPL: dynamisch linken |
| **libc++ / libcxxabi** | **Apache-2.0 mit LLVM-Ausnahme** | Namensnennung |
| **Milkdrop (Fork „modile")** | **unklar, prüfen** | Fork eines Reverse-Engineering-Projekts |
| **Milkdrop-Presets** | **je Preset unterschiedlich** | viele Community-Lizenzen |

**Wichtig:** Die beiden kritischen Punkte sind **FFmpeg** (LGPL/GPL) und
**Milkdrop** (unklar). Wer FFmpeg mitliefert und nicht dynamisch linkt, muss
seinen eigenen Code offenlegen. Wer Milkdrop-Presets mitliefert, muss die Lizenz
**jedes einzelnen Presets** prüfen.

### 2.2 Teil B — unsere Werkzeugkette

| Baustein | Lizenz | Kommerziell? | Pflicht |
|---|---|---|---|
| **Oboe** (Ausgabe) | Apache-2.0 | ja | Namensnennung |
| **Media3 / ExoPlayer** (normaler Player) | Apache-2.0 | ja | Namensnennung |
| **Signalsmith Stretch** (Time-Stretch) | MIT | ja | Namensnennung |
| **SoundTouch** (Fallback) | LGPL-2.1 | ja | dynamisch linken |
| **Beat This!** (Beats/Downbeats, Code **und** Gewichte) | MIT | ja | Namensnennung |
| **libebur128** (Lautheit LUFS) | MIT | ja | Namensnennung |
| **eigene Implementierung** (Tonart Chroma+Profile, Metriken, Energie) | eigen | ja | — |
| **LiteRT / LiteRT-LM** (Laufzeit, ab v0.18.0 EmbeddingGemma-2-Audio, Kotlin/C++) | Apache-2.0 | ja | Namensnennung |
| ~~**librosa** (Analyse, offline)~~ | ~~ISC~~ | — | **abgelöst durch ADR-012** |
| **sqlite-vec / USearch** (Vektorsuche) | MIT / Apache-2.0 | ja | Namensnennung |
| **EmbeddingGemma 2** (Gewichte) | **Apache-2.0** | ja | Namensnennung; zusätzlich Gemma Prohibited Use Policy |
| **Gemma 4** (Gewichte, optional) | Gemma-Lizenz | ja, mit Auflagen | Nutzungsbedingungen, Weitergabe |
| **Demucs** (Stems, optional) | MIT | ja | Namensnennung |

> **Korrektur 08.10.2026 (ADR-012, ADR-015):** Die Zeilen „librosa" und
> „EmbeddingGemma 2 (Gemma-Terms)" der ersten Fassung sind korrigiert bzw.
> ergänzt. Beat This!, libebur128, LiteRT-LM und die eigenen Implementierungen
> waren noch nicht eingetragen. **Hinweis für Plan B** (falls EmbeddingGemma 2 an
> Musik scheitert): MuQ/MuQ-MuLan (CC-BY-NC 4.0) und OpenL3 (Gewichte nicht
> kommerziell) scheiden aus, musicnn ist unklar, CLAP ist vor Einsatz im
> Original-Repo zu prüfen.

### 2.3 Die drei Lizenzfallen (für uns)

1. **AudioTrack/AAudio:** keine Lizenzfrage, aber ABI-Frage (Abschnitt 6).
2. **FFmpeg:** wenn wir es nutzen, **dynamisch linken** und die LGPL-Bedingungen
   erfüllen, oder bewusst die GPL wählen.
3. **Gemma-Gewichte:** kommerziell erlaubt, aber mit Nutzungsbedingungen und
   Weitergabepflicht. Vor dem Release abgleichen.

---

## 3 · Übernahme-Protokoll

Status je Baustein aus der Poweramp-Analyse. Drei Werte:
**übernehmen** (Idee nachbauen), **nicht übernehmen**, **prüfen**.

| Baustein | Status | Grund |
|---|---|---|
| Zwei Threads (Decoder, DSP) | **übernehmen** | Grundlage, wenig Aufwand |
| Lock-freier SPSC-Ringpuffer | **übernehmen** | verhindert die meisten Fehler |
| Plugin-Muster (`PluginContext`) | **übernehmen**, aber als Tabelle | Reflection zu teuer für uns |
| Nachrichten-Router (8 Kontexte) | **übernehmen** (vereinfacht) | entkoppelt, aber voller Router ist Overkill |
| `mmap`-Ringpuffer | **prüfen** | erst wenn `malloc` messbar stört |
| Decoder-Slots (2) | **prüfen** | nützlich für Auto-DJ (Deck B) |
| ↳ Korrektur 08.10.2026 | **übernehmen** | Doppelnennung; entschieden in ADR-010 (siehe Zeile unten) |
| EQ + Kopfraum + ReplayGain | **übernehmen** | Kern des Klangs |
| Gapless-Buchführung (Delay/Padding) | **übernehmen** | sonst Lücken |
| Postfade-Blöcke | **übernehmen** | Grundlage der Übergänge |
| Wellenform + Ersatzwelle + Crossfade | **übernehmen** | direkt nachbaubar |
| Drei-Scheiben-Bitmap für Balken | **übernehmen** | spart Rechenzeit |
| Bedarfsgesteuerte Animation (Dirty-Flags) | **übernehmen** | Akku |
| nanoTime-Interpolation | **übernehmen** | flüssig ohne Engine-Fragen |
| Bitmap-Cache + zweistufiges Laden | **übernehmen** | Speicher |
| Inkremementeller Scan | **übernehmen** | zweiter Start in Sekunden |
| 1024-Frames-Sicherheitsboden | **übernehmen** | kein Absturz bei Gerätefehlern |
| Skins / Widgetpack | **nicht übernehmen** | nicht unser Produkt |
| Visualizer (Milkdrop, EGL/GL) | **nicht übernehmen** | teuer, kein Kern |
| OpenMPT / WavPack / Musepack | **prüfen** | nur wenn wir Tracker-/Lossless-Formate brauchen |
| mbedTLS / Netzwerk | **nicht übernehmen** | nur falls Sync kommt |
| Decoder-Slots `slot_0`, `slot_1` | **übernehmen** | Basis für Deck A/B |

---

## 4 · Konstantenregister

Alle belegten Zahlen an einer Stelle.

### 4.1 Engine und Puffer

| Konstante | Wert | Bedeutung |
|---|---|---|
| `MIN_BUF_FRAMES_SAFE` | **1024 Frames** | Ersatz-Puffergröße bei Gerätefehler |
| `request_dsp_blocks` | **1 bis 10** | Blöcke in der DSP-Kette |
| `request_dsp_prefetch_blocks` | **1 bis 10** | Vorlauf-Puffer |
| `request_dsp_postfade_blocks` | **0 bis 10** | Zusatzblöcke fürs Ausklingen |
| `features.latency_ms` | **1,0 bis 10000,0** | Ausgabe-Latenz |
| `features.presentation_latency_ms` | **0,0 bis 10000,0** | Latenz bis hörbar |
| `num_blocks` | **> 0** | Pflicht |
| `frames_per_block` | **>= 1** | Pflicht |
| `MAX_SUBSYSTEM_CONTEXTS` | **8** | Nachrichten-Router |
| `MAX_TIME_TO_SCAN_NS` | **1.999.999.999 ns** | Wellenform-Scan-Grenze |
| Decoder-Slots | **2** | `slot_0`, `slot_1` |
| Thread-Priorität Audio | nice **-8** | `setpriority` |
| Thread-Priorität DSP | nice **-14** | `setpriority` |

### 4.2 Formeln

```
 block_ms   = num_blocks * 1000 / sample_rate
 sr_mult    = max(1, sample_rate / 48000)
 frames	pro Block = sample_rate * block_ms / 1000
```

### 4.3 Binärdateien

| Wert | Betrag |
|---|---|
| `.text` | 2.292.076 B (2,19 MiB) |
| `.rodata` | 371.610 B |
| `.eh_frame` | 453.068 B |
| `.gcc_except_table` | 99.320 B |
| `.bss` | 5.693.360 B (5,43 MiB) |
| `.rela.plt` | 10.848 B (452 Einträge) |
| Exporte | 16 |
| Dynamische Symbole | 524 |
| Funktionen gesamt | 17.122 |
| Verankerte Funktionen | 189 |

### 4.4 Bitmasken (Ausgabe und Bluetooth)

| Feld | Werte |
|---|---|
| Abtastraten | 1=44100, 2=48000, 4=88200, 8=96000, 16=176400, 32=192000 |
| Bits je Sample | 1=16, 2=24, 4=32 |
| Kanäle | 1=MONO, 2=STEREO |
| Codecs | 0 SBC, 1 AAC, 2 aptX, 3 aptX HD, 4 LDAC, 5/6 SSC/LHDC/HWA, 1000000 LHDC/HWA |

---

## 5 · Nachrichten- und Zustandsregister

### 5.1 Nachrichten (belegt)

| Name | Richtung | Bedeutung |
|---|---|---|
| `MSG_OPEN` / `request_open` | Steuerung → Decoder | Datei öffnen |
| `MSG_SEEK` / `request_seek` | Steuerung → Decoder | Springen (mit Serial) |
| `MSG_FILL` / `decoder_filled` | Decoder → DSP | PCM geliefert |
| `MSG_CLOSE` / `decoder_closed` | Steuerung → Decoder | Schließen |
| `MSG_DECODER_EOF` | Decoder → DSP | Dateiende |
| `PACKET_TYPE_SEEK_RES` | Decoder → DSP | Seek-Ergebnis |
| `PACKET_TYPE_SEEK` | DSP → Decoder | Seek anfordern |
| `MSG_SET_USER_AGENT` | Java → Decoder | Nutzerkennung (Netz) |
| `PA_SIZEOF_PLUGIN_MSG` | Prüfwert | Nachrichtengröße |
| `MSG_DSP_*` / `MILK_DSP_MSG_AUDIO_SOURCE_FD` | DSP → Plugin | Audio an Visualizer |

### 5.2 Ausführungs-Handler (`exec_*`)

| Handler | Seite | Bedeutung |
|---|---|---|
| `exec_decoder_opened` | DSP | Decoder ist offen |
| `exec_decoder_filled` | DSP | Puffer gefüllt |
| `exec_decoder_seeked` | DSP | Seek ausgeführt |
| `exec_decoder_failed` | DSP | Decoder-Fehler |
| `exec_decoder_closed` | DSP | Decoder geschlossen |
| `exec_seek` | DSP | Seek anstoßen |
| `exec_on_decoder_opened_msg` | Decoder | Meldung erhalten |
| `exec_on_decoder_closed_msg` | Decoder | Meldung erhalten |
| `exec_on_dsp_track_started` | DSP | Track startet |
| `exec_on_dsp_track_ended_or_faded` | DSP | Track endet / klingt aus |
| `exec_on_dsp_seek_done` | DSP | Seek fertig |
| `process_decoder_seeked` | DSP | Seek nachbereiten |
| `process_post_decoder_seeked` | DSP | nach Seek aufräumen |
| `resume_or_pause_after_seek` | DSP | nach Seek weiter oder pausieren |

### 5.3 Zustände

| Zustand | Bedeutung |
|---|---|
| `DSP_STATE_PAUSING` | weich pausieren |
| `DSP_STATE_STOPPING` | stoppen |
| `DSP_STATE_ZEROS_TO_AUTO_STOPPED` | Stille schieben, dann aus |
| `CC_STATE_WAIT_FOR_RESUME` | wartet auf Fortsetzung |
| `CC_FLAG_PENDING_EOF` | Dateiende vorgemerkt |
| `CC_FLAG_FILLED` | Puffer gefüllt |
| `CC_FLAG_FILLED` (Decoder) | bei gefülltem Puffer ignorieren |

### 5.4 Ausgabe-Flags (belegt)

| Flag | Bedeutung |
|---|---|
| `FLAG_NEEDS_DEEP_BUFFER` | Hersteller braucht großen Puffer |
| `FLAG_SUPPORTS_SPEAKER` | Lautsprecher nutzbar |
| `PA_OUTPUT_CAP_SEEK_FAST_VOLUME` | schnelles Lautstärkesetzen |
| `PA_OUTPUT_CAP_NO_EQU` | kein EQ über diesen Weg |
| `FLAG_SUPPORTS_LDAC` | LDAC über `ro.somc.ldac.audio.supported` |

---

## 6 · Gerätematrix (Hersteller-Sonderbehandlung)

Belegt aus `audio_platform.c`, `PaBluetoothCodecConfig`, `vendor`-Strings.

| Hersteller | Erkennung | Sonderbehandlung |
|---|---|---|
| **Xiaomi / MIUI** | `ro.miui.ui.version.code` | `FLAG_NEEDS_DEEP_BUFFER` (großer Puffer) |
| **OnePlus / Oppo** | `isOnePlusOrOppo`-Prüfung | `FLAG_NEEDS_DEEP_BUFFER` |
| **Motorola** | Geräteprüfung | `!FLAG_SUPPORTS_SPEAKER` |
| **Samsung** | Hersteller-Flag | Codec **SSC** |
| **Sony** | `ro.somc.ldac.audio.supported` | **LDAC** freigeschaltet |
| **HTC** | `ro.build.sense.version` | Erkennung (Sense) |
| **Qualcomm** | `libbluetooth_qti.so` | Bluetooth-Codec-Abfrage |
| **allgemein** | `ro.build.version.sdk`, `ro.build.version.preview_sdk` | ABI-/API-Weiche |

**Unsere Konsequenz:** Die Puffergröße muss **pro Gerät** gewählt werden. Ein
fester Wert ist entweder zu klein (Knacken) oder zu groß (Latenz).

---

## 7 · Funktionsregister (`FUN_` → Bedeutung)

Alle Funktionen, deren **echter Name** aus den Strings bekannt ist. Die übrigen
der 189 sind nur über Adresse und Klasse bekannt (siehe
`WISSEN-POWERAMP-ARCHITEKTUR.md`, Abschnitt 30).

### 7.1 Öffentliche Exporte

| Name | Adresse |
|---|---|
| `JNI_OnLoad` / `JNI_OnUnload` | 00205598 / 00205974 |
| `internal_plugininterface_set_package` | 0026e958 |
| `internal_register_decoder` | 0036ee00 |
| `internal_register_dsp` | 0036eed8 |
| `internal_set_dspi` | 00271394 |
| `internal_set_resampler` | 00377870 |
| `pa_alloc_plugin_context` | 0026f398 |
| `pa_format_infos_same` | 0026f448 |
| `pa_get_plugin` / `pa_get_plugin_by_uniq_name` | 0026f13c / 0026f198 |
| `pa_log_format_info` | 0026f4bc |
| `pa_register_decoder` / `pa_register_dsp` / `pa_register_output` | 0026eed0 / 0026efa8 / 0026f134 |
| `pa_send_msg` | 0036f4dc |

### 7.2 Decoder

| Name | Adresse |
|---|---|
| `decoder_thread_start` | 003788d4 |
| `decoder_thread_run` | 003789ac |
| `decoder_thread_request_seek` | 00377c20 |
| `open_decoder_or_release` | 00377e5c |
| `decoder_open` | 0038ba54 u. a. |
| `decoder_decode` | 00385590 |
| `decoder_seek` | 0038a7a4 u. a. |
| `decoder_pause_hint` / `decoder_resume_hint` | 00385cfc / 00385cc0 |
| `decoder_handle_msg` / `decoder_handle_mgs` | 00389820 / 0038a018 |
| `callbackOnDecoderOpened/OpenFailed/Closed/Seeked` | 00372e74 |
| `scan_decode_init` | 00260ba4 |
| `scan_with_decoder` | 00260d1c |
| `resampleAndScaleAsNeeded` | 00260d1c |
| `ffmpegdecoder_get_tag` | 00387608 / 0038c724 |
| `ffmpegdecoder_get_file_type` | 00387d74 |
| `ffmpegdecoder_context not initialized` | 00385590 |
| `pamp_proto_seek` | 00386adc |
| `dropStoredBuffer` | 0038c9e0 |
| `amediadecoder_init` | 0038b918 |
| `moddecoder_init` / `mpcdecoder_init` / `wvdecoder_init` | 00389fc8 / 003897d0 / 003886d0 |
| `poweramp_register_decoder` | 0038b918 u. a. |

### 7.3 DSP

| Name | Adresse |
|---|---|
| `dsp_thread_create` | 003958e0 |
| `dsp_thread_run` / `_dsp_thread_build` | 00396720 |
| `dsp_thread_start` | 003965dc |
| `dsp_thread_release_impl` | 0039928c |
| `dsp_thread_request_open` | 00395070 |
| `dsp_thread_get_int_param` | 00396f54 |
| `dsp_thread_init_plugins` | 00396720 |
| `dsp_block` / `dsp_do_dsp_block` | 00397704 / 00397358 |
| `create_output_and_buffers` | 003958e0 |
| `open_output_and_init_buffers` | 00396720 |
| `process_decoder_seeked` | 003989bc |
| `process_post_decoder_seeked` | 00398ac8 |
| `resume_or_pause_after_seek` | 00398b50 |
| `exec_seek` | 00398d28 |
| `exec_decoder_opened/filled/seeked/failed/closed` | 0039a294 / 0039a6cc / 0039a588 / 0039a4d0 / 0039a470 |
| `resampler3_handle_msg` | 0039b214 |
| `flush_resampler_last_frames` | 00378bcc |
| `handle_dsp_band_coefs` | 00308200 |
| `handle_dsp_equ_rebuild` | 00307d74 |
| `replaygain_track_gain` / `_album_gain` / `_track_peak` / `_album_peak` | 003893d8 / 0038960c |
| `mmapped_mapping_init` / `mmaped_circular_buffer` | 003774f4 |
| `SetLength` (Reverb) | 0025e954 u. a. |
| `plugin.tempo` (TempoPluginService) | 0039c210 |

### 7.4 Ausgabe

| Name | Adresse |
|---|---|
| `output_create` (alle Wege) | 0037ddd0, 00390dc8, 0037c080, 00393af0 |
| `getMinBufferSize` | 0036d678 |
| `at_getMinBufferSize48` | 0036e328 |
| `getNativeOutputSampleRate` | 0036d678 u. a. |
| `get_params_via_audiotrack_proxy` | 0037cb68 |
| `flush_buffers` / `flush_buffers_locked` | 0037d8b8 / 0039279c |
| `AudioSystem::getLatency` | 00315008 |
| `AAudioStream_*` | 003928a4 |
| `extract_latency` | — |
| (`output_config.c`) `get_options/get_sample_rates/get_sample_formats/get_supported_devices` | 0037171c / 003718dc / 0037195c / 00371694 |
| `audioplatform_detect` | 00379308 |
| CcPluginService | 0039369c |

### 7.5 Querschnitt und Fremd

| Name | Adresse |
|---|---|
| `pipeline_init` / `native_build` / `native_request_open` / `native_seek` / `native_route_msg` | 003734e0 / 00373a70 / 00260ba4 / 00373f3c / 00374344 |
| `msg_router_route_msg` | 00376850 |
| `msg_router_register_subsystem_no_sync` | 00376658 |
| `register_subsystem_for_plugin_type` | 00376658 |
| `msg_handler_exec_handle_msgs` | 00376da8 |
| `native_plugin_manager_init` / `native_get_plugins` | 0036f660 / 0036f7d8 |
| `register_plugin_internal` / `plugininterface_init` | 0036ea54 / 0036f3f0 |
| `plugin_handle_msg` | 0039ad30, 0037ff6c, 0037dc8c, 003755e4 |
| `set_thread_priority` (`priority.c`) | 0039b214 (Umfeld) |
| Flex-Lexer (`yy_scan_buffer`, `yy_create_buffer`, `REJECT`) | 00233828, 0023528c, 002804d4, 002800cc |
| `glDiscardFramebufferEXT`, `eglSwapBuffers`, `eglCreatePbufferSurface` | 00257b54, 0023b5cc, 0022c828 |

### 7.6 Vollständige Liste aller 189 verankerten Funktionen

Aufsteigend nach Klasse, dann nach Adresse. „Name" nur, wo der echte Name aus
den Strings bekannt ist, sonst „—". Klasse nach Abschnitt 30.10 des
Architektur-Dokuments (über Beweis-String oder Aufrufer).

**Decoder (Decoder-Thread, Decoder-Plugins, Tag, Scan) — 67**

| Adresse | Name / Rolle |
|---|---|
| 00260ba4 | `scan_decode_init` (ScanDecode) |
| 00260d1c | `scan_with_decoder`, `resampleAndScaleAsNeeded` |
| 00261fec | `!temp byte buffer size` |
| 0036ee00 | `internal_register_decoder` |
| 0036fedc | `nativeutils.c` |
| 00371e70 | `dirscanner.c` |
| 00372e74 | `callbackOnDecoderOpened/OpenFailed/Closed/Seeked` |
| 00374df4 | `exec_on_decoder_opened_msg` |
| 00377c20 | `decoder_thread_request_seek` |
| 00377e5c | `open_decoder_or_release` |
| 00378788 | `decoder thread` |
| 003788d4 | `decoder_thread_start` |
| 003789ac | `decoder_thread_run` |
| 00378bcc | `flush_resampler_last_frames` |
| 0037903c | `plugin_handle_msg` (decoder_thread) |
| 003791b4 | `decoder_thread.c` |
| 003841fc | `Failed to register poweramp_ffmpegdecoder` |
| 003842c4 | `decoder_handle_mgs` |
| 0038455c | `ffmpegdecoder2.c` |
| 00384594 | `!avio_ctx_buffer`, `seekable` |
| 00385590 | `decoder_decode` |
| 003859b8 | `decoder_seek()` |
| 00385cc0 | `decoder_resume_hint` |
| 00385cfc | `decoder_pause_hint` |
| 00385d38 | `ffmpegdecoder2.c` |
| 00385f30 | `ffmpegdecoder2.c` |
| 0038651c | `ffmpegdecoder2.c` |
| 003869a0 | `ffmpegdecoder2.c` |
| 00386adc | `pamp_proto_seek`, `PACKET_TYPE_SEEK_RES` |
| 00386dd8 | `ffmpegdecoder2.c` |
| 00386eb8 | `ffmpegdecoder2.c` |
| 00386f80 | `ffmpegdecoder2.c` |
| 00387028 | `ffmpegdecoder2.c` |
| 003871f4 | `ffmpegdecoder2.c` |
| 00387318 | `ffmpegdecoder2.c` |
| 00387608 | `ffmpegdecoder_get_tag` |
| 00387d74 | `ffmpegdecoder_get_file_type` |
| 003886d0 | `wvdecoder_init` |
| 00388720 | `decoder_handle_msg` (wv) |
| 0038874c | `wvdecoder.c` |
| 00388808 | `wvdecoder.c` / ReplayGain-Nennung |
| 00388ef8 | `decoder_seek` (wv) |
| 0038960c | `replaygain_` |
| 003897d0 | `mpcdecoder_init` |
| 00389820 | `decoder_handle_msg` (mpc) |
| 0038984c | `mpcdecoder.c` |
| 00389900 | `decoder_open` (mpc) |
| 00389cf4 | `mpcdecoder.c` |
| 00389e70 | `decoder_seek` (mpc) |
| 00389fc8 | `moddecoder_init` |
| 0038a018 | `decoder_handle_mgs` (mod) |
| 0038a100 | `moddecoder.c` |
| 0038a21c | `decoder_open` (mod) |
| 0038a688 | `moddecoder.c` |
| 0038a7a4 | `decoder_seek` (mod) |
| 0038a930 | `moddecoder.c` |
| 0038a95c | `moddecoder.c` |
| 0038b918 | `amediadecoder_init` |
| 0038b970 | `amediadecoder.c` |
| 0038ba54 | `decoder_open` (amedia) |
| 0038c080 | `decoder_decode` (amedia) |
| 0038c354 | `decoder_seek` (amedia) |
| 0038c4bc | `amediadecoder.c` |
| 0038c724 | `ffmpegdecoder_get_tag` (amedia) |
| 0038c9e0 | `dropStoredBuffer` |
| 003a17ec | `seek.sync_samples` (OpenMPT) |
| 003a2194 | `render.resampler.emulate_amiga_type` (OpenMPT) |
| 003c0f60 | `Truncated bit buffer` |

**DSP (dsp_thread, EQ, ReplayGain, Resampler, Reverb, Milk-DSP, Tempo) — 56**

| Adresse | Name / Rolle |
|---|---|
| 0025c8b8 | Reverb (`SetLength`) |
| 0025c9ec | Reverb |
| 0025cb7c | Reverb |
| 0025e1b4 | Reverb |
| 0025e860 | Reverb |
| 0025e8d8 | Reverb |
| 0025e954 | Reverb (`SetLength`) |
| 0025e9d0 | Reverb |
| 0025ea4c | Reverb |
| 0025eb4c | MilkDSPPlugin |
| 0025ed4c | MilkDSPPlugin |
| 0025f424 | MilkDSPPlugin |
| 0025f50c | MilkDSPPlugin |
| 00307d74 | `handle_dsp_equ_rebuild` |
| 00308200 | `handle_dsp_band_coefs` |
| 0037555c | `exec_on_dsp_seek_done` |
| 003774f4 | `mmaped_circular_buffer` |
| 00377870 | `internal_set_resampler` |
| 003893d8 | `replaygain_*` |
| 003958e0 | `create_output_and_buffers`, `dsp_thread_create` |
| 00394e6c | `dsp_thread.c` |
| 00394f44 | `dsp_thread.c` |
| 00395070 | `dsp_thread_request_open` |
| 00395238 | `dsp_thread.c` |
| 003965dc | `dsp_thread_start` |
| 00396720 | `_dsp_thread_build`, `dsp_thread_run` |
| 00396e54 | `dsp_thread.c` |
| 00396eac | `dsp_thread.c` |
| 00396f00 | `dsp_thread.c` |
| 00396f54 | `dsp_thread_get_int_param` |
| 0039704c | `dsp_thread.c` |
| 00397260 | `dsp_thread.c` |
| 00397358 | `dsp_do_dsp_block` |
| 00397704 | `dsp_block` |
| 0039824c | `dsp_thread.c` |
| 003985f4 | `dsp_thread.c` |
| 003989bc | `process_decoder_seeked` |
| 00398ac8 | `process_post_decoder_seeked` |
| 00398b50 | `resume_or_pause_after_seek` |
| 00398d28 | `exec_seek` |
| 003991f4 | `dsp_thread.c` |
| 0039928c | `dsp_thread_release_impl` |
| 00399420 | `dsp_thread.c` |
| 00399fe0 | `dsp_thread.c` |
| 0039a294 | `exec_decoder_opened` |
| 0039a470 | `exec_decoder_closed` |
| 0039a4d0 | `exec_decoder_failed` |
| 0039a588 | `exec_decoder_seeked` |
| 0039a6cc | `exec_decoder_filled` |
| 0039aba0 | `dsp_thread.c` |
| 0039ad30 | `plugin_handle_msg` (dsp) |
| 0039b214 | `resampler3_handle_msg` |
| 0039b3c0 | `resampler3.c` / plugininterface |
| 0039b458 | `Failed to init resampler` |
| 0039b6bc | `resampler3.c` |
| 0039c210 | `tempo.c` (TempoPluginService) |

**Ausgabe (AAudio, OpenSL ES, AudioTrack, Cast, Lader, Plattform) — 23**

| Adresse | Name / Rolle |
|---|---|
| 00315008 | `AudioSystem::getLatency` (audiotrack_direct) |
| 0036d1f4 | Bibliothekslader (`dlopen`, `lseek`) |
| 0036d678 | `getMinBufferSize` |
| 0036e328 | `at_getMinBufferSize48` |
| 003714b0 | `bad config_blob_msg ... safe output config` |
| 00371568 | `output_buf_ms=...` |
| 003715b8 | `OutputInternalHelper` |
| 00371694 | `!get_supported_devices` |
| 0037171c | `!get_options` |
| 003718dc | `!get_sample_rates` |
| 0037195c | `!get_sample_formats` |
| 00379308 | `FLAG_NEEDS_DEEP_BUFFER`, MIUI/Oppo/moto |
| 0037b00c | `FLAG_SUPPORTS_SPEAKER`, `SEEK_FAST_VOLUME` |
| 0037c080 | `getProperty(OUTPUT_FRAMES_PER_BUFFER)` (osl) |
| 0037cb68 | `get_params_via_audiotrack_proxy` |
| 0037d8b8 | `flush_buffers` (osl) |
| 0037ddd0 | `output_create` (at) |
| 00380034 | `output_create` (`using_callback`) |
| 00390dc8 | `output_create` (aa) |
| 0039279c | `flush_buffers_locked` |
| 003928a4 | `AAudioStream_*` |
| 0039369c | `CcPluginService` |
| 00393af0 | `output_create` (cc) |

**Querschnitt (Pipeline, Router, Plugin-API, JNI) — 20**

| Adresse | Name / Rolle |
|---|---|
| 002621f0 | JNI `(Ljava/nio/ByteBuffer;I)[C` |
| 0036d678 | s. Ausgabe (Doppelnennung vermeiden) |
| 0036ea54 | `register_plugin_internal` |
| 0036efb0 | `plugininterface-internal.c` |
| 0036f3f0 | `plugininterface_init` |
| 0036f4dc | `pa_send_msg` |
| 0036f660 | `native_plugin_manager_init` |
| 0036f7d8 | `native_get_plugins` |
| 003708cc | `native_fd_lseek` |
| 003734e0 | `pipeline.c`, `dsp_thread`, `not an output plugin` |
| 00373a70 | `native_build` |
| 00373f3c | `native_seek` |
| 00374344 | `native_route_msg` |
| 003755e4 | `plugin_handle_msg`, JNI critical |
| 00376658 | `register_subsystem_for_plugin_type` |
| 00376850 | `msg_router_route_msg` |
| 00376da8 | `msg_handler_exec_handle_msgs` |
| 0037dc8c | `plugin_handle_msg` |
| 0037ff6c | `plugin_handle_msg` |
| 0045a988 | JNI `([B)Ljava/nio/ByteBuffer;` |
| 0036eed8 | `internal_register_dsp` |

**Visualizer (Milk-Renderer, GL/EGL, Lua, Bild) — 9**

| Adresse | Name / Rolle |
|---|---|
| 0022c828 | `failed eglCreatePbufferSurface` |
| 0022e6f8 | lädt `milk/lua/milk_main.lua` |
| 0022f3d0 | `loadLBuffer` (Lua) |
| 00233594 | `image buffer for '%s' invalid size` |
| 0023afe0 | `failed eglSwapBuffers` |
| 0023b5cc | `failed eglSwapBuffers` |
| 0023bb84 | `failed eglSwapBuffers` |
| 00257b54 | `glDiscardFramebufferEXT` |
| 0026e944 | `GL_EXT_draw_buffers`, `GL_EXT_shader_framebuffer_fetch` |

**Fremdbibliothek (Flex-Lexer/Parser für Lua/EEL; Codec-Bild) — 13**

| Adresse | Name / Rolle |
|---|---|
| 00233828 | Flex-Lexer (`yy_scan_buffer`) |
| 00234ae0 | `yyensure_buffer_stack` |
| 00234b80 | `yy_create_buffer` |
| 00234f68 | `yy_scan_buffer` |
| 0023528c | Flex-Lexer |
| 002364c4 | `yyensure_buffer_stack` |
| 00236564 | `yy_create_buffer` |
| 00236a0c | `yy_scan_buffer` |
| 00280020 | `yyensure_buffer_stack` |
| 002800cc | `yy_create_buffer` |
| 002804d4 | Flex-Parser |
| 00280854 | `scanner uses REJECT` |
| 0043c048 | `NULL row buffer` (Bild/Codec) |

**Summe: 189** (67 Decoder, 56 DSP, 23 Ausgabe, 20 Querschnitt, 9 Visualizer,
13 Fremd; `FUN_0036d678` ist in der Querschnitt-Liste ausgelassen, weil es bei
der Ausgabe steht).

---

## 8 · Entscheidungsprotokoll (ADR)

> **Ergänzung 08.10.2026:** Maßgeblich ist `adr/README.md`. Dort stehen ADR-011 bis ADR-017;
> ADR-005 ist durch ADR-012 abgelöst, ADR-008 ist zum Produkt Belegkasten ausgelagert.

Jede Entscheidung: Frage, Alternativen, Wahl, Grund, Datum.

**ADR-001 · Eigene native Engine statt Media3 für den Mixer** *(06.10.2026)*
- Frage: Womit mischen wir zwei Decks?
- Alternativen: Media3/ExoPlayer, eigene Engine auf Oboe.
- Wahl: eigene Engine auf Oboe.
- Grund: Media3 hat über 250 ms Sink-Latenz und keine Zwei-Deck-API. Für
  beatgenaue Übergänge ungeeignet.

**ADR-002 · Media3 für den normalen Player** *(06.10.2026)*
- Wahl: Media3/ExoPlayer 1.11.x für Bibliothek, Wiedergabe, Android Auto.
- Grund: ausgereift, Apache-2.0, Gapless. Kein Grund, das nachzubauen.

**ADR-003 · Signalsmith Stretch statt Rubber Band** *(06.10.2026)*
- Alternativen: Rubber Band (GPL oder Kauf), SoundTouch (LGPL), Signalsmith (MIT).
- Wahl: Signalsmith als Standard, SoundTouch als Rückfall.
- Grund: MIT (kein Kauf, keine Offenlegung), aktiv gepflegt, gut bei 0,75 bis 1,5 fach.

**ADR-004 · Feste Tabelle statt Reflection für Plugins** *(06.10.2026)*
- Wahl: Name → Factory in einer Tabelle.
- Grund: Poweramps Reflection-Weg ist elegant, aber teuer und fehleranfällig.
  Für ein kleines Team ist eine Tabelle klarer und sicherer.

**ADR-005 · Analyse offline per librosa statt on-device** *(06.10.2026)*
- Wahl: BPM/Key/Beat offline (ISC), nur Einbetten on-device.
- Grund: Essentia (AGPL), aubio/libKeyFinder (GPL) sind für uns nicht nutzbar.

**ADR-006 · LiteRT/MediaPipe statt MediaPipe LLM Inference** *(06.10.2026)*
- Wahl: MediaPipe Universal Embedder + LiteRT-LM.
- Grund: Die LLM-Inference-API ist eingestellt; LiteRT-LM ist der Weg 2026.

**ADR-007 · Vektoren an den Datei-Hash gebunden** *(06.10.2026)*
- Wahl: Analyse und Einbettung hängen an einem Inhalts-Hash.
- Grund: Bibliothek wird genau einmal gerechnet; Änderungen lösen gezielt neu aus.

**ADR-008 · Archiv bleibt ohne Zahlung lesbar** *(06.10.2026)*
- Wahl: Belegkasten-Archiv bleibt frei zugänglich.
- Grund: Projektbefund, dass Abo-Fallen der häufigste Defekt sind; Vertrauen ist
  der Unterschied.

**ADR-009 · Kein Visualizer (EGL/GL)** *(06.10.2026)*
- Wahl: kein Milkdrop-ähnlicher Visualizer.
- Grund: teuer, kein Kernnutzen, kein Unterschied zu Poweramp.

**ADR-010 · Zwei Decoder-Slots** *(06.10.2026)*
- Wahl: Deck A und Deck B als getrennte Slots mit eigener Seek-Nummer.
- Grund: Poweramp-Muster; Voraussetzung für nahtlose Übergänge.

**ADR-011 · PC-Prototyp zuerst, Android später** *(08.10.2026)*
- Wahl: Python-Prototyp, der analysiert, auswählt, Übergänge prüft und einen Mix
  **rendert**. Android erst nach bestandenen Toren.
- Grund: Die Kernwette (Vektoren für Musik, Analysegenauigkeit, Klang der
  Übergänge) ist ohne Android prüfbar; der gerenderte Mix ist Test und Hörprobe
  zugleich. Code in `prototyp/`.

**ADR-012 · Analyse mit permissiven Modellen statt librosa** *(08.10.2026, löst ADR-005 ab)*
- Wahl: Beat This! (MIT, Code und Gewichte) für Beats/Downbeats, eigene
  Tonart-Schätzung (Chroma + Key-Profile), libebur128 (MIT) für LUFS.
- Grund: librosa ist Python, hat kein Key und keine Downbeats; Essentia/aubio/
  libKeyFinder/QM-DSP sind AGPL/GPL, madmom-Modelle CC-BY-NC-SA.
- **Konsequenz 08.10.2026:** Plan B (falls EmbeddingGemma an Musik scheitert) hat
  selbst ein Lizenzproblem – MuQ/OpenL3 nicht-kommerziell, musicnn unklar,
  CLAP prüfen. Daher zusätzlich **Plan C**: eigene Merkmale ohne Textsuche.

**ADR-013 · Hash nur über die Audiodaten** *(08.10.2026, ergänzt ADR-007)*
- Wahl: Stichprobe über den Audio-Bereich (Länge plus feste Blöcke an Anfang,
  Mitte, Ende), nicht über Tag-Blöcke. Retagging behält die Analyse.

**ADR-014 · Tempoangleich per Resampling in Version 1** *(08.10.2026)*
- Wahl: Song B per Resampling auf das Tempo von A (±3 %), Tonhöhe ändert sich
  mit; Keylock erst in Phase 5.

**ADR-015 · Stimmung per Zero-Shot, Gemma 4 optional** *(08.10.2026)*
- Wahl: Stimmungswörter als Text einbetten, nächstgelegener Audio-Vektor gewinnt.
  Kein Sprachmodell für den Kern. **Beleg:** EmbeddingGemma 2 ist Apache 2.0.

**ADR-016 · Oboe im geteilten Stromsparmodus** *(08.10.2026)*
- Wahl: `PowerSaving`/`Shared` statt `LowLatency`/`Exclusive`. Gemessen werden
  Aussetzer pro Stunde und Positionsgenauigkeit, nicht Gesamtlatenz.

**ADR-017 · Eigene Engine als Media3-Player** *(08.10.2026)*
- Wahl: Engine hinter `SimpleBasePlayer`, **eine** MediaSession.

---

## 9 · Versionierung des Dokuments

| Datum | Änderung | Von |
|---|---|---|
| 06.10.2026 | Erstanlage `WISSEN-POWERAMP-ARCHITEKTUR.md` | Analyse |
| 06.10.2026 | Abschnitte 1 bis 14 ergänzt (Kette, Plugins, Threads, Performance) | Analyse |
| 06.10.2026 | Abschnitte 15 bis 19 (Übergänge, Gemma, Wellenform, UI, Animation) | Analyse |
| 06.10.2026 | Abschnitte 20 bis 23 (Routing, Scanner, Plugins/Skins, UI-Folgen) | Analyse |
| 06.10.2026 | Abschnitte 24 bis 27 (Tiefenanalysen, Performance) | Analyse |
| 06.10.2026 | Abschnitt 28 (Binärdatei), 29 (jede Binärdatei) | Analyse |
| 06.10.2026 | Abschnitt 30 (189 Funktionen) und 30.10/30.11 (**Korrekturen**) | Analyse |
| 06.10.2026 | `PROTOKOLLE.md` (dieses Dokument) | Analyse |
| 08.10.2026 | ADR-011 bis ADR-017, `ROADMAP-KLANGBILD.md`; Korrekturzeilen in §3, §8, §12, §14 | Review |
| 08.10.2026 | Ergänzung: Lizenz-Tabelle §2.2 (Beat This!, libebur128, Apache 2.0), ADR-Liste §8 (011–017), Messplan §12 (PC-Prototyp), offene Punkte §14 | Review |

**Regel:** Wenn eine frühere Zahl geändert wird, bleibt die alte Zeile stehen und
bekommt eine Korrekturzeile. Nichts wird still überschrieben.

---

## 10 · Sicherheitsgrad je Aussage

Drei Stufen. Jede wichtige Aussage gehört in eine.

| Stufe | Bedeutung | Beispiel |
|---|---|---|
| **belegt** | eigener Beweis-String, Dateiname oder Adresse | `MIN_BUF_FRAMES_SAFE = 1024` |
| **geschlossen** | eindeutiger Aufrufer, keine eigene Quelle | `FUN_00377c20 = decoder_thread_request_seek` |
| **vermutet** | nur Adressnähe | (nach 30.10 keine mehr) |

**Stand:** Nach der String-Querverweistabelle (Abschnitt 30.10) ist **keine**
Aussage mehr auf Stufe `vermutet`. Alles ist `belegt` oder `geschlossen`.

---

## 11 · Glossar

| Begriff | Bedeutung |
|---|---|
| **Frame** | Ein Sample über alle Kanäle (Stereo: 2 Werte) |
| **Block** | Feste Anzahl Frames, die zusammen verarbeitet wird |
| **Ringpuffer** | Kreisförmiger Puffer zwischen zwei Threads |
| **SPSC** | Single Producer / Single Consumer (ein Schreiber, ein Leser) |
| **Prefetch** | Vorlauf-Puffer, damit der DSP nie wartet |
| **Postfade** | Zusatzblöcke hinter dem Track fürs Ausklingen |
| **XRun / Underrun** | Aussetzer, weil die Ausgabe keine Daten bekam |
| **Latency** | Puffer-Latenz der Ausgabe |
| **Presentation Latency** | Zeit bis der Ton tatsächlich hörbar ist |
| **DVC** | Direct Volume Control: Lautstärke im DSP statt im Systemmixer |
| **AVRCP / Absolute Volume** | Bluetooth-Lautstärkesteuerung |
| **Gapless** | Nahtlose Wiedergabe ohne Lücke |
| **Encoder-Delay / Padding** | Vor- und Nachlauf, den ein Codec anfügt |
| **PEQ** | Parametrischer Equalizer (Biquad-Bänder) |
| **Headroom** | Absenkung, damit der EQ nicht übersteuert |
| **ReplayGain / LUFS** | Lautheits-Angleich zwischen Titeln |
| **Camelot** | Notation für harmonische Tonarten (z.B. 8A) |
| **MRL** | Matryoshka Representation Learning (Vektor kürzen) |
| **RAG** | Retrieval Augmented Generation (Suchen + Antworten) |
| **Biquad** | Filter zweiter Ordnung (EQ-Grundbaustein) |
| **Dirty Flag** | Merker "muss neu gezeichnet werden" |
| **Layout Inflation** | XML in View-Objekte umwandeln |

---

## 12 · Messplan

> **Korrektur 08.10.2026 (ADR-016):** Die Latenzziele „unter 60/30 ms“ entfallen. Stattdessen:
> Positionsgenauigkeit über `getTimestamp` und Aussetzer pro Stunde.

Was wird wie gemessen, gegen welche Schwelle.

| Messgröße | Werkzeug | Schwelle | Rhythmus |
|---|---|---|---|
| Aussetzer (Underruns) | eigener Zähler in der App | unter 1 pro Stunde | immer |
| ~~Gesamtlatenz Musik~~ | ~~Oboe `calculateLatencyMillis`~~ | ~~unter 60 ms~~ | **entfällt (ADR-016)** |
| ~~Gesamtlatenz Auto-DJ~~ | ~~dito~~ | ~~unter 30 ms~~ | **entfällt (ADR-016)** |
| Positionsgenauigkeit Anzeige | Oboe `getTimestamp` | Abweichung unter 1 Puffer | pro Gerät |
| Allokationen im Audiopfad | `Debug.getNativeHeapAllocatedSize` | 0 im Callback | in Tests |
| Thread-Priorität | `Process.getThreadPriority` | `THREAD_PRIORITY_AUDIO` | beim Start |
| Anzeige-Frame-Callback | Zähler im Stillstand | 0 pro Sekunde | in Tests |
| Gapless-Lücke | Frame-Vergleich | 0 Frames | pro Album |
| EQ-Umschaltknacken | Hörtest | keines | pro Release |
| Wellenform-Erstlauf | Zeitmessung | unter 2 s pro Datei | pro Scan |
| Scan-Dauer (2. Start) | Zeitmessung | unter 3 s für 10.000 Dateien | pro Start |

**Neu: Messplan PC-Prototyp (Phase 0–2, ergänzt 08.10.2026)**

Jede Messung schreibt nach `prototyp/ergebnisse/` (CSV plus Markus-Bericht).

| Messgröße | Werkzeug | Schwelle / Bericht |
|---|---|---|
| Analysezeit je Track | Zeitmessung im Prototyp | Median und 95. Perzentil je Stufe (Dekodieren, Beats, Key, LUFS, Embedding) |
| Speicher und Modellgröße | `psutil` / Prozessangaben | 570-M-Konfiguration, 256 Dimensionen |
| Vektorqualität | eigene Auswertung | 768 gegen 256 Dimensionen auf denselben Nachbarn |
| LUFS-Genauigkeit | eigener BS.1770 gegen pyebur128 | maximale Abweichung unter 0,1 LU |
| Nachbarn und Textsuche | Blindbewertung (Prototyp-UI) | Tore aus `ROADMAP-KLANGBILD.md` Phase 0.1, mit Wilson-Intervall |
| BPM / Downbeat / Tonart | eigene Metriken | Tore aus Phase 0.2, mit Wilson-Intervall |
| Mix-Ausgabe | Lautheitsmessung | −14 LUFS integriert, True Peak ≤ −1 dBTP |
| Hörtest | Bewertungsbogen | je Person, blind und randomisiert |

**Verfahren:** Jede Messung braucht einen **Ort** (im Code) und eine
**Aufzeichnung** (Log oder Zähler). Ohne beides ist es keine Messung, sondern
ein Gefühl.

---

## 13 · Bau-Protokoll

### 13.1 Unsere Einstellungen (geplant)

| Einstellung | Wert | Grund |
|---|---|---|
| ABI | arm64-v8a (später armeabi-v7a) | Abdeckung |
| NDK | aktuelles LTS | Stabilität |
| `-fvisibility=hidden` | an | nur gewollte Exporte sichtbar |
| `-ffile-prefix-map=<pfad>=.` | an | keine Pfad-Spuren im Binary |
| `strip` | an | keine Funktionsnamen |
| Versionsstring | `Klangbild/1.0` + FFmpeg-Version | Fehlersuche |
| Bibliotheks-Aufteilung | 2 (Kern + groß) | wenig Dateien, klar trennbar |

### 13.2 Was Poweramp macht (zum Vergleich)

| Einstellung | Bei Poweramp |
|---|---|
| ABI | arm64-v8a |
| Exporte | 16 (klein gehalten) |
| Symbole | gestrippt (17.122 `FUN_`) |
| Bibliotheken | 2 (`libpowerampcore.so`, `libffmpeg_neon.so`) |
| Pfad-Spuren | **vorhanden** (`/Users/maksimpetrov/...`) → nicht nachmachen |
| Versionsstring | `Lavf/58.27.103 Poweramp` |

---

## 14 · Offene-Punkte-Register

| # | Offener Punkt | Was ihn schließt |
|---|---|---|
| 1 | Rechenlast auf schwachen Geräten | Test auf einem 200-Euro-Handy |
| 2 | Zahlungsbereitschaft für Auto-DJ extra | Warteliste, bezahlte Beta |
| 3 | Marktgröße lokaler Sammlungen | externe Marktdaten |
| 4 | ~~EmbeddingGemma-2-Lizenz (Apache vs. Gemma)~~ **geschlossen 08.10.2026: Apache 2.0** | Google Developer Guide EmbeddingGemma 2 (ADR-015) |
| 11 | Taugen die EmbeddingGemma-2-Vektoren für **Musik**? (Encoder ist als „speech and sound" beschrieben, Musik in Trainingsdaten und MSEB nicht belegt; MAEB enthält Musik-Tasks) | Phase 0.0 (Belege) und 0.1 (Blindtest mit Baseline) |
| 12 | **Neu 08.10.2026 – Ersatz, wenn das Tor fällt** (MuQ/OpenL3 nicht-kommerziell, musicnn unklar, CLAP prüfen) | Plan B/Plan C, eigenes ADR |
| 13 | **Neu – CC-Musik für die öffentliche Hörprobe** inklusive Lizenz-Tabelle | Phase 2 |
| 5 | Milkdrop-Fork „modile" Lizenz | Repo prüfen (nur Kenntnis) |
| 6 | Bedeutung der drei `native_scan`-Parameter | eigene Definition festlegen |
| 7 | `FUN_00261fec` genaue Rolle | Aufruferkette im Gesamtdump |
| 8 | `FUN_003708cc` genaue Rolle | Aufruferkette im Gesamtdump |
| 9 | Bedienung und Aufwand der Engine für ein kleines Team | Prototyp bauen |
| 10 | Ob Übergänge auf großen Rastern akzeptabel klingen | Hörtest |
| 14 | **Neu – Tor-Schwellen**: vor dem Test festgelegt (60/90/80/70 waren Vorschläge) | `ROADMAP-KLANGBILD.md` Phase 0.1/0.2, Ergänzung 08.10.2026 |

**Regel:** Ein offener Punkt wird nur mit einem **Beleg** geschlossen, nicht mit
einer Meinung. Bis dahin bleibt er offen.

---

## 15 · Quellen

- Privates Handover-Repo (nur Studium): `README.md`,
  `native/elf-headers.txt`, `native/exports-defined.txt`, `native/exports-all.txt`,
  `native/strings.txt`, `native/key-strings.txt`,
  `native/ffmpeg-exports-defined.txt`,
  `native/ghidra/{key-functions.c,all-functions.c,string-xrefs.tsv}`
- Eigene Analysen: `WISSEN-POWERAMP-ARCHITEKTUR.md`, `PRODUKT-KLANGBILD.md`,
  `ARCHITEKTUR-KLANGBILD.md`, `ANDROID-AUTODJ-TOOLCHAIN-2026.md`
- Lizenzprüfung: libopenmpt (BSD-3-Clause), WavPack (BSD-3-Clause), Musepack
  (BSD), mbedTLS (Apache-2.0), TagLib (LGPL/MPL), LuaJIT (MIT)
