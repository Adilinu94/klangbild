package de.klangbild.core

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Test

class TitelAnalyseTest {

    @Test
    fun `Hin- und Rueckweg erhaelt die Werte`() {
        val a = TitelAnalyse("Am", "8A", -5.2)
        val gelesen = TitelAnalyse.aus(a.json())
        assertEquals(a, gelesen)
    }

    @Test
    fun `fehlende Lautheit bleibt null`() {
        val a = TitelAnalyse("F#m", "11A", null)
        assertEquals(a, TitelAnalyse.aus(a.json()))
    }

    @Test
    fun `Tempo und Beats ueberstehen den Rueckweg`() {
        val a = TitelAnalyse("Am", "8A", -5.2, 124, listOf(0.5f, 0.984f, 1.468f))
        val gelesen = TitelAnalyse.aus(a.json())
        assertEquals(a, gelesen)
        assertEquals(3, gelesen?.beats?.size)
    }

    @Test
    fun `fremde Version und kaputter Text ergeben null`() {
        assertNull(TitelAnalyse.aus("""{"version":2,"tonart":"Am","camelot":"8A","lufs":-5.2}"""))
        assertNull(TitelAnalyse.aus("""{"version":1,"tonart":"Am"}"""))
        assertNull(TitelAnalyse.aus("kein json"))
    }
}
