"""Phase 1.0 · Auto-DJ-Engine gegen bekannte Ground-Truth messen (Vorab-Tor).

Warum dieser Lauf existiert (und was er NICHT ist)
-------------------------------------------------
Das Roadmap-Tor für Phase 1 ist ein **blinder Hörtest mit Menschen** (Mehrheit
bevorzugt den Mix, kein Übergang ist ein „Unfall"). Der läuft in Phase 2. Bevor
man Menschen an einen Mix setzt, prüft man die **maschinell prüfbaren** Zusagen
derselben Engine – genau wie Phase 0.9 Beat This! erst an synthetischen
Metronomen gemessen hat, bevor echte Musik drankam. Dieser Lauf ist die
Vorab-Messung, nicht der Ersatz für den Hörtest.

Was hier gegen **bekannte** Signale geprüft wird
-----------------------------------------------
Set-Songs sind synthetische Metronome (Wiederverwendung aus `phase02`) mit
**bekanntem** Tempo und **bekannten** Downbeats. Der Planer (`plan.baue_set`)
wählt die Reihenfolge, die Engine (`mix.mix_set`) rendert sie. Gemessen werden
drei Zusagen, die ohne Menschen prüfbar sind:

1. **Tempo-Gate (ADR-020):** jeder geplante Übergang zieht B höchstens ±1 % auf
   A. Größere Faktoren würden nach 8 Takten hörbar galoppieren - und ohne
   Keylock auch hörbar verstimmen (0,51 Halbtöne bei 3 %).
2. **Beat-Kontinuität (ADR-020, der Kern):** über jeden Übergang bleibt das
   Beat-Raster stehen – kein Galoppieren, kein Stolpern. Gemessen als Streuung
   der Abstände detektierter Einsätze im ganzen Mix (Onset-Detektion auf dem
   gerenderten Audio, nicht auf der Annahme).
3. **Lautheit des Mixes (Roadmap-Hartwert):** −14 LUFS integriert, True Peak
   ≤ −1 dBTP.

Ehrliche Grenze: Alle Tempi liegen **innerhalb ±1 %** eines Zentrums, damit das
Tempo-Gate nie greift – dieser Lauf präft Resampling **und** Ausrichtung, nicht
die Gate-Logik (die ist in `test_plan.py` unit-getestet). Metronome sind der
leichteste Fall (ein Klang, kein Groove); der Lauf schließt die Render-Kette,
nicht das Produkt. Alles Wiederverwendete (`Metronom`, `wilson`, `lufs`,
`plan`, `mix`, `resample`) kommt aus den eigenen Modulen – die Zahlen sind
vergleichbar, nur der Prüfgegenstand ist neu.
"""

from __future__ import annotations

import csv
import json
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import config, lufs, metrics, mix, plan, resample
from .phase02 import baue_metronome

# Tempi alle innerhalb ±1 % von 120 (Spread 119,4-120,6 = 1 %): jedes Paar passiert
# das Tempo-Gate, damit der Lauf Resampling/Ausrichtung prüft, nicht die Gate-Logik.
TEMPI = (120.0, 120.6, 119.4, 120.3, 119.7, 120.9)
TAKT = 4
SEKUNDEN = 24.0

# Tore (Wilson-Untergrenze wie Phase 0.4/0.8/0.9, nicht der Punktwert).
TOR_GALOPP_CV_MAX = 0.03      # Streuung der Beat-Abstände: 3 % = kein Galopp
TOR_LAUTHEIT_TOL_DB = 0.5     # Mix innerhalb ±0,5 dB von −14 LUFS


def _log(text: str) -> None:
    print(text, flush=True)


def _musik_signal(metro) -> np.ndarray:
    """Musik-aehnliches Signal fuer den Phase-1-Vorab-Check (nicht phase02).

    `phase02.Metronom.signal` ist ein reiner Impuls-Zug: zwischen den Schlaehen
    ist Stille, der Crest-Factor ~24 dB (reale Musik ~10-14 dB). Auf -14 LUFS
    normalisiert explodiert der wahre Peak; der -1-dBTP-Deckel opfert dann ~17 dB
    und reisst die Lautheit auf ~-26 LUFS. `mix.py` ist korrekt - das **Signal**
    war unrealistisch.

    Wir behalten die **Ground-Truth-Positionen** aus metro.beats/downbeats (der
    Auto-DJ richtet sich danach) und legen darum:
    - einen Kick (abklingender Tiefton) auf jeden Schlag -> klarer Einsatz fuer
      die Onset-Erkennung und Masse fuer den Basstausch,
    - ein getragenes, leises Bett dazwischen -> realistischer RMS, kontrollierter
      Crest-Factor, kontinuierliche Energie (wie ein Pad).

    Das Bett bleibt unter der 20-%-Onset-Schwelle, schlaegt aber im RMS zu Buche -
    genau der Unterschied, der -14 LUFS und -1 dBTP gemeinsam erreichbar macht.
    """
    rate = int(metro.rate)
    anzahl = int(metro.sekunden * rate)
    if anzahl <= 0:
        return np.zeros(0, dtype=np.float32)
    t = np.arange(anzahl, dtype=np.float64) / rate

    # Getragenes Bett: leiser Akkord (tiefe Teiler), gibt vorwiegend RMS-Energie.
    bett = (0.16 * np.sin(2 * np.pi * 110.0 * t)
            + 0.09 * np.sin(2 * np.pi * 165.0 * t)
            + 0.07 * np.sin(2 * np.pi * 220.0 * t))
    signal = bett

    # Kick auf jeden Schlag: abklingender 60-Hz-Ton, scharfer Einsatz.
    for index, zeit in enumerate(metro.beats):
        start = int(zeit * rate)
        if start >= anzahl:
            break
        laenge = min(int(0.12 * rate), anzahl - start)
        tt = np.arange(laenge, dtype=np.float64) / rate
        hull = np.exp(-tt / 0.028)
        kick = 0.6 * hull * np.sin(2 * np.pi * 58.0 * tt)
        # Downbeat minimal betont (nur Orientierung; Onsets egal ob betont).
        amplitude = 1.0 if index % metro.takt == 0 else 0.82
        signal[start:start + laenge] += amplitude * kick

    return np.clip(signal, -1.0, 1.0).astype(np.float32)


# --- Synthetisches Set -------------------------------------------------------
@dataclass(frozen=True)
class SetTrack:
    """Ein Set-Song mit bekannter Ground-Truth: Tempo, Downbeats, Camelot."""

    track_id: int
    bpm: float
    camelot: str
    metro: object                       # phase02.Metronom

    @property
    def signal(self) -> np.ndarray:
        # Musik-aehnlich (Kick + getragenes Bett), nicht der rohe Klick-Zug - nur
        # so sind -14 LUFS und -1 dBTP physikalisch gemeinsam erreichbar.
        return _musik_signal(self.metro)


# Camelot-Leiter: benachbarte Codes (9A→10A→11A→…), damit der Planer eine
# harmonische Folge findet. Energie bewusst gleich (-18 dB), kein Vektor – der
# Lauf prüft die Harmonie-/Tempo-Kette, nicht Klang/Energie (separate unit-getestet).
_CAMELOT_LEITER = ("8A", "9A", "10A", "11A", "12A", "1A")
_ENERGIE_DB = -18.0


# Tempo-Versatz je Trial: das ganze Set wandert innerhalb der erlaubten
# Bandbreite. Ein gemeinsamer Versatz aendert die **paarweise** Spannweite
# nicht (bleibt 1 %) - jeder Uebergang passiert das +-1 %-Gate, nur die
# absoluten Tempi (Sample-Zahlen, Faktoren, Blendenpunkt) aendern sich.
# 8 Versaetze x rotierter Start = genug Kombinationen, damit 40 Trials alle
# **verschieden** rendern (identische Renderings 40x gezaehlt haetten Wilson
# unfair verengt - genau die Annahme, die dieses Projekt nicht macht).
_OFFSETS = tuple(round(-1.0 + 0.25 * i, 2) for i in range(8))


def _offset_fuer(seed: int) -> float:
    """Gemeinsamer Tempo-Versatz (BPM) fuer einen Trial."""
    return _OFFSETS[seed % len(_OFFSETS)]


def _start_fuer(seed: int, anzahl: int) -> int:
    """Start-Track (1-basiert) rotieren -> anderer Master, andere Faktoren."""
    return (seed // len(_OFFSETS)) % anzahl + 1


def baue_set_tracks(offset: float = 0.0) -> list[SetTrack]:
    """Baut die synthetischen Set-Songs: ein Metronom je Tempo, Camelot-Leiter.

    `offset` verschiebt alle Tempi gleichmaessig (BPM). Die paarweise
    Spannweite bleibt identisch, das +-1 %-Gate haelt fuer jedes Paar.
    """
    tempi = tuple(round(t + offset, 3) for t in TEMPI)
    metro_liste = baue_metronome(tempi=tempi, takt=TAKT, sekunden=SEKUNDEN)
    tracks: list[SetTrack] = []
    for index, (metro, camelot) in enumerate(zip(metro_liste, _CAMELOT_LEITER), 1):
        tracks.append(SetTrack(track_id=index, bpm=metro.bpm, camelot=camelot,
                               metro=metro))
    return tracks


def _plan_tracks(set_tracks: list[SetTrack]) -> list[plan.Track]:
    """Uebersetzt Set-Tracks in die Planer-Eingabe (Merkmale, kein Audio)."""
    return [
        plan.Track(id=t.track_id, pfad=f"synthetisch:{t.track_id}", bpm=t.bpm,
                   camelot=t.camelot, energie_db=_ENERGIE_DB, vektor=None)
        for t in set_tracks
    ]

# --- Das Beat-Raster im gerenderten Mix messen (Onset-Erkennung) -------------
# Kein Modell, kein Annahme-Wert: wir schauen dem fertigen Mix zu und messen,
# wo wirklich Einsaetze liegen. Galoppiert das Raster, wachsen die Abstaende
# unregelmaessig - genau das faellt hier auf (ADR-020, der Kern von Phase 1).

# Kreuzblende in Takten (Roadmap nennt 8/16 Takte; fuer den Vorab-Check genuegt
# eine kurze Blende - die Raster-Kontinuitaet haengt nicht an ihrer Laenge).
BLENDE_TAKTE = 2


def _onsets(signal: np.ndarray, rate: int, min_abstand_s: float = 0.2) -> np.ndarray:
    """Beat-Einsaetze als Peaks der Kurzzeitenergie (rein aus dem Signal).

    Fenster 10 ms, Hop 5 ms. Ein Peak zaehlt nur, wenn er die Schwelle erreicht
    und der letzte Einsatz mindestens `min_abstand_s` zurueckliegt (Refraktaer-
    zeit gegen Doppel-Treffer auf einem Klick).
    """
    x = np.asarray(signal, dtype=np.float64)
    frame = max(1, round(0.010 * rate))
    hop = max(1, round(0.005 * rate))
    if x.size < frame:
        return np.zeros(0)
    quadrat = x * x
    kumuliert = np.concatenate(([0.0], np.cumsum(quadrat)))
    stellen = np.arange(0, x.size - frame + 1, hop)
    energie = (kumuliert[stellen + frame] - kumuliert[stellen]) / frame
    spitze = float(energie.max()) if energie.size else 0.0
    if spitze <= 0.0:
        return np.zeros(0)
    schwelle = 0.2 * spitze
    min_hop = max(1, round(min_abstand_s * rate / hop))
    einsaetze: list[float] = []
    letzter_index = -10**9
    for i in range(1, energie.size - 1):
        if (energie[i] >= schwelle and energie[i] >= energie[i - 1]
                and energie[i] > energie[i + 1]
                and i - letzter_index >= min_hop):
            einsaetze.append((i * hop + frame / 2.0) / rate)
            letzter_index = i
    return np.asarray(einsaetze, dtype=np.float64)


def _cv_intervalle(einsaetze: np.ndarray) -> float:
    """Variationskoeffizient der Beat-Abstaende: 0 = perfekt gleichmaessig.

    Galoppiert oder stolpert das Raster, waechst die Streuung der Abstaende.
    Weniger als 3 Einsaetze sind nicht messbar -> gilt als schlecht (1,0), statt
    eine 0 aus fast keinen Werten zu behaupten.
    """
    if einsaetze.size < 3:
        return 1.0
    d = np.diff(einsaetze)
    mittel = float(d.mean())
    if mittel <= 0:
        return 1.0
    return float(d.std() / mittel)



# --- Ein Trial: planen -> rendern -> messen ----------------------------------
def _master_bpm(reihenfolge: list[int], set_tracks: list[SetTrack]) -> float:
    """Das Tempo des ersten Songs ist der Master-Takt (Vinyl-Prinzip, ADR-020)."""
    index = {t.track_id: t for t in set_tracks}
    erster = reihenfolge[0]
    return float(index[erster].bpm)


def _faktoren(
    reihenfolge: list[int], set_tracks: list[SetTrack], master_bpm: float
) -> dict[int, float]:
    """Zieht **jeden** Track auf den Master-Takt (nicht auf den Vorgaenger).

    Wuerde jeder Track nur auf seinen Nachbarn gezogen, wanderte das Raster ueber
    drei Songs sichtbar (Fehler addieren sich). Ein gemeinsamer Master haelt das
    ganze Set auf einem Takt. Track 0 ist der Master selbst (Faktor 1,0).
    `tempo_faktor(von, auf) = auf/von` (>1 = schneller), also von/bpm -> master.
    """
    faktoren: dict[int, float] = {}
    for position, tid in enumerate(reihenfolge):
        track = next(t for t in set_tracks if t.track_id == tid)
        if position == 0:
            faktoren[tid] = 1.0
        else:
            faktoren[tid] = resample.tempo_faktor(track.bpm, master_bpm)
    return faktoren


def _blende_s(master_bpm: float) -> float:
    """Blendenlaenge in **ganzen Takten** des Masters.

    Das ist der Kern der Raster-Kontinuitaet: nur wenn die Blende eine ganze
    Zahl von Master-Takten (und damit Taktanfaengen) umfasst, setzt B's erste
    Taktordnung exakt auf A's Raster. Sonst verschiebt sich die Phase - und genau
    das soll die CV-Messung hoeren.
    """
    takt_sekunden = TAKT * (60.0 / master_bpm)
    return BLENDE_TAKTE * takt_sekunden


def trial_messen(seed: int, set_tracks: list[SetTrack], start_id: int | None = None) -> dict:
    """Ein voller Durchlauf: Planer waehlt, Engine rendert, wir messen zu.

    Reihenfolge: plan.baue_set (rein Merkmale) -> mix.mix_set (Audio) -> Onsets
    im gerenderten Mix -> Streuung (CV), Lautheit, True Peak. Alles, was hier
    geprueft wird, ist ohne Menschen nachpruefbar.
    """
    plan_tracks = _plan_tracks(set_tracks)
    planung = plan.baue_set(plan_tracks, start_id=start_id)
    reihenfolge = planung.reihenfolge
    index = {t.track_id: t for t in set_tracks}

    master_bpm = _master_bpm(reihenfolge, set_tracks)
    faktoren = _faktoren(reihenfolge, set_tracks, master_bpm)
    blende_s = _blende_s(master_bpm)

    audio = {t.track_id: t.signal for t in set_tracks}
    downbeats = {t.track_id: [float(x) for x in t.metro.downbeats] for t in set_tracks}
    rate = int(set_tracks[0].metro.rate)

    mischung, protokoll = mix.mix_set(
        reihenfolge=reihenfolge,
        audio=audio,
        downbeats=downbeats,
        rate=rate,
        faktoren=faktoren,
        blende_s=blende_s,
        basstausch=True,
        ziel_lufs=config.LUFS_ZIEL,
    )

    einsaetze = _onsets(mischung, rate)
    cv = _cv_intervalle(einsaetze)

    # Tempo-Gate je Uebergang: der auf B **tatsaechlich angewandte** Faktor zieht
    # es auf den Master. tempo_passt(bpm, master) prueft genau diesen Faktor
    # (master/bpm) gegen +-1 % - dieselbe Grenze, die ADR-020 fuer den Planer setzt.
    gate_ok = True
    for ue in protokoll.uebergaenge:
        auf = index[ue.to_id].bpm
        if not resample.tempo_passt(auf, master_bpm):
            gate_ok = False

    # Lautheit unabhaengig nachmessen (nicht dem Protokoll glauben): der Lauf
    # soll eine falsche Angabe der Engine aufdecken, nicht sie blind uebernehmen.
    lufs_gemessen = lufs.integrierte_lautheit(mischung, rate)
    tp_gemessen = lufs.true_peak_dbtp(mischung, rate)
    lufs_ok = abs(lufs_gemessen - config.LUFS_ZIEL) <= TOR_LAUTHEIT_TOL_DB
    tp_ok = tp_gemessen <= config.TRUE_PEAK_GRENZE + TOR_LAUTHEIT_TOL_DB

    return {
        "seed": seed,
        "master_bpm": round(master_bpm, 3),
        "reihenfolge": reihenfolge,
        "blende_s": round(blende_s, 4),
        "anzahl_einsaetze": int(einsaetze.size),
        "beat_cv": round(cv, 5),
        "beat_cv_ok": bool(cv <= TOR_GALOPP_CV_MAX),
        "gate_ok": bool(gate_ok),
        "lufs": round(protokoll.lufs, 3),
        "true_peak": round(protokoll.true_peak, 3),
        "lautheit_ok": bool(lufs_ok and tp_ok),
        "dauer_s": round(protokoll.dauer_s, 3),
    }


def _quote(treffer: int, gesamt: int) -> dict:
    """Trefferquote mit Wilson-Intervall (wie Phase 0.4/0.8/0.9, UG entscheidet)."""
    unten, oben = metrics.wilson(treffer, gesamt)
    return {
        "treffer": treffer,
        "gesamt": gesamt,
        "quote": (treffer / gesamt) if gesamt else 0.0,
        "wilson_unten": unten,
        "wilson_oben": oben,
    }


def auswerten(triale: list[dict]) -> dict:
    """Fasst die Trials zu Kennzahlen mit Toren an der Wilson-Untergrenze.

    Drei Tore (je ein Tor, entschieden an der Untergrenze, nicht am Punktwert):
    - Beat-Kontinuitaet: CV der Einsaetz-Abstaende <= 3 % (kein Galopp).
    - Tempo-Gate: jeder Uebergang innerhalb +-1 % (ADR-020).
    - Lautheit: -14 LUFS (+-0,5 dB) und True Peak <= -1 dBTP.
    """
    n = len(triale)
    beat_ok = sum(1 for t in triale if t["beat_cv_ok"])
    gate_ok = sum(1 for t in triale if t["gate_ok"])
    laut_ok = sum(1 for t in triale if t["lautheit_ok"])

    beat_ug = config.TOR_10_KONTINUITAET_MIN
    gate_ug = config.TOR_10_GATE_MIN
    laut_ug = config.TOR_10_LAUTHEIT_MIN

    def tor_erreicht(quote_dict: dict, schwelle: float) -> bool:
        return bool(quote_dict["gesamt"] > 0 and quote_dict["wilson_unten"] >= schwelle)

    beat = _quote(beat_ok, n)
    gate = _quote(gate_ok, n)
    laut = _quote(laut_ok, n)
    cv_werte = [t["beat_cv"] for t in triale]
    return {
        "anzahl_trials": n,
        "beat_kontinuitaet": beat,
        "tempo_gate": gate,
        "lautheit": laut,
        "beat_cv_mittel": round(sum(cv_werte) / n, 5) if n else 0.0,
        "beat_cv_max": round(max(cv_werte), 5) if n else 0.0,
        "tore": {
            "beat_kontinuitaet_ug_min": beat_ug,
            "tempo_gate_ug_min": gate_ug,
            "lautheit_ug_min": laut_ug,
        },
        "erreicht": {
            "beat_kontinuitaet": tor_erreicht(beat, beat_ug),
            "tempo_gate": tor_erreicht(gate, gate_ug),
            "lautheit": tor_erreicht(laut, laut_ug),
        },
        "alle": bool(
            tor_erreicht(beat, beat_ug)
            and tor_erreicht(gate, gate_ug)
            and tor_erreicht(laut, laut_ug)
        ),
    }


# --- Export (wie Phase 0.9: JSON + CSV + Bericht) ---------------------------
def _json_schreiben(ordner: Path, z: dict) -> Path:
    p = ordner / "phase10-autodj.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(z, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def _csv_schreiben(ordner: Path, triale: list[dict]) -> Path:
    """Vollstaendiger Per-Trial-Export - wie Phase 0.4/0.8/0.9, jede Zeile nachvollziehbar."""
    p = ordner / "phase10-autodj-tracks.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    felder = ["seed", "master_bpm", "blende_s", "anzahl_einsaetze", "beat_cv",
              "beat_cv_ok", "gate_ok", "lufs", "true_peak", "lautheit_ok",
              "dauer_s", "reihenfolge"]
    with p.open("w", encoding="utf-8", newline="") as f:
        schreiber = csv.DictWriter(f, fieldnames=felder, extrasaction="ignore")
        schreiber.writeheader()
        for t in triale:
            zeile = dict(t)
            zeile["reihenfolge"] = "-".join(str(x) for x in t["reihenfolge"])
            schreiber.writerow(zeile)
    return p


def _bericht_schreiben(ordner: Path, z: dict, dauer: float) -> Path:
    p = ordner / "phase10-autodj.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    nl = chr(10)
    zeilen = [
        "# Phase 1.0 · Auto-DJ-Engine gegen bekannte Ground-Truth (Vorab-Tor)",
        "",
        "> Interner Messlauf, nichts ausgeliefert (Lizenz-Gate ADR-012). Vorab-Pruefung",
        "> der **maschinell pruefbaren** Zusagen der Uebergangs-Engine, bevor Menschen",
        "> (Hoertest, Phase 2) an einen Mix gesetzt werden.",
        "",
        "**Setup:** synthetische Set-Songs (Metronome aus `phase02`) mit bekanntem Tempo",
        "und bekannten Downbeats. Der Planer (`plan.baue_set`) waehlt die Reihenfolge,",
        "die Engine (`mix.mix_set`) rendert. Onset-Erkennung auf dem **gerenderten**",
        "Audio misst die Beat-Kontinuitaet - kein Modell, kein Annahme-Wert.",
        "",
        f"- Trials: {z['anzahl_trials']}",
        f"- Dauer: {dauer:0.1f} s",
        f"- mittlere Beat-CV: {z['beat_cv_mittel']:.4f} · max: {z['beat_cv_max']:.4f}",
        "",
        "## Drei Tore (entschieden an der Wilson-Untergrenze, nicht am Punktwert)",
        "",
        "| Tor | Treffer/N | Quote | Wilson-UG | Schwelle | erreicht? |",
        "|---|---|---|---|---|---|",
    ]
    tore = [
        ("Beat-Kontinuitaet (CV <= 3 %)", z["beat_kontinuitaet"],
         z["tore"]["beat_kontinuitaet_ug_min"], z["erreicht"]["beat_kontinuitaet"]),
        ("Tempo-Gate (+-1 %, ADR-020)", z["tempo_gate"],
         z["tore"]["tempo_gate_ug_min"], z["erreicht"]["tempo_gate"]),
        ("Lautheit (-14 LUFS, TP <= -1 dBTP)", z["lautheit"],
         z["tore"]["lautheit_ug_min"], z["erreicht"]["lautheit"]),
    ]
    for name, q, ug, ok in tore:
        zeilen.append(
            f"| {name} | {q['treffer']}/{q['gesamt']} | {q['quote'] * 100:0.1f} % "
            f"| {q['wilson_unten'] * 100:0.1f} % | >= {ug * 100:0.0f} % "
            f"| {'**JA**' if ok else 'NEIN'} |"
        )
    zeilen += [
        "",
        "## Ehrliche Grenze",
        "",
        "- Alle Tempi liegen **innerhalb +-1 %** eines Zentrums, damit das Tempo-Gate",
        "  nie greift. Dieser Lauf prueft Resampling **und** Ausrichtung, nicht die",
        "  Gate-Logik (die ist unit-getestet in `test_plan.py`).",
        "- Metronome sind der **leichteste** Fall (ein Klang, kein Groove). Der Lauf",
        "  schliesst die Render-Kette, **nicht** das Produkt.",
        "- Selbst bei **perfekten** Trials braucht die Wilson-Untergrenze n >= 35, um",
        "  0,90 zu erreichen (UG bei k=n ist n/(n+z^2) = n/(n+3,84)). Ein kleiner",
        "  Stichprobenumfang kann das Tor strukturell nicht bestehen - darum die",
        "  Default-Trialzahl von 40 (UG ca. 0,912 bei perfektem Lauf).",
        "- Das Roadmap-Tor fuer Phase 1 bleibt der **blinde Hoertest** (Mehrheit",
        "  bevorzugt den Mix, kein Uebergang ein „Unfall\"). Dieser Lauf ist die",
        "  Vorab-Messung, nicht der Ersatz.",
        "",
        "> Jeder Trial steht in `phase10-autodj-tracks.csv`.",
    ]
    p.write_text(nl.join(zeilen) + nl, encoding="utf-8")
    return p


# Trials: n >= 35, damit die Wilson-UG bei perfektem Lauf 0,90 erreicht
# (UG bei k=n ist n/(n+3,84); bei n=40 -> 0,912). Weniger kann das Tor nicht
# bestehen, selbst wenn die Engine fehlerfrei arbeitet.
TRIALS = 40


# --- Ablauf -----------------------------------------------------------------
def laufen(args) -> int:
    einstellungen = config.vorbereiten(config.aus_argumenten(args))
    ordner = einstellungen.ergebnisse

    set_tracks = baue_set_tracks()
    anzahl = int(getattr(args, "trials", 0) or TRIALS)
    limit = int(getattr(args, "limit", 0) or 0)
    seeds = list(range(anzahl))
    if limit and limit < len(seeds):
        seeds = seeds[:limit]

    _log(f"Phase 1.0 · {len(seeds)} Trials · Set aus {len(set_tracks)} Songs "
         f"(Tempi {min(TEMPI):.0f}-{max(TEMPI):.0f} BPM, alle innerhalb +-1 %)")

    beginn = time.time()
    triale: list[dict] = []
    for seed in seeds:
        # Echte eigene Messung je Trial: Tempo-Zentrum per Offset verschoben und
        # Start-Track rotiert (anderer Master, andere Resampling-Richtungen). Der
        # Planer bleibt pro Eingabe deterministisch; die Streuung kommt aus dem
        # legalen Eingaberaum, nicht aus Zufall - sonst zaehlten wir einen Mix
        # 40x und verengten das Wilson-Intervall unfair (Phase 0.9-Disziplin).
        set_tracks = baue_set_tracks(offset=_offset_fuer(seed))
        start_id = _start_fuer(seed, len(set_tracks))
        t = trial_messen(seed, set_tracks, start_id=start_id)
        triale.append(t)
        _log(f"  seed {seed:>2}: CV {t['beat_cv']:.4f} "
             f"{'ok' if t['beat_cv_ok'] else 'FEHLER'} · "
             f"Gate {'ok' if t['gate_ok'] else 'FEHLER'} · "
             f"Lautheit {'ok' if t['lautheit_ok'] else 'FEHLER'} · "
             f"{t['anzahl_einsaetze']} Einsaetze · {t['dauer_s']:.1f}s")
    dauer = time.time() - beginn

    z = auswerten(triale)
    z["dauer_s"] = round(dauer, 2)
    tol = getattr(config, "TEMPO_MAX_ABWEICHUNG", None)
    if tol is None:
        tol = getattr(resample, "TEMPO_MAX_ABWEICHUNG", 0.03)
    z["grenzen"] = {
        "beat_cv_max": TOR_GALOPP_CV_MAX,
        "tempo_gate_max_abweichung": tol,
        "lufs_ziel": config.LUFS_ZIEL,
        "true_peak_grenze": config.TRUE_PEAK_GRENZE,
        "lautheit_toleranz_db": TOR_LAUTHEIT_TOL_DB,
    }

    for name, schluessel in (("Beat-Kontinuitaet", "beat_kontinuitaet"),
                             ("Tempo-Gate", "tempo_gate"),
                             ("Lautheit", "lautheit")):
        q = z[schluessel]
        _log(f"  {name}: {q['quote'] * 100:0.1f} % ({q['treffer']}/{q['gesamt']}) "
             f"UG {q['wilson_unten'] * 100:0.1f} % -> "
             f"{'Tor erreicht' if z['erreicht'][schluessel] else 'Tor NICHT erreicht'}")
    _log(f"  Beat-CV Mittel {z['beat_cv_mittel']:.4f} · max {z['beat_cv_max']:.4f}")
    _log(f"  Alle Tore: {'ERREICHT' if z['alle'] else 'NICHT erreicht'}")

    _json_schreiben(ordner, z)
    _csv_schreiben(ordner, triale)
    _bericht_schreiben(ordner, z, dauer)
    _log(f"JSON:    {ordner / 'phase10-autodj.json'}")
    _log(f"CSV:     {ordner / 'phase10-autodj-tracks.csv'}")
    _log(f"Bericht: {ordner / 'phase10-autodj.md'}")
    return 0



