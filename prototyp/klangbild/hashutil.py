"""Datei-Hash ueber die Audiodaten (ADR-007, ADR-013).

Tags schreiben darf keine neue Analyse ausloesen. Deshalb wird nicht die ganze
Datei gehasht, sondern eine **Stichprobe ueber den Audio-Bereich**: seine Laenge
plus feste Bloecke an Anfang, Mitte und Ende. Tag-Bloecke (ID3v2/ID3v1/APE,
Vorbis-Kommentare, MP4-Metadaten, Cover) bleiben aussen vor.

Faelle, die der Code bewusst **nicht** verschiebt:
- MP4/M4A: der Audio-Bereich ist ohne Atom-Parser nicht sicher bestimmbar. Dann
  wird die ganze Datei gehasht und der Container als `unbekannt` markiert.
- Alles andere wird exakt bestimmt.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path

BLOCK_BYTES = 64 * 1024
_HASH_KENNUNG = b"klangbild-audio-hash-v1"


@dataclass(frozen=True)
class Bereich:
    start: int
    ende: int
    container: str

    @property
    def laenge(self) -> int:
        return max(0, self.ende - self.start)


def _id3v2_groesse(kopf: bytes) -> int:
    """Groesse eines ID3v2-Tags inkl. Kopf (10 Byte). Syncsafe-Zahl."""
    if len(kopf) < 10 or kopf[:3] != b"ID3":
        return 0
    groesse = 0
    for byte in kopf[6:10]:
        groesse = (groesse << 7) | (byte & 0x7F)
    gesamt = 10 + groesse
    if kopf[5] & 0x10:  # Footer-Flag
        gesamt += 10
    return gesamt


def _ape_tag_groesse(dateiende: bytes) -> int:
    """Groesse eines APEv2-Tags am Dateiende (Footer 32 Byte)."""
    if len(dateiende) < 32:
        return 0
    fuss = dateiende[-32:]
    if fuss[:8] != b"APETAGEX":
        return 0
    groesse = struct.unpack_from("<I", fuss, 12)[0]
    flags = struct.unpack_from("<I", fuss, 20)[0]
    kopf_vorhanden = bool(flags & 0x80000000)
    return 32 + groesse + (32 if kopf_vorhanden else 0)


def _lyrics3_groesse(dateiende: bytes) -> int:
    if len(dateiende) >= 15 and dateiende[-15:-9] == b"LYRICS":
        try:
            return 6 + int(dateiende[-9:-1].decode("ascii", "ignore").strip() or 0) + 9
        except ValueError:
            return 0
    return 0


def _mp3_bereich(pfad: Path, groesse: int) -> Bereich:
    with pfad.open("rb") as datei:
        kopf = datei.read(10)
        start = _id3v2_groesse(kopf)
        datei.seek(max(0, groesse - 128))
        ende_roh = datei.read(128)
        datei.seek(max(0, groesse - 32))
        ende_kurz = datei.read(32)
    ende = groesse
    if len(ende_roh) == 128 and ende_roh[:3] == b"TAG":  # ID3v1
        ende -= 128
    if len(ende_kurz) == 32 and ende_kurz[:8] == b"APETAGEX":
        ende -= _ape_tag_groesse(ende_kurz)
    else:
        with pfad.open("rb") as datei:
            datei.seek(max(0, groesse - 256))
            ende_roh = datei.read(256)
        if b"LYRICS200" in ende_roh or b"LYRICSEND" in ende_roh:
            ende -= _lyrics3_groesse(ende_roh[-15:])
    return Bereich(start=start, ende=max(start, ende), container="mp3")


def _flac_bereich(pfad: Path) -> Bereich:
    with pfad.open("rb") as datei:
        kopf = datei.read(4)
        if kopf != b"fLaC":
            return Bereich(0, pfad.stat().st_size, "unbekannt")
        position = 4
        while True:
            datei.seek(position)
            block_kopf = datei.read(4)
            if len(block_kopf) < 4:
                break
            letzter = bool(block_kopf[0] & 0x80)
            laenge = int.from_bytes(block_kopf[1:4], "big")
            position += 4 + laenge
            if letzter:
                break
        start = position
    groesse = pfad.stat().st_size
    ende = groesse
    with pfad.open("rb") as datei:
        datei.seek(max(0, groesse - 128))
        ende_roh = datei.read(128)
    if len(ende_roh) == 128 and ende_roh[:3] == b"TAG":
        ende -= 128
    return Bereich(start=start, ende=max(start, ende), container="flac")


def _wav_bereich(pfad: Path) -> Bereich:
    with pfad.open("rb") as datei:
        kopf = datei.read(12)
        if len(kopf) < 12 or kopf[:4] != b"RIFF" or kopf[8:12] != b"WAVE":
            return Bereich(0, pfad.stat().st_size, "unbekannt")
        position = 12
        daten_start = daten_ende = None
        while True:
            datei.seek(position)
            chunk_kopf = datei.read(8)
            if len(chunk_kopf) < 8:
                break
            name = chunk_kopf[:4]
            laenge = int.from_bytes(chunk_kopf[4:8], "little")
            inhalt = position + 8
            if name == b"data":
                daten_start = inhalt
                daten_ende = inhalt + laenge
                break
            position = inhalt + laenge + (laenge & 1)  # Chunks sind wort-ausgerichtet
        if daten_start is None:
            return Bereich(0, pfad.stat().st_size, "unbekannt")
        return Bereich(start=daten_start, ende=daten_ende, container="wav")


def audio_bereich(pfad: str | Path) -> Bereich:
    """Bestimmt den Audio-Datenbereich einer Datei."""
    pfad = Path(pfad)
    groesse = pfad.stat().st_size
    endung = pfad.suffix.lower()
    if endung == ".mp3":
        return _mp3_bereich(pfad, groesse)
    if endung == ".flac":
        return _flac_bereich(pfad)
    if endung == ".wav":
        return _wav_bereich(pfad)
    return Bereich(start=0, ende=groesse, container="unbekannt")


def datei_hash(pfad: str | Path, block_bytes: int = BLOCK_BYTES) -> tuple[str, Bereich]:
    """Liefert (Hash, Bereich). Gleicher Inhalt -> gleicher Hash, egal wo die Datei liegt."""
    pfad = Path(pfad)
    bereich = audio_bereich(pfad)
    if bereich.laenge <= 0:
        return "", bereich

    mitte = bereich.start + bereich.laenge // 2
    stellen = sorted(
        {
            bereich.start,
            max(bereich.start, min(mitte - block_bytes // 2, bereich.ende - block_bytes)),
            max(bereich.start, bereich.ende - block_bytes),
        }
    )
    verdichter = hashlib.sha256()
    verdichter.update(_HASH_KENNUNG)
    verdichter.update(str(bereich.laenge).encode("ascii"))
    with pfad.open("rb") as datei:
        if bereich.laenge <= 4 * block_bytes:
            datei.seek(bereich.start)
            rest = bereich.laenge
            while rest > 0:
                brocken = datei.read(min(block_bytes, rest))
                if not brocken:
                    break
                verdichter.update(brocken)
                rest -= len(brocken)
        else:
            for stelle in stellen:
                datei.seek(stelle)
                brocken = datei.read(min(block_bytes, bereich.ende - stelle))
                verdichter.update(len(brocken).to_bytes(8, "big"))
                verdichter.update(brocken)
    return verdichter.hexdigest(), bereich
