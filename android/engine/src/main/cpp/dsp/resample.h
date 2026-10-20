// Tempoangleich per Resampling (BAUPLAN-ANDROID T6.2, ADR-014).
//
// Port von resample.resample_linear und resample.resample sowie mix._auffuellen.
// Linear wie die Referenz: Android rechnet nie mit soxr (nur der Desktop-Hoertest darf das).
//
// Nur fuer Baker und Host-Test, nie im Audio-Callback.
#pragma once

#include <cstddef>
#include <span>
#include <vector>

namespace klangbild::dsp {

/// `resample.resample_linear`: liest `signal` um `faktor` schneller ab (lineare Interpolation).
/// `faktor > 1` macht die Ausgabe kuerzer und hoeher; `faktor == 1` gibt eine Kopie.
std::vector<float> resampleLinear(std::span<const float> signal, double faktor);

/// `resample.resample`: wie oben, aber je Kanal (interleaved, `channels` Kanaele).
std::vector<float> resample(std::span<const float> signal, int rate, double faktor, int channels = 2);

/// `mix._auffuellen`: bringt ein Signal exakt auf `frames` Frames (kuerzen oder mit Stille fuellen).
std::vector<float> padTo(std::vector<float> signal, std::size_t frames, int channels = 2);

}  // namespace klangbild::dsp
