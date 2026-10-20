package de.klangbild.core

import kotlin.math.PI
import kotlin.math.sin

/**
 * Wandelt den PCM-Cache (Stereo, 44,1 kHz) in mono 22,05 kHz fuer Beat This!.
 * Blockweise gelesen, Tiefpass mit 63 Koeffizienten (Blackman, Grenze 11 kHz)
 * und Halbierung: der Speicher bleibt bei einem Block plus dem Ergebnis.
 */
object Abtastung {

    private const val TAPS = 63
    private const val GRENZE_HZ = 11000.0
    private const val QUELLE = 44100

    private val koeffizienten = DoubleArray(TAPS) { n ->
        val m = n - (TAPS - 1) / 2.0
        val fc = GRENZE_HZ / QUELLE
        val sinc = if (m == 0.0) 2.0 * fc else sin(2.0 * PI * fc * m) / (PI * m)
        val fenster = 0.42 - 0.5 * kotlin.math.cos(2.0 * PI * n / (TAPS - 1)) +
            0.08 * kotlin.math.cos(4.0 * PI * n / (TAPS - 1))
        sinc * fenster
    }.let { roh ->
        val summe = roh.sum()
        DoubleArray(TAPS) { roh[it] / summe }
    }

    fun mono22050(pcm: PcmDatei): FloatArray {
        val frames = pcm.frames()
        if (frames <= 0) return FloatArray(0)

        val ausgabe = FloatArray(frames / 2)
        val verzoegerung = DoubleArray(TAPS)
        var geschrieben = 0
        var start = 0

        while (start < frames) {
            val anzahl = minOf(16384, frames - start)
            val stereo = pcm.lese(start, anzahl)
            for (i in 0 until anzahl) {
                val mono = ((stereo[2 * i] + stereo[2 * i + 1]) * 0.5f).toDouble()

                for (k in 0 until TAPS - 1) verzoegerung[k] = verzoegerung[k + 1]
                verzoegerung[TAPS - 1] = mono

                val global = start + i
                if (global % 2 == 0) {
                    var wert = 0.0
                    for (k in 0 until TAPS) wert += koeffizienten[k] * verzoegerung[k]
                    if (geschrieben < ausgabe.size) ausgabe[geschrieben++] = wert.toFloat()
                }
            }
            start += anzahl
        }
        return if (geschrieben == ausgabe.size) ausgabe else ausgabe.copyOf(geschrieben)
    }
}
