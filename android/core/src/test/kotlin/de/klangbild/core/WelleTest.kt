package de.klangbild.core

import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assumptions.assumeTrue
import org.junit.jupiter.api.Test
import java.io.File

/**
 * Golden-Test der farbigen Wellenform (Port von `welle.berechnen`): synthetisches Signal,
 * kurzes Signal (Padding) und Stille. Verglichen werden die uint8-Spalten peak/r/g/b.
 */
class WelleTest {

    private val dir: File = File(System.getProperty("klangbild.goldendir") ?: "testdata/golden")

    @Test
    fun `Wellenform trifft die drei Golden-Faelle`() {
        assumeTrue(dir.isDirectory, "Golden-Ordner fehlt: ${dir.absolutePath}")
        val g = Golden(dir)

        for (name in listOf("welle_synthetic", "welle_kurz", "welle_stille")) {
            val fall = g.case(name)
            val ein = fall.inputs
            val rate = ein["rate"]?.jsonPrimitive?.content?.toInt() ?: Welle.RATE
            val verweis = ein["mono"]!!.jsonObject
            val shape = verweis["shape"]!!.jsonArray.map { it.jsonPrimitive.content.toInt() }
            val mono = g.f32(verweis["file"]!!.jsonPrimitive.content, shape)

            val spalten = Welle.berechnen(mono, rate)
            val erwartet = fall.expected.jsonObject

            pruefe("$name peak", g.values(erwartet.getValue("peak")), spalten.peak)
            pruefe("$name r", g.values(erwartet.getValue("r")), spalten.r)
            pruefe("$name g", g.values(erwartet.getValue("g")), spalten.g)
            pruefe("$name b", g.values(erwartet.getValue("b")), spalten.b)
        }
    }

    private fun pruefe(name: String, soll: DoubleArray, ist: IntArray) {
        assertEquals(soll.size, ist.size, "$name: Laenge")
        for (i in soll.indices) {
            assertEquals(soll[i].toInt(), ist[i], "$name[$i]")
        }
    }
}
