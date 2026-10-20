package de.klangbild.engine

import de.klangbild.core.AutoDjController
import de.klangbild.core.BakeEintrag
import de.klangbild.core.BakePlan

/**
 * Bäcker über JNI (BAUPLAN §4.5, M8b): reicht den Übergangsplan und die PCM-Puffer an
 * `libklangbild.so` und liefert Audio und Info zurück. Die PCM-Puffer (Stereo interleaved)
 * und die Einträge kommen aus der Bibliothek des Aufrufers.
 *
 * Blockiert (Dehnen, Filtern, Limiter): im Planer-Thread aufrufen, nie im UI- oder Audio-Thread.
 */
class NativeBaker(
    private val eintrag: (Int) -> BakeEintrag?,
    private val pcm: (Int) -> FloatArray?,
    private val hallIr: FloatArray,
    private val riserNoise: FloatArray? = null,
) : AutoDjController.Baker {

    override fun backen(auftrag: AutoDjController.BackAuftrag): AutoDjController.BackErgebnis {
        val a = eintrag(auftrag.a.id)
        val b = eintrag(auftrag.b.id)
        val aPcm = pcm(auftrag.a.id)
        val bPcm = pcm(auftrag.b.id)
        if (a == null || b == null || aPcm == null || bPcm == null) return fehler(auftrag)

        val plan = BakePlan.json(a, b, auftrag.plan.einst, auftrag.abS, auftrag.ausS, auftrag.einS, auftrag.weiter)
        val handle = NativeEngine.bake(plan, aPcm, bPcm, hallIr, riserNoise)
        if (handle == 0L) return fehler(auftrag)
        return try {
            val info = BakePlan.info(NativeEngine.bakeInfo(handle))
            val audio = NativeEngine.bakeAudio(handle)
            AutoDjController.BackErgebnis(
                audio,
                AutoDjController.BackInfo(info.sync, info.blendeS, info.takte, info.loopGuete),
            )
        } finally {
            NativeEngine.releaseBake(handle)
        }
    }

    private fun fehler(auftrag: AutoDjController.BackAuftrag): AutoDjController.BackErgebnis =
        AutoDjController.BackErgebnis(
            null,
            AutoDjController.BackInfo(sync = false, blendeS = 0.0, takte = auftrag.plan.takte),
        )
}
