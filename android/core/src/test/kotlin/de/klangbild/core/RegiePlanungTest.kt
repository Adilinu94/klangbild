package de.klangbild.core

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.double
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import java.io.File

/** Golden-Tests der Regie: `regie.planen` gegen die synthetischen Faelle. */
class RegiePlanungTest {

    private val goldenDir = File(
        System.getProperty("klangbild.goldendir") ?: "testdata/golden",
    )

    @Test
    fun `planen entspricht dem Prototyp`() {
        if (!goldenDir.isDirectory) return
        val golden = Golden(goldenDir)
        for (stil in listOf("kurz", "ausgewogen", "lang")) {
            for (anteil in listOf("schnell", "lang")) {
                val name = "regie_synthetic_${stil}_${anteil}"
                val fall = golden.case(name)
                val a = referenz(fall.inputs.getValue("a") as JsonObject)
                val pa = liesProfil(golden, fall.inputs.getValue("pa") as JsonObject)
                val b = referenz(fall.inputs.getValue("b") as JsonObject)
                val pb = liesProfil(golden, fall.inputs.getValue("pb") as JsonObject)
                val e = Einstellungen.ausDict((fall.inputs.getValue("e") as JsonObject))
                val abS = fall.inputs.getValue("ab_s").jsonPrimitive.double
                val sync = fall.inputs.getValue("sync").jsonPrimitive.booleanOrNull ?: false
                val harmonisch = fall.inputs.getValue("harmonisch").jsonPrimitive.booleanOrNull ?: false
                val stemsDa = fall.inputs.getValue("stems_da").jsonPrimitive.booleanOrNull ?: false

                val ist = RegiePlanung.planen(a, pa, b, pb, e, abS, sync, harmonisch, stemsDa = stemsDa)
                val erwartet = fall.expected as JsonArray
                assertEquals(erwartet.size, ist.size, "$name: Zahl der Plaene")
                for (k in erwartet.indices) {
                    val soll = erwartet[k].jsonObject
                    val plan = ist[k]
                    assertEquals(soll.getValue("rezept").jsonPrimitive.content, plan.rezept, "$name/$k/rezept")
                    assertEquals(soll.getValue("grund").jsonPrimitive.content, plan.grund, "$name/$k/grund")
                    assertEquals(soll.getValue("aus_s").jsonPrimitive.double, plan.ausS, 1e-6, "$name/$k/aus_s")
                    assertEquals(soll.getValue("ein_s").jsonPrimitive.double, plan.einS, 1e-6, "$name/$k/ein_s")
                    assertEquals(soll.getValue("takte").jsonPrimitive.double, plan.takte.toDouble(), 1e-9, "$name/$k/takte")
                    assertEquals(soll.getValue("punkte").jsonPrimitive.double, plan.punkte, 1e-6, "$name/$k/punkte")
                    vergleicheEinstellungen("$name/$k/einst", soll.getValue("einst") as JsonObject, plan.einst.toMap())
                }
            }
        }
    }

    private fun referenz(j: JsonObject): RegiePlanung.Referenz = RegiePlanung.Referenz(
        id = j.getValue("id").jsonPrimitive.content.toInt(),
        pfad = j.getValue("pfad").jsonPrimitive.content,
        camelot = j["camelot"]?.takeUnless { it is JsonNull }?.jsonPrimitive?.content,
    )

    private fun vergleicheEinstellungen(name: String, erwartet: JsonObject, ist: Map<String, Any?>) {
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
