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
- **Lizenz-Gate (Recherche 08.10.2026):** Keiner der drei Testsätze liefert
  für eine **geschlossene** App lizenzfreies Audio mit Tonart-/Takt-Labels.
  Harmonix stellt nur Mel-Spektren bereit (kein Audio) und hat keine Tonart-Labels;
  GTZAN hat nur Genre bei umstrittener Herkunft; GiantSteps-Audio sind kommerzielle
  Beatport-Ausschnitte. **Gelöst über Phase 0.4 (FMAK):** echter Gold-Korpus mit
  Experten-Tonart-Labels (CC BY 4.0) und forschungsfreiem Audio; interner
  Vergleich verletzt das Gate nicht (Auslieferung, nicht Auswertung).
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

### 0.4 · Echtes Gold-Tor gegen FMAK (Labels frei, Audio forschungsfrei) (neu 08.10.2026)

**Idee (Nutzerwunsch):** Nicht nur Silber (Phase 0.3, Modellübereinstimmung),
sondern **Gold** — die Tonart *wirklich* gegen von Expert:innen bestimmte
Labels prüfen, um zu sehen, ob unser Weg das richtige Ergebnis trifft.

Der passende Korpus ist **FMAK** (Wong & Hernández, ISMIR 2023): **5.489
Lieder** (340 h, 17 Genres), Tonart von einem Konzertpianisten mit absolutem
Gehör bestimmt, kreuzannotiert mit hoher Übereinstimmung. Die **Labels** stehen
unter **CC BY 4.0**. Das Audio stammt aus der **Free Music Archive** — jede:r
Künstler:in hat die Lizenz selbst gewählt (die Metadaten sind CC BY 4.0, das
Audio „frei für nicht-kommerzielle Forschung").

**Lizenz-Einordnung (ADR-012), ehrlich abgegrenzt:** Das Lizenz-Gate regelt die
***Auslieferung***, nicht die **interne Auswertung**. Ein Gold-Tor lädt FMAK
lokal, rechnet unsere Tonart dagegen und notiert nur eine Trefferquote — nichts
wird ausgeliefert, kein GPL-Werk gebündelt, keine Audiodatei ins Repo. Genau so
arbeitet die MIREX-Bewertung. **Die FMAK-Dateien bleiben lokal** und sind in
`.gitignore` ausgeschlossen (nur Code + Ergebnis-Zahlen kommen ins Repo).

**Warum FMAK und nicht die blockierten Sätze aus 0.2:** Harmonix hat kein Audio
und keine Tonart, GTZAN nur Genre, GiantSteps-Audio ist kommerziell. FMAK ist
der erste Korpus mit **echten Experten-Tonart-Labels** *und* verfügbarem Audio.

**Datenformat (empirisch am echten Download belegt, mirdata-Referenz):**
- Labels `fmakv2.csv`: Spalten `key_and_mode` (z. B. „F# Major", „Bb minor"),
  `track_id` (Integer), `spotify_uri`. Kein separates Key/Mode — wird per
  `key_and_mode.split(" ")` geparst (mirdata `fma_keys.py`).
- Audio-Zuordnung `fma_keys_index.json`: `track_id → "<3 Ziffern>/<6-stellig
  zero-padded>.mp3"` + md5. Audio liegt in Zenodo-Zips je ID-Bereich
  (`000-019.zip` … `110-124.zip`); der kleinste Block (Ordner `000`) hat **51
  Tracks** — ein handhabbares Gold-Subset.

**Befehl:** `python -m klangbild gold` (`klangbild/phase04.py`). Lädt die
Labels (CSV, ~293 kB) und den Index (~622 kB) automatisch, erwartet das
**Audio-Subset lokal** (Pfad konfigurierbar), schätzt mit dem eigenen Chroma-
Schätzer und misst **exakte** und **Camelot-Nachbar**-Treffer mit
**Wilson-Intervall** gegen das 0.2-Tor (exakt ≥ 50 %, Nachbar ≥ 70 %). Ergebnis:
`ergebnisse/phase04-gold.md` + `.json`, Abschnitt in `python -m klangbild
report`.

> Hinweis: FMAK-Musik ist teils „Internet-Lo-Fi"; das macht die Tonart-Erkennung
> **schwerer** als bei Studio-Mastern. Ein guter Score dort ist aussagekräftiger,
> nicht weniger. Fehlt Audio lokal, holt `gold --fmak-remote` es Track für Track
> per **HTTP-Range** aus `fma_small.zip` (der Host erlaubt Ranges) und legt es
> lokal ab – kein 7,6-GB-Volldownload nötig. Einmal geholt, bleibt es lokal.

---

## Phase 0.5 · Tonart-Schätzung verbessert (an FMAK gemessen)

Auslöser: Phase 0.4 zeigte auf n=400 **exakt 43,8 %** (Krumhansl-Profil allein),
das 0.2-Tor (exakt ≥ 50 %) war verfehlt. Statt weiter zu raten, wurde **jede
Kandidat-Verbesserung gegen denselben FMAK-Goldsatz gemessen** (n=400, exakt und
Camelot-Nachbar, Tor = Wilson-Untergrenze). Die Messung entschied, nicht die
Annahme.

**Was half (gemessen, in `klangbild/keyestimate.py` übernommen):**

| Veränderung | exakt | Nachbar | Bewertung |
|---|---|---|---|
| Basis (Krumhansl, keine Frame-Norm) | 43,8 % | 68,0 % | Ausgang |
| Frame-Normierung (jeder Frame auf 1) | 47,2 % | 70,2 % | **+3,4 pp**, übernommen (Vorgabe `norm_frame=True`) |
| Ensemble-Profil (Mittel Krumhansl/Aarden/Temperley) | 46,2 % | 70,0 % | **+2,4 pp**, übernommen (Vorgabe `profile="ensemble"`) |
| **Frame-Norm + Ensemble** | **48,2 %** | **73,5 %** | **+4,4 pp**, neuer Standard |

Die beiden Gewinner **addieren sich fast vollständig** (48,2 % liegt über jedem
Einzelwert) – ein Zeichen, dass sie unabhängige Fehler beheben, nicht auf
denselben Tracks. Der echte Produktionslauf (`python -m klangbild gold`)
bestätigt das Experiment auf die Nachkommastelle: **48,2 %**.

**Was schadete (bewusst verworfen, als Warnung im Code-Docstring vermerkt):**
log-Kompression **−25,3 pp** (18,5 %!), harmonische Oktaven-Verstärkung leicht.
Das belegt: „mehr Signal-Verarbeitung" ist nicht automatisch besser – nur die
Messung trennt Fortschritt von Rückschritt.

**Nebeneffekt:** Die **„weit"-Fehler** (völlig daneben) fielen von 24 % auf
16,5 %, und die Nachbar-Wilson-Untergrenze steht mit 69,0 % Haaresbreite am
70 %-Tor. Verankert durch zwei Regressionstests (`tests/test_keyestimate.py`).

> Tor-Status nach Phase 0.5: exakt 48,2 % (UG 43,4 %) und Nachbar 73,5 % (UG
> 69,0 %) – **beide Tore noch nicht** erfüllt, aber deutlich näher. Der nächste
> Hebel ist die Modus-Verwechslung (Dur/Moll verwechselt), die im Fehlerbild
> weiterhin sichtbar bleibt.

---

## Phase 0.6 · Modus-Trennung (Dur/Moll) – Versuch, sauber negativ

Die Fehlerdiagnose (Phase 0.5) zeigte einen **echten, messbaren Mode-Bias**:
wir sagen 74× fälschlich **Dur** statt Moll, aber nur 47× umgekehrt. Die
Modus-Entscheidung stimmt in **69,8 %** der Fälle. Das ist ein naheliegender,
nicht-zirkulärer Hebel. Er wurde **gemessen** (FMAK n=400), statt angenommen.

**Geprüft und gemessen verworfen (alles gegen denselben Goldsatz):**

| Ansatz | exakt | Ergebnis |
|---|---|---|
| Basis (Phase 0.5) | 48,2 % | Ausgang |
| Terz-Energie (große/kleine Terz erzwingt Modus) | = 48,2 % | **0 Fixes** – zirkulär: nutzt dieselbe Chroma-Energie, die den Modus schon bestimmt hat |
| Globaler Dur→Moll-Bias (Sweep 0,01…0,10) | 45,8…48,0 % | repariert 2–6 Fälle, **zerschießt aber mehr** → netto **negativ** bei jedem Wert |
| Kosinus-Profil, Summen-Profil, eng gekoppelte Terz | ≤ 48,2 % | kein Gewinn |

**Warum der Bias scheitert (die eigentliche Erkenntnis):** Der Mode-Bias ist
real, aber **global nicht korrigierbar**. Im Chroma-Raum sind „richtig-Dur" und
„fälschlich-Dur" **nicht unterscheidbar** – ein Schwellenwert verschiebt das
Problem, statt es zu lösen (handelt einen richtigen Dur gegen zwei falsche ein).
Das belegt: Das Chroma-Profil-Verfahren hat bei **48,2 % exakt seine natürliche
Decke**. Die Modus-Verwechslung liegt **in der Repräsentation** (flaches Chroma
auf polyphoner Musik), nicht in einem behebbaren Parameter.

**Konsequenz (Entscheidung, nicht Schönfärberei):** Kein Bias oder Terz-Trick
wurde in den Code übernommen – er würde messbar verschlechtern. Wer die
Modus-Genauigkeit heben will, braucht **kein besseres Chroma-Profil**, sondern
eine andere Repräsentation (z. B. ein trainiertes Modell / der Konsens-Weg aus
Phase 0.3, der bereits auf der Bibliothek läuft). Das ist der ehrliche,
belegte Befund statt einer Schein-Verbesserung.

> Tor-Status unverändert: exakt 48,2 %, Nachbar 73,5 %. Phase 0.6 schließt die
> Frage „reicht ein feineres Profil? " mit einem **gemessenen Nein** und lenkt
> den nächsten Schritt auf den trainierten Modell-Pfad.

---

## Phase 0.8 · skey (gelerntes Modell) gegen denselben FMAK-Goldsatz

Phase 0.6 endete mit der These: „Die Tonart-Decke liegt nicht am Profil, sondern
an der **Repräsentation** – ein *gelerntes* Modell könnte sie durchbrechen." Diese
Phase prüft die These, statt sie zu behaupten. `skey` (Deezer, **MIT**) ist ein
kleines CNN (HCQT → ChromaNet), das seine Tonart-Gewichte *gelernt* hat statt
handgeschriebene Profile zu nutzen.

**Messkette 1:1 (ADR-012):** derselbe Goldsatz (FMAK, n=400), dieselbe Metrik,
dieselben Tore, dasselbe Wilson-Intervall – nur der Schätzer ist skey statt unseres
Chroma-Profils. Alles Wiederverwendete (Goldlader, Fehlerklassen, `auswerten`) kommt
aus `phase04`. Damit ist „besser" belastbar, nicht anekdotisch.

**Ergebnis (n=400, `python -m klangbild phase08`, auf CPU deterministisch):**

| Kennzahl | unser Profil (Phase 0.5) | **skey (Phase 0.8)** | Δ | Tor | erreicht? |
|---|---|---|---|---|---|
| exakt | 48,2 % | **58,8 %** | **+10,5 pp** | 50 % (Wilson-UG ≥ 50 %) | **JA** (UG 53,9 %) |
| Nachbar | 73,5 % | **82,2 %** | **+8,8 pp** | 70 % (Wilson-UG ≥ 70 %) | **JA** (UG 78,2 %) |

Δ rechnet der Bericht selbst aus den Artefakten (`phase04-gold.json` gegen
`phase08-skey.json`), es steht nicht als Zahl im Code – beide Deltas sind
Differenzen der *ungekürzten* Quoten (235/400 − 193/400 = 10,5 pp,
329/400 − 294/400 = 8,8 pp), nicht der gerundeten Anzeigewerte.

**Belastbar:** Der Vergleich entscheidet nicht am Punktwert, sondern an der
*Untergrenze* des Wilson-Intervalls (wie Phase 0.2/0.4). skey liegt mit **UG 53,9 %
über der 50-%-Schwelle** und mit **UG 78,2 % klar über 70 %** – beide Tore sind
nicht knapp, sondern mit Abstand erfüllt. Damit ist der trainierten-Modell-These
aus Phase 0.6 **zum ersten Mal ein Messwert zugeordnet, der beide Tore reißt**.

**Wo skey liegt (Fehlerklassen, n=400):** exakt 58,8 % · quint 15,5 % ·
weit 11,0 % · diagonal 6,8 % · modus 8,0 %. Auch ein gelerntes Modell verwechselt
vor allem Quint-Nachbarn und Modus – dieselben Schwierigkeiten wie unser Profil,
nur auf deutlich höherem Niveau.

**Lizenz & Abhängigkeiten (ADR-012, Lizenz-Gate):** skey = **MIT** (Deezer,
permissiv, passiert das Gate). Abhängigkeiten: torch, torchaudio, tqdm, einops,
**nnAudio**, soundfile – **kein librosa**, keine GPL-Nachbarschaft. skey liest per
torchaudio mit soundfile-Backend (MP3-fähig) und berechnet die HCQT per nnAudio.
Interner Messlauf; die Auslieferung regelt weiterhin das Lizenz-Gate.

**Konsequenz für den Plan:** Phase 0.2 hat einen tragfähigen Tonart-Schätzer.
Phase 1 kann auf **skey** als Produktions-Schätzer bauen (oder auf einen eigenen,
später trainierten Ersatz). Unser eigenes Chroma-Profil bleibt als
lizenz-/abhängigkeitsfreie Basis für PC-und-Android-Einheitlichkeit (ADR-012), aber
die Genauigkeitsspitze kommt aus dem gelernten Modell.

Befehl (interne Auswertung, nichts ausgeliefert):

```bash
python -m klangbild phase08 --limit 5   # Rauchtest
python -m klangbild phase08             # voller Lauf auf n=400
```

Ergebnisse landen in `ergebnisse/phase08-skey.{json,md,tracks.csv}`. Die Tore
(exakt ≥ 50 %, Nachbar ≥ 70 %, als **Wilson-Untergrenze**) sind dieselben wie in
Phase 0.2/0.4 — erfüllt nur, wenn die Untergrenze, nicht bloß der Punktwert, darüber
liegt.

> Tor-Status: exakt 58,8 % (UG 53,9 %) und Nachbar 82,2 % (UG 78,2 %) — **beide
> Tore erfüllt**. skey (MIT, Deezer) ist damit der Nachfolger-Kandidat für die
> Produktions-Tonartschätzung. Ausliefer-Entscheid (Lizenz-Gate ADR-012): MIT ist
> permissiv, passiert das Gate; die Auslieferung selbst (Modelldatei 0,7 MB) ist
> separat zu prüfen. Nächster Schritt: skey als Standard-Schätzer andocken und
> das Chroma-Profil als Offline-Fallback behalten.

---

## Phase 0.9 · Beat This! auf Tempo/Downbeat mit belastbarem n

Phase 0.2 hat Tempo, Beat und Downbeat an **7** Metronomen gemessen und beide
Tore als „erreicht" geführt. Das hielt einer Prüfung nicht stand — und genau das
ist der Grund für diese Phase:

| | Phase 0.2 | Problem |
|---|---|---|
| Fälle | 7 (nur 4/4) | 7/7 Treffer → Wilson-**UG 64,6 %**, Tor aber 90 % |
| Tor-Entscheid | am **Punktwert** (`zaehler/n >= schwelle`) | „erfüllt" hing am Zufall, nicht an der Belastbarkeit |

Mit n=7 ist **ein einziger Fehler 14 Punkte**. Die Aussage „Tempo-Tor erreicht"
war eine Punktwert-Aussage, keine belastbare — während Phase 0.4 und 0.8 längst
an der Untergrenze entscheiden. Diese Phase korrigiert genau diesen Bruch, ohne
die Messkette zu wechseln:

```bash
python -m klangbild phase09 --limit 12 --bpm-stufen 2 --sekunden 10  # Rauchtest
python -m klangbild phase09             # voller Lauf: 67 Tempi x 6 Taktarten
```

Zwei Dinge sind gegenüber Phase 0.2 geändert, beides bewusst:

1. **n groß genug, dass die Untergrenze trägt** — 67 Tempi × 6 Taktarten (n=402).
   Das Tempo-Raster ist **logarithmisch** plus feste Anker: Tempo-Verwechslung ist
   eine Oktavfrage (60 gegen 120). Ein lineares Raster von 60–180 lässt 120 auf
   122,45 fallen — die häufigste Verwechslung läge *zwischen* den Messpunkten und
   wäre damit gar nicht gemessen.
2. **Mehrere Taktarten** (3/4, 4/4, 5/4, 6/4, 7/4, 9/4). Downbeat ist
   taktabhängig; wer nur 4/4 prüft, prüft den leichtesten Fall und hält ihn für
   das Ganze. Eine Gesamtquote würde das verstecken, darum die Aufschlüsselung.

Alles Wiederverwendete (Ground-Truth-Bau, `beat_f1`, `bpm_richtig`,
`downbeat_richtig`, `wilson`) kommt aus `phase02`/`metrics` — nur n, Taktarten
und die Tor-Regel ändern sich.

**Echtes Ergebnis (voller Lauf, n=402 = 67 Tempi × 6 Taktarten, ~5 min, CPU):**

| Kennzahl | Treffer/N | Quote | Wilson 95 % | Tor (als UG) | erreicht? |
|---|---|---|---|---|---|
| Tempo richtig (±4 %) | 402/402 | 100,0 % | 99,1–100,0 % | ≥ 90 % | **JA** |
| Downbeat richtig (±1 Takt) | 387/402 | 96,3 % | 93,9–97,9 % | ≥ 80 % | **JA** |

- mittlere Beat-F1: 0,994

Beide Tore sind erreicht — und **an der Untergrenze**, nicht am Punktwert. Das ist
genau die Aussage, die Phase 0.2 nicht treffen konnte: dort waren beide Tore
„erreicht" auf 7 Fällen, wo 7/7 nur eine UG von 64,6 % ergibt.

Nach Taktart bleibt das Bild gleichmäßig — Downbeat trifft 65/67 in 3/4, 4/4 und
6/4 sowie 64/67 in 5/4, 7/4 und 9/4, Tempo ausnahmslos 67/67. Es gibt also keine
Taktart, die das Modell überproportional schwer hat (und auch keinen „4/4-Bonus").
Details: `ergebnisse/phase09-beats.{json,md,tracks.csv}`.

> Tor-Status: Tempo 100,0 % (UG 99,1 %) und Downbeat 96,3 % (UG 93,9 %) — **beide
> Phase-0.2-Tore erfüllt**, jetzt belastbar. Damit kann Phase 1 die
> Übergangs-Engine (ADR-014) auf gemessene Downbeats stützen statt auf eine
> n=7-Vermutung.

> **Grenze der Aussage (wichtig):** die Fälle sind **synthetische Metronome** —
> starres Tempo, ein Klang, kein Groove. Das ist der leichteste Fall. Die Tore
> belegen, dass Messkette *und* Modell auf bekannten Signalen richtig liegen,
> **nicht** dass Beat This! auf echter Musik so trifft. Für echtes Musik-Gold mit
> Beat-Labels braucht es ein lizenzfreies Korpus; das ist für Tempo genauso offen
> wie für Tonart (Lizenz-Gate ADR-012). Ebenfalls offen: **Tempo-Wechsel**
> (ritardando/accelerando), Groove-Swing und Live-Offset — alles Dinge, die ein
> starres Metronom nicht erzeugen kann.

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

**Phase 1.0 fertig — Auto-DJ-Engine gegen bekannte Ground-Truth gemessen (n=40):**

Die Engine (Planer, Vinyl-Resampling, Mix-Renderer) ist gebaut und wurde nicht
anegenommen, sondern **gemessen** — dieselbe Disziplin wie Phase 0.8/0.9. Als
Ground-Truth dienen **synthetische Sets mit bekanntem Tempo/Raster**: ein
musik-ähnliches Signal (Kick-Onset über getragenem Bett, realistischer
Crest-Factor ~12 dB statt eines nackten Klick-Zugs) mit exakt bekannten Beat- und
Downbeat-Positionen aus `phase02.baue_metronome`. Jeder Trial zieht **jeden**
Track auf das Tempo des Masters (durchgehend ein Raster, ADR-014) und rendert das
Set; ein Onset-Detektor misst danach das tatsächliche Beat-Raster im Mix.

| Kennzahl | Treffer/N | Quote | Wilson-UG | Tor (als UG) | erreicht? |
|---|---|---|---|---|---|
| Beat-Kontinuität (CV ≤ 0,03) | 40/40 | 100,0 % | 91,2 % | ≥ 90 % | **JA** |
| Tempo-Gate (≤ ±3 %) | 40/40 | 100,0 % | 91,2 % | ≥ 90 % | **JA** |
| Lautheit (−14 LUFS ±0,5, TP ≤ −1) | 40/40 | 100,0 % | 91,2 % | ≥ 90 % | **JA** |

- mittlere Beat-CV im Mix: **0,0092** (max 0,0099) — das Raster bleibt über den
  ganzen Setübergang hinweg durchgehend; ein Galoppieren (das ADR-014 verhindern
  will) tritt nicht auf.
- Entscheidungen fallen an der **Untergrenze** des Wilson-Intervalls, nicht am
  Punktwert: 40/40 ergeben UG 91,2 %, sicher über dem 90-%-Tor. (Arithmetisch
  braucht ein perfektes k/n die UG n/(n+3,84); die daher n ≥ 35 — 40 Trials sind
  genau deswegen gewählt, damit das Tor überhaupt erreichbar ist.)
- **Determinismus:** der Planer ist pro Eingabe deterministisch; die n=40 Trials
  sind **40 echte, verschiedene** Renderings — jeder Trial verschiebt das
  Tempo-Zentrum (Sweep über die legale ±3-%-Bandbreite) und rotiert den
  Start-Track (→ anderer Master, andere Resampling-Richtungen). Kein Measurement
  wird 40× gezählt; das Intervall ist ehrlich.


**Grenze der Aussage (wichtig):** Die Tore belegen, dass **Messkette und Engine
auf bekannten synthetischen Signalen** korrekt liegen — Beat-Raster durchgehend,
Tempo innerhalb der Gate-Grenze, Lautheit auf dem Referenz-Niveau. Sie belegen
**nicht**, dass die Übergänge auf echter Musik gut *klingen*. Genau dafür ist das
**Hörtest-Design** oben (blind, randomisiert, „Unfall"-Markierung) der nächste
Schritt. Offen bleiben: echter Musik-Groove (die synthetischen Sets sind starr),
Tempo-Wechsel innerhalb eines Songs und die tatsächliche Hörqualität der
Bass-Tausch-Blende.

Befehle: `python -m klangbild phase10` (Messlauf, `--limit`/`--trials`),
`python -m klangbild plan` und `python -m klangbild mix` (auf echter Bibliothek).
Details: `prototyp/ergebnisse/phase10-autodj.{json,md,tracks.csv}`.
Abgedeckt durch `tests/test_plan.py`, `tests/test_resample.py`,
`tests/test_mix.py` (168 Tests grün).


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
| Genauigkeit von BPM/Key/Downbeat | Phase 0.2, Key in Phase 0.5 vertieft + Phase 0.8 (skey erreicht Tor) |
| Hören Menschen den Unterschied? | Phase 1 |
| Zahlbereitschaft / Interesse | Phase 2 |
| Rechenlast Analyse, Engine-Stabilität | Phase 3 |
| Ersatz, wenn EmbeddingGemma 2 an Musik scheitert | Plan C (eigenes ADR, Phase 0.1) |
