package de.klangbild.core

import kotlinx.serialization.json.JsonObject
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNotNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import java.io.File

/** Tests des Auto-DJ-Controllers: Versuche, Selbstkontrolle, Sicherheits-Blend. */
class AutoDjControllerTest {

    private val goldenDir = File(
        System.getProperty("klangbild.goldendir") ?: "testdata/golden",
    )

    private fun aufbau(): Pair<Pair<Track, Profil>, Pair<Track, Profil>>? {
        if (!goldenDir.isDirectory) return null
        val golden = Golden(goldenDir)
        val pa = liesProfil(golden, golden.case("profil_synthetic_0").inputs["profile"]!! as JsonObject)
        val pb = liesProfil(golden, golden.case("profil_synthetic_1").inputs["profile"]!! as JsonObject)
        val a = Track(1, "DnB/a.mp3", 120.0, "8A", -12.0)
        val b = Track(2, "DnB/b.mp3", 121.0, "9A", -11.0)
        return (a to pa) to (b to pb)
    }

    private fun baker(
        sync: (Int) -> Boolean,
        log: MutableList<AutoDjController.BackAuftrag>,
    ): AutoDjController.Baker = object : AutoDjController.Baker {
        override fun backen(auftrag: AutoDjController.BackAuftrag): AutoDjController.BackErgebnis {
            val nummer = log.size
            log.add(auftrag)
            return AutoDjController.BackErgebnis(
                null,
                AutoDjController.BackInfo(sync(nummer), 4.0, auftrag.plan.takte),
            )
        }
    }

    @Test
    fun `erster Plan gewinnt`() {
        val aufbau = aufbau() ?: return
        val (a, pa) = aufbau.first
        val (b, pb) = aufbau.second
        val log = mutableListOf<AutoDjController.BackAuftrag>()
        val ergebnis = AutoDjController.vorbereiten(
            a, pa, b, pb, Einstellungen(art = "eigen"), 0.0, 0.0, false, 120.0, baker({ true }, log),
        )
        assertNotNull(ergebnis)
        assertEquals(1, log.size)
        assertTrue(log[0].plan.einst.art in AutoDjController.SYNC_ARTEN)
    }

    @Test
    fun `durchgefallener Plan fuehrt zum naechsten Rezept`() {
        val aufbau = aufbau() ?: return
        val (a, pa) = aufbau.first
        val (b, pb) = aufbau.second
        val log = mutableListOf<AutoDjController.BackAuftrag>()
        val ergebnis = AutoDjController.vorbereiten(
            a, pa, b, pb, Einstellungen(art = "eigen"), 0.0, 0.0, false, 120.0, baker({ it > 0 }, log),
        )
        assertNotNull(ergebnis)
        assertEquals(2, log.size)
        assertTrue(log[0].plan.rezept != log[1].plan.rezept, "gleiches Rezept wurde wiederholt")
    }

    @Test
    fun `alles faellt durch, dann Sicherheits-Blend`() {
        val aufbau = aufbau() ?: return
        val (a, pa) = aufbau.first
        val (b, pb) = aufbau.second
        val log = mutableListOf<AutoDjController.BackAuftrag>()
        val ergebnis = AutoDjController.vorbereiten(
            a, pa, b, pb, Einstellungen(art = "eigen"), 0.0, 0.0, false, 120.0, baker({ false }, log),
        )
        assertNotNull(ergebnis)
        val sicher = log.last().plan
        assertEquals("profi_eq", sicher.rezept)
        assertTrue(sicher.takte <= 16)
        assertEquals("eigen", sicher.einst.art)
        assertEquals("profi", sicher.einst.eq)
        assertTrue(sicher.einst.loop == "keiner" || sicher.einst.loop == "auto")
    }
}
