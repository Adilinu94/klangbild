package de.klangbild.core

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
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

    @Test
    fun `tempoMal verdoppelt und halbiert das Raster`() {
        if (!goldenDir.isDirectory) return
        val golden = Golden(goldenDir)
        val p = liesProfil(golden, golden.case("profil_synthetic_0").inputs["profile"]!! as JsonObject)

        val doppelt = tempoMal(p, 2.0)
        assertEquals(128, doppelt.n)
        val takte2 = doubleArrayOf(0.0, 1.0, 2.0, 3.0, 4.0, 5.0)
        for (i in takte2.indices) assertEquals(takte2[i], doppelt.takte[i], 1e-9, "takte2[$i]")
        assertEquals(-24.0, doppelt.baender[0][0], 1e-9)
        assertEquals(-22.0, doppelt.gesamt[3], 1e-9)
        assertEquals(-65.0, doppelt.stems!!.getValue("vocals")[2], 1e-9)
        assertEquals(true, doppelt.rasterOk[3])

        val halb = tempoMal(p, 0.5)
        assertEquals(32, halb.n)
        val takte05 = doubleArrayOf(0.0, 4.0, 8.0, 12.0)
        for (i in takte05.indices) assertEquals(takte05[i], halb.takte[i], 1e-9, "takte05[$i]")
        assertEquals(-24.0, halb.baender[0][0], 1e-9)
        assertEquals(-22.0, halb.gesamt[3], 1e-9)
        assertEquals(true, halb.rasterOk[3])
    }

    private fun vergleicheReihe(name: String, feld: String, erwartet: JsonObject, ist: DoubleArray) {
        val ref = Golden.toDoubles(erwartet.getValue(feld))
        assertEquals(ref.size, ist.size, "$name/$feld Laenge")
        for (i in ref.indices) assertEquals(ref[i], ist[i], 1e-6, "$name/$feld[$i]")
    }
}
