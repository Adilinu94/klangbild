# ADR-006 · LiteRT/MediaPipe statt MediaPipe LLM Inference

**Status:** angenommen · ergänzt durch [ADR-015](ADR-015-stimmung-per-zero-shot.md) (08.10.2026)
**Datum:** 06.10.2026

## Kontext

Wir brauchen auf dem Gerät ein Einbettungsmodell (EmbeddingGemma 2) und ein
Sprachmodell (Gemma 4). Es gibt mehrere Laufzeitwege.

## Entscheidung

- **Einbetten/Suchen:** MediaPipe Tasks **Universal Embedder** + **Semantic
  Retriever**.
- **Sprachmodell:** **LiteRT-LM** mit Gemma 4 (E2B/E4B).
- **Rückfall:** ONNX Runtime Mobile oder llama.cpp (beide MIT).

## Alternativen

1. **MediaPipe LLM Inference API.** Verworfen: für Android/iOS eingestellt
   (maintenance-only).
2. **LiteRT-LM.** Gewählt (Production-ready, Apache-2.0).
3. **ONNX Runtime Mobile / llama.cpp.** Als Rückfall behalten.

## Begründung

- Die MediaPipe LLM Inference API ist offiziell abgekündigt; neue Android-Projekte
  sollen auf LiteRT-LM wechseln.
- LiteRT und LiteRT-LM sind Apache-2.0 und laufen auf CPU/GPU/NPU.
- MediaPipe Universal Embedder passt direkt zu EmbeddingGemma 2.

## Konsequenzen

- Die Modell-Gewichte (Gemma-Lizenz) sind getrennt von der Laufzeit zu betrachten
  (kommerziell erlaubt, mit Auflagen).
- Genau **eine** Datei kapselt die Laufzeit (Fassade), damit ein API-Wechsel
  billig bleibt.

## Belege

- `ANDROID-AUTODJ-TOOLCHAIN-2026.md` (Abschnitt 6)
- `WISSEN-POWERAMP-ARCHITEKTUR.md` Abschnitt 16.1

## Ergänzung 08.10.2026

**LiteRT-LM unterstützt ab v0.18.0 EmbeddingGemma 2 multimodal** – also
Text, Vision **und Audio** – mit MRL-Kürzung in **Python, Kotlin, Swift, Web
(JavaScript) und C++**. Dazu gehören `litert-lm import` für den Import eigener
Modelle und ein OpenAI-kompatibler `/v1/embeddings`-Endpoint. Google kündigt
außerdem ML-Kit-APIs auf LiteRT-Basis an.

**Folge für uns:** Der Android-Pfad für die Einbettung ist **LiteRT-LM**, nicht
eine eigene ONNX-Konvertierung. Ein ONNX-Export existiert zwar
(`onnx-community/embeddinggemma-2-ONNX`), aber Revision, Tokenizer und
Audio-Vorverarbeitung müssten aufwändig gegen die Referenz verifiziert werden.
Der Rückfall ONNX Runtime Mobile / llama.cpp (beide MIT) bleibt.
