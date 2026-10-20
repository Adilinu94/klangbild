#include "dsp/raster.h"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <numbers>
#include <vector>

namespace klangbild::dsp {
namespace {

constexpr double kRate = 44100.0;

double medians(std::vector<double> v) {
    if (v.empty()) return 0.0;
    const std::size_t n = v.size();
    std::sort(v.begin(), v.end());
    return (n % 2 == 1) ? v[n / 2] : (v[n / 2 - 1] + v[n / 2]) / 2.0;
}

/// `np.angle(np.exp(1j*x))`: x auf (-pi, pi] gewickelt.
double wrapPi(double x) { return std::atan2(std::sin(x), std::cos(x)); }

/// `x % b` wie numpy: Ergebnis traegt das Vorzeichen von `b`.
double nmod(double x, double b) {
    double r = std::fmod(x, b);
    if (r != 0.0 && ((r < 0.0) != (b < 0.0))) r += b;
    return r;
}

/// `np.interp(x, xp, fp)`: ausserhalb konstant, dazwischen linear.
double interpConst(double x, const std::vector<double>& xp, const std::vector<double>& fp) {
    if (xp.empty()) return 0.0;
    if (x <= xp.front()) return fp.front();
    if (x >= xp.back()) return fp.back();
    std::size_t k = 1;
    while (k < xp.size() && xp[k] < x) ++k;
    const double steigung = (fp[k] - fp[k - 1]) / (xp[k] - xp[k - 1]);
    return steigung * (x - xp[k - 1]) + fp[k - 1];
}

int naechsterIndex(const std::vector<double>& werte, double ab, bool phrase, int start = 0) {
    for (int i = start; i < static_cast<int>(werte.size()); ++i) {
        if (werte[static_cast<std::size_t>(i)] >= ab && (!phrase || i % kPhrase == 0)) return i;
    }
    return static_cast<int>(werte.size()) - 1;
}

int phraseBei(const std::vector<double>& werte, double t) {
    int best = 0;
    double bestAbstand = 1e300;
    for (int i = 0; i < static_cast<int>(werte.size()); i += kPhrase) {
        const double abstand = std::abs(werte[static_cast<std::size_t>(i)] - t);
        if (abstand < bestAbstand) {
            bestAbstand = abstand;
            best = i;
        }
    }
    return best;
}

int argminAbs(const std::vector<double>& werte, double t) {
    int best = 0;
    double bestAbstand = 1e300;
    for (int i = 0; i < static_cast<int>(werte.size()); ++i) {
        const double abstand = std::abs(werte[static_cast<std::size_t>(i)] - t);
        if (abstand < bestAbstand) {
            bestAbstand = abstand;
            best = i;
        }
    }
    return best;
}

int floordiv(int a, int b) {
    int q = a / b;
    if (a % b != 0 && ((a < 0) != (b < 0))) --q;
    return q;
}

}  // namespace

double ext(double x, const std::vector<double>& xp, const std::vector<double>& fp) {
    if (xp.size() < 2) {
        return x - (xp.empty() ? 0.0 : xp[0]) + (fp.empty() ? 0.0 : fp[0]);
    }
    double y = interpConst(x, xp, fp);
    const double links = (fp[1] - fp[0]) / (xp[1] - xp[0]);
    const double rechts = (fp.back() - fp[fp.size() - 2]) / (xp.back() - xp[xp.size() - 2]);
    if (x < xp.front()) y = fp.front() + (x - xp.front()) * links;
    if (x > xp.back()) y = fp.back() + (x - xp.back()) * rechts;
    return y;
}

std::vector<double> raster(std::span<const double> takte, double bisS) {
    std::vector<double> t(takte.begin(), takte.end());
    if (t.size() < 2) {
        if (t.empty()) {
            t = {0.0, 2.0};
        } else {
            t = {t[0], t[0] + 2.0};
        }
    }
    const std::size_t von = t.size() > 8 ? t.size() - 8 : 0;
    std::vector<double> abstaende;
    for (std::size_t i = von + 1; i < t.size(); ++i) abstaende.push_back(t[i] - t[i - 1]);
    const double p = medians(abstaende);
    if (t.back() < bisS && p > 0.0) {
        const double ende = t.back();
        const int m = static_cast<int>((bisS - ende) / p) + 1;   // np.arange(1, m+1)
        for (int k = 1; k <= m; ++k) t.push_back(ende + p * static_cast<double>(k));
    }
    return t;
}

std::vector<double> regulaer(std::span<const double> downbeats, double bpm, double bisS) {
    const double taktPeriode = bpm > 0.0 ? 240.0 / bpm : 2.0;
    std::vector<double> d(downbeats.begin(), downbeats.end());
    if (d.empty()) {
        const int n = static_cast<int>(std::max(bisS, taktPeriode) / taktPeriode) + 2;
        std::vector<double> t(static_cast<std::size_t>(n));
        for (int i = 0; i < n; ++i) t[static_cast<std::size_t>(i)] = taktPeriode * static_cast<double>(i);
        return t;
    }

    const double schlag = taktPeriode / 4.0;
    std::vector<double> w(d.size());
    for (std::size_t i = 0; i < d.size(); ++i) w[i] = wrapPi(2.0 * std::numbers::pi * d[i] / schlag);

    std::array<double, 16> h{};
    const double step = 2.0 * std::numbers::pi / 16.0;
    for (double v : w) {
        int idx = static_cast<int>(std::floor((v + std::numbers::pi) / step));
        idx = std::clamp(idx, 0, 15);
        h[static_cast<std::size_t>(idx)] += 1.0;
    }
    std::array<double, 16> summe{};
    for (int i = 0; i < 16; ++i) {
        summe[static_cast<std::size_t>(i)] =
            h[static_cast<std::size_t>(i)] + h[static_cast<std::size_t>((i + 15) % 16)] +
            h[static_cast<std::size_t>((i + 1) % 16)];
    }
    int best = 0;
    for (int i = 1; i < 16; ++i) {
        if (summe[static_cast<std::size_t>(i)] > summe[static_cast<std::size_t>(best)]) best = i;
    }
    const double c = -std::numbers::pi + (static_cast<double>(best) + 0.5) * std::numbers::pi / 8.0;

    double sumCos = 0.0, sumSin = 0.0;
    int count = 0;
    for (double v : w) {
        if (std::abs(wrapPi(v - c)) <= std::numbers::pi / 4.0) {
            sumCos += std::cos(v);
            sumSin += std::sin(v);
            ++count;
        }
    }
    const double lage = (count > 0 ? std::atan2(sumSin, sumCos) : 0.0) / (2.0 * std::numbers::pi) * schlag;

    std::array<int, 4> zaehler{};
    for (double v : d) {
        const long long k = static_cast<long long>(std::nearbyint((v - lage) / schlag)) % 4;
        zaehler[static_cast<std::size_t>((k + 4) % 4)] += 1;
    }
    int eins = 0;
    for (int i = 1; i < 4; ++i) {
        if (zaehler[static_cast<std::size_t>(i)] > zaehler[static_cast<std::size_t>(eins)]) eins = i;
    }

    const double phase = lage + static_cast<double>(eins) * schlag;
    const double start = phase + taktPeriode * std::nearbyint((d[0] - phase) / taktPeriode);
    const int n = static_cast<int>(std::max(bisS - start, taktPeriode) / taktPeriode) + 2;
    std::vector<double> t(static_cast<std::size_t>(n));
    for (int i = 0; i < n; ++i) t[static_cast<std::size_t>(i)] = start + taktPeriode * static_cast<double>(i);

    std::vector<double> rest(d.size());
    std::vector<char> auf(d.size());
    for (std::size_t i = 0; i < d.size(); ++i) {
        rest[i] = nmod(d[i] - lage + schlag / 2.0, schlag) - schlag / 2.0;
        auf[i] = std::abs(rest[i]) < schlag / 4.0 ? 1 : 0;
    }
    std::vector<double> kx, ky;
    for (std::size_t i = 0; i < d.size(); ++i) {
        if (!auf[i]) continue;
        const double x = d[i];
        std::vector<double> werte;
        for (std::size_t j = 0; j < d.size(); ++j) {
            if (auf[j] && std::abs(d[j] - x) <= kDriftS) werte.push_back(rest[j]);
        }
        if (werte.size() >= 3) {
            kx.push_back(x);
            ky.push_back(medians(werte));
        }
    }
    if (!kx.empty()) {
        for (double& v : t) v += interpConst(v, kx, ky);
    }
    return t;
}

std::vector<double> taktraster(const Eintrag& eintrag, double bisS) {
    std::vector<double> t = regulaer(eintrag.downbeats, eintrag.bpm, bisS);
    if (!eintrag.fein.empty()) {
        std::vector<double> kx, ky;
        kx.reserve(eintrag.fein.size());
        ky.reserve(eintrag.fein.size());
        for (const auto& knoten : eintrag.fein) {
            kx.push_back(knoten[0]);
            ky.push_back(knoten[1]);
        }
        for (double& v : t) v += interpConst(v, kx, ky);
    }
    return t;
}

double periode(std::span<const double> t, int i, int halb) {
    const int lo = std::max(0, i - halb);
    const int hi = std::min(static_cast<int>(t.size()) - 1, i + halb);
    std::vector<double> d;
    for (int k = lo + 1; k <= hi; ++k) d.push_back(t[static_cast<std::size_t>(k)] - t[static_cast<std::size_t>(k - 1)]);
    if (d.empty()) return 2.0;
    const double m = medians(d);
    std::vector<double> kern;
    for (double v : d) {
        if (std::abs(v - m) <= 0.1 * m) kern.push_back(v);
    }
    if (kern.empty()) return m;
    double summe = 0.0;
    for (double v : kern) summe += v;
    return summe / static_cast<double>(kern.size());
}

Cut ausstieg(const Spur& a, const Settings& e, int takte, double abS, bool weiter, std::optional<double> ausS,
             int rate) {
    const double dauer = static_cast<double>(a.frames) / static_cast<double>(rate);
    std::vector<double> abar = raster(a.buf, dauer + 64.0 * 2.5);
    const int letzter = static_cast<int>(std::upper_bound(abar.begin(), abar.end(), dauer) - abar.begin()) - 1;
    int i0 = 0;
    if (ausS) {
        i0 = argminAbs(abar, a.zuPuffer(*ausS));
        if (abar[static_cast<std::size_t>(std::max(0, i0))] < abS - 1e-3) {
            i0 = naechsterIndex(abar, abS, !weiter);
        }
    } else if (weiter) {
        i0 = naechsterIndex(abar, abS, e.weiterAb == "phrase");
    } else {
        if (e.ausstieg == "outro" && !a.eintrag.abschnitte.empty()) {
            i0 = phraseBei(abar, a.zuPuffer(a.eintrag.abschnitte.back()));
        } else if (e.ausstieg == "vor_ende") {
            i0 = letzter - e.vorEndeTakte;
        } else {
            i0 = std::max(0, floordiv(letzter - takte, kPhrase) * kPhrase);
        }
        i0 = std::min(i0, std::max(0, letzter - takte));
        if (abar[static_cast<std::size_t>(std::max(0, i0))] < abS) i0 = naechsterIndex(abar, abS, true);
    }
    return {abar, std::max(0, i0)};
}

Cut einstieg(const Eintrag& b, long long bSamples, const Settings& e, std::optional<double> einS, int rate) {
    const double dauer = static_cast<double>(bSamples) / static_cast<double>(rate) + 64.0 * 2.5;
    std::vector<double> bbar = taktraster(b, dauer);
    if (einS) return {bbar, argminAbs(bbar, *einS)};
    if (e.einstieg == "drop" && !b.abschnitte.empty()) return {bbar, phraseBei(bbar, b.abschnitte[0])};
    return {bbar, 0};
}

Spur rohSpur(const Eintrag& eintrag, std::vector<float> puffer, int rate) {
    Spur spur;
    spur.eintrag = eintrag;
    spur.frames = static_cast<long long>(puffer.size() / 2);
    spur.puffer = std::move(puffer);
    spur.orig = taktraster(eintrag, static_cast<double>(spur.frames) / static_cast<double>(rate));
    spur.buf = spur.orig;
    return spur;
}

}  // namespace klangbild::dsp
