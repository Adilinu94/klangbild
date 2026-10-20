#include "dsp/warp_keylock.h"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <numbers>
#include <vector>

#include "dsp/mixing.h"     // kChannels
#include "dsp/stretch.h"

namespace klangbild::dsp {
namespace {

constexpr std::size_t ch = static_cast<std::size_t>(kChannels);
constexpr long long kNaht = 1024;          // uebergang.NAHT
constexpr long long kSuche = 441;          // uebergang.SUCHE
constexpr long long kKontext = 8192;       // uebergang.KONTEXT
constexpr long long kMaxLauf = 30LL * 44100;   // uebergang.MAX_LAUF

/// `uebergang._ausschnitt`: y[von : von+laenge], ausserhalb mit Stille.
std::vector<float> ausschnitt(std::span<const float> y, long long von, long long laenge) {
    const long long n = std::max<long long>(0, laenge);
    std::vector<float> aus(static_cast<std::size_t>(n) * ch, 0.0f);
    const long long frames = static_cast<long long>(y.size() / ch);
    const long long a = std::max<long long>(0, von);
    const long long b = std::min<long long>(frames, von + laenge);
    for (long long i = a; i < b; ++i) {
        for (std::size_t c = 0; c < ch; ++c) {
            aus[static_cast<std::size_t>(i - von) * ch + c] = y[static_cast<std::size_t>(i) * ch + c];
        }
    }
    return aus;
}

double korrelation(const std::vector<float>& a, const std::vector<float>& b) {
    const long long frames = static_cast<long long>(std::min(a.size(), b.size()) / ch);
    double dot = 0.0, aa = 0.0, bb = 0.0;
    for (long long i = 0; i < frames; ++i) {
        const double x = static_cast<double>(a[static_cast<std::size_t>(i) * ch] +
                                             a[static_cast<std::size_t>(i) * ch + 1]);
        const double y = static_cast<double>(b[static_cast<std::size_t>(i) * ch] +
                                             b[static_cast<std::size_t>(i) * ch + 1]);
        dot += x * y;
        aa += x * x;
        bb += y * y;
    }
    return dot / std::max(std::sqrt(aa * bb), 1e-12);
}

/// `uebergang._ausrichten`: Verschiebung in [lo, hi], bei der y[start+tau:] am besten zu ref passt.
long long ausrichten(const std::vector<float>& ref, const std::vector<float>& y, long long start, long long lo,
                     long long hi, double& korr) {
    korr = 0.0;
    if (hi < lo) return 0;
    const long long rf = static_cast<long long>(ref.size() / ch);
    const long long yf = static_cast<long long>(y.size() / ch);
    if (rf <= 0) return 0;
    std::vector<double> r(static_cast<std::size_t>(rf));
    for (long long i = 0; i < rf; ++i) {
        r[static_cast<std::size_t>(i)] = static_cast<double>(ref[static_cast<std::size_t>(i) * ch] +
                                                              ref[static_cast<std::size_t>(i) * ch + 1]);
    }
    const long long qVon = start + lo;
    const long long qEnde = std::min(yf, start + hi + rf);
    const long long qLaenge = std::max<long long>(0, qEnde - qVon);
    if (qVon < 0 || qLaenge < rf + (hi - lo)) return 0;
    std::vector<double> q(static_cast<std::size_t>(qLaenge));
    for (long long i = 0; i < qLaenge; ++i) {
        q[static_cast<std::size_t>(i)] = static_cast<double>(y[static_cast<std::size_t>(qVon + i) * ch] +
                                                              y[static_cast<std::size_t>(qVon + i) * ch + 1]);
    }
    const double rr = [&r] {
        double s = 0.0;
        for (double v : r) s += v * v;
        return s;
    }();
    long long best = 0;
    double bestNorm = -1e300;
    for (long long k = 0; k + rf <= qLaenge; ++k) {
        double kreuz = 0.0, energie = 0.0;
        for (long long j = 0; j < rf; ++j) {
            const double qv = q[static_cast<std::size_t>(k + j)];
            kreuz += qv * r[static_cast<std::size_t>(j)];
            energie += qv * qv;
        }
        const double norm = kreuz / std::sqrt(std::max(energie * rr, 1e-12));
        if (norm > bestNorm) {
            bestNorm = norm;
            best = k;
        }
    }
    korr = bestNorm;
    return lo + best;
}

/// `uebergang._ueberblenden`: Kreuzblende ohne Pegelloch, Normierung nach der Korrelation.
std::vector<float> ueberblenden(const std::vector<float>& alt, const std::vector<float>& neu, double korr) {
    const long long frames = static_cast<long long>(std::min(alt.size(), neu.size()) / ch);
    std::vector<float> aus(static_cast<std::size_t>(frames) * ch);
    for (long long i = 0; i < frames; ++i) {
        const double t = (static_cast<double>(i) + 0.5) / static_cast<double>(std::max<long long>(1, frames));
        const double w = std::pow(std::cos(t * std::numbers::pi / 2.0), 2.0);
        const double g = 1.0 / std::sqrt(std::max(w * w + (1.0 - w) * (1.0 - w) +
                                                      2.0 * std::max(korr, 0.0) * w * (1.0 - w),
                                                  1e-6));
        for (std::size_t c = 0; c < ch; ++c) {
            const std::size_t idx = static_cast<std::size_t>(i) * ch + c;
            const double wert = (static_cast<double>(alt[idx]) * w + static_cast<double>(neu[idx]) * (1.0 - w)) * g;
            aus[idx] = static_cast<float>(wert);
        }
    }
    return aus;
}

}  // namespace

std::vector<float> warpKeylock(std::span<const float> audio, std::span<const long long> quell,
                               std::span<const long long> ziel, bool randVorn, bool randHinten, int rate) {
    const long long nAus = ziel.empty() ? 0 : ziel.back();
    std::vector<float> aus(static_cast<std::size_t>(std::max<long long>(0, nAus)) * ch, 0.0f);
    if (quell.size() < 2 || ziel.size() != quell.size()) return aus;
    const long long frames = static_cast<long long>(audio.size() / ch);

    std::vector<double> faktoren(quell.size() - 1);
    for (std::size_t i = 0; i + 1 < quell.size(); ++i) {
        faktoren[i] = static_cast<double>(quell[i + 1] - quell[i]) /
                      static_cast<double>(std::max<long long>(1, ziel[i + 1] - ziel[i]));
    }
    std::vector<std::size_t> grenzen{0};
    for (std::size_t i = 1; i < faktoren.size(); ++i) {
        const double ref = faktoren[grenzen.back()];
        if (std::abs(faktoren[i] - ref) > 0.001 * ref ||
            quell[i] - quell[grenzen.back()] > kMaxLauf) {
            grenzen.push_back(i);
        }
    }
    grenzen.push_back(faktoren.size());

    struct Lauf {
        long long za = 0, ze = 0;
        bool still = true;
        std::size_t auftrag = 0;
        long long basis = 0, qa = 0;
    };
    struct Auftrag {
        std::vector<float> stueck;
        double faktor = 1.0;
    };
    std::vector<Lauf> laeufe;
    std::vector<Auftrag> auftraege;
    for (std::size_t g = 0; g + 1 < grenzen.size(); ++g) {
        const std::size_t i0 = grenzen[g], i1 = grenzen[g + 1];
        const long long qa = quell[i0], qe = quell[i1], za = ziel[i0], ze = ziel[i1];
        if (ze <= za) continue;
        if (qe - qa < kNaht) {
            Lauf l;
            l.za = za;
            l.ze = ze;
            l.still = true;
            laeufe.push_back(l);
            continue;
        }
        const long long links = std::min<long long>(kKontext, std::max<long long>(0, qa));
        const long long rechts = std::min<long long>(kKontext, std::max<long long>(0, frames - qe));
        const double f = static_cast<double>(qe - qa) / static_cast<double>(ze - za);
        const long long basis = static_cast<long long>(std::nearbyint(static_cast<double>(links) / f));
        Lauf l;
        l.za = za;
        l.ze = ze;
        l.still = false;
        l.auftrag = auftraege.size();
        l.basis = basis;
        l.qa = qa;
        laeufe.push_back(l);
        Auftrag a;
        a.stueck = ausschnitt(audio, qa - links, (qe + rechts) - (qa - links));
        a.faktor = f;
        auftraege.push_back(std::move(a));
    }

    std::vector<std::vector<float>> ergebnisse;
    ergebnisse.reserve(auftraege.size());
    for (const Auftrag& a : auftraege) ergebnisse.push_back(dehnen(a.stueck, a.faktor, rate));

    bool hatVorher = false;
    std::vector<float> vy;
    long long vBasis = 0, vTau = 0, vZa = 0;
    for (const Lauf& l : laeufe) {
        if (l.still) {
            hatVorher = false;
            continue;
        }
        const std::vector<float>& y = ergebnisse[l.auftrag];
        const long long yFrames = static_cast<long long>(y.size() / ch);
        long long tau = 0;
        long long kern = l.za;
        if (hatVorher) {
            const long long s0 = std::max<long long>(0, l.za - kNaht / 2);
            const long long nb = std::min<long long>(kNaht, nAus - s0);
            const std::vector<float> alt = ausschnitt(vy, vBasis + vTau + s0 - vZa, nb);
            const long long start = l.basis + s0 - l.za;
            const long long lo = std::max(-kSuche, -start);
            const long long hi = std::min(kSuche, yFrames - start - nb);
            double korr = 0.0;
            tau = ausrichten(alt, y, start, lo, hi, korr);
            const std::vector<float> neu = ausschnitt(y, start + tau, nb);
            const std::vector<float> gemischt = ueberblenden(alt, neu, korr);
            for (long long i = 0; i < nb; ++i) {
                for (std::size_t c = 0; c < ch; ++c) {
                    aus[static_cast<std::size_t>(s0 + i) * ch + c] = gemischt[static_cast<std::size_t>(i) * ch + c];
                }
            }
            kern = s0 + nb;
        } else if (randVorn && l.za == 0) {
            const long long nb = std::min(kNaht, l.ze - l.za);
            const std::vector<float> alt = ausschnitt(audio, l.qa, nb);
            const long long lo = std::max(-kSuche, -l.basis);
            const long long hi = std::min(kSuche, yFrames - l.basis - nb);
            double korr = 0.0;
            tau = ausrichten(alt, y, l.basis, lo, hi, korr);
            const std::vector<float> neu = ausschnitt(y, l.basis + tau, nb);
            const std::vector<float> gemischt = ueberblenden(alt, neu, korr);
            for (long long i = 0; i < nb; ++i) {
                for (std::size_t c = 0; c < ch; ++c) {
                    aus[static_cast<std::size_t>(i) * ch + c] = gemischt[static_cast<std::size_t>(i) * ch + c];
                }
            }
            kern = nb;
        }
        const long long laenge = l.ze - kern;
        if (laenge > 0) {
            const std::vector<float> teil = ausschnitt(y, l.basis + tau + kern - l.za, laenge);
            for (long long i = 0; i < laenge; ++i) {
                for (std::size_t c = 0; c < ch; ++c) {
                    aus[static_cast<std::size_t>(kern + i) * ch + c] = teil[static_cast<std::size_t>(i) * ch + c];
                }
            }
        }
        vy = y;
        vBasis = l.basis;
        vTau = tau;
        vZa = l.za;
        hatVorher = true;
    }

    if (randHinten && nAus > 0) {
        const long long nb = std::min(kNaht, nAus);
        std::vector<float> alt(aus.begin() + static_cast<std::ptrdiff_t>((nAus - nb) * static_cast<long long>(ch)),
                               aus.end());
        const std::vector<float> neu = ausschnitt(audio, quell.back() - nb, nb);
        const std::vector<float> gemischt = ueberblenden(alt, neu, korrelation(alt, neu));
        for (long long i = 0; i < nb; ++i) {
            for (std::size_t c = 0; c < ch; ++c) {
                aus[static_cast<std::size_t>(nAus - nb + i) * ch + c] = gemischt[static_cast<std::size_t>(i) * ch + c];
            }
        }
    }
    return aus;
}

}  // namespace klangbild::dsp
