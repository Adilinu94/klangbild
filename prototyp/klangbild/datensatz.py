"""Datensatz der benoteten Uebergaenge fuer den Kritiker (BAUPLAN-UEBERGAENGE §2.1).

Eine Zeile je benotetem Uebergang aus allen Uebergangstest-Runden und den Daumen-Bewertungen
im Mixer (§7.1, Gewicht 0,5): Merkmale aus den Takt-Profilen (Rezept, Lage in A und B, Paar,
Ergebnis der fertigen Blende) und die Note.

    python -m klangbild datensatz      # -> ergebnisse/datensatz/uebergaenge.jsonl

B's Einsatz steht erst ab Runde 12 in den Clip-Daten (`ein_takt`). Fuer aeltere Runden wird er
rekonstruiert: das Clip-Ende (nach der Blende nur B, im Originaltempo) wird per Kreuzkorrelation
der Huellkurven in B's Song gesucht; unter einer Korrelation von 0,6 bleibt er offen (NaN).
Gemessen an Runde 12/13 (Einsatz bekannt): 41 von 42 gefunden, 30 davon auf den Takt genau; die
Ausreisser liegen meist ganze Phrasen daneben (der Song wiederholt sich, die Huellkurve passt dort auch).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from . import config, plan, profil, regie
from .profil import PHRASE, Profil

ERGEBNISSE = config.PROTOTYP_WURZEL / "ergebnisse"
LIVE = ERGEBNISSE / "live-bewertungen"
ZIEL = ERGEBNISSE / "datensatz" / "uebergaenge.jsonl"
ETIKETTEN = ("intro", "aufbau", "drop", "haupt", "break", "outro")
STILE = {"kurz": 0, "ausgewogen": 1, "lang": 2}
STUFEN = {"klassisch": 0, "kreativ": 1, "wild": 2}
ERGEBNIS = ("lautheit_spanne_db", "loch_db")   # nur nach dem Backen bekannt (Kritiker "nachher")
HUELLE_HZ = 100
KORR_MIN = 0.6


def bewertete_faelle() -> list[tuple[str, dict, dict]]:
    """(Ordner, Meta, Bewertung) aller benoteten Faelle aus allen Uebergangstest-Runden."""
    aus = []
    for ordner in sorted(ERGEBNISSE.glob("uebergangstest*")):
        datei = ordner / "bewertungen.json"
        if not datei.exists():
            continue
        for nr, b in json.loads(datei.read_text(encoding="utf-8")).items():
            meta = ordner / "clips" / f"{int(nr):03d}.json"
            if b.get("note") and meta.exists():
                m = json.loads(meta.read_text(encoding="utf-8"))
                if "info" in m:
                    aus.append((ordner.name, m, b))
    return aus


def live_faelle() -> list[tuple[str, dict, dict]]:
    """Live-Bewertungen aus dem Mixer (§7.1, Schulnote im Popup): gleiches Format, nur ohne Audio."""
    aus = []
    for ordner in sorted(LIVE.glob("*")):
        datei = ordner / "bewertungen.json"
        if not datei.exists():
            continue
        for nr, b in json.loads(datei.read_text(encoding="utf-8")).items():
            meta = ordner / "clips" / f"{int(nr):03d}.json"
            if b.get("note") and meta.exists():
                aus.append(("live-" + ordner.name, json.loads(meta.read_text(encoding="utf-8")), b))
    return aus


# --- Merkmale ----------------------------------------------------------------------------------

def _etikett(p: Profil, takt: int) -> str:
    et = p.etiketten()
    return et[min(len(et) - 1, p.phrase_von(takt))] if takt < p.n else "outro"


def _seite(p: Profil | None, takt: int | None, L: int, name: str) -> dict:
    """Lage in einem Song: Etikett, Pegel (zum Song-Median), Gesang im Fenster."""
    if p is None or takt is None or not 0 <= takt < p.n:
        return {}
    fenster = regie._fenster(p.gesamt, takt, L)[:max(1, min(L, p.n - takt))]
    g = p.gesang()
    return {f"{name}_et={_etikett(p, takt)}": 1.0,
            f"{name}_pegel": float(np.mean(fenster) - np.median(p.gesamt)),
            **({f"{name}_gesang": float(np.mean(regie._fenster(g, takt, L)))} if g is not None else {})}


def merkmale(pa: Profil | None, pb: Profil | None, i: int | None, j: int | None, L: int, rezept: str, *,
             stems: bool, sync: bool, experimente: str, stil: str, spielanteil: str, weiter: bool,
             bpm_a: float | None = None, bpm_b: float | None = None, camelot_a: str | None = None,
             camelot_b: str | None = None, k_ein: int = 0, mal: int = 0) -> dict:
    """Merkmale eines Uebergangs (vor dem Backen bekannt). Fehlendes bleibt weg (Modell: NaN)."""
    m = {f"rezept={rezept}": 1.0, "takte": float(L), "stems": float(stems), "sync": float(sync),
         "experimente": float(STUFEN.get(experimente, 0)), "stil": float(STILE.get(stil, 1)),
         "schnell": float(spielanteil == "schnell"), "weiter": float(weiter)}
    if bpm_a and bpm_b:
        m["bpm_abstand"] = abs(bpm_a - bpm_b)
    if camelot_a and camelot_b:
        m["camelot"] = plan.harmonie_note(camelot_a, camelot_b)[0]
    m.update(_seite(pa, i, L, "a"))
    m.update(_seite(pb, j, L, "b"))
    if pa is not None and i is not None and 0 <= i < pa.n:
        m["a_rest"] = float(pa.n - i - L)
    if pb is not None and j is not None and 0 <= j < pb.n:
        nach = j + L - mal * k_ein
        m["b_drop_danach"] = float(_etikett(pb, nach) == "drop")
        m["b_einsatz"] = regie._einsatz(pb, nach)
        if pa is not None and i is not None and 0 <= i < pa.n:
            bi = regie._b_index(j, L, k_ein, mal)
            h = regie._harmonie(pa, pb, i, bi)
            if h is not None:
                m["harmonie"] = h
            e_a = float(np.mean(pa.gesamt[i:i + max(1, L // 2)]))
            e_b = float(np.mean(pb.gesamt[nach:nach + PHRASE])) if nach < pb.n else -30.0
            m["energiesprung"] = e_b - e_a
            ga, gb = pa.gesang(), pb.gesang()
            if ga is not None and gb is not None:
                m["gesang_gegeneinander"] = float(np.mean(regie._fenster(ga, i, L) * regie._werte(gb, bi)))
    return m


def ergebnis(blende: np.ndarray, vor: np.ndarray, nach: np.ndarray, takte: int) -> dict:
    """Lautheit der fertigen Blende je Takt (RMS, dB): Spanne und tiefstes Loch gegen A davor und B danach
    (earshot-Versuch: Atempausen gefielen eher, tiefe Loecher nicht)."""
    def db(x):
        x = x.mean(axis=1) if x.ndim > 1 else x
        return 10.0 * np.log10(np.mean(np.square(x, dtype=np.float64)) + 1e-10) if len(x) else np.nan

    stuecke = np.array_split(blende, max(1, takte))
    je_takt = np.array([db(s) for s in stuecke if len(s)])
    if not je_takt.size:
        return {}
    ref = np.nanmean([db(vor), db(nach)])
    return {"lautheit_spanne_db": float(np.ptp(je_takt)), "loch_db": float(np.min(je_takt) - ref)}


# --- B's Einsatz in alten Runden ---------------------------------------------------------------

def _huelle(mono: np.ndarray, rate: int) -> np.ndarray:
    hop = rate // HUELLE_HZ
    x = np.abs(mono[:len(mono) // hop * hop]).reshape(-1, hop).mean(axis=1)
    return np.log(x + 1e-4)


def finden(song: np.ndarray, stueck: np.ndarray) -> tuple[int, float]:
    """(Lage in Huellkurven-Schritten, Korrelation) des Stuecks im Song (Pearson je Lage)."""
    from scipy.signal import correlate

    m = len(stueck)
    if m < 50 or len(song) < m:
        return 0, 0.0
    z = (stueck - stueck.mean()) / (stueck.std() + 1e-9)
    zaehler = correlate(song, z, mode="valid", method="fft")
    c1, c2 = np.concatenate([[0.0], np.cumsum(song)]), np.concatenate([[0.0], np.cumsum(song ** 2)])
    mittel = (c1[m:] - c1[:-m]) / m
    sd = np.sqrt(np.maximum((c2[m:] - c2[:-m]) / m - mittel ** 2, 1e-12))
    r = zaehler / (m * sd)
    k = int(np.argmax(r))
    return k, float(r[k])


def b_einsatz(m: dict, clip: np.ndarray, rate: int, b_mono: np.ndarray, b_rate: int, pb: Profil) -> int | None:
    """B's Einsatztakt aus dem Clip: das Ende nach der Blende (nur B, Originaltempo) im Song suchen."""
    i = m["info"]
    ende = clip[int(m["blende_bis_s"] * rate):]
    if len(ende) < 2 * rate:
        return None
    k, r = finden(_huelle(b_mono, b_rate), _huelle(ende.mean(axis=1) if ende.ndim > 1 else ende, rate))
    if r < KORR_MIN:
        return None
    pos = k / HUELLE_HZ   # B's Originalsekunde am Blendenende
    if not i.get("sync"):   # B lief ungedehnt ab seinem Einsatz
        return pb.takt_bei(pos - i["blende_s"])
    loop = i.get("b_intro_loop") or {}
    return pb.takt_bei(pos) - (i["takte"] - loop.get("mal", 0) * loop.get("takte", 0))


# --- Bauen ----------------------------------------------------------------------------------------

def zeile(ordner: str, m: dict, b: dict, pa: Profil | None, pb: Profil | None, j: int | None,
          erg: dict | None = None) -> dict:
    i = m["info"]
    a_takt = i.get("aus_takt")
    if a_takt is None and pa is not None and "a_orig_start" in i:
        a_takt = pa.takt_bei(i["a_orig_start"]) + i.get("vorlauf_takte", 0)
    loop = i.get("b_intro_loop") or {}
    mm = merkmale(pa, pb, a_takt, j, int(i.get("takte", 8)), i.get("rezept") or i.get("art", "?"),
                  stems=bool(i.get("stems")), sync=bool(i.get("sync")), experimente=m.get("experimente", "klassisch"),
                  stil=m.get("stil", "ausgewogen"), spielanteil=m.get("spielanteil", "lang"),
                  weiter=bool(m.get("weiter")), bpm_a=i.get("bpm_a"), bpm_b=i.get("bpm_b"),
                  camelot_a=m["a"].get("camelot"), camelot_b=m["b"].get("camelot"),
                  k_ein=loop.get("takte", 0), mal=loop.get("mal", 0))
    mm.update(erg or {})
    return {"runde": ordner, "nr": m["nr"], "note": b["note"], "gewicht": 0.5 if b.get("daumen") else 1.0,   # alte Daumen: nur 4/2
            "stichworte": b.get("stichworte", []), "kommentar": b.get("kommentar", ""),
            "ein_takt": j, "ein_takt_rekonstruiert": "ein_takt" not in i and j is not None, "merkmale": mm}


def bauen(ziel: Path = ZIEL) -> list[dict]:
    import soundfile as sf

    from . import audioio, db

    conn = db.verbinden(config.DATENBANK)
    pfade = {int(z["id"]): z["pfad"] for z in conn.execute("SELECT id, pfad FROM tracks")}
    songs: dict[int, np.ndarray] = {}
    zeilen = []
    for ordner, m, b in bewertete_faelle() + live_faelle():
        i = m["info"]
        pa, pb = profil.gespeichert(m["a"]["id"]), profil.gespeichert(m["b"]["id"])
        j = i.get("ein_takt")
        erg = None
        clip_datei = ERGEBNISSE / ordner / "clips" / f"{m['nr']:03d}.flac"
        if clip_datei.exists():
            clip, rate = sf.read(str(clip_datei), dtype="float32")
            v, e = int(m["blende_von_s"] * rate), int(m["blende_bis_s"] * rate)
            erg = ergebnis(clip[v:e], clip[max(0, v - 4 * rate):v], clip[e:e + 4 * rate], int(i.get("takte", 8)))
            if j is None and pb is not None and m["b"]["id"] in pfade:
                bid = m["b"]["id"]
                if bid not in songs:
                    songs.clear()   # Speicher: ein Song reicht, die Faelle kommen je Runde
                    try:
                        songs[bid] = audioio.decodieren(pfade[bid], rate).daten
                    except Exception:  # noqa: BLE001 - Datei weg: Einsatz bleibt offen
                        songs[bid] = np.zeros(0, np.float32)
                j = b_einsatz(m, clip, rate, songs[bid], rate, pb) if songs[bid].size else None
        zeilen.append(zeile(ordner, m, b, pa, pb, j, erg))
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text("".join(json.dumps(z, ensure_ascii=False) + "\n" for z in zeilen), encoding="utf-8")
    return zeilen


def laden(ziel: Path = ZIEL) -> list[dict]:
    return [json.loads(x) for x in ziel.read_text(encoding="utf-8").splitlines() if x.strip()]


def kommando(_args=None) -> int:
    zeilen = bauen()
    alt = [z for z in zeilen if z["runde"] < "uebergangstest-20261014-runde12" and z["runde"].startswith("ueber")]
    gesetzt = sum(z["ein_takt"] is not None for z in alt)
    print(f"{len(zeilen)} Übergänge -> {ZIEL}; B-Einsatz rekonstruiert für {gesetzt}/{len(alt)} aus Runde 1-11",
          flush=True)
    return 0
