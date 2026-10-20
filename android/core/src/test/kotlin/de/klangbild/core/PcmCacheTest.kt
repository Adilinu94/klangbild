package de.klangbild.core

import org.junit.jupiter.api.Assertions.assertArrayEquals
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNotNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.io.File

/** Tests des PCM-Caches (BAUPLAN §4.3): Kopf, fortlaufendes Schreiben, LRU. */
class PcmCacheTest {

    @TempDir
    lateinit var ordner: File

    @Test
    fun `Schreiben und Lesen mit fortschreitendem Kopf`() {
        val cache = PcmCache(ordner, 4)
        val datei = cache.anlegen(7, 0, 100)
        try {
            datei.schreibeBlock(floatArrayOf(0f, 1f, -1f, 0.5f), 2)
            assertEquals(2, datei.kopf().frames)
            datei.schreibeBlock(floatArrayOf(-0.25f, 0.25f), 2)
            val kopf = datei.kopf()
            assertEquals(3, kopf.frames)
            assertEquals(2, kopf.channels)
            assertEquals(44100, kopf.rate)
            assertEquals(PcmDatei.VERSION, kopf.version)

            assertArrayEquals(
                floatArrayOf(0f, 1f, -1f, 0.5f, -0.25f, 0.25f),
                datei.lese(0, 3),
                1e-4f,
            )
            val rest = datei.lese(2, 4)   // nur ein Frame vorhanden, Rest Stille
            assertEquals(8, rest.size)
            assertEquals(-0.25f, rest[0], 1e-4f)
            assertEquals(0.25f, rest[1], 1e-4f)
            assertEquals(0f, rest[2], 1e-6f)
            assertEquals(0f, rest[3], 1e-6f)
            assertEquals(0f, rest[6], 1e-6f)
        } finally {
            datei.close()
        }

        val wieder = cache.oeffnen(7, 0, 100)
        assertNotNull(wieder)
        wieder!!.use {
            assertEquals(3, it.frames())
            assertArrayEquals(floatArrayOf(0f, 1f), it.lese(0, 1).copyOfRange(0, 2), 1e-4f)
        }
    }

    @Test
    fun `LRU haelt hoechstens vier Dateien`() {
        val cache = PcmCache(ordner, 4)
        for (i in 1..6) {
            cache.anlegen(i, 0, 10).close()
            cache.datei(i, 0, 10).setLastModified(1_600_000_000_000L + i * 1000L)
        }
        cache.aufraeumen()
        assertEquals(4, cache.alle().size)
        assertTrue(cache.alle().none { it.name == "1_0_10.pcm" || it.name == "2_0_10.pcm" })
        assertTrue(cache.alle().any { it.name == "6_0_10.pcm" })
    }

    @Test
    fun `behaltene Dateien bleiben`() {
        val cache = PcmCache(ordner, 4)
        for (i in 1..6) {
            cache.anlegen(i, 0, 10).close()
            cache.datei(i, 0, 10).setLastModified(1_600_000_000_000L + i * 1000L)
        }
        cache.aufraeumen(listOf("1_0_10.pcm"))
        assertEquals(4, cache.alle().size)
        assertTrue(cache.alle().any { it.name == "1_0_10.pcm" })
        assertTrue(cache.alle().none { it.name == "2_0_10.pcm" })
    }
}
