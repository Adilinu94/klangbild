package de.klangbild.core

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.jsonPrimitive

/** Liest ein `Profil` aus dem Golden-Format (`_profile_data` in golden.py). */
internal fun liesProfil(golden: Golden, j: JsonObject): Profil {
    val takte = golden.values(j.getValue("takte"))
    val baenderFlach = golden.values(j.getValue("baender"))
    val n = takte.size
    val baender = Array(n) { i ->
        doubleArrayOf(baenderFlach[i * 3], baenderFlach[i * 3 + 1], baenderFlach[i * 3 + 2])
    }
    val gesamt = golden.values(j.getValue("gesamt"))
    val stemsElement = j["stems"]
    val stems = if (stemsElement is JsonObject) {
        stemsElement.mapValues { (_, v) -> golden.values(v) }
    } else {
        null
    }
    val rasterOk = (j.getValue("raster_ok") as JsonArray).map { it.jsonPrimitive.boolean }.toBooleanArray()
    val dauer = j.getValue("dauer").jsonPrimitive.content.toDouble()
    val chromaElement = j["chroma"]
    val chroma = when {
        chromaElement == null || chromaElement is JsonNull -> null
        chromaElement is JsonObject -> {
            val flach = golden.values(chromaElement)
            Array(n) { i -> DoubleArray(12) { k -> flach[i * 12 + k] } }
        }
        else -> {
            val flach = Golden.toDoubles(chromaElement)
            Array(n) { i -> DoubleArray(12) { k -> flach[i * 12 + k] } }
        }
    }
    return Profil(takte, baender, gesamt, stems, rasterOk, dauer, chroma)
}
