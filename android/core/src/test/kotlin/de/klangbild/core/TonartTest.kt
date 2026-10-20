package de.klangbild.core

import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assumptions.assumeTrue
import org.junit.jupiter.api.Test
import java.io.File

/**
 * Golden-Test der Tonart-Schaetzung (Port von `keyestimate.tonart_schaetzen`): drei Signale
 * (kurz, Stille, synthetisch) mal vier Profile (Krumhansl, Aarden, Temperley, Ensemble).
 */
class TonartTest {

    private val dir: File = File(System.getProperty("klangbild.goldendir") ?: "testdata/golden")

    @Test
    fun `Tonart trifft die zwoelf Golden-Faelle`() {
        assumeTrue(dir.isDirectory, "Golden-Ordner fehlt: ${dir.absolutePath}")
        val g = Golden(dir)
        val namen = ArrayList<String>()
        for (signal in listOf("kurz", "stille", "synthetic")) {
            for (profil in listOf("aarden", "ensemble", "krumhansl", "temperley")) {
                namen.add("key_${signal}_$profil")
            }
        }

        for (name in namen) {
            val fall = g.case(name)
            val ein = fall.inputs
            val rate = ein["rate"]!!.jsonPrimitive.content.toInt()
            val profil = ein["profile"]?.jsonPrimitive?.content ?: "ensemble"
            val signalVerweis = ein["signal"]!!.jsonObject
            val shape = signalVerweis["shape"]!!.jsonArray.map { it.jsonPrimitive.content.toInt() }
            val signal = g.f32(signalVerweis["file"]!!.jsonPrimitive.content, shape)

            val erwartet = fall.expected.jsonObject
            val tonart = TonartSchaetzung.schaetzen(signal, rate, profil)

            assertEquals(erwartet.getValue("name").jsonPrimitive.content, tonart.name, "$name: Name")
            assertEquals(erwartet.getValue("camelot").jsonPrimitive.content, tonart.camelot, "$name: Camelot")
            assertEquals(
                erwartet.getValue("punkte").jsonPrimitive.content.toDouble(),
                tonart.punkte,
                1e-6,
                "$name: Punkte",
            )
            assertEquals(
                erwartet.getValue("vertrauen").jsonPrimitive.content.toDouble(),
                tonart.vertrauen,
                1e-6,
                "$name: Vertrauen",
            )
        }
    }
}
