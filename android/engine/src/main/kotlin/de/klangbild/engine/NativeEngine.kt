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
     * Spielt eine PCM-Cache-Datei (BAUPLAN §4.3) ab [startFrame]. Startet den Stream beim ersten
     * Aufruf. [spur] ist die Kennung, die [poll] als [POLL_FEEDER_SPUR] meldet.
     * `false`, wenn die Datei fehlt oder keinen gültigen Kopf hat.
     */
    external fun startFile(pfad: String, startFrame: Long, spur: Long): Boolean

    /**
     * Hängt eine Datei an, die ab [abFrame] der aktuellen (oder am Dateiende bei -1) nahtlos beginnt
     * (kein Flush). Damit spielt der Auto-DJ die Kette A-Rest → gebackene Blende → B-Rest als drei
     * Cache-Dateien. `false`, wenn keine Engine läuft oder die Datei ungültig ist.
     */
    external fun queueFile(pfad: String, startFrame: Long, spur: Long, abFrame: Long): Boolean

    /**
     * Schreibt die Diagnosewerte in [out] (mindestens [POLL_SIZE] Felder), Reihenfolge wie BAUPLAN §5.4.
     * Billig und nicht blockierend; 10-mal pro Sekunde aufrufen, nicht je Frame. Im Spike belegt:
     * [POLL_HEARD_FRAME] (Frames, die der Callback gelesen hat), [POLL_PLAYING], [POLL_UNDERFLOWS].
     * Alles andere ist -1 bzw. 0.
     */
    external fun poll(out: LongArray)

    /**
     * Backt einen Übergang (BAUPLAN §4.5). `plan` ist das JSON des Übergangsplans, die Puffer sind
     * Stereo interleaved (L,R,...). Liefert ein Handle (> 0) oder 0 bei kaputtem Plan. Das Ergebnis
     * wird mit [bakeAudio]/[bakeInfo] abgeholt und mit [releaseBake] freigegeben.
     * Blockiert (Dehnen und Filtern): nicht auf dem Main-Thread aufrufen.
     */
    external fun bake(plan: String, aPcm: FloatArray, bPcm: FloatArray, hallIr: FloatArray, riserNoise: FloatArray?): Long

    /** PCM der gebackenen Spur B (Stereo interleaved); null bei Fehlern. */
    external fun bakeAudio(handle: Long): FloatArray?

    /** Info-JSON des Ergebnisses (`{"fehler": ...}`, wenn das Backen scheiterte). */
    external fun bakeInfo(handle: Long): String

    /** Gibt den nativen Speicher des Ergebnisses frei. */
    external fun releaseBake(handle: Long)

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
