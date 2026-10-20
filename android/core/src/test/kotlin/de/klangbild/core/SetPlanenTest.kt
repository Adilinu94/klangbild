package de.klangbild.core

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test

/** Fingerabdruck-Tests von `plan.set_planen` und `plan.bogen_ziel` (Werte aus dem Prototyp). */
class SetPlanenTest {

    private val tracks = listOf(
        Track(1, "t1", 120.0, "8A", -12.0, energie = 0.3, genre = "A"),
        Track(2, "t2", 122.0, "9A", -11.0, energie = 0.5, genre = "A"),
        Track(3, "t3", 124.0, "10A", -10.0, energie = 0.7, genre = "B"),
        Track(4, "t4", 126.0, "11A", -9.0, energie = 0.8, genre = "B"),
        Track(5, "t5", 128.0, "12A", -13.0, energie = 0.4, genre = "A"),
        Track(6, "t6", 121.0, "1A", -14.0, energie = 0.2, genre = "C"),
    )
    private val energien = listOf(0.3, 0.5, 0.7, 0.8, 0.4, 0.2)

    @Test
    fun `bogenZiel entspricht dem Prototyp`() {
        assertEquals(List(6) { null }, Planer.bogenZiel(energien, 6, "gleichmaessig"))
        val aufbauen = Planer.bogenZiel(energien, 6, "aufbauen")
        val sollAufbauen = listOf(0.25, 0.35, 0.45, 0.55, 0.65, 0.75)
        for (i in 0 until 6) assertEquals(sollAufbauen[i], aufbauen[i]!!, 1e-9, "aufbauen[$i]")
        val welle = Planer.bogenZiel(energien, 6, "welle")
        val sollWelle = listOf(0.45, 0.626776695, 0.7, 0.626776695, 0.45, 0.273223305)
        for (i in 0 until 6) assertEquals(sollWelle[i], welle[i]!!, 1e-9, "welle[$i]")
    }

    @Test
    fun `setPlanen entspricht dem Prototyp`() {
        val keine = { _: Int, _: Int -> null }
        assertEquals(listOf(1, 2, 3, 4, 5, 6), Planer.setPlanen(tracks, 1, 5.0, "locker", keine))
        assertEquals(
            listOf(1, 6, 5, 2, 3, 4),
            Planer.setPlanen(tracks, 1, 5.0, "locker", keine, bogen = "aufbauen"),
        )
        assertEquals(
            listOf(1, 2, 3, 4, 5, 6),
            Planer.setPlanen(tracks, 1, 5.0, "locker", keine, bogen = "welle"),
        )
        assertEquals(listOf(3, 4, 5, 2, 1, 6), Planer.setPlanen(tracks, 3, 5.0, "aus", keine))
        assertEquals(
            listOf(1, 6, 4, 3, 2, 5),
            Planer.setPlanen(tracks, 1, 5.0, "locker", { a, _ -> if (a % 2 == 0) 5.0 else 2.0 }),
        )
    }
}
