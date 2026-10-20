package de.klangbild.core

import kotlin.math.abs
import kotlin.math.exp
import kotlin.math.floor
import kotlin.math.max
import kotlin.math.min

/**
 * Titel-Profil (Port von `prototyp/klangbild/profil.py`): jeder Song Takt fuer Takt vermessen.
 *
 * Je Takt Pegel in Bass/Mitten/Hoehen (dB), Gesamtpegel und optional Pegel je Stem. Daraus
 * leitet die Regie Gesang, Drums, Bass, Dichte, Phrasenversatz, Drops, Phrasengrenzen,
 * Etiketten und das Energielevel ab. Abgeleitete Reihen werden einmal gerechnet (die Regie
 * fragt sie tausendfach ab).
 */
class Profil(
    val takte: DoubleArray,
    val baender: Array<DoubleArray>,
    val gesamt: DoubleArray,
    val stems: Map<String, DoubleArray>?,
    val rasterOk: BooleanArray,
    val dauer: Double,
    val chroma: Array<DoubleArray>? = null,
) {
    val n: Int get() = takte.size

    private val memo = HashMap<String, Any?>()

    @Suppress("UNCHECKED_CAST")
    private fun <T> einmal(schluessel: String, rechnen: () -> T): T {
        if (memo.containsKey(schluessel)) return memo[schluessel] as T
        val wert = rechnen()
        memo[schluessel] = wert
        return wert
    }

    /** Gesang je Takt aktiv (0/1); null = unbekannt (keine Stems). */
    fun gesang(): DoubleArray? = einmal("gesang") {
        val s = stems ?: return@einmal null
        val v = s.getValue("vocals")
        val grenze = percentile(v, 95.0) - 20.0
        DoubleArray(n) { if (v[it] - gesamt[it] > -25.0 && v[it] > grenze) 1.0 else 0.0 }
    }

    /** Drums/Kick je Takt aktiv (0/1); ohne Stems aus dem Bassband geschaetzt. */
    fun drums(): DoubleArray = einmal("drums") {
        val s = stems
        if (s != null) {
            val d = s.getValue("drums")
            val grenze = percentile(d, 95.0) - 18.0
            DoubleArray(n) { if (d[it] - gesamt[it] > -12.0 && d[it] > grenze) 1.0 else 0.0 }
        } else {
            val b = tiefband()
            val grenze = percentile(b, 90.0) - 9.0
            DoubleArray(n) { if (b[it] > grenze) 1.0 else 0.0 }
        }
    }

    /** Bassline/Tiefbass je Takt aktiv (0/1). */
    fun bass(): DoubleArray = einmal("bass") {
        val b = stems?.get("bass") ?: tiefband()
        val grenze = percentile(b, 90.0) - 10.0
        DoubleArray(n) { if (b[it] > grenze) 1.0 else 0.0 }
    }

    /** 0..1: wie viel gleichzeitig spielt (Anteil aktiver Stems bzw. Baender). */
    fun dichte(): DoubleArray = einmal("dichte") {
        val s = stems
        if (s != null) {
            val reihen = s.map { (_, v) ->
                val grenze = percentile(v, 95.0) - 15.0
                DoubleArray(n) { if (v[it] > grenze) 1.0 else 0.0 }
            }
            DoubleArray(n) { i -> reihen.sumOf { it[i] } / reihen.size }
        } else {
            val spitze = DoubleArray(3) { c -> percentile(DoubleArray(n) { baender[it][c] }, 95.0) }
            DoubleArray(n) { i -> (0 until 3).count { baender[i][it] > spitze[it] - 12.0 } / 3.0 }
        }
    }

    /** Phrasenversatz 0..7: Phrasen beginnen bei Takt 8q - s. */
    fun versatz(): Int = einmal("versatz") {
        if (n < 4 * PHRASE) return@einmal 0
        val reihen = mutableListOf(gesamt)
        if (stems != null) {
            reihen.add(stems.getValue("bass"))
            reihen.add(stems.getValue("drums"))
        } else {
            reihen.add(tiefband())
        }
        val sprung = DoubleArray(n)
        for (x in reihen) {
            val c = cumsum0(x)
            for (k in 4..n - 4) {
                val d = (c[k + 4] - c[k]) - (c[k] - c[k - 4])
                sprung[k] += d * d / 16.0
            }
        }
        val wert = DoubleArray(PHRASE) { o -> meanStride(sprung, o) }
        var o = 0
        for (i in 1 until PHRASE) if (wert[i] > wert[o]) o = i
        if (wert[o] < 1.3 * wert[0]) o = 0   // kein klarer Versatz: beim Raster ab Takt 0 bleiben
        (PHRASE - o) % PHRASE
    }

    /** 1-3 Drop-Takte: wo Bass und Drums nach einem leiseren Teil voll einsetzen. */
    fun drops(): List<Int> = einmal("drops") {
        if (n < 16) return@einmal emptyList<Int>()
        val reihen = mutableListOf(gesamt)
        if (stems != null) {
            reihen.add(stems.getValue("bass"))
            reihen.add(stems.getValue("drums"))
        } else {
            reihen.add(tiefband())
        }
        val k = (4..n - 4).toList()
        val sprung = DoubleArray(k.size)
        for (x in reihen) {
            val c = cumsum0(x)
            k.forEachIndexed { idx, kk ->
                sprung[idx] += ((c[kk + 4] - c[kk]) - (c[kk] - c[kk - 4])) / 4.0
            }
        }
        val cb = cumsum0(bass())
        val cd = cumsum0(drums())
        val voll = BooleanArray(k.size) { idx ->
            (cb[k[idx] + 4] - cb[k[idx]]) >= 3.0 && (cd[k[idx] + 4] - cd[k[idx]]) >= 3.0
        }
        val reihenfolge = sprung.indices.sortedWith(compareByDescending { sprung[it] })
        val auswahl = mutableListOf<Int>()
        var oben: Double? = null
        for (m in reihenfolge) {
            if (sprung[m] < DROP_SPRUNG_DB || (oben != null && sprung[m] < DROP_REL * oben)) break
            if (!voll[m]) continue
            if (oben == null) oben = sprung[m]
            if (auswahl.all { abs(k[m] - it) >= DROP_ABSTAND }) auswahl.add(k[m])
            if (auswahl.size == 3) break
        }
        auswahl.map { dropGenau(it) }.sorted()
    }

    /** Erster voller Drop-Takt ab k (bis k+2). */
    private fun dropGenau(k: Int): Int {
        val bass = stems?.get("bass") ?: tiefband()
        val drums = stems?.get("drums") ?: gesamt
        val ende = min(n, k + 5)
        if (ende - k < 3) return k
        val rb = median(bass.copyOfRange(k + 1, ende)) - 4.0
        val rd = median(drums.copyOfRange(k + 1, ende)) - 4.0
        for (t in k until min(n, k + 3)) {
            if (bass[t] >= rb && drums[t] >= rd) return t
        }
        return k
    }

    /** Phrasenanfaenge (aufsteigend, ab 0): 8er-Raster ab jedem Drop. */
    fun grenzen(): List<Int> = einmal("grenzen") {
        val d = drops()
        val g = sortedSetOf<Int>()
        g.add(0)
        if (d.isNotEmpty()) {
            var x = d[0]
            while (x > 0) {
                g.add(x)
                x -= PHRASE
            }
            val paare = d + n
            for (i in d.indices) {
                var v = paare[i]
                while (v < paare[i + 1]) {
                    g.add(v)
                    v += PHRASE
                }
            }
        } else {
            for (q in 1..n / PHRASE + 1) g.add(q * PHRASE - versatz())
        }
        val gefiltert = g.filter { it in 0 until n }
        val fest = setOf(0) + d
        val aus = mutableListOf<Int>()
        for ((i, x) in gefiltert.withIndex()) {
            val naechste = if (i + 1 < gefiltert.size) gefiltert[i + 1] else n
            if (x !in fest && ((aus.isNotEmpty() && x - aus.last() < 3) || naechste - x < 3)) continue
            aus.add(x)
        }
        aus
    }

    /** Erster Takt der Phrase q. */
    fun phraseStart(q: Int): Int {
        val g = grenzen()
        return if (q < g.size) g[q] else g.last() + PHRASE * (q - g.size + 1)
    }

    /** Phrasenindex, in dem `takt` liegt. */
    fun phraseVon(takt: Int): Int {
        val g = grenzen()
        val m = max(0, takt)
        var q = 0
        while (q < g.size && g[q] <= m) q++
        q -= 1
        return if (takt < n || q < g.size - 1) q else q + (m - g.last()) / PHRASE
    }

    /** Erste Phrasengrenze ab `takt`. */
    fun phraseAb(takt: Int): Int {
        val q = phraseVon(takt)
        return if (phraseStart(q) == takt) takt else phraseStart(q + 1)
    }

    /** Etikett je Phrase: intro, aufbau, drop, haupt, break, outro. */
    fun etiketten(): List<String> = einmal("etiketten") {
        val g0 = grenzen()
        val grenzen = g0 + n
        val m = g0.size
        val e = DoubleArray(m) { i -> meanBereich(gesamt, grenzen[i], max(grenzen[i] + 1, grenzen[i + 1])) }
        val dr = DoubleArray(m) { i -> meanBereich(drums(), grenzen[i], max(grenzen[i] + 1, grenzen[i + 1])) }
        val laut = percentile(e, 75.0)
        val leise = BooleanArray(m) { e[it] < laut - 4.0 }
        val aus = MutableList(m) { "haupt" }
        var i = 0
        while (i < m && (leise[i] || dr[i] < 0.5)) {
            aus[i] = "intro"
            i++
        }
        var j = m - 1
        while (j > i && (leise[j] || dr[j] < 0.5)) {
            aus[j] = "outro"
            j--
        }
        for (p in i..j) {
            if (dr[p] < 0.3) {
                aus[p] = "break"
            } else if (leise[p]) {
                aus[p] = "aufbau"
            }
        }
        for (t in drops()) aus[phraseVon(t)] = "drop"
        aus
    }

    fun taktBei(t: Double): Int {
        var best = 0
        var abstand = Double.MAX_VALUE
        for (i in takte.indices) {
            val d = abs(takte[i] - t)
            if (d < abstand) {
                abstand = d
                best = i
            }
        }
        return best.coerceIn(0, n - 1)
    }

    /** 0 (ruhig) .. 1 (hart) in den Takten mit Drums. */
    fun energielevel(): Double = einmal("energielevel") {
        var haupt = BooleanArray(n) { drums()[it] > 0.5 }
        if (haupt.count { it } < 4) haupt = BooleanArray(n) { true }
        val hoch = (0 until n).filter { haupt[it] }.map { baender[it][2] - gesamt[it] }.toDoubleArray()
        var z = 1.32 * (median(hoch) + 16.05) / 4.18
        val s = stems
        if (s != null) {
            val other = s.getValue("other")
            val rest = (0 until n).filter { haupt[it] }.map { other[it] - gesamt[it] }.toDoubleArray()
            z -= 1.39 * (median(rest) + 13.0) / 5.88
        }
        1.0 / (1.0 + exp(-z))
    }

    private fun tiefband(): DoubleArray = DoubleArray(n) { baender[it][0] }

    companion object {
        const val PHRASE = 8
        const val DROP_SPRUNG_DB = 9.0
        const val DROP_ABSTAND = 24
        const val DROP_REL = 0.4

        /** `np.percentile` (lineare Interpolation, Standard). */
        fun percentile(values: DoubleArray, q: Double): Double {
            if (values.isEmpty()) return Double.NaN
            val s = values.sortedArray()
            val pos = (s.size - 1) * q / 100.0
            val lo = floor(pos).toInt()
            val hi = min(lo + 1, s.size - 1)
            val frac = pos - lo
            return s[lo] + frac * (s[hi] - s[lo])
        }

        /** `np.median`: sortiert, bei gerader Zahl das Mittel der beiden mittleren. */
        fun median(values: DoubleArray): Double {
            if (values.isEmpty()) return Double.NaN
            val s = values.sortedArray()
            return if (s.size % 2 == 1) s[s.size / 2] else (s[s.size / 2 - 1] + s[s.size / 2]) / 2.0
        }

        private fun cumsum0(x: DoubleArray): DoubleArray {
            val c = DoubleArray(x.size + 1)
            for (i in x.indices) c[i + 1] = c[i] + x[i]
            return c
        }

        private fun meanStride(x: DoubleArray, offset: Int, step: Int = PHRASE): Double {
            var summe = 0.0
            var anzahl = 0
            var i = offset
            while (i < x.size) {
                summe += x[i]
                anzahl++
                i += step
            }
            return if (anzahl == 0) 0.0 else summe / anzahl
        }

        private fun meanBereich(x: DoubleArray, von: Int, bis: Int): Double {
            if (bis <= von) return 0.0
            var summe = 0.0
            for (i in von until bis) summe += x[i]
            return summe / (bis - von)
        }
    }
}

/**
 * `profil.tempo_mal`: Profil im doppelten (2.0: jeder Takt wird zwei) oder halben Taktraster
 * (0.5: jeder zweite Takt), fuer Doppel-/Halbtempo-Uebergaenge.
 */
fun tempoMal(p: Profil, faktor: Double): Profil {
    if (p.n == 0) return p
    val takte: DoubleArray
    val zu: (DoubleArray) -> DoubleArray
    val zuBool: (BooleanArray) -> BooleanArray
    val zuReihen: (Array<DoubleArray>) -> Array<DoubleArray>
    if (faktor > 1.0) {
        takte = DoubleArray(p.n * 2)
        for (i in 0 until p.n) {
            takte[2 * i] = p.takte[i]
            takte[2 * i + 1] = p.takte[i]
        }
        for (i in 0 until p.n) {
            val naechste = if (i + 1 < p.n) p.takte[i + 1] else 2.0 * p.takte[p.n - 1] - p.takte[p.n - 2]
            takte[2 * i + 1] += (naechste - p.takte[i]) / 2.0
        }
        zu = { x -> DoubleArray(x.size * 2) { j -> x[j / 2] } }
        zuBool = { x -> BooleanArray(x.size * 2) { j -> x[j / 2] } }
        zuReihen = { x -> Array(x.size * 2) { j -> x[j / 2] } }
    } else {
        takte = DoubleArray((p.n + 1) / 2) { p.takte[it * 2] }
        zu = { x -> DoubleArray((x.size + 1) / 2) { j -> x[j * 2] } }
        zuBool = { x -> BooleanArray((x.size + 1) / 2) { j -> x[j * 2] } }
        zuReihen = { x -> Array((x.size + 1) / 2) { j -> x[j * 2] } }
    }
    return Profil(
        takte,
        zuReihen(p.baender),
        zu(p.gesamt),
        p.stems?.mapValues { (_, v) -> zu(v) },
        zuBool(p.rasterOk),
        p.dauer,
        p.chroma?.let { zuReihen(it) },
    )
}
