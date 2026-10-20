package de.klangbild.core

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.double
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonPrimitive
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import java.io.File

/** Golden-Tests des Planers (BAUPLAN-ANDROID M7): Rangliste und ganze Reihenfolge. */
class PlanTest {

    private val goldenDir = File(
        System.getProperty("klangbild.goldendir") ?: "testdata/golden",
    )

    @Test
    fun `rangliste entspricht dem Prototyp`() {
        if (!goldenDir.isDirectory) return
        val golden = Golden(goldenDir)
        for (name in listOf("rangliste_streng", "rangliste_locker", "rangliste_aus")) {
            val fall = golden.case(name)
            val aktuell = track(fall.inputs.getValue("aktuell") as JsonObject)
            val kandidaten = (fall.inputs.getValue("kandidaten") as JsonArray).map { track(it as JsonObject) }
            val maxBpm = fall.inputs.getValue("max_bpm").jsonPrimitive.double
            val harmonie = fall.inputs.getValue("harmonie").jsonPrimitive.content
            val n = fall.inputs.getValue("n").jsonPrimitive.int
            val ist = Planer.rangliste(aktuell, kandidaten, maxBpm, harmonie, n).map { it.id }
            assertEquals(ids(fall.expected), ist, name)
        }
    }

    @Test
    fun `sortiere_332 entspricht dem Prototyp`() {
        if (!goldenDir.isDirectory) return
        val golden = Golden(goldenDir)
        val fall = golden.case("sortiere_332")
        val tracks = (fall.inputs.getValue("tracks") as JsonArray).map { track(it as JsonObject) }
        val maxBpm = fall.inputs.getValue("max_bpm").jsonPrimitive.double
        val harmonie = fall.inputs.getValue("harmonie").jsonPrimitive.content
        assertEquals(ids(fall.expected), Planer.sortiereAlle(tracks, maxBpm, harmonie))
    }

    private fun ids(element: kotlinx.serialization.json.JsonElement): List<Int> =
        Golden.toDoubles(element).map { it.toInt() }

    private fun track(j: JsonObject): Track = Track(
        id = j.getValue("id").jsonPrimitive.int,
        pfad = j.getValue("pfad").jsonPrimitive.content,
        bpm = zahl(j["bpm"]),
        camelot = text(j["camelot"]),
        energieDb = zahl(j["energie_db"]),
        energie = zahl(j["energie"]),
        genre = text(j["genre"]),
        vektor = (j["vektor"] as? JsonArray)?.map { it.jsonPrimitive.double },
    )

    private fun zahl(element: kotlinx.serialization.json.JsonElement?): Double? =
        if (element == null || element is JsonNull) null else element.jsonPrimitive.double

    private fun text(element: kotlinx.serialization.json.JsonElement?): String? =
        if (element == null || element is JsonNull) null else element.jsonPrimitive.content
}
