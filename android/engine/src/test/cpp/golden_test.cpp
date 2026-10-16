// Golden-Leser-Test (BAUPLAN-ANDROID §12.1, Aufgabe T0.3).
//
// Prueft, dass der C++-Leser JSON + `.f32` genau wie der Python-Export liest.
// Die eigentlichen DSP-Golden-Tests (band_teilen, mischen, backen ...) folgen
// ab M5 und nutzen denselben Leser.
//
// Der Golden-Ordner kommt aus -DKLINGBILD_GOLDENDIR (siehe build.gradle.kts).

#include "golden.h"

#include <gtest/gtest.h>

#include <cmath>
#include <cstdlib>
#include <string>
#include <vector>

namespace {

using klangbild::test::Golden;
using klangbild::test::GoldenError;
using klangbild::test::Json;

std::string goldendir() {
    // Vorrang: Umgebungsvariable (direkter Aufruf). Sonst der von CMake/Gradle
    // gesetzte Default (KLINGBILD_GOLDENDIR_DEFAULT, siehe CMakeLists.txt).
    const char* aus_umgebung = std::getenv("KLINGBILD_GOLDENDIR");
    if (aus_umgebung != nullptr && aus_umgebung[0] != '\0') {
        return aus_umgebung;
    }
#ifdef KLINGBILD_GOLDENDIR_DEFAULT
    return KLINGBILD_GOLDENDIR_DEFAULT;
#else
    return "testdata/golden";
#endif
}

TEST(GoldenReader, OrdnerVorhanden) {
    EXPECT_NO_THROW({ Golden g{goldendir()}; });
}

TEST(GoldenReader, ReaderDummyAusJsonUndF32) {
    Golden g{goldendir()};
    auto c = g.case_of("reader_dummy");

    EXPECT_EQ(c.function, "identity");
    EXPECT_EQ(c.tolerance, "values");

    const Json& audio = c.inputs.at("audio");
    EXPECT_EQ(audio.at("count").as_double(), 4.0);
    std::vector<int> shape;
    for (const auto& d : audio.at("shape").items) shape.push_back(static_cast<int>(d.as_double()));
    EXPECT_EQ(shape.size(), 2u);

    std::vector<float> werte = g.f32(audio.at("file").as_string(), shape);
    EXPECT_EQ(werte.size(), 4u);

    // Erwartete Werte aus dem JSON stimmen bitgenau mit der f32-Datei.
    const Json& erwartet = c.expected.at("values");
    std::vector<double> soll = erwartet.numbers();
    ASSERT_EQ(soll.size(), werte.size());
    for (size_t i = 0; i < soll.size(); ++i) {
        EXPECT_FLOAT_EQ(static_cast<float>(soll[i]), werte[i]);
    }
    EXPECT_EQ(c.expected.at("channels").as_double(), 2.0);
    EXPECT_EQ(c.expected.at("frames").as_double(), 2.0);
}

TEST(GoldenReader, KurzeReferenzkurve) {
    // kurven_basis ist der erste Fall, den ab T5.1 ein DSP-Test gegenrechnet.
    Golden g{goldendir()};
    auto c = g.case_of("kurven_basis");
    EXPECT_EQ(c.function, "mix.equal_power_blende");
    ASSERT_TRUE(c.expected.is_array());

    std::vector<double> aus = c.expected.items[0].numbers();
    std::vector<double> ein = c.expected.items[1].numbers();
    EXPECT_EQ(aus.size(), 64u);
    EXPECT_EQ(ein.size(), 64u);
    EXPECT_NEAR(aus[0], 1.0, 1e-6);
    // endpoint=False: sin(63/64 * pi/2), nicht genau 1.
    EXPECT_NEAR(ein[63], std::sin(63.0 / 64.0 * 3.14159265358979323846 / 2.0), 1e-6);

    // Equipotenz: cos^2 + sin^2 = 1 an jeder Stelle.
    for (size_t i = 0; i < aus.size(); ++i) {
        EXPECT_NEAR(aus[i] * aus[i] + ein[i] * ein[i], 1.0, 1e-6);
    }
}

TEST(GoldenReader, LangesArrayUeberF32) {
    Golden g{goldendir()};
    auto c = g.case_of("band_200");

    const Json& signal = c.inputs.at("signal");
    std::vector<int> shape;
    for (const auto& d : signal.at("shape").items) shape.push_back(static_cast<int>(d.as_double()));
    std::vector<float> werte = g.f32(signal.at("file").as_string(), shape);
    EXPECT_EQ(static_cast<size_t>(shape[0] * shape[1]), werte.size());

    ASSERT_TRUE(c.expected.is_array());
    std::vector<double> low = g.values(c.expected.items[0]);
    std::vector<double> high = g.values(c.expected.items[1]);
    ASSERT_EQ(low.size(), werte.size());
    ASSERT_EQ(high.size(), werte.size());

    // Komplementaer: low + high = Eingang (innerhalb float32-Grenzen).
    double max_fehler = 0.0;
    for (size_t i = 0; i < werte.size(); ++i) {
        max_fehler = std::max(max_fehler,
                              std::abs((low[i] + high[i]) - static_cast<double>(werte[i])));
    }
    EXPECT_LE(max_fehler, 1e-4);
}

TEST(GoldenReader, ManifestKenntSeineFaelle) {
    Golden g{goldendir()};
    Json manifest = g.raw("manifest");

    std::vector<std::string> faelle;
    for (const auto& f : manifest.at("cases").items) faelle.push_back(f.as_string());
    EXPECT_FALSE(faelle.empty());

    // Jeder im Manifest genannte Fall hat eine JSON-Datei.
    for (const auto& f : faelle) {
        EXPECT_NO_THROW(g.raw(f)) << "Fall ohne Datei: " << f;
    }

    const Json& toleranzen = manifest.at("tolerances");
    EXPECT_TRUE(toleranzen.has("values"));
    EXPECT_TRUE(toleranzen.has("dsp"));
    EXPECT_TRUE(toleranzen.has("reverb"));
    EXPECT_TRUE(toleranzen.has("warp"));
}

TEST(GoldenReader, FehlendesArrayMeldetHinweis) {
    Golden g{goldendir()};
    try {
        g.f32("gibt_es_nicht.f32", {1, 1});
        FAIL() << "Erwartete GoldenError";
    } catch (const GoldenError& e) {
        EXPECT_NE(std::string(e.what()).find("python -m klangbild golden"),
                  std::string::npos);
    }
}

}  // namespace
