package de.klangbild.core

import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

/**
 * Auto-DJ-Titelwahl (Port von `live.Wiedergabe._autodj_wahl` und `_plan_track`).
 *
 * Die besten 6 nach Tempo/Tonart/Energie, dann entscheidet, wie gut sich jeder wirklich mischen
 * laesst (bester Regie-Plan aus den Profilen) und der Energiebogen: nach drei Anstiegen eine
 * Erholung, nach zwei Abstiegen wieder hoch. Ein Sprung im Energielevel kostet bis zu 8 Punkte.
 */
object AutoDjWahl {

    /** Ein Bibliothekstitel mit seinem Profil (Profil darf fehlen). */
    data class Kandidat(val track: Track, val profil: Profil?)

    /** `live._plan_track`: Genre aus dem Ordner, Energielevel aus dem Profil. */
    fun planTrack(track: Track, bpm: Double? = null, energieLevel: Double? = null): Track {
        val ordner = ordnerName(track.pfad)
        return track.copy(
            bpm = bpm ?: track.bpm,
            energie = energieLevel,
            genre = if (ordner.lowercase() == "upload") null else ordner.ifEmpty { null },
        )
    }

    /** Titel ohne Pfad und Endung (wie `Eintrag.titel`). */
    fun titel(pfad: String): String =
        pfad.substringAfterLast('/').substringAfterLast('\\').substringBeforeLast('.')

    /** `live._gleicher_titel`: dieselbe Aufnahme in zwei Dateien/Versionen. */
    fun gleicherTitel(a: String, b: String): Boolean {
        val x = a.lowercase().filter { it.isLetterOrDigit() }
        val y = b.lowercase().filter { it.isLetterOrDigit() }
        val (kurz, lang) = if (x.length <= y.length) x to y else y to x
        return kurz.length >= 8 && lang.startsWith(kurz)
    }

    private fun ordnerName(pfad: String): String {
        val teile = pfad.replace('\\', '/').split('/')
        return if (teile.size >= 2) teile[teile.size - 2] else ""
    }

    private fun meanTeil(x: DoubleArray, von: Int, bis: Int): Double {
        val a = max(0, von)
        val b = min(bis, x.size)
        if (b <= a) return 0.0
        var s = 0.0
        for (i in a until b) s += x[i]
        return s / (b - a)
    }

    /**
     * Naechster Titel oder null. `bpm` ist A's lokales Tempo, `abOriginalS` die Ausstiegsstelle in
     * Originalsekunden, [energieSchritte] die dB-Spruenge der letzten Wechsel.
     */
    fun waehlen(
        aktuell: Track,
        aktuellProfil: Profil?,
        bpm: Double,
        abOriginalS: Double,
        kandidaten: List<Kandidat>,
        gespielt: Set<Int>,
        e: Einstellungen,
        energieSchritte: List<Double>,
        stemsVerfuegbar: (Int) -> Boolean = { false },
    ): Int? {
        val aktuellerTitel = titel(aktuell.pfad)
        val gefiltert = kandidaten.filter {
            it.track.id != aktuell.id && it.track.id !in gespielt &&
                !gleicherTitel(titel(it.track.pfad), aktuellerTitel)
        }
        val ta = planTrack(aktuell, bpm, aktuellProfil?.energielevel())
        val top = Planer.rangliste(
            ta,
            gefiltert.map { planTrack(it.track, energieLevel = it.profil?.energielevel()) },
            e.maxBpm,
            e.harmonie,
        )
        if (top.isEmpty()) return null
        val einst = Einstellungen.regieEinst(e) ?: return top[0].id
        val pa = aktuellProfil ?: return top[0].id

        val schritte = energieSchritte.takeLast(3)
        val ziel = if (schritte.size == 3 && schritte.min() > 1.0) {
            -4.0 to 0.0
        } else if (schritte.size >= 2 && schritte.takeLast(2).max() < -1.0) {
            0.0 to 4.0
        } else {
            -3.0 to 3.0
        }
        val eA = meanTeil(pa.gesamt, pa.n - 32, pa.n) + (if (einst.lautheit) aktuell.gainDb else 0.0)

        val werte = LinkedHashMap<Int, Double>()
        for ((rang, k) in top.withIndex()) {
            val b = kandidaten.firstOrNull { it.track.id == k.id } ?: continue
            val pb = b.profil ?: continue
            val bTempo = k.bpm ?: b.track.bpm ?: continue
            val sync = listOf(1.0, 2.0, 0.5).minOf { abs(bpm - it * bTempo) } <= max(einst.maxBpm, 0.05)
            val harmonisch = Planer.harmonieNote(aktuell.camelot, b.track.camelot).second != "fremd"
            val stems = einst.stems && stemsVerfuegbar(aktuell.id) && stemsVerfuegbar(b.track.id)
            val plaene = RegiePlanung.planen(
                RegiePlanung.Referenz(aktuell.id, aktuell.pfad, aktuell.camelot), pa,
                RegiePlanung.Referenz(b.track.id, b.track.pfad, b.track.camelot), pb,
                einst, abOriginalS, sync, harmonisch, anzahl = 1, stemsDa = stems,
            )
            val plan = plaene.firstOrNull() ?: continue
            val eB = meanTeil(pb.gesamt, 0, 48) + (if (einst.lautheit) b.track.gainDb else 0.0)
            val schritt = eB - eA
            val bogen = if (schritt >= ziel.first && schritt <= ziel.second) {
                1.5
            } else {
                -0.3 * min(abs(schritt - ziel.first), abs(schritt - ziel.second))
            }
            val stimmung = if (k.energie == null || ta.energie == null) 0.0 else -8.0 * abs(k.energie - ta.energie)
            werte[k.id] = plan.punkte + bogen + stimmung - 0.6 * rang
        }
        if (werte.isEmpty()) return top[0].id
        return werte.maxByOrNull { it.value }?.key
    }
}
