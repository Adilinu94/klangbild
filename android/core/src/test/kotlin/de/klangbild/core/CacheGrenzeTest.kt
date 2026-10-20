package de.klangbild.core

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import java.io.File

/** Cache-Obergrenze: nach Anzahl und nach Groesse, das zuletzt genutzte bleibt. */
class CacheGrenzeTest {

    private fun ordner(): File =
        File(System.getProperty("java.io.tmpdir"), "klangbild-cache-${System.nanoTime()}").also { it.mkdirs() }

    @Test
    fun `zu viele Dateien, die aeltesten fliegen raus`() {
        val ordner = ordner()
        val cache = PcmCache(ordner, maxDateien = 2)
        for (i in 1..5) {
            File(ordner, "1$i" + "_0_0.pcm").writeBytes(ByteArray(16 * i))
            Thread.sleep(15)
        }
        val juengste = "15_0_0.pcm"
        cache.aufraeumen(behalten = listOf(juengste))

        val uebrig = cache.alle().map { it.name }
        assertEquals(2, uebrig.size, "übrig: $uebrig")
        assertTrue(juengste in uebrig, "geschützt: $uebrig")
    }

    @Test
    fun `Grenze nach Bytes greift auch bei wenigen Dateien`() {
        val ordner = ordner()
        val cache = PcmCache(ordner, maxDateien = 10, maxBytes = 100)
        File(ordner, "1_0_0.pcm").writeBytes(ByteArray(80))
        Thread.sleep(15)
        File(ordner, "2_0_0.pcm").writeBytes(ByteArray(80))
        cache.aufraeumen(behalten = listOf("2_0_0.pcm"))

        assertEquals(listOf("2_0_0.pcm"), cache.alle().map { it.name })
    }
}
