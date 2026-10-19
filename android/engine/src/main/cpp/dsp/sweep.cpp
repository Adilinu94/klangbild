#include "dsp/sweep.h"

#include <algorithm>
#include <cmath>
#include <numbers>

#include "dsp/mixing.h"   // kRate, kChannels

namespace klangbild::dsp {

namespace {
constexpr std::size_t ch = static_cast<std::size_t>(kChannels);
constexpr double kEdgeSeconds = 0.01;   // uebergang.KANTE_S
constexpr std::size_t kBlock = 1024;    // 23 ms: Frequenzschritt je Block < 1 %
}  // namespace

std::vector<std::array<Biquad, 2>> sweepBiquads(std::span<const double> fc, SweepKind kind, bool resonance) {
    std::vector<std::array<Biquad, 2>> blocks(fc.size());
    const double qs[2] = {0.5412, resonance ? 4.0 : 1.3066};
    for (std::size_t i = 0; i < fc.size(); ++i) {
        // w0 = 2 * pi * clip(fc, 10, 0.45 * RATE) / RATE
        const double clipped = std::clamp(fc[i], 10.0, 0.45 * kRate);
        const double w0 = 2.0 * std::numbers::pi * clipped / kRate;
        const double cosine = std::cos(w0);
        for (int stage = 0; stage < 2; ++stage) {
            const double alpha = std::sin(w0) / (2.0 * qs[stage]);
            const double b1 = kind == SweepKind::Lowpass ? (1.0 - cosine) : -(1.0 + cosine);
            const double b0 = std::abs(b1) / 2.0;
            const double a0 = 1.0 + alpha;
            Biquad& q = blocks[i][static_cast<std::size_t>(stage)];
            q.b0 = b0 / a0;
            q.b1 = b1 / a0;
            q.b2 = b0 / a0;
            q.a1 = -2.0 * cosine / a0;
            q.a2 = (1.0 - alpha) / a0;
        }
    }
    return blocks;
}

std::vector<float> sweep(std::span<const float> x, std::span<const float> amount, SweepKind kind, bool resonance) {
    const std::size_t n = x.size() / ch;
    if (amount.empty() || n == 0) return std::vector<float>(x.begin(), x.end());
    float maxAmount = amount[0];
    for (float a : amount) maxAmount = std::max(maxAmount, a);
    if (static_cast<double>(maxAmount) < 1e-3) return std::vector<float>(x.begin(), x.end());

    // Block-Mitten und Grenzfrequenz je Block (float64): tp 20000 * 0.01 ** m, hp 20 * 100 ** m
    const std::size_t blocks = (n + kBlock - 1) / kBlock;
    std::vector<double> fc(blocks);
    for (std::size_t i = 0; i < blocks; ++i) {
        const std::size_t mid = std::min(i * kBlock + kBlock / 2, n - 1);
        const double m = static_cast<double>(amount[mid]);
        fc[i] = kind == SweepKind::Lowpass ? 20000.0 * std::pow(0.01, m) : 20.0 * std::pow(100.0, m);
    }
    const auto coefficients = sweepBiquads(fc, kind, resonance);

    // Eingeschwungener Anfangszustand aus dem ersten Block: zi = sosfilt_zi(sos[0]) * x[0] (je Kanal)
    const Sos first = {coefficients[0][0], coefficients[0][1]};
    const std::vector<double> zi = sosfiltZi(first);   // (z0, z1) je Abschnitt
    std::vector<double> state(2 * 2 * ch);                // [Abschnitt][z0/z1][Kanal]
    for (std::size_t s = 0; s < 2; ++s)
        for (std::size_t z = 0; z < 2; ++z)
            for (std::size_t c = 0; c < ch; ++c) state[(s * 2 + z) * ch + c] = zi[2 * s + z] * static_cast<double>(x[c]);

    std::vector<float> y(n * ch);
    for (std::size_t b = 0; b < blocks; ++b) {
        const std::size_t begin = b * kBlock;
        const std::size_t end = std::min(begin + kBlock, n);
        for (std::size_t c = 0; c < ch; ++c) {
            double z[2][2] = {{state[(0 * 2 + 0) * ch + c], state[(0 * 2 + 1) * ch + c]},
                              {state[(1 * 2 + 0) * ch + c], state[(1 * 2 + 1) * ch + c]}};
            for (std::size_t i = begin; i < end; ++i) {
                double v = static_cast<double>(x[i * ch + c]);   // float32 -> float64 (exakt)
                for (std::size_t s = 0; s < 2; ++s) {
                    const Biquad& q = coefficients[b][s];
                    const double out = q.b0 * v + z[s][0];
                    z[s][0] = q.b1 * v - q.a1 * out + z[s][1];
                    z[s][1] = q.b2 * v - q.a2 * out;
                    v = out;
                }
                y[i * ch + c] = static_cast<float>(v);          // Zuweisung in ein float32-Array
            }
            for (std::size_t s = 0; s < 2; ++s)
                for (std::size_t zz = 0; zz < 2; ++zz) state[(s * 2 + zz) * ch + c] = z[s][zz];
        }
    }

    // Rand: 10 ms weich vom/ins ungefilterte Signal, wo der Filter offen ist
    const std::size_t edge = std::min(static_cast<std::size_t>(kEdgeSeconds * kRate), n / 2);
    if (edge > 0) {
        std::vector<float> r(edge);   // np.linspace(0, 1, rand, dtype=np.float32)
        for (std::size_t i = 0; i < edge; ++i)
            r[i] = edge == 1 ? 0.0f
                             : (i + 1 == edge ? 1.0f : static_cast<float>(static_cast<double>(i) * (1.0 / static_cast<double>(edge - 1))));
        if (amount[0] < 0.05f) {
            for (std::size_t i = 0; i < edge; ++i)
                for (std::size_t c = 0; c < ch; ++c) y[i * ch + c] = x[i * ch + c] * (1.0f - r[i]) + y[i * ch + c] * r[i];
        }
        if (amount[n - 1] < 0.05f) {
            for (std::size_t i = 0; i < edge; ++i)
                for (std::size_t c = 0; c < ch; ++c) {
                    const std::size_t k = (n - edge + i) * ch + c;
                    y[k] = y[k] * (1.0f - r[i]) + x[k] * r[i];
                }
        }
    }
    return y;
}

std::vector<float> weightBands(std::span<const float> x, const std::vector<float>* low, const std::vector<float>* mid,
                               const std::vector<float>* high) {
    if (low == nullptr && mid == nullptr && high == nullptr) return std::vector<float>(x.begin(), x.end());
    const std::size_t n = x.size() / ch;
    const std::vector<float> xv(x.begin(), x.end());
    // _baender(x): tief < 200 Hz, mitte 200..2000 Hz, hoch > 2000 Hz
    const BandSplit lowRest = bandSplit(xv.data(), n, kChannels, kRate, 200.0);
    const BandSplit midHigh = bandSplit(lowRest.high.data(), n, kChannels, kRate, 2000.0);
    const std::vector<float>* parts[3] = {&lowRest.low, &midHigh.low, &midHigh.high};
    const std::vector<float>* gains[3] = {low, mid, high};
    std::vector<float> out(n * ch, 0.0f);
    for (int band = 0; band < 3; ++band) {
        for (std::size_t i = 0; i < n; ++i)
            for (std::size_t c = 0; c < ch; ++c) {
                const std::size_t k = i * ch + c;
                out[k] += gains[band] == nullptr ? (*parts[band])[k] : (*parts[band])[k] * (*gains[band])[i];
            }
    }
    return out;
}

}  // namespace klangbild::dsp
