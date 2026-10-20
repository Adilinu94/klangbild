#include "dsp/warp.h"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <stdexcept>
#include <utility>
#include <vector>

#include "dsp/mixing.h"     // kChannels
#include "dsp/resample.h"

namespace klangbild::dsp {
namespace {

constexpr std::size_t ch = static_cast<std::size_t>(kChannels);

long long runde(double v) { return static_cast<long long>(std::nearbyint(v)); }

}  // namespace

std::vector<float> warp(std::span<const float> audio, std::span<const double> quellS,
                        std::span<const double> zielS, bool keylock, bool randVorn, bool randHinten, int rate) {
    if (quellS.empty() || zielS.empty() || quellS.size() != zielS.size()) return {};
    const long long frames = static_cast<long long>(audio.size() / ch);

    std::vector<long long> quell(quellS.size());
    std::vector<long long> ziel(zielS.size());
    for (std::size_t i = 0; i < quellS.size(); ++i) {
        quell[i] = std::clamp<long long>(runde(quellS[i] * rate), 0, frames);
        ziel[i] = runde((zielS[i] - zielS[0]) * rate);
    }

    if (keylock && quell.size() >= 2) {
        bool dehnen = false;
        for (std::size_t i = 0; i + 1 < quell.size(); ++i) {
            const double faktor = static_cast<double>(quell[i + 1] - quell[i]) /
                                  static_cast<double>(std::max<long long>(1, ziel[i + 1] - ziel[i]));
            if (std::abs(faktor - 1.0) > 0.002) dehnen = true;   // < 0,2 % ist Resampling (unhoerbar)
        }
        if (dehnen) {
            (void)randVorn;
            (void)randHinten;
            throw std::invalid_argument("warp mit Keylock folgt mit T6.3 (Signalsmith Stretch).");
        }
    }

    std::vector<float> aus;
    long long fertig = 0;
    for (std::size_t i = 0; i + 1 < quell.size(); ++i) {
        const long long nAus = ziel[i + 1] - fertig;
        if (nAus <= 0) continue;
        const long long von = quell[i], bis = quell[i + 1];
        if (bis <= von) {   // hinter dem Songende oder leerer Takt: Stille
            aus.insert(aus.end(), static_cast<std::size_t>(nAus) * ch, 0.0f);
        } else {
            std::vector<float> stueck(audio.begin() + static_cast<std::ptrdiff_t>(von * static_cast<long long>(ch)),
                                      audio.begin() + static_cast<std::ptrdiff_t>(bis * static_cast<long long>(ch)));
            const double faktor = static_cast<double>(bis - von) / static_cast<double>(nAus);
            std::vector<float> gezogen = resample(stueck, rate, faktor, kChannels);
            std::vector<float> aufgefuellt = padTo(std::move(gezogen), static_cast<std::size_t>(nAus));
            aus.insert(aus.end(), aufgefuellt.begin(), aufgefuellt.end());
        }
        fertig += nAus;
    }
    return aus;
}

}  // namespace klangbild::dsp
