package de.klangbild.core

import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assumptions.assumeTrue
import org.junit.jupiter.api.Test
import java.io.File

/**
 * Golden-Test der integrierten Lautheit (ITU-R BS.1770-4): synthetisch (Stereo), kurzes
 * Signal (Block wird gekürzt) und Stille (kein Block über dem absoluten Tor).
 * Der True Peak (soxr-Überabtastung) folgt später.
 */
class LautheitTest {

    private val dir: File = File(System.getProperty("klangbild.goldendir") ?: "testdata/golden")

    @Test
    fun `integrierte Lautheit trifft die drei Golden-Faelle`() {
        assumeTrue(dir.isDirectory, "Golden-Ordner fehlt: ${dir.absolutePath}")
        val g = Golden(dir)

        for (name in listOf("lufs_synthetic", "lufs_kurz", "lufs_stille")) {
            val fall = g.case(name)
            val ein = fall.inputs
            val rate = ein["rate"]!!.jsonPrimitive.content.toInt()
            val verweis = ein["signal"]!!.jsonObject
            val shape = verweis["shape"]!!.jsonArray.map { it.jsonPrimitive.content.toInt() }
            val roh = g.f32(verweis["file"]!!.jsonPrimitive.content, shape)

            val kanaele = if (shape.size == 2) {
                Array(shape[1]) { k -> DoubleArray(shape[0]) { i -> roh[i * shape[1] + k].toDouble() } }
            } else {
                arrayOf(DoubleArray(roh.size) { roh[it].toDouble() })
            }
            val erwartet = when (val text = fall.expected.jsonObject.getValue("integrated").jsonPrimitive.content) {
                "-inf", "-Infinity" -> Double.NEGATIVE_INFINITY
                else -> text.toDouble()
            }
            val berechnet = Lautheit.integriert(kanaele, rate)

            if (erwartet.isInfinite()) {
                assertEquals(erwartet, berechnet, "$name: unendlich erwartet")
            } else {
                assertEquals(erwartet, berechnet, 1e-6, "$name: integrierte Lautheit")
            }
        }
    }
}
