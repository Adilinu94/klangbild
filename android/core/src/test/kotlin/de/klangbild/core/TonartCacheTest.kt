package de.klangbild.core

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import java.io.File
import kotlin.math.PI
import kotlin.math.sin

/**
 * Test des blockweisen Chromas direkt aus dem PCM-Cache (fuer die App, ohne den ganzen
 * Titel als float-Array zu halten). Ein 440-Hz-Kammerton muss in Klasse A (9) landen.
 */
class TonartCacheTest {

    @Test
    fun `chroma aus dem Cache erkennt den Kammerton`() {
        val ordner = File(System.getProperty("java.io.tmpdir"), "klangbild-tonart-${System.nanoTime()}")
        ordner.mkdirs()
        val datei = File(ordner, "1_0_0.pcm")
        val rate = 44100
        val pcm = PcmDatei.anlegen(datei, rate, 2)
        val block = FloatArray(rate * 2)
        for (i in 0 until rate) {
            val wert = (0.5 * sin(2.0 * PI * 440.0 * i / rate)).toFloat()
            block[2 * i] = wert
            block[2 * i + 1] = wert
        }
        repeat(4) { pcm.schreibeBlock(block, 2) }
        pcm.close()

        val gelesen = PcmDatei.oeffnen(datei)
        assertTrue(gelesen != null)
        gelesen!!.use {
            val chroma = TonartSchaetzung.chromaAusCache(it)
            assertEquals(1.0, chroma.sum(), 1e-9)
            var bester = 0
            for (k in 1 until 12) if (chroma[k] > chroma[bester]) bester = k
            assertEquals(9, bester, "A erwartet, Chroma=${chroma.toList()}")

            val tonart = TonartSchaetzung.schaetzen(chroma)
            assertEquals("A", tonart.name.take(1))
        }
        datei.delete()
        ordner.delete()
    }
}
