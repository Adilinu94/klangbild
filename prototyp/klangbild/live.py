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
from collections import OrderedDict
from dataclasses import replace
from typing import Callable

import numpy as np

from . import audioio, config, einstellungen, plan
from .uebergang import DECKE, Eintrag, Spur, _begrenzen, backen

RATE = config.ABTASTRATE_HOERTEST
VORLAUF_S = 2.0          # fruehester Blendenbeginn ab „jetzt" (Mindestwert; waechst mit der Backzeit)

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


def _gleicher_titel(a: str, b: str) -> bool:
    """Dieselbe Aufnahme in zwei Dateien/Versionen ("Song - Artist" / "Song-Artist, Feat X")."""
    norm = lambda t: "".join(c for c in t.lower() if c.isalnum())   # noqa: E731
    x, y = norm(a), norm(b)
    kurz, lang = sorted((x, y), key=len)
    return len(kurz) >= 8 and lang.startswith(kurz)


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
        self._vorschau: dict | None = None   # gewaehlter Titel + Plan, solange der Uebergang noch backt
        self.backt = False                   # Back-Thread rechnet gerade (Vorarbeiten warten dann)
        self._frueh = False
        self._gen = 0   # verwirft Backergebnisse, die von einer Bedienung ueberholt wurden
        self._backzeit = 2.0   # gleitendes Mittel der Backdauer (s)
        self._stream = None
        self.stem_quelle = None   # stems.trennen, wenn Demucs da ist (starten())
        self.vorher: tuple[Eintrag, dict] | None = None   # Song A, solange die Blende laeuft
        self.vorrechner = None    # Stems des uebernaechsten Uebergangs vorrechnen (starten())
        # Zuletzt dekodierte Songs (roh, ~85 MB je 4 min): Neu-Backen nach jeder Bedienung
        # und das Vorrechnen fuer C dekodieren sonst jedes Mal neu (~0,5 s je Song).
        self._dekodiert: OrderedDict[int, np.ndarray] = OrderedDict()
        self._dekodiert_lock = threading.Lock()
        self._rang = 0                       # "anderer Uebergang": n-ter Plan der Regie
        self._letztes_rezept: str | None = None   # Abwechslung: nicht zweimal dasselbe
        # Lernen (lokal): durchgehoerte Uebergaenge +, WEITER in der Blende / "anderer" -
        self.lern_pfad = None                # JSON-Datei; None = nur im Speicher (Tests)
        self.vorlieben: dict[str, float] = {}
        self._lern_offen: str | None = None  # Rezept des laufenden Uebergangs, noch ohne Urteil
        self._energie_schritte: list[float] = []   # Energiebogen: dB-Spruenge der letzten Wechsel

    def roh(self, e: Eintrag) -> np.ndarray:
        """Dekodierter Song ohne Lautheitsangleich (zuletzt genutzte bleiben im Speicher)."""
        with self._dekodiert_lock:
            audio = self._dekodiert.get(e.id)
            if audio is not None:
                self._dekodiert.move_to_end(e.id)
        if audio is None:
            audio = self._roh_laden(e)
            with self._dekodiert_lock:
                self._dekodiert[e.id] = audio
                while len(self._dekodiert) > 3:
                    self._dekodiert.popitem(last=False)
        return audio

    def laden(self, e: Eintrag) -> np.ndarray:
        audio = self.roh(e)
        if self.einst.lautheit and e.gain_db:
            audio = audio * np.float32(10.0 ** (e.gain_db / 20.0))
        audio = np.asarray(audio, dtype=np.float32)
        if audio.size and float(np.abs(audio).max()) > DECKE:   # Dekoder-Ueberschwinger: sonst clippt die Soundkarte
            audio = audio.copy()
            _begrenzen(audio, len(audio))
        return audio

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
        self.verlauf.append({"von": self.spur.eintrag.id, "nach": spur.eintrag.id,
                             **{k: v for k, v in info.items() if k != "kurven"}})
        self.vorher = (self.spur.eintrag, info) if info.get("blende_s") else None
        self.spur, self.pos, self._naechste = spur, 0, None
        # Erst beim echten Wechsel aus der Warteschlange: ein verworfener Uebergang verliert nichts.
        if self.warteschlange and self.warteschlange[0] == spur.eintrag.id:
            self.warteschlange.pop(0)
        self._gespielt.add(spur.eintrag.id)
        if self._lern_offen:   # der vorige Uebergang wurde ohne Eingriff durchgehoert
            self._lernen(self._lern_offen, True)
        self._lern_offen = info.get("rezept")
        self._letztes_rezept = info.get("rezept")
        if info.get("energie_schritt") is not None:
            self._energie_schritte = (self._energie_schritte + [info["energie_schritt"]])[-4:]
        self._frueh = False
        self._rang = 0
        self._gen += 1

    # --- Bedienung -------------------------------------------------------
    def _verwerfen(self) -> None:
        self._naechste = None
        self._vorschau = None
        self._gen += 1

    def play(self, track_id: int) -> None:
        eintrag = self.bibliothek[track_id]
        audio = self.laden(eintrag)   # ausserhalb des Locks: dekodieren dauert
        with self.lock:
            self.vorher = None
            self.spur, self.pos, self.spielt = Spur.roh(eintrag, audio), 0, True
            self._gespielt.add(track_id)
            self.warteschlange = [i for i in self.warteschlange if i != track_id]
            self._frueh = False
            self._rang = 0
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

    def _lernen(self, rezept: str, gut: bool) -> None:
        """Gewicht je Rezept: +0,3 je durchgehoertem, -1 je abgebrochenem Uebergang (-5..+3)."""
        import json

        self.vorlieben[rezept] = float(np.clip(self.vorlieben.get(rezept, 0.0) + (0.3 if gut else -1.0), -5, 3))
        if self.lern_pfad is not None:
            try:
                self.lern_pfad.write_text(json.dumps(self.vorlieben, indent=1), encoding="utf-8")
            except OSError:
                pass

    def weiter(self) -> None:
        with self.lock:
            if self.vorher is not None and self._lern_offen:   # WEITER mitten in der Blende: gefiel nicht
                self._lernen(self._lern_offen, False)
                self._lern_offen = None
            if self.autodj and self.spur is not None:
                self._frueh = True
                self._verwerfen()
                return
            naechster = self.warteschlange.pop(0) if self.warteschlange else None
        if naechster is not None:
            self.play(naechster)

    def anders(self) -> None:
        """Naechstbesten Plan der Regie fuer den kommenden Uebergang nehmen."""
        with self.lock:
            if self.autodj and self.spur is not None:
                if self._naechste is not None and self._naechste[2].get("rezept"):
                    self._lernen(self._naechste[2]["rezept"], False)
                self._rang = (self._rang + 1) % 3
                self._verwerfen()

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

    def leeren(self) -> None:
        with self.lock:
            self.warteschlange = []
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
        from . import profil

        with self.lock:
            aktuell = self.spur.eintrag.id if self.spur else None
            bib, einst = dict(self.bibliothek), self.einst
        # Saubere Mischstellen (Profil): Ende von A und Anfang von B ohne Gesang mischen sich besser
        sauber = {}
        for e in bib.values():
            p = profil.gespeichert(e.id)
            g = p.gesang() if p is not None else None
            if g is not None and len(g) >= 16:
                sauber[e.id] = (1.0 - float(np.mean(g[:16])), 1.0 - float(np.mean(g[-16:])))
        bonus = lambda a, b: sauber.get(a.id, (0.5, 0.5))[1] * sauber.get(b.id, (0.5, 0.5))[0]  # noqa: E731
        tracks = [_plan_track(e) for e in bib.values()]
        folge = plan.sortiere_alle(tracks, einst.max_bpm, einst.harmonie, aktuell, bonus)
        with self.lock:
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
    def _autodj_wahl(self, aktuell: Spur, bpm: float, ab_s: float, gespielt: set[int], einst) -> int | None:
        """Naechster Titel: die besten 6 nach Tempo/Tonart/Energie, dann entscheidet, wie gut
        sich jeder wirklich mischen laesst (bester Regie-Plan aus den Profilen) und der
        Energiebogen (nach drei Anstiegen eine Erholung, nach zwei Abstiegen wieder hoch)."""
        from . import profil, regie, stems, uebergang

        kandidaten = [_plan_track(e) for e in self.bibliothek.values()
                      if e.id not in gespielt and e.id != aktuell.eintrag.id
                      and not _gleicher_titel(e.titel, aktuell.eintrag.titel)]
        top = plan.rangliste(_plan_track(aktuell.eintrag, bpm), kandidaten, einst.max_bpm, einst.harmonie)
        if not top:
            return None
        einst = einstellungen.regie_einst(einst)
        pa = profil.gespeichert(aktuell.eintrag.id) if einst is not None else None
        if pa is None:
            return top[0].id
        schritte = self._energie_schritte[-3:]
        ziel = (-4.0, 0.0) if len(schritte) == 3 and min(schritte) > 1.0 else \
            (0.0, 4.0) if len(schritte) >= 2 and max(schritte[-2:]) < -1.0 else (-3.0, 3.0)
        e_a = float(np.mean(pa.gesamt[-32:])) + (aktuell.eintrag.gain_db if einst.lautheit else 0.0)
        werte = {}
        for rang, k in enumerate(top):
            b = self.bibliothek[k.id]
            pb = profil.gespeichert(b.id)
            if pb is None:
                continue
            plaene = regie.planen(aktuell.eintrag, pa, b, pb, einst, aktuell.zu_original(ab_s),
                                  abs(bpm - b.bpm) <= max(einst.max_bpm, 0.05),
                                  uebergang._harmonisch(aktuell.eintrag.camelot, b.camelot), anzahl=1,
                                  # Gesangsuebergaben zaehlen schon bei der Partnerwahl (wie spaeter beim Backen)
                                  stems_da=(self.stem_quelle is not None and einst.stems
                                            and stems.vorrat_fertig(aktuell.eintrag.id) and stems.vorrat_fertig(b.id)))
            if not plaene:
                continue
            e_b = float(np.mean(pb.gesamt[:48])) + (b.gain_db if einst.lautheit else 0.0)
            schritt = e_b - e_a
            bogen = 1.5 if ziel[0] <= schritt <= ziel[1] else -0.3 * min(abs(schritt - ziel[0]), abs(schritt - ziel[1]))
            werte[k.id] = plaene[0].punkte + bogen - 0.6 * rang
        return max(werte, key=werte.get) if werte else top[0].id

    def vorbereiten(self) -> bool:
        """Backt den naechsten Uebergang, falls noetig. True, wenn einer bereitliegt."""
        with self.lock:
            if self.spur is None or self._naechste is not None:
                return self._naechste is not None
            gen, a, autodj_an, frueh, einst = self._gen, self.spur, self.autodj, self._frueh, self.einst
            # Sonst ist die Blende beim Fertigbacken schon vorbei -> verworfen, eine Phrase spaeter.
            ab_s = self.pos / RATE + max(VORLAUF_S, 1.5 * self._backzeit + 1.0)
            naechster = self.warteschlange[0] if self.warteschlange else None
            aus_queue = naechster is not None
            gespielt = set(self._gespielt)
        if naechster is None and autodj_an:   # ausserhalb des Locks: liest Profile, plant probeweise
            naechster = self._autodj_wahl(a, a.bpm_bei(ab_s), ab_s, gespielt, einst)
        if naechster is None:
            return False

        b = self.bibliothek[naechster]
        with self.lock:
            if gen == self._gen:
                self._vorschau = {"id": b.id, "titel": b.titel, "camelot": b.camelot, "bpm_original": round(b.bpm, 2)}
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
        self.backt = True
        try:
            ergebnis = self._backen_ergebnis(a, b, b_audio, einst, ab_s, frueh, autodj_an)
        finally:
            self.backt = False
        dauer = time.perf_counter() - beginn
        self._backzeit = 0.7 * self._backzeit + 0.3 * dauer
        return self._uebernehmen(gen, a, b, ergebnis, dauer, aus_queue, autodj_an, einst)

    def _backen_ergebnis(self, a, b, b_audio, einst, ab_s, frueh, autodj_an):
        if not autodj_an:
            ergebnis = (len(a.puffer), Spur.roh(b, b_audio), {"art": "schnitt", "modus": "aus"})
        elif (regie := einstellungen.regie_einst(einst)) is not None:
            g = self._auto_backen(a, b, b_audio, regie, ab_s, frueh)
            ergebnis = (g.start_n, g.spur, g.info)
        else:
            g = backen(a, b, b_audio, einst, ab_s, weiter=frueh,
                       stem_quelle=self.stem_quelle, jetzt_s=self.pos / RATE)
            ergebnis = (g.start_n, g.spur, g.info)
        return ergebnis

    def _uebernehmen(self, gen, a, b, ergebnis, dauer, aus_queue, autodj_an, einst) -> bool:
        with self.lock:
            if gen != self._gen or self.spur is not a or ergebnis[0] < self.pos:
                print(f"Uebergang zu {b.titel} verworfen ({dauer:.1f}s): "
                      f"{'Bedienung' if gen != self._gen else 'zu spaet'}", flush=True)
                return False   # inzwischen bedient oder zu spaet: naechste Runde neu backen
            info = {k: v for k, v in ergebnis[2].items() if k != "kurven"}
            print(f"Uebergang zu {b.titel} gebacken in {dauer:.1f}s: {info}", flush=True)
            self._naechste = ergebnis
            self._vorschau = None
            danach = self.warteschlange[1] if aus_queue and len(self.warteschlange) > 1 else (
                self.warteschlange[0] if not aus_queue and self.warteschlange else None)
        if autodj_an and self.vorrechner is not None:
            self.vorrechner(ergebnis[1], danach, einst)
        return True

    def _auto_backen(self, a: Spur, b: Eintrag, b_audio: np.ndarray, einst, ab_s: float, frueh: bool):
        """Auto-DJ V2: Profile laden, Regie plant (Ausstieg, Einsatz, Rezept), backen,
        Selbstkontrolle - faellt der Plan durch, kommt der naechstbeste."""
        from . import profil, regie, stems, uebergang

        t0 = time.perf_counter()
        pa = profil.laden(a.eintrag, lambda: self.roh(a.eintrag))
        pb = profil.laden(b, lambda: self.roh(b))
        t_profil = time.perf_counter() - t0
        sync = abs(a.bpm_bei(ab_s) - b.bpm) <= max(einst.max_bpm, 0.05)
        # Auch nach WEITER: aus dem Vorrat sind die Stems sofort da (Runde 4: bei WEITER brach A's Gesang
        # jedes Mal ab); die Regie haelt WEITER-Gesangsuebergaben kurz (WEITER_GESANG_MAX)
        stems_da = (self.stem_quelle is not None and einst.stems
                    and stems.vorrat_fertig(a.eintrag.id) and stems.vorrat_fertig(b.id))
        plaene = regie.planen(a.eintrag, pa, b, pb, einst, a.zu_original(ab_s), sync,
                              uebergang._harmonisch(a.eintrag.camelot, b.camelot), sofort=frueh,
                              stems_da=stems_da, vorher=self._letztes_rezept, vorlieben=self.vorlieben,
                              a_audio=self.roh(a.eintrag), rate=RATE)
        t_plan = time.perf_counter() - t0 - t_profil
        if not plaene:   # z. B. B kuerzer als jede Blende
            return backen(a, b, b_audio, replace(einst, art="echo"), ab_s, weiter=frueh)
        gain = (lambda e: e.gain_db) if einst.lautheit else (lambda e: 0.0)
        start = min(self._rang, len(plaene) - 1)
        with self.lock:   # schon vor dem Backen anzeigen, was kommt
            if self._vorschau is not None and self._vorschau.get("id") == b.id:
                p0 = plaene[start]
                self._vorschau.update(rezept=p0.rezept, grund=p0.grund, takte=p0.takte, plan=start + 1,
                                      in_s=round(p0.aus_s - a.zu_original(self.pos / RATE), 1))
        ga = pa.gesang()
        e_a = float(np.mean(pa.gesamt[-32:])) + gain(a.eintrag)
        e_b = float(np.mean(pb.gesamt[:48])) + gain(b)

        def backen_plan(plan, k):
            # Loop-Wahl meidet A's Gesang (Profil, Takte ab dem Ausstieg)
            maske = regie._fenster(ga, pa.takt_bei(plan.aus_s), plan.takte) > 0 if ga is not None else None
            g = backen(a, b, b_audio, plan.einst, ab_s, weiter=frueh, stem_quelle=self.stem_quelle,
                       jetzt_s=self.pos / RATE, aus_s=plan.aus_s, ein_s=plan.ein_s, a_gesang=maske)
            g.info.update(rezept=plan.rezept, grund=plan.grund, plan=start + k + 1,
                          energie_schritt=round(e_b - e_a, 1),
                          zeiten={"profil": round(t_profil, 1), "plan": round(t_plan, 1),
                                  "backen": round(time.perf_counter() - t0 - t_profil - t_plan, 1)})
            n = int(g.info["blende_s"] * RATE)
            lw = g.info.get("loop_wahl")
            fehler = (f"Loop nicht sauber (Güte {lw['guete']})" if lw and lw["guete"] < regie.LOOP_GUETE_MIN else
                      regie.pruefen(g.spur.puffer[:n], RATE, g.info["takte"], pa, pb, plan.aus_s,
                                    plan.ein_s, gain(a.eintrag), gain(b), plan.rezept))
            return g, fehler

        for k, plan in enumerate(plaene[start:start + (2 if frueh else 3)]):
            g, fehler = backen_plan(plan, k)
            if fehler is None:
                return g
            print(f"Selbstkontrolle {b.titel}: Plan {start + k + 1} ({plan.rezept}) {fehler}", flush=True)
        if frueh:   # WEITER wartet: keine Zeit fuer weitere Versuche
            g.info["pruefung"] = fehler
            return g
        # Nichts bestanden: sicherer Profi-Blend am besten Ausstieg, ohne Loop und Effekt
        p0 = plaene[start]
        kurz = min(p0.takte, 16)   # Ueberlaengen gelten nur fuer Gesangsuebergaben (Runde 5, Fall 4: 48 Takte)
        a_endet = pa.n - pa.takt_bei(p0.aus_s) < kurz   # A klingt in der Blende aus: nur mit Loop
        sicher = replace(p0, rezept="profi_eq", grund="Sicherheits-Blend: die Rezepte davor fielen durch",
                         takte=kurz, einst=replace(p0.einst, takte=kurz, weiter_takte=kurz, art="eigen",
                                       lautstaerke="nahtlos", eq="profi", filter="keiner",
                                       effekt="keiner", effekt_ein="keiner", loop="auto" if a_endet else "keiner",
                                       loop_ein=0, loop_ein_mal=0))
        g, fehler = backen_plan(sicher, 0)
        g.info["pruefung"] = fehler
        return g

    def _stems_vorrechnen(self, spur_b: Spur, c_id: int | None, einst) -> None:
        """Outro-Fenster von B und Intro-Fenster von C in den Stem-Cache (asynchron).

        Demucs braucht ~2,3x Echtzeit; just in time reicht das bei kurzen Songs
        nicht. Vorgerechnet liegen die Stems beim naechsten Backen schon bereit.
        """
        from . import stems, uebergang

        if (not einst.stems or einstellungen.regie_einst(einst) is not None   # Regie: der Vorrat deckt ganze Songs
                or not (einst.art in uebergang.STEM_ARTEN or einst.art == "auto")):
            return
        abar, i0 = uebergang.ausstieg(spur_b, einst, einst.takte, ab_s=0.0)
        stems.vorrechnen(*uebergang.fenster_a(spur_b, abar, i0, einst.takte))
        c = self.bibliothek.get(c_id) if c_id is not None else None
        if c is not None:
            c_audio = self.laden(c)
            bbar, j0 = uebergang.einstieg(c, len(c_audio), einst)
            stems.vorrechnen(*uebergang.fenster_b(c, c_audio, bbar, j0, einst.takte))

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
                                "pos_s": round(s.zu_original(t), 3),
                                "dauer_s": round(s.zu_original(len(s.puffer) / RATE), 2),
                                # Originalsekunden je Echtzeitsekunde (fuer fluessiges Scrollen)
                                "orig_pro_s": round(s.zu_original(t + 1.0) - s.zu_original(t), 5)}
            if self.vorher is not None:
                e, info = self.vorher
                seit = self.pos / RATE
                if self.spur is not None and seit < info["blende_s"]:
                    z["vorher"] = {"id": e.id, "titel": e.titel, "camelot": e.camelot,
                                   "orig_pos": round(info["a_orig_start"] + seit * info["a_orig_pro_s"], 3),
                                   "orig_pro_s": info["a_orig_pro_s"], "seit_s": round(seit, 3),
                                   "blende_s": info["blende_s"], "art": info["art"],
                                   "kurven": info.get("kurven"), "a_loop": info.get("a_loop", []),
                                   "a_orig_start": info["a_orig_start"]}
            if self._naechste is None and self._vorschau is not None:
                z["vorschau"] = dict(self._vorschau)
            if self._naechste is not None:
                wechsel_n, spur, info = self._naechste
                z["naechster"] = {"id": spur.eintrag.id, "titel": spur.eintrag.titel,
                                  "camelot": spur.eintrag.camelot, **info,
                                  "in_s": round((wechsel_n - self.pos) / RATE, 3),
                                  "bpm_original": round(spur.eintrag.bpm, 2),
                                  "orig_start": round(spur.zu_original(0.0), 3),
                                  "orig_pro_s": round(spur.zu_original(1.0) - spur.zu_original(0.0), 5)}
            return z

    # --- Laufzeit ---------------------------------------------------------
    def starten(self) -> None:
        """Audio-Stream und Back-Thread starten (nicht in Tests)."""
        import sounddevice as sd

        from . import stems, uebergang

        uebergang.dehn_pool_starten()   # Keylock-Dehnen in eigenen Prozessen (GIL)
        if stems.verfuegbar():
            self.stem_quelle = stems.trennen
            self.vorrechner = self._stems_vorrechnen

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
