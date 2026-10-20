package de.klangbild.core

import java.util.Locale
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
