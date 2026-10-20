package de.klangbild.core

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import java.io.File

/** Tests der Paarnoten: Tempo-Rahmen, Cache-Rundlauf und Rundung wie Python. */
class PaarnotenTest {

    @Test
    fun `imTempo kennt Doppel- und Halbtempo`() {
        assertTrue(Paarnoten.imTempo(120.0, 123.0, 5.0))
        assertFalse(Paarnoten.imTempo(120.0, 130.0, 5.0))
        assertTrue(Paarnoten.imTempo(120.0, 60.0, 5.0))
        assertTrue(Paarnoten.imTempo(120.0, 240.0, 5.0))
        assertTrue(Paarnoten.imTempo(120.0, 120.04, 0.0))    // max(max_bpm, 0,05)
        assertFalse(Paarnoten.imTempo(120.0, 120.2, 0.0))
    }

    @Test
    fun `Cache laedt und speichert, fremde Version verfaellt`() {
        val datei = File.createTempFile("paarnoten", ".json")
        try {
            val noten = Paarnoten("0.3.0", datei)
            noten.setzen(1, 2, 3.47, "profi_eq", 4.12)
            noten.setzen(2, 3, 2.5, "echo_out", 1.9)
            noten.speichern()

            val wieder = Paarnoten("0.3.0", datei)
            assertEquals(3.47, wieder.note(1, 2)!!, 1e-12)
            assertEquals("profi_eq", wieder.rezept(1, 2))
            assertEquals(2.5, wieder.note(2, 3)!!, 1e-12)
            assertNull(wieder.note(9, 9))

            assertNull(Paarnoten("0.4.0", datei).note(1, 2))
        } finally {
            datei.delete()
        }
    }

    @Test
    fun `runde entspricht Python`() {
        assertEquals(2.67, Paarnoten.runde(2.675, 2), 1e-12)
        assertEquals(0.12, Paarnoten.runde(0.125, 2), 1e-12)   // halbe Werte zur geraden Zahl
        assertEquals(0.14, Paarnoten.runde(0.135, 2), 1e-12)
        assertEquals(3.46, Paarnoten.runde(3.465, 2), 1e-12)
    }
}
