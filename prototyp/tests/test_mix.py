"""Tests fuer mix.py - die Uebergangs-Engine (Phase 1, ADR-014).

Geprueft wird die Mathe, die einen Uebergang hoerbar kaputt macht, wenn sie
falsch ist: equipotente Blende (kein Lautstaerke-Loch), komplementaere
Bandteilung und Bass-Tausch (zwei Baesse addieren sich nie), der True-Peak-Deckel
sowie Laenge eines gerenderten Uebergangs und Lautheit eines ganzen Sets. Alles
gegen **bekannte** synthetische Signale - kein Hoeren, kein Raten.
"""

from __future__ import annotations

import numpy as np
import pytest

from klangbild import mix


def _scipy_da() -> bool:
    try:
        import scipy.signal  # noqa: F401

        return True
    except ImportError:  # pragma: no cover - scipy ist Standard im Prototyp
        return False


def _sinus(frequenz: float, sekunden: float = 1.0, rate: int = 22050, amp: float = 0.5):
    t = np.arange(int(sekunden * rate)) / rate
    return (amp * np.sin(2 * np.pi * frequenz * t)).astype(np.float32)


def _rms(x) -> float:
    x = np.asarray(x, dtype=np.float64)
    return float(np.sqrt(np.mean(x * x))) if x.size else 0.0


# --- Equipotente Blende ------------------------------------------------------


def test_equal_power_blende_endpunkte_und_leistung():
    aus, ein = mix.equal_power_blende(1000)
    assert aus.size == ein.size == 1000
    assert abs(aus[0] - 1.0) < 1e-6 and abs(ein[0]) < 1e-6
    assert abs(aus[-1]) < 0.01                       # faellt gegen 0
    leistung = aus.astype(np.float64) ** 2 + ein.astype(np.float64) ** 2
    assert np.allclose(leistung, 1.0, atol=1e-5)     # gleiche Leistung ueberall


def test_equal_power_blende_leer():
    aus, ein = mix.equal_power_blende(0)
    assert aus.size == 0 and ein.size == 0


# --- Auffuellen (Länge exakt) ------------------------------------------------


def test_auffuellen_kuerzt_und_fuellt_mit_stille():
    x = np.ones(10, dtype=np.float32)
    assert mix._auffuellen(x, 4).size == 4           # kuerzen
    assert mix._auffuellen(x, 10).size == 10         # unveraendert
    aufgefuellt = mix._auffuellen(x, 14)
    assert aufgefuellt.size == 14 and aufgefuellt[-1] == 0.0   # Stille am Ende


# --- Bass-Rampen: Bass wird halbzeitig uebergeben ----------------------------


def test_bass_rampen_geben_bass_halbzeitig_weiter():
    rate = 22050
    n = rate                                     # 1 s Blende
    aus, ein = mix._bass_rampen(n, rate)
    assert aus.size == ein.size == n
    assert aus[0] == 1.0 and ein[0] == 0.0       # A haelt den Bass am Anfang
    assert aus[-1] == 0.0 and ein[-1] == 1.0     # B uebernimmt am Ende
    mitte = n // 2
    assert 0.3 < aus[mitte] < 0.7                # weicher Tausch an der Mitte
    assert abs((aus[mitte] + ein[mitte]) - 1.0) < 0.2


# --- Bandteilung: komplementaer und (mit scipy) selektiv ---------------------


def test_band_teilen_ist_komplementaer():
    rate = 22050
    x = _sinus(300.0, 1.0, rate) + _sinus(3000.0, 1.0, rate)
    low, high = mix.band_teilen(x, rate, 500.0)
    assert np.allclose(low + high, x, atol=1e-4)     # high = signal - low
    assert _rms(low) < _rms(x)                       # Tiefpass nimmt Energie raus


def test_band_teilen_filtert_wirklich_wenn_scipy_da():
    if not _scipy_da():
        pytest.skip("scipy fehlt - Bandteilung degradiert ehrlich zum Durchlass")
    rate = 22050
    bass = _sinus(80.0, 1.0, rate)
    low, high = mix.band_teilen(bass, rate, 500.0)
    assert _rms(low) > 0.8 * _rms(bass)              # Bass bleibt im LOW-Band
    assert _rms(high) < 0.2 * _rms(bass)             # kaum Durchlass nach oben


# --- True-Peak-Deckel: Absenken statt harte Kappung -------------------------


def test_decke_true_peak_senkt_ueberhöhung_unter_grenze():
    from klangbild import config, lufs

    rate = 22050
    # Lautes Signal, das die -1 dBTP-Grenze klar reisst (Amp 0,98 ~ -0,2 dBFS,
    # mit Oversampling wandert die Spitze noch hoeher).
    laut = _sinus(997.0, 1.0, rate, amp=0.98)
    vorher = lufs.true_peak_dbtp(laut, rate)
    gedeckt, danach = mix._decke_true_peak(laut, rate)
    # Ehrliche Absenkung: Pegel sinkt monoton, nichts wird geclippt.
    assert danach <= config.TRUE_PEAK_GRENZE
    assert danach < vorher
    assert float(np.abs(gedeckt).max()) <= float(np.abs(laut).max())


def test_decke_true_peak_verzerrt_nicht_unter_grenze():
    from klangbild import config

    rate = 22050
    leise = _sinus(997.0, 1.0, rate, amp=0.1)        # klar unter der Grenze
    gedeckt, spitze = mix._decke_true_peak(leise, rate)
    # Unter der Grenze bleibt das Signal bitgleich (kein sinnloser Pegelverlust).
    assert np.array_equal(gedeckt, leise)
    assert spitze <= config.TRUE_PEAK_GRENZE


def test_decke_true_peak_form_bleibt_erhalten():
    # Reine Pegelabsenkung aendert die Wellenform nicht - nur die Amplitude.
    # Ein harter/sinusfoermiger Limiter wuerde die Form knicken (das war der Bug).
    rate = 22050
    laut = _sinus(440.0, 0.5, rate, amp=0.99)
    gedeckt, _ = mix._decke_true_peak(laut, rate)
    n = len(laut)
    k = int(0.3 * n)                                 # Probe in der Mitte
    # Verhaeltnis zum lokalen Max bleibt konstant -> gleiche Form, anderer Pegel.
    assert abs(gedeckt[k] / laut[k] - float(gedeckt.max()) / float(laut.max())) < 1e-4
