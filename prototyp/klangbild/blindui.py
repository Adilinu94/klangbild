"""Bewertungsoberflaeche im Browser (blind, ohne Zusatzpakete).

Der Engpass in Phase 0.1 ist nicht das Einbetten, sondern das **blinde Bewerten**
von Nachbar- und Textaufgaben. Deshalb ein kleines lokales Web-Interface:
Ausgangssong bzw. Anfrage oben, darunter die Kandidaten mit Abspielknopf und
drei Urteilen (passt / geht / passt nicht) plus Marke „Unfall".

Bewusst ohne Fremdbibliothek (kein Flask): nur `http.server` aus der
Standardbibliothek, damit nichts installiert werden muss und nichts
versehentlich ausgeliefert wird.
"""

from __future__ import annotations

import html
import json
import sqlite3
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import audioio, config, db

KOPF = """<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Klangbild · Phase 0.1</title>
<style>
 :root { color-scheme: light dark; }
 body { font: 15px/1.5 system-ui, sans-serif; margin: 0 auto; max-width: 900px; padding: 24px; }
 h1 { font-size: 20px; } h2 { font-size: 17px; margin-top: 28px; }
 .karte { border: 1px solid #8884; border-radius: 10px; padding: 12px 14px; margin: 10px 0; }
 .seed { background: #8881; }
 .zeile { display: flex; gap: 14px; align-items: center; flex-wrap: wrap; }
 audio { height: 34px; }
 .urteil label { margin-right: 12px; white-space: nowrap; }
 .unfall { color: #b00; font-weight: 600; }
 .weiter { font-weight: 600; padding: 8px 16px; }
 .fortschritt { color: #888; font-size: 13px; }
 table { border-collapse: collapse; } td, th { padding: 4px 10px; text-align: left; }
</style></head><body>"""


class Zustand:
    def __init__(self, conn: sqlite3.Connection, cache: Path):
        self.conn = conn
        self.cache = cache
        (cache / "listen").mkdir(parents=True, exist_ok=True)


_ZUSTAND: Zustand | None = None


# --------------------------------------------------------------------------
# Audio-Ausschnitt fuer das Ohr erzeugen
# --------------------------------------------------------------------------
def _vektor_version(conn: sqlite3.Connection) -> str:
    zeile = conn.execute(
        "SELECT modell_version FROM embeddings GROUP BY modell_version"
        " ORDER BY COUNT(*) DESC LIMIT 1"
    ).fetchone()
    return zeile["modell_version"] if zeile else config.MODELL_VERSION


def listen_clip(conn: sqlite3.Connection, track_id: int, position: str) -> Path | None:
    """Erzeugt einmalig einen 44,1-kHz-Ausschnitt aus der Originaldatei."""
    ziel = _ZUSTAND.cache / "listen" / f"{track_id}_{position}.wav"  # type: ignore[union-attr]
    if ziel.exists():
        return ziel
    version = _vektor_version(conn)
    zeile = conn.execute(
        "SELECT clip_pfad, start_s, ende_s FROM embeddings"
        " WHERE track_id=? AND position=? AND modell_version=?",
        (track_id, position, version),
    ).fetchone()
    if zeile is None or not zeile["clip_pfad"]:
        return None
    quelle = Path(zeile["clip_pfad"])
    if not quelle.exists():
        return None
    try:
        audio = audioio.decodieren(quelle, 44100)
    except audioio.Lesefehler:
        return None
    start_s = zeile["start_s"] or 0.0
    ende_s = zeile["ende_s"] or (start_s + config.AUSSCHNITT_SEKUNDEN)
    start = max(0, int(start_s * audio.rate))
    ende = min(len(audio.daten), int(ende_s * audio.rate))
    audioio.ausschnitt_schneiden(audio, start, ende, ziel)
    return ziel


# --------------------------------------------------------------------------
# Seiten
# --------------------------------------------------------------------------
def _kopfzeile(conn: sqlite3.Connection) -> str:
    gesamt = conn.execute("SELECT COUNT(*) FROM aufgaben").fetchone()[0]
    erledigt = conn.execute(
        "SELECT COUNT(DISTINCT aufgabe_id) FROM bewertungen"
    ).fetchone()[0]
    return f'<p class="fortschritt">Aufgaben: {erledigt} von {gesamt} bewertet</p>'


def _uebersicht(conn: sqlite3.Connection) -> str:
    zeilen = []
    for art, titel in (
        ("nachbarn", "Nachbarn (bezahlt der Klang?)"),
        ("baseline", "Baseline (Zufall)"),
        ("text", "Textsuche (sinnvoll)"),
        ("unsinn", "Kontrolle (Unsinn)"),
    ):
        aufgaben = db.aufgaben(conn, art)
        bewertet = {
            zeile["aufgabe_id"]
            for zeile in conn.execute(
                "SELECT DISTINCT b.aufgabe_id FROM bewertungen b JOIN aufgaben a"
                " ON a.id=b.aufgabe_id WHERE a.art=?",
                (art,),
            ).fetchall()
        }
        offen = [a for a in aufgaben if a["id"] not in bewertet]
        naechste = offen[0]["id"] if offen else (aufgaben[0]["id"] if aufgaben else "")
        zeilen.append(
            f'<div class="karte"><h2>{html.escape(titel)}</h2>'
            f'<p class="fortschritt">{len(bewertet)} von {len(aufgaben)} bewertet</p>'
            + (f'<p><a href="/task/{html.escape(naechste)}">Weiter bewerten →</a></p>' if aufgaben else "<p>Keine Aufgaben.</p>")
            + "</div>"
        )
    return "".join(zeilen)


def _audio_tag(conn: sqlite3.Connection, track_id: int, position: str) -> str:
    clip = listen_clip(conn, track_id, position)
    if clip is None:
        return '<em>kein Ausschnitt verfuegbar</em>'
    return f'<audio controls preload="none" src="/audio/{track_id}/{position}"></audio>'


def _aufgabe_seite(conn: sqlite3.Connection, aufgabe_id: str) -> str:
    aufgabe = conn.execute("SELECT * FROM aufgaben WHERE id=?", (aufgabe_id,)).fetchone()
    if aufgabe is None:
        return "<p>Aufgabe nicht gefunden.</p>"
    tracks = json.loads(aufgabe["tracks_json"])

    kopf = f'<p><a href="/">← Übersicht</a></p><h1>{html.escape(aufgabe_id)}</h1>'
    seed_html = ""
    if aufgabe["seed_track_id"]:
        seed = conn.execute(
            "SELECT pfad FROM tracks WHERE id=?", (aufgabe["seed_track_id"],)
        ).fetchone()
        name = Path(seed["pfad"]).name if seed else "?"
        seed_html = (
            f'<div class="karte seed"><strong>Ausgangssong</strong>'
            f'<div class="zeile">{_audio_tag(conn, aufgabe["seed_track_id"], "mitte")}'
            f"<span>{html.escape(name)}</span></div></div>"
        )
    if aufgabe["text"]:
        kopf += f'<div class="karte seed"><strong>Anfrage:</strong> {html.escape(aufgabe["text"])}</div>'

    kandidaten = []
    for rang, track_id in enumerate(tracks, 1):
        kandidaten.append(
            f'<div class="karte"><div class="zeile">'
            f"<strong>Treffer {rang}</strong>{_audio_tag(conn, track_id, 'mitte')}"
            f'<span class="urteil">'
            f'<label><input type="radio" name="urteil-{track_id}" value="passt"> passt</label>'
            f'<label><input type="radio" name="urteil-{track_id}" value="geht"> geht</label>'
            f'<label><input type="radio" name="urteil-{track_id}" value="passt_nicht"> passt nicht</label>'
            f'<label class="unfall"><input type="checkbox" name="unfall-{track_id}"> Unfall</label>'
            f"</span></div></div>"
        )
    kandidaten_html = "".join(kandidaten)

    return (
        kopf
        + seed_html
        + '<form method="post" action="/rate">'
        + f'<input type="hidden" name="aufgabe" value="{html.escape(aufgabe_id)}">'
        + '<p>Wer bewertet? <input name="rater" placeholder="Name" required></p>'
        + kandidaten_html
        + '<p><button class="weiter" type="submit">Speichern &amp; weiter</button></p>'
        + "</form>"
        + f'<p><a href="/task/{html.escape(_naechste_id(conn, aufgabe_id))}">Überspringen →</a></p>'
    )


def _naechste_id(conn: sqlite3.Connection, aufgabe_id: str) -> str:
    ids = [zeile["id"] for zeile in conn.execute("SELECT id FROM aufgaben ORDER BY id")]
    if aufgabe_id in ids:
        index = ids.index(aufgabe_id)
        if index + 1 < len(ids):
            return ids[index + 1]
    return ids[0] if ids else ""


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------
class _Handler(BaseHTTPRequestHandler):
    server_version = "KlangbildPrototyp/0.1"

    def log_message(self, *args):  # ruhiger Server
        return

    def _sende(self, inhalt: bytes, typ: str = "text/html; charset=utf-8", code: int = 200) -> None:
        self.send_response(code)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(inhalt)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(inhalt)

    def do_GET(self) -> None:  # noqa: N802
        pfad = urllib.parse.urlparse(self.path)
        teile = [t for t in pfad.path.split("/") if t]

        if not teile:
            inhalt = KOPF + "<h1>Klangbild · Phase 0.1</h1>" + _kopfzeile(_ZUSTAND.conn) + _uebersicht(_ZUSTAND.conn)
            self._sende((inhalt + "</body></html>").encode("utf-8"))
            return

        if teile[0] == "task" and len(teile) == 2:
            seite = _aufgabe_seite(_ZUSTAND.conn, urllib.parse.unquote(teile[1]))
            self._sende((KOPF + seite + "</body></html>").encode("utf-8"))
            return

        if teile[0] == "audio" and len(teile) == 3:
            try:
                track_id, position = int(teile[1]), teile[2]
            except ValueError:
                self._sende(b"ungueltig", "text/plain; charset=utf-8", 400)
                return
            clip = listen_clip(_ZUSTAND.conn, track_id, position)
            if clip is None:
                self._sende(b"kein Ausschnitt", "text/plain; charset=utf-8", 404)
                return
            self._sende(clip.read_bytes(), "audio/wav")
            return

        self._sende(b"nicht gefunden", "text/plain; charset=utf-8", 404)

    def do_POST(self) -> None:  # noqa: N802
        if urllib.parse.urlparse(self.path).path != "/rate":
            self._sende(b"nicht gefunden", "text/plain; charset=utf-8", 404)
            return
        laenge = int(self.headers.get("Content-Length", "0"))
        daten = urllib.parse.parse_qs(self.rfile.read(laenge).decode("utf-8"))
        aufgabe_id = (daten.get("aufgabe") or [""])[0]
        rater = (daten.get("rater") or ["anonym"])[0].strip() or "anonym"
        aufgabe = _ZUSTAND.conn.execute(
            "SELECT tracks_json FROM aufgaben WHERE id=?", (aufgabe_id,)
        ).fetchone()
        if aufgabe is None:
            self._sende(b"unbekannte Aufgabe", "text/plain; charset=utf-8", 400)
            return
        tracks = json.loads(aufgabe["tracks_json"])
        for rang, track_id in enumerate(tracks, 1):
            urteil = (daten.get(f"urteil-{track_id}") or [""])[0]
            if urteil not in {"passt", "geht", "passt_nicht"}:
                continue
            unfall = f"unfall-{track_id}" in daten
            db.bewertung_speichern(_ZUSTAND.conn, aufgabe_id, track_id, rang, urteil, unfall, rater)
        _ZUSTAND.conn.commit()

        self.send_response(303)
        self.send_header("Location", f"/task/{_naechste_id(_ZUSTAND.conn, aufgabe_id)}")
        self.end_headers()


def starten(conn: sqlite3.Connection, cache: Path, host: str, port: int) -> int:
    global _ZUSTAND
    _ZUSTAND = Zustand(conn, cache)
    aufgaben = conn.execute("SELECT COUNT(*) FROM aufgaben").fetchone()[0]
    print(f"Bewertungsoberflaeche: http://{host}:{port}  ({aufgaben} Aufgaben)", flush=True)
    print("Beenden mit Strg+C", flush=True)
    server = ThreadingHTTPServer((host, port), _Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbeendet", flush=True)
    finally:
        server.server_close()
    return 0
