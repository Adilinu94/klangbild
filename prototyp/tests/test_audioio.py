"""Tests fuer das Lesen, Ratenwandeln und Schneiden von Audio."""

from __future__ import annotations

import numpy as np
import soundfile as sf

from klangbild import audioio, config


def _wav_schreiben(pfad, sekunden: float = 30.0, rate: int = 44100, kanaele: int = 2):
    t = np.arange(int(sekunden * rate)) / rate
    ton = 0.2 * np.sin(2 * np.pi * 440.0 * t)
    daten = np.column_stack([ton] * kanaele).astype(np.float32)
    sf.write(str(pfad), daten, rate)
    return pfad


def test_decodieren_wandelt_auf_mono_und_rate(tmp_path):
    pfad = _wav_schreiben(tmp_path / "a.wav")
    audio = audioio.decodieren(pfad, config.ABTASTRATE_EINBETTUNG)
    assert audio.rate == config.ABTASTRATE_EINBETTUNG
    assert abs(audio.sekunden - 30.0) < 0.05
    assert audio.daten.ndim == 1


def test_ausschnitte_anfang_mitte_ende():
    audio = audioio.Audio(daten=np.zeros(22050 * 60, dtype=np.float32), rate=22050)
    plan = audioio.ausschnitte_planen(audio)
    namen = [name for name, _, _ in plan]
    assert namen == ["anfang", "mitte", "ende"]
    assert plan[0][1] == 0
    assert plan[2][2] == len(audio.daten)
    for _, start, ende in plan:
        assert ende - start == int(config.AUSSCHNITT_SEKUNDEN * audio.rate)


def test_kurzer_track_ueberlappt_aber_stuerzt_nicht():
    audio = audioio.Audio(daten=np.zeros(22050 * 10, dtype=np.float32), rate=22050)
    plan = audioio.ausschnitte_planen(audio)
    assert len(plan) == 3
    for _, start, ende in plan:
        assert 0 <= start <= ende <= len(audio.daten)


def test_schnitt_wird_geschrieben(tmp_path):
    quelle = _wav_schreiben(tmp_path / "a.wav")
    audio = audioio.decodieren(quelle, 22050)
    ziel = audioio.ausschnitt_schneiden(audio, 0, 22050, tmp_path / "clip.wav")
    daten, rate = sf.read(str(ziel))
    assert rate == 22050
    assert len(daten) == 22050
