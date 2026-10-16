"""Uebergaenge nach Rezept (Phase 2, ADR-019/022): Beat-Warp + Uebergangsarten.

Kernidee: Jeder Song wird **Takt fuer Takt** auf ein Ziel-Taktraster gezogen
(`warp`). Mit Keylock dehnt Signalsmith Stretch (Tonhoehe bleibt), ohne Keylock
`resample` (Vinyl). Alle Tempo-Optionen sind nur verschiedene Zielraster:

- b_an_a: B uebernimmt die Taktlaenge von A (und behaelt sie danach).
- a_an_b: in der Blende laufen beide im Tempo von B; danach B original.
- rampe:  die Taktlaenge gleitet ueber die Blende von A nach B; danach B original.

Zeiten: Eine `Spur` haelt ihre Takte zweimal - in Originalzeit (`orig`) und in
Pufferzeit (`buf`, nach dem Dehnen). Beide Achsen werden stueckweise linear
ineinander umgerechnet (`zu_puffer`/`zu_original`).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np

from . import config, mix, resample
from .einstellungen import Einstellungen
from .keyestimate import camelot_nachbarn

RATE = config.ABTASTRATE_HOERTEST
PHRASE = 8            # Takte je Phrase
NAHT = 1024           # Kreuzblende an einer Naht zwischen zwei Dehn-Aufrufen (~23 ms)
SUCHE = 441           # WSOLA: Naht um bis zu ±10 ms auf die beste Uebereinstimmung schieben
KONTEXT = 8192        # Eingangsrand je Dehn-Aufruf (> Signalsmith-Latenz 2x2646)
MAX_LAUF = 30 * RATE  # laengster Dehn-Aufruf (Eingang)
_DEHN_POOL = None
STEM_ARTEN = ("drums_zuerst", "acapella", "gesangsschutz", "gesang_zuerst", "double_drop")
SYNC_ARTEN = ("eq", "crossfade", "filter", "eigen") + STEM_ARTEN


@dataclass(frozen=True)
class Eintrag:
    """Ein mischbarer Bibliothekstrack mit den Merkmalen aus der Analyse."""

    id: int
    pfad: str
    bpm: float
    camelot: str | None
    downbeats: list[float]
    gain_db: float = 0.0
    energie: list[float] = field(default_factory=list)
    abschnitte: list[float] = field(default_factory=list)

    @property
    def titel(self) -> str:
        return Path(self.pfad).stem

    @property
    def energie_db(self) -> float | None:
        return float(np.mean(self.energie)) if self.energie else None


def _ext(x: float | np.ndarray, xp: np.ndarray, fp: np.ndarray):
    """np.interp mit linearer Fortsetzung ueber beide Enden."""
    if len(xp) < 2:
        return np.asarray(x, dtype=float) - (xp[0] if len(xp) else 0) + (fp[0] if len(fp) else 0)
    y = np.interp(x, xp, fp)
    links = (fp[1] - fp[0]) / (xp[1] - xp[0])
    rechts = (fp[-1] - fp[-2]) / (xp[-1] - xp[-2])
    y = np.where(np.asarray(x) < xp[0], fp[0] + (np.asarray(x) - xp[0]) * links, y)
    y = np.where(np.asarray(x) > xp[-1], fp[-1] + (np.asarray(x) - xp[-1]) * rechts, y)
    return y


def raster(takte: list[float] | np.ndarray, bis_s: float) -> np.ndarray:
    """Taktzeiten, nach vorne bis `bis_s` mit der Taktlaenge am Ende fortgesetzt."""
    t = np.asarray(takte, dtype=float)
    if t.size < 2:
        t = np.array([0.0, 2.0]) if t.size == 0 else np.array([t[0], t[0] + 2.0])
    periode = float(np.median(np.diff(t[-8:])))
    if t[-1] < bis_s and periode > 0:
        t = np.concatenate([t, t[-1] + periode * np.arange(1, int((bis_s - t[-1]) / periode) + 2)])
    return t


def regulaer(downbeats: list[float], bpm: float, bis_s: float, um_s: float) -> np.ndarray:
    """Gleichmaessiges Taktraster aus dem Song-Tempo; Downbeats liefern nur die Phase.

    Beat This! liefert in Breakdowns/Intros stellenweise falsche Downbeats (in ~5 %
    der Bibliothek grob). Taktweise darauf zu dehnen wuerde genau dort das Audio
    verzerren. Das Tempo kommt deshalb aus der BPM-Regression (±0,1 %), die Phase
    aus dem Kreismittel der Downbeats im Umkreis von ±30 s um `um_s`.
    shortcut: setzt konstantes Tempo im Song voraus; Upgrade: Raster abschnittsweise.
    """
    periode = 240.0 / bpm if bpm and bpm > 0 else 2.0
    d = np.asarray(downbeats, dtype=float)
    nah = d[np.abs(d - um_s) <= 30.0]
    if nah.size < 4:
        nah = d
    phase = (float(np.angle(np.mean(np.exp(2j * np.pi * nah / periode)))) / (2 * np.pi) * periode
             if nah.size else 0.0)
    # Index 0 = Rasterpunkt am ersten erkannten Downbeat (Phrasenanker wie bisher).
    erster = float(d[0]) if d.size else 0.0
    start = phase + periode * np.round((erster - phase) / periode)   # darf minimal < 0 sein
    return start + periode * np.arange(0, int(max(bis_s - start, periode) / periode) + 2)


@dataclass
class Spur:
    """Ein geladener (ggf. gedehnter) Song im Puffer."""

    eintrag: Eintrag
    puffer: np.ndarray          # (n, 2) float32
    orig: np.ndarray            # Takte in Originalzeit
    buf: np.ndarray             # dieselben Takte in Pufferzeit

    @classmethod
    def roh(cls, eintrag: Eintrag, puffer: np.ndarray) -> "Spur":
        dauer = len(puffer) / RATE
        t = regulaer(eintrag.downbeats, eintrag.bpm, dauer, um_s=0.75 * dauer)   # Ausstieg liegt hinten
        return cls(eintrag, puffer, t, t.copy())

    def zu_puffer(self, t_orig: float) -> float:
        return float(_ext(t_orig, self.orig, self.buf))

    def zu_original(self, t_buf: float) -> float:
        return float(_ext(t_buf, self.buf, self.orig))

    def bpm_bei(self, t_buf: float) -> float:
        """Lokales Tempo (BPM, 4/4) an einer Pufferstelle."""
        i = int(np.clip(np.searchsorted(self.buf, t_buf), 1, len(self.buf) - 1))
        p = _periode(self.buf, i)
        return 240.0 / p if p > 0 else self.eintrag.bpm


# --- Beat-Warp --------------------------------------------------------------

def _dehnen(stueck: np.ndarray, faktor: float) -> np.ndarray:
    """Ein Signalsmith-Aufruf (Modulebene, damit er auch im Pool-Prozess laeuft).

    python-stretch macht je Aufruf seek -> process -> flush -> reset: jeder Aufruf
    ist ein eigenstaendiges Stueck. Zwei Aufrufe passen an ihrer Grenze nicht
    zusammen (Phasen unabhaengig, gemessen Korrelation -0,8..+0,9) - frueher
    knackte es deshalb alle 4096 Samples. Darum: so wenige Aufrufe wie moeglich.
    """
    import python_stretch as ps

    s = ps.Signalsmith.Stretch()
    s.preset(2, RATE)
    s.timeFactor = faktor
    return s.process(np.ascontiguousarray(stueck.T, dtype=np.float32)).T


def _aufwaermen() -> None:
    import time

    _dehnen(np.zeros((RATE // 4, 2), np.float32), 1.01)
    time.sleep(0.3)   # haelt den Prozess kurz belegt, damit jeder Worker einen Auftrag bekommt


def _niedrig() -> None:
    """Pool-Prozess unter normaler Prioritaet: der Audio-Callback im Mixer hat Vorrang."""
    import os

    try:
        if os.name == "nt":
            import ctypes

            ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
        else:
            os.nice(5)
    except (OSError, AttributeError):
        pass


def _parallel(*aufgaben):
    """Aufgaben (ohne Argumente) gleichzeitig in Threads; die Arbeit steckt im Dehn-Pool,
    die Threads warten nur. Ergebnisse in der Reihenfolge der Aufgaben."""
    from concurrent.futures import ThreadPoolExecutor

    if len(aufgaben) == 1:
        return [aufgaben[0]()]
    with ThreadPoolExecutor(max_workers=len(aufgaben)) as ex:
        return [f.result() for f in [ex.submit(a) for a in aufgaben]]


def dehn_pool_starten() -> None:
    """Signalsmith haelt den GIL; ein langer Aufruf im Mixer-Prozess liesse den
    Audio-Callback verhungern. Live laufen die Aufrufe deshalb in eigenen Prozessen."""
    global _DEHN_POOL
    if _DEHN_POOL is None:
        from concurrent.futures import ProcessPoolExecutor

        import os

        _DEHN_POOL = ProcessPoolExecutor(max_workers=max(2, (os.cpu_count() or 4) * 3 // 4), initializer=_niedrig)
        # Prozesse und Signalsmith jetzt starten (sonst kostet der erste Uebergang ~5 s mehr)
        for _ in range(_DEHN_POOL._max_workers):
            _DEHN_POOL.submit(_aufwaermen)


def _alle_dehnen(auftraege: list[tuple[np.ndarray, float]]) -> list[np.ndarray]:
    global _DEHN_POOL
    if _DEHN_POOL is not None and auftraege:
        try:
            return list(_DEHN_POOL.map(_dehnen, *zip(*auftraege)))
        except Exception as fehler:  # noqa: BLE001 - kaputter Pool: lieber lokal als gar nicht
            print(f"Dehn-Pool ausgefallen, rechne lokal: {fehler}", flush=True)
            _DEHN_POOL = None
    return [_dehnen(s, f) for s, f in auftraege]


def _ausschnitt(y: np.ndarray, von: int, laenge: int) -> np.ndarray:
    """y[von:von+laenge], ausserhalb mit Stille aufgefuellt."""
    aus = np.zeros((laenge, 2), np.float32)
    a, b = max(0, von), min(len(y), von + laenge)
    if b > a:
        aus[a - von:b - von] = y[a:b]
    return aus


def _korrelation(a: np.ndarray, b: np.ndarray) -> float:
    a, b = a.sum(1), b.sum(1)
    return float(np.dot(a, b) / max(np.sqrt(np.dot(a, a) * np.dot(b, b)), 1e-12))


def _ausrichten(ref: np.ndarray, y: np.ndarray, start: int, lo: int, hi: int) -> tuple[int, float]:
    """WSOLA: Verschiebung tau in [lo, hi], bei der y[start+tau:][:len(ref)] am besten zu ref passt."""
    if hi < lo:
        return 0, 0.0
    r = ref.sum(1).astype(np.float64)
    q = y[start + lo:start + hi + len(r)].sum(1).astype(np.float64)
    if len(q) < len(r) + (hi - lo):
        return 0, 0.0
    korr = np.correlate(q, r, mode="valid")
    energie = np.convolve(q * q, np.ones(len(r)), mode="valid")
    norm = korr / np.sqrt(np.maximum(energie * np.dot(r, r), 1e-12))
    i = int(np.argmax(norm))
    return lo + i, float(norm[i])


def _ueberblenden(alt: np.ndarray, neu: np.ndarray, korr: float) -> np.ndarray:
    """Kreuzblende ohne Pegelloch: Normierung passend zur Korrelation der beiden Teile."""
    t = (np.arange(len(alt)) + 0.5) / max(1, len(alt))
    w = np.cos(t * np.pi / 2) ** 2
    g = 1.0 / np.sqrt(np.maximum(w ** 2 + (1 - w) ** 2 + 2 * max(korr, 0.0) * w * (1 - w), 1e-6))
    return ((alt * w[:, None] + neu * (1 - w)[:, None]) * g[:, None]).astype(np.float32)


def _warp_keylock(audio: np.ndarray, quell: np.ndarray, ziel: np.ndarray,
                  rand_vorn: bool, rand_hinten: bool) -> np.ndarray:
    faktoren = np.diff(quell) / np.maximum(1, np.diff(ziel))
    # Laeufe: Takte mit (fast) gleichem Faktor (±0,1 % = 1,7 Cent) in EINEM Aufruf.
    # b_an_a/a_an_b: wenige Laeufe; Rampe: eine Naht je Takt(gruppe). Hoechstens
    # MAX_LAUF je Lauf: riesige Pool-Ergebnisse auszupacken sperrt sonst den GIL (84 ms).
    grenzen = [0]
    for i in range(1, len(faktoren)):
        if (abs(faktoren[i] - faktoren[grenzen[-1]]) > 0.001 * faktoren[grenzen[-1]]
                or quell[i] - quell[grenzen[-1]] > MAX_LAUF):
            grenzen.append(i)
    grenzen.append(len(faktoren))
    laeufe, auftraege = [], []
    for i0, i1 in zip(grenzen[:-1], grenzen[1:]):
        qa, qe, za, ze = int(quell[i0]), int(quell[i1]), int(ziel[i0]), int(ziel[i1])
        if ze <= za:
            continue
        if qe - qa < NAHT:   # hinter dem Songende: Stille
            laeufe.append((za, ze, None))
            continue
        links, rechts = min(KONTEXT, qa), min(KONTEXT, len(audio) - qe)
        f = (qe - qa) / (ze - za)
        laeufe.append((za, ze, (len(auftraege), int(round(links / f)), qa)))
        auftraege.append((audio[qa - links:qe + rechts], f))
    ergebnisse = _alle_dehnen(auftraege)

    n_aus = int(ziel[-1])
    aus = np.zeros((n_aus, 2), np.float32)
    vorher = None   # (y, basis, tau, za) des vorigen Laufs; sein Rand reicht ueber die Naht
    for za, ze, job in laeufe:
        if job is None:
            vorher = None
            continue
        k, basis, qa = job
        y, tau, kern = ergebnisse[k], 0, za
        if vorher is not None:   # Naht: ausrichten (WSOLA) und kurz ueberblenden
            vy, vbasis, vtau, vza = vorher
            s0 = max(0, za - NAHT // 2)
            n = min(NAHT, n_aus - s0)
            alt = _ausschnitt(vy, vbasis + vtau + s0 - vza, n)
            start = basis + s0 - za
            tau, korr = _ausrichten(alt, y, start, max(-SUCHE, -start), min(SUCHE, len(y) - start - n))
            aus[s0:s0 + n] = _ueberblenden(alt, _ausschnitt(y, start + tau, n), korr)
            kern = s0 + n
        elif rand_vorn and za == 0:   # Anschluss an das ungedehnte Original davor
            n = min(NAHT, ze - za)
            alt = _ausschnitt(audio, qa, n)
            tau, korr = _ausrichten(alt, y, basis, max(-SUCHE, -basis), min(SUCHE, len(y) - basis - n))
            aus[:n] = _ueberblenden(alt, _ausschnitt(y, basis + tau, n), korr)
            kern = n
        aus[kern:ze] = _ausschnitt(y, basis + tau + kern - za, ze - kern)
        vorher = (y, basis, tau, za)
    if rand_hinten and n_aus > 0:   # Anschluss an das ungedehnte Original danach
        n = min(NAHT, n_aus)
        alt, neu = aus[-n:].copy(), _ausschnitt(audio, int(quell[-1]) - n, n)
        aus[-n:] = _ueberblenden(alt, neu, _korrelation(alt, neu))
    return aus


def warp(audio: np.ndarray, quell_s: np.ndarray, ziel_s: np.ndarray, keylock: bool,
         rand_vorn: bool = False, rand_hinten: bool = False) -> np.ndarray:
    """Zieht `audio[quell_s[0]:quell_s[-1]]` so, dass Takt i auf ziel_s[i]-ziel_s[0] faellt.

    `rand_vorn`/`rand_hinten`: das Ergebnis geht am Anfang/Ende nahtlos in das
    ungedehnte Original ueber (Blendenbeginn von A, Blendenende von B), sonst
    knackt es beim Umschalten. Gemessen: Klicks landen auf ±1 ms im Zielraster.
    """
    quell = np.round(np.asarray(quell_s) * RATE).astype(int)
    ziel = np.round((np.asarray(ziel_s) - ziel_s[0]) * RATE).astype(int)
    quell = np.clip(quell, 0, len(audio))
    # Unter 0,2 % Abweichung (< 3,5 Cent) ist Resampling unhoerbar und viel schneller.
    faktoren = np.diff(quell) / np.maximum(1, np.diff(ziel))
    if keylock and np.any(np.abs(faktoren - 1) > 0.002):
        return _warp_keylock(audio, quell, ziel, rand_vorn, rand_hinten)
    teile, fertig = [], 0
    for i in range(len(quell) - 1):
        n_aus = ziel[i + 1] - fertig
        stueck = audio[quell[i]:quell[i + 1]]
        if n_aus <= 0:
            continue
        if len(stueck) == 0:
            teile.append(np.zeros((n_aus, 2), np.float32))
        else:   # linear je Takt, ab dem Taktanfang: stetig an den Taktgrenzen und zu den Nachbarn
            teile.append(mix._auffuellen(resample.resample(stueck, RATE, len(stueck) / n_aus), n_aus))
        fertig += n_aus
    return np.concatenate(teile) if teile else np.zeros((0, 2), np.float32)


# --- Uebergangsarten (Blenden auf gleich langen, synchronen Abschnitten) -----

# Fenster (Anteile der Blende) je Band bzw. Stem: A blendet in (von, bis) aus, B ein.
FILTER_FENSTER = (((0.45, 0.55), (0.45, 0.55)),   # Bass: kurzer Tausch in der Mitte
                  ((0.25, 0.75), (0.25, 0.75)),   # Mitten
                  ((0.5, 1.0), (0.0, 0.5)))       # Hoehen: B zuerst, A zuletzt
STEM_PLAN = {
    "drums_zuerst": {"drums": ((0.0, 0.5), (0.0, 0.5)), "bass": ((0.45, 0.55), (0.45, 0.55)),
                     "other": ((0.5, 1.0), (0.5, 1.0)), "vocals": ((0.5, 0.7), (0.7, 1.0))},
    "acapella": {"drums": ((0.0, 0.5), (0.0, 0.5)), "bass": ((0.45, 0.55), (0.45, 0.55)),
                 "other": ((0.0, 0.5), (0.0, 0.5)), "vocals": ((0.85, 1.0), (0.9, 1.0))},
    "gesangsschutz": {"drums": ((0.0, 1.0), (0.0, 1.0)), "bass": ((0.45, 0.55), (0.45, 0.55)),
                      "other": ((0.0, 1.0), (0.0, 1.0)), "vocals": ((0.3, 0.5), (0.5, 0.7))},
    "gesang_zuerst": {"drums": ((0.5, 0.75), (0.5, 0.75)), "bass": ((0.6, 0.65), (0.6, 0.65)),
                      "other": ((0.5, 0.75), (0.5, 0.75)), "vocals": ((0.0, 0.06), (0.0, 0.06))},
    "double_drop": {"drums": ((0.94, 1.0), (0.5, 0.51)), "bass": ((0.93, 0.95), (0.93, 0.95)),
                    "other": ((0.94, 1.0), (0.0, 0.5)), "vocals": ((0.47, 0.5), (0.5, 0.51))},
}


def stem_plan(art: str, takte: int, gesang_takt: int = -1) -> dict:
    """{Stem: ((A von, bis), (B von, bis))} als Anteile der Blende. Die Gesangs-Uebergaben folgen
    `gesang_takt` (die Regie setzt ihn aus den Profilen), sonst die feste Aufteilung STEM_PLAN.

    - acapella: A's Instrumente gehen am Anfang (B's kommen), A's Gesang laeuft ueber B weiter
      und klingt einen Takt nach seiner letzten Zeile (`gesang_takt`) aus; B singt erst danach.
    - gesang_zuerst: B's Gesang kommt sofort ueber A's Instrumental, B's Musik erst ab
      `gesang_takt` - dann tauschen Drums, Bass und Rest.
    - double_drop: `gesang_takt` ist der gemeinsame Drop. A's Drop bleibt voll, auch sein Bass. B's
      Instrumente kommen ueber den Aufbau, B's Drums und Stimme mit dem Drop (A singt bis zum Drop, B ab
      dem Drop: nie zwei), B ohne Bass. Am Ende der Bass-Switch auf B, dann geht A (Runde 9).
    """
    if art not in ("acapella", "gesang_zuerst", "double_drop") or not 0 < gesang_takt <= takte:
        return STEM_PLAN[art]
    t, g = 1 / max(1, takte), gesang_takt / max(1, takte)
    if art == "double_drop":
        return {"drums": ((1 - t, 1.0), (g, g + t / 8)), "other": ((1 - t, 1.0), (0.0, g)),
                "bass": ((1 - t - t / 8, 1 - t + t / 8),) * 2, "vocals": ((g - t / 4, g), (g, g + t / 8))}
    w = max(2 * t, min(0.25, 8 * t))                   # Instrumenten-Tausch: ein Viertel, hoechstens 8 Takte
    if art == "acapella":
        # Singt A bis ans Fensterende (danach still), bleibt die Stimme voll: kein Ausblenden mitten in
        # A's letztem Wort (Runde 6: "endet zu abrupt"); das Echo klingt hinter der Blende aus
        va = g
        return {"drums": ((0.0, w), (0.0, w)), "other": ((0.0, w), (0.0, w)),
                "bass": ((w / 2 - t / 8, w / 2 + t / 8),) * 2,
                "vocals": ((va, va + t), (min(1.0, va + 4 * t), min(1.0, va + 5 * t)))}   # erst nach A's Echo
    e = min(1.0, g + w)                                # B's Musik kommt, A's geht
    m = (g + e) / 2
    return {"drums": ((g, e), (g, e)), "other": ((g, e), (g, e)), "bass": ((m - t / 8, m + t / 8),) * 2,
            "vocals": ((g, e), (0.0, t))}             # B's Gesang sofort; A's Spur geht mit A's Musik
    # (A singt ab B's erster Zeile nicht mehr - Regie; die Spur enthaelt sonst A-Klangreste)


def _rampe(n: int, von: float, bis: float) -> np.ndarray:
    """Equipotente Einblendkurve (0->1) zwischen den Anteilen von..bis der Laenge."""
    t = (np.arange(n) / max(1, n)).astype(np.float32)
    x = np.clip((t - von) / max(1e-9, bis - von), 0.0, 1.0)
    return np.sin(x * np.pi / 2)[:, None].astype(np.float32)


def _baender(x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    tief, rest = mix.band_teilen(x, RATE, 200.0)
    mitte, hoch = mix.band_teilen(rest, RATE, 2000.0)
    return tief, mitte, hoch


def _echo(a: np.ndarray, schlag_n: int) -> np.ndarray:
    """A spielt einen Schlag, dann Echo-Fahne (1 Schlag Delay, Feedback 0,7: klingt ueber ~4 Takte aus)."""
    n = len(a)
    huelle = np.zeros((n, 1), np.float32)
    flanke = max(1, int(0.01 * RATE))
    huelle[:schlag_n] = 1.0
    huelle[schlag_n:schlag_n + flanke, 0] = np.linspace(1.0, 0.0, min(flanke, max(0, n - schlag_n)))
    trocken = a * huelle
    aus = trocken.copy()
    for k in range(1, 17):
        d = k * schlag_n
        if d >= n:
            break
        aus[d:] += trocken[:n - d] * (0.7 ** k)
    return aus


def mischen(art: str, a: np.ndarray, b: np.ndarray, takte: int) -> np.ndarray:
    """Mischt zwei gleich lange, taktsynchrone Abschnitte nach `art`."""
    n = min(len(a), len(b))
    a, b = a[:n], b[:n]
    if art == "eq":
        return mix._fade_segment(a, b, RATE, True)
    if art == "filter":
        # Hochpass-Sweep auf A, Tiefpass oeffnet auf B: B's Hoehen kommen zuerst,
        # A's Hoehen gehen zuletzt; die Baesse tauschen kurz in der Mitte (nie zwei,
        # nie keiner). Je Band: A (von, bis), B (von, bis).
        aus = np.zeros_like(a)
        for teil_a, teil_b, ((va, ba), (vb, bb)) in zip(_baender(a), _baender(b), FILTER_FENSTER):
            aus += teil_a * np.sqrt(1 - _rampe(n, va, ba) ** 2) + teil_b * _rampe(n, vb, bb)
        return aus
    if art == "echo":
        takt_n = n // max(1, takte)
        b_ein = _rampe(n, takt_n / n, min(1.0, 2 * takt_n / n)) if takt_n < n else _rampe(n, 0, 1)   # B ueber 1 Takt
        return _echo(a, max(1, takt_n // 4)) + b * b_ein
    if art == "schnitt":
        kurz = min(1.0, 0.01 * RATE / max(1, n))
        return a * (1 - _rampe(n, 0.0, kurz)) + b * _rampe(n, 0.0, kurz)
    # crossfade und alles ohne Stems: equipotent
    aus_k, ein_k = mix.equal_power_blende(n)
    return a * aus_k[:, None] + b * ein_k[:, None]


# --- Art "eigen": Bausteine je Kategorie (Lautstaerke, EQ, Filter, Effekt, Loop) --------------

FILTER_PLAN = {"keiner": (), "tp_aus": ("a_tp",), "tp_ein": ("b_tp",), "tp_beide": ("a_tp", "b_tp"),
               "hp_aus": ("a_hp",), "hp_ein": ("b_hp",), "hp_beide": ("a_hp", "b_hp"),
               "tp_ein_hp_aus": ("b_tp", "a_hp"), "hp_ein_tp_aus": ("b_hp", "a_tp"),
               "hp_aus_reso": ("a_hp",), "tp_aus_reso": ("a_tp",)}
KANTE_S = 0.01      # "hart" = 10 ms Rampe: hoerbar hart, aber ohne Knacken
HALL_S = 2.4        # Nachhallzeit (RT60)
NASS = {"hall": 0.8, "echo": 1.3, "delay": 1.1, "pingpong": 1.4}   # Runde 9: Fahnen unter B kaum hoerbar   # Echo-/Delay-Out muss ueber B hoerbar bleiben


def _huellen(e: Einstellungen, takte: int, n: int, kante: float) -> dict:
    """Alle Huellkurven der Art "eigen" an n Stellen (Ton: je Sample, Anzeige: 64 Punkte).

    Werte 0..1. None = Baustein inaktiv (spart Rechenzeit). Filter: 0 offen, 1 zu.
    """
    x = (np.arange(n) / max(1, n)).astype(np.float32)

    def ein(v: float, b: float) -> np.ndarray:
        return np.sin(np.pi / 2 * np.clip((x - v) / max(1e-9, b - v), 0, 1)).astype(np.float32)

    def aus(v: float, b: float) -> np.ndarray:
        return np.cos(np.pi / 2 * np.clip((x - v) / max(1e-9, b - v), 0, 1)).astype(np.float32)

    k, takt = kante, 1.0 / max(1, takte)
    h: dict = dict.fromkeys(("a_tief", "b_tief", "a_mitte", "b_mitte", "a_hoch", "b_hoch",
                             "a_tp", "a_hp", "b_tp", "b_hp", "a_send", "b_send", "nass_ab", "b_rueck"))
    h["a_vol"], h["b_vol"] = {
        "nahtlos": lambda: (aus(0, 1), ein(0, 1)),
        "linear": lambda: (1 - x, x.copy()),
        "ueberlappung": lambda: (aus(0.5, 1), ein(0, 0.5)),
        "hart_ein": lambda: (aus(0, 1), ein(0, k)),
        "hart_aus": lambda: (aus(1 - k, 1), ein(0, 1)),
        "hart_beide": lambda: (aus(1 - k, 1), ein(0, k)),
        "mitte": lambda: (aus(0.5 - k / 2, 0.5 + k / 2), ein(0.5 - k / 2, 0.5 + k / 2)),
        # A hart weg in der Mitte (ins Echo), B kommt ueber einen Takt (Runde 10: "B kommt zu ruckartig")
        "mitte_weich": lambda: (aus(0.5 - k / 2, 0.5 + k / 2), ein(0.5 - k / 2, 0.5 + takt)),
        "frueh": lambda: (aus(0, 0.25), ein(0, 0.25)),
        "spaet": lambda: (aus(0.75, 1), ein(0.75, 1)),
        # A voll bis in den letzten Takt, dann ein Takt Ausblenden: die Effektfahne (Send vor dem
        # Fader) klingt weiter - kein harter Schluss (Uebergangstest Runde 3: "endet zu abrupt")
        "letzter_takt": lambda: (aus(1 - takt, 1), ein(0, 1)),
        # Drop-Swap: A spielt bis zum Schluss (Trick am Ende); B's Aufbau kommt in den letzten (hoechstens 4)
        # Takten dazu, sein Drop schlaegt nach der Blende ein (Runde 8: "B hoert man erst nach dem Uebergang")
        "drop": lambda: (aus(1 - k, 1), ein(1 - min(0.5, 4 * takt), 1 - min(0.25, 2 * takt))),
        # Double Drop: B kommt im ersten Takt voll dazu (Bass per EQ erst am Drop), A geht im letzten
        "doppel": lambda: (aus(1 - takt, 1), ein(0, takt)),
    }[e.lautstaerke]()
    if e.trick == "wechsel" and 0 < e.gesang_takt < takte - 2:
        # Drop-Cuts (Runde 10: "Drops aufeinanderlegen und dann hin und her wechseln"): vor dem Drop nur A,
        # ab dem Drop taktweise A/B, die letzten 2 Takte B. Immer nur ein Song (mit seinem Bass) hoerbar.
        g = e.gesang_takt
        b_an = np.zeros_like(x)
        for t0 in range(g, takte):
            if (t0 - g) // 2 % 2 == 1 or t0 >= takte - 2:
                b_an = np.maximum(b_an, ein(t0 * takt, t0 * takt + k) * aus((t0 + 1) * takt - k, (t0 + 1) * takt)
                                  if t0 < takte - 1 else ein(t0 * takt, t0 * takt + k))
        h["a_vol"], h["b_vol"] = 1 - b_an, b_an
    if e.trick == "teaser" and takte >= 4:
        # Crossfader-Cuts: in den Takten vor dem Ende blitzt B auf dem letzten Schlag auf (A ist dann weg)
        gate = np.zeros_like(x)
        for t0 in (range(takte - 8, takte - 4) if takte >= 8 else range(takte - 4, takte - 1)):
            gate = np.maximum(gate, ein((t0 + 0.75) * takt, (t0 + 0.75) * takt + k)
                              * aus((t0 + 1) * takt - k, (t0 + 1) * takt))
        h["a_vol"], h["b_vol"] = h["a_vol"] * (1 - gate), np.maximum(h["b_vol"], gate)

    # EQ: Basswechsel auf einer Taktgrenze, ueber einen Schlag (nie zwei Baesse, nie keiner)
    def tausch(p: float) -> tuple[np.ndarray, np.ndarray]:
        return aus(p - takt / 8, p + takt / 8), ein(p - takt / 8, p + takt / 8)

    if e.eq == "profi":
        # Wie am Club-Mixer: B's Fader in einem Takt hoch, A's im letzten Takt runter; die EQs
        # machen die Blende. B's Hoehen zuerst (Hi-Hats als neue Ebene, Anstieg in dB),
        # Mitten tauschen in der Mitte (Gesang/Melodie nie doppelt), Bass-Tausch in einem Schlag
        # auf `bass_takt` (wo B's Bassline einsetzt), A's Hoehen gehen zuletzt.
        def db_ein(v: float, b: float, tiefe: float = 30.0) -> np.ndarray:
            r = np.clip((x - v) / max(1e-9, b - v), 0, 1)
            return np.where(x < v, 0.0, 10 ** (-tiefe * (1 - r) / 20)).astype(np.float32)

        def db_aus(v: float, b: float, tiefe: float = 30.0) -> np.ndarray:
            r = np.clip((x - v) / max(1e-9, b - v), 0, 1)
            return np.where(r >= 1, 0.0, 10 ** (-tiefe * r / 20)).astype(np.float32)

        h["a_vol"], h["b_vol"] = aus(1 - takt, 1), ein(0, takt)
        h["b_hoch"], h["a_hoch"] = db_ein(0, 3 / 8), db_aus(5 / 8, 1)
        h["a_mitte"], h["b_mitte"] = aus(3 / 8, 5 / 8), ein(3 / 8, 5 / 8)
        p = e.bass_takt / takte if 0 < e.bass_takt < takte else 0.5
        h["a_tief"], h["b_tief"] = aus(p - takt / 8, p + takt / 8), ein(p - takt / 8, p + takt / 8)
    elif e.eq == "bass_mitte":
        h["a_tief"], h["b_tief"] = tausch(0.5)
    elif e.eq == "bass_anfang":
        h["a_tief"], h["b_tief"] = tausch(takt if takte > 1 else 0.25)
    elif e.eq == "bass_ende":
        h["a_tief"], h["b_tief"] = tausch(1 - takt if takte > 1 else 0.75)
    elif e.eq == "drei_band":   # Hoehen von B zuerst, Mitten in der Mitte, Bass-Tausch, A's Hoehen zuletzt
        (ta, tb), (ma, mb), (ha, hb) = FILTER_FENSTER
        h["a_tief"], h["b_tief"] = aus(*ta), ein(*tb)
        h["a_mitte"], h["b_mitte"] = aus(*ma), ein(*mb)
        h["a_hoch"], h["b_hoch"] = aus(*ha), ein(*hb)
    elif e.eq == "bass_schnell":   # A verliert den Bass im ersten Takt, B bringt ihn mit
        h["a_tief"] = aus(0, takt)
    elif e.eq == "bass_lang":
        h["a_tief"], h["b_tief"] = aus(0, 1), ein(0, 1)
    elif e.eq == "bass_takt":   # Double Drop: nur ein Bass, Tausch genau auf `bass_takt` (dem Drop)
        h["a_tief"], h["b_tief"] = tausch(e.bass_takt / takte if 0 < e.bass_takt < takte else 0.5)

    for schluessel in FILTER_PLAN[e.filter]:   # A schliesst ueber die Blende, B oeffnet
        h[schluessel] = x.copy() if schluessel[0] == "a" else 1 - x
        if schluessel[0] == "a" and e.effekt != "keiner":
            # Abstimmung: der Effekt bekommt A nach dem Filter. Ganz zu (2 kHz Hochpass bzw.
            # 200 Hz Tiefpass) bliebe fuer Echo/Hall nichts uebrig - wie DJs: Filter auf ~60 %,
            # dann ins Echo.
            h[schluessel] = np.minimum(h[schluessel], 0.6).astype(np.float32)

    if e.effekt != "keiner":
        modus = e.effekt.split("_", 1)[1]
        p = 0.5 if modus == "mitte_aus" else 1.0
        # Wie am Mixer: der Effekt kommt erst kurz vor dem Ausstieg dazu (die letzten 1-2 Takte),
        # wenn A noch klingt; der Send greift vor EQ und Fader (mischen_eigen). Danach klingt
        # die Fahne ueber B aus. Ueber die ganze Blende verteilt waere er dort, wo A leise ist.
        fx = min(2 * takt, p / 2)
        h["a_send"] = np.where(x < p, ein(p - fx, p - 0.75 * fx), 0).astype(np.float32)
        if p < 1:   # A endet am Effektpunkt, die Fahne klingt aus
            h["a_vol"] = h["a_vol"] * aus(p, p + k)
        if modus == "ende_ab":
            h["nass_ab"] = aus(1 - k, 1)
    if e.effekt_ein == "rueckhall":   # Reverse-Reverb: schwillt bis zu B's Einsatz (b_vol halb oben)
        h["b_rueck"] = float(np.argmax(h["b_vol"] >= 0.5)) / max(1, n)
    if e.effekt_ein == "hall":   # B kommt aus dem Hall: erst nass (vor dem Fader), nach ~2 Takten trocken
        h["b_send"] = aus(min(takt, 0.25), min(3 * takt, 0.5))
    return h


def _baender_gewichten(x: np.ndarray, tief, mitte, hoch) -> np.ndarray:
    if tief is None and mitte is None and hoch is None:
        return x
    aus = np.zeros_like(x)
    for teil, g in zip(_baender(x), (tief, mitte, hoch)):
        aus += teil if g is None else teil * g[:, None]
    return aus


def _biquads(fc: np.ndarray, art: str, reso: bool = False) -> np.ndarray:
    """4-poliger Butterworth (2 RBJ-Biquads) je Block: (bloecke, 2, 6). `reso`: Resonanzspitze (~+10 dB)."""
    w0 = 2 * np.pi * np.clip(fc, 10.0, 0.45 * RATE) / RATE
    cos = np.cos(w0)
    teile = []
    for q in (0.5412, 4.0 if reso else 1.3066):
        alpha = np.sin(w0) / (2 * q)
        b1 = (1 - cos) if art == "tp" else -(1 + cos)
        b0 = np.abs(b1) / 2
        a0 = 1 + alpha
        teile.append(np.stack([b0 / a0, b1 / a0, b0 / a0, np.ones_like(w0),
                               -2 * cos / a0, (1 - alpha) / a0], axis=1))
    return np.stack(teile, axis=1)


def _sweep(x: np.ndarray, menge: np.ndarray | None, art: str, reso: bool = False) -> np.ndarray:
    """Zeitvariabler Tief-/Hochpass (DJ-Filter): menge 0 = offen, 1 = zu (Tiefpass 200 Hz,
    Hochpass 2 kHz). Koeffizienten je Block, Filterzustand laeuft durch."""
    if menge is None or float(np.max(menge)) < 1e-3:
        return x
    from scipy.signal import sosfilt, sosfilt_zi

    blk = 1024   # 23 ms: Frequenzschritt je Block < 1 %, unhoerbar; kleinere Bloecke kosten nur Zeit
    mitte = np.minimum(np.arange(0, len(x), blk) + blk // 2, len(x) - 1)
    m = menge[mitte].astype(np.float64)
    fc = 20000.0 * 0.01 ** m if art == "tp" else 20.0 * 100.0 ** m
    sos = _biquads(fc, art, reso)
    zi = sosfilt_zi(sos[0])[:, :, None] * x[0][None, None, :]   # eingeschwungen: kein Startknacks
    y = np.empty_like(x)
    for i, s in enumerate(range(0, len(x), blk)):
        y[s:s + blk], zi = sosfilt(sos[i], x[s:s + blk], axis=0, zi=zi)
    rand = min(int(KANTE_S * RATE), len(x) // 2)
    r = np.linspace(0, 1, rand, dtype=np.float32)[:, None]
    if menge[0] < 0.05:     # offen am Anfang: weich vom ungefilterten Signal uebernehmen
        y[:rand] = x[:rand] * (1 - r) + y[:rand] * r
    if menge[-1] < 0.05:    # offen am Ende: nahtlos ins ungefilterte Signal danach
        y[-rand:] = y[-rand:] * (1 - r) + x[-rand:] * r
    return y.astype(np.float32)


def _hall_ir() -> np.ndarray:
    """Stereo-Hall: abklingendes Rauschen (RT60 2,4 s), abgedunkelt, 20 ms Vorverzoegerung."""
    m = int(HALL_S * RATE)
    t = np.arange(m) / RATE
    ir = np.random.default_rng(7).standard_normal((m, 2)) * np.exp(-6.9 * t / HALL_S)[:, None]
    ir = mix._filtern(mix._sos("low", 5000.0, RATE), ir.astype(np.float32))
    ir = np.concatenate([np.zeros((int(0.02 * RATE), 2), np.float32), ir])
    return (ir / np.sqrt(np.sum(ir ** 2, axis=0))).astype(np.float32)


def _nass(typ: str, send: np.ndarray, schlag_n: float) -> np.ndarray:
    """Effektanteil (laenger als send: die Fahne klingt aus)."""
    if typ == "hall":
        from scipy.signal import oaconvolve

        ir = _hall_ir()
        return NASS["hall"] * np.stack([oaconvolve(send[:, c], ir[:, c]) for c in (0, 1)],
                                       axis=1).astype(np.float32)
    art = typ.rstrip("0123456789")   # echo50 / delay100 ...
    prozent = int(typ[len(art):])
    verz = max(1, int(round(schlag_n * prozent / 100)))
    rueck = {"echo": 0.7, "pingpong": 0.55}.get(art, 0.35)
    wiederholungen = int(np.ceil(np.log(0.01) / np.log(rueck)))
    aus = np.zeros((len(send) + wiederholungen * verz, 2), np.float32)
    for k in range(1, wiederholungen + 1):
        if art == "pingpong":   # abwechselnd links/rechts
            aus[k * verz:k * verz + len(send), k % 2] += send.mean(axis=1) * np.float32(rueck ** k)
        else:
            aus[k * verz:k * verz + len(send)] += send * np.float32(rueck ** k)
    if art == "echo":   # Echo dunkel und weich, Delay klar
        aus = mix._filtern(mix._sos("low", 3000.0, RATE), aus)
    return NASS[art] * aus


def _loop_plan(e: Einstellungen, takte: int) -> list[tuple[int, int, int]]:
    """Loop-Abschnitte (von, bis, Groesse) in Achteln der Blende; Quelle ist immer `von`
    des ersten Abschnitts. Wie DJs Loops einsetzen:
    - 4/8/16 Schlaege: das Outro von A wird ab Blendenbeginn festgehalten (A bleibt
      hoerbar, seine naechsten Teile - z. B. Gesang - kommen nicht mehr).
    - 1/2 Schlaege: Stutter-Loop in den 2 Takten, bevor A leise wird.
    - Rolle: 4 Takte vor dem Leisewerden 4 -> 2 -> 1 -> 1/2 Schlag, dann bleibt 1/2.
    """
    ende = takte * 8
    if e.loop in ("4", "8", "16", "32"):
        start = min(max(0, e.loop_start), max(0, takte - 1)) * 8
        return [(start, ende, int(e.loop) * 2)]
    vol = _huellen(e, takte, 256, 0.01)["a_vol"]
    leise = int(np.argmax(vol < 0.5)) if np.any(vol < 0.5) else 256
    aus = max(8, int(round(leise / 256 * ende / 8)) * 8)   # Takt, an dem A leise wird
    if e.loop == "rolle":
        s0 = max(0, aus - 32)
        q = [s0 + i * (aus - s0) // 4 for i in range(5)]
        return [(q[i], q[i + 1], g) for i, g in enumerate((8, 4, 2, 1))] + [(aus, ende, 1)]
    return [(max(0, aus - 16), ende, int(e.loop) * 2)]


def _achtel(takt_n: np.ndarray) -> np.ndarray:
    takte = len(takt_n) - 1
    return np.round(np.concatenate([np.linspace(takt_n[i], takt_n[i + 1], 9)[:-1]
                                    for i in range(takte)] + [[takt_n[-1]]])).astype(int)


def _loopen(a: np.ndarray, takt_n: np.ndarray, plan: list[tuple[int, int, int]]) -> np.ndarray:
    """A loopt im Taktraster nach `_loop_plan` (Naht je Loop-Sprung equipotent, ~6 ms)."""
    achtel = _achtel(takt_n)
    aus = a.copy()
    f = 256
    rein = np.sin(np.linspace(0, np.pi / 2, f, dtype=np.float32))[:, None]
    quelle = achtel[plan[0][0]]
    for von, bis, groesse in plan:
        for j in range(von, bis, groesse):
            ziel, laenge = achtel[j], achtel[min(j + groesse, bis)] - achtel[j]
            if ziel == quelle or laenge <= 0:   # erster Durchlauf = das Original selbst
                continue
            stueck = _ausschnitt(a, quelle, laenge + f)
            stueck = stueck[:max(0, min(len(stueck), len(aus) - ziel))]
            nf = min(f, len(stueck))
            aus[ziel:ziel + nf] = aus[ziel:ziel + nf] * rein[::-1][:nf] + stueck[:nf] * rein[:nf]
            aus[ziel + nf:ziel + len(stueck)] = stueck[nf:]
    return aus


def loop_info(e: Einstellungen, takt_s: np.ndarray) -> list[dict]:
    """Loop-Abschnitte in Blendensekunden fuer die Anzeige (Wellenform von A springt mit)."""
    if e.art != "eigen" or e.loop in ("keiner", "auto"):
        return []
    achtel = _achtel(np.asarray(takt_s, dtype=float) * RATE) / RATE
    plan = _loop_plan(e, len(takt_s) - 1)
    q = float(achtel[plan[0][0]])
    return [{"von": round(float(achtel[v]), 3), "bis": round(float(achtel[b]), 3), "quelle": round(q, 3),
             "laenge": round(float(achtel[min(v + g, len(achtel) - 1)] - achtel[v]), 4)}
            for v, b, g in plan if b > v]


# --- Loop-Wahl: wo und wie lang klingt ein Loop sauber? -----------------------------------------

def _beat_merkmale(x: np.ndarray, takt_n: np.ndarray) -> np.ndarray:
    """Klangbild je Schlag: 16 log. Frequenzbaender (40 Hz - 16 kHz) in dB, Zeile je Schlag."""
    grenzen = np.round(np.concatenate([np.linspace(takt_n[i], takt_n[i + 1], 5)[:-1]
                                       for i in range(len(takt_n) - 1)] + [[takt_n[-1]]])).astype(int)
    mono = x.mean(axis=1) if x.ndim > 1 else x
    f_n = 4096
    baender = np.digitize(np.fft.rfftfreq(f_n, 1 / RATE), np.geomspace(40, 16000, 17))
    fenster = np.hanning(f_n).astype(np.float32)
    zeilen = []
    for a0, a1 in zip(grenzen[:-1], grenzen[1:]):
        stueck = mix._auffuellen(mono[a0:min(a1, a0 + f_n)], f_n)
        spek = np.abs(np.fft.rfft(stueck * fenster)) ** 2
        zeilen.append(10 * np.log10(np.bincount(baender, spek, minlength=18)[1:17] + 1e-9))
    return np.array(zeilen)


def _aehnlich(f: np.ndarray, i: int, j: int, n: int) -> float:
    """Mittlere Aehnlichkeit (Kosinus der Klangfarben-Form) von Schlag i.. und j.. ueber n Schlaege."""
    n = min(n, len(f) - i, len(f) - j)
    if n <= 0:
        return 0.0
    a, b = f[i:i + n], f[j:j + n]
    a, b = a - a.mean(axis=1, keepdims=True), b - b.mean(axis=1, keepdims=True)
    cos = np.sum(a * b, axis=1) / np.maximum(np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1), 1e-9)
    pegel = 1.0 - np.minimum(1.0, np.abs(f[i:i + n].mean(1) - f[j:j + n].mean(1)) / 12.0)
    return float(np.mean(cos * pegel))


def loop_waehlen(a: np.ndarray, takt_n: np.ndarray, meiden: np.ndarray | None = None,
                 groessen: tuple[int, ...] = (8, 4, 2, 1), fenster: int | None = None) -> tuple[int, int, float]:
    """(Start-Takt, Laenge in Takten, Guete 0..1) des saubersten Loops im Fenster `a`.

    Sauber = der Abschnitt wiederholt sich im Original schon fast gleich (dann faellt der
    Loop nicht auf), kein Gesang darin (`meiden` je Takt), auf Taktgrenze, moeglichst spaet
    (A spielt vorher normal weiter) und eher lang (4/8 Takte klingen musikalischer als 1).

    `fenster`: nur die ersten n Takte duerfen geloopt werden; `a` darf darueber hinaus laenger
    sein, damit auch gegen das, was hinter der Blende im Original folgt, verglichen wird."""
    takte = len(takt_n) - 1
    f = _beat_merkmale(a, takt_n)
    pegel = f.mean(axis=1)
    lebt = pegel > pegel.max() - 35.0                  # Schlaege mit Ton (A kann im Fenster enden)
    verfuegbar = int(np.flatnonzero(lebt)[-1] // 4 + 1) if lebt.any() else 0
    erlaubt = min(verfuegbar, fenster if fenster else takte)   # Loops nur innerhalb des Fensters
    n_fenster = fenster if fenster else takte
    best = (0, min(4, max(1, n_fenster)), 0.0)
    best_p = -9.0
    for L in groessen:
        for s0 in range(0, max(0, erlaubt - L) + 1):
            if L > n_fenster or s0 + L > erlaubt:
                continue
            if meiden is not None and np.any(np.asarray(meiden)[s0:s0 + L]):
                continue
            folge = min(L, verfuegbar - (s0 + L))
            if folge >= 1:   # was im Original folgt, aehnelt dem Abschnitt -> Loop faellt nicht auf
                guete = _aehnlich(f, 4 * s0, 4 * (s0 + L), 4 * folge)
            elif L >= 2:     # nichts mehr dahinter: Haelften des Abschnitts vergleichen
                guete = _aehnlich(f, 4 * s0, 4 * s0 + 2 * L, 2 * L) - 0.05
            else:
                continue
            p = guete + 0.04 * np.log2(L) + 0.08 * s0 / max(1, n_fenster) + (0.03 if s0 % 4 == 0 else 0.0)
            if p > best_p:
                best_p, best = p, (s0, L, guete)
    return best


def _intro_loop(b_audio: np.ndarray, bbar: np.ndarray, j0: int, k: int, mal: int):
    """B's erste `k` Takte ab j0 `mal`-mal zusaetzlich: virtuelles Audio + Taktraster und die
    Rueckrechnung virtuelle -> Originalzeit. B's Gesang kommt so spaeter, die Blende hat Zeit."""
    ib0, ibk = int(round(bbar[j0] * RATE)), int(round(bbar[j0 + k] * RATE))
    stueck = b_audio[ib0:ibk]
    d = len(stueck)
    f = min(256, d)
    rein = np.sin(np.linspace(0, np.pi / 2, f, dtype=np.float32))[:, None]
    teile = [b_audio[:ibk]]
    for _ in range(mal):   # je Durchgang: was natuerlich folgen wuerde, kurz aus-, den Anfang einblenden
        neu = stueck.copy()
        neu[:f] = mix._auffuellen(b_audio[ibk:ibk + f], f) * rein[::-1] + stueck[:f] * rein
        teile.append(neu)
    teile.append(b_audio[ibk:])
    dauer = d / RATE
    raster_v = np.concatenate([bbar[:j0 + k]] + [bbar[j0:j0 + k] + r * dauer for r in range(1, mal + 1)]
                              + [bbar[j0 + k:] + mal * dauer])
    t0 = bbar[j0]

    def rueck(t: np.ndarray) -> np.ndarray:
        t = np.asarray(t, float)
        return np.where(t <= t0, t, np.where(t < t0 + (mal + 1) * dauer, t0 + (t - t0) / (mal + 1),
                                             t - mal * dauer))

    return np.concatenate(teile).astype(np.float32), raster_v, rueck


# --- Pegel-Deckel je Band ---------------------------------------------------------------------

def _takt_db(x: np.ndarray, takt_n: np.ndarray) -> np.ndarray:
    q = np.concatenate([[0.0], np.cumsum(np.mean(np.asarray(x, np.float64) ** 2, axis=1))])
    g = np.clip(takt_n, 0, len(x))
    return 10 * np.log10((q[g[1:]] - q[g[:-1]]) / np.maximum(1, np.diff(g)) + 1e-12)


def _deckeln(y: np.ndarray, ra: np.ndarray, rb: np.ndarray, takt_n: np.ndarray,
             toleranz: float = 1.5, max_db: float = 6.0) -> np.ndarray:
    """Kein Buckel: je Takt hoechstens so laut wie der lautere der beiden Songs (+1,5 dB) in
    diesem Band. Nur absenken (gewollte Ausblendungen bleiben), weich ueber die Taktmitten."""
    if len(takt_n) < 2:
        return y
    zuviel = _takt_db(y, takt_n) - np.maximum(_takt_db(ra, takt_n), _takt_db(rb, takt_n)) - toleranz
    g_db = -np.clip(zuviel, 0.0, max_db)
    if not np.any(g_db < -0.05):
        return y
    mitte = (takt_n[:-1] + takt_n[1:]) / 2
    g = 10 ** (np.interp(np.arange(len(y)), mitte, g_db) / 20)
    return (y * g[:, None]).astype(np.float32)


def _abspielen(a: np.ndarray, pos: np.ndarray) -> np.ndarray:
    """a an gebrochenen Sample-Positionen (linear interpoliert)."""
    idx = np.arange(len(a))
    return np.stack([np.interp(pos, idx, a[:, c]) for c in range(a.shape[1])], axis=1).astype(np.float32)


def _bremse(a: np.ndarray, n: int) -> np.ndarray:
    """Tape-Stop: die letzten n Samples laeuft A immer langsamer bis zum Stillstand (Tonhoehe faellt mit)."""
    n = min(n, len(a))
    if n < 2:
        return a
    s, t = len(a) - n, np.arange(n) / n
    aus = a.copy()
    aus[s:] = _abspielen(a, s + n * (t - t * t / 2)) * np.sqrt(1 - t)[:, None].astype(np.float32)
    return aus


def _spinback(a: np.ndarray, n: int) -> np.ndarray:
    """Backspin: an den letzten n Samples wird A angehalten und schnell rueckwaerts gedreht, dann laeuft er aus."""
    n = min(n, len(a))
    if n < 2:
        return a
    s, t = len(a) - n, np.arange(n) / n
    v = np.where(t < 0.08, 1 - 5 * t / 0.08, -4 * ((1 - t) / 0.92) ** 2)   # +1 -> -4 -> 0
    pos = np.clip(s + np.cumsum(v), 0, len(a) - 1)
    aus = a.copy()   # Runde 11: "Backspin lauter" - haelt den Pegel laenger, statt gleich abzufallen
    aus[s:] = _abspielen(a, pos) * (1.2 * (1 - t) ** 0.3)[:, None].astype(np.float32)
    return aus


def _flanger(a: np.ndarray, tiefe: np.ndarray, schlag_n: float) -> np.ndarray:
    """Flanger: A plus eine um 1-5 ms wandernde Kopie (LFO 2 Takte), Anteil `tiefe` (0..1 je Sample)."""
    idx = np.arange(len(a))
    lfo = 0.5 * (1 - np.cos(2 * np.pi * idx / max(1.0, 8 * schlag_n)))
    kopie = _abspielen(a, idx - (0.001 + 0.004 * lfo) * RATE)
    w = tiefe[:, None].astype(np.float32)          # am Ende 1:1 -> volle Kerben (vorher 0,7: zu zart)
    return ((a + w * kopie) / (1 + w)).astype(np.float32)


def _phaser(a: np.ndarray, tiefe: np.ndarray, schlag_n: float) -> np.ndarray:
    """Phaser: 4 Allpaesse (Eckfrequenz 300 Hz-3 kHz, LFO 2 Takte) + Original -> wandernde Kerben."""
    from scipy.signal import sosfilt

    blk = 1024
    mitte = np.minimum(np.arange(0, len(a), blk) + blk // 2, len(a) - 1)
    fc = 300.0 * 10 ** (0.5 * (1 - np.cos(2 * np.pi * mitte / max(1.0, 8 * schlag_n))))
    t = np.tan(np.pi * fc / RATE)
    k = (t - 1) / (t + 1)                      # Allpass 1. Ordnung: (k + z^-1) / (1 + k z^-1)
    zi = np.zeros((2, 2, a.shape[1]))
    nass = np.empty_like(a)
    for i, s in enumerate(range(0, len(a), blk)):
        # zwei Allpass-Stufen je Biquad: (k + z^-1)^2 / (1 + k z^-1)^2
        sos = np.array([[k[i] ** 2, 2 * k[i], 1.0, 1.0, 2 * k[i], k[i] ** 2]] * 2)
        nass[s:s + blk], zi = sosfilt(sos, a[s:s + blk], axis=0, zi=zi)
    w = tiefe[:, None].astype(np.float32)
    return ((a + w * nass) / (1 + w)).astype(np.float32)


def _gate(a: np.ndarray, takt_n: np.ndarray) -> np.ndarray:
    """Trans: A in den letzten 2 Takten im Achtel-Takt an/aus, im letzten in Sechzehnteln (Kanten 2 ms)."""
    takte = len(takt_n) - 1
    if takte < 2:
        return a
    g = np.ones(len(a), np.float32)
    for t0, teile in ((takte - 2, 8), (takte - 1, 16)):
        grenzen = np.linspace(takt_n[t0], takt_n[t0 + 1], teile + 1).astype(int)
        for s0, s1 in zip(grenzen[1::2], grenzen[2::2]):   # jede zweite Unterteilung stumm
            g[s0:s1] = 0.0
    from scipy.ndimage import uniform_filter1d

    g = uniform_filter1d(g, int(0.002 * RATE) | 1)
    return (a * g[:, None]).astype(np.float32)


def _crush(a: np.ndarray, tiefe: np.ndarray) -> np.ndarray:
    """Bitcrusher: Aufloesung 16 -> 7 Bit und Abtastung bis 1/8 (Sample-and-Hold), Anteil waechst mit `tiefe`
    bis 70 % (Runde 12: "etwas zu stark")."""
    stufe = 1 + np.round(7 * tiefe).astype(int)               # Halten ueber 1..8 Samples
    idx = np.arange(len(a))
    gehalten = a[idx - idx % np.maximum(1, stufe)]
    bits = 16 - 9 * tiefe
    q = (2.0 ** (bits - 1))[:, None]
    roh = np.round(gehalten * q) / q
    w = 0.7 * tiefe[:, None]
    return (a * (1 - w) + roh * w).astype(np.float32)


def _rueckhall(b: np.ndarray, p: int, schlag_n: float) -> np.ndarray:
    """Reverse-Reverb: der Hall von B's erstem Schlag ab `p`, rueckwaerts - er schwillt bis genau zu p an."""
    aus = np.zeros_like(b)
    x = b[p:p + int(schlag_n)]
    if len(x) < 16:
        return aus
    y = _nass("hall", x[::-1].copy(), schlag_n)[::-1]     # Fahne liegt jetzt vor dem Einsatz
    start = p + len(x) - len(y)
    lo = max(0, start)
    aus[lo:min(len(b), start + len(y))] = y[lo - start:min(len(y), len(b) - start)]
    aus[p:] = 0.0                                          # ab dem Einsatz spielt B trocken
    return aus


def _riser(n: int, m: int, pegel: float) -> np.ndarray:
    """Noise-Riser ueber die letzten m Samples: Rauschen, das mit dem Hochpass nach oben steigt und lauter wird."""
    aus = np.zeros((n, 2), np.float32)
    m = min(m, n)
    if m < 2:
        return aus
    t = np.arange(m) / m
    rauschen = np.random.default_rng(3).standard_normal((m, 2)).astype(np.float32)
    rauschen = _sweep(rauschen, (0.9 * t).astype(np.float32), "hp")
    aus[n - m:] = rauschen * (pegel * 10 ** (-24 * (1 - t) / 20))[:, None].astype(np.float32)
    return aus


def _trocken(a: np.ndarray, b: np.ndarray, h: dict, takt_n: np.ndarray) -> np.ndarray:
    """Trockene Blende: je Band EQ-Kurve x Fader, je Band gegen Buckel gedeckelt."""
    av, bv = h["a_vol"][:, None], h["b_vol"][:, None]
    gewichte = [(h[f"a_{k}"], h[f"b_{k}"]) for k in ("tief", "mitte", "hoch")]
    if all(ga is None and gb is None for ga, gb in gewichte):
        return _deckeln(a * av + b * bv, a, b, takt_n)
    aus = np.zeros_like(a)
    for ta, tb, (ga, gb) in zip(_baender(a), _baender(b), gewichte):
        teil = ta * (av if ga is None else ga[:, None] * av) + tb * (bv if gb is None else gb[:, None] * bv)
        aus += _deckeln(teil, ta, tb, takt_n)
    return aus


def mischen_eigen(a: np.ndarray, b: np.ndarray, e: Einstellungen, takt_n: np.ndarray
                  ) -> tuple[np.ndarray, np.ndarray]:
    """Art "eigen": (Blende, Nachlauf). Der Nachlauf (Hall-/Echofahne) wird nach der
    Blende auf B addiert. `takt_n`: Taktgrenzen der Blende in Samples (ab 0)."""
    n = min(len(a), len(b))
    a, b = a[:n], b[:n]
    takte = len(takt_n) - 1
    h = _huellen(e, takte, n, min(0.25, KANTE_S * RATE / max(1, n)))
    if e.loop not in ("keiner", "auto"):
        a = _loopen(a, takt_n, _loop_plan(e, takte))
    schlag_n = float(takt_n[-1]) / max(1, takte) / 4
    if e.trick == "flanger":   # schleicht sich ein, am Ende voll
        a = _flanger(a, np.sqrt(np.arange(n) / n), schlag_n)
    elif e.trick == "bremse":
        a = _bremse(a, int(2 * schlag_n))
    elif e.trick == "spinback":
        a = _spinback(a, int(3 * schlag_n))
    elif e.trick == "phaser":
        a = _phaser(a, np.sqrt(np.arange(n) / n), schlag_n)
    elif e.trick == "gate":
        a = _gate(a, takt_n)
    elif e.trick == "crush":
        a = _crush(a, np.sqrt(np.arange(n) / n))
    # Filter vor dem Effekt-Send (wie am Mixer), EQ und Fader danach: ein Echo/Hall bekommt A
    # auch dann, wenn die EQs A schon wegdrehen - sonst waere der Effekt nicht zu hoeren.
    reso = e.filter.endswith("_reso")
    a = _sweep(_sweep(a, h["a_tp"], "tp", reso), h["a_hp"], "hp", reso)
    b = _sweep(_sweep(b, h["b_tp"], "tp"), h["b_hp"], "hp")
    blende = _trocken(a, b, h, takt_n)
    if e.trick == "riser":   # ueber die letzten (hoechstens 8) Takte, am Ende fast so laut wie A
        m = int(takt_n[-1] - takt_n[max(0, takte - 8)])
        blende = blende + _riser(n, m, 0.9 * float(np.sqrt(np.mean(a.astype(np.float64) ** 2))))
    if h["b_rueck"] is not None:
        blende = blende + 1.5 * _rueckhall(b, int(h["b_rueck"] * n), schlag_n)
    nachlauf = np.zeros((0, 2), np.float32)
    for seite, typ, send in (("a", e.effekt.split("_")[0], h["a_send"]), ("b", "hall", h["b_send"])):
        if send is None:
            continue
        nass = _nass(typ, (a if seite == "a" else b) * send[:, None], schlag_n)
        if seite == "b":
            nass *= np.float32(0.6)   # B laeuft parallel zu A: Hall-Einstieg dezenter
        if seite == "a" and h["nass_ab"] is not None:   # abschneiden: Fahne endet mit der Blende
            nass = nass[:n] * h["nass_ab"][:, None]
        blende = blende + nass[:n]
        rest = nass[n:]
        if len(rest) > len(nachlauf):
            rest[:len(nachlauf)] += nachlauf
            nachlauf = rest
        else:
            nachlauf[:len(rest)] += rest
    return blende.astype(np.float32), nachlauf.astype(np.float32)


def kurven_eigen(e: Einstellungen, takte: int) -> dict[str, dict[str, np.ndarray]]:
    n = KURVEN_PUNKTE
    h = _huellen(e, takte, n, 0.01)
    x = np.arange(n) / n
    a = {"lautstaerke": h["a_vol"]}
    b = {"lautstaerke": h["b_vol"]}
    for name, band in (("bass", "tief"), ("mitten", "mitte"), ("hoehen", "hoch")):
        if h[f"a_{band}"] is not None or h[f"b_{band}"] is not None:
            a[name] = h[f"a_{band}"] if h[f"a_{band}"] is not None else np.ones(n)
            b[name] = h[f"b_{band}"] if h[f"b_{band}"] is not None else np.ones(n)
    for seite, d in (("a", a), ("b", b)):
        zu = [h[f"{seite}_{f}"] for f in ("tp", "hp") if h[f"{seite}_{f}"] is not None]
        if zu:
            d["filter"] = np.max(zu, axis=0)
    if h["a_send"] is not None:
        typ, modus = e.effekt.split("_", 1)
        p = 0.5 if modus == "mitte_aus" else 1.0
        fahne = np.where(x < p, h["a_send"], np.exp(-(x - p) * takte * 2))   # klingt aus
        a["hall" if typ == "hall" else "echo"] = fahne * (h["nass_ab"] if h["nass_ab"] is not None else 1)
    if h["b_send"] is not None:
        b["hall"] = h["b_send"]
    if e.loop not in ("keiner", "auto"):
        a["loop"] = np.zeros(n)
        for von, bis, _ in _loop_plan(e, takte):
            a["loop"][(x >= von / (8 * takte)) & (x < bis / (8 * takte))] = 1.0
    if e.loop_ein > 0 and e.loop_ein_mal > 0:
        b["loop"] = (x < min(1.0, e.loop_ein * (e.loop_ein_mal + 1) / max(1, takte))).astype(float)
    return {"a": a, "b": b}


KURVEN_PUNKTE = 64


def kurven(art: str, takte: int, e: Einstellungen | None = None) -> dict[str, dict[str, list[float]]]:
    """Automationskurven fuer die Anzeige (wie Spotify Mix), je Song und Parameter.

    Werte 0..1 an KURVEN_PUNKTE gleichmaessigen Stellen der Blende. Abgetastet aus
    denselben Fenstern/Huellkurven, die `mischen`/`mischen_stems` auf den Ton legen.
    Parameter: lautstaerke, bass (EQ), filter (1 = Filter zu), echo, gesang, drums.
    """
    n = KURVEN_PUNKTE
    ein = lambda von, bis: _rampe(n, von, bis)[:, 0]            # noqa: E731
    aus = lambda von, bis: np.sqrt(1 - ein(von, bis) ** 2)       # noqa: E731
    x = np.arange(n) / n
    a: dict[str, np.ndarray] = {}
    b: dict[str, np.ndarray] = {}
    if art == "eigen":
        a, b = kurven_eigen(e or Einstellungen(), takte).values()
    elif art in STEM_PLAN:
        namen = {"drums": "drums", "bass": "bass", "other": "lautstaerke", "vocals": "gesang"}
        for stem, ((va, ba), (vb, bb)) in stem_plan(art, takte, e.gesang_takt if e else -1).items():
            a[namen[stem]], b[namen[stem]] = aus(va, ba), ein(vb, bb)
    elif art == "eq":
        a["lautstaerke"], b["lautstaerke"] = aus(0, 1), ein(0, 1)
        a["bass"], b["bass"] = (x < 0.5).astype(float), (x >= 0.5).astype(float)
    elif art == "filter":
        ab = [(aus(*fa), ein(*fb)) for fa, fb in FILTER_FENSTER]
        a["lautstaerke"], b["lautstaerke"] = aus(0.5, 1.0), ein(0.0, 0.5)
        a["bass"], b["bass"] = ab[0]
        a["filter"] = 1 - np.mean([k[0] for k in ab], axis=0)    # Hochpass schliesst
        b["filter"] = 1 - np.mean([k[1] for k in ab], axis=0)    # Tiefpass oeffnet
    elif art == "echo":
        takt, schlag = 1 / max(1, takte), 1 / max(1, takte) / 4
        a["lautstaerke"] = (x < schlag).astype(float)
        a["echo"] = np.where(x < schlag, 0.0, 0.7 ** ((x - schlag) / schlag))
        b["lautstaerke"] = np.clip((x - takt) / takt, 0.0, 1.0)
    elif art == "schnitt":
        a["lautstaerke"], b["lautstaerke"] = np.zeros(n), np.ones(n)
    else:   # crossfade
        a["lautstaerke"], b["lautstaerke"] = aus(0, 1), ein(0, 1)
    runden = lambda d: {k: [round(float(v), 3) for v in werte] for k, werte in d.items()}  # noqa: E731
    return {"a": runden(a), "b": runden(b)}


def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x, dtype=np.float64)))) if x.size else 0.0


def _singt(stems: dict[str, np.ndarray]) -> bool:
    """Gesang traegt mindestens 15 % des Pegels im Fenster."""
    gesamt = _rms(sum(stems.values()))
    return gesamt > 0 and _rms(stems["vocals"]) > 0.15 * gesamt


def mischen_stems(art: str, a: dict[str, np.ndarray], b: dict[str, np.ndarray], takte: int = 1,
                  gesang_takt: int = -1, mit_fahne: bool = False, echo: bool = False):
    """Stem-Uebergaenge: je Stem eigene Ein-/Ausblendung (Anteile der Blendenlaenge).

    - drums_zuerst: B-Drums laufen in der ersten Haelfte unter A ein (A-Drums
      gehen), danach Bass-Tausch in der Mitte, dann Rest und Gesang.
    - acapella: A's Gesang bleibt bis kurz vor Schluss ueber B's Instrumental.
    - gesangsschutz: wie EQ-Mix, aber A singt nur bis 50 %, B erst ab 50 %.
    gesang_zuerst: B's Gesang ueber A's Instrumental, B's Musik danach (siehe stem_plan).

    `mit_fahne`: (Blende, Fahne) - die Echo-Fahne von A's letzten Worten hinter der Blende.
    `echo` (double_drop): A's Musik geht im letzten Takt ins Echo.
    """
    n = len(a["drums"])
    aus = np.zeros_like(a["drums"])
    plan = stem_plan(art, takte, gesang_takt)
    # Double Drop: B ohne Tiefen bis zum Bass-Switch (Low-EQ zu) - auch Kick und Bassreste in B's
    # anderen Spuren; nie zwei Baesse (Runde 9: "doppelter Bass")
    schalter = _rampe(n, *plan["bass"][1]) if art == "double_drop" else None
    for k, ((va, ba), (vb, bb)) in plan.items():
        bk = b[k][:n]
        if schalter is not None and k != "bass":
            tief, rest = mix.band_teilen(bk, RATE, 150.0)
            bk = rest + tief * schalter
        aus += a[k][:n] * np.sqrt(1 - _rampe(n, va, ba) ** 2) + bk * _rampe(n, vb, bb)
    if art == "acapella" and gesang_takt > 0:
        # A's letzte Worte gehen ins Echo, statt nur auszublenden (klingt ueber B aus)
        va, ba = plan["vocals"][0]
        x = np.arange(n) / n
        send = np.where(x < ba, np.clip((x - (va - 0.5 / takte)) * takte * 2, 0, 1), 0).astype(np.float32)
        nass = _nass("echo75", a["vocals"][:n] * send[:, None], n / takte / 4)
        aus += nass[:n]
        fahne = nass[n:]
    elif art == "gesang_zuerst" and 0 < gesang_takt <= takte:
        # Runde 13, Fall 23: "Man hoert Track B erst nach dem Uebergang" - ab der Haelfte der Gesangsphase
        # laufen B's Drums hochpass-gefiltert (> 2 kHz: Hi-Hats, Shaker) bei -12 dB mit, ab der Uebergabe voll
        fahne = np.zeros((0, 2), np.float32)
        g, t = gesang_takt / takte, 1 / max(1, takte)
        hats = mix.band_teilen(b["drums"][:n], RATE, 2000.0)[1]
        ein = _rampe(n, g / 2, g / 2 + t) * np.sqrt(1 - _rampe(n, *plan["drums"][1]) ** 2)
        aus += hats * ein * np.float32(10 ** (-12 / 20))
    elif art == "double_drop" and echo:
        t = 1 / max(1, takte)
        x = np.arange(n) / n
        send = np.clip((x - (1 - 1.5 * t)) / (0.5 * t), 0, 1).astype(np.float32)   # letzter Takt
        nass = _nass("echo75", (a["drums"][:n] + a["other"][:n]) * send[:, None], n / takte / 4)
        aus += nass[:n]
        fahne = nass[n:]
    else:
        fahne = np.zeros((0, 2), np.float32)
    return (aus, fahne) if mit_fahne else aus


DECKE = 0.966   # -0,3 dBFS


def _begrenzen(x: np.ndarray, bis: int, decke: float = DECKE) -> None:
    """Limiter fuer x[:bis] (in place): Zwei laute Songs zusammen ueberschreiten 0 dBFS,
    die Soundkarte schneidet hart ab -> Knacken. Offline mit Vorschau: die Verstaerkung
    sinkt 10 ms vor einer Spitze und kehrt geglaettet zurueck; nie ueber der Decke."""
    from scipy.ndimage import maximum_filter1d, minimum_filter1d, uniform_filter1d

    teil = x[:bis]
    if not len(teil):
        return
    spitze = np.abs(teil).max(axis=1)
    fenster, blk = int(0.02 * RATE) | 1, 1 << 16
    # Nur Bloecke mit Spitzen (meist wenige): kurze Rechenstuecke, der GIL bleibt frei.
    for start in np.unique(np.flatnonzero(spitze > decke) // blk) * blk:
        lo, hi, ende = max(0, start - 2 * fenster), min(len(teil), start + blk + 2 * fenster), \
            min(len(teil), start + blk)
        g = np.minimum(1.0, decke / np.maximum(maximum_filter1d(spitze[lo:hi], fenster), 1e-9))
        g = uniform_filter1d(minimum_filter1d(g, fenster), fenster)   # glatt und <= g
        teil[start:ende] *= g[start - lo:ende - lo, None].astype(np.float32)


# --- Planung + Backen ---------------------------------------------------------

def _naechster_index(werte: np.ndarray, ab: float, phrase: bool, start: int = 0) -> int:
    for i in range(start, len(werte)):
        if werte[i] >= ab and (not phrase or i % PHRASE == 0):
            return i
    return len(werte) - 1


def _phrase_bei(werte: np.ndarray, t: float) -> int:
    """Phrasenanfang (Index) am naechsten an Zeit t."""
    kandidaten = np.arange(0, len(werte), PHRASE)
    return int(kandidaten[np.argmin(np.abs(werte[kandidaten] - t))])


# Die Partnerwahl misst am Song-BPM; das lokale Tempo an der Stelle streut darum (Runde 12: 5,0 BPM Abstand im
# Song, lokal knapp darueber -> Echo-Out/Schnitt statt Blende). So viel BPM darf es lokal mehr sein.
TEMPO_SPIEL = 0.5


def _periode(t: np.ndarray, i: int, halb: int = 8) -> float:
    """Lokale Taktlaenge: Mittel der Abstaende nahe am Median (±halb Takte).

    Der Median allein klebt am 20-ms-Raster von Beat This!, der reine Mittelwert
    kippt an unregelmaessigen Intro-Downbeats - das Mittel des Kerns ist beides nicht.
    """
    lo, hi = max(0, i - halb), min(len(t) - 1, i + halb)
    d = np.diff(t[lo:hi + 1])
    if d.size == 0:
        return 2.0
    m = float(np.median(d))
    kern = d[np.abs(d - m) <= 0.1 * m]
    return float(np.mean(kern)) if kern.size else m


def _harmonisch(a: str | None, b: str | None) -> bool:
    return bool(a and b and (a == b or b in camelot_nachbarn(a)))


def ausstieg(a: Spur, e: Einstellungen, takte: int, ab_s: float, weiter: bool = False,
             aus_s: float | None = None):
    """(Taktraster von A in Pufferzeit, Index des Takts, an dem die Blende beginnt).

    `aus_s` (Originalsekunde, von der Regie): genau dort, sofern nicht schon vorbei."""
    a_dauer = len(a.puffer) / RATE
    abar = raster(a.buf, a_dauer + 64 * 2.5)
    letzter = int(np.searchsorted(abar, a_dauer, side="right")) - 1   # letzter Takt im Song
    if aus_s is not None:
        i0 = int(np.argmin(np.abs(abar - a.zu_puffer(aus_s))))
        if abar[i0] < ab_s - 1e-3:
            i0 = _naechster_index(abar, ab_s, not weiter)
    elif weiter:
        i0 = _naechster_index(abar, ab_s, e.weiter_ab == "phrase")
    else:
        if e.ausstieg == "outro" and a.eintrag.abschnitte:
            i0 = _phrase_bei(abar, a.zu_puffer(a.eintrag.abschnitte[-1]))
        elif e.ausstieg == "vor_ende":
            i0 = letzter - e.vor_ende_takte
        else:   # letzte Phrase, in die die Blende noch passt
            i0 = max(0, (letzter - takte) // PHRASE * PHRASE)
        i0 = min(i0, max(0, letzter - takte))   # A soll die ganze Blende hoerbar bleiben
        if abar[max(0, i0)] < ab_s:
            i0 = _naechster_index(abar, ab_s, True)
    return abar, max(0, i0)


def einstieg(b: Eintrag, b_samples: int, e: Einstellungen, ein_s: float | None = None):
    """(Taktraster von B in Originalzeit, Index des Takts, an dem B einsetzt)."""
    if ein_s is not None:   # von der Regie: genau dort
        bbar = regulaer(b.downbeats, b.bpm, b_samples / RATE + 64 * 2.5, um_s=ein_s + 15.0)
        return bbar, int(np.argmin(np.abs(bbar - ein_s)))
    drop_s = b.abschnitte[0] if e.einstieg == "drop" and b.abschnitte else None
    bbar = regulaer(b.downbeats, b.bpm, b_samples / RATE + 64 * 2.5,
                    um_s=drop_s if drop_s is not None else 20.0)
    return bbar, (_phrase_bei(bbar, drop_s) if drop_s is not None else 0)


def fenster_a(a: Spur, abar: np.ndarray, i0: int, takte: int):
    """(Audio, Cache-Schluessel) des Blendenfensters von A - fuer Stems und Vorrechnen.

    Ist das Fenster ungedehntes Original, nennt der Schluessel die Originallage
    ("id@start_n"): dann passen auch Stems aus dem Vorrat (stems.aus_vorrat)."""
    ia, ie = int(round(abar[i0] * RATE)), int(round(abar[i0 + takte] * RATE))
    o0, o1 = a.zu_original(abar[i0]), a.zu_original(abar[i0 + takte])
    if abs((o1 - o0) - (abar[i0 + takte] - abar[i0])) < 1e-3:
        schluessel = f"{a.eintrag.id}@{int(round(o0 * RATE))}_{ie - ia}"
    else:
        schluessel = f"{a.eintrag.id}_{len(a.puffer)}_{ia}_{ie}"
    return mix._auffuellen(a.puffer[ia:ie], ie - ia), schluessel


def fenster_b(b: Eintrag, b_audio: np.ndarray, bbar: np.ndarray, j0: int, takte: int):
    ib, ie = int(round(bbar[j0] * RATE)), int(round(bbar[j0 + takte] * RATE))
    return mix._auffuellen(b_audio[ib:ie], ie - ib), f"{b.id}@{ib}_{ie - ib}"


@dataclass
class Gebacken:
    start_n: int     # Blendenbeginn im Puffer von A
    spur: Spur       # B, Puffer beginnt mit der Blende
    info: dict


def backen(a: Spur, b: Eintrag, b_audio: np.ndarray, e: Einstellungen, ab_s: float,
           weiter: bool = False, stem_quelle=None, jetzt_s: float | None = None,
           aus_s: float | None = None, ein_s: float | None = None,
           a_gesang: np.ndarray | None = None) -> Gebacken:
    """Plant und rendert den Uebergang A -> B nach den Einstellungen.

    `stem_quelle(audio, schluessel) -> {drums, bass, other, vocals}` (stems.trennen)
    schaltet die Stem-Uebergaenge frei. Sie werden nur genutzt, wenn die Zeit bis
    zur Blende fuer die Trennung reicht; sonst EQ-Mix (ADR-018: nie warten).
    """
    takte = e.weiter_takte if weiter else e.takte
    abar, i0 = ausstieg(a, e, takte, ab_s, weiter, aus_s)
    bbar, j0 = einstieg(b, len(b_audio), e, ein_s)

    p_a, p_b = _periode(abar, i0), _periode(bbar, j0)
    bpm_a, bpm_b = 240.0 / p_a, 240.0 / p_b
    sync = abs(bpm_a - bpm_b) <= max(e.max_bpm, 0.05) + TEMPO_SPIEL
    vor = 0   # §5.2 Vorlauf: A gleitet vor der Blende in vor Takten auf B's Tempo, die Blende laeuft dann synchron
    if not sync and e.tempo_modus == "vorlauf" and not weiter and e.keylock:
        from .regie import VORLAUF_MAX, VORLAUF_TAKTE

        if abs(p_a / p_b - 1.0) <= VORLAUF_MAX:
            vor = next((v for v in (VORLAUF_TAKTE, VORLAUF_TAKTE // 2) if i0 >= v and abar[i0 - v] >= ab_s - 1e-3), 0)
            sync = vor > 0
    rueck = None   # Intro-Loop von B: virtuelle -> Originalzeit
    b_loop = sync and e.art == "eigen" and e.loop_ein > 0 and e.loop_ein_mal > 0 and j0 + e.loop_ein < len(bbar)
    if b_loop:
        b_audio, bbar, rueck = _intro_loop(b_audio, bbar, j0, e.loop_ein, e.loop_ein_mal)

    art = e.art
    if art == "auto":
        art = "eq" if sync and _harmonisch(a.eintrag.camelot, b.camelot) else ("echo" if takte > 1 else "schnitt")
    if art in SYNC_ARTEN and not sync:
        art = "echo"
    if art == "echo":
        takte = min(takte, 4)
    if art == "schnitt":
        takte = 1

    t0 = abar[i0]
    loop_wahl = None
    # Stems: gewuenscht (Stem-Art oder Auto mit Stems) und zeitlich machbar?
    jetzt = ab_s - 3.0 if jetzt_s is None else jetzt_s
    stem_grund = ""
    will_stems = sync and not b_loop and (e.art in STEM_ARTEN or (e.art == "auto" and art == "eq" and e.stems))
    if will_stems:
        if stem_quelle is None or not e.stems:
            stem_grund = "Stems aus/nicht installiert"
        else:
            fa, ka = fenster_a(a, abar, i0, takte)
            fb, kb = fenster_b(b, b_audio, bbar, j0, takte)
            from . import stems as _st

            offen = sum(len(f) for f, k in ((fa, ka), (fb, kb)) if not _st.bereit(k))
            # Trennzeit offener Fenster + Dehnen/Mischen von 8 Stem-Spuren (~0,35 s je s).
            if weiter and offen:
                stem_grund = "WEITER: Stems nicht vorberechnet"
            elif t0 - jetzt < _st.bedarf_s(offen) + 0.35 * (len(fa) + len(fb)) / RATE + 5.0:
                stem_grund = "zu knapp fuer Stem-Trennung"
    nutze_stems = will_stems and not stem_grund
    if art in STEM_ARTEN and not nutze_stems:
        art = "eq" if e.modus == "manuell" else "eigen"   # Auto-DJ: Profi-EQ aus dem Plan
        takte = min(takte, 16)   # lange Gesangsuebergaben gehen nur mit Stems
    if sync and e.tempo_modus == "b_an_a":
        perioden = np.full(takte, p_a)
    elif sync and e.tempo_modus in ("a_an_b", "vorlauf"):
        perioden = np.full(takte, p_b)
    elif sync:
        perioden = p_a + (p_b - p_a) * (np.arange(takte) + 0.5) / takte
    else:
        perioden = np.diff(abar[i0:i0 + takte + 1])   # A behaelt sein Raster, B laeuft frei
    ziel = t0 + np.concatenate([[0.0], np.cumsum(perioden)])

    laenge = ziel[-1] - t0
    b_ende = len(b_audio) / RATE
    j1 = j0 + takte
    rest_orig = np.concatenate([bbar[j1:][bbar[j1:] < b_ende], [b_ende]])
    b_an_a = sync and e.tempo_modus == "b_an_a"
    # Vorlauf: Periode gleitet linear von A nach B; A in EINEM Zug mit der Blende gedehnt (keine Naht)
    t_vor = abar[i0 - vor]
    ziel_vor = t_vor + np.concatenate([[0.0], np.cumsum(p_a + (p_b - p_a) * (np.arange(vor) + 0.5) / max(1, vor))])
    n_vor = int(round((ziel_vor[-1] - t_vor) * RATE)) if vor else 0

    # A geht am Blendenbeginn nahtlos aus dem Original in die gedehnte Fassung ueber.
    def a_dehnen():
        return warp(a.puffer, abar[i0 - vor:i0 + takte + 1],
                    np.concatenate([ziel_vor[:-1], ziel_vor[-1] + ziel - t0]), e.keylock, rand_vorn=True)

    if b_an_a:
        # B bleibt im Takt von A: Blende + Rest in EINEM Zug gedehnt, ohne Naht dazwischen.
        rest_ziel = laenge + np.concatenate([[0.0], np.cumsum(np.diff(rest_orig) * p_a / p_b)])
        a_seg, voll = _parallel(a_dehnen, lambda: warp(
            b_audio, np.concatenate([bbar[j0:j1], rest_orig]), np.concatenate([ziel[:-1], t0 + rest_ziel]), e.keylock))
        b_seg, rest = voll[:len(a_seg)], voll[len(a_seg):]
    elif sync:   # Rampe/a_an_b: B endet die Blende im Originaltempo -> nahtlos ins Original
        a_seg, b_seg = _parallel(a_dehnen, lambda: warp(b_audio, bbar[j0:j1 + 1], ziel, e.keylock, rand_hinten=True))
        rest_ziel = laenge + (rest_orig - rest_orig[0])
        rest = b_audio[int(round(rest_orig[0] * RATE)):]
    else:
        a_seg = a_dehnen()
        start = int(round(bbar[j0] * RATE))
        b_seg = b_audio[start:start + len(a_seg)]
    a_vor, a_seg = a_seg[:n_vor], a_seg[n_vor:]
    b_seg = mix._auffuellen(b_seg, len(a_seg))
    nachlauf = np.zeros((0, 2), np.float32)
    if nutze_stems:
        sa, sb = stem_quelle(fa, ka), stem_quelle(fb, kb)
        qa, qb = abar[i0:i0 + takte + 1] - t0, bbar[j0:j0 + takte + 1] - bbar[j0]
        gewarpt = _parallel(
            *[(lambda v=v: mix._auffuellen(warp(v, qa, ziel, e.keylock, rand_vorn=True), len(a_seg)))
              for v in sa.values()],
            *[(lambda v=v: mix._auffuellen(warp(v, qb, ziel, e.keylock, rand_hinten=not b_an_a), len(a_seg)))
              for v in sb.values()])
        wa = dict(zip(sa, gewarpt[:len(sa)]))
        wb = dict(zip(sb, gewarpt[len(sa):]))
        if art not in STEM_ARTEN:   # Auto: Gesangsschutz nur, wenn beide singen
            art = "gesangsschutz" if _singt(wa) and _singt(wb) else "eq"
        if art in STEM_ARTEN:
            blende, nachlauf = mischen_stems(art, wa, wb, takte, e.gesang_takt, mit_fahne=True,
                                             echo=e.effekt != "keiner")
        else:
            blende = mischen(art, a_seg, b_seg, takte)
        # Ende: von der Stem-Summe in B's Gesamtsignal, das nahtlos weiterlaeuft
        m = min(NAHT, len(blende))
        blende[-m:] = _ueberblenden(blende[-m:], b_seg[-m:], _korrelation(blende[-m:], b_seg[-m:]))
    elif art == "eigen":
        takt_n = np.round((ziel - t0) * RATE).astype(int)
        if e.loop == "auto":   # Stelle und Laenge des Loops nach Wiederholbarkeit
            # Vergleich auch gegen die 8 Takte hinter der Blende (im Original): Loop faellt dort nicht auf
            n_ext = max(0, min(takte + 8, len(abar) - 1 - i0))
            x_ext = a.puffer[int(round(abar[i0] * RATE)):int(round(abar[i0 + n_ext] * RATE))]
            tn_ext = np.round((abar[i0:i0 + n_ext + 1] - abar[i0]) * RATE).astype(int)
            if n_ext >= takte and len(x_ext) > 0:
                s0, loop_takte, guete = loop_waehlen(x_ext, tn_ext, a_gesang, fenster=takte)
            else:
                s0, loop_takte, guete = loop_waehlen(a_seg, takt_n, a_gesang)
            e = replace(e, loop=str(4 * loop_takte), loop_start=s0)
            loop_wahl = {"start_takt": s0, "schlaege": 4 * loop_takte, "guete": round(guete, 2)}
        blende, nachlauf = mischen_eigen(a_seg, b_seg, e, takt_n)
    else:
        blende = mischen(art, a_seg, b_seg, takte)

    if vor:   # der Vorlauf von A steht vor der Blende im Puffer von B (Umschalten schon am Vorlauf-Beginn)
        blende = np.concatenate([a_vor, blende])
    if not sync:
        # B lief in der Blende ungedehnt ab bbar[j0]: einfach nahtlos weiterspielen.
        start = int(round(bbar[j0] * RATE))
        puffer = np.concatenate([blende, b_audio[start + len(blende):]]).astype(np.float32)
        orig = bbar[j0:]
        buf = orig - bbar[j0]
    else:
        puffer = np.concatenate([blende, rest]).astype(np.float32)
        orig = np.concatenate([bbar[j0:j1], rest_orig])
        buf = np.concatenate([ziel[:-1] - t0, rest_ziel]) + n_vor / RATE
    n_fahne = min(len(nachlauf), len(puffer) - len(blende))
    puffer[len(blende):len(blende) + n_fahne] += nachlauf[:n_fahne]
    # Gedehnte Reste (b_an_a) koennen ueber 0 dBFS gehen, das Original nicht (True Peak <= -1 dBTP).
    _begrenzen(puffer, len(puffer) if b_an_a else len(blende) + n_fahne + RATE)
    if rueck is not None:
        orig = rueck(orig)
    sortiert = np.argsort(orig, kind="stable")
    orig, buf = orig[sortiert], buf[sortiert]
    _, eindeutig = np.unique(orig, return_index=True)
    spur = Spur(b, puffer, orig[eindeutig], buf[eindeutig])
    a_start = a.zu_original(t_vor)
    gesamt = laenge + n_vor / RATE
    info = {"art": art, "takte": takte, "sync": sync, "bpm_a": round(bpm_a, 2),
            "bpm_b": round(bpm_b, 2), "modus": e.tempo_modus if sync else "frei",
            "stems": nutze_stems, **({"hinweis": stem_grund} if stem_grund else {}),
            # fuer die Deck-Ansicht: A bleibt bis zum Blendenende sichtbar
            "blende_s": round(float(gesamt), 3), "a_orig_start": round(a_start, 3),
            "b_orig_start": round(float(rueck(bbar[j0:j0 + 1])[0] if rueck is not None else bbar[j0]), 3),
            "a_orig_pro_s": round((a.zu_original(ziel[-1]) - a_start) / gesamt, 5) if gesamt > 0 else 1.0,
            **({"vorlauf_s": round(n_vor / RATE, 3), "vorlauf_takte": vor} if vor else {}),
            # Taktanfaenge im Puffer von B (s), 4 Takte ueber die Blende hinaus (Kick-Kontrolle, regie.pruefen_drop)
            "raster_s": [round(float(x), 4) for x in np.concatenate(
                [ziel - t0, ziel[-1] - t0 + p_b * np.arange(1, 5)]) + n_vor / RATE],
            "kurven": kurven(art, takte, e),
            "a_loop": loop_info(e, ziel - t0) if art == "eigen" else [],
            **({"loop_wahl": loop_wahl} if loop_wahl else {}),
            **({"b_intro_loop": {"takte": e.loop_ein, "mal": e.loop_ein_mal}} if b_loop else {})}
    return Gebacken(int(round(t_vor * RATE)), spur, info)
