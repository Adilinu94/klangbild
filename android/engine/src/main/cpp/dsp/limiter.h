// Limiter fuer die gebackene Blende (BAUPLAN-ANDROID T5.7/M6).
//
// Port von uebergang._begrenzen: zwei laute Songs zusammen ueberschreiten 0 dBFS, die Soundkarte
// schneidet hart ab. Die Verstaerkung sinkt 10 ms vor einer Spitze und kehrt geglaettet zurueck.
//
// Nur fuer Baker und Host-Test, nie im Audio-Callback.
#pragma once

#include <vector>

namespace klangbild::dsp {

/// uebergang.DECKE: -0,3 dBFS.
inline constexpr double kDecke = 0.966;

/// `uebergang._begrenzen(x, bis, decke)` in place: begrenzt `x[:bis]` (Frames), Stereo interleaved.
void begrenzen(std::vector<float>& x, long long bis, double decke = kDecke, int rate = 44100, int channels = 2);

}  // namespace klangbild::dsp
