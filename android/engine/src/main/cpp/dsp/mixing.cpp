#include "dsp/mixing.h"

#include <algorithm>
#include <cmath>

#include "dsp/curves.h"
#include "dsp/filters.h"

namespace klangbild::dsp {

namespace {

constexpr std::size_t ch = static_cast<std::size_t>(kChannels);

/// Drei Baender nach `uebergang._baender`: Tief (< 200 Hz), Mitte (200 bis 2000 Hz), Hoehen (> 2000 Hz).
struct Bands {
    std::vector<float> low, mid, high;
};

Bands splitBands(const std::vector<float>& x, std::size_t frames) {
    BandSplit lowRest = bandSplit(x.data(), frames, kChannels, kRate, 200.0);
    BandSplit midHigh = bandSplit(lowRest.high.data(), frames, kChannels, kRate, 2000.0);
    return {std::move(lowRest.low), std::move(midHigh.low), std::move(midHigh.high)};
}

}  // namespace

std::vector<float> fadeSegment(std::span<const float> a, std::span<const float> b, int rate, bool bassSwap,
                               double splitHz) {
    const std::size_t n = std::min(a.size(), b.size()) / ch;
    if (n == 0) return {};
    const CurvePair fade = equalPowerBlend(static_cast<int>(n));
    std::vector<float> out(n * ch);
    if (!bassSwap) {
        for (std::size_t i = 0; i < n; ++i)
            for (std::size_t c = 0; c < ch; ++c) out[i * ch + c] = a[i * ch + c] * fade.out[i] + b[i * ch + c] * fade.in[i];
        return out;
    }
    const BandSplit sa = bandSplit(a.data(), n, kChannels, rate, splitHz);
    const BandSplit sb = bandSplit(b.data(), n, kChannels, rate, splitHz);
    const CurvePair swap = bassRamps(static_cast<int>(n), rate);
    for (std::size_t i = 0; i < n; ++i) {
        for (std::size_t c = 0; c < ch; ++c) {
            const std::size_t k = i * ch + c;
            const float high = sa.high[k] * fade.out[i] + sb.high[k] * fade.in[i];
            const float low = sa.low[k] * swap.out[i] + sb.low[k] * swap.in[i];
            out[k] = high + low;
        }
    }
    return out;
}

std::vector<float> echo(std::span<const float> a, int beatN) {
    const std::size_t n = a.size() / ch;
    std::vector<float> envelope(n, 0.0f);
    const int flank = std::max(1, static_cast<int>(0.01 * kRate));   // 10 ms
    const std::size_t beat = static_cast<std::size_t>(std::max(beatN, 0));
    // huelle[:schlag_n] = 1.0   (Slices werden gekappt)
    for (std::size_t i = 0; i < std::min(beat, n); ++i) envelope[i] = 1.0f;
    // huelle[schlag_n:schlag_n + flanke, 0] = np.linspace(1.0, 0.0, min(flanke, max(0, n - schlag_n)))
    const std::size_t count = std::min(static_cast<std::size_t>(flank), n > beat ? n - beat : 0);
    for (std::size_t i = 0; i < count; ++i) {
        double v;
        if (count == 1) {
            v = 1.0;
        } else if (i + 1 == count) {
            v = 0.0;   // np.linspace setzt den Endpunkt exakt
        } else {
            v = 1.0 + static_cast<double>(i) * (-1.0 / static_cast<double>(count - 1));
        }
        envelope[beat + i] = static_cast<float>(v);
    }
    std::vector<float> dry(n * ch);
    for (std::size_t i = 0; i < n; ++i)
        for (std::size_t c = 0; c < ch; ++c) dry[i * ch + c] = a[i * ch + c] * envelope[i];
    std::vector<float> out = dry;
    for (int k = 1; k <= 16; ++k) {
        const std::size_t d = static_cast<std::size_t>(k) * beat;
        if (d >= n) break;
        const float gain = static_cast<float>(std::pow(0.7, k));   // 0.7 ** k: Python-float, dann float32
        for (std::size_t i = d; i < n; ++i)
            for (std::size_t c = 0; c < ch; ++c) out[i * ch + c] += dry[(i - d) * ch + c] * gain;
    }
    return out;
}

std::vector<float> mix(std::string_view kind, std::span<const float> a, std::span<const float> b, int bars) {
    const std::size_t n = std::min(a.size(), b.size()) / ch;
    if (n == 0) return {};
    const std::span<const float> sa = a.first(n * ch);
    const std::span<const float> sb = b.first(n * ch);
    if (kind == "eq") return fadeSegment(sa, sb, kRate, true);

    if (kind == "filter") {
        // Hochpass-Sweep auf A, Tiefpass oeffnet auf B (uebergang.FILTER_FENSTER): je Band A (von, bis), B (von, bis).
        struct Window { double aFrom, aTo, bFrom, bTo; };
        constexpr Window windows[3] = {{0.45, 0.55, 0.45, 0.55}, {0.25, 0.75, 0.25, 0.75}, {0.5, 1.0, 0.0, 0.5}};
        const Bands bandsA = splitBands(std::vector<float>(sa.begin(), sa.end()), n);
        const Bands bandsB = splitBands(std::vector<float>(sb.begin(), sb.end()), n);
        const std::vector<float>* partsA[3] = {&bandsA.low, &bandsA.mid, &bandsA.high};
        const std::vector<float>* partsB[3] = {&bandsB.low, &bandsB.mid, &bandsB.high};
        std::vector<float> out(n * ch, 0.0f);
        for (int band = 0; band < 3; ++band) {
            const std::vector<float> rampA = ramp(static_cast<int>(n), windows[band].aFrom, windows[band].aTo);
            const std::vector<float> rampB = ramp(static_cast<int>(n), windows[band].bFrom, windows[band].bTo);
            for (std::size_t i = 0; i < n; ++i) {
                const float r2 = rampA[i] * rampA[i];                 // _rampe(...) ** 2
                const float fadeOutA = std::sqrt(1.0f - r2);          // np.sqrt(1 - r ** 2)
                for (std::size_t c = 0; c < ch; ++c) {
                    const std::size_t k = i * ch + c;
                    out[k] += (*partsA[band])[k] * fadeOutA + (*partsB[band])[k] * rampB[i];
                }
            }
        }
        return out;
    }

    if (kind == "echo") {
        const std::size_t beatsPerBar = n / static_cast<std::size_t>(std::max(1, bars));   // takt_n = n // max(1, takte)
        std::vector<float> bIn;
        if (beatsPerBar < n) {
            bIn = ramp(static_cast<int>(n), static_cast<double>(beatsPerBar) / static_cast<double>(n),
                       std::min(1.0, 2.0 * static_cast<double>(beatsPerBar) / static_cast<double>(n)));
        } else {
            bIn = ramp(static_cast<int>(n), 0.0, 1.0);
        }
        std::vector<float> out = echo(sa, static_cast<int>(std::max<std::size_t>(1, beatsPerBar / 4)));
        for (std::size_t i = 0; i < n; ++i)
            for (std::size_t c = 0; c < ch; ++c) out[i * ch + c] += sb[i * ch + c] * bIn[i];
        return out;
    }

    if (kind == "schnitt") {
        const double shortLen = std::min(1.0, 0.01 * kRate / static_cast<double>(std::max<std::size_t>(1, n)));
        const std::vector<float> r = ramp(static_cast<int>(n), 0.0, shortLen);
        std::vector<float> out(n * ch);
        for (std::size_t i = 0; i < n; ++i)
            for (std::size_t c = 0; c < ch; ++c) out[i * ch + c] = sa[i * ch + c] * (1.0f - r[i]) + sb[i * ch + c] * r[i];
        return out;
    }

    // crossfade und alles ohne Stems: equipotent
    return fadeSegment(sa, sb, kRate, false);
}

}  // namespace klangbild::dsp
