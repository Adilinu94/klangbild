"""Titel-Profil (Auto-DJ V2): jeder Song Takt fuer Takt vermessen.

Je Takt: Pegel in Bass/Mitten/Hoehen (dB, dieselben Weichen wie der Mixer), Gesamtpegel,
und - wenn der Stem-Vorrat da ist - Pegel je Stem (Gesang, Drums, Bass, Rest). Daraus je
Phrase (8 Takte) ein Etikett: intro, aufbau, drop, haupt, break, outro. Die Regie
(`regie.py`) sucht damit Ausstieg, Einsatz und Rezept.

Zeiten sind Originalsekunden des Songs. Ergebnis als JSON im Cache (~10 KB je Titel).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path

import numpy as np

from . import config, mix

RATE = config.ABTASTRATE_HOERTEST
CACHE = config.CACHE / "profil"
VERSION = 2   # 2: Chroma je Takt
PHRASE = 8
STEMS = ("vocals", "drums", "bass", "other")
ETIKETTEN = ("intro", "aufbau", "drop", "haupt", "break", "outro")
# Drops (nach Runde 14, "ein Lied hat meist 1-3 Drops"): Einsatz von Bass + Drums + Pegel (Summe der Spruenge, je 4
# Takte davor/danach); an 417 Titeln: 1 Drop 76, 2 Drops 254, 3 Drops 75, keiner 12
DROP_SPRUNG_DB = 9.0
DROP_ABSTAND = 24     # Takte zwischen zwei Drops (ein Drop-Abschnitt ist mindestens 16 Takte lang)
DROP_REL = 0.4        # schwaechere Einsaetze zaehlen nur ab 40 % des staerksten


def _einmal(f):
    """Abgeleitete Reihen je Profil nur einmal rechnen (die Regie fragt sie tausendfach ab)."""
    @wraps(f)
    def innen(self):
        if f.__name__ not in self._memo:
            self._memo[f.__name__] = f(self)
        return self._memo[f.__name__]
    return innen


@dataclass
class Profil:
    takte: np.ndarray                     # Taktanfaenge (s), Index 0 = erster Downbeat
    baender: np.ndarray                   # (n, 3) dB: Bass < 200 Hz, Mitten, Hoehen > 2,5 kHz
    gesamt: np.ndarray                    # (n,) dB
    stems: dict[str, np.ndarray] | None   # dB je Takt; None ohne Stem-Vorrat
    raster_ok: np.ndarray                 # (n,) Downbeat liegt nahe am Taktraster
    dauer: float
    chroma: np.ndarray | None = None      # (n, 12) Tonvorrat je Takt (Summe 1); aus Harmonie-Stems
    _memo: dict = field(default_factory=dict, init=False, repr=False, compare=False)

    # --- abgeleitet -----------------------------------------------------------------------
    @property
    def n(self) -> int:
        return len(self.takte)

    @_einmal
    def gesang(self) -> np.ndarray | None:
        """Gesang je Takt aktiv (0/1); None = unbekannt (keine Stems)."""
        if self.stems is None:
            return None
        v = self.stems["vocals"]
        # Gesangsspur relativ zum Mix: Uebersprechen liegt um -50 dB, Gesang ab ~-30 dB (Tal bei -40 dB
        # ueber die Bibliothek). Frueher -10 dB: nur lauter Gesang zaehlte, 54 Songs galten als "ohne"
        # (Uebergangstest Runde 3: "die Vocals von A haetten laenger bleiben koennen").
        return ((v - self.gesamt > -25.0) & (v > np.percentile(v, 95) - 20.0)).astype(float)

    @_einmal
    def drums(self) -> np.ndarray:
        """Drums/Kick je Takt aktiv (0/1); ohne Stems aus dem Bassband geschaetzt."""
        if self.stems is not None:
            d = self.stems["drums"]
            return ((d - self.gesamt > -12.0) & (d > np.percentile(d, 95) - 18.0)).astype(float)
        b = self.baender[:, 0]
        return (b > np.percentile(b, 90) - 9.0).astype(float)

    @_einmal
    def bass(self) -> np.ndarray:
        """Bassline/Tiefbass je Takt aktiv (0/1)."""
        b = self.stems["bass"] if self.stems is not None else self.baender[:, 0]
        return (b > np.percentile(b, 90) - 10.0).astype(float)

    @_einmal
    def dichte(self) -> np.ndarray:
        """0..1: wie viel gleichzeitig spielt (Anteil aktiver Stems bzw. Baender)."""
        if self.stems is not None:
            spitze = {k: np.percentile(v, 95) for k, v in self.stems.items()}
            return np.mean([(v > spitze[k] - 15.0) for k, v in self.stems.items()], axis=0)
        spitze = np.percentile(self.baender, 95, axis=0)
        return np.mean(self.baender > spitze - 12.0, axis=1)

    @_einmal
    def versatz(self) -> int:
        """Phrasenversatz s (0..7): Phrasen beginnen bei Takt 8q - s. Der Taktzaehler beginnt am ersten
        Downbeat, die echten 8-Takt-Phrasen (Drops, Breaks) liegen oft 1-4 Takte daneben (Uebergangstest
        Runde 8/9: Drops nicht deckungsgleich, "falsche Stelle"). Gewaehlt wird der Versatz, an dem Pegel,
        Bass und Drums ueber den ganzen Song am staerksten wechseln (je 4 Takte davor/danach, quadriert: nur
        der Takt genau an der Grenze zaehlt voll)."""
        if self.n < 4 * PHRASE:
            return 0
        reihen = [self.gesamt] + ([self.stems["bass"], self.stems["drums"]] if self.stems else [self.baender[:, 0]])
        sprung = np.zeros(self.n)
        for x in reihen:
            c = np.concatenate([[0.0], np.cumsum(x)])
            k = np.arange(4, self.n - 4 + 1)
            sprung[k] += ((c[k + 4] - c[k]) - (c[k] - c[k - 4])) ** 2 / 16
        wert = np.array([np.mean(sprung[o::PHRASE]) for o in range(PHRASE)])
        o = int(np.argmax(wert))
        if wert[o] < 1.3 * wert[0]:   # kein klarer Versatz: beim Raster ab Takt 0 bleiben
            o = 0
        return (PHRASE - o) % PHRASE

    @_einmal
    def drops(self) -> list[int]:
        """1-3 Drop-Takte: wo Bass und Drums nach einem leiseren Teil voll einsetzen. Je Takt der Sprung
        (Mittel der 4 Takte danach minus der 4 davor) in Pegel, Bass und Drums, summiert; die staerksten
        Einsaetze mit DROP_ABSTAND Takten Abstand, danach muessen Bass und Drums laufen (3 von 4 Takten)."""
        if self.n < 16:
            return []
        reihen = [self.gesamt] + ([self.stems["bass"], self.stems["drums"]] if self.stems else [self.baender[:, 0]])
        k = np.arange(4, self.n - 3)
        sprung = np.zeros(len(k))
        for x in reihen:
            c = np.concatenate([[0.0], np.cumsum(x)])
            sprung += ((c[k + 4] - c[k]) - (c[k] - c[k - 4])) / 4
        cb, cd = (np.concatenate([[0.0], np.cumsum(r)]) for r in (self.bass(), self.drums()))
        voll = ((cb[k + 4] - cb[k]) >= 3) & ((cd[k + 4] - cd[k]) >= 3)
        auswahl: list[int] = []
        oben = None   # staerkster Einsatz mit vollem Bass und Drums danach
        for m in np.argsort(-sprung, kind="stable"):
            if sprung[m] < DROP_SPRUNG_DB or (oben is not None and sprung[m] < DROP_REL * oben):
                break
            if not voll[m]:
                continue
            oben = sprung[m] if oben is None else oben
            if all(abs(int(k[m]) - a) >= DROP_ABSTAND for a in auswahl):
                auswahl.append(int(k[m]))
            if len(auswahl) == 3:
                break
        return sorted(self._drop_genau(t) for t in auswahl)

    def _drop_genau(self, k: int) -> int:
        """Erster voller Drop-Takt ab k (bis k+2): Bass und Drums schon fast so laut wie im Drop danach
        (Median der 4 Takte nach k, -4 dB). Runde 15: der 4-Takt-Sprung traf oft den halbvollen Takt mit
        dem Auftakt davor, der Double Drop lag dann einen Takt daneben (Faelle 17, 19, 37)."""
        bass = self.stems["bass"] if self.stems else self.baender[:, 0]
        drums = self.stems["drums"] if self.stems else self.gesamt
        ende = min(self.n, k + 5)
        if ende - k < 3:
            return k
        rb, rd = np.median(bass[k + 1:ende]) - 4.0, np.median(drums[k + 1:ende]) - 4.0
        for t in range(k, min(self.n, k + 3)):
            if bass[t] >= rb and drums[t] >= rd:
                return t
        return k

    @_einmal
    def grenzen(self) -> list[int]:
        """Phrasenanfaenge (aufsteigend, ab 0): 8er-Raster ab jedem Drop, vor dem ersten Drop rueckwaerts
        gezaehlt (nach Runde 14: bei 39 % der Titel lag der staerkste Drop nicht auf dem alten, festen Raster;
        bei 140 lagen die Drops eines Titels nicht im selben 8er-Raster). Ohne Drops: fester Versatz.
        Phrasen unter 3 Takten gehen in der Nachbarphrase auf."""
        d = self.drops()
        if d:
            g = {0} | set(range(d[0], 0, -PHRASE))
            for a, b in zip(d, d[1:] + [self.n]):
                g |= set(range(a, b, PHRASE))
        else:
            g = {0} | {q * PHRASE - self.versatz() for q in range(1, self.n // PHRASE + 2)}
        g = sorted(x for x in g if 0 <= x < self.n)
        fest = {0, *d}
        aus = []
        for i, x in enumerate(g):
            naechste = g[i + 1] if i + 1 < len(g) else self.n
            if x not in fest and ((aus and x - aus[-1] < 3) or naechste - x < 3):
                continue
            aus.append(x)
        return aus

    def phrase_start(self, q: int) -> int:
        """Erster Takt der Phrase q (Phrase 0 beginnt am Songanfang; Grenzen siehe `grenzen`)."""
        g = self.grenzen()
        return g[q] if q < len(g) else g[-1] + PHRASE * (q - len(g) + 1)

    def phrase_ab(self, takt: int) -> int:
        """Erste Phrasengrenze ab `takt`."""
        q = self.phrase_von(takt)
        return takt if self.phrase_start(q) == takt else self.phrase_start(q + 1)

    @_einmal
    def etiketten(self) -> list[str]:
        """Etikett je Phrase (Grenzen siehe `grenzen`); "drop" nur, wo ein Drop beginnt (`drops`)."""
        n_ph = len(self.grenzen())
        grenzen = self.grenzen() + [self.n]
        e = np.array([np.mean(self.gesamt[a:max(a + 1, b)]) for a, b in zip(grenzen, grenzen[1:])])
        d = np.array([np.mean(self.drums()[a:max(a + 1, b)]) for a, b in zip(grenzen, grenzen[1:])])
        bass = np.array([np.mean(self.bass()[a:max(a + 1, b)]) for a, b in zip(grenzen, grenzen[1:])])
        laut = np.percentile(e, 75)
        leise = e < laut - 4.0
        aus = ["haupt"] * n_ph
        i = 0
        while i < n_ph and (leise[i] or d[i] < 0.5):          # dünner Anfang
            aus[i] = "intro"
            i += 1
        j = n_ph - 1
        while j > i and (leise[j] or d[j] < 0.5):             # dünnes Ende
            aus[j] = "outro"
            j -= 1
        for p in range(i, j + 1):
            if d[p] < 0.3:
                aus[p] = "break"
            elif leise[p]:
                aus[p] = "aufbau"
        for t in self.drops():   # Drop = Einsatz von Bass und Drums (Runde 11, hedex: Drop auf dem Drum-Aufbau)
            aus[self.phrase_von(t)] = "drop"
        return aus

    def phrase_von(self, takt: int) -> int:
        g = self.grenzen()
        q = int(np.searchsorted(g, max(0, takt), side="right")) - 1
        return q if takt < self.n or q < len(g) - 1 else q + (max(0, takt) - g[-1]) // PHRASE

    def takt_bei(self, t: float) -> int:
        return int(np.clip(np.argmin(np.abs(self.takte - t)), 0, self.n - 1))

    @_einmal
    def energielevel(self) -> float:
        """0 (ruhig) .. 1 (hart) in den Takten mit Drums: viel Hoehen und wenig Flaechen/Melodie (Rest-Stem) =
        hart. Logistisch kalibriert am 16.10.2026 an 417 Titeln mit den Ordnern als grobem Etikett (Chill/TOBI
        gegen Hard UKG/DnB), 10-fach-CV-AUC 0,86; ohne Stems nur die Hoehen (AUC 0,75)."""
        haupt = self.drums() > 0.5
        if haupt.sum() < 4:
            haupt = np.ones(self.n, bool)
        z = 1.32 * (np.median(self.baender[haupt, 2] - self.gesamt[haupt]) + 16.05) / 4.18
        if self.stems is not None:
            z -= 1.39 * (np.median(self.stems["other"][haupt] - self.gesamt[haupt]) + 13.0) / 5.88
        return float(1.0 / (1.0 + np.exp(-z)))

    # --- Speicher --------------------------------------------------------------------------
    def als_dict(self) -> dict:
        r = lambda a: np.round(np.asarray(a, float), 2).tolist()   # noqa: E731
        return {"version": VERSION, "takte": r(self.takte), "baender": r(self.baender),
                "gesamt": r(self.gesamt), "raster_ok": self.raster_ok.astype(int).tolist(),
                "stems": {k: r(v) for k, v in self.stems.items()} if self.stems else None,
                "dauer": self.dauer,
                "chroma": np.round(self.chroma, 3).tolist() if self.chroma is not None else None}

    @classmethod
    def aus_dict(cls, d: dict) -> "Profil":
        return cls(np.asarray(d["takte"]), np.asarray(d["baender"]), np.asarray(d["gesamt"]),
                   {k: np.asarray(v) for k, v in d["stems"].items()} if d.get("stems") else None,
                   np.asarray(d["raster_ok"], bool), float(d["dauer"]),
                   np.asarray(d["chroma"]) if d.get("chroma") is not None else None)


def tempo_mal(p: Profil, faktor: float) -> Profil:
    """Profil im doppelten (faktor 2: jeder Takt wird zwei) oder halben Taktraster (0,5: jeder zweite Takt),
    fuer Doppel-/Halbtempo-Uebergaenge (BAUPLAN-UEBERGAENGE §5.3).
    shortcut: Werte je Takt werden verdoppelt bzw. ausgeduennt, nicht neu gemessen; Upgrade: aus dem Audio."""
    if faktor > 1:
        t = np.repeat(p.takte, 2)
        t[1::2] += np.diff(np.append(p.takte, 2 * p.takte[-1] - p.takte[-2])) / 2
        zu = lambda x: np.repeat(x, 2, axis=0)   # noqa: E731
    else:
        t = p.takte[::2]
        zu = lambda x: x[::2]   # noqa: E731
    return Profil(t, zu(p.baender), zu(p.gesamt), {k: zu(v) for k, v in p.stems.items()} if p.stems else None,
                  zu(p.raster_ok), p.dauer, zu(p.chroma) if p.chroma is not None else None)


def _db_je_takt(x: np.ndarray, grenzen: np.ndarray) -> np.ndarray:
    """RMS in dB je [grenzen[i], grenzen[i+1]) Samples (mono)."""
    q = np.concatenate([[0.0], np.cumsum(np.asarray(x, np.float64) ** 2)])
    lang = np.maximum(1, np.diff(grenzen))
    return 10 * np.log10((q[grenzen[1:]] - q[grenzen[:-1]]) / lang + 1e-10)


def _chroma_je_takt(x: np.ndarray, grenzen: np.ndarray) -> np.ndarray:
    """Mittleres Chroma (12 Klassen, je Frame auf Summe 1) je Takt; 65 Hz - 2,1 kHz wie keyestimate."""
    f_n, hop = 8192, 4096
    x = np.pad(np.asarray(x, np.float32), (0, max(0, f_n - len(x))))
    frames = np.lib.stride_tricks.sliding_window_view(x, f_n)[::hop]
    freq = np.fft.rfftfreq(f_n, 1 / RATE)
    gueltig = (freq >= 65.0) & (freq <= 2100.0)
    klasse = np.rint(69 + 12 * np.log2(freq[gueltig] / 440.0)).astype(int) % 12
    zuordnung = np.zeros((int(gueltig.sum()), 12), np.float32)
    zuordnung[np.arange(len(klasse)), klasse] = 1.0
    fenster = np.hanning(f_n).astype(np.float32)
    summe, anzahl = np.zeros((len(grenzen) - 1, 12)), np.zeros(len(grenzen) - 1)
    for start in range(0, len(frames), 256):
        teil = frames[start:start + 256]
        ch = (np.abs(np.fft.rfft(teil * fenster, axis=1))[:, gueltig] ** 2) @ zuordnung
        ch /= np.maximum(ch.sum(axis=1, keepdims=True), 1e-12)
        mitte = (start + np.arange(len(teil))) * hop + f_n // 2
        takt = np.searchsorted(grenzen, mitte, side="right") - 1
        ok = (takt >= 0) & (takt < len(anzahl))
        np.add.at(summe, takt[ok], ch[ok])
        np.add.at(anzahl, takt[ok], 1)
    return summe / np.maximum(anzahl, 1)[:, None]


def berechnen(eintrag, audio: np.ndarray, stems: dict[str, np.ndarray] | None = None) -> Profil:
    """Profil aus dem dekodierten Song (n, 2) und optional seinen Stems (gleiche Laenge)."""
    dauer = len(audio) / RATE
    t = _raster(eintrag, dauer)
    grenzen = np.clip(np.round(np.concatenate([t, [min(dauer, 2 * t[-1] - t[-2])]]) * RATE), 0,
                      len(audio)).astype(int)
    mono = audio.mean(axis=1)
    tief, rest = mix.band_teilen(mono, RATE, 200.0)
    mitte, hoch = mix.band_teilen(rest, RATE, 2500.0)
    baender = np.stack([_db_je_takt(b, grenzen) for b in (tief, mitte, hoch)], axis=1)
    gesamt = _db_je_takt(mono, grenzen)
    st = None
    if stems is not None:
        st = {k: _db_je_takt(stems[k][:len(audio)].mean(axis=1), grenzen) for k in STEMS}
    d = np.asarray(eintrag.downbeats, float)
    if d.size:
        naechst = np.abs(d[np.clip(np.searchsorted(d, t), 0, d.size - 1)] - t)
        naechst = np.minimum(naechst, np.abs(d[np.clip(np.searchsorted(d, t) - 1, 0, d.size - 1)] - t))
        raster_ok = naechst < 0.07
    else:
        raster_ok = np.zeros(len(t), bool)
    # Tonvorrat aus Harmonie + Gesang (ohne Drums, die verwischen das Chroma), sonst aus dem Mix
    harmonie = (stems["other"] + stems["vocals"])[:len(audio)].mean(axis=1) if stems is not None else mono
    return Profil(t, baender, gesamt, st, raster_ok, dauer, _chroma_je_takt(harmonie, grenzen))


def _datei(track_id: int, cache: Path | None) -> Path:
    return (cache or CACHE) / f"{track_id}.json"


def speichern(track_id: int, p: Profil, cache: Path | None = None) -> None:
    datei = _datei(track_id, cache)
    datei.parent.mkdir(parents=True, exist_ok=True)
    datei.write_text(json.dumps(p.als_dict()), encoding="utf-8")


def gespeichert(track_id: int, cache: Path | None = None) -> Profil | None:
    try:
        d = json.loads(_datei(track_id, cache).read_text(encoding="utf-8"))
        return Profil.aus_dict(d) if d.get("version") == VERSION else None
    except (OSError, ValueError, KeyError):
        return None


def _raster(eintrag, dauer: float) -> np.ndarray:
    from .uebergang import regulaer

    t = regulaer(eintrag.downbeats, eintrag.bpm, dauer)
    t = t[(t >= -0.5) & (t < dauer - 0.5)]
    return t if len(t) >= 2 else np.array([0.0, dauer])


def passt(p: Profil, eintrag) -> bool:
    """Ist das Taktraster des Profils das aktuelle des Eintrags (nach einem Raster-Anker oder neuer Raster-Regel)?
    Bis Runde 17 gegen die Downbeats geprueft: bei unruhigen Downbeats fiel das immer durch, das Profil wurde
    bei jedem Laden neu gerechnet (13 s je Uebergang)."""
    t = _raster(eintrag, p.dauer)
    return len(t) == p.n and float(np.max(np.abs(t - p.takte))) < 0.006   # gespeichert auf 10 ms gerundet


def laden(eintrag, audio_quelle, cache: Path | None = None, neu: bool = False) -> Profil:
    """Profil aus dem Cache; fehlt es (oder fehlen darin Stems, die inzwischen im Vorrat
    liegen, oder passt sein Raster nicht mehr zu den Downbeats), wird es aus `audio_quelle()`
    (rohes Audio) neu berechnet."""
    from . import stems as st

    p = None if neu else gespeichert(eintrag.id, cache)
    mit_stems = st.vorrat_fertig(eintrag.id)
    if p is not None and (p.stems is not None or not mit_stems) and passt(p, eintrag):
        return p
    audio = audio_quelle()
    stems = st.aus_vorrat(eintrag.id, 0.0, audio) if mit_stems else None
    p = berechnen(eintrag, audio, stems)
    speichern(eintrag.id, p, cache)
    return p
