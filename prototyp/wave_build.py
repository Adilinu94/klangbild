"""Echte Waveform-Daten fuer die UI-Mockups aus der Analyse-DB.

64 Balken aus der gespeicherten RMS-Kurve (energie_json, dBFS -80..0 -> 0..100),
Downbeat-Ticks: Balken-Index, unter dem ein Downbeat liegt.
Ausgabe: ui/mockups/waveform-data.json mit je 2 Tracks (Player + ON-AIR).

Version: aus klangbild.config.ANALYSE_VERSION (derzeit 0.3.0, BPM-Regression),
Tracks: dieselben beiden wie in R1 (Angel of Mine / Arcade) - ihre BPM haben
sich mit der Regression leicht geaendert (130.0 / 134.0).
"""
import sqlite3, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from klangbild.config import ANALYSE_VERSION

N = 64
HIER = Path(__file__).resolve().parent
DB = HIER / "ergebnisse" / "klangbild.db"
OUT = HIER.parent / "ui" / "mockups" / "waveform-data.json"


def balken(track_id: int) -> dict:
    c = sqlite3.connect(DB)
    pfad, bpm, camelot, lufs, downs_j, e_j = c.execute(
        "SELECT t.pfad,f.bpm,f.key_camelot,f.lufs,f.downbeats_json,f.energie_json "
        "FROM features f JOIN tracks t ON t.id=f.track_id "
        "WHERE f.track_id=? AND f.analyse_version=?", (track_id, ANALYSE_VERSION)
    ).fetchone()
    c.close()
    paare = json.loads(e_j)  # [[zeit_s, db], ...]
    zeiten = [p[0] for p in paare]
    werte = [p[1] for p in paare]
    n = len(werte)
    lo, hi = min(werte), max(werte)
    if hi - lo < 3.0:  # fast Stille: feste Mitte statt Riesen-Verstaerkung
        lo, hi = hi - 3.0, hi
    bars = []
    for k in range(N):
        a, b = k * n // N, max(k * n // N + 1, (k + 1) * n // N)
        peak = max(werte[a:b])
        bars.append(round((peak - lo) / (hi - lo) * 100.0, 1))
    downs = json.loads(downs_j or "[]")
    dauer = zeiten[-1] if zeiten else 1.0
    bar_von = lambda d: min(N - 1, int(d / dauer * N))
    ticks = sorted({bar_von(d) for d in downs})
    # Phrasen-Ticks: jeder 8. Downbeat (= Phrasenanfang, PHRASEN_TAKTE aus autodj)
    ticks_phrase = sorted({bar_von(d) for d in downs[::8]})
    name = Path(pfad)
    return {
        "titel": name.stem.split("-")[0].strip()[:24],
        "interpret": (name.stem.split("-")[1].strip()[:24]
                      if "-" in name.stem else "UNBEKANNT"),
        "bpm": round(bpm or 0, 1), "camelot": camelot,
        "lufs": round(lufs, 1) if lufs else None,
        "dauer_s": round(dauer, 1),
        "bars": bars, "ticks": ticks, "ticks_phrase": ticks_phrase,
    }


daten = {
    "player": balken(11),     # Angel of Mine (BPM s. quelle)
    "onair": balken(12),      # Arcade (BPM s. quelle)
    "quelle": (f"klangbild.db features@{ANALYSE_VERSION}, "
               "64 RMS-Peak-Balken aus energie_json"),
}
OUT.write_text(json.dumps(daten, ensure_ascii=False), encoding="utf-8")
for key in ("player", "onair"):
    d = daten[key]
    print(key, "|", d["titel"], "|", d["interpret"], "|", d["bpm"],
          "|", d["camelot"], "|", d["lufs"], "| dauer:", d["dauer_s"],
          "| ticks:", len(d["ticks"]))
print("->", OUT)
