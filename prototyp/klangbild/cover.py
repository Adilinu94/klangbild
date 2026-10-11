"""Eingebettete Cover aus MP3 (ID3v2 APIC/PIC) und FLAC (PICTURE-Block) lesen.

Eigener, kleiner Leser statt mutagen (GPL). Er liest nur den Tag-Bereich am
Dateianfang, nicht das Audio. Fuer die Oberflaeche wird das Bild auf 256 px
verkleinert (Pillow, HPND) und als JPEG im Cache abgelegt.
"""

from __future__ import annotations

import io
from pathlib import Path

from . import config
from .hashutil import _id3v2_groesse

CACHE = config.CACHE / "cover"
KANTE = 256


def _bis_null(daten: bytes, start: int, breit: bool) -> int:
    """Index hinter dem Null-Terminator ab `start` (UTF-16: zwei Null-Bytes, ausgerichtet)."""
    if not breit:
        ende = daten.find(b"\x00", start)
        return len(daten) if ende < 0 else ende + 1
    i = start
    while i + 1 < len(daten):
        if daten[i] == 0 and daten[i + 1] == 0:
            return i + 2
        i += 2
    return len(daten)


def _id3_bild(tag: bytes) -> bytes | None:
    version, flags = tag[3], tag[5]
    körper = tag[10:]
    if flags & 0x80 and version < 4:   # Unsynchronisation (v2.3: ganzer Tag)
        körper = körper.replace(b"\xff\x00", b"\xff")
    if flags & 0x40 and version == 3 and len(körper) >= 4:   # erweiterter Kopf
        körper = körper[4 + int.from_bytes(körper[:4], "big"):]
    i = 0
    kopf_n, id_n = (6, 3) if version == 2 else (10, 4)
    while i + kopf_n <= len(körper):
        fid = körper[i:i + id_n]
        if fid[:1] == b"\x00":
            break
        roh = körper[i + id_n:i + id_n + (3 if version == 2 else 4)]
        if version == 4:
            groesse = (roh[0] << 21) | (roh[1] << 14) | (roh[2] << 7) | roh[3]
        else:
            groesse = int.from_bytes(roh, "big")
        daten = körper[i + kopf_n:i + kopf_n + groesse]
        i += kopf_n + groesse
        if fid not in (b"APIC", b"PIC") or len(daten) < 4:
            continue
        breit = daten[0] in (1, 2)
        if fid == b"PIC":   # v2.2: Format 3 Zeichen, Typ, Beschreibung
            pos = _bis_null(daten, 5, breit)
        else:
            pos = _bis_null(daten, 1, False) + 1          # MIME, dann Bildtyp
            pos = _bis_null(daten, pos, breit)            # Beschreibung
        if pos < len(daten):
            return daten[pos:]
    return None


def _flac_bild(datei) -> bytes | None:
    if datei.read(4) != b"fLaC":
        return None
    while True:
        kopf = datei.read(4)
        if len(kopf) < 4:
            return None
        letzter, typ = bool(kopf[0] & 0x80), kopf[0] & 0x7F
        laenge = int.from_bytes(kopf[1:4], "big")
        if typ != 6:
            datei.seek(laenge, 1)
        else:
            b = datei.read(laenge)
            pos = 4
            pos += 4 + int.from_bytes(b[pos:pos + 4], "big")    # MIME
            pos += 4 + int.from_bytes(b[pos:pos + 4], "big")    # Beschreibung
            pos += 16                                           # Breite, Hoehe, Tiefe, Farben
            n = int.from_bytes(b[pos:pos + 4], "big")
            return b[pos + 4:pos + 4 + n] or None
        if letzter:
            return None


def eingebettet(pfad: str | Path) -> bytes | None:
    """Rohbytes des ersten eingebetteten Bildes oder None."""
    pfad = Path(pfad)
    try:
        with pfad.open("rb") as f:
            if pfad.suffix.lower() == ".flac":
                return _flac_bild(f)
            kopf = f.read(10)
            groesse = _id3v2_groesse(kopf)
            if not groesse:
                return None
            return _id3_bild(kopf + f.read(groesse - 10))
    except (OSError, IndexError, ValueError):
        return None


def vorschau(track_id: int, pfad: str | Path, cache: Path | None = None) -> bytes | None:
    """Verkleinertes JPEG (256 px) aus dem Cache bzw. frisch aus der Datei; None ohne Cover."""
    cache = cache or CACHE
    ziel = cache / f"{track_id}.jpg"
    leer = cache / f"{track_id}.leer"
    if ziel.exists():
        return ziel.read_bytes()
    if leer.exists():
        return None
    roh = eingebettet(pfad)
    cache.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image

        bild = Image.open(io.BytesIO(roh or b"")).convert("RGB")
        bild.thumbnail((KANTE, KANTE))
        puffer = io.BytesIO()
        bild.save(puffer, "JPEG", quality=85)
    except Exception:  # noqa: BLE001 - kein/kaputtes Bild: Platzhalter in der Oberflaeche
        leer.touch()
        return None
    ziel.write_bytes(puffer.getvalue())
    return puffer.getvalue()
