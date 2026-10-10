# Klangbild — DJ-Techniken, Stems, Markt und GitHub-Recherche

**Stand: 10.10.2026 · Recherche-Dokument (keine Entscheidung)**
Grundlage für Profi-Übergänge mit Stems. Entscheidungen daraus brauchen eigene
ADRs. Vorschläge dafür stehen in §10.

**Sicherheitsgrad** wie in `PROTOKOLLE.md` §10: *belegt* (Quelle steht dabei),
*Herstellerangabe* (nicht unabhängig geprüft), *offen* (muss gemessen werden).

---

## 0 · Kurzfassung (die fünf Fragen)

| Frage | Antwort |
|---|---|
| **Reichen die Infos, um Profi-Übergänge mit Stems zu bauen?** | **Für Techniken und Architektur ja.** Offen ist kein Wissen, sondern drei Messungen: Geschwindigkeit der Stem-Trennung auf dem Handy, Klang der Rezepte im Hörtest, Strukturerkennung auf echter Musik (§11). |
| **Gibt es fertige Lösungen?** | **Ja, aber nicht für Android und eigene Dateien.** Spotify Mix und Apple Music AutoMix machen DJ-Übergänge für Streaming. djay hat Automix mit Stems (Neural Mix), belegt für iOS, für Android unklar. Auf GitHub ist **nichts produktionsreif**: Alle 13 Repos sind Prototypen mit 0–1 Sternen (§7). |
| **Lohnt sich die App?** | **Nur mit Stems als Kern.** Normale Übergänge (EQ, Filter, Echo, Loop) sind seit 2025 Standard in Streaming-Abos. Die Nische ist „Stem-Automix für eigene Dateien, offline, ohne Abo, auf Android". Sie ist echt, aber klein. Ein Android-Projekt genau dafür (Autobeat-DJ) wurde am 10.10.2026 archiviert. Tötungskriterien bleiben (§8). |
| **Was machen wir besser?** | Übergänge mit Stems (Drums zuerst, Gesang ohne Überlappung, **Tonart-Konflikte über Stems retten**), Cue-Wahl nach Struktur, eine **automatische Qualitätsprüfung jedes Übergangs** vor dem Abspielen, editierbar wie Spotify, plus Stem-Spuren (§9). |
| **Wichtigster neuer Befund** | Echte DJs lassen **Keylock an**: Nur 2,5 % der Titel werden transponiert (Kim et al. 2020). Unser Vinyl-Angleich ±3 % (ADR-014) verstimmt bis zu einen halben Halbton und **macht harmonisches Mischen zunichte**. Er sollte auf ±1 % begrenzt werden, oder Keylock kommt früher (§10). |

---

## 1 · Was Spotify Mix zeigt (Analyse deiner Screenshots)

Spotify „Mix" (Beta seit August 2025, nur Premium) ist ein **Spurenmodell pro
Übergang**. Jede Spur hat eine kleine Liste fertiger Kurven:

| Spur (Farbe) | Im Screenshot gewählt | Was die Kurve tut |
|---|---|---|
| **Lautstärke** (blau) | „Nahtloser Übergang" | S-Kurve: A von 1 auf 0, B von 0 auf 1 |
| **EQ** (gelb) | „Basswechsel in Übergangsmitte" | Bass von A fällt hart zur Mitte, Bass von B steigt hart zur Mitte |
| **Filter** (rosa) | „Hochpassfilter ausgehend" | Hochpass auf A, öffnet ab der Mitte bis zum Ende |
| **Effekte** (weiß) | „Echo (75 %) deaktivieren (Ende)" | Echo-Send auf A steigt ab der Mitte, Feedback 75 % |
| **Looping** (orange) | „2-Beat-Loop" (Auswahl 1/2/4/8/16 Beats) | Loop auf einem Abschnitt von A |

Voreinstellungen: „Automatisch", „Benutzerdefiniert", „Ausblenden" (laut Presse
auch „Rise"). BPM und Tonart werden angezeigt, die Übergänge werden mit der
Playlist gespeichert ([Spotify Support](https://support.spotify.com/ro-en/article/mixed-playlists/),
[RouteNote](https://routenote.com/blog/spotify-mix-customizable-transitions/)).

**Was Spotify fehlt (unsere Lücke):**
- **Keine Stems.** Alles läuft über EQ und Filter auf dem Gesamtsignal. Ein
  Bass-Cut per EQ nimmt die Kick mit, zwei Gesangsspuren überlagern sich.
- Ein kurzes Fenster pro Paar. Keine Brücke über mehrere Phrasen, keine
  Verlängerung eines zu kurzen Outros.
- Nur Streaming und nur mit Abo, keine eigenen Dateien.

**Folgerung:** Das Spurenmodell ist gut und bekannt. Wir übernehmen es als
**Datenformat** (§6) und erweitern es um **Stem-Spuren**, eine Tempo-Spur und
frei gewählte Fensterlängen in Takten.

---

## 2 · Grundlagen, die jeder Übergang braucht

### 2.1 Beatmatching (Tempo und Phase)
- **Tempo** gleich machen (Deck B auf das Tempo von A) und die **Phase**
  ausrichten (Beats von B fallen auf die Beats von A).
- Laut Analyse von 20.765 echten Übergängen ändern DJs das Tempo selten stark:
  **86,1 % der Titel unter 5 %, 94,5 % unter 10 %** (Kim et al., ISMIR 2020, *belegt*).
- Mikro-Ausrichtung nach dem Beat-Raster per Kreuzkorrelation der Onsets
  (Idee aus `autodj-mixer`). Sie fängt Raster-Fehler von wenigen Millisekunden ab.
- **Tempo-Rampe:** Bei größeren Abständen das Tempo über 8–32 Takte gleiten
  lassen, statt zu springen. B darf nach dem Übergang langsam auf sein
  Originaltempo zurück (`autodj-mixer`, `dj-kyoko`).
- **Halbes/Doppeltes Tempo:** 140 BPM passt zu 70 BPM, 87 BPM zu 174 (DnB).

### 2.2 Keylock und Tonhöhe
- **Keylock (Master Tempo):** Tempo ändern bei gleicher Tonhöhe. Laut Kim et al.
  lassen DJs ihn praktisch immer an. **Nur 2,5 %** der gespielten Titel wurden
  transponiert, davon **94,3 % um genau einen Halbton** (*belegt*).
- **Rechnung zu ADR-014:** Vinyl-Angleich um +3 % hebt die Tonhöhe um
  12·log2(1,03) = **0,51 Halbtöne**, bei 1 % sind es 0,17 (17 Cent). Ein halber
  Halbton liegt genau zwischen zwei Tonarten. Selbst eine passende Camelot-Wahl
  klingt dann schief (§10).
- **Bewusster Key-Shift:** B um ±1 Halbton in die Tonart von A ziehen.
  Vorsichtig, nur mit Keylock.

### 2.3 Harmonisches Mischen (Camelot-Rad)
| Schritt | Beispiel von 8A | Wirkung |
|---|---|---|
| gleiche Zahl und Buchstabe | 8A | sicher |
| ±1 | 7A, 9A | sicher, leichte Farbänderung |
| A↔B (Dur/Moll) | 8B | sicher, Stimmungswechsel |
| **+2 „Energy Boost"** | 10A | spürbares Anheben (Mixed In Key) |
| +7 / −5 | 3A | harter Bruch, bewusst und selten |

Quellen sind sich bei +1 vs. +2 als „Energy Boost" uneinig
([Mixed In Key](https://mixedinkey.com/workflows/change-energy-with-camelot-wheel/)).
Gewichtete Skala für den Planer (Idee aus `infinite_dj`): gleich 1,0,
parallel 0,9, ±1 0,8, abfallend.
**Wichtig:** Mit Stems verliert die Tonart an Gewicht, wenn sich beim Übergang
nur die Drums überlagern (§4, S3).

### 2.4 Phrasierung und Struktur
- 1 Takt = 4 Beats. Phrasen sind fast immer **8, 16 oder 32 Takte**. Mitten in
  einer Phrase zu mischen fühlt sich auch bei perfektem Beatmatch „falsch" an
  ([DJ.Studio](https://dj.studio/blog/phrasing-dj-mixing)).
- **Belegt aus echten Mixen:** Übergangslängen häufen sich bei **Vielfachen von
  32 Beats**, Cue-Outs zeigen deutliche Spitzen alle 32 Beats. DJs setzen
  denselben Track an ähnlichen Stellen an: **73,6 % innerhalb von 8 Takten**,
  86,2 % innerhalb von 16 Takten (Kim et al.).
- Klassisches Timing: Hat B 8 Takte Intro, startet B **8 Takte vor** dem Beginn
  des Outros von A. Dann landet die erste Strophe von B auf dem ersten Takt des
  Outros.
- **Struktur-Labels** (Intro, Strophe, Refrain, Break, Drop, Outro) entscheiden
  das Rezept (§5). Werkzeug: `allin1` (§7.3).
- **Cue-Wahl:** jeden Downbeat als Kandidat bewerten (Phrasengrenze,
  Energietal, Trend, Textur; Idee aus `infinite_dj`). Nicht nur Anfang und
  Ende nehmen.

### 2.5 Pegel und Klang
- **Lautheit** pro Titel angleichen (LUFS, haben wir), **Headroom** in der
  Mischung, **Limiter** am Ende (True Peak ≤ −1 dBTP, haben wir).
- **Blendkurven:** equal power (cos/sin) für unkorrelierte Signale. Die S-Kurve
  (Spotify) startet und endet weich. Linear nur bei korrelierten Signalen.
- **3-Band-EQ wie am DJ-Mixer:** Bässe unter ~200 Hz, Mitten, Höhen.
  Echtzeit-Trennung mit **Linkwitz-Riley-Weiche (LR4)**, phasentreu.
  `mix.py` nutzt offline Butterworth nullphasig plus Komplement. Für den Render
  ist das gut, auf Android braucht es LR4.

---

## 3 · Übergangsrezepte ohne Stems (Werkzeugkasten)

Jedes Rezept steht mit Länge, Einsatz, Ablauf und Voraussetzung da. Das
sind die Bausteine, die Spotify Mix, djay, PulseGrid und claude-dj gemeinsam
haben.

| # | Rezept | Länge | Wann | Ablauf | Voraussetzung |
|---|---|---|---|---|---|
| R1 | **Langer EQ-Blend** | 16–32 Takte | House, Techno, gleiche Energie | B kommt ohne Bass, Höhen und Mitten über die erste Hälfte rein; **Bass-Tausch hart auf einem Downbeat** zur Phrasenmitte; dann Mitten und Höhen von A raus | Beatmatch, Tonart kompatibel |
| R2 | **Kurzer Blend** | 4–8 Takte | Pop, Gesang, Tempo nah | wie R1 gerafft | Beatmatch |
| R3 | **Filter-Blend** | 8–16 Takte | weicher Wechsel, leichter Tonart-Konflikt | Hochpass auf A öffnet langsam (20 Hz → 1–2 kHz), B von unten mit Tiefpass rein | Beatmatch |
| R4 | **Echo-Out** | 1–2 Takte | großer Tempo- oder Tonart-Sprung | am Phrasenende Delay 1/2 oder 3/4 Beat, Feedback 50–75 %, Send auf 100 %, A zu **auf der 1**, B startet hart | keine (kein Overlap) |
| R5 | **Hall-Wash / Freeze** | 1–4 Takte | Genrewechsel, Stimmungsbruch | wie R4 mit Hall statt Delay | keine |
| R6 | **Cut / Slam auf die 1** | 0 | Energie halten, Drop auf Drop | A endet am Phrasenende, B startet auf seinem Drop | Phrase sauber |
| R7 | **Loop-Verlängerung / Loop-Roll** | 4–16 Takte | Outro von A zu kurz | letzte 4/8 Takte Drums von A loopen, B darüber; Roll 4→2→1→½ Beat als Build | Beat-Raster sicher |
| R8 | **Breakdown-Mix** | 8–16 Takte | B kommt im beatlosen Teil von A | B rhythmisch rein, während A keine Drums hat; Tempo-Unterschied stört weniger | Struktur-Label „Break" |
| R9 | **Double Drop** | 8–16 Takte | Höhepunkt | beide Drops gleichzeitig | gleiche Tonart und Tempo (mit Stems leichter) |
| R10 | **Tempo-Rampe** | 8–32 Takte | ΔBPM > 3 % | Tempo gleitet mit Keylock von A nach B, dann Blend | Keylock |
| R11 | **Brake / Spinback** | ½–1 Takt | Effekt, sparsam | A bremst wie ein Plattenteller ab, B startet | keine |

**Auswahl ohne Stems** (Lookup nach Struktur, Idee aus `autodj-mixer`):
Outro→Intro: R1 mit 16 Takten. Strophe→Strophe: R2 mit 4 Takten.
Tonart inkompatibel: längere Blende mit Filter (R3) oder Echo-Out (R4).
Gesang an beiden Mischpunkten: B auf eine instrumentale Stelle schieben.

---

## 4 · Übergänge mit Stems (der eigentliche Unterschied)

**Stems** = getrennte Spuren je Titel: **Drums, Bass, Gesang, Rest
(Harmonie/Melodie)**. Mit Stems steuert der Übergang die vier Teile einzeln
statt nur Frequenzbänder.

| # | Stem-Rezept | Ablauf | Warum besser als EQ |
|---|---|---|---|
| S1 | **Drums zuerst** | B nur Drums 8–16 Takte unter A, die Drums von A gehen raus → Bass-Tausch → Harmonie von B rein, Harmonie von A raus → Gesang von B erst nach dem Gesang von A | sauberster Profi-Blend, keine Doppel-Kick |
| S2 | **Bass-Tausch per Stem** | Bass-Stem von A raus, Bass-Stem von B rein, auf den Downbeat | Ein EQ-Bass-Cut nimmt die **Kick** mit, ein Stem nicht |
| S3 | **Tonart-Rettung** | Bei Tonart-Konflikt überlagern sich **nur Drums** (plus Bass einer Seite). Harmonie und Gesang laufen nie gleichzeitig | Paare außerhalb des Camelot-Rads werden mischbar. **Der Planer bekommt mehr Kandidaten** |
| S4 | **Gesang ohne Überlappung** | Gesang von A vor dem Overlap stumm oder per Echo raus, Gesang von B erst nach dem Bass-Tausch | Kein Gesangs-Clash. Laut `claude-dj`, `jevdj` und `autodj-mixer` die häufigste Fehlerquelle |
| S5 | **Acapella-Brücke (Mashup)** | Gesang von A 8–16 Takte über das Instrumental von B | echter DJ-Moment; braucht gute Trennung und passende Tonart (sonst ±1 Halbton) |
| S6 | **Instrumental-Brücke** | Drums von A loopen, Harmonie von B darüber | verbindet sehr unterschiedliche Titel |
| S7 | **Stem-Echo** | nur der Gesang von A geht ins Echo, der Rest wird normal geblendet | wie R4, aber musikalischer |
| S8 | **Drum-Swap** | Drums von B ersetzen früh die von A, der Rest von A läuft weiter | Groove-Wechsel ohne Bruch |

**Marktlage Stems:** djay (Neural Mix) trennt Gesang, Harmonie, Bass und Drums
in Echtzeit, Automix wählt Gesang oder Rhythmus automatisch
([VentureBeat](https://venturebeat.com/technology/algoriddims-djay-pro-ai-can-transfer-vocals-and-rhythms-between-songs),
belegt für iOS). VirtualDJ 2025 hat einen „StemSwap Sampler" (Loops 4–32 Beats)
([MusicTech](https://musictech.com/news/gear/virtualdj-2025-stemswap-sampler/)).
Spotify und Apple haben **keine** Stem-Übergänge.

---

## 5 · Rezept-Auswahl (Regelwerk V1, später gelernt)

Eingaben je Paar A→B: ΔBPM, Camelot-Abstand, Struktur-Label am Cue-Out von A
und am Cue-In von B, Gesang in beiden Fenstern (aus dem Gesangs-Stem),
Energie-Ziel, Stems verfügbar ja/nein.

| Lage | Rezept |
|---|---|
| Tonart passt, ΔBPM ≤ 3 %, Outro→Intro | S1 (mit Stems) oder R1 |
| Tonart passt nicht, ΔBPM ≤ 3 % | **S3** (mit Stems) oder R3/R4 |
| Gesang in beiden Fenstern | S4, sonst Cue auf instrumentale Stelle schieben |
| ΔBPM 3–8 % | R10, dann S1/R1 |
| ΔBPM > 8 % oder Genrewechsel | R4, R5 oder R6 |
| Outro von A kürzer als nötig | R7 vor dem eigentlichen Blend |
| Energie-Ziel „Höhepunkt" | R9/S5 bei passender Tonart, Camelot +2 im Planer |
| Analyse unsicher (Raster- oder Tonart-Vertrauen niedrig) | nur R4 oder R6, kein Overlap |

**Später:** Gewichte aus Nutzerverhalten lernen, lokal (Skips, Änderungen im
Editor; Idee aus `aryanbakshi25/autodj`: „learning loop").

---

## 6 · Datenformat: das Übergangsrezept (Vorschlag)

Ein Übergang wird als **Daten** beschrieben, nicht als Code. Derselbe
Renderer läuft im PC-Prototyp (offline) und auf Android (Echtzeit). Der Editor
ändert nur Daten. Das passt zu ADR-011 (Verfahren übertragen, nicht Code).

```json
{
  "von": "track:3f9a", "zu": "track:81c2",
  "laenge_takte": 16,
  "cue_out_a_beat": 448, "cue_in_b_beat": 0,
  "tempo": {"kurve": "rampe", "von_bpm": 124.0, "zu_bpm": 126.0, "keylock": true},
  "spuren": {
    "a.gain":   {"kurve": "s", "von": 1, "zu": 0},
    "b.gain":   {"kurve": "s", "von": 0, "zu": 1},
    "a.stem.drums":  [[0, 1], [8, 0]],
    "b.stem.drums":  [[0, 0], [8, 1]],
    "a.stem.bass":   [[0, 1], [8, 1], [8, 0]],
    "b.stem.bass":   [[0, 0], [8, 0], [8, 1]],
    "a.stem.vocals": [[0, 1], [4, 0]],
    "b.stem.vocals": [[0, 0], [12, 0], [14, 1]],
    "a.filter":  {"typ": "hochpass", "punkte": [[8, 20], [16, 1500]]},
    "a.fx.echo": {"teiler": 0.5, "feedback": 0.75, "punkte": [[14, 0], [16, 1]]},
    "a.loop":    null
  },
  "rezept": "S1", "grund": "Tonart 8A→9A, ΔBPM 1,6 %, Outro→Intro"
}
```

Punkte sind `[Takt, Wert]`, ein doppelter Takt bedeutet einen harten Sprung
auf dem Downbeat. Ohne Stems fallen die `stem`-Spuren weg und `a.eq.low` usw.
übernehmen.

---

## 7 · GitHub- und Marktrecherche: Bewertung jeder Quelle

**Lizenzregel:** Ohne Lizenzdatei gilt „alle Rechte vorbehalten". Dann
übernehmen wir **nur Ideen, keinen Code**. GPL/AGPL: ebenfalls nur Ideen
(ADR-012). MIT: Code dürfte übernommen werden, aber keines dieser Repos ist
reif genug, um Code zu übernehmen.

### 7.1 Die angefragten Repos

| Repo | Was | Stack | Lizenz | Reife | Nützlich für uns |
|---|---|---|---|---|---|
| [aryanbakshi25/autodj](https://github.com/aryanbakshi25/autodj) | Club-Auto-DJ: Energie-Kurve, Phrasen, Harmonie, Wünsche live | TS + Python (librosa), Web Audio, **Signalsmith als WASM** | **keine** | Phase 0, 6 Commits, Audio noch nicht angeschlossen | **Ideen:** Beam-Search über eine Energiekurve, Rezept-Scoring mit Gesangs-Clash-Schutz, Lernschleife, „nie still"-Failsafe, `AudioEngine`-Schnittstelle (DSP austauschbar) |
| [joberman32/infinite_dj](https://github.com/joberman32/infinite_dj) | Bibliothek analysieren, Reihenfolge, Mix live oder als WAV | Python, Rubber Band, sounddevice | **keine** | 57 Commits, Tests, Kalibrierdoku | **Ideen:** jeden Downbeat als Cue-Kandidat gewichten, Camelot-Gewichtsskala, Drei-Phasen-EQ mit Bass-Tausch, Lookahead-Scheduler in drei Threads |
| [StanAngular/autodj-mixer](https://github.com/StanAngular/autodj-mixer) | Offline-Mixer mit Struktur und Stems | Python, madmom, „All-in-One" (Demucs), librosa | **MIT** | 247 Commits, aber viele Einzelskripte, von KI-Agenten gebaut | **Ideen:** Blendlänge und EQ-Art per **Tabelle aus den Struktur-Labels**, Tonart-Konflikt → länger und Notch-EQ, **Gesang überlappt → B auf instrumentale Stelle schieben**, FFT-Feinausrichtung, Tempo-Rampe zurück |
| [russel-gandhi/AutoMix-AI](https://github.com/russel-gandhi/AutoMix-AI) | DJ-Mix und Mashup | Python, Streamlit, Demucs, pyrubberband | **keine** | 2 Commits | **Idee:** Mashup-Kette (Demucs → Key-Shift → Tempo-Warp), Stem-Cache per Hash. Sonst nichts |
| [lapat/dj-kyoko](https://github.com/lapat/dj-kyoko) | Offline-Mix im Stil eines Künstlers | Python, **Beat This!**, Essentia, rubberband | **MIT** (Essentia darin AGPL) | 4 Commits | **Ideen:** **Phasen- und Amplituden-Prüfung mit Wiederholung** anderer Blendpunkte, Snippets je Übergang zum Gegenhören, Bass-zuerst-Tausch |
| [Rahul04-alt/AutoMixAi](https://github.com/Rahul04-alt/AutoMixAi) | Web-Tool: Analyse, Zwei-Track-Mix, Beat-Generator | FastAPI, React, TensorFlow, Essentia | **MIT** | Demo, Widersprüche im README | **Idee:** getrennte Kurven für Bass und Mitte/Höhen (Trennung 200 Hz), HPSS als grober Gesangsdetektor. Sonst wenig |
| [ysy-ym/pulsegrid](https://github.com/ysy-ym/pulsegrid) | Browser-DJ-Studio mit zwei Decks, Set aus Text-Wunsch, Auto Play | JS + Python, Web Audio, Rubber Band | **MIT** | 2 Commits, aber breite Funktionen | **Ideen:** **Übergangs-Audit sperrt Auto Play**, Cue-Paare je Übergang, Änderung in der Liste plant nur die betroffenen Übergänge neu. Das ist das beste UI-Vorbild |
| [calumjs/claude-dj](https://github.com/calumjs/claude-dj) | DJ-Rig, gesteuert von Claude Code per Text | Node, Web Audio, Demucs, WSOLA | **keine** | 3 Commits | **Ideen:** vollständiger Wortschatz (blend, bassswap, echo, cut, brake, spinback, loop roll, Einstieg bei intro/drop), Planung auf der **Audio-Uhr**, **Gesangskarte aus dem Stem**, „Mix-Monitor" kritisiert jeden Übergang |
| [csteinmetz1/AutomaticMixingPapers](https://github.com/csteinmetz1/AutomaticMixingPapers) | Literaturliste | – | MIT | 109 Sterne | **Gering:** Es geht um Multitrack-Produktionsmischung, kaum um DJ-Übergänge. Nur Nachschlagewerk |
| [sony/FxNorm-automix](https://github.com/sony/FxNorm-automix) | Deep Learning mischt **Multitracks** (Studio) | PyTorch 1.9 | MIT (Gewichte ohne Angabe) | Forschung, 21 Commits | **Nein.** Mischt Spuren einer Produktion, keine zwei fertigen Songs |
| [ngocthanhgl/Autobeat-DJ](https://github.com/ngocthanhgl/Autobeat-DJ) | **Android**-Player mit DJ-Modus für eigene Dateien | Kotlin, nativer Analyzer | **GPL-3.0** | **am 10.10.2026 archiviert**, 119 Commits, 0 Sterne | **Warnsignal und Datenpunkt:** genau unsere Idee, aufgegeben. Eigenangabe: Analyse 5–10 s pro Titel (Dimensity 9400). Code wegen GPL nicht nutzbar. Die APK nicht installieren (Sideload, keine Prüfsummen) |
| [sammy03f/AutoDJ](https://github.com/sammy03f/AutoDJ) | Anfang eines Auto-DJ | Python, nur stdlib | **keine** | 6 Commits, nur WAV-Laden | **Nein** |
| [nqobile-x/jevdj](https://github.com/nqobile-x/jevdj) | KI-DJ im Browser mit DJ-Ansagen | FastAPI, TS, Web Audio, Groq | **keine** | 3 Commits | **Ideen:** Regeln filtern vor (BPM ±8 % inkl. halb/doppelt, Camelot), LLM wählt **nur mit Vertrauen ≥ 0,40**, sonst Regel-Rückfall. Energie-Ziele als Perzentile der eigenen Sammlung. Mischpunkt springt bei Gesang (≥ 0,6) zur nächsten instrumentalen Phrase |
| [Offtrack](https://www.offtrack.com/) | **Konkurrenzprodukt:** „AI DJ app in your pocket", kürzt Songs auf Highlights, Smart Mix | iOS + Android | proprietär | am Markt | **Konkurrenz und Idee.** Android nur Spotify Premium und SoundCloud, **eigene Dateien nur auf iOS**. Idee „Songs auf Highlights kürzen" |

**Gesamturteil:** Kein Repo ist ein Fundament. Fast alle bauen dasselbe Gerüst
(librosa oder Beat This!, Krumhansl-Tonart, Camelot, EQ-Blend mit
Bass-Tausch, Rubber Band). Unser Prototyp misst dabei strenger (Wilson-Tore,
Gold-Labels). Den Wert bringen **neun Ideen** (§9) und die Bestätigung, dass
**Gesangs-Clash und Cue-Wahl** die Kernprobleme sind.

### 7.2 Fertige Produkte (Markt)

| Produkt | Plattform | Quelle | Übergänge | Stems | Bewertung für uns |
|---|---|---|---|---|---|
| **Spotify Mix** | alle | nur Streaming, Premium | Lautstärke, EQ, Filter, Echo, Loop; editierbar; Presets | nein | setzt die **Erwartung**: Wer Spotify hat, braucht uns nicht |
| **Apple Music AutoMix** (iOS 26) | Apple | nur Streaming, Abo | Time-Stretch und Beatmatch, automatisch, **keine** Einstellungen | nein | Bequemlichkeit, keine Kontrolle |
| **djay (Algoriddim)** | iOS, Android, Desktop | eigene Dateien und Dienste | Automix AI, Dissolve/Riser/Echo, Neural-Mix-Übergang | **ja, Echtzeit** (iOS belegt; Neural-Mix-Crossfader auf Android laut Forum 2025 **noch nicht**) | **stärkster Gegner.** Aber DJ-Werkzeug, kein Player; Android-Stand unklar |
| **VirtualDJ** | Desktop | eigene Dateien | Automix mit eigenen Übergängen | StemSwap Sampler | Profi-Desktop, nicht mobil |
| **Offtrack** | iOS, Android | Android nur Streaming | Übergangspunkte, Smart Mix, Highlights | nein | auf Android keine eigenen Dateien |
| **Mixxx** | Desktop | eigene Dateien | Auto DJ (einfach) | Stem-Wiedergabe (2.6) | GPL, nur Studienobjekt |
| **Poweramp** | Android | eigene Dateien | nur Crossfade, Gapless | nein | unser Player-Vorbild, kein Auto-DJ |

### 7.3 Zusätzlich gefundene Bausteine

| Baustein | Was | Lizenz | Nutzen |
|---|---|---|---|
| [CPJKU/beat_this](https://github.com/CPJKU/beat_this) | Beats/Downbeats | MIT | **haben wir** (Phase 0.9 bestanden) |
| [mir-aidj/all-in-one](https://github.com/mir-aidj/all-in-one) (`allin1`) | **Beats, Downbeats und Struktur-Labels** (intro, verse, chorus, break, bridge, inst, solo, outro) in einem Lauf, trennt intern per Demucs | Code MIT; Gewichte **ohne Angabe**, trainiert auf dem Harmonix-Set | **PC-Prototyp: sofort.** Liefert Struktur **und** Stems. Für das Produkt die Gewichtslizenz klären. Braucht madmom und NATTEN |
| [facebookresearch/demucs](https://github.com/facebookresearch/demucs) (HTDemucs) | 4 Stems: drums, bass, vocals, other | Code MIT; Gewichtslizenz im Repo nicht genannt, **prüfen** | Standard für Stems. Repo **archiviert**, Fixes nur noch im Fork `adefossez/demucs`. 6-Stem-Modell: Klavier mit viel Übersprechen. Laufzeit „etwa 1,5× Songdauer" ohne Hardwareangabe |
| [demixr/demixr-app](https://github.com/demixr/demixr-app) | HTDemucs **auf Android** (ExecuTorch/Vulkan oder ONNX/CPU), Chunking mit Overlap-Add | MIT | **bestes Studienobjekt** für Stems auf dem Handy. Keine Zeitangaben, „noch in Entwicklung" |
| [google/oboe · OboeDJ](https://github.com/google/oboe/tree/main/samples/OboeDJ) | zwei Decks, Crossfader, Tempo-Faktor | Apache-2.0 | Engine-Vorlage (ADR-016) |
| [mir-aidj/djmix-analysis](https://github.com/mir-aidj/djmix-analysis) + [Kim et al. 2020](https://arxiv.org/abs/2008.10267) | Analyse von 1.557 echten Mixen, 20.765 Übergänge | Code ohne Lizenzangabe | **Zahlen für unsere Regeln** (§2.1, 2.2, 2.4) |
| [Raveform (TISMIR 2026)](https://mir-aidj.github.io/raveform/) | 4.902 Mixe, 1.423 Tracks mit Struktur, Mix-in/out-Punkte | ohne Lizenzangabe | Referenz, wo DJs ein- und aussteigen; Lizenz vor Nutzung klären |
| DJtransGAN ([arXiv 2110.06525](https://arxiv.org/abs/2110.06525)) | lernt EQ- und Fader-Kurven aus echten Mixen | nur Paper, kein Code gefunden | Bestätigt das Spurenmodell; Lernen später |
| dnb-autodj ([Vande Veire 2018](https://asmp-eurasipjournals.springeropen.com/articles/10.1186/s13636-018-0134-8)) | automatischer DnB-DJ mit Hörtest (18 Fans) | **AGPL** | nur Ideen und Hörtest-Aufbau |
| HS-TasNet ([arXiv 2402.17701](https://arxiv.org/abs/2402.17701)) | Stems in Echtzeit mit 23 ms Latenz | kein Code | zeigt: Echtzeit geht, aber mit weniger Qualität (SDR 4,65–5,55) |
| AudioShake SDK | Stems on-device auf Android | kommerziell | Herstellerangabe „bis 250× Echtzeit, < 50 ms". Kauf-Option, falls Demucs zu langsam ist |

---

## 8 · Lohnt es sich?

**Ehrliche Bilanz:**
1. **Normale DJ-Übergänge sind keine Differenz mehr.** Spotify (seit 08/2025)
   und Apple (iOS 26) liefern sie im Abo mit. Wer streamt, hat keinen Grund zu
   wechseln.
2. **Die Nische bleibt:** eigene Dateien, Android, offline, ohne Abo. Dort gibt
   es heute Poweramp (nur Crossfade), djay (DJ-App, Stems auf Android unklar)
   und Offtrack (auf Android nur Streaming). Ein Android-Projekt genau für
   diese Nische (Autobeat-DJ) ist gerade **archiviert** worden.
3. **Stems sind der einzige technische Vorsprung**, den Spotify und Apple
   nicht haben, und genau das, was Profi-Übergänge hörbar besser macht
   (S1–S4). djay hat ihn auch, ist aber ein DJ-Werkzeug, kein Player.
4. Der Markt eigener Sammlungen ist klein (bisher offen, `PRODUKT-KLANGBILD.md` §12).

**Empfehlung:** Weiterbauen **nur mit Stems als Kern** und nur, wenn der
Hörtest das belegt. Konkret in Phase 1 ein **A/B/C-Hörtest**:
(A) Shuffle mit Crossfade, (B) EQ-Blend im Spotify-Stil, (C) Stem-Übergänge.
**Neues Tor (Vorschlag):** C wird gegenüber B klar bevorzugt. Wenn nicht, ist
der Abstand zu Spotify zu klein für ein Produkt. Die Tötungskriterien aus §15
des Produktdokuments gelten weiter.

**Günstigere Alternative zum Marktest:** Der PC-Prototyp rendert bereits Mixe.
Ein Desktop-Werkzeug „Mix aus meiner Sammlung" (für Sport, Autofahrt,
Streamer) wäre ohne Android-Engine testbar. Nur eine Idee, keine Empfehlung.

---

## 9 · Was wir besser machen (Differenzierung)

1. **Stem-Automix für eigene Dateien auf Android, offline.** Das bietet heute
   kein Player.
2. **Tonart-Rettung über Stems (S3).** Mehr mischbare Paare, also bessere
   Reihenfolgen nach Klang und Energie statt nur nach Camelot. Messbar: Anteil
   der Kandidaten, die durch S3 zusätzlich mischbar werden.
3. **Gesangs-Clash-Schutz** über eine Gesangskarte aus dem Stem (S4).
4. **Cue-Wahl nach Struktur und Statistik:** jeden Downbeat bewerten,
   Struktur-Labels, 32-Beat-Raster wie bei echten DJs (§2.4).
5. **Automatische Qualitätsprüfung vor dem Abspielen** (wie PulseGrid-Audit,
   claude-dj-Monitor, dj-kyoko-Gate), aber gemessen statt geschätzt:

   | Messgröße im Overlap | Schwelle (Vorschlag) |
   |---|---|
   | Beat-Phasenfehler (Onset-Kreuzkorrelation) | < 10 ms |
   | Bass-Kollision (beide Bässe gleichzeitig laut) | 0 Takte |
   | Gesangs-Überlappung (beide Gesangs-Stems aktiv) | 0 s, außer bei S5 |
   | Lautheitsloch oder -spitze (Kurzzeit-LUFS) | innerhalb ±1,5 LU |
   | harmonischer Konflikt, solange beide Harmonie-Stems laufen | Chroma-Dissonanz unter Grenze |
   | True Peak | ≤ −1 dBTP |

   Fällt ein Übergang durch, wählt der Planer ein sichereres Rezept (bis
   hin zu R4/R6). Das passt zur Messkultur des Projekts (Wilson-Tore).
6. **Editierbar wie Spotify**, plus Stem-Spuren, längere Fenster, Loops über
   mehrere Phrasen, gespeichert mit der Playlist.
7. **Songs auf Highlights kürzen** (Offtrack-Idee), etwa für kurze Sets.
8. **Erklärung der Wahl** (ADR-015: Gemma 4 optional), z. B. „Tonart 8A→9A,
   +1,6 % Tempo, Drums zuerst wegen Gesang".
9. **Lokal lernen** aus Skips und Änderungen, ohne Server.

---

## 10 · Folgen für Architektur und Roadmap (Vorschläge, nicht umgesetzt)

| Thema | Heute | Vorschlag | Form |
|---|---|---|---|
| **Stems** | „Kann", Phase 6, offline (`PRODUKT-KLANGBILD.md` §5c) | **Kern ab Phase 1.** Auf dem Handy **nur das Übergangsfenster** trennen (z. B. letzte 45 s von A + erste 45 s von B), während A noch läuft. Braucht etwa 0,75× Echtzeit statt Echtzeit. Ergebnis cachen | neues **ADR-018** |
| **Exakte Rekonstruktion** | – | Rest r = Original − Summe der Stems zum Stem „other" addieren. Alle Stems auf 1 ergeben dann **exakt** das Original. Wechsel zwischen Original und Stems ist unhörbar | Teil von ADR-018 |
| **Übergangsformat** | Renderer fest in `mix.py` | Datenformat aus §6, ein Renderer für PC und Android, Editor ändert nur Daten | neues **ADR-019** |
| **Vinyl-Angleich** | ±3 % ohne Keylock (ADR-014) | **auf ±1 % begrenzen** (17 Cent), oder Keylock (Signalsmith) schon im PC-Prototyp. Grund: 86 % der echten Titel < 5 %, Keylock fast immer an, ±3 % = 0,51 Halbtöne | ADR-014 durch neues ADR ergänzen |
| **Prototyp `mix.py`** | **Mono**, ein Rezept (EQ-Blend mit Bass-Tausch) | Stereo, Rezepte R1–R7 und S1–S4 nach §6, Stems und Struktur über `allin1`, Qualitätsprüfung nach §9.5 | Phase 1 |
| **Phase 1 Tor** | Hörtest gegen Shuffle | A/B/C-Hörtest (§8) | Roadmap |
| **Phase 3** | Analysezeit messen | zusätzlich **Demucs-Zeit pro 90 s Fenster** auf einem Mittelklasse-Handy (ONNX und ExecuTorch, Vorlage demixr). Rückfall ohne Stems: R1–R7 | Roadmap |
| **Engine** | zwei Decks | je Deck Original + 4 Stems, EQ (LR4), Filter, FX-Send, Loop; Demucs im Hintergrund-Thread mit niedriger Priorität, der Audio-Callback darf nie warten | ADR-001/010 ergänzen |
| **Speicher** | – | 4 Stems × 90 s × 44,1 kHz × Stereo × 16 Bit ≈ **64 MB** pro Fenster als Rohdaten. Kurz cachen, ältere löschen | ADR-018 |

---

## 11 · Was noch fehlt (Antwort auf „Reichen die Infos?")

| Offen | Warum Recherche nicht reicht | Wie wir es schließen |
|---|---|---|
| Stem-Trennung auf dem Handy schnell genug? | keine offene Quelle mit Messwerten auf Android | Phase 3: 90-s-Fenster auf einem Mittelklasse-Gerät messen |
| Klingen die Stem-Rezepte besser? | Geschmack, Artefakte (Übersprechen, besonders bei Acapella) | Phase 1: A/B/C-Hörtest |
| Struktur-Labels auf echter Musik genau genug? | `allin1` gibt auf GitHub keine Genauigkeit an | wie Phase 0.4/0.9: gegen lizenzfreie Gold-Labels messen |
| Lizenz der Gewichte von HTDemucs und `allin1` | in den Repos nicht genannt | vor dem Release im Original klären (ADR-012-Regel) |
| djay auf Android: Stems im Automix? | Forum 2025 „noch nicht", 2026 nichts gefunden | App selbst testen |
| Zahlbereitschaft | nur außerhalb des Stores messbar | Phase 2 |

---

## 12 · Quellen

**Repos (angefragt):** [aryanbakshi25/autodj](https://github.com/aryanbakshi25/autodj) ·
[joberman32/infinite_dj](https://github.com/joberman32/infinite_dj) ·
[StanAngular/autodj-mixer](https://github.com/StanAngular/autodj-mixer) ·
[russel-gandhi/AutoMix-AI](https://github.com/russel-gandhi/AutoMix-AI) ·
[lapat/dj-kyoko](https://github.com/lapat/dj-kyoko) ·
[Rahul04-alt/AutoMixAi](https://github.com/Rahul04-alt/AutoMixAi) ·
[ysy-ym/pulsegrid](https://github.com/ysy-ym/pulsegrid) ·
[calumjs/claude-dj](https://github.com/calumjs/claude-dj) ·
[csteinmetz1/AutomaticMixingPapers](https://github.com/csteinmetz1/AutomaticMixingPapers) ·
[sony/FxNorm-automix](https://github.com/sony/FxNorm-automix) ·
[ngocthanhgl/Autobeat-DJ](https://github.com/ngocthanhgl/Autobeat-DJ) ·
[sammy03f/AutoDJ](https://github.com/sammy03f/AutoDJ) ·
[nqobile-x/jevdj](https://github.com/nqobile-x/jevdj) ·
[Offtrack](https://www.offtrack.com/)

**Markt:** [Spotify Support: Mixed Playlists](https://support.spotify.com/ro-en/article/mixed-playlists/) ·
[RouteNote: Spotify Mix](https://routenote.com/blog/spotify-mix-customizable-transitions/) ·
[MusicTech: Apple Music AutoMix](https://musictech.com/news/gear/apple-music-automix-ai/) ·
[MacMyths: AutoMix-Grenzen](https://macmyths.com/how-to-use-apple-automix-for-beat-to-beat-style-mixing-on-ios-26-and-macos-tahoe/) ·
[djay Android Release Notes](https://cdn.algoriddim.com/djay-android/releasenotes) ·
[Algoriddim-Forum: Neural Mix Android](https://community.algoriddim.com/t/neural-mix-crossfaders-android/34809) ·
[MusicTech: djay Automix-Übergänge](https://musictech.net/news/gear/algoriddim-free-dj-software-djay-pro-ai-automix-and-neural-mix/) ·
[VentureBeat: djay Neural Mix](https://venturebeat.com/technology/algoriddims-djay-pro-ai-can-transfer-vocals-and-rhythms-between-songs) ·
[MusicTech: VirtualDJ StemSwap](https://musictech.com/news/gear/virtualdj-2025-stemswap-sampler/)

**Technik und Forschung:** [Kim et al. 2020, Analyse echter DJ-Mixe](https://arxiv.org/abs/2008.10267) ·
[mir-aidj/djmix-analysis](https://github.com/mir-aidj/djmix-analysis) ·
[Raveform](https://mir-aidj.github.io/raveform/) ·
[mir-aidj/all-in-one](https://github.com/mir-aidj/all-in-one) ·
[facebookresearch/demucs](https://github.com/facebookresearch/demucs) ·
[demixr/demixr-app](https://github.com/demixr/demixr-app) ·
[DJtransGAN](https://arxiv.org/abs/2110.06525) ·
[HS-TasNet](https://arxiv.org/abs/2402.17701) ·
[Vande Veire & De Bie 2018](https://asmp-eurasipjournals.springeropen.com/articles/10.1186/s13636-018-0134-8) ·
[AudioShake SDK](https://www.audioshake.ai/products/sdk)

**DJ-Praxis:** [DJ.Studio: Phrasing](https://dj.studio/blog/phrasing-dj-mixing) ·
[Mixed In Key: Energie mit dem Camelot-Rad](https://mixedinkey.com/workflows/change-energy-with-camelot-wheel/) ·
[DJ TechTools-Forum: Phrase Matching](https://forum.djtechtools.com/t/question-about-phrase-matching-mixing-to-compliment-a-tracks-musical-structure/68140)
