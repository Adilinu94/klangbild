"""Regie (Auto-DJ V2): je Titelpaar Ausstieg, Einsatz, Laenge und Rezept selbst waehlen.

Vorgehen wie ein DJ (Belege: KONZEPT-SMART-AUTODJ.md, PLAN-AUTODJ-V2.md):
1. Kandidaten: Phrasenanfaenge in A (Ausstieg) und B (Einsatz), Laengen je Stil.
2. Punkte je Kombination aus den Takt-Profilen: kein Gesang gegen Gesang, B uebernimmt
   nach der Blende mit einem tragenden Teil (Drop/Hauptteil), A ist im Fenster duenn
   (Outro/Break), A hoert natuerlich auf, Energie passt, Raster sicher, Spielanteil.
3. Rezept aus der Lage (Gesang, Tonart und Tonvorrat im Fenster, Tempo, Energierichtung,
   Stems, Stil); Effekte, Filter, Loops und Lautstaerke sind je Rezept aufeinander abgestimmt.
4. Rangliste: der beste Plan zuerst; die naechsten sind Ersatz ("anderer Uebergang",
   Selbstkontrolle).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

from . import mix
from .einstellungen import Einstellungen
from .profil import PHRASE, Profil

# Blendenlaenge als Zeit, nicht als feste Taktzahl: 16 Takte sind bei 174 BPM (DnB) 22 s, bei
# 120 BPM 32 s. Profis: House/Techno 16-32 Takte (30-60 s), DnB 8-16 (11-22 s), Hip-Hop kurz.
# Uebergangstest 14.10.2026 (46 Noten): 4 Takte (8 s) 1,4 · 8 Takte 2,3 · 16 Takte 3,9.
# kurz ab 20 s: 16 Runden, 8 Takte 2,85 / 4 Takte 1,45 gegen 16-32 Takte 3,2-3,4 ("zu abrupt" = haeufigste Kritik)
DAUER_S = {"kurz": (20.0, 32.0), "ausgewogen": (28.0, 64.0), "lang": (45.0, 66.0)}
WEITER_DAUER_S = {"kurz": (14.0, 24.0), "ausgewogen": (14.0, 34.0), "lang": (20.0, 34.0)}
TAKT_STUFEN = (4, 8, 16, 24, 32)
LOOP_REZEPTE = ("outro_loop", "loop_echo", "loop_filter", "loop_fx", "intro_loop_b", "rolle")
GESANG_REZEPTE = ("acapella", "gesang_zuerst")
GESANG_TEILE = ("A singt über B's Musik weiter", "B's Gesang kommt vor seiner Musik")
# Gesang ueber der Musik des anderen darf lange tragen ("ruhig ueber eine Minute, wenn die Tonart passt")
GESANG_LAENGEN = (16, 24, 32, 40, 48, 56, 64, 72, 80, 96)   # unabhaengig vom Stil: der Gesang bestimmt die Laenge
GESANG_MAX_S = 180.0   # Runde 4: "die Uebergangsdauer kann auch ruhig mal laenger als 1 Minute sein"
WEITER_GESANG_MAX = 32  # WEITER: der Uebergang muss schnell gebacken sein
# Experimente (Einstellung): Vorzugswert der DJ-Tricks und Bonus fuer Lagen, nach denen B's Drop einschlaegt
EXPERIMENT_WERT = {"klassisch": 0.0, "kreativ": 3.2, "wild": 5.0}
EXPERIMENT_DROP = {"klassisch": 0.0, "kreativ": 1.0, "wild": 2.5}
DROP_TRICKS = ("riser_drop", "bremse_drop", "spinback_drop", "teaser_drop", "gate_drop")
FRUEH_GESANG = "A's Gesang trägt"   # frueher Ausstieg: nur fuer eine Gesangsuebergabe (Runde 4, Fall 40)
DROP_SICHER_DB = 5.0    # Drop sicher neben dem Taktanfang: verwerfen (kalibriert, BAUPLAN-UEBERGAENGE §3.1)
PASSUNG_MIN = 0.35      # Double Drop/Drop-Cuts nur bis ~2,6 dB Pegel-Abstand der Drops (§4.2)
VORLAUF_MAX = 0.08      # Tempo-Abstand, den A vor der Blende auf B's Tempo gleiten darf (§5.2)
VORLAUF_TAKTE = 16
# Energielevel beider Songs (profil.energielevel): hart -> hart lebt vom Drop-Wechsel, ruhig -> ruhig von langen Blends
HART, RUHIG, ENERGIE_REZEPT_BONUS = 0.6, 0.35, 0.5
LANG32_BONUS = 0.3      # Runde 13: 32 Takte 4,67 (n = 3) gegen 16 Takte 3,93 (§6.2, nach 2 Runden pruefen)
BRUECKE = "B startet ohne Drums"
KRITIK_GEWICHT = 1.0    # Rang der Regie (0..1) + Gewicht * (Note des Kritikers - 3) (§2.3)
ANZAHL_INTERN = 8       # so viele Plaene bewertet der Kritiker


def laengen(modus: str, takt_s: float, sofort: bool = False) -> tuple[int, ...]:
    """Erlaubte Blendenlaengen (Takte) fuer den Stil, so dass die Dauer im Zeitfenster liegt."""
    lo, hi = (WEITER_DAUER_S if sofort else DAUER_S)[modus]
    passend = tuple(L for L in TAKT_STUFEN if lo <= L * takt_s <= hi)
    return passend or (min(TAKT_STUFEN, key=lambda L: min(abs(L * takt_s - lo), abs(L * takt_s - hi))),)


def _takt_s(p: Profil) -> float:
    return float(np.median(np.diff(p.takte))) if p.n > 1 else 2.0


@dataclass
class Plan:
    aus_s: float            # Blendenbeginn in A (Originalsekunde)
    ein_s: float            # Einsatz von B (Originalsekunde)
    takte: int
    einst: Einstellungen    # vollstaendig fuer uebergang.backen (Art, Bausteine, Takte)
    rezept: str
    grund: str
    punkte: float


@dataclass
class _Lage:
    i: int                  # Takt in A
    j: int                  # Takt in B
    takte: int
    punkte: float
    teile: list[str]
    k_ein: int = 0          # Intro-Loop von B: Takte
    mal: int = 0            # ... zusaetzliche Durchgaenge
    harm: float | None = None   # Tonvorrat im Fenster passt (0..1)
    drop_k: int = 0         # Double Drop: Takte bis zum gemeinsamen Drop (0 = keiner)


def _fenster(x: np.ndarray, von: int, n: int) -> np.ndarray:
    """x[von:von+n], hinter dem Ende mit 0 aufgefuellt."""
    aus = np.zeros(n)
    stueck = x[max(0, von):von + n]
    aus[:len(stueck)] = stueck
    return aus


def _mittelgewicht(n: int) -> np.ndarray:
    """Wie stark beide Songs in Takt k gleichzeitig hoerbar sind (Mitte der Blende am meisten)."""
    x = (np.arange(n) + 0.5) / n
    return 4 * x * (1 - x)


def _a_kandidaten(pa: Profil, ab_takt: int, e: Einstellungen, sofort: bool,
                  stems_da: bool = False) -> list[tuple[int, float, str]]:
    """(Takt, Punkte, Begruendung) fuer den Ausstieg aus A."""
    if sofort and e.weiter_ab == "takt":   # WEITER: naechster Takt
        return [(ab_takt, 0.0, "")]
    if sofort:   # WEITER: naechste 4-Takt-Grenze (Phrase, wenn sie gleich kommt), notfalls 1-2 Gruppen spaeter
        naechste_phrase = pa.phrase_ab(ab_takt)
        erste = naechste_phrase if naechste_phrase - ab_takt <= 4 else naechste_phrase - 4
        return [(erste + 4 * k, -2.5 * k, "") for k in range(3) if erste + 4 * k < pa.n]
    et = pa.etiketten()
    n_ph = len(et)
    aus = []
    if e.spielanteil == "schnell":
        # Profi-Kurzspiel: Wechsel in der zweiten Haelfte, kurz nachdem der Drop gelaufen ist.
        mitte = pa.n // 2
        drops = [pa.phrase_start(p) for p in range(n_ph) if et[p] == "drop" and pa.phrase_start(p) >= mitte] or \
            [pa.phrase_start(p) for p in range(n_ph) if et[p] == "haupt" and pa.phrase_start(p) >= mitte]
        # Runde 8: "du schneidest immer weg, wenn der Drop gerade gelaufen ist" - A's Drop laeuft aus
        # (bis sein Abschnitt endet, hoechstens 2 Phrasen)
        if drops:
            q0 = pa.phrase_von(drops[0])
            q = q0 + 1
            while q < n_ph and et[q] in ("drop", "haupt") and q < q0 + 2:
                q += 1
            start = pa.phrase_start(q)
        else:
            start = mitte
        for k, takt in enumerate([g for g in pa.grenzen() if g >= start][:3]):
            aus.append((takt, 3.0 - 1.5 * k, "zweite Hälfte nach dem Drop"))
        if drops and start > pa.phrase_ab(drops[0] + 1):   # Ausweg, wenn A nach seinem Drop zu kurz ist
            aus.append((pa.phrase_ab(drops[0] + 1), -1.5, "zweite Hälfte nach dem Drop"))
        if all(pa.n - t < 16 for t, _, _ in aus):   # Drop-Abschnitt bis kurz vors Ende: Platz fuer die Blende
            # (Runde 14-17, Must Be Right: nur 10 Takte Rest, Loop ueber Gesang unmoeglich -> 4x Note 1-2)
            platz = [g for g in pa.grenzen() if mitte <= g <= pa.n - 16]
            if platz:
                aus.append((platz[-1], -2.0, "zweite Hälfte, Platz für die Blende"))
    else:
        # So lange wie moeglich: Kandidaten im letzten Drittel, spaeter = besser.
        start = pa.phrase_start(pa.phrase_von(int(pa.n * 0.7)))
        for takt in [g for g in pa.grenzen() if g >= start]:
            aus.append((takt, 6.0 * takt / max(1, pa.n), "spielt lang"))
        ga = pa.gesang() if stems_da else None
        if ga is not None:   # A's letzte Gesangsteile: von dort kann A's Stimme lange ueber B weiterlaufen
            for takt in [g for g in pa.grenzen() if pa.phrase_start(pa.phrase_von(pa.n // 2)) <= g < start]:
                if ga[takt:takt + PHRASE].any():
                    aus.append((takt, 6.0 * takt / max(1, pa.n), FRUEH_GESANG))
    return [(t, p, g) for t, p, g in aus if t >= ab_takt] or [(pa.phrase_ab(ab_takt), -2.0, "")]


def _beatlos(pb: Profil) -> np.ndarray:
    """Takte ohne Drums (0/1): Drum-Stem unter -35 dB, ohne Stems Tiefband 10 dB unter dem Song-Median."""
    if pb.stems is not None:
        return pb.stems["drums"] < -35.0
    return pb.baender[:, 0] < float(np.median(pb.baender[:, 0])) - 10.0


def _brueckenstart(pb: Profil, j: int) -> bool:
    """Bei Takt j beginnt ein beatloser Teil von mindestens 4 Takten (dort hoert man kein Tempo)."""
    return j + 4 <= pb.n and bool(_beatlos(pb)[j:j + 4].all())


def _b_kandidaten(pb: Profil, e: Einstellungen, laengen, sync: bool = True) -> list[tuple[int, float]]:
    """(Takt, Punkte) fuer den Einsatz von B: Phrasenanfaenge in den ersten ~40 %.
    Ohne Tempo-Angleich zaehlen beatlose Teile (Brücke, §5.1) deutlich mehr."""
    et = pb.etiketten()
    aus = []
    # Songanfang und B's Phrasengrenzen (mit Versatz): nie mitten in B's Phrase einsteigen
    for takt in [g for g in pb.grenzen() if g <= int(pb.n * 0.4)]:
        if e.spielanteil == "schnell":
            p = 0.0    # Intro ueberspringen ist erlaubt
        else:
            p = -0.8 * takt / PHRASE    # moeglichst von vorn
        if et[pb.phrase_von(takt)] == "break":
            p -= 1.0
        if not sync and _brueckenstart(pb, takt):
            p += 3.0
        aus.append((takt, p))
    return aus


def _b_index(j: int, L: int, k_ein: int = 0, mal: int = 0) -> np.ndarray:
    """B-Takt je Blendentakt; mit Intro-Loop laufen B's erste `k_ein` Takte (mal+1)-mal."""
    k = np.arange(L)
    if not k_ein or not mal:
        return j + k
    schleife = k_ein * (mal + 1)
    return np.where(k < schleife, j + k % k_ein, j + k_ein + (k - schleife))


def _werte(x: np.ndarray, idx: np.ndarray) -> np.ndarray:
    """x[idx], ausserhalb des Songs 0."""
    return np.where(idx < len(x), x[np.clip(idx, 0, len(x) - 1)], 0.0)


def _harmonie(pa: Profil, pb: Profil, i: int, bi: np.ndarray) -> float | None:
    """Wie gut passt der Tonvorrat im Fenster zusammen (0..1, Kosinus der mittleren Chroma)?

    Ueber das Fenster gemittelt, nicht Takt fuer Takt: zwei Songs in derselben Tonart spielen selten
    gleichzeitig dieselben Akkorde (je Takt: gleiche Tonart Median 0,63, fremde 0,47 - kaum getrennt;
    gemittelt 0,78 gegen 0,59, gemessen an den Paaren der Uebergangstests)."""
    if pa.chroma is None or pb.chroma is None:
        return None
    w = _mittelgewicht(len(bi))[:, None]
    ia = np.clip(i + np.arange(len(bi)), 0, pa.n - 1)
    ca, cb = np.sum(pa.chroma[ia] * w, axis=0), np.sum(pb.chroma[np.clip(bi, 0, pb.n - 1)] * w, axis=0)
    return float(ca @ cb / max(float(np.linalg.norm(ca) * np.linalg.norm(cb)), 1e-9))


def _gesang_uebergabe(pa: Profil, pb: Profil, i: int, bi: np.ndarray) -> tuple[str, int, int] | None:
    """Gesangs-Uebergabe mit Stems, wenn dabei nie zwei Stimmen gleichzeitig klingen:
    ("acapella", Takt nach A's letzter Zeile, Takte A-Gesang allein ueber B's Musik) oder
    ("gesang_zuerst", Takt, ab dem B's Musik kommt, Takte B-Gesang ueber A's Instrumental)."""
    ga, gb = pa.gesang(), pb.gesang()
    L = len(bi)
    if ga is None or gb is None or pa.n - i < L:   # A endet in der Blende: dort traegt nur ein Loop
        return None
    a, b = _fenster(ga, i, L) > 0, _werte(gb, bi) > 0
    tausch = max(2, min(8, L // 4))                  # Takte, in denen die Instrumente wechseln
    if b.any() and not a[max(0, int(np.flatnonzero(b)[0]) - 1):].any():
        v = int(np.flatnonzero(b)[0])                # B's erste Zeile im Fenster; A singt ab da nicht mehr
        # B singt ueber A, bis B's Musik am Ende kommt - oder frueher, wenn A's Musik vorher ausklingt
        # (Runde 3: "da Track A schon frueh endet, haetten B's Instrumente frueher einsetzen muessen")
        x = pa.gesamt[i:i + L]
        leise = np.flatnonzero(x < np.max(x[:4]) - 8.0)
        g = (int(leise[0]) if leise.size else L) - tausch
        # B's Stimme soll wirklich tragen: sie beginnt frueh und singt den groessten Teil bis zur Uebergabe
        if g - v >= 4 and int(b[v:g].sum()) >= max(4, 0.6 * (g - v)) and v <= max(8, L // 4):
            return "gesang_zuerst", g, int(b[v:g].sum())
        return None
    if a.any():
        g = int(np.flatnonzero(a)[-1]) + 1          # A's Zeile endet hier (danach singt A im Fenster nicht)
        # A's Zeile endet in der Blende - oder genau mit ihr (danach singt A nicht weiter, auch am Songende)
        zeile_endet = g < L or not _fenster(ga, i + L, 2).any()
        if not zeile_endet:   # A singt durch: an der letzten Phrasengrenze ausblenden (mit Echo, Runde 4 Fall 45)
            grenzen = [k for k in range(tausch + 2, L) if (i + k) % PHRASE == 0]
            if grenzen:
                g, zeile_endet = grenzen[-1], True
        allein = int(a[tausch:g].sum())              # A singt allein ueber B's Musik
        if zeile_endet and allein >= 4 and not b[:g + 5].any():   # B singt erst, wenn A's Echo verklungen ist
            return "acapella", g, allein
    return None


def _bewerten(pa: Profil, pb: Profil, i: int, j: int, L: int, e: Einstellungen, k_ein: int = 0,
              mal: int = 0, stems_da: bool = False, tonart_ok: bool = False) -> tuple[float, list[str], float | None]:
    """Punkte einer Kombination (hoeher = besser), Stichworte fuer die Begruendung, Harmonie."""
    if stems_da and not k_ein:
        bi = _b_index(j, L)
        ueb = _gesang_uebergabe(pa, pb, i, bi)
        harm = _harmonie(pa, pb, i, bi) if ueb is not None else None
        # gleiche/benachbarte Tonart: ab 0,55 (10 % der Fenster gleicher Tonart liegen unter 0,59)
        if ueb is not None and (harm is None or harm >= (0.55 if tonart_ok else 0.65)):   # Stimme ueber fremder Musik: Toene muessen passen
            # Die Musik wechselt nur in `t` Takten (acapella am Anfang, gesang_zuerst am Ende); danach
            # bzw. davor klingt eine Stimme ueber dem anderen Song. Bewertet wird dieser Wechsel, die
            # Stimme bringt je Takt Punkte, der Tonvorrat zaehlt ueber das ganze Fenster.
            t = max(2, min(8, L // 4))
            von = 0 if ueb[0] == "acapella" else L - t
            p, teile, _ = _grundwert(pa, pb, i + von, j + von, t, e)
            if e.spielanteil == "lang":   # A "spielt" mit seiner Stimme bis zur Uebergabe weiter
                p += 1.5 * (_verpasst(pa, i + von + t) - _verpasst(pa, i + (ueb[1] if von == 0 else L)))
                if von == 0:   # Gegenstueck zu _a_kandidaten (spaeter = besser): A endet erst nach seiner Zeile
                    p += 6.0 * ueb[1] / max(1, pa.n)
            if harm is not None:
                p += float(np.clip(4.0 * (harm - 0.7), -2.0, 1.2)) * (L / 16.0 + 0.5)
            # Runde 3: "die Vocals haetten viel laenger bleiben koennen" - die Stimme ueber dem anderen Song
            # ist erwuenscht, je Takt deutlich
            return p + 2.0 + 0.6 * ueb[2], teile + [GESANG_TEILE[GESANG_REZEPTE.index(ueb[0])]], harm
    p, teile, harm = _grundwert(pa, pb, i, j, L, e, k_ein, mal)
    # A singt ueber das Blendenende hinaus weiter: ohne Stems endet A mitten im Wort
    ga = pa.gesang()
    if ga is not None and i + L < pa.n and ga[i + L - 1] > 0 and ga[i + L] > 0:
        p -= 3.0
    return p, teile, harm


DROP_AUSSPIELEN = 16    # so viele Takte laeuft ein Drop von A mindestens, bevor die Blende beginnt
STRUKTUR_STRAFE = 20.0  # Strukturfehler: nur, wenn sonst nichts geht


def _strukturfehler(pa: Profil, pb: Profil, i: int, bi: np.ndarray, L: int, sofort: bool,
                    gesang: bool = False) -> str | None:
    """Harte DJ-Regeln (nach Runde 16, 10 von 10 schlechtesten Faellen verletzten eine davon):
    - A startet keinen Drop in der Blende (Faelle 6, 34: "Drop von A viel frueher" als der von B),
    - B startet keinen Drop mitten in der Blende (er gehoert ans Ende: der Wechsel),
    - A's Drop spielt mindestens 16 Takte aus, bevor die Blende beginnt (Fall 30: "mitten im Drop leiser").
    Double Drops (beide Drops auf demselben Takt) baut _double_drops getrennt."""
    if not gesang and any(i < d < i + L for d in pa.drops()):
        return "A's Drop käme in der Blende"
    b_drops = set(pb.drops())
    if not gesang and any(int(t) in b_drops for t in bi[1:]):
        return "B's Drop käme mitten in der Blende"
    if not sofort and any(0 <= i - d < DROP_AUSSPIELEN for d in pa.drops()):
        return "A's Drop wäre noch keine 16 Takte gelaufen"
    return None


def _verpasst(pa: Profil, ab_takt: int) -> int:
    """Hauptteile/Drops von A ab diesem Takt (entfallen, wenn A hier aufhoert)."""
    ea = pa.etiketten()
    return sum(1 for q in range(pa.phrase_von(ab_takt), len(ea)) if ea[q] in ("drop", "haupt"))


def _grundwert(pa: Profil, pb: Profil, i: int, j: int, L: int, e: Einstellungen, k_ein: int = 0,
               mal: int = 0) -> tuple[float, list[str], float | None]:
    """Punkte des Musikwechsels im Fenster (ohne Stem-Gesangsuebergabe)."""
    w = _mittelgewicht(L)
    bi = _b_index(j, L, k_ein, mal)
    nach_takt = j + L - mal * k_ein if k_ein else j + L
    teile, p = [], 0.0
    ga, gb = pa.gesang(), pb.gesang()
    if ga is not None and gb is not None:
        clash = float(np.sum(_fenster(ga, i, L) * _werte(gb, bi) * w)) / L
        p -= 8.0 * clash   # Runde 16 (Faelle 4, 23): "lass die Vocals ruhig uebereinander laufen", lieber ruhiger
        if clash < 0.02:
            teile.append("kein Gesang gegeneinander")
    # B uebernimmt nach der Blende mit einem tragenden Teil
    eb = pb.etiketten()
    nach = eb[min(len(eb) - 1, pb.phrase_von(nach_takt))] if nach_takt < pb.n else "outro"
    p += {"drop": 3.0, "haupt": 2.0, "aufbau": 0.5, "intro": 0.0, "break": -1.0, "outro": -3.0}[nach]
    if nach == "drop":
        teile.append("B's Drop direkt nach der Blende")
    # B's Drop mitten in der Blende ist verschenkt
    drops_b = {pb.phrase_start(q) for q, x in enumerate(eb) if x == "drop"}
    if any(int(t) in drops_b for t in bi[1:] if t != j):
        p -= 2.5
    # A im Fenster: duenn ist gut, Hauptteil wegblenden schlecht
    ea = pa.etiketten()
    lab_a = [ea[min(len(ea) - 1, pa.phrase_von(k))] for k in range(i, min(pa.n, i + L))] or ["outro"]
    gut_a = np.mean([{"outro": 1.0, "break": 0.6, "intro": 0.3, "aufbau": 0.2, "haupt": -0.6,
                      "drop": -1.0}[x] for x in lab_a])
    p += 2.0 * gut_a
    # Runde 10: "im Drop in ein Intro uebergehen ist nicht gut" - A voll, B noch duenn
    lab_b = [eb[min(len(eb) - 1, pb.phrase_von(int(t)))] for t in bi if t < pb.n]
    if np.mean([x in ("drop", "haupt") for x in lab_a]) > 0.5 and lab_b and \
            np.mean([x == "intro" for x in lab_b]) > 0.5:
        p -= 2.0
    if lab_a[0] in ("outro", "break"):
        teile.append(f"A im {'Outro' if lab_a[0] == 'outro' else 'Break'}")
    # A hoert natuerlich auf: Songende oder Abschnittswechsel am Blendenende
    if i + L >= pa.n - 2 or (i + L < pa.n and ea[min(len(ea) - 1, pa.phrase_von(i + L))] != lab_a[-1]):
        p += 1.0
    # Spielanteil "lang": kein Hauptteil/Drop von A darf durch den fruehen Ausstieg entfallen
    if e.spielanteil == "lang":
        p -= 1.5 * _verpasst(pa, i + L)
    if e.modus == "lang" and L == 32 and pa.n - i >= 32:
        p += LANG32_BONUS
    # Zwei duenne Teile vertragen lange Blenden, zwei dichte nicht
    dichte = 0.5 * (np.mean(_fenster(pa.dichte(), i, L)) + np.mean(_werte(pb.dichte(), bi)))
    p += (0.6 - dichte) * (L / 8.0)
    # Tonvorrat im Fenster selbst (nicht nur die Tonart des ganzen Songs)
    harm = _harmonie(pa, pb, i, bi)
    if harm is not None:
        p += float(np.clip(4.0 * (harm - 0.7), -2.0, 1.2)) * (L / 16.0 + 0.5)
        if harm > 0.85:
            teile.append("Harmonie passt im Fenster")
    # Energiesprung zwischen A's Fenster und B danach
    e_a = float(np.mean(pa.gesamt[i:i + max(1, L // 2)])) if i < pa.n else -30.0
    e_b = float(np.mean(pb.gesamt[nach_takt:nach_takt + PHRASE])) if nach_takt < pb.n else -30.0
    sprung = e_b - e_a
    erlaubt = (0.0, 6.0) if e.spielanteil == "schnell" else (-3.0, 3.0)
    p -= 0.3 * max(0.0, erlaubt[0] - sprung, sprung - erlaubt[1])
    # Unsicheres Taktraster: lieber nicht lange ueberlappen
    unsicher = 1.0 - 0.5 * (np.mean(_fenster(pa.raster_ok.astype(float), i, L))
                            + np.mean(_werte(pb.raster_ok.astype(float), bi)))
    p -= 4.0 * unsicher * (L / 16.0)
    if k_ein:
        # Uebergangstest Runde 2: "beim einzublendenden Lied wird fast nie ein Loop benutzt" -
        # bei gleich guter Lage lieber B's Intro loopen (A loopt ohnehin oft)
        p += 0.3
        teile.append(f"B's Intro geloopt ({k_ein} Takte × {mal + 1}), Gesang/Drop erst danach")
    return p, teile, harm


def _intro_loops(pb: Profil, j: int, L: int) -> list[tuple[int, int]]:
    """Moegliche Intro-Loops von B: (Takte, Wiederholungen), wenn B's Gesang oder Hauptteil sonst in
    der Blende kaemen (ein Drop waere dort verschenkt) und B's Anfang sauber ist (kein Gesang, Drums)."""
    gb = pb.gesang()
    singt = gb is not None and bool(np.any(gb[j:j + L] > 0))
    voll_drin = any(x in ("drop", "haupt") and j < pb.phrase_start(q) < j + L for q, x in enumerate(pb.etiketten()))
    if not (singt or voll_drin):
        return []
    aus = []
    for k in (4, 8):
        if (j + 2 * k > pb.n or (gb is not None and gb[j:j + k].any())
                or np.mean(pb.drums()[j:j + k]) < 0.5):
            continue
        for mal in (1, 2, 3):
            if k * (mal + 1) <= L:
                aus.append((k, mal))
    return aus


def _drop_takt(p: Profil, takt: int) -> int:
    """Drop-Takt auf den Takt genau: ein erkannter Drop (Profil.drops) bis 4 Takte daneben, sonst bis
    +-2 Takte daneben, wenn Bass, Drums und Pegel dort deutlich staerker einsetzen (je 2 Takte)."""
    nah = [d for d in p.drops() if abs(d - takt) <= 4]
    if nah:
        return min(nah, key=lambda d: abs(d - takt))
    reihen = [p.gesamt] + ([p.stems["bass"], p.stems["drums"]] if p.stems else [p.baender[:, 0]])

    def sprung(k: int) -> float:
        if k < 2 or k + 2 > p.n:
            return -np.inf
        return float(sum(np.mean(x[k:k + 2]) - np.mean(x[k - 2:k]) for x in reihen))

    best = max(range(takt - 2, takt + 3), key=sprung)
    return best if sprung(best) > 1.5 * max(sprung(takt), 1.0) else takt


def _einsatz(p: Profil, k: int) -> float:
    """Wie stark ein Drop auf Takt k einsetzt: groesster Sprung (dB, je 2 Takte) in Pegel, Bass oder Drums.
    Runde 11: die Etiketten nannten einen Drum-Aufbau "Drop", der Bass kam 20 Takte spaeter ("Takt daneben")."""
    if k < 2 or k + 2 > p.n:
        return 0.0
    reihen = [p.gesamt] + ([p.stems["bass"], p.stems["drums"]] if p.stems else [p.baender[:, 0]])
    return max(float(np.mean(x[k:k + 2]) - np.mean(x[k - 2:k])) for x in reihen)


def _drop_werte(p: Profil, k: int) -> np.ndarray:
    """Pegel, Drums und Bass (relativ zum Pegel) der 8 Takte ab dem Drop."""
    s = slice(k, k + PHRASE)
    g = float(np.mean(p.gesamt[s]))
    st = p.stems or {"drums": p.baender[:, 1], "bass": p.baender[:, 0]}
    return np.array([g, float(np.mean(st["drums"][s])) - g, float(np.mean(st["bass"][s])) - g])


def _drop_gleich(pa: Profil, pb: Profil, d_a: int, d_b: int) -> bool:
    """Drop-Cuts nur zwischen gleich starken Drops: Pegel bis 1 dB, Drums/Bass bis 2 dB auseinander.
    Runde 12: drei Drop-Cuts Note 2 ("komplett unterschiedliches Energielevel"), Pegel 1,6-3,5 dB auseinander."""
    d = np.abs(_drop_werte(pa, d_a) - _drop_werte(pb, d_b))
    return bool(d[0] <= 1.0 and d[1] <= 2.0 and d[2] <= 2.0)


DROP_EINSATZ = 6.0   # dB: darunter ist es kein Drop, auf den ein Trick oder ein Double Drop zielen kann


def _tief(x: np.ndarray, rate: int) -> np.ndarray:
    """Tiefband (< 150 Hz, Kick und Bass) als Leistung je Sample, mono."""
    mono = x.mean(axis=1) if x.ndim > 1 else x
    return mix.band_teilen(np.asarray(mono, np.float64), rate, 150.0)[0] ** 2


def _drop_schlag(p: Profil, audio: np.ndarray, rate: int, takt: int) -> tuple[int, int, float]:
    """(Takt, Versatz in Achteln, Sicherheit dB): Wo setzt der Drop auf den Schlag genau ein?

    Tiefband-Pegel je Achtel (dB) +-2 Takte um den Taktanfang; je Kandidat (ganze Schlaege, +-1 Takt)
    das dB-Mittel des Takts danach minus des Takts davor - im dB-Mittel zaehlt ein einzelner Vorschlag
    vor dem Drop kaum. Sicherheit = Abstand zum zweitbesten Schlag. Versatz != 0: das Downbeat-Raster
    liegt neben dem Drop (Beat This!-Fehler oder ein anderer Einsatz ist der Drop)."""
    if takt < 2 or takt + 2 >= p.n:
        return takt, 0, 0.0
    tl = float(p.takte[takt + 1] - p.takte[takt])
    achtel = tl / 8 * rate
    a0 = int(round((p.takte[takt] - 2 * tl) * rate))
    if achtel < 4 or a0 < 0 or a0 + int(32 * achtel) > len(audio):
        return takt, 0, 0.0
    leistung = _tief(audio[a0:a0 + int(32 * achtel)], rate)
    grenzen = np.round(np.arange(33) * achtel).astype(int)
    db = 10.0 * np.log10(np.add.reduceat(leistung, grenzen[:-1]) / np.diff(grenzen) + 1e-9)
    werte = {k: float(np.mean(db[16 + 2 * k:24 + 2 * k]) - np.mean(db[8 + 2 * k:16 + 2 * k])) for k in range(-4, 5)}
    best = max(werte, key=werte.get)
    return takt, 2 * best, float(werte[best] - max(v for k, v in werte.items() if k != best))


def _drop_ok(p: Profil, takt: int, audio: np.ndarray | None, rate: int) -> bool:
    """Kein Drop sicher neben der Eins (ohne Audio: nicht pruefbar, alter Weg). Runde 12/13: "verwerfen, wenn
    unsicher" haette 4 von 5 Double Drops mit Note 5 gestrichen; "sicher daneben" fing den Fall mit einem Takt
    Versatz (Runde 13, Fall 13) - den mit einem Schlag faengt die Kick-Kontrolle nach dem Backen."""
    if audio is None:
        return True
    _, versatz, sicher = _drop_schlag(p, audio, rate, takt)
    return versatz == 0 or sicher < DROP_SICHER_DB


def kick_lage(x: np.ndarray, rate: int, raster: np.ndarray, k: int, takte: int = 4) -> float | None:
    """Lage der Anschlaege (Kick + Snare-Koerper, Faltung wie `anker.versatz`) in `takte` Takten ab Takt k:
    so viele s liegen sie hinter dem Raster (Taktanfaenge in s). None ohne klares Muster."""
    from . import anker

    raster = np.asarray(raster, float)
    if k < 0 or k + takte >= len(raster):
        return None
    a0, a1 = int(raster[k] * rate), int(raster[k + takte] * rate)
    mono = x[a0:a1].mean(axis=1) if x.ndim > 1 else x[a0:a1]
    if len(mono) < rate:
        return None
    f = anker._anschlag(mono, rate, 0, 100) + anker._anschlag(mono, rate, 150, 400)
    t = raster[k] + np.arange(len(f)) * anker.HOP / rate
    beats = np.interp(np.arange(4 * takte + 1) / 4, np.arange(takte + 1), raster[k:k + takte + 1])
    j = np.clip(np.searchsorted(beats, t) - 1, 0, len(beats) - 2)
    i, klar = anker._faltung(f, ((t - beats[j]) / (beats[j + 1] - beats[j]) + 0.5) % 1.0 - 0.5)
    return ((i + 0.5) / anker.STUFEN - 0.5) * float(np.median(np.diff(beats))) if klar >= anker.KLAR_MIN else None


def kicks_versetzt(a_roh: np.ndarray, a_raster: np.ndarray, ia: int, b_roh: np.ndarray, b_raster: np.ndarray,
                   ib: int, rate: int) -> str | None:
    """Kick-Kontrolle fuer Double Drop/Drop-Cuts: liegen A's Kicks ab Takt ia und B's ab Takt ib (Originale, je eigenes
    Raster) gleich weit neben ihrem Raster? Sonst laufen nach dem gemeinsamen Drop zwei versetzte Kick-Zuege.
    Ersetzt die Messung im fertigen Mix (bis Runde 18): deren Einsatz-Erkennung trennt Zuege unter ~80 ms nicht und
    mass je nach Kick-Form 0-30 ms neben dem Raster - 5 von 13 Double Drops fielen durch, auch einzelne Songs."""
    la, lb = kick_lage(a_roh, rate, a_raster, ia), kick_lage(b_roh, rate, b_raster, ib)
    if la is None or lb is None or abs(lb - la) <= FLAM_S:
        return None
    return f"Kicks von A und B {abs(lb - la) * 1000:.0f} ms versetzt"


FLAM_S = 0.015   # weiter auseinander klingen zwei Kicks doppelt ("nicht im Takt")


def _passung(pa: Profil, pb: Profil, d_a: int, d_b: int) -> float:
    """Passen zwei Drops in der Energie zusammen (0..1)? 1 bei gleichem Pegel der 8 Takte ab dem Drop, 0 ab
    4 dB Abstand. Kalibriert an Runde 12/13 (BAUPLAN-UEBERGAENGE §4.2): "passen nicht" lag 3,1-3,7 dB auseinander,
    Note 5 hoechstens 2,2 dB; Drums/Bass trennten nicht (Note 5 mit 4,9 dB Bass-Abstand). Klang-Vektoren
    zaehlen nicht: EmbeddingGemma 2 trennt die Genres nicht (AUC 0,57, ADR-015 Nachtrag)."""
    return 1.0 - min(1.0, abs(float(_drop_werte(pa, d_a)[0] - _drop_werte(pb, d_b)[0])) / 4.0)


def _double_drops(pa: Profil, pb: Profil, e: Einstellungen, ab_takt: int, stems_da: bool = False,
                  audio: tuple | None = None, a=None, b=None) -> list[_Lage]:
    """Double Drop (DnB, Andy C): A's und B's Drop fallen auf denselben Takt. B laeuft eine Phrase vorher
    ohne Bass mit ein, am Drop tauscht der Bass (nie zwei Baesse), beide Drops laufen D Takte zusammen,
    dann geht A. Nur mit passenden Toenen; ohne Stems auch nur ohne zwei Stimmen im Drop (mit Stems tauscht
    die Stimme mit dem Bass). Punkte: relativ (_rangliste).
    Mit `audio` (A, B, Rate) nur Drops, die auf den Schlag genau sicher sind (§3.1); nur Paare, die passen (§4.2)."""
    a_audio, b_audio, rate = audio or (None, None, 44100)
    ea, eb = pa.etiketten(), pb.etiketten()
    a_drops = [d for d in (_drop_takt(pa, pa.phrase_start(q)) for q, x in enumerate(ea)
                           if x == "drop" and pa.phrase_start(q) >= max(ab_takt + PHRASE, pa.n // 2))
               if _einsatz(pa, d) >= DROP_EINSATZ and _drop_ok(pa, d, a_audio, rate)]
    b_drops = [d for d in (_drop_takt(pb, pb.phrase_start(q)) for q, x in enumerate(eb) if x == "drop" and q >= 1)
               if _einsatz(pb, d) >= DROP_EINSATZ and _drop_ok(pb, d, b_audio, rate)][:2]
    ga, gb = pa.gesang(), pb.gesang()
    aus = []
    for d_a in a_drops:
        for d_b in b_drops:
            if _passung(pa, pb, d_a, d_b) < PASSUNG_MIN:
                continue   # Runde 12/13: "Lieder passen nicht zueinander"
            for dauer in (8, 16):
                i, j, L = d_a - PHRASE, d_b - PHRASE, PHRASE + dauer
                if i < ab_takt or j < 0 or pa.n - i < L or j + L > pb.n:
                    continue
                bi = _b_index(j, L)
                harm = _harmonie(pa, pb, i, bi)
                if harm is not None and harm < 0.8:
                    continue   # zwei volle Drops uebereinander: die Toene muessen gut passen (Runde 9: "beissen sich")
                if pa.stems and pb.stems and min(_drop_werte(pa, d_a)[2], _drop_werte(pb, d_b)[2]) < -20.0:
                    continue   # ein Drop ohne Bass: kein echter Drop zum Uebereinanderlegen
                if not stems_da and ga is not None and gb is not None and \
                        (_fenster(ga, d_a, dauer) * _werte(gb, bi[PHRASE:])).any():
                    continue   # zwei Stimmen im Drop
                # lieber 16 Takte: A's Drop soll lange voll laufen (Runde 9: "Drop von A laenger hoeren")
                p = 2.0 * (harm - 0.85 if harm is not None else 0.0) + 1.0 * d_a / pa.n + (0.3 if dauer == 16 else 0.0)
                aus.append(_Lage(i, j, L, p, ["Double Drop: beide Drops auf denselben Takt"], harm=harm, drop_k=PHRASE))
    return aus


def _chill(eintrag, p: Profil) -> bool:
    """Ruhige elektronische Musik: der Ordner (das Genre der Bibliothek) heisst Chill; ohne Ordner (Upload)
    das Energielevel (Chill-Median 0,39, UKG/DnB 90 % ueber 0,5)."""
    ordner = [t.lower() for t in Path(eintrag.pfad).parent.parts] if eintrag is not None else []
    if ordner and ordner[-1] != "upload":
        return any("chill" in t for t in ordner)
    return p.energielevel() < 0.5


def _rangliste(pa: Profil, pb: Profil, e: Einstellungen, ab_takt: int, sofort: bool,
               stems_da: bool = False, tonart_ok: bool = False, sync: bool = True,
               audio: tuple | None = None, a=None, b=None) -> list[_Lage]:
    stufen = laengen(e.modus, _takt_s(pa), sofort)
    # Gesangs-Uebergaben: Laenge nach dem Gesang, nicht nach dem Stil (auch viel laenger)
    extra = () if not stems_da else tuple(
        L for L in GESANG_LAENGEN if L not in stufen and L * _takt_s(pa) <= GESANG_MAX_S
        and (not sofort or L <= WEITER_GESANG_MAX))
    lagen = []
    drop_bonus = 0.0 if sofort else EXPERIMENT_DROP[e.experimente]
    lo, hi = sorted((pa.energielevel(), pb.energielevel()))
    hart, ruhig = lo >= HART, hi <= RUHIG
    for i, p_a, g_a in _a_kandidaten(pa, ab_takt, e, sofort, stems_da):
        for j, p_b in _b_kandidaten(pb, e, stufen, sync):
            for L in stufen + extra:
                if j + L > pb.n:
                    continue
                if L in extra:
                    ueb = _gesang_uebergabe(pa, pb, i, _b_index(j, L))
                    if ueb is None or ueb[1] < L - 12:   # lange Blende nur, soweit Gesang/Musik sie tragen
                        continue
                rest_a = pa.n - i
                if rest_a < L:   # A endet in der Blende: nur mit Loop (A braucht Drums am Anfang)
                    if np.mean(_fenster(pa.drums(), i, 2)) < 0.5 or rest_a < 2:
                        continue
                varianten = [(0, 0)] + (_intro_loops(pb, j, L) if not sofort else [])
                for k_ein, mal in varianten:
                    p, teile, harm = _bewerten(pa, pb, i, j, L, e, k_ein, mal, stems_da, tonart_ok)
                    # Gesangsuebergaben: die Musik des einen laeuft unter der Stimme des anderen, ihr Drop darf kommen
                    gesang = bool(set(teile) & set(GESANG_TEILE))
                    fehler = _strukturfehler(pa, pb, i, _b_index(j, L, k_ein, mal), L, sofort, gesang)
                    if fehler:
                        p -= STRUKTUR_STRAFE
                        teile = teile + [fehler]
                    if (L in extra or g_a == FRUEH_GESANG) and not set(teile) & set(GESANG_TEILE):
                        continue   # Toene passen nicht: keine Ueberlaenge; frueher Ausstieg nur fuer A's Stimme
                    if k_ein and harm is not None and harm < 0.65:
                        continue   # beissende Toene nicht lange uebereinander loopen
                    if "B's Drop direkt nach der Blende" in teile:   # Experimente: Drop-Tricks brauchen den Drop
                        p += drop_bonus
                        if hart:
                            p += ENERGIE_REZEPT_BONUS
                            teile = teile + ["beide hart: Drop-Wechsel"]
                    if ruhig and L >= 16:
                        p += ENERGIE_REZEPT_BONUS
                        teile = teile + ["beide ruhig: lange Blende"]
                    if not sync and _brueckenstart(pb, j):
                        teile = teile + [BRUECKE]
                    lagen.append(_Lage(i, j, L, p + p_a + p_b, ([g_a] if g_a else []) + teile, k_ein, mal, harm))
    lagen.sort(key=lambda x: -x.punkte)
    if e.experimente != "klassisch" and not sofort and lagen and sync:
        # Double Drops gegen die beste normale Lage: "wild" vorn, "kreativ" nur mit sehr passenden Toenen
        vorn = lagen[0].punkte + (1.0 if e.experimente == "wild" else -1.0)
        dd = [replace(x, punkte=vorn + x.punkte) for x in _double_drops(pa, pb, e, ab_takt, stems_da, audio, a, b)]
        lagen = sorted(lagen + dd, key=lambda x: -x.punkte)
    return lagen


def _rezept(lage: _Lage, pa: Profil, pb: Profil, e: Einstellungen, sync: bool, harmonisch: bool,
            stems_da: bool, vorher: str | None, vorlieben: dict[str, float] | None = None,
            loop_ok: bool = True, sofort: bool = False, audio: tuple | None = None, a=None, b=None,
            vorlauf: bool = False) -> tuple[str, dict, str]:
    """(Rezeptname, Einstellungsfelder, Begruendung) aus der Lage.

    Jedes Rezept ist in sich abgestimmt: ein Effekt auf A kommt nur dort, wo A noch voll
    spielt (Fader oben, EQ offen - "hart_aus" haelt A bis zum Schnitt), ein Filter nur, wenn
    nicht schon der EQ dasselbe Band wegnimmt, ein Loop nur auf sauber wiederholbaren Takten.
    """
    i, j, L = lage.i, lage.j, lage.takte
    bi = _b_index(j, L, lage.k_ein, lage.mal)
    ga, gb = pa.gesang(), pb.gesang()
    singt_a = ga is not None and np.mean(_fenster(ga, i + L // 2, L - L // 2)) > 0.25
    singt_b = gb is not None and np.mean(_werte(gb, bi)) > 0.25
    a_endet = pa.n - i < L
    real = max(1, min(L, pa.n - i))   # nur Takte, in denen A noch spielt (dahinter ist Stille, kein Break)
    a_break = np.mean(_fenster(pa.drums(), i, real)) < 0.3
    gesang_kommt = ga is not None and not a_endet and np.mean(_fenster(ga, i, 2)) < 0.25 and \
        np.mean(_fenster(ga, i + L // 2, L - L // 2)) > 0.25
    nach_takt = j + L - lage.mal * lage.k_ein
    e_a = float(np.mean(pa.gesamt[i:i + max(1, L // 2)])) if i < pa.n else -30.0
    e_b = float(np.mean(pb.gesamt[nach_takt:nach_takt + PHRASE])) if nach_takt < pb.n else e_a
    steigern, beruhigen = e_b - e_a > 3.0, e_b - e_a < -3.0
    # Abrupt ist nur dort musikalisch, wo B direkt mit seinem Drop uebernimmt (A endet, der Drop
    # schlaegt ein). Sonst hoert der Hoerer nur ein abgeschnittenes A (Uebergangstest: "zu abrupt").
    eb = pb.etiketten()
    b_drop_danach = nach_takt < pb.n and eb[min(len(eb) - 1, pb.phrase_von(nach_takt))] == "drop"
    if lage.harm is not None:   # Tonvorrat im Fenster schlaegt die Tonart des ganzen Songs
        harmonisch = lage.harm >= 0.75 or (harmonisch and lage.harm >= 0.55)
    basis = dict(art="eigen", lautstaerke="nahtlos", eq="profi", filter="keiner", effekt="keiner",
                 effekt_ein="keiner", loop="keiner", loop_start=-1, loop_ein=0, loop_ein_mal=0, trick="keiner",
                 takte=L, weiter_takte=L, tempo_modus="vorlauf" if vorlauf else "rampe")
    # A haelt bis zum Schnitt (Fader und EQ offen), B kommt equipotent, Bass wechselt spaet:
    halten = dict(lautstaerke="hart_aus", eq="bass_ende")          # nur in einen Drop
    ausklingen = dict(lautstaerke="letzter_takt", eq="bass_ende")  # A klingt im letzten Takt mit dem Effekt aus
    kurz8 = dict(takte=min(L, 8), weiter_takte=min(L, 8))
    kandidaten: list[tuple[str, dict, str, float]] = []
    if sync and not vorlauf:   # backen entscheidet am lokalen Tempo der Stelle, nicht am Song-BPM
        from .uebergang import TEMPO_SPIEL, _periode
        sync = abs(240.0 / _periode(pa.takte, i) - 240.0 / _periode(pb.takte, j)) <= max(e.max_bpm, 0.05) + TEMPO_SPIEL
    elif vorlauf:   # wie backen: Tempo an Ausstieg und Einsatz (Runde 19 vorab: 160 -> 174 BPM fiel erst beim Backen durch)
        from .uebergang import _periode
        sync = abs(_periode(pa.takte, i) / _periode(pb.takte, j) - 1.0) <= VORLAUF_MAX
    if lage.drop_k and sync:   # die Lage ist fuer den Double Drop gebaut: nur er passt hier
        # Mit Stems tauscht auch die Stimme auf dem Drop; ohne (oder als Ersatz in backen) die Huellen der Art eigen
        # Runde 9: A's Drop bleibt voll (auch sein Bass), B kommt ohne Bass dazu - beide Drops voll, ein
        # Bass; am Ende der Bass-Switch auf B, dann geht A (mit Effekt: ins Echo)
        # Drop-Cuts aus: 14 Runden 2,2 (4 von 5 Noten <= 2)
        if False and e.experimente == "wild" and (i // PHRASE + j // PHRASE + pa.n + pb.n) % 4 == 1 and \
                _drop_gleich(pa, pb, i + lage.drop_k, j + lage.drop_k):
            return "drop_cuts", {**basis, "trick": "wechsel", "eq": "keiner", "gesang_takt": lage.drop_k}, \
                "Drop-Cuts: beide Drops übereinander, taktweise hin und her, dann B"
        echo = e.experimente == "wild"
        return "double_drop", {**basis, "lautstaerke": "doppel", "eq": "bass_takt", "bass_takt": L - 1,
                               **({"art": "double_drop", "gesang_takt": lage.drop_k} if stems_da else {}),
                               **({"effekt": "echo100_ende_aus"} if echo else {})}, \
            ("Stems: " if stems_da else "") + "Double Drop: beide Drops voll, nur A's Bass, " + \
            ("B's Stimme kommt auf dem Drop, " if stems_da else "") + "Bass-Switch am Ende" + \
            (", A geht ins Echo" if echo else "")
    # Ein Effekt auf A ist nur hoerbar, wenn A dort selbst noch klingt: in einem ausklingenden
    # Outro (viel leiser als B) verschwindet jedes Echo/jeder Hall unter B -> dann ohne Effekt.
    a_ende = float(np.mean(_fenster(pa.gesamt, i + L - 2, 2))) if i + L - 2 < pa.n else -60.0
    b_dort = float(np.mean(_werte(pb.gesamt, bi[-2:])))
    effekt_hoerbar = a_ende >= b_dort - 8.0
    # Mit Loop wiederholt A eine Stelle aus dem Fenster (meist spaet): dann zaehlt deren Pegel, nicht
    # A's Ende. Vorsichtig die zweite Haelfte des Teils, in dem A noch spielt.
    real_a = pa.gesamt[i:min(pa.n, i + L)]
    loop_hoerbar = len(real_a) > 0 and float(np.mean(real_a[len(real_a) // 2:])) >= b_dort - 8.0

    mut = EXPERIMENT_WERT[e.experimente]
    dreh = i // PHRASE + j // PHRASE + pa.n + pb.n   # Abwechslung je Paar (i, j liegen auf Phrasen)

    def kann(name, felder, text, wert=1.0):
        """Kandidat mit Vorzugswert; Effekt nur, wo er hoerbar ist. Experimente: auch normale Blends
        bekommen einen Ausstiegs-Effekt (Runde 9: "fast keinen Effekt gehoert")."""
        dort_hoerbar = loop_hoerbar if felder.get("loop", "keiner") != "keiner" else effekt_hoerbar
        if e.experimente == "wild" and dreh % 2 == 0 and dort_hoerbar and felder.get("art", "eigen") == "eigen" \
                and name not in GESANG_REZEPTE \
                and felder.get("effekt", "keiner") == "keiner" and felder.get("trick", "keiner") == "keiner":
            fx = ("echo100", "pingpong50")[dreh // 2 % 2]
            felder = {**felder, "effekt": f"{fx}_ende_aus",
                      **({"filter": "hp_aus_reso"} if e.experimente == "wild" and felder.get("filter") == "hp_aus" else {})}
            text += {"echo100": ", A geht ins Echo", "pingpong50": ", A geht ins Ping-Pong-Delay"}[fx]
        hoerbar = loop_hoerbar if felder.get("loop", "keiner") != "keiner" else effekt_hoerbar
        if felder.get("effekt", "keiner") != "keiner" and not hoerbar:
            return
        # an dieser Stelle gibt es keinen sauberen Loop (Ausnahme: A endet in der Blende - in der des Rezepts:
        # loop_filter kuerzt auf 8 Takte, Runde 18 vorab: der unsaubere Loop rutschte sonst durch)
        if not (loop_ok or pa.n - i < felder.get("takte", L)) and felder.get("loop", "keiner") != "keiner":
            return
        kandidaten.append((name, {**basis, **felder}, text, wert))

    # Loops: A wiederholt eine saubere Stelle (die Auswahl trifft uebergang.loop_waehlen) oder
    # B's Intro laeuft im Loop, damit sein Gesang erst nach der Blende kommt.
    # WEITER verlaesst A mitten im Song: ein Loop haelt A auf einer sauberen Stelle, statt es
    # mitten in der Phrase abzuschneiden (Uebergangstest: WEITER 1,3, "abrupt", "falsche Stelle").
    loop_wert = {"kurz": 1.9, "ausgewogen": 2.2, "lang": 2.5}[e.modus] + (
        1.0 if a_endet or gesang_kommt or sofort else 0.0)
    if not sync:
        if _brueckenstart(pb, j):   # §5.1: A geht ins Echo, B beginnt ohne Drums - dort hoert man kein Tempo
            kann("bruecke_beatlos", dict(art="echo"),
                 "Tempo zu weit auseinander: A geht ins Echo, B startet in einem Teil ohne Drums", 3.0)
        kann("schnitt", dict(art="schnitt"), "Tempo zu weit auseinander: harter Schnitt auf die 1",
             2.0 if e.modus == "kurz" else 0.5)
        kann("echo_out", dict(art="echo"), "Tempo zu weit auseinander: Echo-Out", 1.0)
    else:
        wild = e.experimente == "wild"
        # wild: auch in B's Hauptteil (ohne Drop danach), dort klingt ein Schnitt mit Trick wie ein Neustart
        voll_danach = nach_takt < pb.n and eb[min(len(eb) - 1, pb.phrase_von(nach_takt))] in ("drop", "haupt")
        # A muss am Ende noch voll spielen, sonst klingt A vor dem Trick schon aus (Runde 8: Loch vor dem Drop)
        a_voll = a_ende >= float(np.percentile(pa.gesamt, 75)) - 6.0
        # B's Drop genau auf der Eins nach der Blende (nicht nur im 8er-Raster der Etiketten)
        _, b_audio, rate = audio or (None, None, 44100)
        drop_genau = b_drop_danach and _drop_takt(pb, nach_takt) == nach_takt and \
            _einsatz(pb, nach_takt) >= DROP_EINSATZ and _drop_ok(pb, nach_takt, b_audio, rate)
        if mut and (drop_genau or (wild and voll_danach and not b_drop_danach)) and a_voll and \
                not a_endet and not lage.k_ein:
            # Drop-Swap wie im DnB: B's Aufbau kommt in den letzten Takten unter A, A endet mit einem Trick,
            # B's Drop schlaegt auf die Eins ein. Wild: B schwillt aus einem Reverse-Reverb an.
            drop = dict(lautstaerke="drop", eq="bass_ende", **({"effekt_ein": "rueckhall"} if wild else {}))
            tricks = (("riser_drop", dict(drop, filter="hp_aus_reso" if wild else "hp_aus", trick="riser"),
                       "Noise-Riser, A dünnt mit " + ("resonantem " if wild else "") + "Hochpass aus"),
                      ("bremse_drop", dict(drop, trick="bremse"), "Tape-Stop auf A"),
                      ("spinback_drop", dict(drop, trick="spinback"), "Backspin auf A"),
                      ("gate_drop", dict(drop, trick="gate"), "A wird zerhackt (Trans)"))
            # Runde 16: Riser 1,33 (3 von 3 <= 2) - "nur bei starkem Drop von B": echter Drop, Pegel +6 dB
            stark = drop_genau and nach_takt >= 2 and                 float(np.mean(pb.gesamt[nach_takt:nach_takt + 2]) - np.mean(pb.gesamt[nach_takt - 2:nach_takt])) >= 6.0
            for k, (name, felder, text) in enumerate(tricks):
                if name == "riser_drop" and not stark:
                    continue
                # Runde 19: Backspin bei Chill 3,0 (n = 7, "passt nicht bei ruhigen Liedern, nur bei UKG, DnB"),
                # bei UKG/DnB 4,0 (n = 29); "nur wenn bei B dann ein Drop kommt"
                if name == "spinback_drop" and (not drop_genau or _chill(a, pa) or _chill(b, pb)):
                    continue
                if name != "teaser_drop" or L >= 4:
                    kann(name, felder, text + ", B's Drop schlägt ein", mut + 0.05 * ((dreh + k) % len(tricks)))
        if mut and not a_endet:   # A bekommt einen Modulations-Effekt und geht ins Echo/Ping-Pong
            fx = ("flanger", "phaser", "crush")[dreh % 3]
            echo = ("echo100", "pingpong50")[dreh // 3 % 2]
            kann("fx_echo", dict(ausklingen, trick=fx, effekt=f"{echo}_ende_aus"),
                 f"A bekommt {dict(flanger='einen Flanger', phaser='einen Phaser', crush='den Bitcrusher')[fx]} "
                 f"und geht ins {'Echo' if echo == 'echo100' else 'Ping-Pong-Delay'}", mut - 1.5)
        ueb = _gesang_uebergabe(pa, pb, i, bi) if stems_da and not lage.k_ein else None
        if ueb is not None and harmonisch:   # eine Stimme ueber fremder Musik braucht passende Toene
            kann(ueb[0], dict(art=ueb[0], gesang_takt=ueb[1]),
                 f"Stems: A's Musik geht, A singt {ueb[2]} Takte über B weiter" if ueb[0] == "acapella" else
                 f"Stems: B's Gesang {ueb[2]} Takte über A's Musik, B's Musik erst danach", 4.0)
        if lage.k_ein and harmonisch:   # beissende Toene nicht lange uebereinander loopen
            lang_loop = lage.k_ein * (lage.mal + 1) >= 8
            # Tiefpass nur mit Bass-Tausch, nie mit dem EQ-Swap (Runde 17, Faelle 14/30: der Swap laesst B anfangs
            # nur Hoehen, der Tiefpass nahm genau die weg - B 16 Takte stumm, A ohne Hoehen "allein mit Tiefpass")
            kann("intro_loop_b", dict(loop_ein=lage.k_ein, loop_ein_mal=lage.mal,
                                      **({"filter": "tp_ein", "eq": "bass_mitte"} if lang_loop else {}),
                                      **({"loop": "auto"} if a_endet else {})),
                 "B's Intro im Loop" + (", öffnet sich mit dem Tiefpass" if lang_loop else "")
                 + ", damit Gesang/Drop erst nach der Blende kommen", 3.0)
        if a_break and not singt_b and not a_endet and not sofort:
            # B laeuft mit seinen Drums unter A's Break ein, A blendet ueber die ganze Blende aus
            # (frueher: A in der ersten Viertel weg -> im Test 10 von 10 Mal "zu abrupt").
            kann("breakdown", dict(eq="bass_mitte"), "B übernimmt im Break von A", 0.3)   # 14 Runden: 1,93
        # Loop von A braucht Drums; endet A in der Blende, ist er Pflicht. Loopt B's Intro, loopt A nicht
        # (Runde 5: A- und B-Loop zugleich 2,27, "zu viel auf einmal"; intro_loop_b loopt A nur, wenn A endet)
        if (not a_break or a_endet) and not lage.k_ein:
            kann("outro_loop", dict(loop="auto"),
                 "A's Outro im Loop verlängert" if a_endet else
                 "A's Gesang käme noch: sauberer Takt im Loop" if gesang_kommt else
                 "WEITER: A loopt eine saubere Stelle, B übernimmt darunter" if sofort else
                 "A loopt eine saubere Stelle, B übernimmt darunter", loop_wert)
            kann("loop_echo", dict(ausklingen, loop="auto", effekt="echo50_ende_aus"),
                 "A loopt, am Ende geht A ins Echo", loop_wert - 0.3)
            if L >= 16:   # ein langer Loop allein wird eintoenig: A wird duenner und geht ins Echo
                kann("loop_fx", dict(lautstaerke="letzter_takt", eq="bass_mitte", filter="hp_aus", loop="auto",
                                     effekt="echo100_ende_aus"),
                     "A loopt, wird mit dem Hochpass dünner und geht am Ende ins Echo", loop_wert + 0.2)
            if not harmonisch:
                # A blendet ueber die ganze Blende aus, waehrend der Hochpass schliesst (hart: "endet zu abrupt")
                # Toene beissen sich: nicht lange ueberlappen (Runde 3: loop_filter 2,75, "Tonarten beissen sich")
                kann("loop_filter", dict(kurz8, lautstaerke="nahtlos", eq="bass_mitte", filter="hp_aus", loop="auto"),
                     "Tonarten passen nicht: A loopt und dünnt mit Hochpass aus", loop_wert + 0.3)
        if e.modus == "kurz":
            # Schnitt in der Mitte nur, wenn B dort nicht viel leiser ist (Runde 10 vorab: 11 dB Loch nach dem Schnitt)
            b_mitte = float(np.mean(_werte(pb.gesamt, bi[L // 2:L // 2 + 2])))
            a_mitte = float(np.mean(_fenster(pa.gesamt, i + L // 2 - 2, 2)))
            if singt_a and singt_b and b_mitte >= a_mitte - 6.0:
                kann("schnitt_echo", dict(lautstaerke="mitte_weich" if sofort else "mitte", eq="keiner",
                                          effekt="echo50_mitte_aus"),
                     "beide singen: Schnitt in der Mitte, A geht ins Echo", 3.0)
            if b_drop_danach:   # kurz und knapp wie im DnB: A geht ins Echo, B's Drop schlaegt ein
                kann("echo_drop", dict(halten, effekt="echo100_ende_aus"), "A geht ins Echo, B's Drop übernimmt", 3.0)
            if e.spielanteil == "schnell" and b_drop_danach and harmonisch:
                # Rolle = Aufbau in einen Drop; ohne Drop dahinter oder mit beissender Tonart klang sie
                # im Test wie ein Unfall (1,3)
                kann("rolle", dict(halten, loop="rolle"), "Loop-Rolle in B's Drop", 0.3)   # 14 Runden: 1,33
                kann("delay_out", dict(halten, effekt="delay50_ende_aus"), "kurzer Blend, A geht ins Delay", 2.0)
            kann("kurz_eq", {} if harmonisch else dict(lautstaerke="hart_aus", eq="bass_mitte", filter="hp_aus"),
                 "kurzer Profi-Blend" if harmonisch else "Tonarten passen nicht: A dünnt mit Hochpass aus", 1.0)
        if e.modus == "ausgewogen":
            if stems_da and singt_a and singt_b:
                kann("gesangsschutz", dict(art="gesangsschutz"), "beide singen: Stimmen nacheinander (Stems)", 3.0)
            if not harmonisch:
                kann("filter_blend", dict(kurz8, lautstaerke="hart_aus", eq="bass_mitte", filter="hp_aus"),
                     "Tonarten passen nicht: kurzer Blend, A dünnt mit Hochpass aus", 1.5)
            if stems_da and harmonisch and not lage.k_ein:   # Stem-Arten loopen B's Intro nicht (Lage waere dafuer gebaut)
                kann("drums_zuerst", dict(art="drums_zuerst"), "Drums von B zuerst, dann Bass und Rest (Stems)", 2.0)
                kann("melodie_zuerst", dict(art="melodie_zuerst"),
                     "Stems: B's Melodie zuerst über A's Groove, dann Drums und Bass, B's Gesang zuletzt", 3.4)
            if beruhigen:
                kann("tiefpass_aus", dict(lautstaerke="hart_aus", eq="bass_mitte", filter="tp_aus"),
                     "B ruhiger: A wird mit Tiefpass dunkel", 2.0)
            if e.spielanteil == "schnell":
                kann("echo_out_blend", {**kurz8, **ausklingen, "effekt": "echo50_ende_aus"},
                     "Blend, am Ende geht A ins Echo", 2.0)
            kann("profi_eq", {}, "Profi-Blend: Höhen → Mitten → Bass-Tausch", 1.0)
        if e.modus == "lang":
            if stems_da and singt_a and singt_b:
                kann("gesangsschutz", dict(art="gesangsschutz"), "beide singen: Stimmen nacheinander (Stems)", 3.0)
            if not harmonisch:
                kann("hochpass_hall", dict(lautstaerke="letzter_takt", eq="bass_mitte", filter="hp_aus",
                                           effekt="hall_ende_aus"),
                     "Tonarten passen nicht: A dünnt mit Hochpass aus und geht in den Hall", 2.5)
            if beruhigen:
                kann("relaxed", dict(lautstaerke="letzter_takt", eq="bass_mitte", filter="tp_aus", effekt="hall_ende_aus"),
                     "B ruhiger: A wird dunkel und klingt im Hall aus", 2.5)
            if stems_da and harmonisch and not lage.k_ein:   # Stem-Arten loopen B's Intro nicht (Lage waere dafuer gebaut)
                kann("drums_zuerst", dict(art="drums_zuerst"), "Drums von B zuerst, dann Bass und Rest (Stems)", 2.0)
                kann("melodie_zuerst", dict(art="melodie_zuerst"),
                     "Stems: B's Melodie zuerst über A's Groove, dann Drums und Bass, B's Gesang zuletzt", 3.4)
            kann("profi_eq", {}, "langer Profi-Blend: Höhen → Mitten → Bass-Tausch", 1.0)
    if a_endet:   # A klingt in der Blende aus: ohne Loop bliebe ein Loch
        mit_loop = [k for k in kandidaten if k[1].get("loop", "keiner") != "keiner" or k[0] in GESANG_REZEPTE]
        kandidaten = mit_loop or kandidaten
    if not kandidaten:
        kann("profi_eq", {}, "Profi-Blend")
    # Abwechslung: nach einem Loop-Rezept kommt bevorzugt ein anderes (sonst loopt jeder Uebergang)
    nach_loop = vorher in LOOP_REZEPTE
    kandidaten.sort(key=lambda k: -(k[3] - (1.5 if nach_loop and k[0] in LOOP_REZEPTE else 0.0)
                                    + REZEPT_GEWICHT * (REZEPT_NOTE.get(k[0], REZEPT_MITTEL) - REZEPT_MITTEL)))   # stabil
    vorlieben = vorlieben or {}
    # Abwechslung: nicht zweimal dasselbe; Gelerntes: was du oft abbrichst, nur wenn nichts anderes geht
    for name, felder, text, _ in kandidaten:
        if name != vorher and vorlieben.get(name, 0.0) > -2.0:
            return name, felder, text
    for name, felder, text, _ in kandidaten:
        if name != vorher:
            return name, felder, text
    return kandidaten[0][:3]


# Mittlere Note je Rezept aus 19 Hoerrunden (662 Noten, zum Mittel 3,27 hin geschrumpft: +10 Pseudo-Noten).
# shortcut: fester Stand 18.10.2026 (Scratchpad rezept_note.py); neu ausrechnen, wenn weitere Runden bewertet sind
REZEPT_MITTEL = 3.27
REZEPT_NOTE = {"acapella": 3.53, "breakdown": 2.49, "bremse_drop": 3.2, "bruecke_beatlos": 3.24, "double_drop": 3.14,
               "drop_cuts": 2.91, "drums_zuerst": 3.12, "echo_drop": 3.28, "echo_out": 3.15, "echo_out_blend": 3.24,
               "filter_blend": 3.22, "fx_echo": 3.35, "gate_drop": 3.21, "gesang_zuerst": 3.65, "gesangsschutz": 3.49,
               "hochpass_hall": 2.91, "intro_loop_b": 3.34, "kurz_eq": 3.14, "loop_filter": 3.19, "loop_fx": 3.17,
               "melodie_zuerst": 3.42, "outro_loop": 3.31, "riser_drop": 2.92, "rolle": 2.82, "schnitt": 2.97,
               "schnitt_echo": 3.14, "spinback_drop": 3.71, "teaser_drop": 3.14}
REZEPT_GEWICHT = 2.0   # je Notenpunkt ueber/unter dem Mittel (profi_eq fehlt: seine Noten sind meist Sicherheits-Blends)


def _bass_takt(pa: Profil, pb: Profil, i: int, bi: np.ndarray, L: int) -> int:
    """Takt des Bass-Tauschs: wo B's Bassline einsetzt, sonst wo A's Bass am schwaechsten ist,
    sonst bei drei Vierteln. Nur auf Taktgruppen (4er, bei kurzen Blenden 2er) in der zweiten Haelfte:
    der EQ-Swap tauscht vorher Hoehen und Mitten, der Bass kommt zuletzt."""
    raster = 4 if L >= 16 else 2 if L >= 4 else 1
    erlaubt = [k for k in range(raster, L, raster) if L / 2 <= k <= 3 * L / 4] or [max(1, L // 2)]
    bb = _werte(pb.bass(), bi[:L])
    for k in erlaubt:
        if bb[k] > 0.5 and bb[k - 1] < 0.5:
            return k
    ba = _fenster(pa.stems["bass"] if pa.stems else pa.baender[:, 0], i, L)
    if np.ptp(ba[erlaubt]) > 6.0:
        return int(erlaubt[int(np.argmin(ba[erlaubt]))])
    return erlaubt[-1]


LOOP_GUETE_MIN = 0.7   # darunter faellt die Wiederholung auf: kein A-Loop an dieser Stelle


def _loop_guete(pa: Profil, i: int, L: int, a_audio: np.ndarray, rate: int) -> float:
    """Wie sauber laesst sich A im Fenster ab Takt i loopen? Dieselbe Wahl wie beim Backen (meidet Gesang).
    Endet A vorher, zaehlt nur der Rest."""
    from .uebergang import loop_im_original

    ga = pa.gesang()
    return float(loop_im_original(a_audio, pa.takte, i, L, _fenster(ga, i, L) > 0 if ga is not None else None,
                                  rate)[2])


def planen(a, pa: Profil, b, pb: Profil, e: Einstellungen, ab_s: float, sync: bool, harmonisch: bool,
           sofort: bool = False, stems_da: bool = False, vorher: str | None = None,
           anzahl: int = 3, vorlieben: dict[str, float] | None = None,
           a_audio: np.ndarray | None = None, rate: int = 44100,
           b_audio: np.ndarray | None = None, kritiker=None) -> list[Plan]:
    """Die besten `anzahl` Plaene fuer A -> B (verschiedene Ausstiege/Einsaetze).

    Mit `a_audio` (A roh, `rate`) wird fuer Loop-Rezepte vorab geprueft, ob an der Stelle ein
    sauberer Loop existiert; sonst waehlt die Regie dort ein Rezept ohne A-Loop. Endet A in der
    Blende und sein Rest laesst sich nicht sauber loopen, kommt der Ausstieg erst nach den anderen.
    Mit `b_audio` werden Drops auf den Schlag genau geprueft (§3.1). Mit `kritiker` (kritiker.Kritiker) werden
    bis zu ANZAHL_INTERN Plaene nach Regie-Rang und geschaetzter Note neu sortiert (§2.3).
    Liegen die Tempi bis VORLAUF_MAX auseinander, gleitet A vor der Blende auf B's Tempo (§5.2): die Regie
    plant dann wie mit Angleich, nur VORLAUF_TAKTE spaeter."""
    ab_takt = int(np.searchsorted(pa.takte, ab_s - 1e-3))
    from .uebergang import _periode
    vorlauf = (not sync and not sofort and e.keylock and e.max_bpm > 0 and pa.n > 1 and pb.n > 1
               and abs(_periode(pb.takte, 0) / _periode(pa.takte, ab_takt) - 1.0) <= VORLAUF_MAX)
    if vorlauf:
        sync, ab_takt = True, ab_takt + VORLAUF_TAKTE
    audio = (a_audio, b_audio, rate)
    lagen = _rangliste(pa, pb, e, ab_takt, sofort, stems_da, harmonisch, sync, audio, a, b)
    plaene, gesehen, zurueck = [], set(), []

    def plan_aus(lage: _Lage, loop_ok: bool = True) -> Plan:
        name, felder, text = _rezept(lage, pa, pb, e, sync, harmonisch, stems_da, vorher, vorlieben, loop_ok, sofort,
                                     audio, a, b, vorlauf)
        if felder["eq"] != "bass_takt":   # Double Drop: der Bass tauscht auf dem Drop
            felder["bass_takt"] = _bass_takt(pa, pb, lage.i, _b_index(lage.j, felder["takte"], lage.k_ein, lage.mal),
                                             felder["takte"])
        aus_s = float(pa.takte[lage.i]) if lage.i < pa.n else float(pa.takte[-1])
        stichworte = ", ".join(dict.fromkeys(lage.teile))
        return Plan(aus_s, float(pb.takte[lage.j]), felder["takte"], replace(e, **felder), name,
                    text + (f" · {stichworte}" if stichworte else ""), lage.punkte)

    for lage in lagen:
        if (lage.i, lage.j) in gesehen:
            continue
        gesehen.add((lage.i, lage.j))
        plan = plan_aus(lage)
        if (a_audio is not None and plan.einst.loop == "auto"
                and _loop_guete(pa, lage.i, plan.takte, a_audio, rate) < LOOP_GUETE_MIN):
            if pa.n - lage.i >= plan.takte:   # A endet nicht in der Blende: Rezept ohne A-Loop
                plan = plan_aus(lage, loop_ok=False)
            # A endet in der (neuen) Blende: nur mit diesem (schlechten) Loop moeglich, nur zur Not
            if plan.einst.loop == "auto" and _loop_guete(pa, lage.i, plan.takte, a_audio, rate) < LOOP_GUETE_MIN:
                zurueck.append(plan)
                continue
        plaene.append(plan)
        if len(plaene) >= (max(anzahl, ANZAHL_INTERN) if kritiker is not None else anzahl):
            break
    if kritiker is not None and plaene:
        noten = [kritiker.vorher(plan_merkmale(p, pa, pb, e, sync, sofort, stems_da, a, b)) for p in plaene]
        wert = [1.0 - k / max(1, len(plaene) - 1) + KRITIK_GEWICHT * (noten[k] - 3.0) for k in range(len(plaene))]
        plaene = [replace(plaene[k], grund=f"{plaene[k].grund} · Kritiker: {noten[k]:.1f}")
                  for k in sorted(range(len(plaene)), key=lambda k: -wert[k])]
    return (plaene + zurueck)[:anzahl] if plaene else zurueck[:anzahl]


def plan_merkmale(plan: Plan, pa: Profil, pb: Profil, e: Einstellungen, sync: bool, sofort: bool, stems_da: bool,
                  a=None, b=None) -> dict:
    """Merkmale eines Plans fuer den Kritiker - dieselben wie im Datensatz der benoteten Uebergaenge."""
    from .datensatz import merkmale
    from .uebergang import STEM_ARTEN, _periode

    i, j = pa.takt_bei(plan.aus_s), pb.takt_bei(plan.ein_s)
    return merkmale(pa, pb, i, j, plan.takte, plan.rezept, stems=stems_da and plan.einst.art in STEM_ARTEN,
                    sync=sync, experimente=e.experimente, stil=e.modus, spielanteil=e.spielanteil, weiter=sofort,
                    bpm_a=240.0 / _periode(pa.takte, i), bpm_b=240.0 / _periode(pb.takte, j),
                    camelot_a=getattr(a, "camelot", None), camelot_b=getattr(b, "camelot", None),
                    k_ein=plan.einst.loop_ein, mal=plan.einst.loop_ein_mal)


def _pegel_soll(blende: np.ndarray, rate: int, n_takte: int, pa: Profil, pb: Profil, aus_s: float,
                ein_s: float, gain_a: float, gain_b: float, rezept: str):
    """Je Takt der Blende (Ist-Pegel, Obergrenze, Untergrenze) in dB, oder None, wenn das Rezept nicht
    geprueft wird. Obergrenze: der lautere Song an derselben Stelle +3,5 dB; Untergrenze: die ideale
    Blende (Leistung gleitet von A nach B) -9 dB, nicht im ersten/letzten Takt."""
    if n_takte < 2 or rezept in ("schnitt", "echo_out", "schnitt_echo", "echo_drop", "intro_loop_b", "double_drop",
                                 "drop_cuts")\
            or rezept in DROP_TRICKS:
        return None
    takt_s = len(blende) / rate / n_takte
    mono = blende.mean(axis=1) if blende.ndim > 1 else blende
    ist, oben, unten = np.zeros(n_takte), np.zeros(n_takte), np.full(n_takte, -np.inf)
    for k in range(n_takte):
        teil = mono[int(k * takt_s * rate):int((k + 1) * takt_s * rate)]
        ist[k] = 10 * np.log10(np.mean(teil.astype(np.float64) ** 2) + 1e-10)
        # Mit Loop wiederholt A seinen Anfang: dessen Pegel ist der Vergleich
        ia = pa.takt_bei(aus_s + (0 if "loop" in rezept or rezept == "rolle" else k * takt_s))
        jb = pb.takt_bei(ein_s + k * takt_s)
        la, lb = pa.gesamt[ia] + gain_a, pb.gesamt[jb] + gain_b
        oben[k] = max(la, lb) + 3.5
        x = (k + 0.5) / n_takte
        # gesang_zuerst: bis zur Uebergabe traegt A allein (B nur mit Gesang) - kein Loch
        if k not in (0, n_takte - 1) and rezept != "gesang_zuerst":
            unten[k] = 10 * np.log10((1 - x) * 10 ** (la / 10) + x * 10 ** (lb / 10)) - 9.0
    return ist, oben, unten


def pruefen(blende: np.ndarray, rate: int, n_takte: int, pa: Profil, pb: Profil, aus_s: float,
            ein_s: float, gain_a: float, gain_b: float, rezept: str) -> str | None:
    """Selbstkontrolle des fertigen Uebergangs: Lautstaerke-Buckel oder -Loch gegenueber den
    beiden Songs an derselben Stelle. Gibt eine Begruendung zurueck, wenn er durchfaellt."""
    werte = _pegel_soll(blende, rate, n_takte, pa, pb, aus_s, ein_s, gain_a, gain_b, rezept)
    if werte is None:
        return None
    for k, (ist, oben, unten) in enumerate(zip(*werte)):
        if ist > oben:
            return f"zu laut in Takt {k + 1} (+{ist - oben + 3.5:.1f} dB)"
        if ist < unten:
            return f"Loch in Takt {k + 1} ({ist - unten - 9.0:.1f} dB)"
    return None


REPARATUR_MAX_DB = 6.0   # ein Loch wird hoechstens um 6 dB angehoben (tiefer: Plan verwerfen)


def pegel_reparieren(blende: np.ndarray, rate: int, n_takte: int, pa: Profil, pb: Profil, aus_s: float,
                     ein_s: float, gain_a: float, gain_b: float, rezept: str) -> bool:
    """Statt einen Plan wegen Buckel/Loch zu verwerfen (Runde 14: zu viele Sicherheits-Blends): den
    Pegel je Takt in die Grenzen ziehen (1 dB Abstand), weich ueber die Taktmitten, an Anfang und Ende
    der Blende unveraendert (kein Sprung zu A davor / B danach). Aendert `blende` in place."""
    werte = _pegel_soll(blende, rate, n_takte, pa, pb, aus_s, ein_s, gain_a, gain_b, rezept)
    if werte is None:
        return False
    ist, oben, unten = werte
    g_db = np.clip(np.minimum(0.0, oben - 1.0 - ist) + np.maximum(0.0, unten + 1.0 - ist), -12.0, REPARATUR_MAX_DB)
    if not np.any(np.abs(g_db) > 0.05):
        return False
    from .uebergang import _begrenzen

    n = len(blende)
    mitte = (np.arange(n_takte) + 0.5) * n / n_takte
    g = 10 ** (np.interp(np.arange(n), np.concatenate([[0], mitte, [n]]), np.concatenate([[0], g_db, [0]])) / 20)
    blende *= g[:, None].astype(blende.dtype) if blende.ndim > 1 else g.astype(blende.dtype)
    if blende.ndim > 1:
        _begrenzen(blende, n)
    return True
