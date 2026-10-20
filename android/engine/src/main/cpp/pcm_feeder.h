// PcmFeeder: die echte Quelle fuer den OutputRing (BAUPLAN-ANDROID §4.3, T2.2/T2.3).
//
// Liest den PCM-Cache (Kopf `KBPC`, int16 little endian, Stereo 44,1 kHz) ab einer
// Startposition und schreibt Block fuer Block in den Ring. Ist eine zweite Datei gesetzt,
// laeuft sie am Ende der ersten ohne Luecke und ohne Flush weiter (Uebergang: A-Rest,
// gebackene Blende, B-Rest als drei Dateien). Solange keine Datei offen ist, laeuft der
// Sinus aus dem Spike weiter (Diagnose-Seite).
//
// Regeln:
// - `fill()` laeuft im Feeder-Thread, nie im Audio-Callback (§0 Regel 4). Ein Mutex ist
//   darum erlaubt; er schuetzt nur Dateien und Lesepositionen.
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
    /// die alte Spur sauber ausblendet. `wachsend`: die Datei wird noch geschrieben; am
    /// vorlaeufigen Ende wird nicht abgeschlossen, sondern gewartet (fortschreitendes Dekodieren).
    /// `false` bei fehlender/ungueltiger Datei (alte Quelle bleibt).
    bool oeffne(const std::string& pfad, int64_t startFrame = 0, int64_t spur = 0, bool wachsend = false) {
        Quelle neu;
        if (!oeffneQuelle(neu, pfad, startFrame, spur)) return false;
        core_.requestFlush();   // vor dem Tausch: der Callback wirft die alte Spur weg
        std::lock_guard<std::mutex> lock(mutex_);
        schliesseQuelle(aktuell_);
        schliesseQuelle(naechste_);
        aktuell_ = neu;
        hatNaechste_ = false;
        fertig_ = false;
        wachsend_ = wachsend;
        phase_ = 0.0;
        return true;
    }

    /// Meldet, dass die wachsende Datei fertig geschrieben ist (Ende erreicht).
    void quelleFertig() {
        std::lock_guard<std::mutex> lock(mutex_);
        wachsend_ = false;
    }

    /// Haengt eine Datei an, die ab `abFrame` der aktuellen (oder am Dateiende, wenn `abFrame` < 0)
    /// ohne Luecke und ohne Flush beginnt. `abFrame` ist die Position in der aktuellen Datei.
    /// `false` bei ungueltiger Datei; die Warteschlange bleibt dann leer.
    bool setzeNaechste(const std::string& pfad, int64_t startFrame = 0, int64_t spur = 0, int64_t abFrame = -1) {
        Quelle neu;
        if (!oeffneQuelle(neu, pfad, startFrame, spur)) return false;
        std::lock_guard<std::mutex> lock(mutex_);
        schliesseQuelle(naechste_);
        naechste_ = neu;
        hatNaechste_ = true;
        naechsteAb_ = abFrame;
        return true;
    }

    /// Schliesst beide Dateien; danach spielt wieder der Sinus (Tests/Diagnose).
    void schliesse() {
        std::lock_guard<std::mutex> lock(mutex_);
        schliesseQuelle(aktuell_);
        schliesseQuelle(naechste_);
        hatNaechste_ = false;
        fertig_ = false;
    }

    /// Fuellt den Ring, solange Platz ist. Gibt die Zahl der geschriebenen Frames zurueck.
    uint32_t fill() {
        if (core_.flushAck() != core_.flushSerial()) return 0;
        std::lock_guard<std::mutex> lock(mutex_);
        if (aktuell_.datei == nullptr) return fillSinus();
        uint32_t total = 0;
        while (!fertig_ && core_.ring().writable() >= kChunkFrames) {
            if (aktuell_.datei == nullptr) {
                fertig_ = true;
                break;
            }
            if (hatNaechste_ && naechsteAb_ >= 0 && aktuell_.position >= naechsteAb_) {
                wechsle();
                continue;
            }
            const int64_t verfuegbar = gesamtFrames(aktuell_.datei);
            const int64_t rest = verfuegbar - aktuell_.position;
            if (rest <= 0) {
                if (hatNaechste_) {
                    wechsle();
                    continue;
                }
                if (wachsend_) break;   // Datei waechst noch: spaeter weiterfuellen
                fertig_ = true;
                break;
            }
            int64_t grenze = std::min<int64_t>(rest, kChunkFrames);
            if (hatNaechste_ && naechsteAb_ >= 0) {
                grenze = std::min<int64_t>(grenze, naechsteAb_ - aktuell_.position);
            }
            if (grenze <= 0) continue;
            const uint32_t n = static_cast<uint32_t>(grenze);
            if (!leseBlock(aktuell_, n)) {
                fertig_ = true;
                break;
            }
            const uint32_t geschrieben = core_.ring().write(buffer_.data(), n);
            aktuell_.position += geschrieben;
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
        return aktuell_.position;
    }
    int64_t spur() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return aktuell_.spur;
    }
    bool fertig() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return fertig_;
    }
    bool offen() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return aktuell_.datei != nullptr;
    }
    bool naechsteGesetzt() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return hatNaechste_;
    }

private:
    static constexpr double kPi = 3.14159265358979323846;

    struct Quelle {
        std::FILE* datei = nullptr;
        int64_t position = 0;
        int64_t spur = 0;
    };

    void wechsle() {
        schliesseQuelle(aktuell_);
        aktuell_ = naechste_;
        naechste_ = Quelle{};
        hatNaechste_ = false;
        naechsteAb_ = -1;
    }

    static void schliesseQuelle(Quelle& quelle) {
        if (quelle.datei != nullptr) {
            std::fclose(quelle.datei);
            quelle.datei = nullptr;
        }
    }

    /// Oeffnet und prueft eine Cache-Datei, ohne den Zustand des Feeders anzutasten.
    static bool oeffneQuelle(Quelle& ziel, const std::string& pfad, int64_t startFrame, int64_t spur) {
        std::FILE* datei = std::fopen(pfad.c_str(), "rb");
        if (datei == nullptr) return false;
        unsigned char kopf[kKopfBytes] = {};
        if (std::fread(kopf, 1, kKopfBytes, datei) != kKopfBytes || std::memcmp(kopf, "KBPC", 4) != 0) {
            std::fclose(datei);
            return false;
        }
        const uint16_t version = static_cast<uint16_t>(kopf[4] | (kopf[5] << 8));
        const uint16_t kanaele = static_cast<uint16_t>(kopf[6] | (kopf[7] << 8));
        if (version != 1 || kanaele != 2) {
            std::fclose(datei);
            return false;
        }
        ziel.datei = datei;
        ziel.position = std::max<int64_t>(0, startFrame);
        ziel.spur = spur;
        return true;
    }

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
    static int64_t gesamtFrames(std::FILE* datei) {
        const long alt = std::ftell(datei);
        if (alt < 0) return 0;
        if (std::fseek(datei, 0, SEEK_END) != 0) return 0;
        const long groesse = std::ftell(datei);
        if (std::fseek(datei, alt, SEEK_SET) != 0) return 0;
        if (groesse < static_cast<long>(kKopfBytes)) return 0;
        return (groesse - static_cast<long>(kKopfBytes)) / 4;
    }

    bool leseBlock(Quelle& quelle, uint32_t n) {
        const long offset = static_cast<long>(kKopfBytes) + static_cast<long>(quelle.position) * 4;
        if (std::fseek(quelle.datei, offset, SEEK_SET) != 0) return false;
        const std::size_t bytes = static_cast<std::size_t>(n) * 4;
        if (std::fread(roh_.data(), 1, bytes, quelle.datei) != bytes) return false;
        for (uint32_t i = 0; i < n * 2; ++i) buffer_[i] = static_cast<float>(roh_[i]) / 32767.0f;
        return true;
    }

    PlaybackCore& core_;
    double step_;
    float amplitude_;
    double phase_ = 0.0;

    mutable std::mutex mutex_;
    Quelle aktuell_;
    Quelle naechste_;
    bool hatNaechste_ = false;
    int64_t naechsteAb_ = -1;
    bool wachsend_ = false;
    bool fertig_ = false;

    std::vector<float> buffer_;
    std::vector<int16_t> roh_;
    std::atomic<bool> running_{false};
    std::thread thread_;
};

}  // namespace klangbild
