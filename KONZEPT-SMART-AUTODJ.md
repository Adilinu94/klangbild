# Klangbild — Konzept: Auto-DJ wählt jeden Übergang selbst

Stand 2026-10-11 · ergänzt `WISSEN-DJ-TECHNIKEN-UND-REPOS.md` (§2–§5) · noch nicht umgesetzt

**Ziel:** Du stellst nur noch einen **Mix-Stil** ein: „Kurz & sauber",
„Ausgewogen" oder „Lang & komplex". Der Auto-DJ wählt dann je Titelpaar selbst
Einstiegspunkt, Länge, Lautstärkekurve, EQ, Filter, Effekte, Loops und Stems. Er
zeigt jeweils an, warum er so entschieden hat. Die bisherigen Einstellungen
bleiben als „Manuell" erhalten.

---

## 1 · Was Profi-DJs tatsächlich tun (belegt)

| Befund | Quelle | Folge für uns |
|---|---|---|
| Übergangslängen häufen sich bei **Vielfachen von 32 Beats** (8 Takte); Cue-Outs liegen auf Phrasengrenzen | Kim et al., 20.765 Übergänge aus 1.557 echten Mixen | Längen nur 4/8/16/32 Takte, Start immer auf einem Phrasenanfang (haben wir) |
| **86 %** der Titel werden um weniger als 5 % im Tempo verändert, 94,5 % um weniger als 10 %. Keylock ist Standard, nur 2,5 % werden transponiert | Kim et al. | Grenze ±5 % als Normalfall, darüber Echo-Out oder Schnitt. Keylock an lassen |
| DJs setzen denselben Titel an ähnlichen Stellen an: 73,6 % innerhalb von 8 Takten | Kim et al. | Gute Cue-Punkte sind vorhersagbar: Regeln reichen, kein Training nötig |
| Wechselpunkt = Stelle hoher **Neuheit** (Rhythmus, Lautheit, Klang, Harmonie), **immer am Anfang einer Periode**, und der Teil danach muss **für sich stehen** können | Zehren et al., aus DJ-Interviews, 96 % brauchbare Punkte | Cue-In von B dort, wo B nach der Blende „trägt" (nicht in ein dünnes Intro hinein enden) |
| Drei Grundtypen: **Double Drop** (beide Drops gleichzeitig; Einstieg 16 Takte vor dem Drop), **Rolling** (A's Energie läuft, B's Drop übernimmt), **Relaxed** (A klingt aus, B startet von vorn). Bass und Höhen von B kommen erst zum Wechsel. Gleicher Typ nie zweimal hintereinander | Vande Veire & De Bie (Drum & Bass); Hörtest 17 von 18 bevorzugt | Energieverlauf bestimmt den Typ. Abwechslung per Übergangsmatrix |
| **Gesang entscheidet**: Regeln je Fall V→V, V→NV, NV→V, NV→NV (V = Gesang an der Mischstelle). Schnelle Übergänge bei V→V werden als unangenehm bewertet | DJtransGAN (Sony/Academia Sinica), Hörtest mit 136 Personen | Gesang je Takt messen (Gesangs-Stem) und nach diesen 4 Fällen entscheiden |
| **Dicht gegen dünn:** Zwei dünne Intros/Outros vertragen lange Blends. Zwei dichte Teile mit Gesang verlangen einen kurzen Schnitt auf den Downbeat. Passende Tonarten erlauben 32 Takte Überlappung, unpassende kurze Überlappung oder Filter | DJ.Studio, Mixed In Key (Praxis) | Dichte (Drums + Harmonie) je Takt messen |
| **Energiebogen:** Warm-up lange Blends, Peak kurze harte Wechsel, Release Filter/Hall/Echo. Steigern = Cut oder Echo-Out in einen Drop. Beruhigen = langer Blend | DJ.Studio „Anatomy of a great mix" | Energiedifferenz A→B bestimmt Kurve und Effekt |

---

## 2 · Merkmale, die der Auto-DJ braucht

| Merkmal | Heute | Neu |
|---|---|---|
| BPM, Taktraster, Phrasen | ✓ (Beat This!, ±0,1 %) | – |
| Tonart (Camelot) | ✓ | Vertrauen der Tonart nutzen (`key_vertrauen`, schon in der DB) |
| Energie | ✓ alle 0,5 s (`energie_json`) | **je Takt** mitteln |
| Abschnittsgrenzen | ✓ Neuheit (`abschnitte_json`) | Etiketten aus Energie: **Intro / Aufbau / Drop / Break / Outro** (Drop = Energiesprung nach einem Tal) |
| **Gesang je Takt** | ✗ | aus dem Gesangs-Stem des Vorrats (RMS je Takt). Fällt beim Anlegen des Vorrats ab, ohne Zusatzkosten |
| **Drums je Takt** (Dichte, „beatlos") | ✗ | aus dem Drum-Stem des Vorrats |

Der Stem-Vorrat aus diesem Schritt liefert die Gesang- und Drum-Kurven gleich
mit. Ohne Grafikkarte reicht er für Uploads und die Warteschlange. Mit CUDA ist
in rund einer Stunde die ganze Bibliothek fertig (Abschnitt 6).

---

## 3 · Entscheidung je Übergang (Regelwerk V2)

**Schritt 1, Cue-Out in A.** Kandidaten sind alle Phrasenanfänge im letzten
Drittel. Jeder bekommt Punkte:
- \+ Outro- oder Break-Etikett, sinkende Energie, kein Gesang in den nächsten N Takten
- − mitten in einer Gesangsphrase, kurz vor dem Ende, wenn die Blende nicht mehr passt

**Schritt 2, Cue-In in B.** Kandidaten sind die Phrasenanfänge im Intro.
Gewählt wird so, dass B's erster Gesang und B's Drop **nach** der Blende
kommen. Die Ausnahme ist Double Drop: Dort landen beide Drops gleichzeitig.

**Schritt 3, Rezept wählen** (Stil-Regler skaliert Länge und Effektfreude):

| Lage | Kurz & sauber | Ausgewogen | Lang & komplex |
|---|---|---|---|
| NV→NV, Tonart passt, ΔBPM ≤ 3 % | EQ, Basswechsel Mitte, 8 T | EQ, 16 T | Stems: Drums zuerst, 32 T; Loop, wenn das Outro von A zu kurz ist |
| V(A)→NV | Echo-Out am Gesangsende, 4 T | Gesang von A per Stem-Echo raus, 8 T | Acapella-Brücke (Gesang A über Instrumental B), 16 T, nur bei passender Tonart |
| NV→V(B) | Blende endet vor B's Gesang | dito, 8–16 T | Drums zuerst, B's Gesang erst nach dem Basswechsel |
| V→V | Schnitt auf die 1 | Gesangsschutz, 4–8 T | Gesangsschutz plus Hall auf A's Gesang |
| Tonart unpassend | Filter-Blend kurz / Echo-Out | nur Drums überlappen (Stems), 8 T | Tonart-Rettung: Harmonie und Gesang nie gleichzeitig, 16 T |
| ΔBPM 3–5 % | Rampe, 8 T | Rampe, 16 T | Rampe, 32 T |
| ΔBPM > Grenze | Schnitt | Echo-Out | Hall-Wash oder Loop-Rolle + Echo-Out |
| B deutlich energiereicher (steigern) | Schnitt in den Drop | Rolling: Echo-Out von A auf B's Drop | Double Drop (bei passender Tonart und Tempo) |
| B deutlich ruhiger (beruhigen) | Blend 8 T | Tiefpass auf A, 16 T | Relaxed: Hall-Ausklang von A, B von vorn, 32 T |
| A an der Stelle beatlos (Break) | B hart auf die 1 | Breakdown-Mix | Breakdown-Mix mit Hochpass auf B, der sich öffnet |
| Analyse unsicher (Raster/Tonart) | Echo-Out | Echo-Out | Echo-Out (kein Overlap) |

**Schritt 4, Abwechslung.** Dasselbe Rezept nicht zweimal hintereinander,
nach dem Muster der Übergangsmatrix bei Vande Veire. Bei Gleichstand ein
kleiner Zufall.

**Schritt 5, Begründung anzeigen.** Zum Beispiel: „Drums zuerst · 16 Takte ·
beide instrumental, 8A→9A, +1,2 BPM, Energie gleich".

**Später, Lernen:** Drückst du in einer Blende WEITER oder änderst den
Übergang, ist das ein Minuspunkt für Rezept und Lage. Die Gewichte passen sich
lokal an, ohne Cloud.

---

## 4 · Einbau (klein und testbar)

1. **`klangbild/merkmale.py`** – Energie, Gesang und Drums je Takt, dazu
   Abschnittsetiketten (Intro/Drop/Break/Outro). Gesang und Drums kommen aus
   dem Stem-Vorrat (`stems.vorrat_anlegen` speichert die RMS-Kurven mit).
2. **`klangbild/regie.py`** – `planen(a, b, stil, merkmale) -> Plan`. Der Plan
   enthält Cue-Out-Takt, Cue-In-Takt und Takte sowie die Einstellungen
   (Art „eigen" oder Stem-Art mit allen Bausteinen) und einen Grund. Das
   Regelwerk ist eine Tabelle (Daten), nicht verschachtelte if-Ketten.
3. **`uebergang.backen`** bekommt den Plan statt fester Einstellungen. Ausstieg
   und Einstieg sind dann exakte Takte, der Rest bleibt gleich.
4. **Oberfläche** – oben ein Regler „Mix-Stil" (Manuell / Kurz / Ausgewogen /
   Lang & komplex). In der NÄCHSTER-Zeile steht der Grund. Die Kurven zeigen
   wie heute, was passiert.
5. **Tests** – synthetische Merkmale je Zeile der Tabelle, dazu die
   Echt-Matrix (wie in diesem Schritt) mit Prüfung auf Gesangsüberlappung
   (aus den Stems), Phrasenlage und Pegel.
6. **Hörprobe** durch dich: je Stil 10 Übergänge, bewertet mit 1–5.

Reihenfolge: zuerst 1 und Gesang je Takt (Grundlage), dann 2–4, zuletzt das
Lernen.

---

## 5 · Was bewusst nicht

- **Generative KI** für den Übergang (z. B. DJtransGAN, MusicGen-Füller): Im
  Hörtest war DJtransGAN nicht besser als einfache Regeln. Die Modelle bringen
  Lizenz- und Rechenlast mit.
- **Lernen aus fremden Mixen:** Datensätze wie 1001Tracklists sind nur auf
  Anfrage erhältlich. Die Regeln oben fassen deren Ergebnisse schon zusammen.

## 6 · Voraussetzung, die alles schneller macht

In diesem PC steckt eine **NVIDIA RTX 2070 (8 GB)**. Installiert ist aber
PyTorch nur für die CPU. Demucs braucht auf der CPU ~2,3× Echtzeit, auf der
Grafikkarte typischerweise 20–50× schneller. Dann:
- Der Stem-Vorrat für alle ~330 Titel ist in rund einer Stunde fertig statt in ~2 Tagen.
- „Zu knapp für Stems" verschwindet praktisch, auch nach WEITER.

Nötig dafür: die CUDA-Variante von `torch` und `torchaudio` (Download ~2,5 GB).

---

## Quellen

- [Kim et al., A Computational Analysis of Real-World DJ Mixes (ISMIR 2020)](https://arxiv.org/abs/2008.10267)
- [Vande Veire & De Bie, From raw audio to a seamless mix (EURASIP 2018)](https://asmp-eurasipjournals.springeropen.com/articles/10.1186/s13636-018-0134-8)
- [Zehren et al., Automatic Detection of Cue Points for DJ Mixing](https://arxiv.org/abs/2007.08411)
- [Chen et al., Automatic DJ Transitions with Differentiable Audio Effects and GANs (DJtransGAN)](https://arxiv.org/abs/2110.06525)
- [DJ.Studio, Anatomy of a Great DJ Mix](https://dj.studio/blog/anatomy-great-dj-mix-structure-energy-flow-transition-logic)
- [DJ.Studio Help, Transition Editor](https://help.dj.studio/en/articles/8106059-transition-editor)
- [Mixed In Key, Control the energy level of your DJ sets](https://mixedinkey.com/book/control-the-energy-level-of-your-dj-sets/)
- [MusicTech, djay Pro AI Automix und Neural Mix](https://musictech.com/news/gear/algoriddim-free-dj-software-djay-pro-ai-automix-and-neural-mix)
- [Mixmag, Apple Music AutoMix](https://mixmag.net/read/apple-music-launches-new-automix-feature-that-blends-tracks-together-using-ai-tech)
