"""Python-Referenzdaten fuer den Android-Port (BAUPLAN-ANDROID T0.2).

JSON bleibt strikt: nicht endliche Skalare werden als "-inf"/"inf"/"nan"
geschrieben. Grosse Float-Arrays liegen little endian, C-order (Stereo L/R
interleaved) in f32. Jeder Verweis enthaelt Form, Offset und SHA-256.
Musikausschnitte bleiben lokal; der Export liest die Bibliothek nur.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import platform
import sqlite3
import struct
from dataclasses import asdict, is_dataclass
from pathlib import Path

import numpy as np

from . import config, einstellungen, energy, hashutil, keyestimate, lufs, mix, plan, profil, regie, welle
from . import uebergang as u
from .einstellungen import Einstellungen

FORMAT_VERSION = 1
SEED = 20261014
RATE = u.RATE


class Writer:
    """Ein Fall pro JSON; identische binaere Arrays werden wiederverwendet."""

    def __init__(self, target: Path):
        self.target = Path(target)
        self.target.mkdir(parents=True, exist_ok=True)
        if any(self.target.iterdir()):
            raise ValueError("Golden-Ziel muss leer sein (keine fremden Referenzen ueberschreiben).")
        self.cases: list[str] = []
        self.files: dict[str, str] = {}
        self.arrays: dict[tuple[str, tuple[int, ...]], dict] = {}
        self.gaps: list[str] = []

    def blob(self, name: str, data: bytes) -> str:
        (self.target / name).write_bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        self.files[name] = digest
        return digest

    def array(self, name: str, values: np.ndarray) -> dict:
        array = np.ascontiguousarray(values, dtype="<f4")
        data = array.tobytes(order="C")
        digest = hashlib.sha256(data).hexdigest()
        key = (digest, array.shape)
        if key not in self.arrays:
            self.blob(name, data)
            self.arrays[key] = {"file": name, "dtype": "float32-le", "shape": list(array.shape),
                                "offset": 0, "count": array.size, "sha256": digest}
        return self.arrays[key].copy()

    def encode(self, value, name: str):
        if is_dataclass(value):
            value = asdict(value)
        if isinstance(value, np.ndarray):
            # Integers and float64 plan/clock values stay lossless in JSON.
            if value.dtype == np.float32 and value.size > 256:
                return self.array(name + ".f32", value)
            return self.encode(value.tolist(), name)
        if isinstance(value, np.generic):
            return self.encode(value.item(), name)
        if isinstance(value, float) and not math.isfinite(value):
            return "nan" if math.isnan(value) else "inf" if value > 0 else "-inf"
        if isinstance(value, dict):
            return {str(k): self.encode(v, name + "_" + str(k)) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self.encode(v, name + f"_{i}") for i, v in enumerate(value)]
        if isinstance(value, set):
            return self.encode(sorted(value), name)
        return value

    def json(self, name: str, value) -> None:
        data = json.dumps(self.encode(value, name.removesuffix(".json")), ensure_ascii=False,
                          sort_keys=True, indent=2, allow_nan=False) + "\n"
        self.blob(name, data.encode("utf-8"))

    def case(self, name: str, function: str, inputs: dict, expected, tolerance: str = "values") -> None:
        self.json(name + ".json", {"format_version": FORMAT_VERSION, "function": function,
                                  "inputs": inputs, "expected": expected, "tolerance": tolerance})
        self.cases.append(name)

    def finish(self, real_tracks: list[int]) -> dict:
        sources = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in sorted(Path(__file__).parent.glob("*.py"))}
        versions = {name: importlib.metadata.version(name)
                    for name in ("numpy", "scipy", "soxr", "soundfile", "python-stretch")}
        manifest = {"format_version": FORMAT_VERSION, "seed": SEED, "python": platform.python_version(),
                    "packages": versions, "sources": sources, "cases": sorted(self.cases),
                    "files": dict(sorted(self.files.items())), "real_tracks": real_tracks, "gaps": self.gaps,
                    "tolerances": {"values": {"absolute": 1e-6},
                                   "dsp": {"absolute": 1e-4, "rms_dbfs_below": -80},
                                   "reverb": {"rms_dbfs_below": -70},
                                   "warp": {"length_exact": True, "click_ms": 1,
                                            "rms_per_bar_db": 0.2, "correlation_min": 0.99}}}
        self.json("manifest.json", manifest)
        return manifest


def signal(seconds: float, variant: int = 0) -> np.ndarray:
    """Sinus, feste Rauschfolge und Klicks; Kanaele bewusst verschieden."""
    n = round(seconds * RATE)
    t = np.arange(n, dtype=np.float64) / RATE
    rng = np.random.default_rng(SEED + variant)
    left = 0.18 * np.sin(2 * np.pi * (80 + 17 * variant) * t)
    right = 0.16 * np.sin(2 * np.pi * (440 + 33 * variant) * t + 0.3)
    x = np.stack([left, right], axis=1) + 0.02 * rng.standard_normal((n, 2))
    for k, start in enumerate(range(0, n, RATE // 2)):
        length = min(128, n - start)
        x[start:start + length] += (0.4 if k % 4 == 0 else 0.2) * np.exp(-np.arange(length) / 18)[:, None]
    return x.astype(np.float32)


def _profile_data(p: profil.Profil) -> dict:
    # Do not round through als_dict: expected results must match the supplied inputs.
    return {"takte": p.takte, "baender": p.baender, "gesamt": p.gesamt, "stems": p.stems,
            "raster_ok": p.raster_ok, "dauer": p.dauer, "chroma": p.chroma}


def _derived(p: profil.Profil) -> dict:
    return {"gesang": p.gesang(), "drums": p.drums(), "bass": p.bass(), "dichte": p.dichte(),
            "versatz": p.versatz(), "etiketten": p.etiketten(),
            "phrase_start": [p.phrase_start(i) for i in range(12)],
            "phrase_ab": [p.phrase_ab(i) for i in range(p.n)]}


def _synthetic_profile(variant: int, with_stems: bool = True) -> profil.Profil:
    levels = np.array([-22, -18, -9, -10, -16, -9, -10, -22], dtype=float)
    total = np.repeat(levels, 8)
    bands = np.stack([total - 2, total - 5, total - 9], axis=1)
    stem_levels = None
    if with_stems:
        vocals = np.full(len(total), -65.0)
        vocals[16 + variant * 8:32 + variant * 8] = total[16 + variant * 8:32 + variant * 8] - 3
        drums = total - 3
        drums[32:40] = -60
        stem_levels = {"vocals": vocals, "drums": drums, "bass": total - 4, "other": total - 6}
    chroma = np.zeros((len(total), 12))
    chroma[:, [0, 4, 7]] = 1 / 3
    return profil.Profil(np.arange(len(total)) * 2.0, bands, total, stem_levels,
                         np.ones(len(total), bool), len(total) * 2.0, chroma)


def _dsp(w: Writer) -> None:
    a, b = signal(8), signal(8, 1)
    ar, br = w.array("signal_a.f32", a), w.array("signal_b.f32", b)
    w.case("reader_dummy", "identity", {"audio": w.array("reader_dummy.f32", np.array([[0, 1], [-0.5, 0.25]], np.float32))},
           {"frames": 2, "channels": 2, "values": [0.0, 1.0, -0.5, 0.25]})
    w.case("kurven_basis", "mix.equal_power_blende", {"n": 64}, mix.equal_power_blende(64))
    for rate in (44100, 22050):
        w.json(f"sos_{rate}.json", {str(hz): {kind: mix._sos(kind, hz, rate)
                                              for kind in ("low", "high")}
                                  for hz in (200, 2000, 2500, 3000, 5000)})
    ir = u._hall_ir()
    w.case("hall_ir", "uebergang._hall_ir", {}, w.array("hall_ir.f32", ir), "reverb")
    for hz in (200, 2000, 2500):
        w.case(f"band_{hz}", "mix.band_teilen", {"signal": ar, "rate": RATE, "trenn_hz": hz},
               mix.band_teilen(a, RATE, hz), "dsp")
    for n in (0, 1, 8, 15):
        w.case(f"band_kurz_{n}", "mix.band_teilen", {"signal": a[:n], "rate": RATE, "trenn_hz": 200},
               mix.band_teilen(a[:n], RATE, 200), "dsp")
    for art in ("eq", "filter", "echo", "schnitt", "crossfade"):
        for bars in (1, 4, 16):
            w.case(f"mischen_{art}_{bars}", "uebergang.mischen", {"art": art, "a": ar, "b": br, "takte": bars},
                   u.mischen(art, a, b, bars), "dsp")
        w.case(f"kurven_{art}", "uebergang.kurven", {"art": art, "takte": 16}, u.kurven(art, 16))
    for field in ("lautstaerke", "eq", "filter", "effekt", "effekt_ein", "loop", "trick"):
        for value in einstellungen.AUSWAHL[field]:
            e = Einstellungen(art="eigen", **{field: value})
            w.case(f"huellen_{field}_{value}", "uebergang._huellen",
                   {"e": e, "takte": 16, "n": 1000, "kante": 0.001}, u._huellen(e, 16, 1000, 0.001))
    amount = np.linspace(0, 1, len(a), dtype=np.float32)
    for art in ("tp", "hp"):
        for reso in (False, True):
            w.case(f"sweep_{art}_{int(reso)}", "uebergang._sweep",
                   {"x": ar, "menge": amount, "art": art, "reso": reso}, u._sweep(a, amount, art, reso), "dsp")
    send = a[:RATE // 4]
    for typ in ("hall",) + einstellungen.EFFEKT_TYPEN[1:]:
        w.case(f"nass_{typ}", "uebergang._nass", {"typ": typ, "send": send, "schlag_n": RATE / 2},
               u._nass(typ, send, RATE / 2), "reverb" if typ == "hall" else "dsp")
    tn = np.arange(5) * (len(a) // 4)
    for gain in (1, 2, 4):
        w.case(f"deckeln_{gain}", "uebergang._deckeln", {"y": a * gain, "ra": ar, "rb": br, "takt_n": tn},
               u._deckeln(a * gain, a, b, tn), "dsp")
    for size in ("1", "2", "4", "8", "16", "32", "rolle"):
        e = Einstellungen(art="eigen", loop=size)
        lp = u._loop_plan(e, 4)
        w.case(f"loop_{size}", "uebergang._loopen", {"a": ar, "takt_n": tn, "plan": lp}, u._loopen(a, tn, lp), "dsp")
    for name, avoid in (("frei", None), ("gesang", np.array([1, 1, 0, 0])), ("alle", np.ones(4))):
        w.case(f"loopwahl_{name}", "uebergang.loop_waehlen", {"a": ar, "takt_n": tn, "meiden": avoid},
               u.loop_waehlen(a, tn, avoid))
    for repeats in (1, 2):
        audio, grid, back = u._intro_loop(b, tn / RATE, 0, 1, repeats)
        points = np.linspace(-1, 15, 33)
        w.case(f"introloop_{repeats}", "uebergang._intro_loop",
               {"b_audio": br, "bbar": tn / RATE, "j0": 0, "k": 1, "mal": repeats, "points": points},
               {"audio": audio, "raster": grid, "rueck": back(points)}, "dsp")
    recipes = {"profi_eq": {"eq": "profi"}, "outro_loop": {"eq": "profi", "loop": "8"},
               "echo_out": {"lautstaerke": "letzter_takt", "effekt": "echo75_ende_aus"},
               "hall": {"effekt": "hall_ende_aus", "filter": "tp_aus"},
               "rolle": {"loop": "rolle", "lautstaerke": "hart_aus"}}
    recipes.update({"trick_" + v: {"trick": v, "lautstaerke": "drop"} for v in einstellungen.TRICK[1:]})
    for name, fields in recipes.items():
        e = Einstellungen(art="eigen", **fields)
        w.case(f"eigen_{name}", "uebergang.mischen_eigen", {"a": ar, "b": br, "e": e, "takt_n": tn},
               u.mischen_eigen(a, b, e, tn), "reverb" if "hall" in e.effekt else "dsp")
        w.case(f"kurven_eigen_{name}", "uebergang.kurven", {"art": "eigen", "takte": 4, "e": e}, u.kurven("eigen", 4, e))
    # Peaks on both sides of the limiter's 65536-frame block boundary.
    peaks = a.copy()
    peaks[[0, 65535, 65536, len(a) - 1]] = [2, -2]
    for name, x, end in (("stille", np.zeros_like(a), len(a)), ("leise", a, len(a)),
                         ("spitzen", peaks, len(peaks)), ("teil", peaks, 65536), ("leer", a, 0)):
        y = x.copy()
        u._begrenzen(y, end)
        w.case(f"limiter_{name}", "uebergang._begrenzen", {"x": x, "bis": end, "decke": u.DECKE}, y, "dsp")
    source = np.array([0, 2, 4, 6, 8], dtype=float)
    dest = np.array([0, 1.9, 3.82, 5.77, 7.75])
    for keylock in (False, True):
        w.case("warp_keylock" if keylock else "warp_vinyl", "uebergang.warp",
               {"audio": ar, "quell_s": source, "ziel_s": dest, "keylock": keylock},
               u.warp(a, source, dest, keylock), "warp" if keylock else "dsp")
    _planning(w, a, b)


def _planning(w: Writer, a_audio: np.ndarray, b_audio: np.ndarray) -> None:
    a = u.Eintrag(90001, "synthetic-a", 120, "8B", [0, 2, 4, 6], abschnitte=[2, 6])
    b = u.Eintrag(90002, "synthetic-b", 123, "9B", [0, 240 / 123, 480 / 123, 720 / 123], abschnitte=[2, 6])
    spur = u.Spur.roh(a, a_audio)
    for name, beats, bpm in (("leer", [], 0), ("normal", a.downbeats, 120),
                             ("versatz", [0.3, 2.31, 4.28, 6.32], 120), ("ausreisser", [0, 2, 5, 6], 120)):
        w.case(f"regulaer_{name}", "uebergang.regulaer", {"downbeats": beats, "bpm": bpm, "bis_s": 12},
               u.regulaer(beats, bpm, 12))
    for choice in einstellungen.AUSWAHL["ausstieg"]:
        e = Einstellungen(ausstieg=choice, takte=1)
        w.case(f"ausstieg_{choice}", "uebergang.ausstieg",
               {"eintrag": a, "frames": len(a_audio), "orig": spur.orig, "buf": spur.buf, "e": e, "takte": 1, "ab_s": 1},
               u.ausstieg(spur, e, 1, 1))
    for choice in ("intro", "drop"):
        e = Einstellungen(einstieg=choice)
        w.case(f"einstieg_{choice}", "uebergang.einstieg", {"b": b, "b_samples": len(b_audio), "e": e},
               u.einstieg(b, len(b_audio), e))
    for name, fields in (("vinyl", {"keylock": False}), ("keylock", {"keylock": True}),
                         ("echo", {"art": "echo", "keylock": False}),
                         ("introloop", {"art": "eigen", "keylock": False, "loop_ein": 1, "loop_ein_mal": 1})):
        e = Einstellungen(takte=1, stems=False, ausstieg="phrase", **fields)
        baked = u.backen(spur, b, b_audio, e, 0, aus_s=2, ein_s=0)
        w.case(f"backen_{name}", "uebergang.backen",
               {"a": a, "a_audio": a_audio, "b": b, "b_audio": b_audio, "e": e, "ab_s": 0, "aus_s": 2, "ein_s": 0},
               {"start_n": baked.start_n, "audio": baked.spur.puffer, "orig": baked.spur.orig,
                "buf": baked.spur.buf, "info": baked.info}, "warp")
    profiles = [_synthetic_profile(0), _synthetic_profile(1), _synthetic_profile(0, False)]
    for i, p in enumerate(profiles):
        w.case(f"profil_synthetic_{i}", "profil.Profil", {"profile": _profile_data(p)}, _derived(p))
    for style in ("kurz", "ausgewogen", "lang"):
        for share in ("schnell", "lang"):
            e = Einstellungen(modus=style, spielanteil=share)
            w.case(f"regie_synthetic_{style}_{share}", "regie.planen",
                   {"a": a, "pa": _profile_data(profiles[0]), "b": b, "pb": _profile_data(profiles[1]),
                    "e": e, "ab_s": 0, "sync": True, "harmonisch": True, "stems_da": True},
                   regie.planen(a, profiles[0], b, profiles[1], e, 0, True, True, stems_da=True))
    calculated = profil.berechnen(a, a_audio)
    w.case("profil_berechnen", "profil.berechnen", {"eintrag": a, "audio": a_audio}, _profile_data(calculated))
    w.case("loopguete_synthetic", "regie._loop_guete",
           {"pa": _profile_data(calculated), "i": 0, "L": 2, "a_audio": a_audio, "rate": RATE},
           regie._loop_guete(calculated, 0, 2, a_audio, RATE))
    for name, gain, recipe in (("normal", 1, "profi_eq"), ("laut", 8, "profi_eq"),
                               ("loch", 0, "profi_eq"), ("ausnahme", 0, "echo_out")):
        w.case(f"pruefen_{name}", "regie.pruefen",
               {"blende": a_audio * gain, "rate": RATE, "n_takte": 4, "pa": _profile_data(calculated),
                "pb": _profile_data(calculated), "aus_s": 0, "ein_s": 0, "gain_a": 0, "gain_b": 0, "rezept": recipe},
               regie.pruefen(a_audio * gain, RATE, 4, calculated, calculated, 0, 0, 0, 0, recipe))
    tracks = [plan.Track(i, f"synthetic-{i}", 118 + i % 13, f"{1 + i % 12}A", -12 - i % 5) for i in range(1, 333)]
    w.case("sortiere_332", "plan.sortiere_alle", {"tracks": tracks, "max_bpm": 5, "harmonie": "locker"}, plan.sortiere_alle(tracks, 5))
    for harmony in ("streng", "locker", "aus"):
        w.case(f"rangliste_{harmony}", "plan.rangliste",
               {"aktuell": tracks[0], "kandidaten": tracks[1:20], "max_bpm": 5, "harmonie": harmony, "n": 6},
               [t.id for t in plan.rangliste(tracks[0], tracks[1:20], 5, harmony)])
    for field, choices in einstellungen.AUSWAHL.items():
        for choice in choices:
            w.case(f"einstellungen_{field}_{choice}", "einstellungen.aus_dict", {"roh": {field: choice}}, einstellungen.aus_dict({field: choice}))
    for name, raw in (("leer", {}), ("ungueltig", {"takte": 3, "keylock": None, "modus": "falsch", "max_bpm": "oops"}),
                       ("grenzen", {"max_bpm": 50, "bass_takt": -90, "loop_ein": 99}), ("typen", {"takte": "8", "max_bpm": "2.5"})):
        w.case(f"einstellungen_{name}", "einstellungen.aus_dict", {"roh": raw}, einstellungen.aus_dict(raw))


def _analysis(w: Writer, name: str, audio: np.ndarray) -> None:
    mono = audio.mean(axis=1).astype(np.float32)
    # Exact soxr input is stored too: Android's decoder/resampler is not under test here.
    import soxr

    low = soxr.resample(mono, RATE, 22050).astype(np.float32)
    ref = w.array(name + "_mono.f32", low)
    for profile in ("ensemble", "krumhansl", "aarden", "temperley"):
        w.case(f"key_{name}_{profile}", "keyestimate.tonart_schaetzen", {"signal": ref, "rate": 22050, "profile": profile},
               keyestimate.tonart_schaetzen(low, 22050, profile))
    w.case(f"lufs_{name}", "lufs", {"signal": audio, "rate": RATE},
           {"integrated": lufs.integrierte_lautheit(audio, RATE), "true_peak": lufs.true_peak_dbtp(audio, RATE)})
    w.case(f"energie_{name}", "energy", {"signal": ref, "rate": 22050},
           {"rms": energy.rms_kurve(low, 22050), "novelty": energy.neuheits_kurve(low, 22050),
            "sections": energy.abschnitte(low, 22050)})
    w.case(f"welle_{name}", "welle.berechnen", {"mono": ref, "rate": 22050}, welle.berechnen(low, 22050))


def _hashes(w: Writer) -> None:
    payload = bytes(range(256)) * 1024
    # ID3 variants must not change the sampled audio hash.
    for name, data in (("mp3", payload), ("mp3_id3", b"ID3\x04\x00\x00\x00\x00\x00\x04tags" + payload + b"TAG" + bytes(125)),
                       ("wav", b"RIFF" + struct.pack("<I", len(payload) + 12) + b"WAVEdata" + struct.pack("<I", len(payload)) + payload)):
        filename = f"hash_{name}." + ("wav" if name == "wav" else "mp3")
        w.blob(filename, data)
        path = w.target / filename
        digest, region = hashutil.datei_hash(path)
        w.case(f"hash_{name}", "hashutil", {"file": filename}, {"bereich": region, "hash": digest})


def _real(w: Writer, count: int) -> list[tuple[u.Eintrag, profil.Profil, np.ndarray]]:
    from .audioio import decodieren_stereo

    if not config.DATENBANK.exists():
        w.gaps.append("Echte Titel: Desktop-Datenbank fehlt.")
        return []
    conn = sqlite3.connect(config.DATENBANK.as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT t.id,t.pfad,f.bpm,f.key_camelot,f.downbeats_json FROM tracks t "
                            "JOIN features f ON f.track_id=t.id WHERE f.analyse_version=? AND f.bpm>0 ORDER BY t.id",
                            (config.ANALYSE_VERSION,)).fetchall()
    finally:
        conn.close()
    selected = []
    for row in rows:
        p = profil.gespeichert(row["id"])
        if p is None or not Path(row["pfad"]).is_file():
            continue
        decoded = decodieren_stereo(row["pfad"], RATE)
        full = decoded.daten
        assert decoded.rate == RATE
        # A deterministic 8-second excerpt; strip title/path from distributable metadata.
        start = min(round(p.takte[max(0, p.n // 2)] * RATE), max(0, len(full) - 8 * RATE))
        audio = full[max(0, start):max(0, start) + 8 * RATE].copy()
        entry = u.Eintrag(row["id"], f"local-track-{row['id']}", row["bpm"], row["key_camelot"], json.loads(row["downbeats_json"]))
        w.case(f"profil_{entry.id}", "profil.Profil", {"profile": _profile_data(p)}, _derived(p))
        _analysis(w, f"real_{entry.id}", audio)
        selected.append((entry, p, audio))
        if len(selected) >= count:
            break
    if len(selected) < count:
        w.gaps.append(f"Echte Titel: {len(selected)}/{count} mit vorhandenem Profil und Audio.")
    for (a, pa, _), (b, pb, _) in zip(selected, selected[1:]):
        for style in ("kurz", "ausgewogen", "lang"):
            for share in ("schnell", "lang"):
                e = Einstellungen(modus=style, spielanteil=share)
                sync, harm = abs(a.bpm - b.bpm) <= e.max_bpm, u._harmonisch(a.camelot, b.camelot)
                stems = pa.stems is not None and pb.stems is not None
                w.case(f"regie_{a.id}_{b.id}_{style}_{share}", "regie.planen",
                       {"a": a, "pa": _profile_data(pa), "b": b, "pb": _profile_data(pb), "e": e,
                        "ab_s": 0, "sync": sync, "harmonisch": harm, "stems_da": stems},
                       regie.planen(a, pa, b, pb, e, 0, sync, harm, stems_da=stems))
    return selected


def _beatthis(w: Writer, signals: list[tuple[str, np.ndarray]]) -> None:
    from . import beats

    checkpoint = config.BEAT_THIS_CHECKPOINT
    if not checkpoint.is_file() or not beats.verfuegbar():
        w.gaps.append("Beat This!: lokaler final0-Checkpoint oder Python-Paket fehlt; kein Download gestartet.")
        return
    import soxr
    import torch
    from beat_this.inference import Audio2Beats

    # CPU, a fixed reduction order and deterministic kernels; no GPU-dependent output.
    old_threads = torch.get_num_threads()
    old_deterministic = torch.are_deterministic_algorithms_enabled()
    old_warn = torch.is_deterministic_algorithms_warn_only_enabled()
    try:
        torch.set_num_threads(1)
        torch.use_deterministic_algorithms(True)
        model = Audio2Beats(checkpoint_path=str(checkpoint), device="cpu", dbn=False)
        digest = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
        for name, audio in signals:
            mono = soxr.resample(audio.mean(axis=1), RATE, 22050).astype(np.float32)
            with torch.inference_mode():
                beat, downbeat = model(mono, 22050)
            w.case(f"beatthis_{name}", "beat_this.Audio2Beats",
                   {"signal": mono, "rate": 22050, "checkpoint": "final0", "checkpoint_sha256": digest, "dbn": False},
                   {"beats": np.asarray(beat), "downbeats": np.asarray(downbeat)})
    finally:
        torch.set_num_threads(old_threads)
        torch.use_deterministic_algorithms(old_deterministic, warn_only=old_warn)
    w.gaps.append("Beat This! small0/ONNX-Paritaet bleibt Tor G-A (M10); diese Referenz nutzt Desktop final0.")


def export(target: Path, real_count: int = 5, include_beats: bool = True,
           synthetic: bool = True) -> dict:
    """Schreibt einen Golden-Satz nach `target`.

    `synthetic=True` schreibt die synthetischen Faelle (Sin/Rauschen mit festem
    Seed, Klickspur) - das ist der committbare Anteil. `real_count>0` ergaenzt
    Ausschnitte echter Bibliothekstitel; die gehoeren NIE ins oeffentliche Repo
    (Musik-Lizenz) und landen darum in einem eigenen, ignorierten Ordner
    (`synthetic=False`, z. B. testdata/golden-real).
    """
    w = Writer(target)
    if synthetic:
        _dsp(w)
        _hashes(w)
        for name, audio in (("synthetic", signal(8)), ("stille", np.zeros((RATE, 2), np.float32)),
                            ("kurz", signal(0.01))):
            _analysis(w, name, audio)
    selected = _real(w, real_count) if real_count else []
    if include_beats:
        signals = ([("synthetic", signal(16))] if synthetic else [])
        signals += [(f"real_{e.id}", audio) for e, _, audio in selected]
        if signals:
            _beatthis(w, signals)
    else:
        w.gaps.append("Beat This!-Inferenz fuer diesen Testlauf deaktiviert.")
    return w.finish([e.id for e, _, _ in selected])


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path, help="Leerer Zielordner, z. B. ../android/testdata/golden")
    parser.add_argument(
        "--mit-echten-titeln", action="store_true",
        help="Zusaetzlich Ausschnitte aus echten Titeln der Bibliothek exportieren (nur lokal, "
             "wegen Musik-Lizenz NIE ins oeffentliche Repo committen).",
    )
    parser.add_argument(
        "--anzahl", type=int, default=5,
        help="Zahl der echten Titel im Export (Default: 5; nur mit --mit-echten-titeln).",
    )
    parser.add_argument(
        "--ohne-beats", action="store_true",
        help="Beat-This!-Inferenz ueberspringen (schneller, kein Checkpoint/Torch noetig).",
    )
    args = parser.parse_args(argv)
    # Synthetische Faelle (committbar) in `target`; echte Titel-Ausschnitte
    # (Musik-Lizenz, NIE veroeffentlichen) in einen getrennten, ignorierten
    # Ordner `<target>-real`. So bleibt der committete Satz sauber, egal wer
    # den Export spaeter erneut mit echten Titeln fahrt.
    beats = not args.ohne_beats
    try:
        result = export(args.target, real_count=0, include_beats=beats, synthetic=True)
    except (ValueError, OSError) as error:
        parser.exit(1, f"Golden-Export fehlgeschlagen: {error}\n")
    print(f"{len(result['cases'])} synthetische Golden-Faelle: {args.target}")
    for gap in result["gaps"]:
        print(f"Offen: {gap}")
    if args.mit_echten_titeln:
        real_target = args.target.parent / (args.target.name + "-real")
        try:
            real = export(real_target, real_count=args.anzahl, include_beats=beats, synthetic=False)
        except (ValueError, OSError) as error:
            parser.exit(1, f"Echt-Titel-Export fehlgeschlagen: {error}\n")
        print(f"{len(real['cases'])} Faelle mit {len(real['real_tracks'])} echten Titeln: {real_target}")
        print("Achtung: enthaelt Ausschnitte echter Titel - nur lokal behalten, nicht veroeffentlichen.")
        for gap in real["gaps"]:
            print(f"Offen: {gap}")
    return 0
