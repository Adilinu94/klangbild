"""Phase 2 · Klangbild-Mixer: lokaler Server + Browser-Oberflaeche (ADR-021).

Aufruf:
    python -m klangbild mixer            # oeffnet http://127.0.0.1:8766

Die Wiedergabe laeuft in Python (`live.Wiedergabe`, sounddevice); der Browser
ist Fernbedienung, fragt `/api/zustand` mehrmals pro Sekunde ab und laedt Songs
hoch. Hochgeladene Songs analysiert ein Hintergrund-Thread mit derselben Logik
wie `analyze` (`pipeline.track_analysieren`). Server wie `blindui.py`:
Standardbibliothek, nur localhost.
"""

from __future__ import annotations

import json
import re
import threading
import urllib.parse
import webbrowser
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import autodj, config, cover, db, einstellungen, live, uebergang, welle

SEITE = Path(__file__).with_name("mixer.html")
# soundfile liest kein AAC (M4A) - lieber gleich ablehnen als spaeter "fehler".
UPLOAD_ENDUNGEN = config.AUDIO_ENDUNGEN - {".m4a", ".aac"}
UPLOAD_MAX_BYTES = 1 << 30   # 1 GB je Datei


def bibliothek_laden(conn, version: str) -> dict[int, live.Eintrag]:
    """Mischbare Tracks (ohne Dubletten, `autodj.lade_tracks`) plus Pegel, Energie, Abschnitte."""
    tracks, downbeats, pfade, _ = autodj.lade_tracks(conn, version, start=None, laenge=0)
    extra = {
        int(z["track_id"]): z for z in conn.execute(
            "SELECT track_id, lufs, true_peak, energie_json, abschnitte_json FROM features"
            " WHERE analyse_version=?", (version,))
    }
    bib = {}
    for t in tracks:
        z = extra.get(t.id)
        energie = [float(v) for _, v in json.loads(z["energie_json"] or "[]")] if z else []
        abschnitte = [float(x) for x in json.loads(z["abschnitte_json"] or "[]")] if z else []
        bib[t.id] = live.Eintrag(
            id=t.id, pfad=pfade[t.id], bpm=t.bpm, camelot=t.camelot, downbeats=downbeats[t.id],
            gain_db=live.gain_db(z["lufs"], z["true_peak"]) if z else 0.0,
            energie=energie, abschnitte=abschnitte)
    return bib


def sicherer_name(name: str) -> str | None:
    """Dateiname aus dem Upload: ohne Pfad, nur harmlose Zeichen, erlaubte Endung."""
    name = Path(name.replace("\\", "/")).name
    stamm, endung = Path(name).stem, Path(name).suffix.lower()
    stamm = re.sub(r"[^\w\s.,()&'+-]", "_", stamm).strip(" .")[:150]
    if not stamm or endung not in UPLOAD_ENDUNGEN:
        return None
    return stamm + endung


class Mixer:
    """Wiedergabe + Upload-Analyse + Einstellungen, geteilt von allen Requests."""

    def __init__(self, wiedergabe: live.Wiedergabe, datenbank: Path, version: str,
                 upload_ordner: Path, einst_pfad: Path):
        self.w = wiedergabe
        self.datenbank = datenbank
        self.version = version
        self.upload_ordner = upload_ordner
        self.einst_pfad = einst_pfad
        self.lock = threading.Lock()
        self.offen: list[Path] = []
        self.analyse = {"fertig": 0, "fehler": 0, "aktuell": None, "meldung": ""}
        self._wecker = threading.Event()
        self.stem_auftraege: list[int] = []   # frisch hochgeladene Titel zuerst
        self.stem_fehler: set[int] = set()
        self._profil_ok: set[int] = set()   # Profil liegt fertig im Cache
        self.stem_status = {"aktuell": None, "meldung": ""}

    # --- Upload + Analyse --------------------------------------------------
    def hochladen(self, name: str, daten_lesen, laenge: int) -> str:
        sicher = sicherer_name(name)
        if sicher is None:
            raise ValueError(f"Nicht unterstuetzt: {name} (erlaubt: {', '.join(sorted(UPLOAD_ENDUNGEN))})")
        if not 0 < laenge <= UPLOAD_MAX_BYTES:
            raise ValueError("Datei leer oder zu gross")
        self.upload_ordner.mkdir(parents=True, exist_ok=True)
        ziel, n = self.upload_ordner / sicher, 1
        while ziel.exists():
            ziel = self.upload_ordner / f"{Path(sicher).stem} ({n}){Path(sicher).suffix}"
            n += 1
        rest = laenge
        with ziel.open("wb") as f:
            while rest > 0:
                block = daten_lesen(min(rest, 1 << 20))
                if not block:
                    break
                f.write(block)
                rest -= len(block)
        if rest:
            ziel.unlink(missing_ok=True)
            raise ValueError("Upload abgebrochen")
        with self.lock:
            self.offen.append(ziel)
        self._wecker.set()
        return ziel.name

    def _analysieren(self, pfad: Path) -> None:
        from . import beats, hashutil, pipeline

        conn = db.verbinden(self.datenbank)
        try:
            stat = pfad.stat()
            h, bereich = hashutil.datei_hash(pfad)
            tid, _ = db.track_eintragen(conn, pfad, stat.st_size, stat.st_mtime, h,
                                        bereich.container, bereich.start, bereich.ende)
            werte = pipeline.track_analysieren(pfad, beats.verfuegbar())
            db.features_speichern(conn, tid, self.version, werte)
            conn.commit()
            ok = werte.get("status") == "ok"
            self.analyse["fertig" if ok else "fehler"] += 1
            if not ok:
                self.analyse["meldung"] = f"{pfad.name}: {werte.get('status')}"
            self.w.bibliothek_setzen(bibliothek_laden(conn, self.version))
            if ok:
                with self.lock:
                    self.stem_auftraege.append(tid)
        finally:
            conn.close()

    def _worker(self) -> None:
        while True:
            self._wecker.wait()
            with self.lock:
                pfad = self.offen.pop(0) if self.offen else None
                if pfad is None:
                    self._wecker.clear()
                    continue
            self.analyse["aktuell"] = pfad.name
            try:
                self._analysieren(pfad)
            except Exception as fehler:  # noqa: BLE001 - eine kaputte Datei stoppt den Worker nicht
                self.analyse["fehler"] += 1
                self.analyse["meldung"] = f"{pfad.name}: {fehler}"
            self.analyse["aktuell"] = None

    def _stem_kandidat(self):
        """Naechster Titel ohne Stem-Vorrat: Uploads, dann Warteschlange, dann (falls
        gewaehlt) die ganze Bibliothek."""
        from . import stems

        e = self.w.einst
        if not e.stems or e.stems_vorrat == "aus":
            return None
        bib = self.w.bibliothek
        with self.lock:
            reihe = list(self.stem_auftraege)
        z = self.w.zustand()   # laufender und naechster Titel zuerst: die Regie braucht sie gleich
        reihe = [x["id"] for x in (z["aktuell"], z["naechster"]) if x] + reihe
        reihe += list(self.w.warteschlange)
        if e.stems_vorrat == "alle":
            reihe += sorted(bib)
        for tid in reihe:
            if tid in bib and tid not in self.stem_fehler and not stems.vorrat_fertig(tid):
                return bib[tid]
        return None

    def _profil_nachholen(self) -> bool:
        """Ein Profil nachrechnen (Titel mit Stems, aber ohne Profil): sonst kostet es ~5 s je Titel
        mitten im Backen des Uebergangs. Laufender und naechster Titel zuerst. True = es gab Arbeit."""
        from . import profil, stems

        if self.w.backt or self.w.vorher is not None:   # nicht mit Backen und laufender Blende um CPU/GIL streiten
            return False
        z = self.w.zustand()
        reihe = ([x["id"] for x in (z["aktuell"], z["naechster"]) if x] + list(self.w.warteschlange)
                 + sorted(self.w.bibliothek))
        for tid in reihe:
            if tid in self._profil_ok or tid not in self.w.bibliothek or tid in self.stem_fehler:
                continue
            p = profil.gespeichert(tid)
            if p is not None and (p.stems is not None or not stems.vorrat_fertig(tid)):
                self._profil_ok.add(tid)
                continue
            eintrag = self.w.bibliothek[tid]
            self.stem_status["aktuell"] = f"Profil: {eintrag.titel}"
            try:
                profil.laden(eintrag, lambda: live._datei_laden(eintrag))
                self._profil_ok.add(tid)
            except Exception as fehler:  # noqa: BLE001 - ein Titel darf die Vorarbeit nicht stoppen
                self.stem_fehler.add(tid)
                self.stem_status["meldung"] = f"{eintrag.titel}: {fehler}"
            self.stem_status["aktuell"] = None
            return True
        return False

    def _stem_worker(self) -> None:
        from . import stems

        ruhe = threading.Event()
        while True:
            eintrag = self._stem_kandidat()
            if eintrag is None:
                if not self._profil_nachholen():
                    ruhe.wait(5.0)
                continue
            self.stem_status["aktuell"] = eintrag.titel
            try:
                from . import profil

                roh = live._datei_laden(eintrag)
                teile = stems.vorrat_anlegen(eintrag.id, roh)
                profil.speichern(eintrag.id, profil.berechnen(eintrag, roh, teile))   # fuer die Regie
                del roh, teile
            except Exception as fehler:  # noqa: BLE001 - ein Titel darf den Vorrat nicht stoppen
                self.stem_fehler.add(eintrag.id)
                self.stem_status["meldung"] = f"{eintrag.titel}: {fehler}"
            with self.lock:
                self.stem_auftraege = [t for t in self.stem_auftraege if t != eintrag.id]
            self.stem_status["aktuell"] = None

    def starten(self) -> None:
        from . import stems

        threading.Thread(target=self._worker, daemon=True).start()
        if stems.verfuegbar():
            threading.Thread(target=self._stem_worker, daemon=True).start()

    # --- Zustand + Einstellungen --------------------------------------------
    def zustand(self) -> dict:
        z = self.w.zustand()
        with self.lock:
            z["analyse"] = {**self.analyse, "offen": len(self.offen)}
        z["bibliothek_anzahl"] = len(self.w.bibliothek)
        z["stems_vorrat"] = dict(self.stem_status)
        return z

    def einstellungen_setzen(self, roh: dict) -> dict:
        neu = einstellungen.aus_dict(roh, self.w.einst)
        einstellungen.speichern(self.einst_pfad, neu)
        self.w.einstellungen_setzen(neu)
        return asdict(neu)


_M: Mixer | None = None


class _Handler(BaseHTTPRequestHandler):
    server_version = "KlangbildMixer/0.2"

    def log_message(self, *args):  # ruhiger Server
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
        w = _M.w
        if pfad == "/":
            self._sende(SEITE.read_bytes(), "text/html; charset=utf-8")
        elif pfad == "/api/zustand":
            self._json(_M.zustand())
        elif pfad == "/api/einstellungen":
            self._json({"werte": asdict(w.einst), "auswahl": einstellungen.AUSWAHL,
                        "takte": einstellungen.TAKTE, "grenzen": einstellungen.GRENZEN})
        elif pfad == "/api/bibliothek":
            from . import stems

            self._json([{"id": e.id, "titel": e.titel, "bpm": round(e.bpm, 2), "camelot": e.camelot,
                         "stems": stems.vorrat_fertig(e.id)}
                        for e in sorted(w.bibliothek.values(), key=lambda e: e.titel.lower())])
        elif pfad.startswith(("/api/track/", "/api/cover/", "/api/welle/")):
            rest = pfad.rsplit("/", 1)[1]
            e = w.bibliothek.get(int(rest)) if rest.isdigit() else None
            if e is None:
                self._json({"fehler": "unbekannt"}, 404)
            elif pfad.startswith("/api/cover/"):
                bild = cover.vorschau(e.id, e.pfad)
                if bild is None:
                    self._json({"fehler": "kein Cover"}, 404)
                else:
                    self._sende(bild, "image/jpeg")
            elif pfad.startswith("/api/welle/"):
                self._json(welle.laden(e.id, e.pfad))
            else:
                takte = uebergang.regulaer(e.downbeats, e.bpm, (e.downbeats[-1] if e.downbeats else 0) + 30,
                                           um_s=e.downbeats[len(e.downbeats) // 2] if e.downbeats else 0)
                from . import profil

                p = profil.gespeichert(e.id)   # Abschnitte (Intro/Drop/...) fuer die Anzeige
                abschnitte = [] if p is None else [
                    {"von": round(float(p.takte[min(p.n - 1, p.phrase_start(k))]), 2), "etikett": x}
                    for k, x in enumerate(p.etiketten())]
                self._json({"id": e.id, "energie": e.energie, "takte": [round(t, 3) for t in takte],
                            "phrasen": [round(t, 3) for t in takte[::autodj.PHRASEN_TAKTE]],
                            "abschnitte": abschnitte})
        else:
            self._json({"fehler": "nicht gefunden"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        url = urllib.parse.urlparse(self.path)
        befehl = url.path.removeprefix("/api/")
        laenge = int(self.headers.get("Content-Length", "0") or 0)
        w = _M.w
        gelesen = [0]

        def lesen(n: int) -> bytes:
            block = self.rfile.read(n)
            gelesen[0] += len(block)
            return block

        try:
            if befehl == "upload":
                name = urllib.parse.parse_qs(url.query).get("name", [""])[0]
                try:
                    self._json({"datei": _M.hochladen(name, lesen, laenge)})
                except ValueError:
                    # Rest des Bodys wegwerfen: sonst bricht die Verbindung ab, bevor der Browser
                    # die Fehlermeldung (400) lesen kann.
                    rest = min(laenge - gelesen[0], UPLOAD_MAX_BYTES)
                    while rest > 0:
                        block = self.rfile.read(min(rest, 1 << 20))
                        if not block:
                            break
                        rest -= len(block)
                    raise
                return
            daten = json.loads(self.rfile.read(laenge) or b"{}")
            if befehl == "einstellungen":
                self._json(_M.einstellungen_setzen(daten))
                return
            aktionen = {
                "play": lambda: w.play(int(daten["id"])),
                "pause": w.pause,
                "seek": lambda: w.seek(float(daten["s"])),
                "weiter": w.weiter,
                "anders": w.anders,
                "queue": lambda: w.einreihen(int(daten["id"])),
                "entfernen": lambda: w.entfernen(int(daten["index"])),
                "verschieben": lambda: w.verschieben(int(daten["index"]), int(daten["richtung"])),
                "sortieren": w.sortieren,
                "leeren": w.leeren,
                "autodj": lambda: w.autodj_setzen(bool(daten["an"])),
            }
            if befehl not in aktionen:
                self._json({"fehler": "unbekannter Befehl"}, 404)
                return
            aktionen[befehl]()
        except (KeyError, ValueError, TypeError) as fehler:
            self._json({"fehler": str(fehler)}, 400)
            return
        except Exception as fehler:  # noqa: BLE001 - z. B. unlesbare Datei: melden statt abstuerzen
            self._json({"fehler": str(fehler)}, 500)
            return
        self._json(_M.zustand())


class EinzelServer(ThreadingHTTPServer):
    """Ohne SO_REUSEADDR: Windows liesse sonst einen zweiten Server auf denselben Port, und der
    Browser spraeche mit dem alten (gemessen: zwei Uebergangstests auf 8767). So scheitert der zweite."""

    allow_reuse_address = False


def server(mixer: Mixer, host: str, port: int) -> ThreadingHTTPServer:
    global _M
    _M = mixer
    return EinzelServer((host, port), _Handler)


def laufen(args) -> int:
    e = config.vorbereiten(config.aus_argumenten(args))
    conn = db.verbinden(e.datenbank)
    try:
        bib = bibliothek_laden(conn, e.analyse_version)
    finally:
        conn.close()
    einst_pfad = e.ergebnisse / "mixer-einstellungen.json"
    wiedergabe = live.Wiedergabe(bib, einst=einstellungen.laden(einst_pfad))
    wiedergabe.lern_pfad = e.ergebnisse / "regie-lernen.json"   # Vorlieben je Rezept (lokal)
    try:
        wiedergabe.vorlieben = {k: float(v) for k, v in json.loads(
            wiedergabe.lern_pfad.read_text(encoding="utf-8")).items()}
    except (OSError, ValueError, AttributeError):
        pass
    mixer = Mixer(wiedergabe, e.datenbank, e.analyse_version, config.DATEN / "upload", einst_pfad)
    url = f"http://{args.host}:{args.port}"
    try:   # Port zuerst: ein zweiter Start darf keinen zweiten Audio-Stream oeffnen
        srv = server(mixer, args.host, args.port)
    except OSError:
        print(f"Der Mixer läuft schon: {url}", flush=True)
        webbrowser.open(url)
        return 0
    wiedergabe.starten()
    mixer.starten()
    print(f"Klangbild-Mixer: {url}  ({len(bib)} Titel) - Beenden mit Strg+C", flush=True)
    webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbeendet", flush=True)
    finally:
        srv.server_close()
    return 0
