// Art "eigen": die volle Blende (BAUPLAN-ANDROID T5.11).
//
// Port von uebergang.mischen_eigen: Huellen, Loop, Trick, Filter, trockene Mischung mit
// Buckel-Deckelung, Effekt-Sends und Nachlauf (Hall-/Echofahne).
//
// Nur fuer Baker und Host-Test, nie im Audio-Callback.
#pragma once

#include <span>
#include <vector>

#include "dsp/settings.h"

namespace klangbild::dsp {

struct EigenBlend {
    std::vector<float> blende;    // die Blende selbst (n Frames)
    std::vector<float> nachlauf;  // Fahne nach der Blende, wird auf B addiert
};

/// `uebergang.mischen_eigen(a, b, e, takt_n)`.
/// `hallIr` ist die Hall-Impulsantwort (interleaved); `riserNoise` liefert `m` Frames Rauschen fuer
/// den Trick "riser" (der Prototyp zieht es aus `default_rng(3)`, Zufall ist nicht bitgleich portierbar).
/// Fehlt `riserNoise` bei `trick == "riser"`, wirft die Funktion `std::invalid_argument`.
EigenBlend mischenEigen(std::span<const float> a, std::span<const float> b, const Settings& settings,
                        std::span<const double> taktN, std::span<const float> hallIr,
                        std::span<const float> riserNoise = {}, int rate = 44100);

}  // namespace klangbild::dsp
