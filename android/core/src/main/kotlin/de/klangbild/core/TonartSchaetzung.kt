package de.klangbild.core

import kotlin.math.abs
import kotlin.math.log2
import kotlin.math.max
import kotlin.math.sqrt

/**
 * Tonart-Schaetzung aus Chroma und Key-Profilen (Port von `keyestimate.py`, ADR-012).
 *
 * Chroma: FFT 8192, Hop 2048, 65–2100 Hz, jeder Rahmen auf Summe 1 normiert (entkoppelt
 * die Tonart vom Lautstaerkeverlauf), dann Mittel ueber alle Rahmen. Die Tonart ist die
 * hoechste Pearson-Korrelation zwischen Chroma und einem der 24 rotierten Profile.
 */
object TonartSchaetzung {

    val KRUMHANSL_DUR = doubleArrayOf(6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88)
    val KRUMHANSL_MOLL = doubleArrayOf(6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17)
    val AARDEN_DUR = doubleArrayOf(
        17.7661, 0.1456, 14.9265, 0.1602, 19.8722, 11.7655, 0.2912,
        25.0960, 0.1459, 9.0306, 0.3200, 10.9661,
    )
    val AARDEN_MOLL = doubleArrayOf(
        18.2648, 0.7376, 14.1370, 16.1760, 0.5710, 17.5384, 1.9588,
        15.0119, 0.7911, 16.8725, 4.3542, 11.8864,
    )
    val TEMPERLEY_DUR = doubleArrayOf(5.0, 2.0, 3.5, 2.0, 4.5, 4.0, 2.0, 4.5, 2.0, 3.5, 1.5, 4.0)
    val TEMPERLEY_MOLL = doubleArrayOf(5.0, 2.0, 3.5, 4.5, 2.0, 4.0, 2.0, 4.5, 3.5, 2.0, 3.5, 1.5)

    val ENSEMBLE_DUR = mittelProfil(KRUMHANSL_DUR, AARDEN_DUR, TEMPERLEY_DUR)
    val ENSEMBLE_MOLL = mittelProfil(KRUMHANSL_MOLL, AARDEN_MOLL, TEMPERLEY_MOLL)

    val TONNAMEN = arrayOf("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")

    private val CAMELOT_DUR = mapOf(
        "C" to "8B", "G" to "9B", "D" to "10B", "A" to "11B", "E" to "12B", "B" to "1B",
        "F#" to "2B", "C#" to "3B", "G#" to "4B", "D#" to "5B", "A#" to "6B", "F" to "7B",
    )
    private val CAMELOT_MOLL = mapOf(
        "A" to "8A", "E" to "9A", "B" to "10A", "F#" to "11A", "C#" to "12A", "G#" to "1A",
        "D#" to "2A", "A#" to "3A", "F" to "4A", "C" to "5A", "G" to "6A", "D" to "7A",
    )

    data class Tonart(val name: String, val camelot: String, val vertrauen: Double, val punkte: Double)

    private fun mittelProfil(vararg profile: DoubleArray): DoubleArray {
        val mittel = DoubleArray(profile.size) { i -> profile[i].average() }
        return DoubleArray(12) { k -> profile.indices.sumOf { profile[it][k] / mittel[it] } }
    }

    /** Mittleres Chroma ueber das Signal (`keyestimate.chroma`). */
    fun chroma(signal: FloatArray, rate: Int, frame: Int = 8192, hop: Int = 2048): DoubleArray {
        val x = if (signal.size < frame) signal.copyOf(frame) else signal
        val fenster = FloatArray(frame) { (0.5 - 0.5 * kotlin.math.cos(2.0 * Math.PI * it / (frame - 1))).toFloat() }
        val anzahl = max(1, 1 + (x.size - frame) / hop)
        val summe = DoubleArray(12)
        val rahmen = DoubleArray(frame)

        for (index in 0 until anzahl) {
            val start = index * hop
            for (i in 0 until frame) {
                val wert = if (start + i < x.size) x[start + i] else 0f
                rahmen[i] = (wert * fenster[i]).toDouble()
            }
            val leistung = Fft.leistung(rahmen)

            val beitrag = DoubleArray(12)
            for (k in 0..frame / 2) {
                val f = k * rate.toDouble() / frame
                if (f < 65.0 || f > 2100.0) continue
                val midi = 69.0 + 12.0 * log2(max(f, 1e-9) / 440.0)
                var klasse = Math.rint(midi).toInt() % 12
                if (klasse < 0) klasse += 12
                beitrag[klasse] += leistung[k]
            }
            val teiler = beitrag.sum()
            if (teiler > 0.0) for (k in 0 until 12) beitrag[k] /= teiler
            for (k in 0 until 12) summe[k] += beitrag[k]
        }

        val gesamt = summe.sum()
        if (gesamt <= 0.0) return DoubleArray(12) { 1.0 / 12.0 }
        for (k in 0 until 12) summe[k] /= gesamt
        return summe
    }

    /** Tonart und Modus; Standard ist das Ensemble-Profil. */
    fun schaetzen(signal: FloatArray, rate: Int, profil: String = "ensemble"): Tonart =
        schaetzen(chroma(signal, rate), profil)

    /**
     * Tonart aus einem bereits berechneten Chroma. Damit kann der Aufrufer das Chroma
     * blockweise aus dem PCM-Cache sammeln (siehe [chromaAusCache]), ohne den ganzen
     * Titel als float-Array zu halten.
     */
    fun schaetzen(chroma: DoubleArray, profil: String = "ensemble"): Tonart {
        val (dur, moll) = when (profil) {
            "krumhansl" -> KRUMHANSL_DUR to KRUMHANSL_MOLL
            "aarden" -> AARDEN_DUR to AARDEN_MOLL
            "temperley" -> TEMPERLEY_DUR to TEMPERLEY_MOLL
            else -> ENSEMBLE_DUR to ENSEMBLE_MOLL
        }

        val ergebnisse = ArrayList<Triple<Double, String, String>>(24)
        for (halbtoene in TONNAMEN.indices) {
            val name = TONNAMEN[halbtoene]
            ergebnisse.add(Triple(korrelation(chroma, rotiert(dur, halbtoene)), name, CAMELOT_DUR.getValue(name)))
            ergebnisse.add(
                Triple(korrelation(chroma, rotiert(moll, halbtoene)), "${name}m", CAMELOT_MOLL.getValue(name)),
            )
        }
        ergebnisse.sortWith(
            compareByDescending<Triple<Double, String, String>> { it.first }.thenByDescending { it.second },
        )
        val bester = ergebnisse[0]
        val zweiter = ergebnisse[1]
        val abstand = max(0.0, bester.first - zweiter.first)
        return Tonart(
            name = bester.second,
            camelot = bester.third,
            vertrauen = minOf(1.0, abstand / 0.5),
            punkte = bester.first,
        )
    }

    /**
     * Chroma direkt aus dem PCM-Cache, Rahmen fuer Rahmen (Speicher bleibt bei einem
     * Rahmen). Gleiche Parameter wie [chroma]; der Cache ist Stereo/44,1 kHz.
     */
    fun chromaAusCache(pcm: PcmDatei, rate: Int = 44100, frame: Int = 8192, hop: Int = 2048): DoubleArray {
        val frames = pcm.frames()
        if (frames <= 0) return DoubleArray(12) { 1.0 / 12.0 }
        val fenster = FloatArray(frame) { (0.5 - 0.5 * kotlin.math.cos(2.0 * Math.PI * it / (frame - 1))).toFloat() }
        val anzahl = if (frames < frame) 1 else 1 + (frames - frame) / hop
        val summe = DoubleArray(12)
        val rahmen = DoubleArray(frame)

        for (index in 0 until anzahl) {
            val stereo = pcm.lese(index * hop, frame)
            for (i in 0 until frame) {
                val mono = (stereo[2 * i] + stereo[2 * i + 1]) / 2f
                rahmen[i] = (mono * fenster[i]).toDouble()
            }
            val leistung = Fft.leistung(rahmen)
            val beitrag = DoubleArray(12)
            for (k in 0..frame / 2) {
                val f = k * rate.toDouble() / frame
                if (f < 65.0 || f > 2100.0) continue
                val midi = 69.0 + 12.0 * log2(max(f, 1e-9) / 440.0)
                var klasse = Math.rint(midi).toInt() % 12
                if (klasse < 0) klasse += 12
                beitrag[klasse] += leistung[k]
            }
            val teiler = beitrag.sum()
            if (teiler > 0.0) for (k in 0 until 12) beitrag[k] /= teiler
            for (k in 0 until 12) summe[k] += beitrag[k]
        }

        val gesamt = summe.sum()
        if (gesamt <= 0.0) return DoubleArray(12) { 1.0 / 12.0 }
        for (k in 0 until 12) summe[k] /= gesamt
        return summe
    }

    /** Nachbarn auf dem Camelot-Rad (gleiche Nummer ±1 und Moduswechsel). */
    fun camelotNachbarn(code: String): Set<String> {
        if (code.length < 2 || !code.dropLast(1).all { it.isDigit() }) return setOf(code)
        val nummer = code.dropLast(1).toInt()
        val modus = code.last()
        val anderer = if (modus == 'B') 'A' else 'B'
        val nachbarn = HashSet<String>()
        for (abstand in -1..1) {
            val n = ((nummer - 1 + abstand) % 12 + 12) % 12 + 1
            nachbarn.add("$n$modus")
        }
        nachbarn.add("$nummer$anderer")
        return nachbarn
    }

    private fun rotiert(profil: DoubleArray, halbtoene: Int): DoubleArray =
        DoubleArray(12) { i -> profil[((i - halbtoene) % 12 + 12) % 12] }

    private fun korrelation(a: DoubleArray, b: DoubleArray): Double {
        val am = a.average()
        val bm = b.average()
        var zaehler = 0.0
        var na = 0.0
        var nb = 0.0
        for (i in a.indices) {
            val x = a[i] - am
            val y = b[i] - bm
            zaehler += x * y
            na += x * x
            nb += y * y
        }
        val nenner = sqrt(na * nb)
        return if (nenner <= 0.0) 0.0 else zaehler / nenner
    }

    /** Rundungshelfer fuer Tests: Abstand zweier Tonarten im Camelot-Rad. */
    fun camelotAbstand(a: String, b: String): Int {
        if (a == b) return 0
        val na = a.dropLast(1).toIntOrNull() ?: return 99
        val nb = b.dropLast(1).toIntOrNull() ?: return 99
        val d = abs(na - nb)
        return minOf(d, 12 - d)
    }
}
