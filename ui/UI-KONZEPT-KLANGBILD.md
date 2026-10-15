# Klangbild · UI-Konzept (Nothing Design System, Android)

**Stand: 10.10.2026 · Entwurf Rev. 2 · Richtung: `ui/DIRECTION.md`**
**Rev. 2:** Aufbau folgt **Poweramp** (Nutzer-Screenshots vom 28.07.2026:
Bibliothek als Kategorie-Liste, Player mit rundem Cover mittig + Waveform-
Seekbar, Alle-Titel mit Toolbar, Mini-Player) — Haut, Typo und Verhalten
bleiben **Nothing**. Fonts wie gehabt. Mockups: `ui/mockups/klangbild.html`.
**Rev. 3 (14.10.2026):** Player-Gesten gelten nach `BAUPLAN-ANDROID.md` §8.4:
Play-Knopf mittig auf der laufenden Wellenform, Wellenform wischen = Position,
Cover wischen = Titel mit 3D-Ausblendung (Referenz `ui/referenz/`). Das
ersetzt §3.2 Punkte 1, 5 und 6.

Dies ist das komplette UI-Konzept der Android-App (Phase 4–6). Es beantwortet:
Konzept, Screens, Design-Elemente, Aufbau, Animationen — mit Begründung, was
von Spotify / Apple Music / Poweramp übernommen und was bewusst verworfen wird.

---

## 1 · Konzept in einem Satz

**Klangbild ist ein Messgerät, das Musik spielt** — schwarzes Panel, weiße
Daten, eine rote Signalleuchte. Die Analyse-Engine (BPM, Camelot, LUFS) bekommt
eine ablesbare Frontplatte; der Auto-DJ bekommt einen einzigen roten Schalter.
(Vollbrief, Tokens, Signatur-Storyboard: `ui/DIRECTION.md`.)

Drei-Lagen-Regel je Screen: **primär** (eine Sache, Doto/Space Grotesk groß),
**sekundär** (Kontext, Space Grotesk), **tertiär** (Metadaten, Space Mono Caps
in `#999999`, an Ränder und Unterkanten geschoben). Squint-Test: Nach
Zusammenkneifen muss genau ein Element übrig bleiben.

---

## 2 · Screen-Map (Poweramp-Aufbau, Nothing-Haut)

```
BIBLIOTHEK (Kategorie-Liste)    PLAYER (rund + Waveform)    AUTO-DJ-KONSOLE
├─ Alle Titel ─┐                ├─ Cover-Scheibe            ├─ Schalter + Set
├─ Ordner      │ Toolbar:       ├─ Titel/Künstler           ├─ Eingreifen
├─ Interpreten │ Shuffle·Play·  ├─ Icon-Reihe (4)           └─ Protokoll
├─ Playlists   │ Suche·Auswählen│ ├─ Waveform + Play-Kreis
├─ Warteschl.  ├─ Track-Zeilen  ├─ Icon-Bar (4)
└─ …           └─ Mini-Player   └─ Mini-Player
SUCHE (Klang) · ALBUM-DETAIL · ENERGIE-REISE · EINSTELLUNGEN+EQ
```

**Navigation wie Poweramp:** keine Bottom-Text-Nav, sondern **4er-Icon-Bar**
(Bibliothek, EQ/Analyse, Suche, Menü) + **Mini-Player** darüber (Scheibe,
Titel, Play/Pause, Segment-Fortschritt). Monoline-Icons 1,5 px, aktiv = weiß
bzw. rot-Punkt bei ON AIR, inaktiv = `#666666`.

---

## 3 · Die Screens (Aufbau je Screen)

### 3.1 Bibliothek (Kategorie-Liste wie Poweramp)

- **Primär:** Headline `BIBLIOTHEK` in Space Grotesk Light 300, 40 px,
  linksbündig (kein Gruß, kein Hero-Zahlenspiel mehr — die Liste ist der Star).
- **Zeilen (64 dp Takt):** **Mono-Icon-Kreis** (48 px, `--surface`, 1 px
  Border, Monoline-Icon weiß) + Label in Grotesk-Caps 20 px Light. Kein
  Pastell, keine Emoji: `ALLE TITEL · ORDNER · INTERPRETEN ·
  WIEDERGABELISTEN · WARTESCHLANGE (1/1) · HÄUFIG GESPIELT · KÜRZLICH
  GESPIELT · KÜRZLICH HINZUGEFÜGT`. Zähler rechts in Mono (`8.214`).
- **Tertiär:** oben nichts außer Uhr/Status (System); Sc liczba als dünner
  Segment-Scrollbalken rechts (Poweramp hat blau — unserer ist weiß).
- **Unten:** Mini-Player + 4er-Icon-Bar (s. §2).
- **Übernommen:** komplette Informationsarchitektur (Kategorien, Zähler,
  Mini-Player, Icon-Bar). **Verworfen:** Pastell-Icons, blauer Akzent,
  dünne Light-Typo ohne Kontrast (unsere Labels bekommen `#E8E8E8` auf
  Schwarz statt Poweramp-Grau auf Weiß).

### 3.2 Player (rundes Cover mittig + Waveform — Poweramp-Gerüst, Nothing-Haut)

Aufbau von oben nach unten exakt wie dein Screenshot, nur umgehäutet:

1. **Cover-Scheibe:** rund, ~280 dp, **mittig**, rotiert bei Wiedergabe
   langsam (33⅓-Umdrehungs-Anmutung: 8 s/Umdrehung, linear, pausiert mit
   Play). Kein Cover → graue Scheibe mit eingeätztem Loch (wie Poweramp-
   Platzhalter, aber in `--surface` statt Hellgrau).
2. **Titel/Künstler:** Titel in Grotesk-Medium Caps 24 (Poweramp-Blau → unser
   Weiß), darunter `INTERPRET – TITEL` in Mono 13 `#999999`. Kein Doto-Riese
   mehr (Rev. 1 verworfen — Familiarität schlägt Poster).
3. **Datenzeile (neu, das Instrument):** `127 BPM · 8A · −11.2 LUFS` in Mono
   12 unter dem Künstler — Poweramp zeigt das nicht, wir schon (Frontplatte).
4. **Icon-Reihe (4):** Herz/Sleeptimer-nah, Uhr (Sleep), Repeat, Shuffle —
   Monoline, inaktiv `#666666`, aktiv = weiß (Shuffle an = weiß + Punkt).
   Poweramp-Blau → Weiß/Rot.
5. **Waveform-Seekbar (Herzstück):** 64 RMS-Peak-Balken aus der gespeicherten
   Analyse (`features.energie_json`, Track-relativ normiert — belegt in
   `ui/mockups/waveform-data.json`, gebaut mit `prototyp/wave_build.py`,
   Beispiel: Angel of Mine 130.0 BPM/3B, Arcade 134.0 BPM/8A — gemessen mit
   der 0.3.0-BPM-Regression), 3 px breit,
   2 px Gap, volle Breite. Gespielt = **weiß**, offen = `#333333`,
   Phrasen-Anfänge (jeder 8. Downbeat, `PHRASEN_TAKTE`) = rote 1-px-Ticks
   unter der Nulllinie. **Kein Spiegel-Gloss** (Poweramps Reflexion entfällt —
   OLED-Disziplin). Scrubben: Finger folgt 1:1, Zeit rollt in Mono, Haptic
   beim Sekunden-Snap. Links `0:03`, rechts `3:31` in Mono 12.
6. **Play-Kreis über der Wave:** 72 dp weißer Kreis mit schwarzem
   Pause-/Play-Glyph, **überlappt die Waveform links** (wie dein Screenshot:
   Blau → Weiß/Schwarz). 100 ms Press-Dim, kein Bounce.
7. **Auto-DJ-Zusatz (nur wenn an):** rote Beat-Ticks + Countdown-Segmente
   (8 Takte Blende = 8 Segmente, füllen sich rot, dazu `TAKT 5/8` in Mono;
   s. Mockup-Screens 03/04) + Zeile `[NÄCHSTER: RUSTY NAILS · 11B]` unter der
   Wave; Play-Kreis bekommt roten Ring statt Vollrot (Rot bleibt Ereignis,
   frisst den Screen nicht).
8. **Unten:** Mini-Player gibt es hier nicht (ist der Player) — nur 4er-Icon-Bar.
- **Gesten (Poweramp-Parität):** Swipe links/rechts auf Cover = Track,
  Swipe hoch/runter = Lautstärke, Tap auf Wave = Springen. Long-Press = Kontext.
- **Verworfen von Poweramp:** blauer Akzent, Gloss-Reflexion, Skinbarkeit,
  überladene Pro-Buttons (Rating-Sterne etc. → Long-Press-Menü).

### 3.3 Auto-DJ-Konsole (der rote Screen) — unverändert, plus Wave-Anker

Wie Rev. 1 (Schalter, Set-Segmente, Camelot-Kette, Protokoll, 3 Pills).
Neu: Mini-Waveform des Übergangsfensters (letzte 45 s A + erste 45 s B als
Doppel-Wave, rot = Blende) — die Brücke zum Player-Gefühl. Rest s. Rev. 1.

### 3.4 Alle Titel (Toolbar + Zeilen + Mini-Player wie dein Screenshot)

- **Header:** `‹ BIBLIOTHEK` (Mono, zurück) + Headline `ALLE TITEL` + Icon-Kreis.
- **Toolbar:** Shuffle, Play, Suche, `AUSWÄHLEN` (Mono-Caps), ⋮ — Monoline,
  Play = weiß gefüllt.
- **Track-Zeile (72 dp):** Cover 56 px **quadratisch, 12 px Radius** (Poweramp-
  Parität — rund ist nur die Player-Scheibe), Titel Grotesk 500 18, Künstler
  Mono 13 grau, Meta-Zeile `♪ 3:36 | MP3 | 127 BPM | 8A` in Mono 12. Kein
  Cover → Scheiben-Platzhalter.
- **Mini-Player (fixiert über Icon-Bar, s. Mockup-Screen 09):** rotierende
  Mini-Scheibe 40 px + Titel (weiß/Mono) + Künstler + Pause-Icon + **2-px-
  Segment-Fortschritt** darunter. Zwei Zustände: normal (BPM · Camelot) vs.
  Auto-DJ-Blende (rot: `BLENDE 5/8` + rotes Segment). Tap → Player (Zoom),
  Swipe-hoch → Player (folgt Finger), Swipe-seitlich → Track (Haptic-Snap),
  Tap Pause → Scheibe friert ohne Snap. Immer sichtbar außer im Player selbst.
- **Queue** bleibt Bottom-Sheet aus Rev. 1 (aktuelle Zeile mit Rot-Kante +
  Beat-Punkt, `[AUTO]`-Chips mit Grund).

### 3.5 Suche / Klang-Suche — unverändert (Rev. 1)

### 3.6 Album- / Künstler-Detail — unverändert (Rev. 1)

### 3.7 Energie-Reise (Phase 6, Kann) — unverändert (Rev. 1)

### 3.8 Einstellungen (schlank!) — unverändert (Rev. 1)

---

## 4 · Design-Elemente (Baukasten, Nothing-treu)

| Element | Spec | Wo |
|---|---|---|
| Doto-Display | 48–72 px, −0.02em, nur Headlines/Zahlen | Player-Titel, Bibliotheks-Zahl, ON AIR |
| Mono-Labels | Space Mono 11 px, Caps, 0.08em, `#999999` | überall als Beschriftung |
| Segment-Balken | Blöcke, 2 px Gaps, Hero 16–20 / Standard 8–12 / Kompakt 4–6 px | Fortschritt, Set, Energie |
| Beat-Punkt | 8 px Kreis, rot, pulsiert im Beat (120 ms an) | Player, Konsole, Mini-Player |
| Camelot-Chip | Border-Chip 4 px, Mono 12, Match = grün | Track-Zeilen, Protokoll |
| Mechanik-Toggle | Pill, ON = rot/weiß invertiert, 44 dp Target | Auto-DJ, Einstellungen |
| Inline-Status | `[GESCANNT]`, `[NEU GEPLANT]`, `[KEIN TREFFER]`, Mono | statt Toasts überall |
| Dot-Grid | 12–16 px Raster, Opacity 0.1–0.2, nur Hintergrund | Konsole, Empty-States |
| Hairlines | 1 px `#222222`, volle Breite | alle Listen |
| Cover-Scheibe (rund) | 280 dp Player / 40 px Mini, Rotation 8 s/U, Pause mit Play | Player, Mini-Player |
| Waveform-Seekbar | ~64 Balken, 3/2 px, weiß/`#333`, rote Downbeat-Ticks, kein Gloss | Player (+ Mini-Doppel-Wave in Konsole) |
| Play-Kreis | 72 dp weiß/schwarz, überlappt Wave links, 100 ms Dim | Player |
| Kategorie-Zeile | 64 dp, Mono-Icon-Kreis 48 px, Caps-Label 20 Light | Bibliothek |
| Mini-Player | Scheibe + Titel + Pause + 2-px-Segmente, 2 Zustände (normal / Blende rot), 4 Gesten (s. Screen 09) | überall außer Player |
| Countdown-Segmente | 8 Segmente = 8 Takte Blende, rot-füllend + `TAKT n/8` | Player 03/04 |

**Verboten (Skill-Anti-Patterns):** Gradients, Schatten, Blur, Skeletons
(`[LADE…]` stattdessen), Toasts, Emoji-Icons, Zebra-Stripes, Radius > 16 px,
Spring/Bounce, Parallax.

---

## 5 · Animationen (jede mit Wozu, Zeit, Haptic)

Jede Animation beantwortet eine der vier Fragen (woher/wohin, was geschah,
was kann ich, wie fühlte es sich an). Sonst wird sie gelöscht.

| # | Moment | Was | Zeit / Kurve | Haptic | Fallback reduced-motion |
|---|---|---|---|---|---|
| 1 | **AUTO-DJ einrasten** (Signatur) | Thumb springt, wird rot, `[MIX WIRD GEBAUT…]` tippt sich, Segmente füllen | 120 ms ease-out + Tipp-Sequenz | impact light | statisch `[ON AIR]` |
| 2 | **Track-Wechsel im Player** | Scheibe cross-faded, Titel + Zahl rollt, Wave baut sich neu (Balken wachsen 150 ms) | 250 ms ease-out | kein | Cross-Fade |
| 2b | **Cover-Rotation** | Scheibe rotiert linear 8 s/U bei Play, friert bei Pause (kein Snap). Technik: nur `transform: rotate` (Compositor, kein Layout/Paint), `will-change: transform`. Low-Power (Low-RAM-Geräte): Rotation aus, Fortschritt läuft über Segmente + Wave (Schalter `?lowpower=1` im Mockup; real Sensordaten-Fallback) | linear, unendlich | kein | statisch |
| 2c | **Wave-Scrubben** | Balken folgen Finger 1:1, Zeit rollt, Sekunden-Snap mit Haptic | direkt | selection beim Snap | direkt ohne Haptic |
| 3 | **Player auf/zu** | Mini-Leiste wächst per Zoom ins Poster (shared element) | 400 ms Feder | light beim Andocken | Fade |
| 4 | **Übergangs-Countdown** | Segmente des nächsten Übergangs füllen sich, Beat-Punkt pulsiert | Beat-synchron | kein (zu oft) | statische Zahl |
| 5 | **Queue-Sheet** | Drag 1:1, Release → Feder, Rubber-Band am Limit | Feder 350 ms | light beim Einrasten | Fade |
| 6 | **Scrubben** | Wellenform/Segmente folgen Finger 1:1, Zeit rollt | direkt | selection beim Sekunden-Snap | direkt ohne Haptic |
| 7 | **Neuplanung** | Set-Segmente blinken einmal weiß → neue Reihenfolge faded ein | 200 ms | success | Textwechsel |
| 8 | **Suche tippt Ergebnis** | Ergebnis-Zeilen faden gestaffelt (max. 6, je 30 ms) — einzige Staffelung | 180 ms | kein | alle sofort |
| 9 | **Energie-Kurve** | Linie zeichnet sich beim Öffnen | 400 ms | kein | sofort voll |
| 10 | **Fehler** | Betroffene Zeile: Border → rot + `[FEHLER: …]` inline | 150 ms | error | statisch |

**Niemals:** Staggered-Fade-ups auf jedem Screen, Bounce, Parallax,
Cover-Zoom beim Scrollen, Glow/Blob hinter dem Beat-Punkt (der Punkt pulsiert
durch An/Aus, nicht durch Leuchten — OLED-Disziplin).

---

## 6 · Was wir von wem lernen (ehrlich)

- **Spotify:** Listen-Dichte, Long-Press statt Button-Chaos, Suche als Nav-Punkt,
  Daumen-Zone. Verworfen: Grün, Karten, Social, flüchtige Sheets.
- **Apple Music:** Typo-Mut, Großzügigkeit, Queue im Kontext. Verworfen:
  Full-Bleed-Cover, Glas-auf-Content, Lyrics-Bühne.
- **Poweramp (Gerüst, Rev. 2):** Kategorie-Liste, runder Player mit Waveform-
  Seekbar + überlappendem Play-Kreis, Toolbar auf Alle Titel, Mini-Player,
  4er-Icon-Bar, Gesten (Swipe = Track/Lautstärke, Tap auf Wave = Springen).
  Verworfen: blauer Akzent, Gloss-Reflexion, Pastell-Icons, Skin-Baukasten,
  Einstellungs-Labyrinth.
- **Nothing (Haut, immer):** Doto/Space-Mono-Frontplatte, Monochrom + ein Rot,
  Segmente statt Slider, Inline-Status statt Toasts, rotierende Scheibe statt
  Vinyl-Skeuomorphismus mit Glanz. **Cover-Regel:** echtes Cover-Art aus den
  Tags (MP3-APIC etc.) rotiert als Label mit; ohne Cover ein einfarbiger Platz
  mit Doto-Anfangsbuchstabe (Mockups: `covers/track-11.jpg`, `track-12.jpg`
  aus den echten Dateien extrahiert).
- **Nothing (OS, X-App, Glyph):** Dot-Matrix als Identität (Doto = Ndot-Ersatz),
  Monochrom als Haltung, Glyph-Musik-Visualizer als Vorbild für den Beat-Punkt,
  Nothing-X-EQ als Vorbild für den EQ-Screen (10 Bänder, vertikal, instrumentell).
- **djay / Cross DJ:** Crossfader-Metapher (als Segmente abstrahiert),
  Übergangs-Protokoll. Verworfen: Deck-Skeuomorphismus.

---

## 7 · Offene Entscheidungen (für dich)

1. **Player-Cover (erledigt durch Rev. 2):** runde Scheibe mittig, ~280 dp,
   rotiert — Poweramp-Parität, Poster verworfen.
2. **Rot-Dauer:** ON-AIR-Rot als Dauerzustand ok, oder soll die Konsole nach
   10 s ins ruhige Weiß zurückfallen und nur der Beat-Punkt rot bleiben?
3. **EQ-Screen:** eigener Nav-Unterpunkt oder nur aus Player erreichbar?
   Vorschlag: nur aus Player (Einstellungen bleiben bei 12 Zeilen).
4. **Light-Modus-Führung:** Beide Modi gleichwertig ausgearbeitet (dein Wunsch) —
   Mockups zeigen beide; Führung bleibt Dark.
5. **Icon-Bar-Labels (entschieden 10.10.2026):** `BIBL./EQ/SUCHE/MENÜ` in
   Mono-Caps 9 px bleiben darunter — Poweramp-Parität, 48-dp-Touch-Target,
   hilft Umsteigern 35+. Rein ikonisch verworfen (Rate-Risiko).
6. **ADR-020 (angenommen 10.10.2026):** Tempo-Gate ±1 % statt ±3 % — betrifft
   nur die Engine, nicht das UI (Konsole zeigt weiter `×1.0xx`).
