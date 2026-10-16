"""Kritiker: schaetzt die Note (1-5) eines Uebergangs aus seinen Merkmalen (BAUPLAN-UEBERGAENGE §2.2-2.4).

Training (nur PC, sklearn): flache Gradient-Boosting-Baeume auf dem Datensatz (datensatz.py), ehrlich
gemessen mit Leave-one-round-out gegen das Rezept-Mittel. Eingeschaltet ("aktiv") wird er nur, wenn er das
Tor schafft. Gespeichert werden die Baeume als JSON; die Auswertung (`Kritiker`) liest nur dieses JSON -
so laeuft sie auch auf Android (Critic.kt, M3/M7).

    python -m klangbild kritiker --trainieren     # -> ergebnisse/kritiker/{modell.json, bericht.md}

Zwei Modelle: "vorher" (Merkmale vor dem Backen, sortiert die Plaene der Regie) und "nachher" (mit der
Lautheit der fertigen Blende, Selbstkontrolle: unter NACHHER_MIN faellt der Plan durch).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from . import config
from .datensatz import ERGEBNIS

ZIEL = config.PROTOTYP_WURZEL / "ergebnisse" / "kritiker"
PARAMS = dict(max_depth=3, max_iter=200, learning_rate=0.05, l2_regularization=1.0)
NACHHER_MIN = 2.0
TOR = {"mae_vorsprung": 0.05, "spearman": 0.30, "schlecht_im_drittel": 0.5}


# --- Auswertung (auch fuer Android: nur dieses Stueck wird portiert) ------------------------------

def _baum(b: dict, x: list[float]) -> float:
    k = 0
    while not b["blatt"][k]:
        v = x[b["f"][k]]
        links = b["fehlt_links"][k] if math.isnan(v) else v <= b["s"][k]
        k = b["l"][k] if links else b["r"][k]
    return b["wert"][k]


def schaetzen(modell: dict, m: dict) -> float:
    """Note aus den Merkmalen (dict wie datensatz.merkmale); fehlende One-hot-Merkmale = 0, sonst NaN."""
    x = [m.get(n, 0.0 if "=" in n else math.nan) for n in modell["namen"]]
    return float(min(5.0, max(1.0, modell["basis"] + sum(_baum(b, x) for b in modell["baeume"]))))


class Kritiker:
    """Liest modell.json; `vorher`/`nachher` schaetzen die Note eines Plans bzw. einer fertigen Blende."""

    def __init__(self, daten: dict):
        self.daten = daten

    @classmethod
    def laden(cls, pfad: Path = ZIEL / "modell.json", nur_aktiv: bool = True) -> "Kritiker | None":
        try:
            d = json.loads(pfad.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return cls(d) if d.get("aktiv") or not nur_aktiv else None

    def vorher(self, m: dict) -> float:
        return schaetzen(self.daten["vorher"], m)

    def nachher(self, m: dict) -> float:
        return schaetzen(self.daten["nachher"], m)


# --- Training ---------------------------------------------------------------------------------------

def _x(zeilen: list[dict], namen: list[str]) -> np.ndarray:
    return np.array([[z["merkmale"].get(n, 0.0 if "=" in n else np.nan) for n in namen] for z in zeilen], float)


def _modell(zeilen: list[dict], namen: list[str]):
    from sklearn.ensemble import HistGradientBoostingRegressor

    return HistGradientBoostingRegressor(**PARAMS, random_state=0).fit(
        _x(zeilen, namen), [z["note"] for z in zeilen], sample_weight=[z["gewicht"] for z in zeilen])


def exportieren(model, namen: list[str]) -> dict:
    """Baeume als JSON (Merkmal, Schwelle, Kinder, Blattwert) - unabhaengig von sklearn auswertbar."""
    baeume = []
    for iteration in model._predictors:
        k = iteration[0].nodes
        baeume.append({"f": k["feature_idx"].tolist(), "s": [float(v) for v in k["num_threshold"]],
                       "l": k["left"].tolist(), "r": k["right"].tolist(), "blatt": k["is_leaf"].astype(bool).tolist(),
                       "fehlt_links": k["missing_go_to_left"].astype(bool).tolist(),
                       "wert": [float(v) for v in k["value"]]})
    return {"namen": namen, "basis": float(np.ravel(model._baseline_prediction)[0]), "baeume": baeume}


def _spearman(a, b) -> float:
    from scipy.stats import spearmanr

    return float(spearmanr(a, b).statistic)


def messen(zeilen: list[dict], namen: list[str]) -> dict:
    """Leave-one-round-out ueber die Hoertest-Runden (Daumen-Daten nur im Training) gegen das Rezept-Mittel."""
    runden = sorted({z["runde"] for z in zeilen if not z["runde"].startswith("live-")})
    test, vorh, basis = [], [], []
    rezept = lambda z: next((k for k in z["merkmale"] if k.startswith("rezept=")), "?")   # noqa: E731
    for r in runden:
        rest = [z for z in zeilen if z["runde"] != r]
        dran = [z for z in zeilen if z["runde"] == r]
        model = _modell(rest, namen)
        vorh += list(np.clip(model.predict(_x(dran, namen)), 1, 5))
        mittel = {}
        for z in rest:
            mittel.setdefault(rezept(z), []).append(z["note"])
        alle = float(np.mean([z["note"] for z in rest]))
        basis += [float(np.mean(mittel.get(rezept(z), [alle]))) for z in dran]
        test += dran
    echt = np.array([z["note"] for z in test], float)
    vorh, basis = np.array(vorh), np.array(basis)
    drittel = np.percentile(vorh, 100 / 3)
    schlecht = echt <= 2
    je_runde = {r: {"n": int(sum(z["runde"] == r for z in test)),
                    "mae": float(np.mean([abs(v - z["note"]) for v, z in zip(vorh, test) if z["runde"] == r])),
                    "mae_basis": float(np.mean([abs(v - z["note"]) for v, z in zip(basis, test) if z["runde"] == r]))}
                for r in runden}
    fehler = sorted(zip(np.abs(vorh - echt), vorh, test), key=lambda t: -t[0])[:10]
    return {"n": len(test), "mae": float(np.mean(np.abs(vorh - echt))), "mae_basis": float(np.mean(np.abs(basis - echt))),
            "spearman": _spearman(vorh, echt), "spearman_basis": _spearman(basis, echt),
            "schlecht_im_drittel": float(np.mean(vorh[schlecht] <= drittel)) if schlecht.any() else 0.0,
            "je_runde": je_runde,
            "fehler": [{"runde": z["runde"], "nr": z["nr"], "echt": z["note"], "geschaetzt": round(float(v), 2),
                        "rezept": next((k[7:] for k in z["merkmale"] if k.startswith("rezept=")), "?"),
                        "kommentar": z.get("kommentar", "")[:80]} for _, v, z in fehler]}


def tor(w: dict) -> bool:
    return (w["mae"] <= w["mae_basis"] - TOR["mae_vorsprung"] and w["spearman"] >= TOR["spearman"]
            and w["schlecht_im_drittel"] >= TOR["schlecht_im_drittel"])


def wichtig(zeilen: list[dict], namen: list[str], n: int = 12) -> list[tuple[str, float]]:
    from sklearn.inspection import permutation_importance

    model = _modell(zeilen, namen)
    x, y = _x(zeilen, namen), [z["note"] for z in zeilen]
    r = permutation_importance(model, x, y, n_repeats=5, random_state=0, scoring="neg_mean_absolute_error")
    return sorted(zip(namen, r.importances_mean.tolist()), key=lambda t: -t[1])[:n]


def trainieren(zeilen: list[dict]) -> tuple[dict, str]:
    """(modell.json-Inhalt, Bericht). Zwei Merkmals-Varianten: vorher (ohne Ergebnis) und nachher (mit)."""
    alle = sorted({k for z in zeilen for k in z["merkmale"]})
    varianten = {"vorher": [n for n in alle if n not in ERGEBNIS],
                 # dritte Variante (nur Bericht): ohne Abschnitts-Etiketten, weniger Merkmale gegen Ueberanpassung
                 "vorher_kompakt": [n for n in alle if n not in ERGEBNIS and not n.startswith(("a_et=", "b_et="))],
                 "nachher": alle}
    gemessen = {k: messen(zeilen, namen) for k, namen in varianten.items()}
    aktiv = tor(gemessen["vorher"])
    modell = {"aktiv": aktiv, "tor": TOR, "n": len(zeilen),
              **{k: exportieren(_modell(zeilen, varianten[k]), varianten[k]) for k in ("vorher", "nachher")},
              "messung": {k: {x: v for x, v in w.items() if x not in ("fehler", "je_runde")} for k, w in gemessen.items()}}
    aus = ["# Kritiker: Leave-one-round-out gegen das Rezept-Mittel", "",
           f"{len(zeilen)} Übergänge, {len([z for z in zeilen if z['runde'].startswith('live-')])} davon Daumen "
           f"(Gewicht 0,5). Tor (Vorher-Modell): MAE ≤ Basis − {TOR['mae_vorsprung']}, Spearman ≥ {TOR['spearman']}, "
           f"≥ {TOR['schlecht_im_drittel']:.0%} der Noten ≤ 2 im schlechtesten Drittel der Schätzungen.", "",
           f"**Ergebnis: Kritiker {'AN (Tor geschafft)' if aktiv else 'AUS (Tor verfehlt)'}**", "",
           "| Variante | MAE | MAE Rezept-Mittel | Spearman | Spearman Rezept-Mittel | Noten ≤ 2 im schlechtesten Drittel | Tor |",
           "|---|---|---|---|---|---|---|"]
    for k, w in gemessen.items():
        aus.append(f"| {k} | {w['mae']:.2f} | {w['mae_basis']:.2f} | {w['spearman']:+.2f} | {w['spearman_basis']:+.2f} "
                   f"| {w['schlecht_im_drittel']:.0%} | {'ja' if tor(w) else 'nein'} |")
    aus += ["", "## Je Runde (vorher)", "", "| Runde | n | MAE | MAE Rezept-Mittel |", "|---|---|---|---|"]
    aus += [f"| {r} | {x['n']} | {x['mae']:.2f} | {x['mae_basis']:.2f} |" for r, x in gemessen["vorher"]["je_runde"].items()]
    aus += ["", "## Wichtigste Merkmale (Permutation, nachher-Modell auf allen Daten)", ""]
    aus += [f"- {n}: {v:+.3f}" for n, v in wichtig(zeilen, varianten["nachher"])]
    aus += ["", "## Die 10 größten Fehlschätzungen (vorher)", "", "| Runde | Fall | Note | geschätzt | Rezept | Kommentar |",
            "|---|---|---|---|---|---|"]
    aus += [f"| {f['runde'][-7:]} | {f['nr']} | {f['echt']} | {f['geschaetzt']} | {f['rezept']} | {f['kommentar']} |"
            for f in gemessen["vorher"]["fehler"]]
    return modell, "\n".join(aus) + "\n"


def kommando(args) -> int:
    from . import datensatz

    if getattr(args, "trainieren", False) or not datensatz.ZIEL.exists():
        datensatz.bauen()
    modell, bericht = trainieren(datensatz.laden())
    ZIEL.mkdir(parents=True, exist_ok=True)
    (ZIEL / "modell.json").write_text(json.dumps(modell), encoding="utf-8")
    (ZIEL / "bericht.md").write_text(bericht, encoding="utf-8")
    print(f"Kritiker {'AN' if modell['aktiv'] else 'AUS (Tor verfehlt)'} -> {ZIEL / 'bericht.md'}", flush=True)
    return 0
