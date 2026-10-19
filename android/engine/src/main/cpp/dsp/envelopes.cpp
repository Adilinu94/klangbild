#include "dsp/envelopes.h"

#include <algorithm>
#include <cmath>
#include <numbers>
#include <stdexcept>
#include <string>
#include <tuple>
#include <utility>

namespace klangbild::dsp {

namespace {

/// Hilfsklasse mit den Bausteinen aus `_huellen`: x, ein(v, b), aus(v, b) in float32.
class Builder {
public:
    explicit Builder(int n) : n_(static_cast<std::size_t>(std::max(n, 0))), x_(n_) {
        // x = (np.arange(n) / max(1, n)).astype(np.float32): Division in float64, dann float32.
        const double denom = static_cast<double>(std::max(1, n));
        for (std::size_t i = 0; i < n_; ++i) x_[i] = static_cast<float>(static_cast<double>(i) / denom);
    }

    std::size_t size() const { return n_; }
    const Curve& x() const { return x_; }

    /// ein(v, b): sin(pi/2 * clip((x - v) / max(1e-9, b - v), 0, 1)); Python-Skalare rechnen in float32.
    Curve in(double v, double b) const { return shaped(v, b, /*rising=*/true); }
    /// aus(v, b): cos(pi/2 * clip(...)).
    Curve out(double v, double b) const { return shaped(v, b, /*rising=*/false); }

    Curve zeros() const { return Curve(n_, 0.0f); }
    Curve copyOfX() const { return x_; }
    Curve oneMinusX() const {
        Curve r(n_);
        for (std::size_t i = 0; i < n_; ++i) r[i] = 1.0f - x_[i];
        return r;
    }

private:
    Curve shaped(double v, double b, bool rising) const {
        const float vF = static_cast<float>(v);
        const float spanF = static_cast<float>(std::max(1e-9, b - v));
        const float halfPi = static_cast<float>(std::numbers::pi / 2.0);
        Curve r(n_);
        for (std::size_t i = 0; i < n_; ++i) {
            const float c = std::clamp((x_[i] - vF) / spanF, 0.0f, 1.0f);
            r[i] = rising ? std::sin(halfPi * c) : std::cos(halfPi * c);
        }
        return r;
    }

    std::size_t n_;
    Curve x_;
};

Curve oneMinus(const Curve& a) {
    Curve r(a.size());
    for (std::size_t i = 0; i < a.size(); ++i) r[i] = 1.0f - a[i];
    return r;
}

Curve maximum(const Curve& a, const Curve& b) {
    Curve r(a.size());
    for (std::size_t i = 0; i < a.size(); ++i) r[i] = std::max(a[i], b[i]);   // np.maximum (keine NaN im Spiel)
    return r;
}

Curve multiply(const Curve& a, const Curve& b) {
    Curve r(a.size());
    for (std::size_t i = 0; i < a.size(); ++i) r[i] = a[i] * b[i];
    return r;
}

/// uebergang.FILTER_PLAN: welche Filterkurven je `filter`-Wahl gesetzt werden.
struct FilterPlan {
    bool aTp = false, bTp = false, aHp = false, bHp = false;
};

FilterPlan filterPlan(const std::string& filter) {
    if (filter == "keiner") return {};
    if (filter == "tp_aus" || filter == "tp_aus_reso") return {.aTp = true};
    if (filter == "tp_ein") return {.bTp = true};
    if (filter == "tp_beide") return {.aTp = true, .bTp = true};
    if (filter == "hp_aus" || filter == "hp_aus_reso") return {.aHp = true};
    if (filter == "hp_ein") return {.bHp = true};
    if (filter == "hp_beide") return {.aHp = true, .bHp = true};
    if (filter == "tp_ein_hp_aus") return {.bTp = true, .aHp = true};
    if (filter == "hp_ein_tp_aus") return {.aTp = true, .bHp = true};
    throw std::invalid_argument("unbekannter Filter: " + filter);
}

}  // namespace

Envelopes envelopes(const Settings& e, int bars, int n, double edge) {
    const Builder bld(n);
    const double k = edge;
    const double bar = 1.0 / static_cast<double>(std::max(1, bars));   // takt
    Envelopes h;

    // --- Lautstaerke -------------------------------------------------------------------------
    const std::string& v = e.volume;
    if (v == "nahtlos") { h.aVol = bld.out(0, 1); h.bVol = bld.in(0, 1); }
    else if (v == "linear") { h.aVol = bld.oneMinusX(); h.bVol = bld.copyOfX(); }
    else if (v == "ueberlappung") { h.aVol = bld.out(0.5, 1); h.bVol = bld.in(0, 0.5); }
    else if (v == "hart_ein") { h.aVol = bld.out(0, 1); h.bVol = bld.in(0, k); }
    else if (v == "hart_aus") { h.aVol = bld.out(1 - k, 1); h.bVol = bld.in(0, 1); }
    else if (v == "hart_beide") { h.aVol = bld.out(1 - k, 1); h.bVol = bld.in(0, k); }
    else if (v == "mitte") { h.aVol = bld.out(0.5 - k / 2, 0.5 + k / 2); h.bVol = bld.in(0.5 - k / 2, 0.5 + k / 2); }
    else if (v == "mitte_weich") { h.aVol = bld.out(0.5 - k / 2, 0.5 + k / 2); h.bVol = bld.in(0.5 - k / 2, 0.5 + bar); }
    else if (v == "frueh") { h.aVol = bld.out(0, 0.25); h.bVol = bld.in(0, 0.25); }
    else if (v == "spaet") { h.aVol = bld.out(0.75, 1); h.bVol = bld.in(0.75, 1); }
    else if (v == "letzter_takt") { h.aVol = bld.out(1 - bar, 1); h.bVol = bld.in(0, 1); }
    else if (v == "drop") { h.aVol = bld.out(1 - k, 1); h.bVol = bld.in(1 - std::min(0.5, 4 * bar), 1 - std::min(0.25, 2 * bar)); }
    else if (v == "doppel") { h.aVol = bld.out(1 - bar, 1); h.bVol = bld.in(0, bar); }
    else throw std::invalid_argument("unbekannte lautstaerke: " + v);

    // --- Tricks, die die Fader ueberschreiben ------------------------------------------------
    if (e.trick == "wechsel" && 0 < e.vocalBar && e.vocalBar < bars - 2) {
        const int g = e.vocalBar;
        Curve bOn = bld.zeros();
        for (int t0 = g; t0 < bars; ++t0) {
            if (((t0 - g) / 2) % 2 == 1 || t0 >= bars - 2) {
                const Curve rise = bld.in(t0 * bar, t0 * bar + k);
                const Curve candidate = t0 < bars - 1 ? multiply(rise, bld.out((t0 + 1) * bar - k, (t0 + 1) * bar)) : rise;
                bOn = maximum(bOn, candidate);
            }
        }
        h.aVol = oneMinus(bOn);
        h.bVol = bOn;
    }
    if (e.trick == "teaser" && bars >= 4) {
        Curve gate = bld.zeros();
        const int from = bars >= 8 ? bars - 8 : bars - 4;
        const int to = bars >= 8 ? bars - 4 : bars - 1;
        for (int t0 = from; t0 < to; ++t0) {
            gate = maximum(gate, multiply(bld.in((t0 + 0.75) * bar, (t0 + 0.75) * bar + k),
                                          bld.out((t0 + 1) * bar - k, (t0 + 1) * bar)));
        }
        const Curve aNew = multiply(h.aVol, oneMinus(gate));
        const Curve bNew = maximum(h.bVol, gate);
        h.aVol = aNew;
        h.bVol = bNew;
    }

    // --- EQ: Bass-Tausch auf einer Taktgrenze (nie zwei Baesse, nie keiner) -------------------
    const auto swap = [&](double p) { return std::pair<Curve, Curve>{bld.out(p - bar / 8, p + bar / 8), bld.in(p - bar / 8, p + bar / 8)}; };
    if (e.eq == "profi") {
        const int s = std::max(1, bars / 4);
        const int pb = (0 < e.bassBar && e.bassBar < bars) ? e.bassBar : std::max(1, bars - s);
        const int pm = std::max(1, std::min(2 * s, pb - s));
        const int ph = std::max(1, std::min(s, pm - s));
        h.aVol = bld.out(1 - bar, 1);
        h.bVol = bld.in(0, bar);
        // vor = (10 ** ((-30 + 18 * clip(x / max(1e-9, ph * takt), 0, 1)) / 20)).astype(np.float32)   (alles float32)
        const float denom = static_cast<float>(std::max(1e-9, ph * bar));
        const float limit = static_cast<float>(ph * bar);
        Curve pre(bld.size());
        for (std::size_t i = 0; i < pre.size(); ++i) {
            const float c = std::clamp(bld.x()[i] / denom, 0.0f, 1.0f);
            const float dB = (-30.0f + 18.0f * c) / 20.0f;
            const float gain = std::pow(10.0f, dB);
            pre[i] = bld.x()[i] < limit ? gain : 0.0f;   // vor * (x < ph * takt)
        }
        auto [aHigh, bHigh] = swap(ph * bar);
        h.aHigh = std::move(aHigh);
        h.bHigh = maximum(bHigh, pre);
        auto [aMid, bMid] = swap(pm * bar);
        h.aMid = std::move(aMid);
        h.bMid = std::move(bMid);
        auto [aLow, bLow] = swap(pb * bar);
        h.aLow = std::move(aLow);
        h.bLow = std::move(bLow);
    } else if (e.eq == "bass_mitte") {
        std::tie(h.aLow, h.bLow) = swap(0.5);
    } else if (e.eq == "bass_anfang") {
        std::tie(h.aLow, h.bLow) = swap(bars > 1 ? bar : 0.25);
    } else if (e.eq == "bass_ende") {
        std::tie(h.aLow, h.bLow) = swap(bars > 1 ? 1 - bar : 0.75);
    } else if (e.eq == "drei_band") {   // Hoehen von B zuerst, Mitten in der Mitte, Bass-Tausch, A's Hoehen zuletzt
        h.aLow = bld.out(0.45, 0.55); h.bLow = bld.in(0.45, 0.55);
        h.aMid = bld.out(0.25, 0.75); h.bMid = bld.in(0.25, 0.75);
        h.aHigh = bld.out(0.5, 1.0); h.bHigh = bld.in(0.0, 0.5);
    } else if (e.eq == "bass_schnell") {   // A verliert den Bass im ersten Takt, B bringt ihn mit
        h.aLow = bld.out(0, bar);
    } else if (e.eq == "bass_lang") {
        h.aLow = bld.out(0, 1); h.bLow = bld.in(0, 1);
    } else if (e.eq == "bass_takt") {   // Double Drop: nur ein Bass, Tausch genau auf `bass_takt`
        std::tie(h.aLow, h.bLow) = swap((0 < e.bassBar && e.bassBar < bars) ? static_cast<double>(e.bassBar) / bars : 0.5);
    }

    // --- Filter: A schliesst ueber die Blende, B oeffnet ---------------------------------------
    const FilterPlan plan = filterPlan(e.filter);
    const bool withEffect = e.effect != "keiner";
    const auto filterCurveA = [&]() {
        Curve c = bld.copyOfX();
        if (withEffect) for (float& f : c) f = std::min(f, 0.6f);   // Filter auf ~60 %, dann ins Echo
        return c;
    };
    if (plan.aTp) h.aLowpass = filterCurveA();
    if (plan.bTp) h.bLowpass = bld.oneMinusX();
    if (plan.aHp) h.aHighpass = filterCurveA();
    if (plan.bHp) h.bHighpass = bld.oneMinusX();

    // --- Effekt (Send vor EQ und Fader) -------------------------------------------------------
    if (withEffect) {
        const std::size_t us = e.effect.find('_');
        const std::string mode = us == std::string::npos ? e.effect : e.effect.substr(us + 1);
        const double p = mode == "mitte_aus" ? 0.5 : 1.0;
        const double fx = std::min(2 * bar, p / 2);
        const Curve rise = bld.in(p - fx, p - 0.75 * fx);
        const float pF = static_cast<float>(p);
        Curve send(bld.size());
        for (std::size_t i = 0; i < send.size(); ++i) send[i] = bld.x()[i] < pF ? rise[i] : 0.0f;   // np.where(x < p, ..., 0)
        h.aSend = std::move(send);
        if (p < 1) h.aVol = multiply(h.aVol, bld.out(p, p + k));   // A endet am Effektpunkt, die Fahne klingt aus
        if (mode == "ende_ab") h.wetOff = bld.out(1 - k, 1);
    }
    if (e.effectIn == "rueckhall") {   // Reverse-Reverb: schwillt bis zu B's Einsatz (b_vol halb oben)
        std::size_t first = 0;         // np.argmax(b_vol >= 0.5): erster Treffer, sonst 0
        for (std::size_t i = 0; i < h.bVol.size(); ++i) {
            if (h.bVol[i] >= 0.5f) { first = i; break; }
        }
        h.bReverse = static_cast<double>(first) / static_cast<double>(std::max(1, n));
    }
    if (e.effectIn == "hall") {        // B kommt aus dem Hall: erst nass (vor dem Fader), nach ~2 Takten trocken
        h.bSend = bld.out(std::min(bar, 0.25), std::min(3 * bar, 0.5));
    }
    return h;
}

}  // namespace klangbild::dsp
