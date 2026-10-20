package de.klangbild.core

import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assumptions.assumeTrue
import org.junit.jupiter.api.Test
import java.io.File

/**
 * Golden-Test des Profils: Bandtrennung (scipy-SOS + filtfilt) und Pegel je Takt gegen
 * `profil.berechnen`. Chroma folgt mit dem FFT-Schritt und bleibt hier aussen vor.
 */
class ProfilBauTest {

    private val dir: File = File(System.getProperty("klangbild.goldendir") ?: "testdata/golden")

    @Test
    fun `Pegel je Takt treffen den Golden-Fall`() {
        assumeTrue(dir.isDirectory, "Golden-Ordner fehlt: ${dir.absolutePath}")
        val g = Golden(dir)
        val fall = g.case("profil_berechnen")
        val ein = fall.inputs

        val audioVerweis = ein["audio"]!!.jsonObject
        val shape = audioVerweis["shape"]!!.jsonArray.map { it.jsonPrimitive.content.toInt() }
        val audio = g.f32(audioVerweis["file"]!!.jsonPrimitive.content, shape)

        val eintrag = ein["eintrag"]!!.jsonObject
        val downbeats = eintrag["downbeats"]!!.jsonArray.map { it.jsonPrimitive.content.toDouble() }
        val bpm = eintrag["bpm"]!!.jsonPrimitive.content.toDouble()

        val profil = ProfilBau.profil(audio, downbeats, bpm)
        val erwartet = fall.expected.jsonObject

        val baenderFlach = g.values(erwartet.getValue("baender"))
        assertEquals(profil.n * 3, baenderFlach.size, "Anzahl Takte")
        for (i in 0 until profil.n) {
            for (k in 0 until 3) {
                assertEquals(baenderFlach[i * 3 + k], profil.baender[i][k], 1e-6, "Band $k, Takt $i")
            }
        }

        val gesamt = g.values(erwartet.getValue("gesamt"))
        for (i in 0 until profil.n) {
            assertEquals(gesamt[i], profil.gesamt[i], 1e-6, "Gesamt, Takt $i")
        }
    }
}
