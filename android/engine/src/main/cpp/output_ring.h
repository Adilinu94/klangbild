// OutputRing: lockfreier Ringpuffer zwischen Feeder und Audio-Callback
// (BAUPLAN-ANDROID §5.3).
//
// - SPSC: genau ein Schreiber (Feeder-Thread) und genau ein Leser (Callback).
// - Stereo, float, interleaved (L,R,L,R,...).
// - Kapazitaet 44 100 Frames (1 s); der Speicher ist eine Zweierpotenz
//   (65 536 Frames), damit die Indizes mit einer Maske umlaufen.
// - Indizes sind `std::atomic<uint64_t>` mit acquire/release. Zaehlt man ab 0 mit
//   44 100 Frames je Sekunde, laeuft ein uint64_t in Jahrtausenden nicht ueber.
// - Der Speicher wird im Konstruktor angelegt (nicht im Callback).
//
// Erlaubt im Callback: read(), discardAll(). Alles ist `noexcept`, ohne Sperre,
// ohne Allokation (BAUPLAN §0 Regel 4).
#pragma once

#include <algorithm>
#include <atomic>
#include <cstdint>
#include <cstring>
#include <memory>

namespace klangbild {

class OutputRing {
public:
    static constexpr uint32_t kChannels = 2;
    static constexpr uint32_t kStorageFrames = 65536;   // Zweierpotenz
    static constexpr uint32_t kCapacityFrames = 44100;  // logische Fuellgrenze (1 s)
    static_assert((kStorageFrames & (kStorageFrames - 1)) == 0, "Speicher muss eine Zweierpotenz sein");
    static_assert(kCapacityFrames <= kStorageFrames, "Kapazitaet passt nicht in den Speicher");
    static_assert(std::atomic<uint64_t>::is_always_lock_free, "uint64_t-Atomics muessen sperrfrei sein");

    OutputRing() : data_(new float[static_cast<std::size_t>(kStorageFrames) * kChannels]()) {}

    OutputRing(const OutputRing&) = delete;
    OutputRing& operator=(const OutputRing&) = delete;

    /// Nur Schreiber (Feeder): haengt bis zu `frames` Frames an, gibt die Anzahl zurueck.
    /// Schreibt nie ueber die Kapazitaet hinaus; bei vollem Ring 0.
    uint32_t write(const float* in, uint32_t frames) noexcept {
        const uint64_t w = write_.load(std::memory_order_relaxed);
        const uint64_t r = read_.load(std::memory_order_acquire);
        const uint64_t fill = w - r;
        const uint32_t free = fill >= kCapacityFrames ? 0u : kCapacityFrames - static_cast<uint32_t>(fill);
        const uint32_t n = std::min(frames, free);
        if (n == 0) return 0;
        const uint32_t start = static_cast<uint32_t>(w & kMask);
        const uint32_t first = std::min(n, kStorageFrames - start);
        std::memcpy(data_.get() + static_cast<std::size_t>(start) * kChannels, in,
                    static_cast<std::size_t>(first) * kChannels * sizeof(float));
        if (n > first) {
            std::memcpy(data_.get(), in + static_cast<std::size_t>(first) * kChannels,
                        static_cast<std::size_t>(n - first) * kChannels * sizeof(float));
        }
        write_.store(w + n, std::memory_order_release);
        return n;
    }

    /// Nur Leser (Callback): kopiert hoechstens `frames` Frames, gibt die Anzahl zurueck.
    uint32_t read(float* out, uint32_t frames) noexcept {
        const uint64_t r = read_.load(std::memory_order_relaxed);
        const uint64_t w = write_.load(std::memory_order_acquire);
        const uint32_t n = static_cast<uint32_t>(std::min<uint64_t>(frames, w - r));
        if (n == 0) return 0;
        const uint32_t start = static_cast<uint32_t>(r & kMask);
        const uint32_t first = std::min(n, kStorageFrames - start);
        std::memcpy(out, data_.get() + static_cast<std::size_t>(start) * kChannels,
                    static_cast<std::size_t>(first) * kChannels * sizeof(float));
        if (n > first) {
            std::memcpy(out + static_cast<std::size_t>(first) * kChannels, data_.get(),
                        static_cast<std::size_t>(n - first) * kChannels * sizeof(float));
        }
        read_.store(r + n, std::memory_order_release);
        return n;
    }

    /// Nur Leser (Callback): verwirft alles, was bis jetzt geschrieben wurde.
    void discardAll() noexcept {
        read_.store(write_.load(std::memory_order_acquire), std::memory_order_release);
    }

    /// Frames, die jetzt lesbar sind (von beiden Seiten aufrufbar; nur eine Momentaufnahme).
    uint32_t available() const noexcept {
        const uint64_t r = read_.load(std::memory_order_acquire);
        const uint64_t w = write_.load(std::memory_order_acquire);
        return static_cast<uint32_t>(w - r);
    }

    /// Frames, die der Schreiber jetzt noch anhaengen darf (Momentaufnahme).
    uint32_t writable() const noexcept { return kCapacityFrames - std::min(available(), kCapacityFrames); }

private:
    static constexpr uint64_t kMask = kStorageFrames - 1;

    std::unique_ptr<float[]> data_;
    // Auf getrennten Cache-Zeilen, damit Schreiber und Leser sich nicht gegenseitig ausbremsen.
    alignas(64) std::atomic<uint64_t> write_{0};
    alignas(64) std::atomic<uint64_t> read_{0};
};

}  // namespace klangbild
