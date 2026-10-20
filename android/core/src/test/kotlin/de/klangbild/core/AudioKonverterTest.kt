package de.klangbild.core

import org.junit.jupiter.api.Assertions.assertArrayEquals
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import java.nio.ByteBuffer
import java.nio.ByteOrder

/** Tests der Decoder-Bausteine (M2): Byte-Wandlung, Stereo, lineares Resampling. */
class AudioKonverterTest {

    @Test
    fun `PCM 16 bit wird zu float`() {
        val bytes = ByteBuffer.allocate(6).order(ByteOrder.LITTLE_ENDIAN)
            .putShort(0).putShort(16384).putShort(-16384).array()
        assertArrayEquals(floatArrayOf(0f, 0.5f, -0.5f), AudioKonverter.pcm16ZuFloat(bytes), 1e-6f)
    }

    @Test
    fun `PCM float wird gelesen`() {
        val bytes = ByteBuffer.allocate(8).order(ByteOrder.LITTLE_ENDIAN)
            .putFloat(0.25f).putFloat(-0.75f).array()
        assertArrayEquals(floatArrayOf(0.25f, -0.75f), AudioKonverter.pcmFloatZuFloat(bytes), 1e-7f)
    }

    @Test
    fun `Mono wird zu Stereo, mehr Kanaele auf zwei gekuerzt`() {
        assertArrayEquals(
            floatArrayOf(0.1f, 0.1f, 0.2f, 0.2f),
            AudioKonverter.aufStereo(floatArrayOf(0.1f, 0.2f), 1),
            1e-7f,
        )
        assertArrayEquals(
            floatArrayOf(0.1f, 0.2f, 0.3f, 0.4f),
            AudioKonverter.aufStereo(floatArrayOf(0.1f, 0.2f, 0.5f, 0.3f, 0.4f, 0.6f), 3),
            1e-7f,
        )
        assertArrayEquals(
            floatArrayOf(0.1f, 0.2f),
            AudioKonverter.aufStereo(floatArrayOf(0.1f, 0.2f), 2),
            1e-7f,
        )
    }

    @Test
    fun `Resampling halbiert und verdoppelt die Laenge`() {
        val stereo = floatArrayOf(0f, 0f, 1f, 1f, 2f, 2f, 3f, 3f)
        assertArrayEquals(stereo, AudioKonverter.resampleLinear(stereo, 2, 44100, 44100), 1e-7f)

        // 48 kHz -> 24 kHz: jeder zweite Frame.
        val halb = AudioKonverter.resampleLinear(stereo, 2, 48000, 24000)
        assertEquals(4, halb.size)
        assertArrayEquals(floatArrayOf(0f, 0f, 2f, 2f), halb, 1e-6f)

        // 24 kHz -> 48 kHz: doppelt so viele Frames, linear interpoliert, Ende konstant.
        val doppelt = AudioKonverter.resampleLinear(stereo, 2, 24000, 48000)
        assertEquals(16, doppelt.size)
        assertArrayEquals(floatArrayOf(0f, 0f, 0.5f, 0.5f, 1f, 1f, 1.5f, 1.5f), doppelt.copyOfRange(0, 8), 1e-6f)
        assertArrayEquals(floatArrayOf(3f, 3f, 3f, 3f), doppelt.copyOfRange(12, 16), 1e-6f)
    }
}
