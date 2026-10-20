package de.klangbild.core

import kotlin.math.log10
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

/**
 * Bandtrennung wie `mix.band_teilen` (Port von scipy `butter(4, …, output="sos")` +
 * `sosfiltfilt`) und Pegel je Takt wie `profil._db_je_takt`.
 *
 * Die SOS-Koeffizienten sind die exakten scipy-Werte für 44,1 kHz (200 Hz und 2500 Hz).
 * Gefiltert wird in double, das Ergebnis wie im Prototyp auf float32 gerundet; das ist
 * wichtig, weil die Golden-Werte aus genau dieser Rundung stammen.
 */
object ProfilBau {

    private val TIEF = arrayOf(
        doubleArrayOf(
            3.9711191921338650e-08, 7.9422383842677300e-08, 3.9711191921338650e-08,
            1.0, -1.9479140290729067, 9.4870512526541229e-01,
        ),
        doubleArrayOf(
            1.0, 2.0, 1.0,
            1.0, -1.9776257216220969, 9.7842888446975140e-01,
        ),
    )

    private val MITTE = arrayOf(
        doubleArrayOf(
            6.5724537671273630e-04, 1.3144907534254726e-03, 6.5724537671273630e-04,
            1.0, -1.4177269518539084, 5.1267399376173806e-01,
        ),
        doubleArrayOf(
            1.0, 2.0, 1.0,
            1.0, -1.6537781154646098, 7.6453381481132743e-01,
        ),
    )

    /** (tief, mitte, hoch) aus mono; `rest = mono - tief`, `hoch = rest - mitte`. */
    fun teilen(mono: FloatArray): Triple<FloatArray, FloatArray, FloatArray> {
        val tief = filtfilt(TIEF, mono)
        val rest = FloatArray(mono.size) { mono[it] - tief[it] }
        val mitte = filtfilt(MITTE, rest)
        val hoch = FloatArray(rest.size) { rest[it] - mitte[it] }
        return Triple(tief, mitte, hoch)
    }

    /** RMS in dB je [grenzen[i], grenzen[i+1]) (mono); gleiche Formel wie `_db_je_takt`. */
    fun dbJeTakt(mono: FloatArray, grenzen: IntArray): DoubleArray {
        val q = DoubleArray(mono.size + 1)
        for (i in mono.indices) {
            val wert = mono[i].toDouble()
            q[i + 1] = q[i] + wert * wert
        }
        return DoubleArray(grenzen.size - 1) { i ->
            val laenge = max(1, grenzen[i + 1] - grenzen[i])
            10.0 * log10((q[grenzen[i + 1]] - q[grenzen[i]]) / laenge + 1e-10)
        }
    }

    /**
     * Profil aus dekodiertem Audio (Stereo interleaved, 44,1 kHz) und Downbeats.
     * Chroma folgt mit dem FFT-Schritt; hier bleiben die Pegel.
     */
    fun profil(audio: FloatArray, downbeats: List<Double>, bpm: Double): Profil {
        val frames = audio.size / 2
        val rate = 44100
        val dauer = frames.toDouble() / rate
        val mono = FloatArray(frames) { (audio[2 * it] + audio[2 * it + 1]) / 2f }

        var takte = Taktraster.taktraster(downbeats, bpm, dauer)
        takte = takte.filter { it >= -0.5 && it < dauer - 0.5 }.toDoubleArray()
        if (takte.size < 2) takte = doubleArrayOf(0.0, dauer)

        val ende = min(dauer, 2.0 * takte.last() - takte[takte.size - 2])
        val grenzen = IntArray(takte.size + 1)
        for (i in takte.indices) grenzen[i] = (takte[i] * rate).roundToInt().coerceIn(0, frames)
        grenzen[takte.size] = (ende * rate).roundToInt().coerceIn(0, frames)

        val (tief, mitte, hoch) = teilen(mono)
        val baender = Array(takte.size) { i ->
            doubleArrayOf(
                dbJeTakt(tief, grenzen)[i],
                dbJeTakt(mitte, grenzen)[i],
                dbJeTakt(hoch, grenzen)[i],
            )
        }
        val gesamt = dbJeTakt(mono, grenzen)

        val rasterOk = BooleanArray(takte.size) { i ->
            if (downbeats.isEmpty()) {
                false
            } else {
                val naechst = downbeats.minOf { d -> kotlin.math.abs(d - takte[i]) }
                naechst < 0.07
            }
        }
        return Profil(takte, baender, gesamt, null, rasterOk, dauer)
    }

    // --- scipy-Nachbau: sosfiltfilt ------------------------------------------------

    private fun filtfilt(sos: Array<DoubleArray>, x: FloatArray): FloatArray {
        val rand = 3 * (2 * sos.size + 1)
        if (x.size <= rand) return kausal(sos, x)

        val ext = DoubleArray(x.size + 2 * rand)
        var erster = x[0].toDouble()
        var letzter = x[x.size - 1].toDouble()
        for (i in 0 until rand) {
            ext[i] = 2.0 * erster - x[rand - i].toDouble()
            ext[rand + x.size + i] = 2.0 * letzter - x[x.size - 2 - i].toDouble()
        }
        for (i in x.indices) ext[rand + i] = x[i].toDouble()

        val start = sosfiltZi(sos)
        for (s in start.indices) {
            start[s][0] *= ext[0]
            start[s][1] *= ext[0]
        }
        val vor = sosfilt(sos, ext, start)

        val zurueck = sosfiltZi(sos)
        val ende = vor[vor.size - 1]
        for (s in zurueck.indices) {
            zurueck[s][0] *= ende
            zurueck[s][1] *= ende
        }
        val rueck = sosfilt(sos, vor.reversedArray(), zurueck)
        return FloatArray(x.size) { i -> rueck[vor.size - 1 - (rand + i)].toFloat() }
    }

    private fun kausal(sos: Array<DoubleArray>, x: FloatArray): FloatArray {
        val zi = Array(sos.size) { DoubleArray(2) }
        val y = sosfilt(sos, DoubleArray(x.size) { x[it].toDouble() }, zi)
        return FloatArray(x.size) { y[it].toFloat() }
    }

    /** `sosfilt` (Direct Form II) mit Anfangszustand je Abschnitt; Abschnitte in Reihe. */
    private fun sosfilt(sos: Array<DoubleArray>, x: DoubleArray, zi: Array<DoubleArray>): DoubleArray {
        val y = DoubleArray(x.size)
        for (s in sos.indices) {
            val eingang = if (s == 0) x else y
            val k = sos[s]
            val b0 = k[0]
            val b1 = k[1]
            val b2 = k[2]
            val a1 = k[4]
            val a2 = k[5]
            var z1 = zi[s][0]
            var z2 = zi[s][1]
            for (n in eingang.indices) {
                val xn = eingang[n]
                val yn = b0 * xn + z1
                z1 = b1 * xn + z2 - a1 * yn
                z2 = b2 * xn - a2 * yn
                y[n] = yn
            }
            zi[s][0] = z1
            zi[s][1] = z2
        }
        return y
    }

    /** `sosfilt_zi`: Einschwingzustand je Abschnitt, skaliert mit dem Gleichgewinn. */
    private fun sosfiltZi(sos: Array<DoubleArray>): Array<DoubleArray> {
        val zi = Array(sos.size) { DoubleArray(2) }
        var skala = 1.0
        for (s in sos.indices) {
            val k = sos[s]
            val b0 = k[0]
            val b1 = k[1]
            val b2 = k[2]
            val a1 = k[4]
            val a2 = k[5]
            val yss = (b0 + b1 + b2) / (1.0 + a1 + a2)
            zi[s][0] = skala * (b1 + b2 - (a1 + a2) * yss)
            zi[s][1] = skala * (b2 - a2 * yss)
            skala *= yss
        }
        return zi
    }
}
