#include "dsp/tricks.h"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <numbers>
#include <utility>
#include <vector>

#include "dsp/effects.h"
#include "dsp/filters.h"   // Sos, sosfiltBlock
#include "dsp/mixing.h"    // kChannels, kRate
#include "dsp/sweep.h"

namespace klangbild::dsp {
namespace {

constexpr std::size_t ch = static_cast<std::size_t>(kChannels);

long long runde(double v) { return static_cast<long long>(std::nearbyint(v)); }

std::vector<float> kopie(std::span<const float> a) { return std::vector<float>(a.begin(), a.end()); }

/// `scipy.ndimage.uniform_filter1d(g, size)` mit mode="reflect" (Halb-Sample-Symmetrie: der Rand
/// wird gespiegelt und dabei wiederholt).
std::vector<float> uniformFilter1d(std::vector<float> g, int size) {
    const int n = static_cast<int>(g.size());
    std::vector<float> aus(g.size());
    if (n == 0) return aus;
    const int halb = size / 2;
    const int periode = 2 * n;
    const auto index = [n, periode](int i) {
        if (n == 1) return 0;
        int k = i % periode;
        if (k < 0) k += periode;
        return k < n ? k : periode - 1 - k;
    };
    for (int i = 0; i < n; ++i) {
        double summe = 0.0;
        for (int j = -halb; j <= halb; ++j) summe += static_cast<double>(g[static_cast<std::size_t>(index(i + j))]);
        aus[static_cast<std::size_t>(i)] = static_cast<float>(summe / static_cast<double>(size));
    }
    return aus;
}

}  // namespace

std::vector<float> abspielen(std::span<const float> a, std::span<const double> pos) {
    const long long frames = static_cast<long long>(a.size() / ch);
    std::vector<float> aus(a.size());
    if (frames <= 0) return aus;
    for (std::size_t i = 0; i < pos.size(); ++i) {
        const double p = pos[i];
        for (std::size_t c = 0; c < ch; ++c) {
            double wert = 0.0;
            if (p <= 0.0) {
                wert = static_cast<double>(a[c]);
            } else if (p >= static_cast<double>(frames - 1)) {
                wert = static_cast<double>(a[static_cast<std::size_t>(frames - 1) * ch + c]);
            } else {
                const long long i0 = static_cast<long long>(std::floor(p));
                const double frac = p - static_cast<double>(i0);
                wert = static_cast<double>(a[static_cast<std::size_t>(i0) * ch + c]) * (1.0 - frac) +
                       static_cast<double>(a[static_cast<std::size_t>(i0 + 1) * ch + c]) * frac;
            }
            aus[i * ch + c] = static_cast<float>(wert);
        }
    }
    return aus;
}

std::vector<float> bremse(std::span<const float> a, long long n) {
    const long long frames = static_cast<long long>(a.size() / ch);
    std::vector<float> aus = kopie(a);
    n = std::min(n, frames);
    if (n < 2) return aus;
    const long long s = frames - n;
    std::vector<double> pos(static_cast<std::size_t>(n));
    std::vector<float> pegel(static_cast<std::size_t>(n));
    for (long long i = 0; i < n; ++i) {
        const double t = static_cast<double>(i) / static_cast<double>(n);
        pos[static_cast<std::size_t>(i)] = static_cast<double>(s) + static_cast<double>(n) * (t - t * t / 2.0);
        pegel[static_cast<std::size_t>(i)] = static_cast<float>(std::sqrt(1.0 - t));
    }
    const std::vector<float> teil = abspielen(a, pos);
    for (long long i = 0; i < n; ++i) {
        for (std::size_t c = 0; c < ch; ++c) {
            const std::size_t idx = static_cast<std::size_t>(s + i) * ch + c;
            aus[idx] = teil[static_cast<std::size_t>(i) * ch + c] * pegel[static_cast<std::size_t>(i)];
        }
    }
    return aus;
}

std::vector<float> spinback(std::span<const float> a, long long n) {
    const long long frames = static_cast<long long>(a.size() / ch);
    std::vector<float> aus = kopie(a);
    n = std::min(n, frames);
    if (n < 2) return aus;
    const long long s = frames - n;
    std::vector<double> pos(static_cast<std::size_t>(n));
    std::vector<float> pegel(static_cast<std::size_t>(n));
    double summe = 0.0;
    for (long long i = 0; i < n; ++i) {
        const double t = static_cast<double>(i) / static_cast<double>(n);
        const double v = t < 0.08 ? 1.0 - 6.0 * t / 0.08
                                  : (t < 0.4 ? -5.0 : -5.0 * std::pow((1.0 - t) / 0.6, 2.0));
        summe += v;
        pos[static_cast<std::size_t>(i)] =
            std::clamp(static_cast<double>(s) + summe, 0.0, static_cast<double>(frames - 1));
        pegel[static_cast<std::size_t>(i)] = static_cast<float>(1.2 * std::pow(1.0 - t, 0.3));
    }
    const std::vector<float> teil = abspielen(a, pos);
    for (long long i = 0; i < n; ++i) {
        for (std::size_t c = 0; c < ch; ++c) {
            const std::size_t idx = static_cast<std::size_t>(s + i) * ch + c;
            aus[idx] = teil[static_cast<std::size_t>(i) * ch + c] * pegel[static_cast<std::size_t>(i)];
        }
    }
    return aus;
}

std::vector<float> flanger(std::span<const float> a, std::span<const double> depth, double beatN) {
    const long long frames = static_cast<long long>(a.size() / ch);
    const double periode = std::max(1.0, 8.0 * beatN);
    std::vector<double> pos(static_cast<std::size_t>(frames));
    for (long long i = 0; i < frames; ++i) {
        const double lfo = 0.5 * (1.0 - std::cos(2.0 * std::numbers::pi * static_cast<double>(i) / periode));
        pos[static_cast<std::size_t>(i)] =
            static_cast<double>(i) - (0.001 + 0.004 * lfo) * static_cast<double>(kRate);
    }
    const std::vector<float> kopieSignal = abspielen(a, pos);
    std::vector<float> aus(a.size());
    for (long long i = 0; i < frames; ++i) {
        const float w = static_cast<float>(depth[static_cast<std::size_t>(i)]);
        for (std::size_t c = 0; c < ch; ++c) {
            const std::size_t idx = static_cast<std::size_t>(i) * ch + c;
            aus[idx] = (a[idx] + w * kopieSignal[idx]) / (1.0f + w);
        }
    }
    return aus;
}

std::vector<float> phaser(std::span<const float> a, std::span<const double> depth, double beatN) {
    const long long frames = static_cast<long long>(a.size() / ch);
    constexpr int blk = 1024;
    const long long bloecke = (frames + blk - 1) / blk;
    const double periode = std::max(1.0, 8.0 * beatN);
    std::vector<double> k(static_cast<std::size_t>(bloecke));
    for (long long b = 0; b < bloecke; ++b) {
        const long long mitte = std::min(b * blk + blk / 2, frames - 1);
        const double fc = 300.0 * std::pow(10.0, 0.5 * (1.0 - std::cos(2.0 * std::numbers::pi *
                                                                    static_cast<double>(mitte) / periode)));
        const double t = std::tan(std::numbers::pi * fc / static_cast<double>(kRate));
        k[static_cast<std::size_t>(b)] = (t - 1.0) / (t + 1.0);
    }

    std::vector<float> nass(a.size(), 0.0f);
    std::vector<double> state;   // 2 Abschnitte, 2 Zustaende, 2 Kanaele
    for (long long b = 0; b < bloecke; ++b) {
        const long long von = b * blk;
        const long long bis = std::min<long long>(von + blk, frames);
        Sos sos(2);
        const double kk = k[static_cast<std::size_t>(b)];
        for (Biquad& q : sos) {
            q.b0 = kk * kk;
            q.b1 = 2.0 * kk;
            q.b2 = 1.0;
            q.a1 = 2.0 * kk;
            q.a2 = kk * kk;
        }
        const std::span<const float> block(a.data() + static_cast<std::ptrdiff_t>(von * static_cast<long long>(ch)),
                                           static_cast<std::size_t>(bis - von) * ch);
        const std::vector<float> gefiltert = sosfiltBlock(sos, block, static_cast<std::size_t>(bis - von), kChannels, state);
        std::copy(gefiltert.begin(), gefiltert.end(), nass.begin() + static_cast<std::ptrdiff_t>(von * static_cast<long long>(ch)));
    }

    std::vector<float> aus(a.size());
    for (long long i = 0; i < frames; ++i) {
        const float w = static_cast<float>(depth[static_cast<std::size_t>(i)]);
        for (std::size_t c = 0; c < ch; ++c) {
            const std::size_t idx = static_cast<std::size_t>(i) * ch + c;
            aus[idx] = (a[idx] + w * nass[idx]) / (1.0f + w);
        }
    }
    return aus;
}

std::vector<float> gate(std::span<const float> a, std::span<const double> taktN) {
    const long long frames = static_cast<long long>(a.size() / ch);
    std::vector<float> aus = kopie(a);
    const int takte = static_cast<int>(taktN.size()) - 1;
    if (takte < 2 || frames <= 0) return aus;
    std::vector<float> g(static_cast<std::size_t>(frames), 1.0f);
    const int aufteilung[2][2] = {{takte - 2, 8}, {takte - 1, 16}};
    for (const auto& fall : aufteilung) {
        const int t0 = fall[0];
        const int teile = fall[1];
        const double von = taktN[static_cast<std::size_t>(t0)];
        const double bis = taktN[static_cast<std::size_t>(t0 + 1)];
        const double schritt = (bis - von) / static_cast<double>(teile);
        std::vector<long long> grenzen(static_cast<std::size_t>(teile) + 1);
        for (int i = 0; i <= teile; ++i) {
            const double wert = i == teile ? bis : von + schritt * static_cast<double>(i);
            grenzen[static_cast<std::size_t>(i)] = static_cast<long long>(wert);   // astype(int) schneidet ab
        }
        for (int i = 1; i + 1 <= teile; i += 2) {
            const long long s0 = std::clamp<long long>(grenzen[static_cast<std::size_t>(i)], 0, frames);
            const long long s1 = std::clamp<long long>(grenzen[static_cast<std::size_t>(i + 1)], 0, frames);
            for (long long j = s0; j < s1; ++j) g[static_cast<std::size_t>(j)] = 0.0f;
        }
    }
    const int fenster = static_cast<int>(0.002 * static_cast<double>(kRate)) | 1;
    g = uniformFilter1d(std::move(g), fenster);
    for (long long i = 0; i < frames; ++i) {
        for (std::size_t c = 0; c < ch; ++c) {
            const std::size_t idx = static_cast<std::size_t>(i) * ch + c;
            aus[idx] = a[idx] * g[static_cast<std::size_t>(i)];
        }
    }
    return aus;
}

std::vector<float> crush(std::span<const float> a, std::span<const double> depth) {
    const long long frames = static_cast<long long>(a.size() / ch);
    std::vector<float> aus(a.size());
    for (long long i = 0; i < frames; ++i) {
        const double tiefe = depth[static_cast<std::size_t>(i)];
        const long long stufe = 1 + runde(7.0 * tiefe);
        const long long quelle = i - i % std::max<long long>(1, stufe);
        const double bits = 16.0 - 9.0 * tiefe;
        const double q = std::pow(2.0, bits - 1.0);
        const double w = 0.7 * tiefe;
        for (std::size_t c = 0; c < ch; ++c) {
            const std::size_t idx = static_cast<std::size_t>(i) * ch + c;
            const double gehalten = static_cast<double>(a[static_cast<std::size_t>(quelle) * ch + c]);
            const double roh = std::nearbyint(gehalten * q) / q;
            aus[idx] = static_cast<float>(static_cast<double>(a[idx]) * (1.0 - w) + roh * w);
        }
    }
    return aus;
}

std::vector<float> rueckhall(std::span<const float> b, int p, double beatN, std::span<const float> hallIr) {
    const long long frames = static_cast<long long>(b.size() / ch);
    std::vector<float> aus(b.size(), 0.0f);
    const long long laenge = static_cast<long long>(beatN);   // int(schlag_n)
    const long long von = std::clamp<long long>(p, 0, frames);
    const long long bis = std::clamp<long long>(static_cast<long long>(p) + laenge, 0, frames);
    if (bis - von < 16) return aus;

    std::vector<float> x(static_cast<std::size_t>(bis - von) * ch);
    for (long long i = 0; i < bis - von; ++i) {
        for (std::size_t c = 0; c < ch; ++c) {
            x[static_cast<std::size_t>(i) * ch + c] = b[static_cast<std::size_t>(bis - 1 - i) * ch + c];
        }
    }
    std::vector<float> y = wetSignal("hall", x, beatN, hallIr);
    const long long yFrames = static_cast<long long>(y.size() / ch);
    std::vector<float> yr(y.size());
    for (long long i = 0; i < yFrames; ++i) {
        for (std::size_t c = 0; c < ch; ++c) {
            yr[static_cast<std::size_t>(i) * ch + c] = y[static_cast<std::size_t>(yFrames - 1 - i) * ch + c];
        }
    }
    const long long start = static_cast<long long>(p) + (bis - von) - yFrames;
    const long long lo = std::max<long long>(0, start);
    const long long hi = std::min<long long>(frames, start + yFrames);
    for (long long i = lo; i < hi; ++i) {
        for (std::size_t c = 0; c < ch; ++c) {
            aus[static_cast<std::size_t>(i) * ch + c] = yr[static_cast<std::size_t>(i - start) * ch + c];
        }
    }
    for (long long i = std::max<long long>(0, p); i < frames; ++i) {
        for (std::size_t c = 0; c < ch; ++c) aus[static_cast<std::size_t>(i) * ch + c] = 0.0f;
    }
    return aus;
}

std::vector<float> riser(int frames, int m, double level, std::span<const float> noise) {
    std::vector<float> aus(static_cast<std::size_t>(std::max(0, frames)) * ch, 0.0f);
    m = std::min(m, frames);
    if (m < 2) return aus;
    const std::size_t noiseFrames = noise.size() / ch;
    if (static_cast<int>(noiseFrames) < m) return aus;

    std::vector<double> t(static_cast<std::size_t>(m));
    std::vector<float> menge(static_cast<std::size_t>(m));
    for (int i = 0; i < m; ++i) {
        t[static_cast<std::size_t>(i)] = static_cast<double>(i) / static_cast<double>(m);
        menge[static_cast<std::size_t>(i)] = static_cast<float>(0.9 * t[static_cast<std::size_t>(i)]);
    }
    const std::vector<float> rauschen =
        sweep(std::span<const float>(noise.data(), static_cast<std::size_t>(m) * ch), menge, SweepKind::Highpass);
    for (int i = 0; i < m; ++i) {
        const float pegel = static_cast<float>(level * std::pow(10.0, -24.0 * (1.0 - t[static_cast<std::size_t>(i)]) / 20.0));
        for (std::size_t c = 0; c < ch; ++c) {
            aus[static_cast<std::size_t>(frames - m + i) * ch + c] =
                rauschen[static_cast<std::size_t>(i) * ch + c] * pegel;
        }
    }
    return aus;
}

}  // namespace klangbild::dsp
