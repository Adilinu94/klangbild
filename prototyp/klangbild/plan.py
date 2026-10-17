"""Auto-DJ-Planer (Phase 1, ROADMAP-KLANGBILD.md, Architektur §4).

Baut aus einer Sammlung analysierter Tracks ein Set. Die Note eines Uebergangs
A->B ist eine gewichtete Summe aus drei Teilen (config.PLANER_*):

- Harmonie (Camelot): exakt / Nachbar / fremd  -> 1,0 / 0,6 / 0,0
- Klang (Kosinus-Aehnlichkeit der gemittelten Vektoren) -> 0..1
- Energie-Reise: grosse Lautstaerke-Spruenge werden bestraft -> 0..1

Tempo ist **kein** Gewicht, sondern ein hartes Gate: ein Song ausserhalb ±1 %
des Deck-Tempos ist gar nicht waehlbar (ADR-020, resample.tempo_passt). Sonst
galoppieren die Songs nach der Resampling-Angleichung hoerbar auseinander. Das
Deck-Tempo ist das Tempo des Start-Songs; alle Uebergaenge ziehen darauf, damit
die Beats ueber das ganze Set auf einem Raster liegen.

Der Planer ist reine Datenverarbeitung: er liest Merkmale (nicht Audio) und
liefert eine Reihenfolge. Wie die Uebergaenge **klingen**, entscheidet mix.py;
wie gut Plan und Mix zusammenpassen, misst phase10.py gegen bekannte Signale.

Energie ist erst ab dem **dritten** Song gewichtet: am Anfang zaehlt die Passung
zum Nachbarn, die Energie-Reise formt das Set erst, wenn es laenger wird.
Determinismus: Gleichstaende werden ueber die kleinere Track-ID gebrochen; bei
gleichen Eingaben entsteht dieselbe Reihenfolge.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import config
from .keyestimate import camelot_nachbarn
from .resample import TEMPO_MAX_ABWEICHUNG, tempo_faktor, tempo_passt


@dataclass(frozen=True)
class Track:
    """Merkmale eines Songs, die der Planer braucht.

    `vektor` ist der gemittelte, normierte Klang-Vektor (aus db.alle_vektoren)
    oder None - dann faellt der Klang-Anteil heraus und die uebrigen Gewichte
    werden neu normiert (keine scheinbare Strafe fuer fehlende Vektoren).
    `energie_db` ist die mittlere Energie (dBFS) fuer die Energie-Reise.
    `energie` ist das Energielevel 0 (ruhig) .. 1 (hart) aus dem Profil (profil.energielevel), `genre` der
    Ordner des Titels (die Sammlung ist nach Genre sortiert); beide None = unbekannt.
    """

    id: int
    pfad: str
    bpm: float | None
    camelot: str | None
    energie_db: float | None = None
    vektor: object | None = None  # np.ndarray (1D, normiert) oder None
    energie: float | None = None
    genre: str | None = None


@dataclass(frozen=True)
class Uebergang:
    """Ein bewerteter Uebergang von Song A (from_id) zu Song B (to_id)."""

    from_id: int
    to_id: int
    harmonie: float      # 0..1 (exakt/Nachbar/fremd)
    klang: float         # 0..1 Kosinus-Aehnlichkeit (0,5 falls kein Vektor)
    energie: float       # 0..1 (1 = kein Sprung, 0 = grosser Sprung)
    note: float          # gewichtete Summe 0..1
    tempo_faktor: float  # wie B auf das Deck-Tempo gezogen wird (ADR-020)
    grund: str           # z. B. "gleiche Tonart", "Camelot-Nachbar", "fremd"


@dataclass
class Plan:
    """Ein gebautes Set: Reihenfolge, begruendete Uebergaenge, uebersprungener Rest."""

    reihenfolge: list[int] = field(default_factory=list)
    uebergaenge: list[Uebergang] = field(default_factory=list)
    uebersprungen: list[str] = field(default_factory=list)


def harmonie_note(ziel: str, kandidat: str) -> tuple[float, str]:
    """Harmonie-Note (0..1) und Klassifikation zweier Camelot-Codes."""
    if not ziel or not kandidat:
        return config.PLANER_HARMONIE_FREMD, "fremd"
    if ziel == kandidat:
        return config.PLANER_HARMONIE_EXAKT, "gleiche Tonart"
    if kandidat in camelot_nachbarn(ziel):
        return config.PLANER_HARMONIE_NACHBAR, "Camelot-Nachbar"
    return config.PLANER_HARMONIE_FREMD, "fremd"


def energie_note(
    ziel_db: float | None, kandidat_db: float | None, max_sprung: float
) -> tuple[float, str]:
    """Energie-Note (0..1) aus dem Lautstaerke-Sprung (dBFS, mittlere Energie).

    Ab `max_sprung` (config.PLANER_ENERGIE_MAX_SPRUNG_DB) ist die Note 0; groessere
    Spruenge werden auf 0 geklemmt (vorzeichenunabhaengig). Fehlt einer der Werte,
    ist die Note neutral 0,5 - fehlendes Wissen darf nicht wie Abneigung wirken.
    """
    if ziel_db is None or kandidat_db is None:
        return 0.5, "Energie unbekannt"
    sprung = abs(float(kandidat_db) - float(ziel_db))
    if sprung >= max_sprung:
        return 0.0, "Energie-Sprung"
    return 1.0 - sprung / max_sprung, "Energie passend"


def _kosinus(a, b) -> float:
    """Kosinus-Aehnlichkeit zweier Vektoren, robust auf 0..1 gemappt."""
    try:
        import numpy as np

        a = np.asarray(a, dtype=np.float64).reshape(-1)
        b = np.asarray(b, dtype=np.float64).reshape(-1)
        na = float(np.linalg.norm(a))
        nb = float(np.linalg.norm(b))
        if na <= 0 or nb <= 0:
            return 0.5
        aehnlichkeit = float(np.dot(a, b) / (na * nb))
        return min(1.0, max(0.0, (aehnlichkeit + 1.0) / 2.0))
    except Exception:  # noqa: BLE001 - nie am Plan scheitern
        return 0.5

def uebergang_note(
    ziel: Track,
    kandidat: Track,
    energie_gewichtet: bool,
    deck_bpm: float | None = None,
    max_sprung: float | None = None,
) -> Uebergang:
    """Bewertet den Uebergang ziel -> kandidat inklusive Begruendung.

    `deck_bpm` ist das Tempo, auf das gemischt wird (Standard: Tempo des
    Zielsongs). Der zurueckgegebene tempo_faktor rechnet wie resample.tempo_faktor,
    damit Plan und mix identisch rechnen.
    """
    if max_sprung is None:
        max_sprung = config.PLANER_ENERGIE_MAX_SPRUNG_DB
    harm, harm_grund = harmonie_note(ziel.camelot, kandidat.camelot)
    hat_klang = ziel.vektor is not None and kandidat.vektor is not None
    if hat_klang:
        klang = _kosinus(ziel.vektor, kandidat.vektor)
        klang_grund = "Klang-Aehnlichkeit"
    else:
        klang = 0.5
        klang_grund = "Klang unbekannt"
    energie, energie_grund = energie_note(ziel.energie_db, kandidat.energie_db, max_sprung)

    # Tempo-Angleich (Faktor): der Kandidat wird per Resampling auf das
    # Deck-Tempo gezogen. tempo_faktor(von, auf) = auf/von, geklemmt auf ±1 %
    # (ADR-020). Basis ist das Deck-Tempo, sonst das Tempo des Zielsongs.
    # Faktor = basis/kandidat: ein **schnellerer** Kandidat (groesseres
    # kandidat.bpm) wird verlangsamt (<1), damit seine Beats aufs Deck-Raster
    # fallen - genau die Richtung, die resample_linear braucht (f>1 = schneller).
    basis = deck_bpm if deck_bpm else ziel.bpm
    faktor = 1.0
    tempo_ok = True
    if basis and kandidat.bpm:
        tempo_ok = tempo_passt(basis, kandidat.bpm, TEMPO_MAX_ABWEICHUNG)
        faktor = tempo_faktor(kandidat.bpm, basis, TEMPO_MAX_ABWEICHUNG)

    # Gewichte: fehlt der Klang-Vektor, faellt sein Anteil heraus und der Rest
    # wird neu normiert, sonst bestraft ein fehlender Vektor alle gleichmaessig.
    w_h = config.PLANER_GEWICHT_HARMONIE
    w_k = config.PLANER_GEWICHT_KLANG if hat_klang else 0.0
    w_e = config.PLANER_GEWICHT_ENERGIE if energie_gewichtet else 0.0
    summe = w_h + w_k + w_e
    note = harm if summe <= 0 else (w_h * harm + w_k * klang + w_e * energie) / summe

    gruende = [harm_grund]
    if hat_klang:
        gruende.append(klang_grund)
    if energie_gewichtet:
        gruende.append(energie_grund)
    if not tempo_ok:
        # Jenseits ±1 % galoppiert der Uebergang selbst nach geklemmtem
        # Resampling hoerbar auseinander (ADR-020): Note 0. Der Faktor bleibt als
        # (geklemmte) Referenz stehen, damit Aufrufer den Fall sehen koennen.
        note = 0.0
        gruende.append("Tempo-Gate (ueber ±1 %)")

    return Uebergang(
        from_id=ziel.id,
        to_id=kandidat.id,
        harmonie=harm,
        klang=klang,
        energie=energie,
        note=note,
        tempo_faktor=faktor,
        grund=", ".join(gruende),
    )


def baue_set(
    tracks: list[Track],
    start_id: int | None = None,
    laenge: int = 0,
    energie_ab: int = 3,
) -> Plan:
    """Baut ein Set gierig: jeder naechste Song maximiert die Uebergangsnote.

    Das Deck-Tempo ist das Tempo des Start-Songs; ein Song ausserhalb ±1 %
    davon ist gar nicht waehlbar (hartes Gate, ADR-020). Bleibt kein Tempo-
    kompatibler Song uebrig, endet das Set vorzeitig - lieber kuerzer als ein
    galoppierender Uebergang. Die uebrigen Tracks werden als uebersprungen
    ausgewiesen. Determinismus: Gleichstand ueber kleinere Track-ID gebrochen.
    """
    if not tracks:
        return Plan()

    index = {t.id: t for t in tracks}
    if start_id is not None and start_id in index:
        aktuell = index[start_id]
    else:
        aktuell = tracks[0]

    deck_bpm = aktuell.bpm
    plan = Plan()
    plan.reihenfolge.append(aktuell.id)
    uebrig = [t for t in tracks if t.id != aktuell.id]
    ziel = len(tracks) if laenge <= 0 else min(laenge, len(tracks))

    while len(plan.reihenfolge) < ziel and uebrig:
        energie_gewichtet = len(plan.reihenfolge) >= max(1, energie_ab)
        beste: Uebergang | None = None
        beste_key: tuple[float, int] | None = None
        naechster: Track | None = None
        for kandidat in uebrig:
            if deck_bpm and kandidat.bpm and not tempo_passt(deck_bpm, kandidat.bpm, TEMPO_MAX_ABWEICHUNG):
                continue
            u = uebergang_note(aktuell, kandidat, energie_gewichtet, deck_bpm=deck_bpm)
            key = (u.note, -kandidat.id)
            if beste_key is None or key > beste_key:
                beste_key = key
                beste = u
                naechster = kandidat
        if beste is None or naechster is None:
            break  # kein Tempo-kompatibler Song mehr uebrig
        plan.uebergaenge.append(beste)
        plan.reihenfolge.append(naechster.id)
        uebrig.remove(naechster)
        aktuell = naechster

    for t in uebrig:
        plan.uebersprungen.append(t.pfad)
    return plan




# --- Phase 2: Bibliothek sortieren / naechsten Song waehlen (mit Keylock) ------

def rangliste(
    aktuell: Track, kandidaten: list[Track], max_bpm: float, harmonie: str = "locker",
    n: int = 6, bonus=None,
) -> list[Track]:
    """Die `n` besten naechsten Songs nach Tempo-Grenze (absolute BPM), Harmonie, Energie.

    Mit Keylock darf das Tempo um `max_bpm` angeglichen werden (ADR-022). Liegt kein
    Kandidat in der Grenze, kommen die tempo-naechsten - der Uebergang faellt dann auf
    Echo/Schnitt zurueck, statt das Set abzubrechen.
    `harmonie`: "streng" = nur gleiche Tonart/Camelot-Nachbar, falls vorhanden;
    "locker" = Harmonie zaehlt in der Note; "aus" = ignorieren.
    `bonus(aktuell, kandidat) -> float` (0..1) fliesst mit 20 % ein (z. B. saubere Mischstellen).
    """
    if not kandidaten:
        return []
    basis = aktuell.bpm or 0.0

    def abstand(k: Track) -> float:   # auch Doppel-/Halbtempo (85 <-> 170) mischt (BAUPLAN-UEBERGAENGE §5.3)
        return min(abs((k.bpm or basis) * f - basis) for f in (1.0, 2.0, 0.5))

    pool = [k for k in kandidaten if abstand(k) <= max_bpm + 1e-9]
    if not pool:
        return sorted(kandidaten, key=lambda k: (abstand(k), k.id))[:n]
    if harmonie == "streng":
        passend = [k for k in pool if harmonie_note(aktuell.camelot, k.camelot)[1] != "fremd"]
        pool = passend or pool

    def note(k: Track) -> tuple[float, int]:
        harm = harmonie_note(aktuell.camelot, k.camelot)[0] if harmonie != "aus" else 0.5
        if aktuell.energie is not None and k.energie is not None:   # ruhig nach hart (gleiches Tempo) vermeiden
            energie = 1.0 - min(1.0, 2.0 * abs(aktuell.energie - k.energie))
        else:
            energie = energie_note(aktuell.energie_db, k.energie_db, config.PLANER_ENERGIE_MAX_SPRUNG_DB)[0]
        tempo = 1.0 - abstand(k) / max(max_bpm, 1.0)
        wert = 0.35 * harm + 0.4 * energie + 0.25 * tempo
        if aktuell.genre and k.genre and aktuell.genre != k.genre:
            wert -= 0.2
        if bonus is not None:
            wert = 0.8 * wert + 0.2 * bonus(aktuell, k)
        return (wert, -k.id)

    return sorted(pool, key=note, reverse=True)[:n]


def naechster(
    aktuell: Track, kandidaten: list[Track], max_bpm: float, harmonie: str = "locker", bonus=None,
) -> Track | None:
    """Bester naechster Song (siehe `rangliste`)."""
    beste = rangliste(aktuell, kandidaten, max_bpm, harmonie, 1, bonus)
    return beste[0] if beste else None


# --- Set planen statt Paar (BAUPLAN-UEBERGAENGE §8) -----------------------------------------------------

BOGEN = 0.25          # Strafe 1 je 0,25 Energielevel Abstand zur Zielkurve (aufbauen/welle)
ENERGIE_SPRUNG = 4.0  # Strafe je Energielevel-Sprung (0..1): hart -> ruhig kostet ~2 Notenpunkte
GENRE_STRAFE = 1.5    # Wechsel des Genres (Ordner)
REZEPT_STRAFE = 1.0   # zweimal hintereinander dasselbe Rezept
VARIANTE = 1.0        # "neue Reihenfolge": Zufall bis 1 Notenpunkt je Schritt der gierigen Wahl


def bogen_ziel(energien: list[float], n: int, bogen: str) -> list[float | None]:
    """Energie-Ziel je Position: gleichmaessig (keins, nur kleine Spruenge zaehlen), aufbauen (10. -> 90.
    Perzentil), welle (auf und ab)."""
    import numpy as np

    if not energien or bogen == "gleichmaessig":
        return [None] * n
    lo, mitte, hi = (float(x) for x in np.percentile(energien, [10, 50, 90]))
    if bogen == "aufbauen":
        return [lo + (hi - lo) * k / max(1, n - 1) for k in range(n)]
    if bogen == "welle":   # eine Welle je ~8 Titel
        return [mitte + 0.5 * (hi - lo) * float(np.sin(2 * np.pi * k / 8)) for k in range(n)]
    return [mitte] * n


def _set_schritt(index: dict, a: int, b: int, vor: int | None, pos: int, ziel, note, rezept) -> float:
    """Kosten von a -> b an Position pos (b steht dort): -Note + Energiesprung + Genrewechsel + Energiebogen +
    gleiches Rezept wie davor."""
    k = -note(a, b)
    ta, tb = index[a], index[b]
    if ta.energie is not None and tb.energie is not None:
        k += ENERGIE_SPRUNG * abs(ta.energie - tb.energie)
    if ta.genre and tb.genre and ta.genre != tb.genre:
        k += GENRE_STRAFE
    if tb.energie is not None and ziel[pos] is not None:
        k += abs(tb.energie - ziel[pos]) / BOGEN
    if rezept is not None and vor is not None:
        r = rezept(a, b)
        if r is not None and r == rezept(vor, a):
            k += REZEPT_STRAFE
    return k


def _set_kosten(folge: list[int], index: dict, ziel, note, rezept, von: int = 1, bis: int | None = None) -> float:
    bis = len(folge) - 1 if bis is None else min(bis, len(folge) - 1)
    return sum(_set_schritt(index, folge[k - 1], folge[k], folge[k - 2] if k >= 2 else None, k, ziel, note, rezept)
               for k in range(max(1, von), bis + 1))


def _zwei_opt(folge: list[int], index: dict, ziel, note, rezept, fenster: int = 8, zeit_s: float = 3.0) -> list[int]:
    """2-opt auf kurzen Abschnitten (bis `fenster` Titel umdrehen; der Start bleibt): je Umkehr aendern sich nur
    die Kosten im Abschnitt und an seinen Raendern. Stoppt ohne Verbesserung oder nach `zeit_s`."""
    import time

    folge, beginn, besser = list(folge), time.perf_counter(), True
    while besser and time.perf_counter() - beginn < zeit_s:
        besser = False
        for i in range(1, len(folge) - 1):
            for j in range(i + 1, min(len(folge), i + fenster)):
                neu = folge[:i] + folge[i:j + 1][::-1] + folge[j + 1:]
                if _set_kosten(neu, index, ziel, note, rezept, i, j + 2) < \
                        _set_kosten(folge, index, ziel, note, rezept, i, j + 2) - 1e-9:
                    folge, besser = neu, True
    return folge


def set_planen(tracks: list[Track], start_id: int, max_bpm: float, harmonie: str, paarnote, rezept=None,
               bogen: str = "gleichmaessig", zufall=None) -> list[int]:
    """Reihenfolge nach erwarteten Uebergangsnoten (`paarnote(a, b) -> 1..5 | None`, paarnoten.py): gierig den
    naechsten mit den geringsten Kosten (Note, Energiesprung, Genre, Bogen), dann 2-opt. Fehlt eine Paarnote,
    schaetzt sie Tempo/Tonart/Energie."""
    index = {t.id: t for t in tracks}
    ziel = bogen_ziel([t.energie for t in tracks if t.energie is not None], len(tracks), bogen)

    def note(a: int, b: int) -> float:
        x = paarnote(a, b)
        if x is not None:
            return float(x)
        ta, tb = index[a], index[b]
        if min(abs((tb.bpm or 0) * f - (ta.bpm or 0)) for f in (1.0, 2.0, 0.5)) > max_bpm + 1e-9:
            return 0.5   # ausserhalb des Tempo-Rahmens: nur Echo/Schnitt
        harm = harmonie_note(ta.camelot, tb.camelot)[0] if harmonie != "aus" else 0.5
        energie = energie_note(ta.energie_db, tb.energie_db, config.PLANER_ENERGIE_MAX_SPRUNG_DB)[0]
        return 1.0 + 4.0 * (0.6 * harm + 0.4 * energie) * 0.75   # Schaetzung bleibt unter echten Paarnoten

    folge, uebrig = [start_id], set(index) - {start_id}
    while uebrig:
        vor = folge[-2] if len(folge) >= 2 else None
        b = min(sorted(uebrig), key=lambda x: _set_schritt(index, folge[-1], x, vor, len(folge), ziel, note, rezept)
                + (zufall.uniform(0.0, VARIANTE) if zufall else 0.0))
        folge.append(b)
        uebrig.remove(b)
    return _zwei_opt(folge, index, ziel, note, rezept)


def sortiere_alle(
    tracks: list[Track], max_bpm: float, harmonie: str = "locker", start_id: int | None = None,
    bonus=None, paarnote=None, rezept=None, bogen: str = "gleichmaessig", zufall=None,
) -> list[int]:
    """Alle Tracks in eine Reihenfolge bringen (gierig, jeder Song einmal).

    Start: `start_id` oder der groesste Tempo-Cluster (wie autodj.lade_tracks).
    Mit `paarnote` (BAUPLAN-UEBERGAENGE §8) nach erwarteten Uebergangsnoten, Energiebogen und Abwechslung
    der Rezepte (set_planen), sonst nach Tempo/Tonart/Energie (rangliste). `zufall` (random.Random): eine
    andere Variante (nur mit `paarnote`).
    shortcut: O(n^2) gierig; bei ~8.000 Titeln einige Minuten. Upgrade: Cluster
    nach Tempo vorsortieren und nur Nachbarn vergleichen.
    """
    if not tracks:
        return []
    index = {t.id: t for t in tracks}
    if start_id not in index:
        from collections import Counter

        modal = Counter(round(t.bpm or 0) for t in tracks).most_common(1)[0][0]
        start_id = next(t.id for t in tracks if round(t.bpm or 0) == modal)
    if paarnote is not None:
        return set_planen(tracks, start_id, max_bpm, harmonie, paarnote, rezept, bogen, zufall)
    aktuell = index[start_id]
    uebrig = [t for t in tracks if t.id != start_id]
    folge = [start_id]
    while uebrig:
        aktuell = naechster(aktuell, uebrig, max_bpm, harmonie, bonus)
        uebrig.remove(aktuell)
        folge.append(aktuell.id)
    return folge
