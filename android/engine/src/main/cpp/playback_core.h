// PlaybackCore: die Logik des Oboe-Callbacks (BAUPLAN-ANDROID §5.3, T1.1/T1.2).
//
// Diese Klasse kennt Oboe nicht. `process()` ist der Rumpf von `onAudioReady` und
// laeuft darum auch im Host-Test. Im Callback gilt (§0 Regel 4): kein new/malloc,
// kein Lock, kein Datei-I/O, kein Log, kein JNI, keine Exception. Hier kommen nur
// Atomics, Kopieren und Rechnen vor.
//
// Ablauf je Block:
//   1. Wurde ein Flush verlangt (play/seek)? Dann erst die noch im Ring liegenden
//      alten Frames in 10 ms ausblenden, danach den Ring leeren (kein Knacken).
//   2. Spielt die Wiedergabe nicht, wird in 10 ms ausgeblendet und dann Stille
//      geliefert. Beim Weiterspielen wird in 10 ms eingeblendet.
//   3. Sonst kopiert der Callback hoechstens `frames` Frames aus dem Ring. Fehlen
//      welche, wird mit Stille aufgefuellt und `underflows` um 1 erhoeht.
//
// Flush-Handshake fuer den Feeder: Der Feeder schreibt erst, wenn
// `flushAck() == flushSerial()`. Offen fuer T2.3: Schreibt der Feeder genau waehrend
// des Flushs noch ein Stueck der alten Spur, bleibt es im Ring. Das loest die
// Timeline (Zustellung erst nach Bestaetigung), nicht dieser Spike.
#pragma once

#include <atomic>
#include <algorithm>
#include <cstdint>

#include "output_ring.h"

namespace klangbild {

class PlaybackCore {
public:
    /// Laenge von Ein- und Ausblendung: 10 ms bei 44 100 Hz.
    static constexpr int32_t kRampFrames = 441;

    static_assert(std::atomic<uint32_t>::is_always_lock_free, "uint32_t-Atomics muessen sperrfrei sein");
    static_assert(std::atomic<bool>::is_always_lock_free, "bool-Atomics muessen sperrfrei sein");

    OutputRing& ring() noexcept { return ring_; }

    // --- Steuerung (von Kotlin/Feeder, nie aus dem Callback) --------------------------------
    void setPlaying(bool playing) noexcept { playing_.store(playing, std::memory_order_release); }
    bool playing() const noexcept { return playing_.load(std::memory_order_acquire); }

    /// play/seek: Der Callback verwirft den Ring. Gibt die neue Seriennummer zurueck.
    uint32_t requestFlush() noexcept { return flushSerial_.fetch_add(1, std::memory_order_acq_rel) + 1; }
    uint32_t flushSerial() const noexcept { return flushSerial_.load(std::memory_order_acquire); }
    /// Letzte Seriennummer, die der Callback erledigt hat. Gleich `flushSerial()` heisst: Ring ist leer.
    uint32_t flushAck() const noexcept { return flushAck_.load(std::memory_order_acquire); }

    // --- Zaehler (lesbar von ueberall) ------------------------------------------------------
    /// Luecken bei laufender Wiedergabe (wie `underflows` im Desktop).
    uint32_t underflows() const noexcept { return underflows_.load(std::memory_order_relaxed); }
    /// Aus dem Ring gelesene Frames (inklusive der 10-ms-Rampen).
    uint64_t framesPlayed() const noexcept { return framesPlayed_.load(std::memory_order_acquire); }

    // --- Callback ---------------------------------------------------------------------------
    /// Rumpf von `onAudioReady`: fuellt `out` mit `frames` Stereo-Frames (immer vollstaendig).
    void process(float* out, int32_t frames) noexcept {
        if (frames <= 0) return;
        const uint32_t want = flushSerial_.load(std::memory_order_acquire);
        const bool playing = playing_.load(std::memory_order_acquire);

        if (want != seen_ && !flushing_) {
            if (rampPos_ > 0) {
                flushing_ = true;   // alte Frames liegen noch im Ring: erst ausblenden
            } else {
                finishFlush(want);  // schon stumm: sofort leeren
            }
        }

        const bool wantSound = playing && !flushing_;
        const uint32_t n = static_cast<uint32_t>(frames);
        // Beim Ausblenden nur so viele Frames verbrauchen, wie die Rampe noch braucht. Sonst gingen je
        // nach Blockgroesse bis zu `frames` Frames Audio verloren und die Position nach dem Weiterspielen
        // haenge von der Blockgroesse ab.
        const uint32_t toRead = wantSound ? n : std::min<uint32_t>(n, static_cast<uint32_t>(rampPos_));
        uint32_t got = 0;
        if (toRead > 0) got = ring_.read(out, toRead);
        if (got < n) std::fill(out + 2 * static_cast<std::size_t>(got), out + 2 * static_cast<std::size_t>(n), 0.0f);
        if (wantSound && got < n) underflows_.fetch_add(1, std::memory_order_relaxed);

        applyRamp(out, frames, wantSound, static_cast<int32_t>(got));

        if (got > 0) framesPlayed_.fetch_add(got, std::memory_order_release);
        if (flushing_ && rampPos_ == 0) finishFlush(want);
    }

private:
    /// Verstellt die Verstaerkung je Frame um 1/441 in Richtung Ziel (0 oder 1).
    /// Ganzzahliger Zaehler, damit 0 und 1 nach genau 441 Frames exakt erreicht sind.
    /// Hochgezaehlt wird nur ueber Frames mit echtem Audio (`withData` von `frames`): Sonst waere die
    /// Rampe bei einer Luecke schon oben und das Audio danach finge ohne Einblendung an. Nach einer
    /// Luecke (Ring leer bei laufender Wiedergabe) beginnt die Einblendung darum neu.
    void applyRamp(float* out, int32_t frames, bool up, int32_t withData) noexcept {
        constexpr float kInv = 1.0f / static_cast<float>(kRampFrames);
        for (int32_t i = 0; i < frames; ++i) {
            if (up) {
                if (i < withData && rampPos_ < kRampFrames) ++rampPos_;
            } else if (rampPos_ > 0) {
                --rampPos_;
            }
            const float g = rampPos_ == kRampFrames ? 1.0f : static_cast<float>(rampPos_) * kInv;
            out[2 * i] *= g;
            out[2 * i + 1] *= g;
        }
        if (up && withData < frames) rampPos_ = 0;   // Luecke: danach wieder von 0 einblenden
    }

    void finishFlush(uint32_t serial) noexcept {
        ring_.discardAll();
        seen_ = serial;
        flushing_ = false;
        flushAck_.store(serial, std::memory_order_release);
    }

    OutputRing ring_;
    std::atomic<bool> playing_{false};
    std::atomic<uint32_t> flushSerial_{0};
    std::atomic<uint32_t> flushAck_{0};
    std::atomic<uint32_t> underflows_{0};
    std::atomic<uint64_t> framesPlayed_{0};

    // Nur vom Callback-Thread benutzt:
    uint32_t seen_ = 0;
    bool flushing_ = false;
    int32_t rampPos_ = 0;   // 0 = stumm, kRampFrames = volle Lautstaerke
};

}  // namespace klangbild
