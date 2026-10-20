#include "dsp/mischen_eigen.h"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include "dsp/automation.h"   // loopPlan
#include "dsp/effects.h"      // wetSignal
#include "dsp/envelopes.h"
#include "dsp/level.h"        // trocken
#include "dsp/loop.h"         // loopen
#include "dsp/mixing.h"       // kChannels
#include "dsp/sweep.h"
#include "dsp/tricks.h"

namespace klangbild::dsp {
namespace {

constexpr std::size_t ch = static_cast<std::size_t>(kChannels);
constexpr double kKanteS = 0.01;   // uebergang.KANTE_S

/// `uebergang._schlag_bei`: Schlaglaenge (Frames) im Takt um Frame `p`.
double schlagBei(std::span<const double> taktN, long long p) {
    const auto treffer = std::upper_bound(taktN.begin(), taktN.end(), static_cast<double>(p));
    long long k = static_cast<long long>(treffer - taktN.begin()) - 1;
    k = std::clamp<long long>(k, 0, static_cast<long long>(taktN.size()) - 2);
    return (taktN[static_cast<std::size_t>(k + 1)] - taktN[static_cast<std::size_t>(k)]) / 4.0;
}

/// `uebergang._send_ende`: letzter Frame mit Anteil ungleich 0, sonst der letzte.
long long sendEnde(const Curve& send) {
    for (long long i = static_cast<long long>(send.size()) - 1; i >= 0; --i) {
        if (send[static_cast<std::size_t>(i)] != 0.0f) return i;
    }
    return static_cast<long long>(send.size()) - 1;
}

std::vector<float> mitPegel(std::span<const float> x, const Curve& pegel) {
    std::vector<float> aus(x.size());
    for (std::size_t i = 0; i < x.size(); ++i) aus[i] = x[i] * pegel[i / ch];
    return aus;
}

std::vector<float> mitFaktor(std::span<const float> x, float faktor) {
    std::vector<float> aus(x.size());
    for (std::size_t i = 0; i < x.size(); ++i) aus[i] = x[i] * faktor;
    return aus;
}

/// `_deckeln`/`_takt_db` indizieren mit ganzen Frames; im Prototyp ist `takt_n` ein int-Array.
std::vector<int> taktFrames(std::span<const double> taktN) {
    std::vector<int> aus(taktN.size());
    for (std::size_t i = 0; i < taktN.size(); ++i) aus[i] = static_cast<int>(std::nearbyint(taktN[i]));
    return aus;
}

}  // namespace

EigenBlend mischenEigen(std::span<const float> a, std::span<const float> b, const Settings& e,
                        std::span<const double> taktN, std::span<const float> hallIr,
                        std::span<const float> riserNoise, int rate) {
    const std::size_t n = std::min(a.size() / ch, b.size() / ch);
    std::vector<float> aa(a.begin(), a.begin() + static_cast<std::ptrdiff_t>(n * ch));
    std::vector<float> bb(b.begin(), b.begin() + static_cast<std::ptrdiff_t>(n * ch));
    const int takte = static_cast<int>(taktN.size()) - 1;
    if (takte < 1) throw std::invalid_argument("mischenEigen braucht mindestens einen Takt im Raster.");

    const Envelopes h = envelopes(e, takte, static_cast<int>(n),
                                  std::min(0.25, kKanteS * static_cast<double>(rate) / static_cast<double>(std::max<std::size_t>(1, n))));

    if (e.loop != "keiner" && e.loop != "auto") {
        aa = loopen(aa, taktN, loopPlan(e, takte), e.keylock, rate);
    }

    const double schlagN = taktN.back() / static_cast<double>(std::max(1, takte)) / 4.0;
    const double schlagEnde = schlagBei(taktN, static_cast<long long>(n) - 1);

    std::vector<double> tiefe(static_cast<std::size_t>(n));
    for (std::size_t i = 0; i < tiefe.size(); ++i) tiefe[i] = std::sqrt(static_cast<double>(i) / static_cast<double>(n));

    if (e.trick == "flanger") {
        aa = flanger(aa, tiefe, schlagN);
    } else if (e.trick == "bremse") {
        aa = bremse(aa, static_cast<long long>(2.0 * schlagEnde));
    } else if (e.trick == "spinback") {
        aa = spinback(aa, static_cast<long long>(3.0 * schlagEnde));
    } else if (e.trick == "phaser") {
        aa = phaser(aa, tiefe, schlagN);
    } else if (e.trick == "gate") {
        aa = gate(aa, taktN);
    } else if (e.trick == "crush") {
        aa = crush(aa, tiefe);
    }

    // Filter vor dem Effekt-Send (wie am Mixer), EQ und Fader danach.
    const bool reso = e.filter.size() >= 5 && e.filter.substr(e.filter.size() - 5) == "_reso";
    const std::span<const float> aTp = h.aLowpass ? std::span<const float>(*h.aLowpass) : std::span<const float>{};
    const std::span<const float> aHp = h.aHighpass ? std::span<const float>(*h.aHighpass) : std::span<const float>{};
    const std::span<const float> bTp = h.bLowpass ? std::span<const float>(*h.bLowpass) : std::span<const float>{};
    const std::span<const float> bHp = h.bHighpass ? std::span<const float>(*h.bHighpass) : std::span<const float>{};
    aa = sweep(sweep(aa, aTp, SweepKind::Lowpass, reso), aHp, SweepKind::Highpass, reso);
    bb = sweep(sweep(bb, bTp, SweepKind::Lowpass, false), bHp, SweepKind::Highpass, false);

    std::vector<float> blende = trocken(aa, bb, h, taktFrames(taktN));

    if (e.trick == "riser") {
        const long long von = static_cast<long long>(std::max(0, takte - 8));
        const long long m = static_cast<long long>(taktN.back() - taktN[static_cast<std::size_t>(von)]);
        double summe = 0.0;
        for (float v : aa) summe += static_cast<double>(v) * static_cast<double>(v);
        const double rms = aa.empty() ? 0.0 : std::sqrt(summe / static_cast<double>(aa.size()));
        if (riserNoise.empty()) {
            throw std::invalid_argument("mischenEigen: Trick 'riser' braucht Rauschen (T5.11).");
        }
        const std::vector<float> r = riser(static_cast<int>(n), static_cast<int>(m), 0.9 * rms, riserNoise);
        for (std::size_t i = 0; i < blende.size(); ++i) blende[i] += r[i];
    }

    if (h.bReverse) {
        const int p = static_cast<int>(*h.bReverse * static_cast<double>(n));
        const std::vector<float> rev = rueckhall(bb, p, schlagN, hallIr);
        for (std::size_t i = 0; i < blende.size(); ++i) blende[i] += 1.5f * rev[i];
    }

    std::vector<float> nachlauf;
    const std::string typA = e.effect.substr(0, e.effect.find('_'));
    for (int seite = 0; seite < 2; ++seite) {
        const Curve* send = seite == 0 ? (h.aSend ? &*h.aSend : nullptr) : (h.bSend ? &*h.bSend : nullptr);
        if (send == nullptr) continue;
        const bool aSeite = seite == 0;
        const std::vector<float> quelle = mitPegel(aSeite ? std::span<const float>(aa) : std::span<const float>(bb), *send);
        const double schlag = schlagBei(taktN, sendEnde(*send));
        std::vector<float> nass = wetSignal(aSeite ? std::string_view(typA) : std::string_view("hall"), quelle, schlag, hallIr);
        if (!aSeite) nass = mitFaktor(nass, 0.6f);
        if (aSeite && h.wetOff) {
            std::vector<float> gekappt(std::min(nass.size(), n) * ch);
            for (std::size_t i = 0; i < n; ++i) {
                for (std::size_t c = 0; c < ch; ++c) {
                    if (i * ch + c >= nass.size()) continue;
                    gekappt[i * ch + c] = nass[i * ch + c] * (*h.wetOff)[i];
                }
            }
            nass = std::move(gekappt);
        }

        for (std::size_t i = 0; i < n && i * ch + ch <= nass.size(); ++i) {
            for (std::size_t c = 0; c < ch; ++c) blende[i * ch + c] += nass[i * ch + c];
        }

        const std::size_t gesamt = nass.size() / ch;
        std::vector<float> rest;
        if (gesamt > n) rest.assign(nass.begin() + static_cast<std::ptrdiff_t>(n * ch), nass.end());
        const std::size_t restFrames = rest.size() / ch;
        const std::size_t nachFrames = nachlauf.size() / ch;
        if (restFrames > nachFrames) {
            for (std::size_t i = 0; i < nachFrames; ++i) {
                for (std::size_t c = 0; c < ch; ++c) rest[i * ch + c] += nachlauf[i * ch + c];
            }
            nachlauf = std::move(rest);
        } else {
            for (std::size_t i = 0; i < restFrames; ++i) {
                for (std::size_t c = 0; c < ch; ++c) nachlauf[i * ch + c] += rest[i * ch + c];
            }
        }
    }

    return {std::move(blende), std::move(nachlauf)};
}

}  // namespace klangbild::dsp
