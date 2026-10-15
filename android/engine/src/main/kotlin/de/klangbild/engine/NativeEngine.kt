package de.klangbild.engine

/**
 * JNI-Fassade des nativen Kerns (`libklangbild.so`, BAUPLAN §5.11).
 *
 * Regeln, die für jede Methode gelten:
 * - nie aus dem Audio-Callback aufrufen,
 * - nie vom Main-Thread aus blockieren (`bake` läuft auf dem Planer-Thread),
 * - jedes `open`/`create` hat ein `release`, und Kotlin ruft es im `finally`.
 *
 * Bis M1 steht hier nur die Bau-Auskunft; der Oboe-Stream, der PCM-Cache und
 * das Backen kommen mit T1.1/T2.2/T6.5 dazu.
 */
object NativeEngine {
    init {
        System.loadLibrary("klangbild")
    }

    /** Version der nativen Schnittstelle (steigt bei Vertragsänderungen). */
    external fun aboVersion(): Int
}
