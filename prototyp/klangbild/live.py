"""Phase 2 · Echtzeit-Wiedergabe mit Auto-DJ (ADR-021).

Prinzip „vorausbacken": Der Audio-Callback (`Wiedergabe.fuellen`) rechnet
nichts, er kopiert nur Samples aus einem fertigen Puffer. Der Uebergang zum
naechsten Song wird in einem Hintergrund-Thread nach den Einstellungen gebacken
(`uebergang.backen`: Beat-Warp mit Keylock, Uebergangsart, Laenge in Takten) und
als fertiger Puffer von B bereitgelegt. Am Blendenbeginn schaltet der Callback
nur die Referenz um.
"""

from __future__ import annotations

import math
import threading
import time
from typing import Callable

import numpy as np

from . import audioio, config, einstellungen, plan
from .uebergang import Eintrag, Spur, backen

RATE = config.ABTASTRATE_HOERTEST
VORLAUF_S = 3.0          # fruehester Blendenbeginn ab „jetzt" (Backzeit + Puffer)

__all__ = ["Eintrag", "Spur", "Wiedergabe", "gain_db", "RATE"]


def gain_db(lufs: float | None, true_peak: float | None) -> float:
    """Pegel auf -14 LUFS, gedeckelt auf True Peak <= -1 dBTP (live, je Track)."""
    if lufs is None or not math.isfinite(lufs):
        return 0.0
    g = config.LUFS_ZIEL - lufs
    if true_peak is not None and math.isfinite(true_peak):
        g = min(g, config.TRUE_PEAK_GRENZE - true_peak)
    return g


def _datei_laden(eintrag: Eintrag) -> np.ndarray:
    return audioio.decodieren_stereo(eintrag.pfad, RATE).daten


def _plan_track(e: Eintrag, bpm: float | None = None) -> plan.Track:
    return plan.Track(id=e.id, pfad=e.pfad, bpm=bpm or e.bpm, camelot=e.camelot,
                      energie_db=e.energie_db, vektor=None)


class Wiedergabe:
    """Player + Auto-DJ. `fuellen` ist der Callback-Kern, testbar ohne Soundkarte."""

    def __init__(self, bibliothek: dict[int, Eintrag],
                 laden: Callable[[Eintrag], np.ndarray] = _datei_laden,
                 einst: einstellungen.Einstellungen | None = None):
        self.bibliothek = bibliothek
        self._roh_laden = laden
        self.einst = einst or einstellungen.Einstellungen()
        self.lock = threading.RLock()
        self.spur: Spur | None = None
        self.pos = 0
        self.spielt = False
        self.autodj = False
        self.warteschlange: list[int] = []
        self.verlauf: list[dict] = []
        self.underflows = 0
        self._gespielt: set[int] = set()
        self._naechste: tuple[int, Spur, dict] | None = None  # (wechsel_n, spur B, info)
        self._frueh = False
        self._gen = 0   # verwirft Backergebnisse, die von einer Bedienung ueberholt wurden
        self._stream = None

    def laden(self, e: Eintrag) -> np.ndarray:
        audio = self._roh_laden(e)
        if self.einst.lautheit and e.gain_db:
            audio = audio * np.float32(10.0 ** (e.gain_db / 20.0))
        return np.asarray(audio, dtype=np.float32)

    # --- Callback --------------------------------------------------------
    def fuellen(self, frames: int) -> np.ndarray:
        aus = np.zeros((frames, 2), dtype=np.float32)
        with self.lock:
            fertig = 0
            while fertig < frames and self.spielt and self.spur is not None:
                grenze = self._naechste[0] if self._naechste else len(self.spur.puffer)
                n = min(frames - fertig, grenze - self.pos)
                if n > 0:
                    aus[fertig:fertig + n] = self.spur.puffer[self.pos:self.pos + n]
                    self.pos += n
                    fertig += n
                if self.pos >= grenze:
                    if self._naechste:
                        self._umschalten()
                    else:
                        self.spielt = False   # Songende, nichts mehr geplant
        return aus

    def _umschalten(self) -> None:
        _, spur, info = self._naechste
        self.verlauf.append({"von": self.spur.eintrag.id, "nach": spur.eintrag.id, **info})
        self.spur, self.pos, self._naechste = spur, 0, None
        # Erst beim echten Wechsel aus der Warteschlange: ein verworfener Uebergang verliert nichts.
        if self.warteschlange and self.warteschlange[0] == spur.eintrag.id:
            self.warteschlange.pop(0)
        self._gespielt.add(spur.eintrag.id)
        self._frueh = False
        self._gen += 1

    # --- Bedienung -------------------------------------------------------
    def _verwerfen(self) -> None:
        self._naechste = None
        self._gen += 1

    def play(self, track_id: int) -> None:
        eintrag = self.bibliothek[track_id]
        audio = self.laden(eintrag)   # ausserhalb des Locks: dekodieren dauert
        with self.lock:
            self.spur, self.pos, self.spielt = Spur.roh(eintrag, audio), 0, True
            self._gespielt.add(track_id)
            self.warteschlange = [i for i in self.warteschlange if i != track_id]
            self._frueh = False
            self._verwerfen()

    def pause(self) -> None:
        with self.lock:
            self.spielt = not self.spielt and self.spur is not None

    def seek(self, original_s: float) -> None:
        with self.lock:
            if self.spur is None:
                return
            n = self.spur.zu_puffer(original_s) * RATE
            self.pos = int(np.clip(n, 0, len(self.spur.puffer) - 1))
            self._verwerfen()

    def weiter(self) -> None:
        with self.lock:
            if self.autodj and self.spur is not None:
                self._frueh = True
                self._verwerfen()
                return
            naechster = self.warteschlange.pop(0) if self.warteschlange else None
        if naechster is not None:
            self.play(naechster)

    def einreihen(self, track_id: int) -> None:
        with self.lock:
            if track_id in self.bibliothek:
                self.warteschlange.append(track_id)
                self._verwerfen()

    def entfernen(self, index: int) -> None:
        with self.lock:
            if 0 <= index < len(self.warteschlange):
                self.warteschlange.pop(index)
                self._verwerfen()

    def verschieben(self, index: int, richtung: int) -> None:
        with self.lock:
            ziel = index + richtung
            if 0 <= index < len(self.warteschlange) and 0 <= ziel < len(self.warteschlange):
                w = self.warteschlange
                w[index], w[ziel] = w[ziel], w[index]
                self._verwerfen()

    def sortieren(self) -> None:
        """Ganze Bibliothek in die beste Reihenfolge; sie wird die Warteschlange."""
        with self.lock:
            aktuell = self.spur.eintrag.id if self.spur else None
            tracks = [_plan_track(e) for e in self.bibliothek.values()]
            folge = plan.sortiere_alle(tracks, self.einst.max_bpm, self.einst.harmonie, aktuell)
            self.warteschlange = [i for i in folge if i != aktuell]
            self._verwerfen()

    def autodj_setzen(self, an: bool) -> None:
        with self.lock:
            self.autodj = bool(an)
            self._verwerfen()

    def einstellungen_setzen(self, neu: einstellungen.Einstellungen) -> None:
        with self.lock:
            self.einst = neu
            self._verwerfen()

    def bibliothek_setzen(self, bib: dict[int, Eintrag]) -> None:
        with self.lock:
            self.bibliothek = bib
            self.warteschlange = [i for i in self.warteschlange if i in bib]

    # --- Hintergrund: naechsten Uebergang backen -------------------------
    def _autodj_wahl(self, aktuell: Spur, bpm: float) -> int | None:
        kandidaten = [_plan_track(e) for e in self.bibliothek.values()
                      if e.id not in self._gespielt and e.id != aktuell.eintrag.id]
        k = plan.naechster(_plan_track(aktuell.eintrag, bpm), kandidaten,
                           self.einst.max_bpm, self.einst.harmonie)
        return k.id if k else None

    def vorbereiten(self) -> bool:
        """Backt den naechsten Uebergang, falls noetig. True, wenn einer bereitliegt."""
        with self.lock:
            if self.spur is None or self._naechste is not None:
                return self._naechste is not None
            gen, a, autodj_an, frueh, einst = self._gen, self.spur, self.autodj, self._frueh, self.einst
            ab_s = self.pos / RATE + VORLAUF_S
            naechster = self.warteschlange[0] if self.warteschlange else None
            aus_queue = naechster is not None
            if naechster is None and autodj_an:
                naechster = self._autodj_wahl(a, a.bpm_bei(ab_s))
        if naechster is None:
            return False

        b = self.bibliothek[naechster]
        try:
            b_audio = self.laden(b)
        except Exception as fehler:  # noqa: BLE001 - ein kaputter Track darf den Mixer nicht stoppen
            print(f"Ueberspringe {b.titel}: {fehler}", flush=True)
            with self.lock:
                self._gespielt.add(naechster)
                if aus_queue and self.warteschlange and self.warteschlange[0] == naechster:
                    self.warteschlange.pop(0)
            return False
        beginn = time.perf_counter()
        if not autodj_an:
            ergebnis = (len(a.puffer), Spur.roh(b, b_audio), {"art": "schnitt", "modus": "aus"})
        else:
            g = backen(a, b, b_audio, einst, ab_s, weiter=frueh)
            ergebnis = (g.start_n, g.spur, g.info)
        dauer = time.perf_counter() - beginn

        with self.lock:
            if gen != self._gen or self.spur is not a or ergebnis[0] < self.pos:
                print(f"Uebergang zu {b.titel} verworfen ({dauer:.1f}s): "
                      f"{'Bedienung' if gen != self._gen else 'zu spaet'}", flush=True)
                return False   # inzwischen bedient oder zu spaet: naechste Runde neu backen
            print(f"Uebergang zu {b.titel} gebacken in {dauer:.1f}s: {ergebnis[2]}", flush=True)
            self._naechste = ergebnis
            return True

    # --- Zustand fuer die Oberflaeche -------------------------------------
    def zustand(self) -> dict:
        with self.lock:
            z: dict = {"spielt": self.spielt, "autodj": self.autodj, "underflows": self.underflows,
                       "aktuell": None, "naechster": None,
                       "warteschlange": [{"id": i, "titel": self.bibliothek[i].titel}
                                         for i in self.warteschlange if i in self.bibliothek],
                       "verlauf": self.verlauf[-10:]}
            if self.spur is not None:
                s, e = self.spur, self.spur.eintrag
                t = self.pos / RATE
                z["aktuell"] = {"id": e.id, "titel": e.titel, "camelot": e.camelot,
                                "bpm": round(s.bpm_bei(t), 2), "bpm_original": round(e.bpm, 2),
                                "pos_s": round(s.zu_original(t), 2),
                                "dauer_s": round(s.zu_original(len(s.puffer) / RATE), 2)}
            if self._naechste is not None:
                wechsel_n, spur, info = self._naechste
                z["naechster"] = {"id": spur.eintrag.id, "titel": spur.eintrag.titel,
                                  "camelot": spur.eintrag.camelot, **info,
                                  "in_s": round((wechsel_n - self.pos) / RATE, 2)}
            return z

    # --- Laufzeit ---------------------------------------------------------
    def starten(self) -> None:
        """Audio-Stream und Back-Thread starten (nicht in Tests)."""
        import sounddevice as sd

        def callback(outdata, frames, _zeit, status):
            if status.output_underflow:
                self.underflows += 1
            outdata[:] = self.fuellen(frames)

        # latency="high": ~0,1-0,2 s Puffer gegen kurze GIL-Sperren des Back-Threads.
        self._stream = sd.OutputStream(samplerate=RATE, channels=2, dtype="float32",
                                       blocksize=1024, latency="high", callback=callback)
        self._stream.start()

        def schleife():
            ruhe = threading.Event()
            while True:
                try:
                    self.vorbereiten()
                except Exception as fehler:  # noqa: BLE001 - Back-Thread darf nie sterben
                    print(f"Uebergang fehlgeschlagen: {fehler}", flush=True)
                ruhe.wait(0.25)

        threading.Thread(target=schleife, daemon=True).start()
