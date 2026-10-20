package de.klangbild.core

import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

/**
 * Regie: die besten Plaene fuer A -> B (Port von `prototyp/klangbild/regie.py`).
 *
 * Bewertet Kandidaten (Ausstieg in A, Einsatz in B, Laenge) nach musikalischen Regeln, waehlt
 * ein Rezept und liefert fertige Plaene fuer `uebergang.backen`. Audioabhaengige Pruefungen
 * (Drops auf den Schlag, Kick-Kontrolle, Loop-Guete) laufen im nativen Baker; hier gelten sie
 * ohne Audio als bestanden, genau wie im Prototyp mit `audio=None`.
 */
object RegiePlanung {

    const val PHRASE = 8
    const val GESANG_MAX_S = 180.0
    const val WEITER_GESANG_MAX = 32
    const val DROP_SICHER_DB = 5.0
    const val PASSUNG_MIN = 0.35
    const val VORLAUF_MAX = 0.08
    const val VORLAUF_TAKTE = 16
    const val DROP_AUSSPIELEN = 16
    const val STRUKTUR_STRAFE = 20.0
    const val DROP_EINSATZ = 6.0
    const val LOOP_GUETE_MIN = 0.7
    const val REZEPT_MITTEL = 3.27
    const val REZEPT_GEWICHT = 2.0
    const val HART = 0.6
    const val RUHIG = 0.35
    const val ENERGIE_REZEPT_BONUS = 0.5
    const val LANG32_BONUS = 0.3
    const val TEMPO_SPIEL = 0.5

    val GESANG_REZEPTE = listOf("acapella", "gesang_zuerst")
    val GESANG_TEILE = listOf("A singt über B's Musik weiter", "B's Gesang kommt vor seiner Musik")
    val GESANG_LAENGEN = listOf(16, 24, 32, 40, 48, 56, 64, 72, 80, 96)
    val LOOP_REZEPTE = listOf("outro_loop", "loop_echo", "loop_filter", "loop_fx", "intro_loop_b", "rolle")
    val EXPERIMENT_WERT = mapOf("klassisch" to 0.0, "kreativ" to 3.2, "wild" to 5.0)
    val EXPERIMENT_DROP = mapOf("klassisch" to 0.0, "kreativ" to 1.0, "wild" to 2.5)
    const val BRUECKE = "B startet ohne Drums"

    val REZEPT_NOTE = mapOf(
        "acapella" to 3.53, "breakdown" to 2.49, "bremse_drop" to 3.2, "bruecke_beatlos" to 3.24,
        "double_drop" to 3.14, "drop_cuts" to 2.91, "drums_zuerst" to 3.12, "echo_drop" to 3.28,
        "echo_out" to 3.15, "echo_out_blend" to 3.24, "filter_blend" to 3.22, "fx_echo" to 3.35,
        "gate_drop" to 3.21, "gesang_zuerst" to 3.65, "gesangsschutz" to 3.49, "hochpass_hall" to 2.91,
        "intro_loop_b" to 3.34, "kurz_eq" to 3.14, "loop_filter" to 3.19, "loop_fx" to 3.17,
        "melodie_zuerst" to 3.42, "outro_loop" to 3.31, "riser_drop" to 2.92, "rolle" to 2.82,
        "schnitt" to 2.97, "schnitt_echo" to 3.14, "spinback_drop" to 3.71, "teaser_drop" to 3.14,
    )

    /** Ein Songbezug der Regie: Pfad (fuer Chill) und Tonart. */
    data class Referenz(val id: Int = 0, val pfad: String = "", val camelot: String? = null)

    data class Plan(
        val ausS: Double,
        val einS: Double,
        val takte: Int,
        val einst: Einstellungen,
        val rezept: String,
        val grund: String,
        val punkte: Double,
    )

    data class Lage(
        val i: Int,
        val j: Int,
        val takte: Int,
        val punkte: Double,
        val teile: List<String>,
        val kEin: Int = 0,
        val mal: Int = 0,
        val harm: Double? = null,
        val dropK: Int = 0,
    )

    private data class KandidatRezept(val name: String, val felder: Map<String, Any>, val text: String, val wert: Double)

    // --- Kleine Helfer ---------------------------------------------------------

    private fun mean(x: DoubleArray, von: Int = 0, bis: Int = x.size): Double {
        val a = max(0, von)
        val b = min(bis, x.size)
        if (b <= a) return Double.NaN
        var s = 0.0
        for (i in a until b) s += x[i]
        return s / (b - a)
    }

    private fun clip(v: Double, lo: Double, hi: Double): Double = max(lo, min(hi, v))

    /** `uebergang._periode`: lokale Taktlaenge (Mittel der Abstaende nahe am Median). */
    fun periode(t: DoubleArray, i: Int, halb: Int = 8): Double {
        val lo = max(0, i - halb)
        val hi = min(t.size - 1, i + halb)
        if (hi <= lo) return 2.0
        val d = DoubleArray(hi - lo) { t[lo + it + 1] - t[lo + it] }
        val m = Profil.median(d)
        val kern = d.filter { abs(it - m) <= 0.1 * m }
        return if (kern.isEmpty()) m else kern.sum() / kern.size
    }

    /** `np.searchsorted(werte, x, side="left")`. */
    private fun searchLeft(werte: DoubleArray, x: Double): Int {
        var lo = 0
        var hi = werte.size
        while (lo < hi) {
            val mid = (lo + hi) / 2
            if (werte[mid] < x) lo = mid + 1 else hi = mid
        }
        return lo
    }

    private fun rasterOkFloat(p: Profil): DoubleArray = DoubleArray(p.n) { if (p.rasterOk[it]) 1.0 else 0.0 }

    // --- Harmonie und Gesang ---------------------------------------------------

    /** `regie._harmonie`: Kosinus der ueber das Fenster gemittelten Chroma (0..1). */
    fun harmonie(pa: Profil, pb: Profil, i: Int, bi: IntArray): Double? {
        val ca = pa.chroma ?: return null
        val cb = pb.chroma ?: return null
        val w = Regie.mittelgewicht(bi.size)
        val a = DoubleArray(12)
        val b = DoubleArray(12)
        for (k in bi.indices) {
            val ia = (i + k).coerceIn(0, pa.n - 1)
            val ib = bi[k].coerceIn(0, pb.n - 1)
            for (c in 0 until 12) {
                a[c] += ca[ia][c] * w[k]
                b[c] += cb[ib][c] * w[k]
            }
        }
        var dot = 0.0
        var na = 0.0
        var nb = 0.0
        for (c in 0 until 12) {
            dot += a[c] * b[c]
            na += a[c] * a[c]
            nb += b[c] * b[c]
        }
        return dot / max(kotlin.math.sqrt(na) * kotlin.math.sqrt(nb), 1e-9)
    }

    /** `regie._gesang_uebergabe`: (Rezept, Takt, Takte) oder null, wenn zwei Stimmen klingen wuerden. */
    fun gesangUebergabe(pa: Profil, pb: Profil, i: Int, bi: IntArray): Triple<String, Int, Int>? {
        val ga = pa.gesang() ?: return null
        val gb = pb.gesang() ?: return null
        val L = bi.size
        if (pa.n - i < L) return null
        val fensterA = Regie.fenster(ga, i, L)
        val a = BooleanArray(L) { fensterA[it] > 0 }
        val bWerte = Regie.werte(gb, bi)
        val b = BooleanArray(L) { bWerte[it] > 0 }
        val tausch = max(2, min(8, L / 4))
        val bErste = b.indexOfFirst { it }
        if (bErste >= 0 && !a.drop(max(0, bErste - 1)).any { it }) {
            val x = DoubleArray(L) { pa.gesamt[i + it] }
            var spitze = Double.NEGATIVE_INFINITY
            for (k in 0 until min(4, L)) spitze = max(spitze, x[k])
            val leise = x.indexOfFirst { it < spitze - 8.0 }
            val g = (if (leise >= 0) leise else L) - tausch
            val summe = if (g > bErste) b.slice(bErste until min(g, L)).count { it } else 0
            if (g - bErste >= 4 && summe >= max(4.0, 0.6 * (g - bErste)) && bErste <= max(8, L / 4)) {
                return Triple("gesang_zuerst", g, summe)
            }
            return null
        }
        if (a.any { it }) {
            var g = a.indexOfLast { it } + 1
            var zeileEndet = g < L || Regie.fenster(ga, i + L, 2).any { it > 0 }
            if (!zeileEndet) {
                val grenzen = (tausch + 2 until L).filter { (i + it) % PHRASE == 0 }
                if (grenzen.isNotEmpty()) {
                    g = grenzen.last()
                    zeileEndet = true
                }
            }
            val allein = if (g > tausch) a.slice(tausch until min(g, L)).count { it } else 0
            if (zeileEndet && allein >= 4 && !b.take(min(g + 5, L)).any { it }) {
                return Triple("acapella", g, allein)
            }
        }
        return null
    }

    // --- Bewertung -------------------------------------------------------------

    fun strukturfehler(
        pa: Profil,
        pb: Profil,
        i: Int,
        bi: IntArray,
        L: Int,
        sofort: Boolean,
        gesang: Boolean = false,
    ): String? {
        if (!gesang && pa.drops().any { i < it && it < i + L }) return "A's Drop käme in der Blende"
        val bDrops = pb.drops().toSet()
        if (!gesang && bi.drop(1).any { it in bDrops }) return "B's Drop käme mitten in der Blende"
        if (!sofort && pa.drops().any { 0 <= i - it && i - it < DROP_AUSSPIELEN }) {
            return "A's Drop wäre noch keine 16 Takte gelaufen"
        }
        return null
    }

    /** `regie._verpasst`: Hauptteile/Drops von A ab diesem Takt. */
    fun verpasst(pa: Profil, abTakt: Int): Int {
        val ea = pa.etiketten()
        var n = 0
        for (q in pa.phraseVon(abTakt) until ea.size) if (ea[q] in listOf("drop", "haupt")) n++
        return n
    }

    /** `regie._grundwert`: Punkte des Musikwechsels im Fenster. */
    fun grundwert(
        pa: Profil,
        pb: Profil,
        i: Int,
        j: Int,
        L: Int,
        e: Einstellungen,
        kEin: Int = 0,
        mal: Int = 0,
    ): Triple<Double, List<String>, Double?> {
        val w = Regie.mittelgewicht(L)
        val bi = Regie.bIndex(j, L, kEin, mal)
        val nachTakt = if (kEin != 0) j + L - mal * kEin else j + L
        val teile = mutableListOf<String>()
        var p = 0.0
        val ga = pa.gesang()
        val gb = pb.gesang()
        if (ga != null && gb != null) {
            val fenster = Regie.fenster(ga, i, L)
            val werte = Regie.werte(gb, bi)
            var clash = 0.0
            for (k in 0 until L) clash += fenster[k] * werte[k] * w[k]
            clash /= L
            p -= 8.0 * clash
            if (clash < 0.02) teile.add("kein Gesang gegeneinander")
        }
        val eb = pb.etiketten()
        val nach = if (nachTakt < pb.n) eb[min(eb.size - 1, pb.phraseVon(nachTakt))] else "outro"
        p += mapOf("drop" to 3.0, "haupt" to 2.0, "aufbau" to 0.5, "intro" to 0.0, "break" to -1.0, "outro" to -3.0)
            .getValue(nach)
        if (nach == "drop") teile.add("B's Drop direkt nach der Blende")
        val dropsB = eb.indices.filter { eb[it] == "drop" }.map { pb.phraseStart(it) }.toSet()
        if (bi.drop(1).any { it != j && it in dropsB }) p -= 2.5
        val ea = pa.etiketten()
        val labA = (i until min(pa.n, i + L)).map { ea[min(ea.size - 1, pa.phraseVon(it))] }
            .ifEmpty { listOf("outro") }
        val gutA = labA.map {
            mapOf("outro" to 1.0, "break" to 0.6, "intro" to 0.3, "aufbau" to 0.2, "haupt" to -0.6, "drop" to -1.0)
                .getValue(it)
        }.average()
        p += 2.0 * gutA
        val labB = bi.filter { it < pb.n }.map { eb[min(eb.size - 1, pb.phraseVon(it))] }
        if (labA.count { it in listOf("drop", "haupt") }.toDouble() / labA.size > 0.5 && labB.isNotEmpty() &&
            labB.count { it == "intro" }.toDouble() / labB.size > 0.5
        ) {
            p -= 2.0
        }
        if (labA[0] in listOf("outro", "break")) {
            teile.add(if (labA[0] == "outro") "A im Outro" else "A im Break")
        }
        if (i + L >= pa.n - 2 || (i + L < pa.n && ea[min(ea.size - 1, pa.phraseVon(i + L))] != labA.last())) {
            p += 1.0
        }
        if (e.spielanteil == "lang") p -= 1.5 * verpasst(pa, i + L)
        if (e.modus == "lang" && L == 32 && pa.n - i >= 32) p += LANG32_BONUS
        val dichte = 0.5 * (mean(Regie.fenster(pa.dichte(), i, L)) + mean(Regie.werte(pb.dichte(), bi)))
        p += (0.6 - dichte) * (L / 8.0)
        val harm = harmonie(pa, pb, i, bi)
        if (harm != null) {
            p += clip(4.0 * (harm - 0.7), -2.0, 1.2) * (L / 16.0 + 0.5)
            if (harm > 0.85) teile.add("Harmonie passt im Fenster")
        }
        val eA = if (i < pa.n) mean(pa.gesamt, i, i + max(1, L / 2)) else -30.0
        val eB = if (nachTakt < pb.n) mean(pb.gesamt, nachTakt, nachTakt + PHRASE) else -30.0
        val sprung = eB - eA
        val erlaubt = if (e.spielanteil == "schnell") 0.0 to 6.0 else -3.0 to 3.0
        p -= 0.3 * max(0.0, max(erlaubt.first - sprung, sprung - erlaubt.second))
        val unsicher = 1.0 - 0.5 * (mean(Regie.fenster(rasterOkFloat(pa), i, L)) +
            mean(Regie.werte(rasterOkFloat(pb), bi)))
        p -= 4.0 * unsicher * (L / 16.0)
        if (kEin != 0) {
            p += 0.3
            teile.add("B's Intro geloopt ($kEin Takte × ${mal + 1}), Gesang/Drop erst danach")
        }
        return Triple(p, teile, harm)
    }

    fun bewerten(
        pa: Profil,
        pb: Profil,
        i: Int,
        j: Int,
        L: Int,
        e: Einstellungen,
        kEin: Int = 0,
        mal: Int = 0,
        stemsDa: Boolean = false,
        tonartOk: Boolean = false,
    ): Triple<Double, List<String>, Double?> {
        if (stemsDa && kEin == 0) {
            val bi = Regie.bIndex(j, L)
            val ueb = gesangUebergabe(pa, pb, i, bi)
            val harm = if (ueb != null) harmonie(pa, pb, i, bi) else null
            if (ueb != null && (harm == null || harm >= (if (tonartOk) 0.55 else 0.65))) {
                val t = max(2, min(8, L / 4))
                val von = if (ueb.first == "acapella") 0 else L - t
                val (p0, teile, _) = grundwert(pa, pb, i + von, j + von, t, e)
                var p = p0
                if (e.spielanteil == "lang") {
                    p += 1.5 * (verpasst(pa, i + von + t) - verpasst(pa, i + if (von == 0) ueb.second else L))
                    if (von == 0) p += 6.0 * ueb.second / max(1, pa.n)
                }
                if (harm != null) p += clip(4.0 * (harm - 0.7), -2.0, 1.2) * (L / 16.0 + 0.5)
                return Triple(
                    p + 2.0 + 0.6 * ueb.third,
                    teile + GESANG_TEILE[GESANG_REZEPTE.indexOf(ueb.first)],
                    harm,
                )
            }
        }
        var (p, teile, harm) = grundwert(pa, pb, i, j, L, e, kEin, mal)
        val ga = pa.gesang()
        if (ga != null && i + L < pa.n && ga[i + L - 1] > 0 && ga[i + L] > 0) p -= 3.0
        return Triple(p, teile, harm)
    }

    private fun introLoops(pb: Profil, j: Int, L: Int): List<Pair<Int, Int>> {
        val gb = pb.gesang()
        val singt = gb != null && (j until min(pb.n, j + L)).any { gb[it] > 0 }
        val vollDrin = pb.etiketten().withIndex().any { (q, x) ->
            x in listOf("drop", "haupt") && pb.phraseStart(q) > j && pb.phraseStart(q) < j + L
        }
        if (!singt && !vollDrin) return emptyList()
        val aus = mutableListOf<Pair<Int, Int>>()
        for (k in listOf(4, 8)) {
            if (j + 2 * k > pb.n) continue
            if (gb != null && (j until min(pb.n, j + k)).any { gb[it] > 0 }) continue
            if (mean(pb.drums(), j, j + k) < 0.5) continue
            for (mal in listOf(1, 2, 3)) {
                if (k * (mal + 1) <= L) aus.add(k to mal)
            }
        }
        return aus
    }

    private fun dropTakt(p: Profil, takt: Int): Int {
        val nah = p.drops().filter { abs(it - takt) <= 4 }
        if (nah.isNotEmpty()) return nah.minBy { abs(it - takt) }
        val reihen = mutableListOf(p.gesamt)
        if (p.stems != null) {
            reihen.add(p.stems.getValue("bass"))
            reihen.add(p.stems.getValue("drums"))
        } else {
            reihen.add(DoubleArray(p.n) { p.baender[it][0] })
        }
        fun sprung(k: Int): Double {
            if (k < 2 || k + 2 > p.n) return Double.NEGATIVE_INFINITY
            var s = 0.0
            for (x in reihen) s += mean(x, k, k + 2) - mean(x, k - 2, k)
            return s
        }
        var best = takt - 2
        for (k in takt - 1..takt + 2) if (sprung(k) > sprung(best)) best = k
        return if (sprung(best) > 1.5 * max(sprung(takt), 1.0)) best else takt
    }

    private fun einsatz(p: Profil, k: Int): Double {
        if (k < 2 || k + 2 > p.n) return 0.0
        val reihen = mutableListOf(p.gesamt)
        if (p.stems != null) {
            reihen.add(p.stems.getValue("bass"))
            reihen.add(p.stems.getValue("drums"))
        } else {
            reihen.add(DoubleArray(p.n) { p.baender[it][0] })
        }
        return reihen.maxOf { mean(it, k, k + 2) - mean(it, k - 2, k) }
    }

    private fun dropWerte(p: Profil, k: Int): DoubleArray {
        val g = mean(p.gesamt, k, k + PHRASE)
        val drums = p.stems?.get("drums") ?: DoubleArray(p.n) { p.baender[it][1] }
        val bass = p.stems?.get("bass") ?: DoubleArray(p.n) { p.baender[it][0] }
        return doubleArrayOf(g, mean(drums, k, k + PHRASE) - g, mean(bass, k, k + PHRASE) - g)
    }

    private fun passung(pa: Profil, pb: Profil, dA: Int, dB: Int): Double =
        1.0 - min(1.0, abs(dropWerte(pa, dA)[0] - dropWerte(pb, dB)[0]) / 4.0)

    fun doubleDrops(
        pa: Profil,
        pb: Profil,
        e: Einstellungen,
        abTakt: Int,
        stemsDa: Boolean = false,
        a: Referenz? = null,
        b: Referenz? = null,
    ): List<Lage> {
        val ea = pa.etiketten()
        val eb = pb.etiketten()
        val aDrops = ea.indices.filter { q ->
            ea[q] == "drop" && pa.phraseStart(q) >= max(abTakt + PHRASE, pa.n / 2)
        }.map { dropTakt(pa, pa.phraseStart(it)) }.filter { einsatz(pa, it) >= DROP_EINSATZ }
        val bDrops = eb.indices.filter { q -> eb[q] == "drop" && q >= 1 }
            .map { dropTakt(pb, pb.phraseStart(it)) }
            .filter { einsatz(pb, it) >= DROP_EINSATZ }
            .take(2)
        val ga = pa.gesang()
        val gb = pb.gesang()
        val aus = mutableListOf<Lage>()
        for (dA in aDrops) {
            for (dB in bDrops) {
                if (passung(pa, pb, dA, dB) < PASSUNG_MIN) continue
                for (dauer in listOf(8, 16)) {
                    val i = dA - PHRASE
                    val j = dB - PHRASE
                    val L = PHRASE + dauer
                    if (i < abTakt || j < 0 || pa.n - i < L || j + L > pb.n) continue
                    val bi = Regie.bIndex(j, L)
                    val harm = harmonie(pa, pb, i, bi)
                    if (harm != null && harm < 0.8) continue
                    if (pa.stems != null && pb.stems != null &&
                        min(dropWerte(pa, dA)[2], dropWerte(pb, dB)[2]) < -20.0
                    ) {
                        continue
                    }
                    if (!stemsDa && ga != null && gb != null) {
                        val fenster = Regie.fenster(ga, dA, dauer)
                        val werte = Regie.werte(gb, IntArray(L - PHRASE) { bi[PHRASE + it] })
                        if ((0 until dauer).any { fenster[it] * werte[it] != 0.0 }) continue
                    }
                    val p = 2.0 * (harm?.minus(0.85) ?: 0.0) + 1.0 * dA / pa.n + (if (dauer == 16) 0.3 else 0.0)
                    aus.add(
                        Lage(
                            i, j, L, p,
                            listOf("Double Drop: beide Drops auf denselben Takt"),
                            harm = harm, dropK = PHRASE,
                        ),
                    )
                }
            }
        }
        return aus
    }

    fun chill(eintrag: Referenz?, p: Profil): Boolean {
        val ordner = if (eintrag != null && eintrag.pfad.isNotEmpty()) {
            eintrag.pfad.replace('\\', '/').split('/').dropLast(1).map { it.lowercase() }
        } else {
            emptyList()
        }
        if (ordner.isNotEmpty() && ordner.last() != "upload") return ordner.any { "chill" in it }
        return p.energielevel() < 0.5
    }

    // --- Rangliste -------------------------------------------------------------

    fun rangliste(
        pa: Profil,
        pb: Profil,
        e: Einstellungen,
        abTakt: Int,
        sofort: Boolean,
        stemsDa: Boolean = false,
        tonartOk: Boolean = false,
        sync: Boolean = true,
        a: Referenz? = null,
        b: Referenz? = null,
    ): List<Lage> {
        val stufen = Regie.laengen(e.modus, Regie.taktS(pa), sofort)
        val extra = if (!stemsDa) {
            emptyList()
        } else {
            GESANG_LAENGEN.filter { L ->
                L !in stufen && L * Regie.taktS(pa) <= GESANG_MAX_S && (!sofort || L <= WEITER_GESANG_MAX)
            }
        }
        var lagen = mutableListOf<Lage>()
        val dropBonus = if (sofort) 0.0 else EXPERIMENT_DROP.getValue(e.experimente)
        val energien = listOf(pa.energielevel(), pb.energielevel()).sorted()
        val hart = energien[0] >= HART
        val ruhig = energien[1] <= RUHIG
        for (ka in Regie.aKandidaten(pa, abTakt, e, sofort, stemsDa)) {
            for (kb in Regie.bKandidaten(pb, e, sync)) {
                for (L in stufen + extra) {
                    if (kb.takt + L > pb.n) continue
                    if (L in extra) {
                        val ueb = gesangUebergabe(pa, pb, ka.takt, Regie.bIndex(kb.takt, L))
                        if (ueb == null || ueb.second < L - 12) continue
                    }
                    val restA = pa.n - ka.takt
                    if (restA < L) {
                        if (mean(Regie.fenster(pa.drums(), ka.takt, 2)) < 0.5 || restA < 2) continue
                    }
                    val varianten = mutableListOf(0 to 0)
                    if (!sofort) varianten.addAll(introLoops(pb, kb.takt, L))
                    for ((kEin, mal) in varianten) {
                        var (p, teile, harm) = bewerten(pa, pb, ka.takt, kb.takt, L, e, kEin, mal, stemsDa, tonartOk)
                        val gesang = teile.any { it in GESANG_TEILE }
                        val fehler = strukturfehler(
                            pa, pb, ka.takt, Regie.bIndex(kb.takt, L, kEin, mal), L, sofort, gesang,
                        )
                        if (fehler != null) {
                            p -= STRUKTUR_STRAFE
                            teile = teile + fehler
                        }
                        if ((L in extra || ka.grund == Regie.FRUEH_GESANG) && teile.none { it in GESANG_TEILE }) {
                            continue
                        }
                        if (kEin != 0 && harm != null && harm < 0.65) continue
                        if ("B's Drop direkt nach der Blende" in teile) {
                            p += dropBonus
                            if (hart) {
                                p += ENERGIE_REZEPT_BONUS
                                teile = teile + "beide hart: Drop-Wechsel"
                            }
                        }
                        if (ruhig && L >= 16) {
                            p += ENERGIE_REZEPT_BONUS
                            teile = teile + "beide ruhig: lange Blende"
                        }
                        if (!sync && Regie.brueckenstart(pb, kb.takt)) teile = teile + BRUECKE
                        lagen.add(
                            Lage(
                                ka.takt, kb.takt, L, p + ka.punkte + kb.punkte,
                                (if (ka.grund.isNotEmpty()) listOf(ka.grund) else emptyList()) + teile,
                                kEin, mal, harm,
                            ),
                        )
                    }
                }
            }
        }
        lagen = lagen.sortedByDescending { it.punkte }.toMutableList()
        if (e.experimente != "klassisch" && !sofort && lagen.isNotEmpty() && sync) {
            val vorn = lagen[0].punkte + (if (e.experimente == "wild") 1.0 else -1.0)
            val dd = doubleDrops(pa, pb, e, abTakt, stemsDa, a, b).map { it.copy(punkte = vorn + it.punkte) }
            lagen = (lagen + dd).sortedByDescending { it.punkte }.toMutableList()
        }
        return lagen
    }

    // --- Rezept ----------------------------------------------------------------

    private fun Map<String, Any>.text(key: String, standard: String): String = this[key] as? String ?: standard

    fun rezept(
        lage: Lage,
        pa: Profil,
        pb: Profil,
        e: Einstellungen,
        syncIn: Boolean,
        harmonischIn: Boolean,
        stemsDa: Boolean,
        vorher: String?,
        vorlieben: Map<String, Double>? = null,
        loopOk: Boolean = true,
        sofort: Boolean = false,
        a: Referenz? = null,
        b: Referenz? = null,
        vorlauf: Boolean = false,
    ): Triple<String, Map<String, Any>, String> {
        val i = lage.i
        val j = lage.j
        val L = lage.takte
        var sync = syncIn
        var harmonisch = harmonischIn
        val bi = Regie.bIndex(j, L, lage.kEin, lage.mal)
        val ga = pa.gesang()
        val gb = pb.gesang()
        val singtA = ga != null && mean(Regie.fenster(ga, i + L / 2, L - L / 2)) > 0.25
        val singtB = gb != null && mean(Regie.werte(gb, bi)) > 0.25
        val aEndet = pa.n - i < L
        val real = max(1, min(L, pa.n - i))
        val aBreak = mean(Regie.fenster(pa.drums(), i, real)) < 0.3
        val gesangKommt = ga != null && !aEndet && mean(Regie.fenster(ga, i, 2)) < 0.25 &&
            mean(Regie.fenster(ga, i + L / 2, L - L / 2)) > 0.25
        val nachTakt = j + L - lage.mal * lage.kEin
        val eA = if (i < pa.n) mean(pa.gesamt, i, i + max(1, L / 2)) else -30.0
        val eB = if (nachTakt < pb.n) mean(pb.gesamt, nachTakt, nachTakt + PHRASE) else eA
        val beruhigen = eB - eA < -3.0
        val eb = pb.etiketten()
        val bDropDanach = nachTakt < pb.n && eb[min(eb.size - 1, pb.phraseVon(nachTakt))] == "drop"
        if (lage.harm != null) harmonisch = lage.harm >= 0.75 || (harmonisch && lage.harm >= 0.55)

        val basis = mutableMapOf<String, Any>(
            "art" to "eigen", "lautstaerke" to "nahtlos", "eq" to "profi", "filter" to "keiner",
            "effekt" to "keiner", "effekt_ein" to "keiner", "loop" to "keiner", "loop_start" to -1,
            "loop_ein" to 0, "loop_ein_mal" to 0, "trick" to "keiner", "takte" to L, "weiter_takte" to L,
            "tempo_modus" to (if (vorlauf) "vorlauf" else "rampe"),
        )
        val halten = mapOf("lautstaerke" to "hart_aus", "eq" to "bass_ende")
        val ausklingen = mapOf("lautstaerke" to "letzter_takt", "eq" to "bass_ende")
        val kurz8 = mapOf("takte" to min(L, 8), "weiter_takte" to min(L, 8))
        val kandidaten = mutableListOf<KandidatRezept>()

        if (sync && !vorlauf) {
            sync = abs(240.0 / periode(pa.takte, i) - 240.0 / periode(pb.takte, j)) <= max(e.maxBpm, 0.05) + TEMPO_SPIEL
        } else if (vorlauf) {
            sync = abs(periode(pa.takte, i) / periode(pb.takte, j) - 1.0) <= VORLAUF_MAX
        }

        if (lage.dropK != 0 && sync) {
            val echo = e.experimente == "wild"
            val felder = basis.toMutableMap()
            felder["lautstaerke"] = "doppel"
            felder["eq"] = "bass_takt"
            felder["bass_takt"] = L - 1
            if (stemsDa) {
                felder["art"] = "double_drop"
                felder["gesang_takt"] = lage.dropK
            }
            if (echo) felder["effekt"] = "echo100_ende_aus"
            val text = (if (stemsDa) "Stems: " else "") + "Double Drop: beide Drops voll, nur A's Bass, " +
                (if (stemsDa) "B's Stimme kommt auf dem Drop, " else "") + "Bass-Switch am Ende" +
                (if (echo) ", A geht ins Echo" else "")
            return Triple("double_drop", felder, text)
        }

        val aEnde = if (i + L - 2 < pa.n) mean(Regie.fenster(pa.gesamt, i + L - 2, 2)) else -60.0
        val bDort = mean(Regie.werte(pb.gesamt, IntArray(2) { bi[max(0, bi.size - 2) + it] }))
        val effektHoerbar = aEnde >= bDort - 8.0
        val realA = if (i < pa.n) pa.gesamt.sliceArray(i until min(pa.n, i + L)) else DoubleArray(0)
        val loopHoerbar = realA.isNotEmpty() && mean(realA, realA.size / 2, realA.size) >= bDort - 8.0
        val mut = EXPERIMENT_WERT.getValue(e.experimente)
        val dreh = i / PHRASE + j / PHRASE + pa.n + pb.n

        fun kann(name: String, felderIn: Map<String, Any>, textIn: String, wert: Double = 1.0) {
            var felder = felderIn
            var text = textIn
            val loopArt = felder.text("loop", "keiner") != "keiner"
            val dortHoerbar = if (loopArt) loopHoerbar else effektHoerbar
            if (e.experimente == "wild" && dreh % 2 == 0 && dortHoerbar &&
                felder.text("art", "eigen") == "eigen" && name !in GESANG_REZEPTE &&
                felder.text("effekt", "keiner") == "keiner" && felder.text("trick", "keiner") == "keiner"
            ) {
                val fx = listOf("echo100", "pingpong50")[dreh / 2 % 2]
                felder = felder + mapOf("effekt" to "${fx}_ende_aus")
                if (felder.text("filter", "keiner") == "hp_aus") felder = felder + mapOf("filter" to "hp_aus_reso")
                text += if (fx == "echo100") ", A geht ins Echo" else ", A geht ins Ping-Pong-Delay"
            }
            val hoerbar = if (felder.text("loop", "keiner") != "keiner") loopHoerbar else effektHoerbar
            if (felder.text("effekt", "keiner") != "keiner" && !hoerbar) return
            val takteFeld = (felder["takte"] as? Int) ?: L
            if (!(loopOk || pa.n - i < takteFeld) && felder.text("loop", "keiner") != "keiner") return
            kandidaten.add(KandidatRezept(name, basis + felder, text, wert))
        }

        val loopWert = mapOf("kurz" to 1.9, "ausgewogen" to 2.2, "lang" to 2.5).getValue(e.modus) +
            (if (aEndet || gesangKommt || sofort) 1.0 else 0.0)

        if (!sync) {
            if (Regie.brueckenstart(pb, j)) {
                kann("bruecke_beatlos", mapOf("art" to "echo"),
                    "Tempo zu weit auseinander: A geht ins Echo, B startet in einem Teil ohne Drums", 3.0)
            }
            kann("schnitt", mapOf("art" to "schnitt"), "Tempo zu weit auseinander: harter Schnitt auf die 1",
                if (e.modus == "kurz") 2.0 else 0.5)
            kann("echo_out", mapOf("art" to "echo"), "Tempo zu weit auseinander: Echo-Out", 1.0)
        } else {
            val wild = e.experimente == "wild"
            val vollDanach = nachTakt < pb.n &&
                eb[min(eb.size - 1, pb.phraseVon(nachTakt))] in listOf("drop", "haupt")
            val aVoll = aEnde >= Profil.percentile(pa.gesamt, 75.0) - 6.0
            // Ohne Audio gilt ``_drop_ok`` wie im Prototyp: nicht pruefbar heisst bestanden.
            val dropGenau = bDropDanach && dropTakt(pb, nachTakt) == nachTakt && einsatz(pb, nachTakt) >= DROP_EINSATZ
            if (mut > 0 && (dropGenau || (wild && vollDanach && !bDropDanach)) && aVoll && !aEndet && lage.kEin == 0) {
                val drop = mutableMapOf<String, Any>("lautstaerke" to "drop", "eq" to "bass_ende")
                if (wild) drop["effekt_ein"] = "rueckhall"
                val tricks = listOf(
                    Triple(
                        "riser_drop",
                        drop + mapOf("filter" to (if (wild) "hp_aus_reso" else "hp_aus"), "trick" to "riser"),
                        "Noise-Riser, A dünnt mit " + (if (wild) "resonantem " else "") + "Hochpass aus",
                    ),
                    Triple("bremse_drop", drop + ("trick" to "bremse"), "Tape-Stop auf A"),
                    Triple("spinback_drop", drop + ("trick" to "spinback"), "Backspin auf A"),
                    Triple("gate_drop", drop + ("trick" to "gate"), "A wird zerhackt (Trans)"),
                )
                val stark = dropGenau && nachTakt >= 2 &&
                    mean(pb.gesamt, nachTakt, nachTakt + 2) - mean(pb.gesamt, nachTakt - 2, nachTakt) >= 6.0
                for ((k, t) in tricks.withIndex()) {
                    val (name, felder, text) = t
                    if (name == "riser_drop" && !stark) continue
                    if (name == "spinback_drop" && (!dropGenau || chill(a, pa) || chill(b, pb))) continue
                    kann(name, felder, text + ", B's Drop schlägt ein", mut + 0.05 * ((dreh + k) % tricks.size))
                }
            }
            if (mut > 0 && !aEndet) {
                val fx = listOf("flanger", "phaser", "crush")[dreh % 3]
                val echo = listOf("echo100", "pingpong50")[dreh / 3 % 2]
                val fxText = mapOf("flanger" to "einen Flanger", "phaser" to "einen Phaser", "crush" to "den Bitcrusher")
                    .getValue(fx)
                kann(
                    "fx_echo", ausklingen + mapOf("trick" to fx, "effekt" to "${echo}_ende_aus"),
                    "A bekommt $fxText und geht ins " + (if (echo == "echo100") "Echo" else "Ping-Pong-Delay"),
                    mut - 1.5,
                )
            }
            val ueb = if (stemsDa && lage.kEin == 0) gesangUebergabe(pa, pb, i, bi) else null
            if (ueb != null && harmonisch) {
                val text = if (ueb.first == "acapella") {
                    "Stems: A's Musik geht, A singt ${ueb.third} Takte über B weiter"
                } else {
                    "Stems: B's Gesang ${ueb.third} Takte über A's Musik, B's Musik erst danach"
                }
                kann(ueb.first, mapOf("art" to ueb.first, "gesang_takt" to ueb.second), text, 4.0)
            }
            if (lage.kEin != 0 && harmonisch) {
                val langLoop = lage.kEin * (lage.mal + 1) >= 8
                val felder = mutableMapOf<String, Any>("loop_ein" to lage.kEin, "loop_ein_mal" to lage.mal)
                if (langLoop) {
                    felder["filter"] = "tp_ein"
                    felder["eq"] = "bass_mitte"
                }
                if (aEndet) felder["loop"] = "auto"
                kann(
                    "intro_loop_b", felder,
                    "B's Intro im Loop" + (if (langLoop) ", öffnet sich mit dem Tiefpass" else "") +
                        ", damit Gesang/Drop erst nach der Blende kommen",
                    3.0,
                )
            }
            if (aBreak && !singtB && !aEndet && !sofort) {
                kann("breakdown", mapOf("eq" to "bass_mitte"), "B übernimmt im Break von A", 0.3)
            }
            if ((!aBreak || aEndet) && lage.kEin == 0) {
                kann(
                    "outro_loop", mapOf("loop" to "auto"),
                    if (aEndet) "A's Outro im Loop verlängert"
                    else if (gesangKommt) "A's Gesang käme noch: sauberer Takt im Loop"
                    else if (sofort) "WEITER: A loopt eine saubere Stelle, B übernimmt darunter"
                    else "A loopt eine saubere Stelle, B übernimmt darunter",
                    loopWert,
                )
                kann("loop_echo", ausklingen + mapOf("loop" to "auto", "effekt" to "echo50_ende_aus"),
                    "A loopt, am Ende geht A ins Echo", loopWert - 0.3)
                if (L >= 16) {
                    kann(
                        "loop_fx",
                        mapOf(
                            "lautstaerke" to "letzter_takt", "eq" to "bass_mitte", "filter" to "hp_aus",
                            "loop" to "auto", "effekt" to "echo100_ende_aus",
                        ),
                        "A loopt, wird mit dem Hochpass dünner und geht am Ende ins Echo", loopWert + 0.2,
                    )
                }
                if (!harmonisch) {
                    kann(
                        "loop_filter",
                        kurz8 + mapOf(
                            "lautstaerke" to "nahtlos", "eq" to "bass_mitte", "filter" to "hp_aus", "loop" to "auto",
                        ),
                        "Tonarten passen nicht: A loopt und dünnt mit Hochpass aus", loopWert + 0.3,
                    )
                }
            }
            if (e.modus == "kurz") {
                val bMitte = mean(Regie.werte(pb.gesamt, IntArray(2) { bi[L / 2 + it] }))
                val aMitte = mean(Regie.fenster(pa.gesamt, i + L / 2 - 2, 2))
                if (singtA && singtB && bMitte >= aMitte - 6.0) {
                    kann(
                        "schnitt_echo",
                        mapOf(
                            "lautstaerke" to (if (sofort) "mitte_weich" else "mitte"), "eq" to "keiner",
                            "effekt" to "echo50_mitte_aus",
                        ),
                        "beide singen: Schnitt in der Mitte, A geht ins Echo", 3.0,
                    )
                }
                if (bDropDanach) {
                    kann("echo_drop", halten + mapOf("effekt" to "echo100_ende_aus"),
                        "A geht ins Echo, B's Drop übernimmt", 3.0)
                }
                if (e.spielanteil == "schnell" && bDropDanach && harmonisch) {
                    kann("rolle", halten + mapOf("loop" to "rolle"), "Loop-Rolle in B's Drop", 0.3)
                    kann("delay_out", halten + mapOf("effekt" to "delay50_ende_aus"),
                        "kurzer Blend, A geht ins Delay", 2.0)
                }
                kann(
                    "kurz_eq",
                    if (harmonisch) emptyMap() else mapOf(
                        "lautstaerke" to "hart_aus", "eq" to "bass_mitte", "filter" to "hp_aus",
                    ),
                    if (harmonisch) "kurzer Profi-Blend" else "Tonarten passen nicht: A dünnt mit Hochpass aus",
                    1.0,
                )
            }
            if (e.modus == "ausgewogen") {
                if (stemsDa && singtA && singtB) {
                    kann("gesangsschutz", mapOf("art" to "gesangsschutz"),
                        "beide singen: Stimmen nacheinander (Stems)", 3.0)
                }
                if (!harmonisch) {
                    kann(
                        "filter_blend",
                        kurz8 + mapOf("lautstaerke" to "hart_aus", "eq" to "bass_mitte", "filter" to "hp_aus"),
                        "Tonarten passen nicht: kurzer Blend, A dünnt mit Hochpass aus", 1.5,
                    )
                }
                if (stemsDa && harmonisch && lage.kEin == 0) {
                    kann("drums_zuerst", mapOf("art" to "drums_zuerst"),
                        "Drums von B zuerst, dann Bass und Rest (Stems)", 2.0)
                    kann("melodie_zuerst", mapOf("art" to "melodie_zuerst"),
                        "Stems: B's Melodie zuerst über A's Groove, dann Drums und Bass, B's Gesang zuletzt", 3.4)
                }
                if (beruhigen) {
                    kann("tiefpass_aus", mapOf(
                        "lautstaerke" to "hart_aus", "eq" to "bass_mitte", "filter" to "tp_aus",
                    ), "B ruhiger: A wird mit Tiefpass dunkel", 2.0)
                }
                if (e.spielanteil == "schnell") {
                    kann("echo_out_blend", kurz8 + ausklingen + ("effekt" to "echo50_ende_aus"),
                        "Blend, am Ende geht A ins Echo", 2.0)
                }
                kann("profi_eq", emptyMap(), "Profi-Blend: Höhen → Mitten → Bass-Tausch", 1.0)
            }
            if (e.modus == "lang") {
                if (stemsDa && singtA && singtB) {
                    kann("gesangsschutz", mapOf("art" to "gesangsschutz"),
                        "beide singen: Stimmen nacheinander (Stems)", 3.0)
                }
                if (!harmonisch) {
                    kann(
                        "hochpass_hall",
                        mapOf(
                            "lautstaerke" to "letzter_takt", "eq" to "bass_mitte", "filter" to "hp_aus",
                            "effekt" to "hall_ende_aus",
                        ),
                        "Tonarten passen nicht: A dünnt mit Hochpass aus und geht in den Hall", 2.5,
                    )
                }
                if (beruhigen) {
                    kann(
                        "relaxed",
                        mapOf(
                            "lautstaerke" to "letzter_takt", "eq" to "bass_mitte", "filter" to "tp_aus",
                            "effekt" to "hall_ende_aus",
                        ),
                        "B ruhiger: A wird dunkel und klingt im Hall aus", 2.5,
                    )
                }
                if (stemsDa && harmonisch && lage.kEin == 0) {
                    kann("drums_zuerst", mapOf("art" to "drums_zuerst"),
                        "Drums von B zuerst, dann Bass und Rest (Stems)", 2.0)
                    kann("melodie_zuerst", mapOf("art" to "melodie_zuerst"),
                        "Stems: B's Melodie zuerst über A's Groove, dann Drums und Bass, B's Gesang zuletzt", 3.4)
                }
                kann("profi_eq", emptyMap(), "langer Profi-Blend: Höhen → Mitten → Bass-Tausch", 1.0)
            }
        }

        var auswahl: List<KandidatRezept> = kandidaten
        if (aEndet) {
            val mitLoop = kandidaten.filter { it.felder.text("loop", "keiner") != "keiner" || it.name in GESANG_REZEPTE }
            if (mitLoop.isNotEmpty()) auswahl = mitLoop
        }
        if (auswahl.isEmpty()) {
            kann("profi_eq", emptyMap(), "Profi-Blend")
            auswahl = kandidaten
        }
        val nachLoop = vorher != null && vorher in LOOP_REZEPTE
        val sortiert = auswahl.sortedWith(
            compareByDescending<KandidatRezept> {
                it.wert - (if (nachLoop && it.name in LOOP_REZEPTE) 1.5 else 0.0) +
                    REZEPT_GEWICHT * ((REZEPT_NOTE[it.name] ?: REZEPT_MITTEL) - REZEPT_MITTEL)
            },
        )
        val vorliebenMap = vorlieben ?: emptyMap()
        sortiert.firstOrNull { it.name != vorher && (vorliebenMap[it.name] ?: 0.0) > -2.0 }?.let {
            return Triple(it.name, it.felder, it.text)
        }
        sortiert.firstOrNull { it.name != vorher }?.let { return Triple(it.name, it.felder, it.text) }
        val erster = sortiert[0]
        return Triple(erster.name, erster.felder, erster.text)
    }

    /** `regie._bass_takt`: Takt des Bass-Tauschs. */
    fun bassTakt(pa: Profil, pb: Profil, i: Int, bi: IntArray, L: Int): Int {
        val raster = if (L >= 16) 4 else if (L >= 4) 2 else 1
        var erlaubt = (raster until L step raster).filter { it >= L / 2.0 && it <= 3.0 * L / 4.0 }
        if (erlaubt.isEmpty()) erlaubt = listOf(max(1, L / 2))
        val bb = Regie.werte(pb.bass(), IntArray(L) { bi[it] })
        for (k in erlaubt) {
            if (bb[k] > 0.5 && bb[k - 1] < 0.5) return k
        }
        val quelle = pa.stems?.get("bass") ?: DoubleArray(pa.n) { pa.baender[it][0] }
        val ba = Regie.fenster(quelle, i, L)
        val werte = erlaubt.map { ba[it] }
        val ptp = werte.max() - werte.min()
        if (ptp > 6.0) {
            var best = 0
            for (k in 1 until werte.size) if (werte[k] < werte[best]) best = k
            return erlaubt[best]
        }
        return erlaubt.last()
    }

    // --- Planen ----------------------------------------------------------------

    fun planen(
        a: Referenz?,
        pa: Profil,
        b: Referenz?,
        pb: Profil,
        e: Einstellungen,
        abS: Double,
        syncIn: Boolean,
        harmonisch: Boolean,
        sofort: Boolean = false,
        stemsDa: Boolean = false,
        vorher: String? = null,
        anzahl: Int = 3,
        vorlieben: Map<String, Double>? = null,
    ): List<Plan> {
        var abTakt = searchLeft(pa.takte, abS - 1e-3)
        var sync = syncIn
        val vorlauf = !sync && !sofort && e.keylock && e.maxBpm > 0 && pa.n > 1 && pb.n > 1 &&
            abs(periode(pb.takte, 0) / periode(pa.takte, abTakt) - 1.0) <= VORLAUF_MAX
        if (vorlauf) {
            sync = true
            abTakt += VORLAUF_TAKTE
        }
        val lagen = rangliste(pa, pb, e, abTakt, sofort, stemsDa, harmonisch, sync, a, b)
        val plaene = mutableListOf<Plan>()
        val gesehen = HashSet<Pair<Int, Int>>()

        fun planAus(lage: Lage, loopOk: Boolean = true): Plan {
            val (name, felderIn, text) = rezept(
                lage, pa, pb, e, sync, harmonisch, stemsDa, vorher, vorlieben, loopOk, sofort, a, b, vorlauf,
            )
            val felder = felderIn.toMutableMap()
            val takte = (felder["takte"] as? Int) ?: lage.takte
            if (felder.text("eq", "keiner") != "bass_takt") {
                felder["bass_takt"] = bassTakt(pa, pb, lage.i, Regie.bIndex(lage.j, takte, lage.kEin, lage.mal), takte)
            }
            val ausS = if (lage.i < pa.n) pa.takte[lage.i] else pa.takte.last()
            val stichworte = lage.teile.distinct().joinToString(", ")
            var einst = e
            for ((feld, wert) in felder) einst = einst.mit(feld, wert)
            return Plan(
                ausS, pb.takte[lage.j], takte, einst, name,
                text + (if (stichworte.isNotEmpty()) " · $stichworte" else ""),
                lage.punkte,
            )
        }

        for (lage in lagen) {
            val paar = lage.i to lage.j
            if (paar in gesehen) continue
            gesehen.add(paar)
            plaene.add(planAus(lage))
            if (plaene.size >= anzahl) break
        }
        return plaene
    }
}
