package de.klangbild.core

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import java.io.File
import kotlin.math.PI
import kotlin.math.sin

/**
 * Der blockweise Weg aus dem PCM-Cache muss denselben Wert liefern wie die Rechnung auf dem
 * ganzen Signal (gleiche Filter, gleiche Bloecke, nur andere Summationsreihenfolge).
 */
class LautheitCacheTest {

    @Test
    fun `aus dem Cache stimmt mit dem Direktweg ueberein`() {
        val ordner = File(System.getProperty("java.io.tmpdir"), "klangbild-lufs-${System.nanoTime()}")
        ordner.mkdirs()
        val datei = File(ordner, "1_0_0.pcm")
        val rate = 44100
        val pcm = PcmDatei.anlegen(datei, rate, 2)
        val block = FloatArray(rate * 2)
        for (i in 0 until rate) {
            val wert = (0.3 * sin(2.0 * PI * 440.0 * i / rate)).toFloat()
            block[2 * i] = wert
            block[2 * i + 1] = wert
        }
        repeat(2) { pcm.schreibeBlock(block, 2) }
        pcm.close()

        val links = DoubleArray(2 * rate) { i -> block[2 * (i % rate)].toDouble() }
        val rechts = DoubleArray(2 * rate) { i -> block[2 * (i % rate) + 1].toDouble() }
        val direkt = Lautheit.integriert(arrayOf(links, rechts), rate)

        val gelesen = PcmDatei.oeffnen(datei)
        assertTrue(gelesen != null)
        gelesen!!.use {
            val ausCache = Lautheit.ausCache(it, rate)
            // Der Ringsummen-Lauf rundet anders als die Praefixsummen (1e-5 dB Drift).
            assertEquals(direkt, ausCache, 1e-3, "Cache-Weg weicht ab")
            assertTrue(ausCache > -70.0, "Sinus muss hoerbar sein: $ausCache")
        }
        datei.delete()
        ordner.delete()
    }
}
