// OboeOutput: der Oboe-Stream, der PlaybackCore::process() im Audio-Callback aufruft
// (BAUPLAN-ANDROID §5.3, T1.1). Die Logik steckt in PlaybackCore; diese Klasse
// verdrahtet nur Oboe.
//
// Stream: Output, PowerSaving, Shared, Float, 2 Kanaele, 44 100 Hz,
// Resampler-Qualitaet Medium, Usage Media, ContentType Music (ADR-016).
//
// Fehler-Callback, Neustart und Bluetooth folgen mit T1.3.
//
// Nur auf Android gebaut (Oboe). Der Host-Test prueft PlaybackCore direkt.
#pragma once

#include <memory>

#include <oboe/Oboe.h>

#include "playback_core.h"

namespace klangbild {

class OboeOutput : public oboe::AudioStreamDataCallback, public std::enable_shared_from_this<OboeOutput> {
public:
    /// `core` muss laenger leben als der Stream (stop() vor dem Zerstoeren des Kerns).
    explicit OboeOutput(PlaybackCore& core) : core_(core) {}

    /// Oeffnet und startet den Stream. false, wenn Oeffnen oder Starten scheitert.
    /// Muss auf einem `std::shared_ptr<OboeOutput>` aufgerufen werden (Oboe haelt den Callback).
    bool start();

    /// Stoppt, schliesst und gibt den Stream frei. Danach ist der Callback sicher nicht mehr aktiv.
    void stop();

    bool running() const { return stream_ != nullptr; }

    // Audio-Callback (hoechste Prioritaet): nichts ausser PlaybackCore::process (§0 Regel 4).
    oboe::DataCallbackResult onAudioReady(oboe::AudioStream* stream, void* audioData, int32_t numFrames) override;

private:
    PlaybackCore& core_;
    std::shared_ptr<oboe::AudioStream> stream_;
};

}  // namespace klangbild
