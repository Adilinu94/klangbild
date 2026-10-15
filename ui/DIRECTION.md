# Klangbild · UI-Direction (Nothing Design System)

**Stand: 10.10.2026 · Status: Entwurf zur Abstimmung · R2 umgesetzt**
**Brief (self-authored):** Musik-Player für eigene Dateien + Auto-DJ, Android, Zielgruppe
Sammler mit großer lokaler Bibliothek (Persona Tom, 41, 8.000 Titel).
Kernaktion in den ersten 10 Sekunden: Song antippen → spielt. Oder: Auto-DJ
einschalten → Mix läuft. Gefühl in drei Worten: **präzise, ruhig, mechanisch.**
Referenzen außerhalb von Apps: Braun-Taschenradio (SK 4), Flughafentafel
(Solani), Teenage-Engineering-Bedienfeld.

## Konzept

**Klangbild ist ein Messgerät, das Musik spielt.**

Nicht eine Bühne (Apple Music), nicht eine Social-Plattform (Spotify), nicht ein
Cockpit mit 200 Schaltern (Poweramp). Ein Instrument: schwarzes Panel, weiße
Daten, eine rote Signalleuchte. Die DJ-Maschine im Hintergrund (BPM, Tonart,
Camelot, LUFS) bekommt eine ablesbare Frontplatte — und der Auto-DJ einen
einzigen roten Schalter.

Mapping auf App-Designer-Directions: **C. Instrument** als Basis (dicht,
exakt, dunkel, eine Signalfarbe), gekreuzt mit **D. Swiss Timetable**
(Grid, Riesen-Ziffern, ein Rot, keine Karten) und einer Prise
**F. Colour Field** (der Player-Screen als Poster: Titel in Doto-Riesenlettern).
Der Skill nennt sein eigenes Slop-Risiko beim Namen: graue Papier-Mono-Langeweile.
Dagegen stehen hier: das Poster, der Glyph-Visualizer, die Timetable-Ziffern.

## Drei Richtungen (exploriert, eine gewählt)

1. **A — „Die Tafel" (gewählt).** Dark-OLED, Doto-Headlines wie Abflughafen,
   Space-Mono-Daten, ein Rot. Player als Poster, Bibliothek als Timetable.
2. **B — „Das Handbuch" (verloren).** Light-Papier, technische Zeichnung,
   alles Dokumentation. Schön, aber Musik ist Nacht — Light wird sauber
   abgeleitet, nicht geführt.
3. **C — „Die Bühne" (verloren).** Cover-Art-bleed wie Apple Music, Farbe aus
   dem Bild. Verrät das Konzept: Bei uns ist die *Maschine* der Star, nicht
   das Cover. Cover bleiben klein und quadratisch, nie Full-Bleed.

## Abgelehnte Kategorie-Defaults

| App | Default | Wir nicht |
|---|---|---|
| Spotify | grün auf schwarz, runde Karten, Social-Overlays | kein Grün, keine Kartenstapel, kein Social |
| Apple Music | Full-Bleed-Artwork, Glas, Lyrics-Bühne | Cover max. 112 px in Listen, kein Glas auf Content |
| Poweramp | Skin-Baukasten, 200 Einstellungen, Wisch-Gesten überall | eine Meinung statt Optionen, Gesten nur wo sie tragen |

## Tokens (Nothing-Skill + eigene Ableitung)

Fonts (Google Fonts): **Doto** (Display, nur 36 px+), **Space Grotesk**
(UI-Text), **Space Mono** (alle Daten, alle Labels, Caps).
Dark: `#000000` / `#111111` / `#1A1A1A`, Text `#FFFFFF` / `#E8E8E8` /
`#999999` / `#666666`. Light: `#F5F5F5` / `#FFFFFF`, Text `#000000` /
`#1A1A1A` / `#666666` / `#999999`. Akzent: **Rot `#D71921`** = der Auto-DJ
ist an / Live / Warnung. Erfolg `#4A9E5C`, Warnung `#D4A843`.
Radien: Pills für Buttons, 4–8 px technisch, max. 16 px Cards.
Motion: 150–250 ms Mikro, 300–400 ms Übergänge, `cubic-bezier(0.25,0.1,0.25,1)`,
Opacity vor Position, kein Spring/Bounce, kein Parallax.

## Signatur-Interaktion: der AUTO-DJ-Schalter

Storyboard: (1) Ruhezustand — mechanischer Kippschalter, Gravur `AUTO-DJ`,
Stellung OFF. (2) Finger legt um — Schalter rastet mit 120 ms `ease-out` ein,
leichter Haptic-`impact`. (3) Der Schalter wird rot, Statuszeile tippt
`[MIX WIRD GEBAUT…]` in Doto, Segment für Segment. (4) Erster Übergang rastet
ein: `[ON AIR]` + roter Punkt pulsiert im Beat (120 ms an, Rest aus — kein
Glow). Reduced Motion: kein Puls, nur statisch `[ON AIR]`.
Der Moment beantwortet „Was ist gerade passiert?" und ist nach dem 100. Mal
noch gut, weil er unter einer Sekunde bleibt und nie blockiert.

## Content (echt, uneben)

Bibliothek: 8.214 Tracks, 673 Alben. Beispiele: „Aphex Twin — Xtal"
(4:54, 127 BPM, 8A), „Boards of Canada — Dayvan Cowboy" (5:01, 102 BPM, 5A),
„Moderat — Rusty Nails" (4:10, 122 BPM, 11B). Auto-DJ-Set: 14 Tracks,
58:32 min, Master 124 BPM, Übergänge 8 Takte, alle Camelot-Nachbarn.
Energie-Reise: 20:00 ruhig → 21:00 euphorisch.

## Rev. 2 (10.10.2026, Nutzerwunsch nach Poweramp-Screenshots)

Aufbau folgt **Poweramp**, Haut bleibt **Nothing**:

- **Bibliothek = Kategorie-Liste** (Alle Titel, Ordner, Interpreten,
  Wiedergabelisten, Warteschlange, Häufig gespielt, Kürzlich gespielt,
  Kürzlich hinzugefügt) statt Segmented-Control. Icon-Kreise statt
  Farbklexe: Monoline-Icons auf `--surface`, keine Pastellkreise.
- **Player = rundes Cover, mittig** (Vinyl-Metapher, rotiert langsam bei
  Wiedergabe), Titel in Caps darunter, 4er-Icon-Reihe, **Waveform-Seekbar**
  mit überlappendem Play-Kreis, Zeiten links/rechts, 4er-Icon-Bar unten.
- **Alle Titel = Header + Toolbar** (Shuffle, Play, Suche, Auswählen, ⋮) +
  Track-Zeilen + Mini-Player.
- **Mini-Player** über der Nav: rotierende Mini-Scheibe, Titel/Künstler,
  Play/Pause, dünner Segment-Fortschritt.
- **Waveform** ist segmentierte RMS-Kurve (aus `energy.py`, ~64 Balken je
  Track): gespielt = weiß, offen = `#333`, Downbeats = rote Ticks. Kein
  Spiegel-Gloss (Poweramp-Reflexion entfällt — OLED-Disziplin).
- Der Poster-Entwurf aus Rev. 1 (eckiges Cover links, Doto-Riesentitel) ist
  **verworfen**: Familiarität für Poweramp-Umsteiger schlägt Poster-Geste.
  Doto bleibt für Zahlen/Status (`8.214`, `ON AIR`, Track-Nummern).

## R2 (10.10.2026, Feinschliff nach Selbstkritik)

- **Lucide-SVGs statt Unicode:** alle Icons als Monoline-SVG (1,5 px,
  runde Caps), kein Zeichen-Font — keine Tofu-Kästchen auf Geräten.
- **Countdown-Segmente:** 8 Takte Blende = 8 Segmente, füllen sich rot +
  `TAKT n/8` in Mono (Player-Screens 03/04).
- **Mini-Player-Screen 09:** Normal vs. Blende-Zustand + 4 Gesten
  (Tap, Swipe-hoch, Swipe-seitlich, Pause) mit Zeiten/Haptik dokumentiert.
- **Echte Cover:** aus den MP3-Tags extrahiert (`mockups/covers/`), rotieren
  als Label mit; ohne Cover Doto-Anfangsbuchstabe.
- **Rotation Low-End:** nur `transform: rotate` (Compositor, `will-change`),
  Low-Power-Fallback ohne Rotation (Segmente tragen den Fortschritt),
  Schalter `?lowpower=1` im Mockup.
