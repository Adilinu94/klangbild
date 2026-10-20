package de.klangbild.engine

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import de.klangbild.core.PcmCache
import de.klangbild.core.PcmDatei
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.abs

/**
 * Gerätetest des Decoders (M2): schreibt eine WAV-Datei mit bekanntem Inhalt, dekodiert sie
 * und prüft den PCM-Cache. Läuft auf dem angeschlossenen Handy (`connectedDebugAndroidTest`).
 */
@RunWith(AndroidJUnit4::class)
class DecoderTest {

    @Test
    fun dekodiertWavInDenCache() {
        val kontext = InstrumentationRegistry.getInstrumentation().targetContext
        val ordner = File(kontext.cacheDir, "decoder-test").apply {
            deleteRecursively()
            mkdirs()
        }
        val wav = File(ordner, "test.wav")
        schreibeWav(wav, rate = 44100, kanaele = 2, frames = 44100)

        val cache = PcmCache(File(ordner, "pcm"))
        val ergebnis = Decoder().dekodiere(wav, cache, trackId = 1)

        assertEquals(44100, ergebnis.rate)
        assertTrue("Frames: ${ergebnis.frames}", abs(ergebnis.frames - 44100) <= 1)

        val pfad = cache.finde(1)
        assertNotNull("Cache-Datei fehlt", pfad)
        val datei = PcmDatei.oeffnen(pfad!!)
        datei!!.use {
            assertEquals(2, it.kopf().channels)
            val werte = it.lese(0, 4)
            assertEquals(0.5f, werte[0], 2e-3f)
            assertEquals(-0.25f, werte[1], 2e-3f)
            assertEquals(0.5f, werte[2], 2e-3f)
            assertEquals(-0.25f, werte[3], 2e-3f)
        }
    }

    /** Konstantes Stereo-Signal: links 0,5, rechts -0,25. */
    private fun schreibeWav(datei: File, rate: Int, kanaele: Int, frames: Int) {
        val bytes = ByteBuffer.allocate(frames * kanaele * 2).order(ByteOrder.LITTLE_ENDIAN)
        val links = (0.5 * 32767).toInt().toShort()
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
        kopf.putShort(1)  // PCM
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
