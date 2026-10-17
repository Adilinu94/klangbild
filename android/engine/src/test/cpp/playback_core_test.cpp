// Host-Tests fuer OutputRing, Rampen und die Callback-Logik (BAUPLAN-ANDROID T1.1/T1.2).
// Kein Oboe, kein Geraet: PlaybackCore::process() wird direkt aufgerufen.
#include <gtest/gtest.h>

#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <numbers>
#include <new>
#include <random>
#include <thread>
#include <vector>

#include "denormals.h"
#include "output_ring.h"
#include "playback_core.h"
#include "sine_feeder.h"

// GCC meldet bei eigenen operator new/delete auf malloc/free einen Fehlalarm (Inlining der Allokatoren).
#if defined(__GNUC__) && !defined(__clang__)
#pragma GCC diagnostic ignored "-Wmismatched-new-delete"
#endif

using klangbild::OutputRing;
using klangbild::PlaybackCore;
using klangbild::SineFeeder;

// --- Allokationen zaehlen (nur wenn scharf geschaltet): beweist "kein new im Callback" ---------------
// Unter AddressSanitizer ersetzt der Sanitizer selbst operator new; dort entfaellt der Zaehler.
#if defined(__SANITIZE_ADDRESS__)
#define KLINGBILD_ASAN 1
#elif defined(__has_feature)
#if __has_feature(address_sanitizer)
#define KLINGBILD_ASAN 1
#endif
#endif

namespace {
std::atomic<bool> gZaehleAllokationen{false};
std::atomic<long> gAllokationen{0};
}  // namespace

#ifndef KLINGBILD_ASAN
void* operator new(std::size_t n) {
    if (gZaehleAllokationen.load(std::memory_order_relaxed)) gAllokationen.fetch_add(1, std::memory_order_relaxed);
    if (void* p = std::malloc(n ? n : 1)) return p;
    throw std::bad_alloc();
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }
#endif

namespace {

constexpr double kPi = std::numbers::pi;
constexpr int32_t kRamp = PlaybackCore::kRampFrames;

/// Stereo-Sinus (L = R), interleaved, ab absolutem Frame `start`.
std::vector<float> sinus(int64_t start, int64_t frames, double hz, float amp) {
    std::vector<float> v(static_cast<std::size_t>(frames) * 2);
    for (int64_t i = 0; i < frames; ++i) {
        const float s = amp * static_cast<float>(std::sin(2.0 * kPi * hz * static_cast<double>(start + i) / 44100.0));
        v[static_cast<std::size_t>(2 * i)] = s;
        v[static_cast<std::size_t>(2 * i + 1)] = s;
    }
    return v;
}

/// Schreibt `quelle` ganz in den Ring (der Test haelt die Fuellung unter der Kapazitaet).
void fuettern(PlaybackCore& core, const std::vector<float>& quelle) {
    const uint32_t frames = static_cast<uint32_t>(quelle.size() / 2);
    ASSERT_EQ(core.ring().write(quelle.data(), frames), frames);
}

/// Laesst den Callback `frames` Frames in Bloecken der angegebenen Groessen (reihum) rechnen.
std::vector<float> laufen(PlaybackCore& core, int64_t frames, const std::vector<int32_t>& bloecke) {
    std::vector<float> aus;
    aus.reserve(static_cast<std::size_t>(frames) * 2);
    std::vector<float> block;
    int64_t fertig = 0;
    std::size_t k = 0;
    while (fertig < frames) {
        const int32_t n = static_cast<int32_t>(std::min<int64_t>(bloecke[k++ % bloecke.size()], frames - fertig));
        block.assign(static_cast<std::size_t>(n) * 2, -777.0f);   // Marker: wird immer ueberschrieben
        core.process(block.data(), n);
        aus.insert(aus.end(), block.begin(), block.end());
        fertig += n;
    }
    return aus;
}

/// Groesster Betrag der Differenz zweier aufeinanderfolgender Frames (je Kanal).
/// `stelle` bekommt den Frame, an dem er auftritt (fuer die Fehlersuche).
double groessterSprung(const std::vector<float>& v, std::size_t* stelle = nullptr) {
    double m = 0.0;
    for (std::size_t i = 2; i + 1 < v.size(); ++i) {
        const double d = std::abs(static_cast<double>(v[i]) - v[i - 2]);
        if (d > m) {
            m = d;
            if (stelle) *stelle = i / 2;
        }
    }
    return m;
}

}  // namespace

// ============================== OutputRing ======================================================

TEST(OutputRing, UmlaufUndReihenfolge) {
    OutputRing ring;
    std::vector<float> in(2000), out(2 * 777);
    int64_t geschrieben = 0, gelesen = 0;
    while (gelesen < 300000) {
        // schreiben, solange Platz ist
        const uint32_t n = std::min<uint32_t>(1000, ring.writable());
        for (uint32_t i = 0; i < n; ++i) {
            in[2 * i] = static_cast<float>((geschrieben + i) % 1000003);
            in[2 * i + 1] = -in[2 * i];
        }
        geschrieben += ring.write(in.data(), n);
        const uint32_t got = ring.read(out.data(), 777);
        for (uint32_t i = 0; i < got; ++i) {
            ASSERT_EQ(out[2 * i], static_cast<float>((gelesen + i) % 1000003)) << gelesen + i;
            ASSERT_EQ(out[2 * i + 1], -out[2 * i]);
        }
        gelesen += got;
    }
    EXPECT_GT(gelesen, static_cast<int64_t>(OutputRing::kStorageFrames) * 4);   // mehrfach umgelaufen
}

TEST(OutputRing, KapazitaetUndTeilweiseTransfers) {
    OutputRing ring;
    std::vector<float> in(2 * 50000, 0.5f), out(2 * 50000);
    EXPECT_EQ(ring.writable(), OutputRing::kCapacityFrames);
    EXPECT_EQ(ring.write(in.data(), 50000), OutputRing::kCapacityFrames);   // nie ueber 1 s
    EXPECT_EQ(ring.writable(), 0u);
    EXPECT_EQ(ring.write(in.data(), 10), 0u);
    EXPECT_EQ(ring.read(out.data(), 100), 100u);
    EXPECT_EQ(ring.write(in.data(), 200), 100u);
    EXPECT_EQ(ring.read(out.data(), 50000), OutputRing::kCapacityFrames);   // liest hoechstens, was da ist
    EXPECT_EQ(ring.read(out.data(), 10), 0u);
    ring.write(in.data(), 500);
    ring.discardAll();
    EXPECT_EQ(ring.available(), 0u);
    EXPECT_EQ(ring.writable(), OutputRing::kCapacityFrames);
}

TEST(OutputRing, EinSchreiberEinLeserStresstest) {
    OutputRing ring;
    constexpr int64_t kGesamt = 3'000'000;
    std::atomic<bool> fehler{false};
    const auto frist = std::chrono::steady_clock::now() + std::chrono::seconds(60);

    std::thread schreiber([&] {
        std::mt19937 rng(1);
        std::vector<float> chunk(2 * 2048);
        int64_t k = 0;
        while (k < kGesamt && !fehler.load()) {
            const uint32_t n = static_cast<uint32_t>(std::min<int64_t>(1 + rng() % 2048, kGesamt - k));
            for (uint32_t i = 0; i < n; ++i) {
                chunk[2 * i] = static_cast<float>((k + i) & 0xFFFFF);          // < 2^24: exakt als float
                chunk[2 * i + 1] = static_cast<float>(((k + i) >> 3) & 0xFFFFF);
            }
            const uint32_t w = ring.write(chunk.data(), n);
            k += w;
            if (w < n) {   // nicht alles geschrieben: den Rest im naechsten Anlauf (Reihenfolge wahren)
                k -= w;
                for (uint32_t i = 0; i < w; ++i) {}   // (nichts: der Test schreibt neu ab k + w)
                k += w;
                // Reststueck neu aufbauen
                const uint32_t rest = n - w;
                for (uint32_t i = 0; i < rest; ++i) {
                    chunk[2 * i] = static_cast<float>((k + i) & 0xFFFFF);
                    chunk[2 * i + 1] = static_cast<float>(((k + i) >> 3) & 0xFFFFF);
                }
                uint32_t off = 0;
                while (off < rest && !fehler.load()) {
                    const uint32_t w2 = ring.write(chunk.data() + 2 * static_cast<std::size_t>(off), rest - off);
                    off += w2;
                    if (w2 == 0) std::this_thread::yield();
                    if (std::chrono::steady_clock::now() > frist) fehler = true;
                }
                k += rest;
            }
        }
    });

    std::mt19937 rng(2);
    std::vector<float> out(2 * 1500);
    int64_t gelesen = 0;
    while (gelesen < kGesamt && !fehler.load()) {
        const uint32_t got = ring.read(out.data(), 1 + rng() % 1500);
        for (uint32_t i = 0; i < got; ++i) {
            const int64_t k = gelesen + i;
            if (out[2 * i] != static_cast<float>(k & 0xFFFFF) || out[2 * i + 1] != static_cast<float>((k >> 3) & 0xFFFFF)) {
                fehler = true;
                ADD_FAILURE() << "falscher Wert bei Frame " << k;
                break;
            }
        }
        gelesen += got;
        if (got == 0) std::this_thread::yield();
        if (std::chrono::steady_clock::now() > frist) fehler = true;
    }
    schreiber.join();
    EXPECT_FALSE(fehler.load());
    EXPECT_EQ(gelesen, kGesamt);
}

// ============================== Rampen ==========================================================

TEST(PlaybackCore, EinblendungDauertGenau441FramesUndIstDanachExakt1) {
    PlaybackCore core;
    fuettern(core, std::vector<float>(2 * 3000, 1.0f));   // Gleichspannung 1,0
    core.setPlaying(true);
    const auto out = laufen(core, 3000, {512});
    for (int i = 0; i < kRamp; ++i) {
        ASSERT_FLOAT_EQ(out[2 * i], static_cast<float>(i + 1) / kRamp) << i;    // linear
        ASSERT_EQ(out[2 * i], out[2 * i + 1]);
    }
    for (int i = kRamp - 1; i < 3000; ++i) ASSERT_EQ(out[2 * i], 1.0f) << i;      // exakt voll ab Frame 440
    EXPECT_EQ(core.framesPlayed(), 3000u);
    EXPECT_EQ(core.underflows(), 0u);
}

TEST(PlaybackCore, StilleSolangeNichtGespieltWird) {
    PlaybackCore core;
    fuettern(core, std::vector<float>(2 * 1000, 1.0f));
    const auto out = laufen(core, 2000, {300});
    for (float s : out) ASSERT_EQ(s, 0.0f);
    EXPECT_EQ(core.ring().available(), 1000u);   // nichts verbraucht
    EXPECT_EQ(core.underflows(), 0u);
}

// T1.2: "Rampe 441 Frames, kein Sprung groesser als 0,01 zwischen zwei Samples beim Pausieren eines
// vollen Sinus". Ein 440-Hz-Sinus mit Amplitude 1 hat selbst Schritte bis 0,063 pro Sample. Darum
// gilt die Schranke fuer den Sprung, den die Rampe ZUSAETZLICH zur Steigung des Signals erzeugt.
TEST(PlaybackCore, PausierenMitRampeOhneZusaetzlichenSprung) {
    const double signalSchritt = 2.0 * kPi * 440.0 / 44100.0;   // groesster Schritt des Sinus (Amplitude 1)
    double maxAmplitudeBeimStopp = 0.0;
    int geprueft = 0;
    for (int blockModus = 0; blockModus < 3; ++blockModus) {
        const std::vector<std::vector<int32_t>> bloecke = {{441}, {192, 480, 1024, 64, 333}, {1}};
        for (int versatz = 0; versatz < 100; versatz += 7) {   // viele Phasenlagen, auch am Scheitel
            PlaybackCore core;
            const int64_t stopp = 3000 + versatz;
            const int64_t gesamt = stopp + 2000;
            const auto quelle = sinus(0, gesamt, 440.0, 1.0f);   // voller Pegel
            // Ring ist nur 1 s gross: die ganze Quelle (< 6000 Frames) passt hinein.
            fuettern(core, quelle);
            core.setPlaying(true);
            auto out = laufen(core, stopp, bloecke[static_cast<std::size_t>(blockModus)]);
            core.setPlaying(false);
            const auto rest = laufen(core, gesamt - stopp, bloecke[static_cast<std::size_t>(blockModus)]);
            out.insert(out.end(), rest.begin(), rest.end());

            // (a) vor dem Stopp: nach der Einblendung Ausgabe == Eingabe
            for (int64_t i = kRamp; i < stopp; ++i)
                ASSERT_EQ(out[static_cast<std::size_t>(2 * i)], quelle[static_cast<std::size_t>(2 * i)]) << i;
            // (b) keine Spruenge ueber Signalsteigung + 0,01, ueber die ganze Strecke inkl. Einblendung und Stille
            ASSERT_LE(groessterSprung(out), signalSchritt + 0.01) << "Modus " << blockModus << " Versatz " << versatz;
            // (c) nach 441 Frames Ausblendung exakt Stille (Frame stopp+440 ist der erste mit Verstaerkung 0)
            for (int64_t i = stopp + kRamp - 1; i < gesamt; ++i)
                ASSERT_EQ(out[static_cast<std::size_t>(2 * i)], 0.0f) << i;
            ASSERT_NE(out[static_cast<std::size_t>(2 * (stopp + kRamp - 2))], 0.0f);   // davor noch nicht
            maxAmplitudeBeimStopp = std::max(maxAmplitudeBeimStopp, std::abs(static_cast<double>(quelle[static_cast<std::size_t>(2 * stopp)])));
            ++geprueft;
        }
    }
    // Der Test ist nur aussagekraeftig, wenn ein harter Schnitt hoerbar springen wuerde.
    EXPECT_GT(maxAmplitudeBeimStopp, 0.9) << "kein Stopp nahe dem Scheitel getestet";
    EXPECT_GT(geprueft, 30);
}

TEST(PlaybackCore, WeiterspielenBlendetEinOhneSprung) {
    const double signalSchritt = 2.0 * kPi * 440.0 / 44100.0;
    PlaybackCore core;
    const auto quelle = sinus(0, 20000, 440.0, 1.0f);
    fuettern(core, quelle);
    core.setPlaying(true);
    auto out = laufen(core, 3000, {480});
    core.setPlaying(false);
    auto pause = laufen(core, 1500, {480});
    out.insert(out.end(), pause.begin(), pause.end());
    core.setPlaying(true);
    auto weiter = laufen(core, 3000, {480});
    out.insert(out.end(), weiter.begin(), weiter.end());

    // Dazwischen liegt eine Luecke (441 Frames wurden beim Ausblenden verbraucht): die Ausgabe ist
    // trotzdem sprungfrei, weil vor und nach der Stille die Verstaerkung 0 ist.
    EXPECT_LE(groessterSprung(out), signalSchritt + 0.01);
    for (int i = 0; i < 1500 - kRamp; ++i) ASSERT_EQ(out[2 * (3000 + kRamp + i)], 0.0f);   // Stille
    // Ab 441 Frames nach dem Weiterspielen wieder volle Lautstaerke: Ausgabe gleich Ring-Inhalt.
    const std::size_t zeilen = 3000 + 1500;
    for (int i = kRamp; i < 3000; ++i) {
        const int64_t quellFrame = 3000 + kRamp + i;   // 441 Frames beim Ausblenden verbraucht
        ASSERT_EQ(out[2 * (zeilen + i)], quelle[static_cast<std::size_t>(2 * quellFrame)]) << i;
    }
    EXPECT_EQ(core.underflows(), 0u);
}

// ============================== Underflow =======================================================

TEST(PlaybackCore, UnderflowNurBeiLaufenderWiedergabeUndJeBlockEinmal) {
    PlaybackCore core;
    std::vector<float> block(2 * 480, -1.0f);
    for (int i = 0; i < 10; ++i) core.process(block.data(), 480);   // pausiert und leer
    EXPECT_EQ(core.underflows(), 0u);
    for (float s : block) ASSERT_EQ(s, 0.0f);

    core.setPlaying(true);
    core.process(block.data(), 480);   // leer, aber es soll laufen: echte Luecke
    EXPECT_EQ(core.underflows(), 1u);
    for (float s : block) ASSERT_EQ(s, 0.0f);

    fuettern(core, std::vector<float>(2 * 100, 0.5f));   // zu wenig fuer einen Block
    std::fill(block.begin(), block.end(), -1.0f);
    core.process(block.data(), 480);
    EXPECT_EQ(core.underflows(), 2u);                    // je Block einmal, nicht je Frame
    EXPECT_EQ(core.framesPlayed(), 100u);
    for (std::size_t i = 2 * 100; i < block.size(); ++i) ASSERT_EQ(block[i], 0.0f) << i;   // Rest Stille
}

TEST(PlaybackCore, NachEinerLueckeBeginntAudioMitEinblendung) {
    PlaybackCore core;
    fuettern(core, sinus(0, 3000, 440.0, 1.0f));
    core.setPlaying(true);
    auto out = laufen(core, 4000, {500});               // der Ring laeuft nach 3000 Frames leer
    EXPECT_GT(core.underflows(), 0u);
    for (int i = 3000; i < 4000; ++i) ASSERT_EQ(out[static_cast<std::size_t>(2 * i)], 0.0f) << i;   // Luecke = Stille

    const auto neu = sinus(5000, 3000, 440.0, 1.0f);   // Audio kommt zurueck, mitten im Sinus
    fuettern(core, neu);
    const auto danach = laufen(core, 3000, {500});
    for (int i = 0; i < kRamp; ++i)   // eingeblendet: nie lauter als die Rampe es zulaesst
        ASSERT_LE(std::abs(danach[static_cast<std::size_t>(2 * i)]), static_cast<float>(i + 1) / kRamp + 1e-6f) << i;
    EXPECT_LE(std::abs(danach[0]), 1.0f / kRamp + 1e-6f);   // erster Frame praktisch stumm: kein Knacken
    for (int i = kRamp; i < 3000; ++i) ASSERT_EQ(danach[static_cast<std::size_t>(2 * i)], neu[static_cast<std::size_t>(2 * i)]) << i;
}

// ============================== Flush ===========================================================

TEST(PlaybackCore, FlushBlendetAltesAusLeertDenRingUndBestaetigt) {
    const double schritt = 2.0 * kPi * 880.0 / 44100.0 * 0.5;   // groesster Schritt des lauteren der beiden Sinus
    PlaybackCore core;
    fuettern(core, sinus(0, 10000, 440.0, 0.5f));
    core.setPlaying(true);
    auto out = laufen(core, 2000, {480});

    const uint32_t serial = core.requestFlush();
    EXPECT_NE(core.flushAck(), serial);               // noch nicht bestaetigt: der Feeder darf nicht schreiben
    // Bloecke laufen lassen, bis der Callback bestaetigt hat (Ausblenden der alten Frames, dann Leeren).
    int bloecke = 0;
    while (core.flushAck() != serial && bloecke < 10) {
        auto aus = laufen(core, 480, {480});
        out.insert(out.end(), aus.begin(), aus.end());
        ++bloecke;
    }
    EXPECT_EQ(core.flushAck(), serial);
    EXPECT_EQ(bloecke, 1);                            // 441 Frames Rampe passen in einen Block von 480
    EXPECT_EQ(core.ring().available(), 0u);           // alter Inhalt weg
    for (int i = kRamp - 1; i < 480; ++i) ASSERT_EQ(out[2 * (2000 + i)], 0.0f) << i;      // nach 441 Frames stumm

    // Neue Spur (anderer Ton) sofort nach der Bestaetigung, wie der Feeder: wird eingeblendet.
    fuettern(core, sinus(100000, 8000, 880.0, 0.5f));
    auto neu = laufen(core, 2000, {480});
    out.insert(out.end(), neu.begin(), neu.end());
    std::size_t stelle = 0;
    EXPECT_LE(groessterSprung(out, &stelle), schritt + 0.01) << "Sprung bei Frame " << stelle;
    EXPECT_EQ(core.underflows(), 0u);
    const auto erwartet = sinus(100000, 2000, 880.0, 0.5f);
    for (int i = kRamp; i < 2000; ++i)   // danach ungedaempft
        ASSERT_EQ(out[2 * (2480 + i)], erwartet[static_cast<std::size_t>(2 * i)]) << i;
}

TEST(PlaybackCore, FlushImStillstandLeertSofort) {
    PlaybackCore core;
    fuettern(core, std::vector<float>(2 * 5000, 1.0f));
    const uint32_t serial = core.requestFlush();
    std::vector<float> block(2 * 128);
    core.process(block.data(), 128);
    EXPECT_EQ(core.flushAck(), serial);
    EXPECT_EQ(core.ring().available(), 0u);
}

TEST(PlaybackCore, FlushWaehrendPausierenFuehrtAusblendungZuEnde) {
    PlaybackCore core;
    fuettern(core, sinus(0, 10000, 440.0, 1.0f));
    core.setPlaying(true);
    auto out = laufen(core, 3000, {1024});
    core.setPlaying(false);
    const uint32_t serial = core.requestFlush();
    auto rest = laufen(core, 2000, {1024});
    out.insert(out.end(), rest.begin(), rest.end());
    EXPECT_EQ(core.flushAck(), serial);
    EXPECT_EQ(core.ring().available(), 0u);
    EXPECT_LE(groessterSprung(out), 2.0 * kPi * 440.0 / 44100.0 + 0.01);
}

// ============================== Eigenschaften ===================================================

TEST(PlaybackCore, AusgabeHaengtNichtVonDerBlockgroesseAb) {
    auto lauf = [](const std::vector<int32_t>& bloecke) {
        PlaybackCore core;
        fuettern(core, sinus(0, 12000, 440.0, 0.7f));
        core.setPlaying(true);
        auto out = laufen(core, 4000, bloecke);
        core.setPlaying(false);
        auto a = laufen(core, 1500, bloecke);
        out.insert(out.end(), a.begin(), a.end());
        core.setPlaying(true);
        auto b = laufen(core, 3000, bloecke);
        out.insert(out.end(), b.begin(), b.end());
        return out;
    };
    const auto referenz = lauf({1});
    for (const auto& bloecke : std::vector<std::vector<int32_t>>{{7}, {441}, {1024}, {192, 480, 64, 333}})
        ASSERT_EQ(lauf(bloecke), referenz);
}

TEST(PlaybackCore, KeineAllokationImCallback) {
#ifdef KLINGBILD_ASAN
    GTEST_SKIP() << "Allokationszaehler ist unter AddressSanitizer abgeschaltet";
#endif
    PlaybackCore core;
    SineFeeder feeder(core);
    std::vector<float> block(2 * 480);
    feeder.fill();   // schreibt ausserhalb der Messung (std::vector im Feeder)
    gAllokationen = 0;
    gZaehleAllokationen = true;
    for (int i = 0; i < 400; ++i) {
        if (i == 50) core.setPlaying(true);
        if (i == 150) core.setPlaying(false);
        if (i == 200) core.requestFlush();
        if (i == 250) core.setPlaying(true);
        core.process(block.data(), 480);   // enthaelt Rampen, Flush, Unterlauf (Ring laeuft leer)
        (void)core.underflows();
        (void)core.framesPlayed();
    }
    gZaehleAllokationen = false;
    EXPECT_EQ(gAllokationen.load(), 0);
    EXPECT_GT(core.underflows(), 0u);   // der Lauf hat den Unterlauf-Zweig wirklich durchlaufen
}

// ============================== SineFeeder ======================================================

TEST(SineFeeder, DurchgehenderSinusUeberChunkGrenzen) {
    PlaybackCore core;
    SineFeeder feeder(core, 440.0, 0.25f);
    core.setPlaying(true);
    std::vector<float> aus;
    std::vector<float> block(2 * 441);
    for (int i = 0; i < 400; ++i) {   // ~4 s: der Ring (1 s) wird mehrfach neu gefuellt
        feeder.fill();
        core.process(block.data(), 441);
        aus.insert(aus.end(), block.begin(), block.end());
    }
    EXPECT_EQ(core.underflows(), 0u);
    const double erlaubt = 2.0 * kPi * 440.0 / 44100.0 * 0.25 * 1.001;
    EXPECT_LE(groessterSprung(aus), erlaubt);   // keine Naht an den 512er-Chunk-Grenzen
    // Pegel: nach der Einblendung erreicht der Sinus seine Amplitude.
    float spitze = 0;
    for (std::size_t i = 2 * 1000; i < aus.size(); ++i) spitze = std::max(spitze, std::abs(aus[i]));
    EXPECT_NEAR(spitze, 0.25f, 1e-3f);
}

TEST(SineFeeder, SchreibtNichtSolangeFlushUnbestaetigtIst) {
    PlaybackCore core;
    SineFeeder feeder(core);
    EXPECT_GT(feeder.fill(), 0u);
    core.requestFlush();
    EXPECT_EQ(feeder.fill(), 0u);      // Callback hat noch nicht bestaetigt
    std::vector<float> block(2 * 128);
    core.process(block.data(), 128);   // bestaetigt und leert
    EXPECT_GT(feeder.fill(), 0u);
}

TEST(SineFeeder, ThreadUndEchtzeitCallbackOhneUnterlauf) {
    PlaybackCore core;
    SineFeeder feeder(core);
    feeder.start();
    std::this_thread::sleep_for(std::chrono::milliseconds(150));   // Ring fuellen lassen
    core.setPlaying(true);
    std::vector<float> block(2 * 441);
    auto naechster = std::chrono::steady_clock::now();
    for (int i = 0; i < 60; ++i) {   // 60 x 10 ms wie ein Oboe-Callback
        core.process(block.data(), 441);
        naechster += std::chrono::milliseconds(10);
        std::this_thread::sleep_until(naechster);
    }
    feeder.stop();
    EXPECT_EQ(core.underflows(), 0u);
    EXPECT_EQ(core.framesPlayed(), 60u * 441u);
}

// ============================== Denormals =======================================================

#if defined(__SSE__) || defined(_M_X64)
// Das Register gilt je Thread: der Test laeuft in einem eigenen Thread und laesst die anderen Tests unberuehrt.
TEST(Denormals, FlushToZeroGiltImAufrufenderThread) {
    volatile float denormal = 1e-39f;          // kleiner als die kleinste normale float-Zahl (~1,2e-38)
    volatile float halb = 0.5f;
    float vorher = -1.0f, nachher = -1.0f;
    std::thread t([&] {
        vorher = denormal * halb;              // ohne FTZ/DAZ: bleibt eine (denormale) Zahl > 0
        klangbild::enableFlushToZero();
        nachher = denormal * halb;             // mit FTZ/DAZ: 0
    });
    t.join();
    EXPECT_GT(vorher, 0.0f);
    EXPECT_EQ(nachher, 0.0f);
    EXPECT_GT(denormal * halb, 0.0f);          // dieser Thread ist unveraendert
}
#endif
