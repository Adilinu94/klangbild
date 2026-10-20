package de.klangbild.core

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.jsonPrimitive
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Test
import java.io.File

/**
 * Golden-Tests des Profils (BAUPLAN-ANDROID M7): abgeleitete Reihen gegen
 * `profil_synthetic_*` aus dem Python-Export.
 */
class ProfilTest {

    private val goldenDir = File(
        System.getProperty("klangbild.goldendir") ?: "testdata/golden",
    )

    @Test
    fun `abgeleitete Reihen entsprechen dem Prototyp`() {
        if (!goldenDir.isDirectory) return
        val golden = Golden(goldenDir)
        val namen = listOf("profil_synthetic_0", "profil_synthetic_1", "profil_synthetic_2")
        for (name in namen) {
            val fall = golden.case(name)
            val profil = liesProfil(golden, fall.inputs["profile"]!! as JsonObject)
            val erwartet = fall.expected as JsonObject

            val gesang = erwartet["gesang"]
            if (gesang == null || gesang is JsonNull) {
                assertNull(profil.gesang(), "$name/gesang")
            } else {
                vergleicheReihe(name, "gesang", erwartet, profil.gesang()!!)
            }
            vergleicheReihe(name, "drums", erwartet, profil.drums())
            vergleicheReihe(name, "bass", erwartet, profil.bass())
            vergleicheReihe(name, "dichte", erwartet, profil.dichte())
            vergleicheReihe(name, "phrase_start", erwartet, DoubleArray(12) { profil.phraseStart(it).toDouble() })
            vergleicheReihe(name, "phrase_ab", erwartet, DoubleArray(profil.n) { profil.phraseAb(it).toDouble() })
            assertEquals(
                (erwartet["versatz"]!!.jsonPrimitive.content).toInt(),
                profil.versatz(),
                "$name/versatz",
            )
            assertEquals(
                (erwartet["etiketten"] as JsonArray).map { it.jsonPrimitive.content },
                profil.etiketten(),
                "$name/etiketten",
            )
        }
    }

    private fun liesProfil(golden: Golden, j: JsonObject): Profil {
        val takte = golden.values(j.getValue("takte"))
        val baenderFlach = golden.values(j.getValue("baender"))
        val n = takte.size
        val baender = Array(n) { i -> doubleArrayOf(baenderFlach[i * 3], baenderFlach[i * 3 + 1], baenderFlach[i * 3 + 2]) }
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

    private fun vergleicheReihe(name: String, feld: String, erwartet: JsonObject, ist: DoubleArray) {
        val ref = Golden.toDoubles(erwartet.getValue(feld))
        assertEquals(ref.size, ist.size, "$name/$feld Laenge")
        for (i in ref.indices) assertEquals(ref[i], ist[i], 1e-6, "$name/$feld[$i]")
    }
}
