package de.klangbild.engine

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import de.klangbild.core.PcmCache
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * Gerätetest der Wiedergabe (M2): legt einen PCM-Cache an, startet den Oboe-Stream und prüft,
 * dass der Callback Frames liest und der Feeder die Spur meldet. Hörtest nicht nötig; es zählt
 * der Datenfluss auf echter Hardware.
 */
@RunWith(AndroidJUnit4::class)
class PcmPlaybackTest {

    @Test
    fun spieltPcmCacheUeberOboe() {
        val kontext = InstrumentationRegistry.getInstrumentation().targetContext
        val ordner = File(kontext.cacheDir, "pcm-playback").apply {
            deleteRecursively()
            mkdirs()
        }
        val cache = PcmCache(ordner)
        val datei = cache.anlegen(77, 0, 2 * 44100)
        val block = FloatArray(44100 * 2) { i -> if (i % 2 == 0) 0.3f else -0.3f }
        datei.schreibeBlock(block, 2)
        datei.schreibeBlock(block, 2)
        datei.close()

        val pfad = cache.datei(77, 0, 2 * 44100).absolutePath
        assertTrue("startFile", NativeEngine.startFile(pfad, 0, 77))
        try {
            NativeEngine.setPlaying(true)
            val werte = LongArray(NativeEngine.POLL_SIZE)
            val frist = System.currentTimeMillis() + 3000
            while (System.currentTimeMillis() < frist && werte[NativeEngine.POLL_HEARD_FRAME] == 0L) {
                Thread.sleep(50)
                NativeEngine.poll(werte)
            }
            assertTrue("Kein Callback: ${werte.joinToString()}", werte[NativeEngine.POLL_HEARD_FRAME] > 0)
            assertEquals(77L, werte[NativeEngine.POLL_FEEDER_SPUR])
            assertTrue(
                "Feeder-Position ${werte[NativeEngine.POLL_FEEDER_POS]}",
                werte[NativeEngine.POLL_FEEDER_POS] > 0,
            )
        } finally {
            NativeEngine.stop()
        }
    }
}
