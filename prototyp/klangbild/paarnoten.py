"""Erwartete Uebergangsnoten aller Titelpaare (BAUPLAN-UEBERGAENGE §8).

Je Paar A -> B im Tempo-Rahmen (auch Doppel-/Halbtempo) plant die Regie den besten Uebergang aus den
Profilen (ohne Audio: die Loop-Pruefung kommt erst beim echten Backen). Die Note ist die Schaetzung des
Kritikers, solange er sein Tor nicht schafft die auf 1..5 gestreckten Regie-Punkte. Die Reihenfolge der
Playlist (`plan.sortiere_alle`) richtet sich danach.

    python -m klangbild paarnoten        # ~0,1 s je Paar; fertige Paare bleiben im Cache

Cache: cache/paarnoten.json, gilt nur fuer dieselbe Analyse- und Regie-Version.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from . import config

CACHE = config.CACHE / "paarnoten.json"
REGIE_VERSION = "2026-10-16"   # bei Aenderungen an der Regie hochzaehlen: alte Paarnoten verfallen


class Paarnoten:
    """{(a, b): (Note, Rezept)} aus dem Cache; verworfen, wenn die Version nicht passt."""

    def __init__(self, version: str, pfad: Path = CACHE):
        self.pfad, self.version = pfad, f"{version}|{REGIE_VERSION}"
        self.daten: dict[str, list] = {}
        try:
            roh = json.loads(pfad.read_text(encoding="utf-8"))
            if roh.get("version") == self.version:
                self.daten = roh["noten"]
        except (OSError, ValueError, KeyError):
            pass

    def neu_laden(self) -> "Paarnoten":
        """Frisch aus dem Cache (der Hintergrund-Lauf `paarnoten` fuellt ihn, waehrend der Mixer laeuft)."""
        return Paarnoten(self.version.split("|")[0], self.pfad)

    def note(self, a: int, b: int) -> float | None:
        x = self.daten.get(f"{a}_{b}")
        return x[0] if x else None

    def rezept(self, a: int, b: int) -> str | None:
        x = self.daten.get(f"{a}_{b}")
        return x[1] if x else None

    def speichern(self) -> None:
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        self.pfad.write_text(json.dumps({"version": self.version, "noten": self.daten}), encoding="utf-8")


def im_tempo(bpm_a: float, bpm_b: float, max_bpm: float) -> bool:
    return min(abs(bpm_a - f * bpm_b) for f in (1.0, 2.0, 0.5)) <= max(max_bpm, 0.05)


def rechnen(bib: dict, noten: Paarnoten, e, ids: list[int] | None = None, zeitlimit_s: float | None = None) -> int:
    """Fehlende Paarnoten fuer `ids` (Standard: alle) rechnen; gibt die Zahl neuer Paare zurueck."""
    from . import kritiker as kr
    from . import profil, regie, uebergang

    k = kr.Kritiker.laden()
    ids = [i for i in (ids or sorted(bib)) if i in bib and profil.gespeichert(i) is not None]
    beginn, neu, roh = time.perf_counter(), 0, []
    for a in ids:
        pa = profil.gespeichert(a)
        for b in ids:
            if a == b or f"{a}_{b}" in noten.daten or not im_tempo(bib[a].bpm, bib[b].bpm, e.max_bpm):
                continue
            pb = profil.gespeichert(b)
            sync = abs(bib[a].bpm - bib[b].bpm) <= max(e.max_bpm, 0.05)
            plaene = regie.planen(bib[a], pa, bib[b], pb, e, 0.0, sync,
                                  uebergang._harmonisch(bib[a].camelot, bib[b].camelot), anzahl=1, kritiker=k)
            if plaene:
                p = plaene[0]
                note = k.vorher(regie.plan_merkmale(p, pa, pb, e, sync, False, False, bib[a], bib[b])) if k else None
                roh.append((f"{a}_{b}", p.punkte, note, p.rezept))
                neu += 1
            if zeitlimit_s and time.perf_counter() - beginn > zeitlimit_s:
                break
        if zeitlimit_s and time.perf_counter() - beginn > zeitlimit_s:
            break
    if roh:
        # Ohne Kritiker: Regie-Punkte ueber die Perzentile auf 1..5 strecken (Punkte sind nur relativ sinnvoll)
        punkte = np.array([r[1] for r in roh] + [v[2] for v in noten.daten.values() if len(v) > 2])
        lo, hi = np.percentile(punkte, [5, 95]) if len(punkte) > 1 else (punkte[0] - 1, punkte[0] + 1)
        for schluessel, p, note, rezept in roh:
            if note is None:
                note = float(np.clip(1.0 + 4.0 * (p - lo) / max(hi - lo, 1e-9), 1.0, 5.0))
            noten.daten[schluessel] = [round(note, 2), rezept, round(float(p), 2)]
    return neu


def kommando(args) -> int:
    from . import db, einstellungen, mixer

    e = config.vorbereiten(config.aus_argumenten(args))
    conn = db.verbinden(e.datenbank)
    try:
        bib = mixer.bibliothek_laden(conn, e.analyse_version)
    finally:
        conn.close()
    einst = einstellungen.regie_einst(einstellungen.laden(e.ergebnisse / "mixer-einstellungen.json")) \
        or einstellungen.Einstellungen()
    noten = Paarnoten(e.analyse_version)
    fertig = 0
    while True:   # in Haeppchen speichern: ein Abbruch verliert hoechstens zwei Minuten
        neu = rechnen(bib, noten, einst, zeitlimit_s=120.0)
        noten.speichern()
        fertig += neu
        print(f"{fertig} Paare neu, {len(noten.daten)} im Cache", flush=True)
        if neu == 0:
            return 0
