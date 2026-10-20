#include "dsp/level.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <optional>
#include <vector>

#include "dsp/filters.h"
#include "dsp/mixing.h"   // kRate, kChannels

namespace klangbild::dsp {
namespace {

constexpr std::size_t ch = static_cast<std::size_t>(kChannels);

long long clampFrame(int frame, std::size_t frames) {
    return std::clamp<long long>(frame, 0, static_cast<long long>(frames));
}

/// `np.interp(x, xp, fp)`: ausserhalb der Stuetzstellen konstant, dazwischen linear
/// (Steigung zuerst, wie numpy).
double interp(double x, const std::vector<double>& xp, const std::vector<double>& fp) {
    if (xp.empty()) return 0.0;
    if (x <= xp.front()) return fp.front();
    if (x >= xp.back()) return fp.back();
    std::size_t k = 1;
    while (k < xp.size() && xp[k] < x) ++k;
    const double steigung = (fp[k] - fp[k - 1]) / (xp[k] - xp[k - 1]);
    return steigung * (x - xp[k - 1]) + fp[k - 1];
}

/// `uebergang._baender`: Tiefband bei 200 Hz, dann Rest bei 2000 Hz in Mitte und Hoch.
std::array<std::vector<float>, 3> bands(std::span<const float> x, std::size_t frames) {
    const BandSplit tief = bandSplit(x.data(), frames, kChannels, kRate, 200.0);
    const BandSplit rest = bandSplit(tief.high.data(), frames, kChannels, kRate, 2000.0);
    return {tief.low, rest.low, rest.high};
}

}  // namespace

std::vector<double> taktDb(std::span<const float> x, std::span<const int> taktN) {
    const std::size_t frames = x.size() / ch;
    std::vector<double> q(frames + 1, 0.0);
    for (std::size_t i = 0; i < frames; ++i) {
        const double links = static_cast<double>(x[i * ch]);
        const double rechts = static_cast<double>(x[i * ch + 1]);
        q[i + 1] = q[i] + (links * links + rechts * rechts) / 2.0;
    }
    std::vector<double> aus;
    if (taktN.size() < 2) return aus;
    aus.reserve(taktN.size() - 1);
    for (std::size_t k = 0; k + 1 < taktN.size(); ++k) {
        const long long von = clampFrame(taktN[k], frames);
        const long long bis = clampFrame(taktN[k + 1], frames);
        const long long laenge = std::max<long long>(1, bis - von);
        const double leistung = (q[static_cast<std::size_t>(bis)] - q[static_cast<std::size_t>(von)]) /
                                static_cast<double>(laenge) + 1e-12;
        aus.push_back(10.0 * std::log10(leistung));
    }
    return aus;
}

std::vector<float> deckeln(std::span<const float> y, std::span<const float> ra, std::span<const float> rb,
                           std::span<const int> taktN, double toleranz, double maxDb) {
    std::vector<float> aus(y.begin(), y.end());
    if (taktN.size() < 2) return aus;
    const std::vector<double> dy = taktDb(y, taktN);
    const std::vector<double> da = taktDb(ra, taktN);
    const std::vector<double> db = taktDb(rb, taktN);
    std::vector<double> verstaerkung_db(dy.size());
    bool noetig = false;
    for (std::size_t k = 0; k < dy.size(); ++k) {
        const double zuviel = dy[k] - std::max(da[k], db[k]) - toleranz;
        verstaerkung_db[k] = -std::min(std::max(zuviel, 0.0), maxDb);
        if (verstaerkung_db[k] < -0.05) noetig = true;
    }
    if (!noetig) return aus;

    std::vector<double> mitte(verstaerkung_db.size());
    for (std::size_t k = 0; k < verstaerkung_db.size(); ++k) {
        mitte[k] = (static_cast<double>(taktN[k]) + static_cast<double>(taktN[k + 1])) / 2.0;
    }
    const std::size_t frames = y.size() / ch;
    for (std::size_t i = 0; i < frames; ++i) {
        const double g = std::pow(10.0, interp(static_cast<double>(i), mitte, verstaerkung_db) / 20.0);
        for (std::size_t c = 0; c < ch; ++c) {
            aus[i * ch + c] = static_cast<float>(static_cast<double>(y[i * ch + c]) * g);
        }
    }
    return aus;
}

std::vector<float> trocken(std::span<const float> a, std::span<const float> b, const Envelopes& h,
                           std::span<const int> taktN) {
    const std::size_t frames = a.size() / ch;
    const bool ohne_eq = !h.aLow && !h.bLow && !h.aMid && !h.bMid && !h.aHigh && !h.bHigh;
    if (ohne_eq) {
        std::vector<float> gemischt(a.size());
        for (std::size_t i = 0; i < a.size(); ++i) {
            const std::size_t f = i / ch;
            gemischt[i] = a[i] * h.aVol[f] + b[i] * h.bVol[f];
        }
        return deckeln(gemischt, a, b, taktN);
    }

    const std::array<std::vector<float>, 3> ba = bands(a, frames);
    const std::array<std::vector<float>, 3> bb = bands(b, frames);
    const std::optional<Curve>* ga[3] = {&h.aLow, &h.aMid, &h.aHigh};
    const std::optional<Curve>* gb[3] = {&h.bLow, &h.bMid, &h.bHigh};
    std::vector<float> aus(a.size(), 0.0f);
    for (std::size_t k = 0; k < 3; ++k) {
        std::vector<float> teil(a.size());
        for (std::size_t i = 0; i < a.size(); ++i) {
            const std::size_t f = i / ch;
            const float wa = *ga[k] ? (*(*ga[k]))[f] * h.aVol[f] : h.aVol[f];
            const float wb = *gb[k] ? (*(*gb[k]))[f] * h.bVol[f] : h.bVol[f];
            teil[i] = ba[k][i] * wa + bb[k][i] * wb;
        }
        const std::vector<float> gedeckelt = deckeln(teil, ba[k], bb[k], taktN);
        for (std::size_t i = 0; i < aus.size(); ++i) aus[i] += gedeckelt[i];
    }
    return aus;
}

}  // namespace klangbild::dsp
