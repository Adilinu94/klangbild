package de.klangbild.core

import kotlin.math.abs
import kotlin.math.max
import kotlin.math.sqrt

/**
 * Farbige Wellenform wie Serato/VirtualDJ (Port von `welle.berechnen`).
 *
 * STFT mit 1024er Hann-Fenster und Hop 220 (≈100 Spalten/s bei 22,05 kHz Mono). Je Spalte:
 * `peak` (Spitzenwert) und die Energie in drei Baendern (< 200 Hz, 200–2000 Hz, > 2000 Hz)
 * als r/g/b. Alle Baender teilen einen Bezug (99. Perzentil), damit die echten Verhaeltnisse
 * erhalten bleiben (Bass-Passagen rot, Mitten gruen).
 */
object Welle {

    const val RATE = 22050
    const val HOP = 220
    const val FENSTER = 1024

    data class Spalten(val peak: IntArray, val r: IntArray, val g: IntArray, val b: IntArray)

    fun berechnen(mono: FloatArray, rate: Int = RATE): Spalten {
        val x = if (mono.size < FENSTER) mono.copyOf(FENSTER) else mono
        val anzahl = 1 + (x.size - FENSTER) / HOP
        val fenster = FloatArray(FENSTER) { (0.5 - 0.5 * kotlin.math.cos(2.0 * Math.PI * it / (FENSTER - 1))).toFloat() }
        val frequenz = DoubleArray(FENSTER / 2 + 1) { k -> k * rate.toDouble() / FENSTER }

        val tief = (0..FENSTER / 2).filter { frequenz[it] >= 20.0 && frequenz[it] < 200.0 }
        val mitte = (0..FENSTER / 2).filter { frequenz[it] >= 200.0 && frequenz[it] < 2000.0 }
        val hoch = (0..FENSTER / 2).filter { frequenz[it] >= 2000.0 && frequenz[it] < rate / 2.0 }

        val r = DoubleArray(anzahl)
        val g = DoubleArray(anzahl)
        val b = DoubleArray(anzahl)
        val peak = DoubleArray(anzahl)
        val rahmen = DoubleArray(FENSTER)

        for (i in 0 until anzahl) {
            val start = i * HOP
            var spitze = 0.0
            for (k in 0 until FENSTER) {
                val roh = x[start + k].toDouble()
                if (abs(roh) > spitze) spitze = abs(roh)
                rahmen[k] = (x[start + k] * fenster[k]).toDouble()
            }
            peak[i] = spitze

            val leistung = Fft.leistung(rahmen)
            r[i] = sqrt(band(leistung, tief))
            g[i] = sqrt(band(leistung, mitte))
            b[i] = sqrt(band(leistung, hoch))
        }

        val maxima = DoubleArray(anzahl) { max(r[it], max(g[it], b[it])) }
        val bezug = Profil.percentile(maxima, 99.0).let { if (it > 0.0) it else 1.0 }
        val peakBezug = Profil.percentile(peak, 99.5).let { if (it > 0.0) it else 1.0 }

        fun skala(werte: DoubleArray, teiler: Double): IntArray = IntArray(werte.size) { i ->
            (werte[i] / teiler * 255.0).toInt().coerceIn(0, 255)
        }

        return Spalten(
            peak = skala(peak, peakBezug),
            r = skala(r, bezug),
            g = skala(g, bezug),
            b = skala(b, bezug),
        )
    }

    private fun band(leistung: DoubleArray, bins: List<Int>): Double {
        var summe = 0.0
        for (k in bins) summe += leistung[k]
        return summe
    }
}
