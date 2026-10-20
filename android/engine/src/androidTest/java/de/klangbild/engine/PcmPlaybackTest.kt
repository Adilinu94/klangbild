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

    @Test
    fun spieltZweiDateienNacheinander() {
        val kontext = InstrumentationRegistry.getInstrumentation().targetContext
        val ordner = File(kontext.cacheDir, "pcm-playback-kette").apply {
            deleteRecursively()
            mkdirs()
        }
        val cache = PcmCache(ordner)
        val block = FloatArray(44100 * 2) { i -> if (i % 2 == 0) 0.2f else -0.2f }
        for (id in listOf(77, 78)) {
            val datei = cache.anlegen(id, 0, 44100)
            datei.schreibeBlock(block, 2)
            datei.close()
        }
        val a = cache.datei(77, 0, 44100).absolutePath
        val b = cache.datei(78, 0, 44100).absolutePath

        assertTrue("startFile", NativeEngine.startFile(a, 0, 77))
        try {
            assertTrue("queueFile", NativeEngine.queueFile(b, 0, 78, -1))
            NativeEngine.setPlaying(true)
            val werte = LongArray(NativeEngine.POLL_SIZE)
            val frist = System.currentTimeMillis() + 5000
            while (System.currentTimeMillis() < frist && werte[NativeEngine.POLL_FEEDER_SPUR] != 78L) {
                Thread.sleep(50)
                NativeEngine.poll(werte)
            }
            assertEquals("Spur wechselt nicht: ${werte.joinToString()}", 78L, werte[NativeEngine.POLL_FEEDER_SPUR])
            assertTrue("Kein Callback", werte[NativeEngine.POLL_HEARD_FRAME] > 0)
        } finally {
            NativeEngine.stop()
        }
    }

    @Test
    fun verwirftDenTitelSofort() {
        val kontext = InstrumentationRegistry.getInstrumentation().targetContext
        val ordner = File(kontext.cacheDir, "pcm-playback-verwerfen").apply {
            deleteRecursively()
            mkdirs()
        }
        val cache = PcmCache(ordner)
        val ton = FloatArray(4 * 44100 * 2) { i -> if (i % 2 == 0) 0.3f else -0.3f }
        cache.anlegen(77, 0, 4 * 44100).use { it.schreibeBlock(ton, 2) }
        cache.anlegen(78, 0, 44100).use { it.schreibeBlock(ton.copyOf(44100 * 2), 2) }
        val autoDj = AutoDjPlayer(Player(cache), cache)
        val blende = FloatArray(2 * 44100) { i -> if (i % 2 == 0) 0.1f else -0.1f }

        assertTrue("startFile", autoDj.spiele(cache.datei(77, 0, 4 * 44100), 77))
        try {
            // Blende erst nach 4 s; verworfen wird nach 300 ms.
            assertTrue("Blende anhaengen", autoDj.haengeBlendeAn(77, 78, blende, 4 * 44100, cache.datei(78, 0, 44100)))
            Thread.sleep(300)
            assertTrue("verwerfen", autoDj.verwerfen())

            val spurBlende = AutoDjPlayer.blendeSpur(77, 78)
            val werte = LongArray(NativeEngine.POLL_SIZE)
            val frist = System.currentTimeMillis() + 2000
            while (System.currentTimeMillis() < frist && werte[NativeEngine.POLL_FEEDER_SPUR] != spurBlende) {
                Thread.sleep(50)
                autoDj.aktualisiere()
                NativeEngine.poll(werte)
            }
            assertEquals("Blende nicht sofort: ${werte.joinToString()}", spurBlende, werte[NativeEngine.POLL_FEEDER_SPUR])
        } finally {
            autoDj.zuruecksetzen()
            NativeEngine.stop()
        }
    }

    @Test
    fun vorschauLaeuftNebenDerWiedergabe() {
        val kontext = InstrumentationRegistry.getInstrumentation().targetContext
        val ordner = File(kontext.cacheDir, "pcm-playback-vorschau").apply {
            deleteRecursively()
            mkdirs()
        }
        val cache = PcmCache(ordner)
        val ton = FloatArray(4 * 44100 * 2) { i -> if (i % 2 == 0) 0.3f else -0.3f }
        cache.anlegen(77, 0, 4 * 44100).use { it.schreibeBlock(ton, 2) }
        cache.anlegen(78, 0, 2 * 44100).use { it.schreibeBlock(ton.copyOf(2 * 44100 * 2), 2) }
        val player = Player(cache)

        assertTrue("startFile", player.spiele(cache.datei(77, 0, 4 * 44100), 77))
        try {
            assertTrue("Vorschau", player.vorschau(cache.datei(78, 0, 2 * 44100), 78))
            val werte = LongArray(NativeEngine.VORSCHAU_FELDER)
            val frist = System.currentTimeMillis() + 2000
            while (System.currentTimeMillis() < frist && werte[NativeEngine.VORSCHAU_POS] == 0L) {
                Thread.sleep(50)
                NativeEngine.vorschauPoll(werte)
            }
            assertEquals("Vorschau-Spur", 78L, werte[NativeEngine.VORSCHAU_SPUR])
            assertTrue("Vorschau liest nicht", werte[NativeEngine.VORSCHAU_POS] > 0)
            assertEquals("Hauptspur veraendert", 77L, player.zustand().spur)
        } finally {
            player.vorschauStoppe()
            NativeEngine.stop()
        }
        assertEquals("Vorschau laeuft noch", false, NativeEngine.vorschauPoll(LongArray(NativeEngine.VORSCHAU_FELDER)))
    }

    @Test
    fun ketteAutoDjMitGebackenerBlende() {
        val kontext = InstrumentationRegistry.getInstrumentation().targetContext
        val ordner = File(kontext.cacheDir, "pcm-playback-autodj").apply {
            deleteRecursively()
            mkdirs()
        }
        val cache = PcmCache(ordner)
        val ton = FloatArray(44100 * 2) { i -> if (i % 2 == 0) 0.3f else -0.3f }
        for (id in listOf(77, 78)) {
            cache.anlegen(id, 0, 44100).use { it.schreibeBlock(ton, 2) }
        }
        val autoDj = AutoDjPlayer(Player(cache), cache)
        val blende = FloatArray(2 * 44100) { i -> if (i % 2 == 0) 0.1f else -0.1f }

        assertTrue("startFile", autoDj.spiele(cache.datei(77, 0, 44100), 77))
        try {
            assertTrue("Blende anhaengen", autoDj.haengeBlendeAn(77, 78, blende, 44100, cache.datei(78, 0, 44100)))
            val werte = LongArray(NativeEngine.POLL_SIZE)
            val frist = System.currentTimeMillis() + 8000
            while (System.currentTimeMillis() < frist && werte[NativeEngine.POLL_FEEDER_SPUR] != 78L) {
                Thread.sleep(50)
                autoDj.aktualisiere()
                NativeEngine.poll(werte)
            }
            assertEquals("Spur: ${werte.joinToString()}", 78L, werte[NativeEngine.POLL_FEEDER_SPUR])
        } finally {
            autoDj.zuruecksetzen()
            NativeEngine.stop()
        }
    }
}
