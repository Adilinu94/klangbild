#include "dsp/backen.h"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstddef>
#include <numeric>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "dsp/introloop.h"
#include "dsp/limiter.h"
#include "dsp/mischen_eigen.h"
#include "dsp/mixing.h"
#include "dsp/resample.h"   // padTo
#include "dsp/rounding.h"
#include "dsp/warp.h"

namespace klangbild::dsp {
namespace {

constexpr std::size_t ch = static_cast<std::size_t>(kChannels);
constexpr double kTempoSpiel = 0.5;      // uebergang.TEMPO_SPIEL
constexpr double kVorlaufMax = 0.08;     // regie.VORLAUF_MAX
constexpr int kVorlaufTakte = 16;        // regie.VORLAUF_TAKTE

bool istSyncArt(const std::string& art) {
    return art == "eq" || art == "crossfade" || art == "filter" || art == "eigen" ||
           art == "drums_zuerst" || art == "acapella" || art == "gesangsschutz" ||
           art == "gesang_zuerst" || art == "double_drop" || art == "melodie_zuerst";
}

bool istStemArt(const std::string& art) {
    return art == "drums_zuerst" || art == "acapella" || art == "gesangsschutz" ||
           art == "gesang_zuerst" || art == "double_drop" || art == "melodie_zuerst";
}

/// `uebergang._harmonisch` mit `keyestimate.camelot_nachbarn`.
bool harmonisch(const std::string& a, const std::string& b) {
    if (a.empty() || b.empty()) return false;
    if (a == b) return true;
    if (a.size() < 2 || !std::all_of(a.begin(), a.end() - 1, [](unsigned char c) { return std::isdigit(c) != 0; })) {
        return false;
    }
    const int nummer = std::stoi(a.substr(0, a.size() - 1));
    const char modus = a.back();
    const char anderer = modus == 'B' ? 'A' : 'B';
    for (int abstand = -1; abstand <= 1; ++abstand) {
        const int n = ((nummer - 1 + abstand) % 12 + 12) % 12 + 1;
        if (b == std::to_string(n) + modus) return true;
    }
    return b == std::to_string(nummer) + anderer;
}

long long runde(double v) { return static_cast<long long>(std::nearbyint(v)); }

std::vector<double> cumsum(const std::vector<double>& v) {
    std::vector<double> aus(v.size());
    double summe = 0.0;
    for (std::size_t i = 0; i < v.size(); ++i) {
        summe += v[i];
        aus[i] = summe;
    }
    return aus;
}

std::vector<float> ausschnitt(const std::vector<float>& y, long long von, long long bis) {
    const long long frames = static_cast<long long>(y.size() / ch);
    const long long a = std::clamp<long long>(von, 0, frames);
    const long long b = std::clamp<long long>(bis, 0, frames);
    if (b <= a) return {};
    return std::vector<float>(y.begin() + static_cast<std::ptrdiff_t>(a * static_cast<long long>(ch)),
                              y.begin() + static_cast<std::ptrdiff_t>(b * static_cast<long long>(ch)));
}

void anhaengen(std::vector<float>& ziel, const std::vector<float>& teil) {
    ziel.insert(ziel.end(), teil.begin(), teil.end());
}

void anhaengen(std::vector<double>& ziel, const std::vector<double>& teil) {
    ziel.insert(ziel.end(), teil.begin(), teil.end());
}

}  // namespace

Gebacken backen(const Spur& a, const Eintrag& b, std::span<const float> bAudio, const Settings& e, double abS,
                bool weiter, std::optional<double> ausS, std::optional<double> einS,
                std::span<const float> hallIr, std::span<const float> riserNoise, int rate) {
    int takte = weiter ? e.weiterTakte : e.takte;

    const Cut aus = ausstieg(a, e, takte, abS, weiter, ausS, rate);
    const std::vector<double>& abar = aus.raster;
    const int i0 = aus.index;

    std::vector<float> bAudioLokal(bAudio.begin(), bAudio.end());
    Cut ein = einstieg(b, static_cast<long long>(bAudioLokal.size() / ch), e, einS, rate);
    std::vector<double> bbar = std::move(ein.raster);
    const int j0 = ein.index;

    const double pA = periode(abar, i0);
    const double pB = periode(bbar, j0);
    const double bpmA = 240.0 / pA;
    const double bpmB = 240.0 / pB;
    bool sync = std::abs(bpmA - bpmB) <= std::max(e.maxBpm, 0.05) + kTempoSpiel;

    int vor = 0;
    if (!sync && e.tempoModus == "vorlauf" && !weiter && e.keylock) {
        if (std::abs(pA / pB - 1.0) <= kVorlaufMax) {
            for (int v : {kVorlaufTakte, kVorlaufTakte / 2}) {
                if (i0 >= v && abar[static_cast<std::size_t>(i0 - v)] >= abS - 1e-3) {
                    vor = v;
                    break;
                }
            }
            sync = vor > 0;
        }
    }

    IntroLoop introLoop;
    bool bLoop = false;
    if (sync && e.art == "eigen" && e.loopIn > 0 && e.loopInTimes > 0 &&
        j0 + e.loopIn < static_cast<int>(bbar.size())) {
        introLoop = klangbild::dsp::introLoop(bAudioLokal, bbar, j0, e.loopIn, e.loopInTimes, rate);
        bAudioLokal = introLoop.audio;
        bbar = introLoop.raster;
        bLoop = true;
    }

    std::string art = e.art;
    if (art == "auto") {
        art = (sync && harmonisch(a.eintrag.camelot, b.camelot)) ? "eq" : (takte > 1 ? "echo" : "schnitt");
    }
    if (istSyncArt(art) && !sync) art = "echo";
    if (art == "echo") takte = std::min(takte, 4);
    if (art == "schnitt") takte = 1;

    const double t0 = abar[static_cast<std::size_t>(i0)];

    std::string stemGrund;
    const bool willStems = sync && !bLoop &&
                           (istStemArt(e.art) || (e.art == "auto" && art == "eq" && e.stems));
    const bool nutzeStems = false;   // Stems folgen mit M11
    if (willStems) stemGrund = "Stems aus/nicht installiert";
    if (istStemArt(art) && !nutzeStems) {
        art = e.modus == "manuell" ? "eq" : "eigen";
        takte = std::min(takte, 16);
    }

    std::vector<double> perioden(static_cast<std::size_t>(takte));
    if (sync && e.tempoModus == "b_an_a") {
        std::fill(perioden.begin(), perioden.end(), pA);
    } else if (sync && (e.tempoModus == "a_an_b" || e.tempoModus == "vorlauf")) {
        std::fill(perioden.begin(), perioden.end(), pB);
    } else if (sync) {
        for (int k = 0; k < takte; ++k) {
            perioden[static_cast<std::size_t>(k)] =
                pA + (pB - pA) * (static_cast<double>(k) + 0.5) / static_cast<double>(takte);
        }
    } else {
        for (int k = 0; k < takte; ++k) {
            perioden[static_cast<std::size_t>(k)] =
                abar[static_cast<std::size_t>(i0 + k + 1)] - abar[static_cast<std::size_t>(i0 + k)];
        }
    }
    std::vector<double> ziel(static_cast<std::size_t>(takte) + 1);
    ziel[0] = t0;
    const std::vector<double> periodenSumme = cumsum(perioden);
    for (int k = 0; k < takte; ++k) ziel[static_cast<std::size_t>(k + 1)] = t0 + periodenSumme[static_cast<std::size_t>(k)];

    const double laenge = ziel.back() - t0;
    const double bEnde = static_cast<double>(bAudioLokal.size() / ch) / static_cast<double>(rate);
    const int j1 = j0 + takte;
    std::vector<double> restOrig;
    for (std::size_t k = static_cast<std::size_t>(j1); k < bbar.size(); ++k) {
        if (bbar[k] < bEnde) restOrig.push_back(bbar[k]);
    }
    restOrig.push_back(bEnde);
    const bool bAnA = sync && e.tempoModus == "b_an_a";

    const double tVor = abar[static_cast<std::size_t>(i0 - vor)];
    std::vector<double> zielVor(static_cast<std::size_t>(vor) + 1, tVor);
    {
        std::vector<double> periodenVor(static_cast<std::size_t>(vor));
        for (int k = 0; k < vor; ++k) {
            periodenVor[static_cast<std::size_t>(k)] =
                pA + (pB - pA) * (static_cast<double>(k) + 0.5) / static_cast<double>(std::max(1, vor));
        }
        const std::vector<double> summe = cumsum(periodenVor);
        for (int k = 0; k < vor; ++k) zielVor[static_cast<std::size_t>(k + 1)] = tVor + summe[static_cast<std::size_t>(k)];
    }
    const long long nVor = vor ? runde((zielVor.back() - tVor) * static_cast<double>(rate)) : 0;

    // A geht am Blendenbeginn nahtlos aus dem Original in die gedehnte Fassung ueber.
    std::vector<double> quellA(abar.begin() + static_cast<std::ptrdiff_t>(i0 - vor),
                               abar.begin() + static_cast<std::ptrdiff_t>(i0 + takte + 1));
    std::vector<double> zielA;
    zielA.insert(zielA.end(), zielVor.begin(), zielVor.end() - 1);
    const double versatz = zielVor.back() - t0;
    for (double z : ziel) zielA.push_back(z + versatz);
    std::vector<float> aSeg = warp(a.puffer, quellA, zielA, e.keylock, true, false, rate);

    std::vector<float> bSeg;
    std::vector<double> restZiel;
    std::vector<float> rest;
    if (bAnA) {
        std::vector<double> restZielDiff;
        for (std::size_t k = 1; k < restOrig.size(); ++k) {
            restZielDiff.push_back((restOrig[k] - restOrig[k - 1]) * pA / pB);
        }
        restZiel.push_back(laenge);
        const std::vector<double> summe = cumsum(restZielDiff);
        for (double v : summe) restZiel.push_back(laenge + v);

        std::vector<double> quellB(bbar.begin() + static_cast<std::ptrdiff_t>(j0),
                                   bbar.begin() + static_cast<std::ptrdiff_t>(std::min<std::size_t>(static_cast<std::size_t>(j1), bbar.size())));
        anhaengen(quellB, restOrig);
        std::vector<double> zielB;
        zielB.insert(zielB.end(), ziel.begin(), ziel.end() - 1);
        for (double v : restZiel) zielB.push_back(t0 + v);
        const std::vector<float> voll = warp(bAudioLokal, quellB, zielB, e.keylock, false, false, rate);
        const std::size_t trenn = aSeg.size();
        bSeg.assign(voll.begin(), voll.begin() + static_cast<std::ptrdiff_t>(std::min(trenn, voll.size())));
        rest.assign(voll.begin() + static_cast<std::ptrdiff_t>(std::min(trenn, voll.size())), voll.end());
    } else if (sync) {
        std::vector<double> quellB(bbar.begin() + static_cast<std::ptrdiff_t>(j0),
                                   bbar.begin() + static_cast<std::ptrdiff_t>(std::min<std::size_t>(static_cast<std::size_t>(j1 + 1), bbar.size())));
        bSeg = warp(bAudioLokal, quellB, ziel, e.keylock, false, true, rate);
        restZiel.push_back(laenge);
        for (std::size_t k = 1; k < restOrig.size(); ++k) restZiel.push_back(laenge + (restOrig[k] - restOrig[0]));
        rest = ausschnitt(bAudioLokal, runde(restOrig[0] * static_cast<double>(rate)),
                          static_cast<long long>(bAudioLokal.size() / ch));
    } else {
        const long long start = runde(bbar[static_cast<std::size_t>(j0)] * static_cast<double>(rate));
        bSeg = ausschnitt(bAudioLokal, start, start + static_cast<long long>(aSeg.size() / ch));
    }

    std::vector<float> aVor(aSeg.begin(), aSeg.begin() + static_cast<std::ptrdiff_t>(std::min<std::size_t>(
        static_cast<std::size_t>(std::max<long long>(0, nVor)) * ch, aSeg.size())));
    aSeg.erase(aSeg.begin(), aSeg.begin() + static_cast<std::ptrdiff_t>(
        std::min<std::size_t>(static_cast<std::size_t>(std::max<long long>(0, nVor)) * ch, aSeg.size())));
    bSeg = padTo(std::move(bSeg), aSeg.size() / ch);

    std::vector<float> blende;
    std::vector<float> nachlauf;
    if (nutzeStems) {
        throw std::invalid_argument("backen: Stem-Uebergaenge folgen mit M11.");
    }
    if (art == "eigen") {
        Settings eigen = e;
        if (eigen.loop == "auto") {
            const LoopChoice wahl = loopInOriginal(a.puffer, abar, i0, takte, std::nullopt, rate);
            eigen.loop = std::to_string(4 * wahl.bars);
            eigen.loopStart = wahl.start;
        }
        std::vector<double> taktN(ziel.size());
        for (std::size_t k = 0; k < ziel.size(); ++k) taktN[k] = ziel[k] - t0;
        const EigenBlend gemischt = mischenEigen(aSeg, bSeg, eigen, taktN, hallIr, riserNoise, rate);
        blende = gemischt.blende;
        nachlauf = gemischt.nachlauf;
    } else {
        blende = mix(art, aSeg, bSeg, takte);
    }

    if (vor) {
        std::vector<float> zusammen = aVor;
        anhaengen(zusammen, blende);
        blende = std::move(zusammen);
    }

    std::vector<float> puffer;
    std::vector<double> orig, buf;
    if (!sync) {
        const long long start = runde(bbar[static_cast<std::size_t>(j0)] * static_cast<double>(rate));
        puffer = blende;
        anhaengen(puffer, ausschnitt(bAudioLokal, start + static_cast<long long>(blende.size() / ch),
                                     static_cast<long long>(bAudioLokal.size() / ch)));
        orig.assign(bbar.begin() + j0, bbar.end());
        buf.resize(orig.size());
        for (std::size_t k = 0; k < orig.size(); ++k) buf[k] = orig[k] - bbar[static_cast<std::size_t>(j0)];
    } else {
        puffer = blende;
        anhaengen(puffer, rest);
        orig.assign(bbar.begin() + j0, bbar.begin() + std::min<std::size_t>(static_cast<std::size_t>(j1), bbar.size()));
        anhaengen(orig, restOrig);
        for (int k = 0; k < takte; ++k) buf.push_back(ziel[static_cast<std::size_t>(k)] - t0);
        anhaengen(buf, restZiel);
        const double vorS = static_cast<double>(nVor) / static_cast<double>(rate);
        for (double& v : buf) v += vorS;
    }

    const long long blendeFrames = static_cast<long long>(blende.size() / ch);
    const long long pufferFrames = static_cast<long long>(puffer.size() / ch);
    const long long nFahne = std::min<long long>(static_cast<long long>(nachlauf.size() / ch),
                                                 pufferFrames - blendeFrames);
    for (long long i = 0; i < nFahne; ++i) {
        for (std::size_t c = 0; c < ch; ++c) {
            puffer[static_cast<std::size_t>(blendeFrames + i) * ch + c] += nachlauf[static_cast<std::size_t>(i) * ch + c];
        }
    }
    begrenzen(puffer, bAnA ? pufferFrames : blendeFrames + nFahne + static_cast<long long>(rate), kDecke, rate,
              kChannels);

    if (bLoop) orig = introLoopBack(introLoop, orig);

    std::vector<std::size_t> reihenfolge(orig.size());
    std::iota(reihenfolge.begin(), reihenfolge.end(), 0);
    std::stable_sort(reihenfolge.begin(), reihenfolge.end(),
                     [&orig](std::size_t x, std::size_t y) { return orig[x] < orig[y]; });
    std::vector<double> origEindeutig, bufEindeutig;
    for (std::size_t k : reihenfolge) {
        if (!origEindeutig.empty() && origEindeutig.back() == orig[k]) continue;
        origEindeutig.push_back(orig[k]);
        bufEindeutig.push_back(buf[k]);
    }

    Gebacken ergebnis;
    ergebnis.startN = runde(tVor * static_cast<double>(rate));
    ergebnis.spur.eintrag = b;
    ergebnis.spur.frames = pufferFrames;
    ergebnis.spur.puffer = std::move(puffer);
    ergebnis.spur.orig = std::move(origEindeutig);
    ergebnis.spur.buf = std::move(bufEindeutig);

    const double aStart = a.zuOriginal(tVor);
    const double gesamt = laenge + static_cast<double>(nVor) / static_cast<double>(rate);

    BackInfo& info = ergebnis.info;
    info.art = art;
    info.takte = takte;
    info.sync = sync;
    info.bpmA = roundTo(bpmA, 2);
    info.bpmB = roundTo(bpmB, 2);
    info.modus = sync ? e.tempoModus : "frei";
    info.stems = nutzeStems;
    info.hinweis = stemGrund;
    info.blendeS = roundTo(gesamt, 3);
    info.aOrigStart = roundTo(aStart, 3);
    info.bOrigStart = roundTo(bLoop ? introLoopBack(introLoop, std::vector<double>{bbar[static_cast<std::size_t>(j0)]})[0]
                                    : bbar[static_cast<std::size_t>(j0)],
                              3);
    info.aOrigProS = gesamt > 0.0 ? roundTo((a.zuOriginal(ziel.back()) - aStart) / gesamt, 5) : 1.0;
    if (vor) {
        info.hatVorlauf = true;
        info.vorlaufS = roundTo(static_cast<double>(nVor) / static_cast<double>(rate), 3);
        info.vorlaufTakte = vor;
    }
    {
        std::vector<double> raster;
        for (double z : ziel) raster.push_back(z - t0);
        const double ende = ziel.back() - t0;
        for (int k = 1; k < 5; ++k) raster.push_back(ende + pB * static_cast<double>(k));
        const double vorS = static_cast<double>(nVor) / static_cast<double>(rate);
        for (double& v : raster) v = roundTo(v + vorS, 4);
        info.rasterS = std::move(raster);
    }
    info.kurven = automation(art, takte, e);
    if (art == "eigen") {
        std::vector<double> blendZeiten;
        for (double z : ziel) blendZeiten.push_back(z - t0);
        info.aLoop = loopInfo(e, blendZeiten);
    }
    if (bLoop) {
        info.hatIntroLoop = true;
        info.introTakte = e.loopIn;
        info.introMal = e.loopInTimes;
    }
    return ergebnis;
}

}  // namespace klangbild::dsp
