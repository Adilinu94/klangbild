package de.klangbild.engine

import de.klangbild.core.PcmCache
import java.io.File

/**
 * Auto-DJ-Kette (M8c): A läuft, die gebackene Blende hängt ab `abS` an, danach folgt B.
 *
 * Das Audio kommt fertig vom Übergangs-Bäcker ([de.klangbild.core.AutoDjController] +
 * [NativeBaker]); diese Klasse schreibt es in den PCM-Cache, hängt es an den Feeder und
 * schaltet auf B weiter, sobald die Blende läuft. [haengeBlendeAn] blockiert (Dekodieren,
 * Datei-I/O): nicht auf dem Main-Thread aufrufen. [aktualisiere] ist billig und darf
 * regelmäßig (z. B. alle 100 ms) laufen.
 */
class AutoDjPlayer(private val player: Player, private val cache: PcmCache) {

    private var blendeSpur: Long = 0
    private var blendePfad: String? = null
    private var blendeAktiv = false
    private var bPfad: String? = null
    private var bStart: Long = 0
    private var bSpur: Long = 0

    /** Spielt [datei] von vorn; die Blende folgt später über [haengeBlendeAn]. */
    fun spiele(datei: File, aId: Int): Boolean = player.spiele(datei, aId.toLong())

    /**
     * Schreibt die gebackene Blende in den Cache und hängt sie ab [abFrame] (Frame in A) an.
     * [bDatei] wird vorab in den Cache gelegt; sobald die Blende läuft, folgt B ab [bStartFrame].
     * `false`, wenn das Audio leer/ungerade ist, B nicht dekodiert werden kann oder der Feeder
     * die Blende nicht annimmt.
     */
    fun haengeBlendeAn(
        aId: Int,
        bId: Int,
        audio: FloatArray,
        abFrame: Long,
        bDatei: File,
        bStartFrame: Long = 0,
    ): Boolean {
        if (audio.isEmpty() || audio.size % 2 != 0) return false
        val ziel = cache.blendeDatei(aId, bId)
        cache.anlegenBlende(aId, bId).use { it.schreibeBlock(audio, 2) }

        val bCache = player.vorbereiten(bDatei, bId.toLong()) ?: return false
        val spur = blendeSpur(aId, bId)
        if (!NativeEngine.queueFile(ziel.absolutePath, 0, spur, abFrame)) return false
        blendeSpur = spur
        blendePfad = ziel.absolutePath
        blendeAktiv = true
        bPfad = bCache.absolutePath
        bStart = bStartFrame
        bSpur = bId.toLong()
        return true
    }

    /** Regelmäßig aufrufen: hängt B an, sobald der Feeder die Blende spielt. */
    fun aktualisiere(): Boolean {
        if (!blendeAktiv) return false
        if (player.zustand().spur != blendeSpur) return false
        val pfad = bPfad ?: return false
        val angehaengt = NativeEngine.queueFile(pfad, bStart, bSpur, -1)
        if (angehaengt) {
            blendeAktiv = false
            bPfad = null
        }
        return angehaengt
    }

    /**
     * Verwirft den laufenden Titel: die Blende beginnt sofort an der aktuellen Position statt
     * erst bei `abS` (harter Schnitt, wie beim Wegziehen einer Platte). `false`, wenn keine
     * Blende wartet.
     */
    fun verwerfen(): Boolean {
        if (!blendeAktiv) return false
        val pfad = blendePfad ?: return false
        val position = player.zustand().position
        return NativeEngine.queueFile(pfad, 0, blendeSpur, position)
    }

    /** Beim Stoppen oder Verwerfen: Blende und B vergessen. */
    fun zuruecksetzen() {
        blendeAktiv = false
        blendePfad = null
        bPfad = null
    }

    companion object {
        /** Negative Spur, damit sie nie mit einer Titel-ID kollidiert. */
        fun blendeSpur(aId: Int, bId: Int): Long = -1_000_000L - (aId.toLong() * 100_000L + bId)
    }
}
