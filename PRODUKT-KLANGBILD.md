# Klangbild — Produktdokument vor dem Bau

**Stand: 06.10.2026 · Verfasser: Produktentwicklung**
Dieses Dokument wird geschrieben, **bevor** eine Zeile Code entsteht. Es denkt
die Idee zu Ende, prüft die Werkzeuge, benennt die Risiken und legt fest, woran
wir messen. Die technische Werkzeug-Recherche liegt ausführlich in
`ANDROID-AUTODJ-TOOLCHAIN-2026.md`.

**Kurz gefasst:** ein normaler Musik-Player (Vorbild Poweramp) mit einem
zuschaltbaren Auto-DJ. Gemma macht die **Auswahl** und das **Verstehen**. Die
**Übergänge** macht Signalverarbeitung.

---

## 1 · Pressemitteilung (zuerst geschrieben, nach der Regel „vom Kunden her denken")

> **Klangbild: dein Player, der auflegt**
>
> *Ein Musik-Player für eigene Dateien, der auf Wunsch die Übergänge selbst
> macht. Kein Abo, kein Konto, nichts in der Cloud.*
>
> Wer seine Musik selbst besitzt, kennt das Problem: Der Player spielt brav ab,
> aber die Playlist muss man bauen, und zwischen zwei Songs ist Funkstille.
> Klangbild schaltet auf Wunsch den Auto-DJ ein. Aus der ganzen Bibliothek
> entsteht eine Playlist, die zusammenpasst: nach Stimmung, Tempo und Tonart.
> Die Übergänge setzt die App auf den Takt, mit Bass-Tausch, Filter, Echo und
> Endlos-Schleifen, wie ein DJ.
>
> Das Besondere: Die App wählt nicht nach Metadaten, sondern nach **Klang**.
> Ein Modell auf dem Gerät versteht, wie ein Song wirkt. Und weil alles lokal
> läuft, verlässt kein einziger Ton und kein Hörgeschmack das Handy.
>
> „Ich wollte die Bequemlichkeit eines Streaming-Dienstes ohne die Cloud und
> ohne Abo", sagt die Entwicklerin. „Deine Dateien bleiben deine Dateien."
>
> Klangbild erscheint im Google Play Store. Einmalig 7,99 Euro. Kein Abo.

**FAQ zur Pressemitteilung (die Fragen, die ein Kunde stellen würde)**

- **Brauche ich ein Konto?** Nein.
- **Gehen meine Daten in die Cloud?** Nein, es gibt keinen Server.
- **Was, wenn ich keinen Auto-DJ will?** Dann ist es ein normaler Player. Die
  KI ist abschaltbar und stört nie.
- **Funktioniert es offline?** Ja, vollständig.
- **Kann ich eingreifen?** Jederzeit: überspringen, mehr Energie, ruhiger.
- **Warum kein Abo?** Es gibt keinen Server, also keinen Grund dafür.

---

## 2 · Problem und Warum jetzt

**Das Problem.** Drei Dinge nerven bei eigenen Dateien:
1. **Ordnung.** Tags sind falsch oder leer. Man sucht, was man nicht benennen
   kann.
2. **Playlist-Arbeit.** Eine gute Reihenfolge muss man selbst bauen.
3. **Der Übergang.** Zwischen zwei Songs ist Funkstille, kein Fluss.

**Warum jetzt.** Zwei Dinge sind neu zusammen:

1. **EmbeddingGemma 2** (6. Oktober 2026) kann erstmals **Ton auf dem Gerät**
   verstehen und in Vektoren legen. Damit wird „Auswahl nach Klang" lokal
   möglich, ohne Cloud und ohne Serverkosten.
2. **Signalsmith Stretch (MIT)** und **Oboe (Apache-2.0)** erlauben eine eigene,
   lizenzfreie Audio-Engine mit Time-Stretch und niedriger Latenz. Vorher hieß
   das entweder teures SDK oder GPL.

**Was gemessen ist und was nicht.**

| Aussage | Status |
|---|---|
| Es gibt keinen lokalen Player mit Auto-DJ nach Klang | plausibel, im Wettbewerbscheck geprüft (Abschnitt 11) |
| GPL/AGPL blockieren die naheliegenden Analyse-Tools | **belegt** (Lizenzrecherche) |
| Signalsmith Stretch ist MIT und kommerziell frei | **belegt** |
| Leute zahlen für einen Player | belegt in der Kategorie (Poweramp) |
| Leute zahlen speziell für den Auto-DJ | **nicht belegt**, muss getestet werden |
| Wie groß der Markt lokaler Sammlungen ist | **nicht gemessen**, eher klein (Abschnitt 12) |

---

## 3 · Zielgruppe

**Erste Zielgruppe (eng):** Menschen mit einer **eigenen, größeren Sammlung**.
Dazu gehören DJs, Sammler, Musiker und alle, die oft **offline** unterwegs sind
(Auto, Flugzeug, Ausland, ohne Datenvolumen).

**Persona:** „Tom, 41, hat 8.000 Titel auf dem Handy. Auf der Fahrt will er
Musik ohne Werbung, ohne Netz und ohne dass er eine Playlist bauen muss. Er
würde gern einen fließenden Übergang, aber kein DJ-Programm lernen."

**Zweite Zielgruppe (später):** Hobby-DJs, die einen einfachen Assistenten
wollen, aber kein teures Programm.

**Bewusst nicht erste Zielgruppe:** Profi-DJs. Die brauchen Hardware, tiefe
Kontrolle und stehen auf Rekordbox, Serato und Traktor.

---

## 4 · Positionierung

**Für** Menschen mit eigener Musiksammlung,
**die** Musik ohne Abo, offline und mit fließenden Übergängen wollen,
**ist Klangbild** ein Musik-Player mit Auto-DJ,
**der** aus der ganzen Bibliothek eine passende Playlist baut und die Übergänge
wie ein DJ setzt,
**anders als** Poweramp, Spotify oder DJ-Programme,
**weil** er nach Klang auswählt, komplett auf dem Gerät läuft und kein Abo
verlangt.

**Der eine Satz:** Ein Player, der die Übergänge selbst macht und nie in die
Cloud schaut.

---

## 5 · Kernfunktionen

Priorisiert nach MoSCoW. Die Spalte „Motor" sagt, wer die Arbeit macht:
**Gemma** (Auswahl, Verstehen), **DSP** (Signalverarbeitung), **Player**
(Standard-Wiedergabe).

### 5a · Normaler Player (muss zuerst perfekt sein)

| Priorität | Funktion | Motor |
|---|---|---|
| Muss | Bibliothek: Ordner, Alben, Künstler, Genres | Player |
| Muss | Wiedergabe ohne Lücke (Gapless) | Player (Media3) |
| Muss | Tags **lesen** | Player (TagLib) |
| Muss | Tags **schreiben** | Player (TagLib) |
| Muss | Suche, Queue, Wischgesten, Widget, Benachrichtigung | Player |
| Muss | Kopfhörertasten, Sleep-Timer, Equalizer | Player |
| Muss | Formate: MP3, AAC, FLAC, OGG, Opus, WAV, ALAC | Player |

> **Korrektur 08.10.2026 (Roadmap Phase 4):** „Tags **schreiben**" ist von
> „Muss" auf **„Soll"** herabgestuft – Scoped Storage braucht je Datei eine
> Zustimmung, und das Schreiben ändert den Hash-Speicher (ADR-013). Ohne
> Tag-Schreiben in Version 1 ist der Auto-DJ voll funktionsfähig. „Tags lesen"
> bleibt Muss. Die Zeile oben bleibt als Original stehen.

### 5b · Klang-Verstehen (der Gemma-Teil)

| Priorität | Funktion | Motor |
|---|---|---|
| Muss | Klang-Vektor je Song („klingt ähnlich") | **Gemma** (EmbeddingGemma 2) |
| Muss | Suchen mit Worten („etwas Ruhiges fürs Einschlafen") | **Gemma** + Vektorsuche |
| Soll | Stimmungs-Label und stimmungsbasierte Listen | **Gemma 4** |
| Soll | Kaputte Tags reparieren, fehlende ergänzen | **Gemma 4** |
| Soll | „Mehr wie das" (Sofort-Radio aus eigenen Dateien) | **Gemma** + Vektorsuche |

### 5c · Auto-DJ (der Kern des Produkts)

| Priorität | Funktion | Motor |
|---|---|---|
| Muss | Auto-DJ ein- und ausschalten | Player/Logik |
| Muss | Playlist aus der ganzen Bibliothek nach Stimmung, Tempo, Tonart | **Gemma** (Auswahl) + Logik |
| Muss | Einfaches Überblenden der Songs | DSP |
| Muss | Übergänge auf der Taktgrenze (Loops, Cues) | DSP |
| Soll | **Beatmatching**: Tempo angleichen, Tonhöhe halten (Keylock) | DSP (Signalsmith) |
| Soll | **Bass-Tausch** und 3-Band-EQ-Übergänge | DSP (Custom) |
| Soll | **Filter-Sweep** (Hoch-/Tiefpass) als Übergang | DSP (Custom) |
| Soll | **Looping** und Roll-Effekte im Übergang | DSP |
| Soll | **Echo/Reverb-Auslauf** als Übergang | DSP (Custom) |
| Soll | Harmonische Auswahl (Camelot-Rad), optional Key-Shift | Logik + **Gemma** |
| Kann | Energie-Reise: „2 Stunden, ruhig zu euphorisch" | **Gemma 4** + Planer |
| Kann | Struktur nutzen: Übergang vor dem Drop | DSP (Signal) |
| Kann | Stimm-Modus: Gesang/Instrumente trennen (offline) | Demucs |

**Der Kern in einem Satz:** Ohne Gemma gäbe es keine Auswahl nach Klang und
Stimmung. Ohne DSP gäbe es keine Übergänge. Beides zusammen ist das Produkt.

---

## 6 · Nutzerfluss

**Normaler Modus**
App öffnen, Song antippen, spielt. Keine KI im Weg.

**Auto-DJ einschalten**
Ein Tipp auf „Auto-DJ". Optional ein Wunsch in Worten („Party, eher treibend").
Die App baut eine Reihenfolge und beginnt zu mischen.

**Eingreifen**
Während der Fahrt: „mehr Energie", „ruhiger", „nächster". Die App plant neu.

**Der Übergang (das Herz)**
Kurz vor dem Ende von Song A startet Deck B. Beide laufen auf demselben Beat.
Die App zieht das Tempo an, tauscht den Bass, schwenkt den Filter und blendet
über. Der Hörer merkt nur, dass es weitergeht.

---

## 7 · Was bewusst NICHT gebaut wird (Non-Goals)

- **Kein Streaming.** Nur eigene Dateien.
- **Keine Cloud, kein Konto.** Keine Server, keine Nutzerkonten.
- **Kein Abo.** Einmal kaufen, für immer nutzen.
- **Kein Profi-DJ-Werkzeug.** Kein Vier-Deck, kein MIDI-Controller-Zoo, kein
  Aufnahme-Studio.
- **Keine soziale Funktion.** Kein Teilen, keine Charts.
- **Keine Echtzeit-Stem-Trennung.** Stem-Trennung läuft offline und wird
  gecacht, nicht live (Abschnitt 8).
- **Keine Werbung.**

---

## 8 · Technik und Architektur

### 8a · Die Grundentscheidung

Es gibt **zwei Audio-Pfade**:

1. **Normaler Player** über **AndroidX Media3 / ExoPlayer 1.11.x** (Apache-2.0).
   Das ist der ausgereifte Standard für Bibliothek, Wiedergabe, MediaSession,
   Android Auto und Gapless.
2. **Auto-DJ-Mixer** als **eigene native Engine auf Oboe** (Apache-2.0).

**Warum nicht Media3 für den Mixer:** Media3s `DefaultAudioSink` arbeitet mit
über 250 ms Puffer und kennt kein Zwei-Deck. Für sample-genaues Beatmatching
ist das der falsche Layer. Deshalb eine eigene Engine.

### 8b · Die Mixer-Engine

```
 Song A ─▶ [Decode] ─▶ [Time-Stretch/Keylock] ─▶ [EQ/FX] ─▶ [Gain] ─┐
                                                                     ├─▶ [Mix] ─▶ Oboe/AAudio ─▶ Lautsprecher
 Song B ─▶ [Decode] ─▶ [Time-Stretch/Keylock] ─▶ [EQ/FX] ─▶ [Gain] ─┘
```

- **Ein einziger Audio-Callback** (Oboe, `PerformanceMode::LowLatency`,
  `SharingMode::Exclusive`, AAudio MMAP) liest beide Decks aus Ringpuffern und
  mischt im **gleichen Sample-Raster**. Damit sind beide Decks fest
  synchronisiert.
- **Decoding** über MediaCodec (Plattform) oder native Decoder. Achtung bei
  FFmpeg: Die LGPL/GPL-Variante muss bewusst gewählt werden.
- **Time-Stretch/Keylock:** **Signalsmith Stretch (MIT)** als Standard. Klingt
  am besten bei moderaten Dehnungen (etwa 0,75 bis 1,5 fach), und genau dort
  spielt sich Beatmatching ab. Fallback: SoundTouch (LGPL).
- **Effekte:** eigene DSP-Kette (Biquad-/SVF-Filter, Delay, 3-Band-EQ) plus
  MIT-Bausteine aus `signalsmith-audio/dsp`.

### 8c · Die Analyse-Schicht (läuft einmal vorab)

Pro Datei werden berechnet und gespeichert, geknüpft an einen
**Datei-Fingerabdruck (Hash)**: ändert sich nichts, wird nichts neu gerechnet.

| Wert | Motor |
|---|---|
| Tempo (BPM), Beat-Raster, Downbeat | Analyse |
| Tonart + Camelot-Code | Analyse |
| Lautheit (LUFS) | Analyse |
| Energie-Kurve | Signal (RMS) |
| Abschnitte (Intro, Build, Drop, Break) | Signal (Neuheits-Kurve) |
| **Klang-Vektor** | **EmbeddingGemma 2** |
| Stimmungs-Label | ~~**Gemma 4**~~ → Zero-Shot über EmbeddingGemma 2 (ADR-015) |

**Die Lizenzfalle hier ist die größte im ganzen Projekt.** Die naheliegenden
Analyse-Tools sind fast alle Copyleft:
Essentia **AGPLv3**, aubio **GPLv3**, libKeyFinder **GPLv3**, QM-DSP **GPLv2**,
Rubber Band **GPLv2**. Für eine geschlossene App heißt das: kaufen oder selbst
bauen. Zusätzlich sind die **Essentia-Modelle CC BY-NC-ND** und die
**madmom-Modelle CC BY-NC-SA**, also **nicht kommerziell**, obwohl der
madmom-Code selbst BSD ist.

**Unser Ausweg:** Analyse **offline und vorgelagert** mit **librosa (ISC,
kommerziell frei)** beim Einlesen der Bibliothek, oder eine **eigene,
schlanke Implementierung** für BPM/Beat/Key auf dem Gerät. Kein AGPL-Code im
Produkt.

> **Abgelöst 08.10.2026 (ADR-012):** librosa ist Python und liefert weder Tonart
> noch Downbeats. Gültig sind **Beat This!** (MIT) für Beats/Downbeats, eine
> **eigene** Tonart-Schätzung (Chroma + Key-Profile) und **libebur128** (MIT) für
> LUFS – auf PC und Android mit demselben Verfahren, damit die gemessene
> Genauigkeit überträgt.

### 8d · Die KI-Schicht

- **Einbetten:** EmbeddingGemma 2 über **LiteRT-LM** (ab v0.18.0 mit offizieller
  Unterstützung für EmbeddingGemma-2-**Audio** in Kotlin und C++, inklusive
  MRL-Kürzung); Rückfall MediaPipe Universal Embedder bzw. ONNX Runtime. Kürzen
  auf 256 Dimensionen (Matrjoschka) gegen Speicher.
- **Vektorsuche:** **sqlite-vec** / **USearch** – oder, solange die Bibliothek
  unter 50.000 Titeln bleibt, ein einfacher Kosinus über alle Vektoren
  (8.000 × 256 = 8 MB, dafür braucht es keinen Index).
- **Antworten/Auswahl:** **LiteRT-LM** mit **Gemma 4 E2B/E4B** (optionaler
  Download, ADR-015).
- **Runtime-Lizenz:** LiteRT und LiteRT-LM sind Apache-2.0. **EmbeddingGemma 2
  steht ebenfalls unter Apache 2.0** (Modellkarte und Developer Guide); es gilt
  zusätzlich die Gemma Prohibited Use Policy. **Gemma-4-Gewichte** laufen unter
  der **Gemma-Lizenz** (kommerziell erlaubt, mit Auflagen).

> **Korrektur 08.10.2026 (ADR-015):** EmbeddingGemma 2 ist **Apache 2.0**,
> nicht „Gemma-Terms". Der frühere Vermerk „vor Nutzung klären" ist erledigt.
> Die Angabe unten in 8e ist entsprechend korrigiert.

### 8e · Der vollständige Werkzeug-Stack

| Baustein | Empfehlung | Lizenz | Kommerziell |
|---|---|---|---|
| Player-Basis | Media3 / ExoPlayer 1.11.x | Apache-2.0 | ja |
| Audio-Engine | Oboe (AAudio MMAP/Exclusive) | Apache-2.0 | ja |
| Decoding | MediaCodec (Plattform) | AOSP | ja |
| Time-Stretch | **Signalsmith Stretch** (Fallback SoundTouch) | MIT / LGPL | ja |
| Analyse (Beats/Downbeats) | **Beat This!** (Code und Gewichte) | MIT | ja |
| Analyse (Tonart) | **eigene Implementierung** (Chroma + Key-Profile) | eigen | ja |
| Analyse (Lautheit) | **libebur128** | MIT | ja |
| Effekte | **Custom-DSP** + signalsmith dsp | MIT / eigen | ja |
| Embeddings | EmbeddingGemma 2 (LiteRT-LM) | **Apache-2.0** | ja (+ Prohibited Use Policy) |
| Sprachmodell | LiteRT-LM + Gemma 4 (E2B/E4B) | Gemma-Lizenz | Auflagen |
| Vektorsuche | Kosinus / sqlite-vec / USearch | Apache-2.0 / MIT | ja |
| Stem-Trennung | Demucs v4 über ONNX, offline, INT8 | MIT | ja |
| Tags | TagLib (LGPL/MPL) via NDK | LGPL/MPL | ja mit Auflagen |

> **Korrektur 08.10.2026 (ADR-012, ADR-015):** Die Zeilen „Analyse" und
> „Embeddings" der ersten Fassung (librosa bzw. „Gemma-Terms / klären") sind
> ersetzt; Beat This!, libebur128 und die eigene Tonart-Schätzung ergänzt.

**Die drei größten Lizenzfallen:**
1. **AGPL/GPL in der Analyse** (Essentia, aubio, libKeyFinder, QM-DSP, Rubber
   Band). Nicht ohne Kauf oder Quelloffenlegung.
2. **CC-„NC"-Modelle** (Essentia-Modelle, madmom-Modelle). Nicht kommerziell,
   auch wenn der Code frei ist. Dazu: die Superpowered-Evaluation erlaubt nur
   1.000 Installationen.
3. **Versteckte Kosten.** Superpowered (etwa 6.000 bis 10.000 je Jahr) und
   zplane élastique (Royalty) sind Bezahl-SDKs. JUCE ist AGPL und damit für eine
   geschlossene App kaufpflichtig.

### 8f · Die Übergangs-Engine im Detail (Beatmatching, Loop, Effekte)

Das ist der Teil, den der Nutzer hört. Er baut auf **DSP**, nicht auf Gemma.

- **Beatmatching:** Beide Decks laufen auf derselben Tempo- und Phasenlage. Der
  Rate-Regler von Deck B wird auf das Tempo von A gezogen (Signalsmith Stretch),
  die Downbeats werden ausgerichtet.
- **Keylock:** Tempo ändern ohne Tonhöhenänderung. Ohne das klingt Beatmatching
  wie ein beschleunigtes Band.
- **Harmonisch:** Auswahl über das Camelot-Rad. Optional B per Pitch-Shift in die
  Tonart von A ziehen, vorsichtig dosiert.
- **Cue-Punkte und Loops:** Ein- und Ausstiegspunkte liegen auf der Taktgrenze.
  Beatlange Loops und Roll-Effekte sind Standard.
- **Bass-Tausch:** Zu Beginn des Übergangs wird der Bass von B abgesenkt, dann in
  einem Takt auf A/B umgeschaltet. Verhindert, dass sich zwei Bässe beißen.
- **Filter-Sweep:** Hoch- oder Tiefpass wandert über den Übergang. Klassisch und
  billig.
- **Echo/Reverb-Auslauf:** Song A läuft mit Echo aus, während B schon spielt.
- **Phrasierung:** Übergänge beginnen am Ende einer 8er- oder 16er-Phrase.
- **Struktur:** Wenn erkannt, wird der Übergang direkt vor den Drop von B gelegt.

> **Abgelöst (08.10.2026):** gültig ist nur noch `ROADMAP-KLANGBILD.md` (ADR-011). Version 1 gleicht das Tempo per Resampling an (ADR-014).

**Erste Version klein halten:** In Version 1 nur **Überblenden plus Songs, die
im Tempo nah liegen**. Kein Tempostrecken, kein Key-Shift. Das spart die halbe
Schwierigkeit und klingt schon ordentlich. Beatmatching und Effekte kommen in
Version 2 und 3.

---

## 9 · Datenschutz und Recht

- **DSGVO:** kein Server, keine Übermittlung. Datenschutzerklärung kurz und
  ehrlich.
- **Kein Konto.**
- **Lizenzen:** Die Lizenzprüfung (Abschnitt 8e) ist **vor** dem Bau zu
  erledigen, nicht danach. Ein falsch eingebundenes AGPL-Teil kann das Produkt
  unverkäuflich machen.
- **Modell-Lizenzen:** Gemma-Teil vor der Veröffentlichung mit den
  Gemma-Terms abgleichen.
- **Musikrechte:** Die App spielt nur Dateien, die der Nutzer besitzt. Kein
  Katalog, keine Rechtefragen. Lyrics-Funktionen (falls später) vorher klären.

---

## 10 · Monetarisierung

- **Einmalzahl**, etwa 7,99 Euro. Vorbild Poweramp, das genau so funktioniert.
- **Optional:** eine höhere Stufe (etwa 14,99 Euro) mit Auto-DJ und
  Stem-Werkzeugen.
- **Warum Einmalzahl möglich ist:** kein Server, keine laufenden Kosten.
- **Keine Abo-Falle, keine Testphase-Falle.**

---

## 11 · Wettbewerb und Differenzierung

| Gegner | Stärke | Unsere Antwort |
|---|---|---|
| Poweramp, Musicolet, VLC, AIMP | gute Player, Tags | wir wählen nach Klang und mischen |
| Spotify, YouTube Music | Bequemlichkeit, Empfehlung | wir sind lokal, offline, ohne Abo |
| Mixxx, Virtual DJ, djay | echter Auto-DJ | sie sind groß und für Profis; wir sind ein Player für alle |
| Superpowered-basierte Apps | Technik | teuer; wir bauen auf MIT auf |

**Unsere echte Differenz:** Auswahl **nach Klang** statt nur nach BPM und
Tonart, dazu **lokal, offline und ohne Abo**. Das Mischen selbst ist gelöst
(Mixxx kann es), die Auswahl nach Klang ist der neue Teil.

---

## 12 · Risiken und Gegenmaßnahmen

| Risiko | Wahrscheinlichkeit | Wirkung | Gegenmaßnahme |
|---|---|---|---|
| Lizenzfalle (AGPL/GPL) zu spät entdeckt | mittel | hoch | vor dem Bau klären, permissive Werkzeuge wählen |
| Markt klein (lokale Sammlungen) | hoch | hoch | ehrlich prüfen, mit Warteliste testen |
| Rechenlast (Analyse, Time-Stretch) | mittel | mittel | Voranalyse im Hintergrund, nur am Ladegerät |
| Falsches Beat-Raster | mittel | hoch | Sicherheitswert prüfen, sonst nur überblenden |
| Erste Analyse dauert lang | hoch | mittel | fortsetzbar, mit Fortschritt, im Hintergrund |
| Falsche Modell-Lizenz | niedrig | hoch | vor Release abgleichen |
| Nachahmung durch Google | niedrig | mittel | Nische, nicht Plattformfunktion |

---

## 13 · Erfolgsmessung

**Nordstern:** Anteil der Nutzer, die den **Auto-DJ mindestens einmal pro Woche**
nutzen. Nicht Downloads. Der Auto-DJ ist das Versprechen.

**Aktivierung:** Erste Wiedergabe **und** erste Auto-DJ-Session in den ersten
Sitzungen.

**Qualität:** Anteil der Übergänge ohne hörbaren Fehler (interner Hörtest).

**Bindung:** Anteil der Nutzer im vierten Wochenfenster.

**Geld:** Anteil der Warteliste, die kauft.

---

## 14 · Validierung vor dem Bau (Reihenfolge entscheidend)

> **Korrektur 08.10.2026 (ADR-011, ROADMAP-KLANGBILD.md):** Die Reihenfolge hat
> sich geändert – die **Landingpage kommt nicht mehr zuerst**. Sie braucht eine
> Hörprobe, und die existiert erst nach Phase 1 (gerenderter Mix). Gültige
> Reihenfolge: **PC-Prototyp (Phase 0) → Hörtest (Phase 1) → Landingpage
> (Phase 2)**. Das Prinzip „erst messen, dann bauen" bleibt unverändert.

1. ~~**Landingpage mit Warteliste.**~~ *(jetzt Phase 2)*
2. **Hörprobe.** Zwei Beispiel-Übergänge vorführen (vorher/nachher). Ist der
   Unterschied hörbar und begeistert er?
3. **Prototyp der Engine.** Zwei Songs sauber überblenden und tempo-angleichen.
4. **Test mit 10 Nutzern.** Aufgabe: 30 Minuten Auto-DJ hören und bewerten.
5. **Erst dann** bauen.

**Diese Reihenfolge ist die Lehre des Projekts:** 28 Ideen sind gescheitert,
weil von einer Beobachtung direkt auf ein Produkt geschlossen wurde.

---

## 15 · Tötungskriterien (wann wir aufhören)

- **Landingpage:** 500 Besucher und unter 5 Anmeldungen.
- **Hörprobe:** Testhörer hören keinen Unterschied oder finden es schlechter.
- **Prototyp:** Beatmatching klingt hörbar falsch und lässt sich nicht fixen.
- **Lizenz:** Der nötige Werkzeug-Stack lässt sich nicht ohne unbezahlbare
  Lizenz bauen.
- **Technik:** Die Engine läuft auf dem Zielgerät nicht stabil.

---

## 16 · MVP und Phasen (nach Ergebnis, nicht nach Zeit)

> **Abgelöst (08.10.2026):** gültig ist nur noch `ROADMAP-KLANGBILD.md` (ADR-011).

**Phase A · Player.** Bibliothek, Wiedergabe, Tags, Playlists, Widgets. Kein
Auto-DJ. Ziel: fühlt sich wie Poweramp an.

**Phase B · Verstehen.** Analyse (BPM, Key, Vektor), Suchen mit Worten,
Stimmungslisten. Ziel: die App kennt die Sammlung.

**Phase C · Auto-DJ einfach.** Auswahl nach Harmonie, Tempo, Stimmung. Nur
Überblenden. Ziel: es läuft eine Stunde ohne Fehler.

**Phase D · Übergangs-Engine.** Beatmatching, Keylock, Bass-Tausch, Filter,
Loops, Echo. Ziel: es klingt wie ein DJ.

**Phase E · Extras.** Energie-Reise, Wunsch in Worten, Stem-Trennung offline.

**Abnahmekriterien Phase C:**
- Auto-DJ läuft eine Stunde ohne hörbaren Fehler.
- Übergänge sitzen auf der Taktgrenze.
- Kein Netzwerkverkehr (nachweisbar).
- Eingreifen ist jederzeit möglich, ohne Abbruch.

**Abnahmekriterien Phase D:**
- Beatmatching hält zwei Songs im Raster, Tonhöhe bleibt.
- Bass-Tausch und Filter-Sweep funktionieren und sind hörbar sauber.
- Loop und Echo-Auslauf laufen stabil.

---

## 17 · Offene Fragen

1. **Marktgröße.** Lokale Sammlungen sind klein und treu, nicht groß. Offen.
2. **Zahlbereitschaft für den Auto-DJ extra.** Nur außerhalb der Stores messbar.
3. **Rechenlast** von Analyse und Time-Stretch auf echten Mittelklasse-Geräten
   → Phase 3.
4. ~~**Lizenz von EmbeddingGemma 2**~~ **geschlossen 08.10.2026: Apache 2.0**
   (Modellkarte, Developer Guide; ADR-015). Zusätzlich gilt die Gemma Prohibited
   Use Policy.
5. **Qualität der Stimmungs-Auswahl.** Nur im Hörtest zu klären.
6. **Ob die Engine-Entwicklung** für ein Einzelteam realistisch ist → Phase 0/3.
7. **Neu 08.10.2026 – taugt der Audio-Encoder für Musik?** Google beschreibt ihn
   als „speech and sound encoder", Musik ist in Trainingsdaten und Benchmarks
   nicht belegt → Phase 0.0/0.1, inklusive **Plan C** (eigene Merkmale statt
   Vektorraum), falls das Tor fällt.
8. **Neu – welcher Musik-Text-Encoder ist überhaupt lizenzierbar?** MuQ/OpenL3
   nicht-kommerziell, musicnn unklar → vor Plan B klären (ADR-012).
9. **Neu – CC-Musik für die öffentliche Hörprobe.** Sammlung plus
   Lizenz-Tabelle je Titel, Namensnennung auf der Seite (Phase 2).

---

## 18 · Anhang und Quellen

- Ausführliche Werkzeug-Recherche: `ANDROID-AUTODJ-TOOLCHAIN-2026.md`
- Vorherige Konzeptdokumente: `GEMMA-IDEEN.md`, `GEMMA-IDEEN-10.md`,
  `ARCHITEKTUR-KLANGBILD.md`
- Oboe: https://github.com/google/oboe
- Signalsmith Stretch: https://github.com/Signalsmith-Audio/signalsmith-stretch
- Media3: https://github.com/androidx/media
- EmbeddingGemma 2: https://developers.googleblog.com/embeddinggemma-2-the-developer-guide/
- LiteRT-LM: https://github.com/google-ai-edge/LiteRT-LM
- Essentia-Lizenz (AGPL): https://essentia.upf.edu/licensing_information.html
- Rubber Band Lizenz (GPL/kauf): https://breakfastquay.com/rubberband/license.html
- Mixxx: https://github.com/mixxxdj/mixxx
