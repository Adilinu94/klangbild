// Loops in der Blende (BAUPLAN-ANDROID T5.8).
//
// Port von uebergang._achtel, uebergang._loopen und uebergang.loop_info.
// Der Loop haelt das Outro von A fest; bei Tempo-Rampe wird jedes Stueck ueber
// `warp` auf seinen Platz im Raster gedehnt (Runde 19).
//
// Nur fuer Baker und Oberflaeche, nie im Audio-Callback.
#pragma once

#include <span>
#include <vector>

#include "dsp/automation.h"   // LoopSection
#include "dsp/settings.h"

namespace klangbild::dsp {

/// `uebergang._achtel`: Taktgrenzen `taktN` in Achtel-Samples (8 je Takt, letzte Grenze schliesst).
std::vector<long long> eighthGrid(std::span<const double> taktN);

/// `uebergang._loopen`: setzt die Loop-Abschnitte `plan` auf `a`, Naht je Sprung equipotent
/// (256 Samples). Laenge wie `a`. Wirft bei leerem `plan` (IndexError im Prototyp).
std::vector<float> loopen(std::span<const float> a, std::span<const double> taktN,
                          std::span<const LoopSection> plan, bool keylock = true, int rate = 44100);

/// Ein Loop-Abschnitt in Blendensekunden fuer die Anzeige.
struct LoopInfo {
    double von = 0.0;
    double bis = 0.0;
    double quelle = 0.0;
    double laenge = 0.0;
};

/// `uebergang.loop_info`: nur bei `art == "eigen"` und gesetztem Loop; sonst leer.
std::vector<LoopInfo> loopInfo(const Settings& settings, std::span<const double> taktS);

}  // namespace klangbild::dsp
