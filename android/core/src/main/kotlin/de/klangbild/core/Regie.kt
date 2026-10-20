package de.klangbild.core

import java.util.Locale
import kotlin.math.abs
import kotlin.math.log10
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow

/**
 * Selbstkontrolle des Uebergangs (Port von `regie._pegel_soll` und `regie.pruefen`).
 *
 * Ein fertig gebackener Uebergang darf weder einen Lautstaerke-Buckel noch ein Loch gegenueber
 * den beiden Songs an derselben Stelle haben. Die Regie verwirft den Plan sonst (oder zieht den
 * Pegel in die Grenzen, siehe `pegel_reparieren` im nativen Baker).
 */
object Regie {

    val DROP_TRICKS = listOf("riser_drop", "bremse_drop", "spinback_drop", "teaser_drop", "gate_drop")
    const val REPARATUR_MAX_DB = 6.0

    /** Blendendauer je Stil (`regie.DAUER_S`). */
    val DAUER_S = mapOf("kurz" to (20.0 to 32.0), "ausgewogen" to (28.0 to 64.0), "lang" to (45.0 to 66.0))

    /** Blendendauer bei WEITER (`regie.WEITER_DAUER_S`). */
    val WEITER_DAUER_S = mapOf("kurz" to (14.0 to 24.0), "ausgewogen" to (14.0 to 34.0), "lang" to (20.0 to 34.0))

    val TAKT_STUFEN = listOf(4, 8, 16, 24, 32)
    const val FRUEH_GESANG = "A's Gesang trägt"

    /** Ein Ausstiegs-/Einsatzkandidat mit Punkten und Begruendung. */
    data class Kandidat(val takt: Int, val punkte: Double, val grund: String)

    /** `regie.laengen`: erlaubte Blendenlaengen, deren Dauer im Zeitfenster liegt. */
    fun laengen(modus: String, taktS: Double, sofort: Boolean = false): List<Int> {
        val (lo, hi) = (if (sofort) WEITER_DAUER_S else DAUER_S).getValue(modus)
        val passend = TAKT_STUFEN.filter { it * taktS >= lo && it * taktS <= hi }
        if (passend.isNotEmpty()) return passend
        return listOf(TAKT_STUFEN.minWith(compareBy { minOf(abs(it * taktS - lo), abs(it * taktS - hi)) }))
    }

    /** `regie._takt_s`: mittlere Taktlaenge des Profils. */
    fun taktS(p: Profil): Double {
        if (p.n <= 1) return 2.0
        val d = DoubleArray(p.n - 1) { p.takte[it + 1] - p.takte[it] }
        return Profil.median(d)
    }

    /** `regie._fenster`: x[von : von+n], hinter dem Ende mit 0 aufgefuellt. */
    fun fenster(x: DoubleArray, von: Int, n: Int): DoubleArray {
        val aus = DoubleArray(n)
        val start = maxOf(0, von)
        val ende = minOf(x.size, von + n)
        if (ende > start) {
            for (i in 0 until ende - start) aus[i] = x[start + i]
        }
        return aus
    }

    /** `regie._mittelgewicht`: wie stark beide Songs in Takt k gleichzeitig hoerbar sind. */
    fun mittelgewicht(n: Int): DoubleArray = DoubleArray(n) {
        val x = (it + 0.5) / n
        4 * x * (1 - x)
    }

    /** `regie._a_kandidaten`: (Takt, Punkte, Begruendung) fuer den Ausstieg aus A. */
    fun aKandidaten(
        pa: Profil,
        abTakt: Int,
        e: Einstellungen,
        sofort: Boolean,
        stemsDa: Boolean = false,
    ): List<Kandidat> {
        if (sofort && e.weiterAb == "takt") return listOf(Kandidat(abTakt, 0.0, ""))
        if (sofort) {
            val naechstePhrase = pa.phraseAb(abTakt)
            val erste = if (naechstePhrase - abTakt <= 4) naechstePhrase else naechstePhrase - 4
            return (0..2).map { erste + 4 * it to -2.5 * it }
                .filter { it.first < pa.n }
                .map { Kandidat(it.first, it.second, "") }
        }
        val et = pa.etiketten()
        val nPh = et.size
        val aus = mutableListOf<Kandidat>()
        if (e.spielanteil == "schnell") {
            // Profi-Kurzspiel: Wechsel in der zweiten Haelfte, kurz nachdem der Drop gelaufen ist.
            val mitte = pa.n / 2
            var drops = (0 until nPh).filter { et[it] == "drop" && pa.phraseStart(it) >= mitte }
                .map { pa.phraseStart(it) }
            if (drops.isEmpty()) {
                drops = (0 until nPh).filter { et[it] == "haupt" && pa.phraseStart(it) >= mitte }
                    .map { pa.phraseStart(it) }
            }
            // A's Drop laeuft aus (bis sein Abschnitt endet, hoechstens 2 Phrasen).
            val start = if (drops.isNotEmpty()) {
                val q0 = pa.phraseVon(drops[0])
                var q = q0 + 1
                while (q < nPh && et[q] in listOf("drop", "haupt") && q < q0 + 2) q++
                pa.phraseStart(q)
            } else {
                mitte
            }
            for ((k, takt) in pa.grenzen().filter { it >= start }.take(3).withIndex()) {
                aus.add(Kandidat(takt, 3.0 - 1.5 * k, "zweite Hälfte nach dem Drop"))
            }
            if (drops.isNotEmpty() && start > pa.phraseAb(drops[0] + 1)) {
                aus.add(Kandidat(pa.phraseAb(drops[0] + 1), -1.5, "zweite Hälfte nach dem Drop"))
            }
            if (aus.all { pa.n - it.takt < 16 }) {
                // Drop-Abschnitt bis kurz vors Ende: Platz fuer die Blende.
                val platz = pa.grenzen().filter { it >= mitte && it <= pa.n - 16 }
                if (platz.isNotEmpty()) {
                    aus.add(Kandidat(platz.last(), -2.0, "zweite Hälfte, Platz für die Blende"))
                }
            }
        } else {
            // So lange wie moeglich: Kandidaten im letzten Drittel, spaeter = besser.
            val start = pa.phraseStart(pa.phraseVon((pa.n * 0.7).toInt()))
            for (takt in pa.grenzen().filter { it >= start }) {
                aus.add(Kandidat(takt, 6.0 * takt / maxOf(1, pa.n), "spielt lang"))
            }
            val ga = if (stemsDa) pa.gesang() else null
            if (ga != null) {
                // A's letzte Gesangsteile: von dort kann A's Stimme lange ueber B weiterlaufen.
                val frueh = pa.phraseStart(pa.phraseVon(pa.n / 2))
                for (takt in pa.grenzen().filter { it >= frueh && it < start }) {
                    val bis = minOf(pa.n, takt + Profil.PHRASE)
                    if ((takt until bis).any { ga[it] != 0.0 }) {
                        aus.add(Kandidat(takt, 6.0 * takt / maxOf(1, pa.n), FRUEH_GESANG))
                    }
                }
            }
        }
        val gefiltert = aus.filter { it.takt >= abTakt }
        return gefiltert.ifEmpty { listOf(Kandidat(pa.phraseAb(abTakt), -2.0, "")) }
    }

    /** `regie._beatlos`: Takte ohne Drums (0/1). */
    fun beatlos(pb: Profil): BooleanArray {
        val s = pb.stems
        if (s != null) {
            val d = s.getValue("drums")
            return BooleanArray(pb.n) { d[it] < -35.0 }
        }
        val tief = DoubleArray(pb.n) { pb.baender[it][0] }
        val median = Profil.median(tief)
        return BooleanArray(pb.n) { tief[it] < median - 10.0 }
    }

    /** `regie._brueckenstart`: bei Takt j beginnt ein beatloser Teil von mindestens 4 Takten. */
    fun brueckenstart(pb: Profil, j: Int): Boolean {
        if (j + 4 > pb.n) return false
        val beatlos = beatlos(pb)
        return (j until j + 4).all { beatlos[it] }
    }

    /** `regie._b_kandidaten`: (Takt, Punkte) fuer den Einsatz von B. */
    fun bKandidaten(pb: Profil, e: Einstellungen, sync: Boolean = true): List<Kandidat> {
        val et = pb.etiketten()
        val aus = mutableListOf<Kandidat>()
        for (takt in pb.grenzen().filter { it <= (pb.n * 0.4).toInt() }) {
            var p = if (e.spielanteil == "schnell") {
                0.0   // Intro ueberspringen ist erlaubt
            } else {
                -0.8 * takt / Profil.PHRASE   // moeglichst von vorn
            }
            if (et[pb.phraseVon(takt)] == "break") p -= 1.0
            if (!sync && brueckenstart(pb, takt)) p += 3.0
            aus.add(Kandidat(takt, p, ""))
        }
        return aus
    }

    /** `regie._b_index`: B-Takt je Blendentakt; mit Intro-Loop laufen B's erste `kEin` Takte (mal+1)-mal. */
    fun bIndex(j: Int, L: Int, kEin: Int = 0, mal: Int = 0): IntArray {
        if (kEin == 0 || mal == 0) return IntArray(L) { j + it }
        val schleife = kEin * (mal + 1)
        return IntArray(L) { k -> if (k < schleife) j + k % kEin else j + kEin + (k - schleife) }
    }

    /** `regie._werte`: x[idx], ausserhalb des Songs 0. */
    fun werte(x: DoubleArray, idx: IntArray): DoubleArray =
        DoubleArray(idx.size) { i ->
            if (idx[i] < x.size) x[idx[i].coerceIn(0, x.size - 1)] else 0.0
        }

    /** Rezepte, die nicht auf Buckel/Loch geprueft werden (Schnitt, Echo, Stems, Tricks). */
    private val AUSNAHMEN = listOf(
        "schnitt", "echo_out", "schnitt_echo", "echo_drop", "intro_loop_b", "double_drop", "drop_cuts",
    )

    /** Je Takt: Ist-Pegel, Obergrenze und Untergrenze in dB. */
    data class PegelSoll(val ist: DoubleArray, val oben: DoubleArray, val unten: DoubleArray)

    /** `regie._pegel_soll`: null, wenn das Rezept nicht geprueft wird. */
    fun pegelSoll(
        blende: FloatArray,
        rate: Int,
        nTakte: Int,
        pa: Profil,
        pb: Profil,
        ausS: Double,
        einS: Double,
        gainA: Double,
        gainB: Double,
        rezept: String,
    ): PegelSoll? {
        if (nTakte < 2 || rezept in AUSNAHMEN || rezept in DROP_TRICKS) return null
        val frames = blende.size / 2
        val taktS = frames.toDouble() / rate / nTakte
        val mono = DoubleArray(frames) {
            ((blende[it * 2] + blende[it * 2 + 1]) / 2.0f).toDouble()
        }

        val ist = DoubleArray(nTakte)
        val oben = DoubleArray(nTakte)
        val unten = DoubleArray(nTakte) { Double.NEGATIVE_INFINITY }
        // Mit Loop wiederholt A seinen Anfang: dessen Pegel ist der Vergleich.
        val loopRezept = "loop" in rezept || rezept == "rolle"
        for (k in 0 until nTakte) {
            val von = (k * taktS * rate).toInt()
            val bis = ((k + 1) * taktS * rate).toInt()
            var summe = 0.0
            val ende = min(bis, frames)
            for (i in von until ende) summe += mono[i] * mono[i]
            ist[k] = 10.0 * log10(if (bis > von) summe / (bis - von) + 1e-10 else 1e-10)

            val ia = pa.taktBei(ausS + (if (loopRezept) 0.0 else k * taktS))
            val jb = pb.taktBei(einS + k * taktS)
            val la = pa.gesamt[ia] + gainA
            val lb = pb.gesamt[jb] + gainB
            oben[k] = max(la, lb) + 3.5
            val x = (k + 0.5) / nTakte
            // gesang_zuerst: bis zur Uebergabe traegt A allein (B nur mit Gesang) - kein Loch.
            if (k != 0 && k != nTakte - 1 && rezept != "gesang_zuerst") {
                unten[k] = 10.0 * log10((1.0 - x) * 10.0.pow(la / 10.0) + x * 10.0.pow(lb / 10.0)) - 9.0
            }
        }
        return PegelSoll(ist, oben, unten)
    }

    /** `regie.pruefen`: Begruendung, wenn der Uebergang durchfaellt, sonst null. */
    fun pruefen(
        blende: FloatArray,
        rate: Int,
        nTakte: Int,
        pa: Profil,
        pb: Profil,
        ausS: Double,
        einS: Double,
        gainA: Double,
        gainB: Double,
        rezept: String,
    ): String? {
        val werte = pegelSoll(blende, rate, nTakte, pa, pb, ausS, einS, gainA, gainB, rezept) ?: return null
        for (k in 0 until nTakte) {
            if (werte.ist[k] > werte.oben[k]) {
                return "zu laut in Takt ${k + 1} (+${nachkomma(werte.ist[k] - werte.oben[k] + 3.5)} dB)"
            }
            if (werte.ist[k] < werte.unten[k]) {
                return "Loch in Takt ${k + 1} (${nachkomma(werte.ist[k] - werte.unten[k] - 9.0)} dB)"
            }
        }
        return null
    }

    /** Python-`f"{x:.1f}"` (eine Nachkommastelle, Dezimalpunkt). */
    private fun nachkomma(x: Double): String = String.format(Locale.ROOT, "%.1f", x)
}
