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
    private var aktuelleDatei: File? = null
    private var aktuelleSpur: Long = 0
    private var dateiWaechst = false

    /**
     * Spielt [datei] ab [startFrame]. Beim ersten Mal wird dekodiert; die Wiedergabe startet
     * bereits nach der ersten Sekunde Cache, der Rest wird im Hintergrund weitergeschrieben.
     */
    fun spiele(datei: File, spurId: Long, startFrame: Long = 0): Boolean {
        val vorhanden = cache.finde(spurId.toInt())
        if (vorhanden != null) {
            dauer = PcmDatei.oeffnen(vorhanden)?.use { it.frames().toLong() } ?: 0
            return starte(vorhanden, spurId, startFrame)
        }
        if (!datei.isFile) return false

        val ziel = cache.datei(spurId.toInt(), 0, 0)
        var gestartet = false
        val ergebnis = try {
            decoder.dekodiere(datei, cache, spurId.toInt(), beiBlock = { frames ->
                if (!gestartet && frames >= 44100) {
                    gestartet = NativeEngine.startFile(ziel.absolutePath, 0, spurId, true)
                    if (gestartet) {
                        dateiWaechst = true
                        NativeEngine.setPlaying(true)
                    }
                }
            })
        } catch (_: Throwable) {
            if (gestartet) NativeEngine.stop()
            return false
        }
        dauer = ergebnis.frames.toLong()
        if (!gestartet) return starte(ziel, spurId, 0)
        NativeEngine.quelleFertig()
        dateiWaechst = false
        aktuelleDatei = ziel
        aktuelleSpur = spurId
        return true
    }

    /** Startet [datei] ohne Umweg ueber den Decoder (Cache liegt schon vor). */
    private fun starte(datei: File, spurId: Long, startFrame: Long): Boolean {
        if (!NativeEngine.startFile(datei.absolutePath, startFrame, spurId, false)) return false
        NativeEngine.setPlaying(true)
        dateiWaechst = false
        aktuelleDatei = datei
        aktuelleSpur = spurId
        return true
    }

    /** Springt im laufenden Titel an [frame] (Flush, Warteschlange wird verworfen). */
    fun springeZu(frame: Long): Boolean {
        val datei = aktuelleDatei ?: return false
        if (!NativeEngine.startFile(datei.absolutePath, frame.coerceAtLeast(0), aktuelleSpur, dateiWaechst)) {
            return false
        }
        NativeEngine.setPlaying(true)
        return true
    }

    fun pause() = NativeEngine.setPlaying(false)
    fun weiter() = NativeEngine.setPlaying(true)
    fun stoppe() = NativeEngine.stop()

    /**
     * Vorschau eines Titels auf einem zweiten Stream, während die Wiedergabe weiterläuft.
     * Blockiert beim ersten Mal (Dekodieren); [dauer] der laufenden Wiedergabe bleibt erhalten.
     */
    fun vorschau(datei: File, spurId: Long): Boolean {
        val alt = dauer
        val ziel = vorbereiten(datei, spurId)
        dauer = alt
        if (ziel == null) return false
        return NativeEngine.vorschauStarte(ziel.absolutePath, 0, spurId)
    }

    fun vorschauStoppe() = NativeEngine.vorschauStoppe()

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
        val ergebnis = try {
            decoder.dekodiere(datei, cache, spurId.toInt())
        } catch (_: Throwable) {
            return null
        }
        dauer = ergebnis.frames.toLong()
        return cache.finde(spurId.toInt())
    }
}
