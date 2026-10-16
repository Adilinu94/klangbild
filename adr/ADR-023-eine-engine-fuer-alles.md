# ADR-023 · Eine Engine für alles (auch der normale Modus)

**Status:** vorgeschlagen
**Datum:** 15.10.2026
**Ergänzt:** ADR-002, ADR-017 (löst dort Option 3 ein)

## Kontext

ADR-002 führt zwei Wiedergabewege ein: Media3/ExoPlayer für den normalen
Player, die eigene native Engine für den Auto-DJ. ADR-017 kapselt bereits beide
hinter **einem** Media3-`Player` (`SimpleBasePlayer`), damit es nur eine
MediaSession gibt. Offen blieb dort Option 3: ExoPlayer ganz weglassen.

Der Desktop-Prototyp hat diesen zweiten Weg nicht. `live.py` rendert **jeden**
Übergang mit derselben Engine (`uebergang.backen`). Ohne Auto-DJ ist der
Übergang ein nahtloser Schnitt am Songende (`_backen_ergebnis`, `autodj_an=False`).
Es gibt also bereits eine Implementierung, die beide Modi mit einem Renderer
abdeckt – getestet und gehört.

Zwei Player nebeneinander bedeuten: zwei Zustandsmaschinen, zwei
Positionsbegriffe, ein Moduswechsel mitten im Lauf. Die djay-Analyse (§88)
nennt genau diesen Doppelbetrieb als Fehlerquelle.

## Entscheidung

1. **Auch der normale Modus läuft über die eigene Engine.** Ohne Auto-DJ ist
   der „Übergang" ein Schnitt am Songende, genau wie im Desktop
   (`_backen_ergebnis`, `autodj_an=False`). Die Engine schaltet auf die nächste
   Spur, wenn die aktuelle ihr Ende erreicht.
2. **Media3 bleibt Fassade.** `SimpleBasePlayer` bedient Session,
   Benachrichtigung, Sperrbildschirm, Kopfhörertasten und Android Auto. Es gibt
   genau eine MediaSession (ADR-017).
3. **Kein ExoPlayer im APK.** Media3 wird nur als `session` + `common`
   eingebunden (keine `media3-exoplayer`-Abhängigkeit).

## Alternativen

1. **Zwei Player, wie ADR-002.** Verworfen: Moduswechsel als Bruchstelle, zwei
   Positionsbegriffe, doppelte Wartung.
2. **Nur die eigene Engine.** **Gewählt.** Der Desktop beweist, dass ein
   Renderer beide Modi trägt.
3. **ExoPlayer auch für den Auto-DJ.** Verworfen: Echtzeit-Signalgraph im
   Callback widerspricht dem Vorausbacken (siehe ADR-024).

## Konsequenzen

- Die Engine muss den gapless-Schnitt können (Timeline schließt Segmente direkt
  aneinander, §5.2 im Bauplan). Der Desktop macht es genauso.
- Der Player-Zustand kommt aus einer Quelle. Kein Zustandswechsel, kein
  Umhängen der Session.
- Media3 bleibt eine reine Anzeige-/Steuerungsschicht; ein späterer Wechsel der
  Benachrichtigungs-Bibliothek berührt die Engine nicht.
- Risiko: Fehlt Media3-ExoPlayer-Funktionalität (z. B. exotische Container),
  muss der eigene Decoder sie liefern. Der Decoder-Port steht in M2 (§5.5);
  die Formatliste deckt MP3, AAC/M4A, FLAC, OGG/Vorbis, Opus, WAV.

## Belege

- ADR-002, ADR-017
- djay-Analyse §88 (Doppelbetrieb als Fehlerquelle)
- `prototyp/klangbild/live.py` (`_backen_ergebnis`, `autodj_an=False`)
- `BAUPLAN-ANDROID.md` §3.4
