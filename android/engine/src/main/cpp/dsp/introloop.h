// Intro-Loop von B (BAUPLAN-ANDROID T5.10).
//
// Port von uebergang._intro_loop: B's erste `k` Takte ab `j0` werden `mal`-mal zusaetzlich
// gespielt. Ergebnis ist virtuelles Audio, das dazu passende Taktraster und die Rueckrechnung
// virtuelle -> Originalzeit.
//
// Nur fuer Regie und Baker, nie im Audio-Callback.
#pragma once

#include <span>
#include <vector>

namespace klangbild::dsp {

struct IntroLoop {
    std::vector<float> audio;    // virtuelles Audio (ungedehnt, nur wiederholt)
    std::vector<double> raster;  // Taktraster dazu (Sekunden)
    double t0 = 0.0;             // Beginn des wiederholten Stuecks
    int repeats = 0;             // `mal`
    double duration = 0.0;       // Laenge eines Durchgangs (s)
};

/// `uebergang._intro_loop(b_audio, bbar, j0, k, mal)`.
IntroLoop introLoop(std::span<const float> bAudio, std::span<const double> bbar, int j0, int k, int repeats,
                    int rate = 44100);

/// Die `rueck`-Funktion aus `_intro_loop`: virtuelle Zeit (s) in Originalzeit (s).
std::vector<double> introLoopBack(const IntroLoop& loop, std::span<const double> t);

}  // namespace klangbild::dsp
