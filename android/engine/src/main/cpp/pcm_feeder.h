// PcmFeeder: die echte Quelle fuer den OutputRing (BAUPLAN-ANDROID §4.3, T2.2/T2.3).
//
// Liest den PCM-Cache (Kopf `KBPC`, int16 little endian, Stereo 44,1 kHz) ab einer
// Startposition und schreibt Block fuer Block in den Ring. Solange keine Datei offen ist,
// laeuft der Sinus aus dem Spike weiter (Diagnose-Seite).
//
// Regeln:
// - `fill()` laeuft im Feeder-Thread, nie im Audio-Callback (§0 Regel 4). Ein Mutex ist
//   darum erlaubt; er schuetzt nur Datei und Leseposition.
// - Nach `oeffne()` wird erst geschrieben, wenn der Callback den Flush bestaetigt hat
//   (`flushAck() == flushSerial()`). So kommt keine alte Spur in den neuen Abschnitt.
// - Fortschreitendes Schreiben des Decoders: die verfuegbaren Frames kommen aus der
//   Dateigroesse, nicht aus dem Kopf. Der Feeder liest nie ueber das Dateiende hinaus.
#pragma once

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include "playback_core.h"

namespace klangbild {

class PcmFeeder {
public:
    static constexpr uint32_t kKopfBytes = 16;
    static constexpr uint32_t kChunkFrames = 512;

    explicit PcmFeeder(PlaybackCore& core, double sineHz = 440.0, float sineAmplitude = 0.25f,
                       double sampleRate = 44100.0)
        : core_(core), step_(2.0 * kPi * sineHz / sampleRate), amplitude_(sineAmplitude) {
        buffer_.resize(static_cast<std::size_t>(kChunkFrames) * 2);
        roh_.resize(static_cast<std::size_t>(kChunkFrames) * 2);
    }

    ~PcmFeeder() {
        stop();
        schliesse();
    }

    PcmFeeder(const PcmFeeder&) = delete;
    PcmFeeder& operator=(const PcmFeeder&) = delete;

    /// Oeffnet eine PCM-Cache-Datei und setzt die Leseposition. Fordert einen Flush an, damit
    /// die alte Spur sauber ausblendet. `false` bei fehlender/ungueltiger Datei (alte Quelle bleibt).
    bool oeffne(const std::string& pfad, int64_t startFrame = 0, int64_t spur = 0) {
        std::FILE* neu = std::fopen(pfad.c_str(), "rb");
        if (neu == nullptr) return false;
        unsigned char kopf[kKopfBytes] = {};
        if (std::fread(kopf, 1, kKopfBytes, neu) != kKopfBytes || std::memcmp(kopf, "KBPC", 4) != 0) {
            std::fclose(neu);
            return false;
        }
        const uint16_t version = static_cast<uint16_t>(kopf[4] | (kopf[5] << 8));
        const uint16_t kanaele = static_cast<uint16_t>(kopf[6] | (kopf[7] << 8));
        if (version != 1 || kanaele != 2) {
            std::fclose(neu);
            return false;
        }

        core_.requestFlush();   // vor dem Tausch: der Callback wirft die alte Spur weg

        std::lock_guard<std::mutex> lock(mutex_);
        if (datei_ != nullptr) std::fclose(datei_);
        datei_ = neu;
        position_ = std::max<int64_t>(0, startFrame);
        spur_ = spur;
        fertig_ = false;
        phase_ = 0.0;
        return true;
    }

    /// Schliesst die Datei; danach spielt wieder der Sinus (Tests/Diagnose).
    void schliesse() {
        std::lock_guard<std::mutex> lock(mutex_);
        if (datei_ != nullptr) {
            std::fclose(datei_);
            datei_ = nullptr;
        }
        fertig_ = false;
    }

    /// Fuellt den Ring, solange Platz ist. Gibt die Zahl der geschriebenen Frames zurueck.
    uint32_t fill() {
        if (core_.flushAck() != core_.flushSerial()) return 0;
        std::lock_guard<std::mutex> lock(mutex_);
        if (datei_ == nullptr) return fillSinus();
        uint32_t total = 0;
        while (!fertig_ && core_.ring().writable() >= kChunkFrames) {
            const int64_t verfuegbar = gesamtFrames();
            const int64_t rest = verfuegbar - position_;
            if (rest <= 0) {
                fertig_ = true;
                break;
            }
            const uint32_t n = static_cast<uint32_t>(std::min<int64_t>(kChunkFrames, rest));
            if (!leseBlock(n)) {
                fertig_ = true;
                break;
            }
            const uint32_t geschrieben = core_.ring().write(buffer_.data(), n);
            position_ += geschrieben;
            total += geschrieben;
            if (geschrieben < n) break;
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

    int64_t position() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return position_;
    }
    int64_t spur() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return spur_;
    }
    bool fertig() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return fertig_;
    }
    bool offen() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return datei_ != nullptr;
    }

private:
    static constexpr double kPi = 3.14159265358979323846;

    uint32_t fillSinus() {
        uint32_t total = 0;
        while (core_.ring().writable() >= kChunkFrames) {
            for (uint32_t i = 0; i < kChunkFrames; ++i) {
                const float s = amplitude_ * static_cast<float>(std::sin(phase_));
                buffer_[2 * i] = s;
                buffer_[2 * i + 1] = s;
                phase_ += step_;
                if (phase_ >= 2.0 * kPi) phase_ -= 2.0 * kPi;
            }
            total += core_.ring().write(buffer_.data(), kChunkFrames);
        }
        return total;
    }

    /// Frames, die in der Datei stehen (Kopf 16 Byte, danach 4 Byte je Frame).
    int64_t gesamtFrames() const {
        std::FILE* datei = datei_;
        if (datei == nullptr) return 0;
        const long alt = std::ftell(datei);
        if (alt < 0) return 0;
        if (std::fseek(datei, 0, SEEK_END) != 0) return 0;
        const long groesse = std::ftell(datei);
        if (std::fseek(datei, alt, SEEK_SET) != 0) return 0;
        if (groesse < static_cast<long>(kKopfBytes)) return 0;
        return (groesse - static_cast<long>(kKopfBytes)) / 4;
    }

    bool leseBlock(uint32_t n) {
        const long offset = static_cast<long>(kKopfBytes) + static_cast<long>(position_) * 4;
        if (std::fseek(datei_, offset, SEEK_SET) != 0) return false;
        const std::size_t bytes = static_cast<std::size_t>(n) * 4;
        if (std::fread(roh_.data(), 1, bytes, datei_) != bytes) return false;
        for (uint32_t i = 0; i < n * 2; ++i) buffer_[i] = static_cast<float>(roh_[i]) / 32767.0f;
        return true;
    }

    PlaybackCore& core_;
    double step_;
    float amplitude_;
    double phase_ = 0.0;

    mutable std::mutex mutex_;
    std::FILE* datei_ = nullptr;
    int64_t position_ = 0;
    int64_t spur_ = 0;
    bool fertig_ = false;

    std::vector<float> buffer_;
    std::vector<int16_t> roh_;
    std::atomic<bool> running_{false};
    std::thread thread_;
};

}  // namespace klangbild
