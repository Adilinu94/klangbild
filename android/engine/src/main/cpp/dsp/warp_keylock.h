// Keylock-Warp mit WSOLA-Naehten (BAUPLAN-ANDROID T6.3).
//
// Port von uebergang._warp_keylock: Takte mit (fast) gleichem Faktor in einem Dehn-Aufruf,
// Naht zwischen zwei Aufrufen per WSOLA ausgerichtet und korrelationsnormiert ueberblendet.
//
// Nur fuer Baker und Host-Test, nie im Audio-Callback.
#pragma once

#include <span>
#include <vector>

namespace klangbild::dsp {

/// `uebergang._warp_keylock(audio, quell, ziel, rand_vorn, rand_hinten)`. `quell`/`ziel` sind
/// Frames (wie in `warp`), Stereo interleaved. Ausgabelaenge: `ziel.back()` Frames.
std::vector<float> warpKeylock(std::span<const float> audio, std::span<const long long> quell,
                               std::span<const long long> ziel, bool randVorn, bool randHinten,
                               int rate = 44100);

}  // namespace klangbild::dsp
