package de.klangbild.core

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.double
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import java.io.File

/**
 * Golden-Tests der Einstellungen (BAUPLAN-ANDROID M7): alle `einstellungen_*`-Faelle
 * des Python-Exports gegen [Einstellungen.ausDict].
 */
class EinstellungenTest {

    private val goldenDir = File(
        System.getProperty("klangbild.goldendir") ?: "testdata/golden",
    )

    @Test
    fun `ausDict entspricht dem Prototyp in allen Faellen`() {
        if (!goldenDir.isDirectory) return   // ohne Export ueberspringen, nicht falsch rot
        val golden = Golden(goldenDir)
        val namen = golden.caseNames().filter { it.startsWith("einstellungen_") }
        check(namen.size > 100) { "Zu wenige Einstellungs-Faelle: ${namen.size}" }
        for (name in namen) {
            val fall = golden.case(name)
            val roh = fall.inputs["roh"]!!.jsonObject
            vergleiche(name, fall.expected.jsonObject, Einstellungen.ausDict(roh).toMap())
        }
    }

    @Test
    fun `regieEinst gibt bei manuell mit eigener Art nichts zurueck`() {
        // Ausser "manuell" gibt die Regie die Einstellungen unveraendert zurueck.
        assertEquals(
            Einstellungen(modus = "kurz"),
            Einstellungen.regieEinst(Einstellungen(modus = "kurz")),
        )
        assertEquals(
            Einstellungen(modus = "ausgewogen"),
            Einstellungen.regieEinst(Einstellungen(modus = "manuell")),
        )
        assertEquals(
            null,
            Einstellungen.regieEinst(Einstellungen(modus = "manuell", art = "eq")),
        )
    }

    private fun vergleiche(name: String, erwartet: JsonObject, ist: Map<String, Any?>) {
        assertEquals(erwartet.keys, ist.keys, "$name: Felder")
        for ((feld, element) in erwartet) {
            val primitiv = element.jsonPrimitive
            val wert = ist.getValue(feld)
            when {
                primitiv.isString -> assertEquals(primitiv.content, wert, "$name/$feld")
                primitiv.booleanOrNull != null -> assertEquals(primitiv.booleanOrNull, wert, "$name/$feld")
                else -> assertEquals(primitiv.double, (wert as Number).toDouble(), 1e-12, "$name/$feld")
            }
        }
    }
}
