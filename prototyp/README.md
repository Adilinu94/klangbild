# Klangbild-Prototyp (Phase 0)

Prüft die zwei Wetten, an denen das Produkt hängt, **bevor** Android gebaut wird
(ADR-011, `../ROADMAP-KLANGBILD.md`):

1. **Phase 0.1** – Ordnet EmbeddingGemma 2 Musik sinnvoll ein (Nachbarn und
   Textsuche)? Mit Blindbewertung, Zufalls-Baseline und Kontrollsatz.
2. **Phase 0.2** – Stimmen BPM, Downbeat und Tonart (ADR-012)?

Dazu kommt die Vorstufe **Phase 0.0**: erst die öffentlichen Musik-Benchmarks
(MAEB) und die Modellkonfiguration klären, dann den teuren Hörtest starten.

## Installation

Die Umgebung liegt **bewusst auf G:** (in `prototyp/.venv`), weil C: wenig Platz
hat. Auch der ~1,5-GB-Modell-Cache landet auf G: – die Pfade sind im venv per
`.pth`-Datei erzwungen (`HF_HOME`, `PIP_CACHE_DIR` → `../.cache`), damit **nichts**
Großes auf C: ankommt, egal wie Python gestartet wird. Ein eigener Override
(`HF_HOME=…` selbst setzen) gewinnt trotzdem.

Venv anlegen (einmalig, auf G:):

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -U pip
```

Leicht (reicht für Analyse und Oberfläche):

```bash
.venv\Scripts\python -m pip install numpy scipy soundfile soxr mutagen
.venv\Scripts\python -m pip install pytest            # für die Tests
```

Schwer (nur für echte Einbettungen und Beats):

```bash
.venv\Scripts\python -m pip install "sentence-transformers>=6.1.0" torch beat-this einops rotary-embedding-torch
```

Getestet mit Python 3.13 auf Windows, **CPU-only torch** (`2.14.1+cpu`, kein
CUDA) – für den Prototyp reicht das völlig und spart ~1,5 GB gegenüber der
CUDA-Variante. Beim ersten `embed` lädt das Modell `google/embeddinggemma-2`
(Apache 2.0, ca. 1,5 GB) nach `../.cache/huggingface`.

> Tests laufen immer im venv: `.venv\Scripts\python -m pytest`. Für alle
> weiteren Befehle unten gilt dasselbe – entweder das venv aktivieren
> (`.venv\Scripts\activate`) oder `.venv\Scripts\python -m klangbild …` nutzen.

## Ablauf

```bash
cd prototyp
python -m pytest                        # 114 Tests, alle ohne Modelldownload

python -m klangbild scan                # Sammlung einlesen und hashen (ADR-013)
python -m klangbild analyze             # Tonart, Lautheit, Energie, Beats
python -m klangbild embed               # Einbettungen (Modell noetig)

# Ohne Modell nur die Mechanik testen (Zufallsvektoren, NIE für das Tor):
python -m klangbild embed --pseudo --limit 20

python -m klangbild neighbors --n 20    # 20 Nachbar-Aufgaben
python -m klangbild baseline  --n 20    # 20 Zufalls-Aufgaben (Vergleichsmassstab)
python -m klangbild text   --queries beispiele/texte-sinnvoll.txt
python -m klangbild unsinn --queries beispiele/texte-unsinn.txt

python -m klangbild serve               # blinde Bewertung im Browser
python -m klangbild report              # Bericht mit Torpruefung

# Phase 0.2 / 0.3 / 0.4 - Tonart schrittweise belegen (Lizenz-Gate ADR-012):
python -m klangbild metronom            # BPM/Beat/Downbeat auf bekannten Metronomen
python -m klangbild konsens             # Tonart-Konsens eigener + freier Modelle (Silber)
python -m klangbild gold                # Tonart gegen FMAK-Expertenlabels (echtes Gold-Tor)
python -m klangbild gold --fmak-remote --limit 20   # FMAK-Audio per Range laden, Stichprobe
python -m klangbild phase08             # skey (trainiertes CNN) gegen denselben Goldsatz
```

Alle Pfade sind überschreibbar: `--bibliothek`, `--datenbank`, `--cache`,
`--ergebnisse`. Nichts verlässt den Rechner; Audio und Modelle stehen in
`.gitignore`.

## Was die Befehle tun

| Befehl | Wirkung |
|---|---|
| `scan` | findet Audiodateien, bildet den **Audio-Hash** (ohne Tag-Blöcke, ADR-013) und legt den Track an. Gleicher Inhalt → keine Neuberechnung, geänderter Inhalt → Analyse und Vektoren werden verworfen. |
| `analyze` | Tonart (Chroma + Key-Profile), Lautheit (eigene BS.1770-4), True Peak, Energie-Kurve, Abschnitte. Beats/Downbeats über Beat This!, falls installiert. |
| `embed` | je Track drei Ausschnitte (Anfang/Mitte/Ende, 20 s, 16 kHz mono), 256 Dimensionen, **re-normalisiert**. Nur Text- und Audio-Encoder geladen (570 M). |
| `neighbors` / `baseline` | bauen die Bewertungsaufgaben (Seed + k Kandidaten). |
| `text` / `unsinn` | Textanfragen als Vektor gegen die Audio-Vektoren, Top-k. |
| `serve` | lokale Oberfläche: Ausgangssong bzw. Anfrage oben, Kandidaten blind darunter, Urteil und Marke „Unfall". |
| `report` | schreibt `ergebnisse/phase0-bericht.md` mit Quoten, Wilson-Intervallen und Torprüfung. Bettet Konsens (0.3), Gold (0.4) und skey (0.8) ein; das skey-Delta wird aus beiden Artefakten **berechnet**, nicht getippt. |

## Die Tore (festgelegt, `../ROADMAP-KLANGBILD.md`)

| Prüfung | Schwelle |
|---|---|
| Nachbarn „Unfall" | ≤ 5 % |
| Nachbarn „passt/geht" | ≥ 10 Prozentpunkte über der Zufalls-Baseline |
| Textsuche „passt/geht" | ≥ 60 % |
| Kontrollsatz Unsinn | ≤ 20 % |
| BPM | ± 4 % (Oktav zählt) bei ≥ 90 % |
| Downbeat | ± 1 Takt bei ≥ 80 % |
| Tonart | exakt ≥ 50 %, inkl. Camelot-Nachbar ≥ 70 % |

Jede Quote wird mit **Wilson-Intervall** berichtet; bei 20 Fällen ist ein Fehler
5 Punkte, deshalb zählt die untere Intervallgrenze.

## Wichtige Warnungen

- **`--pseudo` niemals für das Tor.** Die Zufallsvektoren sind mit
  `modell_version="pseudo"` markiert und erscheinen in `status` getrennt.
- **Nicht `pedalboard`** einbinden (JUCE → GPLv3), und `librosa` nur zum
  Vergleichen außerhalb des Audiopfads. Der Prototyp nutzt `soundfile` + `soxr`,
  damit der Audiopfad später genauso auf Android läuft.
- **Kein stiller Wechsel** von Konfiguration oder Präfix während einer
  Testreihe – sonst ist das Tor nicht mehr aussagekräftig (ADR-015).

## Aufbau

```
klangbild/
  config.py        alle Werte, die ein Tor beeinflussen
  audioio.py       lesen, Raten wandeln, Ausschnitte schneiden
  hashutil.py      Audio-Bereich finden + Hash (ADR-013)
  keyestimate.py   Chroma + Key-Profile, Camelot
  lufs.py          BS.1770-4 + True Peak (spiegelbildlich zu libebur128)
  energy.py        RMS-Kurve, Neuheits-Kurve, Abschnitte
  beats.py         Beat-This!-Anbindung (optional)
  embeddings.py    EmbeddingGemma 2 (570 M, 256 d, re-normalisiert)
  metrics.py       Beat-F1, BPM, Downbeat, Tonart, Wilson-Intervall
  db.py            SQLite-Schema (wie die spätere Android-DB)
  evaluate.py      Aufgaben bauen + Tore auswerten
  blindui.py       Bewertungsoberfläche (nur Standardbibliothek)
  pipeline.py      Kommandozeile
  report.py        Bericht (Konsens 0.3, Gold 0.4, skey 0.8)
tests/             114 Tests
beispiele/         Anfrage-Listen für Textsuche und Kontrollsatz
ergebnisse/        Bericht und Datenbank (nicht im Git)
```
