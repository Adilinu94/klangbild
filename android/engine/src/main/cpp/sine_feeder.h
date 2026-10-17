// SineFeeder: Testquelle fuer den Engine-Spike (BAUPLAN-ANDROID T1.1: "Sinus 440 Hz
// aus dem Feeder"). Schreibt einen durchgehenden Sinus in den OutputRing.
// Wird vom echten Feeder (Timeline, M2) abgeloest.
//
// `fill()` ist die einzelne, deterministische Fuellung (testbar ohne Thread);
// `start()`/`stop()` machen daraus einen Thread. Laeuft nie im Audio-Callback.
#pragma once

#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <thread>
#include <vector>

#include "playback_core.h"

namespace klangbild {

class SineFeeder {
public:
    explicit SineFeeder(PlaybackCore& core, double hz = 440.0, float amplitude = 0.25f, double sampleRate = 44100.0)
        : core_(core), step_(2.0 * 3.14159265358979323846 * hz / sampleRate), amplitude_(amplitude) {
        buffer_.resize(static_cast<std::size_t>(kChunkFrames) * 2);
    }
    ~SineFeeder() { stop(); }

    SineFeeder(const SineFeeder&) = delete;
    SineFeeder& operator=(const SineFeeder&) = delete;

    /// Fuellt den Ring, solange Platz ist und der Callback den letzten Flush bestaetigt hat.
    /// Gibt die Zahl der geschriebenen Frames zurueck.
    uint32_t fill() {
        if (core_.flushAck() != core_.flushSerial()) return 0;
        uint32_t total = 0;
        while (core_.ring().writable() >= kChunkFrames) {
            for (uint32_t i = 0; i < kChunkFrames; ++i) {
                const float s = amplitude_ * static_cast<float>(std::sin(phase_));
                buffer_[2 * i] = s;
                buffer_[2 * i + 1] = s;
                phase_ += step_;
                if (phase_ >= 2.0 * 3.14159265358979323846) phase_ -= 2.0 * 3.14159265358979323846;
            }
            total += core_.ring().write(buffer_.data(), kChunkFrames);
        }
        return total;
    }

    void start() {
        if (running_.exchange(true)) return;
        thread_ = std::thread([this] {
            while (running_.load(std::memory_order_acquire)) {
                fill();
                std::this_thread::sleep_for(std::chrono::milliseconds(5));
            }
        });
    }

    void stop() {
        if (!running_.exchange(false)) return;
        if (thread_.joinable()) thread_.join();
    }

private:
    static constexpr uint32_t kChunkFrames = 512;

    PlaybackCore& core_;
    double step_;
    float amplitude_;
    double phase_ = 0.0;
    std::vector<float> buffer_;
    std::atomic<bool> running_{false};
    std::thread thread_;
};

}  // namespace klangbild
