# Klangbild — Gesamtarchitektur

**Stand: 06.10.2026**
Ein normaler Musik-Player (Vorbild: Poweramp) mit einem zuschaltbaren Auto-DJ.
Gemma macht die **Auswahl** und das **Verstehen**. Die **Übergänge** macht
Signalverarbeitung. Diese Trennung ist der ganze Kern des Plans.

---

## 1 · Die Grundidee in einem Bild

```
   Nutzer
     |
 [ Player-UI ]  Bibliothek, Suche, Queue, Widgets
     |
 [ Wiedergabe ] ExoPlayer/Media3, Gapless, EQ
     |
     +-------------------------------+
     |                               |
 [ Auto-DJ-Planer ]            [ Normaler Modus ]
   Auswahl + Reihenfolge          Song antippen
   (Gemma)                        (keine KI)
     |
 [ Übergangs-Engine ]
   Fade, EQ, Tempo, Takt
   (DSP, kein Gemma)
     |
 [ Analyse-Schicht ]  <- läuft EINMAL vorab
   BPM, Key, Energie, Struktur, Vektor
     |
 [ Lokale Datenbank ]
   Metadaten + Analyse + Vektoren
```

Zwei Betriebsarten, ein Fundament:
- **Normal:** wie Poweramp. Antippen, spielt. Keine KI im Weg.
- **Auto-DJ:** die App übernimmt. Sie wählt, ordnet und blendet.

---

## 2 · Modul 1 — Player-Fundament (der normale Player)

Damit es sich wie eine echte Musik-App anfühlt.

- **Dateizugriff:** Storage Access Framework und MediaStore. Ordner, Alben,
  Künstler, Genres, eigene Listen.
- **Tags:** lesen und schreiben (ID3, Vorbis, FLAC, M4A).
- **Formate:** MP3, AAC, FLAC, OGG, Opus, WAV, ALAC.
- **Wiedergabe:** ExoPlayer (Media3). Gapless, ReplayGain, Equalizer,
  Lautstärke-Angleich.
- **Bedienung:** Queue, Wischgesten, Widget, Benachrichtigung,
  Kopfhörertasten, Sleep-Timer, Ordner-Ansicht.
- **Zwischenspeicher:** lokale Datenbank (SQLite/Room) für schnelle Bibliothek.

Wichtig: Dieser Teil hat **nichts** mit KI zu tun. Er muss einfach nur sehr gut
sein. Sonst rettet der Auto-DJ nichts.

---

## 3 · Modul 2 — Analyse-Schicht (läuft einmal vorab)

Das ist der teure Teil, und man rechnet ihn **einmal** für die Bibliothek, nicht
während des Abspielens. Danach ist alles billig.

Pro Song wird berechnet und gespeichert:

| Wert | Wofür | Werkzeug |
|---|---|---|
| **Tempo (BPM)** | Mischen | Beat This! (ADR-012) |
| **Beat-Raster + Downbeat** | Übergang im Takt | Beat This! (ADR-012) |
| **Tonart + Camelot-Code** | harmonisches Mischen | **eigene Implementierung** (Chroma + Key-Profile, ADR-012) |
| **Lautheit (LUFS)** | gleich laute Songs | **libebur128** (MIT, ADR-012) |
| **Energie-Kurve** | Reise von ruhig nach laut | RMS über die Zeit |
| **Abschnitte (Intro, Build, Drop, Break)** | Übergang richtig setzen | Neuheits-Kurve aus Signal |
| **Klang-Vektor** | „ähnlich klingend", Stimmung | **EmbeddingGemma 2** (256 Dimensionen) |
| **Stimmungs-Label** | Auswahl nach Gefühl | ~~**Gemma 4** aus dem Vektor~~ → Zero-Shot im Einbettungsraum (ADR-015) |

> **Abgelöst 08.10.2026 (ADR-012):** Die drei Werkzeug-Zeilen der ersten Fassung
> nannten Essentia/madmom/aubio bzw. libKeyFinder – alle AGPL/GPL und damit für
> eine geschlossene App unbrauchbar. Oben steht die gültige Auswahl.
> **Ergänzung:** Jede Zeile bekommt ein **Vertrauensfeld** und die Tabelle einen
> `analysis_version`-Wert (nächster Abschnitt).

**Der wichtige Trick:** Alles hängt an einem **Datei-Fingerabdruck (Hash)**.
Ändert sich eine Datei nicht, wird nichts neu gerechnet. So analysiert die App
eine Bibliothek genau einmal.

**Ehrlich:** Die erste Analyse einer großen Sammlung dauert lange und zieht
Akkusaft. Sie läuft im Hintergrund, am Ladegerät, mit Fortschrittsanzeige.

---

## 4 · Modul 3 — Auto-DJ-Planer (hier wirkt Gemma)

Aufgabe: aus der ganzen Bibliothek eine **Reihenfolge** bauen, die sich gut
anhört.

**Die Bewertung eines Kandidaten** entsteht aus vier Teilen:

1. **Harmonie:** Abstand auf dem Camelot-Rad (gleiche oder benachbarte Tonart).
2. **Tempo:** nahe am aktuellen Song, oder sauberes Doppel oder Halb (140 zu 70).
3. **Klangbild:** Ähnlichkeit der Vektoren. „Klingt nach derselben Stimmung."
4. **Energie-Reise:** passt der Song in die gewünschte Kurve (ruhig zu euphorisch)?

Punkt 3 und 4 sind der neue Teil. Klassische Auto-DJs nutzen nur Punkt 1
und 2.

**Was Gemma 4 hier tut:**
- Es versteht den Wunsch in Worten: „zwei Stunden, entspannt zu euphorisch".
- Es gibt der Reise eine Richtung und wählt daraus Stimmungen.
- Es benennt das Set („Abendfahrt", „Langer Weg").
- Es **erklärt** die Wahl: „Dieser Song, weil plus 2 BPM und gleiche Tonart."

**Was Gemma 4 hier nicht tut:** BPM und Tonart rechnen. Das macht die
Signalanalyse. Ein Sprachmodell, das Sekunden oder BPM schätzt, liegt falsch.

---

## 5 · Modul 4 — Übergangs-Engine (DSP, kein Gemma)

Für jedes benachbarte Paar wird ein Übergang geplant und ausgeführt.

- **Typ:** Überblenden, Bass-Tausch, Filter-Sweep, harter Schnitt, Echo-Auslauf.
- **Länge:** in Takten (4, 8, 16), auf die Taktgrenze gesetzt.
- **Tempo-Angleich:** Song B an das Tempo von A anpassen (**Signalsmith Stretch**,
  ADR-003; in Version 1 per Resampling, ADR-014). Ohne Tonhöhenänderung
  (ab Phase 5, siehe ADR-014).
- **Harmonie:** bleibt die Tonart gleich, muss nichts passieren. Unterscheiden
  sie sich, kann man B per Pitch-Shift in die Tonart von A ziehen. Vorsichtig
  einsetzen, klingt schnell künstlich.
- **Phrasierung:** Übergang am Ende einer 8er- oder 16er-Phrase von A beginnen
  und bei B auf einem Downbeat landen.
- **Struktur nutzen:** den Übergang direkt vor den Drop von B oder nach dem
  Drop von A setzen. Das kommt aus der Abschnitts-Erkennung.
- **Klang:** zwei Spuren zusammenführen, 3-Band-EQ, Filter.

**Das technisch Schwierigste:** Android spielt normalerweise zwei Tonströme
getrennt. Für einen exakten, sample-genauen Übergang braucht man eine eigene
Audiokette (zwei Player plus eine eigene Misch- und Filterstufe, oder eine
native Engine wie Oboe). Das ist der Punkt, an dem aus „einfach" „echte
Entwicklungsarbeit" wird.

---

## 6 · Modul 5 — Wiedergabe im Auto-DJ

- Zwei **Decks**: Deck A spielt, Deck B ist vorgeladen und voranalysiert.
- Am Übergangspunkt mischt die Engine.
- Springt der Nutzer oder sucht etwas, plant der Planer ab dem aktuellen Song
  neu.
- Einfache Anzeige: zwei Decks, BPM, Tonart, wie viel Zeit bis zum Übergang.
- Steuerung während der Fahrt: „mehr Energie", „ruhiger", „nächster".

---

## 7 · Wer macht was (die wichtigste Tabelle)

| Aufgabe | Zuständig |
|---|---|
| BPM, Takt, Tonart | Signalanalyse (Beat This!, eigene Implementierung) |
| Energie-Kurve | Signal (RMS) |
| Drop und Abschnitte | Signal (Neuheits-Kurve) |
| „klingt ähnlich" | **EmbeddingGemma 2** |
| Stimmung benennen | **Zero-Shot im Einbettungsraum** (ADR-015), kein Gemma 4 nötig |
| Auswahl und Reihenfolge | Planer, gefüttert von Gemma-Vektoren |
| Set beschreiben und erklären | **Gemma 4** (optionaler Download, Phase 6) |
| Übergang ausführen | DSP (Signalsmith Stretch ab Phase 5, Filter, EQ) |

Wer das verwechselt und von Gemma einen Zeitstempel oder BPM verlangt,
bekommt Unsinn.

---

## 8 · Datenmodell (kurz)

```
track(id, pfad, hash, titel, künstler, album, dauer, ...)
features(track_id, analysis_version, bpm, beat_raster, downbeats,
         key_camelot, key_vertrauen, lufs, energie_kurve, abschnitte)
embedding(track_id, abschnitt, vektor_256, start, ende, modell_version)
stimmung(track_id, tags)
set(id, name, quelle=auto_dj, erstellt)
uebergang(set_id, von_track, zu_track, typ, takte, stretch_ratio, cue_in, cue_out)
```

> **Ergänzung 08.10.2026 (ADR-007, ADR-013):** Zwei Felder sind Pflicht, sonst
> vergleicht der Hörtest nach einem Modellwechsel alte mit neuen Werten:
> **`analysis_version`** in `features` (wechselt das Verfahren, wird **alles**
> neu gerechnet) und **`modell_version`** in `embedding`. Aus dem Hash-Rechner
> (ADR-013) kommt ein Feld für die **Stichproben-Position**, damit ein
> Retagging nachvollziehbar bleibt.

---

## 9 · Der Ablauf im Auto-DJ (Schritte)

1. Nutzer tippt **Auto-DJ**.
2. Optional ein Wunsch in Worten („Party, eher treibend").
3. Planer wählt einen Start-Song und geht Song für Song weiter, nach den vier
   Bewertungsteilen und der Energie-Reise.
4. Die Übergangs-Engine rechnet für jedes Paar Typ, Länge, Tempo-Anpassung und
   Cue-Punkte.
5. Deck A startet, Deck B wird geladen.
6. Am Übergangspunkt mischt die Engine.
7. Der Nutzer kann steuern oder eingreifen; es wird neu geplant.

---

## 10 · Erste Version klein halten (wichtiger Rat)

> **Abgelöst (08.10.2026):** gültig ist nur noch `ROADMAP-KLANGBILD.md` (ADR-011). Version 1 gleicht das Tempo per Resampling an (ADR-014).

Nicht mit allem anfangen. Die realistische Reihenfolge:

- **Version 1:** Auto-DJ nur mit **Überblenden** und Songs, die **nahe
  beieinander** liegen im Tempo. Kein Tempostrecken. Das spart die halbe
  Schwierigkeit und klingt schon ordentlich.
- **Version 2:** Phrasierung (Übergang auf 8er/16er), Tonart-Regel.
- **Version 3:** Tempostrecken und Filter-Sweeps, Struktur-Marker nutzen.
- **Version 4:** Party-Modus mit Energie-Reise und Wunsch in Worten.

Das Tempostrecken ist der teuerste Teil. Wer damit anfängt, verliert sich.

---

## 11 · Risiken

| Risiko | Wirkung | Gegenmaßnahme |
|---|---|---|
| Falsches Beat-Raster | hörbarer Unfall | Sicherheitswert prüfen, sonst nur überblenden |
| Tempostrecken klingt künstlich | unschön | nur kleine Unterschiede, Grenze setzen |
| Erste Analyse dauert lange | Nutzer wartet | im Hintergrund, mit Fortschritt, fortsetzbar |
| Akku und Hitze | schlechte Bewertungen | nur am Ladegerät oder in Stufen |
| Genre-Sprung | klingt falsch | Bewertung bremst zu große Sprünge |
| Markt voll | kaum Aufmerksamkeit | Unterschied ist Stimmung, lokal, kein Abo |
| Lizenzfallen | teuer | Lizenzen prüfen (siehe unten) |

**Lizenz-Warnung:** Manche Werkzeuge sind nicht frei für Firmen. Essentia ist
AGPL, aubio ist GPL, Rubber Band hat eine kommerzielle Lizenz. Vor dem Start
prüfen, sonst wird aus der schönen Idee ein Rechtsproblem. EmbeddingGemma 2
ist Apache 2.0 und damit unkritisch.

---

## 12 · Phasen (nach Ergebnis, nicht nach Zeit)

> **Abgelöst (08.10.2026):** gültig ist nur noch `ROADMAP-KLANGBILD.md` (ADR-011).

- **Phase A · Player.** Bibliothek, Wiedergabe, Playlists, Widgets. Ohne KI.
- **Phase B · Analyse und Stimmung.** BPM, Key, Vektoren, Suchen mit Worten.
- **Phase C · Auto-DJ einfach.** Auswahl nach Harmonie, Tempo, Stimmung.
  Nur Überblenden.
- **Phase D · Übergangs-Engine.** Phrasierung, Tempo, Filter, Struktur.
- **Phase E · Party-Modus.** Energie-Reise, Wunsch in Worten, Erklärung.

**Abnahmekriterien Phase C:**
- Auto-DJ läuft eine Stunde ohne hörbaren Fehler.
- Übergänge sitzen auf der Taktgrenze.
- Kein Netzwerkverkehr (nachweisbar).
- Der Nutzer kann jederzeit eingreifen, ohne dass die Wiedergabe abbricht.

---

## 13 · Offene Fragen

1. **Rechenlast** des Tempostreckens auf echten Geräten. Nicht gemessen.
2. **Marktgröße.** Lokale Sammlungen sind klein und treu, nicht groß.
3. **Zahlbereitschaft** für Auto-DJ extra. Muss getestet werden.
4. **Wie gut** die Stimmungs-Auswahl wirklich trifft. Nur im Hörtest zu klären.
5. **Lizenzkosten** der DSP-Werkzeuge.

---

## 14 · Quellen und Vorbilder

- Vorbild Player: Poweramp (Einmalzahl, Equalizer, Gapless).
- Vorbilder Auto-DJ: Mixxx, Virtual DJ Automix, djay Automix.
- EmbeddingGemma 2: Google, 06.10.2026.
