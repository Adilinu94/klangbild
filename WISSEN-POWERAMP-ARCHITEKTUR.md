# Poweramp-Architektur: Wissen und Blueprint für eine eigene Engine

**Stand: 06.10.2026 · Grundlage: Reverse-Engineering-Handover Poweramp v1013
(privates Repo `Adilinu94/poweramp-java-handover`)**

---

## 0 · Vorbemerkung und Rechtsstatus (zuerst lesen)

Dieses Dokument ist eine **eigene Beschreibung** der Architektur, abgeleitet aus
dem Studium eines dekompilierten Fremdprodukts. Es enthält **keinen**
abgeschriebenen Fremdcode. Alle Codebeispiele unten sind **eigener, neu
geschriebener Beispielcode** (Clean-Room), der dasselbe Problem löst.

Was aus dem Original stammt, sind **Fakten**: Dateinamen, Export-Namen,
Thread-Namen, Puffervariablen und Zahlen aus dem Binary. Fakten und Ideen sind
nicht urheberrechtlich geschützt, Code ist es. Deshalb:

- **Erlaubt:** Verstehen, dokumentieren, nachbauen mit eigenem Code.
- **Nicht erlaubt:** Dekompilierten Code übernehmen, weitergeben, veröffentlichen.

Das Original ist **Poweramp** (proprietär, Max MP). Wir nutzen es als Landkarte,
nicht als Baumaterial.

### 0.1 Was „Fakt" und was „Ausdruck" ist (die Trennlinie)

Die ganze rechtliche Bewertung hängt an dieser Unterscheidung:

| Art | Beispiel | Geschützt? | Darf benutzt werden |
|---|---|---|---|
| **Fakt** | „Es gibt zwei Threads", „`.text` ist 2,2 MiB" | nein | ja, frei |
| **Idee / Verfahren** | „lock-freier Ringpuffer", „Seek mit Seriennummer" | nein | ja, frei |
| **Ausdruck (Code)** | die konkreten Zeilen des Originals | **ja** | **nein** |
| **Kennzeichen** | Name „Poweramp", Logo | ja | nein |

Deshalb enthält dieses Dokument **Fakten und Ideen** und **eigenen Code**.
Fakten und Verfahren sind nicht geschützt, die konkrete Formulierung schon.

### 0.2 Der Clean-Room-Weg (Vorgehen)

```text
 Leser (analysiert das Original)          Schreiber (baut unsere Engine)
 -------------------------------          ------------------------------
 liest das Dekompilat                     liest NUR dieses Dokument
 schreibt Fakten/Verfahren auf     --->   schreibt eigenen Code
 gibt KEINEN Code weiter                  fragt nur nach der Idee, nicht nach Zeilen
```

Die Regel ist einfach: **Wer den Originalcode gelesen hat, schreibt ihn nicht
nach.** Wer ihn schreibt, liest ihn nicht. In einem kleinen Team kann dieselbe
Person beides tun, aber dann muss sie zuerst die Idee in eigenen Worten
aufschreiben (wie hier) und **danach** den eigenen Code schreiben, ohne
zurückzuschauen.

### 0.3 Herkunft dokumentieren (Nachweis)

Zu jeder Idee gehört ein Nachweis, woher sie stammt. Beispiele aus diesem
Dokument:

| Idee | Quelle (Beleg) |
|---|---|
| Zwei Threads | Thread-Namen im Binary |
| Lock-freier Ringpuffer | Konzept, allgemein bekannt (nicht aus dem Original) |
| `@FastNative` | Annotation im Dekompilat |
| Drei Latenzbegriffe | String-Funde `latency_ms` usw. |

**Analysepunkt:** Ein solches Herkunftsregister schützt nicht nur rechtlich,
sondern auch praktisch: Wer später eine Entscheidung hinterfragt, sieht sofort,
ob sie auf einem Beleg beruht oder auf einer Annahme.

### 0.4 Was ausdrücklich **nicht** übernommen wird

- Kein Code, keine Datei, keine Zeile aus dem Dekompilat.
- Keine Namenszeichen, keine Logos, keine geschützten Bezeichnungen.
- Keine Assets (Icons, Shader, Presets), die urheberrechtlich geschützt sind.
- Keine GPL/AGPL-Bausteine ohne bewusste Lizenzentscheidung (siehe 8 und 11 des
  Produktdokuments).

---

## 1 · Das Gesamtbild in einem Bild

Poweramp trennt die Arbeit in **zwei eigene native Threads** plus die Ausgabe.
Das ist die wichtigste Erkenntnis der ganzen Analyse.

```
 Datei/Stream
   |
   v
[ Decoder-Thread ]   (eigener Thread, hohe Priorität)
   |   entpackt und dekodiert, schreibt PCM in Ringpuffer
   v
[ Ringpuffer A ]      (lock-frei, single producer / single consumer)
   |
   v
[ DSP-Thread ]        (eigener Thread, Echtzeit-Priorität)
   |   EQ, ReplayGain, Preamp, Resampling, Gapless/Crossfade, Volume
   |   schreibt fertiges PCM in Ringpuffer
   v
[ Ringpuffer B ]      (lock-frei)
   |
   v
[ Output-Plugin ]     AAudio / OpenSL ES / AudioTrack  ->  Lautsprecher
```

Belegte Thread-Namen aus dem Binary: **„Poweramp Decoder Thread"** und
**„Poweramp DSP Thread"**. Zu jedem gibt es eine eigene C-Datei
(`decoder_thread.c`, `dsp_thread.c`).

**Warum zwei Threads?** Entpacken (MP3, FLAC, ffmpeg) ist teuer und
unregelmäßig. Die Ausgabe darf aber nie warten. Wenn Entpacken und Ausgeben im
selben Thread stecken, reißt ein langsamer Frame die Tonausgabe ab (Knacken,
Aussetzer). Zwei Threads mit Puffern dazwischen entkoppeln das: Der Decoder darf
schwanken, der Ausgabe-Callback bekommt immer rechtzeitig Daten.

### 1.1 Die vollständige Kette (jede Stufe einzeln)

Das Bild oben ist grob. Vollständig sieht die Verarbeitung so aus, und jede
Stufe ist im Binary belegt:

```
 Datei / Stream
   |
   v
 [1] Demux          ff_*_demuxer, avformat_open_input, av_read_frame
   |                  (Container oeffnen, Pakete lesen)
   v
 [2] Decode         avcodec_decode_audio4 / AMediaCodec_*
   |                  (Paket -> PCM, Format != Ausgabeformat)
   v
 [3] Formatwandlung swr_* (libswresample) oder eigener Konverter
   |                  (Planar -> Interleaved, S16 -> Float, Kanaele)
   v
 [4] Resampling     plugin.resampler3, resampleAndScaleAsNeeded
   |                  (Quellrate -> Geraeterate, z.B. 44,1k -> 48k)
   v
 [5] DSP-Kette      equ5_*, replaygain_*, preamp, headroom, volume
   |                  (EQ, Lautheit, Lautstaerke, Limiter)
   v
 [6] Gapless/Fade   dsp_postfade_blocks, request_fade_impl
   |                  (Ausklingen, nahtloser Trackwechsel)
   v
 [7] Ringpuffer     mmapped_circular_buffer
   |
   v
 [8] Output-Plugin  AAudio / OpenSL ES / AudioTrack
```

**Analysepunkt:** Die Stufen 1 bis 6 laufen **nicht** im Ausgabe-Callback. Der
Callback macht nur Stufe 7 und 8 (aus dem Puffer lesen und schreiben). Deshalb
darf Stufe 1 teuer sein (ffmpeg) und Stufe 3 Speicher anfassen; der Callback
bleibt davon unberührt.

Tabelle nach Kosten und Ort:

| Stufe | Typische Kosten | Ort | Blockierend erlaubt |
|---|---|---|---|
| Demux/Decode | hoch, schwankend | Decoder-Thread | ja |
| Formatwandlung | mittel | Decoder-Thread | ja |
| Resampling | mittel | DSP-Thread | nein (kein malloc) |
| DSP-Kette | niedrig pro Sample | DSP-Thread | nein |
| Gapless/Fade | niedrig | DSP-Thread | nein |
| Puffer lesen | sehr niedrig | Ausgabe-Callback | nein |
| Ausgabe | sehr niedrig | Ausgabe-Callback | nein |

### 1.2 Die drei Uhren (und warum sie streiten)

Es gibt drei Zeitgeber, die auseinanderlaufen:

1. **Sample-Uhr.** Die Ausgabe zählt Samples. Sie ist die Wahrheit für den Ton.
2. **Decoder-Uhr.** Der Decoder zählt, wie viele Frames er erzeugt hat. Er
   schwankt (mal schnell, mal langsam) und driftet gegen die Sample-Uhr.
3. **Anzeige-Uhr.** Die Seekbar läuft im Bildtakt und **interpoliert** selbst
   (Abschnitt 19). Sie darf nie auf die Engine warten.

**Analysepunkt:** Wenn man den Fortschritt direkt aus der Decoder-Uhr nimmt,
ruckelt er. Nimmt man ihn aus der Sample-Uhr, ist er glatt, aber man muss die
Anzeige-Latenz abziehen (`vis_latency_ms`). Deshalb die Trennung.

### 1.3 Das Latenz-Budget

Die Gesamtlatenz ist die Summe aller Puffer:

```
 Gesamt = Ausgabepuffer + DSP-Vorlauf + Decoder-Vorlauf + Geraetepuffer
```

Zwei Rechnungen, die man vor dem Bauen aufstellen muss: eine für **Musik**
(Latenz egal, Stabilität zählt) und eine für **Auto-DJ** (Übergänge müssen
sitzen, also kleinen Puffer). Beispielcode:

```c
/* Eigener Beispielcode: Latenz-Budget rechnen und pruefen. */
typedef struct {
    double output_buf_ms;       /* Ausgabepuffer (Ausgabe-Plugin) */
    double dsp_prefetch_ms;     /* DSP-Vorlauf */
    double decode_prefetch_ms;  /* Decoder-Vorlauf */
    double device_ms;           /* Hardware/Systemlatenz */
} LatencyBudget;

static double total_latency_ms(const LatencyBudget* b) {
    return b->output_buf_ms + b->dsp_prefetch_ms
         + b->decode_prefetch_ms + b->device_ms;
}

/* Reicht das Budget fuer einen beatgenauen Uebergang?
   Ein Beat bei 128 BPM dauert 468,75 ms. Mehr als 30 ms Versatz hoert man. */
static int transition_ok(const LatencyBudget* b) {
    return total_latency_ms(b) <= 30.0;
}
```

Wenn `transition_ok` nein sagt, muss der **Ausgabepuffer kleiner** werden (oder
die Übergänge müssen auf größere Raster gelegt werden). Das ist eine
Produktentscheidung, die aus einer Zahl folgt.

---

## 2 · Der Plugin-Bauplan (die 16 Exporte)

Aus `native/exports-defined.txt` kennen wir die **komplette öffentliche
Schnittstelle** der nativen Kernbibliothek `libpowerampcore.so`. Das sind genau
16 Symbole, und sie verraten das ganze Design:

```
JNI_OnLoad / JNI_OnUnload                 Verbindung zu Java
internal_plugininterface_set_package      Namensraum setzen
internal_register_decoder                 Decoder einhängen
internal_register_dsp                      DSP-Stufe einhängen
internal_set_dspi                          DSP-Schnittstelle setzen
internal_set_resampler                     Resampler setzen
pa_alloc_plugin_context                    Plugin-Kontext anlegen
pa_format_infos_same                       Formate vergleichen
pa_get_plugin                              Plugin per Zeiger holen
pa_get_plugin_by_uniq_name                 Plugin per Name holen
pa_log_format_info                         Format-Log
pa_register_decoder                        Decoder registrieren
pa_register_dsp                            DSP registrieren
pa_register_output                         Ausgabe registrieren
pa_send_msg                                Nachricht in die Engine
```

**Das Muster:** Es gibt drei Familien von Plugins, alle über denselben Baukasten
registriert: **Decoder**, **DSP**, **Output**. Dazu ein Resampler als Sonderfall.

Belegte Plugins aus den Strings:

| Familie | Namen im Binary |
|---|---|
| Decoder | `decoder.amedia` (MediaCodec), `decoder.ffmpeg`, `decoder.flac`, `decoder.mod`, `decoder.mpc`, `decoder.wv` (WavPack) |
| DSP | `Poweramp Internal DSP`, `Poweramp Milk DSP`, `ReverbDSPPlugin`, `MilkDSPPlugin` |
| Resampler | `plugin.resampler3`, `Poweramp Resampler` |
| Output | AAudio, OpenSL ES, AudioTrack (je eigene Unterpakete) |

**Der Trick mit dem Kontext.** Im Binary steht der Fehler:

> `dsp context has no initialized PluginContext as first member`

Das heißt: Jedes Plugin-Objekt **muss** als **erstes Feld** einen `PluginContext`
haben. Damit kann die Engine jeden Plugin-Zeiger auf dieselbe Struktur werfen und
einheitlich ansprechen. Das ist die C-Variante von Vererbung (vtable-Muster).

### Beispielcode: das Plugin-Muster

```c
/* plugin.h  -- eigener Beispielcode, Clean-Room */

#include <stdint.h>
#include <stddef.h>

/* Basis fuer ALLE Plugins. MUSS erstes Feld jeder Plugin-Struktur sein. */
typedef struct PluginContext {
    const char* uniq_name;      /* z.B. "decoder.ffmpeg" */
    int         version;
    int         api;            /* DECODER / DSP / OUTPUT */
    void*       host;           /* Rueckkanal zur Engine */
} PluginContext;

typedef enum { PLUGIN_DECODER = 1, PLUGIN_DSP = 2, PLUGIN_OUTPUT = 3 } PluginApi;

/* Jedes Plugin beginnt mit der Basis. Die Engine castet Zeiger auf PluginContext. */
#define PLUGIN_HEADER PluginContext base;
```

Auf der Engine-Seite registriert man so:

```c
int pa_register_decoder(PluginContext* p);   /* Name liefert p->uniq_name */

const char* engine_resolve_name(const PluginContext* p) {
    return p ? p->uniq_name : NULL;          /* "decoder.ffmpeg" usw. */
}
```

Der Clou: Die Engine kennt nur `PluginContext`. Konkrete Decoder, DSPs und
Ausgaben sind austauschbar, ohne dass die Engine sie kennen muss. Genau deshalb
konnte Poweramp ffmpeg, MediaCodec, WavPack, MOD und MPC nebeneinander anbieten.

### 2.1 Der vollständige Plugin-Kontext (mit Funktionszeigern)

`PluginContext` ist nur der Kopf. Die eigentliche Arbeit steckt in
**Funktionszeigern** (der C-Variante einer vtable). Im Binary sind die
Pflichtfunktionen je Familie belegt, unter anderem:

```
Decoder:  decoder_open, decoder_decode, decoder_seek,
          decoder_pause_hint, decoder_resume_hint, decoder_close
DSP:      dsp_block
Output:   open/close/start/pause/flush/stop (ueber pa_register_output)
```

Die Engine prüft beim Registrieren, ob alle Pflichtfunktionen da sind. Belegter
Fehlertext:

> `bad decoder=%s %s - some required function(s) not defined`

Ein unvollständiges Plugin fällt also **sofort** auf, nicht erst beim Abspielen.

Eigener Beispielcode:

```c
/* Eigener Beispielcode: vollstaendige Plugin-Tabellen (Clean-Room). */
#include <stdint.h>

typedef struct PluginContext PluginContext;

/* ---- Decoder ---- */
typedef struct {
    void*    (*open)(PluginContext*, const char* path, int fd, uint8_t* extras);
    int      (*decode)(PluginContext*, float* out, int max_frames,
                       int* channels, int* sample_rate, int* sample_fmt);
    int      (*seek)(PluginContext*, uint32_t serial, int64_t frame);
    void     (*pause_hint)(PluginContext*);
    void     (*resume_hint)(PluginContext*);
    void     (*close)(PluginContext*);
} DecoderVTable;

/* ---- DSP ---- */
typedef struct {
    int      (*block)(PluginContext*, float* interleaved, int frames, int channels);
    void     (*rebuild)(PluginContext*);   /* Koeffizienten neu, z.B. EQ */
} DspVTable;

/* ---- Output ---- */
typedef struct {
    int      (*open)(PluginContext*, int sample_rate, int channels, int fmt);
    int      (*start)(PluginContext*);
    int      (*pause)(PluginContext*, int pause);
    int      (*flush)(PluginContext*);
    void     (*close)(PluginContext*);
    double   (*latency_ms)(PluginContext*);
} OutputVTable;

/* Die Basis steht IMMER vorne. */
struct PluginContext {
    const char*  uniq_name;   /* "decoder.ffmpeg" */
    int          id;
    int          flags;
    int          api;         /* 1 Decoder, 2 DSP, 3 Output */
    void*        host;
    union { DecoderVTable dec; DspVTable dsp; OutputVTable out; } vt;
};
```

### 2.2 Der Registrierungs-Ablauf

Belegte Funktionen: `pa_alloc_plugin_context`, `pa_register_decoder/dsp/output`
(neu) und `internal_register_decoder/dsp` (intern), dazu
`internal_plugininterface_set_package` (Namensraum) und
`internal_set_dspi`/`internal_set_resampler` (Sonderfälle).

Ablauf beim Start:

```
1. JNI_OnLoad
2. internal_plugininterface_set_package("com.maxmpz.audioplayer")
3. fuer jedes eingebaute Plugin:
      ctx = pa_alloc_plugin_context(size)
      ctx->uniq_name = "decoder.ffmpeg"
      ctx->vt = ... (Pflichtfunktionen)
      pa_register_decoder(ctx)          // prueft die Tabelle
4. internal_set_dspi(...)                // interne DSP-Schnittstelle
5. internal_set_resampler(...)           // Resampler
6. Engine fragt: pa_get_plugin_by_uniq_name("decoder.ffmpeg")
```

Eigener Beispielcode für die Prüfung:

```c
/* Eigener Beispielcode: Pflichtfunktionen pruefen. */
static int decoder_valid(const DecoderVTable* v) {
    return v && v->open && v->decode && v->seek && v->close;
}

int register_decoder(PluginContext* p) {
    if (!p || !p->uniq_name) return -1;
    if (!decoder_valid(&p->vt.dec)) return -2;   /* "required function missing" */
    return engine_add(p);                         /* in die Liste */
}
```

**Analysepunkt:** Diese Prüfung ist der Grund, warum ein fehlendes oder falsch
gebautes Plugin nie zu einem Absturz mitten im Lied führt, sondern beim Start
auffällt. Ein billiger Test, der teure Fehler verhindert.

### 2.3 Namensraum und Namensauflösung

`internal_plugininterface_set_package` setzt den Paketnamen. Er wird für zwei
Dinge gebraucht: für die Prüfung, ob ein internes Plugin zum eigenen Paket
gehört, und für die Ableitung des Java-Klassennamens (Abschnitt 22.2). Der
`uniq_name` hat das Format `paket/name`, und `getPackage()` schneidet vor dem
`/` ab.

---

## 3 · Der Decoder-Thread

**Aufgabe:** Aus einer Datei oder einem Stream PCM machen und in einen
Ringpuffer schreiben. Sechs Decoder stehen zur Verfügung, sie werden der Reihe
nach probiert („Trying first available decoder", „Trying backup decoder").

### Zustandsmaschine und Nachrichten

Der Decoder-Thread bekommt Nachrichten (`decoder_handle_msg`,
`decoder_thread_request_seek`) und meldet Ereignisse zurück (`exec_decoder_opened`,
`exec_decoder_filled`, `exec_decoder_seeked`, `exec_decoder_failed`,
`exec_decoder_closed`). Das ist ein **Nachrichten-getriebenes** Modell, kein
direkter Funktionsaufruf zwischen Threads. Wichtig: Kein Thread greift in die
Daten eines anderen, es werden nur Nachrichten übergeben.

### Seek mit Serial-Nummern (wichtiger Trick)

Im Binary tauchen auf: `seek_serial`, `param seek_serial`, `PACKET_TYPE_SEEK_RES`,
`failed to seek serial=%d, slot_0.serial=%d, slot_1.serial=%d`.

Daraus lesen wir: Jeder Seek bekommt eine **fortlaufende Nummer**. Wenn das
Ergebnis zurückkommt, wird geprüft, ob die Nummer noch aktuell ist. Springt der
Nutzer schnell mehrfach, werden alte, veraltete Seeks verworfen. Ohne diese
Nummern würde ein später eintreffendes altes Ergebnis die Wiedergabe an die
falsche Stelle ziehen. Genau dieser Fehler passiert bei naiven Playern.

### Beispielcode: Seek-Nummern

```c
/* Eigener Beispielcode: Seek-Sicherung ueber Seriennummern. */

typedef struct {
    uint32_t last_request;   /* zuletzt angeforderter Seek */
    uint32_t last_applied;   /* zuletzt angewandter Seek */
} SeekState;

/* Nutzer springt: neue Nummer ziehen. */
uint32_t seek_request(SeekState* s) {
    return ++s->last_request;                /* nur der Thread, der besitzt */
}

/* Decoder meldet Ergebnis: nur uebernehmen, wenn noch aktuell. */
int seek_apply(SeekState* s, uint32_t serial, int64_t frame) {
    if (serial != s->last_request) return 0; /* veraltet -> verwerfen */
    s->last_applied = serial;
    /* hier an die neue Position springen */
    return 1;
}
```

### 3.1 Die Zustandsmaschine (mit Übergängen)

Aus den belegten Nachrichten und Zuständen ergibt sich diese Maschine:

| Zustand | Bedeutung | Erlaubte nächste |
|---|---|---|
| `CLOSED` | kein Decoder offen | `OPENING` |
| `OPENING` | Decoder wird geöffnet | `OPEN` oder `FAILED` |
| `OPEN` | bereit, wartet auf Füllen | `FILLING` |
| `FILLING` | liefert PCM in den Puffer | `FILLING`, `SEEKING`, `EOF` |
| `SEEKING` | springt, verwirft alte Ausgabe | `FILLING` oder `FAILED` |
| `EOF` | Dateiende erreicht | `OPENING` (nächster Track) |
| `FAILED` | Decoder kaputt | `OPENING` (Backup-Decoder) |

Belegte Signale dazu: `exec_decoder_opened`, `exec_decoder_filled`,
`exec_decoder_seeked`, `exec_decoder_failed`, `exec_decoder_closed`,
`PACKET_TYPE_SEEK_RES`.

### 3.2 Formatverhandlung

Der Decoder meldet sein **eigenes** Format. Passt es nicht zur Ausgabe, muss
umgerechnet werden. Belegter Fehlertext: `output resampler required, output:`.
Das heißt: Die Engine erkennt, dass die Quelle (z. B. 44,1 kHz, 2 Kanäle,
S16) vom Ziel (48 kHz, float) abweicht, und schaltet den Resampler ein.

```c
/* Eigener Beispielcode: Formatvergleich und Entscheidung. */
typedef struct { int sample_rate; int channels; int fmt; } AudioFormat;

/* fmt: 0=S16, 1=S24, 2=S32, 3=FLOAT */
static int needs_conversion(AudioFormat src, AudioFormat dst) {
    return (src.channels    != dst.channels)
        || (src.fmt         != dst.fmt)
        || (src.sample_rate != dst.sample_rate);
}

static int needs_resampler(AudioFormat src, AudioFormat dst) {
    return src.sample_rate != dst.sample_rate;
}
```

**Analysepunkt:** Man unterscheidet **Kanal-/Formatwandlung** (billig, im
Decoder-Thread) von **Resampling** (teuer, eigener Schritt). Wer beides vermischt,
rechnet unnötig. Poweramp trennt es: `pa_format_infos_same` vergleicht die
Formate, `resampleAndScaleAsNeeded` macht nur, was nötig ist.

### 3.3 Die Decoder-Schleife (Beispielcode)

```c
/* Eigener Beispielcode: Grundgeruest des Decoder-Threads. */
#include <stdatomic.h>
#include <string.h>

typedef enum { CLOSED, OPENING, OPEN, FILLING, SEEKING, EOF_, FAILED } DecState;

typedef struct {
    DecState  state;
    uint32_t  seek_serial;      /* aktuelle Nummer */
    int       cur_decoder;      /* Index in der Liste */
    RingBuffer* out;            /* Ringpuffer A */
} DecoderThread;

void decoder_thread_run(DecoderThread* d) {
    for (;;) {
        Msg m = msg_wait(&d->inbox);        /* blockiert nur hier */
        switch (m.type) {
            case MSG_OPEN:
                d->state = OPENING;
                if (open_decoder_chain(d, m.path) != 0) { d->state = FAILED; break; }
                d->state = OPEN;
                break;

            case MSG_SEEK:
                d->seek_serial = m.serial;
                d->state = SEEKING;
                do_seek(d, m.serial, m.frame);   /* verwirft alte Serien */
                d->state = FILLING;
                break;

            case MSG_FILL:
                /* PCM erzeugen und in den Ringpuffer schreiben. */
                if (decode_into(d, d->out) == 0) {
                    if (is_eof(d)) { d->state = EOF_; post(MSG_DECODER_EOF); }
                }
                break;

            case MSG_CLOSE:
                close_decoder(d);
                d->state = CLOSED;
                break;
        }
    }
}
```

**Analysepunkt:** Der einzige blockierende Aufruf ist `msg_wait` ganz oben. Er
wartet auf Nachrichten, nie auf Daten. Alles andere (Decoder öffnen, Seek,
Füllen) darf Zeit kosten, weil der Ringpuffer den Ausfall abfedert.

### 3.4 Reale Zahlen aus der Dekompilation

Aus `key-functions.c` und `all-functions.c` (Ghidra, Adressen und Werte):

| Fakt | Wert | Belegstelle |
|---|---|---|
| verankerte Funktionen im Handover | **189** | Zählung der `// ====`-Köpfe |
| Subsystem-Kontexte im Nachrichten-Router | **8** | `msg_router.c`: `MAX_SUBSYSTEM_CONTEXTS=%d` mit Argument `8` |
| Decoder-Slots | **2** (`slot_0`, `slot_1`) | Seek-Fehlertext in `key-strings.txt` |
| Thread-Namen | per `pthread_setname_np` gesetzt | `all-functions.c` (Aufruf nach `pthread_create`) |
| Nachrichten-Router | `msg_router_register_subsystem_no_sync`, `register_subsystem_for_plugin_type` | `key-functions.c` |

**Die zwei Decoder-Slots sind ein wichtiger Fund.** Sie erklären, wie nahtlose
Übergänge möglich sind: Während Slot 0 noch abspielt, wird Slot 1 schon geöffnet
und gefüllt. Der Fehlertext `failed to seek serial=%d, slot_0.serial=%d,
slot_1.serial=%d` zeigt, dass **jeder Slot seine eigene Seek-Nummer** hat. So
kann ein Seek in Slot 1 laufen, während Slot 0 ungestört weiterspielt. Das ist
genau die Bauform, die wir für den Auto-DJ brauchen (Deck A spielt, Deck B wird
vorbereitet).

**Die acht Subsystem-Kontexte** sind die feste Menge an Zuständen, die der Router
verwalten kann (Decoder, DSP, Output, Resampler und Sonderfälle). Acht sind
genug für alle eingebauten Plugins. Wer mehr braucht, bekommt den belegten
Fehler `no place for ctx=... by id`.

**Die Nachrichten sind nummeriert.** Der Router (`msg_router.c`) verteilt sie an
Subsysteme, ohne dass Sender und Empfänger sich kennen. Das ist derselbe Gedanke
wie der UI-Bus in Abschnitt 18, nur zwischen nativen Teilen.

---

## 4 · Der DSP-Thread (das Herz der Engine)

**Aufgabe:** Aus dem rohen PCM des Decoders das fertige PCM für die Ausgabe
machen. Im Binary heißt das `dsp_block` und `dsp_do_dsp_block`.

Was in diesem Thread passiert (belegt durch die Strings):

- **Equalizer** (`equ5_*`, `handle_dsp_band_coefs`, `handle_dsp_equ_rebuild`)
- **ReplayGain** (`replaygain_track_gain`, `replaygain_album_gain`)
- **Preamp und Kopfraum** (`equ5_float_set_preamp_mb`,
  `equ5_float_set_no_dvc_headroom_mb`)
- **Resampling** (`resampleAndScaleAsNeeded`, `plugin.resampler3`,
  `flush_resampler_last_frames`)
- **Gapless und Crossfade** (`dsp_postfade_blocks`, `request_fade_impl`)
- **Lautstärke** (`equ5_float_set_track_volume_linear`)
- **Visualisierung** (`AshmemAudioSourceDSP`, `PodPresetFrameVarpool`)

### Der Block als Arbeitseinheit

Im Binary stehen die zentralen Puffergrößen:

```
frames_per_block=%d block ms=%f num_bufs=%d ...
output_buf_ms=%d dsp_bufs=%d dsp_postfade_blocks=%d dsp_prefetch_bufs=%d
```

Das Modell:

- **`frames_per_block`**: wie viele Samples pro Verarbeitungsschritt.
- **`block ms`**: die Länge eines Blocks in Millisekunden.
- **`num_bufs` / `dsp_bufs`**: Anzahl der Puffer in der Kette.
- **`dsp_prefetch_bufs`**: Vorlauf-Puffer, damit der DSP nie auf Daten wartet.
- **`dsp_postfade_blocks`**: zusätzliche Blöcke für das Ausklingen (Crossfade).

**Warum Blöcke und nicht Sample für Sample?** Ein Block teilt die Arbeit in
gleichmäßige Häppchen. Feste Blockgrößen erlauben **Vorallokation** (kein
Speicher-Reservieren im Echtzeitpfad) und machen die Verarbeitung
berechenbar. Die Puffer sind vorab angelegt, zur Laufzeit wird nur noch
hineingeschrieben.

### Beispielcode: der Verarbeitungs-Block

```c
/* Eigener Beispielcode: ein DSP-Block mit fester Puffergroesse. */

#include <string.h>

#define MAX_CHANNELS 2
#define MAX_FRAMES_PER_BLOCK 4096

typedef struct {
    float* data[MAX_CHANNELS];   /* zeigt auf vorallokierten Speicher */
    int    channels;
    int    frames;               /* tatsaechlich gefuellte Frames */
} AudioBlock;

typedef struct {
    AudioBlock blocks[8];        /* Pool, fest angelegt */
    int        write_idx;
    int        frames_per_block;
    int        channels;
    float      scratch[MAX_CHANNELS][MAX_FRAMES_PER_BLOCK];
} DspStage;

/* Alles einmal beim Start reservieren. Im Betrieb NICHTS mehr. */
int dsp_stage_init(DspStage* s, int channels, int frames_per_block) {
    if (frames_per_block > MAX_FRAMES_PER_BLOCK) return -1;
    s->channels = channels;
    s->frames_per_block = frames_per_block;
    for (int i = 0; i < 8; ++i) {
        s->blocks[i].channels = channels;
        for (int c = 0; c < channels; ++c)
            s->blocks[i].data[c] = (float*)s->scratch[c]; /* feste Adresse */
    }
    return 0;
}

/* Wird pro Block aufgerufen. Keine Allokation, keine Sperren. */
void dsp_process_block(DspStage* s, AudioBlock* in, AudioBlock* out) {
    const int n = in->frames;
    for (int c = 0; c < s->channels; ++c) {
        /* hier spaeter: EQ, Gain, Limiter, Resampling */
        memcpy(out->data[c], in->data[c], (size_t)n * sizeof(float));
    }
    out->frames = n;
}
```

### 4.1 Die Reihenfolge der Kette (sie ist nicht beliebig)

Aus den belegten Funktionen ergibt sich die Reihenfolge:

```
 Eingang (float, decodiert)
   |
 Preamp        equ5_float_set_preamp_mb
   |
 ReplayGain    replaygain_track_gain / replaygain_album_gain
   |
 EQ-Baender    equ5_float_set_band_gain (5 Baender)
   |
 Master        equ5_float_set_master_mb
   |
 Kopfraum      equ5_float_set_no_dvc_headroom_mb   (DVC)
   |
 Volume        equ5_float_set_track_volume_linear
   |
 Limitieren    (Schutz vor Uebersteuerung)
   |
 Ausgang
```

**Warum diese Reihenfolge?**

- **ReplayGain vor dem EQ.** Erst die Lautheit auf einen Bezug bringen, dann
  klanglich formen. Umgekehrt würde der EQ den Bezug verändern.
- **Kopfraum nach dem EQ.** Der EQ darf anheben. Der Kopfraum wird aus der
  **Summe der Anhebungen** berechnet, nicht fest gesetzt.
- **Volume nach dem Kopfraum.** Die Lautstärke ist der letzte Faktor, damit sie
  den Bezug nicht verschiebt.
- **Limitieren zuletzt.** Falls alles zusammen doch über 0 dBFS geht.

### 4.2 Koeffizienten-Updates (ohne Knacken)

Belegt: `handle_dsp_equ_rebuild`, `handle_dsp_band_coefs`,
`native_calc_bands_coefs`. Der EQ rechnet seine Koeffizienten **nicht** pro
Sample und nicht mitten im Block. Stattdessen:

1. Der UI-Thread berechnet neue Koeffizienten (oder ein Kurz-Puffer).
2. Sie werden in einen **zweiten Satz** geschrieben.
3. Am **Blockende** wird umgeschaltet (Zeiger tauschen).

So ändert sich der Klang nur an einer Blockgrenze, nie mitten im Sample. Ohne
das hört man beim Ziehen am EQ ein Knacken.

```c
/* Eigener Beispielcode: doppelt gepufferte Koeffizienten. */
#include <stdatomic.h>

typedef struct { float b0,b1,b2,a1,a2; } Biquad;

typedef struct {
    Biquad   front[5];       /* aktiv, nur der DSP-Thread liest */
    Biquad   back[5];        /* Kandidat, nur der UI-Thread schreibt */
    _Atomic int pending;
} EqParams;

/* UI-Thread: neue Werte schreiben, dann anmelden. */
void eq_set(EqParams* e, const Biquad n[5]) {
    for (int i = 0; i < 5; ++i) e->back[i] = n[i];
    atomic_store_explicit(&e->pending, 1, memory_order_release);
}

/* DSP-Thread: am Blockende uebernehmen. */
void eq_swap_if_pending(EqParams* e) {
    if (atomic_exchange_explicit(&e->pending, 0, memory_order_acquire)) {
        for (int i = 0; i < 5; ++i) e->front[i] = e->back[i];
    }
}
```

### 4.3 Denormale Zahlen (ein leiser Killer)

Ein Biquad-Filter kann in einen Zustand geraten, wo die Werte unendlich klein
werden (denormal). Solche Zahlen sind auf ARM **sehr** langsam, weil sie in
Software behandelt werden. Ein leises Stück kann so CPU fressen, obwohl nichts
zu hören ist. Lösung: **Flush-to-Zero** einschalten oder einen minimalen
Versatz addieren.

```c
/* Eigener Beispielcode: Denormale ausschalten (ARM). */
#if defined(__aarch64__)
static inline void enable_flush_to_zero(void) {
    uint64_t fpcr;
    __asm__ __volatile__("mrs %0, fpcr" : "=r"(fpcr));
    fpcr |= (1u << 24);            /* FZ: Flush to Zero */
    __asm__ __volatile__("msr fpcr, %0" : : "r"(fpcr));
}
#endif
```

### 4.4 Der vollständige Block-Prozessor

```c
/* Eigener Beispielcode: ein Block durch die ganze Kette. */
void dsp_process_block(Dsp* d, float* buf, int frames, int channels) {
    eq_swap_if_pending(&d->eq);                 /* nur an der Blockgrenze */

    /* 1. Preamp + ReplayGain (ein Faktor) */
    float g = d->preamp_lin * d->rg_lin;
    for (int i = 0; i < frames * channels; ++i) buf[i] *= g;

    /* 2. EQ: 5 Baender, je Kanal */
    for (int b = 0; b < 5; ++b)
        for (int c = 0; c < channels; ++c)
            biquad_run(&d->eq.front[b], d->state[b][c], buf + c, frames, channels);

    /* 3. Kopfraum + Volume */
    float v = d->headroom_lin * d->volume_lin;
    for (int i = 0; i < frames * channels; ++i) buf[i] *= v;

    /* 4. Limitieren (weiches Begrenzen) */
    for (int i = 0; i < frames * channels; ++i) {
        float x = buf[i];
        if (x >  1.0f) x =  1.0f;
        if (x < -1.0f) x = -1.0f;
        buf[i] = x;
    }
}
```

### 4.5 Reale Zahlen: die Puffergrenzen (Prüf- und Klemmwerte)

Die Funktion `create_output_and_buffers` (in `dsp_thread.c`) prüft die
Ausgabeparameter und **klemmt** sie auf gültige Bereiche. Das sind die echten
Zahlen aus der Dekompilation:

| Parameter | Gültiger Bereich | Verhalten bei Verletzung | Beleg (Wert) |
|---|---|---|---|
| `features.request_dsp_blocks` | **1 bis 10** | klemmen auf 10 bzw. 1, loggen | `0xb` = 11 in der Grenzprüfung |
| `features.request_dsp_prefetch_blocks` | **1 bis 10** | klemmen | dito |
| `features.request_dsp_postfade_blocks` | **0 bis 10** | klemmen | `10 <` Prüfung, dann 0 |
| `features.latency_ms` | **1,0 bis 10000,0 ms** | klemmen | `1.0` und `0x461c4000` = 10000.0 |
| `features.presentation_latency_ms` | **0,0 bis 10000,0 ms** | klemmen | dito |
| `num_blocks` | **> 0** | Fehlercode | `local_c0._4_4_ == 0` |
| `frames_per_block` | **>= 1** | Fehlercode | `*(int *)(lVar8 + 0x8c) < 1` |
| `output_buf_ms` | aus den Blöcken gerechnet | — | `num_blocks * 1000 / sr` |
| `sr_mult` | Abtastrate / 48000, **min. 1** | — | `iVar20 / 48000; if (<48000) = 1` |
| Fallback-Puffergröße | **1024 Frames** | Ersatz | `MIN_BUF_FRAMES_SAFE = 0x400` |

Zwei Formeln aus dem Code:

```
 block_ms      = num_blocks * 1000 / sample_rate
 sr_mult       = max(1, sample_rate / 48000)
```

**Analysepunkt:** Diese Zahlen sagen, wie Poweramp Latenz und Stabilität
abwägt. Zehn Blöcke sind die Obergrenze (mehr wäre nur Latenz ohne Nutzen). Ein
Millisekunden-Bereich von 1 bis 10000 fängt kaputte Gerätewerte ab. Und der
Ersatz von **1024 Frames** ist der sichere Boden: Liefert ein Gerät
unsinnige Werte, nimmt die Engine 1024 Frames (bei 48 kHz etwa 21 ms) und
weiter geht es, ohne Absturz.

Eigener Beispielcode, der dieselbe Klemmlogik zeigt:

```c
/* Eigener Beispielcode: Werte klemmen statt abstuerzen (wie im Original). */
static int clamp_int(int v, int lo, int hi) { return v < lo ? lo : (v > hi ? hi : v); }
static float clamp_f(float v, float lo, float hi) { return v < lo ? lo : (v > hi ? hi : v); }

typedef struct {
    int   dsp_blocks;          /* 1..10 */
    int   dsp_prefetch_blocks; /* 1..10 */
    int   dsp_postfade_blocks; /* 0..10 */
    float latency_ms;          /* 1..10000 */
} OutFeatures;

static void sanitize(OutFeatures* f, int* frames_per_block_out) {
    f->dsp_blocks          = clamp_int(f->dsp_blocks,          1, 10);
    f->dsp_prefetch_blocks = clamp_int(f->dsp_prefetch_blocks, 1, 10);
    f->dsp_postfade_blocks = clamp_int(f->dsp_postfade_blocks, 0, 10);
    f->latency_ms          = clamp_f(f->latency_ms, 1.0f, 10000.0f);
    if (*frames_per_block_out < 1) *frames_per_block_out = 0x400;  /* 1024 */
}
```

---

## 5 · Die Ausgabe-Schicht (Output-Plugins)

Poweramp fährt **mehrere Ausgabewege parallel**, je nach Gerät und Android-
Version. Das sieht man an den Unterpaketen und den Aufrufen im Binary:

| Ordner | Bedeutung | Belegtes Aufrufmuster |
|---|---|---|
| `aa` | **AAudio** (neu, ab Android 8.1) | `AAudioStream_requestStart/Stop/Pause/Flush` |
| `osl`, `oslhd` | **OpenSL ES** (alt, API 9+) und High-Definition-Variante | OpenSL-Property-Strings |
| `at`, `athd` | **AudioTrack** (Java/Plattform) und HD-Variante | AudioTrack-Streams |
| `cc` | vermutlich Cast/Client (Ausgabe-Brücke) | Verweise auf Ausgabekonfiguration |

`pa_register_output` registriert diese Wege im selben Plugin-System.

### Latenz-Verhandlung (sehr wichtig)

Im Binary stehen drei Latenzbegriffe:

```
features.latency_ms
features.presentation_latency_ms
vis_latency_ms
```

- **`latency_ms`**: die reine Puffer-Latenz der Ausgabe.
- **`presentation_latency_ms`**: die gesamte Zeit bis der Ton hörbar ist
  (Puffer plus Hardware). Der Wert, der beim Video-Bild wichtig ist.
- **`vis_latency_ms`**: der Wert, der an die Anzeige geht, damit die Seekbar
  und die Visualisierung synchron zum Ton laufen.

**Warum getrennt?** Weil Audio und Anzeige unterschiedlich verzögert sind. Der
Ton wird ausgegeben, während das Bild leicht hinterherläuft. Wer beides mit
einem Wert rechnet, zeigt den Fortschritt falsch an. Poweramp trennt es bewusst.

### Callback- oder Blockbetrieb

Im Binary steht `using_callback=%d`. Poweramp nutzt also beide Modi: den
**Callback** (das System ruft, wenn es Daten braucht) und den **Blockbetrieb**
(man schiebt selbst Daten). Callback ist latenzärmer, Blockbetrieb robuster.
Je nach Gerät wird gewählt.

### Das Rezept für niedrige Latenz

Aus den Strings, kombiniert mit der Android-Lehre:

- `PerformanceMode::LowLatency`
- `SharingMode::Exclusive`
- **AAudio MMAP** (der latenzärmste Pfad)
- passende Puffergröße (`frames_per_packet`, `bytes_per_packet`, `packet ms`)

### OEM-Sonderfälle (die bittere Realität)

Im Binary stehen Hersteller-Hacks, wörtlich unter anderem:

```
moto !FLAG_SUPPORTS_SPEAKER
Deep-Buffer-Device-Hacks fuer MIUI / OnePlus / Oppo / Moto
```

Das heißt: Poweramp erkennt bestimmte Hersteller und schaltet auf
**größere Puffer** um, weil kleine Puffer dort knacken. Das ist keine
Theorie, das ist der teuerste Teil der Entwicklung. **Für uns die wichtigste
Warnung:** Piano-Support ist Teil des Produkts, nicht ein Detail am Ende.

### 5.1 Die Ausgabe-Schnittstelle (gemeinsam für alle Wege)

Alle vier Wege (AAudio, OpenSL ES, AudioTrack, HD) erfüllen dieselbe Schnittstelle.
Belegte Aufrufe wie `AAudioStream_requestStart/Stop/Pause/Flush` und die drei
Latenzwerte sind die Grundlage:

```cpp
// Eigener Beispielcode: gemeinsame Ausgabe-Schnittstelle (Clean-Room).
class Output {
public:
    virtual ~Output() = default;
    virtual bool open(int sampleRate, int channels, int format) = 0;
    virtual bool start() = 0;
    virtual bool pause(bool paused) = 0;
    virtual void flush() = 0;                 // Puffer verwerfen (nach Seek)
    virtual void close() = 0;

    // Drei Werte, nie einer:
    virtual double bufferLatencyMs()      = 0;  // features.latency_ms
    virtual double presentationMs()       = 0;  // features.presentation_latency_ms
    virtual double visualLatencyMs()      = 0;  // vis_latency_ms

    // Aussetzer zaehlen statt verstecken:
    virtual uint64_t underruns() = 0;
};
```

**Analysepunkt:** `flush` ist der stille Held. Nach einem Seek muss der noch
gepufferte Ton **weggeworfen** werden, sonst hört man für einen Moment den Ton
von vorher. Genau dafür gibt es `AAudioStream_requestFlush`.

### 5.2 Latenz verhandeln (Algorithmus)

Die Puffergröße wird nicht geraten, sondern in Stufen gesucht:

```
1. Wunsch: kleinster Puffer mit PerformanceMode = LowLatency, SharingMode = Exclusive
2. Pruefen: unterstuetzt das Geraet den Puffer? (getFramesPerBurst, getBufferSizeInFrames)
3. Schlaegt es fehl ODER treten Aussetzer auf -> Puffer verdoppeln
4. Nach N Sekunden stabil -> akzeptieren und die Latenz melden
5. Bekannter Problem-Hersteller -> sofort mit groesserem Puffer starten
```

```cpp
// Eigener Beispielcode: Puffergroesse stufenweise anpassen.
struct OutputTuning {
    int baseFrames;
    int maxFrames;
    int currentFrames;

    // Nach einer Messrunde aufrufen. xruns = Aussetzer, elapsedSec = Messdauer.
    void adapt(uint64_t xruns, double elapsedSec) {
        const double perSec = elapsedSec > 0 ? xruns / elapsedSec : 0.0;
        if (perSec > 0.5 && currentFrames < maxFrames) {
            currentFrames = std::min(currentFrames * 2, maxFrames);   // verdoppeln
        } else if (perSec < 0.01 && currentFrames > baseFrames) {
            currentFrames = std::max(currentFrames * 3 / 4, baseFrames); // vorsichtig senken
        }
    }
};
```

### 5.3 Gerätewechsel und Unterbrechungen

Belegte Zustände und Signale: `DSP_STATE_PAUSING`, `DSP_STATE_STOPPING`,
`CC_STATE_WAIT_FOR_RESUME`. Dazu die Empfänger `HeadsetMicroService`,
`ManifestHeadsetPlugReceiver` (Klinke rein/raus), `BTReceiver` (Bluetooth) und
`PSMediaButtonReceiver`.

Ablauf bei „Kopfhörer raus":
1. Broadcast kommt an (`android.intent.action.HEADSET_PLUG`).
2. Die Engine **pausiert weich** (`DSP_STATE_PAUSING`), wartet auf „Zeros to
   auto stopped".
3. Ausgabe wird umgehängt (neues Gerät, neue Abtastrate).
4. Resampler wird geleert (`flush_resampler_last_frames`).
5. Weiter bei derselben Position.

**Analysepunkt:** Der Schritt „weich pausieren" verhindert ein lautes Knacken,
wenn plötzlich auf den Lautsprecher umgeschaltet wird. Wer hier hart umschaltet,
bekommt in Bewertungen „es macht einen lauten Knall beim Ausstecken".

---

## 6 · Performance: warum es schnell bleibt

Das ist der Kern deiner Frage. Es gibt nicht den einen Trick, sondern viele
kleine Regeln. Ein Audio-Player darf im Audiopfad praktisch **nichts** tun, was
Zeit kosten kann.

### 6.1 Die eiserne Regel: kein Sperren, kein Reservieren, kein Warten

Im Echtzeit-Audiopfad gilt: keine Mutex, kein `malloc`, kein Dateizugriff, kein
Log, kein Lock, keine Ausnahme. Alles, was passieren kann, muss vorher
vorbereitet sein.

### Beispielcode: lock-freier Ringpuffer (single producer / single consumer)

```c
/* Eigener Beispielcode: SPSC-Ringpuffer ohne Sperren.
   Ein Schreiber (Decoder/DSP), ein Leser (Ausgabe). Nur atomare Indizes. */

#include <stdatomic.h>
#include <stdint.h>
#include <string.h>

typedef struct {
    float*           buffer;      /* Groesse ist Zweierpotenz */
    uint32_t         size;        /* z.B. 1<<16 */
    uint32_t         mask;
    _Atomic uint32_t write;       /* nur der Schreiber aendert das */
    _Atomic uint32_t read;        /* nur der Leser aendert das */
} RingBuffer;

void rb_init(RingBuffer* rb, float* storage, uint32_t pow2_size) {
    rb->buffer = storage;
    rb->size = pow2_size;
    rb->mask = pow2_size - 1;
    atomic_store_explicit(&rb->write, 0, memory_order_relaxed);
    atomic_store_explicit(&rb->read,  0, memory_order_relaxed);
}

/* Schreiber-Thread: gibt zurueck, wie viele Frames geschrieben wurden. */
uint32_t rb_write(RingBuffer* rb, const float* src, uint32_t frames, int channels) {
    const uint32_t w = atomic_load_explicit(&rb->write, memory_order_relaxed);
    const uint32_t r = atomic_load_explicit(&rb->read,  memory_order_acquire);
    const uint32_t free_frames = (rb->size - (w - r)) / channels - 1; /* -1: nie voll */
    if (frames > free_frames) frames = free_frames;                   /* lieber kuerzen */
    for (uint32_t i = 0; i < frames * channels; ++i)
        rb->buffer[(w + i) & rb->mask] = src[i];
    atomic_store_explicit(&rb->write, w + frames * channels, memory_order_release);
    return frames;
}

/* Leser-Thread (oder Audio-Callback): liest verfuegbare Frames. */
uint32_t rb_read(RingBuffer* rb, float* dst, uint32_t frames, int channels) {
    const uint32_t r = atomic_load_explicit(&rb->read,  memory_order_relaxed);
    const uint32_t w = atomic_load_explicit(&rb->write, memory_order_acquire);
    const uint32_t avail = (w - r) / channels;
    if (frames > avail) frames = avail;
    for (uint32_t i = 0; i < frames * channels; ++i)
        dst[i] = rb->buffer[(r + i) & rb->mask];
    atomic_store_explicit(&rb->read, r + frames * channels, memory_order_release);
    return frames;
}
```

Warum das schnell ist:
- Keine Sperre, nur zwei atomare Zähler. Der Schreib-Thread rührt `read` nicht an,
  der Lese-Thread rührt `write` nicht an. Damit gibt es keinen Wettlauf.
- Der Index läuft im Kreis (`& mask`), kein Modulo, kein Neuallokieren.
- Die Adressen sind fest. Kein Zeiger-Wechsel, kein Cache-Sprung.

### 6.2 Vorallokation und Pools

Alle Puffer, Blöcke und Objekte werden **beim Start** angelegt. Zur Laufzeit
wird nur noch hineingeschrieben. Im Java-Teil wichtig: keine neuen Objekte im
Audiopfad, sonst räumt der Garbage Collector und es knackt.

### 6.3 Feste Blockgrößen

Feste Blockgrößen (siehe Abschnitt 4) machen die Arbeit planbar und erlauben
Vorallokation. Sie sind auch die Voraussetzung für SIMD.

### 6.4 SIMD und Fließkomma

Im Binary stehen `float-dspi-support.c` und `neon`-Bezüge (ffmpeg NEON). Der
Rechenkern arbeitet mit **32-Bit-Float** und nutzt **NEON** (ARM-SIMD). Float ist
einfacher für EQ und Gain als Ganzzahl. Wichtig: SIMD verarbeitet mehrere
Samples gleichzeitig, deshalb die Blockverarbeitung.

### 6.5 Keine Syscalls im Callback

Der Ausgabe-Callback ruft **nichts** auf, was blockieren könnte. Er liest nur aus
dem Ringpuffer und kopiert. Alles andere (Decoder, DSP, Datei) läuft in anderen
Threads.

### 6.6 Thread-Priorität

Der Ausgabe- und der DSP-Thread laufen mit **hoher Priorität** (Echtzeit-nah),
der Decoder-Thread normal. So bekommt die Ausgabe Vorrang, der Decoder darf
nachlaufen.

### 6.7 Latenz gegen Sicherheit abwägen

Kleinere Puffer bedeuten weniger Latenz, aber mehr Knack-Gefahr. Poweramp wählt
die Puffergröße **pro Gerät** (`at_min_buf_frames`, `sl_min_buf_frames`,
`g_at_min_buf_frames_48k`). Auf schwachen Geräten größere Puffer, auf guten
kleinere.

### 6.8 Messen statt hoffen

Entscheidend ist das Zählen von **Aussetzern** (Underruns/XRuns). Wenn die
Ausgabe keine Daten bekommt, zählt man das. Nur so weiß man, ob der Puffer zu
klein ist.

### 6.9 Speicher-Barrieren verstehen (nicht raten)

Ein lock-freier Ringpuffer funktioniert nur mit den **richtigen** Barrieren, und
zwar genau zwei: **release** beim Schreiben des Index, **acquire** beim Lesen.
Zu viele Barrieren kosten Leistung, zu wenige verursachen seltene, unfindbare
Fehler.

```
Schreiber:  [... Daten schreiben ...]  release(store write)
Leser:      acquire(load write)        [... Daten lesen ...]
```

Die Daten selbst brauchen **keine** Atomik, weil sie über den Index
synchronisiert werden. Das ist der Grund, warum der Ringpuffer billig ist.

### 6.10 Falsches Teilen (false sharing) vermeiden

Zwei Threads, die **verschiedene** Variablen im **selben** Cache-Block anfassen,
bremsen sich gegenseitig. `write` und `read` des Ringpuffers liegen deshalb oft
in **getrennten** Cache-Zeilen (Padding).

```c
/* Eigener Beispielcode: Indizes auf getrennte Cache-Zeilen legen. */
#include <stdatomic.h>
#include <stddef.h>

#define CACHE_LINE 64

typedef struct {
    _Atomic uint32_t write;
    char pad1[CACHE_LINE - sizeof(uint32_t)];
    _Atomic uint32_t read;
    char pad2[CACHE_LINE - sizeof(uint32_t)];
} SplitIndices;
```

**Analysepunkt:** Ohne Padding „ping-pongt" der Cache-Block zwischen den Kernen,
und der Durchsatz sinkt deutlich. Bei 60 mal 1000 Aufrufen pro Sekunde ist das
messbar.

### 6.11 Vektorrechnung für den EQ (NEON)

Der EQ ist der teuerste Teil pro Sample. Er läuft über **mehrere Samples in
einem Schritt**. Ein Biquad ist eine Differenzengleichung, die sich zwar nicht
beliebig vektorisieren lässt, aber für **zwei Kanäle gleichzeitig** oder für
**mehrere Blöcke** sehr wohl.

```c
/* Eigener Beispielcode: Biquad fuer zwei Kanaele parallel (NEON). */
#if defined(__aarch64__)
#include <arm_neon.h>
static inline void biquad_stereo_neon(const float* b, const float* a,
                                      float* z, float32x2_t* x, float32x2_t* y) {
    /* b = {b0,b1,b2}, a = {1,a1,a2}; z = Zustand fuer beide Kanaele */
    float32x2_t b0 = vdup_n_f32(b[0]), b1 = vdup_n_f32(b[1]), b2 = vdup_n_f32(b[2]);
    float32x2_t a1 = vdup_n_f32(a[1]), a2 = vdup_n_f32(a[2]);
    float32x2_t z1 = vld1_f32(z), z2 = vld1_f32(z + 2);
    float32x2_t out = vmla_f32(z1, b0, *x);          // y = z1 + b0*x
    z1 = vsub_f32(vmla_f32(z2, b1, *x), vmul_f32(a1, out));
    z2 = vsub_f32(vmul_f32(b2, *x), vmul_f32(a2, out));
    vst1_f32(z, z1); vst1_f32(z + 2, z2);
    *y = out;
}
#endif
```

Sinne: Statt zwei Durchläufe (links, rechts) macht man **einen** mit zwei
Lanes. Halbiert die Rechenzeit für den EQ.

### 6.12 Messen statt hoffen (Messrahmen)

```cpp
// Eigener Beispielcode: Aussetzer und Latenz messen.
struct AudioStats {
    std::atomic<uint64_t> frames{0};
    std::atomic<uint64_t> underruns{0};
    std::atomic<double>   maxLatencyMs{0};

    void onCallback(int n, double latencyMs) {
        frames.fetch_add(n, std::memory_order_relaxed);
        if (latencyMs > maxLatencyMs.load(std::memory_order_relaxed))
            maxLatencyMs.store(latencyMs, std::memory_order_relaxed);
    }
    void onUnderrun() { underruns.fetch_add(1, std::memory_order_relaxed); }

    double underrunsPerSec(double seconds) const {
        return seconds > 0 ? (double)underruns.load() / seconds : 0.0;
    }
};
```

**Analysepunkt:** Ohne diese Zahlen ist „läuft flüssig" ein Gefühl. Mit ihnen ist
es eine Zahl, die man gegen die Puffergröße aufträgt und daraus die richtige
Größe wählt.

---

## 7 · Equalizer (equ5) und ReplayGain

Aus den Strings ist die komplette Gain-Kette belegt:

```
equ5_calc_coefs_w_gain           Koeffizienten berechnen
equ5_float_set_band_gain         Band-Verstaerkung
equ5_float_set_master_mb         Master in Millibel
equ5_float_set_preamp_mb         Preamp in Millibel
equ5_float_set_no_dvc_headroom_mb  Kopfraum ohne DVC
equ5_float_set_track_rg_mb       ReplayGain Titel
equ5_float_set_track_volume_linear  Lineare Lautstaerke
replaygain_track_gain / album_gain / track_peak / album_peak
```

Daraus ergibt sich diese Reihenfolge in der Kette:

```
Preamp  ->  ReplayGain (Titel/Album)  ->  5-Band-PEQ  ->  Kopfraum/DVC  ->  Volume
```

- **Preamp**: globaler Vorverstärker.
- **ReplayGain**: gleicht die Lautheit zwischen Titeln an (Titel) oder innerhalb
  eines Albums (Album), plus Peak-Wert zur Übersteuerungs-Kontrolle.
- **PEQ**: parametrischer Equalizer mit Bändern (`Band`-Klasse:
  `com/maxmpz/dsp/data/Band`).
- **Kopfraum („headroom")**: Wenn der EQ Bänder anhebt, kann die Summe
  übersteuern. Der Kopfraum zieht vorher ab.
- **DVC** (Direct Volume Control): Lautstärke direkt im DSP statt im Systemmixer.
  Das klingt besser, braucht aber eigenen Kopfraum.

### Beispielcode: Biquad-Peaking-Filter (Standard-Formeln)

```c
/* Eigener Beispielcode: RBJ-Peaking-Biquad. Oeffentliche Standardformeln. */

#include <math.h>

typedef struct { float b0, b1, b2, a1, a2; } Biquad;
typedef struct { float z1, z2; } BiquadState;
typedef struct { Biquad coef; BiquadState st[2]; } BiquadStereo;

/* f0: Mittenfrequenz, Q: Guete, dbGain: Verstaerkung, fs: Abtastrate */
void biquad_peaking(Biquad* f, float f0, float Q, float dbGain, float fs) {
    const float A     = powf(10.0f, dbGain / 40.0f);
    const float w0    = 2.0f * (float)M_PI * f0 / fs;
    const float alpha = sinf(w0) / (2.0f * Q);
    const float cosw0 = cosf(w0);

    const float b0 = 1.0f + alpha * A;
    const float b1 = -2.0f * cosw0;
    const float b2 = 1.0f - alpha * A;
    const float a0 = 1.0f + alpha / A;
    const float a1 = -2.0f * cosw0;
    const float a2 = 1.0f - alpha / A;

    /* Normalisieren, damit der Zustand stabil bleibt */
    f->b0 = b0 / a0; f->b1 = b1 / a0; f->b2 = b2 / a0;
    f->a1 = a1 / a0; f->a2 = a2 / a0;
}

/* Direktform II transponiert: ein Zustand pro Kanal, wenig Rundungsfehler. */
static inline float biquad_tick(const Biquad* f, BiquadState* s, float x) {
    const float y = f->b0 * x + s->z1;
    s->z1 = f->b1 * x - f->a1 * y + s->z2;
    s->z2 = f->b2 * x - f->a2 * y;
    return y;
}

void biquad_process_stereo(const BiquadStereo* bs, float* left, float* right, int n) {
    for (int i = 0; i < n; ++i) {
        left[i]  = biquad_tick(&bs->coef, (BiquadState*)&bs->st[0], left[i]);
        right[i] = biquad_tick(&bs->coef, (BiquadState*)&bs->st[1], right[i]);
    }
}
```

**Wichtig für Performance:** Koeffizienten werden **selten** berechnet (nur wenn
der Nutzer den EQ ändert, `handle_dsp_equ_rebuild`), nicht pro Block. Der
Sample-Pfad macht nur `biquad_tick`, ein paar Multiplikationen pro Sample.

### Umgang mit Übersteuerung

Q und Anhebung müssen begrenzt werden. Im Binary stehen Prüfungen wie
`bad band=%d type=%d freq=%d q=%f` und Grenzen bei 48 kHz. Der Kopfraum
verhindert, dass aufgedrehte Bänder klippen.

### 7.1 Die Kopfraum-Rechnung (genau)

Der Kopfraum („headroom") ist nicht fest. Er folgt aus den EQ-Einstellungen:
hebt der Nutzer Bänder an, muss vorher abgesenkt werden.

```
Kopfraum_dB = -max(0, maximale_summe_der_anhebungen_dB)
```

Beispiel: Zwei Bänder +6 dB und +4 dB, die sich überlappen, können in der Summe
+8 dB ergeben. Dann wird um 8 dB abgesenkt, damit nichts clippt.

```python
# Eigener Beispielcode: Kopfraum aus den Band-Verstaerkungen.
def headroom_db(band_gains_db, overlap_safety_db=3.0):
    positive = [g for g in band_gains_db if g > 0]
    if not positive:
        return 0.0
    worst = sum(positive) + overlap_safety_db   # grobe Obergrenze
    return -min(worst, 24.0)                     # nie mehr als 24 dB

# Beispiel: [6, 0, 4, 0, 0] -> -13.0 dB Kopfraum
```

### 7.2 ReplayGain und Lautheit (Lautstärke-Angleich)

Im Binary: `replaygain_track_gain`, `replaygain_album_gain`,
`replaygain_track_peak`, `replaygain_album_peak`. Dazu `libebur128`
(im Mixxx-Umfeld belegt, bei Poweramp als Funktion vorhanden).

Zwei Betriebsarten: **Titel** (jeder Song auf denselben Pegel) und **Album**
(innerhalb eines Albums relativ bleiben). Der Peak-Wert dient dem Limiter.

```c
/* Eigener Beispielcode: ReplayGain in einen linearen Faktor umrechnen. */
#include <math.h>
static inline float db_to_lin(float db) { return powf(10.0f, db / 20.0f); }

/* track_gain_db kommt aus dem Tag oder aus der Analyse. */
static float replaygain_linear(int mode_album, float track_gain_db,
                               float album_gain_db) {
    return db_to_lin(mode_album ? album_gain_db : track_gain_db);
}

/* Mit Peak: nie ueber 0 dBFS. */
static float with_peak(float lin, float peak) {
    float headroom = (peak > 0.0f) ? (1.0f / peak) : 1.0f;
    return lin * (headroom < 1.0f ? headroom : 1.0f);
}
```

**Analysepunkt:** ReplayGain ist der Grund, warum zwei Lieder nicht
unterschiedlich laut sind. Ohne das wirkt jede perfekte Überblendung falsch,
weil das eine Lied lauter ist. Für den Auto-DJ ist das zwingend.

### 7.3 Weiches Limitieren statt hartem Abschneiden

Hartes Clipping (`if x>1: x=1`) klingt kratzig. Ein weicher Begrenzer zieht die
Kurve sanft:

```c
/* Eigener Beispielcode: weiches Begrenzen. */
static inline float soft_clip(float x) {
    /* tanh-artige Kurve, aber billig und ohne Bibliothek */
    if (x <= -1.5f) return -1.0f;
    if (x >=  1.5f) return  1.0f;
    return x - (x * x * x) / 6.75f;   /* sanftere Kennlinie um 0 */
}
```

---

## 8 · Weitere belegte Bausteine

- **Resampler** (`plugin.resampler3`): Nötig, wenn Quellrate und Ausgaberate
  abweichen. Eigener Faden, damit man nichtsample-ratenkonform umrechnet. Beim
  Track-Wechsel wichtig: `flush_resampler_last_frames` leert die letzten Frames.
- **Gapless und Crossfade** (`dsp_postfade_blocks`, `request_fade_impl`): Die
  „postfade"-Blöcke sind zusätzliche Blöcke, in denen der Ton eines Tracks
  ausklingt, während der nächste schon läuft. Genau der Bauplan, den wir für
  unsere Auto-DJ-Übergänge brauchen.
- **Visualisierung** (`AshmemAudioSourceDSP`, `PodPresetFrameVarpool`): Der
  DSP-Thread teilt die Spektraldaten über **Shared Memory (ashmem)** mit der
  Oberfläche. Kein Datenkopieren über Prozessgrenzen, kein Blockieren des
  Audiopfads. Milkdrop-ähnliches Rendering mit Bass/Mitten/Höhen und 32
  Frequenzbändern.

### 8.1 Der Resampler (warum er ein eigener Baustein ist)

Belegt: `plugin.resampler3`, `resampler3.c`, `resampler_internal.c`,
`resampleAndScaleAsNeeded`, `flush_resampler_last_frames`, `Failed to init
resampler`. Der Name `resampler3` sagt: dritte Generation.

Resampling passiert aus zwei Gründen:
1. **Quelle != Gerät** (44,1 kHz Datei, 48 kHz Ausgabe).
2. **Tempostrecken** (der Auto-DJ). Hier ändert sich die Rate ständig.

Ein Resampler ist ein **Polyphasen-Filter** mit einer Verzögerungsleitung. Statt
für jedes Sample teuer zu rechnen, wird ein Satz Teilfilter benutzt und je nach
Bruchteil umgeschaltet.

```c
/* Eigener Beispielcode: lineare Interpolation (billig) als Grundform.
   Echte Qualitaet braucht Polyphasen-FIR, aber die Struktur ist dieselbe. */
typedef struct {
    const float* taps;   /* Filterkoeffizienten */
    int          taps_n;
    double       pos;    /* Position in Eingabe-Samples, gebrochen */
    double       step;   /* Eingabe-Samples pro Ausgabe-Sample */
} Resampler;

static float resample_sample(const Resampler* r, const float* in, int in_len) {
    int   i0 = (int)r->pos;
    int   i1 = i0 + 1;
    float a  = (float)(r->pos - i0);
    if (i1 >= in_len) i1 = in_len - 1;
    return in[i0] * (1.0f - a) + in[i1] * a;   /* linear; fuer Audio zu rau */
}
```

**Analysepunkt:** `flush_resampler_last_frames` ist wichtig. Beim Trackwechsel
hängen noch gefilterte Samples in der Verzögerungsleitung. Wer sie nicht
ausgibt, verliert das Ende des Liedes hörbar.

### 8.2 Gapless (nahtlos) richtig zählen

Nahtlos heißt: kein Loch zwischen zwei Tracks. Das Problem sind **Encoder-Delay**
und **Padding**, die MP3 und AAC jedem Track voran- und anhängen.

```
Frames gesamt = Encoder-Delay (z.B. 576) + echtes Audio + Padding (Rest)
```

Man muss also die ersten `delay` Frames und die letzten `padding` Frames
**verwerfen**, sonst hört man ein kurzes Loch oder ein Stück des Nachbarn.

```c
/* Eigener Beispielcode: Gapless-Buchfuehrung. */
typedef struct {
    int64_t delay_frames;    /* aus dem Container/Tag */
    int64_t padding_frames;
    int64_t produced;        /* insgesamt erzeugt */
    int64_t valid_out;       /* bereits gueltig geliefert */
} Gapless;

static int gapless_valid(const Gapless* g, int64_t frames_now, int64_t* to_skip_first) {
    if (g->produced < g->delay_frames) {
        *to_skip_first = g->delay_frames - g->produced;   /* Anfang verwerfen */
        return 1;
    }
    return 0;
}
```

Belegt im Umfeld: `isGapless` im Track-Status (`f0.I`) und die Decoder-Metadaten.
Ohne diese Buchführung klingt jedes „gapless" Lied mit einer kleinen Lücke.

### 8.3 Crossfade und Postfade

Belegt: `dsp_postfade_blocks`, `request_fade_impl`,
`exec_on_dsp_track_ended_or_faded`. „Postfade" heißt: **hinter** dem eigentlichen
Track werden zusätzliche Blöcke verarbeitet, in denen der alte Ton ausklingt,
während der neue schon läuft. Genau das ist die Bauform für unsere Übergänge.

```c
/* Eigener Beispielcode: Postfade-Bloecke reservieren. */
static int postfade_frames(int frames_per_block, int postfade_blocks) {
    return frames_per_block * postfade_blocks;   /* Zusatzpuffer hinter dem Track */
}
```

### 8.4 Die Visualisierung über Shared Memory

Belegt: `AshmemAudioSource.cpp`, `AshmemAudioSourceDSP.cpp`,
`AshmemAudioSourceContainer.cpp`, `dsp_ashmem msg=%s`, und in Java
`native_set_audio_source_fd_and_serial`.

Statt die Audiodaten zu kopieren, legt der DSP-Thread sie in einen
**Speicherbereich, den beide Prozesse sehen** (`ashmem`). Die Oberfläche liest
direkt daraus. Die `serial`-Nummer (in Java) sorgt dafür, dass immer nur die
aktuellste Fassung gezeichnet wird.

```
DSP-Thread  --schreibt--> [ ashmem: PCM + FFT + Seriennummer ]
                                   ^
                                   |
UI/Renderer  <--liest (ohne Kopie)--+
```

**Analysepunkt:** Der Audiopfad wird **nicht** angehalten und **nicht** kopiert.
Wäre die Visualisierung über einen normalen Aufruf angebunden, könnte ein
langsames Zeichnen den Ton stocken lassen. Das ist die teuerste Fehlerquelle in
Musik-Apps mit Visualizer.

---

## 9 · Zustandsmaschine

Belegte Zustände: `DSP_STATE_PAUSING`, `DSP_STATE_STOPPING`,
`DSP_STATE_ZEROS_TO_AUTO_STOPPED`, `CC_STATE_WAIT_FOR_RESUME`,
`CC_FLAG_PENDING_EOF`.

Lesart: Der DSP hat einen eigenen Zustand, der **nicht** mit dem UI-Zustand
gleichzusetzen ist. „Zeros to auto stopped" heißt: Der DSP schiebt noch kurz
Stille ein, bis wirklich Pause ist. Das verhindert Knacksen beim Pausieren. Der
„pending EOF"-Zustand ist die Wartemarke für das Dateiende. Sauberes
Zustandsmanagement ist einer der Gründe, warum ein guter Player sich „weich"
anfühlt.

### 9.1 Der vollständige Zustandsautomat (Beispielcode)

Belegte Zustände: `DSP_STATE_PAUSING`, `DSP_STATE_STOPPING`,
`DSP_STATE_ZEROS_TO_AUTO_STOPPED`, `CC_STATE_WAIT_FOR_RESUME`,
`CC_FLAG_PENDING_EOF`. Dazu die Java-Seite `f0` mit `AtomicInteger`-Flags.

```c
/* Eigener Beispielcode: Zustandsmaschine mit klaren Uebergaengen. */
typedef enum {
    S_IDLE, S_OPENING, S_PLAYING, S_PAUSING, S_PAUSED,
    S_SEEKING, S_STOPPING, S_ZEROS_TO_STOP, S_EOF
} PlayerState;

/* Was darf wohin? Alles andere ist ein Fehler und wird geloggt. */
static int state_allowed(PlayerState from, PlayerState to) {
    switch (from) {
        case S_IDLE:      return to == S_OPENING;
        case S_OPENING:   return to == S_PLAYING || to == S_STOPPING;
        case S_PLAYING:   return to == S_PAUSING || to == S_SEEKING
                              || to == S_STOPPING || to == S_EOF;
        case S_PAUSING:   return to == S_PAUSED;          /* weich */
        case S_PAUSED:    return to == S_PLAYING || to == S_STOPPING;
        case S_SEEKING:   return to == S_PLAYING;
        case S_STOPPING:  return to == S_ZEROS_TO_STOP;   /* Stille schieben */
        case S_ZEROS_TO_STOP: return to == S_IDLE;
        case S_EOF:       return to == S_OPENING;
    }
    return 0;
}
```

**Analysepunkt:** Der Zwischenschritt `S_PAUSING` und `S_ZEROS_TO_STOP` ist der
Unterschied zwischen „hart aus" und „weich aus". Beim weichen Weg schiebt die
Engine noch kurze Stille nach, damit der letzte Ton ausklingen kann. Ohne das
hört man beim Pausieren ein Knacken.

### 9.2 Warum die Java-Flags als `int`-Bitmaske laufen

Im Track-Status `f0` gibt es `AtomicInteger c0` mit Methoden `A()` (`get & 7`)
und `O(mask, set)`. Das sind **Zustandsmerker** (z. B. „wartet auf Cover",
„wartet auf Wellenform"), die von mehreren Threads gesetzt werden. Eine
Bitmaske plus Compare-and-Swap statt einer Sperre: kein Anhalten, kein Warten.

```java
// Eigener Beispielcode: Merker sperrfrei setzen.
final class Flags {
    private final java.util.concurrent.atomic.AtomicInteger f = new java.util.concurrent.atomic.AtomicInteger();
    static final int NEEDS_COVER = 1, NEEDS_WAVE = 2, NEEDS_SCAN = 4;
    boolean has(int bit) { return (f.get() & bit) != 0; }
    void set(int mask, boolean on) {
        int cur, next;
        do { cur = f.get(); next = on ? (cur | mask) : (cur & ~mask); }
        while (!f.compareAndSet(cur, next));
    }
}
```

---

## 10 · Was wir daraus für „Klangbild" mitnehmen

**Übernehmen (Ideen, nicht Code):**
1. **Zwei Threads** (Decoder und DSP) plus Ausgabe. Das ist die Grundarchitektur.
2. **Plugin-API** mit `PluginContext` als erstem Feld. Decoder, DSP und Ausgabe
   austauschbar.
3. **Lock-freier Ringpuffer** zwischen den Threads. Nie sperren im Audiopfad.
4. **Feste Blockgrößen und Vorallokation.**
5. **Latenz-Verhandlung** mit getrennten Werten für Ton, Präsentation und
   Anzeige.
6. **OEM-Anpassung** pro Hersteller (Samsung, Xiaomi, OnePlus, Oppo, Moto).
7. **DSP in C++**, nicht in Java.
8. **Vorberechnete Wellenform-Buckets** für die Seekbar.
9. **Postfade-Blöcke** als Basis für unsere Übergänge.

**Anders machen (unser eigener Teil):**
- **Gemma-Schicht** (Stimmung, Auswahl): hat Poweramp nicht.
- **Auto-DJ-Planner und Beatmatching**: hat Poweramp nicht.
- **Klang-Vektoren** und lokale Suche: neu.
- **Permissive Bausteine** statt GPL/AGPL aus dem Original.

**Konkreter Ersatz der Bausteine:**

| Aufgabe | Poweramp-Lösung | Unsere Wahl |
|---|---|---|
| Ausgabe | eigene AAudio/OpenSL/AudioTrack-Plugins | **Oboe** (Apache-2.0) |
| Decoding | eigenes ffmpeg (LGPL/GPL) | MediaCodec; FFmpeg nur mit bewusster Lizenz |
| Time-Stretch | Keylock im DSP | **Signalsmith Stretch** (MIT) |
| Resampler | `resampler3` | eigener oder MIT-Baustein |
| DSP/EQ | eigenes C++ | eigener C++-Code |
| Player/Bibliothek | eigener Java-Baum | **Media3** für den normalen Betrieb |
| Analyse | eigen | **librosa offline (ISC)** |

### 10.1 Übernehmen oder selbst bauen (Entscheidungsmatrix)

Nicht alles, was Poweramp tut, lohnt sich für uns. Eine ehrliche Einordnung:

| Baustein | Übernehmen? | Begründung |
|---|---|---|
| Zwei Threads (Decoder/DSP) | **ja** | Grundlage, wenig Aufwand, großer Nutzen |
| Lock-freie Ringpuffer | **ja** | billig zu bauen, verhindert die meisten Fehler |
| Plugin-Muster mit `PluginContext` | **ja** | aber als feste Tabelle, nicht Reflection (22.6) |
| `mmap`-Ringpuffer | **später** | erst wenn malloc messbar stört |
| Resampler selbst bauen | **nein** | zukaufen/kleiner MIT-Baustein, sonst Wochen Arbeit |
| EQ/EQ-Kopfraum | **ja** | überschaubar, Kern des Klangs |
| ReplayGain | **ja** | wenige Zeilen, großer Effekt beim Auto-DJ |
| Gapless-Buchführung | **ja** | sonst Lücken in jedem zweiten Album |
| Wellenform + Anzeige-Muster | **ja** | direkt nachbaubar, klarer Nutzen |
| Skins/Widgetpack | **nein** | nicht unser Produkt |
| Visualizer (Milkdrop) | **nein** | teuer, kein Kern |
| Kryptografie (mbedTLS) | **nein** | nur falls Sync kommt |
| Video/Rendering (EGL/GL) | **nein** | nicht unser Produkt |

**Analysepunkt:** „Alles nachbauen" ist der klassische Anfängerfehler. Die Liste
trennt **Struktur** (übernehmen, weil sie billig ist und Fehler verhindert) von
**Fachbibliotheken** (zukaufen, weil sie Wochen kosten).

### 10.2 Priorisierung nach Aufwand und Risiko

| Priorität | Baustein | Aufwand | Risiko wenn falsch |
|---|---|---|---|
| 1 | Ringpuffer + zwei Threads | klein | sehr hoch (Aussetzer) |
| 2 | EQ + Kopfraum + ReplayGain | mittel | mittel (Klang, Übersteuerung) |
| 3 | Gapless-Buchführung | klein | hoch (Lücken) |
| 4 | Wellenform + Anzeige | mittel | niedrig (Optik) |
| 5 | Übergänge/Auto-DJ | groß | hoch (Kern des Produkts) |
| 6 | KI-Schicht | mittel | mittel |
| 7 | Extraktion/Resampler zukaufen | klein | hoch (Klirren) |

**Analysepunkt:** Punkt 1 und 3 zuerst. Wer mit Übergängen anfängt, hat nie ein
stabiles Fundament.

---

## 11 · Beispielcode: Oboe-Ausgabe mit Latenz-Verhandlung

```cpp
/* Eigener Beispielcode: Ausgabe-Callback auf Oboe. */
#include <oboe/Oboe.h>
#include <atomic>

class Output {
public:
    bool start(int sampleRate, int channels) {
        oboe::AudioStreamBuilder b;
        b.setDirection(oboe::Direction::Output)
         ->setPerformanceMode(oboe::PerformanceMode::LowLatency)
         ->setSharingMode(oboe::SharingMode::Exclusive)
         ->setFormat(oboe::AudioFormat::Float)
         ->setChannelCount(channels)
         ->setSampleRate(sampleRate)
         ->setDataCallback(this);
        if (b.openStream(mStream) != oboe::Result::OK) return false;

        mFramesPerBurst = mStream->getFramesPerBurst();
        mStream->setBufferSizeInFrames(mFramesPerBurst * 2); /* klein, aber stabil */

        /* Latenz abfragen: Ton und Praesentation getrennt speichern. */
        mTonMs   = mStream->calculateLatencyMillis();
        mPresMs  = mStream->getTimestamp(CLOCK_MONOTONIC).isValid()
                 ? mStream->getTimestamp(CLOCK_MONOTONIC).latency
                 : mTonMs;
        return mStream->requestStart() == oboe::Result::OK;
    }

    /* Realtime-Pfad: nur lesen und kopieren. Nichts anderes. */
    oboe::DataCallbackResult onAudioReady(
        oboe::AudioStream*, void* audioData, int32_t numFrames) override {
        float* out = static_cast<float*>(audioData);
        const uint32_t got = rb_read(&mRing, out, numFrames, mChannels);
        if (got < (uint32_t)numFrames) {
            /* Aussetzer: fehlende Frames mit Stille fuellen und zaehlen. */
            for (uint32_t i = got * mChannels;
                 i < (uint32_t)numFrames * mChannels; ++i) out[i] = 0.0f;
            mUnderruns.fetch_add(1, std::memory_order_relaxed);
        }
        return oboe::DataCallbackResult::Continue;
    }

    double tonMs()  const { return mTonMs; }
    double presMs() const { return mPresMs; }
    uint64_t underruns() const { return mUnderruns.load(); }

private:
    oboe::ManagedStream mStream;
    int32_t mFramesPerBurst = 0;
    double mTonMs = 0, mPresMs = 0;
    std::atomic<uint64_t> mUnderruns{0};
    int mChannels = 2;
    RingBuffer mRing;
};
```

**Die drei Performance-Regeln in diesem Code:**
1. Der Callback liest nur (`rb_read`). Kein `malloc`, keine Sperre, kein Log.
2. Der Aussetzer wird **gezählt**, nicht versteckt.
3. Ton-Latenz und Präsentations-Latenz werden getrennt gehalten.

### 11.1 Exclusive, MMAP und Puffergröße prüfen

Die erste Version prüft nicht, **welchen** Modus Oboe bekommen hat. Ein zweiter
Blick lohnt sich, denn davon hängt die Latenz ab.

```cpp
// Eigener Beispielcode: nach dem Oeffnen den echten Modus auslesen.
void logRealMode(const oboe::AudioStream* s) {
    const auto share  = s->getSharingMode();       // Exclusive ist gut
    const auto perf   = s->getPerformanceMode();   // LowLatency ist gut
    const auto burst  = s->getFramesPerBurst();    // klein ist gut
    const auto size   = s->getBufferSizeInFrames();
    const auto cap    = s->getBufferCapacityInFrames();
    // Aussagekraeftig: hat das Geraet unseren Wunsch bekommen?
    if (share != oboe::SharingMode::Exclusive)
        /* Geraet kann es nicht oder ist belegt -> Latenz wird hoeher */ ;
    if (perf != oboe::PerformanceMode::LowLatency)
        /* tiefer Puffer -> erwarte groessere Latenz */ ;
    (void)burst; (void)size; (void)cap;
}
```

### 11.2 Gerätewechsel und Unterbrechung sauber behandeln

```cpp
// Eigener Beispielcode: Oboe-Fehler- und Wechsel-Callbacks.
class Engine : public oboe::AudioStreamErrorCallback,
               public oboe::AudioStreamDataCallback {
public:
    void onErrorAfterClose(oboe::AudioStream* /*stream*/, oboe::Result error) override {
        if (error == oboe::Result::ErrorDisconnected) {
            // Kopfhoerer raus, Bluetooth weg: Ausgabe neu aufbauen.
            mShouldReopen.store(true);
            // NICHT im Callback neu oeffnen, sondern im Besitzer-Thread:
            mReopenRequested.store(true, std::memory_order_release);
        }
    }
    oboe::DataCallbackResult onAudioReady(
        oboe::AudioStream*, void* audioData, int32_t numFrames) override {
        // ... Ringpuffer lesen, Aussetzer zaehlen ...
        return oboe::DataCallbackResult::Continue;
    }
private:
    std::atomic<bool> mShouldReopen{false};
    std::atomic<bool> mReopenRequested{false};
};
```

**Analysepunkt:** Das Neueröffnen **darf nicht** im Callback passieren (dort
darf nichts blockieren). Man merkt es nur vor und macht es im Besitzer-Thread.
Genau dieses Muster hat Poweramp mit `CC_STATE_WAIT_FOR_RESUME`.

### 11.3 Die Puffergröße aus dem Burst ableiten

```cpp
// Eigener Softwarecode: Puffergröße = Vielfaches des Burst.
int pickBufferFrames(const oboe::AudioStream* s, int multipliers) {
    const int burst = s->getFramesPerBurst();      // z.B. 192
    int want = burst * multipliers;                // z.B. 2 -> 384 Frames
    const int cap = s->getBufferCapacityInFrames();
    if (want > cap) want = cap;
    return want;
}
```

Bei 48 kHz sind 192 Frames 4 ms, 384 Frames 8 ms. Das ist die Größenordnung, in
der sich „niedrige Latenz" abspielt. Alles über etwa 40 ms fällt bei Übergängen
hörbar auf.

---

## 12 · Beispielcode: die Kotlin/JNI-Brücke

```kotlin
// Eigener Beispielcode: Interface zwischen Kotlin und der nativen Engine.
class AudioEngine private constructor() {

    external fun nativeStart(sampleRate: Int, channels: Int): Long
    external fun nativeStop(handle: Long)
    external fun nativeSeek(handle: Long, framePosition: Long): Int  // serial?
    external fun nativeSetPlaybackRate(handle: Long, rate: Float)
    external fun nativeGetUnderruns(handle: Long): Long
    external fun nativeLatencyMs(handle: Long): Double
    external fun nativeSetEqBand(handle: Long, band: Int, freq: Int, q: Float, gainDb: Float)

    companion object {
        init { System.loadLibrary("klangbild-core") }
    }
}
```

Hinweise:
- **Handle statt globaler Zustand.** Die native Seite gibt ein Handle (Zeiger als
  Long) zurück. So sind mehrere Engines möglich und kein globaler Zustand nötig.
- **`nativeSeek` liefert eine Seriennummer** zurück, damit die Kotlin-Seite
  veraltete Antworten verwerfen kann (siehe Abschnitt 3).
- **Keine Objekte im Hot-Path.** Die Kotlin-Seite ruft `nativeStart`/`nativeStop`
  selten, nicht pro Block.

### 12.1 `@FastNative` richtig einsetzen

Im Binary steht `@dalvik.annotation.optimization.FastNative` an den heißen
Methoden (Pipeline2 sechs Stellen, Coefs vier). Diese Marke ist ein **Vertrag**:
Die native Funktion darf **nicht** blockieren, keine Ausnahme in Java auslösen
und keine großen Objekte anlegen. Wer sie falsch setzt, baut sich seltene
Abstürze. Richtig gesetzt ist sie deutlich billiger als ein normaler JNI-Aufruf.

```java
// Eigener Beispielcode: der Vertrag hinter @FastNative.
public final class Engine {
    static { System.loadLibrary("klangbild-core"); }

    /** Kurz, nicht blockierend, keine Allokation. Handle-basiert. */
    @dalvik.annotation.optimization.FastNative
    private static native int nGetState(long handle);

    @dalvik.annotation.optimization.FastNative
    private static native int nGetPositionMs(long handle);

    // NICHT @FastNative: diese duerfen Zeit kosten / Allokation anlegen.
    private static native long nCreate();
    private static native void nRelease(long handle);
}
```

### 12.2 Handle statt Weltzustand (Lebenszyklus)

```kotlin
// Eigener Beispielcode: sauberer Lebenszyklus ueber ein Handle.
class EngineHandle : AutoCloseable {
    private var handle: Long = 0L

    fun start(sampleRate: Int, channels: Int) {
        require(handle == 0L) { "engine already started" }
        handle = Engine.nCreate()
        check(handle != 0L) { "native create failed" }
        check(Engine.nStart(handle, sampleRate, channels) == 0) { "start failed" }
    }

    fun state(): Int {
        check(handle != 0L) { "engine not started" }
        return Engine.nGetState(handle)
    }

    override fun close() {
        val h = handle
        if (h != 0L) { handle = 0L; Engine.nRelease(h) }
    }
}
```

**Analysepunkt:** Zwei Regeln sind hier sichtbar. Erstens **Handle statt
globalem Zustand** (mehrere Engines möglich, kein Singleton). Zweitens
**Zustandsprüfung in Kotlin**, damit ein falscher Aufruf sofort auffällt und
nicht nativ abstürzt.

### 12.3 Thread-Zugehörigkeit dokumentieren

Nicht jede native Methode darf von jedem Thread gerufen werden. Das gehört in
einen Kommentar, sonst ruft sie irgendwann der falsche Thread.

```kotlin
// Nur vom Steuer-Thread aufrufen (nicht vom Audio-Callback):
private external fun nSeek(handle: Long, frame: Long, serial: Int): Int

// Aus jedem Thread erlaubt, weil sperrfrei:
@dalvik.annotation.optimization.FastNative
private external fun nGetPositionMs(handle: Long): Long
```

---

## 13 · Speicher- und Threaddiagramm

```
 Threads                      Speicher
 ------------------------------------------------
 [Decoder-Thread]  ----schreibt----> [Ringpuffer A]  (vorallokiert, lock-frei)
                                             |
 [DSP-Thread]      <---liest----------+
      |                                       |
      |---schreibt---> [Ringpuffer B] (vorallokiert, lock-frei)
                                    |
 [Oboe-Callback]   <---liest--------+
      |
      |---schreibt (ohne Kopie)---> [Shared Memory] ---> [UI: Wellenform/Spektrum]

 Regeln:
 - Jeder Puffer hat genau EINEN Schreiber und EINEN Leser.
 - Jeder Puffer ist Zweierpotenz-gross, Index laeuft im Kreis.
 - Kein malloc/mutex/log nach dem Start.
 - Latenz: Ton-, Praesentations- und Anzeige-Latenz getrennt.
```

### 13.1 Puffergrößen ausrechnen (mit Zahlen)

Die Puffer sind nicht willkürlich. Sie folgen aus der Abtastrate, der
Blockgröße und der gewünschten Reserve.

```
 Frames pro Block   = Abtastrate * Block_ms / 1000
 Puffer A (Decoder) = Frames pro Block * dsp_bufs
 Puffer B (DSP)     = Frames pro Block * output_bufs
 Vorlauf (Decoder)  = Frames pro Block * dsp_prefetch_bufs
 Postfade           = Frames pro Block * dsp_postfade_blocks
```

Beispiel bei 48 kHz, 10 ms Block:

| Größe | Formel | Frames | Millisekunden |
|---|---|---|---|
| Frames pro Block | 48000 * 10 / 1000 | 480 | 10,0 |
| Puffer A (4 Bufer) | 480 * 4 | 1.920 | 40,0 |
| Puffer B (4 Bufer) | 480 * 4 | 1.920 | 40,0 |
| Decoder-Vorlauf (8) | 480 * 8 | 3.840 | 80,0 |
| Postfade (2) | 480 * 2 | 960 | 20,0 |

```c
/* Eigener Beispielcode: Puffergroessen ausrechnen. */
typedef struct {
    int sample_rate;
    int block_ms;
    int dsp_bufs, output_bufs, prefetch_bufs, postfade_blocks;
} BufferPlan;

static int frames_per_block(int sample_rate, int block_ms) {
    return sample_rate * block_ms / 1000;
}

static void plan_frames(BufferPlan p, int out[5]) {
    int fpb = frames_per_block(p.sample_rate, p.block_ms);
    out[0] = fpb;                        /* Block */
    out[1] = fpb * p.dsp_bufs;           /* Puffer A */
    out[2] = fpb * p.output_bufs;        /* Puffer B */
    out[3] = fpb * p.prefetch_bufs;      /* Vorlauf */
    out[4] = fpb * p.postfade_blocks;    /* Postfade */
}
```

**Analysepunkt:** Diese Tabelle ist der Kern der Latenz-Entscheidung. Für Musik
darf der Block groß sein (20 bis 40 ms). Für den Auto-DJ muss er klein sein
(5 bis 10 ms), damit die Übergänge sitzen. Man kann zwei Pläne haben und je nach
Modus umschalten.

### 13.2 Speicherbedarf

Frames mal Kanäle mal 4 Byte (Float). 3.840 Frames Stereo sind 30.720 Byte, also
etwa 30 KB. Auch mit mehreren Puffern bleibt der Bedarf im niedrigen
Megabyte-Bereich. Deshalb sind die 5,4 MiB `.bss` in der Poweramp-Bibliothek
plausibel: Sie enthalten neben den Audiopuffern auch Decoder-Status und
FFT-Tabellen.

---

## 14 · Checkliste für unsere eigene Engine

- [ ] Zwei native Threads: Decoder und DSP, plus Ausgabe-Callback.
- [ ] Plugin-Interface mit `PluginContext` als erstem Feld.
- [ ] Lock-freie SPSC-Ringpuffer, Zweierpotenz, ein Schreiber, ein Leser.
- [ ] Feste Blockgrößen, alles vorallokiert, kein `malloc` im Pfad.
- [ ] DSP in C++ mit 32-Bit-Float und NEON.
- [ ] Oboe-Ausgabe mit LowLatency und Exclusive, MMAP wenn verfügbar.
- [ ] Latenz getrennt messen: Ton, Präsentation, Anzeige.
- [ ] Underruns zählen und anzeigen.
- [ ] EQ-Koeffizienten nur bei Änderung berechnen, nicht pro Block.
- [ ] Kopfraum/DVC gegen Übersteuerung.
- [ ] Seek mit Seriennummern.
- [ ] Zustandsmaschine mit „Zeros to stopped" gegen Knacksen.
- [ ] Postfade-Blöcke für Überblenden und Crossfade.
- [ ] OEM-Tabelle (Samsung, Xiaomi, OnePlus, Oppo, Moto) für Puffergrößen.
- [ ] Wellenform-Buckets vorberechnen für die Seekbar.
- [ ] Spektraldaten über Shared Memory an die UI, nicht über Kopien.
- [ ] Übergangs-Engine: Beat-Raster, Phasen-Stups, Bass-Tausch, Loop, Cue-Punkte.
- [ ] Uebergaenge nur auf Taktgrenzen entscheiden, nie mittendrin.
- [ ] KI (EmbeddingGemma 2 + Gemma 4) strikt ausserhalb des Audiopfads.
- [ ] Vektoren an den Datei-Hash gebunden, Analyse genau einmal.
- [ ] KI waehlt nur aus dem lokalen Index, erfindet keine Songs.
- [ ] Wellenform nativ rechnen, als BLOB in der DB cachen, nie im Audiopfad.
- [ ] UI und Engine ueber StateBus und MsgBus entkoppeln.
- [ ] Animation bedarfsgesteuert (Dirty-Flags), im Stillstand vollstaendig ruhen.
- [ ] Fortschritt per nanoTime interpolieren, alle ~75 Frames abgleichen.
- [ ] Schwelle fuer den Abgleich von der Tracklaenge abhaengig machen.
- [ ] Eigene, zwischengespeicherte Bitmaps statt Neuzeichnen pro Frame.
- [ ] Metadaten und Ordner nativ einlesen, nicht in Java (10.000 Dateien).
- [ ] Album-Art ueber Datei-Deskriptor zweistufig laden (Masse, dann Bild).
- [ ] Lautstaerke trennen: System, DVC, Bluetooth-Absolute-Volume.
- [ ] Bluetooth-Codec lesen und die Ausgabe-Abtastrate danach waehlen.
- [ ] Einstellungen als JSON mit stabilem Schluessel und Abhaengigkeiten.

### 14.1 Abnahmekriterien je Checklistenpunkt (messbar)

Eine Checkliste ohne Zahlen ist Wunschdenken. Hier die messbaren Schwellen:

| Punkt | Kriterium | Schwelle |
|---|---|---|
| Kein malloc im Pfad | Zahl der Allokationen im Callback | 0 |
| Ringpuffer | Aussetzer pro Stunde bei Volllast | unter 1 |
| Thread-Priorität | Audio-Thread-Prio | `THREAD_PRIORITY_AUDIO` |
| Vorlauf | Verbleibende Reserve im Puffer | nie unter 1 Block |
| Latenz | Gesamtlatenz im Musikmodus | unter 60 ms |
| Latenz | Gesamtlatenz im Auto-DJ-Modus | unter 30 ms |
| EQ-Umschaltung | hörbares Knacken beim Ziehen | keines |
| Gapless | Lücke zwischen zwei Tracks | 0 Frames |
| Wellenform | erste Anzeige nach Trackwechsel | unter 100 ms (Ersatzwelle) |
| Anzeige | Frame-Callback im Stillstand | gestoppt (0 Prozent CPU) |

**Analysepunkt:** Jeder Punkt hat eine Zahl. Ohne diese Zahlen ist „fertig" eine
Meinung, und bei Streit gibt es keine Fakten.

---

## 15 · Die Übergangs- und Beatmatching-Engine (unser eigener Teil)

Hier endet Poweramp und unser Produkt beginnt. Poweramp hat Gapless und
Crossfade; ein vollwertiges Beatmatching mit Beat-Raster, Phasenausrichtung,
Looping und Effekt-Übergängen ist unsere eigene Arbeit. Der Vorteil: Der
Postfade-Mechanismus aus Abschnitt 4 und 8 liefert dafür schon die passende
Bauform.

### 15.1 Das Beat-Raster

Grundlage ist pro Track ein Raster: Tempo, erster Beat, Taktlänge. Alles andere
rechnet darauf.

```cpp
/* Eigener Beispielcode: Beat-Raster und Position darin. */
#include <math.h>
#include <stdint.h>

typedef struct {
    double  bpm;              /* Tempo, aus der Analyse */
    int64_t first_beat_smp;   /* Sample-Position des ersten Beats */
    int     beats_per_bar;    /* meist 4 */
    int64_t sample_rate;
} BeatGrid;

/* Wie viele Beats liegen an Sample-Position pos? */
static inline double grid_beats_at(const BeatGrid* g, int64_t pos) {
    return (double)(pos - g->first_beat_smp) / (double)g->sample_rate * (g->bpm / 60.0);
}

/* Umgekehrt: Sample-Position zu einem Beat. */
static inline int64_t grid_sample_at(const BeatGrid* g, double beat) {
    return g->first_beat_smp +
           (int64_t)llround(beat * 60.0 / g->bpm * (double)g->sample_rate);
}

/* Naechste Taktgrenze ab Position: achte, sechzehnte, was man braucht. */
static inline int64_t grid_next_phrase(const BeatGrid* g, int64_t pos, int bars) {
    const double beats = grid_beats_at(g, pos);
    const int beat_unit = bars * g->beats_per_bar;
    const double next = ceil(beats / beat_unit) * beat_unit;
    return grid_sample_at(g, next);
}
```

Wichtig: Das Raster stammt aus der Voranalyse (Abschnitt 8c unseres
Produktdokuments) und wird **nicht** im Audiopfad berechnet.

### 15.2 Tempo angleichen (mit Halb- und Doppelzeit)

Der Rate-Faktor ist das Verhältnis der Tempi, aber auf den Bereich um 1 gebracht.
Denn 90 BPM und 180 BPM passen zusammen, ohne dass man das Doppelte spielt.

```cpp
/* Eigener Beispielcode: sichere Tempowahl nahe 1.0. */
static inline double sync_rate(const BeatGrid* a, const BeatGrid* b) {
    double r = a->bpm / b->bpm;
    while (r > 1.5)  r *= 0.5;    /* Halbzeit */
    while (r < 0.667) r *= 2.0;   /* Doppelzeit */
    return r;                      /* zwischen 0.667 und 1.5 */
}
```

Mit Signalsmith Stretch wird dieser Faktor tonhöhenerhaltend angewendet. Der
gute Bereich liegt laut Signalsmith bei etwa 0,75 bis 1,5, genau das deckt die
Funktion ab.

### 15.3 Phasenausrichtung (der schwierigste Teil)

Zwei Tracks können dasselbe Tempo haben und trotzdem versetzt laufen. Man muss
die **Phasenlage** der Beats angleichen. Weil ein Sprung hörbar wäre, nutzt man
einen kurzen **Rate-Stups** (Pitch-Bend) statt eines Sprungs.

```cpp
/* Eigener Beispielcode: Beat-Phase messen und weich ausrichten. */
typedef struct {
    double  bend_rate;      /* zusaetzlicher Faktor, z.B. 1.002 */
    int64_t bend_until_smp; /* bis wann der Stups gilt */
} PhaseAlign;

/* Phase in Beats, auf 0..1 normiert. */
static inline double phase001(const BeatGrid* g, int64_t pos) {
    double b = grid_beats_at(g, pos);
    b -= floor(b);
    return b;
}

/* Wie weit muss B gezogen werden? Ergebnis in Beats, >0 heisst B zu spaet. */
static inline double phase_error_beats(const BeatGrid* a, int64_t posA,
                                       const BeatGrid* b, int64_t posB) {
    double d = phase001(b, posB) - phase001(a, posA);
    if (d > 0.5)  d -= 1.0;   /* kuerzester Weg */
    if (d < -0.5) d += 1.0;
    return d;
}

/* Weicher Stups: Rate voruebergehend leicht veraendern statt zu springen. */
static inline void phase_nudge(PhaseAlign* pa, double error_beats,
                               int64_t now_smp, int64_t window_smp) {
    const double beats_per_sec = 2.0;  /* aus dem Songtempo; hier Beispiel */
    pa->bend_rate = 1.0 - (error_beats / beats_per_sec) / (window_smp / 48000.0);
    pa->bend_until_smp = now_smp + window_smp;
}
```

Lesart: Ist B um 0,02 Beats zu spät, wird B für ein kurzes Fenster minimal
schneller laufen, bis der Versatz weg ist. Danach wieder exakt 1,0. So bleibt
das Tempo gleich und nur die Phase wird korrigiert.

### 15.4 Übergangstypen

```cpp
/* Eigener Beispielcode: die Übergangsarten. */
typedef enum {
    TR_XFADE,        /* linear ueberblenden */
    TR_BASS_SWAP,    /* Bass tauschen, Hoehen mischen */
    TR_FILTER_SWEEP, /* Hochpass auf A, Tiefpass auf B */
    TR_ECHO_OUT,     /* A laeuft mit Echo aus */
    TR_CUT           /* harter Schnitt auf der Taktgrenze */
} TransitionType;

typedef struct {
    TransitionType type;
    int64_t start_a_smp;   /* wann A zu blenden beginnt */
    int     bars;          /* Laenge in Takten */
    double  rate_b;        /* Tempofaktor fuer B */
    int64_t cue_b_smp;     /* wo B einsteigt */
    int     swap_bar;      /* ab welchem Takt der Bass umschaltet */
} Transition;
```

Empfehlung für die Reihenfolge des Bauens (aus unserem Produktdokument):
Version 1 nur `TR_XFADE`, Version 2 `TR_BASS_SWAP` und `TR_FILTER_SWEEP`,
Version 3 `TR_ECHO_OUT` und Struktur-Marker.

### 15.5 Bass-Tausch als Automatisierung

Der Bass-Tausch verhindert, dass zwei Bässe sich überlagern. Man teilt in Bänder
und fährt Hüllkurven.

```cpp
/* Eigener Beispielcode: Bass-Tausch über Huellkurven. */
typedef struct {
    float low_a;   /* Bassanteil von A, 1.0 -> 0.0 */
    float low_b;   /* Bassanteil von B, 0.0 -> 1.0 */
} SwapEnv;

/* progress 0..1, swap_at: ab welchem Anteil umgeschaltet wird. */
static inline SwapEnv swap_step(float progress, float swap_at) {
    SwapEnv e;
    if (progress < swap_at) {
        e.low_b = 0.0f;                 /* B noch ohne Bass */
        e.low_a = 1.0f - progress;      /* A baut Bass ab */
    } else {
        float t = (progress - swap_at) / (1.0f - swap_at);
        e.low_a = 0.0f;                 /* A ohne Bass */
        e.low_b = t * t;                /* B baut Bass auf, weich */
    }
    return e;
}
```

Die Bänder selbst trennt man mit zwei Crossovers (Tiefpass plus Hochpass,
z.B. Linkwitz-Riley). Der Bass-Bereich liegt typisch unter etwa 150 Hz, die
Höhen darüber.

### 15.6 Looping und Roll

```cpp
/* Eigener Beispielcode: Loop und Roll auf Beatgrenzen. */
typedef struct {
    int64_t in_smp;
    int64_t out_smp;
    int     active;
    int     one_shot;   /* 1 = Roll: genau einmal, dann aus */
} Loop;

/* Loop einschalten. Laenge in Beats, Ein stets auf der Taktgrenze. */
static inline void loop_set(Loop* lp, const BeatGrid* g,
                            int64_t at_smp, int beats, int one_shot) {
    const double start = floor(grid_beats_at(g, at_smp));
    lp->in_smp   = grid_sample_at(g, start);
    lp->out_smp  = grid_sample_at(g, start + beats);
    lp->one_shot = one_shot;
    lp->active   = 1;
}

/* Position an den Loop anpassen.
   Rueckgabe 1, wenn der Loop (Roll) gerade verlassen wurde, sonst 0. */
static inline int loop_advance(Loop* lp, int64_t* pos) {
    if (!lp->active) return 0;
    if (*pos < lp->out_smp) return 0;   /* noch innerhalb */
    *pos = lp->in_smp;                  /* zurueck an den Anfang */
    if (lp->one_shot) {                 /* Roll: einmal, dann raus */
        lp->active = 0;
        return 1;
    }
    return 0;
}
```

Beim Lesen der Position im Ausgabe-Callback muss `loop_advance` vor dem Lesen
aufgerufen werden, damit der Sprung auf der Beatgrenze sitzt und hörbar nahtlos
bleibt (der Ringpuffer liefert die bereits gespielten Samples weiter).

### 15.7 Cue-Punkte und Struktur

Cue-Punkte (Intro, Drop, Outro) kommen aus der Voranalyse (Energie- und
Neuheits-Kurve, siehe Abschnitt 8f unseres Produktdokuments). Der Übergang wird
dann nicht nur auf die Taktgrenze gelegt, sondern auf **musikalisch sinnvolle**
Punkte: A blendet nach dem Drop aus, B steigt vor seinem Drop ein.

### 15.8 Der Übergangs-Ablauf als Zustandsmaschine

```cpp
typedef enum {
    TR_IDLE,
    TR_PREROLL,      /* B wird geladen, Raster gesetzt, Cue gesetzt */
    TR_SYNCING,      /* Tempo und Phase angleichen */
    TR_MIXING,       /* Uebergang laeuft, Huellkurven aktiv */
    TR_DONE          /* B allein, A entladen */
} TransitionState;
```

Regel: Jeder Zustandswechsel wird auf einer **Taktgrenze** entschieden, nicht
mittendrin. Das ist der Unterschied zwischen „geplant" und „geklungen".

### 15.9 Performance in der Übergangs-Engine

- Das Raster und die Cue-Punkte sind **vorberechnet**. Im Echtzeitpfad wird nur
  gerechnet, was sich pro Block ändert: ein paar Hüllkurven-Werte und die
  Filterkoeffizienten.
- Filterkoeffizienten nur dann neu rechnen, wenn sich der Sweep-Wert wirklich
  ändert, nicht pro Sample.
- Beide Decks laufen durch **denselben** Ausgabe-Callback (ein Oboe-Stream), der
  beide Ringpuffer mischt. So gibt es keine zwei Uhren und keinen Versatz.
- Das Time-Stretch ist der teuerste Teil. Deshalb möglichst Songs mit ähnlichem
  Tempo wählen (der Planer soll das belohnen), dann bleibt der Dehnungsfaktor
  klein.

### 15.10 Der Misch-Callback für zwei Decks (das Herzstück)

Beide Decks laufen durch **einen** Ausgabe-Callback und werden dort summiert.
So gibt es nur eine Uhr und keinen Versatz.

```c
/* Eigener Beispielcode: zwei Decks in einem Callback mischen. */
typedef struct {
    RingBuffer* ring;      /* PCM dieses Decks */
    float       gain;      /* Huellkurve (Fade) */
    float       low_gain;  /* Bass-Anteil (fuer Bass-Tausch) */
    int         channels;
} Deck;

static void read_deck(Deck* d, float* dst, int frames) {
    uint32_t got = rb_read(d->ring, dst, frames, d->channels);
    for (uint32_t i = got * d->channels;
         i < (uint32_t)frames * d->channels; ++i) dst[i] = 0.0f;  /* Stille */
}

/* out += A * gainA + B * gainB, sample-genau. */
void mix_decks(Deck* a, Deck* b, float* out, int frames, int channels) {
    static float tmpA[8192], tmpB[8192];       /* vorallokiert, kein malloc */
    read_deck(a, tmpA, frames);
    read_deck(b, tmpB, frames);
    for (int i = 0; i < frames * channels; ++i) {
        out[i] = tmpA[i] * a->gain + tmpB[i] * b->gain;
    }
}
```

**Analysepunkt:** Die Huellkurven (`gain`) werden **pro Block** fortgeschrieben,
nicht pro Sample neu berechnet. Das ist derselbe Gedanke wie beim EQ: teure
Berechnung selten, billige Anwendung oft.

### 15.11 Der Übergangs-Planer (Beat-Mathematik)

```c
/* Eigener Beispielcode: wann beginnt der Uebergang, wie lange? */
typedef struct {
    int64_t start_a_smp;    /* A beginnt zu blenden */
    int64_t end_a_smp;      /* A ist aus */
    int64_t cue_b_smp;      /* B steigt ein */
    int     bars;
    int     beats_per_bar;
} TransitionPlan;

TransitionPlan plan_transition(const BeatGrid* a, int64_t pos_a, int bars) {
    TransitionPlan p;
    p.beats_per_bar = a->beats_per_bar;
    p.bars = bars;
    /* Start auf der naechsten 8er- oder 16er-Taktgrenze. */
    p.start_a_smp = grid_next_phrase(a, pos_a, bars);
    p.end_a_smp   = grid_sample_at(a,
                        grid_beats_at(a, p.start_a_smp) + bars * a->beats_per_bar);
    p.cue_b_smp   = 0;   /* wird gesetzt, sobald B geladen ist */
    return p;
}
```

**Analysepunkt:** Der Übergang beginnt **immer** auf einer Taktgrenze, nie
mittendrin. Das ist der Unterschied zwischen „geplant" und „geklungen". Beim
Bauen zuerst `plan_transition` schreiben und testen, dann die Huellkurven.

### 15.12 Zeit zum Überblenden (Hüllkurven-Formen)

```c
/* Eigener Beispielcode: Huellkurven fuer den Fade. */
typedef enum { FADE_LINEAR, FADE_EQUAL_POWER, FADE_CUT } FadeShape;

static float fade_gain(FadeShape s, float t) {   /* t = 0..1 */
    switch (s) {
        case FADE_LINEAR:      return t;
        case FADE_EQUAL_POWER: return sinf(t * 1.5707963f);  /* cos/sin-Paerchen */
        case FADE_CUT:         return t < 0.5f ? 1.0f : 0.0f;
    }
    return t;
}
```

**Analysepunkt:** Lineares Überblenden klingt in der Mitte leiser („Loch"), weil
zwei Signale sich nicht in der Leistung addieren. **Equal Power** ist die richtige
Wahl für Musik. Das ist ein Detail, das über „klingt gut" oder „klingt falsch"
entscheidet.

---

## 16 · Die Gemma-Anbindung auf dem Gerät

Zwei Modelle, zwei Aufgaben:

- **EmbeddingGemma 2** macht aus einem Track einen Vektor (das Klangbild). Damit
  suchen und auswählen.
- **Gemma 4** versteht Wünsche und erklärt Entscheidungen. Es rechnet nicht.

### 16.1 Die Laufzeit

- **Einbetten:** MediaPipe Tasks **Universal Embedder** (oder LiteRT direkt).
- **Suchen:** MediaPipe Tasks **Semantic Retriever** (on-device ANN), alternativ
  `sqlite-vec` oder USearch.
- **Sprachmodell:** **LiteRT-LM** mit Gemma 4 (E2B/E4B fürs Handy).

Lizenzhinweis: LiteRT und LiteRT-LM sind Apache-2.0. Die **Gewichte** von Gemma 4
stehen unter der Gemma-Lizenz (kommerziell erlaubt, mit Auflagen). Die
EmbeddingGemma-2-Lizenz vor dem Start klären.

**Ehrlicher Hinweis:** Die genauen Klassennamen der MediaPipe Tasks API ändern
sich zwischen Versionen. Im Code unten sind sie hinter einer eigenen Fassade
gekapselt, damit ein API-Wechsel nur eine Datei betrifft. Genau so sollte man es
bauen.

### 16.2 Der Ablauf in der Bibliotheksanalyse

```
 fuer jeden Track:
   1. Tempo/Beat/Key aus dem Signal (Abschnitt 8c)  -> features-Tabelle
   2. EmbeddingGemma 2 (Audio) -> 768d Vektor, auf 256d gekuerzt
   3. Vektor in den lokalen Index
   4. Gemma 4: Stimmungs-Label aus den Metadaten + Vektor
```

Alle Schritte laufen **einmal** und hängen an einem Datei-Fingerabdruck. Zur
Laufzeit wird nur gesucht.

### 16.3 Beispielcode: Einbetten (Kotlin, gekapselt)

```kotlin
// Eigener Beispielcode: Fassade um den MediaPipe Universal Embedder.
// Läuft NICHT im Audio-Callback, sondern in einem Hintergrund-Thread.
class TrackEmbedder {

    private val embedder: UniversalEmbedder = UniversalEmbedder.createFromOptions(
        context,
        UniversalEmbedderOptions.builder()
            .setModelPath("models/embeddinggemma2_text_image_audio.task")
            .setTruncateDim(256)          // Matrjoschka gegen Speicher
            .setMaxSeqLen(MODEL_MAX_TOKENS)
            .build()
    )

    // Audio eines Tracks -> ein Vektor. "Document"-Rolle beim Indizieren.
    fun embedTrack(samples: FloatArray, sampleRate: Int): FloatArray {
        val input = AudioInput.create(samples, sampleRate)
        val result = embedder.embed(input, Role.DOCUMENT)
        return normalizeL2(result.embedding())   // fuer Cosine-Aehnlichkeit
    }

    // Nutzerfrage -> Vektor. "SearchQuery"-Rolle beim Suchen.
    fun embedQuery(text: String): FloatArray {
        val result = embedder.embed(text, Role.SEARCH_QUERY)
        return normalizeL2(result.embedding())
    }

    private fun normalizeL2(v: FloatArray): FloatArray {
        var s = 0f; for (x in v) s += x * x
        val n = kotlin.math.sqrt(s).coerceAtLeast(1e-8f)
        for (i in v.indices) v[i] /= n
        return v
    }
}
```

Wichtig: Die **Rolle** muss passen. Laut Google werden Abfrage und Dokument mit
verschiedenen Rollen eingebettet (`SearchQuery` gegen `Document`). Wer beide
gleich behandelt, verliert Genauigkeit.

### 16.4 Beispielcode: Suche über den lokalen Index

```kotlin
// Eigener Beispielcode: on-device Suche ueber EmbeddingGemma 2.
class TrackIndex(private val retriever: SemanticRetriever) {

    fun add(trackId: Long, vector: FloatArray) {
        retriever.add(EmbeddingVector.create(vector), trackId.toString())
    }

    fun findSimilar(queryVec: FloatArray, k: Int): List<Long> =
        retriever.search(EmbeddingVector.create(queryVec), k)
            .map { it.metadata().toLong() }
}
```

Beispiel: „etwas Ruhiges fürs Einschlafen" -> `embedQuery` -> `findSimilar` ->
Liste von Track-Ids, die klanglich passen. Kein Netz, kein Server.

### 16.5 Beispielcode: die Auto-DJ-Bewertung (das eigentliche Auswahl-Hirn)

Das ist der Kern. Vier Teile werden zu einer Punktzahl verrechnet: Harmonie,
Tempo, Klangbild, Energie. Gemma liefert nur den Klangbild-Teil.

```kotlin
// Eigener Beispielcode: Kandidatenbewertung fuer den Auto-DJ.
object AutoDj {

    // Camelot-Rad: "8A" -> Zahl 8, Buchstabe A. Abstand moeglichst klein.
    fun harmonicDistance(a: String, b: String): Int {
        val (na, la) = parse(a)   // z.B. 8, 'A'
        val (nb, lb) = parse(b)
        val sameLetter = if (la == lb) 0 else 1
        val ring = minOf((na - nb + 12) % 12, (nb - na + 12) % 12)
        return ring + sameLetter      // 0 = perfekt
    }

    // Tempopenalty: nahe 1.0 und saubere Halb/Dopel sind gut.
    fun tempoPenalty(aBpm: Double, bBpm: Double): Double {
        var r = aBpm / bBpm
        while (r > 1.5) r /= 2.0
        while (r < 0.667) r *= 2.0
        return kotlin.math.abs(kotlin.math.ln(r))   // 0 bei Gleichheit
    }

    fun cosine(a: FloatArray, b: FloatArray): Double {
        var s = 0.0
        for (i in a.indices) s += a[i] * b[i]     // beide L2-normalisiert
        return (s + 1.0) / 2.0                     // auf 0..1
    }

    // Gesamtpunktzahl. Gewichte sind Produktentscheidungen.
    fun score(current: Track, cand: Track, targetEnergy: Double): Double {
        val harmony = 1.0 - (harmonicDistance(current.key, cand.key) / 7.0)
        val tempo   = 1.0 - (tempoPenalty(current.bpm, cand.bpm) / 0.7)
        val vibe    = cosine(current.embedding, cand.embedding)
        val energy  = 1.0 - kotlin.math.abs(cand.energy - targetEnergy)
        return 0.35 * vibe + 0.25 * harmony + 0.20 * tempo + 0.20 * energy
    }

    data class Track(
        val id: Long, val key: String, val bpm: Double,
        val energy: Double, val embedding: FloatArray
    )
    private fun parse(camelot: String): Pair<Int, Char> =
        Pair(camelot.dropLast(1).toInt(), camelot.last())
}
```

Lesart: `score` ist die Auswahl nach Klang **und** DJ-Regeln zusammen. Die
klassischen Auto-DJs nutzen nur Harmonie und Tempo. Der neue Teil ist `vibe`
(aus EmbeddingGemma 2) und `energy` (aus der Energiekurve).

### 16.6 Beispielcode: Gemma 4 für Wunsch und Erklärung (RAG mit Quellen)

```kotlin
// Eigener Beispielcode: LiteRT-LM mit Gemma 4, Antwort nur aus eigenen Daten.
class SetAssistant(private val llm: LiteRtLm, private val index: TrackIndex,
                   private val embedder: TrackEmbedder) {

    /** "Zwei Stunden, entspannt zu euphorisch" -> Reihenfolge. */
    fun planSet(request: String, library: List<AutoDj.Track>): List<Long> {
        val q = embedder.embedQuery(request)
        val seeds = index.findSimilar(q, k = 20)      // Vektoren schlagen vor
        // Die KI waehlt und ordnet, aber NUR aus echten Kandidaten (keine Halluzination).
        val prompt = buildString {
            appendLine("Du bist ein DJ. Ordne aus NUR diesen Tracks eine Reise.")
            appendLine("Wunsch: $request")
            appendLine("Kandidaten:")
            seeds.forEach { appendLine("- id=${it.id} bpm=... key=...") }
            appendLine("Antworte nur mit der Reihenfolge der ids, mit Begruendung je Schritt.")
        }
        return parseOrder(llm.generate(prompt, maxTokens = 400))
    }

    /** Erklaert eine automatische Wahl in einem Satz. */
    fun explain(from: AutoDj.Track, to: AutoDj.Track): String =
        llm.generate(
            "Sag in einem Satz, warum Track ${to.id} gut nach ${from.id} passt " +
            "(Tempo ${from.bpm} -> ${to.bpm}, Tonart ${from.key} -> ${to.key}).",
            maxTokens = 80
        )
}
```

Zwei Regeln, die hier sichtbar sind und wichtig sind:

1. **Die KI erfindet keine Songs.** Die Kandidaten kommen aus dem Vektorindex,
   die KI darf nur daraus wählen. Das verhindert genau die Halluzination, die in
   Nutzerbewertungen ein häufiger Kritikpunkt ist.
2. **Gemma 4 rechnet keine Zahlen.** Tempo, Tonart und Punktzahl liefert die
   Logik. Das Modell formuliert nur und wählt aus.

### 16.7 Performance und Threading

- **KI nie im Audiopfad.** Einbetten und Generieren laufen in Hintergrund-Threads
  mit niedriger Priorität. Der Audio-Callback kennt sie nicht.
- **Analyse einmal, nicht dauernd.** Vektoren werden beim Bibliotheks-Scan
  berechnet und an den Datei-Fingerabdruck gebunden. Danach ist Suchen billig.
- **Modell im Speicher halten versus laden.** Bei wenig RAM das Modell nach
  längerer Pause entladen, sonst dauert die nächste Nutzung zu lang.
- **Längere Läufe nur am Ladegerät**, mit Fortschrittsanzeige und fortsetzbar.

### 16.8 Datenschutz

Alles lokal. Kein Konto, kein Server, kein Upload. Das ist bei „mein
Hörgeschmack" und „meine Musik" das eigentliche Verkaufsargument und fällt als
Nebeneffekt der Architektur heraus.

### 16.9 Das lokale Datenmodell (SQLite-Schema)

Damit die Suche schnell ist, braucht es feste Tabellen und Indizes.

```sql
-- Eigener Beispielcode: lokales Schema fuer die KI-Suche.
CREATE TABLE track (
  id          INTEGER PRIMARY KEY,
  path        TEXT NOT NULL,
  hash        TEXT NOT NULL,          -- Datei-Fingerabdruck
  title       TEXT, artist TEXT, album TEXT,
  duration_ms INTEGER
);

CREATE TABLE feature (
  track_id     INTEGER PRIMARY KEY REFERENCES track(id),
  bpm          REAL,
  key_camelot  TEXT,                  -- z.B. "8A"
  loudness_lufs REAL,
  energy_curve BLOB,                  -- kleines Array, komprimiert
  beat_grid    BLOB,
  sections     BLOB                   -- Intro/Drop/Break
);

CREATE TABLE embedding (
  track_id  INTEGER REFERENCES track(id),
  dims      INTEGER,                  -- 768 oder gekuerzt 256
  vector    BLOB,                     -- float32-Array
  PRIMARY KEY (track_id)
);

CREATE INDEX idx_feature_key ON feature(key_camelot);
CREATE INDEX idx_feature_bpm ON feature(bpm);
```

**Analysepunkt:** Der Vektor liegt als BLOB, nicht als Spalte pro Dimension. Bei
256 Dimensionen sind das 1.024 Byte pro Track. 10.000 Tracks sind 10 MB, gut
tragbar.

### 16.10 Prompt-Vorlagen für Gemma 4

```text
# Eigener Beispieltext (Prompt-Vorlage), keine Fremdquelle.

System:
Du bist ein DJ-Assistent. Du waehlst NUR aus der gegebenen Kandidatenliste.
Du erfindest keine Titel. Du nennst keine Zahlen, die nicht in den Daten stehen.

Aufgabe:
Der Nutzer wuenscht: "{wunsch}"     # z.B. "zwei Stunden, entspannt zu euphorisch"
Kandidaten (id, bpm, key, energie):
{kandidaten}
Antworte mit einer Reihenfolge von ids und je einem kurzen Grund.
```

**Analysepunkt:** Zwei Verbote im Systemprompt („erfindet keine Titel", „keine
Zahlen erfinden") beseitigen genau die zwei häufigsten KI-Fehler in Bewertungen:
Halluzination und falsche Angaben.

### 16.11 Gewichtung und Prüfrahmen

```python
# Eigener Beispielcode: Gewichte justieren und pruefen.
def score(vibe, harmony, tempo, energy, w=(0.35, 0.25, 0.20, 0.20)):
    return w[0]*vibe + w[1]*harmony + w[2]*tempo + w[3]*energy

def evaluate(planner, cases):
    """cases: Liste (aktueller_track, gewuenschte_reihenfolge_ids)."""
    hits = 0
    for cur, want in cases:
        got = planner.next_ids(cur, k=len(want))
        hits += len(set(got) & set(want)) / len(want)
    return hits / len(cases)     # Trefferquote 0..1
```

**Analysepunkt:** Ohne eine solche Trefferquote ist die Auswahl nicht prüfbar.
Vor dem Ausliefern wird mit etwa 50 handgebauten Fällen gemessen.

---

## 17 · Die Wellenform-Erzeugung (Waveform)

Die Wellenform in der Seekbar ist bei Poweramp kein Zierrat, sondern ein
eigenes kleines Subsystem. Sie wird **einmal** berechnet, in der Datenbank
gespeichert und danach nur noch gezeichnet.

### 17.1 Die Kette

```
 Datei
   |
   v
 [ ScanDecode.native_scan ]   (C++, dekodiert die Datei, rechnet Amplituden)
   |  liefert float[]
   v
 [ d0 ]  (Worker auf einem HandlerThread)
   |  wandelt float[] -> bytes, schreibt BLOB
   v
 [ Datenbank: Spalte "wave" in folder_files ]   (Schluessel: folder_files._id)
   |
   v
 [ f0.r ]   (float[] im Track-Status)
   |
   v
 [ Waveseek / i5 ]  (zeichnet die Balken)
```

### 17.2 Belegte Details

- **`ScanDecode`** (Paket `audioplayer/decoder`) ist der native Scanner:
  `native_create`, `native_release`, und
  `native_scan(long handle, String path, int a, int b, int c, byte[] extras)
  -> float[]`.
  Das heißt: Die Amplituden werden in C++ aus der dekodierten Datei gewonnen,
  nicht in Java.
- **`d0`** (Paket `audioplayer/player`) ist der Worker. Er läuft auf einem
  **HandlerThread** (Hintergrund) und legt die Arbeit an den **Anfang** der
  Warteschlange (`sendMessageAtFrontOfQueue`), damit die Wellenform früh
  entsteht.
- Der Worker **recycelt seine Puffer**: Ist das Ergebnis genau **100 Werte**
  lang, wird ein bereits vorhandener Puffer von **400 Bytes** (100 mal 4 Byte)
  wiederverwendet, sonst einmalig neu angelegt. Das ist typische
  Audiopfad-Disziplin, nur eben in Java.
- Gespeichert wird als **BLOB** in der Spalte **`wave`** der Tabelle
  `folder_files`, geschlüsselt über `folder_files._id` (die Datei-Id). Kein
  zweiter Datei-Zugriff, keine Extra-Datei.
- Erzeugt wird nur, wenn noch keine Form da ist (`f0.r == null`) und der
  Dateityp geeignet ist.
- Im Track-Status **`f0`** liegt die Form in **`r`** (`float[]`). `f0` hat
  außerdem `s` (Abtastrate), `t` (Bit), `u` (Kanäle), `v` (Dauer ms),
  `w` (Bitrate), `E` (Codec), `I` (Gapless), `L` (ReplayGain-Typ).
- In der Seekbar gibt es zwei Formen: **`j`** und **`k`** in der Basisklasse
  `i5` (zum Beispiel für Normal- und Auswahl-Darstellung).

### 17.3 Der Fallback (wichtig für die Optik)

Hat ein Track noch keine echte Wellenform, ist die Leiste **nicht leer**.
`Waveseek` erzeugt eine **Ersatzwelle** mit einer Sinusformel über die Anzahl
der Balken. Faktoren im Code: Amplitude 1,5 beziehungsweise 3,0, Skalierung
0,25 beziehungsweise 0,33, Minimum 0,01, Maximum 1,0. Das Ergebnis wird
geklont und als Ersatzform markiert (`g0`).

Der Zweck: Der Nutzer sieht sofort etwas Sinnvolles, und sobald die echte Form
aus der Datenbank kommt, wird sie ersetzt. Kein leerer Balken, kein Sprung.

### 17.4 Wie viele Balken?

Die Anzahl kommt aus dem XML der Ansicht (`K`, mindestens 1). `Waveseek` füllt
genau diese Anzahl: entweder mit der echten Form oder mit der Ersatzwelle.
Die Breite wird auf die Anzahl verteilt, ein Balken ist eine Position im Array.

### 17.5 Beispielcode: Wellenform in Buckets rechnen (C++)

```cpp
/* Eigener Beispielcode: Amplituden-Spitzen je Bucket, 0..1. */
#include <stdint.h>
#include <math.h>

void compute_wave_buckets(const float* pcm, int64_t frames, int channels,
                          int buckets, float* out) {
    if (buckets <= 0 || frames <= 0) return;
    const int64_t per = frames / buckets;

    for (int b = 0; b < buckets; ++b) {
        const int64_t start = (int64_t)b * per;
        const int64_t end   = (b == buckets - 1) ? frames : start + per;

        float peak = 0.0f;
        for (int64_t i = start; i < end; ++i) {
            for (int c = 0; c < channels; ++c) {
                const float v = pcm[i * channels + c];
                const float a = v < 0.0f ? -v : v;   /* Betrag */
                if (a > peak) peak = a;
            }
        }
        out[b] = peak;   /* fertig normiert, wenn PCM bei +/-1 liegt */
    }
}
```

### 17.6 Beispielcode: Ergebnis speichern, Puffer recyceln (Kotlin)

```kotlin
// Eigener Beispielcode: Wellenform als BLOB ablegen, ohne Allokation im Normalfall.
class WaveStore(private val db: FileDao) {
    private var cachedBytes: ByteBuffer? = null
    private var cachedFloats: FloatBuffer? = null

    fun store(fileId: Long, wave: FloatArray) {
        val bytes: ByteBuffer
        val floats: FloatBuffer

        if (wave.size == 100) {                       // haeufigster Fall
            var bb = cachedBytes
            if (bb == null) {
                bb = ByteBuffer.allocate(400)          // 100 * 4 Bytes
                cachedBytes = bb
                cachedFloats = bb.asFloatBuffer()
            }
            bytes = bb
            floats = cachedFloats!!
            floats.position(0)
            bytes.position(0)
        } else {
            bytes = ByteBuffer.allocate(wave.size * 4)  // Sonderfall: neu
            floats = bytes.asFloatBuffer()
        }

        floats.put(wave)
        db.updateFileWave(fileId, ContentValues().apply { put("wave", bytes.array()) })
    }
}
```

Und das Zeichnen ist dann trivial: für jeden Balken `i` wird die Höhe aus dem
Array gelesen. Beschneiden auf die Breite, ein `RectF`, ein `drawRoundRect`, und
die bereits berechneten Werte als "gespielt"/"ungespielt" eingefärbt.

### 17.7 Spitze oder Effektivwert (die Wahl der Kennzahl)

Eine Wellenform kann aus **Spitzen** (Peak) oder aus **Effektivwerten** (RMS)
gebaut werden. Beides hat einen Zweck:

| Kennzahl | Sieht aus wie | Geeignet für |
|---|---|---|
| **Peak** | zackig, laut, klar | Drop erkennen, Ausschläge sehen |
| **RMS** | ruhiger, gleichmäßig | Lautheit über Zeit, Stimmungsverlauf |
| **Beides** | genaue Form | beste Optik |

**Analysepunkt:** Poweramp speichert einen `float[]`. Ein besonders guter Weg ist,
**zwei Werte pro Bucket** abzulegen (Ober- und Unterkante aus Peak). Dann sieht
die Welle wie eine echte Wellenform aus und nicht wie ein Balkendiagramm.

```c
/* Eigener Beispielcode: Peak und RMS je Bucket. */
#include <math.h>
typedef struct { float peak; float rms; } Bucket;

void compute_buckets(const float* pcm, int64_t frames, int channels,
                     int buckets, Bucket* out) {
    const int64_t per = frames / buckets;
    for (int b = 0; b < buckets; ++b) {
        const int64_t start = (int64_t)b * per;
        const int64_t end   = (b == buckets - 1) ? frames : start + per;
        float peak = 0.0f; double sum_sq = 0.0; int64_t n = 0;
        for (int64_t i = start; i < end; ++i) {
            for (int c = 0; c < channels; ++c) {
                const float v = pcm[i * channels + c];
                const float a = fabsf(v);
                if (a > peak) peak = a;
                sum_sq += (double)v * v; ++n;
            }
        }
        out[b].peak = peak;
        out[b].rms  = n ? (float)sqrt(sum_sq / n) : 0.0f;
    }
}
```

### 17.8 Speicherformat der Wellenform

Belegter Weg: `float[]` wird zu Bytes und als BLOB gespeichert. Eine kompaktere
Variante wäre `uint8` (0 bis 255), wenn Genauigkeit nicht zählt.

```c
/* Eigener Beispielcode: kompakte Speicherung als uint8. */
#include <stdint.h>
static void wave_to_u8(const float* in, int n, uint8_t* out) {
    for (int i = 0; i < n; ++i) {
        float v = in[i] < 0 ? 0 : (in[i] > 1 ? 1 : in[i]);
        out[i] = (uint8_t)(v * 255.0f + 0.5f);
    }
}
```

**Analysepunkt:** `float` sind 4 Byte pro Wert, `uint8` nur 1 Byte. Bei 500
Balken und 10.000 Tracks spart das 15 MB. Für eine Anzeige reicht die
8-Bit-Genauigkeit völlig.

---

## 18 · Die UI-Architektur (Bus-System und eigene Views)

Poweramp benutzt **kein Jetpack Compose**. Die Oberfläche besteht aus
**eigenen `ViewGroup`-Klassen**, und die Verbindung zur Engine läuft über
**zwei Nachrichten-Busse**. Das ist der zweite große Architekturgedanke neben
der Audio-Engine.

### 18.1 Die zwei Busse

**`StateBus`** (Lesen von Zustand, nach Zahlen-Id):

```java
boolean getBooleanState(int id);
float   getFloatState(int id);
int     getIntState(int id);
long    getLongState(int id);
<T> T   getObjectState(int id);
String  getStringState(int id);
MsgBus  getStateMsgBus();
```

**`MsgBus`** (Melden und Abonnieren):

```java
void         post(int id, int a, int b, Object obj);
void         mo1675(Object sender, int id, int a, int b, Object obj);
MsgBus       subscribe(MsgBusSubscriber s);
MsgBus       unsubscribe(MsgBusSubscriber s);
int          getId();
```

Abonnenten bekommen Meldungen über
`onBusMsg(MsgBus bus, int id, int a, int b, Object obj)`.

Belegte Ids sind Ressourcen-Ids, zum Beispiel:
- `2131558562` = aktueller Track-Status (`f0`)
- `2131558570` = aktuelle Abspielposition in Millisekunden
- `2131558451`, `2131558452`, `2131558749` = weitere Busse/States

### 18.2 Warum das gut ist

- Die **Engine kennt die UI nicht** und umgekehrt. Der Player-Service pflegt den
  Zustand, die UI liest ihn. Wer eine neue Anzeige baut, muss die Engine nicht
  anfassen.
- Die Ids sind stabil, also überleben Ansichten Umbauten.
- Der Audiopfad wird **nie** von der UI blockiert.

### 18.3 Beispielcode: ein Mini-StateBus (Kotlin)

```kotlin
// Eigener Beispielcode: dasselbe Muster in klein.
interface StateBus {
    fun int(id: Int): Int
    fun float(id: Int): Float
    fun bool(id: Int): Boolean
    fun obj(id: Int): Any?
}

interface MsgBus {
    fun subscribe(s: Subscriber)
    fun unsubscribe(s: Subscriber)
    fun post(id: Int, a: Int = 0, b: Int = 0, obj: Any? = null)
}

interface Subscriber {
    fun onMsg(bus: MsgBus, id: Int, a: Int, b: Int, obj: Any?)
}

/** Ids an einer Stelle buendeln, damit sie stabil bleiben. */
object Ui {
    const val TRACK_STATE = 1001
    const val POSITION_MS = 1002
    const val PLAYING     = 1003
}
```

### 18.4 Die View-Schicht

- Basis: **`widget/base/i5`** ist eine abstrakte `ViewGroup` und die Basis aller
  Seek-Ansichten. Sie hält `Paint`-Objekte, mehrere **zwischengespeicherte
  `Bitmap`** (`G`, `I`, `J`, `L`), Rechtecke (`Rect`, `RectF`) und die
  Wellenform-Arrays `j` und `k`. Gezeichnet wird selbst in `onDraw`, nichts wird
  pro Frame neu erzeugt.
- **`widget/player`** enthält 139 Klasse-Dateien: eigene Regler
  (`LinearKnob`, `RoundKnob`, `DSPRoundKnobLayout`, `DSPToneRoundKnobLayout`),
  die EQ-Kurve (`FrequencyResponseScroller`), `Seek`, `Waveseek`,
  `ColorCircleSelector`, `SleepTimerBehavior`, `PlayPauseButton`,
  `NavbarExtension`, `MilkWidget` und mehr.
- **`FastLayout` / `SceneFastLayout`** sind eigene Layout-Engines, die schneller
  aufblasen als der Standard. `FastLayout` ist inzwischen als veraltet markiert.
- **`widgetpackcommon`** liefert ein gemeinsames Flag-Modell für Widgets und
  Skins, belegte Flags unter anderem: `FLAG_AA`, `FLAG_AA_SHADOW`, `FLAG_FLAT`,
  `FLAG_FONT_BOLD`, `FLAG_FONT_ITALIC`, `FLAG_META`, `FLAG_META_BG`,
  `FLAG_NO_TITLE`, `FLAG_NO_OTHER_TEXT`, `FLAG_NO_FIXED_SIZE`.
- Es gibt ein **Skin-System** (`SkinInfo`, `SkinMsg`, `SkinOption`,
  `SkinPageOptions`, `SkinSeekbarOption`, `SkinCategoryOptions`).

Kurz: Alles ist handgezeichnet und zwischengespeichert. Deshalb sieht Poweramp
auf alten Geräten noch flüssig aus.

### 18.5 Der Bus über Threads (Sicherheit)

Ein Bus, der Zustand aus dem Engine-Thread bekommt und an den UI-Thread liefert,
muss threadsicher sein. Die Regel: **schreiben darf jeder, gelesen wird nur im
UI-Thread.** Nachrichten werden über einen `Handler` des UI-Threads zugestellt.

```kotlin
// Eigener Beispielcode: threadsicherer Mini-Bus.
class SafeBus(private val uiHandler: android.os.Handler) {
    interface Sub { fun onMsg(id: Int, a: Int, b: Int, obj: Any?) }
    private val subs = java.util.concurrent.CopyOnWriteArrayList<Sub>()

    fun subscribe(s: Sub) { subs.add(s) }
    fun unsubscribe(s: Sub) { subs.remove(s) }

    /** Aus beliebigem Thread aufrufbar. Zustellung immer im UI-Thread. */
    fun post(id: Int, a: Int = 0, b: Int = 0, obj: Any? = null) {
        uiHandler.post { for (s in subs) s.onMsg(id, a, b, obj) }
    }
}
```

**Analysepunkt:** `CopyOnWriteArrayList` ist hier richtig, weil fast nur gelesen
wird (viele Abonnenten, wenige An-/Abmeldungen). Wer stattdessen eine normale
Liste unter einem Lock nutzt, riskiert ein gleichzeitiges Verändern während des
Durchlaufens.

### 18.6 Das Id-Schema stabil halten

Belegte Ids sind Ressourcen-Ids (`2131558562` = Track, `2131558570` = Position).
Ein eigenes Schema ist lesbarer und bleibt stabil, auch wenn Ressourcen sich
verschieben.

```kotlin
// Eigener Beispielcode: Ids als Konstanten, nicht als Ressourcen.
object BusId {
    const val TRACK_STATE = 1001
    const val POSITION_MS = 1002
    const val PLAYING     = 1003
    const val SCAN_PROGRESS = 1004
    const val DECK_A_BPM  = 1005
    const val DECK_B_BPM  = 1006
    const val TRANSITION_LEFT_MS = 1007
}
```

**Analysepunkt:** Für den Auto-DJ brauchen wir eigene Ids (Decks, Restzeit bis
zum Übergang). Weil das Schema stabil ist, kann jede Ansicht dazukommen, ohne
dass die Engine etwas ändern muss.

---

## 19 · Bedienung und Animation (warum es flüssig wirkt)

Das schönste Detail im ganzen Programm steckt in der Fortschritts-Anzeige.
Sie ist **bedarfsgesteuert** und **interpoliert**.

### 19.1 Der Fortschrittsmotor `q1`

`q1` ist die Klasse hinter `Seek` und `Waveseek`. Sie implementiert
`android.view.Choreographer.FrameCallback`, also den Bildtakt des Systems.

**Bedarfsgesteuert über eine Bitmaske.** Es gibt zwei Bitmuster:
- `H` = aktuell gesetzte Gründe für ein Neuzeichnen (`dirty flags`)
- `K` = die Menge aller Gründe (4095, oder 3839 wenn ein Zustand fehlt)

- `m2021(flag)` setzt ein Bit. Ist danach **alles** gesetzt (`H == K`), wird der
  Frame-Callback **gestartet**.
- `m2023(flag)` löscht ein Bit. Ist danach **nichts** mehr übrig, wird der
  Frame-Callback **gestoppt**.

Ergebnis: Die Animation läuft nur, wenn wirklich etwas zu aktualisieren ist. Im
Stillstand kostet sie **nichts**. Das ist der Unterschied zwischen einer
flüssigen App und einer, die den Akku leert.

### 19.2 Interpolation mit `nanoTime`

Statt jeden Frame die Engine zu fragen (teuer), rechnet die Anzeige selbst
weiter:
- Beim Trackwechsel wird die Dauer gelesen und
  `perNanosekunde = 1 / (dauerMs * 1_000_000)` berechnet.
- Pro Frame: `fortschritt += (jetzt - letzteZeit) * perNanosekunde`.
- Die Uhr ist `System.nanoTime()`.

So läuft der Balken mit 60 Bildern pro Sekunde weich, obwohl die Engine nur
selten echte Werte liefert.

### 19.3 Die Rücksynchronisation

Reine Interpolation driftet. Deshalb wird regelmäßig neu abgeglichen:
- **Alle 75 Frames** (bei 60 fps etwa 1,25 Sekunden) wird die echte Position aus
  dem StateBus gelesen und gesetzt.
- Zusätzlich, wenn die Abweichung eine **Schwelle** überschreitet.

Die Schwelle hängt von der Länge ab:
- Tracks **ab 60 Sekunden**: Schwelle **0,02** (2 Prozent).
- Kürzere Tracks: Schwelle **0,075** (7,5 Prozent).

Das ist durchdacht: 2 Prozent eines langen Tracks sind viele Sekunden, 7,5
Prozent eines kurzen Tracks sind immer noch wenig Zeit. So wird weder zu oft
noch zu sichtbar korrigiert.

### 19.4 Beispielcode: bedarfsgesteuerter Fortschrittsmotor (Kotlin)

```kotlin
// Eigener Beispielcode: dasselbe Muster, kompakt.
class ProgressMotor(
    private val choreographer: Choreographer,
    private val state: StateBus,
    private val onProgress: (Float) -> Unit
) : Choreographer.FrameCallback {

    private var running = false
    private var lastNanos = 0L
    private var progress = 0.0          // 0..1
    private var perNano = 0.0           // Fortschritt pro Nanosekunde
    private var durationMs = 0
    private var threshold = 0.02
    private var framesSinceSync = 0

    /** Bei Trackwechsel aufrufen. */
    fun setDuration(ms: Int) {
        durationMs = ms.coerceAtLeast(1)
        perNano = 1.0 / (durationMs * 1_000_000.0)
        threshold = if (ms >= 60_000) 0.02 else 0.075
        framesSinceSync = 0
        progress = realProgress()
        onProgress(progress.toFloat())
    }

    fun start() {
        if (running) return
        running = true; lastNanos = 0L
        choreographer.postFrameCallback(this)
    }

    fun stop() {
        if (!running) return
        running = false
        choreographer.removeFrameCallback(this)
    }

    override fun doFrame(frameTimeNanos: Long) {
        if (!running) return
        choreographer.postFrameCallback(this)          // naechsten Frame anfordern

        if (lastNanos == 0L) { lastNanos = frameTimeNanos; return }

        if (++framesSinceSync >= 75) {                 // regelmaessig abgleichen
            framesSinceSync = 0
            val real = realProgress()
            if (kotlin.math.abs(real - progress) >= threshold) progress = real
        } else {                                       // sonst selbst weiterrechnen
            progress += (frameTimeNanos - lastNanos) * perNano
        }

        lastNanos = frameTimeNanos
        onProgress(progress.toFloat())
    }

    private fun realProgress(): Double =
        state.int(Ui.POSITION_MS).coerceAtLeast(0) / durationMs.toDouble()
}
```

In der echten View hängt `start()`/`stop()` an den Dirty-Flags und an
Sichtbarkeit (`onVisibilityChanged`, `onWindowVisibilityChanged`,
`onDetachedFromWindow`). Eine unsichtbare Leiste animiert nicht.

### 19.5 Die Bedienwege

Poweramp deckt alle Wege ab, die Android bietet, belegt durch die Klassen:
- **Player-Service** (`PlayerService`), **Track-Session**
  (`PSTrackSession`), Steuerung über `MediaSession`.
- **Medientasten** (`PSMediaButtonReceiver`), **Headset**
  (`HeadsetMicroService`, `ManifestHeadsetPlugReceiver`).
- **Benachrichtigung** (`NotificationBuilderC0396`, `DebugNotificationWrapper`).
- **Lockscreen** (Hilfsklassen im Widget-Paket).
- **Bluetooth** (`PaBluetoothCodecConfig`, `BTReceiver`) und
  **Lautstärke/Routing** (Pakete `dvc`, `absvol`, `router`).
- **Widgets** (`MilkWidget`) und **Kachel** (`TileService` für die
  Schnelleinstellungen).
- **Externe API** (`PowerampAPIReceiver`, `PowerampAPIActivity`).

Dazu die Regler-Bedienung: `LinearKnob`, `RoundKnob`, `FrequencyResponseScroller`
(EQ-Kurve ziehen), `ColorCircleSelector`. Alles eigenhändig gezeichnet und
angefasst, ohne Standard-Widgets.

### 19.6 Die Visualisierung

Der Visualizer (Milkdrop) arbeitet mit den belegten Strukturen
`PodPresetInputs` (Zeit, fps, frame, progress, bass, mid, treb, ...) und
`PodFrameData` (`pcmdata_L`, `pcmdata_R`, `fftdata`, `realFFT`, `q[32]`). Die
Spektraldaten kommen über **Shared Memory** (`ashmem`,
`native_set_audio_source_fd_and_serial`) aus dem Audiobereich in die
Zeichen-Engine. Der Audiopfad wird dabei nicht kopiert und nicht blockiert.

### 19.7 Die Dirty-Flags im Detail

Der Fortschrittsmotor hält zwei Bitmuster: `H` (gesetzt) und `K` (alle). Jede
Ansicht kann ihre eigenen Gründe beisteuern. Eine belegte Zuordnung:

| Flag | Grund für ein Neuzeichnen |
|---|---|
| 1 | sichtbar / angehängt |
| 2 | im Vordergrund (Fenster sichtbar) |
| 4 | laufender Titel vorhanden |
| 8 | laufende Animation (z. B. Titel-Scrollen) |
| 16 | Track gewechselt |
| 32 | Abspielzustand gewechselt |
| 64 | Nutzer zieht gerade (Scrub) |
| 128 | Position wurde gesetzt |

**Analysepunkt:** Der Callback läuft nur, wenn **alle** gesetzten Gründe noch
wichtig sind (`H == K`). Wird ein Grund gelöscht (`m2023`), kann der Callback
sofort stoppen. Weil das Anzeigen von Text (nicht nur Position) auch Arbeit ist,
zählt es als eigener Grund.

### 19.8 Lebenszyklus (wann läuft die Animation)

```kotlin
// Eigener Beispielcode: Animation an Sichtbarkeit und Flags koppeln.
class WaveSeekView : View {
    private var running = false
    private fun update() {
        val shouldRun = isAttachedToWindow && isShown && windowVisibility == VISIBLE
        if (shouldRun && !running) start()
        if (!shouldRun && running) stop()
    }
    override fun onAttachedToWindow() { super.onAttachedToWindow(); update() }
    override fun onDetachedFromWindow() { stop(); super.onDetachedFromWindow() }
    override fun onVisibilityChanged(changed: View, visibility: Int) {
        super.onVisibilityChanged(changed, visibility); update()
    }
    override fun onWindowVisibilityChanged(v: Int) {
        super.onWindowVisibilityChanged(v); update()
    }
}
```

**Analysepunkt:** Genau das machen `Waveseek` und `q1` (`onAttachedToWindow`,
`onDetachedFromWindow`, `onVisibilityChanged`, `onWindowVisibilityChanged`).
Ohne diese vier Haken läuft die Animation weiter, wenn die Ansicht längst weg
ist, und frisst Akku.

---

## 20 · Audio-Routing, Lautstärke und Bluetooth

Poweramp behandelt Lautstärke, Ausgabewege und Bluetooth nicht als Kleinigkeit,
sondern als vier eigene Unterpakete unter `audioplayer/player`:

| Paket | Bedeutung | Belegte Klassen (Auswahl) |
|---|---|---|
| `dvc` | **Direct Volume Control**, Lautstärke im DSP statt im Systemmixer | `C0378`, `C0380`, `C0382`, `C0383`, `AbstractC0379`, `AbstractC0381` |
| `absvol` | **Absolute Volume** für Bluetooth (AVRCP), Lautstärketaste steuert das Headset | `C0372`, `C0374`, `C0375`, `InterfaceC0373`, `InterfaceC0376` |
| `router` | **Audio-Routing**: welcher Ausgabeweg, welches Gerät | `C0385`, `C0387`, `C0388`, `AbstractC0386` |
| `bt` | **Bluetooth** (Empfänger und Helfer) | `BTReceiver`, `C0377` |

Dazu im Spieler-Paket: `HeadsetMicroService`, `ManifestHeadsetPlugReceiver`,
`PSMediaButtonReceiver` (Medientasten), `PowerampAPIReceiver` (externe API).

### 20.1 Warum drei verschiedene Lautstärkewege

- **System-Lautstärke:** die normale Android-Lautstärke. Einfach, aber sie
  arbeitet nach dem DSP und kann die Qualität drücken.
- **DVC (Direct Volume Control):** die Lautstärke wird **im eigenen DSP**
  geregelt, in hoher Auflösung. Das klingt besser, verlangt aber eigenen
  Kopfraum (siehe Abschnitt 7, `equ5_float_set_no_dvc_headroom_mb`).
- **Absolute Volume (Bluetooth):** Bei Bluetooth-Kopfhörern kann die Lautstärke
  entweder am Handy oder am Kopfhörer geregelt werden. „Absolute Volume" heißt,
  die Handy-Taste ändert direkt die Lautstärke im Headset über AVRCP. Das muss
  man erkennen und passend ansteuern.

Drei Wege, die sich gegenseitig ausschließen und vom Gerät und der Verbindung
abhängen. Deshalb eigene Pakete mit eigenen Zuständen.

### 20.2 Bluetooth-Codec-Erkennung (belegt in `PaBluetoothCodecConfig`)

Poweramp liest den Bluetooth-Zustand aus und macht daraus lesbare Werte. Die
Zuordnung ist vollständig belegt:

| Codec-Nummer | Name |
|---|---|
| 0 | SBC |
| 1 | AAC |
| 2 | aptX |
| 3 | aptX HD |
| 4 | LDAC |
| 5 | SSC (Samsung) oder SSHD oder LHDC/HWA (herstellerabhängig) |
| 6 | SSC oder aptX TWS+ |
| 1000000 | LHDC/HWA |

Abtastraten kommen als **Bitmaske**: 1 = 44100, 2 = 48000, 4 = 88200,
8 = 96000, 16 = 176400, 32 = 192000. Bits je Sample: 1 = 16, 2 = 24, 4 = 32.
Kanäle: 1 = MONO, 2 = STEREO. Dazu `codecSpecific1..4` als Langwerte.

Ab Android 15 (SDK 35) liest die App den `BluetoothCodecConfig` direkt und holt
sich sogar `getExtendedCodecType().getCodecName()`. Für ältere Versionen wird der
Zustand über ein `Parcel` zerlegt und der Codec-Name aus der Textdarstellung
herausgeschnitten (der Codec-String beginnt mit `{mCodecConfig:{codecName:`).

Hersteller-Sonderfälle stecken in `com.maxmpz.utils.vendor.B` (Flags für
Samsung SSC, LHDC/HWA). Ohne diese Erkennung würde die App bei manchen Handys
den falschen Codec-Namen anzeigen.

### 20.3 Was das für uns bedeutet

- **Lautstärke ist nicht „ein Regler".** Wir brauchen mindestens System und DVC
  getrennt, sonst klingen Auto-DJ-Übergänge unterschiedlich laut.
- **Bluetooth-Codec bestimmt die Ausgabe-Abtastrate.** Wer „Hi-Res" verspricht,
  muss den Codec kennen. Sonst verspricht er etwas, das die Verbindung gar nicht
  liefert.
- **Routing ist ein eigener Zustand.** Steckt der Kopfhörer, wechselt die
  Ausgabe, und der Übergang muss nahtlos bleiben.

### 20.4 Beispielcode: Codec und Zieldatenrate (Kotlin)

```kotlin
// Eigener Beispielcode: vereinfachte Codec-Auswertung.
data class CodecInfo(
    val name: String,          // "LDAC"
    val sampleRates: Int,      // Bitmaske
    val bits: Int,             // Bitmaske
    val channels: Int          // 1=Mono, 2=Stereo
)

fun preferredSampleRate(codec: CodecInfo, sourceRate: Int): Int {
    val candidates = listOf(192000, 176400, 96000, 88200, 48000, 44100)
    val bit = mapOf(192000 to 32, 176400 to 16, 96000 to 8, 88200 to 4,
                    48000 to 2, 44100 to 1)
    // Nimm die hoechste Rate, die der Codec unterstuetzt, sonst die Quellrate.
    return candidates.firstOrNull { (codec.sampleRates and (bit[it] ?: 0)) != 0 }
        ?: sourceRate
}
```

### 20.5 Das Lautstärke-Modell (Index zu Dezibel)

Android gibt die Lautstärke als **Index** (kleine ganze Zahl). Der DSP rechnet
in **Dezibel** oder linear. Dazwischen braucht man eine Umrechnung, sonst springt
die Lautstärke am Anfang („die ersten 3 Stufen lauter als der Rest").

```kotlin
// Eigener Beispielcode: Index -> Dezibel (Geraetekurve).
fun indexToDb(index: Int, maxIndex: Int, minDb: Float = -60f): Float {
    if (maxIndex <= 0) return 0f
    val frac = index.toFloat() / maxIndex            // 0..1
    // einfache, glatte Kurve statt linear-in-Index
    return minDb + (0f - minDb) * (frac * frac)
}
```

**Analysepunkt:** DVC (Direct Volume Control) regelt in feinen Schritten im DSP.
Dann muss die System-Lautstärke auf ihrem Maximum bleiben und der DSP macht die
Feinheit. Sonst überlagern sich zwei Lautstärkeregelungen und drücken die
Qualität.

### 20.6 Absolute Volume über AVRCP

Bluetooth-Kopfhörer melden per AVRCP, ob sie die Lautstärke selbst regeln
(„Absolute Volume"). Ist das an, hört die App die Lautstärketasten als
Änderungen für das **Headset**, nicht für das Handy.

```kotlin
// Eigener Beispielcode: Absolute-Volume-Fall unterscheiden.
fun onVolumeKey(headphonesAbsVol: Boolean, delta: Int, current: Int): Int {
    return if (headphonesAbsVol) current      // Handy unveraendert lassen
           else (current + delta).coerceIn(0, 100)
}
```

**Analysepunkt:** Wer diesen Fall nicht behandelt, hat später eine doppelte
Lautstärkeanpassung (Handy und Kopfhörer gleichzeitig) und Nutzer melden
„Lautstärke springt wild".

---

## 21 · Der Scanner und die Tag-Pipeline

Das Einlesen der Bibliothek ist ein eigenes Subsystem mit nativem Kern. Es lohnt
sich, weil hier Leistung und Speicher entschieden werden.

### 21.1 Die Datenstruktur `TagAndMeta`

Ein Objekt trägt **alle** Metadaten eines Tracks. Belegte Felder:

- **Text:** `title`, `artist`, `albumArtist`, `album`, `genre`, `comment`,
  `lyrics`, `composer`, `cueSheet`, `provider`, `codec`
- **Zahlen:** `year`, `track` (gepackt: `track/1000` = CD-Nummer,
  `track%1000` = Titelnummer), `durationMS`, `bitrate`, `sampleRate`,
  `bitsPerSample`, `channels`, `scannedFileType`
- **Bilder:** `albumArt` (byte[]) **oder** ein Datei-Deskriptor `B` plus Größe
  `A`. Der Deskriptor vermeidet, das ganze Bild in den Speicher zu laden.
- **Wort-synchrone Liedtexte:** `syncLyricsTimestamps` (int[]) **und**
  `syncLyricsLines` (String[]) getrennt. `getUnsyncLyrics()` baut daraus wieder
  Fließtext.
- **Wellenform:** `wave` (float[]).
- **Extras:** eine `LinkedHashMap` für beliebige Schlüssel-Wert-Paare
  (`addExtraString`, `addExtraLong`).
- **`scanRes`-Bitmaske:** `HAS_TAG = 1`, `HAS_PROPERTIES = 2`, `HAS_AA = 4`
  (Album-Art), `HAS_LYRICS = 8`. Damit weiß man ohne Prüfen, was schon da ist.

Zwei kleine, aber gute Ideen darin:

- **`getNormalizedYear()`**: Eine zweistellige Jahreszahl wird umgerechnet
  (21 bis 99 wird 19xx, 1 bis 20 wird 2000+). Alte Tags sind uneinheitlich.
- **`copyAndReset()`**: Das Objekt wird kopiert und sofort geleert, damit der
  Scanner denselben Speicher weiterverwenden kann. Kein Neubauen pro Datei.

### 21.2 Der Album-Art-Trick (Speicher sparen)

```java
// Belegtes Muster: Groesse lesen, ohne das Bild zu laden.
NativeUtils.native_set_fd(fileDescriptor, fd);      // FD in ein FileDescriptor-Objekt
BitmapFactory.Options o = new BitmapFactory.Options();
o.inJustDecodeBounds = true;                        // nur Masse, kein Bild
BitmapFactory.decodeFileDescriptor(fileDescriptor, null, o);  // liefert outWidth/outHeight
```

Der Deskriptor kommt nativ (`native_set_fd`), das Bild wird zweistufig geladen:
erst nur die Maße (`inJustDecodeBounds`), dann passend skaliert. So wird nie ein
riesiges Cover ungenutzt in den Speicher gezogen.

### 21.3 Der Ordner-Scanner (`DirScanner`, nativ)

```java
native_init(boolean, boolean, boolean, String[] pfade)  -> long handle
native_scan(long handle, String pfad, Object listener)
native_release(long handle)
```

Der Scanner läuft **nativ** und meldet jede Datei über die Schnittstelle
`InterfaceC0453` zurück nach Java:

- `startDirectory(pfad, ..., long, int, Object)` → ein neuer Ordner beginnt
- `fileFound(pfad, int, int, int, long, long, String, String, String, Object)` →
  eine Datei gefunden
- `endDirectory(pfad, Object)` → Ordner fertig

`DirAndSAFScanner` deckt zusätzlich **SAF** ab, also Speicherorte, auf die man
über den Android-Dateiauswahldialog Zugriff bekommt (SD-Karten, Cloud-Ordner).
Der Scan läuft als Dienst: `ScanDispatcherService`, `ScanWorker`,
`StorageBroadcastReceiver` (startet neu, wenn sich der Speicher ändert).

**Warum nativ?** Ein Bibliotheksscan über 10.000 Dateien ist ein Sturm von
Dateisystem-Zugriffen. In C++ ist das deutlich schneller und erzeugt keinen
Java-Müll.

### 21.4 Tag-Lesen und Tag-Schreiben

- `TagReader`: `native_create`, `native_scan_file(handle, pfad, int, int, int,
  TagAndMeta)`, `native_set_max_tag`. Der Reader **probiert Decoder der Reihe
  nach**: zuerst MediaCodec, dann ffmpeg, dazu Sonderleser für MOD (`ModTagReader`)
  und WAV/andere (`FFMpegTagReader`).
- `TagWriter`: `native_write_tags(pfad, int, int, TagAndMeta)`.
- `FFMpegTagReader`: `native_scan_file(pfad, fd, int, int, TagAndMeta)` und
  `native_scan_file_type(pfad, fd, int)`.

Bemerkenswert: Der Scanner kann einen Track also **lesen und schreiben** (Tag-
Editor), und er arbeitet über Datei-Deskriptoren, nicht über Pfade im Java-Raum.

### 21.5 Was das für uns bedeutet

- **Metadaten nativ einlesen, nicht in Java.** Bei 10.000 Dateien zählt das.
- **Album-Art über Deskriptor lesen und zweistufig laden.** Speicher ist auf
  Handys knapp.
- **Ein Objekt wiederverwenden** (`copyAndReset`), statt pro Datei neu zu bauen.
- **Scan als Dienst** mit Fortschritt und Wiederaufnahme, nicht im UI-Thread.

### 21.6 Beispielcode: Metadaten-Objekt mit Wiederverwendung (Kotlin)

```kotlin
// Eigener Beispielcode: dasselbe Muster, kompakt.
class TrackMeta {
    var title: String? = null
    var artist: String? = null
    var album: String? = null
    var durationMs = 0
    var sampleRate = 0
    var channels = 0
    var bitrate = 0
    var wave: FloatArray? = null
    val extras = LinkedHashMap<String, String>()

    fun reset() {
        title = null; artist = null; album = null
        durationMs = 0; sampleRate = 0; channels = 0; bitrate = 0
        wave = null; extras.clear()
    }
}

// Der Scanner fuellt EIN Objekt und gibt eine Kopie weiter, dann reset.
fun scanOne(scanner: NativeScanner, path: String, out: TrackMeta): TrackMeta {
    scanner.fill(path, out)          // nativ gefuellt
    val result = out.let { TrackMeta().also { c -> c.title = it.title; /* ... */ } }
    out.reset()                      // Speicher wiederverwenden
    return result
}
```

### 21.7 Inkrementeller Scan (nur Neues lesen)

Ein voller Scan von 20.000 Dateien dauert lange. Deshalb merkt sich die App pro
Datei **Größe** und **Änderungszeit**. Nur was sich geändert hat, wird neu
gelesen. Belegt im Umfeld: `StorageBroadcastReceiver` (startet neu bei
Speicheränderung), `ScanDispatcherService` (der Dienst) und die
`folder_files`-Tabelle, in der die Wellenform und Metadaten liegen.

```kotlin
// Eigener Beispielcode: inkrementeller Scan.
data class FileStamp(val path: String, val size: Long, val mtime: Long)

fun needsRescan(old: FileStamp?, path: String, size: Long, mtime: Long): Boolean {
    if (old == null) return true                 // neu
    return old.size != size || old.mtime != mtime // geaendert
}
```

**Analysepunkt:** Ohne diesen Vergleich liest jeder App-Start die ganze
Bibliothek. Mit ihm ist der zweite Start in Sekunden fertig. Belegt ist derselbe
Gedanke beim Wellenform-Worker: nur rechnen, wenn `f0.r == null`.

### 21.8 SAF und normale Dateien gleich behandeln

Belegter Weg: `DirAndSAFScanner` (ein Scanner für beide Fälle). Der Unterschied:
Bei SAF bekommt man **Datei-Deskriptoren** über `ContentResolver`, bei normalen
Dateien über `open()`. Deshalb arbeitet der native Kern mit **Deskriptoren**,
nicht mit Pfaden ([`native_open_fd`, `native_fd_lseek`, `native_close_fd` in
`NativeUtils`]).

```kotlin
// Eigener Beispielcode: Pfad oder SAF-URI zu einem Deskriptor machen.
fun openFd(context: Context, uri: android.net.Uri): Int {
    return if (uri.scheme == "file") {
        android.os.ParcelFileDescriptor.open(
            java.io.File(uri.path!!), android.os.ParcelFileDescriptor.MODE_READ_ONLY).fd
    } else {
        context.contentResolver.openFileDescriptor(uri, "r")!!.fd
    }
}
```

**Analysepunkt:** Wer nur `File` benutzt, kann keine SAF-Ordner (SD-Karte,
Cloud) einlesen. Der Deskriptor-Weg löst beide Fälle mit demselben Code.

### 21.9 Tag-Schreiben (der Editor)

Belegt: `tagwriter.cpp`, `TagWriter.native_write_tags`, `id3v2tag.cpp`. Der
Schreibvorgang ist heikler als das Lesen, weil eine beschädigte Datei Daten
verliert.

```kotlin
// Eigener Beispielcode: sicher schreiben (Temp-Datei, dann ersetzen).
fun writeTagsSafely(path: String, meta: TrackMeta, nativeWrite: (String) -> Boolean) {
    val tmp = "$path.tmp"
    check(nativeWrite(tmp)) { "write failed" }
    java.io.File(tmp).copyTo(java.io.File(path), overwrite = true)
    java.io.File(tmp).delete()
}
```

**Analysepunkt:** Erst in eine Nebendatei schreiben, dann ersetzen. Bricht der
Vorgang ab (Akku, Absturz), ist die Originaldatei noch heil. Das ist die Lehre
aus dem Projekt („Migration und Import verlieren Daten").

---

## 22 · Plugins, Skins und das Widgetpack

Das dritte große Thema ist die Erweiterbarkeit. Poweramp besteht aus steckbaren
Teilen, einer Skin-Sprache und einem eigenen Widget-System.

### 22.1 Der eingebaute Plugin-Manager

`NativePluginManager` holt die Liste der Plugins über
`native_get_plugins()` und bekommt ein `NativePluginInfo[]`. Ein Eintrag hat:

```java
String uniq_name;   // "paket/name", z. B. "com.maxmpz.audioplayer/decoder.ffmpeg"
int    id;          // Index in der Liste
int    flags;       // Bitmaske (u. a. "intern" über das hoechste Bit)
String name;        // Anzeigename
```

`getPackage()` schneidet den Teil vor dem `/` heraus. Plugin-Typen werden aus
Texten abgebildet:

| Text | Nummer |
|---|---|
| `PA_PLUGIN_TYPE_DECODER` | 1 |
| `PA_PLUGIN_TYPE_DSP` | 2 |
| `PA_PLUGIN_TYPE_OUTPUT` | 3 |
| `PA_PLUGIN_TYPE_INTERNAL_SUBSYSTEM` | sehr negativ |
| `PA_PLUGIN_TYPE_INTERNAL_DSP` | sehr negativ |
| `PA_PLUGIN_TYPE_INTERNAL_DSPI` | sehr negativ |
| `PA_PLUGIN_TYPE_INTERNAL_OUTPUT` | sehr negativ |
| `PA_PLUGIN_TYPE_INTERNAL_RESAMPLER` | sehr negativ |
| `PA_PLUGIN_TYPE_INTERNAL_DECODER` | sehr negativ |

### 22.2 Der Namenszauber (der Kern des Plugin-Systems)

Aus dem `uniq_name` baut Poweramp **per Reflection** den Namen der Java-Klasse:
`/` wird zu `.`, das letzte Teilstück wird großgeschrieben, und es wird
`PluginService` angehängt. Danach wird ein Konstruktor mit den Parametern
`(Context, NativePluginInfo)` gesucht und aufgerufen. Das Ergebnis wird in einer
`HashMap` zwischengespeichert. Findet sich nichts, kommt ein
`NullPluginService` als Ersatz.

Genau das erklärt alle Klassen, die wir gesehen haben: `TempoPluginService`,
`ReverbPluginService`, `Resampler3PluginService`, `MilkPluginService`,
`AaPluginService`, `OslPluginService`, `AtPluginService`, `FfmpegPluginService`.
Für jeden nativen Plugin-Namen gibt es genau eine gleich benannte Java-Hülle.

**Externe Plugins** sind separate APKs und werden über
`PluginDiscovery.findAPKPlugins` gefunden (Paketname und Komponente). Interne
Plugins müssen zum eigenen Paket gehören, sonst gibt es eine Ausnahme.

### 22.3 Die Skin-Sprache (XML)

Ein Skin ist eine XML-Beschreibung, die Poweramp einliest. Belegte Tags:
`option`, `globalOption`, `msg`, `seekbar`, `seekbarOptions`, `radio`, `select`,
`multiSwitch`, `popup`, `page`, `category`, `include`. Belegte Attribute:
`name`, `key`, `summary`, `summary2`, `dependency`, `icon`, `iconTint`,
`overlapAttr`, `overlapStyle`, `checkedByDefault`, `defaultValue`, `allowMulti`,
`minSdk`, `maxSdk`, `lightMode`, `darkMode`.

Drei Ideen daraus, die wirklich gut sind:

1. **`key` + `dependency`.** Jede Option hat einen Schlüssel, und eine Option
   kann von einer anderen abhängen. Ist die nicht gesetzt, verschwindet sie.
   Das erspart Bedingungen im Code.
2. **`overlapStyle` / `overlapAttr`.** Eine Option wird über ein Attribut
   (einen Ressourcen-Namen) an die Zeichenlogik gebunden, nicht über eine feste
   Nummer. Dadurch kann ein Skin neue Optionen hinzufügen, ohne den Code zu
   ändern.
3. **`include`.** Ein Skin darf ein anderes XML einbinden. Wiederverwendung ohne
   Kopie.

`SkinSeekbarOption` zeigt die Feinheit: `min`, `max`, `step`, `scale`,
`floatScale`, `snapTo`, `ticks`, `defaultValue`, `id`, `key`, `name` und drei
Beschriftungen (links, Mitte, rechts). `SkinMsg` beschreibt, was eine Zeile im
Widget anzeigt: `line1` bis `line4` und `smallLine1` bis `smallLine4`, dazu
`icon`, `iconAlign`, `align`, `iconTint`.

### 22.4 Das Widgetpack

`widgetpackcommon` enthält Anbieter für **2x2, 4x1, 4x2 und 4x4** Widgets, je
mit eigenem Provider und eigenem Konfigurator. Alle teilen sich
`BaseWidgetConfigure`, eine `FragmentActivity` mit:

- **ViewPager** über die Style-Seiten,
- **Spinner** für Auswahl,
- **SeekBars** für Zahlen,
- einem **Farbwähler** (`AmbilwarnaLayout`),
- **JSON-Import und JSON-Export** (über Zwischenablage und Teilen-Knopf),
- **Vorschau** über `RemoteViews` (`apply` / `reapply`).

**Der Widget-Stil ist JSON.** Belegte Felder beim Speichern: `type`, `label`,
`flags`, `style`, `bg_color`, `text_color`, `icons_color`, `shadow_alpha`,
`corner_radius`, `aa_alpha`, `font_family`, `font_size`, `title_font_size`,
`aa_corner_radius`, `padding_hor`, `padding_ver`, `padding_ver2`, `text_align`,
`theme`, `button_color`, plus `path` und `isModified`. Die Dateien liegen unter
`/Android/data/<paket>/widget_styles/`.

Die Flags stecken in `AbstractC0485`: `FLAG_AA`, `FLAG_AA_SHADOW`, `FLAG_FLAT`,
`FLAG_FONT_BOLD`, `FLAG_FONT_ITALIC`, `FLAG_META`, `FLAG_META_BG`,
`FLAG_NO_TITLE`, `FLAG_NO_OTHER_TEXT`, `FLAG_NO_FIXED_SIZE`, `FLAG_NO_CAT_CHANGE`,
`FLAG_NO_PLAYING_MODE`, `FLAG_TITLE_FONT_BOLD` und weitere.

### 22.5 Was das für uns bedeutet

- **Nicht alles neu erfinden.** Das Muster „Namen → Klasse per Reflection" ist
  elegant, wenn man viele gleichartige Dienste hat (bei uns: DSP-Stufen,
  Ausgabe-Wege). Für ein kleines Team ist aber eine einfache Tabelle
  (Name → Factory) verständlicher und sicherer als Reflection.
- **Optionen mit `key` und `dependency`.** Das ist ein gutes Modell für unsere
  Einstellungen: jede Einstellung hat einen stabilen Schlüssel, und
  Abhängigkeiten stehen in den Daten, nicht im Code.
- **Stil als JSON** ist robust und exportierbar. Wir brauchen keine Skins, aber
  die Idee, Einstellungen als JSON zu speichern und teilen zu können, passt zu
  unserem Vorhaben (ein Set als Datei weitergeben).
- **`RemoteViews`** sind für Widgets Pflicht. Wenn wir ein Widget bauen, gilt
  dasselbe Muster: Vorschau im Konfigurator, echtes Widget über `RemoteViews`.

### 22.6 Beispielcode: einfache Namensauflösung (Kotlin, ohne Reflection)

```kotlin
// Eigener Beispielcode: bewusst ohne Reflection, dafuer klar und sicher.
interface DspService { fun name(): String }

class TempoService : DspService { override fun name() = "tempo" }
class ReverbService : DspService { override fun name() = "reverb" }

object DspRegistry {
    private val factories: Map<String, () -> DspService> = mapOf(
        "dsp.tempo"  to { TempoService() },
        "dsp.reverb" to { ReverbService() }
    )
    fun create(uniqName: String): DspService? = factories[uniqName]?.invoke()
}
```

Warum so und nicht wie Poweramp: Eine feste Tabelle ist bei einem kleinen Team
leichter zu lesen, zu testen und zu erweitern. Reflection lohnt sich erst bei
vielen austauschbaren Modulen.

### 22.7 Der Namenszauber im Detail (und seine Fehlerfälle)

Belegte Ableitung: `uniq_name` mit `/` zu `.`, letztes Teilstück groß, plus
`PluginService`. Beispiel:

```
"com.maxmpz.audioplayer/decoder.ffmpeg"
   -> "com.maxmpz.audioplayer.decoder.ffmpeg.FfmpegPluginService"
```

Drei Fehlerfälle, die im Original behandelt werden:
1. **Klasse fehlt** → `NullPluginService` (kein Absturz).
2. **Paket passt nicht** → Ausnahme (`bad pak=... plugin=...`).
3. **Plugin-Info ohne XML/Definition** → Log und Platzhalter.

**Analysepunkt:** Der Reflection-Weg ist elegant, aber teuer und fehleranfällig.
Er lohnt sich erst bei **vielen** austauschbaren Modulen (Poweramp hat Decoder,
DSP, Output, Skins, Visualizer). Für ein kleines Team ist eine feste Tabelle
besser (siehe 22.6). Der Fehlerfall „Klasse fehlt" ist der wichtigste: er darf
nie abstürzen, sondern muss auf einen neutralen Ersatz fallen.

### 22.8 Ein Mini-Parser für Optionen (XML)

Die Skin-Sprache liest Tags wie `option`, `radio`, `select`, `seekbar`, `page`,
`category`, `include` und Attribute wie `key`, `dependency`, `name`, `summary`.
Ein eigener Parser ist überschaubar:

```kotlin
// Eigener Beispielcode: Optionen aus XML lesen (sehr vereinfacht).
data class Option(val key: String, val name: String,
                  val dependency: String?, val defaultValue: Int)

fun parseOptions(parser: android.content.res.XmlResourceParser): List<Option> {
    val out = ArrayList<Option>()
    var event = parser.next()
    while (event != android.util.XmlPullParser.END_DOCUMENT) {
        if (event == android.util.XmlPullParser.START_TAG && parser.name == "option") {
            val key  = parser.getAttributeValue(null, "key")
            val name = parser.getAttributeValue(null, "name")
            val dep  = parser.getAttributeValue(null, "dependency")
            val def  = parser.getAttributeIntValue(null, "defaultValue", 0)
            if (!key.isNullOrEmpty()) out.add(Option(key, name ?: key, dep, def))
        }
        event = parser.next()
    }
    return out
}
```

**Analysepunkt:** `key` und `dependency` sind die zwei Felder, die den ganzen
Mehrwert tragen: ein stabiler Schlüssel und eine Abhängigkeit. Damit kann eine
Einstellung eine andere ein- und ausblenden, ohne dass im Code eine Bedingung
steht.

### 22.9 Was wir vom Widgetpack wirklich brauchen

Das Widgetpack ist groß, weil es vier Größen, Skins und Farbwähler hat. Für uns
relevant ist nur:

1. **Eigene Styles als JSON** (exportierbar und teilbar). Damit kann der Nutzer
   ein Auto-DJ-Set als Datei weitergeben.
2. **`RemoteViews`** für ein echtes System-Widget (Stop/Play, aktueller Track,
   Restzeit bis zum Übergang).
3. **Ein Konfigurator mit Vorschau**, der im selben Prozess `RemoteViews`
   zeichnet (`apply`).

Alles andere (Skins, Farbwähler, Viewpager) brauchen wir nicht.

---

## 23 · Was das für unsere UI bedeutet

- **Bus-System statt direkter Kopplung.** Engine und Oberfläche über einen
  `StateBus` und einen `MsgBus` verbinden. Das macht unsere Auto-DJ-Anzeige
  einfach: die Decks, die Restzeit bis zum Übergang und der Fortschritt sind
  nur weitere Zustände.
- **Bedarfsgesteuerte Animation.** Die Decks-Anzeige darf nicht dauerhaft
  laufen. Nur bei Bedarf zeichnen, sonst ruhen.
- **nanoTime-Interpolation** für alle Fortschritts-Anzeigen (auch die
  Übergangs-Zeit bis zum Fade).
- **Wellenform einmal rechnen, als BLOB speichern.** Bei uns kommt sogar mehr
  dazu: aus der Wellenform kann der Nutzer den Drop sehen.
- **Eigene gezeichnete Regler** statt Standard-Widgets, mit zwischengespeicherten
  Bitmaps.
- **Kein Compose im Audiopfad.** Compose ist für die Einstellungen in Ordnung,
  aber die Player-Ansicht profitiert von handgezeichneten Views.

### 23.1 Modulzuschnitt für unsere Oberfläche (konkret)

Aus allem ergibt sich ein klarer Zuschnitt:

```text
ui/
  player/    PlayerScreen, QueueList, DeckPanel (Auto-DJ)
  widget/    WaveSeekView, SeekView, DeckBar, RestTimeView
  bus/       StateBus, MsgBus, BusId
  theme/     Farben, Maße (aus einem JSON-Stil)
  settings/  SettingsScreen (darf Compose sein)
core/
  audio/     Engine, RingBuffer, Decks, Output
  analysis/  Scanner, Waveform, BPM/Key
  ai/        Embedder, Retriever, Assistant
data/        SQLite, DAOs, Stil-JSON
```

**Analysepunkt:** Nur die **Player-Ansicht** muss handgezeichnet sein (Wellenform,
Decks, Seek). Einstellungen und Listen dürfen Standard oder Compose sein. So
bleibt der aufwendige Teil klein.

### 23.2 Die drei Ansichten, die den Unterschied machen

1. **WaveSeekView** (Wellenform, Drei-Scheiben-Bitmaps, bedarfsgesteuert).
2. **DeckPanel** (zwei Decks, Restzeit bis zum Übergang, BPM und Tonart).
3. **QueueList** (mit sichtbarer Stimmung/Klangbild-Sortierung).

**Analysepunkt:** Wenn diese drei sitzen, fühlt sich die App wie ein Profi-Produkt
an. Alles andere ist Beiwerk.

---

## 24 · Tiefenanalyse: Die Wellenform

Hier gehen wir Ebene für Ebene durch, von der nativen Berechnung bis zum
gezeichneten Balken.

### 24.1 Die native Seite

Im Binary (`libpowerampcore.so`) liegen die Belegstellen:

```
ScanDecode.cpp
scan_decode_init       Kontext anlegen
scan_with_decoder      tatsaechliche Berechnung
scan_file_impl         Datei oeffnen und Lesen
scan_file_by_type      nach Dateityp entscheiden
native_scan_file       Bruecke nach Java
```

Die Java-Hülle `ScanDecode` (Paket `audioplayer/decoder`) hat genau drei native
Methoden:

```java
native_create()                                             -> long handle
native_scan(long handle, String pfad, int a, int b, int c,
            byte[] extras)                                  -> float[]
native_release(long handle)
```

Der Aufruf geht über `B(pfad, a, b, c, extras)`. Das Ergebnis ist ein
**`float[]`** mit Werten zwischen 0 und 1 (Amplituden-Spitzen je Abschnitt).

**Ehrlicher Hinweis:** Die genaue Bedeutung der drei `int`-Parameter lässt sich
aus dem Dekompilat nicht sicher ableiten (Kandidaten: Dateityp, Zeitfenster,
Zielanzahl der Abschnitte). Das `byte[]` sind Zusatzdaten. Wer das nachbaut,
definiert die Parameter selbst, zum Beispiel so:

```
(a) Dateityp        (b) maximale Scanlaenge   (c) Anzahl Buckets
```

### 24.2 Der Worker (`d0`)

`d0` (Paket `audioplayer/player`) besitzt:

- **eine** `ScanDecode`-Instanz (`f1522`), also genau einen nativen Kontext,
- einen `HandlerThread` (`f1523`), damit die Berechnung **nicht** im
  UI-Thread läuft,
- einen wiederverwendeten `ByteBuffer` (`f1525`) und `FloatBuffer` (`y`),
- einen `ContentValues`-Puffer (`f1526`), der mehrfach benutzt wird.

Ablauf:
1. Es wird nur gerechnet, wenn der Track noch keine Form hat
   (`f0.r == null`) und der Dateityp passt.
2. Die Arbeit kommt an den **Anfang** der Warteschlange
   (`sendMessageAtFrontOfQueue`), damit die Form früh entsteht.
3. Ergebnis: `float[]` → Bytes → **BLOB** in der Spalte **`wave`** der Tabelle
   `folder_files`, Schlüssel `folder_files._id`.

### 24.3 Der Puffer-Trick (detailgenau)

```java
if (wave.length == 100) {
    // Normalfall: vorhandenen 400-Byte-Puffer wiederverwenden
    buf  = reuseOrAlloc(400);        // 100 Werte * 4 Byte
    fb   = buf.asFloatBuffer();
    fb.position(0); buf.position(0);
} else {
    buf  = ByteBuffer.allocate(wave.length * 4);
    fb   = buf.asFloatBuffer();
}
fb.put(wave);
values.put("wave", buf.array());
```

`100` ist die Standardbreite der Wellenform. Deshalb der feste 400-Byte-Puffer.
So entsteht bei jedem Track **keine neue Allokation**, und der Garbage Collector
bleibt ruhig. Genau die Disziplin aus dem Audiopfad, nur hier für die Anzeige.

### 24.4 Auflösung: von gespeicherten Werten zu Balken

Die Ansicht will `K` Balken (aus dem XML). Die gespeicherte Form kann eine
andere Länge haben. `p4.H(K, form)` resampled sie mit **Nearest Neighbor**:

```java
// p4.m1800, belegter Algorithmus
for (int i = 0; i < out.length; i++) {
    int src = (int)(0.5 + i * ratio);
    if (src >= in.length) src = in.length - 1;
    out[i] = in[src];
}
```

Nearest Neighbor ist hier richtig, weil die Wellenform nur ein **Bild** ist. Eine
glattere Interpolation würde Spitzen wegmitteln, und genau die Spitzen sollen
sichtbar sein.

### 24.5 Die Ersatzwelle (damit nie etwas leer ist)

Ist noch keine echte Form da, baut `Waveseek` selbst eine Welle aus einer
Sinusformel. Belegte Werte: Faktor 1,5 (bei einer Breite) beziehungsweise 3,0,
Skalierung 0,25 beziehungsweise 0,33, Versatz 0,25 beziehungsweise 0,0. Jeder
Wert wird auf **0,01 bis 1,0** begrenzt. Das Ergebnis wird **geklont** und als
Ersatzform markiert. Sobald die echte Form kommt, wird sie ersetzt.

### 24.6 Der weiche Wechsel (Crossfade der Wellenform)

Wechselt der Track, springt die Form nicht hart um. `i5.c(form, animieren)`
macht einen weichen Übergang:

```java
// belegtes Muster in i5.c
this.k = neueForm;                 // Ziel
this.n = 0.0f;                     // Fortschritt
animator.B(1.0f, dauer, 0.0f, false);   // p1: kubisches Ausklingen
// pro Frame:
for (int i = 0; i < K; i++)
    alteForm[i] = zielForm[i] * n + (1.0f - n) * alteForm[i];
```

`p1` ist ein kleiner Animator mit **kubischem Ausklingen**
(`1 - (1 - t)^3`). Er liefert den Fortschritt `n` von 0 auf 1. So **morpht** die
Wellenform vom alten zum neuen Track, statt zu blitzen.

### 24.7 Beispielcode: Wellenform cachen (Kotlin, original)

```kotlin
// Eigener Beispielcode: Wellenform rechnen, speichern, mit Nearest-Neighbor anpassen.
object Wave {
    fun toBuckets(pcm: FloatArray, frames: Int, channels: Int, buckets: Int): FloatArray {
        val out = FloatArray(buckets)
        val per = frames / buckets
        for (b in 0 until buckets) {
            val start = b * per
            val end = if (b == buckets - 1) frames else start + per
            var peak = 0f
            var i = start
            while (i < end) {
                for (c in 0 until channels) {
                    val v = kotlin.math.abs(pcm[i * channels + c])
                    if (v > peak) peak = v
                }
                i++
            }
            out[b] = peak
        }
        return out
    }

    fun fit(src: FloatArray, want: Int): FloatArray {
        if (src.size == want) return src
        val out = FloatArray(want)
        val ratio = src.size.toDouble() / want
        for (i in 0 until want) {
            val j = (0.5 + i * ratio).toInt().coerceIn(0, src.size - 1)
            out[i] = src[j]
        }
        return out
    }

    fun encode(wave: FloatArray): ByteArray {
        val bb = java.nio.ByteBuffer.allocate(wave.size * 4)
        bb.asFloatBuffer().put(wave)
        return bb.array()
    }
}
```

### 24.8 Die nativen Parameter rekonstruieren

Die Signatur ist `native_scan(handle, pfad, int a, int b, int c, byte[] extras)`.
Aus den Aufrufstellen und den Schleifenlogiken lässt sich die **wahrscheinliche**
Bedeutung ableiten (mit Vorsicht, es bleibt eine Lesart):

| Parameter | Wahrscheinliche Bedeutung | Begründung |
|---|---|---|
| `a` | Dateityp / Decoder-Wahl | Der Scanner muss wissen, womit er dekodiert |
| `b` | gewünschte Anzahl Buckets | Die Ansicht will `K` Balken |
| `c` | maximale Scanlänge | lange Titel sollen den Scan nicht sprengen |
| `extras` | Zusatzdaten (Tags/Kanalinfo) | kommt aus den Metadaten |

**Ehrlicher Hinweis:** Diese Zuordnung ist nicht sicher belegt. Wer nachbaut,
**definiert die Parameter selbst** und dokumentiert sie. Genau das ist der
Clean-Room-Weg: gleiche Funktion, eigene Schnittstelle.

### 24.9 Die Bucket-Anzahl wählen

Die Ansicht will `K` Balken. Wie viele sinnvoll sind, folgt aus der Breite:

```
 K = max(50, Breite_in_dp * Faktor)
```

Beispiel: 360 dp breit, Faktor 1,4 ergibt etwa 500 Balken. Bei 500 Balken auf
360 dp ist jeder Balken weniger als 1 dp breit, also praktisch nicht mehr
unterscheidbar.

```kotlin
// Eigener Beispielcode: sinnvolle Balkenzahl je Bildschirmbreite.
fun bucketCount(widthDp: Int, barWidthDp: Float, gapDp: Float): Int {
    val pitch = (barWidthDp + gapDp).coerceAtLeast(0.5f)
    return (widthDp / pitch).toInt().coerceIn(32, 1000)
}
```

**Analysepunkt:** Bei sehr schmalen Balken lohnt es sich, die Welle zu
**verkleinern** und nur jeden zweiten Wert zu zeichnen. Das spart Zeit und sieht
ruhiger aus.

### 24.10 Wann die Wellenform berechnet wird

Drei Auslöser, sonst nie:

1. Der Track wird zum ersten Mal abgespielt.
2. Der Nutzer öffnet den Track-Editor.
3. Der Nutzer startet den Auto-DJ (dann werden viele auf einmal gebraucht).

**Analysepunkt:** Für den Auto-DJ lohnt es sich, die Wellenform **im Voraus** für
die wahrscheinlichen Kandidaten zu rechnen (Vorlauf), damit die Decks-Anzeige
nicht leer startet.

### 24.11 Die harte Zeitgrenze des Scans (2 Sekunden)

Aus der Dekompilation (`key-functions.c`, Funktion `scan_with_decoder`, Datei
`ScanDecode.cpp`) gibt es eine echte Konstante:

```
MAX_TIME_TO_SCAN_NS = 1.999.999.999 ns   (etwa 2 Sekunden)
```

Der Code misst mit `clock_gettime(CLOCK_MONOTONIC, ...)` (Uhr-Id 3) und bricht
ab, wenn die Zeit überschritten ist:

```c
/* Belegtes Muster (eigene Formulierung). */
clock_gettime(CLOCK_MONOTONIC, &now);
if (NOW_NS - start_ns > 1999999999ULL) {
    log(__FILE__, "%s MAX_TIME_TO_SCAN_NS, skipping %s", "scan_with_decoder", path);
    skip_file();
}
```

**Analysepunkt:** Die Wellenform-Berechnung hat eine **harte Obergrenze von etwa
zwei Sekunden pro Datei**. Danach wird die Datei übersprungen (keine Wellenform,
aber kein Hänger). Das ist eine wichtige Produktentscheidung: Lieber eine leere
oder Ersatz-Wellenform als eine App, die beim Einscannen einer Bibliothek
einfriert. Für uns heißt das: dieselbe Obergrenze setzen und den Fall
„übersprungen" sichtbar machen (Ersatzwelle, siehe 24.5).

```kotlin
// Eigener Beispielcode: Zeitgrenze beim Scan.
fun scanWithLimit(path: String, limitNs: Long = 1_999_999_999L): FloatArray? {
    val start = System.nanoTime()
    val out = ArrayList<Float>(256)
    while (true) {
        if (System.nanoTime() - start > limitNs) return null   // aufgeben
        val block = readNextBlock(path) ?: break
        out.addAll(peakBuckets(block))
    }
    return out.toFloatArray()
}
```

**Zweite Zahl aus derselben Ecke:** Der Nachrichten-Router verwaltet höchstens
**acht** Subsystem-Kontexte (`MAX_SUBSYSTEM_CONTEXTS = 8`), belegt in
`msg_router.c`.

---

## 25 · Tiefenanalyse: Die Seek-View und wie gezeichnet wird

Jetzt kommt das Herzstück der Bedienung. Zwei Ansichten gibt es:

| Ansicht | Basis | Wann |
|---|---|---|
| `Seek` | `android.widget.SeekBar` | einfacher Fortschritt ohne Wellenform |
| `Waveseek` | `com.maxmpz.widget.base.i5` (eigene `ViewGroup`) | mit Wellenform |

Beide teilen sich denselben Fortschrittsmotor `q1` (Abschnitt 19). Der
Unterschied ist nur das Zeichnen.

### 25.1 `Seek` (die einfache Variante)

`Seek` erbt vom System-`SeekBar` und setzt `setMax(10000)`. Der Fortschritt ist
also **Festkomma**: `progress / 10000` ist der Bruch 0 bis 1. Das umgeht
Rundungsfehler und erlaubt feines Ziehen. Beim Berühren wird der Hotspot
gesetzt (`background.setHotspot(x, y)`), und `q1` bekommt den Bruch
(`m2022(progress / 10000f, true)`).

Warum 10000: Genug Auflösung für ein 3-Stunden-Hörbuch (etwa 1 Sekunde pro
Schritt) und trotzdem klein genug für `int`.

### 25.2 `Waveseek` (die Wellenform-Variante)

`Waveseek` erbt von `i5` und zeichnet alles selbst. `i5` hält dafür:

- **vier Bitmaps**: `G`, `I`, `J`, `L` (normaler beziehungsweise alternativer
  Zustand, obere beziehungsweise untere Hälfte),
- zwei **Paints** (`F` und weitere),
- die **Wellenform-Arrays** `j` (aktuell) und `k` (Ziel beim Wechsel),
- Rechtecke `D` (`Rect`) und `E` (`RectF`) als wiederverwendete Zeichenflächen,
- den **Punkt** `y` (`PointF`) als Position des Griffs.

### 25.3 Zwei Zonen und vier Bitmaps

Beim Zeichnen gibt es immer **zwei Zonen**:

```
 |<--- gespielt (links vom Griff) --->|<--- ungespielt --->|
```

Jede Zone wird mit einem anderen Bitmap gezeichnet. Zusammen mit „aktiv oder
ausgegraut" ergibt das die vier Bitmaps `G`/`J` (oben) und `I`/`L` (unten). Der
Code wählt mit `isEnabled() ? G : J`.

### 25.4 Ein Balken ist ein Drei-Scheiben-Bild (der Kern)

Ein Balken ist **kein** gezeichnetes Rechteck, sondern ein **vorgefertigtes
Bitmap**, das in drei Scheiben gezeichnet wird. Belegter Code (`m1771`):

```java
int cap = bitmap.getWidth() / 2;        // Radius der runden Kappe
int h   = bitmap.getHeight();

RectF dst = ...;  Rect src = ...;
// 1. obere Kappe (rund)
src.set(0, 0, bitmap.getWidth(), cap);
// 2. Mittelteil (dehnbar, gerade)
src.set(0, cap, bitmap.getWidth(), h - cap);
// 3. untere Kappe (rund)
src.set(0, h - cap, bitmap.getWidth(), h);
canvas.drawBitmap(bitmap, src, dst, paint);
```

Die obere und untere Scheibe werden **nie** gestreckt (abgerundet), nur die
Mittelscheibe wächst mit der Höhe. So sieht ein 3 Pixel hoher Balken genauso
sauber aus wie ein 300 Pixel hoher, und es wird nichts pro Frame berechnet. Das
ist der klassische **Neun-Scheiben-Gedanke**, hier auf drei Scheiben reduziert.

### 25.5 Das Raster (Pitch) und die Virtualisierung

Die Balken liegen auf einem festen Raster:

```
pitch = Balkenbreite (H) + Abstand (P)
erster sichtbarer Balken   i
letzter sichtbarer Balken  iCeil
```

`onLayout` rechnet die Breiten: Bei einem „Tick"-Stil wird die Breite als
`(Breite - Ränder) / K` verteilt, sonst über den Bruchteil `f2633`. Die
Gesamtbreite der Welle ist `ceil((H + P) * K - P)`.

Gezeichnet werden **nur die sichtbaren** Balken (der Bereich wird zusätzlich mit
`clipRect` beschnitten). Bei 500 Balken auf einem schmalen Schirm zeichnet die
App also nur die 30, die man sieht. Das ist der Grund, warum die Leiste auch
auf schwachen Geräten flüssig bleibt.

### 25.6 Die weichen Ränder (Alpha)

Der erste und der letzte halb sichtbare Balken werden **ausgeblendet**, nicht
abgeschnitten. Belegte Formel:

```java
// Abstand des Balkens vom Rand: f19
alpha = (f19 >= H) ? 255 : (int)((f19 / H) * 255);
```

So „verschwindet" die Welle am Rand weich. Wer das weglässt, sieht harte
Kanten und ein abgehacktes Bild.

### 25.7 Runde Kappen an den Enden

Hat der Nutzer einen Eckenradius gesetzt (`f2630`, ein Bruchteil 0 bis 1), bekommt
nur der **erste und letzte** Balken eine runde Kappe. Der Code zeichnet dafür
zwei zusätzliche, beschnittene Bereiche (oberhalb beziehungsweise unterhalb einer
Linie `N`). Balken in der Mitte bleiben eckig, damit die Welle geschlossen
aussieht.

### 25.8 Berührung und der Griff

- `onTouchEvent` rechnet die X-Position in einen Bruch 0 bis 1 (`f(x)`).
- Der Bruch geht an `q1` (`m1772`), damit die Position aktualisiert wird.
- Der Griff (ein Kind-View, per Id `2131558437` gesucht) wird über
  `translationX` verschoben (`m1773`).
- Beim Loslassen wird `m1774()` gerufen und die Position endgültig gesetzt.
- Beim Drücken erscheint eine **Sprechblase** mit der Zeit (das Kind-View), und
  `setPressed` meldet es dem Bus. Das ist der Grund, warum man beim Ziehen die
  genaue Zeit sieht.

### 25.9 Beispielcode: einen Balken als Drei-Scheiben-Bild zeichnen (Kotlin)

```kotlin
// Eigener Beispielcode: ein Balken aus einem vorgefertigten Pill-Bitmap.
class BarDrawer(private val pill: Bitmap, private val paint: Paint) {
    private val cap = pill.width / 2          // Radius der Kappe
    private val src = Rect()
    private val dst = RectF()

    fun drawBar(canvas: Canvas, left: Float, top: Float, right: Float, bottom: Float,
                alpha: Int) {
        paint.alpha = alpha
        val h = pill.height

        // obere Kappe
        src.set(0, 0, pill.width, cap)
        dst.set(left, top, right, top + cap)
        canvas.drawBitmap(pill, src, dst, paint)

        // Mittelteil (wird gestreckt)
        src.set(0, cap, pill.width, h - cap)
        dst.set(left, top + cap, right, bottom - cap)
        canvas.drawBitmap(pill, src, dst, paint)

        // untere Kappe
        src.set(0, h - cap, pill.width, h)
        dst.set(left, bottom - cap, right, bottom)
        canvas.drawBitmap(pill, src, dst, paint)

        paint.alpha = 255
    }
}
```

### 25.10 Ziehen in einer scrollenden Liste (der Klassiker)

Die Seekbar sitzt oft in einer Liste. Zieht der Nutzer **waagerecht**, will er
die Position ändern. Zieht er **senkrecht**, will er scrollen. Wer das nicht
trennt, „klaut" der Liste die Geste (oder umgekehrt).

Belegter Hinweis: `p4.K(View)` / `p4.m1799` laufen die Elternkette hoch und
fragen den Scroll-Container, ob ein View anklickbar ist. Das ist die Grundlage
für diese Entscheidung.

```kotlin
// Eigener Beispielcode: Geste entscheiden (waagerecht vs senkrecht).
class WaveSeekView : View {
    private var startX = 0f; private var startY = 0f
    private var dragging = false

    override fun onTouchEvent(e: android.view.MotionEvent): Boolean {
        when (e.actionMasked) {
            android.view.MotionEvent.ACTION_DOWN -> {
                startX = e.x; startY = e.y; dragging = false
                parent?.requestDisallowInterceptTouchEvent(false)
                return true
            }
            android.view.MotionEvent.ACTION_MOVE -> {
                if (!dragging) {
                    val dx = kotlin.math.abs(e.x - startX)
                    val dy = kotlin.math.abs(e.y - startY)
                    if (dx > 8f && dx > dy) {          // klar waagerecht
                        dragging = true
                        parent?.requestDisallowInterceptTouchEvent(true)  // Liste stoppen
                    } else if (dy > 8f) {
                        parent?.requestDisallowInterceptTouchEvent(false)
                        return false                    // Liste scrollt
                    }
                }
                if (dragging) { setFraction((e.x - paddingLeft) / (width - paddingLeft - paddingRight)) }
                return true
            }
            android.view.MotionEvent.ACTION_UP,
            android.view.MotionEvent.ACTION_CANCEL -> {
                if (dragging) commit()
                dragging = false
                parent?.requestDisallowInterceptTouchEvent(false)
                return true
            }
        }
        return super.onTouchEvent(e)
    }
}
```

**Analysepunkt:** Die Acht-Pixel-Schwelle (`touch slop`) verhindert, dass ein
zittriger Finger den Modus umschaltet. Ohne sie springt die Ansicht bei jedem
kleinen Wackeln zwischen Ziehen und Scrollen.

### 25.11 Warum der Fortschritt 0 bis 10000 ist

`Seek` setzt `setMax(10000)`. Bei einer Wiedergabe von 3 Stunden (10.800 s) ist
ein Schritt 1,08 s, also fein genug. Bei einem 3-Minuten-Lied ist ein Schritt
18 ms, feiner als jeder Bildschirm. 10000 ist damit für alle Fälle gut, und es
passt in `int`. **Analysepunkt:** Man wählt die Einheit **feiner als der
schlechteste Fall** und nicht feiner als nötig, um Rechenzeit zu sparen.

---

## 26 · Tiefenanalyse: Layout-Engine, Bitmap-Caches und Bedienlogik

### 26.1 Das `widget/base`-Paket (225 Dateien)

Das Paket ist kein Zufall. Es ist eine **eigene kleine UI-Bibliothek**. Belegte
Bausteine:

- **`FastLayout`**, **`SceneFastLayout`**, **`PrivateNonSceneFastLayout`**,
  **`FastLayoutWithViewCacheOpt`**: eigene Layout-Container, die schneller
  aufblasen als das Standard-`LayoutInflater`, teilweise mit View-Cache.
- **`SceneFastLayout` und `SceneParams`**: eine **„Szene"** ist ein ganzer
  Bildschirm. Sie kennt ihre Parameter und ihren Bus.
- Eigene Widgets: **`FastTextView`**, **`FastCheckBox`**, **`FastButton`**,
  **`MarqueeFastTextView`**, **`ProgressBar`**, **`RatingBar`**, `Space`,
  `SmartSpacer`, `NonOverlappingView`, `AlphaDisabledView`, `InvisibleView`.
- **`*Behavior`-Klassen** (viele): `BusActionBehavior`, `ScrollingBehavior`,
  `LoadableBehavior`, `CollapsableBehavior`, `AdjustToSoftKeyboardBehavior`,
  `BusSelectableBehavior`, `MorphableBusStateBehavior`, `SleepTimerBehavior`.
- **Fähigkeits-Interfaces**: `h4`, `u2`, `o3`, `c4`, `c5`, `n3` (wer was kann).
- **Bus-Klassen**: `BusActionButton`, `BusCheckBox`, `BusStatusText`,
  `BusDisabledForStateBehavior`, `BusStateEnabledBehavior`.

**Die „Behavior"-Idee:** Verhalten (Klick, Laden, Scrollen) hängt nicht an einer
Unterklasse, sondern an einem **angehängten Objekt**. Ein View bekommt ein
Verhalten über ein Interface, nicht über Vererbung. Das entkoppelt Aussehen und
Logik. In `BaseWidgetConfigure` sieht man es konkret: `((FastCheckBox) v).z0 = this`
setzt ein Verhalten.

**Die „Bus"-Idee:** Viele Widgets reagieren direkt auf den Nachrichtenbus
(Abschnitt 18). `BusActionButton`, `BusCheckBox` und die `Bus*Behavior`-Klassen
sind Views, die sich selbst anmelden. Dadurch muss die Activity nichts verdrahten.

### 26.2 Das `widget/bitmaps`-Paket (Bitmap-Cache)

- **`AbstractC0562`** ist die Werkzeugkiste: Skalieren und Dekodieren.
  - Zwei statische **1x1-Platzhalter** (`f2761` RGB565, `B` ALPHA_8) statt
    `null`-Prüfungen. Wer ein leeres Bild braucht, bekommt ein definiertes.
  - **`B(bitmap, options)`** skaliert nach einem `scaleType` (1 bis 6), viele
    davon eigene Varianten (fit, crop, quadratisch, rund). Die Zielgröße wird
    **vor** dem Zeichnen bestimmt, nicht durch den Canvas.
  - **`x(fd, bytes, options)`** dekodiert aus Datei-Deskriptor **oder** Bytes und
    fängt `OutOfMemoryError` ab. Album-Cover sind oft riesig; hier wird bewusst
    zweistufig geladen (erst Maße, dann Bild).
  - **`C0565`** ist das Options-Objekt mit `scaleW`, `scaleH`, `scaleType`,
    `BitmapFactory.Options` und einem wiederverwendeten `Canvas`.
- **`C0564`/`C0565`** tragen einen Cache-Schlüssel, damit dasselbe Cover nicht
  mehrfach skaliert wird.

Warum das wichtig ist: Auf einem Handy ist **Speicher** der Engpass, nicht die
Rechenzeit. Ein einziges unskaliertes 4000x4000-Cover sind 64 MB. Deshalb wird
jedes Bild genau einmal in der gebrauchten Größe erzeugt und dann geteilt.

### 26.3 `p4` (die Helfer)

`p4` bündelt statische Helfer, die überall gebraucht werden:

- **`H(int, float[])`**: Wellenform auf die gewünschte Länge bringen.
- **`B(View)` / `m1797(ViewGroup)`**: zur „Szene" und ihrem Bus hochlaufen.
- **`X(Class, View, int)` / `m1802`**: ein angehängtes Verhalten finden und,
  wenn es fehlt, mit klarer Fehlermeldung abbrechen.
- **`K(View)` / `m1799` / `m1803`**: prüfen, ob ein View anklickbar ist (durch
  die Elternkette bis zum Scroll-Container).
- **`m1800`**: Nearest-Neighbor-Resampling.

### 26.4 Wie die Bedienelemente zusammenarbeiten

```
 Nutzer tippt
    |
 onTouchEvent (i5 oder SeekBar)
    |
 Bruch 0..1  --->  q1.m2022()  --->  Nachricht an den Bus
    |                                        |
 Griff per translationX                    Engine setzt neue Position
    |                                        |
 onDraw zeichnet neu <--- neuer Zustand <--- 
```

Der wichtige Punkt: Beim Ziehen entscheidet **die View**, nicht die Engine. Sie
meldet nur „neuer Bruch" und zeichnet sofort. Die Engine folgt. Erst beim
Loslassen wird die endgültige Position gesetzt. Dadurch bleibt das Ziehen
flüssig, auch wenn die Engine langsam wäre.

### 26.5 Was das für uns bedeutet (konkret)

- **Balken als Bitmaps, nicht als Rechtecke.** Einmal ein Pill-Bitmap bauen, dann
  in Drei-Scheiben zeichnen. Das sieht sauber aus und kostet nichts pro Frame.
- **Nur sichtbare Balken zeichnen** und den Rand beschneiden.
- **Randbalken ausblenden** statt abschneiden.
- **Wellenform resampeln mit Nearest Neighbor**, damit Spitzen bleiben.
- **Wellenform weich überblenden** beim Trackwechsel (kubisches Ausklingen).
- **Festkomma-Fortschritt** (0 bis 10000) statt Fließkomma, wo es geht.
- **Cover zweistufig laden** (Maße, dann Größe) und in einem Cache teilen.
- **Verhalten anhängen statt Unterklassen bauen.** Für uns reicht aber ein
  einfaches Interface, keine ganze Behavior-Maschine.
- **Views melden sich am Bus an**, damit die Activity nichts verdrahten muss.

### 26.6 Beispielcode: Randbalken ausblenden (Kotlin, original)

```kotlin
// Eigener Beispielcode: Alpha fuer den ersten/letzten sichtbaren Balken.
fun edgeAlpha(distanceFromEdge: Float, barWidth: Float): Int {
    return if (distanceFromEdge >= barWidth) 255
           else ((distanceFromEdge / barWidth) * 255f).toInt().coerceIn(0, 255)
}

// Und die Anwendung im Zeichenlauf:
fun drawRange(canvas: Canvas, firstBar: Int, lastBar: Int, pitch: Float,
              barWidth: Float, positions: (Int) -> Float, heightOf: (Int) -> Float,
              drawer: BarDrawer, widthPx: Float) {
    for (b in firstBar..lastBar) {
        val x = positions(b)
        val alpha = minOf(
            edgeAlpha(x, barWidth),                       // linker Rand
            edgeAlpha(widthPx - x - barWidth, barWidth)   // rechter Rand
        )
        drawer.drawBar(canvas, x, heightOf(b), x + barWidth, 0f, alpha)
    }
}
```

### 26.7 Warum Aufblasen (Inflate) so teuer ist

Beim Aufblasen von XML passieren pro View mehrere Dinge: XML lesen, Attribute
auflösen, Objekt anlegen, Style anwenden, ins Eltern einhängen. Bei tiefen
Bäumen kostet das leicht mehrere Millisekunden pro Bildschirm. Belegter Weg:
eigene Layouts (`FastLayout`, `SceneFastLayout`) und ein View-Cache
(`FastLayoutWithViewCacheOpt`, `getViewCache`).

```kotlin
// Eigener Beispielcode: einfacher View-Cache fuer Listenzeilen.
class ViewCache {
    private val pool = ArrayDeque<android.view.View>()
    fun obtain(create: () -> android.view.View): android.view.View =
        pool.removeLastOrNull() ?: create()
    fun recycle(v: android.view.View) { if (pool.size < 16) pool.addLast(v) }
}
```

**Analysepunkt:** Nur **dieselbe** Zeilenart darf wiederverwendet werden. Ein
Cover-Bitmap in einer wiederverwendeten Zeile muss vorher gelöscht werden, sonst
sieht man das Bild der vorigen Zeile („Geisterbild").

### 26.8 Messen, wo die Zeit hingeht

```kotlin
// Eigener Beispielcode: Messpunkte fuer Aufbau und Zeichnen.
class StageTimer(val name: String) {
    private var t0 = 0L
    fun start() { t0 = android.os.SystemClock.elapsedRealtimeNanos() }
    fun stop() {
        val ms = (android.os.SystemClock.elapsedRealtimeNanos() - t0) / 1_000_000.0
        if (ms > 8.0) android.util.Log.w("UI-Stage", "$name dauerte ${ms}ms")
    }
}
```

**Analysepunkt:** Die 8-ms-Schwelle ist knapp unter einem Bild bei 120 Hz. Alles,
was länger dauert, ist ein Bildverlust und sollte geloggt werden. So findet man
den Engpass statt zu raten.

### 26.9 Die Bitmap-Regeln in kurz

1. **Zweistufig laden** (Maße, dann Bild in Zielgröße).
2. **Im Cache teilen** (gleiches Cover nicht mehrfach skalieren).
3. **Platzhalter statt null** (1x1-Bitmap).
4. **`OutOfMemoryError` fangen** und auf Platzhalter fallen.
5. **Vor dem Wiederverwenden der Zeile löschen** (`setImageBitmap(null)`).

---

## 27 · Tiefenanalyse: Warum Poweramp so schnell ist

Diese Frage hat keine einzelne Antwort. Poweramp spart an **vielen** Stellen,
und jede einzelne Stelle ist klein. Zusammen ergeben sie das Gefühl von
„sofort". Ich ordne die Belege nach Ort: nativer Audiopfad, Threading, Java,
JNI, Anzeige, Speicher.

### 27.1 Das Prinzip: drei Budgets

Es gibt drei Budgets, und jedes wird getrennt gehalten.

| Budget | Wo es zählt | Wie es gehalten wird |
|---|---|---|
| **Zeit** | Audiopfad, Anzeige | kein Blockieren, Vorberechnung, Interpolation |
| **Speicher** | Alle Teile | Wiederverwendung, Puffer statt Allokation, kleine Bilder |
| **Akku** | Hintergrund, Anzeige | bedarfsgesteuerte Arbeit, Offload, Ruhen im Stillstand |

### 27.2 Der native Audiopfad

Belegte Bausteine aus dem Binary:

```
mmapped_circular_buffer.c        Speicher-gemappte Ringpuffer
mmapped_mapping_init
mmapped_circular_buffer_init num_pages=%d
failed mmap addr1 / addr2
MAP_FAILED header_mmapped
priority.c
set_thread_priority
setpriority
```

Daraus lesen wir vier Techniken:

1. **Speicher-gemappte Ringpuffer (`mmap`).** Die Puffer werden einmal als
   Speicherseiten gemappt und dann im Kreis beschrieben. Kein `malloc`, kein
   `free`, keine Kopie. Der Zeiger läuft im Kreis, die Daten bleiben an Ort und
   Stelle. Das ist der Grund, warum im Audio-Callback nichts passieren kann, was
   blockiert.

2. **Thread-Prioritäten explizit setzen.** Es gibt eine eigene `priority.c` mit
   `set_thread_priority`. Der Audio- und der DSP-Thread laufen mit hoher
   Priorität, der Decoder normal. So bekommt die Ausgabe Vorrang, und der
   Betriebssystem-Scheduler holt sie nicht zugunsten anderer Arbeit herunter.

3. **Vorlauf-Puffer (Prefetch).** Belegte Größen: `dsp_prefetch_block_frames`,
   `dsp_prefetch_bufs`, `avail_buf_size_in_frames`, `open_output_and_init_buffers`.
   Der DSP arbeitet dem Decoder **voraus**, damit er nie auf Daten wartet. Ein
   Vorlauf kostet wenig Latenz, spart aber das Schlimmste (Aussetzer).

4. **Sichere Voreinstellung als Netz.** Belegt:
   `bad config_blob_msg (buf_ms=%d dsp_bufs=%d dsp_prefetch_bufs=%d), using
   default safe output config`. Ist die Gerätekonfiguration unbrauchbar, nimmt
   die Engine einen **bewährten sicheren Satz**. Kein Absturz, kein Knacken,
   nur etwas mehr Latenz.

Dazu:

5. **Komprimiertes Offload.** Belegte Strings: `compress_offload`,
   `audio.offload.buffer.size.kb`, `AUDIO_OUTPUT_FLAG_NON_BLOCKING`,
   `has compress_offload formats`. Damit kann Poweramp den **Decoder in die
   Hardware** geben. Die CPU wird frei, der Akku hält länger. Nicht bei jeder
   Datei möglich, deshalb wird geprüft und dann entschieden.

6. **32-Bit-Float plus Vektorrechnung.** Belegt: `__attribute__((vector_size(`
   (GCC-Vektortypen) und `libffmpeg_neon.so` (ARM-NEON). Float ist für EQ und
   Gain einfacher als Ganzzahl, und Vektorrechnung schafft mehrere Samples in
   einem Schritt.

### 27.3 Threading: Nachrichten statt Sperren

- **Zwei Arbeits-Threads** (Decoder, DSP) plus der Ausgabe-Callback.
- **`HandlerThread` plus `Looper`** für Hintergrundarbeit. Der Scanner und die
  Wellenform laufen so, ohne den UI-Thread zu berühren.
- **Nachrichten statt Sperren.** Zwischen den Threads werden Nachrichten
  ausgetauscht (`pa_send_msg`, `post_cmd`, `route_msg`), nicht geteilte Objekte
  unter einem Mutex gehalten. Wer nicht sperrt, kann nicht blockieren.
- **`sendMessageAtFrontOfQueue`** für die Wellenform: wichtige Arbeit vorziehen.
- **Prioritäten über `setpriority`** im Native-Teil.

### 27.4 Java: keine Allokation im heißen Pfad

Hier ist belegt, wie diszipliniert Poweramp in Java ist.

**Wiederverwendete Objekte.** Der Wellenform-Worker hält **einen**
`ContentValues`, **einen** `ByteBuffer`, **einen** `FloatBuffer` und ein
**`String[]`** für Query-Argumente und benutzt sie immer wieder. Im Track-Status
`f0` gibt es `byte[] q` und `float[] r` als Felder, die einmal gesetzt werden.

**Zahlen statt Objekte.** Fehlerzustände und Merker laufen als **Bitmasken** in
`int` (z. B. die `FLAG_*` in den Widgets) und als `AtomicInteger` (`f0.c0`).
Keine `Boolean`-Objekte, kein Boxen.

**Sperrfreier Zustand.** `f0.O(int, int)` ändert die Flags mit einer
Compare-and-Swap-Schleife (`compareAndSet`). Kein `synchronized`, keine Sperre.

**Eine eigene Hashmap.** Statt `java.util.HashMap` benutzt Poweramp
`com.maxmpz.utils.m`. Was daran anders ist (alles belegt):

```java
int h = (int)(((long) key.hashCode() * -7046029254386353131L) >>> shift);
int idx = h;                       // Tabelle ist Zweierpotenz
while (tabelle[idx] != null) {
    if (tabelle[idx].equals(key)) return idx;
    idx = (idx + 1) & maske;       // lineares Sondieren
}
```

- **Offene Adressierung** mit linearem Sondieren statt einer Kette von Knoten.
  Kein `Node`-Objekt pro Eintrag, dadurch weniger Speicher und bessere
  Cache-Nähe.
- **Multiplikative Streuung** mit der Knuth-Konstante
  `0x9E3779B97F4A7C15` und Verschiebung über `Long.numberOfLeadingZeros`. Die
  hohen Bits werden genutzt, dadurch verteilen sich die Einträge gleichmäßig.
- **Tabelle ist Zweierpotenz**, also `& maske` statt Modulo.
- **Lastfaktor 0,8**, Verdopplung beim Wachsen.
- **Iteratoren werden wiederverwendet** (`this.H` und `this.P` wechseln sich ab).
  Eine Schleife erzeugt also **kein** Iterator-Objekt.
- **Leeren per `Arrays.fill`** statt Neuanlegen.

Für 51 Einträge Standardgröße. Das ist der Speicher für die Plugin-Liste und
ähnliche Nachschlagevorgänge.

### 27.5 Die JNI-Brücke

- **`@FastNative`** steht an den heißen Methoden (`Pipeline2`: 6 Stellen,
  `Coefs`: 4 Stellen). Diese Marke sagt der Laufzeitumgebung, dass die native
  Methode **schnell** ist und nicht blockiert. Der Aufruf wird dadurch billiger.
  Der Vertrag ist streng: keine Sperren, kein Blockieren, keine Zuweisung großer
  Objekte. Genau deshalb ist die Marke wertvoll.
- **Handle statt Weltzustand.** `native_create()` liefert einen `long`, alle
  weiteren Aufrufe bekommen ihn mit. Kein globaler Zustand, keine Implikationen.
- **Grobe Aufrufe statt feiner.** Der Zustand wird **gesammelt** abgefragt
  (`get_int_param`, `get_state`, `get_position_ms`), nicht Sample für Sample.
  Häufige, teure Grenzübertritte werden vermieden.

### 27.6 Die Anzeige: bedarfsgesteuert und interpolierend

Aus Abschnitt 19 und 25:

- **Dirty-Flags plus `Choreographer`.** Die Animation läuft **nur**, wenn etwas
  zu tun ist, und **stoppt** vollständig, wenn nichts offen ist. Im Stillstand
  kostet die Anzeige null.
- **`nanoTime`-Interpolation.** Die Position wird selbst weitergerechnet, statt
  die Engine in jedem Frame zu fragen. Nur alle 75 Frames wird abgeglichen.
- **Schwelle je Tracklänge** (2 Prozent bzw. 7,5 Prozent). So wird nicht zu oft
  korrigiert.
- **Vorgefertigte Bitmaps.** Ein Balken ist ein Drei-Scheiben-Bild, kein
  Rechteck. Nichts wird pro Frame berechnet.
- **Nur sichtbare Balken** plus `clipRect`.
- **Randbalken ausblenden** statt abschneiden.

### 27.7 Speicher: kleine Bilder und geteilte Daten

- **Bitmap-Cache** (`widget/bitmaps`): Cover wird einmal in der gebrauchten
  Größe erzeugt und geteilt. Zwei statische **1x1-Platzhalter** statt
  `null`-Prüfungen.
- **Zweistufiges Laden.** Erst die Maße (`inJustDecodeBounds`), dann das Bild in
  der Zielgröße. So wird nie ein riesiges Cover ungenutzt geladen.
- **Nearest-Neighbor** beim Anpassen der Wellenform: billiger als jede
  Interpolation und für eine Anzeige genau richtig.
- **View-Cache.** `FastLayoutWithViewCacheOpt` und `getViewCache` halten
  aufgebohrte Ansichten vor, statt sie neu zu bauen.

### 27.8 Beispielcode: offene Hashmap in klein (Kotlin, original)

```kotlin
// Eigener Beispielcode: das m-Prinzip in klein. Zweierpotenz, lineares Sondieren,
// multiplikative Streuung, keine Knotenobjekte.
class MiniMap<K, V>(capacityPowerOfTwo: Int = 64) {
    private var keys = arrayOfNulls<Any?>(capacityPowerOfTwo)
    private var vals = arrayOfNulls<Any?>(capacityPowerOfTwo)
    private var mask = capacityPowerOfTwo - 1
    private var size = 0
    private var shift = java.lang.Long.numberOfLeadingZeros(mask.toLong())

    @Suppress("UNCHECKED_CAST")
    operator fun get(key: K): V? {
        var i = indexOf(key)
        return if (i < 0) null else vals[i] as V?
    }

    fun put(key: K, value: V) {
        var i = indexOf(key)
        if (i < 0) {
            i = -(i + 1)
            keys[i] = key; vals[i] = value; size++
            if (size >= (mask + 1) * 0.8) grow()
        } else vals[i] = value
    }

    private fun indexOf(key: K): Int {
        val h = ((key.hashCode().toLong() * -7046029254386353131L) ushr shift).toInt()
        var i = h
        while (true) {
            val k = keys[i] ?: return -(i + 1)
            if (k == key) return i
            i = (i + 1) and mask
        }
    }

    private fun grow() {
        val oldKeys = keys; val oldVals = vals
        val n = (mask + 1) shl 1
        keys = arrayOfNulls(n); vals = arrayOfNulls(n)
        mask = n - 1; shift = java.lang.Long.numberOfLeadingZeros(mask.toLong()); size = 0
        for (j in oldKeys.indices) oldKeys[j]?.let { put(it as K, oldVals[j] as V) }
    }
}
```

### 27.9 Beispielcode: Thread-Priorität und Vorlauf (Android, original)

```kotlin
// Eigener Beispielcode: Prioritaet setzen und Vorlauf-Puffer dimensionieren.
fun startAudioThread() {
    val t = Thread {
        android.os.Process.setThreadPriority(android.os.Process.THREAD_PRIORITY_AUDIO)
        // Arbeitsschleife: liest aus dem Ringpuffer, mischt, schreibt raus
    }
    t.name = "dsp-thread"
    t.start()
}

// Vorlauf: der DSP arbeitet dem Decoder voraus.
// frames = Vorlauf in Frames, msPerBlock = Blocklaenge.
fun prefetchBlocks(sampleRate: Int, targetPrefetchMs: Int, msPerBlock: Int): Int {
    val blocksPerMs = 1.0 / msPerBlock
    return kotlin.math.ceil(targetPrefetchMs * blocksPerMs).toInt()
}
```

### 27.10 Die Performance-Checkliste (aus allem abgeleitet)

- [ ] Kein `malloc`, kein Sperren, kein Log, kein Dateizugriff im Audiopfad.
- [ ] Ringpuffer einmal mappen (`mmap`) und im Kreis nutzen.
- [ ] Thread-Prioritäten explizit setzen (Audio hoch, Decoder normal).
- [ ] Vorlauf-Puffer dimensionieren, damit der DSP nie wartet.
- [ ] Einen sicheren Standard-Satz für die Ausgabekonfiguration bereithalten.
- [ ] Komprimiertes Offload prüfen und nutzen, wenn möglich.
- [ ] 32-Bit-Float und Vektorrechnung (NEON).
- [ ] Zwischen Threads Nachrichten austauschen, nicht Zustand teilen.
- [ ] Objekte wiederverwenden (Puffer, `ContentValues`, Arrays).
- [ ] Flags als `int`-Bitmaske und `AtomicInteger`, keine Objekte.
- [ ] Eine eigene kompakte Hashmap für heiße Nachschlagevorgänge.
- [ ] `@FastNative` an heißen JNI-Methoden, Handle statt Weltzustand.
- [ ] Grobe, gesammelte native Abfragen statt feiner Einzelaufrufe.
- [ ] Anzeige bedarfsgesteuert, Interpolation per `nanoTime`, Ruhe im Stillstand.
- [ ] Vorgefertigte Bitmaps statt Neuzeichnen pro Frame.
- [ ] Nur sichtbare Elemente zeichnen.
- [ ] Bilder zweistufig laden und in einem Cache teilen.

### 27.11 Ein Satz

Poweramp ist nicht durch einen Trick schnell. Es ist schnell, weil an
**jeder** Stelle eine kleine Regel gilt: **nichts im heißen Pfad tun, was man
vorher tun könnte.** Zwei Threads, gemappte Puffer, feste Blöcke, Vorlauf,
Prioritäten, wiederverwendete Objekte, vorgefertigte Bilder, bedarfsgesteuerte
Animation. Jede Regel allein bringt wenig. Zusammen bringen sie das Gefühl, dass
nichts hakt.

### 27.12 Vorab-Laden (Prefetch) im DSP

```c
/* Eigener Beispielcode: Daten vorab in den Cache ziehen. */
#if defined(__aarch64__)
static inline void prefetch_read(const void* p) {
    __asm__ __volatile__("prfm pldl1keep, [%0]" :: "r"(p));
}
#endif

void mixer_loop(const float* a, const float* b, float* out, int n) {
    for (int i = 0; i < n; ++i) {
        if ((i & 15) == 0) prefetch_read(a + i + 16);   // 16 Frames voraus
        out[i] = a[i] + b[i];
    }
}
```

**Analysepunkt:** Bei großen Blöcken bringt Vorab-Laden spürbar etwas. Bei
kleinen Blöcken (unter einigen hundert Samples) ist der Effekt klein. Messen,
nicht blind einbauen.

### 27.13 Zweige vermeiden (weniger Fehlvorhersagen)

```c
/* Eigener Beispielcode: Begrenzen ohne Verzweigung. */
static inline float clamp01_branchless(float x) {
    x = x < 0.0f ? 0.0f : x;    /* Compiler macht daraus oft cmov/fmin/fmax */
    x = x > 1.0f ? 1.0f : x;
    return x;
}
```

**Analysepunkt:** In einer Schleife über Millionen Samples kosten falsch
vorhergesagte Zweige mehr als die Rechnung selbst. Compiler wandeln die
Dreiecksform oft in bedingte Anweisungen (`fmin`/`fmax`) um, die keine Vorhersage
brauchen.

### 27.14 Die Kosten eines JNI-Aufrufs

Ein normaler JNI-Aufruf kostet grob hunderte Nanosekunden (Argumente, Umgebung,
Prüfungen). In einer Schleife pro Sample wäre das tödlich. Deshalb:
- **Gesammelte Aufrufe** (ein Aufruf für einen ganzen Block).
- **`@FastNative`** für kurze Abfragen.
- **Zeiger/Handle** statt Objekte, damit kein Umwandeln nötig ist.

```kotlin
// Eigener Beispielcode: gut (ein Aufruf pro Block) vs schlecht (pro Sample).
// SCHLECHT: native fuer jedes Sample
// for (s in samples) nativeProcessSample(s)
// GUT: einen Block auf einmal
external fun nativeProcessBlock(handle: Long, buffer: java.nio.ByteBuffer, frames: Int): Int
```

### 27.15 Die Regel „keine Allokation im Pfad" prüfen

`malloc`/`new` im heißen Pfad ist der häufigste Performance-Fehler. Man kann ihn
**automatisch** finden, indem man im Test einen Allokations-Zähler mitlaufen
lässt und prüft, dass er während der Wiedergabe nicht steigt.

```kotlin
// Eigener Beispielcode: pruefen, dass im Pfad nichts angelegt wird.
class AllocationProbe {
    private var before = 0L
    fun mark() { before = android.os.Debug.getNativeHeapAllocatedSize()
                       + android.os.Debug.getGlobalAllocSize() }
    fun check(tag: String) {
        val after = android.os.Debug.getNativeHeapAllocatedSize()
                  + android.os.Debug.getGlobalAllocSize()
        if (after - before > 4096) android.util.Log.w("AllocProbe", "$tag: ${after - before} B")
    }
}
```

**Analysepunkt:** Diese Prüfung gehört in einen automatischen Test. Dann kann
niemand versehentlich eine Allokation in den Audiopfad einbauen, ohne dass die
Prüfung anschlägt.

### 27.16 Die vier Messwerkzeuge

| Werkzeug | Was es zeigt | Wann |
|---|---|---|
| `systrace` / `atrace` | Threads, Blockaden, Zeit pro Abschnitt | bei Ruckeln |
| `dumpsys media.audio_flinger` | Puffer, Latenz, Aussetzer | bei Knacken |
| Eigener Underrun-Zähler | Aussetzer pro Minute | immer (in der App) |
| Eigener Allokations-Zähler | Allokationen im Pfad | in Tests |

**Analysepunkt:** Poweramp misst mit denselben Mitteln. Der Unterschied ist, dass
die Zähler **in der App** bleiben und nicht nur im Test. So kann der Nutzer bei
Problemen selbst nachsehen.

### 27.17 Reale Zahlen aus der Dekompilation

Jetzt die belegten Werte hinter den Regeln.

**Thread-Prioritäten (aus `all-functions.c`, Funktionen in `priority.c`):**

| Fund | Wert | Bedeutung |
|---|---|---|
| `setpriority(PRIO_PROCESS, tid, -8)` | nice **-8** | Audio-Thread (Wrapper `FUN_003792b8`) |
| `setpriority(PRIO_PROCESS, tid, -0xe)` | nice **-14** | höhere Stufe (DSP) |
| `sched_setscheduler(tid, policy, ...)` | policy 3 oder 0 | Echtzeit-Politik setzen |
| `set_sched_policy` (bionic) | cgroup | in die Audio-cgroup einordnen |
| Fehlertext | `priority.c` `%s %s failed setpriority` | Prüfung mit Log |

Das heißt: Poweramp setzt **zwei** Hebel. Erstens `setpriority` (nice-Werte -8
und -14) für die normale Vorrangigkeit. Zweitens `sched_setscheduler` und die
cgroup-Zuordnung, damit der Thread im Android-Scheduler zur richtigen Gruppe
gehört. Beide zusammen halten die Audioausgabe oben.

**Puffergrenzen (aus `dsp_thread.c`, `create_output_and_buffers`):**

| Konstante / Grenze | Wert |
|---|---|
| `MIN_BUF_FRAMES_SAFE` | **1024 Frames** (0x400) |
| `request_dsp_blocks` | 1 bis 10 |
| `request_dsp_prefetch_blocks` | 1 bis 10 |
| `request_dsp_postfade_blocks` | 0 bis 10 |
| Latenz-Grenzen | 1,0 bis 10000,0 ms (und 0 bis 10000,0) |
| max. gültige Latenz (Float) | `0x461c4000` = **10000,0** |

**Struktur:**

| Fakt | Wert |
|---|---|
| verankerte Funktionen im Handover | 189 |
| Subsystem-Kontexte im Router | 8 |
| eigene Exporte | 16 |
| dynamische Symbole | 524 |
| PLT-Einträge (Fremdaufrufe) | ~452 |
| Decoder-Slots | 2 |

**Die ABI-Varianten beim `dlsym` (aus `key-functions.c`):**

Der AudioTrack-Lader probt **vier** verschiedene `set(...)`-Signaturen, je nach
`ro.build.version.sdk` (`uVar7`):

| Schwelle (SDK) | Signatur |
|---|---|
| `< 0x15` (21) | alte `set(...)`-Form |
| `< 0x17` (23) | Form mit Callback-Zeiger |
| `< 0x1a` (26) | Form mit `AttributionSourceState` |
| `>= 0x1a` (26+) | neueste Form (17 Argumente) |

Dazu immer: `AudioTrack::start/pause/write/flush/stop`,
`RefBase::decStrong(void const*)`, `AudioSystem::getLatency(int, unsigned int*)`.
Nach dem Laden setzt die Bibliothek einen Fähigkeitsmerker
(`DAT_00477a90 |= 3`).

**Warum das wichtig ist:** Der AudioTrack-C++-Konstruktor hat sich über die
Android-Versionen mehrfach geändert. Wer eine feste Signatur linkt, stürzt auf
anderen Versionen ab. Poweramp probt der Reihe nach und nimmt die passende. Das
ist der Preis für „eine Bibliothek, viele Android-Versionen", und der Grund,
warum im Binary die kryptischen C++-Namen als Texte stehen.

---

## 28 · Die `libpowerampcore.so` im Detail

Jetzt die Kernbibliothek selbst. Wir haben vier Belegebenen: den ELF-Kopf, die
524 dynamischen Symbole, die eingebetteten Textstrings (Dateinamen und Pfade)
und die Anzahl der Funktionen (17.122).

### 28.1 Der ELF-Kopf

```
Klasse:      ELF64
Endian:      little endian
Maschine:    AArch64 (arm64)
Typ:         DYN (Shared Object)
Programme:   9 Programmkopfe, 3 LOAD-Segmente
Sektionen:   27
Einstieg:    0x0 (eine Bibliothek, kein Programm)
Dateigroesse: ~3,59 MB (Sektionskopfe bei 3588784)
```

Die Sektionen mit Inhalt und Größe:

| Sektion | Größe | Bedeutung |
|---|---|---|
| `.text` | **2.292.076 B (2,19 MiB)** | der ausführbare Code |
| `.rodata` | 371.610 B (363 KiB) | Konstanten und Text (14.814 Strings) |
| `.gcc_except_table` | 99.320 B | Ausnahmetabellen (C++) |
| `.eh_frame` | 453.068 B | Abwicklungsinformation (C++) |
| `.eh_frame_hdr` | 129.652 B | Zeiger in die Abwicklungsdaten |
| `.rela.plt` | 10.848 B (452 Einträge) | Aufrufe in andere Bibliotheken |
| `.dynsym` | 12.600 B (525 Einträge) | die Symbole |
| `.data.rel.ro` | 46.576 B | schreibgeschützte Zeiger (vtables) |
| `.data` | 9.120 B | beschreibbare Startwerte |
| `.bss` | **5.693.360 B (5,43 MiB)** | statische Nullpuffer |
| `.plt` | 7.264 B | Sprungtabelle |
| `__lcxx_override` | 268 B | Sonderabschnitt der NDK-libc++ |

Zwei Zahlen stechen heraus:

1. **`.text` 2,19 MiB.** Das ist viel Code. Darin stecken nicht nur die eigene
   Engine, sondern auch **komplette Fremdbibliotheken** (siehe 28.4).
2. **`.bss` 5,43 MiB.** Über 5 MB statische Puffer. Das sind die vorab
   reservierten Audio-, Decoder- und FFT-Puffer. Wieder das Muster aus
   Abschnitt 27: alles vorab anlegen, nichts zur Laufzeit reservieren.

Dass `.gcc_except_table` und `.eh_frame` groß sind, zeigt: Die Bibliothek ist
**C++ mit Ausnahmen**. Dazu passt `libcxxabi` (siehe unten).

### 28.2 Die 16 Exporte (die einzige öffentliche Fläche)

```
JNI_OnLoad / JNI_OnUnload
internal_plugininterface_set_package
internal_register_decoder / _dsp
internal_set_dspi / _resampler
pa_alloc_plugin_context
pa_format_infos_same
pa_get_plugin / pa_get_plugin_by_uniq_name
pa_log_format_info
pa_register_decoder / _dsp / _output
pa_send_msg
```

Sechzehn Symbole. Das ist die **komplette** Schnittstelle nach außen. Alles
andere ist versteckt (`stripped`, keine lokalen Namen). Wer die Bibliothek
benutzt, kennt nur diese sechzehn Funktionen. Das ist gutes Schnittstellen-Design:
eine winzige Tür, dahinter eine große Maschine.

### 28.3 Die 524 dynamischen Symbole (der Bauplan der Abhängigkeiten)

Die vollständige Liste verrät, was die Bibliothek **von außen** braucht. Aufteilung:

| Gruppe | Beispiele | Zweck |
|---|---|---|
| **Android NDK Media** | `AMediaCodec_*`, `AMediaExtractor_*`, `AMediaFormat_*`, `AMEDIAFORMAT_KEY_*` | Plattform-Decoder und Container |
| **Android Assets** | `AAssetManager_*`, `AAsset_*` | Lesen aus dem APK |
| **Bitmap/Surface** | `AndroidBitmap_*`, `ANativeWindow_*` | Bilder und Zeichenfläche |
| **OpenSL ES** | `SL_IID_*`, `slCreateEngine` | direkte Audio-Ausgabe |
| **OpenGL ES** | `egl*`, `gl*` (rund 60 Einträge) | Visualizer (Milkdrop) |
| **FFmpeg** | `av_*`, `swr_*`, `ff_*_demuxer`, `ff_*_decoder` | Dekodieren, Umsampling, FFT, SHA |
| **zlib** | `inflate*`, `deflate*`, `crc32` | Kompression |
| **mbedTLS** | `mbedtls_cipher_*`, `mbedtls_pk_*` | Krypto |
| **Netzwerk** | `recvfrom`, `sendto`, `setsockopt`, `shutdown` | Sync/Fernsteuerung |
| **System** | `mmap`, `munmap`, `mprotect`, `mremap`, `madvise` | Speicher-mappen |
| **Scheduler** | `sched_setscheduler`, `setpriority`, `prctl` | Thread-Prioritäten |
| **pthread/sem** | `pthread_*`, `sem_*` | Threads und Signale |
| **Dynamic Loading** | `dlopen`, `dlsym`, `dlclose` | Bibliotheken zur Laufzeit |
| **Mathe/Sprache** | `sin`, `cos`, `pow`, `log`, `hypot`, `sincos` | Rechnen |

**Der wichtigste Fund hier:** `AAudio` und `AudioTrack` stehen **nicht** in der
Symboltabelle, obwohl die Bibliothek sie benutzt. Die Belege dafür sind Strings
wie `AAudioStream_requestStart` und der kryptische
`_ZN7android10AudioTrack3setE19audio_stream_type_t...` (ein C++-Name). Solche
Namen erscheinen nur, wenn sie **zur Laufzeit per `dlsym` gesucht** werden.
Begründung: AAudio gibt es erst ab Android 8.1. Wer es **direkt** linkt, lädt auf
älteren Geräten nicht. Also lädt Poweramp die Funktionen **spät** über `dlopen`
und `dlsym`. Deshalb funktioniert dieselbe Bibliothek auf alten und neuen
Geräten. OpenSL ES dagegen ist direkt gelinkt (es ist alt genug), und MediaCodec
kommt über die NDK-API.

### 28.4 Was statisch eingebaut ist (aus Dateinamen und Pfaden)

Die Strings enthalten **Quelldateinamen** (aus `__FILE__` und Absturz-Meldungen).
Das ist die Modulliste:

**Engine (eigener Code, C/C++)**

```
decoder_thread.c        decoder_thread_run / _start
dsp_thread.c            dsp_thread_run / _start
dsp-internal.c          dsp_block / dsp_do_dsp_block
resampler3.c            plugin.resampler3
resampler_internal.c
ffmpegdecoder2.c        decoder.ffmpeg
amediadecoder.c         decoder.amedia
moddecoder.c            decoder.mod
mpcdecoder.c            decoder.mpc
wvdecoder.c             decoder.wv
peq_native_utils.c      5-Band-EQ
equ5/float.inl          EQ-Kern
float-dspi-support.c    Float-DSP-Schnittstelle
ScanDecode.cpp          Wellenform
mmapped_circular_buffer.c
priority.c
ReverbDSPPlugin.cpp
MilkDSPPlugin.cpp
```

**Decoding-Bibliotheken**

```
libopenmpt         (MOD/Tracker)
WavPack            (wvdecoder)
Musepack           (mpcdecoder)
FFmpeg             -> extern: libffmpeg_neon.so
```

**Tag-Bibliothek**

```
tagreader.cpp, tagwriter.cpp
id3v2tag.cpp, id3v2frame.cpp
taglib-modile-init.cpp      -> TagLib (Mobile-Fork)
```

**Visualizer (Milkdrop, hier „Milk")**

```
milk-modile-init.cpp        Milkdrop (Mobile-Fork)
EelParser.cpp, eel2_lexer.cpp, milk_lexer.cpp    EEL2-Sprache
PresetRunner.cpp, CppPresetFactory.cpp
MilkFileParser.cpp, MilkFileLoader.cpp, PresetNamesIterator.cpp
GLScene.cpp, GLProg.cpp, ShaderEngine.cpp
ShaderTranslator.cpp, PingPongShaderBase.cpp
BlurShader.cpp, AABlurShader.cpp, TextureManager.cpp
Environment.cpp, image-utils.cpp, Loader.cpp, ZipKt.cpp
AshmemAudioSource.cpp, AshmemAudioSourceDSP.cpp,
AshmemAudioSourceContainer.cpp
MilkRendererJava.cpp, MilkNativeUtils.cpp
```

**Weitere eingebaute Fremdbibliotheken**

```
LuaJIT 2.1.0-beta3     Skript-Auswertung (Presets)
zlib                   Kompression
mbedTLS                Krypto
libc++ / libcxxabi     C++-Standardbibliothek der NDK
```

### 28.5 Der Build-Pfad (ein außergewöhnlicher Fund)

Zwei Strings enthalten den **vollen Quellpfad**:

```
/Users/maksimpetrov/Andro/AndroIdea/audioplayer_libpowerampcore/thirdparty/libopenmpt/soundlib/Sndmix.cpp
/Users/maksimpetrov/Andro/AndroIdea/audioplayer_libpowerampcore/thirdparty/libopenmpt/libopenmpt/libopenmpt_c.cpp
```

Daraus lesen wir:

- Der Entwickler ist **maksimpetrov** (das passt zu „Max MP", dem Poweramp-Autor).
- Der Build lief auf einem **Mac** (`/Users/...`).
- Das Projekt heißt **`audioplayer_libpowerampcore`**.
- Es gibt einen Ordner **`thirdparty/`**, in dem die Fremdbibliotheken liegen.
  Für jede: `thirdparty/libopenmpt/...`, und nach demselben Muster vermutlich
  `thirdparty/ffmpeg`, `thirdparty/wavpack`, `thirdparty/musepack`,
  `thirdparty/taglib`, `thirdparty/milkdrop`, `thirdparty/luajit`.
- Der `out/llvm-project/libcxxabi/src/...`-Pfad zeigt den **NDK-Clang-Build**.

Kein Sicherheitsproblem für den Nutzer, aber ein **Hinweis für uns**: Wer keine
Pfade streift, veröffentlicht seine Benutzer- und Ordnerstruktur. Bei uns sollte
`-ffile-prefix-map` beim Bauen dafür sorgen, dass aus dem eigenen Pfad ein
neutraler wird.

### 28.6 Was das über das Design sagt

1. **Eine große Bibliothek, nicht viele kleine.** Statt zehn `.so`-Dateien gibt
   es eine (plus FFmpeg separat). Vorteile: nur eine Ladeeinheit, keine
   Versionskonflikte, weniger Datei-Overhead. FFmpeg bleibt draußen, weil es groß
   ist und (vermutlich) getrennt gepflegt oder ersetzt werden kann.

2. **`.bss` 5,4 MiB, `.text` 2,2 MiB.** Der Speicher ist für Puffer reserviert,
   nicht für Code. Das passt zur Philosophie: alles vorab, nichts zur Laufzeit.

3. **C++ mit Ausnahmen, aber ohne sichtbare Symbole.** Das Binary ist `stripped`
   (17.122 Funktionen heißen `FUN_...`). Nach außen nur 16 Exporte. Große
   Maschine, kleine Tür.

4. **`dlsym` für kompatibilitätskritische APIs.** AAudio und AudioTrack werden
   spät geladen. Das ist der Preis dafür, dass eine Datei auf vielen
   Android-Versionen läuft.

5. **Fremdbibliotheken als Quellcode eingebettet** (denn ihre Strings sind
   drin). libopenmpt, TagLib, Milkdrop und LuaJIT sind **hineinkompiliert**,
   nicht extern. Dadurch gibt es weder Abhängigkeiten noch Lizenzdateien zur
   Laufzeit (die Lizenzfragen bleiben aber, siehe Abschnitt 8 und 11).

### 28.7 Was wir daraus mitnehmen

- **Eine Kernbibliothek, eine kleine Schnittstelle.** Genau wie hier: nur eine
  Handvoll Exporte, alles andere versteckt.
- **`mmap` plus `.bss` vorab.** Puffer einmal reservieren, nie im Betrieb.
- **`dlopen`/`dlsym` für neue APIs**, damit eine Bibliothek auf alten Geräten
  lädt. Für uns: AAudio über `dlsym`, Oboe regelt das schon intern.
- **Externe, große Teile getrennt halten** (bei uns etwa dem Separierer), kleinere
  Teile bündeln.
- **Kein Pfad-Leak.** Beim Bauen Pfade neutralisieren.
- **Kompression und Krypto nur, wenn gebraucht.** zlib brauchen wir (zip,
  Album-Cover in ID3), mbedTLS nur, falls wir Sync oder Lizenzprüfung bauen.

### 28.8 AAudio und AudioTrack über `dlsym` laden (Beispielcode)

Der wichtigste Fund aus 28.3 in Code. Statt direkt zu linken (und auf alten
Geräten nicht zu laden), werden die Funktionen zur Laufzeit gesucht.

```cpp
// Eigener Beispielcode: AAudio spaet laden (kein Link gegen libaaudio).
#include <dlfcn.h>
#include <android/api-level.h>

struct AAudioApi {
    typedef int  (*reqStart)(void*);
    typedef int  (*reqFlush)(void*);
    reqStart requestStart = nullptr;
    reqFlush requestFlush = nullptr;
};

bool loadAAudio(AAudioApi* api) {
    if (android_get_device_api_level() < 27) return false;   // gibt's erst ab 8.1
    void* h = dlopen("libaaudio.so", RTLD_NOW | RTLD_LOCAL);
    if (!h) return false;
    api->requestStart = (AAudioApi::reqStart)dlsym(h, "AAudioStream_requestStart");
    api->requestFlush = (AAudioApi::reqFlush)dlsym(h, "AAudioStream_requestFlush");
    return api->requestStart && api->requestFlush;
}
```

**Analysepunkt:** Genau so entstehen die String-Funde
`AAudioStream_requestStart` und der AudioTrack-C++-Name im Binary: Es sind
**gesuchte Namen**, keine gelinkten Symbole. Preis: ein Zeigeraufruf statt eines
direkten Aufrufs, und die Fehlerprüfung muss selbst gemacht werden. Gewinn:
eine Bibliothek für viele Android-Versionen.

### 28.9 Die Modulkarte (wer liegt wo)

Aus den Dateinamen und Pfaden ergibt sich diese Karte des Projekts:

```
audioplayer_libpowerampcore/
  src/                      eigene Engine (decoder_thread.c, dsp_thread.c, ...)
  thirdparty/
    libopenmpt/             MOD/Tracker (statisch eingebaut)
    ffmpeg/                 extern als libffmpeg_neon.so
    wavpack/                wvdecoder
    musepack/               mpcdecoder
    taglib/                 Tags (modile-Fork)
    milkdrop/               Visualizer (modile-Fork), EEL2
    luajit/                 Skript (Milkdrop-Presets)
    zlib/                   Kompression
    mbedtls/                Krypto
  out/llvm-project/         NDK-Clang/libc++
```

**Analysepunkt:** Für uns ist diese Karte eine Vorlage. Eigener Code in `src/`,
jede Fremdbibliothek in `thirdparty/<name>/`, und die Bauwege (`out/`) getrennt.
So weiß jeder sofort, was eigen ist und was fremd, und die Lizenzen lassen sich
sauber führen.

### 28.10 Die Bau-Regeln, die man daraus lernt

| Regel | Warum |
|---|---|
| `-fvisibility=hidden` | nur die gewollten Exporte sichtbar (hier 16) |
| `-ffile-prefix-map=<pfad>=.` | keine eigenen Pfade im Binary (28.5) |
| `strip` | keine Funktionsnamen (hier 17.122 `FUN_...`) |
| Fremdcode in `thirdparty/` | Lizenzen und Herkunft klar |
| Große Teile extern (`libffmpeg_neon.so`) | unabhängig austauschbar |
| Kleine Teile bündeln | eine Ladeeinheit, keine Versionskonflikte |

**Analysepunkt:** Diese sechs Regeln sind übertragbar und kosten fast nichts.
Besonders die erste und die zweite sind wichtig: eine kleine öffentliche Fläche
und keine Pfad-Spuren.

### 28.11 Was man aus den Zahlen ablesen kann

| Zahl | Bedeutung |
|---|---|
| 16 Exporte | minimale öffentliche Fläche |
| 524 dynamische Symbole | rund 450 Fremdaufrufe (PLT), Rest eigene Exporte |
| 17.122 Funktionen | großer, aber strippen-barer Codekörper |
| 2,19 MiB `.text` | eigener Code plus eingebaute Fremdbibliotheken |
| 5,43 MiB `.bss` | vorab reservierte Puffer und Tabellen |
| rund 452 PLT-Einträge | so viele verschiedene Fremdfunktionen werden gerufen |

**Analysepunkt:** Die Zahlen passen zusammen. Eine kleine Schnittstelle, ein
großer Körper, viel vorab reservierter Speicher, eingebettete Fremdbibliotheken.
Das ist das Bild einer ausgereiften, eigenständigen Audio-Engine.

---

## 29 · Jede Binärdatei genau beschrieben

Die App bringt **zwei** eigene native Bibliotheken mit, dazu die Java-Seite in
**einer** DEX. Hier jede genau.

### 29.1 Übersicht

| Datei | Art | Inhalt | Belegstelle |
|---|---|---|---|
| `lib/arm64-v8a/libpowerampcore.so` | Shared Object | die Engine | `elf-headers.txt`, `exports-*.txt` |
| `lib/arm64-v8a/libffmpeg_neon.so` | Shared Object | FFmpeg + Swresample + mbedTLS | `ffmpeg-exports-defined.txt`, `strings.txt` |
| `classes.dex` | Dalvik-Bytecode | die Java-Oberfläche | `README.md` (genau eine DEX, 7.496.480 B) |

### 29.2 `libpowerampcore.so` — Aufbau von oben nach unten

**Kopf und Segmente**

```
Typ:        ELF64, little endian, AArch64, DYN (Shared Object)
Segmente:   3 LOAD (1x RX, 2x RW), 9 Programmkopfe
Sektionen:  27
Einstieg:   0x0
Datei:      ~3,59 MB (Sektionskopfe bei 3588784)
```

**Sektionen mit Größe** (die wichtigen):

| Sektion | Größe | Anteil |
|---|---|---|
| `.text` | 2.292.076 B | 64 Prozent der Datei |
| `.rodata` | 371.610 B | Konstanten, 14.814 Strings |
| `.eh_frame` | 453.068 B | C++-Abwicklung |
| `.gcc_except_table` | 99.320 B | Ausnahmen |
| `.data.rel.ro` | 46.576 B | vtables |
| `.bss` | 5.693.360 B | **nicht** in der Datei, aber im Speicher |
| `.rela.plt` | 10.848 B | 452 Einträge |
| `.dynsym` | 12.600 B | 525 Einträge |

**Öffentliche Fläche:** genau **16** Symbole (`JNI_OnLoad/OnUnload`, die
`internal_*`- und `pa_*`-Funktionen). Alles andere ist versteckt.

**Importe (524 Symbole):** Android (MediaCodec/Extractor über `libmediandk`,
Assets, Bitmap, Surface), OpenSL ES, EGL/GLES (Visualizer), zlib, **FFmpeg**
(`av_*`, `swr_*`), **mbedTLS**, System (mmap, sched, pthread).

**Statisch eingebaut:** libopenmpt (MOD), TagLib (Mobile-Fork), Milkdrop
(Mobile-Fork) mit EEL2, LuaJIT 2.1.0-beta3, WavPack, Musepack, libc++/libcxxabi.

**Sonderheiten:** die Sektion `__lcxx_override` (libc++), beide Hash-Tabellen
(`.gnu.hash` und `.hash`), `stripped` (17.122 Funktionen ohne Namen).

**Kurz gesagt:** ein großes C++-Programm mit einer 16-Tür-Schnittstelle, das
seine Fremdbibliotheken (außer FFmpeg) selbst mitbringt.

### 29.3 `libffmpeg_neon.so` — Aufbau

Belegt durch `ffmpeg-exports-defined.txt` (130 definierte Exporte) und Strings:

**Version und Art**

```
Versionsstring:  "Lavf/58.27.103 Poweramp"
Bedeutung:       Eigenbau von FFmpeg (Lavf 58.x = FFmpeg-4.2-Zeit),
                 Konfigurationsname "Poweramp"
Art:             reine Audio-Bibliothek (kein Video-Encoding)
Prozessor:       NEON-optimiert (ARM)
```

**Was exportiert wird (130 Einträge), nach Gruppen:**

| Gruppe | Beispiele | Anzahl |
|---|---|---|
| **avformat** | `avformat_open_input`, `av_read_frame`, `av_seek_frame`, `av_find_input_format`, `av_register_all`, `avio_*` | rund 20 |
| **avcodec** | `avcodec_decode_audio4`, `avcodec_find_decoder`, `avcodec_open2`, `avcodec_flush_buffers` | rund 10 |
| **avutil** | `av_malloc`, `av_dict_*`, `av_frame_unref`, `av_packet_unref`, `av_rescale_q`, `av_rdft_*` (FFT), `av_sha_*` (SHA-1), `av_base64_*` | rund 35 |
| **libswresample** | `swr_alloc`, `swr_init`, `swr_convert`, `swr_get_delay`, `swr_get_out_samples`, `swr_drop_output` | 7 |
| **mbedTLS** | `mbedtls_cipher_*`, `mbedtls_pk_*` | 17 |
| **NEON** | `swri_oldapi_conv_flt_to_s16_neon` (Float zu S16 in NEON) | 1 |

**Demuxer (BSS-Objekte, `ff_*_demuxer`):** aac, aiff, ape, asf, dsf, flac, flv,
g722, g723_1, g729, iff, matroska, mov, mp3, mpc, mpc8, ogg, pcm (alaw, mulaw,
s8, u8, s16/u16/s24/u24/s32/u32 je big/little, f32/f64 je big/little, vidc),
tak, tta, wav, wv.

**Decoder (`ff_*_decoder`):** ape, mp2float, mp3float, mp3adufloat, mp3on4float.

**Kurz gesagt:** ein auf Audio reduzierter FFmpeg, der genau die Formate
mitbringt, die die Engine braucht, plus Swresample (fürs Umsamplen), FFT (fürs
Spektrum), SHA-1 (vermutlich für Prüfsummen) und mbedTLS (für Verschlüsselung).
Das `_neon` im Namen sagt: mit ARM-Vektorrechnung gebaut.

### 29.4 Wie die beiden Bibliotheken zusammenhängen

```
 libpowerampcore.so
     |  importiert av_*, swr_*, mbedtls_*        (dynamisch)
     v
 libffmpeg_neon.so
     |  importiert libc, libm, libz ...
     v
 libc.so, libm.so, libz.so

 libpowerampcore.so
     |  importiert AMediaCodec/Extractor, SL_IID_*, gl*, egl*
     v
 libmediandk.so, libOpenSLES.so, libjnigraphics.so, libEGL.so, libGLESv2.so

 libpowerampcore.so
     |  dlopen/dlsym zur Laufzeit
     v
 libaaudio.so (ab API 27), libaudioclient.so (AudioTrack),
 libutils.so (RefBase), libbluetooth_qti.so (BT-Codec)
```

**Analysepunkt:** Es gibt zwei getrennte Bibliotheken, und die Trennung ist
sinnvoll. **FFmpeg** ist groß, ändert sich oft und ist ein Fremdprojekt; es
bleibt **extern** und austauschbar. Die **eigene Engine** und die kleineren
Fremdteile (openmpt, TagLib, Milkdrop, LuaJIT, WavPack, Musepack) sind
**gebündelt**. So gibt es wenige Dateien, klare Herkunft und nur eine Stelle
(FFmpeg), die man unabhängig ersetzen kann.

### 29.5 Vergleich der beiden Bibliotheken

| Merkmal | libpowerampcore.so | libffmpeg_neon.so |
|---|---|---|
| Größe | ~3,59 MB | (separat, nicht im Handover vermessen) |
| Öffentliche Exporte | 16 | 130 |
| Zweck | Engine, DSP, Ausgabe, Decoder-Hülle | Demuxen, Dekodieren, Umsamplen |
| Fremdprojekte | openmpt, TagLib, Milkdrop, LuaJIT, WavPack, Musepack (statisch) | FFmpeg, Swresample, mbedTLS (statisch) |
| Version erkennbar | nein (stripped) | ja (`Lavf/58.27.103 Poweramp`) |
| Wird von wem benutzt | Java (per JNI) | libpowerampcore.so (dynamisch) |
| Besonderheit | 16-Tür-Schnittstelle, `dlsym` für AudioTrack/AAudio | reine Audio-Variante, NEON |

### 29.6 Was wir übernehmen

1. **Zwei Bibliotheken, nicht zehn.** Eine eigene Kernbibliothek plus eine
   austauschbare Fremdbibliothek. Kein Wildwuchs.
2. **Kleine öffentliche Fläche.** Nur die wirklich nötigen Exporte sichtbar.
3. **Fremdteile bündeln, Große extern.** Kleine Bibliotheken hineinbauen, die
   große (FFmpeg, Separierer) getrennt halten.
4. **Versionsstring setzen.** Bei uns: `Klangbild/1.0` und die FFmpeg-Version in
   `avcodec_configuration`. Das hilft bei Fehlersuche ungemein.
5. **NEON von Anfang an vorsehen.** Die Float-zu-S16-Wandlung ist der heiße
   Punkt; eine NEON-Variante spart messbar.
6. **Keine Pfad-Spuren.** `-ffile-prefix-map` beim Bauen.

---

## 30 · Die 189 verankerten Funktionen und ihre Zuordnung

Die Ghidra-Übergabe enthält **189 an Strings verankerte Funktionen**
(`// ==== FUN_xxxxxx @ xxxxxxxx ====`). Jede lässt sich über die
**Dateinamen-Strings** in ihrem Körper einem Quellmodul und damit einem Thread
zuordnen.

### 30.1 Die Methode

Ghidra hat die Namen gestrippt, aber die Absturz- und Log-Aufrufe enthalten
`__FILE__`-Strings (z. B. `"dsp_thread.c"`, `"decoder_thread.c"`,
`"aaoutput.c"`). Ich habe für jede Funktion geprüft, welche Dateinamen in ihrem
Körper vorkommen, und sie danach eingeordnet. Wo kein Marker im Körper steht,
bleibt die Zuordnung **offen** (ehrlich als „unbestimmt" geführt).

### 30.2 Ergebnisübersicht

| Klasse | Anzahl | Bedeutung |
|---|---:|---|
| **Decoder** | ~53 | Decoder-Thread, Decoder-Plugins, Tag/Scan |
| **DSP** | ~52 | DSP-Thread, Resampler, Reverb, Milk-DSP, Tempo, Ringpuffer |
| **Output** | ~13 | AAudio, OpenSL ES, AudioTrack, Cast (cc), Loader, Plattform |
| **Querschnitt** | ~11 | Pipeline, Nachrichten-Router, Plugin-Manager, Handler |
| **Visualizer** | ~4 | Milk-Renderer, Loader (EGL/GL) |
| **unbestimmt** | ~56 | meist Hilfs-/Fremdbibliotheksfunktionen (siehe 30.5) |
| **Summe** | **189** | |

### 30.3 Datei zu Thread (die Zuordnungsregel)

| Quelldatei | Thread/Klasse | Belegte Funktionen |
|---|---|---|
| `decoder_thread.c` | **Decoder** | `decoder_thread_run/_start`, Füllen, Backup-Decoder |
| `ffmpegdecoder2.c` | **Decoder** | `decoder_open/decode/seek`, `pamp_proto_*` |
| `amediadecoder.c` | **Decoder** | MediaCodec-Pfad |
| `moddecoder.c` | **Decoder** | MOD/libopenmpt |
| `mpcdecoder.c` | **Decoder** | Musepack |
| `wvdecoder.c` | **Decoder** | WavPack |
| `ScanDecode.cpp` | **Decoder** | `scan_decode_init`, `scan_with_decoder` |
| `ffmpegtagreader.c`, `tagreader.cpp` | **Decoder/Tag** | Metadaten lesen |
| `dirscanner.c`, `nativeutils.c` | **Decoder/Scan** | Ordner und Dateizugriff |
| `dsp_thread.c` | **DSP** | `dsp_thread_create/_run/_start`, `dsp_do_dsp_block`, alle `exec_*` |
| `pipeline.c` | **Querschnitt** | `pipeline_init`, `native_build/route_msg` |
| `resampler3.c`, `resampler_internal.c` | **DSP** | `resampler3_handle_msg`, `internal_set_resampler` |
| `mmaped_circular_buffer.c` | **DSP** | `mmapped_mapping_init`, ashmem |
| `ReverbDSPPlugin.cpp` | **DSP** | Reverb-Plugin |
| `MilkDSPPlugin.cpp` | **DSP** | Milk-Visualizer-DSP (Audio-Zubringer) |
| `tempo.c` | **DSP** | Tempo/Time-Stretch |
| `output_config.c` | **DSP/Output** | Ausgabekonfiguration |
| `aaoutput.c` | **Output** | AAudio-Ausgabe |
| `osloutput.c` | **Output** | OpenSL-ES-Ausgabe |
| `atoutput.c`, `audiotrack_direct.c` | **Output** | AudioTrack (direkt) |
| `ccoutput.c` | **Output** | Cast/Client-Ausgabe |
| `aaudio_loader.c` | **Output** | spätes Laden von AAudio |
| `audio_platform.c` | **Output** | Plattform-/Herstellererkennung |
| `msg_router.c`, `msg_handler.c` | **Querschnitt** | Nachrichten |
| `native_plugin_manager.c` | **Querschnitt** | Plugin-Liste |
| `MilkRendererJava.cpp`, `Loader.cpp` | **Visualizer** | EGL/GL-Zeichnen |

### 30.4 Die Funktionen nach Klasse (Adressen)

**Decoder (`decoder_thread.c`, `*decoder.c`, `ScanDecode.cpp`, Tag, Scanner)**

```
0036ee00 internal_register_decoder   00377e5c   00386adc   003897d0
00260d1c scan_with_decoder           00387608   0038c724   0038a7a4
00389e70   00388ef8   0038c354       00389fc8   00388808   00388720
0038874c   0038a930   0038a95c       0038a018   0038a100   0038a21c
0038a688   00389820   0038ba54       00389900   00384594   0037903c
003842c4   00387d74   0038b918       003859b8   00385cfc   00385cc0
00378bcc   00371e70 dirscanner       0036fedc nativeutils
0038c9e0   0038984c   00389cf4       0038b970   0038c080   0038c4bc
003871f4   00387318   003869a0       00386dd8   00386eb8   00386f80
0038651c   00385d38   00385f30       003841fc   0038455c   003791b4
```

**DSP (`dsp_thread.c`, Resampler, Reverb, Milk-DSP, Tempo, Ringpuffer)**

```
0025f424 MilkDSPPlugin                003989bc   0039a6cc   0039b214 resampler3
0039b458   0039b6bc   003958e0        00396720   0039a4d0
003893d8 ReplayGain                   00398ac8   00398b50   0039a470
003774f4 mmaped_circular_buffer      0039aba0   0039ad30   0039a294
00399fe0   003991f4   0039928c        00399420   00398d28   0039824c
003985f4   0039704c   00397260        00397358   00397704
00396e54   00396eac   00396f00        00396f54   003965dc
00395070   00395238   00394e6c        00394f44
00377870 internal_set_resampler      0036eed8 internal_register_dsp
0025e860   0025e8d8   0025e954        0025e9d0   0025ea4c   0025e1b4   (Reverb)
0025c8b8   0025c9ec   0025cb7c        (Reverb)
0025f50c   0025eb4c   0025ed4c        (Milk-DSP)
0039c210 tempo
```

**Output (`aaoutput.c`, `osloutput.c`, `atoutput.c`, `ccoutput.c`, Loader, Plattform)**

```
00315008 audiotrack_direct            00379308 audio_platform
0037ddd0 atoutput                     003928a4 aaudio_loader
003715b8 output_config                0037d8b8 osloutput
00390dc8 aaoutput                     0039369c ccoutput
0039279c aaoutput                     0037c080 osloutput
00393af0 ccoutput                     0037cb68 osloutput
0037171c output_config
```

**Querschnitt (Pipeline, Router, Plugin-Manager, Handler)**

```
0036f4dc pa_send_msg                  003734e0 pipeline
00373a70 pipeline                     00372e74 pipeline
003755e4 pipeline                     00374344 pipeline
00376850 msg_router                   00376658 msg_router
00376da8 msg_handler                  0036f7d8 native_plugin_manager
0036f660 native_plugin_manager
```

**Visualizer (Milk-Renderer, Loader)**

```
0023b5cc MilkRendererJava             0022c828 Loader.cpp
0023bb84 MilkRendererJava             0023afe0 MilkRendererJava
```

### 30.5 Die unbestimmten Funktionen (ehrlich benannt)

Rund 56 Funktionen haben **keinen** Dateinamen im Körper. Sie liegen fast alle in
zwei Adressbereichen, die zu den **eingebauten Fremdbibliotheken** gehören:

| Adressbereich | Vermutlicher Ursprung | Begründung |
|---|---|---|
| `0x23xxxx`, `0x24xxxx`, `0x25xxxx` | **LuaJIT / EEL2 / openmpt** | Lexer (`yy_scan_buffer`, "scanner input buffer overflow") |
| `0x26xxxx` | **ScanDecode / ffmpegdecoder** | `scan_with_decoder` liegt bei `0x260d1c` |

Beispiele: `00233828`, `002804d4`, `0023528c` (Flex-Lexer), `00280020`,
`00280854` (Parser), `00260ba4`, `00261fec`, `002621f0` (Nähe ScanDecode).

**Analysepunkt:** Diese Gruppe ist **kein Defekt der Analyse**. Sie zeigt, dass
die Fremdbibliotheken (LuaJIT, EEL2, openmpt) im selben `.text` liegen und keine
eigenen Dateinamen führen. Wer die Zuordnung vollständig will, müsste sie über
den Aufrufer (`key-functions.c`) statt über `__FILE__` bestimmen.

### 30.6 Was die Verteilung sagt

1. **Decoder und DSP sind etwa gleich groß** (~53 zu ~52). Das ist erwartbar:
   sechs Decoder und ein reichhaltiger DSP (EQ, Reverb, Milk, Tempo, Resampler).
2. **Output ist klein** (~13). Weil die vier Ausgabewege gemeinsame Helfer
   nutzen (`output_config.c`, `audio_platform.c`), verteilt sich die Arbeit.
3. **Der Querschnitt ist klein, aber zentral** (Pipeline, Router, Plugin-Manager).
   Wenige Funktionen, aber sie verbinden alles (Abschnitt 2 und 3).
4. **Der Visualizer ist winzig** (~4 verankerte). Der Großteil der
   Visualizer-Arbeit steckt in den Fremdbibliotheken (EEL2, LuaJIT) und in den
   `Milk*Plugin`-Funktionen, die unter „DSP" gezählt sind.

**Für uns die Lehre:** Die eigene Arbeit verteilt sich auf **Decoder** und
**DSP**. Genau dort sollten wir anfangen (siehe Checkliste 14 und Bauplan 10).
Der Output ist Fleißarbeit mit wenigen Wegen. Der Querschnitt (Pipeline, Router)
ist klein, aber die Grundlage.

### 30.7 Auflösung der unbestimmten Funktionen (über die Aufrufer)

Die zuvor „unbestimmten" Funktionen ließen sich fast alle über zwei zusätzliche
Belege zuordnen: **wer sie aufruft** und **wo sie im Adressraum liegen**.

**Methode.** Für jede Funktion habe ich die Aufrufstellen in `key-functions.c`
und `all-functions.c` gesucht. Ruft sie nur eine bekannte Funktion auf, erbt sie
deren Klasse. Zusätzlich hilft die Adressnähe: Die Engine-Teile liegen in
`0x36xxxx` bis `0x3cxxxx`, die Fremdbibliotheken in `0x22xxxx` bis `0x29xxxx`.
Wo beides zusammenpasst, ist die Zuordnung sicher.

#### Die wichtigsten Aufklärungen

| Funktion | Befund | Klasse |
|---|---|---|
| `FUN_00257b54` | von **vielen** `__cxa_atexit`-Funktionen gerufen | **C++-Laufzeit** (statischer Destruktor) |
| `FUN_0036d1f4` | `dlopen("/system/lib64/libaudioclient.so", …)` und `libutils.so` | **Output** (Bibliothekslader) |
| `FUN_003714b0`, `FUN_00371568` | gerufen mit `"aaoutput.c"/"osloutput.c"/"atoutput.c"/"ccoutput.c"` | **Output** (Ausgabekonfiguration) |
| `FUN_0022f3d0` | gerufen mit `"milk/lua/milk_main.lua"` | **Visualizer** (Lua-Lader) |
| `FUN_003788d4`, `FUN_003789ac` | aus `pipeline.c`; Zeiger als Callback | **Pipeline** |
| `FUN_00387028` | aus `ffmpegdecoder2.c` gerufen | **Decoder** |
| `FUN_0038960c` | aus `amediadecoder.c` gerufen | **Decoder** |
| `FUN_00377c20` | aus `dsp_thread.c` gerufen | **DSP** |
| `FUN_0036ea54` | aus `internal_set_resampler` (resampler_internal.c) gerufen | **DSP** |
| `FUN_0036efb0` | aus `ccoutput.c` gerufen | **Output** |
| `FUN_00233828`, `FUN_0023528c`, `FUN_002804d4` | Flex-Lexer (`yy_scan_buffer`) | **Visualizer/Fremd** (Lua/EEL) |
| `FUN_003c0f60` | `Subroutine does not return` (Abbruch) | **Laufzeit** |
| `FUN_0043c048`, `FUN_0045a988` | Bereich `0x43xxxx`/`0x45xxxx`, libc/libc++ | **Laufzeit** |

#### Die vollständige Nachzuordnung

| Adresse | Klasse | Beleg (Aufrufer oder Adressnähe) |
|---|---|---|
| `0036d1f4` | Output | `dlopen` von libaudioclient/libutils |
| `0036ea54` | DSP | Aufruf in `resampler_internal.c` |
| `0036efb0` | Output | Aufruf in `ccoutput.c` |
| `0036f3f0` | Querschnitt | Nähe `pa_send_msg`/Plugin-Manager |
| `0036d678` | Querschnitt | Nähe Plugin-Manager |
| `003708cc` | Querschnitt | Bereich `0x3708cc` (Pipeline/Output) |
| `003714b0` | Output | Aufrufe mit `*output.c` |
| `00371568` | Output | Aufrufe mit `*output.c` |
| `00371694` | Output | Bereich `0x371xxx` (`output_config`) |
| `003718dc` | Output | Bereich `0x371xxx` |
| `0037195c` | Output | Bereich `0x371xxx` |
| `00373f3c` | Querschnitt | Bereich `0x373f3c` (Pipeline) |
| `00374df4` | DSP | als Callback registriert (`FUN_00376020`) |
| `0037555c` | DSP | gerufen aus `FUN_00374df4` |
| `00377c20` | DSP | Aufruf in `dsp_thread.c` |
| `00378788` | DSP | Aufruf im `0x37xxxx`-Bereich |
| `003788d4` | Querschnitt | Aufruf in `pipeline.c` |
| `003789ac` | Querschnitt | Callback von `FUN_003788d4` |
| `0037b00c` | Querschnitt | als Funktionszeiger registriert |
| `0037dc8c` | Output | Nähe `atoutput` (`0x37ddd0`) |
| `0037ff6c` | Output | Bereich `0x37fxxx` (Ausgabe) |
| `00380034` | Decoder | Bereich `0x380xxx` (Decoder) |
| `00387028` | Decoder | Aufruf in `ffmpegdecoder2.c` |
| `003886d0` | Decoder | Bereich `0x388xxx` (Decoder) |
| `0038960c` | Decoder | Aufruf in `amediadecoder.c` |
| `003a17ec` | DSP | Dispatch im `0x3axxxx`-Bereich |
| `003a2194` | DSP | Dispatch im `0x3axxxx`-Bereich |
| `00260ba4` | Decoder | Bereich `0x260xxx` (ScanDecode) |
| `00261fec` | Decoder | Bereich `0x261xxx` (ScanDecode) |
| `002621f0` | Decoder | Bereich `0x262xxx` (ScanDecode) |
| `0026e944` | Decoder | Aufrufe im Scan-Bereich (`0x26xxxx`) |
| `0022e6f8` | Visualizer | lädt `milk/lua/milk_main.lua` |
| `0022f3d0` | Visualizer | Lua-Lader |
| `00233594` | Visualizer/Fremd | Lexer-Bereich `0x23xxxx` |
| `00233828` | Visualizer/Fremd | Flex-Lexer |
| `00234ae0` | Visualizer/Fremd | gerufen aus `00233828` |
| `00234b80` | Visualizer/Fremd | Lexer-Bereich |
| `00234f68` | Visualizer/Fremd | Lexer-Bereich |
| `0023528c` | Visualizer/Fremd | Flex-Lexer |
| `002364c4` | Visualizer/Fremd | gerufen aus `0023528c` |
| `00236564` | Visualizer/Fremd | Lexer-Bereich |
| `00236a0c` | Visualizer/Fremd | Lexer-Bereich |
| `00280020` | Visualizer/Fremd | Parser-Bereich `0x28xxxx` |
| `002800cc` | Visualizer/Fremd | Parser-Bereich |
| `002804d4` | Visualizer/Fremd | Flex-Parser |
| `00280854` | Visualizer/Fremd | gerufen aus `002804d4` |
| `00257b54` | **Laufzeit** | statischer Destruktor (viele Aufrufer) |
| `003c0f60` | **Laufzeit** | Abbruch (`does not return`) |
| `0043c048` | **Laufzeit** | libc++-Bereich |
| `0045a988` | **Laufzeit** | libc/libc++-Bereich |
| `00308200` | Decoder (unsicher) | Dispatch über Nachrichten-Id `0x16` |

**Nicht sicher zuordenbar bleiben etwa 5 Funktionen** (`00308200`,
`0026e944` und drei Verwandte). Sie liegen zwischen den Bereichen und haben
keinen eindeutigen Aufrufer. Ich führe sie offen, statt zu raten.

### 30.8 Korrigierte Verteilung (nach Nachzuordnung)

| Klasse | vorher | nachher |
|---|---:|---:|
| **Decoder** (inkl. Scan/Tag) | 53 | **~62** |
| **DSP** (inkl. Resampler/Reverb/Tempo) | 52 | **~59** |
| **Output** (inkl. Lader/Config) | 13 | **~22** |
| **Querschnitt** (Pipeline/Router/Plugins) | 11 | **~18** |
| **Visualizer/Fremdbibliothek** (Lua/EEL) | 4 | **~18** |
| **C++-Laufzeit** | 0 | **4** |
| unsicher | 56 | **~5** |
| **Summe** | 189 | **189** |

### 30.9 Was die Nachzuordnung lehrt

1. **Der `__FILE__`-Marker ist die beste Spur, aber nicht die einzige.** Rund 50
   Funktionen ließen sich erst über ihre **Aufrufer** zuordnen.
2. **Die Adressbereiche sind verlässlich.** Engine `0x36` bis `0x3c`,
   Fremdbibliotheken `0x22` bis `0x29`. Das allein klärt schon viele Fälle.
3. **Manche Funktionen gehören keinem Thread.** Die vier
   **C++-Laufzeit**-Funktionen (z. B. der statische Destruktor `00257b54`) sind
   keine Engine-Teile. Sie in einen Thread zu zwingen, wäre falsch.
4. **Der Output ist größer, als er aussah** (~22 statt ~13), weil viele
   gemeinsame Helfer (`output_config.c`, Bibliothekslader) dazukommen. Das
   bestätigt Abschnitt 5: Die Ausgabe ist mehr Arbeit, als die vier Wege
   vermuten lassen.

**Für uns die Lehre:** Wer die eigenen Funktionen später einsortiert, sollte
denselben Weg gehen: zuerst die Log-/Datei-Marker, dann die Aufrufer, dann die
Adressbereiche. Und Funktionen, die zu keiner Gruppe gehören (Laufzeit,
Fremdcode), **nicht** hineinzwingen, sondern getrennt führen.

### 30.10 Präzisierung mit der String-Querverweistabelle

Die Datei `native/ghidra/string-xrefs.tsv` ist die **beste Quelle** für die
Zuordnung. Sie listet 335 engine-relevante Strings und für jeden die Funktion,
die ihn benutzt. Damit erkennt man eine Funktion an ihrem **Inhalt**, nicht an
der Nachbarschaft. Das hat mehrere frühere Vermutungen korrigiert.

#### Die Beweise je Funktion (Auszug, vollständig zuordenbar)

| Funktion | Beweis-String (wörtlich aus der Tabelle) | Klasse |
|---|---|---|
| `FUN_00315008` | `_ZN7android11AudioSystem10getLatencyEiPj` | **Output** |
| `FUN_003734e0` | `%s() dsp_thread`, `%s() not an output plugin=%d` | Querschnitt (Pipeline) |
| `FUN_00377e5c` | `open_decoder_or_release`, `Trying backup decoder=%s`, `output resampler required` | **Decoder** (decoder_thread.c) |
| `FUN_00379308` | `FLAG_NEEDS_DEEP_BUFFER android_sdk=%d`, `isOnePlusOrOppo`, `MIUI`, `moto !FLAG_SUPPORTS_SPEAKER` | **Output** (audio_platform.c) |
| `FUN_00386adc` | `PACKET_TYPE_SEEK_RES`, `pamp_proto_seek` | **Decoder** (ffmpegdecoder2.c) |
| `FUN_00387028` | (gelistet unter `ffmpegdecoder2.c`) | **Decoder** |
| `FUN_00372e74` | `callbackOnDecoderOpened`, `callbackOnDecoderOpenFailed`, `callbackOnDecoderClosed`, `callbackOnSeeked` | **Decoder** |
| `FUN_00377c20` | `decoder_thread_request_seek` | **Decoder** |
| `FUN_003788d4` | `decoder_thread_start` | **Decoder** |
| `FUN_003789ac` | `decoder_thread_run` | **Decoder** |
| `FUN_00378788` | `decoder thread` | **Decoder** |
| `FUN_0037903c` | `plugin_handle_msg` (und `decoder_thread.c`) | **Decoder** |
| `FUN_00374df4` | `exec_on_decoder_opened_msg`, `exec_on_dsp_track_started`, `exec_on_dsp_track_ended_or_faded` | **Decoder** (Exec) |
| `FUN_00308200` | `handle_dsp_band_coefs` | **DSP** |
| `FUN_00307d74` | `handle_dsp_equ_rebuild` | **DSP** |
| `FUN_0039a294` | `exec_decoder_opened` | **DSP** |
| `FUN_0039a470` | `exec_decoder_closed` | **DSP** |
| `FUN_0039a4d0` | `exec_decoder_failed`, `cc->serial=...` | **DSP** |
| `FUN_0039a588` | `exec_decoder_seeked` | **DSP** |
| `FUN_0039a6cc` | `exec_decoder_filled`, `DSP_STATE_PAUSING` | **DSP** |
| `FUN_00398d28` | `exec_seek`, `slot_0.serial`, `slot_1.serial` | **DSP** |
| `FUN_003989bc` | `process_decoder_seeked` | **DSP** |
| `FUN_00398ac8` | `process_post_decoder_seeked` | **DSP** |
| `FUN_00398b50` | `resume_or_pause_after_seek` | **DSP** |
| `FUN_0037555c` | `exec_on_dsp_seek_done` | **DSP** |
| `FUN_00396720` | `_dsp_thread_build`, `dsp_thread_run`, `open_output_and_init_buffers` | **DSP** |
| `FUN_003958e0` | `create_output_and_buffers`, `dsp_thread_create`, `request_dsp_blocks` | **DSP** |
| `FUN_00397358` | `dsp_do_dsp_block` | **DSP** |
| `FUN_00397704` | `dsp_block` | **DSP** |
| `FUN_00396f54` | `dsp_thread_get_int_param` | **DSP** |
| `FUN_0025e860` … `0025cb7c` | (gelistet unter `ReverbDSPPlugin.cpp`) | **DSP** |
| `FUN_0025f424`, `0025f50c`, `0025eb4c`, `0025ed4c` | (gelistet unter `MilkDSPPlugin.cpp`) | **DSP** |
| `FUN_0039b214` | `resampler3_handle_msg` | **DSP** |
| `FUN_0039b3c0`, `0039b458`, `0039b6bc` | `resampler3.c`, `Failed to init resampler` | **DSP** |
| `FUN_003774f4` | `mmaped_circular_buffer`, `%s() ashmem_create_region` | **DSP** |
| `FUN_0036f660` | `native_plugin_manager_init`, `.../NativePluginManager` | Querschnitt |
| `FUN_0036ea54` | `register_plugin_internal`, `%s bad plugin name=...` | Querschnitt |
| `FUN_0036f3f0` | `plugininterface_init` | Querschnitt |
| `FUN_0036efb0` | (gelistet unter `plugininterface-internal.c`) | Querschnitt |
| `FUN_0036f4dc pa_send_msg` | `%s() bad msg plugin_id` | Querschnitt |
| `FUN_00376da8` | `%s() bad handle_msg call for=%s(%d)` | Querschnitt |
| `FUN_00376850` | `%s() %s subsystem not found for plugin.type=%d` | Querschnitt |
| `FUN_00376658` | `register_subsystem_for_plugin_type` | Querschnitt |
| `FUN_00374344` | `PA_SIZEOF_PLUGIN_MSG=%zu vs byte_total_len=%d` | Querschnitt |
| `FUN_00373f3c` | `native_seek` | Querschnitt |
| `FUN_003755e4`, `0037ff6c`, `0037dc8c` | `plugin_handle_msg`, `GetPrimitiveArrayCritical` | Querschnitt |
| `FUN_003714b0` | `bad config_blob_msg ... using default safe output config` | **Output** |
| `FUN_00371568` | `output_buf_ms=%d dsp_bufs=%d ...` | **Output** |
| `FUN_003715b8` | `.../plugin/OutputInternalHelper` | **Output** |
| `FUN_00371694` | `!get_supported_devices for output plugin=%s` | **Output** |
| `FUN_0037171c` | `!get_options output plugin=%s` | **Output** |
| `FUN_003718dc` | `!get_sample_rates output plugin=%s` | **Output** |
| `FUN_0037195c` | `!get_sample_formats output plugin=%s` | **Output** |
| `FUN_0036e328` | `at_getMinBufferSize48` | **Output** |
| `FUN_0036d678` | `getMinBufferSize` | **Output** |
| `FUN_0036d1f4` | `lseek() failed for %s` (und `dlopen` von `libaudioclient.so`) | **Output** (Lader) |
| `FUN_0037b00c` | `FLAG_SUPPORTS_SPEAKER`, `PA_OUTPUT_CAP_SEEK_FAST_VOLUME` | **Output** |
| `FUN_00380034` | `frames_per_block=%d block ms=%f ... using_callback=%d` | **Output** |
| `FUN_0037c080` | `AudioManager.getProperty(OUTPUT_FRAMES_PER_BUFFER)` | **Output** |
| `FUN_0037d8b8` | `flush_buffers`, `!buffer_queue_itf` | **Output** |
| `FUN_0037ddd0` | `frames_per_block=... at_min_buf_frames=...` | **Output** |
| `FUN_00390dc8` | `AudioTrack.getMinBufferSize`, `num_bufs=%d at_min_buf_frames` | **Output** |
| `FUN_0039279c` | `flush_buffers_locked` | **Output** |
| `FUN_003928a4` | `AAudioStream_setBufferSizeInFrames`, `..._getBufferCapacityInFrames` | **Output** |
| `FUN_0039369c` | `.../output/cc/CcPluginService` | **Output** |
| `FUN_00393af0` | `frames_per_packet=%d bytes_per_packet=%d packet ms=%f` | **Output** |
| `FUN_00260d1c` | `scan_with_decoder`, `Trying first available decoder`, `resampleAndScaleAsNeeded` | **Decoder** (ScanDecode) |
| `FUN_00260ba4` | `.../decoder/ScanDecode` | **Decoder** |
| `FUN_003c0f60` | `Truncated bit buffer` | **Decoder** (Bitleser) |
| `FUN_003a17ec` | `seek.sync_samples`, `load.skip_plugins` | **Decoder** (OpenMPT) |
| `FUN_003a2194` | `render.resampler.emulate_amiga_type` | **Decoder** (OpenMPT) |
| `FUN_00384594` | `!avio_ctx_buffer`, `seekable`, `recv_buffer_size` | **Decoder** (ffmpeg) |
| `FUN_003893d8` | `replaygain_track_gain/album_gain/track_peak/album_peak` | **DSP** (ReplayGain) |
| `FUN_0038960c` | `replaygain_` | **DSP** (ReplayGain) |
| `FUN_0023b5cc`, `0023bb84`, `0023afe0` | `failed eglSwapBuffers err=%d` | **Visualizer** |
| `FUN_0022c828` | `failed eglCreatePbufferSurface` | **Visualizer** |
| `FUN_0022f3d0` | `loadLBuffer` (und `milk/lua/milk_main.lua`) | **Visualizer** (Lua) |
| `FUN_00233594` | `image buffer for '%s' invalid size %ld` | **Visualizer** (Bild) |
| `FUN_0026e944` | `GL_EXT_draw_buffers`, `GL_EXT_shader_framebuffer_fetch` | **Visualizer** (GL) |
| `FUN_00257b54` | `glDiscardFramebufferEXT` | **Visualizer** (GL) |
| `FUN_00233828`, `0023528c`, `002804d4` | `fatal error - scanner input buffer overflow`, `yy_scan_buffer` | **Fremd** (Flex-Lexer/Parser) |
| `FUN_002800cc`, `00236564`, `00234b80` | `yy_create_buffer` | **Fremd** (Flex) |
| `FUN_00280020`, `002364c4`, `00234ae0` | `yyensure_buffer_stack` | **Fremd** (Flex) |
| `FUN_00280854` | `scanner uses REJECT` | **Fremd** (Flex) |
| `FUN_002621f0` | `(Ljava/nio/ByteBuffer;I)[C` | Querschnitt (JNI) |
| `FUN_0045a988` | `([B)Ljava/nio/ByteBuffer;`, `java/nio/ByteBuffer` | Querschnitt (JNI) |
| `FUN_0043c048` | `NULL row buffer` | **Fremd** (Bild/Codec) |

#### Korrekturen an früheren Angaben

Diese Funktionen hatte ich vorher anders einsortiert. Die Tabelle oben ist die
**richtige** Fassung:

| Funktion | vorher | **richtig** | Beleg |
|---|---|---|---|
| `FUN_00257b54` | C++-Laufzeit | **Visualizer (GL)** | `glDiscardFramebufferEXT` |
| `FUN_0026e944` | Decoder (vermutet) | **Visualizer (GL)** | `GL_EXT_draw_buffers` |
| `FUN_00380034` | Decoder (vermutet) | **Output** | `frames_per_block ... using_callback=` |
| `FUN_0036d1f4` | Output (unsicher) | **Output (Lader)** | `lseek() failed` + `dlopen libaudioclient` |
| `FUN_0036efb0` | Output | **Querschnitt** | `plugininterface-internal.c` |
| `FUN_00377c20` | DSP | **Decoder** | `decoder_thread_request_seek` |
| `FUN_00378788` | DSP | **Decoder** | `decoder thread` |
| `FUN_003788d4` | Querschnitt/Pipeline | **Decoder** | `decoder_thread_start` |
| `FUN_003789ac` | Querschnitt/Pipeline | **Decoder** | `decoder_thread_run` |
| `FUN_00374df4` | DSP | **Decoder (Exec)** | `exec_on_decoder_opened_msg` |
| `FUN_0037555c` | DSP | **DSP (Exec)** | `exec_on_dsp_seek_done` |
| `FUN_00308200` | Decoder (unsicher) | **DSP** | `handle_dsp_band_coefs` |
| `FUN_00307d74` | — | **DSP** | `handle_dsp_equ_rebuild` |
| `FUN_003a17ec` | DSP (vermutet) | **Decoder (OpenMPT)** | `seek.sync_samples` |
| `FUN_003a2194` | DSP (vermutet) | **Decoder (OpenMPT)** | `render.resampler.emulate_amiga_type` |
| `FUN_003c0f60` | Laufzeit | **Decoder (Bitleser)** | `Truncated bit buffer` |
| `FUN_002621f0` | Decoder (Scan) | **Querschnitt (JNI)** | `(Ljava/nio/ByteBuffer;I)[C` |
| `FUN_0045a988` | Laufzeit | **Querschnitt (JNI)** | `([B)Ljava/nio/ByteBuffer;` |
| `FUN_0043c048` | Laufzeit | **Fremd (Bild/Codec)** | `NULL row buffer` |
| `FUN_0037ff6c`, `0037dc8c` | Output | **Querschnitt** | `plugin_handle_msg` |
| `FUN_00373f3c` | Querschnitt | **Querschnitt** | `native_seek` (bestätigt) |

**Damit sind nur noch zwei Funktionen offen:** `FUN_003708cc` (String
`native_fd_lseek`, also eine **Datei-Hilfsfunktion** → Querschnitt/Utils) und
`FUN_00261fec` (`!temp byte buffer size=%d` → Decoder/Scan). Beide haben jetzt
einen Beleg-String, sind also nicht mehr „unbestimmt".

### 30.11 Endgültige Verteilung (mit String-Beweisen)

| Klasse | Anzahl | Kernfunktionen (Beleg) |
|---|---:|---|
| **Decoder** | ~64 | `decoder_thread_*`, `decoder_open/decode/seek`, `scan_with_decoder`, `exec_on_decoder_*`, Tag/Scanner, OpenMPT |
| **DSP** | ~56 | `dsp_thread_*`, `dsp_block`, `exec_decoder_*`, EQ, ReplayGain, Resampler, Reverb, Milk-DSP, Tempo, Ringpuffer |
| **Output** | ~24 | `output_create`, `*output.c`, `getMinBufferSize`, `AAudioStream_*`, `getLatency`, Speicher/Hardware-Marker |
| **Querschnitt** | ~22 | `pipeline_*`, `msg_router_*`, `plugininterface_*`, `native_plugin_manager_*`, `native_seek`, JNI-Helfer |
| **Visualizer** | ~13 | `eglSwapBuffers`, `eglCreatePbufferSurface`, `GL_EXT_*`, `loadLBuffer`, Bild-Puffer |
| **Fremd** (Flex/Lua/EEL) | ~8 | `yy_scan_buffer`, `yy_create_buffer`, `yyensure_buffer_stack`, `REJECT`, `NULL row buffer` |
| **unsicher** | **0** | alle über einen String oder Aufrufer belegt |

**Analysepunkt:** Mit der String-Querverweistabelle ist **keine** Funktion mehr
unbestimmt. Jede entweder über einen eigenen Beweis-String oder über einen
eindeutigen Aufrufer. Das ist der Unterschied zwischen „Adressnähe" (Vermutung)
und „Beweis-String" (Fakt).

### 30.12 Die Methode in drei Stufen (für unsere eigene Analyse)

```text
 Stufe 1  Dateiname im Koerper (__FILE__)          -> sicher
 Stufe 2  Beweis-String aus string-xrefs.tsv        -> sicher
 Stufe 3  eindeutiger Aufrufer                      -> sicher
 Fallback Adressbereich (0x36..0x3c vs 0x22..0x29)  -> Vermutung
```

Wer später eigene Funktionen einsortiert, geht **in dieser Reihenfolge** vor.
Erst wenn alle drei Stufen nichts liefern, ist eine Funktion wirklich offen.

---

## 31 · Quellen

- Privates Handover-Repo `Adilinu94/poweramp-java-handover` (nur Studium):
  `README.md`, `native/exports-defined.txt`, `native/key-strings.txt`,
  `java/sources/com/maxmpz/audioplayer/**`
- Poweramp ist proprietär (Max MP). Kein Code übernommen.
- Ergänzend, eigene frühere Dokumente: `PRODUKT-KLANGBILD.md`,
  `ARCHITEKTUR-KLANGBILD.md`, `ANDROID-AUTODJ-TOOLCHAIN-2026.md`

---

**Ein Satz zum Schluss:** Das Genie von Poweramp ist nicht ein Trick, sondern
die Disziplin, im Audiopfad nichts zu tun, was blockieren kann. Zwei Threads,
lock-freie Puffer, feste Blöcke, alles vorab reserviert, und pro Gerät die
richtige Puffergröße. Das ist der ganze Zauber, und genau den bauen wir nach,
mit eigenem Code und permissiven Bausteinen.
