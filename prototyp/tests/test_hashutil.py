"""Tests fuer den Hash ueber die Audiodaten (ADR-013).

Der Kern in einem Satz: **Tags aendern darf den Hash nicht aendern**, der
Audioinhalt schon. Die Testdateien werden als reine Bytes gebaut – kein Encoder,
keine Beispieldatei, gleiche Aussage.
"""

from __future__ import annotations

import numpy as np

from klangbild import hashutil


def _mp3(payload: bytes, id3v1: bytes = b"", ape: bool = False) -> bytes:
    tag_koerper = b"\x00" * 100
    groesse = len(tag_koerper)
    syncsafe = bytes(
        [(groesse >> 21) & 0x7F, (groesse >> 14) & 0x7F, (groesse >> 7) & 0x7F, groesse & 0x7F]
    )
    daten = b"ID3" + bytes([3, 0, 0]) + syncsafe + tag_koerper + payload
    if id3v1:
        daten += id3v1
    if ape:
        koerper = b"\x00" * 20
        fuss = (
            b"APETAGEX"
            + (2000).to_bytes(4, "little")
            + len(koerper).to_bytes(4, "little")
            + (0).to_bytes(4, "little")
            + (0).to_bytes(4, "little")
            + b"\x00" * 8
        )
        daten += koerper + fuss
    return daten


def _flac(payload: bytes) -> bytes:
    block = bytes([0x80]) + (34).to_bytes(3, "big") + b"\x00" * 34  # STREAMINFO, letzter Block
    return b"fLaC" + block + payload


def _wav(payload: bytes) -> bytes:
    fmt = b"fmt " + (16).to_bytes(4, "little") + b"\x00" * 16
    daten = b"data" + len(payload).to_bytes(4, "little") + payload
    inhalt = b"WAVE" + fmt + daten
    return b"RIFF" + len(inhalt).to_bytes(4, "little") + inhalt


def _schreiben(tmp_path, name, daten: bytes):
    pfad = tmp_path / name
    pfad.write_bytes(daten)
    return pfad


def test_mp3_bereich_ueberspringt_tags(tmp_path):
    payload = bytes(range(256)) * 40
    pfad = _schreiben(tmp_path, "a.mp3", _mp3(payload))
    bereich = hashutil.audio_bereich(pfad)
    assert bereich.container == "mp3"
    assert bereich.start == 110  # 10 Byte Kopf + 100 Byte Tag
    assert bereich.ende == 110 + len(payload)


def test_mp3_retagging_behaelt_hash(tmp_path):
    payload = bytes(range(256)) * 40
    version1 = _schreiben(tmp_path, "v1.mp3", _mp3(payload, id3v1=b"TAG" + b"alt".ljust(125, b"\x00")))
    version2 = _schreiben(tmp_path, "v2.mp3", _mp3(payload, id3v1=b"TAG" + b"neu".ljust(125, b"\x00")))
    hash1, _ = hashutil.datei_hash(version1)
    hash2, _ = hashutil.datei_hash(version2)
    assert hash1 == hash2 and hash1 != ""


def test_mp3_anderer_audioinhalt_aendert_hash(tmp_path):
    payload = bytes(range(256)) * 40
    anders = bytearray(payload)
    anders[1000] ^= 0xFF
    a = _schreiben(tmp_path, "a.mp3", _mp3(payload))
    b = _schreiben(tmp_path, "b.mp3", _mp3(bytes(anders)))
    assert hashutil.datei_hash(a)[0] != hashutil.datei_hash(b)[0]


def test_mp3_ape_tag_wird_abgezogen(tmp_path):
    payload = bytes(range(256)) * 40
    ohne = _schreiben(tmp_path, "ohne.mp3", _mp3(payload))
    mit = _schreiben(tmp_path, "mit.mp3", _mp3(payload, ape=True))
    assert hashutil.audio_bereich(mit).ende == hashutil.audio_bereich(ohne).ende
    assert hashutil.datei_hash(mit)[0] == hashutil.datei_hash(ohne)[0]


def test_flac_bereich_beginnt_nach_metadaten(tmp_path):
    payload = bytes(range(256)) * 40
    pfad = _schreiben(tmp_path, "a.flac", _flac(payload))
    bereich = hashutil.audio_bereich(pfad)
    assert bereich.container == "flac"
    assert bereich.start == 4 + 4 + 34


def test_wav_bereich_findet_data_chunk(tmp_path):
    payload = bytes(range(256)) * 40
    pfad = _schreiben(tmp_path, "a.wav", _wav(payload))
    bereich = hashutil.audio_bereich(pfad)
    assert bereich.container == "wav"
    assert bereich.start == 44
    assert bereich.ende == 44 + len(payload)


def test_verschobene_datei_gleicher_hash(tmp_path):
    """Gleicher Inhalt an anderem Pfad -> gleicher Hash (ADR-007)."""
    payload = bytes(range(256)) * 40
    ordner = tmp_path / "tief" / "tiefer"
    ordner.mkdir(parents=True)
    a = _schreiben(tmp_path, "x.mp3", _mp3(payload))
    b = _schreiben(ordner, "x.mp3", _mp3(payload))
    assert hashutil.datei_hash(a)[0] == hashutil.datei_hash(b)[0]
