package de.klangbild.core

import kotlinx.serialization.json.JsonObject
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import java.io.File

/**
 * Fingerabdruck-Tests der Regie-Kandidaten (M7a-Vorstufe): Werte mit dem Prototyp erzeugt
 * (`regie.laengen`, `_a_kandidaten`, `_b_kandidaten`, `_b_index`, `_fenster`, `_mittelgewicht`).
 */
class RegieKandidatenTest {

    private val goldenDir = File(
        System.getProperty("klangbild.goldendir") ?: "testdata/golden",
    )

    @Test
    fun `laengen und Kandidaten entsprechen dem Prototyp`() {
        if (!goldenDir.isDirectory) return
        val golden = Golden(goldenDir)
        val pa = liesProfil(golden, golden.case("profil_synthetic_0").inputs["profile"]!! as JsonObject)
        val pb = liesProfil(golden, golden.case("profil_synthetic_1").inputs["profile"]!! as JsonObject)

        val taktS = Regie.taktS(pa)
        assertEquals(2.0, taktS, 1e-12)
        assertEquals(listOf(16), Regie.laengen("kurz", taktS))
        assertEquals(listOf(8), Regie.laengen("kurz", taktS, true))
        assertEquals(listOf(16, 24, 32), Regie.laengen("ausgewogen", taktS))
        assertEquals(listOf(8, 16), Regie.laengen("ausgewogen", taktS, true))
        assertEquals(listOf(24, 32), Regie.laengen("lang", taktS))
        assertEquals(listOf(16), Regie.laengen("lang", taktS, true))

        val schnell = Regie.aKandidaten(pa, 0, Einstellungen(spielanteil = "schnell"), false, true)
        assertEquals(listOf(56, 48), schnell.map { it.takt })
        assertEquals(listOf(3.0, -1.5), schnell.map { it.punkte })

        val lang = Regie.aKandidaten(pa, 0, Einstellungen(spielanteil = "lang"), false, true)
        assertEquals(listOf(40, 48, 56), lang.map { it.takt })
        assertEquals(listOf(3.75, 4.5, 5.25), lang.map { it.punkte })
        assertEquals(listOf("spielt lang", "spielt lang", "spielt lang"), lang.map { it.grund })

        val bSchnell = Regie.bKandidaten(pb, Einstellungen(spielanteil = "schnell"), true)
        assertEquals(listOf(0, 8, 16, 24), bSchnell.map { it.takt })
        val bLang = Regie.bKandidaten(pb, Einstellungen(spielanteil = "lang"), true)
        assertEquals(listOf(0, 8, 16, 24), bLang.map { it.takt })
        assertEquals(listOf(-0.0, -0.8, -1.6, -2.4000000000000004), bLang.map { it.punkte })

        val sofortTakt = Regie.aKandidaten(pa, 4, Einstellungen(weiterAb = "takt"), true, true)
        assertEquals(listOf(4), sofortTakt.map { it.takt })
        val sofortPhrase = Regie.aKandidaten(pa, 4, Einstellungen(weiterAb = "phrase"), true, true)
        assertEquals(listOf(8, 12, 16), sofortPhrase.map { it.takt })
        assertEquals(listOf(-0.0, -2.5, -5.0), sofortPhrase.map { it.punkte })

        assertEquals(listOf(3, 4, 5, 6, 7, 8, 9, 10), Regie.bIndex(3, 8).toList())
        assertEquals(listOf(3, 4, 3, 4, 5, 6, 7, 8), Regie.bIndex(3, 8, 2, 1).toList())
        assertEquals(listOf(2.0, 3.0, 0.0, 0.0, 0.0), Regie.fenster(doubleArrayOf(1.0, 2.0, 3.0), 1, 5).toList())
        assertEquals(listOf(0.4375, 0.9375, 0.9375, 0.4375), Regie.mittelgewicht(4).toList())
        assertEquals(listOf(5.0, 0.0), Regie.werte(doubleArrayOf(5.0), intArrayOf(0, 3)).toList())
    }
}
