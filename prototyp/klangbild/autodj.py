"""Phase 1.1 – Auto-DJ-Hörtest: echter Mix aus der eigenen Bibliothek.

Phase 1.0 (`phase10`) hat die Engine gegen **synthetische Metronome** gemessen:
Beat-Kontinuitaet, Tempo-Gate, Lautheit. Das war noetig, weil Ground-Truth ohne
Menschen nachpruefbar sein muss. Es belegt aber nicht, dass die Engine an
**echten Songs** einen hörbaren Mix baut – Metronome haben keine Einsaetze,
keine Uebergaenge, keine Energie-Reise.

Dieses Modul rendert genau diesen Hörtest: es nimmt analysierte Tracks aus der
Datenbank (BPM, Camelot, Downbeats, Energie – von `analyze`/Beat This!/skey),
lässt den **gleichen** Planer (`plan.baue_set`) und die **gleiche** Engine
(`mix.mix_set`) laufen wie Phase 1.0 und schreibt eine echte Mix-Datei plus
Protokoll. Wieder nur Wiederverwendetes – kein zweiter Mix-Algorithmus.

Aufruf:
    python -m klangbild mix --start 12 --laenge 6
    python -m klangbild mix --laenge 5 --aus mix.wav

Tempo-Gate (ADR-014): der Planer laesst nur Songs innerhalb ±3 % des Start-Tempos
zu. Echte Bibliotheken streuen ihre Tempi, deshalb wird als Master-Takt
standardmäßig der größte Tempo-Cluster gewaehlt (laengstes moegliches Set), nicht
einfach der erste Track. `--start <id>` hebt das auf.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np

from . import audioio, config, db, mix, plan, resample

try:
    import soundfile as sf
except Exception:  # noqa: BLE001 - Schreiben ist optional; Messen laeuft auch so
    sf = None  # type: ignore[assignment]


# --- Daten laden --------------------------------------------------------------

def _energie_db(energie_json) -> float | None:
    """Mittlere Energie (dBFS) aus der gespeicherten RMS-Kurve.

    Die Kurve ist eine Liste von [zeit_s, db]-Paaren (energy.rms_kurve). Der
    Planer erwartet einen einzigen mittleren Wert je Track (energie_db). Fehlt
    die Kurve, ist es None – fehlendes Wissen wirkt nicht wie Abneigung.
    """
    try:
        roh = json.loads(energie_json) if isinstance(energie_json, str) else (energie_json or [])
        werte = [float(v) for _, v in roh]
        return sum(werte) / len(werte) if werte else None
    except Exception:  # noqa: BLE001
        return None


def _downbeats(roh) -> list[float]:
    try:
        return [float(x) for x in (json.loads(roh) if isinstance(roh, str) else (roh or []))]
    except Exception:  # noqa: BLE001
        return []


def lade_tracks(
    conn, version: str, *, start: int | None, laenge: int
) -> tuple[list[plan.Track], dict[int, list[float]], dict[int, str], int | None]:
    """Liest analysierte Tracks und waehlt den Master-Takt (groesster Tempo-Cluster).

    Gibt (plan_tracks, downbeats_je_id, pfad_je_id, start_id) zurueck. Nur Tracks
    mit BPM und mindestens einem Downbeat sind mischbar; der Rest faellt heraus,
    bevor geplant wird – der Planer soll nicht auf halben Merkmalen entscheiden.
    """
    zeilen = [
        z for z in db.features_laden(conn, version)
        if z["bpm"] and _downbeats(z["downbeats_json"])
    ]
    if not zeilen:
        return [], {}, {}, None

    # Tempo-Cluster auf ganzes BPM gerundet: der modal-haufigste Wert ist der
    # Master-Takt, weil er die meisten ±3 %-Nachbarn anzieht (laengstes Set).
    if start is not None and any(int(z["id"]) == start for z in zeilen):
        start_id = int(start)
    else:
        haeufigstes_bpm, _ = Counter(round(float(z["bpm"])) for z in zeilen).most_common(1)[0]
        start_id = next(int(z["id"]) for z in zeilen if round(float(z["bpm"])) == haeufigstes_bpm)

    tracks: list[plan.Track] = []
    downbeats: dict[int, list[float]] = {}
    pfade: dict[int, str] = {}
    for z in zeilen:
        tid = int(z["id"])
        tracks.append(
            plan.Track(
                id=tid,
                pfad=z["pfad"],
                bpm=float(z["bpm"]),
                camelot=z["key_camelot"],
                energie_db=_energie_db(z["energie_json"]),
                vektor=None,
            )
        )
        downbeats[tid] = _downbeats(z["downbeats_json"])
        pfade[tid] = z["pfad"]
    return tracks, downbeats, pfade, start_id


def lade_audio(
    reihenfolge: list[int], pfade: dict[int, str], downbeats: dict[int, list[float]], rate: int
) -> tuple[dict[int, np.ndarray], dict[int, list[float]]]:
    """Decodiert die Songs der Reihenfolge als Stereo@rate und liefert Audio+Downbeats.

    Ein Track, der nicht decodierbar ist, wird uebersprungen (statt das Set zu
    killen) – `mix.mix_set` degradiert dann ehrlich. Die Rueckgabe enthaelt nur
    die Tracks, die wirklich da sind.
    """
    audio: dict[int, np.ndarray] = {}
    beats_out: dict[int, list[float]] = {}
    for tid in reihenfolge:
        pfad = pfade.get(tid)
        if not pfad:
            continue
        try:
            a = audioio.decodieren_stereo(pfad, rate)
        except Exception:  # noqa: BLE001,S112 - eine datei darf einzeln scheitern
            continue
        if a.daten.size == 0:
            continue
        audio[tid] = np.asarray(a.daten, dtype=np.float32)
        beats_out[tid] = downbeats.get(tid, [])
    return audio, beats_out


# --- Plan -> Engine-Bruecke (identisch zu Phase 1.0, nur echte Tracks) --------
# Kein zweiter Mix-Algorithmus: faktoren/blende werden exakt wie in
# phase10._faktoren/_blende_s gerechnet, damit Plan und Mix dasselbe Raster
# treffen (ADR-014). Der einzige Unterschied: master = Start-Song statt Track 0.

TAKT = 4          # 4/4-Takt: die Blende umfasst ganze Takte (Taktanfaenge)
BLENDE_TAKTE = 8  # 8 Takte = eine Phrase. Klingt nach DJ (ADR-014); die 2 Takte
                  # von phase10 waren der Mess-Metronom-Wert, kein Hoerwert.
PHRASEN_TAKTE = 8  # Ausstieg am Phrasenanfang: jeder 8. Downbeat ist ein neuer
                   # Takt-Block. Verhindert den Ausstieg im Fade-out/Ausklang.


def _master_bpm(reihenfolge: list[int], index: dict[int, plan.Track]) -> float:
    """Das Tempo des ersten Songs ist der Master-Takt (Vinyl-Prinzip, ADR-014)."""
    return float(index[reihenfolge[0]].bpm)


def _faktoren(
    reihenfolge: list[int], index: dict[int, plan.Track], master_bpm: float
) -> dict[int, float]:
    """Zieht **jeden** Track auf den Master-Takt (nicht auf den Vorgaenger).

    Wie phase10._faktoren: ein gemeinsamer Master haelt das ganze Set auf einem
    Takt; waere jeder nur auf seinen Nachbarn gezogen, wanderte das Raster ueber
    drei Songs sichtbar. Der erste Song ist der Master (Faktor 1,0).
    """
    faktoren: dict[int, float] = {}
    for position, tid in enumerate(reihenfolge):
        if position == 0:
            faktoren[tid] = 1.0
        else:
            faktoren[tid] = resample.tempo_faktor(index[tid].bpm, master_bpm)
    return faktoren


def _blende_s(master_bpm: float) -> float:
    """Blendenlaenge in **ganzen Takten** des Masters (wie phase10._blende_s)."""
    takt_sekunden = TAKT * (60.0 / master_bpm)
    return BLENDE_TAKTE * takt_sekunden


def _protokoll_schreiben(ziel: Path, protokoll, planung, index, pfade,
                         master_bpm, blende_s, faktoren) -> None:
    """Schreibt das nachvollziehbare Protokoll (Songs, Uebergaenge, Lautheit)."""
    gruende = {(u.from_id, u.to_id): u for u in planung.uebergaenge}
    daten = {
        "master_bpm": round(master_bpm, 3),
        "blende_s": round(blende_s, 4),
        "reihenfolge": [
            {
                "id": tid,
                "pfad": pfade.get(tid),
                "bpm": index[tid].bpm,
                "camelot": index[tid].camelot,
                "tempo_faktor": round(float(faktoren.get(tid, 1.0)), 5),
            }
            for tid in protokoll.reihenfolge
        ],
        "uebergaenge": [
            {
                "from_id": u.from_id,
                "to_id": u.to_id,
                "a_ausstieg_s": round(u.a_ausstieg_s, 3),
                "b_einstieg_s": round(u.b_einstieg_s, 3),
                "blende_s": round(u.blende_s, 3),
                "tempo_faktor": round(u.tempo_faktor, 5),
                "grund": gruende[(u.from_id, u.to_id)].grund
                if (u.from_id, u.to_id) in gruende else "",
            }
            for u in protokoll.uebergaenge
        ],
        "uebersprungen": list(planung.uebersprungen),
        "lufs": round(protokoll.lufs, 3),
        "true_peak": round(protokoll.true_peak, 3),
        "dauer_s": round(protokoll.dauer_s, 3),
    }
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text(json.dumps(daten, indent=2, ensure_ascii=False), encoding="utf-8")


def _render(reihenfolge, index, audio, beats):
    """Auto-DJ-Render einer Reihenfolge: Master-Takt, Faktoren, Phrasen-Blende."""
    master_bpm = _master_bpm(reihenfolge, index)
    faktoren = _faktoren(reihenfolge, index, master_bpm)
    blende_s = _blende_s(master_bpm)
    mischung, protokoll = mix.mix_set(
        reihenfolge=reihenfolge,
        audio=audio,
        downbeats=beats,
        rate=config.ABTASTRATE_HOERTEST,
        faktoren=faktoren,
        blende_s=blende_s,
        basstausch=True,
        ziel_lufs=config.LUFS_ZIEL,
        phrasen_takte=PHRASEN_TAKTE,
    )
    return mischung, protokoll, master_bpm, blende_s, faktoren


def laufen(args) -> int:
    """Rendert einen echten Hoertest-Mix aus der eigenen Bibliothek.

    plan.baue_set waehlt die Reihenfolge (rein Merkmale), mix.mix_set rendert
    (dieselbe Engine wie Phase 1.0). Geschrieben werden eine WAV-Datei und ein
    JSON-Protokoll. Rueckgabe: 0 = ok, 2 = keine mischbaren Tracks, 3 = Set zu
    kurz fuer einen Uebergang.
    """
    einstellungen = config.vorbereiten(config.aus_argumenten(args))
    conn = db.verbinden(einstellungen.datenbank)
    try:
        start = getattr(args, "start", None)
        laenge = int(getattr(args, "laenge", 0) or 0)
        tracks, downbeats, pfade, start_id = lade_tracks(
            conn, einstellungen.analyse_version, start=start, laenge=laenge
        )
        if not tracks:
            print("Keine mischbaren Tracks (brauche BPM + Downbeat). "
                  "Erst 'analyze' laufen lassen.")
            return 2

        index = {t.id: t for t in tracks}
        planung = plan.baue_set(tracks, start_id=start_id, laenge=laenge)
        reihenfolge = planung.reihenfolge
        if len(reihenfolge) < 2:
            print(f"Set zu kurz ({len(reihenfolge)} Song(s)) - kein Uebergang "
                  "innerhalb des Tempo-Gates moeglich.")
            return 3

        # Hoertest in Originalqualitaet: Stereo 44,1 kHz. Downbeats sind Sekunden,
        # also ratenunabhaengig.
        audio, beats = lade_audio(reihenfolge, pfade, downbeats,
                                  config.ABTASTRATE_HOERTEST)
        mischung, protokoll, master_bpm, blende_s, faktoren = _render(
            reihenfolge, index, audio, beats)

        aus = getattr(args, "aus", None)
        ziel = Path(aus) if aus else (einstellungen.ergebnisse / "hoertest-mix.wav")
        if sf is not None and mischung.size:
            ziel.parent.mkdir(parents=True, exist_ok=True)
            sf.write(str(ziel), mischung, config.ABTASTRATE_HOERTEST)
            print(f"Mix geschrieben: {ziel}  ({protokoll.dauer_s:.1f}s, "
                  f"{protokoll.lufs:.1f} LUFS, TP {protokoll.true_peak:.2f} dBTP)")
        elif sf is None:
            print("soundfile fehlt - nur Protokoll geschrieben.")

        _protokoll_schreiben(ziel.with_suffix(".json"), protokoll, planung, index,
                             pfade, master_bpm, blende_s, faktoren)
        print(f"Protokoll: {ziel.with_suffix('.json')}  "
              f"({len(reihenfolge)} Songs, Master {master_bpm:.1f} BPM)")
        return 0
    finally:
        conn.close()


# --- Blinder Hoertest: Auto-DJ gegen Shuffle (ROADMAP Phase 1) -----------------

# Kontrolle = was ein normaler Player tut: Zufallsreihenfolge, Ende->Anfang,
# feste Sekunden-Blende ohne Takt, ohne Tempoangleich, ohne Bass-Tausch.
KONTROLL_BLENDE_S = 6.0


def cluster_starts(tracks: list[plan.Track], anzahl: int) -> list[int]:
    """Je Paar ein Start-Song aus einem **anderen** Tempo-Cluster.

    Haeufigste gerundete BPM zuerst; ein Kandidat innerhalb des ±3-%-Gates eines
    schon gewaehlten Clusters faellt weg, sonst klingen alle Paare gleich.
    """
    gewaehlt: list[float] = []
    starts: list[int] = []
    for bpm, _ in Counter(round(t.bpm) for t in tracks).most_common():
        if any(resample.tempo_passt(b, bpm) for b in gewaehlt):
            continue
        gewaehlt.append(bpm)
        starts.append(next(t.id for t in tracks if round(t.bpm) == bpm))
        if len(starts) == anzahl:
            break
    return starts


def _uebergangszeiten(protokoll) -> list[float]:
    return [round(u.mix_beginn_s, 1) for u in protokoll.uebergaenge
            if u.mix_beginn_s is not None]


def laufen_hoertest(args) -> int:
    """Rendert `--paare` blinde Paare (Auto-DJ vs. Shuffle) mit denselben Songs.

    Je Paar: dasselbe Set, einmal als Auto-DJ, einmal als Shuffle-Kontrolle; welche
    Datei A und welche B ist, wird zufaellig gezogen. Die Aufloesung steht nur im
    Schluessel, die Hoerer bekommen WAVs und Bewertungsbogen.
    """
    import csv
    import random

    einstellungen = config.vorbereiten(config.aus_argumenten(args))
    paare = int(getattr(args, "paare", 0) or 3)
    laenge = int(getattr(args, "laenge", 0) or 4)
    rng = random.Random(getattr(args, "seed", None))
    ordner = Path(getattr(args, "aus", None) or einstellungen.ergebnisse / "hoertest")
    conn = db.verbinden(einstellungen.datenbank)
    try:
        tracks, downbeats, pfade, _ = lade_tracks(
            conn, einstellungen.analyse_version, start=None, laenge=laenge)
    finally:
        conn.close()
    if not tracks:
        print("Keine mischbaren Tracks. Erst 'analyze' laufen lassen.")
        return 2
    if sf is None:
        print("soundfile fehlt - ohne WAV kein Hoertest.")
        return 2

    index = {t.id: t for t in tracks}
    ordner.mkdir(parents=True, exist_ok=True)
    schluessel: list[dict] = []
    for nr, start_id in enumerate(cluster_starts(tracks, paare), 1):
        planung = plan.baue_set(tracks, start_id=start_id, laenge=laenge)
        if len(planung.reihenfolge) < 2:
            print(f"Paar {nr}: Cluster um Track {start_id} zu klein - uebersprungen.")
            continue
        audio, beats = lade_audio(planung.reihenfolge, pfade, downbeats,
                                  config.ABTASTRATE_HOERTEST)
        auto, proto_auto, master_bpm, blende_s, faktoren = _render(
            planung.reihenfolge, index, audio, beats)
        folge = list(planung.reihenfolge)
        rng.shuffle(folge)
        # Leere Downbeats: Ausstieg = Songende - Blende, Einstieg = 0 (Player-Verhalten).
        kontrolle, proto_k = mix.mix_set(
            folge, audio, {}, config.ABTASTRATE_HOERTEST, {},
            blende_s=KONTROLL_BLENDE_S, basstausch=False, ziel_lufs=config.LUFS_ZIEL)

        varianten = {"autodj": (auto, proto_auto), "shuffle": (kontrolle, proto_k)}
        arten = list(varianten)
        rng.shuffle(arten)
        eintrag: dict = {"paar": nr, "songs": list(planung.reihenfolge)}
        for buchstabe, art in zip("AB", arten):
            mischung, proto = varianten[art]
            datei = ordner / f"paar{nr}-{buchstabe}.wav"
            sf.write(str(datei), mischung, config.ABTASTRATE_HOERTEST)
            eintrag[buchstabe] = {
                "art": art,
                "datei": datei.name,
                "reihenfolge": proto.reihenfolge,
                "uebergaenge_s": _uebergangszeiten(proto),
                "dauer_s": round(proto.dauer_s, 1),
                "lufs": round(proto.lufs, 2),
                "true_peak": round(proto.true_peak, 2),
            }
        eintrag["autodj_protokoll"] = f"_paar{nr}-autodj.json"
        _protokoll_schreiben(ordner / eintrag["autodj_protokoll"], proto_auto, planung,
                             index, pfade, master_bpm, blende_s, faktoren)
        schluessel.append(eintrag)
        print(f"Paar {nr}: {len(folge)} Songs, A={eintrag['A']['dauer_s']}s, "
              f"B={eintrag['B']['dauer_s']}s")

    if not schluessel:
        print("Kein Paar renderbar.")
        return 3
    # Dateien mit "_" NICHT an die Hoerer geben - sie loesen A/B auf.
    (ordner / "_schluessel.json").write_text(
        json.dumps(schluessel, indent=2, ensure_ascii=False), encoding="utf-8")
    with (ordner / "bewertungsbogen.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["person", "paar", "bevorzugt (A/B)",
                    "unfall_zeitpunkte_s (z. B. 312;645)", "kommentar"])
        for e in schluessel:
            w.writerow(["", e["paar"], "", "", ""])
    print(f"Hoertest: {ordner}  ({len(schluessel)} Paare; '_'-Dateien zurueckhalten)")
    return 0

