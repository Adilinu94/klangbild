"""Lautheit nach ITU-R BS.1770-4 (LUFS) und True Peak – eigene Implementierung.

Grund (ADR-012): libebur128 ist MIT und laeuft spaeter auf Android. Damit die
Zahlen auf PC und Handy **identisch** sind, rechnet der Prototyp dasselbe
Verfahren: K-Gewichtung aus zwei Biquads, 400-ms-Bloecke mit 75 % Ueberlappung,
absolute und relative Torschwelle, -0,691-dB-Offset.

Die Biquad-Koeffizienten werden – wie in libebur128 – **fuer die jeweilige
Abtastrate** aus dem analogen Prototyp berechnet (bilineare Transformation).
Damit ist keine Ratenwandlung noetig, und 22,05 kHz liefert dasselbe Ergebnis
wie 48 kHz.

Referenz: ITU-R BS.1770-4; libebur128 (C) als Verhaltensvorlage, kein Code
uebernommen.
"""

from __future__ import annotations

import math

import numpy as np

try:
    from scipy.signal import lfilter
except ImportError:  # pragma: no cover - Ersatzpfad, langsam
    lfilter = None

try:
    import soxr
except ImportError:  # pragma: no cover
    soxr = None

BLOCK_SEKUNDEN = 0.400
SCHRITT_SEKUNDEN = 0.100
ABSOLUT_SCHWELLE = -70.0
RELATIV_ABSTAND = -10.0
OFFSET = -0.691

# Kenngroessen des K-Gewichtungs-Filters (wie libebur128).
SHELF_F0 = 1681.974450955533
SHELF_G = 3.999843853973347
SHELF_Q = 0.7071752369554196
HIGHPASS_F0 = 38.13547087602444
HIGHPASS_Q = 0.5003270373238773


def _shelf(samplerate: int) -> tuple[np.ndarray, np.ndarray]:
    k = math.tan(math.pi * SHELF_F0 / samplerate)
    vh = 10.0 ** (SHELF_G / 20.0)
    vb = vh**0.4996667741545416
    a0 = 1.0 + k / SHELF_Q + k * k
    b = np.array(
        [
            (vh + vb * k / SHELF_Q + k * k) / a0,
            2.0 * (k * k - vh) / a0,
            (vh - vb * k / SHELF_Q + k * k) / a0,
        ]
    )
    a = np.array([1.0, 2.0 * (k * k - 1.0) / a0, (1.0 - k / SHELF_Q + k * k) / a0])
    return b, a


def _highpass(samplerate: int) -> tuple[np.ndarray, np.ndarray]:
    k = math.tan(math.pi * HIGHPASS_F0 / samplerate)
    a0 = 1.0 + k / HIGHPASS_Q + k * k
    b = np.array([1.0, -2.0, 1.0])
    a = np.array([1.0, 2.0 * (k * k - 1.0) / a0, (1.0 - k / HIGHPASS_Q + k * k) / a0])
    return b, a


def _filter(signal: np.ndarray, b: np.ndarray, a: np.ndarray) -> np.ndarray:
    if lfilter is not None:
        return lfilter(b, a, np.asarray(signal, dtype=np.float64))
    # Ersatzpfad ohne scipy: reine Python-Schleife (nur fuer kleine Testbloecke).
    b0, b1, b2 = b
    a1, a2 = a[1], a[2]
    x = np.asarray(signal, dtype=np.float64)
    y = np.empty_like(x)
    x1 = x2 = y1 = y2 = 0.0
    for index in range(len(x)):
        x0 = float(x[index])
        y0 = b0 * x0 + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        y[index] = y0
        x2, x1 = x1, x0
        y2, y1 = y1, y0
    return y


def k_gewichten(signal: np.ndarray, samplerate: int) -> np.ndarray:
    b1, a1 = _shelf(samplerate)
    b2, a2 = _highpass(samplerate)
    return _filter(_filter(signal, b1, a1), b2, a2)


def _gleitende_summe(werte: np.ndarray, fenster: int) -> np.ndarray:
    """Summe ueber gleitende Fenster in O(n) (Praefixsummen)."""
    fenster = max(1, min(fenster, len(werte)))
    kumuliert = np.concatenate(([0.0], np.cumsum(werte, dtype=np.float64)))
    return kumuliert[fenster:] - kumuliert[:-fenster]


def _block_mittelwerte(gewichtet: np.ndarray, samplerate: int) -> np.ndarray:
    block = int(BLOCK_SEKUNDEN * samplerate)
    schritt = int(SCHRITT_SEKUNDEN * samplerate)
    if len(gewichtet) < block:
        block = len(gewichtet)
        schritt = max(1, block // 4)
    if block <= 0:
        return np.zeros(0)
    quadrate = gewichtet**2
    anzahl = 1 + max(0, len(quadrate) - block) // schritt
    summe = _gleitende_summe(quadrate, block)
    stellen = np.arange(anzahl) * schritt
    return summe[stellen] / block


def _zu_lufs(mittelwert: float) -> float:
    return float("-inf") if mittelwert <= 0 else OFFSET + 10.0 * math.log10(mittelwert)


def integrierte_lautheit(mono: np.ndarray, samplerate: int) -> float:
    """Integrierte Lautheit (LUFS) eines Mono- oder (n, Kanaele)-Signals."""
    if mono.size == 0:
        return float("-inf")
    if mono.ndim == 2:
        # BS.1770: Blockleistungen je Kanal summieren (L/R-Gewicht 1,0).
        bloecke = sum(
            _block_mittelwerte(k_gewichten(mono[:, k], samplerate), samplerate)
            for k in range(mono.shape[1])
        )
    else:
        bloecke = _block_mittelwerte(k_gewichten(mono, samplerate), samplerate)
    if bloecke.size == 0:
        return float("-inf")

    lautheiten = np.array([_zu_lufs(wert) for wert in bloecke])
    ueber_absolut = lautheiten > ABSOLUT_SCHWELLE
    if not np.any(ueber_absolut):
        return float("-inf")

    vorschnitt = _zu_lufs(float(bloecke[ueber_absolut].mean()))
    endgueltig = bloecke[ueber_absolut & (lautheiten > vorschnitt + RELATIV_ABSTAND)]
    if endgueltig.size == 0:
        return float("-inf")
    return _zu_lufs(float(endgueltig.mean()))


def true_peak_dbtp(
    mono: np.ndarray, samplerate: int, ueberabtastung: int = 4, block_sekunden: float = 10.0
) -> float:
    """True Peak in dBTP. Ueberabtastet blockweise, damit der Speicher begrenzt bleibt."""
    if mono.size == 0:
        return float("-inf")
    if soxr is None:
        spitze = float(np.abs(mono).max())
        return 20.0 * math.log10(spitze) if spitze > 0 else float("-inf")

    block = max(1, int(block_sekunden * samplerate))
    spitze = 0.0
    for start in range(0, len(mono), block):
        stueck = mono[start:start + block].astype(np.float64)
        hoch = soxr.resample(stueck, samplerate, samplerate * ueberabtastung)
        spitze = max(spitze, float(np.abs(hoch).max()))
    return 20.0 * math.log10(spitze) if spitze > 0 else float("-inf")


def auf_lautheit_bringen(mono: np.ndarray, samplerate: int, ziel_lufs: float) -> np.ndarray:
    """Bringt ein Signal auf die Ziel-Lautheit (integriert, ohne Begrenzer)."""
    ist = integrierte_lautheit(mono, samplerate)
    if not np.isfinite(ist) or ist <= ABSOLUT_SCHWELLE:
        return mono.astype(np.float32)
    faktor = 10.0 ** ((ziel_lufs - ist) / 20.0)
    return (mono.astype(np.float32) * faktor).astype(np.float32)
