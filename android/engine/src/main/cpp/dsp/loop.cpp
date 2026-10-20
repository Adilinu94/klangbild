#include "dsp/loop.h"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <numbers>
#include <stdexcept>
#include <vector>

#include "dsp/mixing.h"     // kChannels
#include "dsp/resample.h"   // padTo
#include "dsp/warp.h"

namespace klangbild::dsp {
namespace {

constexpr std::size_t ch = static_cast<std::size_t>(kChannels);

long long runde(double v) { return static_cast<long long>(std::nearbyint(v)); }

/// `round(v, stellen)` wie Python: ueber die Dezimaldarstellung, nicht ueber v * 10^n.
double rundeAuf(double v, int stellen) {
    char text[64];
    std::snprintf(text, sizeof text, "%.*f", stellen, v);
    return std::strtod(text, nullptr);
}

/// `uebergang._ausschnitt`: `y[von : von + laenge]`, ausserhalb mit Stille.
std::vector<float> ausschnitt(std::span<const float> y, long long von, long long laenge) {
    const long long n = std::max<long long>(0, laenge);
    std::vector<float> aus(static_cast<std::size_t>(n) * ch, 0.0f);
    const long long frames = static_cast<long long>(y.size() / ch);
    const long long a = std::max<long long>(0, von);
    const long long b = std::min<long long>(frames, von + laenge);
    for (long long i = a; i < b; ++i) {
        const std::size_t ziel = static_cast<std::size_t>(i - von) * ch;
        const std::size_t quelle = static_cast<std::size_t>(i) * ch;
        for (std::size_t c = 0; c < ch; ++c) aus[ziel + c] = y[quelle + c];
    }
    return aus;
}

}  // namespace

std::vector<long long> eighthGrid(std::span<const double> taktN) {
    std::vector<long long> achtel;
    if (taktN.size() < 2) return achtel;
    achtel.reserve((taktN.size() - 1) * 8 + 1);
    for (std::size_t i = 0; i + 1 < taktN.size(); ++i) {
        const double schritt = (taktN[i + 1] - taktN[i]) / 8.0;   // np.linspace(.., 9)
        for (int k = 0; k < 8; ++k) achtel.push_back(runde(taktN[i] + schritt * static_cast<double>(k)));
    }
    achtel.push_back(runde(taktN.back()));
    return achtel;
}

std::vector<float> loopen(std::span<const float> a, std::span<const double> taktN,
                          std::span<const LoopSection> plan, bool keylock, int rate) {
    if (plan.empty()) throw std::invalid_argument("_loopen ohne Loop-Plan.");
    const std::vector<long long> achtel = eighthGrid(taktN);
    std::vector<float> aus(a.begin(), a.end());
    constexpr int f = 256;
    std::vector<float> rein(static_cast<std::size_t>(f));
    const double schritt = (std::numbers::pi / 2.0) / static_cast<double>(f - 1);
    for (int i = 0; i < f; ++i) {
        rein[static_cast<std::size_t>(i)] = std::sin(static_cast<float>(static_cast<double>(i) * schritt));
    }

    const long long q0 = plan[0].from;
    const long long quelle = achtel[static_cast<std::size_t>(q0)];
    const long long nAus = static_cast<long long>(aus.size() / ch);
    for (const LoopSection& abschnitt : plan) {
        for (long long j = abschnitt.from; j < abschnitt.to; j += abschnitt.size) {
            const std::size_t jIdx = static_cast<std::size_t>(j);
            const long long grenzeIdx = std::min<long long>(j + abschnitt.size, abschnitt.to);
            const long long ziel = achtel[jIdx];
            const long long laenge = achtel[static_cast<std::size_t>(grenzeIdx)] - achtel[jIdx];
            if (ziel == quelle || laenge <= 0) continue;   // erster Durchlauf = das Original selbst

            const long long qIndex = std::min<long long>(q0 + grenzeIdx - j,
                                                        static_cast<long long>(achtel.size()) - 1);
            const long long qLaenge = achtel[static_cast<std::size_t>(qIndex)] - quelle;
            std::vector<float> stueck;
            if (std::abs(static_cast<double>(qLaenge - laenge)) > 0.002 * static_cast<double>(laenge)) {
                // Runde 19: bei Tempo-Rampe auf den Platz im Raster dehnen (Keylock wie eingestellt).
                const long long qe = quelle + runde(static_cast<double>(laenge + f) *
                                                   static_cast<double>(qLaenge) / static_cast<double>(laenge));
                const std::vector<double> quellS = {static_cast<double>(quelle) / rate,
                                                    static_cast<double>(qe) / rate};
                const std::vector<double> zielS = {0.0, static_cast<double>(laenge + f) / rate};
                stueck = padTo(warp(a, quellS, zielS, keylock, false, false, rate),
                               static_cast<std::size_t>(laenge + f));
            } else {
                stueck = ausschnitt(a, quelle, laenge + f);
            }

            const long long behalten = std::max<long long>(
                0, std::min<long long>(static_cast<long long>(stueck.size() / ch), nAus - ziel));
            stueck.resize(static_cast<std::size_t>(behalten) * ch);
            const long long nf = std::min<long long>(f, static_cast<long long>(stueck.size() / ch));
            for (long long i = 0; i < nf; ++i) {
                const std::size_t iIdx = static_cast<std::size_t>(i);
                const std::size_t ausIdx = static_cast<std::size_t>(ziel + i) * ch;
                for (std::size_t c = 0; c < ch; ++c) {
                    aus[ausIdx + c] = aus[ausIdx + c] * rein[static_cast<std::size_t>(f - 1) - iIdx] +
                                      stueck[iIdx * ch + c] * rein[iIdx];
                }
            }
            for (long long i = nf; i < behalten; ++i) {
                for (std::size_t c = 0; c < ch; ++c) {
                    aus[static_cast<std::size_t>(ziel + i) * ch + c] = stueck[static_cast<std::size_t>(i) * ch + c];
                }
            }
        }
    }
    return aus;
}

std::vector<LoopInfo> loopInfo(const Settings& e, std::span<const double> taktS) {
    if (e.art != "eigen" || e.loop == "keiner" || e.loop == "auto") return {};
    const int takte = static_cast<int>(taktS.size()) - 1;
    if (takte < 1) return {};
    std::vector<double> taktN(taktS.begin(), taktS.end());
    for (double& v : taktN) v *= kRate;   // takt_s * RATE
    const std::vector<long long> achtel = eighthGrid(taktN);
    std::vector<double> achtelS(achtel.size());
    for (std::size_t i = 0; i < achtel.size(); ++i) achtelS[i] = static_cast<double>(achtel[i]) / kRate;

    const std::vector<LoopSection> plan = loopPlan(e, takte);
    if (plan.empty()) return {};
    const double q = achtelS[static_cast<std::size_t>(plan[0].from)];
    std::vector<LoopInfo> aus;
    for (const LoopSection& s : plan) {
        if (s.to <= s.from) continue;
        const std::size_t i = static_cast<std::size_t>(std::min(s.from + s.size,
                                                               static_cast<int>(achtelS.size()) - 1));
        aus.push_back({rundeAuf(achtelS[static_cast<std::size_t>(s.from)], 3),
                       rundeAuf(achtelS[static_cast<std::size_t>(s.to)], 3),
                       rundeAuf(q, 3),
                       rundeAuf(achtelS[i] - achtelS[static_cast<std::size_t>(s.from)], 4)});
    }
    return aus;
}

}  // namespace klangbild::dsp
