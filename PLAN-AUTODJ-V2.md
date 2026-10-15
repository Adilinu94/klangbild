# Plan · Auto-DJ V2: der Mixer entscheidet je Titelpaar selbst

Stand 2026-10-12 · Grundlage: `KONZEPT-SMART-AUTODJ.md` (Recherche) und
`WISSEN-DJ-TECHNIKEN-UND-REPOS.md` (Rezepte)

**Stand 2026-10-12, umgesetzt:** alle Bausteine 0–8 (`profil.py`, `regie.py`, EQ „profi“,
`live._auto_backen`, Oberfläche). Entscheidungen: Stems für ganze Songs; Spielanteil
schnell/lang; Stil-Stufen Kurz/Ausgewogen/Lang + Manuell; im Auto-Modus sind alle
Übergangs-Einstellungen gesperrt.

**Runde 2 (nach Hörtest):**
- Effekte greifen vor EQ und Fader und kommen erst in den letzten 1–2 Takten vor dem
  Ausstieg, solange A noch klingt; ein Filter öffnet unter einem Effekt höchstens zu 60 %;
  Effekte nur, wenn A am Ausstieg höchstens 8 dB leiser ist als B. Gemessen: Effekte
  −3 bis −14 dB unter dem Mix (vorher bis −53 dB, unhörbar).
- Loops „automatisch“: Stelle und Länge (4/8/16/32 Beats) nach Wiederholbarkeit im
  Original (Klangfarbe je Schlag), ohne Gesang, auf Taktgrenze. Güte 0,77–0,97.
- Intro-Loop von B (Lang & komplex): B's sauberer Anfang läuft 2–4-mal, damit der Gesang
  von B erst nach der Blende einsetzt.
- Rezepte abgestimmt: Effekt-Rezepte halten A bis zum Schnitt (Fader und EQ offen).
- Pegel je Band gedeckelt (kein Buckel über dem lauteren Song + 1,5 dB).
- Harmonie im Fenster per Chroma je Takt (Profil v2).
- Nächster Titel: Top 6 nach Tempo/Tonart/Energie, dann bester Regie-Plan + Energiebogen.
- „Perfekte Reihenfolge“ bevorzugt Paare mit gesangsfreiem Ende/Anfang.
- Lernen: WEITER in der Blende / „anderer Übergang“ = Minus, durchgehört = Plus
  (`ergebnisse/regie-lernen.json`).

**Runde 3 (Test aller Funktionen, 2026-10-14):**
- Loops in jedem Stil: Rezepte `outro_loop`, `loop_echo`, `loop_filter` (A loopt eine saubere
  Stelle), `intro_loop_b` (B's Intro im Loop) und `rolle`; Auswahl nach Vorzugswert statt
  „erster Treffer“. Vorher kam in „Ausgewogen“ nie ein Loop vor.
- „Automatisch“ als Übergangsart ist auch im Stil „Manuell“ die Regie (vorher: alte Festregel
  EQ/Echo/Schnitt ohne Loops und Effekte).
- Fehler behoben: Endet A mitten in der Blende und der Rest hat keine Drums, wählte die Regie
  ein Rezept ohne Loop (Stems-Rezept) → bis −70 dB Loch. Jetzt ist der Loop Pflicht.
- Selbstkontrolle: Loop-Güte < 0,7 oder Pegel-Loch → nächster Plan (bis 3), dann sicherer
  Profi-Blend.
- Tempo: Planung 0,4 s → 0,03 s (Ableitungen je Profil einmal gerechnet); Stem-Rezepte
  8 Spuren gleichzeitig dehnen, Pool vorgewärmt (erster Übergang −5 s), Profile fehlender
  Titel werden im Hintergrund nachgerechnet; Anzeige von Titel und Plan schon vor dem Backen.
- WEITER nutzt keine Stem-Rezepte mehr (backen länger).

**Offen:** Hörtest der neuen Rezepte; manuelle Einstellung für den Intro-Loop von B.

## Ziel in einem Satz

Für jedes Titelpaar sucht der Auto-DJ selbst die beste Stelle zum Wechseln in
A, die beste Einsatzstelle in B, die passende Länge und das passende Rezept.
Höhen, Mitten und Bass blendet er dabei getrennt und taktgenau wie ein DJ am
Mischpult. Du stellst nur noch den **Mix-Stil** ein.

## Was heute fehlt (ehrliche Bestandsaufnahme)

| Heute | Problem |
|---|---|
| Wechsel in A: fest „Outro" oder „letzte Phrase" | Bei langem Outro wird es zu lang, bei Gesang im Outro kollidiert es. Liegt das Outro falsch, mischt er an der falschen Stelle |
| Einsatz in B: immer Takt 1 oder „Drop" | B setzt mit dünnem Intro ein, der Drop landet zufällig in der Blende |
| Rezept: „Auto" = EQ, wenn Tonart passt, sonst Echo | kennt weder Gesang noch Energie, Dichte oder Struktur |
| EQ: Bass-Tausch, Rest gleichzeitig | Höhen, Mitten und Bass laufen nicht getrennt in eigener Reihenfolge, die Pegelkurven sind linear statt in dB |
| Keine Kontrolle des Ergebnisses | Doppelbass, Gesangs-Clash oder Lautstärke-Delle bleiben unbemerkt |

---

## Baustein 0 · Grafikkarte (läuft gerade)

- PyTorch mit CUDA 12.6 für die RTX 2070. Demucs (Stems) und Beat This!
  (Beats bei neuen Uploads) rechnen dann auf der Grafikkarte. Der Code wählt
  sie automatisch.
- Messen: Faktor Rechenzeit je Sekunde Audio. Damit stimmt die Zeitrechnung
  „reicht die Zeit für Stems?".
- **Stem-Vorrat für die ganze Bibliothek** als Hintergrundlauf (erwartet:
  wenige Stunden statt ~2 Tagen). Alles Weitere baut darauf auf.

## Baustein 1 · Titel-Profil: jeder Song Takt für Takt verstanden

Neues Modul `klangbild/profil.py`. Es rechnet einmal je Titel (beim Upload
bzw. als Nachlauf für die Bibliothek) und speichert kompakt in der Datenbank:

| Je Takt | Woher | Wofür |
|---|---|---|
| Pegel **Bass / Mitten / Höhen** (3 Bänder, dB) | Audio, gleiche Weichen wie der Mixer | Doppelbass erkennen, Pegel der Blende je Band planen |
| **Gesang**, **Drums**, **Bass-Instrument**, **Harmonie** (je Stem) | Stems aus dem Vorrat | Gesangs-Clash, „beatlos", wo die Bassline einsetzt |
| **Dichte** (Anzahl aktiver Stems) und **Energie** | daraus | dünn gegen dicht, Energieverlauf |
| **Chroma** (Tonvorrat je Phrase) | Audio | Harmonie-Clash im Überlappungsfenster selbst messen, statt nur die Tonart des ganzen Songs zu kennen |
| **Raster-Vertrauen** | Abweichung der Downbeats vom Raster | unsichere Stellen meiden (heute ~23 % der Titel mit Tempo-Sprüngen) |

Daraus folgt je **Phrase (8 Takte)** ein **Etikett**: Intro, Aufbau, Drop,
Hauptteil, Break (beatlos), Outro. Die Regeln dafür sind einfach: Drop =
Energiesprung nach Tal oder Aufbau mit Drums, Break = kaum Drums, Intro und
Outro = Anfang bzw. Ende mit geringer Dichte. Heutige Neuheitsgrenzen und
Energie gibt es schon; neu sind die Stem-Kurven.

Speicher: ~2–4 KB je Titel. Die Oberfläche kann die Etiketten später als
farbige Abschnitte über der Wellenform zeigen.

## Baustein 2 · Wann wechseln, wo einsetzen (Cue-Suche)

Neues Modul `klangbild/regie.py`. Statt fester Stellen bewertet es **alle
sinnvollen Kombinationen** und nimmt die beste:

- **Kandidaten A (Ausstieg):** jeder Phrasenanfang ab ca. 50 % des Songs
  (einstellbar über „Spielanteil", siehe Entscheidungen).
- **Kandidaten B (Einsatz):** jeder Phrasenanfang in den ersten ~40 % von B.
- **Längen:** 4 / 8 / 16 / 32 Takte (je nach Stil).
- Das sind etwa 10 × 6 × 4 = 240 Kombinationen je Paar, rund 2 ms Rechenzeit,
  weil nur die Takt-Profile verglichen werden.

**Punkte je Kombination** (Gewichte als Tabelle, je Stil anders):

| + gut | − schlecht |
|---|---|
| Blende endet genau, wo in B ein Drop/Hauptteil beginnt („B steht danach für sich" – Regel aus DJ-Interviews) | **Gesang A und B gleichzeitig hörbar** (je Takt, gewichtet mit den geplanten Lautstärken) |
| A ist im Fenster dünn/im Outro/Break, B im Intro | **zwei Basslines gleichzeitig** außerhalb des Tausch-Takts |
| A's Abschnittsgrenze fällt auf das Blendenende (A „hört natürlich auf") | Harmonie-Clash: Chroma der beiden Fenster passt nicht |
| Energie-Übergang passt zum Stil-Ziel (gleich / steigern / beruhigen) | B's Drop oder erster Gesang **mitten in** der Blende (außer bei Double Drop) |
| Raster in beiden Fenstern sicher | A zu früh verlassen (unter Spielanteil) oder B's Anfang zu stark übersprungen |
| | Tempo instabil im Fenster |

Ergebnis: Ausstiegstakt, Einsatztakt, Länge, Lage-Beschreibung (z. B.
„A Outro ohne Gesang → B Intro, Drop nach der Blende").

## Baustein 3 · Rezept wählen (aus der Lage)

Die Lage aus Baustein 2 (Gesang V/NV auf beiden Seiten, Tonart, ΔBPM,
Energierichtung, Break, Raster-Vertrauen) wählt das Rezept aus der Tabelle in
`KONZEPT-SMART-AUTODJ.md` §3. Eine Spalte gilt je Stil (Kurz / Ausgewogen /
Lang & komplex). Zwei Zusätze:
- **Abwechslung:** dasselbe Rezept nicht zweimal hintereinander; bei Gleichstand ein Hauch Zufall.
- **Top-3 statt nur 1:** Die zwei nächstbesten Kombinationen bleiben gemerkt.
  Ein Knopf „anderer Übergang" nimmt die nächste, ohne Neuberechnung.

Ausgabe ist ein **Übergangsplan als Daten** (ADR-019): Ausstieg, Einsatz,
Takte, Tempo-Kurve und **Automationskurven je Deck**: Lautstärke, Bass,
Mitten, Höhen, Filter, Effekte, Loop, Stems. Dazu ein Grund in einem Satz.

## Baustein 4 · Präziser Klang: Höhen, Mitten, Bass wie am DJ-Mixer

Neuer Renderer für den Plan aus Baustein 3, ersetzt die heutigen festen Fenster:

1. **3-Band-Isolator wie ein Club-Mixer:** Bänder Bass < ~200 Hz,
   Mitten 200 Hz–2,5 kHz, Höhen > 2,5 kHz. Nullphasig getrennt, Summe = Original
   (wie heute `band_teilen`). Regelbereich von −∞ (Kill) bis 0 dB
   (Isolator-Prinzip wie DJM-Mischpulte).
2. **Kurven in dB statt linear:** Ein Regler „klingt" logarithmisch. Lineare
   Amplituden-Rampen wirken lange stumm und dann plötzlich laut.
3. **Reihenfolge wie Profis** (Standard-Blend):
   - B's Höhen zuerst (Hi-Hats als neue Ebene)
   - dann Mitten tauschen; Gesang und Melodie leben hier, deshalb gehen A's Mitten raus, sobald B's Mitten kommen
   - **Bass-Tausch in einem Schlag auf einem Phrasen-Downbeat**, an der Stelle, wo B's Bassline laut Profil wirklich einsetzt oder A's Bass Pause macht
   - zuletzt A's Höhen raus
4. **Mit Stems** (Vorrat da) steuert die Kurve Drums, Bass, Harmonie und Gesang
   statt Frequenzbänder. Das ist präziser, weil ein EQ-Bass-Cut auch die Kick
   von A abschneidet und Gesang aus den Mitten nicht ganz entfernt.
5. **Pegel-Regelung je Band:** Aus dem Profil (Pegel je Band und Takt) werden
   die Kurven so nachkorrigiert, dass die Summe je Band in der Blende auf dem
   Zielpegel bleibt: keine Delle, kein Buckel, kein Doppelbass. Danach greift der Limiter.
6. Bausteine aus „eigene Kombination" (Filter, Hall, Echo, Loop) bleiben und
   werden vom Rezept gesetzt.

## Baustein 5 · Selbstkontrolle nach dem Backen

Bevor ein Übergang gespielt wird, misst der Mixer das fertige Ergebnis:
- Gesangs-Überlappung in Sekunden (aus den Stems)
- Doppelbass-Takte (beide Bass-Bänder laut)
- Lautheitsverlauf (Kurzzeit-LUFS: Delle oder Buckel > 2 dB?)
- Spitzen, Phrasenlage

Fällt ein Wert durch, nimmt er automatisch die nächstbeste Kombination
(Top-3). Alles landet im Protokoll. So sehen wir auch ohne Hören, ob V2 besser
ist als V1.

## Baustein 6 · Set-Ebene

- **„Perfekte Reihenfolge"** berücksichtigt künftig, wie gut sich zwei Titel
  wirklich mischen lassen (Bestwert aus Baustein 2, grob), nicht nur Tonart und
  Tempo.
- **Energiebogen** je Stil (Warm-up → Höhepunkt → Ausklang) als Ziel für die
  Energierichtung im Bewertungsschema.
- Die Tempo-Rampe darf über mehrere Titel driften und kehrt zum
  Originaltempo zurück (Profis ändern 86 % der Titel um weniger als 5 %).

## Baustein 7 · Oberfläche

- Oben neuer Regler **Mix-Stil**: Manuell (heutige Einstellungen) · Kurz &
  sauber · Ausgewogen · Lang & komplex.
- NÄCHSTER-Zeile mit Grund, z. B. „Drums zuerst · 16 Takte · A Outro ohne
  Gesang → B Intro, Drop nach der Blende · 8A→9A · +1,2 BPM".
- Knopf **„anderer Übergang"**.
- Etiketten (Intro/Drop/Break/Outro) als Farbstreifen über der Wellenform;
  die Blende als markierter Bereich in beiden Spuren.
- Die bestehenden Kurven zeigen dann Bass, Mitten und Höhen getrennt.

## Baustein 8 · Lernen (später, klein)

WEITER während einer Blende oder „anderer Übergang" zählt als Minuspunkt für
Rezept und Lage. Die Gewichte passen sich lokal leicht an, ohne Cloud.

---

## Reihenfolge und Prüfung

| Schritt | Inhalt | Fertig, wenn |
|---|---|---|
| 0 | GPU, Stem-Vorrat ganze Bibliothek | Faktor gemessen, alle Titel ✓ |
| 1 | Titel-Profil + Etiketten | Tests mit synthetischen Songs; Stichprobe 20 echte Titel: Etiketten plausibel (Bild zum Prüfen) |
| 2+3 | Cue-Suche + Rezeptwahl | je Tabellenzeile ein Test; Echt-Matrix 30 Paare: weniger Gesangs-Clash und Doppelbass als V1 (gemessen) |
| 4 | 3-Band-Renderer in dB, Pegelregelung | Pegel je Band in der Blende ±1,5 dB vom Ziel; kein Knacken (bestehende Prüfungen) |
| 5 | Selbstkontrolle | fällt durch → Ersatz greift (Test) |
| 7 | Oberfläche | live: Stil wechseln, Grund sichtbar, „anderer Übergang" |
| – | **Hörtest durch dich** | 10 Übergänge je Stil, V1 gegen V2 blind, Note 1–5 |
| 6, 8 | Set-Ebene, Lernen | danach |

Jeder Schritt wird einzeln getestet und auf Wunsch einzeln committet.

## Entscheidungen, die ich von dir brauche

1. **Spielanteil:** Darf der Auto-DJ einen Song früher verlassen, wie DJs es
   tun (z. B. nach dem letzten Refrain, ~60–80 % des Songs), oder sollen Songs
   möglichst ganz laufen? Vorschlag: einstellbar, Standard „nach dem letzten
   Höhepunkt".
2. **Stem-Speicher:** nur Anfang und Ende je Titel (~24 MB, ~8 GB für die
   Bibliothek) oder ganze Songs (~50 MB, ~16 GB; dann sind auch frühe Ausstiege
   mit Stems möglich)? Auf G: sind 95 GB frei. Vorschlag: ganze Songs.
3. **Stil-Stufen:** reichen die drei (Kurz / Ausgewogen / Lang & komplex) plus
   „Manuell"?

## Quellen

Siehe `KONZEPT-SMART-AUTODJ.md`, dazu für die EQ-Reihenfolge:
- [Violet Recording, How to EQ Mix as a DJ](https://violetrecording.com/how-to-eq-mix-as-a-dj/)
- [DJ.Studio, DJ EQ Mixing](https://dj.studio/blog/dj-eqmixing)
- [mixgraph, Bass swap](https://www.mixgraph.io/glossary/bass-swap)
- [DJM-900NXS2 Spezifikation (EQ −26…+6 dB, Isolator −∞…+6 dB)](https://www.knightsoundandlight.com/products/pioneer-djm-900nxs2)
