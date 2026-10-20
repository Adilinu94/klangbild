// Host-Tests fuer den PCM-Feeder (BAUPLAN-ANDROID T2.2/T2.3): liest den Cache ab einer
// Startposition, wartet auf den Flush und fuellt den Ring. Kein Oboe, kein Geraet.
#include <gtest/gtest.h>

#include <cstdint>
#include <cstdio>
#include <string>
#include <vector>

#include "pcm_feeder.h"
#include "playback_core.h"

using klangbild::PcmFeeder;
using klangbild::PlaybackCore;

namespace {

/// Schreibt eine PCM-Cache-Datei (Kopf `KBPC`, int16, Stereo 44,1 kHz).
bool schreibePcm(const std::string& pfad, const std::vector<float>& stereo) {
    std::FILE* datei = std::fopen(pfad.c_str(), "wb");
    if (datei == nullptr) return false;
    const uint32_t frames = static_cast<uint32_t>(stereo.size() / 2);
    unsigned char kopf[16] = {'K', 'B', 'P', 'C', 1, 0, 2, 0, 0x44, 0xAC, 0, 0, 0, 0, 0, 0};
    for (int i = 0; i < 4; ++i) kopf[12 + i] = static_cast<unsigned char>((frames >> (8 * i)) & 0xFF);
    bool ok = std::fwrite(kopf, 1, sizeof(kopf), datei) == sizeof(kopf);
    for (float wert : stereo) {
        const int16_t roh = static_cast<int16_t>(std::max(-32767.0f, std::min(32767.0f, wert * 32767.0f)));
        const unsigned char bytes[2] = {
            static_cast<unsigned char>(roh & 0xFF),
            static_cast<unsigned char>((roh >> 8) & 0xFF),
        };
        ok = ok && std::fwrite(bytes, 1, 2, datei) == 2;
    }
    std::fclose(datei);
    return ok;
}

}  // namespace

TEST(PcmFeeder, LiestAbStartframeNachDemFlush) {
    const std::string pfad = "pcm-feeder-test.pcm";
    std::vector<float> quelle(2 * 3000);
    for (int i = 0; i < 3000; ++i) {
        quelle[2 * i] = static_cast<float>(i) / 10000.0f;
        quelle[2 * i + 1] = -quelle[2 * i];
    }
    ASSERT_TRUE(schreibePcm(pfad, quelle));

    PlaybackCore core;
    PcmFeeder feeder(core);
    ASSERT_TRUE(feeder.oeffne(pfad, 100, 7));
    EXPECT_TRUE(feeder.offen());
    EXPECT_EQ(feeder.fill(), 0u);   // Flush noch nicht bestaetigt

    std::vector<float> block(2 * 441);
    core.process(block.data(), 441);   // Callback bestaetigt und leert den Ring
    EXPECT_EQ(feeder.fill(), 2900u);   // 3000 - 100, passt alles in den Ring
    EXPECT_EQ(feeder.spur(), 7);
    EXPECT_EQ(feeder.position(), 3000);

    std::vector<float> aus(2 * 2900);
    ASSERT_EQ(core.ring().read(aus.data(), 2900), 2900u);
    for (int i = 0; i < 2900; ++i) {
        EXPECT_NEAR(aus[2 * i], quelle[2 * (100 + i)], 1e-4f) << i;
        EXPECT_NEAR(aus[2 * i + 1], quelle[2 * (100 + i) + 1], 1e-4f) << i;
    }
    EXPECT_EQ(feeder.fill(), 0u);
    EXPECT_TRUE(feeder.fertig());
    std::remove(pfad.c_str());
}

TEST(PcmFeeder, OhneDateiLaeuftDerSinus) {
    PlaybackCore core;
    PcmFeeder feeder(core);
    EXPECT_FALSE(feeder.offen());
    EXPECT_GT(feeder.fill(), 0u);
    std::vector<float> block(2 * 256);
    core.setPlaying(true);
    core.process(block.data(), 256);
    EXPECT_EQ(core.underflows(), 0u);
}

TEST(PcmFeeder, UngueltigeDateiLaesstDieQuelleStehen) {
    const std::string pfad = "pcm-feeder-kaputt.pcm";
    std::FILE* datei = std::fopen(pfad.c_str(), "wb");
    ASSERT_NE(datei, nullptr);
    std::fputs("nope", datei);
    std::fclose(datei);

    PlaybackCore core;
    PcmFeeder feeder(core);
    EXPECT_FALSE(feeder.oeffne(pfad));
    EXPECT_FALSE(feeder.offen());
    EXPECT_GT(feeder.fill(), 0u);   // Sinus laeuft weiter
    std::remove(pfad.c_str());
}
