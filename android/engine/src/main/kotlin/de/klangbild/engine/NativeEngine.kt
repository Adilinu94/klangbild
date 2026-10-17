package de.klangbild.engine

/**
 * JNI-Fassade des nativen Kerns (`libklangbild.so`, BAUPLAN §5.11).
 *
 * Regeln, die für jede Methode gelten:
 * - nie aus dem Audio-Callback aufrufen,
 * - nie vom Main-Thread aus blockieren (`bake` läuft auf dem Planer-Thread),
 * - jedes `open`/`create` hat ein `release`, und Kotlin ruft es im `finally`.
 *
 * Stand M1 (Spike): Oboe-Stream mit Sinus-Testquelle (`start`, `stop`, `setPlaying`, `poll`).
 * Der PCM-Cache und das Backen kommen mit T2.2/T6.5 dazu.
 */
object NativeEngine {
    init {
        System.loadLibrary("klangbild")
    }

    /** Version der nativen Schnittstelle (steigt bei Vertragsänderungen). */
    external fun aboVersion(): Int

    /**
     * Öffnet und startet den Oboe-Stream; die Quelle ist ein Sinus mit 440 Hz (Spike M1).
     * `false`, wenn sich der Stream nicht öffnen oder starten lässt. Blockiert kurz: nicht auf dem Main-Thread.
     */
    external fun start(): Boolean

    /** Stoppt und schließt den Stream. Danach ist der Callback nicht mehr aktiv. */
    external fun stop()

    /** Spielen oder Pause; der Callback blendet in 10 ms ein bzw. aus. */
    external fun setPlaying(playing: Boolean)

    /**
     * Schreibt die Diagnosewerte in [out] (mindestens [POLL_SIZE] Felder), Reihenfolge wie BAUPLAN §5.4.
     * Billig und nicht blockierend; 10-mal pro Sekunde aufrufen, nicht je Frame. Im Spike belegt:
     * [POLL_HEARD_FRAME] (Frames, die der Callback gelesen hat), [POLL_PLAYING], [POLL_UNDERFLOWS].
     * Alles andere ist -1 bzw. 0.
     */
    external fun poll(out: LongArray)

    /** Anzahl der Felder von [poll]. Gleich `kPollSize` in jni_bridge.cpp. */
    const val POLL_SIZE = 7
    const val POLL_HEARD_SPUR = 0
    const val POLL_HEARD_FRAME = 1
    const val POLL_FEEDER_SPUR = 2
    const val POLL_FEEDER_POS = 3
    const val POLL_PLAYING = 4
    const val POLL_UNDERFLOWS = 5
    const val POLL_LATENCY_FRAMES = 6
}
