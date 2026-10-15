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

import numpy as np

from .einstellungen import Einstellungen
from .profil import PHRASE, Profil

# Blendenlaenge als Zeit, nicht als feste Taktzahl: 16 Takte sind bei 174 BPM (DnB) 22 s, bei
# 120 BPM 32 s. Profis: House/Techno 16-32 Takte (30-60 s), DnB 8-16 (11-22 s), Hip-Hop kurz.
# Uebergangstest 14.10.2026 (46 Noten): 4 Takte (8 s) 1,4 · 8 Takte 2,3 · 16 Takte 3,9.
DAUER_S = {"kurz": (14.0, 32.0), "ausgewogen": (28.0, 64.0), "lang": (45.0, 66.0)}
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
        for k, takt in enumerate(range(start, min(pa.n, start + 3 * PHRASE), PHRASE)):
            aus.append((takt, 3.0 - 1.5 * k, "zweite Hälfte nach dem Drop"))
        if drops and start > drops[0] + PHRASE:   # Ausweg, wenn A nach seinem Drop zu kurz fuer die Blende ist
            aus.append((drops[0] + PHRASE, -1.5, "zweite Hälfte nach dem Drop"))
    else:
        # So lange wie moeglich: Kandidaten im letzten Drittel, spaeter = besser.
        start = pa.phrase_start(pa.phrase_von(int(pa.n * 0.7)))
        for takt in range(start, pa.n, PHRASE):
            aus.append((takt, 6.0 * takt / max(1, pa.n), "spielt lang"))
        ga = pa.gesang() if stems_da else None
        if ga is not None:   # A's letzte Gesangsteile: von dort kann A's Stimme lange ueber B weiterlaufen
            for takt in range(pa.phrase_start(pa.phrase_von(pa.n // 2)), start, PHRASE):
                if ga[takt:takt + PHRASE].any():
                    aus.append((takt, 6.0 * takt / max(1, pa.n), FRUEH_GESANG))
    return [(t, p, g) for t, p, g in aus if t >= ab_takt] or [(pa.phrase_ab(ab_takt), -2.0, "")]


def _b_kandidaten(pb: Profil, e: Einstellungen, laengen) -> list[tuple[int, float]]:
    """(Takt, Punkte) fuer den Einsatz von B: Phrasenanfaenge in den ersten ~40 %."""
    et = pb.etiketten()
    aus = []
    # Songanfang und B's Phrasengrenzen (mit Versatz): nie mitten in B's Phrase einsteigen
    for takt in dict.fromkeys([0] + list(range(pb.phrase_start(1), int(pb.n * 0.4) + 1, PHRASE))):
        if e.spielanteil == "schnell":
            p = 0.0    # Intro ueberspringen ist erlaubt
        else:
            p = -0.8 * takt / PHRASE    # moeglichst von vorn
        if et[pb.phrase_von(takt)] == "break":
            p -= 1.0
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
        if zeile_endet and allein >= 2 and not b[:g + 5].any():   # B singt erst, wenn A's Echo verklungen ist
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
        p -= 12.0 * clash
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
    """Drop-Takt auf den Takt genau: `takt` liegt auf dem versetzten Phrasenraster (Profil.versatz); bis
    +-2 Takte daneben, wenn Bass, Drums und Pegel dort deutlich staerker einsetzen (je 2 Takte)."""
    reihen = [p.gesamt] + ([p.stems["bass"], p.stems["drums"]] if p.stems else [p.baender[:, 0]])

    def sprung(k: int) -> float:
        if k < 2 or k + 2 > p.n:
            return -np.inf
        return float(sum(np.mean(x[k:k + 2]) - np.mean(x[k - 2:k]) for x in reihen))

    best = max(range(takt - 2, takt + 3), key=sprung)
    return best if sprung(best) > 1.5 * max(sprung(takt), 1.0) else takt


def _double_drops(pa: Profil, pb: Profil, e: Einstellungen, ab_takt: int, stems_da: bool = False) -> list[_Lage]:
    """Double Drop (DnB, Andy C): A's und B's Drop fallen auf denselben Takt. B laeuft eine Phrase vorher
    ohne Bass mit ein, am Drop tauscht der Bass (nie zwei Baesse), beide Drops laufen D Takte zusammen,
    dann geht A. Nur mit passenden Toenen; ohne Stems auch nur ohne zwei Stimmen im Drop (mit Stems tauscht
    die Stimme mit dem Bass). Punkte: relativ (_rangliste)."""
    ea, eb = pa.etiketten(), pb.etiketten()
    a_drops = [_drop_takt(pa, pa.phrase_start(q)) for q, x in enumerate(ea)
               if x == "drop" and pa.phrase_start(q) >= max(ab_takt + PHRASE, pa.n // 2)]
    b_drops = [_drop_takt(pb, pb.phrase_start(q)) for q, x in enumerate(eb) if x == "drop" and q >= 1][:2]
    ga, gb = pa.gesang(), pb.gesang()
    aus = []
    for d_a in a_drops:
        for d_b in b_drops:
            for dauer in (8, 16):
                i, j, L = d_a - PHRASE, d_b - PHRASE, PHRASE + dauer
                if i < ab_takt or j < 0 or pa.n - i < L or j + L > pb.n:
                    continue
                bi = _b_index(j, L)
                harm = _harmonie(pa, pb, i, bi)
                if harm is not None and harm < 0.8:
                    continue   # zwei volle Drops uebereinander: die Toene muessen gut passen (Runde 9: "beissen sich")
                if not stems_da and ga is not None and gb is not None and \
                        (_fenster(ga, d_a, dauer) * _werte(gb, bi[PHRASE:])).any():
                    continue   # zwei Stimmen im Drop
                # lieber 16 Takte: A's Drop soll lange voll laufen (Runde 9: "Drop von A laenger hoeren")
                p = 2.0 * (harm - 0.85 if harm is not None else 0.0) + 1.0 * d_a / pa.n + (0.3 if dauer == 16 else 0.0)
                aus.append(_Lage(i, j, L, p, ["Double Drop: beide Drops auf denselben Takt"], harm=harm, drop_k=PHRASE))
    return aus


def _rangliste(pa: Profil, pb: Profil, e: Einstellungen, ab_takt: int, sofort: bool,
               stems_da: bool = False, tonart_ok: bool = False) -> list[_Lage]:
    stufen = laengen(e.modus, _takt_s(pa), sofort)
    # Gesangs-Uebergaben: Laenge nach dem Gesang, nicht nach dem Stil (auch viel laenger)
    extra = () if not stems_da else tuple(
        L for L in GESANG_LAENGEN if L not in stufen and L * _takt_s(pa) <= GESANG_MAX_S
        and (not sofort or L <= WEITER_GESANG_MAX))
    lagen = []
    drop_bonus = 0.0 if sofort else EXPERIMENT_DROP[e.experimente]
    for i, p_a, g_a in _a_kandidaten(pa, ab_takt, e, sofort, stems_da):
        for j, p_b in _b_kandidaten(pb, e, stufen):
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
                    if (L in extra or g_a == FRUEH_GESANG) and not set(teile) & set(GESANG_TEILE):
                        continue   # Toene passen nicht: keine Ueberlaenge; frueher Ausstieg nur fuer A's Stimme
                    if k_ein and harm is not None and harm < 0.65:
                        continue   # beissende Toene nicht lange uebereinander loopen
                    if "B's Drop direkt nach der Blende" in teile:   # Experimente: Drop-Tricks brauchen den Drop
                        p += drop_bonus
                    lagen.append(_Lage(i, j, L, p + p_a + p_b, ([g_a] if g_a else []) + teile, k_ein, mal, harm))
    lagen.sort(key=lambda x: -x.punkte)
    if e.experimente != "klassisch" and not sofort and lagen:
        # Double Drops gegen die beste normale Lage: "wild" vorn, "kreativ" nur mit sehr passenden Toenen
        vorn = lagen[0].punkte + (1.0 if e.experimente == "wild" else -1.0)
        dd = [replace(x, punkte=vorn + x.punkte) for x in _double_drops(pa, pb, e, ab_takt, stems_da)]
        lagen = sorted(lagen + dd, key=lambda x: -x.punkte)
    return lagen


def _rezept(lage: _Lage, pa: Profil, pb: Profil, e: Einstellungen, sync: bool, harmonisch: bool,
            stems_da: bool, vorher: str | None, vorlieben: dict[str, float] | None = None,
            loop_ok: bool = True, sofort: bool = False) -> tuple[str, dict, str]:
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
                 takte=L, weiter_takte=L, tempo_modus="rampe")
    # A haelt bis zum Schnitt (Fader und EQ offen), B kommt equipotent, Bass wechselt spaet:
    halten = dict(lautstaerke="hart_aus", eq="bass_ende")          # nur in einen Drop
    ausklingen = dict(lautstaerke="letzter_takt", eq="bass_ende")  # A klingt im letzten Takt mit dem Effekt aus
    kurz8 = dict(takte=min(L, 8), weiter_takte=min(L, 8))
    kandidaten: list[tuple[str, dict, str, float]] = []
    if sync:   # backen entscheidet am lokalen Tempo der Stelle, nicht am Song-BPM
        from .uebergang import _periode
        sync = abs(240.0 / _periode(pa.takte, i) - 240.0 / _periode(pb.takte, j)) <= max(e.max_bpm, 0.05)
    if lage.drop_k and sync:   # die Lage ist fuer den Double Drop gebaut: nur er passt hier
        # Mit Stems tauscht auch die Stimme auf dem Drop; ohne (oder als Ersatz in backen) die Huellen der Art eigen
        # Runde 9: A's Drop bleibt voll (auch sein Bass), B kommt ohne Bass dazu - beide Drops voll, ein
        # Bass; am Ende der Bass-Switch auf B, dann geht A (mit Effekt: ins Echo)
        if e.experimente == "wild" and (i // PHRASE + j // PHRASE + pa.n + pb.n) % 2:
            return "drop_cuts", {**basis, "trick": "wechsel", "eq": "keiner", "gesang_takt": lage.drop_k}, \
                "Drop-Cuts: beide Drops übereinander, taktweise hin und her, dann B"
        echo = e.experimente == "wild"
        return "double_drop", {**basis, "lautstaerke": "doppel", "eq": "bass_takt", "bass_takt": L - 1,
                               **({"art": "double_drop", "gesang_takt": lage.drop_k} if stems_da else {}),
                               **({"effekt": "echo75_ende_aus"} if echo else {})}, \
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
        if mut and dort_hoerbar and felder.get("art", "eigen") == "eigen" and name not in GESANG_REZEPTE \
                and felder.get("effekt", "keiner") == "keiner" and felder.get("trick", "keiner") == "keiner":
            fx = ("echo75", "pingpong75", "hall")[dreh % 3]
            felder = {**felder, "effekt": f"{fx}_ende_aus",
                      **({"filter": "hp_aus_reso"} if e.experimente == "wild" and felder.get("filter") == "hp_aus" else {})}
            text += {"echo75": ", A geht ins Echo", "pingpong75": ", A geht ins Ping-Pong-Delay",
                     "hall": ", A geht in den Hall"}[fx]
        hoerbar = loop_hoerbar if felder.get("loop", "keiner") != "keiner" else effekt_hoerbar
        if felder.get("effekt", "keiner") != "keiner" and not hoerbar:
            return
        if not (loop_ok or a_endet) and felder.get("loop", "keiner") != "keiner":
            return   # an dieser Stelle gibt es keinen sauberen Loop (Ausnahme: A endet in der Blende)
        kandidaten.append((name, {**basis, **felder}, text, wert))

    # Loops: A wiederholt eine saubere Stelle (die Auswahl trifft uebergang.loop_waehlen) oder
    # B's Intro laeuft im Loop, damit sein Gesang erst nach der Blende kommt.
    # WEITER verlaesst A mitten im Song: ein Loop haelt A auf einer sauberen Stelle, statt es
    # mitten in der Phrase abzuschneiden (Uebergangstest: WEITER 1,3, "abrupt", "falsche Stelle").
    loop_wert = {"kurz": 1.9, "ausgewogen": 2.2, "lang": 2.5}[e.modus] + (
        1.0 if a_endet or gesang_kommt or sofort else 0.0)
    if not sync:
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
        drop_genau = b_drop_danach and _drop_takt(pb, nach_takt) == nach_takt
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
            for k, (name, felder, text) in enumerate(tricks):
                if name != "teaser_drop" or L >= 4:
                    kann(name, felder, text + ", B's Drop schlägt ein", mut + 0.05 * ((dreh + k) % len(tricks)))
        if mut and not a_endet:   # A bekommt einen Modulations-Effekt und geht ins Echo/Ping-Pong
            fx = ("flanger", "phaser", "crush")[dreh % 3]
            echo = ("echo75", "pingpong75")[dreh // 3 % 2]
            kann("fx_echo", dict(ausklingen, trick=fx, effekt=f"{echo}_ende_aus"),
                 f"A bekommt {dict(flanger='einen Flanger', phaser='einen Phaser', crush='den Bitcrusher')[fx]} "
                 f"und geht ins {'Echo' if echo == 'echo75' else 'Ping-Pong-Delay'}", mut - 0.6)
        ueb = _gesang_uebergabe(pa, pb, i, bi) if stems_da and not lage.k_ein else None
        if ueb is not None and harmonisch:   # eine Stimme ueber fremder Musik braucht passende Toene
            kann(ueb[0], dict(art=ueb[0], gesang_takt=ueb[1]),
                 f"Stems: A's Musik geht, A singt {ueb[2]} Takte über B weiter" if ueb[0] == "acapella" else
                 f"Stems: B's Gesang {ueb[2]} Takte über A's Musik, B's Musik erst danach", 4.0)
        if lage.k_ein and harmonisch:   # beissende Toene nicht lange uebereinander loopen
            lang_loop = lage.k_ein * (lage.mal + 1) >= 8
            kann("intro_loop_b", dict(loop_ein=lage.k_ein, loop_ein_mal=lage.mal,
                                      **({"filter": "tp_ein"} if lang_loop else {}),
                                      **({"loop": "auto"} if a_endet else {})),
                 "B's Intro im Loop" + (", öffnet sich mit dem Tiefpass" if lang_loop else "")
                 + ", damit Gesang/Drop erst nach der Blende kommen", 3.0)
        if a_break and not singt_b and not a_endet and not sofort:
            # B laeuft mit seinen Drums unter A's Break ein, A blendet ueber die ganze Blende aus
            # (frueher: A in der ersten Viertel weg -> im Test 10 von 10 Mal "zu abrupt").
            kann("breakdown", dict(eq="bass_mitte"), "B übernimmt im Break von A", 2.0)
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
                                     effekt="echo75_ende_aus"),
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
                kann("echo_drop", dict(halten, effekt="echo75_ende_aus"), "A geht ins Echo, B's Drop übernimmt", 3.0)
            if e.spielanteil == "schnell" and b_drop_danach and harmonisch:
                # Rolle = Aufbau in einen Drop; ohne Drop dahinter oder mit beissender Tonart klang sie
                # im Test wie ein Unfall (1,3)
                kann("rolle", dict(halten, loop="rolle"), "Loop-Rolle in B's Drop", 2.8)
                kann("delay_out", dict(halten, effekt="delay75_ende_aus"), "kurzer Blend, A geht ins Delay", 2.0)
            kann("kurz_eq", {} if harmonisch else dict(lautstaerke="hart_aus", eq="bass_mitte", filter="hp_aus"),
                 "kurzer Profi-Blend" if harmonisch else "Tonarten passen nicht: A dünnt mit Hochpass aus", 1.0)
        if e.modus == "ausgewogen":
            if stems_da and singt_a and singt_b:
                kann("gesangsschutz", dict(art="gesangsschutz"), "beide singen: Stimmen nacheinander (Stems)", 3.0)
            if not harmonisch:
                kann("filter_blend", dict(kurz8, lautstaerke="hart_aus", eq="bass_mitte", filter="hp_aus"),
                     "Tonarten passen nicht: kurzer Blend, A dünnt mit Hochpass aus", 1.5)
            if stems_da and harmonisch:
                kann("drums_zuerst", dict(art="drums_zuerst"), "Drums von B zuerst, dann Bass und Rest (Stems)", 2.0)
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
            if stems_da and harmonisch:
                kann("drums_zuerst", dict(art="drums_zuerst"), "Drums von B zuerst, dann Bass und Rest (Stems)", 2.0)
            kann("profi_eq", {}, "langer Profi-Blend: Höhen → Mitten → Bass-Tausch", 1.0)
    if a_endet:   # A klingt in der Blende aus: ohne Loop bliebe ein Loch
        mit_loop = [k for k in kandidaten if k[1].get("loop", "keiner") != "keiner" or k[0] in GESANG_REZEPTE]
        kandidaten = mit_loop or kandidaten
    if not kandidaten:
        kann("profi_eq", {}, "Profi-Blend")
    # Abwechslung: nach einem Loop-Rezept kommt bevorzugt ein anderes (sonst loopt jeder Uebergang)
    nach_loop = vorher in LOOP_REZEPTE
    kandidaten.sort(key=lambda k: -(k[3] - (1.5 if nach_loop and k[0] in LOOP_REZEPTE else 0.0)))   # stabil
    vorlieben = vorlieben or {}
    # Abwechslung: nicht zweimal dasselbe; Gelerntes: was du oft abbrichst, nur wenn nichts anderes geht
    for name, felder, text, _ in kandidaten:
        if name != vorher and vorlieben.get(name, 0.0) > -2.0:
            return name, felder, text
    for name, felder, text, _ in kandidaten:
        if name != vorher:
            return name, felder, text
    return kandidaten[0][:3]


def _bass_takt(pa: Profil, pb: Profil, i: int, bi: np.ndarray, L: int) -> int:
    """Takt des Bass-Tauschs: wo B's Bassline einsetzt, sonst wo A's Bass am schwaechsten ist,
    sonst die Mitte. Nur auf Taktgruppen (4er, bei kurzen Blenden 2er) im mittleren Bereich."""
    raster = 4 if L >= 16 else 2 if L >= 4 else 1
    erlaubt = [k for k in range(raster, L, raster) if L / 4 <= k <= 3 * L / 4] or [L // 2]
    bb = _werte(pb.bass(), bi[:L])
    for k in erlaubt:
        if bb[k] > 0.5 and bb[k - 1] < 0.5:
            return k
    ba = _fenster(pa.stems["bass"] if pa.stems else pa.baender[:, 0], i, L)
    if np.ptp(ba[erlaubt]) > 6.0:
        return int(erlaubt[int(np.argmin(ba[erlaubt]))])
    return L // 2


LOOP_GUETE_MIN = 0.7   # darunter faellt die Wiederholung auf: kein A-Loop an dieser Stelle


def _loop_guete(pa: Profil, i: int, L: int, a_audio: np.ndarray, rate: int) -> float:
    """Wie sauber laesst sich A im Fenster ab Takt i loopen (aus dem Original, wie backen es waehlt)?
    Endet A vorher, zaehlt nur der Rest."""
    from .uebergang import loop_waehlen

    n = max(0, min(L + 8, pa.n - 1 - i))
    if n < 1:
        return 0.0
    fenster = min(L, n)
    t = pa.takte[i:i + n + 1] - pa.takte[i]
    a0 = int(round(pa.takte[i] * rate))
    tn = np.round(t * rate).astype(int)
    x = a_audio[a0:a0 + tn[-1]]
    if len(x) < tn[-1] // 2:
        return 1.0   # Audio passt nicht zum Profil: nicht beurteilbar
    ga = pa.gesang()
    meiden = _fenster(ga, i, fenster) > 0 if ga is not None else None
    return float(loop_waehlen(x, tn, meiden, fenster=fenster)[2])


def planen(a, pa: Profil, b, pb: Profil, e: Einstellungen, ab_s: float, sync: bool, harmonisch: bool,
           sofort: bool = False, stems_da: bool = False, vorher: str | None = None,
           anzahl: int = 3, vorlieben: dict[str, float] | None = None,
           a_audio: np.ndarray | None = None, rate: int = 44100) -> list[Plan]:
    """Die besten `anzahl` Plaene fuer A -> B (verschiedene Ausstiege/Einsaetze).

    Mit `a_audio` (A roh, `rate`) wird fuer Loop-Rezepte vorab geprueft, ob an der Stelle ein
    sauberer Loop existiert; sonst waehlt die Regie dort ein Rezept ohne A-Loop. Endet A in der
    Blende und sein Rest laesst sich nicht sauber loopen, kommt der Ausstieg erst nach den anderen."""
    ab_takt = int(np.searchsorted(pa.takte, ab_s - 1e-3))
    lagen = _rangliste(pa, pb, e, ab_takt, sofort, stems_da, harmonisch)
    plaene, gesehen, zurueck = [], set(), []

    def plan_aus(lage: _Lage, loop_ok: bool = True) -> Plan:
        name, felder, text = _rezept(lage, pa, pb, e, sync, harmonisch, stems_da, vorher, vorlieben, loop_ok, sofort)
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
            if pa.n - lage.i < plan.takte:   # A endet hier: nur mit diesem (schlechten) Loop moeglich
                zurueck.append(plan)
                continue
            plan = plan_aus(lage, loop_ok=False)
        plaene.append(plan)
        if len(plaene) >= anzahl:
            break
    return (plaene + zurueck)[:anzahl] if plaene else zurueck[:anzahl]


def pruefen(blende: np.ndarray, rate: int, n_takte: int, pa: Profil, pb: Profil, aus_s: float,
            ein_s: float, gain_a: float, gain_b: float, rezept: str) -> str | None:
    """Selbstkontrolle des fertigen Uebergangs: Lautstaerke-Buckel oder -Loch gegenueber den
    beiden Songs an derselben Stelle. Gibt eine Begruendung zurueck, wenn er durchfaellt."""
    if n_takte < 2 or rezept in ("schnitt", "echo_out", "schnitt_echo", "echo_drop", "intro_loop_b", "double_drop",
                                 "drop_cuts")\
            or rezept in DROP_TRICKS:
        return None
    takt_s = len(blende) / rate / n_takte
    mono = blende.mean(axis=1) if blende.ndim > 1 else blende
    for k in range(n_takte):
        teil = mono[int(k * takt_s * rate):int((k + 1) * takt_s * rate)]
        ist = 10 * np.log10(np.mean(teil.astype(np.float64) ** 2) + 1e-10)
        # Mit Loop wiederholt A seinen Anfang: dessen Pegel ist der Vergleich
        ia = pa.takt_bei(aus_s + (0 if "loop" in rezept or rezept == "rolle" else k * takt_s))
        jb = pb.takt_bei(ein_s + k * takt_s)
        la, lb = pa.gesamt[ia] + gain_a, pb.gesamt[jb] + gain_b
        if ist > max(la, lb) + 3.5:
            return f"zu laut in Takt {k + 1} (+{ist - max(la, lb):.1f} dB)"
        x = (k + 0.5) / n_takte   # ideale Blende: Leistung gleitet von A nach B
        soll = 10 * np.log10((1 - x) * 10 ** (la / 10) + x * 10 ** (lb / 10))
        # gesang_zuerst: bis zur Uebergabe traegt A allein (B nur mit Gesang) - kein Loch
        if ist < soll - 9.0 and k not in (0, n_takte - 1) and rezept != "gesang_zuerst":
            return f"Loch in Takt {k + 1} ({ist - soll:.1f} dB)"
    return None
