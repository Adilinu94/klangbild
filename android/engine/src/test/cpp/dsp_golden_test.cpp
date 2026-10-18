// Golden-Tests des DSP-Ports (BAUPLAN-ANDROID M5): jede portierte Funktion gegen die
// Python-Referenz aus android/testdata/golden. Toleranzen nach §12.3 (golden.h).
//
// Der volle Satz entsteht mit `python -m klangbild golden <ziel>`; die grossen Binaerdateien
// (.f32) liegen nicht im Repo. Fehlen sie, werden die betroffenen Tests uebersprungen (nicht
// still bestanden): GTEST_SKIP nennt den Grund.
#include <gtest/gtest.h>

#include <cmath>
#include <cstdlib>
#include <fstream>
#include <string>
#include <vector>

#include "dsp/curves.h"
#include "dsp/filters.h"
#include "golden.h"

namespace {

using klangbild::test::Golden;
using klangbild::test::GoldenCase;
using klangbild::test::GoldenError;
using klangbild::test::Json;

std::string goldenDir() {
    const char* fromEnv = std::getenv("KLINGBILD_GOLDENDIR");
    if (fromEnv != nullptr && fromEnv[0] != '\0') return fromEnv;
#ifdef KLINGBILD_GOLDENDIR_DEFAULT
    return KLINGBILD_GOLDENDIR_DEFAULT;
#else
    return "testdata/golden";
#endif
}

Golden& golden() {
    static Golden g{goldenDir()};
    return g;
}

/// Gibt es die Binaerdateien des vollen Satzes? (Pruefmarke: das erste Eingangssignal.)
[[maybe_unused]] bool hasBinaries() {
    return std::ifstream(goldenDir() + "/signal_a.f32", std::ios::binary).good();
}

#define REQUIRE_BINARIES()                                                                          \
    do {                                                                                            \
        if (!hasBinaries()) GTEST_SKIP() << "Golden-Binaerdateien fehlen: python -m klangbild golden <ziel>"; \
    } while (0)

std::vector<double> concat(const std::vector<float>& a, const std::vector<float>& b) {
    std::vector<double> v(a.begin(), a.end());
    v.insert(v.end(), b.begin(), b.end());
    return v;
}

}  // namespace

// ============================== T5.1 Kurven =====================================================

TEST(DspCurves, EqualPowerBlendMatchesGolden) {
    Golden& g = golden();
    const GoldenCase c = g.case_of("kurven_basis");
    const int n = static_cast<int>(c.inputs.at("n").as_double());
    const auto curves = klangbild::dsp::equalPowerBlend(n);
    ASSERT_EQ(static_cast<int>(curves.out.size()), n);
    g.expect_values("kurven_basis", c.expected, concat(curves.out, curves.in));   // erwartet: [aus, ein]
}

TEST(DspCurves, EqualPowerBlendEdgeCases) {
    EXPECT_TRUE(klangbild::dsp::equalPowerBlend(0).out.empty());
    EXPECT_TRUE(klangbild::dsp::equalPowerBlend(-3).in.empty());
    const auto one = klangbild::dsp::equalPowerBlend(1);
    ASSERT_EQ(one.out.size(), 1u);
    EXPECT_EQ(one.out[0], 1.0f);   // Endpunkt nicht enthalten: nur der Anfang
    EXPECT_EQ(one.in[0], 0.0f);
    for (int n : {2, 3, 8, 1000}) {
        const auto c = klangbild::dsp::equalPowerBlend(n);
        for (int i = 0; i < n; ++i) {
            const double sum = static_cast<double>(c.out[static_cast<std::size_t>(i)]) * c.out[static_cast<std::size_t>(i)] +
                               static_cast<double>(c.in[static_cast<std::size_t>(i)]) * c.in[static_cast<std::size_t>(i)];
            ASSERT_NEAR(sum, 1.0, 2e-7) << "n=" << n << " i=" << i;   // gleiche Leistung
        }
    }
}

// Bekannte Werte aus dem Python-Prototyp (uebergang._rampe, mix._bass_rampen), mit numpy 2.4.4 erzeugt.
// Die Funktionen haben keinen eigenen Golden-Fall; ihre Wirkung im Ganzen prueft T5.3 ueber `mischen`.
TEST(DspCurves, RampKnownValuesFromPrototype) {
    const auto r = klangbild::dsp::ramp(8, 0.25, 0.75);   // Anteile 0.25 .. 0.75 der Laenge
    const std::vector<float> expected = {0.0f, 0.0f, 0.0f, 0.3826834559440613f, 0.7071067690849304f,
                                         0.9238795042037964f, 1.0f, 1.0f};
    ASSERT_EQ(r.size(), expected.size());
    for (std::size_t i = 0; i < r.size(); ++i) EXPECT_NEAR(r[i], expected[i], 1e-7) << i;
    EXPECT_TRUE(klangbild::dsp::ramp(0, 0.0, 1.0).empty());
    // von == bis: der Teiler wird auf 1e-9 gesetzt, die Kurve ist eine Stufe
    const auto step = klangbild::dsp::ramp(4, 0.5, 0.5);
    EXPECT_EQ(step[1], 0.0f);
    EXPECT_EQ(step[2], 0.0f);   // t = 0.5 -> x = 0
    EXPECT_EQ(step[3], 1.0f);
}

TEST(DspCurves, BassRampsKnownValuesFromPrototype) {
    // n = 6: die Flanke (auf mitte = 3 gekappt) deckt den ganzen Puffer ab.
    const auto small = klangbild::dsp::bassRamps(6, 44100);
    const std::vector<float> out6 = {1.0f, 0.9330127239227295f, 0.75f, 0.5f, 0.25f, 0.06698727607727051f};
    const std::vector<float> in6 = {0.0f, 0.0669873058795929f, 0.25f, 0.5f, 0.75f, 0.9330127239227295f};
    ASSERT_EQ(small.out.size(), 6u);
    for (std::size_t i = 0; i < 6; ++i) {
        EXPECT_NEAR(small.out[i], out6[i], 1e-7) << i;
        EXPECT_NEAR(small.in[i], in6[i], 1e-7) << i;
    }
    // n = 4410: Stichproben um die Flanke (mitte = 2205, flanke = 441)
    const auto c = klangbild::dsp::bassRamps(4410, 44100);
    ASSERT_EQ(c.out.size(), 4410u);
    const int at[] = {0, 1763, 1764, 2205, 2645, 2646, 4409};
    const float aus[] = {1.0f, 1.0f, 1.0f, 0.5f, 3.159046173095703e-06f, 0.0f, 0.0f};
    const float ein[] = {0.0f, 0.0f, 0.0f, 0.5f, 0.9999968409538269f, 1.0f, 1.0f};
    for (int k = 0; k < 7; ++k) {
        EXPECT_NEAR(c.out[static_cast<std::size_t>(at[k])], aus[k], 1e-7) << at[k];
        EXPECT_NEAR(c.in[static_cast<std::size_t>(at[k])], ein[k], 1e-7) << at[k];
    }
    // Gleiche Leistung ist hier nicht gemeint, aber der Bass darf nie doppelt liegen: aus + ein = 1.
    for (std::size_t i = 0; i < c.out.size(); ++i) ASSERT_NEAR(c.out[i] + c.in[i], 1.0f, 1e-6f) << i;
    EXPECT_TRUE(klangbild::dsp::bassRamps(0, 44100).out.empty());
}

// ============================== T5.2 Filter und band_teilen =====================================

namespace {

/// Wie der Prototyp-Test: Stereo-Sinus mit Phasenversatz je Kanal (feste Formel, kein Zufall).
std::vector<float> formulaSignal(int frames, int channels) {
    std::vector<float> x(static_cast<std::size_t>(frames) * static_cast<std::size_t>(channels));
    for (int i = 0; i < frames; ++i)
        for (int c = 0; c < channels; ++c)
            x[static_cast<std::size_t>(i * channels + c)] = static_cast<float>(0.3 * std::sin(0.05 * i + 0.5 * c));
    return x;
}

double sum(const std::vector<float>& v) {
    double s = 0.0;
    for (float f : v) s += static_cast<double>(f);
    return s;
}

}  // namespace

TEST(DspFilters, ButterworthDesignMatchesGoldenSosTables) {
    Golden& g = golden();
    for (int rate : {44100, 22050}) {
        const Json table = g.raw("sos_" + std::to_string(rate));
        for (const char* hz : {"200", "2000", "2500", "3000", "5000"}) {
            const std::vector<double> want = table.at(hz).at("low").numbers();   // 2 Abschnitte x (b0 b1 b2 a0 a1 a2)
            const auto sos = klangbild::dsp::butterworthLowpass(4, std::stod(hz), rate);
            ASSERT_EQ(sos.size() * 6, want.size()) << rate << " " << hz;
            for (std::size_t s = 0; s < sos.size(); ++s) {
                const double got[6] = {sos[s].b0, sos[s].b1, sos[s].b2, 1.0, sos[s].a1, sos[s].a2};
                for (int k = 0; k < 6; ++k)
                    EXPECT_NEAR(got[k], want[s * 6 + static_cast<std::size_t>(k)], 1e-12) << rate << " Hz " << hz << " Abschnitt " << s << " Feld " << k;
            }
        }
    }
}

TEST(DspFilters, ButterworthDesignFor150HzAndOutOfRange) {
    // 150 Hz fehlt im Golden-Satz (Double-Drop trennt dort): Werte aus mix._sos("low", 150, 44100).
    const auto sos = klangbild::dsp::butterworthLowpass(4, 150.0, 44100);
    ASSERT_EQ(sos.size(), 2u);
    EXPECT_NEAR(sos[0].b0, 1.2680874150452645e-08, 1e-20);
    EXPECT_NEAR(sos[0].a1, -1.9608304562685264, 1e-12);
    EXPECT_NEAR(sos[0].a2, 0.9612783322580798, 1e-12);
    EXPECT_NEAR(sos[1].a1, -1.9833239558223639, 1e-12);
    EXPECT_NEAR(sos[1].a2, 0.983776969583181, 1e-12);
    // mix._sos liefert None ausserhalb von (0, Nyquist)
    EXPECT_TRUE(klangbild::dsp::butterworthLowpass(4, 0.0, 44100).empty());
    EXPECT_TRUE(klangbild::dsp::butterworthLowpass(4, 22050.0, 44100).empty());
    EXPECT_TRUE(klangbild::dsp::butterworthLowpass(4, -5.0, 44100).empty());
    EXPECT_THROW(klangbild::dsp::butterworthLowpass(3, 200.0, 44100), std::invalid_argument);
}

TEST(DspFilters, BandSplitMatchesGolden) {
    REQUIRE_BINARIES();
    Golden& g = golden();
    for (const char* name : {"band_200", "band_2000", "band_2500"}) {
        const GoldenCase c = g.case_of(name);
        const std::vector<double> in = g.values(c.inputs.at("signal"));
        const std::vector<float> signal(in.begin(), in.end());
        const int rate = static_cast<int>(c.inputs.at("rate").as_double());
        const double hz = c.inputs.at("trenn_hz").as_double();
        const auto split = klangbild::dsp::bandSplit(signal.data(), signal.size() / 2, 2, rate, hz);
        std::vector<double> got(split.low.begin(), split.low.end());
        got.insert(got.end(), split.high.begin(), split.high.end());
        ASSERT_EQ(c.tolerance, "dsp");
        g.expect_dsp(name, c.expected, got);   // erwartet: [tief, hoch]
    }
}

TEST(DspFilters, BandSplitShortSignalsFallBackToCausalFilter) {
    Golden& g = golden();
    for (const char* name : {"band_kurz_0", "band_kurz_1", "band_kurz_8", "band_kurz_15"}) {
        const GoldenCase c = g.case_of(name);
        const std::vector<double> in = g.values(c.inputs.at("signal"));
        const std::vector<float> signal(in.begin(), in.end());
        const int rate = static_cast<int>(c.inputs.at("rate").as_double());
        const auto split = klangbild::dsp::bandSplit(signal.data(), signal.size() / 2, 2, rate, c.inputs.at("trenn_hz").as_double());
        std::vector<double> got(split.low.begin(), split.low.end());
        got.insert(got.end(), split.high.begin(), split.high.end());
        g.expect_dsp(name, c.expected, got);
    }
}

// Genau an der Grenze der Polsterung (padlen = 15): bis 15 Samples kausal, ab 16 nullphasig.
// Referenz: mix.band_teilen des Prototyps (numpy 2.4.4, scipy 1.17.1) fuer `formulaSignal`.
TEST(DspFilters, BandSplitAtTheEdgeOfThePadding) {
    struct Case { int n; float low0[2], lowLast[2], highLast[2]; double sumLow, sumHigh; };
    const Case cases[] = {
        {16, {-0.1969512403011322f, 0.007944421842694283f}, {-0.19690638780593872f, 0.007974565960466862f},
         {0.4013980031013489f, 0.2767208218574524f}, -3.02332516, 8.32222223},
        {17, {-0.19618909060955048f, 0.008457423187792301f}, {-0.19613289833068848f, 0.0084952088072896f},
         {0.41133973002433777f, 0.28057223558425903f}, -3.19038532, 8.9935566},
        {40, {-0.161657452583313f, 0.03080841712653637f}, {-0.1595088243484497f, 0.03218516707420349f},
         {0.43819674849510193f, 0.15914423763751984f}, -5.13202261, 23.5431404},
    };
    for (const Case& c : cases) {
        const auto signal = formulaSignal(c.n, 2);
        const auto split = klangbild::dsp::bandSplit(signal.data(), static_cast<std::size_t>(c.n), 2, 44100, 200.0);
        for (int ch = 0; ch < 2; ++ch) {
            EXPECT_NEAR(split.low[static_cast<std::size_t>(ch)], c.low0[ch], 2e-6) << "n=" << c.n << " ch=" << ch;
            EXPECT_NEAR(split.low[static_cast<std::size_t>((c.n - 1) * 2 + ch)], c.lowLast[ch], 2e-6) << "n=" << c.n;
            EXPECT_NEAR(split.high[static_cast<std::size_t>((c.n - 1) * 2 + ch)], c.highLast[ch], 2e-6) << "n=" << c.n;
        }
        EXPECT_NEAR(sum(split.low), c.sumLow, 5e-5) << "n=" << c.n;
        EXPECT_NEAR(sum(split.high), c.sumHigh, 5e-5) << "n=" << c.n;
    }
}

TEST(DspFilters, BandSplitMonoAndOutOfRange) {
    const auto mono = formulaSignal(40, 1);
    const auto split = klangbild::dsp::bandSplit(mono.data(), 40, 1, 44100, 200.0);
    EXPECT_NEAR(sum(split.low), -6.40420023, 5e-5);
    EXPECT_NEAR(sum(split.high), 14.7629164, 5e-5);
    EXPECT_NEAR(split.low[20], -0.159825727f, 2e-6);
    // Trennfrequenz ausserhalb des Bereichs: das Signal bleibt, high ist 0 (mix._sos -> None)
    const auto stereo = formulaSignal(40, 2);
    const auto off = klangbild::dsp::bandSplit(stereo.data(), 40, 2, 44100, 30000.0);
    EXPECT_EQ(off.low, stereo);
    for (float h : off.high) ASSERT_EQ(h, 0.0f);
    // Low + High ergibt das Signal (komplementaer), bis auf float32-Rundung
    const auto st = klangbild::dsp::bandSplit(stereo.data(), 40, 2, 44100, 200.0);
    for (std::size_t i = 0; i < stereo.size(); ++i) ASSERT_NEAR(st.low[i] + st.high[i], stereo[i], 1e-6f) << i;
}
