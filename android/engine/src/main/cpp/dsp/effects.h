// Effektanteil einer Blende: Echo, Delay, Ping-Pong und Hall (BAUPLAN-ANDROID T5.6).
//
// Port von uebergang._nass. Die Hall-Impulsantwort ist ein Asset (hall_ir.f32): ihr Zufall
// (`np.random.default_rng(7)`) wird nicht nachgebaut (§5.9). Stereo float32 interleaved.
//
// Nur fuer Baker und Host-Test, nie im Audio-Callback.
#pragma once

#include <span>
#include <string_view>
#include <vector>

namespace klangbild::dsp {

/// Nachhallzeit der Hall-IR in Sekunden (uebergang.HALL_S); die IR ist 2,4 s + 20 ms Vorverzoegerung lang.
inline constexpr double kHallSeconds = 2.4;

/// `uebergang._nass(typ, send, schlag_n)`: der nasse Anteil des Effekts, laenger als `send`
/// (die Fahne klingt aus). `type` ist "hall" oder Art + Prozent: "echo50", "delay75", "pingpong100", ...
/// `beatN` ist die Laenge eines Schlags in Frames (double: kann halbe Frames haben), `hallIr` die
/// Impulsantwort (Stereo, interleaved; nur fuer "hall" gebraucht).
/// Wirft `std::invalid_argument` bei unbekannter Art.
std::vector<float> wetSignal(std::string_view type, std::span<const float> send, double beatN, std::span<const float> hallIr);

}  // namespace klangbild::dsp
