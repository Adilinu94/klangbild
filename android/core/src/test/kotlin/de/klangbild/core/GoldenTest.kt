package de.klangbild.core

import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Assumptions.assumeTrue
import org.junit.jupiter.api.Test
import java.io.File

/**
 * Golden-Leser-Test (BAUPLAN-ANDROID §12.1, Aufgabe T0.3).
 *
 * Prüft, dass der Kotlin-Leser JSON + `.f32` genau wie der Python-Export liest.
 * Die eigentlichen Rechen-Golden-Tests (Regie, Profil, Planer, Einstellungen)
 * folgen ab M7 und nutzen denselben Leser.
 *
 * Der Golden-Ordner wird per Systemeigenschaft `klangbild.goldendir` übergeben
 * (Gradle setzt ihn auf `android/testdata/golden`). Fehlt er, überspringt der
 * Test, statt falsch rot zu werden.
 */
class GoldenTest {

    private val dir: File =
        File(System.getProperty("klangbild.goldendir") ?: "testdata/golden")

    private fun golden(): Golden {
        assumeTrue(dir.isDirectory, "Golden-Ordner fehlt: ${dir.absolutePath}")
        return Golden(dir)
    }

    @Test
    fun `liest den Reader-Dummy aus JSON und f32`() {
        val g = golden()
        val case = g.case("reader_dummy")

        assertEquals("identity", case.function)
        assertEquals("values", case.tolerance)

        // Der Verweis im JSON zeigt auf die f32-Datei: Form, Zählung.
        val audio = case.inputs["audio"]!!.jsonObject
        val shape = audio["shape"]!!.jsonArray.map { it.jsonPrimitive.content.toInt() }
        val count = audio["count"]!!.jsonPrimitive.content.toInt()
        assertEquals(listOf(2, 2), shape)
        assertEquals(4, count)

        val werte = g.f32(audio["file"]!!.jsonPrimitive.content, shape)
        assertEquals(count, werte.size)

        // Erwartete Werte stehen in `expected.values` (kurzes JSON-Array) und
        // stimmen bitgenau mit der gelesenen f32-Datei überein.
        val erwartet = case.expected.jsonObject["values"]!!.jsonArray
            .map { it.jsonPrimitive.content.toDouble() }.toDoubleArray()
        assertEquals(erwartet.toList(), werte.map { it.toDouble() }.toList())

        // Kanalzählung aus dem Fall stimmt zur Form.
        assertEquals(2, case.expected.jsonObject["channels"]!!.jsonPrimitive.content.toInt())
        assertEquals(2, case.expected.jsonObject["frames"]!!.jsonPrimitive.content.toInt())
    }

    @Test
    fun `liest eine kurze Referenzkurve gegen die f32-Datei`() {
        // kurven_basis ist der erste Fall, den ab T5.1 ein DSP-Test gegenrechnet.
        // `expected` ist hier ein Paar aus zwei Kurven (aus/ein); die Werte stehen
        // als JSON-Zahlen vor, nicht als f32-Verweis.
        val g = golden()
        val case = g.case("kurven_basis")
        assertEquals("mix.equal_power_blende", case.function)

        val aus = Golden.toDoubles(case.expected.jsonArray[0])
        val ein = Golden.toDoubles(case.expected.jsonArray[1])
        assertEquals(64, aus.size)
        assertEquals(64, ein.size)
        // endpoint=False: die Phase endet bei 63/64·π/2, also kurz vor 1.
        // Der letzte "ein"-Wert ist sin(63/64·π/2), nicht genau 1.
        assertEquals(1.0, aus[0], 1e-6)
        assertEquals(kotlin.math.sin(63.0 / 64.0 * Math.PI / 2.0), ein[63], 1e-6)

        // Equipotenz: cos^2 + sin^2 = 1 an jeder Stelle.
        for (i in aus.indices) {
            assertEquals(1.0, aus[i] * aus[i] + ein[i] * ein[i], 1e-6)
        }
    }

    @Test
    fun `liest ein langes Array ueber die f32-Datei`() {
        val g = golden()
        val case = g.case("band_200")

        // Das Eingangssignal liegt als langer f32-Verweis vor.
        val signal = case.inputs["signal"]!!.jsonObject
        val shape = signal["shape"]!!.jsonArray.map { it.jsonPrimitive.content.toInt() }
        val werte = g.f32(signal["file"]!!.jsonPrimitive.content, shape)
        assertEquals(shape[0] * shape[1], werte.size)

        // `expected` ist ein Paar aus zwei gleich langen Bändern (low, high).
        val expected = case.expected.jsonArray
        val low = g.values(expected[0])
        val high = g.values(expected[1])
        assertEquals(werte.size, low.size)
        assertEquals(werte.size, high.size)

        // Komplementär: low + high = Eingang (bitgenau in float32-Grenzen).
        var maxFehler = 0.0
        for (i in werte.indices) {
            maxFehler = maxOf(maxFehler, kotlin.math.abs((low[i] + high[i]) - werte[i]))
        }
        assertTrue(maxFehler <= 1e-4) { "low+high weicht um $maxFehler vom Eingang ab" }
    }

    @Test
    fun `Manifest kennt jeden seiner Faelle als Datei`() {
        val g = golden()
        val manifest = g.manifest()
        val faelle = manifest["cases"]!!.jsonArray.map { it.jsonPrimitive.content }.toSet()
        val dateien = g.caseNames().toSet()

        // Jeder im Manifest genannte Fall hat eine JSON-Datei.
        for (fall in faelle) {
            assertTrue(fall in dateien, "Fall ohne Datei: $fall")
        }
        // Umgekehrt liegen im Ordner höchstens die Zusatzdateien (sos_*), die das
        // Manifest nicht als Fall führt, sondern als Tabelle.
        val zusatz = dateien - "manifest" - faelle
        assertTrue(zusatz.all { it.startsWith("sos_") }) { "Unerwartete Zusatzdateien: $zusatz" }

        val toleranzen = manifest["tolerances"]!!.jsonObject
        for (name in listOf("values", "dsp", "reverb", "warp")) {
            assertTrue(name in toleranzen, "Toleranz fehlt im Manifest: $name")
        }
        // Die Länge muss zur Fallbeschreibung passen (Abnahme T0.2).
        assertEquals(faelle.size, manifest["cases"]!!.jsonArray.size)
    }
}
