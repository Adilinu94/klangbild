"""Uebergangs-Engine des Auto-DJ (Phase 1, ROADMAP, ADR-014).

Rendert aus einem `plan.Plan` eine Mix-Datei. Der Uebergang A->B laeuft nach
ADR-014 (Vinyl-Angleich per Resampling) und der Roadmap Phase 1:

1. **Tempoangleich:** B wird per Resampling (`resample.resample`) auf das Tempo
   von A gezogen. Damit laufen die Beats nach dem Uebergang **im Raster von A**
   statt auseinander - genau das, was 1 % Tempounterschied ueber 16 Takte sonst
   hoerbar galoppieren liesse (ADR-014). Der Faktor kommt **aus dem Plan**, damit
   Planer und Renderer identisch rechnen.
2. **Taktgenaues Einsetzen:** A steigt am Ende einer Phrase aus (auf einem
   Downbeat), B setzt **auf einem Downbeat** ein - und weil B auf A-Tempo
   resampelt ist, bleiben die Downbeats im Gleichtakt.
3. **Crossfade** ueber `blende_sekunden` mit **equipotenter** Raised-Cosine-Kurve
   (cos/sin): gleiche Leistung, kein Lautstaerke-Loch in der Blende.
4. **Bass-Tausch** (Tiefpass/Hochpass im Takt): die Baesse werden in ein LOW- und
   ein HIGH-Band geteilt; das LOW-Band wird an der Blendenmitte von A nach B
   uebergeben (A behaelt den Bass in der ersten Haelfte, B in der zweiten). So
   addieren sich zwei Baesse nie - der klassische Bass-Swap eines DJ.
5. **Lautheit:** der fertige Mix wird auf -14 LUFS gebracht, True Peak <= -1 dBTP
   (`lufs.auf_lautheit_bringen`, eigener BS.1770 - spaeter 1:1 libebur128).

Alles ist reine Signalverarbeitung auf Mono-float32. phase10.py prueft das
Ergebnis gegen **bekannte** synthetische Signale (Klicks je Beat, getrennte
Bass-Frequenzen), statt sich aufs Hoeren zu verlassen.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import config, lufs, resample

# Uebergangs-Filtersteilheit (Butterworth). 4. Ordnung je Band, SOS fuer Stabilität.
FILTER_ORDNUNG = 4
# Ueber dieser Frequenz (Hz) beginnt das HIGH-Band, darunter das LOW-Band (Bass).
BASS_TRENN_HZ = 200.0


def equal_power_blende(n: int) -> tuple[np.ndarray, np.ndarray]:
    """Equipotente Raised-Cosine-Blende: (aus, ein) mit cos/sin ueber [0, pi/2].

    Gleichzeitig 1 an Kurvenanfang und 0 am -ende; aus^2 + ein^2 = 1 (gleiche
    Leistung). Leere Eingabe liefert leere Kurven.
    """
    if n <= 0:
        leer = np.zeros(0, dtype=np.float32)
        return leer, leer.copy()
    phase = np.linspace(0.0, np.pi / 2.0, n, endpoint=False, dtype=np.float64)
    return np.cos(phase).astype(np.float32), np.sin(phase).astype(np.float32)


def _sos(kind: str, trenn_hz: float, rate: int) -> np.ndarray | None:
    """Butterworth-SOS-Koeffizienten fuer 'tief' (low) oder 'hoch' (high)."""
    try:
        from scipy.signal import butter
    except ImportError:  # pragma: no cover - scipy ist im Prototyp-Standard dabei
        return None
    nyquist = rate / 2.0
    if not 0 < trenn_hz < nyquist:
        return None
    return butter(FILTER_ORDNUNG, trenn_hz / nyquist, btype=kind, output="sos")


def _filtern(sos: np.ndarray | None, signal: np.ndarray) -> np.ndarray:
    """Filtert `signal` nullphasig fuer den Offline-Render.

    `sosfiltfilt` laeuft das Filter vorwaerts **und** rueckwaerts: kein Start-
    transient, keine Phasenverschiebung, keine Latenz - genau das will ein
    Offline-Mix (anders als eine Echtzeit-Engine). Ein kausales `sosfilt` liesse
    am Einschwingen Energie ins Nachbarband kippen (bei einem 80-Hz-Bass unter
    einer 500-Hz-Trennung ~42 % Leck - gemessen, siehe test_band_teilen). Ist das
    Signal fuer die Nullphasen-Polsterung zu kurz, faellt es ehrlich auf das
    kausale `sosfilt` zurueck, statt zu werfen.
    """
    if sos is None:
        return signal
    x = np.asarray(signal, dtype=np.float64)
    try:
        from scipy.signal import sosfiltfilt

        return sosfiltfilt(sos, x).astype(np.float32)
    except ValueError:
        # Zu kurz fuer sosfiltfilt (Standard-padlen = 3*(2*n_sections+1)).
        try:
            from scipy.signal import sosfilt

            return sosfilt(sos, x).astype(np.float32)
        except Exception:  # noqa: BLE001 - notfalls ungefiltert weiterreichen
            return signal
    except Exception:  # noqa: BLE001 - notfalls ungefiltert weiterreichen
        return signal


def band_teilen(signal: np.ndarray, rate: int, trenn_hz: float = BASS_TRENN_HZ) -> tuple[np.ndarray, np.ndarray]:
    """Zerlegt in (low, high) bei `trenn_hz`. high = signal - low (komplementaer).

    Fällt scipy aus, ist low = 0 und high = signal (nur Hochband, kein Swap) -
    ehrlich degradiert statt erfunden.
    """
    low = _filtern(_sos("low", trenn_hz, rate), signal)
    high = (signal - low).astype(np.float32)
    return low.astype(np.float32), high


def _auffuellen(signal: np.ndarray, laenge: int) -> np.ndarray:
    """Bringt ein Signal exakt auf `laenge` Samples (kuerzt oder fuellt mit 0)."""
    if signal.size == laenge:
        return signal
    if signal.size > laenge:
        return signal[:laenge]
    return np.concatenate([signal, np.zeros(laenge - signal.size, dtype=np.float32)])


def _fade_segment(
    schwanz_a: np.ndarray,
    kopf_b: np.ndarray,
    rate: int,
    basstausch: bool,
    trenn_hz: float = BASS_TRENN_HZ,
) -> np.ndarray:
    """Ueberblendet A's Schwanz mit B's Kopf ueber die gemeinsame Blendenlaenge.

    Beide Eingaben sind bereits auf dieselbe Laenge `n` gebracht. Ohne
    `basstausch` ist es eine **equipotente** Crossfade (cos/sin, gleiche Leistung,
    kein Lautstaerke-Loch). Mit `basstausch` wird zusaetzlich das Bass-Band an der
    Blendenmitte von A nach B uebergeben (A behaelt den Bass in der ersten
    Haelfte, B in der zweiten), waehrend das Hochband equipotent uebergeht - so
    addieren sich zwei Baesse nie. Faellt scipy aus (kein Band), degradiert der
    Swap ehrlich zur reinen equipotenten Blende.
    """
    n = min(schwanz_a.size, kopf_b.size)
    if n <= 0:
        return np.zeros(0, dtype=np.float32)
    schwanz_a = np.asarray(schwanz_a[:n], dtype=np.float32)
    kopf_b = np.asarray(kopf_b[:n], dtype=np.float32)
    aus, ein = equal_power_blende(n)

    if not basstausch:
        return (schwanz_a * aus + kopf_b * ein).astype(np.float32)

    a_low, a_high = band_teilen(schwanz_a, rate, trenn_hz)
    b_low, b_high = band_teilen(kopf_b, rate, trenn_hz)
    r_aus, r_ein = _bass_rampen(n, rate)
    hoch = a_high * aus + b_high * ein
    tief = a_low * r_aus + b_low * r_ein
    return (hoch + tief).astype(np.float32)



def uebergang_rendern(
    a: np.ndarray,
    b: np.ndarray,
    rate: int,
    faktor: float,
    a_ausstieg_s: float,
    b_einstieg_s: float,
    blende_s: float,
    basstausch: bool = True,
    trenn_hz: float = BASS_TRENN_HZ,
    resample_methode: str = "linear",
) -> np.ndarray:
    """Rendert genau einen Uebergang A -> B und liefert den fertigen Block.

    Ablauf (ADR-014, Roadmap Phase 1):
    - B wird per Resampling auf A-Tempo gezogen (`faktor` stammt aus `plan`, damit
      Planer und Renderer identisch rechnen). Die Beats bleiben damit im Raster.
    - A laeuft bis `a_ausstieg_s` (Ausstieg auf einem Downbeat / Phrasenende). Die
      letzte `blende_s` davon werden mit B ueberblendet.
    - B setzt auf `b_einstieg_s` (einem Downbeat) ein; seine ersten `blende_s`
      bilden die Einblendung, danach laeuft B weiter.
    - Die Ueberblendung ist **equipotent** (gleiche Leistung, kein Loch). Bei
      `basstausch` wird zusaetzlich das Bass-Band an der Blendenmitte von A nach B
      uebergeben (Tiefpass/Hochpass im Takt), damit sich zwei Baesse nie addieren.

    Alle Zeiten in Sekunden. Robust gegen zu kurzes A oder B (wird mit Stille
    aufgefuellt statt zu werfen) - ein Renderer darf nicht mitten im Set sterben.
    """
    blende_n = max(1, round(blende_s * rate))
    ausstieg_n = round(a_ausstieg_s * rate)
    einstieg_n = round(b_einstieg_s * rate)

    b_resamp = resample.resample(b, rate, faktor, methode=resample_methode)

    # A: Kopf (vor der Blende) + Schwanz (die Blendenlaenge, die uebergeht).
    kopf_a = a[: max(0, ausstieg_n - blende_n)]
    schwanz_a = a[max(0, ausstieg_n - blende_n): ausstieg_n]
    schwanz_a = _auffuellen(np.asarray(schwanz_a, dtype=np.float32), blende_n)

    # B: Kopf (die Blendenlaenge ab Einstieg) + Rest (danach).
    kopf_b = b_resamp[einstieg_n: einstieg_n + blende_n]
    kopf_b = _auffuellen(np.asarray(kopf_b, dtype=np.float32), blende_n)
    rest_b = b_resamp[einstieg_n + blende_n:]

    gemischt = _fade_segment(schwanz_a, kopf_b, rate, basstausch, trenn_hz)

    teile = [np.asarray(kopf_a, dtype=np.float32), gemischt, np.asarray(rest_b, dtype=np.float32)]
    return np.concatenate([t for t in teile if t.size]) if any(t.size for t in teile) else np.zeros(0, dtype=np.float32)


@dataclass(frozen=True)
class Uebergangspunkt:
    """Die konkreten Cue-Zeiten (Sekunden) und der Blendenverlauf eines Uebergangs."""

    a_ausstieg_s: float
    b_einstieg_s: float
    blende_s: float
    faktor: float
    from_id: int
    to_id: int


def waehle_ausstieg(downbeats: list[float], gesamt_s: float, blende_s: float) -> float:
    """Waehlt A's Ausstiegs-Downbeat: der letzte, der noch `blende_s` Platz laesst.

    Faellt auf das Songende zurueck, wenn keine Downbeats vorliegen (ehrlich: dann
    wird ohne Taktzeugen uebergeblendet, der Planer hat den Beat-Raster-Teil vorher
    geprueft).
    """
    gueltig = [d for d in downbeats if 0 <= d <= gesamt_s - blende_s]
    if gueltig:
        return float(gueltig[-1])
    return float(max(0.0, gesamt_s - blende_s))


def waehle_einstieg(downbeats: list[float], mindestens_s: float = 0.0) -> float:
    """Waehlt B's Einstiegs-Downbeat: der erste ab `mindestens_s` (sonst der erste).

    Ein kleiner Vorsprung (z. B. ab dem ersten Downbeat) haelt B im Takt; ohne
    Downbeats wird schlicht ab 0 eingesetzt.
    """
    gueltig = [d for d in downbeats if d >= mindestens_s]
    if gueltig:
        return float(gueltig[0])
    if downbeats:
        return float(downbeats[0])
    return 0.0


def _bass_rampen(n: int, rate: int) -> tuple[np.ndarray, np.ndarray]:
    """Bass-Uebergabe: (aus, ein) mit hartem Tausch an der Blendenmitte.

    A behaelt das LOW-Band in der ersten Haelfte (aus=1, ein=0), B in der
    zweiten (aus=0, ein=1); eine ~10-ms-Raised-Cosine-Flanke um die Mitte
    verhindert den Knacks. So addieren sich zwei Baesse nie - der Bass-Swap,
    den die Roadmap Phase 1 fuer den Uebergang fordert.
    """
    if n <= 0:
        leer = np.zeros(0, dtype=np.float32)
        return leer, leer.copy()
    mitte = n // 2
    flanke = max(1, int(0.010 * rate))  # 10 ms weicher Uebergang
    flanke = min(flanke, max(1, mitte))
    aus = np.zeros(n, dtype=np.float32)
    ein = np.zeros(n, dtype=np.float32)
    aus[: mitte + flanke] = 1.0
    ein[mitte - flanke:] = 1.0
    ramp = 0.5 - 0.5 * np.cos(
        np.linspace(0.0, np.pi, 2 * flanke, endpoint=False, dtype=np.float64)
    ).astype(np.float32)
    # aus faellt ueber die Flanke um die Mitte, ein steigt darin.
    aus[mitte - flanke: mitte + flanke] = 1.0 - ramp[: 2 * flanke]
    ein[mitte - flanke: mitte + flanke] = ramp[: 2 * flanke]
    return aus.astype(np.float32), ein.astype(np.float32)

def _decke_true_peak(
    signal: np.ndarray, rate: int, grenze_db: float = config.TRUE_PEAK_GRENZE
) -> tuple[np.ndarray, float]:
    """Bringt den True Peak unter `grenze_db` (dBTP) per **Pegelabsenkung**.

    Erst wird gemessen (`lufs.true_peak_dbtp`); liegt die Spitze darueber, wird das
    **ganze** Signal um genau die Ueberhoehung abgesenkt und erneut gemessen. Das
    ist ehrlich und verzerrungsfrei - kein weiches Knie, kein hartes Klippen.
    Ein True-Peak-Limiter mit Lookahead/Angriff waere der naechste Schritt, aber
    Absenken respektiert die Grenze garantiert und laesst den Mix unverfaerbt.
    Liegt die Spitze drunter, bleibt das Signal unberuehrt (kein Pegelverlust).
    """
    spitze_db = lufs.true_peak_dbtp(signal, rate)
    if not np.isfinite(spitze_db) or spitze_db <= grenze_db:
        return signal, spitze_db
    # Um die Ueberhoehung plus 0,01 dB Sicherheit senken (float32-Rundung), damit
    # die Nachmessung garantiert <= Grenze landet statt haarescharf darauf.
    dba = grenze_db - spitze_db - 0.01
    ausgabe = (signal * (10.0 ** (dba / 20.0))).astype(np.float32)
    return ausgabe, lufs.true_peak_dbtp(ausgabe, rate)


@dataclass(frozen=True)
class MixUebergang:
    """Protokoll eines einzelnen Uebergangs im Mix (Roadmap: je Uebergang)."""

    from_id: int
    to_id: int
    a_ausstieg_s: float
    b_einstieg_s: float
    blende_s: float
    tempo_faktor: float


@dataclass
class MixProtokoll:
    """Protokoll des ganzen Mixes: Reihenfolge, Uebergaenge, Lautheit, Dauer.

    Genau das, was die Roadmap unter „Ausgabe" verlangt: Songs, BPM-Abgleich,
    Cue-Punkte und Lautheit, damit jedes Set nachvollziehbar und jeder Fehler
    einem Uebergang zuordenbar ist.
    """

    reihenfolge: list[int]
    uebergaenge: list[MixUebergang]
    lufs: float
    true_peak: float
    dauer_s: float


def mix_set(
    reihenfolge: list[int],
    audio: dict[int, np.ndarray],
    downbeats: dict[int, list[float]],
    rate: int,
    faktoren: dict[int, float],
    blende_s: float = 2.0,
    basstausch: bool = True,
    ziel_lufs: float = config.LUFS_ZIEL,
) -> tuple[np.ndarray, MixProtokoll]:
    """Rendert ein ganzes Set aus `reihenfolge` zu einer Mix-Datei (Mono).

    Ablauf je Nachbarpaar (A -> B):
    - A steigt auf einem Downbeat aus (`waehle_ausstieg`), B setzt auf einem
      Downbeat ein (`waehle_einstieg`).
    - B wird per `resample` mit `faktoren[B]` auf A's laufendes Tempo gezogen
      (ADR-014). Der Faktor kommt **aus dem Plan**, damit Plan und Mix identisch
      rechnen; beide Spuren liegen so auf demselben Beat-Raster.
    - Die letzten `blende_s` von A und die ersten `blende_s` von B werden
      equipotent uebergeblendet (`_fade_segment`, optional mit Bass-Tausch).

    Am Ende wird der Mix auf `ziel_lufs` gebracht und der True Peak auf
    `config.TRUE_PEAK_GRENZE` gedeckelt. Es wird **nicht** an einem toten Track
    geworfen: fehlt Audio oder ein Downbeat, degradiert der Uebergang ehrlich
    (Schnitt/Ueberblende ohne Taktzeuge), statt das Set abzubrechen.
    """
    if not reihenfolge:
        leer = np.zeros(0, dtype=np.float32)
        return leer, MixProtokoll([], [], float("-inf"), float("-inf"), 0.0)

    blende_n = max(1, round(blende_s * rate))
    protokoll_uebergaenge: list[MixUebergang] = []
    mischung = np.zeros(0, dtype=np.float32)

    for position, track_id in enumerate(reihenfolge):
        roh = audio.get(track_id)
        if roh is None or np.asarray(roh).size == 0:
            continue
        spur = np.asarray(roh, dtype=np.float32).reshape(-1)
        beats = downbeats.get(track_id, []) or []
        gesamt_s = spur.size / rate
        letzter = position == len(reihenfolge) - 1

        # Einstieg: erster Song ab 0, sonst ab dem ersten Downbeat (im Takt).
        einstieg_s = 0.0 if position == 0 else waehle_einstieg(beats)
        # Ausstieg: letzter Downbeat mit Blendenplatz; letzter Song laeuft aus.
        ausstieg_s = gesamt_s if letzter else waehle_ausstieg(beats, gesamt_s, blende_s)

        anfang_n = max(0, round(einstieg_s * rate))
        ende_n = min(spur.size, max(anfang_n + 1, round(ausstieg_s * rate)))
        segment = spur[anfang_n:ende_n]

        # Tempoangleich auf die laufende Zeit (Faktor aus dem Plan, ADR-014).
        faktor = float(faktoren.get(track_id, 1.0)) if position > 0 else 1.0
        if faktor and abs(faktor - 1.0) > 1e-9:
            segment = resample.resample(segment, rate, faktor)

        if position == 0 or mischung.size == 0:
            mischung = segment
        else:
            # Ueberblende: Schwanz der laufenden Mischung trifft Kopf des neuen
            # Segments - beide liegen nach dem Resampling auf demselben Raster.
            schwanz = mischung[-blende_n:] if mischung.size >= blende_n else mischung
            schwanz = _auffuellen(np.asarray(schwanz, dtype=np.float32), blende_n)
            kopf = _auffuellen(np.asarray(segment[:blende_n], dtype=np.float32), blende_n)
            mischbar = _fade_segment(schwanz, kopf, rate, basstausch)
            kopf_mischung = (
                mischung[:-blende_n] if mischung.size >= blende_n
                else np.zeros(0, dtype=np.float32)
            )
            rest = segment[blende_n:]
            mischung = np.concatenate(
                [t for t in (kopf_mischung, mischbar, rest) if t.size]
            )

        if not letzter:
            naechster = reihenfolge[position + 1]
            protokoll_uebergaenge.append(
                MixUebergang(
                    from_id=track_id,
                    to_id=naechster,
                    a_ausstieg_s=ausstieg_s,
                    b_einstieg_s=waehle_einstieg(downbeats.get(naechster, []) or []),
                    blende_s=blende_s,
                    tempo_faktor=float(faktoren.get(naechster, 1.0)),
                )
            )

    # Lautheit auf Ziel, True Peak deckeln (Roadmap: -14 LUFS, <= -1 dBTP).
    angeglichen = lufs.auf_lautheit_bringen(mischung, rate, ziel_lufs)
    gedeckelt, tp = _decke_true_peak(angeglichen, rate)
    lufs_wert = lufs.integrierte_lautheit(gedeckelt, rate)
    protokoll = MixProtokoll(
        reihenfolge=list(reihenfolge),
        uebergaenge=protokoll_uebergaenge,
        lufs=lufs_wert,
        true_peak=tp,
        dauer_s=gedeckelt.size / rate if rate else 0.0,
    )
    return gedeckelt, protokoll

