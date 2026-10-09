# Klangbild — Roadmap (einzige gültige Fassung)

**Stand: 08.10.2026**
Diese Datei **löst die drei bisherigen Fahrpläne ab**:
`ARCHITEKTUR-KLANGBILD.md` §10 (Version 1–4) und §12 (Phase A–E),
`PRODUKT-KLANGBILD.md` §8f („Erste Version klein halten") und §16 (Phase A–E).
Die alten Abschnitte bleiben stehen, gelten aber nicht mehr.

**Grundsatz (ADR-011):** Erst ein **PC-Prototyp** prüft die Kernwette und
erzeugt die Hörprobe. Die Android-App kommt erst, wenn der Prototyp überzeugt.
Jede Phase endet an einem **Tor**: Ist das Kriterium nicht erfüllt, wird nicht
weitergebaut.

> **Ergänzung 08.10.2026:** Alle Schwellen sind **festgelegt** (vorher „Vorschlag"),
> jede Torprüfung hat eine **Baseline** und ein **Konfidenzintervall**. Neu ist
> **Phase 0.0** (Belege einsammeln, bevor der teure Test läuft) und **Plan C**
> für den Fall, dass EmbeddingGemma 2 an Musik scheitert. Code liegt in
> `prototyp/` (siehe `prototyp/README.md`).

---

## Überblick

| Phase | Ort | Ergebnis | Tor |
|---|---|---|---|
| **0** · Kernwette | PC | Wissen: Taugen Vektoren und Analyse für Musik? | Belege + Musiktest + Analysegenauigkeit |
| **1** · Auto-DJ offline | PC | gerenderter Mix (WAV/MP3) + Übergangsprotokoll | Hörtest mit 10 Personen |
| **2** · Validierung | Web | Landingpage mit Hörprobe, Warteliste | Tötungskriterien Produkt §15 |
| **3** · Engine-Spike | Android | zwei Decks auf Oboe, ein Gerät | 1 h ohne Aussetzer, Analysezeit gemessen |
| **4** · App V1 | Android | schlanker Player + Auto-DJ einfach | Abnahme alt „Phase C" |
| **5** · Übergangs-Engine | Android | Keylock, Bass-Tausch, Filter, Echo | Abnahme alt „Phase D" |
| **6** · Extras | Android | Energie-Reise, Wunsch in Worten, Stems | — |

Zuordnung zu den alten Phasen: A (Player) ist verkleinert in Phase 4
aufgegangen, B (Analyse) in Phase 0/1 (PC) und 3 (Port), C → 4, D → 5, E → 6.

---

## Phase 0 · Kernwette prüfen (PC)

Ziel: die zwei Annahmen testen, an denen das Produkt hängt. Kein UI, nur Skripte.

### 0.0 · Belege einsammeln (vor dem teuren Test, Stunden statt Wochen)

- **Musik-Benchmark lesen:** Der **MAEB** (Massive Audio Embedding Benchmark,
  30 Aufgaben, 50+ Modelle, Teil von MTEB) enthält **Musik-Aufgaben**. Für
  EmbeddingGemma 2 die Musik-Task-Ergebnisse auslesen oder die Aufgaben lokal
  laufen lassen. (Die Audio-Benchmark im Model Card, MSEB, deckt Sprecher, Intent,
  Umweltklänge und Bioakustik ab – **kein** Musik. Der Audio-Encoder ist als
  „speech and sound encoder" beschrieben, die Trainingsdaten nennen Sprache,
  Umweltklänge und akustische Events; **Musik ist nicht belegt**.)
- **Konfiguration festlegen** (danach nicht mehr wechseln, sonst ist das Tor
  nicht aussagekräftig):
  - nur **Text- und Audio-Encoder** laden (`vision_config=None`) → **570 M**
    Parameter statt 740 M (Stufen: 270 M Text, 440 M Text+Bild, 570 M Text+Audio,
    740 M alles);
  - Ausgabe **256 Dimensionen** (MRL), danach **re-normalisieren** – ein
    gekürzter, nicht normalisierter Vektor verschlechtert das Ranking still;
  - Rechnung in **bfloat16 oder float32**, **niemals float16** (NaN oder stille
    Verschlechterung);
  - **Task-Präfixe:** Audio **ohne** Präfix, Text **mit** symmetrischem Präfix
    (SentenceSimilarity bzw. Classification). Präfixe gelten nur für Text.
- **Tor:** Nur wenn das Musik-Ergebnis belegt (oder selbst gemessen) ist, läuft
  0.1. Sonst direkt zu **Plan C** (unten, dritter Punkt).

### 0.1 · Taugt EmbeddingGemma 2 für Musik?

- **Testsammlung:** `D:\Music\Chill` (501 Dateien). Davon 300 nach **Genre und
  Epoche geschichtet** auswählen; je Track drei Ausschnitte (Anfang, Mitte, Ende;
  je ca. 20 s, 16 kHz mono) einbetten, 256 Dimensionen, normalisiert.
- **Nachbarn:** 20 zufällige Songs, je die 5 nächsten Nachbarn **blind** bewerten.
- **Textsuche:** 20 Anfragen („ruhig", „treibend", „Gitarre", „zum Einschlafen")
  gegen die Audio-Vektoren, Top 5 bewerten.
- **Bewertung dreistufig** (passt / geht / passt nicht) plus Marke „Unfall",
  mindestens zwei Rater oder wiederholte Stichprobe. Jede Bewertung landet in
  `prototyp/ergebnisse/phase0-1-bewertungen.csv`.
- **Zufalls-Baseline:** dieselbe Bewertung mit fünf **Zufalls**nachbarn (gleiche
  Rater, gleiche Skala). Ohne Baseline ist eine Prozentzahl nicht lesbar.
- **Kontrollsatz:** unsinnige Anfragen („Elektrongaunersounds") dürfen **keine**
  guten Treffer liefern – sonst misst man nur Ähnlichkeit in der Bibliothek.
- **Tor (festgelegt):**
  - Nachbarn: höchstens **5 % „Unfall"** *und* mindestens **10 Prozentpunkte**
    über der Zufalls-Baseline;
  - Textsuche: **≥ 60 % „passt/geht"** bei sinnvollen Anfragen *und* **≤ 20 %**
    bei Unsinn;
  - jede Zahl mit **Wilson-Konfidenzintervall**; die untere Intervallgrenze muss
    den Schwellwert noch erreichen (bei 20 Fällen ist ein einzelner Fehler 5 Punkte).
- **Fällt das Tor:** drei Wege, in dieser Reihenfolge, jeder mit eigenem Eintrag
  statt stiller Umstellung:
  1. **Plan B – anderer Encoder (CLAP).** Lizenz **vor** Einsatz belegen: MuQ und
     MuQ-MuLan (CC-BY-NC 4.0) und OpenL3 (Gewichte nicht-kommerziell) scheiden
     aus, musicnn ist unklar. Für CLAP ist die Gewichts-Lizenz im Original-Repo
     zu prüfen; ein zweiter Blick auf die MRL-Tabelle (256d) lohnt sich.
  2. **Plan B' – eigenes Modell** auf permissiven Gewichten (eigener ADR,
     eigener Zeitplan; kein Schnellschuss).
  3. **Plan C – ohne Textsuche:** „klingt ähnlich" über eigene Merkmale
     (MFCC/Timbre-Statistik, Spektralmerkmale, Energie). Lizenzfrei, aber
     „Suche mit Worten" und „Stimmung" (ADR-015) fallen dann weg – das Produkt
     ändert sich, also braucht es ein eigenes ADR und einen Roadmap-Eintrag.

### 0.2 · Stimmt die Analyse? (Werkzeuge nach ADR-012)

- **Externe Testsätze statt nur eigener Annotation:** Harmonix-Set (912 Titel mit
  Beats, Downbeats, Struktur), GTZAN (nur Genre – hat selbst keine Beat-Labels;
  daher fair als Test, weil Beat This! ohne GTZAN trainiert ist), GiantSteps
  (Tonart). Ergänzend 20 eigene Tracks.
- **Branchen-Benchmark (neu 08.10.2026):** Der Standard für diese Aufgaben ist
  **MIREX** (music-ir.org), nicht MAEB – MAEB bewertet Audio-*Embeddings* und ist
  unter Phase 0.0 für EmbeddingGemma 2 vermerkt. MIREX führt die passenden Tasks
  **Audio Beat Tracking**, **Audio Downbeat Estimation**, **Audio Tempo**, **Audio
  Key Detection** und **Audio Structural Segmentation** mit festen Testsätzen
  (SMC, GTZAN; Ballroom, Hainsworth). Unsere Metriken folgen dem MIREX-Standard:
  Beat-Bewertung als **F-measure mit 70-ms-Fenster** (siehe `klangbild/metrics.py`),
  Tonart über exakte Treffer und relative Dur/Moll. So ist ein späterer
  MIREX-Vergleich direkt möglich, sobald ein Lizenz-freier Korpus belegt ist.
- **Lizenz-Gate (Recherche 08.10.2026, offen):** Keiner der drei Testsätze liefert
  für eine **geschlossene** App lizenzfreies Audio mit Tonart-/Takt-Labels.
  Harmonix stellt nur Mel-Spektren bereit (kein Audio) und hat keine Tonart-Labels;
  GTZAN hat nur Genre bei umstrittener Herkunft; GiantSteps-Audio sind kommerzielle
  Beatport-Ausschnitte. Ein Lader dagegen wird erst nach belegter, freier Lizenz
  gebaut – bis dahin bleibt dieser Punkt **Recherche**, nicht Automatisierung.
- **Messkette ohne Fremddaten prüfen (neu 08.10.2026):** `python -m klangbild
  metronom` (`klangbild/phase02.py`) rechnet BPM, Beat-F1 und Downbeat auf
  Metronomen mit bekannter Ground-Truth. Das belegt die Kette, ohne externe Labels.
  Für die Tonart prüft die Transpositionsprobe (`tests/test_keyestimate.py`) alle
  12 Dur- und Moll-Tonarten auf bekannten Dreiklängen.
- **Metriken selbst rechnen** (kein mir_eval nötig, Lizenzlage unklar):
  Beat-F1 mit ±70 ms Toleranz, Downbeat innerhalb ±1 Takt, Tonart **exakt** und
  **Camelot-Nachbar** getrennt.
- **Tor (festgelegt):** BPM innerhalb **±4 %** (oder exakter Oktav-Fehler
  anerkannt) bei **≥ 90 %**; Downbeat ±1 Takt bei **≥ 80 %**; Tonart exakt bei
  **≥ 50 %**, inklusive Camelot-Nachbar bei **≥ 70 %**. Jeder Wert mit
  Wilson-Intervall. Tracks unter der Schwelle bekommen ein niedriges Vertrauen
  und werden im Auto-DJ **nur überblendet**.

### 0.3 · Konsens-Pseudo-Labeling auf der eigenen Bibliothek (neu 08.10.2026)

**Idee:** Kein Gold-Label verfügbar (Lizenz-Gate, siehe 0.2), aber eine große
eigene Sammlung. Statt blockierter Fremddaten laufen **mehrere methodisch
verschiedene, freie Modelle** über dieselbe Datei:

- **eigener Schätzer** (`keyestimate.py`, Chroma + Key-Profile, reines numpy),
- [`deezer/skey`](https://github.com/deezer/skey) (MIT, selbstüberwacht, State
  of the Art ICASSP 2025) – *optional*,
- [`rekordcloud/openkeyscan`](https://github.com/rekordcloud/openkeyscan-analyzer)
  (MIT, CNN nach Korzeniowski, gibt Camelot/Open-Key) – *optional*,
- für Beat ergänzend `madmom` (BSD) neben `beat_this` – *optional*.

Wo Modelle sich **einig** sind (streng = identischer Camelot-Code, oder im
Camelot-Umfeld), entsteht ein belastbares Silber-Label. Wo sie **abweichen**,
sind genau die harten Fälle, die Phase 0.2 sucht. Das ist die etablierte
**Weak-Supervision**-Methode ohne Gold-Labels.

**Lizenz (ADR-012):** Interne Auswertung/Kalibrierung auf eigenen Dateien
verletzt das Gate nicht – das Gate regelt die *Auslieferung*. Pseudo-Labels
(„8A") sind Fakten, kein geschützter Inhalt; kein Audio wird ausgeliefert, kein
GPL-Werk gebündelt. Für Beat existieren zudem echte, MIT-lizenzierte
Annotationen ([beat_this_annotations](https://github.com/cpjku/beat_this_annotations):
GTZAN, Ballroom, Harmonix, RWC, JAAH …).

**Befehl:** `python -m klangbild konsens` (`klangbild/phase03.py`). Ohne
schwere Abhängigkeiten lauffähig (dann nur eigener Schätzer, ehrlich vermerkt).
Ergebnis: `ergebnisse/phase03-konsens.md` + `.json`, Abschnitt in
`python -m klangbild report`.

**Gemessen wird die Modell-Übereinstimmung, nicht die absolute Wahrheit.** Das
ist bewusst kein MIREX-Gold-Tor; es sagt „mein Schätzer stimmt auf X % der
Tracks mit zwei unabhängigen SOTA-Modellen überein". Für ein echtes MIREX-Tor
(Phase 0.2) braucht es weiterhin einen belegten, freien Korpus.

---

## Phase 1 · Auto-DJ offline (PC)

Ziel: Der Prototyp baut aus der Bibliothek ein Set und **rendert** es als
Audiodatei. Keine Echtzeit, kein Player. Das reicht für Hörtest und Hörprobe.

- **Planer:** Bewertung aus Harmonie (Camelot), Tempo, Klang-Vektor,
  Energie-Reise (Architektur §4). Tempo-Sprünge begrenzt auf ±3 %.
- **Übergang V1 (ADR-014):** Vinyl-Angleich per Resampling, Blende über 8 oder
  16 Takte, beginnt am Ende einer Phrase von A, landet auf einem Downbeat von B.
  Einfacher Bass-Tausch (Tiefpass/Hochpass im Takt). Lautheit per LUFS
  angeglichen.
- **Lautheit des Mixes:** **−14 LUFS integriert, True Peak ≤ −1 dBTP** (Referenz
  Streaming-Niveau), gemessen mit der eigenen BS.1770-Implementierung, die
  später identisch auf Android läuft (libebur128, MIT).
- **Ausgabe:** Mix-Datei plus Protokoll je Übergang (Songs, BPM, Tonart,
  Tempofaktor, Cue-Punkte, Grund der Wahl), damit Fehler zuordenbar sind.
- **Hörtest-Design:** 30 Minuten je Person, **blind** und mit **randomisierter
  Reihenfolge**; je Person drei Paare (Shuffle gegen Auto-DJ) und die Markierung
  jedes Übergangs als „Unfall". 10 Personen sind **richtungsweisend, nicht
  signifikant** – das steht so im Ergebnis, damit das Tor nicht überlesen wird.
- **Tor:** Mehrheit bevorzugt den Auto-DJ-Mix, und kein Übergang wird als
  „Unfall" markiert (Tötungskriterium „Hörprobe").

**Stack (festgelegt, alles lokal):** Python 3.13, numpy/scipy. Dekodierung über
**soundfile** (libsndfile ≥ 1.1, liest FLAC/MP3/WAV), Raten über **soxr** –
**einmal dekodieren**, dann 22,05 kHz für Beat This! und 16 kHz für
EmbeddingGemma 2 teilen. ffmpeg nur als Rückfall, falls soundfile ein Format
nicht liest (M4A). Tonart und Metriken sind **eigene Implementierungen**,
LUFS nach BS.1770 selbst (spiegelbildlich zu libebur128). Beat This! für
Beats/Downbeats, EmbeddingGemma 2 über **sentence-transformers ≥ 6.1.0**. SQLite
für Ergebnisse (Schema wie die spätere Android-DB, inklusive
`analysis_version`), Vektorsuche als Kosinus über numpy.

**Bewusst nicht genutzt:** **pedalboard** (Kern ist JUCE → GPLv3, würde
Android-Probleme kaschieren), librosa nur zu Vergleichszwecken außerhalb des
Audiopfads, mir_eval nicht (Lizenz unklar, Metriken sind selbst geschrieben).

**Lizenzregel für den Prototyp:** Er wird **nicht** weitergegeben, nur die
gerenderten Mixe. Trotzdem nur Werkzeuge nutzen, die später auch auf Android
erlaubt sind (ADR-012), damit die Ergebnisse übertragbar sind.

---

## Phase 2 · Validierung (Produkt §14)

- Landingpage mit Warteliste und der Hörprobe aus Phase 1.
- **Achtung Musikrechte:** Die öffentliche Hörprobe darf **keine** gekauften
  Songs enthalten. Dafür einen Mix aus **frei lizenzierter** Musik rendern
  (CC-BY / CC0; Quellen: Free Music Archive, ccMixter, Jamendo).
- **Pflicht dabei:** `prototyp/ergebnisse/hoerprobe-lizenzen.csv` mit
  Track, Interpret, Lizenz, Quell-URL je Titel; die Namensnennung steht auf der
  Seite neben dem Player. Gekaufte Musik verlässt den privaten Hörtest nie.
- **Weitergabe:** Der Prototyp selbst wird nicht weitergegeben, nur die
  fertigen Mixe (ADR-011).
- **Tor:** Tötungskriterien aus `PRODUKT-KLANGBILD.md` §15 (500 Besucher und
  unter 5 Anmeldungen = Stopp).

---

## Phase 3 · Android-Engine-Spike

Erst jetzt beginnt Android. Ziel: die technischen Unbekannten auf echter
Hardware messen.

- Oboe-Ausgabe mit zwei Decks und **einem** Callback (ADR-001, ADR-010), im
  Modus nach ADR-016. Resampler je Deck auf die Ausgaberate. **Vorlagenstudie zuerst:**
  Googles Beispiel `samples/OboeDJ` im Oboe-Repo (zwei Decks, Crossfader,
  Geschwindigkeitsfaktor, lineare Interpolation) zeigt genau diese Engine – es
  nutzt allerdings `LowLatency`, was ADR-016 bewusst abweicht.
- Die Engine hinter einem Media3-`Player` (ADR-017).
- **Analyse-Port:** Beat This! über `mosynthkey/beat_this_cpp` (MIT, C++ mit
  ONNX-Gewichten, chunked Inference) oder dessen Rust-Port; Modell **`small0`
  (~8,1 MB)** statt `final0` (~78 MB) prüfen. Einbettung über **LiteRT-LM**
  (ab v0.18.0 offiziell mit EmbeddingGemma-2-Audio, Kotlin und C++, MRL-Kürzung)
  statt über eine eigene ONNX-Konvertierung (ADR-006).
- **Messen** (Zahlen vor dem Spike festlegen, Vorschlag in Klammern):
  Analysezeit je Track (Beats, Key, LUFS, Einbettung) auf einem
  Mittelklasse-Gerät, hochgerechnet auf 8.000 Titel (≤ 2 s je Track, 8.000 Titel
  in ≤ 3 Nachtladungen); Akku- und Wärmeverhalten; **Aussetzer pro Stunde
  (< 1)** und Positionsgenauigkeit der Anzeige (`getTimestamp`, ADR-016).
- **Tor:** 1 Stunde Wiedergabe mit Übergängen ohne Aussetzer; die
  Erstanalyse ist im Hintergrund in vertretbarer Zeit fortsetzbar. Sonst
  Tötungskriterium „Technik".

---

## Phase 4 · App V1 (Android)

**Player, verkleinert:** Bibliothek über MediaStore (Ordner, Alben, Künstler),
Gapless, Queue, Benachrichtigung, Kopfhörertasten, Android Auto.
**Bewusst später (Soll statt Muss):** Tags schreiben (Scoped Storage, braucht
Zustimmung je Datei), Widget, Equalizer, Sleep-Timer.

**Auto-DJ einfach:** wie Phase 1, jetzt in Echtzeit. Eingreifen jederzeit
(„nächster", „mehr Energie", „ruhiger") mit Neuplanung.

**Abnahme (alt Phase C):** eine Stunde ohne hörbaren Fehler, Übergänge auf der
Taktgrenze, kein Netzwerkverkehr, Eingreifen ohne Abbruch.

---

## Phase 5 · Übergangs-Engine

Keylock mit Signalsmith Stretch (ADR-003) statt Vinyl-Angleich, größerer
Tempobereich, Filter-Sweep, Echo-Auslauf, Loops, Übergang vor dem Drop.

**Abnahme (alt Phase D):** Beatmatching hält zwei Songs im Raster bei gleicher
Tonhöhe; Bass-Tausch, Filter, Loop und Echo laufen stabil und sauber.

---

## Phase 6 · Extras

Energie-Reise über Stunden, Wunsch in Worten, Set benennen/erklären mit
Gemma 4 als optionalem Download (ADR-015), Stem-Trennung offline.

---

## Offene Messpunkte, die diese Roadmap schließt

| Offener Punkt | geschlossen in |
|---|---|
| Was sagen die Musik-Benchmarks (MAEB) über EmbeddingGemma 2? | Phase 0.0 |
| Taugen die Vektoren für Musik? | Phase 0.1 |
| Genauigkeit von BPM/Key/Downbeat | Phase 0.2 |
| Hören Menschen den Unterschied? | Phase 1 |
| Zahlbereitschaft / Interesse | Phase 2 |
| Rechenlast Analyse, Engine-Stabilität | Phase 3 |
| Ersatz, wenn EmbeddingGemma 2 an Musik scheitert | Plan C (eigenes ADR, Phase 0.1) |
