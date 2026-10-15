// JNI-Fassade des nativen Kerns (BAUPLAN §5.11).
//
// Diese Datei ist die **einzige** Stelle mit JNI. Regeln:
// - JNI-Aufrufe nie aus dem Oboe-Callback.
// - Handles sind `jlong` (Zeiger in eine Tabelle, nicht roh); jedes open/create
//   hat ein release.
// - Keine Exception über die JNI-Grenze werfen: Fehler kommen als Rückgabewert.
//
// Bis M1 steht hier nur die Bau-Auskunft. Der Oboe-Stream (T1.1), die Rampen
// (T1.2) und der PCM-Cache (T2.2) erweitern dieselbe Datei.
#include <jni.h>

#include <cstddef>

namespace {

// Version der nativen Schnittstelle. Steigt, wenn sich das Vertrag zwischen
// Kotlin und C++ ändert (andernfalls bleibt die App bei alter .so stillstehen).
constexpr int kAbiVersion = 1;

}  // namespace

extern "C" JNIEXPORT jint JNICALL
Java_de_klangbild_engine_NativeEngine_aboVersion(JNIEnv* /*env*/, jclass /*typ*/) {
    return static_cast<jint>(kAbiVersion);
}
