// Golden-Tests des DSP-Ports (BAUPLAN-ANDROID M5): jede portierte Funktion gegen die
// Python-Referenz aus android/testdata/golden. Toleranzen nach §12.3 (golden.h).
//
// Der volle Satz entsteht mit `python -m klangbild golden <ziel>`; die grossen Binaerdateien
// (.f32) liegen nicht im Repo. Fehlen sie, werden die betroffenen Tests uebersprungen (nicht
// still bestanden): GTEST_SKIP nennt den Grund.
#include <gtest/gtest.h>

#include <cmath>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

#include "dsp/curves.h"
#include "dsp/automation.h"
#include "dsp/backen.h"
#include "dsp/effects.h"
#include "dsp/fft.h"
#include "dsp/envelopes.h"
#include "dsp/filters.h"
#include "dsp/introloop.h"
#include "dsp/level.h"
#include "dsp/limiter.h"
#include "dsp/loop.h"
#include "dsp/loopchoice.h"
#include "dsp/mischen_eigen.h"
#include "dsp/mixing.h"
#include "dsp/raster.h"
#include "dsp/resample.h"
#include "dsp/sweep.h"
#include "dsp/warp.h"
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
    if (e.has("keylock")) s.keylock = e.at("keylock").as_bool();
    if (e.has("ausstieg")) s.ausstieg = e.at("ausstieg").as_string();
    if (e.has("vor_ende_takte")) s.vorEndeTakte = static_cast<int>(e.at("vor_ende_takte").as_double());
    if (e.has("einstieg")) s.einstieg = e.at("einstieg").as_string();
    if (e.has("weiter_ab")) s.weiterAb = e.at("weiter_ab").as_string();
    if (e.has("takte")) s.takte = static_cast<int>(e.at("takte").as_double());
    if (e.has("weiter_takte")) s.weiterTakte = static_cast<int>(e.at("weiter_takte").as_double());
    if (e.has("max_bpm")) s.maxBpm = e.at("max_bpm").as_double();
    if (e.has("tempo_modus")) s.tempoModus = e.at("tempo_modus").as_string();
    if (e.has("stems")) s.stems = e.at("stems").as_bool();
    if (e.has("art")) s.art = e.at("art").as_string();
    if (e.has("modus")) s.modus = e.at("modus").as_string();
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

// ============================== T5.6 Effekte (Echo, Delay, Ping-Pong, Hall) =====================

namespace {

std::vector<double> randomSignal(std::size_t n, unsigned seed) {
    std::vector<double> v(n);
    unsigned state = seed;
    for (double& x : v) {
        state = state * 1664525u + 1013904223u;   // lineare Kongruenz: fester Ablauf, kein <random>
        x = static_cast<double>(state >> 8) / static_cast<double>(1u << 24) - 0.5;
    }
    return v;
}

}  // namespace

TEST(DspFft, MatchesNaiveDftAndRoundTrips) {
    for (std::size_t n : {1u, 2u, 8u, 64u, 256u}) {
        const klangbild::dsp::Fft fft(n);
        std::vector<std::complex<double>> data(n), original;
        const auto re = randomSignal(n, 11), im = randomSignal(n, 12);
        for (std::size_t i = 0; i < n; ++i) data[i] = {re[i], im[i]};
        original = data;
        fft.forward(data.data());
        for (std::size_t k = 0; k < n; ++k) {   // naive DFT: X[k] = sum x[j] * exp(-2 pi i j k / n)
            std::complex<double> sum = 0.0;
            for (std::size_t j = 0; j < n; ++j) sum += original[j] * std::polar(1.0, -2.0 * 3.14159265358979323846 * static_cast<double>(j * k) / static_cast<double>(n));
            ASSERT_NEAR(std::abs(data[k] - sum), 0.0, 1e-11) << "n=" << n << " k=" << k;
        }
        fft.inverse(data.data());
        for (std::size_t i = 0; i < n; ++i) ASSERT_NEAR(std::abs(data[i] - original[i]), 0.0, 1e-13) << n;
    }
    EXPECT_THROW(klangbild::dsp::Fft(12), std::invalid_argument);
    EXPECT_EQ(klangbild::dsp::nextPowerOfTwo(1), 1u);
    EXPECT_EQ(klangbild::dsp::nextPowerOfTwo(129), 256u);
}

TEST(DspFft, ConvolveMatchesDirectSumIncludingOverlapAddBlocks) {
    const auto x = randomSignal(1000, 21);
    const auto h = randomSignal(37, 22);
    std::vector<double> direct(x.size() + h.size() - 1, 0.0);
    for (std::size_t i = 0; i < x.size(); ++i)
        for (std::size_t j = 0; j < h.size(); ++j) direct[i + j] += x[i] * h[j];
    for (std::size_t fftSize : {0u, 128u, 256u, 4096u}) {   // 128: viele Bloecke; 0: automatisch (ein Block)
        const auto got = klangbild::dsp::convolve(x, h, fftSize);
        ASSERT_EQ(got.size(), direct.size()) << fftSize;
        for (std::size_t i = 0; i < got.size(); ++i) ASSERT_NEAR(got[i], direct[i], 1e-12) << "fft " << fftSize << " i=" << i;
    }
    EXPECT_TRUE(klangbild::dsp::convolve({}, h).empty());
    EXPECT_TRUE(klangbild::dsp::convolve(x, {}).empty());
    const auto single = klangbild::dsp::convolve(x, {2.0});   // IR aus einem Wert: Skalierung
    ASSERT_EQ(single.size(), x.size());
    for (std::size_t i = 0; i < x.size(); ++i) ASSERT_NEAR(single[i], 2.0 * x[i], 1e-13);
    EXPECT_THROW(klangbild::dsp::convolve(x, h, 100), std::invalid_argument);   // keine Zweierpotenz
    EXPECT_THROW(klangbild::dsp::convolve(x, h, 64), std::invalid_argument);    // kleiner als 2 * |h|
}

TEST(DspEffects, WetSignalMatchesGolden) {
    REQUIRE_BINARIES();
    Golden& g = golden();
    // Die Hall-IR ist ein Asset und kommt hier aus dem Golden-Fall hall_ir (Stereo, interleaved).
    const GoldenCase irCase = g.case_of("hall_ir");
    const std::vector<float> ir = floatsOf(g, irCase.expected);
    ASSERT_EQ(ir.size(), 106722u * 2);
    for (const char* name : {"nass_echo50", "nass_echo75", "nass_echo100", "nass_delay50", "nass_delay75", "nass_delay100",
                             "nass_pingpong50", "nass_pingpong75", "nass_hall"}) {
        SCOPED_TRACE(name);
        const GoldenCase c = g.case_of(name);
        const std::vector<float> send = floatsOf(g, c.inputs.at("send"));
        const std::vector<float> wet = klangbild::dsp::wetSignal(c.inputs.at("typ").as_string(), send, c.inputs.at("schlag_n").as_double(), ir);
        const std::vector<double> got(wet.begin(), wet.end());
        if (c.tolerance == "reverb") {
            g.expect_reverb(name, c.expected, got);
        } else {
            ASSERT_EQ(c.tolerance, "dsp");
            g.expect_dsp(name, c.expected, got);
        }
    }
}

#ifdef KLINGBILD_HALL_IR_ASSET
TEST(DspEffects, HallIrAssetEqualsTheGoldenImpulseResponse) {
    REQUIRE_BINARIES();
    std::ifstream asset(KLINGBILD_HALL_IR_ASSET, std::ios::binary | std::ios::ate);
    ASSERT_TRUE(asset.good()) << "Asset fehlt: " << KLINGBILD_HALL_IR_ASSET;
    const std::streamsize bytes = asset.tellg();
    ASSERT_EQ(bytes, static_cast<std::streamsize>(106722) * 2 * 4);   // 2,42 s Stereo, float32 little endian, ohne Kopf
    std::vector<float> fromAsset(static_cast<std::size_t>(bytes) / 4);
    asset.seekg(0);
    asset.read(reinterpret_cast<char*>(fromAsset.data()), bytes);
    Golden& g = golden();
    const std::vector<float> golden = floatsOf(g, g.case_of("hall_ir").expected);
    ASSERT_EQ(golden.size(), fromAsset.size());
    double worst = 0.0;
    for (std::size_t i = 0; i < golden.size(); ++i) worst = std::max(worst, static_cast<double>(std::abs(golden[i] - fromAsset[i])));
    EXPECT_LE(worst, 1e-6) << "Das Asset passt nicht mehr zum Prototyp: Golden neu erzeugen und hall_ir.f32 ersetzen";
}
#endif

TEST(DspEffects, EdgeCasesRoundingAndPingPong) {
    using klangbild::dsp::wetSignal;
    std::vector<float> impulse(2 * 64, 0.0f);
    impulse[0] = 1.0f;
    impulse[1] = 0.5f;
    const std::vector<float> noIr;
    // Python round() rundet halbe Werte zur geraden Zahl: 1102.5 -> 1102, 1103.5 -> 1104 (BAUPLAN §13)
    const auto a = wetSignal("delay100", impulse, 1102.5, noIr);
    EXPECT_NE(a[2 * 1102], 0.0f);
    EXPECT_EQ(a[2 * 1103], 0.0f);
    const auto b = wetSignal("delay100", impulse, 1103.5, noIr);
    EXPECT_NE(b[2 * 1104], 0.0f);
    EXPECT_EQ(b[2 * 1103], 0.0f);
    // Delay: Wiederholung k im Abstand k * Verzoegerung, Pegel 0,35^k * 1,1; beide Kanaele
    const auto d = wetSignal("delay100", impulse, 10.0, noIr);
    EXPECT_NEAR(d[2 * 10], 1.1f * 0.35f, 1e-6);
    EXPECT_NEAR(d[2 * 10 + 1], 1.1f * 0.35f * 0.5f, 1e-6);
    EXPECT_NEAR(d[2 * 20], 1.1f * 0.35f * 0.35f, 1e-6);
    // Ping-Pong: abwechselnd links/rechts, Mono-Summe: k = 1 rechts, k = 2 links
    const auto pp = wetSignal("pingpong100", impulse, 10.0, noIr);
    const float mono = (1.0f + 0.5f) / 2.0f;
    EXPECT_EQ(pp[2 * 10], 0.0f);                                   // k = 1: nur rechts
    EXPECT_NEAR(pp[2 * 10 + 1], 1.4f * mono * 0.55f, 1e-6);
    EXPECT_NEAR(pp[2 * 20], 1.4f * mono * 0.55f * 0.55f, 1e-6);    // k = 2: nur links
    EXPECT_EQ(pp[2 * 20 + 1], 0.0f);
    // Laenge: send + Wiederholungen * Verzoegerung (Echo 0,7: 13, Delay 0,35: 5, Ping-Pong 0,55: 8)
    EXPECT_EQ(wetSignal("echo100", impulse, 10.0, noIr).size(), 2u * (64 + 13 * 10));
    EXPECT_EQ(wetSignal("delay50", impulse, 10.0, noIr).size(), 2u * (64 + 5 * 5));
    EXPECT_EQ(wetSignal("pingpong75", impulse, 10.0, noIr).size(), 2u * (64 + 8 * 8));   // verz = round(7.5) = 8
    // Fehler und leere Eingaben
    EXPECT_THROW(wetSignal("reverse100", impulse, 10.0, noIr), std::invalid_argument);
    EXPECT_THROW(wetSignal("echo", impulse, 10.0, noIr), std::invalid_argument);   // Prozent fehlt (int("") im Prototyp)
    EXPECT_TRUE(wetSignal("hall", {}, 10.0, noIr).empty());
    // Leere Quelle: nur Stille der Laenge Wiederholungen * Verzoegerung (Prototyp: zeros((0 + 13 * 5, 2)))
    const auto silent = wetSignal("echo50", {}, 10.0, noIr);
    EXPECT_EQ(silent.size(), 2u * 13 * 5);
    for (float v : silent) ASSERT_EQ(v, 0.0f);
}

// ============================== T5.7 Pegel und Deckelung ========================================

namespace {

std::vector<int> intsOf(const Json& ref) {
    std::vector<int> v;
    for (double d : ref.numbers()) v.push_back(static_cast<int>(d));
    return v;
}

std::vector<float> levelSignal(int frames, int channels, double amp = 0.3, double a = 0.05,
                               double b = 0.5, double phase = 0.0) {
    std::vector<float> x(static_cast<std::size_t>(frames) * static_cast<std::size_t>(channels));
    for (int i = 0; i < frames; ++i)
        for (int c = 0; c < channels; ++c)
            x[static_cast<std::size_t>(i * channels + c)] =
                static_cast<float>(amp * std::sin(a * i + b * c + phase));
    return x;
}

}  // namespace

TEST(DspLevel, DeckelnMatchesGolden) {
    REQUIRE_BINARIES();
    Golden& g = golden();
    for (int gain : {1, 2, 4}) {
        const std::string name = "deckeln_" + std::to_string(gain);
        SCOPED_TRACE(name);
        const GoldenCase c = g.case_of(name);
        const auto y = floatsOf(g, c.inputs.at("y"));
        const auto ra = floatsOf(g, c.inputs.at("ra"));
        const auto rb = floatsOf(g, c.inputs.at("rb"));
        const auto taktN = intsOf(c.inputs.at("takt_n"));
        const auto out = klangbild::dsp::deckeln(y, ra, rb, taktN);
        ASSERT_EQ(c.tolerance, "dsp");
        g.expect_dsp(name, c.expected, std::vector<double>(out.begin(), out.end()));
    }
}

TEST(DspLevel, DeckelnLaesstLeisesSignalInRuhe) {
    const auto laut = levelSignal(512, 2);
    std::vector<float> leise(laut.size());
    for (std::size_t i = 0; i < laut.size(); ++i) leise[i] = laut[i] * 0.01f;
    const std::vector<int> taktN = {0, 256, 512};
    EXPECT_EQ(klangbild::dsp::deckeln(leise, laut, laut, taktN), leise);
    EXPECT_EQ(klangbild::dsp::deckeln(leise, laut, laut, {}), leise);   // weniger als zwei Grenzen
}

// Referenz: uebergang._takt_db des Prototyps (numpy 2.5.3) fuer 2048 Frames 0.3*sin(0.05*i + 0.5*c).
TEST(DspLevel, TaktDbKnownValuesFromPrototype) {
    const auto x = levelSignal(2048, 2);
    const std::vector<int> taktN = {0, 500, 1000, 1500, 2048};
    const auto db = klangbild::dsp::taktDb(x, taktN);
    ASSERT_EQ(db.size(), 4u);
    EXPECT_NEAR(db[0], -13.448738804571992, 1e-9);
    EXPECT_NEAR(db[1], -13.447762903425534, 1e-9);
    EXPECT_NEAR(db[2], -13.448193059535026, 1e-9);
    EXPECT_NEAR(db[3], -13.43142276747756, 1e-9);
    EXPECT_TRUE(klangbild::dsp::taktDb(x, std::vector<int>{5}).empty());
}

TEST(DspLevel, TrockenKnownValuesFromPrototype) {
    // uebergang._trocken mit Einstellungen(eq="drei_band", lautstaerke="nahtlos"), 4 Takte, 2048 Frames.
    using klangbild::dsp::Settings;
    const auto a = levelSignal(2048, 2);
    const auto b = levelSignal(2048, 2, 0.2, 0.03, 0.7, 1.1);
    const std::vector<int> taktN = {0, 500, 1000, 1500, 2048};
    Settings drei_band;
    drei_band.eq = "drei_band";
    const auto h = klangbild::dsp::envelopes(drei_band, 4, 2048, 0.001);
    const auto out = klangbild::dsp::trocken(a, b, h, taktN);
    ASSERT_EQ(out.size(), a.size());
    EXPECT_NEAR(out[0], 0.0, 1e-6);
    EXPECT_NEAR(out[1], 0.14382766, 1e-6);
    EXPECT_NEAR(out[1000], -0.03682142, 1e-6);
    EXPECT_NEAR(out[1001], 0.099893175, 1e-6);
    EXPECT_NEAR(out[4000], -0.1972779, 1e-6);
    EXPECT_NEAR(out[4095], 0.07383977, 1e-6);
    EXPECT_NEAR(sum(out), -0.27096458548840019, 5e-5);

    // Ohne EQ-Kurven (eq="keiner"): nur Fader, dann deckeln.
    Settings ohne_eq;
    ohne_eq.eq = "keiner";
    const auto h2 = klangbild::dsp::envelopes(ohne_eq, 4, 2048, 0.001);
    EXPECT_NEAR(sum(klangbild::dsp::trocken(a, b, h2, taktN)), -1.6546463336562738, 5e-5);
}

// ============================== T5.12 Automationskurven =========================================

namespace {

void expectSide(Golden& g, const std::string& name, const Json& erwartet,
                const std::map<std::string, klangbild::dsp::Curve>& ist) {
    ASSERT_EQ(erwartet.members.size(), ist.size()) << name;
    for (const auto& [key, curve] : ist) {
        ASSERT_TRUE(erwartet.has(key)) << name << " / " << key;
        g.expect_values(name + "/" + key, erwartet.at(key), std::vector<double>(curve.begin(), curve.end()));
    }
}

/// Die Rezepte aus golden.py (`_dsp`, `recipes`): 5 benannte Blenden und 9 Tricks.
struct Recipe {
    const char* name;
    const char* volume;
    const char* eq;
    const char* filter;
    const char* effect;
    const char* loop;
    const char* trick;
};

constexpr Recipe kRecipes[] = {
    {"profi_eq", nullptr, "profi", nullptr, nullptr, nullptr, nullptr},
    {"outro_loop", nullptr, "profi", nullptr, nullptr, "8", nullptr},
    {"echo_out", "letzter_takt", nullptr, nullptr, "echo75_ende_aus", nullptr, nullptr},
    {"hall", nullptr, nullptr, "tp_aus", "hall_ende_aus", nullptr, nullptr},
    {"rolle", "hart_aus", nullptr, nullptr, nullptr, "rolle", nullptr},
    {"trick_bremse", "drop", nullptr, nullptr, nullptr, nullptr, "bremse"},
    {"trick_spinback", "drop", nullptr, nullptr, nullptr, nullptr, "spinback"},
    {"trick_riser", "drop", nullptr, nullptr, nullptr, nullptr, "riser"},
    {"trick_flanger", "drop", nullptr, nullptr, nullptr, nullptr, "flanger"},
    {"trick_teaser", "drop", nullptr, nullptr, nullptr, nullptr, "teaser"},
    {"trick_phaser", "drop", nullptr, nullptr, nullptr, nullptr, "phaser"},
    {"trick_gate", "drop", nullptr, nullptr, nullptr, nullptr, "gate"},
    {"trick_crush", "drop", nullptr, nullptr, nullptr, nullptr, "crush"},
    {"trick_wechsel", "drop", nullptr, nullptr, nullptr, nullptr, "wechsel"},
};

klangbild::dsp::Settings settingsOf(const Recipe& r) {
    klangbild::dsp::Settings s;
    if (r.volume) s.volume = r.volume;
    if (r.eq) s.eq = r.eq;
    if (r.filter) s.filter = r.filter;
    if (r.effect) s.effect = r.effect;
    if (r.loop) s.loop = r.loop;
    if (r.trick) s.trick = r.trick;
    return s;
}

}  // namespace

TEST(DspAutomation, KurvenMatchesGolden) {
    Golden& g = golden();
    for (const char* art : {"eq", "filter", "echo", "schnitt", "crossfade"}) {
        const std::string name = std::string("kurven_") + art;
        SCOPED_TRACE(name);
        const GoldenCase c = g.case_of(name);
        ASSERT_EQ(static_cast<int>(c.inputs.at("takte").as_double()), 16);
        const auto k = klangbild::dsp::automation(art, 16, klangbild::dsp::Settings{});
        expectSide(g, name + "/a", c.expected.at("a"), k.a);
        expectSide(g, name + "/b", c.expected.at("b"), k.b);
    }
}

TEST(DspAutomation, KurvenEigenMatchesGolden) {
    Golden& g = golden();
    int geprueft = 0;
    for (const Recipe& r : kRecipes) {
        const std::string name = std::string("kurven_eigen_") + r.name;
        SCOPED_TRACE(name);
        const GoldenCase c = g.case_of(name);
        const auto k = klangbild::dsp::automation("eigen", 4, settingsOf(r));
        expectSide(g, name + "/a", c.expected.at("a"), k.a);
        expectSide(g, name + "/b", c.expected.at("b"), k.b);
        ++geprueft;
    }
    EXPECT_EQ(geprueft, 14);
}

// Referenz: uebergang._loop_plan des Prototyps fuer 4 Takte.
TEST(DspAutomation, LoopPlanKnownValuesFromPrototype) {
    using klangbild::dsp::loopPlan;
    using klangbild::dsp::Settings;
    Settings s;
    s.loop = "4";
    auto plan = loopPlan(s, 4);
    ASSERT_EQ(plan.size(), 1u);
    EXPECT_EQ(plan[0].from, 0);
    EXPECT_EQ(plan[0].to, 32);
    EXPECT_EQ(plan[0].size, 8);
    s.loop = "32";
    EXPECT_EQ(loopPlan(s, 4)[0].size, 64);
    s.loop = "1";
    plan = loopPlan(s, 4);
    EXPECT_EQ(plan[0].from, 8);
    EXPECT_EQ(plan[0].to, 32);
    EXPECT_EQ(plan[0].size, 2);
    s.loop = "rolle";
    plan = loopPlan(s, 4);
    const int want[5][3] = {{0, 6, 8}, {6, 12, 4}, {12, 18, 2}, {18, 24, 1}, {24, 32, 1}};
    ASSERT_EQ(plan.size(), 5u);
    for (int i = 0; i < 5; ++i) {
        EXPECT_EQ(plan[static_cast<std::size_t>(i)].from, want[i][0]) << i;
        EXPECT_EQ(plan[static_cast<std::size_t>(i)].to, want[i][1]) << i;
        EXPECT_EQ(plan[static_cast<std::size_t>(i)].size, want[i][2]) << i;
    }
    s.loop = "auto";   // int("auto") im Prototyp
    EXPECT_THROW(loopPlan(s, 4), std::invalid_argument);
}

TEST(DspAutomation, StemArtenWerfen) {
    EXPECT_THROW(klangbild::dsp::automation("drums_zuerst", 16, klangbild::dsp::Settings{}), std::invalid_argument);
    EXPECT_THROW(klangbild::dsp::automation("unbekannt", 16, klangbild::dsp::Settings{}), std::invalid_argument);
}

// ============================== T6.2 Warp ohne Keylock ==========================================

namespace {

/// Toleranz "warp" aus manifest.json: Laenge exakt, RMS je Abschnitt <= 0,2 dB, Korrelation >= 0,99.
void expectWarp(Golden& g, const std::string& name, const Json& erwartet, const std::vector<double>& ist) {
    const std::vector<double> ref = g.values(erwartet);
    ASSERT_EQ(ist.size(), ref.size()) << name;
    double kreuz = 0.0, aa = 0.0, bb = 0.0;
    for (std::size_t i = 0; i < ist.size(); ++i) {
        kreuz += ist[i] * ref[i];
        aa += ist[i] * ist[i];
        bb += ref[i] * ref[i];
    }
    EXPECT_GE(kreuz / std::sqrt(std::max(aa * bb, 1e-30)), 0.99) << name;
    constexpr std::size_t abschnitt = 4096;
    for (std::size_t von = 0; von < ist.size(); von += abschnitt) {
        const std::size_t bis = std::min(ist.size(), von + abschnitt);
        double qa = 0.0, qb = 0.0;
        for (std::size_t i = von; i < bis; ++i) {
            qa += ist[i] * ist[i];
            qb += ref[i] * ref[i];
        }
        const double db = 20.0 * std::log10(std::sqrt(std::max(qa, 1e-30)) / std::sqrt(std::max(qb, 1e-30)));
        EXPECT_LE(std::abs(db), 0.2) << name << " ab Sample " << von << ": " << db << " dB";
    }
}

}  // namespace

TEST(DspWarp, WarpVinylMatchesGolden) {
    REQUIRE_BINARIES();
    Golden& g = golden();
    const GoldenCase c = g.case_of("warp_vinyl");
    ASSERT_FALSE(c.inputs.at("keylock").as_bool());
    const auto audio = floatsOf(g, c.inputs.at("audio"));
    const auto quell = c.inputs.at("quell_s").numbers();
    const auto ziel = c.inputs.at("ziel_s").numbers();
    const auto out = klangbild::dsp::warp(audio, quell, ziel, false);
    ASSERT_EQ(c.tolerance, "dsp");
    g.expect_dsp("warp_vinyl", c.expected, std::vector<double>(out.begin(), out.end()));
}

TEST(DspWarp, ResampleLinearKnownValuesFromPrototype) {
    // resample.resample_linear(arange(8, float32), 2.0) liest jeden zweiten Wert.
    std::vector<float> acht(8);
    for (int i = 0; i < 8; ++i) acht[static_cast<std::size_t>(i)] = static_cast<float>(i);
    const auto halb = klangbild::dsp::resampleLinear(acht, 2.0);
    ASSERT_EQ(halb.size(), 4u);
    for (int i = 0; i < 4; ++i) EXPECT_EQ(halb[static_cast<std::size_t>(i)], 2.0f * i) << i;
    // Faktor 0,5 verdoppelt die Laenge und interpoliert linear; das Ende bleibt beim letzten Wert.
    const auto doppelt = klangbild::dsp::resampleLinear(acht, 0.5);
    ASSERT_EQ(doppelt.size(), 16u);
    EXPECT_EQ(doppelt[0], 0.0f);
    EXPECT_EQ(doppelt[1], 0.5f);
    EXPECT_EQ(doppelt[15], 7.0f);
    // Faktor 1 kopiert, leere Eingabe bleibt leer.
    EXPECT_EQ(klangbild::dsp::resampleLinear(acht, 1.0), acht);
    EXPECT_TRUE(klangbild::dsp::resampleLinear({}, 2.0).empty());
    // Auffuellen und Kuerzen: exakt n Frames.
    EXPECT_EQ(klangbild::dsp::padTo({1, 2}, 3, 2).size(), 6u);
    EXPECT_EQ(klangbild::dsp::padTo({1, 2, 3, 4}, 1, 2), (std::vector<float>{1, 2}));
}

TEST(DspWarp, KeylockDehntStattZuWerfen) {
    const std::vector<float> audio(2 * 44100, 0.1f);
    const std::vector<double> quell = {0.0, 441.0 / 44100.0};
    const std::vector<double> stark = {0.0, 485.0 / 44100.0};   // 9 % gedehnt: Keylock-Weg
    const auto gedehnt = klangbild::dsp::warp(audio, quell, stark, true);
    EXPECT_EQ(gedehnt.size(), 485u * 2);
    const std::vector<double> kaum = {0.0, 441.0 / 44100.0};    // 0 %: Resampling reicht
    EXPECT_NO_THROW(klangbild::dsp::warp(audio, quell, kaum, true));
    EXPECT_TRUE(klangbild::dsp::warp(audio, {}, {}, false).empty());
    // Leeres Audio, aber ein Ziel: der Prototyp liefert Stille in Ziel-Laenge (quell wird auf 0 geklemmt).
    const auto stille = klangbild::dsp::warp({}, quell, kaum, false);
    ASSERT_EQ(stille.size(), 2u * static_cast<std::size_t>(std::nearbyint(kaum[1] * 44100.0)));
    for (float v : stille) ASSERT_EQ(v, 0.0f);
}

TEST(DspWarp, WarpKeylockMatchesGolden) {
    REQUIRE_BINARIES();
    Golden& g = golden();
    const GoldenCase c = g.case_of("warp_keylock");
    ASSERT_TRUE(c.inputs.at("keylock").as_bool());
    const auto audio = floatsOf(g, c.inputs.at("audio"));
    const auto quell = c.inputs.at("quell_s").numbers();
    const auto ziel = c.inputs.at("ziel_s").numbers();
    const auto out = klangbild::dsp::warp(audio, quell, ziel, true);
    ASSERT_EQ(c.tolerance, "warp");
    expectWarp(g, "warp_keylock", c.expected, std::vector<double>(out.begin(), out.end()));
}

// ============================== T5.8 Loops ======================================================

TEST(DspLoop, LoopenMatchesGolden) {
    REQUIRE_BINARIES();
    Golden& g = golden();
    for (const char* size : {"1", "2", "4", "8", "16", "32", "rolle"}) {
        const std::string name = std::string("loop_") + size;
        SCOPED_TRACE(name);
        const GoldenCase c = g.case_of(name);
        const auto a = floatsOf(g, c.inputs.at("a"));
        const auto taktN = c.inputs.at("takt_n").numbers();
        const auto werte = c.inputs.at("plan").numbers();
        ASSERT_EQ(werte.size() % 3, 0u);
        std::vector<klangbild::dsp::LoopSection> plan;
        for (std::size_t i = 0; i + 2 < werte.size(); i += 3) {
            plan.push_back({static_cast<int>(werte[i]), static_cast<int>(werte[i + 1]),
                            static_cast<int>(werte[i + 2])});
        }
        ASSERT_EQ(plan.size(), werte.size() / 3);
        const auto out = klangbild::dsp::loopen(a, taktN, plan);
        ASSERT_EQ(c.tolerance, "dsp");
        g.expect_dsp(name, c.expected, std::vector<double>(out.begin(), out.end()));
    }
}

TEST(DspLoop, AchtelKnownValuesFromPrototype) {
    // uebergang._achtel(arange(5) * 88200): 8 Achtel je Takt, letzte Grenze schliesst den Takt.
    std::vector<double> taktN = {0, 88200, 176400, 264600, 352800};
    const auto achtel = klangbild::dsp::eighthGrid(taktN);
    ASSERT_EQ(achtel.size(), 33u);
    EXPECT_EQ(achtel[0], 0);
    EXPECT_EQ(achtel[1], 11025);
    EXPECT_EQ(achtel[8], 88200);
    EXPECT_EQ(achtel[32], 352800);
    EXPECT_TRUE(klangbild::dsp::eighthGrid(std::vector<double>{1.0}).empty());
}

TEST(DspLoop, LoopInfoKnownValuesFromPrototype) {
    using klangbild::dsp::Settings;
    const std::vector<double> taktS = {0, 2, 4, 6, 8};
    Settings s;
    s.art = "eigen";
    s.loop = "8";
    auto info = klangbild::dsp::loopInfo(s, taktS);
    ASSERT_EQ(info.size(), 1u);
    EXPECT_DOUBLE_EQ(info[0].von, 0.0);
    EXPECT_DOUBLE_EQ(info[0].bis, 8.0);
    EXPECT_DOUBLE_EQ(info[0].quelle, 0.0);
    EXPECT_DOUBLE_EQ(info[0].laenge, 4.0);

    s.loop = "rolle";
    info = klangbild::dsp::loopInfo(s, taktS);
    const double want[5][4] = {{0.0, 1.5, 0.0, 2.0}, {1.5, 3.0, 0.0, 1.0}, {3.0, 4.5, 0.0, 0.5},
                               {4.5, 6.0, 0.0, 0.25}, {6.0, 8.0, 0.0, 0.25}};
    ASSERT_EQ(info.size(), 5u);
    for (std::size_t i = 0; i < 5; ++i) {
        EXPECT_DOUBLE_EQ(info[i].von, want[i][0]) << i;
        EXPECT_DOUBLE_EQ(info[i].bis, want[i][1]) << i;
        EXPECT_DOUBLE_EQ(info[i].quelle, want[i][2]) << i;
        EXPECT_DOUBLE_EQ(info[i].laenge, want[i][3]) << i;
    }

    s.loop = "1";
    info = klangbild::dsp::loopInfo(s, taktS);
    ASSERT_EQ(info.size(), 1u);
    EXPECT_DOUBLE_EQ(info[0].von, 2.0);
    EXPECT_DOUBLE_EQ(info[0].bis, 8.0);
    EXPECT_DOUBLE_EQ(info[0].quelle, 2.0);
    EXPECT_DOUBLE_EQ(info[0].laenge, 0.5);

    s.art = "auto";
    EXPECT_TRUE(klangbild::dsp::loopInfo(s, taktS).empty());
    Settings leer;
    leer.art = "eigen";
    leer.loop = "keiner";
    EXPECT_TRUE(klangbild::dsp::loopInfo(leer, taktS).empty());
}

// ============================== T5.9 Loop-Wahl ==================================================

TEST(DspLoopChoice, ChooseLoopMatchesGolden) {
    REQUIRE_BINARIES();
    Golden& g = golden();
    for (const char* name : {"loopwahl_frei", "loopwahl_gesang", "loopwahl_alle"}) {
        SCOPED_TRACE(name);
        const GoldenCase c = g.case_of(name);
        const auto a = floatsOf(g, c.inputs.at("a"));
        const auto taktN = c.inputs.at("takt_n").numbers();
        std::vector<int> meiden;
        std::optional<std::span<const int>> sperre;
        const Json& roh = c.inputs.at("meiden");
        if (!roh.is_null()) {
            for (double d : roh.numbers()) meiden.push_back(static_cast<int>(d));
            sperre = std::span<const int>(meiden);
        }
        const auto out = klangbild::dsp::chooseLoop(a, taktN, sperre);
        const auto want = c.expected.numbers();
        ASSERT_EQ(want.size(), 3u);
        EXPECT_EQ(out.start, static_cast<int>(want[0]));
        EXPECT_EQ(out.bars, static_cast<int>(want[1]));
        EXPECT_NEAR(out.quality, want[2], 1e-6);
        ASSERT_EQ(c.tolerance, "values");
    }
}

TEST(DspLoopChoice, BeatFeaturesKnownValuesFromPrototype) {
    REQUIRE_BINARIES();
    Golden& g = golden();
    const auto a = floatsOf(g, g.raw("loopwahl_frei").at("inputs").at("a"));
    const std::vector<double> taktN = {0, 88200, 176400, 264600, 352800};
    const auto f = klangbild::dsp::beatFeatures(a, taktN);
    ASSERT_EQ(f.size(), 16u);
    const double want[16] = {8.935666,  38.444125, 37.569673, 0.41072,  4.738242,  7.25541,  40.014991, 7.679253,
                             10.348574, 11.678174, 13.607413, 15.882915, 17.103924, 17.997111, 19.640347, 21.129469};
    for (std::size_t i = 0; i < 16; ++i) EXPECT_NEAR(f[0][i], want[i], 1e-4) << i;
}

TEST(DspLoopChoice, LoopInOriginalKnownValuesFromPrototype) {
    REQUIRE_BINARIES();
    Golden& g = golden();
    const auto puffer = floatsOf(g, g.raw("loopwahl_frei").at("inputs").at("a"));
    const std::vector<double> raster = {0, 2, 4, 6, 8};
    const auto frei = klangbild::dsp::loopInOriginal(puffer, raster, 0, 4);
    EXPECT_EQ(frei.start, 0);
    EXPECT_EQ(frei.bars, 2);
    EXPECT_NEAR(frei.quality, 0.9757748671003617, 1e-6);

    const std::vector<int> meiden = {1, 1, 0, 0};
    const auto gesperrt = klangbild::dsp::loopInOriginal(puffer, raster, 0, 4, std::span<const int>(meiden));
    EXPECT_EQ(gesperrt.start, 0);
    EXPECT_EQ(gesperrt.bars, 3);
    EXPECT_DOUBLE_EQ(gesperrt.quality, 0.0);
}

// ============================== T5.10 Intro-Loop ================================================

TEST(DspIntroLoop, IntroLoopMatchesGolden) {
    REQUIRE_BINARIES();
    Golden& g = golden();
    for (int repeats : {1, 2}) {
        const std::string name = "introloop_" + std::to_string(repeats);
        SCOPED_TRACE(name);
        const GoldenCase c = g.case_of(name);
        const auto b = floatsOf(g, c.inputs.at("b_audio"));
        const auto bbar = c.inputs.at("bbar").numbers();
        const auto points = c.inputs.at("points").numbers();
        const int j0 = static_cast<int>(c.inputs.at("j0").as_double());
        const int k = static_cast<int>(c.inputs.at("k").as_double());
        const int mal = static_cast<int>(c.inputs.at("mal").as_double());
        const auto loop = klangbild::dsp::introLoop(b, bbar, j0, k, mal);
        ASSERT_EQ(c.tolerance, "dsp");
        g.expect_dsp(name + "/audio", c.expected.at("audio"),
                     std::vector<double>(loop.audio.begin(), loop.audio.end()));
        g.expect_values(name + "/raster", c.expected.at("raster"), loop.raster);
        g.expect_values(name + "/rueck", c.expected.at("rueck"), klangbild::dsp::introLoopBack(loop, points));
    }
}

// ============================== T5.11 mischen_eigen =============================================

namespace {

std::vector<float> readF32(const std::string& pfad) {
    std::ifstream datei(pfad, std::ios::binary);
    if (!datei.good()) return {};
    std::vector<char> roh((std::istreambuf_iterator<char>(datei)), std::istreambuf_iterator<char>());
    std::vector<float> aus(roh.size() / 4);
    std::memcpy(aus.data(), roh.data(), aus.size() * 4);
    return aus;
}

}  // namespace

TEST(DspEigen, MischenEigenMatchesGolden) {
    REQUIRE_BINARIES();
    Golden& g = golden();
    const auto ir = floatsOf(g, g.raw("hall_ir").at("expected"));
    // Rauschen fuer den Riser: der Prototyp zieht es aus default_rng(3). Zufall ist nicht bitgleich
    // portierbar, darum liegt die Python-Folge als Testeingabe daneben (nur lokal, wie alle .f32).
    const std::vector<float> rauschen = readF32(goldenDir() + "/riser_noise.f32");
    int geprueft = 0, uebersprungen = 0;
    for (const Recipe& r : kRecipes) {
        const std::string name = std::string("eigen_") + r.name;
        SCOPED_TRACE(name);
        if (std::string(r.name) == "trick_riser" && rauschen.empty()) {
            ++uebersprungen;   // ohne die Python-Rauschfolge nicht vergleichbar
            continue;
        }
        const GoldenCase c = g.case_of(name);
        const auto a = floatsOf(g, c.inputs.at("a"));
        const auto b = floatsOf(g, c.inputs.at("b"));
        const auto taktN = c.inputs.at("takt_n").numbers();
        const auto out = klangbild::dsp::mischenEigen(a, b, settingsOf(r), taktN, ir, rauschen);
        std::vector<double> ist(out.blende.begin(), out.blende.end());
        ist.insert(ist.end(), out.nachlauf.begin(), out.nachlauf.end());
        if (c.tolerance == "reverb") {
            g.expect_reverb(name, c.expected, ist);
        } else {
            ASSERT_EQ(c.tolerance, "dsp");
            g.expect_dsp(name, c.expected, ist);
        }
        ++geprueft;
    }
    EXPECT_EQ(geprueft + uebersprungen, 14);
}

// Referenz: uebergang.mischen_eigen mit effekt_ein="rueckhall" (kein eigener Golden-Fall).
TEST(DspEigen, RueckhallKnownValuesFromPrototype) {
    REQUIRE_BINARIES();
    Golden& g = golden();
    const auto a = floatsOf(g, g.raw("eigen_outro_loop").at("inputs").at("a"));
    const auto b = floatsOf(g, g.raw("eigen_outro_loop").at("inputs").at("b"));
    const std::vector<double> taktN = {0, 88200, 176400, 264600, 352800};
    const auto ir = floatsOf(g, g.raw("hall_ir").at("expected"));
    klangbild::dsp::Settings s;
    s.effectIn = "rueckhall";
    s.volume = "drop";
    const auto out = klangbild::dsp::mischenEigen(a, b, s, taktN, ir);
    ASSERT_EQ(out.blende.size(), 352800u * 2);
    EXPECT_TRUE(out.nachlauf.empty());
    EXPECT_NEAR(out.blende[0], 0.3905813694000244, 1e-5);
    EXPECT_NEAR(out.blende[1], 0.45651981234550476, 1e-5);
    EXPECT_NEAR(out.blende[100000 * 2], 0.09504580497741699, 1e-5);
    EXPECT_NEAR(out.blende[100000 * 2 + 1], -0.14963111281394958, 1e-5);
    double quadrat = 0.0, spitze = 0.0;
    for (float v : out.blende) {
        quadrat += static_cast<double>(v) * static_cast<double>(v);
        spitze = std::max(spitze, std::abs(static_cast<double>(v)));
    }
    EXPECT_NEAR(std::sqrt(quadrat / static_cast<double>(out.blende.size())), 0.12655517347961429, 1e-5);
    EXPECT_NEAR(spitze, 0.7355132699012756, 1e-5);
}

// ============================== T5.7b Limiter ===================================================

TEST(DspLimiter, BegrenzenMatchesGolden) {
    REQUIRE_BINARIES();
    Golden& g = golden();
    for (const char* name : {"limiter_stille", "limiter_leise", "limiter_spitzen", "limiter_teil", "limiter_leer"}) {
        SCOPED_TRACE(name);
        const GoldenCase c = g.case_of(name);
        auto x = floatsOf(g, c.inputs.at("x"));
        const long long bis = static_cast<long long>(c.inputs.at("bis").as_double());
        const double decke = c.inputs.at("decke").as_double();
        klangbild::dsp::begrenzen(x, bis, decke);
        ASSERT_EQ(c.tolerance, "dsp");
        g.expect_dsp(name, c.expected, std::vector<double>(x.begin(), x.end()));
    }
}

// ============================== M6.4 Raster, Ausstieg, Einstieg =================================

namespace {

klangbild::dsp::Eintrag eintragFromJson(const Json& j) {
    klangbild::dsp::Eintrag e;
    e.id = static_cast<int>(j.at("id").as_double());
    e.pfad = j.at("pfad").as_string();
    e.bpm = j.at("bpm").as_double();
    if (j.has("camelot") && !j.at("camelot").is_null()) e.camelot = j.at("camelot").as_string();
    for (double d : j.at("downbeats").numbers()) e.downbeats.push_back(d);
    if (j.has("abschnitte")) {
        for (double d : j.at("abschnitte").numbers()) e.abschnitte.push_back(d);
    }
    if (j.has("fein")) {
        for (const Json& p : j.at("fein").items) {
            const auto werte = p.numbers();
            if (werte.size() == 2) e.fein.push_back({werte[0], werte[1]});
        }
    }
    return e;
}

}  // namespace

TEST(DspRaster, RegulaerMatchesGolden) {
    Golden& g = golden();
    for (const char* name : {"regulaer_leer", "regulaer_normal", "regulaer_versatz", "regulaer_ausreisser"}) {
        SCOPED_TRACE(name);
        const GoldenCase c = g.case_of(name);
        const auto downbeats = c.inputs.at("downbeats").numbers();
        const double bpm = c.inputs.at("bpm").as_double();
        const double bis = c.inputs.at("bis_s").as_double();
        const auto out = klangbild::dsp::regulaer(downbeats, bpm, bis);
        ASSERT_EQ(c.tolerance, "values");
        g.expect_values(name, c.expected, out);
    }
}

TEST(DspRaster, AusstiegMatchesGolden) {
    Golden& g = golden();
    for (const char* name : {"ausstieg_outro", "ausstieg_phrase", "ausstieg_vor_ende"}) {
        SCOPED_TRACE(name);
        const GoldenCase c = g.case_of(name);
        klangbild::dsp::Spur spur;
        spur.eintrag = eintragFromJson(c.inputs.at("eintrag"));
        spur.frames = static_cast<long long>(c.inputs.at("frames").as_double());
        for (double d : c.inputs.at("orig").numbers()) spur.orig.push_back(d);
        for (double d : c.inputs.at("buf").numbers()) spur.buf.push_back(d);
        const klangbild::dsp::Settings s = settingsFromJson(c.inputs.at("e"));
        const int takte = static_cast<int>(c.inputs.at("takte").as_double());
        const double abS = c.inputs.at("ab_s").as_double();
        const auto out = klangbild::dsp::ausstieg(spur, s, takte, abS);
        ASSERT_EQ(c.tolerance, "values");
        g.expect_values(std::string(name) + "/raster", c.expected.items.at(0), out.raster);
        EXPECT_EQ(out.index, static_cast<int>(c.expected.items.at(1).as_double()));
    }
}

TEST(DspRaster, EinstiegMatchesGolden) {
    Golden& g = golden();
    for (const char* name : {"einstieg_intro", "einstieg_drop"}) {
        SCOPED_TRACE(name);
        const GoldenCase c = g.case_of(name);
        const klangbild::dsp::Eintrag b = eintragFromJson(c.inputs.at("b"));
        const long long samples = static_cast<long long>(c.inputs.at("b_samples").as_double());
        const klangbild::dsp::Settings s = settingsFromJson(c.inputs.at("e"));
        const auto out = klangbild::dsp::einstieg(b, samples, s);
        ASSERT_EQ(c.tolerance, "values");
        g.expect_values(std::string(name) + "/raster", c.expected.items.at(0), out.raster);
        EXPECT_EQ(out.index, static_cast<int>(c.expected.items.at(1).as_double()));
    }
}

// Referenz: uebergang.taktraster mit Fein-Anker, raster, _periode und _ext.
TEST(DspRaster, TaktrasterUndHilfenKnownValuesFromPrototype) {
    klangbild::dsp::Eintrag e;
    e.bpm = 120;
    e.downbeats = {0, 2, 4, 6};
    e.fein = {{0.0, 0.02}, {4.0, -0.01}};
    const auto t = klangbild::dsp::taktraster(e, 8.0);
    const double want[6] = {0.02, 2.005, 3.99, 5.99, 7.99, 9.99};
    ASSERT_EQ(t.size(), 6u);
    for (std::size_t i = 0; i < 6; ++i) EXPECT_NEAR(t[i], want[i], 1e-6) << i;

    const std::vector<double> takte = {0, 2, 4, 6};
    EXPECT_EQ(klangbild::dsp::raster(takte, 9.0), (std::vector<double>{0, 2, 4, 6, 8, 10}));
    const std::vector<double> t6 = {0, 2, 4, 6, 8, 10};
    EXPECT_DOUBLE_EQ(klangbild::dsp::periode(t6, 3), 2.0);
    EXPECT_DOUBLE_EQ(klangbild::dsp::ext(1.5, {0, 2, 4}, {0, 2.5, 4.0}), 1.875);
    EXPECT_DOUBLE_EQ(klangbild::dsp::ext(5.0, {0, 2, 4}, {0, 2.5, 4.0}), 4.75);
}

// ============================== M6.5 backen =====================================================

TEST(DspBacken, BackenMatchesGolden) {
    REQUIRE_BINARIES();
    Golden& g = golden();
    const auto ir = floatsOf(g, g.raw("hall_ir").at("expected"));
    for (const char* eintrag : {"backen_vinyl", "backen_echo", "backen_introloop", "backen_keylock"}) {
        const std::string name = eintrag;
        SCOPED_TRACE(name);
        const GoldenCase c = g.case_of(name);
        const klangbild::dsp::Eintrag a = eintragFromJson(c.inputs.at("a"));
        const auto aAudio = floatsOf(g, c.inputs.at("a_audio"));
        const klangbild::dsp::Eintrag b = eintragFromJson(c.inputs.at("b"));
        const auto bAudio = floatsOf(g, c.inputs.at("b_audio"));
        const auto s = settingsFromJson(c.inputs.at("e"));
        const double abS = c.inputs.at("ab_s").as_double();
        std::optional<double> ausS, einS;
        if (!c.inputs.at("aus_s").is_null()) ausS = c.inputs.at("aus_s").as_double();
        if (!c.inputs.at("ein_s").is_null()) einS = c.inputs.at("ein_s").as_double();
        const klangbild::dsp::Spur spur = klangbild::dsp::rohSpur(a, aAudio);
        const auto out = klangbild::dsp::backen(spur, b, bAudio, s, abS, false, ausS, einS, ir);

        const Json& want = c.expected;
        EXPECT_EQ(out.startN, static_cast<long long>(want.at("start_n").as_double()));
        const std::vector<double> audio(out.spur.puffer.begin(), out.spur.puffer.end());
        if (name == "backen_keylock") {
            expectWarp(g, name + "/audio", want.at("audio"), audio);
        } else {
            g.expect_dsp(name + "/audio", want.at("audio"), audio);
        }
        g.expect_values(name + "/orig", want.at("orig"), out.spur.orig);
        g.expect_values(name + "/buf", want.at("buf"), out.spur.buf);

        const Json& wi = want.at("info");
        EXPECT_EQ(out.info.art, wi.at("art").as_string());
        EXPECT_EQ(out.info.takte, static_cast<int>(wi.at("takte").as_double()));
        EXPECT_EQ(out.info.sync, wi.at("sync").as_bool());
        EXPECT_DOUBLE_EQ(out.info.bpmA, wi.at("bpm_a").as_double());
        EXPECT_DOUBLE_EQ(out.info.bpmB, wi.at("bpm_b").as_double());
        EXPECT_EQ(out.info.modus, wi.at("modus").as_string());
        EXPECT_EQ(out.info.stems, wi.at("stems").as_bool());
        EXPECT_DOUBLE_EQ(out.info.blendeS, wi.at("blende_s").as_double());
        EXPECT_DOUBLE_EQ(out.info.aOrigStart, wi.at("a_orig_start").as_double());
        EXPECT_DOUBLE_EQ(out.info.bOrigStart, wi.at("b_orig_start").as_double());
        EXPECT_DOUBLE_EQ(out.info.aOrigProS, wi.at("a_orig_pro_s").as_double());
        g.expect_values(name + "/raster_s", wi.at("raster_s"), out.info.rasterS);
    }
}
