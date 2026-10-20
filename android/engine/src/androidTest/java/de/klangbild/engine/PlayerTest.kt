package de.klangbild.engine

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import de.klangbild.core.PcmCache
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder

/** Gerätetest des Players: dekodieren, starten, pausieren, Zustand lesen. */
@RunWith(AndroidJUnit4::class)
class PlayerTest {

    @Test
    fun dekodiertUndSpielt() {
        val kontext = InstrumentationRegistry.getInstrumentation().targetContext
        val ordner = File(kontext.cacheDir, "player-test").apply {
            deleteRecursively()
            mkdirs()
        }
        val wav = File(ordner, "test.wav")
        schreibeWav(wav, rate = 44100, kanaele = 2, frames = 44100)

        val player = Player(PcmCache(File(ordner, "pcm")))
        try {
            assertTrue("spiele", player.spiele(wav, 5))

            val werte = LongArray(NativeEngine.POLL_SIZE)
            val frist = System.currentTimeMillis() + 5000
            while (System.currentTimeMillis() < frist && werte[NativeEngine.POLL_HEARD_FRAME] == 0L) {
                Thread.sleep(50)
                NativeEngine.poll(werte)
            }
            assertTrue("Kein Callback: ${werte.joinToString()}", werte[NativeEngine.POLL_HEARD_FRAME] > 0)

            val zustand = player.zustand()
            assertTrue("laeuft", zustand.laeuft)
            assertTrue("dauer ${zustand.dauer}", zustand.dauer > 0)
            assertEquals(5L, zustand.spur)
            assertTrue("position ${zustand.position}", zustand.position > 0)

            player.pause()
            assertFalse("pause", player.zustand().laeuft)
        } finally {
            player.stoppe()
        }
    }

    private fun schreibeWav(datei: File, rate: Int, kanaele: Int, frames: Int) {
        val bytes = ByteBuffer.allocate(frames * kanaele * 2).order(ByteOrder.LITTLE_ENDIAN)
        val links = (0.25 * 32767).toInt().toShort()
        val rechts = (-0.25 * 32767).toInt().toShort()
        for (i in 0 until frames) {
            bytes.putShort(links)
            bytes.putShort(rechts)
        }
        val daten = bytes.array()
        val kopf = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN)
        kopf.put("RIFF".toByteArray(Charsets.US_ASCII))
        kopf.putInt(36 + daten.size)
        kopf.put("WAVE".toByteArray(Charsets.US_ASCII))
        kopf.put("fmt ".toByteArray(Charsets.US_ASCII))
        kopf.putInt(16)
        kopf.putShort(1)
        kopf.putShort(kanaele.toShort())
        kopf.putInt(rate)
        kopf.putInt(rate * kanaele * 2)
        kopf.putShort((kanaele * 2).toShort())
        kopf.putShort(16)
        kopf.put("data".toByteArray(Charsets.US_ASCII))
        kopf.putInt(daten.size)
        datei.outputStream().use {
            it.write(kopf.array())
            it.write(daten)
        }
    }
}
