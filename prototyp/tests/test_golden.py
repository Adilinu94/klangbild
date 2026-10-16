"""Golden-Format und deterministischer Export, ohne Musik/Modelldownload."""

import hashlib
import json

import numpy as np
import pytest

from klangbild import golden


def test_export_is_byte_identical_and_complete(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    manifest = golden.export(first, real_count=0, include_beats=False)
    golden.export(second, real_count=0, include_beats=False)
    names = sorted(p.name for p in first.iterdir())
    assert names == sorted(p.name for p in second.iterdir())
    for name in names:
        assert (first / name).read_bytes() == (second / name).read_bytes(), name
    for family in ("kurven", "band", "mischen", "huellen", "sweep", "nass", "hall", "deckeln", "loop",
                   "loopwahl", "introloop", "eigen", "limiter", "warp", "regulaer", "ausstieg", "einstieg",
                   "backen", "profil", "regie", "loopguete", "pruefen", "sortiere", "rangliste", "einstellungen",
                   "hash", "key", "lufs", "energie", "welle"):
        assert any(c.startswith(family + "_") for c in manifest["cases"]), family
    assert len(manifest["cases"]) == len(set(manifest["cases"]))
    for field in ("lautstaerke", "eq", "filter", "effekt", "effekt_ein", "loop"):
        for choice in golden.einstellungen.AUSWAHL[field]:
            assert f"huellen_{field}_{choice}" in manifest["cases"]

    def check(value):
        if isinstance(value, dict):
            if value.get("dtype") == "float32-le":
                raw = (first / value["file"]).read_bytes()
                assert hashlib.sha256(raw).hexdigest() == value["sha256"]
                assert len(raw) == value["count"] * 4
                assert int(np.prod(value["shape"])) == value["count"]
            for item in value.values():
                check(item)
        elif isinstance(value, list):
            for item in value:
                check(item)

    for name in names:
        if name.endswith(".json"):
            check(json.loads((first / name).read_text(encoding="utf-8")))
    assert (first / "hash_mp3.json").read_text() != (first / "hash_mp3_id3.json").read_text()
    bare = json.loads((first / "hash_mp3.json").read_text())["expected"]["hash"]
    tagged = json.loads((first / "hash_mp3_id3.json").read_text())["expected"]["hash"]
    assert bare == tagged


def test_writer_stereo_little_endian_and_deduplication(tmp_path):
    w = golden.Writer(tmp_path)
    x = np.array([[0, 1], [-0.5, 0.25]], dtype=np.float32)
    first = w.array("first.f32", x)
    assert w.array("duplicate.f32", x.copy()) == first
    assert (tmp_path / "first.f32").read_bytes().hex() == "000000000000803f000000bf0000803e"
    assert not (tmp_path / "duplicate.f32").exists()
    w.json("special.json", {"silent": float("-inf")})
    assert json.loads((tmp_path / "special.json").read_text())["silent"] == "-inf"


def test_writer_refuses_existing_files(tmp_path):
    (tmp_path / "user.json").write_text("unchanged")
    with pytest.raises(ValueError, match="leer"):
        golden.Writer(tmp_path)
    assert (tmp_path / "user.json").read_text() == "unchanged"
