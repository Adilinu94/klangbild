package de.klangbild.engine

import de.klangbild.core.PcmCache
import de.klangbild.core.PcmDatei
import java.io.File

/**
 * Der Player für die Oberfläche (M2/M9): dekodiert eine Datei einmal in den PCM-Cache und
 * startet die Wiedergabe über den nativen Kern. [spiele] blockiert (Dekodieren und Datei-I/O),
 * also nie auf dem Main-Thread aufrufen; [zustand] ist billig und darf überall laufen.
 *
 * Die Übergangskette (A-Rest → Blende → B-Rest) folgt mit M8c über [NativeEngine.queueFile].
 */
class Player(private val cache: PcmCache, private val decoder: Decoder = Decoder()) {

    data class Zustand(
        val spur: Long,
        val position: Long,
        val dauer: Long,
        val laeuft: Boolean,
        val underflows: Long,
    )

    private var dauer: Long = 0

    /** Spielt [datei] ab [startFrame]. Beim ersten Mal wird dekodiert und der Cache angelegt. */
    fun spiele(datei: File, spurId: Long, startFrame: Long = 0): Boolean {
        val ziel = pfadFuer(spurId, datei) ?: return false
        if (!NativeEngine.startFile(ziel.absolutePath, startFrame, spurId)) return false
        NativeEngine.setPlaying(true)
        return true
    }

    fun pause() = NativeEngine.setPlaying(false)
    fun weiter() = NativeEngine.setPlaying(true)
    fun stoppe() = NativeEngine.stop()

    /** Aktueller Stand aus `poll` (BAUPLAN §5.4). */
    fun zustand(): Zustand {
        val werte = LongArray(NativeEngine.POLL_SIZE)
        NativeEngine.poll(werte)
        return Zustand(
            spur = werte[NativeEngine.POLL_FEEDER_SPUR],
            position = werte[NativeEngine.POLL_FEEDER_POS],
            dauer = dauer,
            laeuft = werte[NativeEngine.POLL_PLAYING] == 1L,
            underflows = werte[NativeEngine.POLL_UNDERFLOWS],
        )
    }

    /** Cache-Datei des Titels, notfalls vorher dekodieren. Blockiert beim ersten Mal. */
    fun vorbereiten(datei: File, spurId: Long): File? {
        val vorhanden = cache.finde(spurId.toInt())
        if (vorhanden != null) {
            dauer = PcmDatei.oeffnen(vorhanden)?.use { it.frames().toLong() } ?: 0
            return vorhanden
        }
        if (!datei.isFile) return null
        val ergebnis = decoder.dekodiere(datei, cache, spurId.toInt())
        dauer = ergebnis.frames.toLong()
        return cache.datei(spurId.toInt(), 0, ergebnis.frames)
    }

    /** Cache-Datei des Titels, notfalls vorher dekodieren. */
    private fun pfadFuer(spurId: Long, datei: File): File? = vorbereiten(datei, spurId)
}
