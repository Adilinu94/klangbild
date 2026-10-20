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
    val version: Int = VERSION,
) {

    fun json(): String = buildJsonObject {
        put("version", version)
        put("tonart", tonart)
        put("camelot", camelot)
        put("lufs", lufs)
        put("bpm", bpm)
        put("beats", buildJsonArray { beats.forEach { add(JsonPrimitive(it)) } })
    }.toString()

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
                )
            }
        } catch (e: Exception) {
            null
        }
    }
}
