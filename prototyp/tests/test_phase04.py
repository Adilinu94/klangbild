"""Tests fuer Phase 0.4 (Gold-Tor gegen FMAK).

Laeufen ohne den FMAK-Audio-Download: geprueft werden das CSV-/JSON-Parsing, die
Camelot-Uebersetzung inkl. der Bb/Eb-Umwandlung, die Tor-Logik (Wilson-Unter-
grenze) und die robuste Behandlung fehlender Daten. Der echte Audio-Vergleich
haengt am Download und wird hier synthetisch simuliert.
"""


import numpy as np
import pytest

from klangbild import phase04

# --- Camelot-Uebersetzung -----------------------------------------------------


@pytest.mark.parametrize(
    "key,modus,erwartet",
    [
        ("C", "Major", "8B"),
        ("F#", "Major", "2B"),
        ("Bb", "Major", "6B"),   # Bb -> A# -> 6B
        ("A", "minor", "8A"),
        ("Eb", "minor", "2A"),   # Eb -> D# -> 2A
        ("F#", "Minor", "11A"),  # Gross/Klein robust
        ("H", "Major", ""),      # unbekannter Grundton -> leer
    ],
)
def test_keymode_zu_camelot(key, modus, erwartet):
    assert phase04._keymode_zu_camelot(key, modus) == erwartet


# --- Label-Parsing ------------------------------------------------------------


def test_lade_labels_liest_keymode(tmp_path):
    csv_pfad = tmp_path / "fmakv2.csv"
    csv_pfad.write_text(
        "track_id,spotify_uri,key_and_mode\n"
        "10,spotify:track:x,F# Major\n"
        "20,spotify:track:y,Bb minor\n"
        "30,,C Major\n",
        encoding="utf-8",
    )
    labels = phase04._lade_labels(csv_pfad)
    assert labels == {"10": ("F#", "Major"), "20": ("Bb", "minor"), "30": ("C", "Major")}


def test_lade_labels_ignoriert_leere_zeilen(tmp_path):
    csv_pfad = tmp_path / "fmakv2.csv"
    csv_pfad.write_text(
        "track_id,spotify_uri,key_and_mode\n"
        "10,spotify:track:x,F# Major\n"
        "40,,\n"
        ",,\n",
        encoding="utf-8",
    )
    labels = phase04._lade_labels(csv_pfad)
    assert set(labels) == {"10"}


# --- Index-Parsing ------------------------------------------------------------


def test_lade_index_liest_audio_pfad(tmp_path):
    # Echte Struktur: "audio" ist eine Liste [pfad, md5]; nur der Pfad zaehlt.
    idx_pfad = tmp_path / "idx.json"
    idx_pfad.write_text(
        '{"tracks": {"10": {"audio": ["000/000010.mp3", "b1ca8926"]}}}',
        encoding="utf-8",
    )
    idx = phase04._lade_index(idx_pfad)
    assert idx == {"10": "000/000010.mp3"}


# --- Audio-Suche --------------------------------------------------------------


def test_finde_audio_direkt(tmp_path):
    (tmp_path / "000").mkdir()
    ziel = tmp_path / "000" / "000010.mp3"
    ziel.write_bytes(b"x")
    assert phase04._finde_audio(tmp_path, "000/000010.mp3") == ziel


def test_finde_audio_unter_fma_small(tmp_path):
    unter = tmp_path / "fma_small" / "000"
    unter.mkdir(parents=True)
    ziel = unter / "000010.mp3"
    ziel.write_bytes(b"x")
    assert phase04._finde_audio(tmp_path, "000/000010.mp3") == ziel


def test_finde_audio_fehlt(tmp_path):
    assert phase04._finde_audio(tmp_path, "000/000010.mp3") is None


# --- Auswertung / Tor-Logik ---------------------------------------------------


def _vergleich(track_id, gold, schaetzung, exakt, nachbar):
    return phase04.GoldVergleich(
        track_id=track_id, gold=gold, schaetzung=schaetzung,
        vertrauen=0.5, exakt=exakt, nachbar=nachbar,
    )


def test_auswerten_leer_ist_sicher():
    z = phase04.auswerten([])
    assert z["tracks"] == 0
    assert z["exakt"]["quote"] == 0.0
    assert z["exakt"]["erreicht"] is False
    assert z["mittel_vertrauen"] == 0.0


def test_auswerten_perfekt_erreicht_tor():
    v = [_vergleich(str(i), "8A", "8A", True, True) for i in range(10)]
    z = phase04.auswerten(v)
    assert z["exakt"]["treffer"] == 10
    assert z["exakt"]["quote"] == 1.0
    assert z["exakt"]["erreicht"] is True
    assert z["nachbar"]["erreicht"] is True


def test_auswerten_untergrenze_verhindert_ueberbewertung():
    # Nur 2 von 8 exakt (25 %) - Punktwert unter dem 50 %-Tor, Untergrenze noch
    # tiefer: das Tor darf nicht erfuellt sein.
    v = [_vergleich("a", "8A", "8A", True, True),
         _vergleich("b", "8A", "8A", True, True),
         _vergleich("c", "8A", "9B", False, False),
         _vergleich("d", "8A", "9B", False, False),
         _vergleich("e", "8A", "9B", False, False),
         _vergleich("f", "8A", "9B", False, False),
         _vergleich("g", "8A", "9B", False, False),
         _vergleich("h", "8A", "9B", False, False)]
    z = phase04.auswerten(v)
    assert z["exakt"]["treffer"] == 2
    assert z["exakt"]["erreicht"] is False


def test_auswerten_nachbar_zaehlt_camelot_umfeld():
    # Nachbar-Treffer ohne exakten Treffer: Nachbar-Quote hoch, exakt niedrig.
    v = [_vergleich("a", "8A", "9A", False, True),
         _vergleich("b", "8A", "7A", False, True),
         _vergleich("c", "8A", "9A", False, True)]
    z = phase04.auswerten(v)
    assert z["exakt"]["treffer"] == 0
    assert z["nachbar"]["treffer"] == 3
    assert z["nachbar"]["quote"] == 1.0


def test_hart_tracks_nur_exakt_daneben():
    v = [_vergleich("a", "8A", "8A", True, True),
         _vergleich("b", "8A", "9B", False, False)]
    z = phase04.auswerten(v)
    assert z["hart"]["gesamt"] == 1
    assert z["hart"]["tracks"][0]["track_id"] == "b"


# --- Track-Vergleich (synthetisch) --------------------------------------------


def test_track_vergleichen_trifft_bei_sauberer_dreiklangtonspur():
    # Dieselbe robuste Bauform wie tests/test_keyestimate.py: eine Oktave tiefer
    # verankerter Bass macht den Grundton eindeutig. A-Dur (60) -> Camelot 8B.
    rate = 22050
    sekunden = 6.0
    t = np.arange(int(sekunden * rate)) / rate

    def _freq(midi: float) -> float:
        return 440.0 * 2 ** ((midi - 69) / 12)

    tonhoehen = [(48, 0.5), (60, 0.3), (64, 0.25), (67, 0.25)]  # A, C#, E
    signal = np.zeros_like(t)
    for midi, staerke in tonhoehen:
        signal += staerke * np.sin(2 * np.pi * _freq(midi) * t)
    signal = signal.astype(np.float32)
    signal /= np.max(np.abs(signal))

    erg = phase04.track_vergleichen("1", "8B", signal, rate)
    assert erg.gold == "8B"
    assert erg.exakt is True
    assert erg.vertrauen >= 0.0
