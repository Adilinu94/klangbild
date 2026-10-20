package de.klangbild.core

import kotlin.math.PI
import kotlin.math.log10
import kotlin.math.max
import kotlin.math.pow
import kotlin.math.tan

/**
 * Integrierte Lautheit nach ITU-R BS.1770-4 (Port von `lufs.py`, ADR-012).
 *
 * K-Gewichtung aus zwei Biquads (Höhen-Shelf + Hochpass), Koeffizienten je Abtastrate über
 * die bilineare Transformation (wie libebur128). 400-ms-Blöcke mit 100-ms-Schritt, absolute
 * Torschwelle −70 LUFS, relative Schwelle 10 dB unter dem Vorschnitt, Offset −0,691 dB.
 * Stereo: Blockleistungen je Kanal summieren (Gewicht 1,0).
 *
 * Der True Peak (4-fach überabgetastet mit soxr) fehlt hier noch; die Golden-Fälle prüfen
 * vorerst nur `integrated`.
 */
object Lautheit {

    private const val BLOCK_SEKUNDEN = 0.400
    private const val SCHRITT_SEKUNDEN = 0.100
    private const val ABSOLUT = -70.0
    private const val RELATIV = -10.0
    private const val OFFSET = -0.691

    private const val SHELF_F0 = 1681.974450955533
    private const val SHELF_G = 3.999843853973347
    private const val SHELF_Q = 0.7071752369554196
    private const val HIGHPASS_F0 = 38.13547087602444
    private const val HIGHPASS_Q = 0.5003270373238773

    private fun shelf(rate: Int): Pair<DoubleArray, DoubleArray> {
        val k = tan(PI * SHELF_F0 / rate)
        val vh = 10.0.pow(SHELF_G / 20.0)
        val vb = vh.pow(0.4996667741545416)
        val a0 = 1.0 + k / SHELF_Q + k * k
        val b = doubleArrayOf(
            (vh + vb * k / SHELF_Q + k * k) / a0,
            2.0 * (k * k - vh) / a0,
            (vh - vb * k / SHELF_Q + k * k) / a0,
        )
        val a = doubleArrayOf(1.0, 2.0 * (k * k - 1.0) / a0, (1.0 - k / SHELF_Q + k * k) / a0)
        return b to a
    }

    private fun highpass(rate: Int): Pair<DoubleArray, DoubleArray> {
        val k = tan(PI * HIGHPASS_F0 / rate)
        val a0 = 1.0 + k / HIGHPASS_Q + k * k
        val b = doubleArrayOf(1.0, -2.0, 1.0)
        val a = doubleArrayOf(1.0, 2.0 * (k * k - 1.0) / a0, (1.0 - k / HIGHPASS_Q + k * k) / a0)
        return b to a
    }

    internal fun shelfOeffentlich(rate: Int): Pair<DoubleArray, DoubleArray> = shelf(rate)
    internal fun highpassOeffentlich(rate: Int): Pair<DoubleArray, DoubleArray> = highpass(rate)

    /** Kausales Biquad (Direct Form I) wie `lfilter` im Prototyp. */
    private fun filter(x: DoubleArray, b: DoubleArray, a: DoubleArray): DoubleArray {
        val y = DoubleArray(x.size)
        var x1 = 0.0
        var x2 = 0.0
        var y1 = 0.0
        var y2 = 0.0
        for (i in x.indices) {
            val x0 = x[i]
            val y0 = b[0] * x0 + b[1] * x1 + b[2] * x2 - a[1] * y1 - a[2] * y2
            y[i] = y0
            x2 = x1
            x1 = x0
            y2 = y1
            y1 = y0
        }
        return y
    }

    fun kGewichten(x: DoubleArray, rate: Int): DoubleArray {
        val (b1, a1) = shelf(rate)
        val (b2, a2) = highpass(rate)
        return filter(filter(x, b1, a1), b2, a2)
    }

    private fun blockMittel(x: DoubleArray, rate: Int): DoubleArray {
        var block = (BLOCK_SEKUNDEN * rate).toInt()
        var schritt = (SCHRITT_SEKUNDEN * rate).toInt()
        if (x.size < block) {
            block = x.size
            schritt = max(1, block / 4)
        }
        if (block <= 0) return DoubleArray(0)

        val kum = DoubleArray(x.size + 1)
        for (i in x.indices) kum[i + 1] = kum[i] + x[i] * x[i]
        val anzahl = 1 + max(0, x.size - block) / schritt
        return DoubleArray(anzahl) { i ->
            val s = i * schritt
            (kum[s + block] - kum[s]) / block
        }
    }

    private fun lufs(mittel: Double): Double =
        if (mittel <= 0.0) Double.NEGATIVE_INFINITY else OFFSET + 10.0 * log10(mittel)

    /** Integrierte Lautheit eines Mono-Signals. */
    fun integriert(mono: DoubleArray, rate: Int): Double {
        if (mono.isEmpty()) return Double.NEGATIVE_INFINITY
        return ausBloecken(blockMittel(kGewichten(mono, rate), rate))
    }

    /** Integrierte Lautheit mehrerer Kanäle (Stereo: Gewicht 1,0 je Kanal). */
    fun integriert(kanaele: Array<DoubleArray>, rate: Int): Double {
        if (kanaele.isEmpty() || kanaele[0].isEmpty()) return Double.NEGATIVE_INFINITY
        val summe = DoubleArray(blockMittel(kGewichten(kanaele[0], rate), rate).size)
        for (k in kanaele.indices) {
            val m = blockMittel(kGewichten(kanaele[k], rate), rate)
            for (i in summe.indices) summe[i] += m[i]
        }
        return ausBloecken(summe)
    }

    private fun ausBloecken(bloecke: DoubleArray): Double {
        if (bloecke.isEmpty()) return Double.NEGATIVE_INFINITY
        val lautheiten = DoubleArray(bloecke.size) { lufs(bloecke[it]) }
        val absolut = BooleanArray(bloecke.size) { lautheiten[it] > ABSOLUT }
        if (absolut.none { it }) return Double.NEGATIVE_INFINITY

        var summe = 0.0
        var anzahl = 0
        for (i in bloecke.indices) {
            if (absolut[i]) {
                summe += bloecke[i]
                anzahl++
            }
        }
        val vorschnitt = lufs(summe / anzahl)

        var summe2 = 0.0
        var anzahl2 = 0
        for (i in bloecke.indices) {
            if (absolut[i] && lautheiten[i] > vorschnitt + RELATIV) {
                summe2 += bloecke[i]
                anzahl2++
            }
        }
        return if (anzahl2 == 0) Double.NEGATIVE_INFINITY else lufs(summe2 / anzahl2)
    }

    /** Gating der Blockmittelwerte (oeffentlich fuer den Sammler und Tests). */
    fun ausBlockwerten(bloecke: DoubleArray): Double = ausBloecken(bloecke)

    /**
     * Integrierte Lautheit direkt aus dem PCM-Cache (Stereo, 44,1 kHz), blockweise gelesen:
     * der Speicher bleibt bei einem Block, der Filterzustand laeuft mit.
     */
    fun ausCache(pcm: PcmDatei, rate: Int = 44100, blockFrames: Int = 44100): Double {
        val links = LautheitSammler(rate)
        val rechts = LautheitSammler(rate)
        val gesamt = pcm.frames()
        var start = 0
        while (start < gesamt) {
            val anzahl = minOf(blockFrames, gesamt - start)
            val stereo = pcm.lese(start, anzahl)
            links.hinzuBlock(stereo, 0)
            rechts.hinzuBlock(stereo, 1)
            start += anzahl
        }
        val bl = links.blockwerte()
        val br = rechts.blockwerte()
        val summe = DoubleArray(minOf(bl.size, br.size))
        for (i in summe.indices) summe[i] = bl[i] + br[i]
        return ausBloecken(summe)
    }
}

/**
 * K-Gewichtung und 400-ms-Bloecke fuer ein Signal, das stueckweise ankommt. Haelt den
 * Filterzustand und einen Ringpuffer der letzten Blocklaenge; nach dem ersten vollen Block
 * kommt alle 100 ms ein Mittelwert dazu. Damit laesst sich die Lautheit ohne das ganze
 * Signal im Speicher rechnen.
 */
class LautheitSammler(rate: Int) {

    private val blockLaenge = max(1, (0.400 * rate).toInt())
    private val schritt = max(1, (0.100 * rate).toInt())
    private val ring = DoubleArray(blockLaenge)
    private var position = 0
    private var summe = 0.0
    private var anzahl = 0
    private val bloecke = ArrayList<Double>()

    private val b1: DoubleArray
    private val a1: DoubleArray
    private val b2: DoubleArray
    private val a2: DoubleArray

    private val zustand1 = DoubleArray(4)
    private val zustand2 = DoubleArray(4)

    init {
        val shelf = Lautheit.shelfOeffentlich(rate)
        b1 = shelf.first
        a1 = shelf.second
        val hoch = Lautheit.highpassOeffentlich(rate)
        b2 = hoch.first
        a2 = hoch.second
    }

    /** Ein Block Stereo (interleaved) fuer Kanal [kanal]. */
    fun hinzuBlock(stereo: FloatArray, kanal: Int) {
        var i = kanal
        while (i < stereo.size) {
            hinzu(stereo[i].toDouble())
            i += 2
        }
    }

    fun hinzu(wert: Double) {
        val gefiltert = filtere(b2, a2, filtere(b1, a1, wert, zustand1), zustand2)
        val quadrat = gefiltert * gefiltert
        summe += quadrat - ring[position]
        ring[position] = quadrat
        position++
        if (position == blockLaenge) position = 0
        anzahl++
        if (anzahl >= blockLaenge && (anzahl - blockLaenge) % schritt == 0) {
            bloecke.add(summe / blockLaenge)
        }
    }

    fun blockwerte(): DoubleArray = bloecke.toDoubleArray()

    fun ergebnis(): Double = Lautheit.ausBlockwerten(blockwerte())

    private fun filtere(b: DoubleArray, a: DoubleArray, x0: Double, s: DoubleArray): Double {
        val y0 = b[0] * x0 + b[1] * s[0] + b[2] * s[1] - a[1] * s[2] - a[2] * s[3]
        s[1] = s[0]
        s[0] = x0
        s[3] = s[2]
        s[2] = y0
        return y0
    }
}
