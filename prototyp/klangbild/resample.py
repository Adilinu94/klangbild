"""Vinyl-Tempoangleich per Resampling (ADR-014, Gate per ADR-020 auf +-1 %).

Version 1 zieht Song B per **einfachem Resampling** auf das Tempo von A - das
Vinyl-Prinzip. Tonhoehe und Tempo aendern sich dabei gemeinsam; der Planer
begrenzt den Sprung auf +-1 % (ADR-020), das sind 0,17 Halbtöne (17 Cent).
Ohne Keylock wäre ±3 % (0,51 Halbtöne, ADR-014) hörbar verstimmt.

Zwei Wege, **dieselbe** Tempo-Mathematik:

- `resample_linear` ist die **Referenz** (wie OboeDJ, lineare Interpolation).
  Frei von Abhaengigkeiten, numpy only, und später 1:1 die Zahlenbasis von
  Android (ADR-014). Deshalb ist sie der Standard und wird von den Tests
  geprüft.
- `resample_soxr` nutzt soxr als Interpolations-Kern. Nur die **Klangqualitaet**
  des gerenderten Demo-Mixes unterscheidet sich; Taktfaktor, Raster und Plan
  bleiben identisch. Android wird weiter linear rechnen - der Prototyp darf für
  die Hörprobe die bessere Qualität nutzen, ohne dass sich die Planung ändert.

Der Taktfaktor selbst ist geschichtsneutral: `tempo_faktor(von_bpm, auf_bpm)`
liefert >1, wenn B **schneller** laufen muss (kuerzer, hoeher), und wird auf
+-`TEMPO_MAX_ABWEICHUNG` geklemmt.
"""

from __future__ import annotations

import numpy as np

TEMPO_MAX_ABWEICHUNG = 0.01  # +-1 % (ADR-020, Vinyl bis Keylock kommt)


def tempo_faktor(
    von_bpm: float, auf_bpm: float, max_abweichung: float = TEMPO_MAX_ABWEICHUNG
) -> float:
    """Faktor, um ein Signal von `von_bpm` auf `auf_bpm` zu ziehen.

    >1 heißt: schneller abspielen (Ausgang wird kuerzer, Tonhoe hoeher). Das
    Ergebnis wird auf +-`max_abweichung` geklemmt; unplausible Tempi (<=0)
    liefern 1.0 (keine Aenderung), statt still zu verzerren.
    """
    if von_bpm <= 0 or auf_bpm <= 0:
        return 1.0
    roh = auf_bpm / von_bpm
    return float(min(max(roh, 1.0 - max_abweichung), 1.0 + max_abweichung))


def tempo_passt(
    von_bpm: float, auf_bpm: float, max_abweichung: float = TEMPO_MAX_ABWEICHUNG
) -> bool:
    """True, wenn `von_bpm` ohne Klemmung innerhalb +-`max_abweichung` liegt.

    Der Planer nutzt das als harte Bedingung: liegen zwei Tempi weiter als 1 %
    auseinander, gehoeren sie nicht in dasselbe Set (ADR-020).
    """
    if von_bpm <= 0 or auf_bpm <= 0:
        return False
    return abs(auf_bpm - von_bpm) / von_bpm <= max_abweichung


def resample_linear(signal: np.ndarray, faktor: float) -> np.ndarray:
    """Liest ein Signal um `faktor` schneller ab (Referenz, linear).

    `faktor` > 1 macht die Ausgabe um diesen Faktor kuerzer; `faktor` = 2 halbiert
    die Laenge und verdoppelt die Tonhoehe. Leere Eingaben bleiben leer.
    """
    x = np.asarray(signal, dtype=np.float32).reshape(-1)
    if x.size == 0:
        return x.astype(np.float32, copy=True)
    if abs(faktor - 1.0) < 1e-9:
        return x.astype(np.float32, copy=True)
    laenge_aus = max(1, round(x.size / faktor))
    position = np.arange(laenge_aus, dtype=np.float64) * faktor
    i0 = np.floor(position).astype(np.int64)
    frac = (position - i0).astype(np.float32)
    i0 = np.clip(i0, 0, x.size - 1)
    i1 = np.minimum(i0 + 1, x.size - 1)
    aus = x[i0] * (1.0 - frac) + x[i1] * frac
    return aus.astype(np.float32)


def resample_soxr(signal: np.ndarray, rate: int, faktor: float) -> np.ndarray:
    """Dasselbe wie `resample_linear`, aber mit soxr als Interpolations-Kern.

    Nutzt soxr.resample(signal, in_rate=rate*faktor, out_rate=rate): liest also
    das Signal, als laege es mit der hoeheren Rate vor - ergibt genau den
    Vinyl-Effekt (kuerzer, hoeher) mit besserer Qualitaet als linear. Faellt
    ohne soxr auf die lineare Referenz zurueck.
    """
    x = np.asarray(signal, dtype=np.float32).reshape(-1)
    if x.size == 0 or abs(faktor - 1.0) < 1e-9:
        return resample_linear(x, faktor)
    try:
        import soxr
    except ImportError:
        return resample_linear(x, faktor)
    aus = soxr.resample(x, int(rate * faktor), int(rate))
    return np.asarray(aus, dtype=np.float32).reshape(-1)


def resample(
    signal: np.ndarray, rate: int, faktor: float, methode: str = "linear"
) -> np.ndarray:
    """Tempoangleich per Resampling. `methode` in {"linear", "soxr"}.

    Standard ist die referenz-kompatible lineare Interpolation (Android-Basis,
    ADR-014). Fuer den gerenderten Demo-Mix kann `methode="soxr"` die bessere
    Qualitaet liefern - Plan und Raster bleiben davon unberuehrt.
    (n, Kanaele)-Signale werden je Kanal gezogen.
    """
    if np.ndim(signal) == 2:
        return np.stack(
            [resample(signal[:, k], rate, faktor, methode) for k in range(signal.shape[1])],
            axis=1,
        )
    if methode == "soxr":
        return resample_soxr(signal, rate, faktor)
    return resample_linear(signal, faktor)


def schrittzeit(zeit: float, faktor: float) -> float:
    """Zeitstempel (Sekunden) nach Tempoangleich: eine Sekunde wird 1/faktor."""
    if faktor <= 0:
        return zeit
    return zeit / faktor
