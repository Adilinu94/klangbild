package de.klangbild.core

import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.double
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonPrimitive
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import java.io.File

/** Golden-Tests der Selbstkontrolle (`regie.pruefen`). */
class RegieTest {

    private val goldenDir = File(
        System.getProperty("klangbild.goldendir") ?: "testdata/golden",
    )

    @Test
    fun `pruefen entspricht dem Prototyp`() {
        if (!goldenDir.isDirectory) return
        val golden = Golden(goldenDir)
        for (name in listOf("pruefen_normal", "pruefen_laut", "pruefen_loch", "pruefen_ausnahme")) {
            val fall = golden.case(name)
            val blende = golden.values(fall.inputs.getValue("blende")).map { it.toFloat() }.toFloatArray()
            val rate = fall.inputs.getValue("rate").jsonPrimitive.int
            val nTakte = fall.inputs.getValue("n_takte").jsonPrimitive.int
            val pa = liesProfil(golden, fall.inputs.getValue("pa") as JsonObject)
            val pb = liesProfil(golden, fall.inputs.getValue("pb") as JsonObject)
            val ausS = fall.inputs.getValue("aus_s").jsonPrimitive.double
            val einS = fall.inputs.getValue("ein_s").jsonPrimitive.double
            val gainA = fall.inputs.getValue("gain_a").jsonPrimitive.double
            val gainB = fall.inputs.getValue("gain_b").jsonPrimitive.double
            val rezept = fall.inputs.getValue("rezept").jsonPrimitive.content

            val ist = Regie.pruefen(blende, rate, nTakte, pa, pb, ausS, einS, gainA, gainB, rezept)
            val erwartet = fall.expected
            val ref = if (erwartet is JsonNull) null else erwartet.jsonPrimitive.content
            assertEquals(ref, ist, name)
        }
    }
}
