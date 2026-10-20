package de.klangbild.core

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

/** Ein Bibliothekstitel mit allem, was der Bäcker braucht (BAUPLAN §4.5). */
data class BakeEintrag(
    val id: Int,
    val pfad: String,
    val bpm: Double,
    val camelot: String? = null,
    val downbeats: List<Double> = emptyList(),
    val abschnitte: List<Double> = emptyList(),
    val fein: List<List<Double>> = emptyList(),
    val gainDb: Double = 0.0,
)

/** Die Felder des Bäcker-Info-JSON, die der Controller braucht. */
data class BakeInfo(
    val sync: Boolean,
    val blendeS: Double,
    val takte: Int,
    val loopGuete: Double? = null,
    val art: String = "",
    val fehler: String? = null,
)

/**
 * Übergangsplan als JSON (BAUPLAN §4.5): Kotlin plant, C++ rendert. Die Einstellungen gehen
 * mit ihren Prototyp-Feldern (snake_case) hinüber; das Info-JSON kommt im selben Format zurück.
 */
object BakePlan {

    private val JSON = Json { ignoreUnknownKeys = true; isLenient = false }

    fun json(
        a: BakeEintrag,
        b: BakeEintrag,
        e: Einstellungen,
        abS: Double,
        ausS: Double,
        einS: Double,
        weiter: Boolean,
    ): String {
        val wurzel = buildJsonObject {
            put("a", eintrag(a))
            put("b", eintrag(b))
            put("einst", einstellungen(e))
            put("abS", JsonPrimitive(abS))
            put("ausS", JsonPrimitive(ausS))
            put("einS", JsonPrimitive(einS))
            put("weiter", JsonPrimitive(weiter))
        }
        return JSON.encodeToString(JsonObject.serializer(), wurzel)
    }

    fun info(text: String): BakeInfo {
        val obj = JSON.parseToJsonElement(text).jsonObject
        val loop = obj["loop_wahl"] as? JsonObject
        return BakeInfo(
            sync = obj["sync"]?.jsonPrimitive?.booleanOrNull ?: false,
            blendeS = obj["blende_s"]?.jsonPrimitive?.doubleOrNull ?: 0.0,
            takte = obj["takte"]?.jsonPrimitive?.intOrNull ?: 0,
            loopGuete = loop?.get("guete")?.jsonPrimitive?.doubleOrNull,
            art = obj["art"]?.jsonPrimitive?.contentOrNull ?: "",
            fehler = obj["fehler"]?.jsonPrimitive?.contentOrNull,
        )
    }

    private fun eintrag(e: BakeEintrag): JsonObject = buildJsonObject {
        put("id", JsonPrimitive(e.id))
        put("pfad", JsonPrimitive(e.pfad))
        put("bpm", JsonPrimitive(e.bpm))
        e.camelot?.let { put("camelot", JsonPrimitive(it)) }
        put("downbeats", zahlen(e.downbeats))
        put("abschnitte", zahlen(e.abschnitte))
        put("fein", buildJsonArray { for (paar in e.fein) add(zahlen(paar)) })
        put("gainDb", JsonPrimitive(e.gainDb))
    }

    private fun einstellungen(e: Einstellungen): JsonObject = buildJsonObject {
        for ((schluessel, wert) in e.toMap()) {
            when (wert) {
                is String -> put(schluessel, JsonPrimitive(wert))
                is Int -> put(schluessel, JsonPrimitive(wert))
                is Double -> put(schluessel, JsonPrimitive(wert))
                is Boolean -> put(schluessel, JsonPrimitive(wert))
                else -> Unit
            }
        }
    }

    private fun zahlen(werte: List<Double>): JsonArray = buildJsonArray {
        for (wert in werte) add(JsonPrimitive(wert))
    }
}
