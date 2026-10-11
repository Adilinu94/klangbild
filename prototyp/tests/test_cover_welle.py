"""Tests fuer cover.py (ID3/FLAC-Bilder) und welle.py (farbige Wellenform)."""

from __future__ import annotations

import io

import numpy as np
from PIL import Image

from klangbild import cover, welle


def _jpeg() -> bytes:
    puffer = io.BytesIO()
    Image.new("RGB", (600, 400), (200, 30, 30)).save(puffer, "JPEG")
    return puffer.getvalue()


def _syncsafe(n: int) -> bytes:
    return bytes([(n >> 21) & 0x7F, (n >> 14) & 0x7F, (n >> 7) & 0x7F, n & 0x7F])


def test_mp3_apic_v24(tmp_path):
    bild = _jpeg()
    apic = b"\x03" + b"image/jpeg\x00" + b"\x03" + b"Cover\x00" + bild
    frame = b"APIC" + _syncsafe(len(apic)) + b"\x00\x00" + apic
    tag = b"ID3\x04\x00\x00" + _syncsafe(len(frame)) + frame
    datei = tmp_path / "a.mp3"
    datei.write_bytes(tag + b"\xff\xfb" + bytes(100))
    assert cover.eingebettet(datei) == bild
    vorschau = cover.vorschau(1, datei, cache=tmp_path / "c")
    assert max(Image.open(io.BytesIO(vorschau)).size) == cover.KANTE


def test_mp3_apic_v23_utf16_beschreibung(tmp_path):
    bild = _jpeg()
    apic = b"\x01" + b"image/jpeg\x00" + b"\x03" + "Fr".encode("utf-16") + b"\x00\x00" + bild
    frame = b"APIC" + len(apic).to_bytes(4, "big") + b"\x00\x00" + apic
    tag = b"ID3\x03\x00\x00" + _syncsafe(len(frame)) + frame
    datei = tmp_path / "b.mp3"
    datei.write_bytes(tag + bytes(100))
    assert cover.eingebettet(datei) == bild


def test_flac_picture_und_ohne_cover(tmp_path):
    bild = _jpeg()
    mime = b"image/jpeg"
    block = ((3).to_bytes(4, "big") + len(mime).to_bytes(4, "big") + mime + (0).to_bytes(4, "big")
             + bytes(16) + len(bild).to_bytes(4, "big") + bild)
    streaminfo = bytes([0]) + (34).to_bytes(3, "big") + bytes(34)
    picture = bytes([0x80 | 6]) + len(block).to_bytes(3, "big") + block
    datei = tmp_path / "c.flac"
    datei.write_bytes(b"fLaC" + streaminfo + picture)
    assert cover.eingebettet(datei) == bild
    ohne = tmp_path / "d.flac"
    ohne.write_bytes(b"fLaC" + bytes([0x80]) + (34).to_bytes(3, "big") + bytes(34))
    assert cover.eingebettet(ohne) is None
    assert cover.vorschau(9, ohne, cache=tmp_path / "c") is None


def test_welle_bass_rot_mitten_gruen_hoehen_blau():
    t = np.arange(22050 * 2) / 22050
    for f, kanal in ((60, "r"), (1000, "g"), (6000, "b")):
        rauschen = 0.001 * np.random.default_rng(0).normal(size=t.size)
        w = welle.berechnen(np.concatenate([np.sin(2 * np.pi * f * t), rauschen]).astype(np.float32))
        mittel = {k: w[k][:150].mean() for k in "rgb"}
        assert max(mittel, key=mittel.get) == kanal and mittel[kanal] > 200
