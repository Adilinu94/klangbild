package de.klangbild.core

import kotlinx.serialization.json.JsonObject
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import java.io.File

/** Fingerabdruck-Tests der Auto-DJ-Titelwahl (`live._autodj_wahl`). */
class AutoDjWahlTest {

    private val goldenDir = File(
        System.getProperty("klangbild.goldendir") ?: "testdata/golden",
    )

    @Test
    fun `waehlen entspricht dem Prototyp`() {
        if (!goldenDir.isDirectory) return
        val golden = Golden(goldenDir)
        val pa = liesProfil(golden, golden.case("profil_synthetic_0").inputs["profile"]!! as JsonObject)
        val pb = liesProfil(golden, golden.case("profil_synthetic_1").inputs["profile"]!! as JsonObject)

        val a = Track(1, "DnB/a.mp3", 120.0, "8A", -12.0)
        val b = Track(2, "DnB/b.mp3", 121.0, "9A", -11.0)
        val c = Track(3, "Chill/c.mp3", 122.0, "8A", -10.0)
        val d = Track(4, "DnB/d.mp3", 240.0, "10A", -13.0)
        val kandidaten = listOf(
            AutoDjWahl.Kandidat(b, pb),
            AutoDjWahl.Kandidat(c, pa),
            AutoDjWahl.Kandidat(d, pb),
        )
        val e = Einstellungen(modus = "ausgewogen")

        assertEquals(2, AutoDjWahl.waehlen(a, pa, 120.0, 0.0, kandidaten, emptySet(), e, emptyList()))
        assertEquals(2, AutoDjWahl.waehlen(a, pa, 120.0, 0.0, kandidaten, emptySet(), e, listOf(2.0, 3.0, 1.5)))
        assertEquals(2, AutoDjWahl.waehlen(a, pa, 120.0, 0.0, kandidaten, emptySet(), e, listOf(-2.0, -3.0, -1.5)))
        assertEquals(2, AutoDjWahl.waehlen(a, pa, 120.0, 0.0, kandidaten, emptySet(), e, listOf(0.5, -0.5)))
        assertEquals(3, AutoDjWahl.waehlen(a, pa, 120.0, 0.0, kandidaten, setOf(2), e, emptyList()))
    }

    @Test
    fun `gleicherTitel erkennt dieselbe Aufnahme`() {
        assertTrue(AutoDjWahl.gleicherTitel("Song - Artist", "Song-Artist, Feat X"))
        assertFalse(AutoDjWahl.gleicherTitel("a", "a"))   // zu kurz, gilt nicht als Dublette
        assertFalse(AutoDjWahl.gleicherTitel("abcdefgh", "abcdefgi"))
        assertTrue(AutoDjWahl.gleicherTitel("abcdefgh", "abcdefgh remix"))
    }

    @Test
    fun `planTrack nimmt Genre aus dem Ordner`() {
        val t = AutoDjWahl.planTrack(Track(7, "DnB/x.mp3", 120.0, "8A"), energieLevel = 0.4)
        assertEquals("DnB", t.genre)
        assertEquals(0.4, t.energie!!, 1e-12)
        val upload = AutoDjWahl.planTrack(Track(8, "Upload/y.mp3", 120.0, "8A"))
        assertEquals(null, upload.genre)
    }
}
