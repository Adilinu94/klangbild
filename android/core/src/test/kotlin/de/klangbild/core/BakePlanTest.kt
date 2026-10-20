package de.klangbild.core

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.double
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

/** Tests des Übergangsplan-JSON (BAUPLAN §4.5). */
class BakePlanTest {

    @Test
    fun `Plan-JSON hat die Felder des Vertrags`() {
        val a = BakeEintrag(
            1, "DnB/a.mp3", 120.0, "8A",
            listOf(0.0, 2.0), listOf(2.0), listOf(listOf(0.0, 0.01)), -2.1,
        )
        val b = BakeEintrag(2, "DnB/b.mp3", 121.0, "9A")
        val e = Einstellungen(art = "eigen", takte = 16, keylock = false)
        val text = BakePlan.json(a, b, e, 1.5, 2.0, 0.0, false)
        val obj = Json.parseToJsonElement(text).jsonObject

        val ja = obj.getValue("a").jsonObject
        assertEquals(1, ja.getValue("id").jsonPrimitive.int)
        assertEquals("DnB/a.mp3", ja.getValue("pfad").jsonPrimitive.content)
        assertEquals(120.0, ja.getValue("bpm").jsonPrimitive.double, 1e-12)
        assertEquals("8A", ja.getValue("camelot").jsonPrimitive.content)
        assertEquals(2, ja.getValue("downbeats").jsonArray.size)
        assertEquals(0.01, ja.getValue("fein").jsonArray[0].jsonArray[1].jsonPrimitive.double, 1e-12)
        assertEquals(-2.1, ja.getValue("gainDb").jsonPrimitive.double, 1e-12)

        val je = obj.getValue("einst").jsonObject
        assertEquals("eigen", je.getValue("art").jsonPrimitive.content)
        assertEquals(16, je.getValue("takte").jsonPrimitive.int)
        assertFalse(je.getValue("keylock").jsonPrimitive.boolean)
        assertEquals("ausgewogen", je.getValue("modus").jsonPrimitive.content)

        assertEquals(1.5, obj.getValue("abS").jsonPrimitive.double, 1e-12)
        assertEquals(2.0, obj.getValue("ausS").jsonPrimitive.double, 1e-12)
        assertEquals(0.0, obj.getValue("einS").jsonPrimitive.double, 1e-12)
        assertFalse(obj.getValue("weiter").jsonPrimitive.boolean)
    }

    @Test
    fun `info liest die Kerndaten und Fehler`() {
        val info = BakePlan.info(
            """{"art":"eigen","takte":16,"sync":true,"blende_s":30.5,""" +
                """"loop_wahl":{"start_takt":4,"schlaege":16,"guete":0.88}}""",
        )
        assertTrue(info.sync)
        assertEquals(30.5, info.blendeS, 1e-12)
        assertEquals(16, info.takte)
        assertEquals(0.88, info.loopGuete!!, 1e-12)
        assertEquals("eigen", info.art)
        assertNull(info.fehler)

        val fehler = BakePlan.info("""{"fehler":"kaputt"}""")
        assertEquals("kaputt", fehler.fehler)
        assertFalse(fehler.sync)
        assertNull(fehler.loopGuete)
    }
}
