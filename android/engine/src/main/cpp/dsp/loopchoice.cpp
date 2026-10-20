#include "dsp/loopchoice.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <complex>
#include <cstddef>
#include <stdexcept>
#include <vector>

#include "dsp/fft.h"

namespace klangbild::dsp {
namespace {

constexpr int kFftSize = 4096;
constexpr int kBands = 16;
constexpr double kBandLow = 40.0;
constexpr double kBandHigh = 16000.0;

long long runde(double v) { return static_cast<long long>(std::nearbyint(v)); }

/// `np.linspace(von, bis, 5)[:-1]`: vier Viertel je Takt.
void quarterGrid(std::span<const double> taktN, std::vector<long long>& aus) {
    aus.clear();
    if (taktN.size() < 2) return;
    aus.reserve((taktN.size() - 1) * 4 + 1);
    for (std::size_t i = 0; i + 1 < taktN.size(); ++i) {
        const double schritt = (taktN[i + 1] - taktN[i]) / 4.0;
        for (int k = 0; k < 4; ++k) aus.push_back(runde(taktN[i] + schritt * static_cast<double>(k)));
    }
    aus.push_back(runde(taktN.back()));
}

/// `np.geomspace(40, 16000, 17)`: 17 Kanten, geometrisch.
std::array<double, 17> bandEdges() {
    std::array<double, 17> kanten{};
    for (int i = 0; i <= 16; ++i) {
        kanten[static_cast<std::size_t>(i)] = kBandLow * std::pow(kBandHigh / kBandLow,
                                                                  static_cast<double>(i) / 16.0);
    }
    return kanten;
}

/// `np.hanning(4096).astype(np.float32)`: symmetrisches Hann-Fenster.
std::array<float, kFftSize> hannWindow() {
    std::array<float, kFftSize> fenster{};
    for (int i = 0; i < kFftSize; ++i) {
        fenster[static_cast<std::size_t>(i)] =
            static_cast<float>(0.5 - 0.5 * std::cos(2.0 * 3.14159265358979323846 *
                                                    static_cast<double>(i) / static_cast<double>(kFftSize - 1)));
    }
    return fenster;
}

}  // namespace

std::vector<std::vector<double>> beatFeatures(std::span<const float> x, std::span<const double> taktN,
                                              int channels, int rate) {
    std::vector<long long> grenzen;
    quarterGrid(taktN, grenzen);
    if (grenzen.size() < 2) return {};
    const long long frames = static_cast<long long>(x.size() / static_cast<std::size_t>(std::max(1, channels)));

    std::vector<double> mono(static_cast<std::size_t>(std::max<long long>(0, frames)), 0.0);
    for (long long i = 0; i < frames; ++i) {
        float summe = 0.0f;   // x.mean(axis=1) in float32
        for (int c = 0; c < channels; ++c) {
            summe += x[static_cast<std::size_t>(i) * static_cast<std::size_t>(channels) +
                       static_cast<std::size_t>(c)];
        }
        mono[static_cast<std::size_t>(i)] = static_cast<double>(summe / static_cast<float>(channels));
    }

    const std::array<double, 17> kanten = bandEdges();
    std::array<int, kFftSize / 2 + 1> band{};
    for (int i = 0; i <= kFftSize / 2; ++i) {
        const double frequenz = static_cast<double>(i) * static_cast<double>(rate) / kFftSize;
        // np.digitize(freq, kanten) = searchsorted(kanten, freq, side="right")
        band[static_cast<std::size_t>(i)] = static_cast<int>(
            std::upper_bound(kanten.begin(), kanten.end(), frequenz) - kanten.begin());
    }
    const std::array<float, kFftSize> fenster = hannWindow();
    const Fft fft(static_cast<std::size_t>(kFftSize));
    std::vector<std::complex<double>> puffer(static_cast<std::size_t>(kFftSize));

    std::vector<std::vector<double>> zeilen;
    zeilen.reserve(grenzen.size() - 1);
    for (std::size_t r = 0; r + 1 < grenzen.size(); ++r) {
        const long long a0 = grenzen[r];
        const long long a1 = std::min<long long>(grenzen[r + 1], a0 + kFftSize);
        for (int i = 0; i < kFftSize; ++i) {
            const long long quelle = a0 + i;
            float wert = 0.0f;
            if (a0 >= 0 && quelle < a1 && quelle < frames) {
                wert = static_cast<float>(mono[static_cast<std::size_t>(quelle)]);
            }
            // stueck * fenster in float32, dann wie np.fft in double
            puffer[static_cast<std::size_t>(i)] = static_cast<double>(wert * fenster[static_cast<std::size_t>(i)]);
        }
        fft.forward(puffer.data());
        std::array<double, 18> summe{};
        for (int i = 0; i <= kFftSize / 2; ++i) {
            const std::complex<double>& z = puffer[static_cast<std::size_t>(i)];
            const double leistung = z.real() * z.real() + z.imag() * z.imag();
            summe[static_cast<std::size_t>(band[static_cast<std::size_t>(i)])] += leistung;
        }
        std::vector<double> zeile(static_cast<std::size_t>(kBands));
        for (int k = 1; k <= kBands; ++k) {
            zeile[static_cast<std::size_t>(k - 1)] = 10.0 * std::log10(summe[static_cast<std::size_t>(k)] + 1e-9);
        }
        zeilen.push_back(std::move(zeile));
    }
    return zeilen;
}

double similarity(const std::vector<std::vector<double>>& f, int i, int j, int n) {
    const int zeilen = static_cast<int>(f.size());
    n = std::min({n, zeilen - i, zeilen - j});
    if (n <= 0) return 0.0;
    double summe = 0.0;
    for (int t = 0; t < n; ++t) {
        const std::vector<double>& a = f[static_cast<std::size_t>(i + t)];
        const std::vector<double>& b = f[static_cast<std::size_t>(j + t)];
        double ma = 0.0, mb = 0.0;
        for (int k = 0; k < kBands; ++k) {
            ma += a[static_cast<std::size_t>(k)];
            mb += b[static_cast<std::size_t>(k)];
        }
        ma /= kBands;
        mb /= kBands;
        double dot = 0.0, na = 0.0, nb = 0.0;
        for (int k = 0; k < kBands; ++k) {
            const double da = a[static_cast<std::size_t>(k)] - ma;
            const double db = b[static_cast<std::size_t>(k)] - mb;
            dot += da * db;
            na += da * da;
            nb += db * db;
        }
        const double cos = dot / std::max(std::sqrt(na) * std::sqrt(nb), 1e-9);
        const double pegel = 1.0 - std::min(1.0, std::abs(ma - mb) / 12.0);
        summe += cos * pegel;
    }
    return summe / static_cast<double>(n);
}

LoopChoice chooseLoop(std::span<const float> a, std::span<const double> taktN,
                      std::optional<std::span<const int>> meiden, std::span<const int> sizes, int window,
                      int channels, int rate) {
    const int takte = static_cast<int>(taktN.size()) - 1;
    const std::vector<std::vector<double>> f = beatFeatures(a, taktN, channels, rate);
    if (f.empty()) return {0, std::min(4, std::max(1, window > 0 ? window : takte)), 0.0};

    std::vector<double> pegel(f.size());
    double maxPegel = -1e300;
    for (std::size_t r = 0; r < f.size(); ++r) {
        double s = 0.0;
        for (int k = 0; k < kBands; ++k) s += f[r][static_cast<std::size_t>(k)];
        pegel[r] = s / kBands;
        maxPegel = std::max(maxPegel, pegel[r]);
    }
    int letzterLebt = -1;
    for (std::size_t r = 0; r < pegel.size(); ++r) {
        if (pegel[r] > maxPegel - 35.0) letzterLebt = static_cast<int>(r);
    }
    const int verfuegbar = letzterLebt >= 0 ? letzterLebt / 4 + 1 : 0;
    const int nFenster = window > 0 ? window : takte;
    const int erlaubt = std::min(verfuegbar, nFenster);

    LoopChoice best{0, std::min(4, std::max(1, nFenster)), 0.0};
    double bestP = -9.0;
    const std::array<int, 4> standard = {8, 4, 2, 1};
    std::span<const int> groessen = sizes;
    if (groessen.empty()) groessen = standard;

    for (int L : groessen) {
        for (int s0 = 0; s0 <= std::max(0, erlaubt - L); ++s0) {
            if (L > nFenster || s0 + L > erlaubt) continue;
            if (meiden) {
                bool gesperrt = false;
                for (int k = s0; k < s0 + L; ++k) {
                    if ((*meiden)[static_cast<std::size_t>(k)] != 0) gesperrt = true;
                }
                if (gesperrt) continue;
            }
            const int folge = std::min(L, verfuegbar - (s0 + L));
            double guete = 0.0;
            if (folge >= 1) {
                guete = similarity(f, 4 * s0, 4 * (s0 + L), 4 * folge);
            } else if (L >= 2) {
                guete = similarity(f, 4 * s0, 4 * s0 + 2 * L, 2 * L) - 0.05;
            } else {
                continue;
            }
            const double p = guete + 0.04 * std::log2(static_cast<double>(L)) +
                             0.08 * static_cast<double>(s0) / static_cast<double>(std::max(1, nFenster)) +
                             (s0 % 4 == 0 ? 0.03 : 0.0);
            if (p > bestP) {
                bestP = p;
                best = {s0, L, guete};
            }
        }
    }
    return best;
}

LoopChoice loopInOriginal(std::span<const float> puffer, std::span<const double> rasterS, int i, int bars,
                          std::optional<std::span<const int>> meiden, int rate) {
    const double ende = static_cast<double>(puffer.size() / 2) / static_cast<double>(rate) - 0.5;
    // np.searchsorted(raster, ende, side="left") - 1
    const long long treffer = std::lower_bound(rasterS.begin(), rasterS.end(), ende) - rasterS.begin();
    const int letzter = static_cast<int>(treffer) - 1;
    const int n = std::max(0, std::min(bars + 8, letzter - i));
    if (n < 1) return {0, std::max(1, std::min(4, bars)), 0.0};

    std::vector<double> tn(static_cast<std::size_t>(n) + 1);
    for (int k = 0; k <= n; ++k) {
        tn[static_cast<std::size_t>(k)] = static_cast<double>(
            runde((rasterS[static_cast<std::size_t>(i + k)] - rasterS[static_cast<std::size_t>(i)]) * rate));
    }
    const long long a0 = runde(rasterS[static_cast<std::size_t>(i)] * rate);
    const long long bis = std::min<long long>(a0 + static_cast<long long>(tn[static_cast<std::size_t>(n)]),
                                              static_cast<long long>(puffer.size() / 2));
    const long long von = std::max<long long>(0, a0);
    std::vector<float> ausschnitt;
    if (bis > von) {
        ausschnitt.assign(puffer.begin() + static_cast<std::ptrdiff_t>(von * 2),
                          puffer.begin() + static_cast<std::ptrdiff_t>(bis * 2));
    }
    return chooseLoop(ausschnitt, tn, meiden, {}, std::min(bars, n));
}

}  // namespace klangbild::dsp
