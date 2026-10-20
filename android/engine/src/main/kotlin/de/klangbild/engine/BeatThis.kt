package de.klangbild.engine

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import android.content.Context
import de.klangbild.core.Mel
import java.io.File
import java.nio.FloatBuffer
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

/** Beats und Downbeats in Sekunden. */
data class Schlaege(val beats: FloatArray, val downbeats: FloatArray) {
    val verfuegbar: Boolean get() = beats.isNotEmpty()
}

/**
 * Beat This! auf dem Gerät (M10): Mel-Spektrogramm aus [Mel], Chunk-Inferenz und
 * Peak-Nachbearbeitung wie in `mosynthkey/beat_this_cpp` (InferenceProcessor.cpp,
 * Postprocessor.cpp). Erwartet mono mit [Mel.RATE].
 */
class BeatThis private constructor(
    private val umgebung: OrtEnvironment,
    private val modell: OrtSession,
) {

    fun analysiere(mono: FloatArray): Schlaege {
        val spektrogramm = Mel.spektrogramm(mono)
        if (spektrogramm.isEmpty()) return Schlaege(FloatArray(0), FloatArray(0))
        val (beat, downbeat) = vorhersagen(spektrogramm)
        return nachbearbeiten(beat, downbeat)
    }

    /** Chunks mit Rand, Zusammenfuehrung "keep_first" (rueckwaerts, Raender verwerfen). */
    private fun vorhersagen(spektrogramm: Array<FloatArray>): Pair<FloatArray, FloatArray> {
        val laenge = spektrogramm.size
        val starts = ArrayList<Int>()
        var start = -RAND
        while (start < laenge - RAND) {
            starts.add(start)
            start += RAHMEN - 2 * RAND
        }
        if (laenge > RAHMEN - 2 * RAND) {
            starts[starts.size - 1] = (laenge - (RAHMEN - RAND)).coerceAtLeast(starts[starts.size - 1])
        }
        if (starts.isEmpty()) return FloatArray(0) to FloatArray(0)

        val beat = FloatArray(laenge) { -1000f }
        val downbeat = FloatArray(laenge) { -1000f }
        val bloecke = starts.map { block(spektrogramm, it, laenge) }

        for (i in starts.indices.reversed()) {
            val ab = starts[i]
            val (b, d) = bloecke[i]
            val von = if (b.size < 2 * RAND) 0 else RAND
            val bis = if (b.size < 2 * RAND) b.size else b.size - RAND
            for (j in von until bis) {
                val ziel = ab + j
                if (ziel in 0 until laenge) {
                    beat[ziel] = b[j]
                    downbeat[ziel] = d[j]
                }
            }
        }
        return beat to downbeat
    }

    private fun block(spektrogramm: Array<FloatArray>, start: Int, laenge: Int): Pair<FloatArray, FloatArray> {
        val von = max(0, start)
        val bis = min(start + RAHMEN, laenge)
        val links = max(0, -start)
        val rechts = max(0, min(RAND, start + RAHMEN - laenge))
        val rahmen = bis - von + links + rechts
        val daten = FloatArray(rahmen * Mel.N_MELS)
        for (i in 0 until bis - von) {
            System.arraycopy(spektrogramm[von + i], 0, daten, (links + i) * Mel.N_MELS, Mel.N_MELS)
        }
        OnnxTensor.createTensor(
            umgebung,
            FloatBuffer.wrap(daten),
            longArrayOf(1, rahmen.toLong(), Mel.N_MELS.toLong()),
        ).use { eingabe ->
            modell.run(mapOf("input_spectrogram" to eingabe)).use { ergebnis ->
                @Suppress("UNCHECKED_CAST")
                val b = (ergebnis.get("beat").orElseThrow().value as Array<FloatArray>)[0]
                @Suppress("UNCHECKED_CAST")
                val d = (ergebnis.get("downbeat").orElseThrow().value as Array<FloatArray>)[0]
                return b to d
            }
        }
    }

    /** Max-Pool 7, Schwelle 0, Dedupe 1 Rahmen, Downbeats auf den naechsten Beat. */
    private fun nachbearbeiten(beat: FloatArray, downbeat: FloatArray): Schlaege {
        val beats = spitzen(beat)
        val downs = spitzen(downbeat).map { d ->
            if (beats.isEmpty()) d else beats.minByOrNull { abs(it - d) } ?: d
        }.distinct().sorted()

        return Schlaege(
            FloatArray(beats.size) { beats[it] / FPS },
            FloatArray(downs.size) { downs[it] / FPS },
        )
    }

    private fun spitzen(logits: FloatArray): List<Int> {
        val gefunden = ArrayList<Int>()
        for (i in logits.indices) {
            var groesster = Float.NEGATIVE_INFINITY
            for (k in -3..3) {
                val j = i + k
                if (j in logits.indices) groesster = max(groesster, logits[j])
            }
            if (logits[i] == groesster && logits[i] > 0f) gefunden.add(i)
        }
        val ergebnis = ArrayList<Int>()
        if (gefunden.isEmpty()) return ergebnis
        var mittel = gefunden[0].toDouble()
        var anzahl = 1
        for (i in 1 until gefunden.size) {
            val naechster = gefunden[i]
            if (naechster - mittel <= 1.0) {
                anzahl++
                mittel += (naechster - mittel) / anzahl
            } else {
                ergebnis.add(mittel.roundToInt())
                mittel = naechster.toDouble()
                anzahl = 1
            }
        }
        ergebnis.add(mittel.roundToInt())
        return ergebnis
    }

    companion object {

        private const val RAHMEN = 1500
        private const val RAND = 6
        private const val FPS = Mel.RATE.toFloat() / Mel.HOP

        @Volatile
        private var instanz: BeatThis? = null

        /** Einmal je Prozess laden; das Modell liegt als Asset und wird bei Bedarf kopiert. */
        fun holen(context: Context): BeatThis {
            instanz?.let { return it }
            synchronized(this) {
                instanz?.let { return it }
                val datei = File(context.filesDir, "beat_this.onnx")
                if (!datei.isFile || datei.length() < 1_000_000) {
                    context.assets.open("beat_this.onnx").use { quelle ->
                        datei.outputStream().use { ziel -> quelle.copyTo(ziel) }
                    }
                }
                val umgebung = OrtEnvironment.getEnvironment()
                val optionen = OrtSession.SessionOptions().apply { setIntraOpNumThreads(2) }
                return BeatThis(umgebung, umgebung.createSession(datei.absolutePath, optionen)).also { instanz = it }
            }
        }
    }
}
