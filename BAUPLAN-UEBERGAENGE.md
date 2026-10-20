# Bauplan · Bessere Übergänge (Desktop-Mixer und Android)

Stand 2026-10-16 · Grundlagen:
- Desktop-Mixer `prototyp/klangbild/` (Regie V2, 343 Tests grün, nichts seit 3f41627 committet)
- 13 Runden Übergangstest, rund 400 benotete Übergänge
  (`prototyp/ergebnisse/uebergangstest*/bewertungen.json`)
- Gemma-Versuch Stufe 1 und 2, earshot-Versuch (`prototyp/ergebnisse/gemma-probe/`, `earshot-probe/`)
- `BAUPLAN-ANDROID.md` (M0–M12), ADR-018, ADR-019, ADR-024

Dieses Dokument ist für eine umsetzende KI geschrieben, auch für eine schwächere.
Jede Aufgabe nennt:
- Ziel
- Belege
- Dateien
- Schritte
- Test
- Abnahme

Es gelten die Arbeitsregeln aus `BAUPLAN-ANDROID.md` §0. Dazu kommen die Regeln in §0 hier.

---

## 0 · Arbeitsregeln (Pflicht)

1. **Die Noten des Nutzers sind heilig.** `bewertungen.json` in jedem
   `uebergangstest*`-Ordner wird nie verändert, gelöscht oder selbst ausgefüllt.
   Ein Testordner darf nur weg, wenn er keine `bewertungen.json` hat.
2. **Jede Änderung an der Regie wird gehört, nicht nur gerechnet.** Abnahme ist
   immer eine Übergangstest-Runde (§9). Unit-Tests sichern nur die Mechanik.
3. **A/B statt Vorher/Nachher, wo möglich.** Der Haken `live.Wiedergabe.plan_waehler`
   (gebaut für den Gemma-Versuch) lässt pro Paar zwei Varianten gegeneinander
   antreten. Neue Bewerter (Kritiker §2) laufen zuerst so.
4. **Python ist die Vorlage für Android.** Alles, was hier für den Desktop
   gebaut wird, muss sich nach Kotlin oder C++ portieren lassen: keine
   Bibliothek ohne Android-Gegenstück im Laufzeitpfad. Training darf
   Python-only sein, die **Auswertung** eines Modells nicht.
5. **Eine Aufgabe = ein Commit**, erst wenn `pytest` grün ist.
   Mit `git -c core.askPass= commit`, Trailer laut Projekt.
   Nie committen: `prototyp/tmp_maeb*.py`, `prototyp/wave_build.py`, `ui/`.
6. **Patches mit mehreren Zeilen** als Python-Skript (Write-Tool) ausführen, nicht
   per Bash-Heredoc. Apostrophe und `\`-Zeilenenden gehen dort kaputt.

---

## 1 · Was wir wissen (Belege)

| Befund | Quelle | Folge für den Plan |
|---|---|---|
| Regie Runde 13: **4,42**, keine Note ≤ 2 | Stufe 2 | Die Regie ist die Basis, kein Neubau |
| Gemma als Wähler: 3,08; Regie in 8 von 12 Paaren besser | Stufe 2 | Gemma wählt keine Übergänge (§8.4) |
| Gemma als Notengeber: Spearman +0,09…+0,15, nicht besser als Rezept-Mittel | Stufe 1 | Kein LLM als Kritiker |
| earshot (CLAP, Beat-Raster): Spearman ≤ 0,1 je Merkmal | earshot-Versuch | Keine allgemeinen Klangmodelle als Kritiker |
| Lautheit: Spanne +0,16, Loch-Tiefe −0,18 | earshot-Versuch | Atempausen gefallen eher: Merkmal für §2 |
| Double Drop: zweimal Note 1, „Drops nicht auf dem selben Beat“ | R13 Fall 1, 13 (auch R8–R12) | §3 Drop-Ausrichtung |
| „Lieder passen nicht zueinander“: dreimal | R13 Fall 13, 15; R12 Fall 4, 7, 17 | §4 Passung |
| Harter Schnitt bei Tempo-Sprung: 2,5 | R13 | §5 Tempo-Brücken |
| `gesang_zuerst` „B erst nach dem Übergang hörbar“: Note 1 | R13 Fall 23 | §6.1 |
| 32-Takt-Übergänge 4,67 (n = 3) | R13 | §6.2 (klein, nachprüfen) |
| `live._plan_track` übergibt `vektor=None`: Klang-Vektoren ungenutzt | Code | §4 |
| Für DnB- und Hard-UKG-Titel (ids 502–586) gibt es **keine** Klang-Vektoren | DB `embeddings` | §4.1 |
| Clip-Meta enthält B's Einstieg erst ab Runde 12 (`ein_takt`) | Code | §2.1 Rekonstruktion |

---

## 2 · Kritiker, der aus den Noten lernt (größter Hebel)

**Ziel:** Ein kleines Modell schätzt für jeden Plan der Regie die Note, die der
Nutzer geben würde. Die Regie sortiert ihre Pläne damit neu. Das Modell lernt mit
jeder Runde und jedem 👍/👎 (§7) dazu.

Warum kein LLM und kein Klangmodell: Beide sind gemessen gescheitert (§1).
Die Regie kennt aber Merkmale, die direkt mit den Fehlern zu tun haben:
Abschnitt, Gesang, Drop-Einsatz, Energie und Rezept.

### 2.1 Datensatz bauen (Vorarbeit)

**Neue Datei:** `prototyp/klangbild/datensatz.py`, Kommando
`python -m klangbild datensatz`. Ergebnis: `ergebnisse/datensatz/uebergaenge.jsonl`,
eine Zeile pro benotetem Übergang.

Schritte:
1. **Alle Runden einlesen:** `gemma_probe.bewertete_faelle()` wiederverwenden.
   Die Funktion wandert nach `datensatz.py`, `gemma_probe` importiert sie von dort.
2. **B's Einstieg bestimmen:**
   - **Ab Runde 12:** aus `info["ein_takt"]`.
   - **Davor rekonstruieren:**
     - Die letzten 6 s des Clips sind reines B (`blende_bis_s` bis Ende). Daraus und
       aus B's ganzem Song je eine Hüllkurve: Mono, 11 kHz, Betrag, 10-ms-Fenster.
     - Die Hüllkurve des Clip-Endes per Kreuzkorrelation (`scipy.signal.correlate`)
       im Song suchen.
     - Gefundene Sekunde minus `blende_s` = B's Start. Für die Umrechnung in einen
       Takt `profil.takt_bei` nutzen.
     - Mit `sync` lief B gedehnt (`info["bpm_a"]/info["bpm_b"]`). Die Hüllkurve des
       Clip-Endes vorher mit dem Faktor auf B's Tempo zurückrechnen.
     - Gültig nur bei Korrelationsspitze ≥ 0,6. Sonst `ein_takt = null`; die Zeile
       bleibt mit fehlenden B-Merkmalen im Datensatz.
3. **Ab sofort mitschreiben:** In `uebergang.backen` (Info-Dict, Zeile ~1426) kommt
   `b_orig_start` dazu. `live.backen_plan` schreibt `ein_takt` schon. Damit braucht
   keine künftige Runde die Rekonstruktion.
4. **Merkmale je Übergang** (alle aus vorhandenen Funktionen, nichts Neues messen):

| Gruppe | Merkmal | Quelle |
|---|---|---|
| Rezept | Rezeptname (one-hot), Takte, Stems ja/nein, sync, Experimente-Stufe, Stil, Spielanteil, WEITER | `info`, Meta |
| A an der Stelle | Etikett der Phrase (intro/aufbau/drop/haupt/break/outro), Pegel, Gesang-Anteil im Fenster, Takte bis Songende | `profil.etiketten()`, `gesang()`, `_fenster` |
| B an der Stelle | dasselbe für B, dazu: Drop direkt nach der Blende, `_einsatz` am Drop | `regie._einsatz`, `_drop_takt` |
| Paar | Harmonie im Fenster (`regie._harmonie`), Camelot-Abstand, BPM-Abstand, Energiesprung, Klang-Ähnlichkeit (§4, sobald da) | `regie`, `plan` |
| Ergebnis | Lautheits-Spanne und Loch-Tiefe der fertigen Blende | gleiche Rechnung wie `earshot_probe` (Kurzzeit-LUFS) mit `pyloudnorm`-freiem Code aus `regie.pruefen` (RMS je Takt) |
| Ziel | Note, Stichworte, Kommentar | `bewertungen.json` |

**Test:** `tests/test_datensatz.py`.
- Die Rekonstruktion findet auf einem synthetischen Clip (Klickspur mit bekanntem
  Versatz, gedehnt um 2 %) den Start auf ±1 Takt genau.
- Der Merkmals-Bau läuft auf einem Mini-Ordner mit zwei Fällen.

**Abnahme:**
- Für ≥ 90 % der Fälle aus Runde 1–11 ist `ein_takt` gesetzt.
- Für 20 Stichproben stimmt die Rekonstruktion mit einer Neuplanung überein (`exp_planen.py`-Weg).

### 2.2 Modell trainieren und ehrlich messen

**Neue Datei:** `prototyp/klangbild/kritiker.py`, Kommando
`python -m klangbild kritiker --trainieren`.

1. **Modell:** `sklearn.ensemble.HistGradientBoostingRegressor`
   (`max_depth=3`, `max_iter=200`, `learning_rate=0.05`, `l2_regularization=1.0`).
   Ziel ist die Note 1–5. Flache Bäume halten das Modell auf dem Handy auswertbar (§2.4).
2. **Messen mit Leave-one-round-out:** In jeder Runde kehren Paare und Songs
   wieder. Zufällige Kreuzvalidierung würde lügen.
3. **Vergleichsbasis:** Rezept-Mittel aus den anderen Runden (heute MAE 0,69–0,75).
4. **Tor:** Der Kritiker wird nur eingeschaltet, wenn er im Leave-one-round-out
   - MAE ≤ Basis − 0,05 **und** Spearman ≥ 0,30 schafft
   - **und** unter den Fällen mit Note ≤ 2 mindestens die Hälfte im schlechtesten
     Drittel seiner Schätzungen landet.

   Sonst bleibt er aus, und der Bericht nennt die Zahlen. Kein Herumschrauben,
   bis es passt: höchstens 3 Merkmals-Varianten, alle im Bericht.
5. **Bericht:** `ergebnisse/kritiker/bericht.md` mit:
   - Kennzahlen je Runde
   - wichtigste Merkmale (Permutation Importance)
   - die 10 größten Fehlschätzungen
6. **Speichern:** als JSON-Bäume `ergebnisse/kritiker/modell.json`
   (Merkmalsliste, Schwellen, Blattwerte). Eigener Export aus
   `model._predictors`; die Auswertung (§2.4) liest nur dieses JSON.

**Test:**
- Die Auswertung aus JSON liefert dasselbe wie `model.predict` (±1e-6) auf 50 Zufallszeilen.
- Das Tor greift bei Zufallsnoten (Modell bleibt aus).

### 2.3 Einbau in die Regie

1. `regie.planen(..., anzahl=3)` liefert bisher die 3 besten Pläne. Neu: intern bis
   zu 8 Kandidaten bewerten (`anzahl_intern=8`), dann sortieren nach
   `punkte_regie_norm + KRITIK_GEWICHT * (kritik - 3)`. Startwert `KRITIK_GEWICHT = 1.0`.
   `punkte_regie_norm` ist der Rang innerhalb der 8, auf 0 bis 1 skaliert.
2. Die Merkmale für einen **Plan vor dem Backen** kommen aus derselben Funktion
   wie im Datensatz (`datensatz.merkmale_plan(plan, pa, pb, e)`).
   - Ergebnis-Merkmale (Lautheit) gibt es vor dem Backen nicht. Der Kritiker
     bekommt deshalb zwei Varianten: `vorher` (ohne Ergebnis-Merkmale, für die
     Rangfolge) und `nachher` (mit, für die Selbstkontrolle).
   - Fällt `nachher` < 2,0, gilt der Plan als durchgefallen, wie bei `pruefen`.
3. `plan.grund` bekommt „Kritiker: 3,8“. Die Übergangstest-Anzeige zeigt das mit.
4. **A/B-Runde:** `uebergangstest --kritiker` (wie `--gemma`). Jedes Paar einmal
   mit, einmal ohne Kritiker. Der Wähler setzt `plan_waehler`, der Rest ist da.

**Abnahme:** In der A/B-Runde (12 Paare) ist der Kritiker im Mittel nicht
schlechter und hat weniger Noten ≤ 2. Sonst bleibt er aus (Schalter
`Einstellungen.kritiker: bool = False`, ins `AUSWAHL` und in `mixer.html`).

### 2.4 Android

- `:core` bekommt `Critic.kt`: liest `modell.json` aus dem PC-Import
  (`BAUPLAN-ANDROID` M3, Analyse-Import).
- Die Auswertung ist eine Schleife über die Bäume, etwa 40 Zeilen.
- Golden-Test: 50 Merkmalszeilen aus Python, Abweichung ≤ 1e-5.
- **Training bleibt am PC.** Die 👍/👎 vom Handy (§7.1) wandern beim nächsten
  Import zurück zum PC.

---

## 3 · Drop-Ausrichtung messen statt schätzen

**Ziel:** Bei Double Drop, Drop-Cuts und Drop-Tricks landen beide Drops auf
dem gleichen Schlag. Fällt das nach dem Backen anders aus, wird der Plan
verworfen.

**Ursache heute:**
- `regie._drop_takt` sucht den Drop nur auf **Takt**-Raster (±2 Takte), aus
  Profilwerten je Takt.
- Ein Downbeat-Raster, das einen halben Takt oder einen Schlag daneben liegt
  (Beat This!-Fehler), bemerkt es nicht.
- `pruefen` überspringt `double_drop`, `drop_cuts` und alle Drop-Tricks
  komplett: Für genau diese Rezepte gibt es keine Selbstkontrolle.

### 3.1 Drop auf den Schlag genau (vor dem Backen)

**Neue Funktion:** `regie._drop_schlag(eintrag, audio, rate, drop_takt) -> (takt, schlag_versatz, sicherheit)`.

1. Tiefband-Hüllkurve (20–150 Hz, `mix.band_teilen`) aus dem rohen Audio,
   ±2 Takte um den Drop, in Achtel-Schlag-Schritten aus `eintrag.downbeats`
   (bzw. Beats).
2. Einsatzstärke je Kandidat (−8 … +8 Achtel): Mittel der Hüllkurve 1 Takt
   danach minus 1 Takt davor, in dB.
3. Bester Kandidat = Drop.
   - `schlag_versatz` ≠ 0 heißt: Das Downbeat-Raster liegt daneben.
   - `sicherheit` = Abstand zum zweitbesten Kandidaten in dB.
4. Für B wird das Audio gebraucht. `live` hat es (`self.roh(b)`), `planen`
   bekommt deshalb neu `b_audio` (wie heute `a_audio`). Ohne Audio (Tests)
   gilt der alte Weg.
5. `_double_drops` und der Trick-Zweig in `_rezept` nehmen nur Drops mit
   `sicherheit ≥ 3 dB`.
   - Ist `schlag_versatz` ≠ 0, wird der Versatz auf `ein_s` bzw. `aus_s`
     gerechnet (ganze Schläge).
   - Halbe Schläge: verwerfen.

### 3.2 Kick-Kontrolle nach dem Backen

**Neue Funktion:** `regie.pruefen_drop(blende, rate, takt_n, drop_takt) -> str | None`.

1. Tiefband-Onsets (Flux der 20–150-Hz-Hüllkurve, Spitzen über Median + 3 MAD)
   in den 2 Takten ab dem gemeinsamen Drop.
2. Raster aus `takt_n` (Taktgrenzen der Blende).
3. Fehler, wenn ≥ 30 % der starken Onsets mehr als 40 ms neben jedem Achtel des
   Rasters liegen. Das ist ein zweiter, versetzter Kick-Zug.
4. In `live.backen_plan` für `double_drop`, `drop_cuts` und `DROP_TRICKS`
   aufrufen. Im Fehlerfall gilt der nächste Plan (wie bei `pruefen`).

**Tests** (`tests/test_regie.py`):
- Synthetische Kick-Züge, gleich ausgerichtet → `None`.
- Um einen halben Schlag versetzt → Fehler.
- Um einen ganzen Takt versetzt (Kicks fallen wieder aufs Raster) → `None`. Den
  Fall muss 3.1 fangen.
- `_drop_schlag` findet einen um 2 Schläge verschobenen Drop.

**Kalibrierung vor dem Einschalten:**
- Die 40 ms und die 30 % an allen benoteten Double Drops und Drop-Cuts der
  Runden 8–13 nachrechnen (Clips vorhanden).
- Ziel: Die Fälle mit Kommentar „nicht auf dem selben Beat“ fallen durch, die
  mit Note ≥ 4 nicht. Ergebnis-Tabelle in den Commit-Text.

**Abnahme:** In der nächsten Runde keine Double-Drop-Note ≤ 2 mit „Beat“-Kommentar.

**Android:** Beide Funktionen sind reines numpy und kommen in den Port der
Regie (M7). Golden-Tests auf den synthetischen Kick-Zügen.

---

## 4 · „Passen die Lieder zusammen?“

**Ziel:** Riskante Rezepte (Double Drop, Drop-Cuts, Drop-Tricks) nur zwischen
Songs, die klanglich und in der Energie zusammenpassen. Die Partnerwahl nutzt
die Klang-Ähnlichkeit, die heute ungenutzt bleibt.

### 4.1 Klang-Vektoren für alle Titel

1. `python -m klangbild embed` für die Bibliothek laufen lassen. Es fehlen
   mindestens alle DnB- und Hard-UKG-Titel.
   - EmbeddingGemma 2 liegt im HF-Cache.
   - Der Lauf ist lang: Hintergrund, Fortschritt im Log.
2. `mixer.bibliothek_laden` liest pro Titel den Mittelwert der Vektoren
   (anfang/mitte/ende, normiert) in ein neues Feld `Eintrag.vektor`.
3. `live._plan_track` gibt `vektor=e.vektor` statt `None` weiter.

**Vorher prüfen, ob die Vektoren trennen** (Abbruchkriterium):
- Ordner als grobes Genre (DnB, Hard UKG, Chill, …).
- Mittlere Kosinus-Ähnlichkeit innerhalb gegen zwischen den Ordnern, dazu AUC
  „gleicher Ordner?“.
- Bei AUC < 0,75 taugen die Vektoren nicht als Passung. Dann 4.2 nur mit Energie
  bauen und den Befund ins ADR-015-Umfeld schreiben.

### 4.2 Passungs-Wert und Tor

**Neue Funktion:** `regie._passung(a, pa, b, pb, d_a, d_b) -> float` (0..1). Sie verrechnet:
- Klang-Kosinus der beiden Songs, linear auf 0..1
- `1 - min(1, Δ / 4 dB)` der Drop-Werte (`_drop_werte`: Pegel, Drums, Bass), wie bei
  `_drop_gleich`, aber stetig

Gewichtung 0,5 / 0,5. Fehlt der Vektor, zählt nur die Energie.

Einbau:
- `_double_drops` und der Drop-Trick-Zweig: nur mit `_passung ≥ PASSUNG_MIN`
  (Startwert 0,6, kalibrieren wie 3.2).
  - Kalibrierung an den Fällen mit „passen nicht“ (R12 Fall 4, 7, 17; R13
    Fall 13, 15).
  - Gegenbeispiele sind die Double Drops mit Note 5.
- `drop_cuts` braucht weiterhin `_drop_gleich`.
- Partnerwahl (`live._autodj_wahl` → `plan.rangliste`): Der Klang zählt wieder mit,
  weil der Vektor jetzt da ist. Gewicht `config.PLANER_GEWICHT_KLANG` bleibt.
- Übergangstest-Auswertung: neue Tabelle „Passung“ (Quartile).

**Tests:**
- `_passung` ist bei identischen Songs 1 und bei 4 dB Energie-Abstand ohne
  Vektor 0.
- Double Drop wird bei Passung 0,3 nicht angeboten.

**Android:** Die Vektoren kommen per PC-Import (M3) oder aus EmbeddingGemma 2
auf dem Gerät (ADR-006, M10). `_passung` gehört zum Regie-Port (M7).

---

## 5 · Tempo-Sprünge ohne harten Schnitt

**Ziel:** Liegen A und B mehr als `max_bpm` auseinander, gibt es heute nur
Schnitt (2,5) oder Echo-Out (2,0). Dafür kommen zwei DJ-Techniken dazu.

### 5.1 Beatlose Brücke

DJs lassen A ins Echo laufen und starten B in einem Teil **ohne Drums**: Intro-Pad,
Break oder Acapella. Dort hört man kein Tempo. B's Drums kommen danach in B's
eigenem Tempo.

1. **Neue Kandidaten** in `regie._b_kandidaten`, nur wenn `not sync`:
   - Takte in B's ersten 40 %, in denen Drums (Stem) unter −35 dB liegen bzw.
     ohne Stems das Band-0-Mittel unter Song-Median − 10 dB,
   - für mindestens 4 Takte.
2. **Neues Rezept** `bruecke_beatlos`:
   - A `effekt="echo75_ende_aus"` mit langer Fahne (NASS 1,3, Feedback 0,7, siehe R12).
   - B startet im beatlosen Teil mit `lautstaerke` „ein über 2 Takte“.
   - Kein Tempo-Angleich (`sync=False` bleibt).
3. **Rangfolge:** `bruecke_beatlos` vor `echo_out` vor `schnitt`.

**Test:** Profil mit beatlosem Intro, BPM-Abstand 20 → Rezept `bruecke_beatlos`,
`ein_s` liegt im beatlosen Teil.

### 5.2 Tempo vorab angleichen (Vorlauf-Rampe)

A gleitet schon vor der Blende auf B's Tempo. Mit Keylock ist das bis etwa ±8 %
unauffällig, wenn es über 32 Takte geschieht.

1. Neuer `tempo_modus="vorlauf"`: Gilt, wenn |ΔBPM| > `max_bpm`, aber
   ≤ `VORLAUF_MAX` (Startwert 8 % von A).
2. `uebergang.backen` rendert dann ab `aus_s − VORLAUF_TAKTE` (16 oder 32 Takte):
   - A mit einem Zielraster, dessen Periode linear von A auf B gleitet.
   - Danach die normale Blende mit `sync=True`.
   - Das ist dieselbe Warp-Maschinerie wie `rampe`, nur früher begonnen.
3. **Folge für `live`:** Der gebackene Abschnitt beginnt früher. `VORLAUF_S`
   (frühester Blendenbeginn) muss diesen Vorlauf abdecken, also die Backzeit
   prüfen.
4. Die Regie behandelt solche Paare danach wie `sync` (alle Rezepte frei).

**Tests:**
- Vorlauf über 16 Takte: Die Taktlänge am Ende des Vorlaufs ist B's (±0,5 %).
- Die Tonhöhe bleibt mit Keylock gleich (FFT-Spitze, wie der vorhandene Keylock-Test).

### 5.3 Doppel-/Halbtempo

- Liegt B bei etwa der Hälfte oder dem Doppelten von A (±`max_bpm`), wird B's
  Beat-Raster als Halb- bzw. Doppeltempo behandelt, z. B. 85 ↔ 170.
- Das ist ein Faktor 2 in `_periode`, sonst nichts.
- Hard UKG (≈ 140) ↔ DnB (≈ 172) fällt **nicht** darunter. Dafür gibt es 5.1 und 5.2.

**Abnahme:** Testrunde mit absichtlich gemischten Ordnern (Hard UKG + DnB).
Kein Schnitt mehr unter 3,0.

**Android:** 5.1 gehört zum Regie-Port (M7). 5.2 braucht den Warp-Port (M6):
Zielraster mit gleitender Periode, Golden-Test wie 5.2.

---

## 6 · Kleine Rezept-Fixes

### 6.1 `gesang_zuerst`: B schon vorher hörbar machen

- **Befund:** R13 Fall 23, Note 1: „Man hört Track B erst nach dem Übergang.“
- **Ursache:** Bis zur Übergabe läuft von B nur der Vocals-Stem.
- **Fix:** In `uebergang.stem_plan` für `gesang_zuerst` laufen B's Drums **ab der
  Hälfte der Gesangsphase** hochpass-gefiltert (> 2 kHz: Hi-Hats, Shaker) bei −12 dB
  mit. Ab der Übergabe kommen sie voll.
- **Test:** Pegel von B's Drums-Anteil im Fenster vor der Übergabe zwischen −15 und −9 dB.

### 6.2 Längere Übergänge bei Stil „lang“

- **Befund:** 32 Takte 4,67 (n = 3), 16 Takte 3,93 (n = 14). Die Stichprobe ist klein.
- **Fix:** In `regie.laengen("lang")` bekommt 32 einen Bonus von +0,3 in
  `_grundwert`. Nur dort, wo A an der Stelle noch ≥ 32 Takte Material hat.
- **Abnahme:** Nach 2 Runden die Tabelle „Länge“ in der Auswertung prüfen. Bei
  32 Takten unter 16 Takten den Bonus zurücknehmen.

### 6.3 Atempause (aus dem earshot-Befund)

- **Befund:** Blenden mit größerer Lautheits-Spanne gefielen eher, ein tiefes
  Loch nicht.
- **Kein eigener Fix:** Das Merkmal geht in den Kritiker (§2.1) und wird dort
  gewichtet. Erst wenn der Kritiker es als wichtig ausweist, eine Regel daraus
  machen.

---

## 7 · Lernen im echten Betrieb

### 7.1 Daumen-Knopf im Mixer

1. `mixer.html`:
   - Während und bis 30 s nach einer Blende zwei Knöpfe 👍 / 👎 an der
     Blenden-Anzeige.
   - Optional ein Stichwort aus `uebergangstest.STICHWORTE` (Klappliste).
2. `mixer.py`: `POST /api/daumen` mit `{nr_blende, gut, stichwort}`.
3. `live.Wiedergabe` speichert zu jeder gespielten Blende die vollständige Meta.
   Das ist dasselbe Format wie die Übergangstest-Clips (`a`, `b`, `stil`, `info`,
   `ein_takt`, `b_orig_start`).
   - Ziel ist `ergebnisse/live-bewertungen/<datum>/clips/<nr>.json` plus
     `bewertungen.json`.
   - 👍 = Note 4, 👎 = Note 2. Kein Audio speichern, die Merkmale reichen.
4. `datensatz.py` liest diese Ordner mit, gewichtet mit 0,5, weil sie ungenauer
   sind als Hörtest-Noten.
5. Das vorhandene `regie-lernen.json` (Rezept-Vorlieben aus WEITER und „anderer
   Übergang“) bleibt. Der Daumen zählt dort zusätzlich wie ein durchgehörter
   bzw. abgebrochener Übergang.

**Test:** API schreibt Meta und Note; ungültiger Body → 400; `datensatz` liest
den Ordner.

### 7.2 Vorhören (nur PC)

1. `mixer.html`: Ausgabegerät für „Vorhören“ wählbar
   (`HTMLMediaElement.setSinkId`, Chrome/Edge). Ohne Unterstützung bleibt der
   Knopf ausgeblendet.
2. `GET /api/vorhoeren` liefert die schon gebackene nächste Blende als FLAC:
   den Puffer aus `self._naechste`, ab 4 s vor der Blende. Neu gerechnet wird nichts.
3. Daneben „Anderer Übergang“ (gibt es schon: `rang`) und „Diesen nehmen“, das
   den Kandidaten festhält.

**Test:** Endpunkt liefert ohne gebackene Blende 404, mit Blende gültiges FLAC
passender Länge.

**Android:** Der Daumen gehört in M9 (Oberfläche) und schreibt in Room, Export
beim PC-Abgleich. Vorhören entfällt auf dem Handy (ein Ausgang).

---

## 8 · Set planen statt Paar

**Ziel:** Die Reihenfolge der Playlist ergibt sich aus den Übergängen, die
tatsächlich gut werden, nicht nur aus BPM, Tonart und Energie.

1. **Paarnoten vorrechnen:**
   - Neuer Hintergrund-Job `python -m klangbild paarnoten` bzw. Thread im Mixer
     nach dem Analysieren.
   - Für jedes Paar mit |ΔBPM| ≤ `max_bpm` (oder Brücke, §5):
     `regie.planen(..., anzahl=1)` auf den Profilen. Ohne Audio, also ohne
     Loop-Prüfung, die kommt beim echten Backen.
   - Note = Kritiker-Schätzung (§2), sonst normierte Regie-Punkte.
   - Cache `cache/paarnoten.json`, Schlüssel: Track-Hashes + `analyse_version` +
     Regie-Version.
   - Aufwand bei 70 Titeln: ≤ 4900 Paare × ~0,2 s ≈ 15 min einmalig, danach nur
     neue Titel.
2. **Reihenfolge** in `plan.sortiere_alle`:
   - Start beim größten Tempo-Cluster wie heute, dann gierig den besten
     nächsten Titel, danach 2-opt-Verbesserung.
   - Kosten = −Paarnote + Energiebogen-Strafe + Strafe für dasselbe Rezept wie
     beim vorigen Übergang.
3. **Energiebogen** als Einstellung `set_bogen`: `gleichmaessig` /
   `aufbauen` / `welle`.
   - Zielkurve je Position, Strafe = |Energie − Ziel| / 6 dB.
4. **Mixer:** Der Knopf „Perfekte Reihenfolge“ nutzt das. Die Warteschlange zeigt
   je Übergang die erwartete Note.

**Tests:**
- 2-opt verbessert eine absichtlich schlechte Reihenfolge.
- Gleiche Eingabe ergibt die gleiche Reihenfolge.
- Der Cache wird bei neuer `analyse_version` verworfen.

**Android:** Paarnoten rechnet der PC mit, sie kommen mit dem Analyse-Import.
Auf dem Gerät werden nur neue Titel nachgerechnet, im WorkManager-Job beim Laden.

---

## 9 · Abnahme: Übergangstest-Runden

Pro Abschnitt eine Runde, in dieser Reihenfolge:

| Runde | Inhalt | Aufbau | Erfolg |
|---|---|---|---|
| 14 | §3 + §6.1/6.2 | normal, `--experimente kreativ,wild`, Hard UKG + DnB | keine Double-Drop-Note ≤ 2 mit Beat-Kommentar, Mittel ≥ 4,0 |
| 15 | §4 | normal, gemischte Ordner | keine Kritik „passen nicht“ bei Tricks |
| 16 | §2 | `--kritiker` A/B | Kritiker nicht schlechter, weniger Noten ≤ 2 |
| 17 | §5 | Ordner mit Tempo-Sprüngen | kein Rezept unter 3,0 |
| 18 | §8 | Set-Test: 6 Songs am Stück statt einzelner Paare (neuer Modus `--set`) | Set-Note ≥ 4 |

Vor jeder Runde:
- Die alte archivieren (`uebergangstest-20261014-rundeNN`, zweistellig).
- Neue Lieder nehmen, solange vorhanden.

---

## 10 · Android: was sich durch diesen Plan ändert

- **Grundsatz bleibt:** Vorausbacken (ADR-024), kein Echtzeit-Signalgraph.
  Das ist in ADR-024 entschieden und gehört; die Idee „Echtzeit statt
  Vorausbacken“ aus der Diskussion ist damit verworfen.
- **Neu in M7 (Regie-Port):**
  - `_drop_schlag`, `pruefen_drop` (§3)
  - `_passung` (§4)
  - `bruecke_beatlos` (§5.1)
  - Rezept-Fixes (§6)

  Golden-Tests je Funktion.
- **Neu in M6 (Warp):** Zielraster mit Vorlauf-Rampe (§5.2).
- **Neu in M3 (PC-Import):** Kritiker-JSON (§2.4), Paarnoten (§8), Klang-Vektoren.
- **Neu in M9 (Oberfläche):** Daumen (§7.1).
- **Stems (M11):** Demucs ist fürs Handy zu schwer.
  - Stufen wie in BAUPLAN-ANDROID §9.3.
  - Bis dahin wählt die Regie Rezepte ohne Stems. Jedes Rezept hat schon heute
    einen Ersatz (`stems_da=False`).
  - Der Kritiker muss `stems` als Merkmal kennen (§2.1, ist drin).

### 10.1 Rolle von Gemma 4 auf dem Handy

Gemessen: Gemma taugt weder als Wähler noch als Notengeber für Übergänge (§1).
Gemma bekommt deshalb nur die Rolle, in der ein Sprachmodell stark ist: **Sprache
in Einstellungen übersetzen.**

1. **Eingabe:** freier Satz, z. B. „mach's energischer“, „chilliger Abend-Mix ohne
   Experimente“, „mehr Double Drops“.
2. **Ausgabe:** JSON mit Änderungen an `Einstellungen` (nur Felder aus
   `AUSWAHL`, Werte aus den erlaubten Listen) plus optional `set_bogen` (§8).
   Ungültiges wird verworfen, nie geraten.
3. **Prüfung am PC vorab** (ohne Android-Arbeit):
   - 60 Sätze mit Soll-JSON schreiben.
   - `gemma_probe` um einen Befehl `einstellungen` erweitern.
   - Messen: Anteil exakt richtig, Anteil gültig.
   - **Tor:** ≥ 85 % exakt richtig mit E2B. Sonst Feature streichen.
4. Auf dem Handy über LiteRT-LM (ADR-006), Gemma 4 E2B in 4 Bit. Nur auf
   Knopfdruck, kein Dauerbetrieb.

---

## 11 · Reihenfolge und Aufwand

| Schritt | Abschnitt | Aufwand (grob) | hängt ab von |
|---|---|---|---|
| 1 | §3 Drop-Ausrichtung | 1 Tag + Kalibrierung | – |
| 2 | §6 Rezept-Fixes | ½ Tag | – |
| 3 | Runde 14 | Hören | 1, 2 |
| 4 | §4.1 Vektoren (Lauf) + Trennprüfung | ½ Tag + Rechenzeit | – |
| 5 | §4.2 Passung | ½ Tag | 4 |
| 6 | §2.1 Datensatz | 1 Tag | – (besser nach 4) |
| 7 | §2.2–2.3 Kritiker | 1–2 Tage | 6 |
| 8 | §7.1 Daumen | ½ Tag | 6 (Format) |
| 9 | §5 Tempo-Brücken | 2 Tage | – |
| 10 | §8 Set-Planung | 2 Tage | 7 (Note) |
| §8 Genre und Energie (16.10., Nutzerkritik) | `profil.energielevel` 0 (ruhig) … 1 (hart): viel Höhen und wenig Flächen/Melodie (Rest-Stem), kalibriert an den Ordnern (Chill/TOBI gegen Hard UKG/DnB, CV-AUC 0,86). Genre = Ordner des Titels. `plan._set_schritt`: Energiesprung × 4, Genrewechsel 1,5; `set_bogen` zielt auf das Level; `rangliste` und Auto-DJ-Wahl strafen Sprünge | An der echten Bibliothek (417 Titel): Genrewechsel 153 → 26, Energiesprünge > 0,4 von 124 → 9, erwartete Note 3,86 → 3,81. |
| §8 Neue Reihenfolge | Titel links anklicken = spielen + neu sortieren ab diesem Titel; „Perfekte Reihenfolge“ liefert jedes Mal eine andere Variante (`plan.VARIANTE`: Zufall bis 1 Notenpunkt je gieriger Wahl, danach 2-opt) | Ohne Paarnoten bleibt die Sortierung fest. |
| Drop braucht Bass (17.10.) | `Profil.etiketten`: eine Phrase wird nur mit Bass (≥ 50 % der Takte) zum Drop, sonst zum Aufbau; der Drop rutscht auf den Einsatz des Basses | Runde 11 (hedex: Drop auf dem Drum-Aufbau). In der Bibliothek waren 120 von 945 Drops ohne Bass, danach 880 Drops, alle mit Bass. `paarnoten.REGIE_VERSION` erhöht (Cache neu). Android-Golden-Daten noch vom alten Stand. |
| Energie wählt das Rezept (17.10.) | `regie._rangliste`: beide hart (Level ≥ 0,6) +0,5 für Drop-Wechsel, beide ruhig (≤ 0,35) +0,5 für Blenden ab 16 Takten | Prüfen in Runde 14/15. |
| 11 | §7.2 Vorhören | Am 16.10. auf Nutzerwunsch wieder entfernt (ebenso „Anderer Übergang“) | – |
| 12 | §10.1 Gemma-Einstellungen (PC-Prüfung) | ½ Tag | – |

Android-Teile laufen mit den Meilensteinen in `BAUPLAN-ANDROID.md`, nicht vorher.

---

## 12 · Risiken und offene Fragen

- **Zu wenige Noten für den Kritiker.**
  - Rund 400 Übergänge, verteilt auf ~25 Rezepte und drei Genres.
  - Gegenmittel: Tor in §2.2 und Daumen-Daten (§7.1).
  - Scheitert das Tor, ist das ein gültiges Ergebnis. Dann ist die Regie mit
    Regeln weiter der richtige Weg.
- **Rekonstruktion alter B-Einstiege** (§2.1) kann bei stark gedehnten oder
  geloopten Clips scheitern. Diese Fälle bleiben mit Lücken im Datensatz,
  nicht geschätzt.
- **EmbeddingGemma 2 und Musikgenres:** nur moderate MAEB-Werte. §4.1 prüft
  das zuerst und hat ein Abbruchkriterium.
- **Vorlauf-Rampe** (§5.2) verlängert die Backzeit und den Abstand zur
  Blende. Nach WEITER ist dafür keine Zeit: Dort gilt weiter Brücke oder Echo.
- **Downbeat-Fehler von Beat This!** um einen halben Takt kann `_drop_schlag`
  erkennen, aber nicht reparieren. Solche Drops werden verworfen statt verschoben.
- **Lizenz:** Der Kritiker ist ein eigenes Modell aus eigenen Daten, ohne
  Fremdgewichte. Für Gemma 4 gilt Apache 2.0, für EmbeddingGemma 2 siehe ADR-006.

---

## 13 · Stand der Umsetzung (16.10.2026, PC)

Gebaut und mit Unit-Tests gesichert. Die Hör-Abnahmen (§9, Runden 14–18) stehen
noch aus. Die Android-Teile folgen mit den Meilensteinen (§10).

| Abschnitt | Stand | Abweichung vom Plan, mit Beleg |
|---|---|---|
| §2.1 Datensatz | `klangbild/datensatz.py`, `python -m klangbild datensatz`; 402 Übergänge | Rekonstruktion von B's Einstieg: 345 von 360 (96 %) aus Runde 1–11. Gegenprobe an Runde 12/13: 41 von 42 gefunden, 30 auf den Takt genau, Ausreißer meist ganze Phrasen daneben. B läuft nach der Blende im Originaltempo (Rampe), deshalb wird nicht zurückgedehnt. `b_orig_start` steht ab jetzt im Info. |
| §2.2 Kritiker | `klangbild/kritiker.py`, `python -m klangbild kritiker --trainieren`; Bericht `ergebnisse/kritiker/bericht.md` | **Tor verfehlt, Kritiker bleibt AUS.** Vorher-Modell: MAE 0,76 gegen 0,79 (Rezept-Mittel), Spearman +0,23 (gegen +0,06), 45 % der Noten ≤ 2 im schlechtesten Drittel. Drei Varianten gemessen (vorher, vorher_kompakt, nachher), keine schafft das Tor. |
| §2.3 Einbau | `regie.planen(kritiker=…)` mit 8 Kandidaten und `KRITIK_GEWICHT`, Selbstkontrolle „nachher“ in `live`, Einstellung `kritiker` (aus), `uebergangstest --kritiker` (A/B, lädt das Modell auch ohne Tor) | Wirkt erst, wenn `modell.json` „aktiv“ ist. Mit den Daumen-Daten neu trainieren. |
| §3.1 Drop auf den Schlag | `regie._drop_schlag`, `_drop_ok`; `planen(b_audio=…)` | Kalibriert an Runde 12/13: „verwerfen, wenn unsicher“ hätte 4 von 5 Double Drops mit Note 5 gestrichen. Deshalb gilt jetzt: verwerfen, wenn der Drop **sicher daneben** liegt (Versatz ≠ 0 und ≥ 5 dB). Das fängt R13 Fall 13 (ein Takt daneben). Kandidaten nur in ganzen Schlägen; bei Versatz wird verworfen, nicht verschoben. |
| §3.2 Kick-Kontrolle | bis Runde 18 `regie.pruefen_drop`, seit Runde 19 `regie.kicks_versetzt` (siehe Zeile „Runde 18“), in `live` für `double_drop` und `drop_cuts` | Bis Runde 18: Raster in **Sechzehnteln** (UKG-Kicks sind synkopiert), 30 ms Toleranz, mehr als 50 % daneben = Fehler, 12 ms Fenster-Verzug. Ergebnis an 29 Double Drops und Drop-Cuts der Runden 8–13: Beide Fälle „nicht auf dem selben Beat“ fallen durch, keiner der 7 mit Note 5, einer von 2 mit Note 4, 4 von 15 mit Note ≤ 2. **Nicht für Drop-Tricks:** Nach dem Trick spielt nur B, dort gab es nur Fehlalarme. |
| §4.1 Vektoren | Alle 585 Titel eingebettet (die fehlenden 86 nachgerechnet) | **Abbruchkriterium erreicht:** AUC „gleicher Ordner“ 0,57, DnB gegen Hard UKG 0,55 (Grenze 0,75). Die Schritte 2–3 (Vektor durchreichen) entfallen. Nachtrag in ADR-015. |
| §4.2 Passung | `regie._passung`, `PASSUNG_MIN = 0,35`, für Double Drop und Drop-Cuts | Nur der **Pegel**-Abstand der Drops (4 dB = 0). „Passen nicht“ lag bei 3,1–3,7 dB, Note 5 bei höchstens 2,2 dB. Drums und Bass trennten nicht. Drop-Tricks sind ausgenommen (n = 3, keine Trennung). |
| §5.1 Beatlose Brücke | Rezept `bruecke_beatlos` (Art Echo, B startet ohne Drums) | – |
| §5.2 Vorlauf | `tempo_modus="vorlauf"`, `regie.VORLAUF_MAX = 8 %`, `VORLAUF_TAKTE = 16` (Ausweichwert 8) | Nur mit Keylock und `max_bpm > 0`, nie nach WEITER. Der Vorlauf steht im Puffer von B vor der Blende; `blende_s` umfasst ihn, `vorlauf_s` nennt ihn. |
| §5.3 Halb-/Doppeltempo | `profil.tempo_mal`, `live._profil`, `plan.rangliste` | Eintrag und Profil von B laufen im doppelten bzw. halben Raster. |
| §6.1 | B's Hi-Hats (> 2 kHz, −12 dB) ab der Hälfte der Gesangsphase | – |
| §6.2 | `LANG32_BONUS = 0,3` | nach 2 Runden prüfen |
| §7.1 Bewertung | Seit 17.10. in der Übergangsliste des Mixers (statt Daumen/Popup): je Übergang Knöpfe 1–6 (Schulnote), die letzten 20 bewertbar, `POST /api/bewerten {nr, note}`; gespeichert als Note 5,0 … 1,0 (linear) plus `schulnote`; Ziel `ergebnisse/live-bewertungen/<datum>/`; Gewicht 1,0 (alte Daumen 0,5) | Meta wird beim Umschalten nur im Speicher gemerkt (kein Datei-Zugriff im Audio-Callback) und erst mit der Note geschrieben. 1–3 zählt für die Rezept-Vorlieben als gut. |
| §7.2 Vorhören | `GET /api/vorhoeren` (FLAC), Knopf und Ausgabegerät (`setSinkId`) | „Diesen nehmen“ entfällt: Die gebackene Blende bleibt ohnehin, bis jemand bedient. |
| §8 Set-Planung | `klangbild/paarnoten.py` (`python -m klangbild paarnoten`, Cache `cache/paarnoten.json`), `plan.set_planen` (gierig + 2-opt auf Abschnitten bis 8 Titel), Einstellung `set_bogen`, erwartete Note in der Warteschlange | Ohne Kritiker sind die Paarnoten die Regie-Punkte, über die Perzentile auf 1..5 gestreckt. |
| §10.1 Gemma-Einstellungen | `gemma_probe einstellungen`, 60 Sätze in `klangbild/gemma_saetze.json`, Ergebnis in `ergebnisse/gemma-probe/einstellungen-gemma-4-E2B-it.json` | **Tor verfehlt: 41 von 60 exakt (68 %, gefordert 85 %), aber alle 60 gültig.** Typische Fehler: ändert nicht genannte Felder mit („Alles so lassen“ setzt alles), verwechselt die Stufen („mehr Double Drops“ → kreativ statt wild) und überhört „streng“. Nach Plan entfällt die Sprachsteuerung auf dem Handy. Etwa 7 s je Satz auf der RTX 2070. |
| §9 `--set` (Runde 18) | `uebergangstest --set N`: je Fall 6 Songs in der Reihenfolge der Set-Planung, Übergang für Übergang wie live gebacken; zwischen zwei Blenden bleiben je 30 s, die Mitte fällt mit 0,4 s Pause weg (Probe: 6 Songs = 7,7 min, 31 s Backzeit). Set-Fälle fließen nicht in den Kritiker-Datensatz. | Benotet wird das ganze Set. |
| Runde 14 → Raster | `klangbild/anker.py` (`python -m klangbild anker`, Cache `cache/anker.json`): Downbeats je Song auf die Drum-Anschläge (Kick + Snare-Körper, Halbschlag über Kick gegen Snare) | 188 von 417 Titeln verschoben (oft ein halber Schlag). Ursache von „nicht im Takt“ in Runde 14. |
| Runde 14 → Drops/Phrasen | `Profil.drops` (1–3 je Song: Einsatz Bass + Drums + Pegel), `Profil.grenzen` (8er-Raster ab jedem Drop) | Vorher lag bei 39 % der Titel der stärkste Drop nicht auf dem Phrasenraster. |
| Runde 14 → EQ-Swap | EQ `profi`: Höhen, Mitten, Bass tauschen je in einem Schlag auf 4er-Grenzen (16 Takte: 4/8/12), Bass zuletzt auf `bass_takt` (zweite Hälfte) | Quellen: homedjstudio „DJ EQing“, mixgraph „Bass Swap“, wearecrossfader „3 ways to mix house“. |
| Runde 14 → Pegel-Reparatur | `regie.pegel_reparieren`: Buckel/Loch je Takt in die Grenzen ziehen (Loch höchstens +6 dB), erst danach Plan verwerfen; 5 Pläne vor dem Sicherheits-Blend, der keinen Trick mehr erbt | breakdown/rolle 0,3, Drop-Cuts aus (Noten 1,93 / 1,33 / 2,2) |
| Runde 15 → Double Drop | `Profil._drop_genau`: Drop = erster voller Takt (Bass und Drums >= Median danach -4 dB, bis k+2); Double-Drop-EQ: B ohne Bass, Mitten -3 dB, Höhen -8 dB bis zum Bass-Switch (eigen und Stems) | Runde 15: 3,56, Double Drop 2,86 – der Drop lag oft einen Takt zu früh (Auftakt-Takt). |
| Runde 16 → Grundsätzliches | 16 Runden (530 Noten) ausgewertet: Mittel pendelt um 3,2, Einzelregeln heben sich auf. Neu: `regie._strukturfehler` (A startet keinen Drop in der Blende, B's Drop nicht mitten drin, A's Drop spielt ≥ 16 Takte aus; −20 Punkte), `anker.taktphase` (Eins auf dem stärksten Kick-Schlag, ≥ 2× stärker als die alte Eins und ≥ 1,5× als jeder andere Schlag; im Versatz enthalten, Cache-Version 2), kurz ab 20 s (8 Takte 2,85, 4 Takte 1,45 gegen 16–32 Takte 3,2–3,4), Rezept-Vorwert `REZEPT_NOTE` aus allen Noten (geschrumpft), Riser nur vor echtem Drop mit +6 dB Pegel, Hall-Fahne 0,55, Gesangs-Überlappung −8 statt −12 | Quellen: Kim et al. 2020 (1.557 DJ-Mixe: Blendenlängen in 32-Schlag-Stufen, Tempo meist < 5 %), Zehren et al. 2020 (Wechsel immer auf der Eins einer Periode), Vande Veire & De Bie 2018 (DnB-Auto-DJ: drei Übergangsarten double drop / rolling / relaxed, ~10 % der Songs mit falschen Annotationen) |
| Runde 17 → ein Raster je Song | `uebergang.regulaer` ohne Ankerpunkt: Eins = Mehrheit der Downbeats, Schlag-Lage = häufigste Lage (Modus), lokal ±16 s nachgeführt (Drift); Profil, Regie, Backen und Anzeige nutzen dasselbe Raster, `profil.passt` prüft gegen dieses Raster. Loop-Wahl Planung = Backen (`uebergang.loop_im_original`); ein unsauberer Loop nur noch zur Not (auch nach dem Neuwählen und bei Rezepten, die die Blende kürzen). Sicherheits-Blend: unsauberer Loop → kürzere Blende ohne Loop. „schnell“: Ausweg mit ≥ 16 Takten Rest. `intro_loop_b` mit Tiefpass nur mit Bass-Tausch; B-Filter öffnen in höchstens 16 Takten | Runde 17: 3,69 (Runde 16: 3,19). Beat This! setzt die Eins in UKG/Breakbeat abschnittsweise ganze Schläge daneben; das Kreismittel um einen Ankerpunkt (Profil: Songmitte, Backen: Ausstieg) hing vom Punkt ab – bei 109 von 417 Titeln > 50 ms, bis zu 2 Schläge („Loop nicht sauber“, elevateD → Wild Inside 0,3 Schläge daneben: „nicht genau im gleichen Takt“). |
| Runde 18 → Fein-Anker, Echo im Takt | `anker.fein`: Kick-Lage je 4 s (Fenster ±8 s, gleiche Faltung wie der Versatz, höchstens 60 ms bzw. 0,15 Schlag, Median aus 5 Knoten) gegen das fertige Raster, `uebergang.taktraster` = `regulaer` + Knoten (Eintrag.fein, Cache anker.json "fein"). Kick-Kontrolle neu: `regie.kicks_versetzt` vergleicht die Kick-Lage von A und B an ihren Drops (Originale, je eigenes Raster), > 15 ms = Fehler. Echo auf ganzen Schlägen (`echo100`), Ping-Pong auf halben (`pingpong50`), Acapella-Stimme `echo50`; Ausstiegs-Effekt für normale Blends nur noch bei „wild“ und jedes zweite Paar, kein Hall; `fx_echo` −0,9 Vorzug. Backspin 5× schnell bis 40 % (vorher 4×, gleich abbremsend). `REZEPT_NOTE` aus 18 Runden (616 Noten, Mittel 3,23). Neues Stem-Rezept `melodie_zuerst` (B's Harmonien zuerst, dann Drums/Bass, B's Gesang zuletzt; ausgewogen/lang, harmonisch). Übergangstest: mehrere Ordner (`--nur-ordner "A|B"`), B immer aus A's Ordner und möglichst kein B zweimal je Runde, Stil und Experiment unabhängig reihum. Selbstkontrolle: ein Sync-Rezept, das beim Backen ohne Angleich endet (Vorlauf passte nicht), fällt durch (vorher still 4-Takt-Echo); die Regie prüft den Vorlauf wie `backen` am Tempo von Ausstieg und Einsatz (vorher A am Startpunkt gegen B's Takt 0). Stem-Arten (`drums_zuerst`, `melodie_zuerst`) nie auf einer Lage mit B-Intro-Loop (sie loopen nicht, B lief zu weit) | Runde 18: 3,75 (Runde 17: 3,69). `fx_echo` 3,12 (2× Note 2: „klingt, als wären sie nicht im Takt“ – 3/4-Schlag-Echo wiederholt neben den Schlägen; Echo75 über alle Runden 3,08, ohne Effekt 3,57). 5 von 13 Double Drops fielen durch die alte Kick-Kontrolle – schon die einzelnen Songs an ihren Drops: das Raster lag abschnittsweise 20–45 ms neben den Kicks (Arachnids −40 ms vorn, +38 ms hinten), und die Einsatz-Erkennung im Mix trennt zwei Züge unter ~80 ms nicht (Eichung mit versetzten Kopien). |
| Runde 19 → Backspin nur UKG/DnB, Loop und Echo mit der Rampe | Backspin (`spinback_drop`) nur, wenn B's Drop genau auf der Eins einschlägt, und nie bei Chill (`regie._chill`: Ordnername enthält „chill“, ohne Ordner/Upload Energielevel < 0,5). Echo-Verzögerung aus dem Schlag am Ende des Sends statt aus dem Schnitt über die Blende (`_schlag_bei`; auch Acapella-/Double-Drop-Echo der Stems), Bremse/Backspin ebenso. Loop-Stücke werden mit der Tempo-Rampe gedehnt (`_loopen` → `warp`), bei gleichem Tempo unverändert. `REZEPT_NOTE` aus 19 Runden (662 Noten, Mittel 3,27). Danach keine weiteren Hörrunden geplant | Runde 19 (nur Chill↔Chill und UKG↔UKG, alle Titel neu): 3,76 (Runde 18: 3,75), mit Stems 4,06, ohne 3,60. Backspin bei Chill 3,0 (n = 7; „passt nicht bei ruhigen Liedern, nur bei UKG, DnB“), bei UKG/DnB über alle Runden 4,0 (n = 29). Zweimal „nicht im gleichen Takt“: Fall 36 (Rampe 72 → 68 BPM in 4 Takten, das Echo nahm den mittleren Schlag – 24 ms je Wiederholung neben B), Fall 40 (32-Takt-Loop über eine 1-%-Rampe, das Loop-Stück lief bis ~40 ms neben dem Raster). `melodie_zuerst` 3,67 (n = 6), Acapella und B-Intro-Loop je 4,29. Offen: Fall 39 (UKG, B's Einsatz nach dem Intro +5 dB galt als Drop, klang nicht so) |
