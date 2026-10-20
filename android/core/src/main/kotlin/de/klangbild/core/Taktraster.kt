package de.klangbild.core

import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.floor
import kotlin.math.max
import kotlin.math.round
import kotlin.math.sin

/**
 * Das Taktraster eines Songs (Port von `uebergang.regulaer`/`uebergang.taktraster`).
 *
 * Ein Raster je Song für Profil, Regie, Backen und Anzeige: Tempo aus der BPM, die Eins aus
 * der Mehrheit der Downbeats, die Lage im Schlag als Modus (nicht Mittel, damit Off-Beat-
 * Abschnitte die Lage nicht zwischen die Schläge ziehen). Lokal folgt das Raster langsamer
 * Drift über den Median der Abweichung in ±[DRIFT_S]. Hängt nur von den Downbeats ab;
 * [bisS] verlängert nur.
 */
object Taktraster {

    const val DRIFT_S = 16.0

    /** Raster ohne Fein-Anker. Index 0 ist der erste erkannte Downbeat (darf minimal < 0 sein). */
    fun regulaer(downbeats: List<Double>, bpm: Double, bisS: Double): DoubleArray {
        val periode = if (bpm > 0.0) 240.0 / bpm else 2.0
        if (downbeats.isEmpty()) {
            val punkte = (max(bisS, periode) / periode).toInt() + 2
            return DoubleArray(punkte) { periode * it }
        }
        val d = downbeats.toDoubleArray()
        val schlag = periode / 4.0

        val winkel = DoubleArray(d.size) { i ->
            val w = 2.0 * PI * d[i] / schlag
            atan2(sin(w), cos(w))
        }
        val h = IntArray(16)
        for (a in winkel) {
            val fach = floor((a + PI) / (2.0 * PI) * 16.0).toInt().coerceIn(0, 15)
            h[fach]++
        }
        var bester = 0
        var besteZahl = -1
        for (i in 0 until 16) {
            val zahl = h[i] + h[(i + 15) % 16] + h[(i + 1) % 16]
            if (zahl > besteZahl) {
                besteZahl = zahl
                bester = i
            }
        }
        val c = -PI + (bester + 0.5) * PI / 8.0

        var summeX = 0.0
        var summeY = 0.0
        var anzahl = 0
        for (a in winkel) {
            if (abs(winkelAbstand(a - c)) <= PI / 4.0) {
                summeX += cos(a)
                summeY += sin(a)
                anzahl++
            }
        }
        val lage = if (anzahl == 0) 0.0 else atan2(summeY / anzahl, summeX / anzahl) / (2.0 * PI) * schlag

        val zaehler = IntArray(4)
        for (x in d) {
            val k = mod(round((x - lage) / schlag), 4.0).toInt()
            zaehler[k]++
        }
        val eins = zaehler.indices.maxByOrNull { zaehler[it] } ?: 0
        val phase = lage + eins * schlag
        val start = phase + periode * round((d[0] - phase) / periode)
        val punkte = (max(bisS - start, periode) / periode).toInt() + 2
        val t = DoubleArray(punkte) { start + periode * it }

        val rest = DoubleArray(d.size) { i -> mod(d[i] - lage + schlag / 2.0, schlag) - schlag / 2.0 }
        val auf = BooleanArray(d.size) { abs(rest[it]) < schlag / 4.0 }
        val knotenX = ArrayList<Double>()
        val knotenY = ArrayList<Double>()
        for (i in d.indices) {
            if (!auf[i]) continue
            val nahe = (0 until d.size).filter { auf[it] && abs(d[it] - d[i]) <= DRIFT_S }
            if (nahe.size < 3) continue
            knotenX.add(d[i])
            knotenY.add(median(nahe.map { rest[it] }))
        }
        if (knotenX.isNotEmpty()) {
            val kx = knotenX.toDoubleArray()
            val ky = knotenY.toDoubleArray()
            for (i in t.indices) t[i] += interp(t[i], kx, ky)
        }
        return t
    }

    /** Raster plus Fein-Anker (`anker.fein`: lokale Kick-Lage je Abschnitt). */
    fun taktraster(
        downbeats: List<Double>,
        bpm: Double,
        bisS: Double,
        fein: List<List<Double>> = emptyList(),
    ): DoubleArray {
        val t = regulaer(downbeats, bpm, bisS)
        if (fein.size < 2) return t
        val kx = fein.map { it[0] }.toDoubleArray()
        val ky = fein.map { it[1] }.toDoubleArray()
        for (i in t.indices) t[i] += interp(t[i], kx, ky)
        return t
    }

    private fun winkelAbstand(a: Double): Double = atan2(sin(a), cos(a))

    /** `np.mod` (abgerundet), nicht Kotlins `%` (Rest mit Vorzeichen). */
    private fun mod(a: Double, m: Double): Double = a - m * floor(a / m)

    private fun median(werte: List<Double>): Double {
        val s = werte.sorted()
        return if (s.size % 2 == 1) s[s.size / 2] else (s[s.size / 2 - 1] + s[s.size / 2]) / 2.0
    }

    /** `np.interp`: ausserhalb der Stuetzstellen konstant. */
    private fun interp(x: Double, kx: DoubleArray, ky: DoubleArray): Double {
        if (x <= kx[0]) return ky[0]
        if (x >= kx.last()) return ky.last()
        var i = 0
        while (i + 1 < kx.size && kx[i + 1] < x) i++
        val f = (x - kx[i]) / (kx[i + 1] - kx[i])
        return ky[i] + f * (ky[i + 1] - ky[i])
    }
}
