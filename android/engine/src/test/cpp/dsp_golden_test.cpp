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
#include "dsp/envelopes.h"
#include "dsp/filters.h"
#include "dsp/mixing.h"
#include "dsp/sweep.h"
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

// ============================== T5.3 mischen ====================================================

namespace {

std::vector<float> floatsOf(Golden& g, const Json& ref) {
    const std::vector<double> v = g.values(ref);
    return std::vector<float>(v.begin(), v.end());
}

}  // namespace

TEST(DspMixing, MixMatchesGolden) {
    REQUIRE_BINARIES();
    Golden& g = golden();
    for (const char* art : {"eq", "filter", "echo", "schnitt", "crossfade"}) {
        for (int bars : {1, 4, 16}) {
            const std::string name = std::string("mischen_") + art + "_" + std::to_string(bars);
            SCOPED_TRACE(name);
            const GoldenCase c = g.case_of(name);
            ASSERT_EQ(c.inputs.at("art").as_string(), art);
            ASSERT_EQ(static_cast<int>(c.inputs.at("takte").as_double()), bars);
            const std::vector<float> a = floatsOf(g, c.inputs.at("a"));
            const std::vector<float> b = floatsOf(g, c.inputs.at("b"));
            const std::vector<float> out = klangbild::dsp::mix(art, a, b, bars);
            ASSERT_EQ(c.tolerance, "dsp");
            g.expect_dsp(name, c.expected, std::vector<double>(out.begin(), out.end()));
        }
    }
}

TEST(DspMixing, FadeSegmentAndEchoEdgeCases) {
    using klangbild::dsp::echo;
    using klangbild::dsp::fadeSegment;
    using klangbild::dsp::mix;
    EXPECT_TRUE(fadeSegment({}, {}, 44100, true).empty());
    EXPECT_TRUE(mix("eq", {}, {}, 4).empty());
    // Ungleich lange Eingaben: die kuerzere bestimmt die Laenge (n = min(len(a), len(b)))
    const std::vector<float> a(2 * 100, 1.0f), b(2 * 60, 0.5f);
    EXPECT_EQ(mix("crossfade", a, b, 4).size(), 2u * 60);
    EXPECT_EQ(mix("schnitt", a, b, 4).size(), 2u * 60);
    // Echo: bei Stille bleibt es still; ein Impuls auf dem ersten Sample liefert 0,7^k im Abstand k * beatN.
    std::vector<float> impulse(2 * 40, 0.0f);
    impulse[0] = 1.0f;
    impulse[1] = 1.0f;
    const auto tail = echo(impulse, 10);   // beatN = 10: der Impuls liegt in der ersten Huelle (1,0), Echos bei 10, 20, 30
    ASSERT_EQ(tail.size(), impulse.size());
    EXPECT_FLOAT_EQ(tail[0], 1.0f);
    EXPECT_FLOAT_EQ(tail[2 * 10], 0.7f);
    EXPECT_FLOAT_EQ(tail[2 * 20], 0.49f);
    EXPECT_FLOAT_EQ(tail[2 * 30 + 1], 0.343f);
    EXPECT_EQ(tail[2 * 5], 0.0f);
}

// ============================== T5.4 Huellkurven ================================================

namespace {

using klangbild::dsp::Envelopes;
using klangbild::dsp::Settings;

Settings settingsFromJson(const Json& e) {
    Settings s;
    s.volume = e.at("lautstaerke").as_string();
    s.eq = e.at("eq").as_string();
    s.filter = e.at("filter").as_string();
    s.effect = e.at("effekt").as_string();
    s.effectIn = e.at("effekt_ein").as_string();
    s.loop = e.at("loop").as_string();
    s.trick = e.at("trick").as_string();
    s.bassBar = static_cast<int>(e.at("bass_takt").as_double());
    s.vocalBar = static_cast<int>(e.at("gesang_takt").as_double());
    s.loopStart = static_cast<int>(e.at("loop_start").as_double());
    s.loopIn = static_cast<int>(e.at("loop_ein").as_double());
    s.loopInTimes = static_cast<int>(e.at("loop_ein_mal").as_double());
    return s;
}

/// Die Kurven eines Ergebnisses unter ihren Python-Schluesseln (nullptr = inaktiv).
std::vector<std::pair<const char*, const std::vector<float>*>> curveList(const Envelopes& h) {
    const auto p = [](const std::optional<std::vector<float>>& o) { return o ? &*o : nullptr; };
    return {{"a_vol", &h.aVol},          {"b_vol", &h.bVol},         {"a_tief", p(h.aLow)},       {"b_tief", p(h.bLow)},
            {"a_mitte", p(h.aMid)},      {"b_mitte", p(h.bMid)},     {"a_hoch", p(h.aHigh)},      {"b_hoch", p(h.bHigh)},
            {"a_tp", p(h.aLowpass)},     {"a_hp", p(h.aHighpass)},   {"b_tp", p(h.bLowpass)},     {"b_hp", p(h.bHighpass)},
            {"a_send", p(h.aSend)},      {"b_send", p(h.bSend)},     {"nass_ab", p(h.wetOff)}};
}

}  // namespace

TEST(DspEnvelopes, MatchesAllGoldenCases) {
    REQUIRE_BINARIES();
    Golden& g = golden();
    int checked = 0;
    const std::vector<std::pair<std::string, std::vector<const char*>>> groups = {
        {"lautstaerke", {"nahtlos", "linear", "ueberlappung", "hart_ein", "hart_aus", "hart_beide", "mitte", "mitte_weich", "frueh",
                         "spaet", "letzter_takt", "drop", "doppel"}},
        {"eq", {"keiner", "profi", "bass_mitte", "bass_anfang", "bass_ende", "drei_band", "bass_schnell", "bass_lang", "bass_takt"}},
        {"filter", {"keiner", "tp_aus", "tp_ein", "tp_beide", "hp_aus", "hp_ein", "hp_beide", "tp_ein_hp_aus", "hp_ein_tp_aus",
                    "hp_aus_reso", "tp_aus_reso"}},
        {"loop", {"keiner", "auto", "1", "2", "4", "8", "16", "32", "rolle"}},
        {"trick", {"keiner", "bremse", "spinback", "flanger", "phaser", "gate", "crush", "riser", "wechsel", "teaser"}},
        {"effekt_ein", {"keiner", "hall", "rueckhall"}},
    };
    std::vector<std::string> names;
    for (const auto& [group, values] : groups)
        for (const char* v : values) names.push_back("huellen_" + (group == "effekt_ein" ? std::string("effekt_ein") : group) + "_" + v);
    for (const char* effect : {"keiner", "hall", "echo50", "echo75", "echo100", "delay50", "delay75", "delay100", "pingpong50", "pingpong75"})
        for (const char* mode : {"mitte_aus", "ende_aus", "ende_ab"}) {
            if (std::string(effect) == "keiner") continue;
            names.push_back(std::string("huellen_effekt_") + effect + "_" + mode);
        }
    names.push_back("huellen_effekt_keiner");
    for (const std::string& name : names) {
        SCOPED_TRACE(name);
        GoldenCase c;
        try {
            c = g.case_of(name);
        } catch (const GoldenError&) {
            continue;   // Fallnamen, die es nicht gibt (z. B. effekt_ein_keiner heisst anders): nicht erfinden
        }
        const Settings s = settingsFromJson(c.inputs.at("e"));
        const int takte = static_cast<int>(c.inputs.at("takte").as_double());
        const int n = static_cast<int>(c.inputs.at("n").as_double());
        const Envelopes h = klangbild::dsp::envelopes(s, takte, n, c.inputs.at("kante").as_double());
        ASSERT_EQ(c.tolerance, "values");
        for (const auto& [key, curve] : curveList(h)) {
            const Json& want = c.expected.at(key);
            if (want.is_null()) {
                EXPECT_EQ(curve, nullptr) << key << ": im Golden inaktiv, hier gesetzt";
            } else {
                ASSERT_NE(curve, nullptr) << key << ": im Golden gesetzt, hier inaktiv";
                g.expect_values(name + "/" + key, want, std::vector<double>(curve->begin(), curve->end()));
            }
        }
        const Json& reverse = c.expected.at("b_rueck");
        if (reverse.is_null()) {
            EXPECT_FALSE(h.bReverse.has_value());
        } else {
            ASSERT_TRUE(h.bReverse.has_value());
            EXPECT_NEAR(*h.bReverse, reverse.as_double(), 1e-9);
        }
        ++checked;
    }
    EXPECT_EQ(checked, 83);   // alle huellen-Faelle des Golden-Satzes wurden verglichen
}

TEST(DspEnvelopes, UnknownVolumeAndFilterThrow) {
    Settings s;
    s.volume = "gibt_es_nicht";
    EXPECT_THROW(klangbild::dsp::envelopes(s, 8, 100, 0.01), std::invalid_argument);
    Settings f;
    f.filter = "gibt_es_nicht";
    EXPECT_THROW(klangbild::dsp::envelopes(f, 8, 100, 0.01), std::invalid_argument);
}

// Zweige, die der Golden-Satz nicht erreicht (er nutzt nur takte = 16, gesang_takt = -1, bass_takt = -1):
// Fingerabdruecke (Summe, drei Stichproben) aus uebergang._huellen des Prototyps, numpy 2.4.4.
TEST(DspEnvelopes, BranchesWithoutGoldenMatchPrototype) {
    struct Print { const char* key; double sum; float at[3]; };   // at: Index 7 % n, 311 % n, n - 1; b_rueck: nur sum
    struct Known { const char* name; Settings settings; int bars; int n; double edge; std::vector<Print> prints; };
    const std::vector<Known> known = {
        {"wechsel_g3_t16", {.trick = "wechsel", .vocalBar = 3}, 16, 1000, 0.001, {
            {"a_tief", 502.6338607111062, {1.0f, 1.0f, -4.371138828673793e-08f}},
            {"a_vol", 568.0500334501266, {1.0f, 1.0f, 0.0f}},
            {"b_tief", 501.63388238847256, {0.0f, 0.0f, 1.0f}},
            {"b_vol", 431.9499665975509, {0.0f, 0.0f, 1.0f}},
        }},
        {"wechsel_g5_t8", {.trick = "wechsel", .vocalBar = 5}, 8, 512, 0.01, {
            {"a_tief", 258.6777226479566, {1.0f, -4.371138828673793e-08f, -4.371138828673793e-08f}},
            {"a_vol", 390.15644186735153, {1.0f, 1.0f, 0.0f}},
            {"b_tief", 257.6777339428663, {0.0f, 1.0f, 1.0f}},
            {"b_vol", 121.84355814854166, {0.0f, 0.0f, 1.0f}},
        }},
        {"profi_bass10_t16", {.eq = "profi", .bassBar = 10}, 16, 1000, 0.001, {
            {"a_hoch", 127.63384566044007, {1.0f, -4.371138828673793e-08f, -4.371138828673793e-08f}},
            {"a_mitte", 377.63385542599656, {1.0f, 1.0f, -4.371138828673793e-08f}},
            {"a_tief", 627.6338656981925, {1.0f, 1.0f, -4.371138828673793e-08f}},
            {"a_vol", 977.7866402994841, {1.0f, 1.0f, 0.025129729881882668f}},
            {"b_hoch", 888.3101962432265, {0.03551403433084488f, 1.0f, 1.0f}},
            {"b_mitte", 626.6338829249144, {0.0f, 0.0f, 1.0f}},
            {"b_tief", 376.633882150054, {0.0f, 0.0f, 1.0f}},
            {"b_vol", 976.7866424601525, {0.17502307891845703f, 1.0f, 1.0f}},
        }},
        {"profi_t8", {.eq = "profi"}, 8, 512, 0.01, {
            {"a_hoch", 130.6777170528989, {1.0f, -4.371138828673793e-08f, -4.371138828673793e-08f}},
            {"a_mitte", 258.6777226479566, {1.0f, -4.371138828673793e-08f, -4.371138828673793e-08f}},
            {"a_tief", 386.6777282430143, {1.0f, 1.0f, -4.371138828673793e-08f}},
            {"a_vol", 489.24161895364523, {1.0f, 1.0f, 0.024541135877370834f}},
            {"b_hoch", 397.6402034498751, {0.035417571663856506f, 1.0f, 1.0f}},
            {"b_mitte", 257.6777339428663, {0.0f, 1.0f, 1.0f}},
            {"b_tief", 129.67773394286633, {0.0f, 0.0f, 1.0f}},
            {"b_vol", 488.2416209131479, {0.1709619015455246f, 1.0f, 1.0f}},
        }},
        {"profi_t1", {.eq = "profi"}, 1, 300, 0.01, {
            {"a_hoch", 296.40707409381866, {1.0f, 1.0f, 0.7217602133750916f}},
            {"a_mitte", 296.40707409381866, {1.0f, 1.0f, 0.7217602133750916f}},
            {"a_tief", 296.40707409381866, {1.0f, 1.0f, 0.7217602133750916f}},
            {"a_vol", 191.48548977868631, {0.9993283748626709f, 0.9983417987823486f, 0.005235962104052305f}},
            {"b_hoch", 38.09970026090741, {0.03318944573402405f, 0.03411928936839104f, 0.6921432018280029f}},
            {"b_mitte", 13.63317490927875, {0.0f, 0.0f, 0.6921432018280029f}},
            {"b_tief", 13.63317490927875, {0.0f, 0.0f, 0.6921432018280029f}},
            {"b_vol", 190.48549884278327, {0.03664370998740196f, 0.05756402388215065f, 0.9999862909317017f}},
        }},
        {"teaser_t4", {.trick = "teaser"}, 4, 400, 0.01, {
            {"a_tief", 203.9181081086421, {1.0f, -4.371138828673793e-08f, -4.371138828673793e-08f}},
            {"a_vol", 208.68356175534427, {0.9996222257614136f, 0.34243011474609375f, 0.003926938399672508f}},
            {"b_tief", 202.91811179369688, {0.0f, 1.0f, 1.0f}},
            {"b_vol", 276.35741935065016, {0.027485473081469536f, 0.9395433068275452f, 0.999992311000824f}},
        }},
        {"teaser_t6", {.trick = "teaser"}, 6, 600, 0.01, {
            {"a_tief", 303.9180971660912, {1.0f, 0.09410854429006577f, -4.371138828673793e-08f}},
            {"a_vol", 350.5890162747819, {0.9998320937156677f, 0.6864531636238098f, 0.0026179084088653326f}},
            {"b_tief", 302.9181188121438, {0.0f, 0.995561957359314f, 1.0f}},
            {"b_vol", 389.8810722674243, {0.01832493208348751f, 0.7271740436553955f, 0.9999966025352478f}},
        }},
        {"basstakt5_t16", {.eq = "bass_takt", .bassBar = 5}, 16, 1000, 0.001, {
            {"a_tief", 315.1371439614404, {1.0f, 0.80530846118927f, -4.371138828673793e-08f}},
            {"a_vol", 637.1196234467207, {0.9999395608901978f, 0.8830295205116272f, 0.0015707764541730285f}},
            {"b_tief", 689.1371744386852, {0.0f, 0.5928559899330139f, 1.0f}},
            {"b_vol", 636.1196536332136, {0.010995353572070599f, 0.4693174362182617f, 0.9999987483024597f}},
        }},
        {"bassanfang_t1", {.eq = "bass_anfang"}, 1, 200, 0.01, {
            {"a_tief", 57.328364075307526, {1.0f, -4.371138828673793e-08f, -4.371138828673793e-08f}},
            {"a_vol", 127.8232964836061, {0.9984890818595886f, 0.6434558033943176f, 0.007853860035538673f}},
            {"b_tief", 156.32837127894163, {0.0f, 1.0f, 1.0f}},
            {"b_vol", 126.82330223545432, {0.054950181394815445f, 0.7654832601547241f, 0.9999691843986511f}},
        }},
        {"bassende_t1", {.eq = "bass_ende"}, 1, 200, 0.01, {
            {"a_tief", 157.3283685805568, {1.0f, 1.0f, -4.371138828673793e-08f}},
            {"a_vol", 127.8232964836061, {0.9984890818595886f, 0.6434558033943176f, 0.007853860035538673f}},
            {"b_tief", 56.328370809555054, {0.0f, 0.0f, 1.0f}},
            {"b_vol", 126.82330223545432, {0.054950181394815445f, 0.7654832601547241f, 0.9999691843986511f}},
        }},
        {"filter_effekt", {.volume = "letzter_takt", .filter = "tp_aus", .effect = "echo75_ende_ab"}, 4, 400, 0.01, {
            {"a_send", 181.32837030291557, {0.0f, 1.0f, 1.0f}},
            {"a_tief", 203.9181081086421, {1.0f, -4.371138828673793e-08f, -4.371138828673793e-08f}},
            {"a_tp", 167.70000368263572, {0.017500000074505806f, 0.6000000238418579f, 0.6000000238418579f}},
            {"a_vol", 364.16066617146134, {1.0f, 0.9851093292236328f, 0.01570728048682213f}},
            {"b_tief", 202.91811179369688, {0.0f, 1.0f, 1.0f}},
            {"b_vol", 254.14758605649695, {0.027485473081469536f, 0.9395433068275452f, 0.999992311000824f}},
            {"nass_ab", 399.01367142796516, {1.0f, 1.0f, 0.3826844394207001f}},
        }},
        {"rueckhall_t4", {.volume = "ueberlappung", .effectIn = "rueckhall"}, 4, 400, 0.01, {
            {"a_tief", 203.9181081086421, {1.0f, -4.371138828673793e-08f, -4.371138828673793e-08f}},
            {"a_vol", 327.82329576835036, {1.0f, 0.6434559226036072f, 0.007853860035538673f}},
            {"b_rueck", 0.1675, {}},
            {"b_tief", 202.91811179369688, {0.0f, 1.0f, 1.0f}},
            {"b_vol", 326.8233022354543, {0.054950181394815445f, 1.0f, 1.0f}},
        }},
        {"hall_ein_t4", {.effectIn = "hall"}, 4, 400, 0.01, {
            {"a_tief", 203.9181081086421, {1.0f, -4.371138828673793e-08f, -4.371138828673793e-08f}},
            {"a_vol", 255.14757535792887, {0.9996222257614136f, 0.34243011474609375f, 0.003926938399672508f}},
            {"b_send", 164.1606575036895, {1.0f, -4.371138828673793e-08f, -4.371138828673793e-08f}},
            {"b_tief", 202.91811179369688, {0.0f, 1.0f, 1.0f}},
            {"b_vol", 254.14758605649695, {0.027485473081469536f, 0.9395433068275452f, 0.999992311000824f}},
        }},
    };
    for (const Known& k : known) {
        SCOPED_TRACE(k.name);
        const Envelopes h = klangbild::dsp::envelopes(k.settings, k.bars, k.n, k.edge);
        const auto curves = curveList(h);
        std::size_t active = h.bReverse ? 1u : 0u;
        for (const auto& c : curves) active += c.second != nullptr ? 1u : 0u;
        EXPECT_EQ(active, k.prints.size()) << "Zahl der aktiven Kurven";
        for (const Print& want : k.prints) {
            if (std::string(want.key) == "b_rueck") {
                ASSERT_TRUE(h.bReverse.has_value());
                EXPECT_NEAR(*h.bReverse, want.sum, 1e-9);
                continue;
            }
            const std::vector<float>* got = nullptr;
            for (const auto& c : curves)
                if (std::string(c.first) == want.key) got = c.second;
            ASSERT_NE(got, nullptr) << want.key;
            ASSERT_EQ(static_cast<int>(got->size()), k.n);
            double sum = 0.0;
            for (float f : *got) sum += static_cast<double>(f);
            EXPECT_NEAR(sum, want.sum, 2e-4) << want.key;
            const int idx[3] = {7 % k.n, 311 % k.n, k.n - 1};
            for (int j = 0; j < 3; ++j) EXPECT_NEAR((*got)[static_cast<std::size_t>(idx[j])], want.at[j], 2e-6) << want.key << " @" << idx[j];
        }
    }
}

// ============================== T5.5 Sweep ======================================================

namespace {

/// Zwei Toene (rund 350 Hz und 6 kHz) mit Phasenversatz je Kanal: der Filter hat etwas zu tun.
std::vector<float> sweepSignal(int frames) {
    std::vector<float> x(static_cast<std::size_t>(frames) * 2);
    for (int i = 0; i < frames; ++i)
        for (int c = 0; c < 2; ++c)
            x[static_cast<std::size_t>(i * 2 + c)] = static_cast<float>(0.3 * std::sin(0.05 * i + 0.5 * c) + 0.2 * std::sin(0.9 * i + c));
    return x;
}

}  // namespace

TEST(DspSweep, MatchesGolden) {
    REQUIRE_BINARIES();
    Golden& g = golden();
    for (const char* name : {"sweep_tp_0", "sweep_tp_1", "sweep_hp_0", "sweep_hp_1"}) {
        SCOPED_TRACE(name);
        const GoldenCase c = g.case_of(name);
        const std::vector<float> x = floatsOf(g, c.inputs.at("x"));
        const std::vector<float> amount = floatsOf(g, c.inputs.at("menge"));
        const auto kind = c.inputs.at("art").as_string() == "tp" ? klangbild::dsp::SweepKind::Lowpass : klangbild::dsp::SweepKind::Highpass;
        const std::vector<float> y = klangbild::dsp::sweep(x, amount, kind, c.inputs.at("reso").as_bool());
        ASSERT_EQ(c.tolerance, "dsp");
        g.expect_dsp(name, c.expected, std::vector<double>(y.begin(), y.end()));
    }
}

// Zweige, die die Golden-Kurve (menge 0 -> 1) nicht erreicht: Rand am Ende offen, beide Raender offen,
// konstante Menge, Menge 0 (Fruehausstieg). Fingerabdruecke (Summe, 5 Frames) aus uebergang._sweep.
TEST(DspSweep, BranchesWithoutGoldenMatchPrototype) {
    using klangbild::dsp::SweepKind;
    constexpr int n = 5000;
    struct Known { const char* name; SweepKind kind; bool reso; double sum; float at[5][2]; };
    const Known known[] = {
        {"tp_fallend", SweepKind::Lowpass, false, 21.014003429922298, {{1.8480925518815638e-06f, 0.3121219277381897f}, {-0.04620583355426788f, 0.03851282224059105f}, {-0.2648535668849945f, -0.1671144813299179f}, {0.09876973181962967f, 0.1438128501176834f}, {-0.2278386503458023f, -0.036060504615306854f}}},
        {"hp_buckel_reso", SweepKind::Highpass, true, -94.6462245730927, {{0.13022790849208832f, 0.07348844408988953f}, {-0.009647448547184467f, -0.17381273210048676f}, {0.1940479278564453f, 0.16088193655014038f}, {0.2060304582118988f, 0.21119119226932526f}, {-0.2278386503458023f, -0.036060504615306854f}}},
        {"tp_halb", SweepKind::Lowpass, false, 14.455316205904637, {{0.0017933930503204465f, 0.31214600801467896f}, {0.11793545633554459f, -0.029914088547229767f}, {-0.2686472535133362f, -0.17354899644851685f}, {0.28459683060646057f, 0.2966701090335846f}, {-0.28819769620895386f, -0.2903670072555542f}}},
        {"hp_steigend", SweepKind::Highpass, false, 26.722936185346043, {{0.13027016818523407f, 0.07347358018159866f}, {0.09657807648181915f, 0.035591915249824524f}, {0.3822247087955475f, 0.49584758281707764f}, {-0.03426017239689827f, 0.14777526259422302f}, {0.15333926677703857f, 0.1892092227935791f}}},
        {"tp_null", SweepKind::Lowpass, false, 6.376514907187811, {{0.1303074210882187f, 0.07558869570493698f}, {0.15675988793373108f, 0.01754099503159523f}, {-0.06866045296192169f, 0.1508685052394867f}, {0.16541145741939545f, 0.2968747019767761f}, {-0.2278386503458023f, -0.036060504615306854f}}},
    };
    const std::vector<float> x = sweepSignal(n);
    const auto ramp = [&](float from, float to) {
        std::vector<float> m(n);
        for (int i = 0; i < n; ++i) m[static_cast<std::size_t>(i)] = static_cast<float>(from + (static_cast<double>(to) - from) * i / (n - 1));
        m.back() = to;
        return m;
    };
    std::vector<float> buckel(n);
    for (int i = 0; i < n; ++i) buckel[static_cast<std::size_t>(i)] = static_cast<float>(std::sin(std::numbers::pi * i / (n - 1)));
    const std::vector<std::pair<std::string, std::vector<float>>> amounts = {
        {"tp_fallend", ramp(1.0f, 0.0f)}, {"hp_buckel_reso", buckel}, {"tp_halb", std::vector<float>(n, 0.5f)},
        {"hp_steigend", ramp(0.0f, 1.0f)}, {"tp_null", std::vector<float>(n, 0.0f)}};
    const int idx[5] = {3, 441, 2500, 4558, n - 1};
    for (std::size_t k = 0; k < std::size(known); ++k) {
        SCOPED_TRACE(known[k].name);
        ASSERT_EQ(amounts[k].first, known[k].name);
        const std::vector<float> y = klangbild::dsp::sweep(x, amounts[k].second, known[k].kind, known[k].reso);
        ASSERT_EQ(y.size(), x.size());
        double sum = 0.0;
        for (float f : y) sum += static_cast<double>(f);
        EXPECT_NEAR(sum, known[k].sum, 5e-4);
        for (int j = 0; j < 5; ++j)
            for (int c = 0; c < 2; ++c)
                EXPECT_NEAR(y[static_cast<std::size_t>(idx[j] * 2 + c)], known[k].at[j][c], 5e-6) << "Frame " << idx[j] << " Kanal " << c;
    }
    // Menge 0 (unter 1e-3): der Eingang kommt unveraendert zurueck
    EXPECT_EQ(klangbild::dsp::sweep(x, std::vector<float>(n, 0.0f), SweepKind::Lowpass), x);
    EXPECT_EQ(klangbild::dsp::sweep(x, {}, SweepKind::Lowpass), x);
}

TEST(DspSweep, BiquadCoefficientsKnownValues) {
    // Tiefpass bei 1000 Hz: Butterworth-Paar (Q = 0.5412 und 1.3066), RBJ-Cookbook
    const double fc[1] = {1000.0};
    const auto lp = klangbild::dsp::sweepBiquads(fc, klangbild::dsp::SweepKind::Lowpass, false);
    ASSERT_EQ(lp.size(), 1u);
    for (int s = 0; s < 2; ++s) {   // Tiefpass: b0 = b2 = b1 / 2, Verstaerkung 1 bei 0 Hz
        const auto& q = lp[0][static_cast<std::size_t>(s)];
        EXPECT_NEAR(q.b0, q.b2, 1e-15);
        EXPECT_NEAR(q.b1, 2 * q.b0, 1e-15);
        EXPECT_NEAR((q.b0 + q.b1 + q.b2) / (1 + q.a1 + q.a2), 1.0, 1e-12);
    }
    const auto hp = klangbild::dsp::sweepBiquads(fc, klangbild::dsp::SweepKind::Highpass, false);
    for (int s = 0; s < 2; ++s) {   // Hochpass: Verstaerkung 0 bei 0 Hz
        const auto& q = hp[0][static_cast<std::size_t>(s)];
        EXPECT_NEAR(q.b0 + q.b1 + q.b2, 0.0, 1e-15);
    }
    // Resonanz: nur die zweite Stufe aendert sich (Q = 4 statt 1.3066)
    const auto res = klangbild::dsp::sweepBiquads(fc, klangbild::dsp::SweepKind::Lowpass, true);
    EXPECT_EQ(res[0][0].a1, lp[0][0].a1);
    EXPECT_NE(res[0][1].a1, lp[0][1].a1);
    // fc wird auf 10 Hz .. 0.45 * Rate begrenzt
    const double extreme[2] = {1.0, 1e6};
    const auto clipped = klangbild::dsp::sweepBiquads(extreme, klangbild::dsp::SweepKind::Lowpass, false);
    const double ten[1] = {10.0}, top[1] = {0.45 * 44100};
    EXPECT_EQ(clipped[0][0].a1, klangbild::dsp::sweepBiquads(ten, klangbild::dsp::SweepKind::Lowpass, false)[0][0].a1);
    EXPECT_EQ(clipped[1][0].a1, klangbild::dsp::sweepBiquads(top, klangbild::dsp::SweepKind::Lowpass, false)[0][0].a1);
}

TEST(DspSweep, WeightBandsKnownValuesFromPrototype) {
    constexpr int n = 1200;
    const std::vector<float> x = sweepSignal(n);
    // alle Baender ohne Gewicht: x kommt unveraendert zurueck
    EXPECT_EQ(klangbild::dsp::weightBands(x, nullptr, nullptr, nullptr), x);
    std::vector<float> low(n), high(n, 0.5f);
    for (int i = 0; i < n; ++i) low[static_cast<std::size_t>(i)] = static_cast<float>(1.0 - static_cast<double>(i) / (n - 1));
    low.back() = 0.0f;
    const auto y = klangbild::dsp::weightBands(x, &low, nullptr, &high);
    const double sum = [&] { double s = 0; for (float f : y) s += f; return s; }();
    EXPECT_NEAR(sum, 23.567964026413392, 5e-4);
    const float want[3][2] = {{0.08736026287078857f, 0.1655636727809906f}, {-0.3294559717178345f, -0.1763421893119812f},
                              {-0.2638530135154724f, -0.3227608799934387f}};
    const int at[3] = {3, 600, 1199};
    for (int j = 0; j < 3; ++j)
        for (int c = 0; c < 2; ++c) EXPECT_NEAR(y[static_cast<std::size_t>(at[j] * 2 + c)], want[j][c], 5e-6) << at[j];
    // Tiefband stumm, Mitte und Hoehen voll: Bass fehlt, Rest bleibt
    const std::vector<float> zeros(n, 0.0f), ones(n, 1.0f);
    const auto noBass = klangbild::dsp::weightBands(x, &zeros, &ones, &ones);
    double sum2 = 0;
    for (float f : noBass) sum2 += f;
    EXPECT_NEAR(sum2, 18.06835986720398, 5e-4);
    EXPECT_NEAR(noBass[static_cast<std::size_t>(3 * 2)], 0.19920025765895844f, 5e-6);
}
