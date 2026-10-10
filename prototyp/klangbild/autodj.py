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
    """Decodiert die Songs der Reihenfolge nach Mono@rate und liefert Audio+Downbeats.

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
            a = audioio.decodieren(pfad, rate)
        except Exception:  # noqa: BLE001,S112 - eine datei darf einzeln scheitern
            continue
        if a.daten.size == 0:
            continue
        audio[tid] = np.asarray(a.daten, dtype=np.float32).reshape(-1)
        beats_out[tid] = downbeats.get(tid, [])
    return audio, beats_out


# --- Plan -> Engine-Bruecke (identisch zu Phase 1.0, nur echte Tracks) --------
# Kein zweiter Mix-Algorithmus: faktoren/blende werden exakt wie in
# phase10._faktoren/_blende_s gerechnet, damit Plan und Mix dasselbe Raster
# treffen (ADR-014). Der einzige Unterschied: master = Start-Song statt Track 0.

TAKT = 4          # 4/4-Takt: die Blende muss ganze Takte (Taktanfaenge) umfassen
BLENDE_TAKTE = 2  # wie phase10 - Raster-Kontinuitaet haengt nicht an der Laenge


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

        master_bpm = _master_bpm(reihenfolge, index)
        faktoren = _faktoren(reihenfolge, index, master_bpm)
        blende_s = _blende_s(master_bpm)

        audio, beats = lade_audio(reihenfolge, pfade, downbeats,
                                  config.ABTASTRATE_ANALYSE)
        mischung, protokoll = mix.mix_set(
            reihenfolge=reihenfolge,
            audio=audio,
            downbeats=beats,
            rate=config.ABTASTRATE_ANALYSE,
            faktoren=faktoren,
            blende_s=blende_s,
            basstausch=True,
            ziel_lufs=config.LUFS_ZIEL,
        )

        aus = getattr(args, "aus", None)
        ziel = Path(aus) if aus else (einstellungen.ergebnisse / "hoertest-mix.wav")
        if sf is not None and mischung.size:
            ziel.parent.mkdir(parents=True, exist_ok=True)
            sf.write(str(ziel), mischung, config.ABTASTRATE_ANALYSE)
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

