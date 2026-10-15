"""MAEB-Musik-Tasks mit EmbeddingGemma 2 (Audio-Encoder) lokal messen.

GTZANGenre (Klassifikation, 10 Genres) + GTZANAudioReranking (Retrieval).
Modell: google/embeddinggemma-2, nur Text- + Audio-Encoder (wie ADR-015).
Dauert auf CPU eine Weile - Fortschritt wird geloggt.
"""
import os
import sys
import traceback

# Batch-groesse klein halten: 1000 Audio-Clips x 30 s im Speicher war der Grund
# fuer den vorherigen Abbruch (OOM). 8 Clips pro Schritt halten das RAM im Rahmen.
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

import warnings

warnings.filterwarnings("ignore")
import mteb
from mteb import MTEB
from mteb.models import SentenceTransformerEncoderWrapper
from sentence_transformers import SentenceTransformer

HF_HOME = os.path.join(os.path.dirname(__file__), ".cache", "huggingface")
os.environ["HF_HOME"] = HF_HOME

TASKS = ["GTZANGenre", "GTZANAudioReranking"]
OUT = os.path.join(os.path.dirname(__file__), "ergebnisse", "maeb-musik")


def log(msg):
    print(msg, flush=True)


# datasets dekodiert Audio-Spalten nur ueber torchcodec. Das Windows-Rad von
# torchcodec bringt keine FFmpeg-DLLs mit (libtorchcodec_core*.dll laesst sich
# nicht laden). soundfile/libssndfile ist dagegen voll funktionsfaehig, also den
# Decode-Pfad auf soundfile umlegen. sentence-transformers verarbeitet das
# klassische {"array": ..., "sampling_rate": ...}-Format direkt.
import datasets.features.audio as _ds_audio


def _decode_audio_via_soundfile(self, value, token_per_repo_id=None):
    import io

    import numpy as np
    import soundfile as sf

    array, sampling_rate = sf.read(
        io.BytesIO(value["bytes"]), dtype="float32", always_2d=False
    )
    if array.ndim > 1:
        array = array.mean(axis=1)
    if self.sampling_rate and self.sampling_rate != sampling_rate:
        import soxr

        array = soxr.resample(array, sampling_rate, self.sampling_rate)
        sampling_rate = self.sampling_rate
    return {"array": array, "sampling_rate": sampling_rate}


_ds_audio.Audio.decode_example = _decode_audio_via_soundfile
log("Audio-Decode via soundfile aktiv.")

log("Lade Modell ...")
model = SentenceTransformer(
    "google/embeddinggemma-2",
    model_kwargs={"torch_dtype": "float32"},
    config_kwargs={"vision_config": None},
    trust_remote_code=True,
)
log("Modell da.")

# MTEB leitet die Modalities des Modells nur aus dem ModelMeta-Default ["text"] ab,
# wenn ein SentenceTransformer-Objekt uebergeben wird - unabhaengig davon, dass das
# Modell audio kann (hier verifiziert: Audio-Encode ergibt 768-dim Embeddings).
# Ohne audio in modalities werden alle Audio-Tasks stumm uebersprungen
# ("only supports [...]"). Daher den Wrapper direkt bauen und modalities patchen.
wrapper = SentenceTransformerEncoderWrapper(model)
mods = wrapper.mteb_model_meta.modalities or []
if "audio" not in mods:
    wrapper.mteb_model_meta.modalities = sorted(set(mods) | {"audio"})
log(f"Wrapper-Modalities: {wrapper.mteb_model_meta.modalities}")

tasks = []
for name in TASKS:
    t = mteb.get_task(name)
    log(f"Task geladen: {name} (eval_splits={t.eval_splits})")
    tasks.append(t)

log("Messe ...")
evaluation = MTEB(tasks=tasks)
try:
    ergebnis = evaluation.run(
        wrapper,
        output_folder=OUT,
        encode_kwargs={"batch_size": 8},
    )
    log(f"Anzahl Ergebnisse: {len(ergebnis)}")
    for r in ergebnis:
        log(f"{r.task_name} -> {r.scores}")
    if not ergebnis:
        log("HINWEIS: leere Ergebnismenge - Tasks ohne auswertbare Splits?")
    for t in tasks:
        log(f"Task-Status: {t.metadata.name} data_loaded={t.data_loaded}")
except Exception:
    log("FEHLER:")
    log(traceback.format_exc())
log("SCRIPT ENDE")
