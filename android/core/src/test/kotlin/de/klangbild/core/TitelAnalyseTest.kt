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
    fun `Downbeats ueberstehen den Rueckweg`() {
        val a = TitelAnalyse("Am", "8A", -5.2, 124, listOf(0.5f, 0.98f, 1.47f, 1.96f), listOf(0.5f, 1.96f))
        val gelesen = TitelAnalyse.aus(a.json())
        assertEquals(a, gelesen)
        assertEquals(listOf(0.5f, 1.96f), gelesen?.downbeats)
    }

    @Test
    fun `Profil uebersteht den Rueckweg`() {
        val a = TitelAnalyse(
            tonart = "Am",
            camelot = "8A",
            lufs = -5.2,
            bpm = 124,
            beats = listOf(0.5f, 0.98f),
            downbeats = listOf(0.5f),
            raster = listOf(0.5f),
            takte = listOf(0.5f, 2.44f),
            gesamt = listOf(-10.5f, -8.25f),
            baender = listOf(listOf(-20f, -18f), listOf(-25f, -24f), listOf(-30f, -29f)),
            chroma = listOf(listOf(0.1f, 0.2f, 0.3f), listOf(0.4f, 0.5f, 0.6f)),
        )
        val gelesen = TitelAnalyse.aus(a.json())
        assertEquals(a, gelesen)
        assertEquals(3, gelesen?.baender?.size)
        assertEquals(2, gelesen?.chroma?.size)
    }

    @Test
    fun `zurueck in ein Profil`() {
        val a = TitelAnalyse(
            tonart = "Am",
            camelot = "8A",
            lufs = -5.2,
            bpm = 124,
            takte = listOf(0.5f, 2.44f, 4.38f),
            gesamt = listOf(-10.5f, -8.25f, -9.0f),
            baender = listOf(listOf(-20f, -18f, -19f), listOf(-25f, -24f, -24f), listOf(-30f, -29f, -29f)),
            chroma = listOf(listOf(0.1f), listOf(0.2f), listOf(0.3f)),
        )
        val p = a.zuProfil()
        assertEquals(3, p?.n)
        assertEquals(3, p?.baender?.size)
        assertEquals(3, p?.chroma?.size)
        assertEquals(6.32, p!!.dauer, 1e-6)
        assertEquals(-8.25, p.gesamt[1], 1e-6)
    }

    @Test
    fun `ohne Takte kein Profil`() {
        assertNull(TitelAnalyse("Am", "8A", -5.2).zuProfil())
    }

    @Test
    fun `fremde Version und kaputter Text ergeben null`() {
        assertNull(TitelAnalyse.aus("""{"version":2,"tonart":"Am","camelot":"8A","lufs":-5.2}"""))
        assertNull(TitelAnalyse.aus("""{"version":1,"tonart":"Am"}"""))
        assertNull(TitelAnalyse.aus("kein json"))
    }
}
