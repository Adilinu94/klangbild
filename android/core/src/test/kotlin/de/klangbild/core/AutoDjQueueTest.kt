package de.klangbild.core

import kotlinx.serialization.json.JsonObject
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import java.io.File

/** Tests der Warteschlange, des Lernens und der Reihenfolge (live.sortieren). */
class AutoDjQueueTest {

    private val goldenDir = File(
        System.getProperty("klangbild.goldendir") ?: "testdata/golden",
    )

    @Test
    fun `Warteschlange wie im Prototyp`() {
        val q = AutoDjQueue(setOf(1, 2, 3))
        assertTrue(q.einreihen(1))
        assertTrue(q.einreihen(2))
        assertFalse(q.einreihen(9))
        assertTrue(q.verschieben(0, 1))
        assertEquals(listOf(2, 1), q.warteschlange)
        assertFalse(q.verschieben(1, 1))
        assertEquals(2, q.naechster())
        assertEquals(listOf(1), q.warteschlange)
        assertTrue(q.entfernen(0))
        assertTrue(q.warteschlange.isEmpty())
        assertNull(q.naechster())
        q.einreihen(1)
        q.leeren()
        assertTrue(q.warteschlange.isEmpty())
    }

    @Test
    fun `lernen klemmt auf -5 bis 3`() {
        val q = AutoDjQueue()
        repeat(20) { q.lernen("profi_eq", true) }
        assertEquals(3.0, q.vorlieben.getValue("profi_eq"), 1e-12)
        repeat(20) { q.lernen("echo_out", false) }
        assertEquals(-5.0, q.vorlieben.getValue("echo_out"), 1e-12)
    }

    @Test
    fun `bewerten rechnet die Datensatznote`() {
        val q = AutoDjQueue()
        assertEquals(5.0, q.bewerten("x", 1), 1e-12)
        assertEquals(3.4, q.bewerten("x", 3), 1e-12)
        assertEquals(1.0, q.bewerten("x", 6), 1e-12)
        assertEquals(-0.4, q.vorlieben.getValue("x"), 1e-9)
    }

    @Test
    fun `sortieren entspricht dem Prototyp`() {
        if (!goldenDir.isDirectory) return
        val golden = Golden(goldenDir)
        val pa = liesProfil(golden, golden.case("profil_synthetic_0").inputs["profile"]!! as JsonObject)
        val pb = liesProfil(golden, golden.case("profil_synthetic_1").inputs["profile"]!! as JsonObject)
        val tracks = listOf(
            Track(1, "DnB/a.mp3", 120.0, "8A", -12.0),
            Track(2, "DnB/b.mp3", 121.0, "9A", -11.0),
            Track(3, "Chill/c.mp3", 122.0, "8A", -10.0),
            Track(4, "DnB/d.mp3", 123.0, "10A", -13.0),
        )
        val profile: (Int) -> Profil? = { id -> if (id == 1 || id == 3) pa else pb }
        val e = Einstellungen(modus = "ausgewogen")
        val q = AutoDjQueue(setOf(1, 2, 3, 4))
        assertEquals(listOf(1, 2, 4, 3), q.sortieren(tracks, e, null, profile))
        assertEquals(listOf(1, 3, 4), q.sortieren(tracks, e, 2, profile))
    }
}
