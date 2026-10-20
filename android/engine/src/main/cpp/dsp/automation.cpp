#include "dsp/automation.h"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <optional>
#include <stdexcept>
#include <string>

#include "dsp/curves.h"   // ramp

namespace klangbild::dsp {
namespace {

/// uebergang.FILTER_FENSTER: Blendenfenster je Band (A, B) als Anteile der Blende.
constexpr double kFilterWindows[3][2][2] = {
    {{0.45, 0.55}, {0.45, 0.55}},   // Bass: kurzer Tausch in der Mitte
    {{0.25, 0.75}, {0.25, 0.75}},   // Mitten
    {{0.50, 1.00}, {0.00, 0.50}},   // Hoehen: B zuerst, A zuletzt
};

/// `round(float(v), 3)`: gerundet auf die Dezimaldarstellung wie Python (nicht x*1000 runden,
/// sonst kippen Faelle wie 0,0005 auf 0,000 statt 0,001).
double round3(double v) {
    char text[64];
    std::snprintf(text, sizeof text, "%.3f", v);
    return std::strtod(text, nullptr);
}

Curve ones(std::size_t n) { return Curve(n, 1.0f); }

void runden(Automation& k) {
    for (auto* seite : {&k.a, &k.b}) {
        for (auto& [name, kurve] : *seite) {
            for (float& v : kurve) v = static_cast<float>(round3(static_cast<double>(v)));
        }
    }
}

Curve ausKurve(int n, double von, double bis) {
    Curve r = ramp(n, von, bis);   // uebergang._rampe, float32
    for (float& v : r) v = std::sqrt(1.0f - v * v);   // sqrt(1 - ein^2), float32 wie numpy
    return r;
}

std::optional<Curve> filterKurve(const std::optional<Curve>& tp, const std::optional<Curve>& hp) {
    if (!tp) return hp;
    if (!hp) return tp;
    Curve aus = *tp;
    for (std::size_t i = 0; i < aus.size(); ++i) aus[i] = std::max(aus[i], (*hp)[i]);
    return aus;
}

void eigenKurven(Automation& k, int bars, const Settings& e) {
    const int n = kAutomationPoints;
    const Envelopes h = envelopes(e, bars, n, 0.01);
    k.a["lautstaerke"] = h.aVol;
    k.b["lautstaerke"] = h.bVol;

    const std::optional<Curve>* aBand[3] = {&h.aLow, &h.aMid, &h.aHigh};
    const std::optional<Curve>* bBand[3] = {&h.bLow, &h.bMid, &h.bHigh};
    const char* bandName[3] = {"bass", "mitten", "hoehen"};
    for (std::size_t i = 0; i < 3; ++i) {
        if (*aBand[i] || *bBand[i]) {
            k.a[bandName[i]] = *aBand[i] ? **aBand[i] : ones(static_cast<std::size_t>(n));
            k.b[bandName[i]] = *bBand[i] ? **bBand[i] : ones(static_cast<std::size_t>(n));
        }
    }

    if (auto f = filterKurve(h.aLowpass, h.aHighpass)) k.a["filter"] = *f;
    if (auto f = filterKurve(h.bLowpass, h.bHighpass)) k.b["filter"] = *f;

    if (h.aSend) {
        const std::string& effekt = e.effect;
        const std::size_t trenner = effekt.find('_');
        const std::string typ = effekt.substr(0, trenner);
        const std::string modus = trenner == std::string::npos ? std::string() : effekt.substr(trenner + 1);
        const double p = modus == "mitte_aus" ? 0.5 : 1.0;
        Curve fahne(static_cast<std::size_t>(n));
        for (int i = 0; i < n; ++i) {
            const double x = static_cast<double>(i) / n;
            const double wert = x < p ? static_cast<double>((*h.aSend)[static_cast<std::size_t>(i)])
                                      : std::exp(-(x - p) * bars * 2.0);
            const double ab = h.wetOff ? static_cast<double>((*h.wetOff)[static_cast<std::size_t>(i)]) : 1.0;
            fahne[static_cast<std::size_t>(i)] = static_cast<float>(wert * ab);
        }
        k.a[typ == "hall" ? "hall" : "echo"] = fahne;
    }
    if (h.bSend) k.b["hall"] = *h.bSend;

    if (e.loop != "keiner" && e.loop != "auto") {
        Curve loop(static_cast<std::size_t>(n), 0.0f);
        for (const LoopSection& s : loopPlan(e, bars)) {
            for (int i = 0; i < n; ++i) {
                const double x = static_cast<double>(i) / n;
                if (x >= static_cast<double>(s.from) / (8.0 * bars) &&
                    x < static_cast<double>(s.to) / (8.0 * bars)) {
                    loop[static_cast<std::size_t>(i)] = 1.0f;
                }
            }
        }
        k.a["loop"] = loop;
    }
    if (e.loopIn > 0 && e.loopInTimes > 0) {
        const double grenze = std::min(1.0, static_cast<double>(e.loopIn) *
                                                  static_cast<double>(e.loopInTimes + 1) /
                                                  static_cast<double>(std::max(1, bars)));
        Curve loop(static_cast<std::size_t>(n));
        for (int i = 0; i < n; ++i) {
            loop[static_cast<std::size_t>(i)] = static_cast<double>(i) / n < grenze ? 1.0f : 0.0f;
        }
        k.b["loop"] = loop;
    }
}

}  // namespace

std::vector<LoopSection> loopPlan(const Settings& e, int bars) {
    const int ende = bars * 8;
    if (e.loop == "4" || e.loop == "8" || e.loop == "16" || e.loop == "32") {
        const int start = std::min(std::max(0, e.loopStart), std::max(0, bars - 1)) * 8;
        return {{start, ende, std::stoi(e.loop) * 2}};
    }
    const Curve vol = envelopes(e, bars, 256, 0.01).aVol;
    int leise = 256;
    for (std::size_t i = 0; i < vol.size(); ++i) {
        if (vol[i] < 0.5f) {
            leise = static_cast<int>(i);
            break;
        }
    }
    // aus = max(8, int(round(leise / 256 * ende / 8)) * 8): Takt, an dem A leise wird.
    const double takt = std::nearbyint(static_cast<double>(leise) / 256.0 * static_cast<double>(ende) / 8.0);
    const int aus = std::max(8, static_cast<int>(takt) * 8);
    if (e.loop == "rolle") {
        const int s0 = std::max(0, aus - 32);
        int q[5];
        for (int i = 0; i < 5; ++i) q[i] = s0 + i * (aus - s0) / 4;
        const int groessen[4] = {8, 4, 2, 1};
        std::vector<LoopSection> plan;
        for (int i = 0; i < 4; ++i) plan.push_back({q[i], q[i + 1], groessen[i]});
        plan.push_back({aus, ende, 1});
        return plan;
    }
    return {{std::max(0, aus - 16), ende, std::stoi(e.loop) * 2}};
}

Automation automation(std::string_view kind, int bars, const Settings& e) {
    const int n = kAutomationPoints;
    Automation k;
    if (kind == "eigen") {
        eigenKurven(k, bars, e);
        runden(k);
        return k;
    }

    auto ein = [n](double von, double bis) { return ramp(n, von, bis); };
    auto aus = [n](double von, double bis) { return ausKurve(n, von, bis); };

    if (kind == "eq") {
        k.a["lautstaerke"] = aus(0, 1);
        k.b["lautstaerke"] = ein(0, 1);
        Curve aBass(static_cast<std::size_t>(n)), bBass(static_cast<std::size_t>(n));
        for (int i = 0; i < n; ++i) {
            const double x = static_cast<double>(i) / n;
            aBass[static_cast<std::size_t>(i)] = x < 0.5 ? 1.0f : 0.0f;
            bBass[static_cast<std::size_t>(i)] = x >= 0.5 ? 1.0f : 0.0f;
        }
        k.a["bass"] = aBass;
        k.b["bass"] = bBass;
    } else if (kind == "filter") {
        std::array<Curve, 3> ba, bb;
        for (int i = 0; i < 3; ++i) {
            ba[static_cast<std::size_t>(i)] = aus(kFilterWindows[i][0][0], kFilterWindows[i][0][1]);
            bb[static_cast<std::size_t>(i)] = ein(kFilterWindows[i][1][0], kFilterWindows[i][1][1]);
        }
        k.a["lautstaerke"] = aus(0.5, 1.0);
        k.b["lautstaerke"] = ein(0.0, 0.5);
        k.a["bass"] = ba[0];
        k.b["bass"] = bb[0];
        Curve aFilter(static_cast<std::size_t>(n)), bFilter(static_cast<std::size_t>(n));
        for (int i = 0; i < n; ++i) {
            float sa = 0.0f, sb = 0.0f;   // np.mean in float32
            for (int b = 0; b < 3; ++b) {
                sa += ba[static_cast<std::size_t>(b)][static_cast<std::size_t>(i)];
                sb += bb[static_cast<std::size_t>(b)][static_cast<std::size_t>(i)];
            }
            aFilter[static_cast<std::size_t>(i)] = 1.0f - sa / 3.0f;
            bFilter[static_cast<std::size_t>(i)] = 1.0f - sb / 3.0f;
        }
        k.a["filter"] = aFilter;
        k.b["filter"] = bFilter;
    } else if (kind == "echo") {
        const double takt = 1.0 / std::max(1, bars);
        const double schlag = takt / 4.0;
        Curve aVol(static_cast<std::size_t>(n)), aEcho(static_cast<std::size_t>(n)), bVol(static_cast<std::size_t>(n));
        for (int i = 0; i < n; ++i) {
            const double x = static_cast<double>(i) / n;
            const std::size_t j = static_cast<std::size_t>(i);
            aVol[j] = x < schlag ? 1.0f : 0.0f;
            aEcho[j] = x < schlag ? 0.0f : static_cast<float>(std::pow(0.7, (x - schlag) / schlag));
            bVol[j] = static_cast<float>(std::clamp((x - takt) / takt, 0.0, 1.0));
        }
        k.a["lautstaerke"] = aVol;
        k.b["lautstaerke"] = bVol;
        k.a["echo"] = aEcho;
    } else if (kind == "schnitt") {
        k.a["lautstaerke"].assign(static_cast<std::size_t>(n), 0.0f);
        k.b["lautstaerke"].assign(static_cast<std::size_t>(n), 1.0f);
    } else if (kind == "crossfade") {
        k.a["lautstaerke"] = aus(0, 1);
        k.b["lautstaerke"] = ein(0, 1);
    } else {
        throw std::invalid_argument("Automationskurven fuer Art '" + std::string(kind) +
                                    "' folgen mit den Stems (M11).");
    }
    runden(k);
    return k;
}

}  // namespace klangbild::dsp
