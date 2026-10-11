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

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import config, mix, resample
from .einstellungen import Einstellungen
from .keyestimate import camelot_nachbarn

RATE = config.ABTASTRATE_HOERTEST
PHRASE = 8            # Takte je Phrase
GIL_STUECK = 4096      # Samples je Signalsmith-Aufruf (~93 ms Audio, wenige ms Rechenzeit)
STEM_ARTEN = ("drums_zuerst", "acapella", "gesangsschutz")
SYNC_ARTEN = ("eq", "crossfade", "filter", "drums_zuerst", "acapella", "gesangsschutz")


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

def warp(audio: np.ndarray, quell_s: np.ndarray, ziel_s: np.ndarray, keylock: bool) -> np.ndarray:
    """Zieht `audio[quell_s[0]:quell_s[-1]]` so, dass Takt i auf ziel_s[i]-ziel_s[0] faellt.

    Ein Signalsmith-Objekt laeuft streamend ueber alle Segmente (kein Knacksen an
    den Taktgrenzen); je Segment ein eigener Zeitfaktor. Gemessen: Klicks landen
    auf ±1 ms genau im Zielraster.
    """
    quell = np.round(np.asarray(quell_s) * RATE).astype(int)
    ziel = np.round((np.asarray(ziel_s) - ziel_s[0]) * RATE).astype(int)
    quell = np.clip(quell, 0, len(audio))
    stretch = None
    # Unter 0,2 % Abweichung (< 3,5 Cent) ist Resampling unhoerbar und viel schneller.
    faktoren = np.diff(quell) / np.maximum(1, np.diff(ziel))
    if keylock and np.any(np.abs(faktoren - 1) > 0.002):
        import python_stretch as ps

        stretch = ps.Signalsmith.Stretch()
        stretch.preset(2, RATE)
    teile, fertig = [], 0
    for i in range(len(quell) - 1):
        n_aus = ziel[i + 1] - fertig
        stueck = audio[quell[i]:quell[i + 1]]
        if n_aus <= 0:
            continue
        if len(stueck) == 0:
            teile.append(np.zeros((n_aus, 2), np.float32))
        elif stretch is not None:
            stretch.timeFactor = len(stueck) / n_aus
            # Kleine Stuecke: Signalsmith haelt den GIL, der Audio-Callback darf nie verhungern.
            stuecke = [stretch.process(np.ascontiguousarray(stueck[k:k + GIL_STUECK].T)).T
                       for k in range(0, len(stueck), GIL_STUECK)]
            teile.append(mix._auffuellen(np.concatenate(stuecke).astype(np.float32), n_aus))
        else:
            teile.append(mix._auffuellen(resample.resample(stueck, RATE, len(stueck) / n_aus), n_aus))
        fertig += n_aus
    return np.concatenate(teile) if teile else np.zeros((0, 2), np.float32)


# --- Uebergangsarten (Blenden auf gleich langen, synchronen Abschnitten) -----

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
    """A spielt einen Schlag, dann Echo-Fahne (1 Schlag Delay, Feedback 0,55)."""
    n = len(a)
    huelle = np.zeros((n, 1), np.float32)
    flanke = max(1, int(0.01 * RATE))
    huelle[:schlag_n] = 1.0
    huelle[schlag_n:schlag_n + flanke, 0] = np.linspace(1.0, 0.0, min(flanke, max(0, n - schlag_n)))
    trocken = a * huelle
    aus = trocken.copy()
    for k in range(1, 9):
        d = k * schlag_n
        if d >= n:
            break
        aus[d:] += trocken[:n - d] * (0.55 ** k)
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
        fenster = (((0.45, 0.55), (0.45, 0.55)), ((0.25, 0.75), (0.25, 0.75)), ((0.5, 1.0), (0.0, 0.5)))
        aus = np.zeros_like(a)
        for teil_a, teil_b, ((va, ba), (vb, bb)) in zip(_baender(a), _baender(b), fenster):
            aus += teil_a * np.sqrt(1 - _rampe(n, va, ba) ** 2) + teil_b * _rampe(n, vb, bb)
        return aus
    if art == "echo":
        takt_n = n // max(1, takte)
        b_ein = _rampe(n, takt_n / n, (takt_n + 0.01 * RATE) / n) if takt_n < n else _rampe(n, 0, 1)
        return _echo(a, max(1, takt_n // 4)) + b * b_ein
    if art == "schnitt":
        kurz = min(1.0, 0.01 * RATE / max(1, n))
        return a * (1 - _rampe(n, 0.0, kurz)) + b * _rampe(n, 0.0, kurz)
    # crossfade und alles ohne Stems: equipotent
    aus_k, ein_k = mix.equal_power_blende(n)
    return a * aus_k[:, None] + b * ein_k[:, None]


def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x, dtype=np.float64)))) if x.size else 0.0


def _singt(stems: dict[str, np.ndarray]) -> bool:
    """Gesang traegt mindestens 15 % des Pegels im Fenster."""
    gesamt = _rms(sum(stems.values()))
    return gesamt > 0 and _rms(stems["vocals"]) > 0.15 * gesamt


def mischen_stems(art: str, a: dict[str, np.ndarray], b: dict[str, np.ndarray]) -> np.ndarray:
    """Stem-Uebergaenge: je Stem eigene Ein-/Ausblendung (Anteile der Blendenlaenge).

    - drums_zuerst: B-Drums laufen in der ersten Haelfte unter A ein (A-Drums
      gehen), danach Bass-Tausch in der Mitte, dann Rest und Gesang.
    - acapella: A's Gesang bleibt bis kurz vor Schluss ueber B's Instrumental.
    - gesangsschutz: wie EQ-Mix, aber A singt nur bis 50 %, B erst ab 50 %.
    """
    n = len(a["drums"])
    plan_ = {
        "drums_zuerst": {"drums": ((0.0, 0.5), (0.0, 0.5)), "bass": ((0.45, 0.55), (0.45, 0.55)),
                         "other": ((0.5, 1.0), (0.5, 1.0)), "vocals": ((0.5, 0.7), (0.7, 1.0))},
        "acapella": {"drums": ((0.0, 0.5), (0.0, 0.5)), "bass": ((0.45, 0.55), (0.45, 0.55)),
                     "other": ((0.0, 0.5), (0.0, 0.5)), "vocals": ((0.85, 1.0), (0.9, 1.0))},
        "gesangsschutz": {"drums": ((0.0, 1.0), (0.0, 1.0)), "bass": ((0.45, 0.55), (0.45, 0.55)),
                          "other": ((0.0, 1.0), (0.0, 1.0)), "vocals": ((0.3, 0.5), (0.5, 0.7))},
    }[art]
    aus = np.zeros_like(a["drums"])
    for k, ((va, ba), (vb, bb)) in plan_.items():
        aus += a[k][:n] * np.sqrt(1 - _rampe(n, va, ba) ** 2) + b[k][:n] * _rampe(n, vb, bb)
    return aus


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


def ausstieg(a: Spur, e: Einstellungen, takte: int, ab_s: float, weiter: bool = False):
    """(Taktraster von A in Pufferzeit, Index des Takts, an dem die Blende beginnt)."""
    a_dauer = len(a.puffer) / RATE
    abar = raster(a.buf, a_dauer + 64 * 2.5)
    letzter = int(np.searchsorted(abar, a_dauer, side="right")) - 1   # letzter Takt im Song
    if weiter:
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


def einstieg(b: Eintrag, b_samples: int, e: Einstellungen):
    """(Taktraster von B in Originalzeit, Index des Takts, an dem B einsetzt)."""
    drop_s = b.abschnitte[0] if e.einstieg == "drop" and b.abschnitte else None
    bbar = regulaer(b.downbeats, b.bpm, b_samples / RATE + 64 * 2.5,
                    um_s=drop_s if drop_s is not None else 20.0)
    return bbar, (_phrase_bei(bbar, drop_s) if drop_s is not None else 0)


def fenster_a(a: Spur, abar: np.ndarray, i0: int, takte: int):
    """(Audio, Cache-Schluessel) des Blendenfensters von A - fuer Stems und Vorrechnen."""
    ia, ie = int(round(abar[i0] * RATE)), int(round(abar[i0 + takte] * RATE))
    return mix._auffuellen(a.puffer[ia:ie], ie - ia), f"{a.eintrag.id}_{len(a.puffer)}_{ia}_{ie}"


def fenster_b(b: Eintrag, b_audio: np.ndarray, bbar: np.ndarray, j0: int, takte: int):
    ib, ie = int(round(bbar[j0] * RATE)), int(round(bbar[j0 + takte] * RATE))
    return mix._auffuellen(b_audio[ib:ie], ie - ib), f"{b.id}_{ib}_{ie}"


@dataclass
class Gebacken:
    start_n: int     # Blendenbeginn im Puffer von A
    spur: Spur       # B, Puffer beginnt mit der Blende
    info: dict


def backen(a: Spur, b: Eintrag, b_audio: np.ndarray, e: Einstellungen, ab_s: float,
           weiter: bool = False, stem_quelle=None, jetzt_s: float | None = None) -> Gebacken:
    """Plant und rendert den Uebergang A -> B nach den Einstellungen.

    `stem_quelle(audio, schluessel) -> {drums, bass, other, vocals}` (stems.trennen)
    schaltet die Stem-Uebergaenge frei. Sie werden nur genutzt, wenn die Zeit bis
    zur Blende fuer die Trennung reicht; sonst EQ-Mix (ADR-018: nie warten).
    """
    takte = e.weiter_takte if weiter else e.takte
    abar, i0 = ausstieg(a, e, takte, ab_s, weiter)
    bbar, j0 = einstieg(b, len(b_audio), e)

    p_a, p_b = _periode(abar, i0), _periode(bbar, j0)
    bpm_a, bpm_b = 240.0 / p_a, 240.0 / p_b
    sync = abs(bpm_a - bpm_b) <= max(e.max_bpm, 0.05)

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
    # Stems: gewuenscht (Stem-Art oder Auto mit Stems) und zeitlich machbar?
    jetzt = ab_s - 3.0 if jetzt_s is None else jetzt_s
    stem_grund = ""
    will_stems = sync and (e.art in STEM_ARTEN or (e.art == "auto" and art == "eq" and e.stems))
    if will_stems:
        if stem_quelle is None or not e.stems:
            stem_grund = "Stems aus/nicht installiert"
        elif weiter:
            stem_grund = "WEITER: keine Zeit fuer Stems"
        else:
            fa, ka = fenster_a(a, abar, i0, takte)
            fb, kb = fenster_b(b, b_audio, bbar, j0, takte)
            from . import stems as _st

            offen = sum(len(f) for f, k in ((fa, ka), (fb, kb)) if not _st.bereit(k))
            # Trennzeit offener Fenster + Dehnen/Mischen von 8 Stem-Spuren (~0,35 s je s).
            if t0 - jetzt < _st.bedarf_s(offen) + 0.35 * (len(fa) + len(fb)) / RATE + 5.0:
                stem_grund = "zu knapp fuer Stem-Trennung"
    nutze_stems = will_stems and not stem_grund
    if art in STEM_ARTEN and not nutze_stems:
        art = "eq"
    if sync and e.tempo_modus == "b_an_a":
        perioden = np.full(takte, p_a)
    elif sync and e.tempo_modus == "a_an_b":
        perioden = np.full(takte, p_b)
    elif sync:
        perioden = p_a + (p_b - p_a) * (np.arange(takte) + 0.5) / takte
    else:
        perioden = np.diff(abar[i0:i0 + takte + 1])   # A behaelt sein Raster, B laeuft frei
    ziel = t0 + np.concatenate([[0.0], np.cumsum(perioden)])

    a_seg = warp(a.puffer, abar[i0:i0 + takte + 1], ziel, e.keylock)
    if sync:
        b_seg = warp(b_audio, bbar[j0:j0 + takte + 1], ziel, e.keylock)
    else:
        start = int(round(bbar[j0] * RATE))
        b_seg = mix._auffuellen(b_audio[start:start + len(a_seg)], len(a_seg))
    b_seg = mix._auffuellen(b_seg, len(a_seg))
    if nutze_stems:
        sa, sb = stem_quelle(fa, ka), stem_quelle(fb, kb)
        qa, qb = abar[i0:i0 + takte + 1] - t0, bbar[j0:j0 + takte + 1] - bbar[j0]
        wa = {k: mix._auffuellen(warp(v, qa, ziel, e.keylock), len(a_seg)) for k, v in sa.items()}
        wb = {k: mix._auffuellen(warp(v, qb, ziel, e.keylock), len(a_seg)) for k, v in sb.items()}
        if art not in STEM_ARTEN:   # Auto: Gesangsschutz nur, wenn beide singen
            art = "gesangsschutz" if _singt(wa) and _singt(wb) else "eq"
        blende = mischen_stems(art, wa, wb) if art in STEM_ARTEN else mischen(art, a_seg, b_seg, takte)
    else:
        blende = mischen(art, a_seg, b_seg, takte)

    # Rest von B: bei b_an_a im Takt von A weiter, sonst im Originaltempo.
    laenge = ziel[-1] - t0
    b_ende = len(b_audio) / RATE
    if not sync:
        # B lief in der Blende ungedehnt ab bbar[j0]: einfach nahtlos weiterspielen.
        start = int(round(bbar[j0] * RATE))
        puffer = np.concatenate([blende, b_audio[start + len(blende):]]).astype(np.float32)
        orig = bbar[j0:]
        buf = orig - bbar[j0]
    else:
        j1 = j0 + takte
        rest_orig = bbar[j1:][bbar[j1:] < b_ende]
        rest_orig = np.concatenate([rest_orig, [b_ende]])
        if e.tempo_modus == "b_an_a":
            rest_ziel = laenge + np.concatenate([[0.0], np.cumsum(np.diff(rest_orig) * p_a / p_b)])
            rest = warp(b_audio, rest_orig, rest_ziel, e.keylock)
        else:
            rest_ziel = laenge + (rest_orig - rest_orig[0])
            rest = b_audio[int(round(rest_orig[0] * RATE)):]
        puffer = np.concatenate([blende, rest]).astype(np.float32)
        orig = np.concatenate([bbar[j0:j1], rest_orig])
        buf = np.concatenate([ziel[:-1] - t0, rest_ziel])
    sortiert = np.argsort(orig, kind="stable")
    orig, buf = orig[sortiert], buf[sortiert]
    _, eindeutig = np.unique(orig, return_index=True)
    spur = Spur(b, puffer, orig[eindeutig], buf[eindeutig])
    info = {"art": art, "takte": takte, "sync": sync, "bpm_a": round(bpm_a, 2),
            "bpm_b": round(bpm_b, 2), "modus": e.tempo_modus if sync else "frei",
            "stems": nutze_stems, **({"hinweis": stem_grund} if stem_grund else {})}
    return Gebacken(int(round(t0 * RATE)), spur, info)
