"""Gemma-4-Versuch: kann Gemma Uebergaenge einschaetzen und einstellen?

Stufe 1 (`noten`): Gemma schaetzt die Note (1-5) jedes bewerteten Uebergangs aus den
Uebergangstests - aus der Beschreibung (Songs, Einstellungen, Grund der Regie) und mit
`--audio` zusaetzlich aus dem Clip. Gemessen gegen die echten Noten des Nutzers, Vergleich:
Mittel je Rezept (ohne den Fall selbst).

Stufe 2: im Uebergangstest waehlt Gemma je Paar den Plan (`uebergangstest --gemma`).

Stufe 3 (`einstellungen`, BAUPLAN-UEBERGAENGE §10.1): Gemma uebersetzt einen freien Satz ("mach's chilliger")
in Aenderungen an den Mixer-Einstellungen. 60 Saetze mit Soll-Antwort (gemma_saetze.json); Tor fuer das
Handy: >= 85 % exakt richtig mit E2B, sonst wird die Funktion gestrichen.

    python -m klangbild.gemma_probe noten --modell google/gemma-4-E2B-it [--audio] [--max 40]
    python -m klangbild.gemma_probe einstellungen [--modell google/gemma-4-E2B-it]
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

import numpy as np

from . import config
from .datensatz import bewertete_faelle  # noqa: F401 - hier gebraucht und von aussen genutzt

ERGEBNISSE = config.PROTOTYP_WURZEL / "ergebnisse"
REGELN = ("Du bist ein erfahrener DJ (Drum and Bass, UK Garage, House). Du beurteilst automatische "
          "Übergänge zwischen zwei Songs. Ein guter Übergang kommt an der richtigen Stelle im Song, "
          "lässt nie zwei Bässe oder zwei Stimmen gegeneinander laufen, hält den Takt, passt zur Energie "
          "beider Songs und ist weder abrupt noch zu lang. Effekte sollen hörbar, aber nicht störend sein.")


class Gemma:
    """Gemma 4 (E2B/E4B) ueber transformers; Grafikkarte + RAM (accelerate)."""

    def __init__(self, modell: str, audio: bool = False):
        import torch
        from transformers import AutoModelForMultimodalLM, AutoProcessor

        self.processor = AutoProcessor.from_pretrained(modell, padding_side="left")
        m = AutoModelForMultimodalLM.from_pretrained(modell, dtype=torch.bfloat16, attn_implementation="sdpa")
        # Die Per-Layer-Embeddings (E2B: 2,3 Mrd. Parameter) sind eine Nachschlagetabelle: auf der CPU
        # nachschlagen, nur das Ergebnis zur Grafikkarte. device_map="auto" schob sie bei jedem Schritt ganz
        # hinueber (~110 s je Antwort auf 8 GB).
        lm = m.model.language_model
        ple, lm.embed_tokens_per_layer = lm.embed_tokens_per_layer, None
        # Ohne --audio bleibt der Ton-Teil auf der CPU (0,6 GB): sonst lagert Windows bei langen Fragen
        # (30 Beispiele) in den geteilten Speicher aus (70 s statt 10 s je Antwort). Der Bild-Teil muss auf die
        # Grafikkarte: generate() legt die Eingaben auf das Geraet des ersten Teils, und das ist er.
        weg = {} if audio else {"audio_tower": m.model.audio_tower}
        for n in weg:
            setattr(m.model, n, None)
        groesse = sum(p.numel() * p.element_size() for p in m.parameters())
        if groesse < 0.85 * torch.cuda.mem_get_info()[0]:
            m.to("cuda")
        else:   # E4B passt nicht ganz in 8 GB: die letzten Schichten wandern je Schritt aus dem RAM hinueber
            from accelerate import dispatch_model, infer_auto_device_map

            karte = infer_auto_device_map(m, max_memory={0: int(0.8 * torch.cuda.mem_get_info()[0]), "cpu": 40 << 30},
                                          no_split_module_classes=m._no_split_modules)
            dispatch_model(m, karte, main_device="cuda")
        lm.embed_tokens_per_layer = ple
        for n, t in weg.items():
            setattr(m.model, n, t)
        ple.register_forward_pre_hook(lambda mod, args: tuple(a.cpu() if torch.is_tensor(a) else a for a in args))
        ple.register_forward_hook(lambda mod, args, aus: aus.to("cuda"))
        self.model = m

    def fragen(self, text: str, audio: np.ndarray | None = None, max_neu: int = 200) -> str:
        inhalt = ([{"type": "audio"}] if audio is not None else []) + [{"type": "text", "text": text}]
        roh = self.processor.apply_chat_template([{"role": "user", "content": inhalt}], tokenize=False,
                                                 add_generation_prompt=True)
        x = self.processor(text=roh, audio=[audio] if audio is not None else None, return_tensors="pt")
        x = x.to("cuda", dtype=self.model.dtype)
        aus = self.model.generate(**x, max_new_tokens=max_neu, do_sample=False)
        return self.processor.decode(aus[0][x["input_ids"].shape[-1]:], skip_special_tokens=True).strip()


def json_aus(antwort: str) -> dict:
    """Erstes {...} der Antwort (Gemma setzt gern ```json drumherum); {} wenn keins lesbar ist."""
    m = re.search(r"\{.*?\}", antwort, re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        return {}


def _song(t: dict) -> str:
    return f"„{t['titel']}“ ({t['bpm']:.0f} BPM, Tonart {t.get('camelot') or '?'})"


def beschreibung(m: dict) -> str:
    """Ein bewerteter Fall als Text (nur, was die Regie wusste und eingestellt hat)."""
    i = m["info"]
    zeilen = [f"Song A: {_song(m['a'])}", f"Song B: {_song(m['b'])}",
              f"Mix-Stil: {m['stil']}, Experimente: {m.get('experimente', 'klassisch')}, "
              f"Song A spielt {'nur bis nach dem Drop' if m['spielanteil'] == 'schnell' else 'lang'}"
              + (", Übergang per WEITER-Knopf mitten im Song" if m.get("weiter") else ""),
              f"Übergang: Rezept „{i['rezept']}“, {i['takte']} Takte ({i['blende_s']:.0f} s), "
              f"{'mit' if i['stems'] else 'ohne'} Stems, Tempo {'angeglichen' if i['sync'] else 'NICHT angeglichen'}, "
              f"Energiesprung B - A: {i.get('energie_schritt', 0):+.1f} dB",
              f"Begründung der Regie: {i['grund']}"]
    if i.get("einst"):
        zeilen.append("Einstellungen: " + ", ".join(f"{k}={v}" for k, v in i["einst"].items()
                                                     if v not in ("keiner", -1, 0)))
    return "\n".join(zeilen)


def _bereiche(maske) -> str:
    """Takte mit 1 als Bereiche "16-31, 48-63" (Luecken bis 2 Takte ueberbrueckt)."""
    takte = np.flatnonzero(np.asarray(maske) > 0)
    if not takte.size:
        return "keine"
    teile, von = [], takte[0]
    for x, y in zip(takte[:-1], takte[1:]):
        if y - x > 3:
            teile.append(f"{von}-{x}")
            von = y
    return ", ".join(teile + [f"{von}-{takte[-1]}"])


def aufbau(p) -> str:
    """Songaufbau aus dem Profil: Abschnitte mit Starttakt, Gesang in Takten."""
    et = p.etiketten()
    teile = [f"Takt {p.phrase_start(q)} {x}" for q, x in enumerate(et) if q == 0 or x != et[q - 1]]
    g = p.gesang()
    return f"{p.n} Takte; " + ", ".join(teile) + ("" if g is None else f"; Gesang in Takten {_bereiche(g)}")


def plan_text(k: int, plan, pa, pb) -> str:
    ta, tb = pa.takt_bei(plan.aus_s), pb.takt_bei(plan.ein_s)
    la = pa.etiketten()[min(len(pa.etiketten()) - 1, pa.phrase_von(ta))]
    lb = pb.etiketten()[min(len(pb.etiketten()) - 1, pb.phrase_von(tb))]
    return (f"Plan {k}: {plan.rezept} (Stufe {plan.einst.experimente}), {plan.takte} Takte; A ab Takt {ta} ({la}), "
            f"B ab Takt {tb} ({lb}); {plan.grund}")


def waehler(g: Gemma):
    """Fuer live.Wiedergabe.plan_waehler: Gemma waehlt unter den Plaenen der Regie (Stufe 2)."""

    def waehlen(plaene, a, pa, b, pb, einst) -> tuple[int, str]:
        t = lambda e: {"titel": e.titel, "bpm": e.bpm, "camelot": e.camelot}  # noqa: E731
        frage = (REGELN + f"\n\nSong A: {_song(t(a))}\n  Aufbau: {aufbau(pa)}\nSong B: {_song(t(b))}\n  Aufbau: "
                 f"{aufbau(pb)}\nMix-Stil des Hörers: {einst.modus} (kurz = schnelle Wechsel, lang = lange Blenden)."
                 "\n\nDie Regie schlägt diese Übergänge vor:\n"
                 + "\n".join(plan_text(k, p, pa, pb) for k, p in enumerate(plaene))
                 + "\n\nWähle den Übergang, der für genau diese zwei Songs am besten klingt. Antworte nur mit JSON: "
                 "{\"plan\": <Nummer>, \"grund\": \"<ein Satz>\"}")
        antwort = json_aus(g.fragen(frage))
        k = antwort.get("plan")
        if not isinstance(k, int) or not 0 <= k < len(plaene):
            return 0, f"(keine gültige Wahl, Plan 0 der Regie) {antwort}"
        return k, str(antwort.get("grund", ""))

    return waehlen


def _clip_16k(ordner: str, m: dict, laenge_s: float = 30.0) -> np.ndarray:
    """Bis 30 s Mono (16 kHz, so viel hoert Gemma 4) ab 4 s vor der Blende."""
    import soundfile as sf
    from scipy.signal import resample_poly

    x, rate = sf.read(str(ERGEBNISSE / ordner / "clips" / f"{m['nr']:03d}.flac"), dtype="float32")
    a = int(max(0.0, m["blende_von_s"] - 4.0) * rate)
    x = x[a:a + int(laenge_s * rate)].mean(axis=1)
    return resample_poly(x, 16000, rate).astype(np.float32)


def _spearman(x, y) -> float:
    from scipy.stats import spearmanr
    return float(spearmanr(x, y).statistic)


def noten(args) -> int:
    faelle = bewertete_faelle()
    if args.max:
        faelle = [f for k, f in enumerate(faelle) if k % max(1, len(faelle) // args.max) == 0][:args.max]
    alle = bewertete_faelle()
    ziel = ERGEBNISSE / "gemma-probe" / (f"noten-{args.modell.split('/')[-1]}{'-audio' if args.audio else ''}"
                                         f"{f'-bsp{args.beispiele}' if args.beispiele else ''}.json")
    ziel.parent.mkdir(parents=True, exist_ok=True)
    fertig = json.loads(ziel.read_text(encoding="utf-8")) if ziel.exists() else {}
    g = Gemma(args.modell, audio=args.audio)
    frage = (REGELN + "\n\nSchätze, welche Note (1 = schlecht, 5 = perfekt) ein anspruchsvoller Hörer "
             "diesem Übergang gibt" + (" (Ausschnitt: 4 s vor der Blende bis höchstens 30 s)" if args.audio else "")
             + ". Antworte nur mit JSON: {\"note\": <1-5>, \"grund\": \"<ein Satz>\"}\n\n")
    for k, (ordner, m, b) in enumerate(faelle):
        schluessel = f"{ordner}/{m['nr']}"
        if schluessel in fertig:
            continue
        t0 = time.perf_counter()
        bsp = beispiele(alle, ordner, args.beispiele) if args.beispiele else ""
        antwort = g.fragen(frage + bsp + beschreibung(m), _clip_16k(ordner, m) if args.audio else None)
        note = json_aus(antwort).get("note")
        fertig[schluessel] = {"gemma": note if note in (1, 2, 3, 4, 5) else None, "echt": b["note"],
                              "rezept": m["info"]["rezept"], "antwort": antwort[:400]}
        ziel.write_text(json.dumps(fertig, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{k + 1}/{len(faelle)} {schluessel}: Gemma {note} / echt {b['note']} ({time.perf_counter() - t0:.0f} s)",
              flush=True)
    print(auswerten(fertig))
    return 0


def beispiele(alle: list, ohne_ordner: str, n: int) -> str:
    """n bewertete Faelle aus ANDEREN Runden (je Note gleich viele, fest gelost): lernt Gemma den Geschmack
    des Hoerers aus seinen eigenen Noten und Kommentaren?"""
    import random

    rng = random.Random(f"{ohne_ordner}-{n}")
    je_note = {k: [f for f in alle if f[0] != ohne_ordner and f[2]["note"] == k] for k in range(1, 6)}
    wahl = [f for k in range(1, 6) for f in rng.sample(je_note[k], min(len(je_note[k]), n // 5))]
    rng.shuffle(wahl)
    return "So hat dieser Hörer frühere Übergänge bewertet:\n\n" + "\n\n".join(
        beschreibung(m) + f"\nNote: {b['note']}" + (f" – Kommentar: {b['kommentar']}" if b.get("kommentar") else "")
        for _, m, b in wahl) + "\n\nNeuer Übergang:\n"


def auswerten(fertig: dict) -> str:
    gueltig = [v for v in fertig.values() if v["gemma"] is not None]
    if len(gueltig) < 5:
        return f"Zu wenig lesbare Antworten ({len(gueltig)}/{len(fertig)})."
    g = np.array([v["gemma"] for v in gueltig], float)
    e = np.array([v["echt"] for v in gueltig], float)
    # Vergleich ohne KI: Mittel der echten Noten desselben Rezepts, ohne den Fall selbst
    basis = []
    for k, v in enumerate(gueltig):
        rest = [w["echt"] for j, w in enumerate(gueltig) if j != k and w["rezept"] == v["rezept"]]
        basis.append(np.mean(rest) if rest else np.mean(e))
    basis = np.array(basis)
    return (f"Gemma: {len(gueltig)}/{len(fertig)} lesbar · Spearman {_spearman(g, e):+.2f} · "
            f"mittlerer Fehler {np.mean(np.abs(g - e)):.2f} · genau {np.mean(g == e):.0%} · ±1 {np.mean(np.abs(g - e) <= 1):.0%}"
            f"\nVergleich (Rezept-Mittel): Spearman {_spearman(basis, e):+.2f} · mittlerer Fehler {np.mean(np.abs(basis - e)):.2f}"
            f"\nGemma sagt im Mittel {g.mean():.2f}, echt {e.mean():.2f}")


# --- Stufe 3: Sprache -> Einstellungen -------------------------------------------------------------------

SAETZE = Path(__file__).with_name("gemma_saetze.json")
FELDER = {   # nur Felder, die sich in Worten sagen lassen, mit ihrer Bedeutung fuer Gemma
    "modus": {"kurz": "kurze, schnelle Blenden", "ausgewogen": "mittellange Blenden", "lang": "lange, fliessende Blenden"},
    "spielanteil": {"schnell": "frueh wechseln, gleich nach dem Drop", "lang": "Songs moeglichst ganz ausspielen"},
    "experimente": {"klassisch": "keine Effekte/Tricks", "kreativ": "ab und zu Effekte, Double Drops",
                    "wild": "viele Effekte, Double Drops, Backspins"},
    "harmonie": {"streng": "nur passende Tonarten", "locker": "Tonart bevorzugen", "aus": "Tonart egal"},
    "set_bogen": {"gleichmaessig": "gleichbleibende Energie", "aufbauen": "Energie steigt", "welle": "Energie auf und ab"},
}


def einstellungen_frage(satz: str) -> str:
    felder = "\n".join(f"- {f}: " + "; ".join(f"\"{w}\" = {t}" for w, t in werte.items()) for f, werte in FELDER.items())
    return ("Du steuerst einen DJ-Mixer. Der Nutzer sagt, wie er den Mix haben möchte. Übersetze seinen Satz in "
            "Änderungen an diesen Einstellungen (nur Felder, die der Satz wirklich anspricht; nichts raten):\n"
            f"{felder}\n\nAntworte nur mit JSON, z. B. {{\"modus\": \"lang\"}}; ändert der Satz nichts: {{}}.\n\n"
            f"Satz: „{satz}“")


def gueltig(antwort: dict) -> dict | None:
    """Nur erlaubte Felder und Werte (die Oberflaeche ist eine Vertrauensgrenze); sonst None."""
    if not isinstance(antwort, dict) or any(f not in FELDER or v not in FELDER[f] for f, v in antwort.items()):
        return None
    return antwort


def einstellungen_pruefen(args) -> int:
    saetze = json.loads(SAETZE.read_text(encoding="utf-8"))
    g = Gemma(args.modell)
    zeilen, exakt, ok = [], 0, 0
    for satz, soll in saetze:
        t0 = time.perf_counter()
        roh = g.fragen(einstellungen_frage(satz), max_neu=80)
        m = re.search(r"\{.*\}", roh, re.S)
        try:
            ist = gueltig(json.loads(m.group(0))) if m else None
        except json.JSONDecodeError:
            ist = None
        ok += ist is not None
        exakt += ist == soll
        zeilen.append({"satz": satz, "soll": soll, "ist": ist, "roh": roh[:200]})
        print(f"{'OK ' if ist == soll else 'NEIN'} {satz} -> {ist} ({time.perf_counter() - t0:.0f} s)", flush=True)
    ziel = ERGEBNISSE / "gemma-probe" / f"einstellungen-{args.modell.split('/')[-1]}.json"
    ziel.parent.mkdir(parents=True, exist_ok=True)
    n = len(saetze)
    ergebnis = {"exakt": exakt / n, "gueltig": ok / n, "tor": exakt / n >= 0.85, "faelle": zeilen}
    ziel.write_text(json.dumps(ergebnis, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"exakt {exakt}/{n} ({exakt / n:.0%}), gültig {ok}/{n} -> Tor (85 %) {'geschafft' if ergebnis['tor'] else 'verfehlt'}",
          flush=True)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="klangbild.gemma_probe")
    sub = p.add_subparsers(dest="befehl", required=True)
    n = sub.add_parser("noten", help="Gemma schaetzt die Noten der bewerteten Uebergaenge")
    n.add_argument("--modell", default="google/gemma-4-E2B-it")
    n.add_argument("--audio", action="store_true", help="den Clip mithoeren lassen")
    n.add_argument("--max", type=int, default=0, help="nur so viele Faelle (gleichmaessig verteilt)")
    n.add_argument("--beispiele", type=int, default=0, help="so viele bewertete Faelle anderer Runden mitgeben")
    s3 = sub.add_parser("einstellungen", help="Gemma uebersetzt Saetze in Mixer-Einstellungen (Stufe 3)")
    s3.add_argument("--modell", default="google/gemma-4-E2B-it")
    args = p.parse_args()
    return einstellungen_pruefen(args) if args.befehl == "einstellungen" else noten(args)


if __name__ == "__main__":
    raise SystemExit(main())
