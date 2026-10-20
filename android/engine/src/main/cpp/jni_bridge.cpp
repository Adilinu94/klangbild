// JNI-Fassade des nativen Kerns (BAUPLAN §5.11).
//
// Diese Datei ist die **einzige** Stelle mit JNI. Regeln:
// - JNI-Aufrufe nie aus dem Oboe-Callback.
// - Handles sind `jlong` (Zeiger in eine Tabelle, nicht roh); jedes open/create
//   hat ein release.
// - Keine Exception über die JNI-Grenze werfen: Fehler kommen als Rückgabewert.
//
// M1-Spike: start/stop/setPlaying/poll fuer den Oboe-Stream mit der Sinus-Testquelle.
// Der PCM-Cache (T2.2) und alles Weitere erweitern dieselbe Datei.
#include <jni.h>

#include <cstddef>
#include <memory>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>

#include "bake_api.h"
#include "json.h"
#include "oboe_output.h"
#include "pcm_feeder.h"
#include "playback_core.h"

namespace {

// Version der nativen Schnittstelle. Steigt, wenn sich das Vertrag zwischen
// Kotlin und C++ ändert (andernfalls bleibt die App bei alter .so stillstehen).
// 2: start/stop/setPlaying/poll (M1).
// 3: Bäcker (M8b).
// 4: startFile und belegte Feeder-Felder in poll (M2).
// 5: queueFile (nahtlose Folgedatei).
// 6: queueFile mit geplantem Wechsel ab Frame.
// 7: Vorschau auf einem zweiten Stream.
// 8: startFile mit wachsender Datei und quelleFertig.
constexpr int kAbiVersion = 8;

// Anzahl der Felder von poll() (BAUPLAN §5.4); steht gleich in NativeEngine.POLL_SIZE.
constexpr jsize kPollSize = 7;

// Der Spike hat genau eine Engine. Die Steuerung laeuft ueber diese Sperre; der Audio-Callback
// kommt nie hier vorbei (§0 Regel 4).
struct Engine {
    klangbild::PlaybackCore core;
    klangbild::PcmFeeder feeder{core};
    std::shared_ptr<klangbild::OboeOutput> output;
};

std::mutex gMutex;
std::unique_ptr<Engine> gEngine;

// Gebackene Uebergaenge: Handle -> Ergebnis. Kotlin holt Audio und Info ab und gibt das
// Handle wieder frei (jedes bake hat ein releaseBake).
std::unordered_map<jlong, klangbild::BakeErgebnis> gBakes;
jlong gNaechsteBake = 1;

void stopLocked() {
    if (!gEngine) return;
    if (gEngine->output) gEngine->output->stop();   // Stream zu, bevor der Kern zerstoert wird
    gEngine->feeder.stop();
    gEngine.reset();
}

}  // namespace

extern "C" JNIEXPORT jint JNICALL
Java_de_klangbild_engine_NativeEngine_aboVersion(JNIEnv* /*env*/, jclass /*typ*/) {
    return static_cast<jint>(kAbiVersion);
}

extern "C" JNIEXPORT jboolean JNICALL
Java_de_klangbild_engine_NativeEngine_start(JNIEnv* /*env*/, jclass /*typ*/) {
    std::lock_guard<std::mutex> lock(gMutex);
    if (gEngine) return JNI_TRUE;
    auto engine = std::make_unique<Engine>();
    engine->output = std::make_shared<klangbild::OboeOutput>(engine->core);
    engine->feeder.fill();   // Ring vorfuellen, bevor der Stream laeuft
    if (!engine->output->start()) return JNI_FALSE;
    engine->feeder.start();
    gEngine = std::move(engine);
    return JNI_TRUE;
}

extern "C" JNIEXPORT void JNICALL
Java_de_klangbild_engine_NativeEngine_stop(JNIEnv* /*env*/, jclass /*typ*/) {
    std::lock_guard<std::mutex> lock(gMutex);
    stopLocked();
}

extern "C" JNIEXPORT void JNICALL
Java_de_klangbild_engine_NativeEngine_setPlaying(JNIEnv* /*env*/, jclass /*typ*/, jboolean playing) {
    std::lock_guard<std::mutex> lock(gMutex);
    if (gEngine) gEngine->core.setPlaying(playing == JNI_TRUE);
}

// Spielt eine PCM-Cache-Datei ab `startFrame` (M2). Startet den Stream beim ersten Aufruf.
// `spur` ist die Kennung fuer poll(); `wachsend` sagt, dass die Datei noch dekodiert wird.
extern "C" JNIEXPORT jboolean JNICALL
Java_de_klangbild_engine_NativeEngine_startFile(JNIEnv* env, jclass /*typ*/, jstring pfad, jlong startFrame,
                                                jlong spur, jboolean wachsend) {
    if (pfad == nullptr) return JNI_FALSE;
    const char* text = env->GetStringUTFChars(pfad, nullptr);
    const std::string pfadText = text != nullptr ? std::string(text) : std::string();
    if (text != nullptr) env->ReleaseStringUTFChars(pfad, text);
    if (pfadText.empty()) return JNI_FALSE;

    std::lock_guard<std::mutex> lock(gMutex);
    if (!gEngine) {
        auto engine = std::make_unique<Engine>();
        engine->output = std::make_shared<klangbild::OboeOutput>(engine->core);
        if (!engine->output->start()) return JNI_FALSE;
        gEngine = std::move(engine);
    }
    if (!gEngine->feeder.oeffne(pfadText, startFrame, spur, wachsend == JNI_TRUE)) return JNI_FALSE;
    gEngine->core.setPlaying(true);
    gEngine->feeder.start();
    return JNI_TRUE;
}

// Meldet, dass die wachsende Datei zu Ende geschrieben ist (der Feeder darf abschliessen).
extern "C" JNIEXPORT void JNICALL
Java_de_klangbild_engine_NativeEngine_quelleFertig(JNIEnv* /*env*/, jclass /*typ*/) {
    std::lock_guard<std::mutex> lock(gMutex);
    if (gEngine) gEngine->feeder.quelleFertig();
}

// Haengt eine Datei an, die ab `abFrame` der aktuellen (oder am Dateiende, wenn negativ) nahtlos
// beginnt. Kein Flush: der Ring laeuft weiter. Fuer die Uebergangskette A-Rest -> Blende -> B-Rest.
extern "C" JNIEXPORT jboolean JNICALL
Java_de_klangbild_engine_NativeEngine_queueFile(JNIEnv* env, jclass /*typ*/, jstring pfad, jlong startFrame,
                                                jlong spur, jlong abFrame) {
    if (pfad == nullptr) return JNI_FALSE;
    const char* text = env->GetStringUTFChars(pfad, nullptr);
    const std::string pfadText = text != nullptr ? std::string(text) : std::string();
    if (text != nullptr) env->ReleaseStringUTFChars(pfad, text);
    if (pfadText.empty()) return JNI_FALSE;

    std::lock_guard<std::mutex> lock(gMutex);
    if (!gEngine) return JNI_FALSE;
    return gEngine->feeder.setzeNaechste(pfadText, startFrame, spur, abFrame) ? JNI_TRUE : JNI_FALSE;
}

// Felder wie BAUPLAN §5.4. Belegt: [1] Frames, die der Callback gelesen hat, [2] Spur des
// Feeders, [3] Leseposition des Feeders, [4] playing, [5] underflows. Latenz folgt mit T2.4.
extern "C" JNIEXPORT void JNICALL
Java_de_klangbild_engine_NativeEngine_poll(JNIEnv* env, jclass /*typ*/, jlongArray out) {
    if (out == nullptr || env->GetArrayLength(out) < kPollSize) return;
    jlong werte[kPollSize] = {-1, 0, -1, 0, 0, 0, -1};
    {
        std::lock_guard<std::mutex> lock(gMutex);
        if (gEngine) {
            werte[1] = static_cast<jlong>(gEngine->core.framesPlayed());
            werte[2] = static_cast<jlong>(gEngine->feeder.spur());
            werte[3] = static_cast<jlong>(gEngine->feeder.position());
            werte[4] = gEngine->core.playing() ? 1 : 0;
            werte[5] = static_cast<jlong>(gEngine->core.underflows());
        }
    }
    env->SetLongArrayRegion(out, 0, kPollSize, werte);
}

// --- Vorschau (M8c): zweiter, unabhaengiger Stream neben der Wiedergabe ------------

namespace {
std::unique_ptr<Engine> gVorschau;
}

// Spielt eine Datei auf dem Vorschau-Stream; die Wiedergabe laeuft unberuehrt weiter.
extern "C" JNIEXPORT jboolean JNICALL
Java_de_klangbild_engine_NativeEngine_vorschauStarte(JNIEnv* env, jclass /*typ*/, jstring pfad, jlong startFrame,
                                                     jlong spur) {
    if (pfad == nullptr) return JNI_FALSE;
    const char* text = env->GetStringUTFChars(pfad, nullptr);
    const std::string pfadText = text != nullptr ? std::string(text) : std::string();
    if (text != nullptr) env->ReleaseStringUTFChars(pfad, text);
    if (pfadText.empty()) return JNI_FALSE;

    std::lock_guard<std::mutex> lock(gMutex);
    if (!gVorschau) {
        auto engine = std::make_unique<Engine>();
        engine->output = std::make_shared<klangbild::OboeOutput>(engine->core);
        if (!engine->output->start()) return JNI_FALSE;
        gVorschau = std::move(engine);
    }
    if (!gVorschau->feeder.oeffne(pfadText, startFrame, spur)) return JNI_FALSE;
    gVorschau->core.setPlaying(true);
    gVorschau->feeder.start();
    return JNI_TRUE;
}

extern "C" JNIEXPORT void JNICALL
Java_de_klangbild_engine_NativeEngine_vorschauStoppe(JNIEnv* /*env*/, jclass /*typ*/) {
    std::lock_guard<std::mutex> lock(gMutex);
    if (!gVorschau) return;
    if (gVorschau->output) gVorschau->output->stop();
    gVorschau->feeder.stop();
    gVorschau.reset();
}

// Felder: [0] playing, [1] Spur, [2] Position, [3] underflows. false, wenn keine Vorschau laeuft.
extern "C" JNIEXPORT jboolean JNICALL
Java_de_klangbild_engine_NativeEngine_vorschauPoll(JNIEnv* env, jclass /*typ*/, jlongArray aus) {
    if (aus == nullptr || env->GetArrayLength(aus) < 4) return JNI_FALSE;
    jlong werte[4] = {0, -1, 0, 0};
    jboolean laeuft = JNI_FALSE;
    {
        std::lock_guard<std::mutex> lock(gMutex);
        if (gVorschau) {
            werte[0] = gVorschau->core.playing() ? 1 : 0;
            werte[1] = static_cast<jlong>(gVorschau->feeder.spur());
            werte[2] = static_cast<jlong>(gVorschau->feeder.position());
            werte[3] = static_cast<jlong>(gVorschau->core.underflows());
            laeuft = JNI_TRUE;
        }
    }
    env->SetLongArrayRegion(aus, 0, 4, werte);
    return laeuft;
}

// --- Bäcker (M8b) ------------------------------------------------------------

namespace {

std::vector<float> liesFloats(JNIEnv* env, jfloatArray array) {
    std::vector<float> werte;
    if (array == nullptr) return werte;
    const jsize laenge = env->GetArrayLength(array);
    werte.resize(static_cast<std::size_t>(laenge));
    env->GetFloatArrayRegion(array, 0, laenge, werte.data());
    return werte;
}

}  // namespace

extern "C" JNIEXPORT jlong JNICALL
Java_de_klangbild_engine_NativeEngine_bake(JNIEnv* env, jclass /*typ*/, jstring plan, jfloatArray aAudio,
                                          jfloatArray bAudio, jfloatArray hallIr, jfloatArray riserNoise) {
    if (plan == nullptr || aAudio == nullptr || bAudio == nullptr || hallIr == nullptr) return 0;
    const char* text = env->GetStringUTFChars(plan, nullptr);
    const std::string planText = text != nullptr ? std::string(text) : std::string();
    if (text != nullptr) env->ReleaseStringUTFChars(plan, text);

    const std::vector<float> a = liesFloats(env, aAudio);
    const std::vector<float> b = liesFloats(env, bAudio);
    const std::vector<float> ir = liesFloats(env, hallIr);
    const std::vector<float> rauschen = liesFloats(env, riserNoise);

    klangbild::BakeErgebnis ergebnis;
    try {
        const klangbild::BakeAnfrage anfrage = klangbild::parseBakeAnfrage(planText);
        ergebnis = klangbild::bakeTransition(anfrage, a, b, ir, rauschen);
    } catch (const std::exception& fehler) {
        ergebnis.ok = false;
        ergebnis.fehler = fehler.what();
    }

    std::lock_guard<std::mutex> lock(gMutex);
    const jlong handle = gNaechsteBake++;
    gBakes[handle] = std::move(ergebnis);
    return handle;
}

extern "C" JNIEXPORT jfloatArray JNICALL
Java_de_klangbild_engine_NativeEngine_bakeAudio(JNIEnv* env, jclass /*typ*/, jlong handle) {
    std::lock_guard<std::mutex> lock(gMutex);
    auto it = gBakes.find(handle);
    if (it == gBakes.end() || !it->second.ok) return nullptr;
    const std::vector<float>& audio = it->second.audio;
    jfloatArray aus = env->NewFloatArray(static_cast<jsize>(audio.size()));
    if (aus != nullptr && !audio.empty()) {
        env->SetFloatArrayRegion(aus, 0, static_cast<jsize>(audio.size()), audio.data());
    }
    return aus;
}

extern "C" JNIEXPORT jstring JNICALL
Java_de_klangbild_engine_NativeEngine_bakeInfo(JNIEnv* env, jclass /*typ*/, jlong handle) {
    std::lock_guard<std::mutex> lock(gMutex);
    auto it = gBakes.find(handle);
    if (it == gBakes.end()) return env->NewStringUTF("{\"fehler\":\"unbekanntes Handle\"}");
    const klangbild::BakeErgebnis& ergebnis = it->second;
    if (!ergebnis.ok) {
        const std::string text = "{\"fehler\":" + klangbild::jsonText(ergebnis.fehler) + "}";
        return env->NewStringUTF(text.c_str());
    }
    return env->NewStringUTF(ergebnis.info.c_str());
}

extern "C" JNIEXPORT void JNICALL
Java_de_klangbild_engine_NativeEngine_releaseBake(JNIEnv* /*env*/, jclass /*typ*/, jlong handle) {
    std::lock_guard<std::mutex> lock(gMutex);
    gBakes.erase(handle);
}
