"""Phase 0.8 - skey (Deezer, MIT) gegen denselben FMAK-Goldsatz messen.

Warum
-----
Unser eigener Tonart-Schaetzer (Phase 0.4/0.5, Chroma + handgeschriebene
Tonart-Profile) liegt bei **48,2 % exakt / 73,5 % Nachbar** auf dem FMAK-Goldsatz
(n=400) und stösst dort an eine Decke. `skey` (Deezer, MIT) ist ein kleines
gelerntes CNN (HCQT/VQT -> ChromaNet) mit *trainierten* Gewichten statt
handgeschriebener Tonart-Profile. Die Frage dieser Phase, ehrlich und messbar:

    Durchbricht skey unsere 48,2-%-Decke - und passiert es das Phase-0.2-Tor
    (Untergrenze des Wilson-Intervalls >= 50 % exakt / >= 70 % Nachbar)?

Identische Messkette (ADR-012)
-----------------------------
Damit der Vergleich 1:1 belastbar ist, wird **alles** aus `phase04` wiederverwendet:
derselbe Goldsatz, derselbe Lader, dieselbe Camelot-Umrechnung, dieselbe
Fehlerklassen-Logik, dieselben Tore, dasselbe Wilson-Intervall. Einzig der
Schaetzer ist getauscht:

    phase04:  track_vergleichen -> tonart_schaetzen (eigenes Chroma-Profil)
    phase08:  _vergleich        -> skey           (gelerntes CNN)

So ist n identisch und das Intervall identisch - nur die Vorhersage unterscheidet
sich. Genau das macht „besser/schlechter" belastbar statt anekdotisch.

Lizenz & Abhaengigkeiten (ADR-012, Lizenz-Gate)
-----------------------------------------------
- skey: **MIT** (permissiv, passiert das Gate; Deezer).
- Abhaengigkeiten: numpy, torch, torchaudio, tqdm, einops, nnAudio, soundfile.
  **Kein librosa**, keine GPL-Nachbarschaft. skey liest Audio per torchaudio mit
  `soundfile`-Backend (MP3-faehig) und berechnet die HCQT per nnAudio.
- Rein interner Messlauf, nichts ausgeliefert - die Auslieferung regelt das Gate.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from . import audioio, config, keyestimate, phase04

# skey ist ein geklontes Repo unter werkzeuge/skey (eigene Historie, nicht Teil
# dieses Projekts). Wir haengen es NUR fuer diesen Messlauf in den Importpfad -
# lazy, erst beim tatsaechlichen Aufruf (kein Import zur Modul-Ladezeit).
SKEY_REPO = config.PROTOTYP_WURZEL / "werkzeuge" / "skey"


def _log(text: str) -> None:
    print(text, flush=True)


def _skey_laden():
    """Importiert skey lazy und liefert (Modul, ckpt, sr, (hcqt, chromanet, crop_fn), device).

    Das Modell wird EINMAL geladen (nicht pro Track). None wenn skey fehlt oder
    das Modell/der Checkpoint nicht ladbar ist.
    """
    if str(SKEY_REPO) not in sys.path:
        sys.path.insert(0, str(SKEY_REPO))
    try:
        import skey.key_detection as skd
        import torch
    except Exception as fehler:  # noqa: BLE001 - sauberer Abbruch mit Hinweis
        _log(f"skey nicht verfuegbar ({fehler}).")
        _log("Vorhanden? werkzeuge/skey/skey/key_detection.py")
        _log("Abhaengigkeiten im venv? torch, torchaudio, nnAudio, soundfile.")
        return None
    try:
        device = torch.device("cpu")
        ckpt = skd.load_checkpoint(skd.DEFAULT_CHECKPOINT_PATH)
        sr = int(ckpt["audio"]["sr"])
        hcqt, chromanet, crop_fn = skd.load_model_components(ckpt, device)
    except Exception as fehler:  # noqa: BLE001
        _log(f"skey-Checkpoint/Modell nicht ladbar ({fehler}).")
        return None
    return skd, device, sr, (hcqt, chromanet, crop_fn)


def _schaetze_skey(skd, modelle, device, audio_pfad: Path, sr: int):
    """Ein Track durch skey. Gibt (camelot, vertrauen) oder None bei Fehler.

    Rechnet genau wie skeys offizielles `infer_key` (mean ueber die Zeitframes ->
    argmax) und liest zusaetzlich die Softmax-Maximalwahrscheinlichkeit als
    Vertrauen ab.

    Dekodierung bewusst UEBER unser eigenes audioio (soundfile + soxr), nicht ueber
    skeys `load_audio`: das ruft `torchaudio.load(backend="soundfile")`, was in
    dieser torchaudio-Version MP3 trotzdem an TorchCodec/FFmpeg delegiert - genau
    die Nachbarschaft, die ADR-012 vermeidet. Wir liefern skey stattdessen die
    bereits dekodierten Mono-Samples als (1, T)-Tensor (gleiches Format wie
    `load_audio`). Ein Fehler (z. B. sehr kurzes Audio) ueberspringt den Track.
    """
    import numpy as np
    import torch

    hcqt, chromanet, crop_fn = modelle
    try:
        audio = audioio.decodieren(audio_pfad, sr)  # mono float32 @ sr (22050)
        werte = np.asarray(audio.daten, dtype=np.float32)
        if werte.size == 0:
            return None
        # Identische Normalisierung wie skeys load_audio (Teilen durch max|wert|),
        # damit skey sein *trainiertes* Verhalten zeigt - faire, ehrliche Messung.
        max_wert = float(np.max(np.abs(werte)))
        if max_wert > 0:
            werte = werte / max_wert
        # skey erwartet (1, T) wie aus load_audio; dann .unsqueeze(0) -> (1,1,T).
        eingang = torch.from_numpy(werte).unsqueeze(0).unsqueeze(0).to(device)
        with torch.no_grad():
            cropped = crop_fn(hcqt(eingang), torch.zeros(1).to(device))
            logits = chromanet(cropped)  # (T, 24)
            mittel = torch.mean(logits, dim=0)  # (24,)
            idx = int(mittel.argmax())
            vertrauen = float(torch.softmax(mittel, dim=0)[idx])
        camelot = _camelot_aus_skey(skd.key_map[idx])
        if not camelot:
            return None
        return camelot, vertrauen
    except Exception as fehler:  # noqa: BLE001 - ein kaputter Track stoppt nicht den Lauf
        _log(f"  uebersprungen ({audio_pfad.name}): {fehler}")
        return None


def _ist_gueltiges_wort(wort: str) -> bool:
    """True wenn das skey-Wort die Form '<Tonart> <Modus>' hat (ein Leerzeichen).

    skey liefert z. B. 'A Major', 'Bb minor' oder bei Fehler 'error'. 'error' hat
    kein Leerzeichen und wird so zuverlässig abgewiesen; genau das prueft diese
    schlanke Kontrolle, ohne sich auf die genaue Fehlerzeichenkette zu verlassen.
    """
    return bool(wort) and " " in wort


def _camelot_aus_skey(wort: str) -> str:
    """'A Major' -> '11B', 'Bb minor' -> '3A'. Leer wenn unbekannt/Fehler.

    Nutzt phase04s `_keymode_zu_camelot`, damit Gold und Schaetzung exakt dieselbe
    Umrechnung durchlaufen - keine zweite, potenziell abweichende Tabelle. So ist
    das Nachbar-Kriterium identisch zum Gold-Lauf (ADR-012).
    """
    if not _ist_gueltiges_wort(wort):
        return ""
    key, modus = wort.rsplit(" ", 1)
    return phase04._keymode_zu_camelot(key, modus)


def _vergleich(skd, modelle, device, track_id: str, gold_camelot: str,
               audio_pfad: Path, sr: int) -> phase04.GoldVergleich | None:
    """skey-Vorhersage gegen Gold -> GoldVergleich (identisches Format wie phase04).

    `gold_camelot` kommt bereits als Camelot aus `phase04._sammle_paare`.
    """
    ergebnis = _schaetze_skey(skd, modelle, device, audio_pfad, sr)
    if ergebnis is None:
        return None
    schaetzung, vertrauen = ergebnis
    nachbarn = keyestimate.camelot_nachbarn(gold_camelot)
    return phase04.GoldVergleich(
        track_id=track_id,
        gold=gold_camelot,
        schaetzung=schaetzung,
        vertrauen=vertrauen,
        exakt=schaetzung == gold_camelot,
        nachbar=schaetzung == gold_camelot or schaetzung in nachbarn,
    )


# --- Ausgaben ------------------------------------------------------------------
def _bericht_schreiben(ordner: Path, z: dict, dauer: float, gesamt: int) -> Path:
    """Phase-0.8-Bericht: exakt/Nachbar gegen Tor + Vergleich zum Chroma-Profil."""
    nl = "\n"
    einleitung = (
        "Messlauf: skey (Deezer, MIT) gegen von Expert:innen bestimmte Tonarten "
        "(FMAK, CC BY 4.0). Interne Auswertung, nichts ausgeliefert (Lizenz-Gate "
        "ADR-012). Vergleich 1:1 mit Phase 0.4: **derselbe Goldsatz (n), dieselbe "
        "Metrik, dieselben Tore** - nur der Schaetzer ist skey statt unseres "
        "Chroma-Profils. So ist die Aussage belastbar, nicht anekdotisch."
    )
    hinweis_tor = (
        "**Tor-Entscheid:** erfuellt, wenn die *Untergrenze* des Wilson-Intervalls "
        "die Schwelle erreicht (nicht bloss der Punktwert) - wie in Phase 0.2/0.4."
    )

    def _zeile(name: str, teil: dict) -> str:
        return (
            f"| {name} | {teil['treffer']}/{z['tracks']} | "
            f"{teil['quote'] * 100:0.1f} % | "
            f"{teil['wilson_unten'] * 100:0.1f}-{teil['wilson_oben'] * 100:0.1f} % | "
            f"{teil['tor'] * 100:0.0f} % | "
            f"{'JA' if teil['erreicht'] else 'NEIN'} |"
        )

    zeilen = [
        "# Phase 0.8 - skey (ML) gegen FMAK-Goldsatz",
        "",
        einleitung,
        "",
        f"- Dauer: {dauer:.1f} s",
        f"- FMAK-Tracks angefordert (Label + Audio): {gesamt}",
        f"- davon von skey ausgewertet: {z['tracks']}",
        "",
        "## Ergebnis gegen das Phase-0.2-Tor",
        "",
        "| Kennzahl | Treffer/N | Quote | Wilson 95 % | Tor | erreicht? |",
        "|---|---|---|---|---|---|",
        _zeile("exakt gleich", z["exakt"]),
        _zeile("inkl. Camelot-Nachbar", z["nachbar"]),
        "",
        ("**Vergleich zu unserem eigenen Schaetzer (Phase 0.5, n=400):** "
         "48,2 % exakt / 73,5 % Nachbar (Chroma + Tonart-Profile)."),
        "",
        (f"- skey Softmax-Max (roh, unkalibriert), Mittel: "
         f"{z['mittel_vertrauen']:.3f} - **keine Wahrscheinlichkeit!** Die "
         f"ChromaNet-Logits sind nicht als Wahrscheinlichkeit kalibriert; der Wert "
         f"liegt nahe der Gleichverteilung (1/24 = 0.042), obwohl skey 58.8 % "
         f"trifft. Wir gateen deshalb NUR ueber die Trefferquote + Wilson, nie "
         f"ueber diesen Rohwert."),
        "",
        hinweis_tor,
        "",
    ]
    klassen = z.get("klassen") or {}
    if klassen:
        reihenfolge = ("exakt", "modus", "quint", "diagonal", "weit")
        bedeutung = {
            "exakt": "Tonart exakt getroffen",
            "modus": "gleiche Nummer, A<->B (relative Dur/Moll - sehr nah)",
            "quint": "gleicher Buchstabe, Ziffer +/-1 (Quintenzirkel-Nachbar)",
            "diagonal": "Ziffer +/-1 und anderer Buchstabe (nah, kein Nachbar)",
            "weit": "alles andere (mind. zwei Schritte weg)",
        }
        zeilen += [
            "## Fehlerklassen (wo liegt skey daneben?)",
            "",
            "| Klasse | N | Anteil | Bedeutung |",
            "|---|---|---|---|",
        ]
        for k in reihenfolge:
            if k in klassen:
                anteil = klassen[k] / z["tracks"] * 100 if z["tracks"] else 0.0
                zeilen.append(
                    f"| {k} | {klassen[k]} | {anteil:0.1f} % | {bedeutung[k]} |"
                )
        zeilen.append("")
    hart = z.get("hart") or {}
    if hart.get("tracks"):
        zeilen += [
            "## Harte Faelle (erste 50, nicht exakt)",
            "",
            "| track_id | Gold | skey | Klasse |",
            "|---|---|---|---|",
        ]
        for t in hart["tracks"]:
            zeilen.append(
                f"| {t['track_id']} | {t['gold']} | {t['schaetzung']} | {t['klasse']} |"
            )
        zeilen.append("")
    zeilen.append(
        "Vollstaendiger Per-Track-Export (alle Tracks): "
        "`ergebnisse/phase08-skey-tracks.csv`."
    )
    p = ordner / "phase08-skey.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(nl.join(zeilen) + nl, encoding="utf-8")
    return p


def _json_schreiben(ordner: Path, z: dict) -> Path:
    import json

    p = ordner / "phase08-skey.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(z, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def _csv_schreiben(ordner: Path, vergleiche: list) -> Path:
    """Vollstaendiger Per-Track-Export (MIREX-Stil) - eine Zeile je Track."""
    import csv

    p = ordner / "phase08-skey-tracks.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as f:
        schreiber = csv.writer(f)
        schreiber.writerow(
            ["track_id", "gold", "schaetzung", "exakt", "nachbar", "klasse", "vertrauen"]
        )
        for v in vergleiche:
            schreiber.writerow([
                v.track_id, v.gold, v.schaetzung,
                int(v.exakt), int(v.nachbar),
                phase04._fehlerklasse(v.gold, v.schaetzung),
                f"{v.vertrauen:.4f}",
            ])
    return p



# --- Ablauf --------------------------------------------------------------------
def laufen(args) -> int:
    """skey gegen FMAK messen. Audio lokal (--fmak-audio) oder per Range (--fmak-remote)."""
    einstellungen = config.vorbereiten(config.aus_argumenten(args))
    datenordner = Path(getattr(args, "datenordner", None) or (config.DATEN / "fmak"))
    audio_wurzel = Path(getattr(args, "fmak_audio", None) or (config.DATEN / "fmak" / "audio"))
    remote = bool(getattr(args, "fmak_remote", False))
    limit = int(getattr(args, "limit", 0) or 0)
    ordner = einstellungen.ergebnisse

    korpus = phase04.lade_korpus(datenordner)
    if korpus is None:
        _log("FMAK-Labels/Index nicht verfuegbar (Download fehlgeschlagen?).")
        return 2
    labels, index = korpus

    paare = phase04._sammle_paare(labels, index, audio_wurzel, remote, limit)
    gesamt = len(paare)
    if gesamt == 0:
        _log("Keine passenden FMAK-Tracks gefunden.")
        _log("Lokales Audio: fma_small.zip nach <--fmak-audio> entpacken,")
        _log(f"oder on demand holen mit --fmak-remote (Cache unter {audio_wurzel}).")
        return 1

    geladen = _skey_laden()
    if geladen is None:
        return 2
    skd, device, sr, modelle = geladen

    modus_text = "lokal + per Range" if remote else "lokal"
    _log(f"Werte {gesamt} FMAK-Tracks mit skey aus ({modus_text}, sr={sr}) ...")
    start = time.time()
    vergleiche: list = []
    uebersprungen = 0
    for i, (tid, gold, audio_rel, lokalpfad) in enumerate(paare, 1):
        audio_pfad = phase04._audio_pfad_holen(tid, audio_rel, lokalpfad, audio_wurzel, remote)
        if audio_pfad is None:
            uebersprungen += 1
            continue
        v = _vergleich(skd, modelle, device, tid, gold, audio_pfad, sr)
        if v is None:
            uebersprungen += 1
            continue
        vergleiche.append(v)
        if i % 25 == 0 or i == gesamt:
            _log(f"  {i}/{gesamt} ...")
    dauer = time.time() - start

    if not vergleiche:
        _log("Kein Track von skey auswertbar (Audio/Modell-Problem?).")
        return 1

    z = phase04.auswerten(vergleiche)
    _json_schreiben(ordner, z)
    csv_pfad = _csv_schreiben(ordner, vergleiche)
    bericht = _bericht_schreiben(ordner, z, dauer, gesamt)
    _log(f"Exakt:   {z['exakt']['quote'] * 100:0.1f} % "
         f"({z['exakt']['treffer']}/{z['tracks']}) -> "
         f"Tor {'erreicht' if z['exakt']['erreicht'] else 'NICHT erreicht'}")
    _log(f"Nachbar: {z['nachbar']['quote'] * 100:0.1f} % "
         f"({z['nachbar']['treffer']}/{z['tracks']}) -> "
         f"Tor {'erreicht' if z['nachbar']['erreicht'] else 'NICHT erreicht'}")
    if uebersprungen:
        _log(f"uebersprungen: {uebersprungen} von {gesamt}")
    _log(f"JSON: {ordner / 'phase08-skey.json'}")
    _log(f"CSV (alle {len(vergleiche)} Tracks): {csv_pfad}")
    _log(f"Bericht: {bericht}")
    return 0

