"""Einbettung mit EmbeddingGemma 2 (ADR-015, Roadmap Phase 0.1).

Feste Vorgaben, damit der Test aussagekraeftig bleibt:
- nur Text- und Audio-Encoder laden (`vision_config=None`) -> 570 M Parameter
- Ausgabe 256 Dimensionen (MRL), danach **re-normalisieren**
- Rechnung in bfloat16 (falls die Maschine es kann) oder float32, **nie float16**
- Text bekommt ein symmetrisches Task-Praefix, Audio **kein** Praefix

`--pseudo` erzeugt deterministische Ersatzvektoren (aus dem Datei-Hash). Damit
lassen sich Pipeline und Bewertungsoberflaeche ohne Modelldownload testen. Sie
werden mit `modell_version="pseudo"` markiert und duerfen **nie** in ein
Torergebnis einfliessen.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from . import config

_MODELL = None


class EinbettungFehler(RuntimeError):
    pass


def _rechnen_typ():
    try:
        import torch
    except ImportError:
        return None
    if torch.cuda.is_available() and torch.cuda.is_bf16_supported():
        return torch.bfloat16
    return torch.float32


def modell_laden():
    """Laedt EmbeddingGemma 2 in der festgelegten Konfiguration."""
    global _MODELL
    if _MODELL is not None:
        return _MODELL
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as fehler:
        raise EinbettungFehler(
            "sentence-transformers fehlt (>= 6.1.0). Installation:\n"
            "  python -m pip install 'sentence-transformers>=6.1.0' torch\n"
            f"(Ursache: {fehler})"
        ) from fehler

    kwargs = {}
    typ = _rechnen_typ()
    if typ is not None:
        kwargs["model_kwargs"] = {"torch_dtype": typ}
    _MODELL = SentenceTransformer(
        config.EINBETTUNG_MODELL,
        truncate_dim=config.EINBETTUNG_DIM,
        config_kwargs=dict(config.EINBETTUNG_DEAKTIVIERTE_ENCODER),
        **kwargs,
    )
    return _MODELL


def _normalisieren(vektor: np.ndarray) -> np.ndarray:
    vektor = np.asarray(vektor, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(vektor))
    return vektor if norm <= 0 else (vektor / norm).astype(np.float32)


def _kodieren(modell, eingabe) -> np.ndarray:
    """Robuster Aufruf der multimodalen encode-Schnittstelle."""
    versuche = (
        lambda: modell.encode(eingabe),
        lambda: modell.encode([eingabe])[0],
        lambda: modell.encode(eingabe, normalize_embeddings=True),
    )
    letzter = None
    for versuch in versuche:
        try:
            return np.asarray(versuch(), dtype=np.float32).reshape(-1)
        except Exception as fehler:  # noqa: BLE001 - Schnittstelle variiert je Version
            letzter = fehler
    raise EinbettungFehler(
        "encode() hat fuer diese Eingabe keine Vektorform geliefert. Bitte die "
        "Audio-Schnittstelle der installierten sentence-transformers-Version pruefen. "
        f"Letzter Fehler: {letzter}"
    )


def audio_einbetten(clip_pfad: str | Path) -> np.ndarray:
    """Einbettung eines Audio-Ausschnitts (kein Praefix)."""
    modell = modell_laden()
    clip_pfad = str(clip_pfad)
    vektor = _kodieren(modell, {"audio": clip_pfad})
    if vektor.size != config.EINBETTUNG_DIM:
        # Manche Versionen liefern die volle Dimension trotz truncate_dim.
        vektor = vektor[: config.EINBETTUNG_DIM]
    return _normalisieren(vektor)


def text_einbetten(text: str, praefix: str | None = None) -> np.ndarray:
    """Einbettung eines Textes mit symmetrischem Task-Praefix."""
    modell = modell_laden()
    praefix = praefix or config.EINBETTUNG_TRAINIERTEXT_PRAEFIX
    try:
        vektor = modell.encode(text, prompt_name=praefix)
    except Exception:  # noqa: BLE001 - aeltere Versionen kennen prompt_name nicht
        vektor = _kodieren(modell, text)
    vektor = np.asarray(vektor, dtype=np.float32).reshape(-1)
    return _normalisieren(vektor[: config.EINBETTUNG_DIM])


def pseudo_vektor(clip_pfad: str | Path, dim: int = config.EINBETTUNG_DIM) -> np.ndarray:
    """Deterministischer Ersatzvektor zum Testen der Mechanik (nie fuer das Tor)."""
    kennung = hashlib.sha256(Path(clip_pfad).name.encode("utf-8")).digest()
    rng = np.random.default_rng(int.from_bytes(kennung[:8], "big"))
    return _normalisieren(rng.standard_normal(dim).astype(np.float32))
