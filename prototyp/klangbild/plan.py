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
    """

    id: int
    pfad: str
    bpm: float | None
    camelot: str | None
    energie_db: float | None = None
    vektor: object | None = None  # np.ndarray (1D, normiert) oder None


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


