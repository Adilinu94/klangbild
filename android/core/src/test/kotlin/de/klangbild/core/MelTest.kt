package de.klangbild.core

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * Golden-Test der Mel-Vorverarbeitung gegen die Python-Referenz, die dieselbe Rechnung
 * wie `beat_this_cpp/Source/MelSpectrogram.cpp` nachbildet (mono 22,05 kHz, 440 Hz plus
 * 3000 Hz, 3 s).
 */
class MelTest {

    private fun lies(pfad: String): FloatArray {
        val strom = MelTest::class.java.getResourceAsStream("/mel/$pfad")
            ?: error("Testdatei fehlt: /mel/$pfad")
        val bytes = strom.use { it.readBytes() }
        val puffer = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
        return FloatArray(bytes.size / 4) { puffer.getFloat() }
    }

    @Test
    fun `Mel-Spektrogramm stimmt mit der Referenz`() {
        val signal = lies("mel_input.f32")
        val erwartet = lies("mel_expected.f32")
        val frames = erwartet.size / Mel.N_MELS
        assertEquals(151, frames, "Rahmenzahl")
        assertEquals(66150, signal.size, "Abtastwerte")

        val gemessen = Mel.spektrogramm(signal)
        assertEquals(frames, gemessen.size, "Rahmenzahl")

        var groesster = 0.0
        for (f in 0 until frames) {
            for (m in 0 until Mel.N_MELS) {
                val abweichung = kotlin.math.abs(gemessen[f][m] - erwartet[f * Mel.N_MELS + m]).toDouble()
                if (abweichung > groesster) groesster = abweichung
            }
        }
        assertEquals(0.0, groesster, 1e-4, "groesste Abweichung $groesster")
    }
}
