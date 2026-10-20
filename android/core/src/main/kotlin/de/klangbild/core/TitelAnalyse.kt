package de.klangbild.core

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.floatOrNull
import kotlinx.serialization.json.int
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put

/**
 * Ergebnis der Titelanalyse (M10), wie es die App je Titel ablegt: Tonart mit
 * Camelot-Code und integrierte Lautheit. Die Welle und die Takte kommen spaeter dazu,
 * darum traegt das Format eine Version.
 */
data class TitelAnalyse(
    val tonart: String,
    val camelot: String,
    val lufs: Double?,
    val bpm: Int? = null,
    val beats: List<Float> = emptyList(),
    val downbeats: List<Float> = emptyList(),
    val raster: List<Float> = emptyList(),
    val takte: List<Float> = emptyList(),
    val gesamt: List<Float> = emptyList(),
    val baender: List<List<Float>> = emptyList(),
    val chroma: List<List<Float>> = emptyList(),
    val version: Int = VERSION,
) {

    fun json(): String = buildJsonObject {
        put("version", version)
        put("tonart", tonart)
        put("camelot", camelot)
        put("lufs", lufs)
        put("bpm", bpm)
        put("beats", buildJsonArray { beats.forEach { add(JsonPrimitive(it)) } })
        put("downbeats", buildJsonArray { downbeats.forEach { add(JsonPrimitive(it)) } })
        put("raster", buildJsonArray { raster.forEach { add(JsonPrimitive(it)) } })
        put("takte", buildJsonArray { takte.forEach { add(JsonPrimitive(it)) } })
        put("gesamt", buildJsonArray { gesamt.forEach { add(JsonPrimitive(it)) } })
        put("baender", reihen(baender))
        put("chroma", reihen(chroma))
    }.toString()

    private fun reihen(werte: List<List<Float>>) = buildJsonArray {
        werte.forEach { reihe ->
            add(buildJsonArray { reihe.forEach { add(JsonPrimitive(it)) } })
        }
    }

    /**
     * Zurueck in ein [Profil] fuer die Regie. Die Dauer kommt aus dem letzten Takt plus
     * der Taktlaenge davor; ohne Takte gibt es kein Profil.
     */
    fun zuProfil(): Profil? {
        if (takte.isEmpty() || gesamt.isEmpty() || baender.size < 3) return null
        val taktZeiten = takte.map { it.toDouble() }.toDoubleArray()
        val letzter = taktZeiten.last()
        val abstand = if (taktZeiten.size >= 2) letzter - taktZeiten[taktZeiten.size - 2] else 0.0
        return Profil(
            takte = taktZeiten,
            baender = baender.map { reihe -> reihe.map { it.toDouble() }.toDoubleArray() }.toTypedArray(),
            gesamt = gesamt.map { it.toDouble() }.toDoubleArray(),
            stems = null,
            rasterOk = BooleanArray(takte.size) { true },
            dauer = letzter + abstand,
            chroma = chroma.takeIf { it.isNotEmpty() }
                ?.map { reihe -> reihe.map { it.toDouble() }.toDoubleArray() }
                ?.toTypedArray(),
        )
    }

    companion object {

        const val VERSION = 1

        /** Liest eine gespeicherte Analyse; null bei falscher Version oder kaputtem Text. */
        fun aus(text: String): TitelAnalyse? = try {
            val o = Json.parseToJsonElement(text).jsonObject
            val version = o["version"]?.jsonPrimitive?.int ?: 0
            val tonart = o["tonart"]?.jsonPrimitive?.content
            val camelot = o["camelot"]?.jsonPrimitive?.content
            if (version != VERSION || tonart == null || camelot == null) {
                null
            } else {
                TitelAnalyse(
                    tonart = tonart,
                    camelot = camelot,
                    lufs = (o["lufs"] as? JsonPrimitive)?.doubleOrNull,
                    bpm = (o["bpm"] as? JsonPrimitive)?.intOrNull,
                    beats = (o["beats"] as? JsonArray)
                        ?.mapNotNull { (it as? JsonPrimitive)?.floatOrNull }
                        ?: emptyList(),
                    downbeats = (o["downbeats"] as? JsonArray)
                        ?.mapNotNull { (it as? JsonPrimitive)?.floatOrNull }
                        ?: emptyList(),
                    raster = (o["raster"] as? JsonArray)
                        ?.mapNotNull { (it as? JsonPrimitive)?.floatOrNull }
                        ?: emptyList(),
                    takte = reihe(o["takte"]),
                    gesamt = reihe(o["gesamt"]),
                    baender = reihenAus(o["baender"]),
                    chroma = reihenAus(o["chroma"]),
                )
            }
        } catch (e: Exception) {
            null
        }

        private fun reihe(element: kotlinx.serialization.json.JsonElement?): List<Float> =
            (element as? JsonArray)?.mapNotNull { (it as? JsonPrimitive)?.floatOrNull } ?: emptyList()

        private fun reihenAus(element: kotlinx.serialization.json.JsonElement?): List<List<Float>> =
            (element as? JsonArray)?.map { reihe(it) } ?: emptyList()
    }
}
