package de.klangbild.core

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.io.File
import java.math.BigDecimal
import java.math.RoundingMode
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

/**
 * Erwartete Uebergangsnoten aller Titelpaare (Port von `prototyp/klangbild/paarnoten.py`).
 *
 * Je Paar A -> B im Tempo-Rahmen plant die Regie den besten Uebergang aus den Profilen. Die Note
 * wird auf 1..5 gestreckt (der Kritiker ist im Desktop nicht aktiv). Die Reihenfolge der Playlist
 * richtet sich danach.
 */
class Paarnoten(val analyseVersion: String, val datei: File? = null) {

    val version: String = "$analyseVersion|$REGIE_VERSION"

    /** Schluessel "a_b" -> [Note, Rezept, Punkte]. */
    val daten: MutableMap<String, List<Any>> = mutableMapOf()

    init {
        laden()
    }

    private fun laden() {
        val f = datei ?: return
        try {
            if (!f.isFile) return
            val roh = JSON.parseToJsonElement(f.readText(Charsets.UTF_8)).jsonObject
            if (roh["version"]?.jsonPrimitive?.content != version) return
            val noten = roh["noten"]?.jsonObject ?: return
            for ((schluessel, wert) in noten) {
                val liste = wert.jsonArray
                val eintrag = mutableListOf<Any>()
                for (element in liste) {
                    val primitiv = element.jsonPrimitive
                    eintrag.add(if (primitiv.isString) primitiv.content else primitiv.content.toDouble())
                }
                daten[schluessel] = eintrag
            }
        } catch (_: Exception) {
            daten.clear()
        }
    }

    fun neuLaden(): Paarnoten = Paarnoten(analyseVersion, datei)

    fun note(a: Int, b: Int): Double? = (daten["${a}_$b"]?.getOrNull(0) as? Double)

    fun rezept(a: Int, b: Int): String? = (daten["${a}_$b"]?.getOrNull(1) as? String)

    fun setzen(a: Int, b: Int, note: Double, rezept: String?, punkte: Double) {
        daten["${a}_$b"] = listOf(note, rezept ?: "", punkte)
    }

    fun speichern() {
        val f = datei ?: return
        val noten = buildJsonObject {
            for ((schluessel, werte) in daten.toSortedMap()) {
                val liste = buildJsonArray {
                    add(JsonPrimitive(werte[0] as Double))
                    add(JsonPrimitive(werte.getOrNull(1) as? String ?: ""))
                    (werte.getOrNull(2) as? Double)?.let { add(JsonPrimitive(it)) }
                }
                put(schluessel, liste)
            }
        }
        val inhalt = buildJsonObject {
            put("version", JsonPrimitive(version))
            put("noten", noten)
        }
        f.parentFile?.mkdirs()
        f.writeText(JSON.encodeToString(JsonObject.serializer(), inhalt), Charsets.UTF_8)
    }

    companion object {
        const val REGIE_VERSION = "2026-10-18c"

        private val JSON = Json { ignoreUnknownKeys = true; isLenient = false }

        /** `paarnoten.im_tempo`: passt das Tempo (auch Doppel-/Halbtempo)? */
        fun imTempo(bpmA: Double, bpmB: Double, maxBpm: Double): Boolean =
            listOf(1.0, 2.0, 0.5).minOf { abs(bpmA - it * bpmB) } <= max(maxBpm, 0.05)

        /**
         * `paarnoten.rechnen`: fehlende Paarnoten fuer `ids` berechnen, gibt die Zahl neuer Paare zurueck.
         * Ohne Kritiker werden die Regie-Punkte ueber die 5./95.-Perzentile auf 1..5 gestreckt.
         */
        fun rechnen(
            bib: Map<Int, Track>,
            noten: Paarnoten,
            e: Einstellungen,
            profile: (Int) -> Profil?,
            ids: List<Int>? = null,
            harmonisch: (Track, Track) -> Boolean = { a, b ->
                Planer.harmonieNote(a.camelot, b.camelot).second != "fremd"
            },
            zeitlimitS: Double? = null,
        ): Int {
            val auswahl = (ids ?: bib.keys.sorted()).filter { it in bib && profile(it) != null }
            val beginn = System.nanoTime()
            val roh = mutableListOf<Triple<String, Double, String?>>()
            for (a in auswahl) {
                val pa = profile(a) ?: continue
                val ta = bib.getValue(a)
                for (b in auswahl) {
                    if (a == b || "${a}_$b" in noten.daten) continue
                    val tb = bib.getValue(b)
                    if (ta.bpm == null || tb.bpm == null || !imTempo(ta.bpm, tb.bpm, e.maxBpm)) continue
                    val pb = profile(b) ?: continue
                    val sync = abs(ta.bpm - tb.bpm) <= max(e.maxBpm, 0.05)
                    val plaene = RegiePlanung.planen(
                        RegiePlanung.Referenz(ta.id, ta.pfad, ta.camelot), pa,
                        RegiePlanung.Referenz(tb.id, tb.pfad, tb.camelot), pb,
                        e, 0.0, sync, harmonisch(ta, tb), anzahl = 1,
                    )
                    val plan = plaene.firstOrNull() ?: continue
                    roh.add(Triple("${a}_$b", plan.punkte, plan.rezept))
                    if (zeitlimitS != null && (System.nanoTime() - beginn) / 1e9 > zeitlimitS) break
                }
                if (zeitlimitS != null && (System.nanoTime() - beginn) / 1e9 > zeitlimitS) break
            }
            if (roh.isNotEmpty()) {
                val punkte = (roh.map { it.second } +
                    noten.daten.values.filter { it.size > 2 }.map { (it[2] as Double) }).toDoubleArray()
                val lo: Double
                val hi: Double
                if (punkte.size > 1) {
                    lo = Profil.percentile(punkte, 5.0)
                    hi = Profil.percentile(punkte, 95.0)
                } else {
                    lo = punkte[0] - 1.0
                    hi = punkte[0] + 1.0
                }
                for ((schluessel, p, rezept) in roh) {
                    val note = (1.0 + 4.0 * (p - lo) / max(hi - lo, 1e-9)).coerceIn(1.0, 5.0)
                    noten.setzen(
                        schluessel.substringBefore('_').toInt(),
                        schluessel.substringAfter('_').toInt(),
                        runde(note, 2), rezept, runde(p, 2),
                    )
                }
            }
            return roh.size
        }

        /** Python-`round(x, n)`: halbe Werte zur geraden Zahl auf der exakten Binaerdarstellung. */
        fun runde(x: Double, stellen: Int): Double =
            BigDecimal(x).setScale(stellen, RoundingMode.HALF_EVEN).toDouble()
    }
}
