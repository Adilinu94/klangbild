#include "dsp/introloop.h"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <numbers>
#include <utility>
#include <vector>

#include "dsp/mixing.h"     // kChannels
#include "dsp/resample.h"   // padTo

namespace klangbild::dsp {
namespace {

constexpr std::size_t ch = static_cast<std::size_t>(kChannels);

long long runde(double v) { return static_cast<long long>(std::nearbyint(v)); }

/// `b_audio[von:bis]`, ausserhalb gekappt.
std::vector<float> ausschnitt(std::span<const float> y, long long von, long long bis) {
    const long long frames = static_cast<long long>(y.size() / ch);
    const long long a = std::clamp<long long>(von, 0, frames);
    const long long b = std::clamp<long long>(bis, 0, frames);
    if (b <= a) return {};
    return std::vector<float>(y.begin() + static_cast<std::ptrdiff_t>(a * static_cast<long long>(ch)),
                              y.begin() + static_cast<std::ptrdiff_t>(b * static_cast<long long>(ch)));
}

}  // namespace

IntroLoop introLoop(std::span<const float> bAudio, std::span<const double> bbar, int j0, int k, int repeats,
                    int rate) {
    IntroLoop loop;
    loop.repeats = std::max(0, repeats);
    if (bbar.size() < static_cast<std::size_t>(j0 + k + 1) || j0 < 0 || k <= 0) return loop;

    const long long ib0 = runde(bbar[static_cast<std::size_t>(j0)] * rate);
    const long long ibk = runde(bbar[static_cast<std::size_t>(j0 + k)] * rate);
    const std::vector<float> stueck = ausschnitt(bAudio, ib0, ibk);
    const long long d = static_cast<long long>(stueck.size() / ch);
    const long long f = std::min<long long>(256, d);

    std::vector<float> rein(static_cast<std::size_t>(std::max<long long>(0, f)));
    const double schritt = f > 1 ? (std::numbers::pi / 2.0) / static_cast<double>(f - 1) : 0.0;
    for (long long i = 0; i < f; ++i) {
        rein[static_cast<std::size_t>(i)] = std::sin(static_cast<float>(static_cast<double>(i) * schritt));
    }

    std::vector<float> aus = ausschnitt(bAudio, 0, ibk);
    for (int r = 0; r < loop.repeats; ++r) {
        std::vector<float> neu = stueck;
        const std::vector<float> folge = padTo(ausschnitt(bAudio, ibk, ibk + f), static_cast<std::size_t>(std::max<long long>(0, f)));
        for (long long i = 0; i < f; ++i) {
            for (std::size_t c = 0; c < ch; ++c) {
                const std::size_t idx = static_cast<std::size_t>(i) * ch + c;
                neu[idx] = folge[idx] * rein[static_cast<std::size_t>(f - 1) - static_cast<std::size_t>(i)] +
                           stueck[idx] * rein[static_cast<std::size_t>(i)];
            }
        }
        aus.insert(aus.end(), neu.begin(), neu.end());
    }
    const std::vector<float> rest = ausschnitt(bAudio, ibk, static_cast<long long>(bAudio.size() / ch));
    aus.insert(aus.end(), rest.begin(), rest.end());
    loop.audio = std::move(aus);

    loop.t0 = bbar[static_cast<std::size_t>(j0)];
    loop.duration = static_cast<double>(d) / static_cast<double>(rate);
    loop.raster.reserve(bbar.size() + static_cast<std::size_t>(k) * static_cast<std::size_t>(loop.repeats));
    for (int i = 0; i < j0 + k; ++i) loop.raster.push_back(bbar[static_cast<std::size_t>(i)]);
    for (int r = 1; r <= loop.repeats; ++r) {
        for (int i = j0; i < j0 + k; ++i) {
            loop.raster.push_back(bbar[static_cast<std::size_t>(i)] + static_cast<double>(r) * loop.duration);
        }
    }
    for (std::size_t i = static_cast<std::size_t>(j0 + k); i < bbar.size(); ++i) {
        loop.raster.push_back(bbar[i] + static_cast<double>(loop.repeats) * loop.duration);
    }
    return loop;
}

std::vector<double> introLoopBack(const IntroLoop& loop, std::span<const double> t) {
    std::vector<double> aus(t.size());
    const double ende = loop.t0 + static_cast<double>(loop.repeats + 1) * loop.duration;
    for (std::size_t i = 0; i < t.size(); ++i) {
        const double x = t[i];
        if (x <= loop.t0) {
            aus[i] = x;
        } else if (x < ende) {
            aus[i] = loop.t0 + (x - loop.t0) / static_cast<double>(loop.repeats + 1);
        } else {
            aus[i] = x - static_cast<double>(loop.repeats) * loop.duration;
        }
    }
    return aus;
}

}  // namespace klangbild::dsp
