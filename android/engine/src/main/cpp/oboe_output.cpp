#include "oboe_output.h"

#include "denormals.h"

#ifdef __ANDROID__
#include <android/log.h>
#define KLANGBILD_LOGE(...) __android_log_print(ANDROID_LOG_ERROR, "klangbild", __VA_ARGS__)
#else
#define KLANGBILD_LOGE(...) ((void)0)
#endif

namespace klangbild {

bool OboeOutput::start() {
    if (stream_) return true;

    oboe::AudioStreamBuilder builder;
    builder.setDirection(oboe::Direction::Output)
        ->setPerformanceMode(oboe::PerformanceMode::PowerSaving)
        ->setSharingMode(oboe::SharingMode::Shared)
        ->setFormat(oboe::AudioFormat::Float)
        ->setChannelCount(2)
        ->setSampleRate(44100)
        ->setSampleRateConversionQuality(oboe::SampleRateConversionQuality::Medium)
        ->setUsage(oboe::Usage::Media)
        ->setContentType(oboe::ContentType::Music)
        ->setDataCallback(shared_from_this());

    oboe::Result result = builder.openStream(stream_);
    if (result != oboe::Result::OK) {
        KLANGBILD_LOGE("Stream oeffnen fehlgeschlagen: %s", oboe::convertToText(result));
        stream_.reset();
        return false;
    }
    result = stream_->requestStart();
    if (result != oboe::Result::OK) {
        KLANGBILD_LOGE("Stream starten fehlgeschlagen: %s", oboe::convertToText(result));
        stream_->close();
        stream_.reset();
        return false;
    }
    return true;
}

void OboeOutput::stop() {
    if (!stream_) return;
    stream_->requestStop();
    stream_->close();   // wartet, bis kein Callback mehr laeuft
    stream_.reset();    // gibt auch die Callback-Referenz frei
}

oboe::DataCallbackResult OboeOutput::onAudioReady(oboe::AudioStream* /*stream*/, void* audioData,
                                                  int32_t numFrames) {
    // Das Fliesskomma-Register gilt je Thread. Der Callback-Thread kann nach einem Neustart wechseln,
    // darum je Thread einmal (thread_local ohne Konstruktor: keine Allokation).
    thread_local bool ftzGesetzt = false;
    if (!ftzGesetzt) {
        enableFlushToZero();
        ftzGesetzt = true;
    }
    core_.process(static_cast<float*>(audioData), numFrames);
    return oboe::DataCallbackResult::Continue;
}

}  // namespace klangbild
