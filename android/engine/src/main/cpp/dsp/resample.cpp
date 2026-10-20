#include "dsp/resample.h"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <vector>

namespace klangbild::dsp {

std::vector<float> resampleLinear(std::span<const float> signal, double faktor) {
    if (signal.empty()) return {};
    if (std::abs(faktor - 1.0) < 1e-9) return std::vector<float>(signal.begin(), signal.end());

    // laenge_aus = max(1, round(x.size / faktor)); round() rundet halbe Werte zur geraden Zahl.
    const long long laenge = std::max<long long>(
        1, static_cast<long long>(std::nearbyint(static_cast<double>(signal.size()) / faktor)));
    const long long letztes = static_cast<long long>(signal.size()) - 1;
    std::vector<float> aus(static_cast<std::size_t>(laenge));
    for (long long i = 0; i < laenge; ++i) {
        const double position = static_cast<double>(i) * faktor;
        long long i0 = static_cast<long long>(std::floor(position));
        const float frac = static_cast<float>(position - static_cast<double>(i0));
        i0 = std::clamp<long long>(i0, 0, letztes);
        const long long i1 = std::min<long long>(i0 + 1, letztes);
        aus[static_cast<std::size_t>(i)] =
            signal[static_cast<std::size_t>(i0)] * (1.0f - frac) + signal[static_cast<std::size_t>(i1)] * frac;
    }
    return aus;
}

std::vector<float> resample(std::span<const float> signal, int rate, double faktor, int channels) {
    (void)rate;   // die lineare Referenz rechnet ohne Abtastrate (resample.resample_linear)
    if (channels <= 0) return {};
    if (channels == 1) return resampleLinear(signal, faktor);

    const std::size_t frames = signal.size() / static_cast<std::size_t>(channels);
    std::vector<float> aus;
    std::vector<float> kanal(frames);
    for (int c = 0; c < channels; ++c) {
        for (std::size_t i = 0; i < frames; ++i) kanal[i] = signal[i * static_cast<std::size_t>(channels) +
                                                                 static_cast<std::size_t>(c)];
        const std::vector<float> gezogen = resampleLinear(kanal, faktor);
        if (c == 0) aus.assign(gezogen.size() * static_cast<std::size_t>(channels), 0.0f);
        for (std::size_t i = 0; i < gezogen.size(); ++i) {
            aus[i * static_cast<std::size_t>(channels) + static_cast<std::size_t>(c)] = gezogen[i];
        }
    }
    return aus;
}

std::vector<float> padTo(std::vector<float> signal, std::size_t frames, int channels) {
    const std::size_t ziel = frames * static_cast<std::size_t>(channels);
    if (signal.size() == ziel) return signal;
    signal.resize(ziel, 0.0f);
    return signal;
}

}  // namespace klangbild::dsp
