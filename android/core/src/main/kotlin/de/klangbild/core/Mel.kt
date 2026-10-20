package de.klangbild.core

import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.exp
import kotlin.math.ln
import kotlin.math.log
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sqrt

/**
 * Mel-Spektrogramm fuer Beat This!, Parameter und Rechnung wie in
 * `mosynthkey/beat_this_cpp` (MelSpectrogram.cpp): mono 22,05 kHz, n_fft = 1024,
 * Hop 441, periodisches Hann-Fenster, Betragsspektrum durch sqrt(win), 128 Slaney-
 * Baender von 30 bis 11 000 Hz, danach log1p(1000 * Energie).
 */
object Mel {

    const val RATE = 22050
    const val N_FFT = 1024
    const val HOP = 441
    const val N_MELS = 128

    private const val F_MIN = 30.0
    private const val F_MAX = 11000.0
    private const val AMIN = 1e-10
    private const val LOG_FAKTOR = 1000.0
    private const val F_SP = 200.0 / 3.0
    private const val MIN_LOG_HZ = 1000.0
    private const val LOG_SCHRITT = 1.8562979903656263 / 27.0

    private val fenster = DoubleArray(N_FFT) { 0.5 * (1.0 - cos(2.0 * PI * it / N_FFT)) }
    private val bank: Array<DoubleArray> = baueBank()

    fun hzZuMel(hz: Double): Double {
        val minLogMel = MIN_LOG_HZ / F_SP
        return if (hz >= MIN_LOG_HZ) minLogMel + ln(hz / MIN_LOG_HZ) / LOG_SCHRITT else hz / F_SP
    }

    fun melZuHz(mel: Double): Double {
        val minLogMel = MIN_LOG_HZ / F_SP
        return if (mel >= minLogMel) MIN_LOG_HZ * exp(LOG_SCHRITT * (mel - minLogMel)) else F_SP * mel
    }

    private fun baueBank(): Array<DoubleArray> {
        val melMin = hzZuMel(F_MIN)
        val melMax = hzZuMel(F_MAX)
        val hz = DoubleArray(N_MELS + 2) { melZuHz(melMin + (melMax - melMin) * it / (N_MELS + 1)) }
        val bank = Array(N_FFT / 2 + 1) { DoubleArray(N_MELS) }
        for (k in 0..N_FFT / 2) {
            val freq = k * RATE.toDouble() / N_FFT
            for (m in 0 until N_MELS) {
                val links = hz[m]
                val mitte = hz[m + 1]
                val rechts = hz[m + 2]
                val steigt = if (mitte != links) (freq - links) / (mitte - links) else 0.0
                val faellt = if (rechts != mitte) (rechts - freq) / (rechts - mitte) else 0.0
                bank[k][m] = max(0.0, min(steigt, faellt))
            }
        }
        return bank
    }

    /** [frames][128]; leeres Ergebnis bei weniger als 513 Abtastwerten. */
    fun spektrogramm(mono: FloatArray): Array<FloatArray> {
        val halb = N_FFT / 2
        if (mono.size <= halb) return emptyArray()

        val gepolstert = FloatArray(mono.size + 2 * halb)
        for (i in 0 until halb) gepolstert[i] = mono[halb - i]
        for (i in mono.indices) gepolstert[halb + i] = mono[i]
        for (i in 1..halb) gepolstert[halb + mono.size + i - 1] = mono[mono.size - 1 - i]

        val frames = (gepolstert.size - N_FFT) / HOP + 1
        val norm = sqrt(N_FFT.toDouble())
        val ausgabe = Array(frames) { FloatArray(N_MELS) }
        val rahmen = DoubleArray(N_FFT)

        for (f in 0 until frames) {
            val start = f * HOP
            for (i in 0 until N_FFT) rahmen[i] = gepolstert[start + i] * fenster[i]
            val leistung = Fft.leistung(rahmen)
            val staerke = DoubleArray(N_FFT / 2 + 1) { sqrt(leistung[it]) / norm }
            for (m in 0 until N_MELS) {
                var energie = 0.0
                for (k in 0..N_FFT / 2) energie += staerke[k] * bank[k][m]
                ausgabe[f][m] = ln(1.0 + LOG_FAKTOR * max(energie, AMIN)).toFloat()
            }
        }
        return ausgabe
    }
}
