package de.klangbild.core

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import java.io.File
import kotlin.math.PI
import kotlin.math.sin

/**
 * Cache auf 22,05 kHz mono: 1 kHz muss bleiben, 15 kHz (ueber der neuen Grenze)
 * muss weg sein, sonst wuerde er in die Mel-Baender zurueckspiegeln.
 */
class AbtastungTest {

    private val rate = 44100

    private fun cacheMit(vararg toene: Pair<Double, Double>): FloatArray {
        val ordner = File(System.getProperty("java.io.tmpdir"), "klangbild-abt-${System.nanoTime()}")
        ordner.mkdirs()
        val datei = File(ordner, "1_0_0.pcm")
        val pcm = PcmDatei.anlegen(datei, rate, 2)
        val block = FloatArray(rate * 2)
        for (i in 0 until rate) {
            var wert = 0.0
            for ((hz, amp) in toene) wert += amp * sin(2.0 * PI * hz * i / rate)
            block[2 * i] = wert.toFloat()
            block[2 * i + 1] = wert.toFloat()
        }
        repeat(2) { pcm.schreibeBlock(block, 2) }
        pcm.close()

        val gelesen = PcmDatei.oeffnen(datei) ?: error("Cache nicht lesbar")
        val mono = gelesen.use { Abtastung.mono22050(it) }
        datei.delete()
        ordner.delete()
        return mono
    }

    private fun amplitude(signal: FloatArray): Double {
        var summe = 0.0
        for (wert in signal) summe += wert.toDouble() * wert
        return kotlin.math.sqrt(summe / signal.size)
    }

    @Test
    fun `halbe Rate, 1 kHz bleibt`() {
        val mono = cacheMit(1000.0 to 0.5)
        assertEquals(rate, mono.size, "ein 44,1-kHz-Block wird zu 22 050 Werten")
        assertEquals(0.5 / kotlin.math.sqrt(2.0), amplitude(mono), 0.02)
    }

    @Test
    fun `15 kHz wird gedaempft`() {
        val mono = cacheMit(15000.0 to 0.5)
        assertTrue(amplitude(mono) < 0.02, "Rest ${amplitude(mono)}")
    }
}
