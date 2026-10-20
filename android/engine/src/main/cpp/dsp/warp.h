// Beat-Warp: einen Abschnitt auf ein Taktziel ziehen (BAUPLAN-ANDROID T6.2).
//
// Port von uebergang.warp. Der lineare Weg (Keylock aus) ist fertig; der Keylock-Weg
// braucht Signalsmith Stretch (T6.3) und wirft hier, sobald ein Takt mehr als 0,2 %
// gedehnt werden muesste. `rand_vorn`/`rand_hinten` wirkt im Prototyp nur im
// Keylock-Weg und wird darum hier noch nicht ausgewertet.
//
// Nur fuer Baker und Host-Test, nie im Audio-Callback.
#pragma once

#include <span>
#include <vector>

namespace klangbild::dsp {

/// `uebergang.warp`: zieht `audio[quellS[0] .. quellS[-1]]` so, dass Takt `i` auf
/// `zielS[i] - zielS[0]` faellt. `quellS`/`zielS` sind Sekunden, stereo interleaved.
/// Wirft `std::invalid_argument`, wenn `keylock` noetig waere (T6.3).
std::vector<float> warp(std::span<const float> audio, std::span<const double> quellS,
                        std::span<const double> zielS, bool keylock, bool randVorn = false,
                        bool randHinten = false, int rate = 44100);

}  // namespace klangbild::dsp
