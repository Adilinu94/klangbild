package de.klangbild.engine

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import de.klangbild.core.Mel
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import kotlin.math.PI
import kotlin.math.exp
import kotlin.math.sin

/**
 * Beat This! auf dem Gerät: ein Metronom mit 120 BPM muss als rund 20 Beats mit
 * 0,5 s Abstand erkannt werden. Das Modell liegt als Asset im APK.
 */
@RunWith(AndroidJUnit4::class)
class BeatThisTest {

    @Test
    fun metronomMit120Bpm() {
        val rate = Mel.RATE
        val sekunden = 10.0
        val signal = FloatArray((rate * sekunden).toInt())
        val klick = (0.04 * rate).toInt()
        var zeit = 0.5
        while (zeit < sekunden - 0.1) {
            val start = (zeit * rate).toInt()
            for (i in 0 until klick) {
                if (start + i >= signal.size) break
                val t = i.toDouble() / rate
                val huelle = exp(-t / 0.008)
                signal[start + i] += (0.8 * huelle * sin(2.0 * PI * 1000.0 * t)).toFloat()
            }
            zeit += 0.5
        }

        val kontext = InstrumentationRegistry.getInstrumentation().targetContext
        val ergebnis = BeatThis.holen(kontext).analysiere(signal)

        assertTrue("keine Beats erkannt", ergebnis.verfuegbar)
        assertTrue("unerwartet viele Beats: ${ergebnis.beats.size}", ergebnis.beats.size in 16..24)

        val abstaende = ergebnis.beats.toList().zipWithNext { a, b -> (b - a).toDouble() }
        val mittel = abstaende.sorted()[abstaende.size / 2]
        assertTrue("Abstand $mittel statt 0.5 s", kotlin.math.abs(mittel - 0.5) < 0.03)

        val erste = ergebnis.beats.first()
        assertTrue("erster Beat bei $erste", kotlin.math.abs(erste - 0.5) < 0.06)
    }
}
