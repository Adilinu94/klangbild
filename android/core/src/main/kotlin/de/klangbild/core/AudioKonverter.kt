package de.klangbild.core

import java.lang.Math.rint
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.max

/**
 * Bausteine fuer den Decoder (BAUPLAN §4.3, M2): PCM-Bytes in float32 wandeln, auf Stereo
 * bringen und per linearer Interpolation auf die Zielrate ziehen (ADR-014: Android rechnet
 * linear, nicht mit soxr).
 *
 * Stereo ist immer interleaved (L,R,L,R,...).
 */
object AudioKonverter {

    /** PCM 16 bit little endian -> float32 (-1..1 weltengetreu, Teiler 32768). */
    fun pcm16ZuFloat(bytes: ByteArray): FloatArray {
        val werte = bytes.size / 2
        val aus = FloatArray(werte)
        val puffer = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
        for (i in 0 until werte) aus[i] = puffer.getShort().toFloat() / 32768.0f
        return aus
    }

    /** PCM float32 little endian -> float32-Array. */
    fun pcmFloatZuFloat(bytes: ByteArray): FloatArray {
        val werte = bytes.size / 4
        val aus = FloatArray(werte)
        val puffer = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
        for (i in 0 until werte) aus[i] = puffer.getFloat()
        return aus
    }

    /** Bringt ein Signal auf Stereo: Mono wird verdoppelt, mehr als zwei Kanaele auf die ersten zwei gekuerzt. */
    fun aufStereo(daten: FloatArray, channels: Int): FloatArray = when {
        channels <= 0 -> FloatArray(0)
        channels == 2 -> daten.copyOf()
        channels == 1 -> FloatArray(daten.size * 2) { daten[it / 2] }
        else -> {
            val frames = daten.size / channels
            FloatArray(frames * 2) { i -> daten[(i / 2) * channels + (i % 2)] }
        }
    }

    /**
     * Lineares Resampling wie `resample_linear`: `faktor = vonRate / aufRate`, Position je Frame
     * `i * faktor`, Rand konstant. Laenge: `max(1, round(Frames / faktor))`.
     */
    fun resampleLinear(daten: FloatArray, channels: Int, vonRate: Int, aufRate: Int): FloatArray {
        require(channels > 0) { "Kanalzahl muss positiv sein." }
        val frames = daten.size / channels
        if (frames == 0 || vonRate == aufRate || vonRate <= 0 || aufRate <= 0) return daten.copyOf()
        val faktor = vonRate.toDouble() / aufRate.toDouble()
        val laenge = max(1, rint(frames / faktor).toInt())
        val aus = FloatArray(laenge * channels)
        for (i in 0 until laenge) {
            val position = i * faktor
            val i0 = position.toInt()
            val frac = (position - i0).toFloat()
            val a = i0.coerceAtMost(frames - 1)
            val b = (a + 1).coerceAtMost(frames - 1)
            for (c in 0 until channels) {
                aus[i * channels + c] = daten[a * channels + c] * (1.0f - frac) + daten[b * channels + c] * frac
            }
        }
        return aus
    }
}
