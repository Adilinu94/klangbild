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
