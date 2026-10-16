"""Hoertest nur fuer Uebergaenge: blind bewerten (1-5 + Stichworte), mit Stopp und Fortsetzen.

Aufruf:
    python -m klangbild uebergangstest               # backen im Hintergrund + Oberflaeche
    python -m klangbild uebergangstest --auswertung  # Noten je Rezept/Stil -> auswertung.md
    python -m klangbild uebergangstest --neu         # alten Test archivieren, neuen beginnen

Jeder Fall ist ein Titelpaar, wie der Auto-DJ es waehlen und planen wuerde
(`live.Wiedergabe._autodj_wahl`, `_auto_backen`), ohne gelernte Vorlieben. Jedes dritte
Paar kommt zusaetzlich mit Plan 2 und 3 der Regie: daran sieht man, ob Plan 1 wirklich
der beste ist (und spaeter, ob ein Sprachmodell besser waehlt). Jeder fuenfte Fall ist
ein WEITER-Uebergang. Gehoert wird nur der Ausschnitt um die Blende. Jede Note wird sofort
gespeichert; Faelle, Clips und Noten liegen unter `ergebnisse/uebergangstest/`.
"""

from __future__ import annotations

import json
import random
import threading
import time
import urllib.parse
import webbrowser
from collections import Counter, defaultdict
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import numpy as np

from . import config, db, einstellungen, live
from .uebergang import Spur

RATE = live.RATE
SEITE = Path(__file__).with_name("uebergangstest.html")
VOR_S = 8.0     # so viel von A vor der Blende
NACH_S = 6.0    # so viel von B nach der Blende
STILE = ("kurz", "ausgewogen", "lang")
STICHWORTE = ("Gesang prallt aufeinander", "Takt daneben / galoppiert", "Loch / zu leise", "Zu laut",
              "Doppelter Bass", "Loop fällt auf", "Effekt störend", "Effekt nicht hörbar",
              "Tonarten beißen sich", "Zu lang", "Zu kurz / abrupt", "Knacken", "Falsche Stelle im Song")


def faelle_planen(ids: list[int], paare: int, seed: int, stile: tuple[str, ...] = STILE,
                  experimente: tuple[str, ...] = ("klassisch",), gemma: bool = False,
                  waehler: str = "Gemma") -> list[dict]:
    """Feste Fallliste (reproduzierbar ueber `seed`), blind gemischt (`reihe`). `gemma`: jedes Paar
    zweimal - Plan der Regie und die Wahl des zweiten Waehlers (`waehler`: "Gemma" oder "Kritiker",
    BAUPLAN-UEBERGAENGE §2.3) statt der Varianten Plan 2/3."""
    rng = random.Random(seed)
    faelle: list[dict] = []
    for k, a in enumerate(rng.sample(sorted(ids), min(paare, len(ids)))):
        basis = {"a": a, "stil": stile[k % len(stile)], "experimente": experimente[k % len(experimente)], "spielanteil": "schnell" if k % 4 == 3 else "lang",
                 "weiter": k % 5 == 4}
        paar = len(faelle)
        faelle.append({**basis, "nr": paar, "rang": 0, "paar": paar})
        if gemma:
            faelle.append({**basis, "nr": len(faelle), "rang": 0, "paar": paar, "gemma": True, "waehler": waehler})
        elif k % 3 == 1 and not basis["weiter"]:
            for rang in (1, 2):
                faelle.append({**basis, "nr": len(faelle), "rang": rang, "paar": paar})
    reihe = list(range(len(faelle)))
    rng.shuffle(reihe)
    for pos, nr in enumerate(reihe):
        faelle[nr]["reihe"] = pos
    return faelle


def clip(a_puffer: np.ndarray, start_n: int, b_puffer: np.ndarray, blende_s: float) -> tuple[np.ndarray, float]:
    """A kurz vor der Blende + Blende + B kurz danach, Raender weich. (Audio, Blendenbeginn in s)."""
    vor = min(start_n, int(VOR_S * RATE))
    x = np.concatenate([a_puffer[start_n - vor:start_n],
                        b_puffer[:int((blende_s + NACH_S) * RATE)]]).astype(np.float32)
    rand = min(int(0.3 * RATE), len(x) // 2)
    r = np.linspace(0.0, 1.0, rand, dtype=np.float32)[:, None]
    x[:rand] *= r
    x[len(x) - rand:] *= r[::-1]
    return x, vor / RATE


def _schreiben(datei: Path, daten) -> None:
    tmp = datei.with_suffix(datei.suffix + ".tmp")
    tmp.write_text(json.dumps(daten, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(datei)   # nie eine halbe Datei: Stopp/Absturz verliert keine Noten


def _lesen(datei: Path, vorgabe):
    try:
        return json.loads(datei.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return vorgabe


def _bekannte_ids(ordner: Path) -> set[int]:
    """Titel (A und B), die in den archivierten Runden schon zu hoeren waren."""
    ids = set()
    for meta in ordner.parent.glob(f"{ordner.name}-*/clips/*.json"):
        m = _lesen(meta, {})
        ids |= {m[k]["id"] for k in ("a", "b") if isinstance(m.get(k), dict) and "id" in m[k]}
    return ids


class Test:
    def __init__(self, ordner: Path, w: live.Wiedergabe | None = None):
        self.ordner = ordner
        self.clips = ordner / "clips"
        self.clips.mkdir(parents=True, exist_ok=True)
        self.faelle: list[dict] = _lesen(ordner / "faelle.json", [])
        self.bewertungen: dict[str, dict] = _lesen(ordner / "bewertungen.json", {})
        self.w = w
        self.bekannt = _bekannte_ids(ordner)
        self.lock = threading.Lock()
        self.gestoppt = threading.Event()
        self.backt: str | None = None
        self.waehler = None   # Gemma-Versuch (gemma_probe.waehler), nur fuer Faelle mit "gemma"
        self.kritiker = None  # kritiker.Kritiker fuer die A/B-Faelle mit waehler "Kritiker"

    # --- Faelle backen -----------------------------------------------------
    def meta(self, nr: int) -> dict | None:
        return _lesen(self.clips / f"{nr:03d}.json", None)

    def _meta_schreiben(self, nr: int, meta: dict) -> None:
        _schreiben(self.clips / f"{nr:03d}.json", meta)

    def _backen(self, f: dict) -> None:
        import soundfile as sf

        w, nr = self.w, f["nr"]
        mit_kritiker = bool(f.get("gemma")) and f.get("waehler") == "Kritiker"
        e = einstellungen.Einstellungen(modus=f["stil"], spielanteil=f["spielanteil"],
                                        experimente=f.get("experimente", "klassisch"), kritiker=mit_kritiker)
        a = w.bibliothek[f["a"]]
        a_spur = Spur.roh(a, w.laden(a))
        ab_s = 0.45 * len(a_spur.puffer) / RATE if f["weiter"] else 20.0   # WEITER: mitten im Song
        if f["rang"] == 0 and not f.get("gemma"):   # Partner: moeglichst ein Lied, das in den Runden davor nicht vorkam
            bekannt = self.bekannt if len(self.bekannt) < len(w.bibliothek) // 2 else set()
            b_id = w._autodj_wahl(a_spur, a_spur.bpm_bei(ab_s), ab_s, {a.id} | bekannt, e)
        else:
            basis = self.meta(f["paar"]) or {}
            b_id = basis.get("b", {}).get("id")
        if b_id is None or b_id not in w.bibliothek:
            self._meta_schreiben(nr, {"nr": nr, "fehler": "kein passender Partner"})
            return
        b = w.bibliothek[b_id]
        self.backt = f"{a.titel} → {b.titel}"
        w._rang, w._letztes_rezept, w.vorlieben, w.pos = f["rang"], None, {}, 0
        w.plan_waehler = self.waehler if f.get("gemma") and not mit_kritiker else None
        w.kritiker = self.kritiker if mit_kritiker else None
        g = w._auto_backen(a_spur, b, w.laden(b), einstellungen.regie_einst(e), ab_s, f["weiter"])
        info = {k: v for k, v in g.info.items() if k != "kurven"}
        if f.get("gemma"):   # Gemma waehlt dasselbe wie die Regie: nichts Neues zu hoeren
            r = (self.meta(f["paar"]) or {}).get("info", {})
            if (r.get("rezept"), r.get("a_orig_start"), r.get("takte")) == \
                    (info["rezept"], info["a_orig_start"], info["takte"]):
                self._meta_schreiben(nr, {"nr": nr, "doppelt": True, "gemma_gleich": True, "gemma": info.get("gemma")})
                return
        elif f["rang"] > 0:   # die Regie hatte weniger Plaene: derselbe Plan noch einmal waere kein Vergleich
            schon = {(self.meta(x["nr"]) or {}).get("info", {}).get("plan")
                     for x in self.faelle if x["paar"] == f["paar"] and x["nr"] != nr}
            if info.get("plan") in schon:
                self._meta_schreiben(nr, {"nr": nr, "doppelt": True})
                return
        x, blende_von = clip(a_spur.puffer, g.start_n, g.spur.puffer, info["blende_s"])
        sf.write(str(self.clips / f"{nr:03d}.flac"), x, RATE, subtype="PCM_16", format="FLAC")
        eintrag = lambda t: {"id": t.id, "titel": t.titel, "bpm": round(t.bpm, 2), "camelot": t.camelot}  # noqa: E731
        self._meta_schreiben(nr, {
            "nr": nr, "a": eintrag(a), "b": eintrag(b), **{k: f[k] for k in ("stil", "spielanteil", "weiter", "rang")},
            "experimente": f.get("experimente", "klassisch"), "gemma": bool(f.get("gemma")),
            **({"waehler": f.get("waehler", "Gemma")} if f.get("gemma") else {}),
            "info": info, "blende_von_s": round(blende_von, 2),
            "blende_bis_s": round(blende_von + info["blende_s"], 2), "dauer_s": round(len(x) / RATE, 2)})

    def backen_alle(self) -> None:
        """Faelle in Hoerreihenfolge backen (Basis-Paar vor seinen Varianten); fertige ueberspringen."""
        nach_nr = {f["nr"]: f for f in self.faelle}
        for f in sorted(self.faelle, key=lambda x: x["reihe"]):
            for fall in ([nach_nr[f["paar"]]] if f["rang"] or f.get("gemma") else []) + [f]:
                while self.gestoppt.is_set():
                    time.sleep(0.5)
                if self.meta(fall["nr"]) is not None:
                    continue
                try:
                    self._backen(fall)
                except Exception as fehler:  # noqa: BLE001 - ein kaputter Fall stoppt den Test nicht
                    print(f"Fall {fall['nr']}: {fehler}", flush=True)
                    self._meta_schreiben(fall["nr"], {"nr": fall["nr"], "fehler": str(fehler)})
                self.backt = None

    # --- Zustand + Bewertung -----------------------------------------------
    def zustand(self) -> dict:
        reihe = []
        for f in sorted(self.faelle, key=lambda x: x["reihe"]):
            m = self.meta(f["nr"])
            b = self.bewertungen.get(str(f["nr"]))
            reihe.append({"nr": f["nr"], "bereit": bool(m) and "info" in m,
                          "aus": bool(m) and ("fehler" in m or "doppelt" in m),
                          "note": b.get("note") if b else None, "spaeter": bool(b and b.get("spaeter"))})
        return {"reihe": reihe, "gestoppt": self.gestoppt.is_set(), "backt": self.backt,
                "stichworte": STICHWORTE}

    def fall(self, nr: int) -> dict:
        m = self.meta(nr) or {}
        blind = {k: m[k] for k in ("nr", "a", "b", "blende_von_s", "blende_bis_s", "dauer_s") if k in m}
        # seit Runde 12 nicht mehr blind: der Nutzer will je Fall sehen, was eingestellt war
        einst = {k: m[k] for k in ("stil", "spielanteil", "experimente", "weiter") if k in m}
        bewertung = self.bewertungen.get(str(nr))
        info = dict(m.get("info", {}))
        if bewertung and bewertung.get("note"):   # Gemma-Versuch: wer gewaehlt hat, erst nach der Note zeigen
            einst["wahl"] = m.get("waehler", "Gemma") if m.get("gemma") else "Regie"
        else:
            info.pop("gemma", None)
        return {**blind, "einst": {**einst, **info}, "bewertung": bewertung}

    def bewerten(self, nr: int, roh: dict) -> None:
        if not any(f["nr"] == nr for f in self.faelle):
            raise ValueError("unbekannter Fall")
        if roh.get("spaeter"):
            eintrag = {"note": None, "spaeter": True}
        else:
            note = int(roh["note"])
            if not 1 <= note <= 5:
                raise ValueError("Note 1 bis 5")
            eintrag = {"note": note, "stichworte": [s for s in roh.get("stichworte", []) if s in STICHWORTE],
                       "kommentar": str(roh.get("kommentar", ""))[:500],
                       "gehoert_s": round(float(roh.get("gehoert_s", 0.0)), 1)}
        eintrag["zeit"] = time.strftime("%Y-%m-%d %H:%M:%S")
        with self.lock:
            self.bewertungen[str(nr)] = eintrag
            _schreiben(self.ordner / "bewertungen.json", self.bewertungen)


# --- Auswertung ---------------------------------------------------------------

def _zeilen(t: Test) -> list[tuple[dict, dict]]:
    zeilen = []
    for nr_text, b in t.bewertungen.items():
        m = t.meta(int(nr_text))
        if b.get("note") and m and "info" in m:
            zeilen.append((m, b))
    return zeilen


def auswerten(ordner: Path) -> str:
    """Noten je Rezept, Stil, Art, Plan-Rang, Selbstkontrolle, Loop-Guete + die schlechtesten Faelle."""
    t = Test(ordner)
    zeilen = _zeilen(t)
    if not zeilen:
        return "Noch keine Bewertungen.\n"
    noten = [b["note"] for _, b in zeilen]
    aus = [f"# Übergangstest · Auswertung ({time.strftime('%Y-%m-%d %H:%M')})", "",
           f"Bewertet: {len(zeilen)} · Mittel {np.mean(noten):.2f} · Note ≤ 2: {sum(n <= 2 for n in noten)}", ""]
    # Vergleich mit der vorigen Runde (archiviert von --neu): hat die letzte Aenderung geholfen?
    frueher = sorted(ordner.parent.glob(f"{ordner.name}-*"))
    if frueher:
        vor = _zeilen(Test(frueher[-1]))
        if vor:
            vn = [b["note"] for _, b in vor]
            je = lambda zs, k: {str(k(m)): np.mean([b["note"] for mm, b in zs if k(mm) == k(m)])  # noqa: E731
                                for m, _ in zs}
            stil_vor, stil_jetzt = je(vor, lambda m: m["stil"]), je(zeilen, lambda m: m["stil"])
            aus.extend([f"## Vergleich mit der Runde davor ({frueher[-1].name})", "",
                        f"Mittel {np.mean(vn):.2f} → {np.mean(noten):.2f} · Note ≤ 2: "
                        f"{sum(n <= 2 for n in vn)}/{len(vn)} → {sum(n <= 2 for n in noten)}/{len(noten)}", ""]
                       + [f"- {s}: {stil_vor.get(s, float('nan')):.2f} → {stil_jetzt.get(s, float('nan')):.2f}"
                          for s in STILE] + [""])

    def tabelle(titel: str, schluessel) -> None:
        gruppen: dict[str, list] = defaultdict(list)
        for m, b in zeilen:
            gruppen[str(schluessel(m))].append(b)
        aus.extend([f"## {titel}", "", "| Gruppe | n | Mittel | ≤ 2 | häufigste Stichworte |", "|---|---|---|---|---|"])
        for name, bs in sorted(gruppen.items(), key=lambda kv: np.mean([b["note"] for b in kv[1]])):
            sw = Counter(s for b in bs for s in b.get("stichworte", [])).most_common(3)
            aus.append(f"| {name} | {len(bs)} | {np.mean([b['note'] for b in bs]):.2f} | "
                       f"{sum(b['note'] <= 2 for b in bs)} | {', '.join(f'{s} ({n})' for s, n in sw)} |")
        aus.append("")

    tabelle("Je Rezept", lambda m: m["info"].get("rezept", m["info"].get("art")))
    tabelle("Je Stil", lambda m: m["stil"])
    tabelle("Experimente", lambda m: m.get("experimente", "klassisch"))
    tabelle("Je Spielanteil", lambda m: m["spielanteil"])
    tabelle("WEITER oder normal", lambda m: "WEITER" if m["weiter"] else "normal")
    tabelle("Mit Stems", lambda m: "ja" if m["info"].get("stems") else "nein")
    tabelle("Tempo angeglichen (sync)", lambda m: "ja" if m["info"].get("sync") else "nein")
    tabelle("Länge (Takte)", lambda m: m["info"].get("takte"))
    tabelle("Selbstkontrolle", lambda m: "durchgefallen → Sicherheits-Blend" if m["info"].get("pruefung")
            else f"bestanden (Plan {m['info'].get('plan')})")
    tabelle("Loop-Güte", lambda m: "kein Auto-Loop" if "loop_wahl" not in m["info"]
            else ("< 0,8" if m["info"]["loop_wahl"]["guete"] < 0.8 else "≥ 0,8"))

    # Plan 1 gegen 2/3 desselben Paars (Fall-Rang = Startplan der Regie, wie "anderer Uebergang")
    paare: dict[int, dict[int, int]] = defaultdict(dict)
    rang_von = {f["nr"]: (f["paar"], f["rang"]) for f in t.faelle}
    for m, b in zeilen:
        paar, rang = rang_von[m["nr"]]
        paare[paar]["g" if m.get("gemma") else rang] = b["note"]
    mit_gemma = [p for p in paare.values() if 0 in p and "g" in p]
    if mit_gemma or any(f.get("gemma") for f in t.faelle):
        gleich = sum(1 for f in t.faelle if (t.meta(f["nr"]) or {}).get("gemma_gleich"))
        name = next((m.get("waehler", "Gemma") for m, _ in zeilen if m.get("gemma")), "Gemma")
        tabelle("Wer hat gewählt", lambda m: m.get("waehler", "Gemma") if m.get("gemma") else "Regie")
        aus.extend([f"## {name} gegen Regie (gleiches Paar)", "",
                    f"Paare: {len(mit_gemma)} · {name} besser: {sum(p['g'] > p[0] for p in mit_gemma)} · "
                    f"gleich gut: {sum(p['g'] == p[0] for p in mit_gemma)} · Regie besser: "
                    f"{sum(p['g'] < p[0] for p in mit_gemma)} · {name} wählte denselben Plan: {gleich}", ""])
    paare = {k: {r: n for r, n in p.items() if r != "g"} for k, p in paare.items()}
    voll = [p for p in paare.values() if 0 in p and len(p) > 1]
    if voll:
        bester = sum(p[0] >= max(p.values()) for p in voll)
        aus.extend(["## Plan 1 gegen Plan 2/3 (gleiches Paar)", "",
                    f"Paare mit Varianten: {len(voll)} · Plan 1 war (mit-)bester: {bester}", ""]
                   + [f"- Rang {r + 1}: Mittel {np.mean([p[r] for p in voll if r in p]):.2f}"
                      for r in (0, 1, 2) if any(r in p for p in voll)] + [""])

    aus.extend(["## Die schlechtesten Übergänge (Note ≤ 2)", ""])
    for m, b in sorted(zeilen, key=lambda z: z[1]["note"]):
        if b["note"] > 2:
            break
        i = m["info"]
        aus.append(f"- **Fall {m['nr']}** · Note {b['note']} · {m['a']['titel']} → {m['b']['titel']} · "
                   f"{i.get('rezept')} · {i.get('takte')} Takte · {m['stil']}/{m['spielanteil']}"
                   f"{' · WEITER' if m['weiter'] else ''} · {', '.join(b.get('stichworte', [])) or '–'}"
                   f"{' · „' + b['kommentar'] + '“' if b.get('kommentar') else ''}  \n  Grund: {i.get('grund', '–')}")
    text = "\n".join(aus) + "\n"
    (ordner / "auswertung.md").write_text(text, encoding="utf-8")
    return text


# --- Server -------------------------------------------------------------------

_T: Test | None = None


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        return

    def _sende(self, inhalt: bytes, typ: str = "application/json", code: int = 200) -> None:
        self.send_response(code)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(inhalt)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(inhalt)

    def _json(self, daten, code: int = 200) -> None:
        self._sende(json.dumps(daten, ensure_ascii=False).encode("utf-8"), code=code)

    def do_GET(self) -> None:  # noqa: N802
        pfad = urllib.parse.urlparse(self.path).path
        rest = pfad.rsplit("/", 1)[-1].removesuffix(".flac")
        if pfad == "/":
            self._sende(SEITE.read_bytes(), "text/html; charset=utf-8")
        elif pfad == "/api/zustand":
            self._json(_T.zustand())
        elif pfad == "/api/auswertung":
            self._sende(auswerten(_T.ordner).encode("utf-8"), "text/plain; charset=utf-8")
        elif pfad.startswith("/api/fall/") and rest.isdigit():
            self._json(_T.fall(int(rest)))
        elif pfad.startswith("/clip/") and rest.isdigit() and (_T.clips / f"{int(rest):03d}.flac").exists():
            self._sende((_T.clips / f"{int(rest):03d}.flac").read_bytes(), "audio/flac")
        else:
            self._json({"fehler": "nicht gefunden"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        befehl = urllib.parse.urlparse(self.path).path.removeprefix("/api/")
        try:
            daten = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0") or 0)) or b"{}")
            if befehl == "bewerten":
                _T.bewerten(int(daten["nr"]), daten)
            elif befehl == "stopp":
                (_T.gestoppt.set if daten.get("an") else _T.gestoppt.clear)()
            else:
                self._json({"fehler": "unbekannter Befehl"}, 404)
                return
        except (KeyError, ValueError, TypeError) as fehler:
            self._json({"fehler": str(fehler)}, 400)
            return
        self._json(_T.zustand())


def laufen(args) -> int:
    from . import mixer, profil, stems, uebergang

    e = config.vorbereiten(config.aus_argumenten(args))
    ordner = e.ergebnisse / "uebergangstest"
    if args.auswertung:
        print(auswerten(ordner))
        return 0
    if args.neu and ordner.exists():
        ziel = ordner.with_name(f"uebergangstest-{time.strftime('%Y%m%d-%H%M%S')}")
        ordner.rename(ziel)
        print(f"Alter Test archiviert: {ziel}", flush=True)
    conn = db.verbinden(e.datenbank)
    try:
        bib = mixer.bibliothek_laden(conn, e.analyse_version)
    finally:
        conn.close()
    ordner.mkdir(parents=True, exist_ok=True)
    # Test nur mit einem Ordner (z. B. DnB): gemerkt, damit ein Neustart ohne Option dabei bleibt
    nur = ordner / "nur_ordner.txt"
    if args.nur_ordner and not (ordner / "faelle.json").exists():
        nur.write_text(args.nur_ordner, encoding="utf-8")
    if nur.exists():
        wurzel = Path(nur.read_text(encoding="utf-8").strip())
        bib = {i: x for i, x in bib.items() if Path(x.pfad).is_relative_to(wurzel)}
        print(f"Nur {wurzel}: {len(bib)} Titel", flush=True)
    if not (ordner / "faelle.json").exists():
        ids = [i for i in bib if profil.gespeichert(i) is not None] or list(bib)
        # neue Runde mit anderen Liedern als die archivierten (A und B), solange genug uebrig sind
        frisch = [i for i in ids if i not in _bekannte_ids(ordner)]
        ids = frisch if len(frisch) >= 4 * args.paare else ids
        # ohne Partner im Tempo-Rahmen wird jeder Uebergang ein Schnitt (kleine Ordner wie DnB): nicht als A
        grenze = einstellungen.Einstellungen().max_bpm
        ids = [i for i in ids if any(abs(bib[i].bpm - x.bpm) <= grenze for k, x in bib.items() if k != i)] or ids
        _schreiben(ordner / "faelle.json", faelle_planen(ids, args.paare, args.seed,
                                                         tuple(args.stil.split(",")) if args.stil else STILE,
                                                         tuple(args.experimente.split(",")),
                                                         gemma=bool(args.gemma or args.kritiker),
                                                         waehler="Kritiker" if args.kritiker else "Gemma"))
    url = f"http://{args.host}:{args.port}"
    try:   # Port zuerst: ein zweiter Test darf nicht neben dem alten laufen (alter Stand im Speicher)
        srv = mixer.EinzelServer((args.host, args.port), _Handler)
    except OSError:
        print(f"Der Übergangstest läuft schon: {url}", flush=True)
        webbrowser.open(url)
        return 0
    w = live.Wiedergabe(bib)
    uebergang.dehn_pool_starten()
    if stems.verfuegbar():
        w.stem_quelle = stems.trennen

    global _T
    _T = Test(ordner, w)
    if args.gemma:   # Gemma-Versuch: das Modell bleibt im Speicher und waehlt bei den Gemma-Faellen
        from . import gemma_probe
        print(f"Lade {args.gemma} …", flush=True)
        _T.waehler = gemma_probe.waehler(gemma_probe.Gemma(args.gemma))
    if args.kritiker:   # A/B-Runde: das gespeicherte Modell, auch wenn es sein Tor (noch) nicht geschafft hat
        from . import kritiker

        _T.kritiker = kritiker.Kritiker.laden(nur_aktiv=False)
        if _T.kritiker is None:
            print("Kein Kritiker-Modell: erst `python -m klangbild kritiker --trainieren`", flush=True)
            return 1
    fertig = sum(1 for f in _T.faelle if _T.meta(f["nr"]) is not None)
    print(f"Übergangstest: {len(_T.faelle)} Fälle, {fertig} gebacken, {len(_T.bewertungen)} bewertet", flush=True)
    threading.Thread(target=_T.backen_alle, daemon=True).start()
    print(f"Oberfläche: {url}  - Beenden mit Strg+C (Fortschritt bleibt gespeichert)", flush=True)
    webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbeendet - beim nächsten Start geht es an derselben Stelle weiter", flush=True)
    finally:
        srv.server_close()
    return 0
