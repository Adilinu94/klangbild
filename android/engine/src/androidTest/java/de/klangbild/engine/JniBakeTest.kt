package de.klangbild.engine

import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Gerätetest der JNI-Fassade (M8b): backt einen Übergang mit synthetischem Audio und prüft,
 * dass Audio und Info zurückkommen. Die Genauigkeit prüft der Host-Test gegen die Golden-Daten;
 * hier zählt, dass die .so auf dem Gerät lädt und der Vertrag hält.
 */
@RunWith(AndroidJUnit4::class)
class JniBakeTest {

    @Test
    fun backtUeberJni() {
        val rate = 44100
        val a = FloatArray(8 * rate * 2) { i -> if (i % 2 == 0) 0.2f else 0.1f }
        val b = FloatArray(8 * rate * 2) { i -> if (i % 2 == 0) 0.15f else 0.05f }
        val ir = FloatArray(rate)

        val plan = """
            {"a":{"id":1,"pfad":"synthetic-a","bpm":120,"camelot":"8B",
                  "downbeats":[0,2,4,6],"abschnitte":[2,6],"fein":[]},
             "b":{"id":2,"pfad":"synthetic-b","bpm":120,"camelot":"8B",
                  "downbeats":[0,2,4,6],"abschnitte":[2,6],"fein":[]},
             "einst":{"art":"auto","lautstaerke":"nahtlos","eq":"keiner","filter":"keiner",
                      "effekt":"keiner","effekt_ein":"keiner","loop":"keiner","trick":"keiner",
                      "bass_takt":-1,"gesang_takt":-1,"loop_start":-1,"loop_ein":0,
                      "loop_ein_mal":0,"keylock":false,"ausstieg":"phrase","vor_ende_takte":16,
                      "einstieg":"intro","weiter_ab":"phrase","takte":1,"weiter_takte":8,
                      "max_bpm":0.0,"tempo_modus":"keiner","stems":false,"modus":"ausgewogen",
                      "lautheit":true},
             "abS":0.0,"ausS":2.0,"einS":0.0,"weiter":false}
        """.trimIndent()

        val handle = NativeEngine.bake(plan, a, b, ir, null)
        assertTrue("Handle 0 (Plan oder Backen fehlgeschlagen)", handle > 0)
        try {
            val info = NativeEngine.bakeInfo(handle)
            assertTrue(info, info.contains("\"sync\":true"))
            assertTrue(info, info.contains("\"fehler\"") == false)
            val audio = NativeEngine.bakeAudio(handle)
            assertNotNull("Kein Audio", audio)
            assertTrue("Audio zu kurz: ${audio!!.size}", audio.size > 2 * rate)
        } finally {
            NativeEngine.releaseBake(handle)
        }
    }
}
