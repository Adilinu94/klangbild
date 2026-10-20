package de.klangbild.core

import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonPrimitive
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assumptions.assumeTrue
import org.junit.jupiter.api.Test
import java.io.File

/**
 * Golden-Test des Taktrasters (Port von `uebergang.regulaer`): normale Downbeats, konstanter
 * Versatz, ein Ausreisser und ein leerer Eintrag.
 */
class TaktrasterTest {

    private val dir: File = File(System.getProperty("klangbild.goldendir") ?: "testdata/golden")

    @Test
    fun `regulaer trifft die vier Golden-Faelle`() {
        assumeTrue(dir.isDirectory, "Golden-Ordner fehlt: ${dir.absolutePath}")
        val g = Golden(dir)
        for (name in listOf("regulaer_normal", "regulaer_versatz", "regulaer_ausreisser", "regulaer_leer")) {
            val fall = g.case(name)
            val ein = fall.inputs
            val downbeats = (ein["downbeats"] ?: continue).jsonArray.map { it.jsonPrimitive.content.toDouble() }
            val bpm = ein["bpm"]!!.jsonPrimitive.content.toDouble()
            val bis = ein["bis_s"]!!.jsonPrimitive.content.toDouble()
            val erwartet = Golden.toDoubles(fall.expected)
            val aus = Taktraster.regulaer(downbeats, bpm, bis)

            assertEquals(erwartet.size, aus.size, name)
            for (i in erwartet.indices) {
                assertEquals(erwartet[i], aus[i], 1e-6, "$name[$i]")
            }
        }
    }
}
