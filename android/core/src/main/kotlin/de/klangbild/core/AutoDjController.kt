package de.klangbild.core

import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

/**
 * Auto-DJ-Controller (Port von `live.Wiedergabe._auto_backen`): plant den naechsten Uebergang,
 * laesst ihn backen und prueft das Ergebnis selbst nach. Faellt ein Plan durch, kommt der
 * naechstbeste, zuletzt ein Sicherheits-Blend.
 *
 * Der eigentliche Baker (PCM, Dehnen, Mischen) wird injiziert: auf dem Geraet ist das der
 * native Kern ueber JNI, im Test ein Doppel.
 */
object AutoDjController {

    /** Uebergaenge, die eine Tempo-Angleichung brauchen (`uebergang.SYNC_ARTEN`). */
    val SYNC_ARTEN = setOf(
        "eq", "crossfade", "filter", "eigen", "drums_zuerst", "acapella", "gesangsschutz",
        "gesang_zuerst", "double_drop", "melodie_zuerst",
    )

    interface Baker {
        fun backen(auftrag: BackAuftrag): BackErgebnis
    }

    data class BackAuftrag(
        val a: Track,
        val pa: Profil,
        val b: Track,
        val pb: Profil,
        val plan: RegiePlanung.Plan,
        val e: Einstellungen,
        val ausS: Double,
        val einS: Double,
        val weiter: Boolean,
    )

    /** Was der Baker ueber das Ergebnis meldet. */
    data class BackInfo(
        val sync: Boolean,
        val blendeS: Double,
        val takte: Int,
        val loopGuete: Double? = null,
        val pegelReparatur: String? = null,
    )

    data class BackErgebnis(val audio: FloatArray?, val info: BackInfo)

    private fun ref(t: Track) = RegiePlanung.Referenz(t.id, t.pfad, t.camelot)

    /**
     * Uebergang A -> B vorbereiten. `bpm` ist A's lokales Tempo, `abOriginalS` die Ausstiegsstelle
     * in Originalsekunden. `loopGuete(i, L)` liefert die Loop-Guete (nur fuer den Sicherheits-Blend).
     */
    fun vorbereiten(
        a: Track,
        pa: Profil,
        b: Track,
        pb: Profil,
        e: Einstellungen,
        abS: Double,
        abOriginalS: Double,
        weiter: Boolean,
        bpm: Double,
        baker: Baker,
        rang: Int = 0,
        letztesRezept: String? = null,
        vorlieben: Map<String, Double>? = null,
        stemsDa: Boolean = false,
        loopGuete: ((Int, Int) -> Double)? = null,
        rate: Int = 44100,
    ): BackErgebnis? {
        val grenze = max(e.maxBpm, 0.05) + RegiePlanung.TEMPO_SPIEL
        var ziel = b
        var pbZiel = pb
        var sync = b.bpm != null && abs(bpm - b.bpm) <= grenze
        if (!sync && b.bpm != null) {
            // Doppel-/Halbtempo: B laeuft im doppelten/halben Taktraster.
            val f = listOf(2.0, 0.5).firstOrNull { abs(bpm - it * b.bpm) <= grenze }
            if (f != null) {
                ziel = b.copy(bpm = f * b.bpm)
                pbZiel = tempoMal(pb, f)
                sync = true
            }
        }
        val harmonisch = Planer.harmonieNote(a.camelot, ziel.camelot).second != "fremd"
        val plaene = RegiePlanung.planen(
            ref(a), pa, ref(ziel), pbZiel, e, abOriginalS, sync, harmonisch,
            sofort = weiter, stemsDa = stemsDa, vorher = letztesRezept, vorlieben = vorlieben, anzahl = 3,
        )
        if (plaene.isEmpty()) return null

        val start = min(rang, plaene.size - 1)
        val maxVersuche = if (weiter) 2 else 5
        val durchgefallen = mutableSetOf<String>()
        var versuche = 0
        var letztesErgebnis: BackErgebnis? = null
        for (plan in plaene.drop(start)) {
            if (versuche == maxVersuche) break
            if (plan.rezept in durchgefallen) continue
            versuche++
            val auftrag = BackAuftrag(a, pa, ziel, pbZiel, plan, e, plan.ausS, plan.einS, weiter)
            val ergebnis = baker.backen(auftrag)
            if (pruefen(plan, ergebnis, a, pa, ziel, pbZiel, e, rate) == null) return ergebnis
            durchgefallen.add(plan.rezept)
            letztesErgebnis = ergebnis
        }
        if (weiter && letztesErgebnis != null) return letztesErgebnis

        // Nichts bestanden: sicherer Profi-Blend am besten Ausstieg, ohne Loop und Effekt.
        val p0 = plaene[start]
        var kurz = min(p0.takte, 16)
        val iAus = pa.taktBei(p0.ausS)
        var aEndet = pa.n - iAus < kurz
        if (aEndet && loopGuete != null && loopGuete(iAus, kurz) < RegiePlanung.LOOP_GUETE_MIN) {
            kurz = max(2, (pa.n - iAus) / 2 * 2)
            aEndet = false
        }
        val sicher = p0.copy(
            rezept = "profi_eq",
            grund = "Sicherheits-Blend: die Rezepte davor fielen durch",
            takte = kurz,
            einst = p0.einst.copy(
                takte = kurz, weiterTakte = kurz, art = "eigen", lautstaerke = "nahtlos", eq = "profi",
                filter = "keiner", effekt = "keiner", effektEin = "keiner",
                loop = if (aEndet) "auto" else "keiner", loopEin = 0, loopEinMal = 0, trick = "keiner",
                gesangTakt = -1,
            ),
        )
        return baker.backen(BackAuftrag(a, pa, ziel, pbZiel, sicher, e, sicher.ausS, sicher.einS, weiter))
    }

    /** Selbstkontrolle: Tempo, Loop-Sauberkeit, Buckel/Loch. */
    private fun pruefen(
        plan: RegiePlanung.Plan,
        ergebnis: BackErgebnis,
        a: Track,
        pa: Profil,
        b: Track,
        pb: Profil,
        e: Einstellungen,
        rate: Int,
    ): String? {
        val info = ergebnis.info
        if (plan.einst.art in SYNC_ARTEN && !info.sync) return "Tempo beim Backen nicht angeglichen"
        val guete = info.loopGuete
        if (guete != null && guete < RegiePlanung.LOOP_GUETE_MIN) return "Loop nicht sauber (Güte $guete)"
        val audio = ergebnis.audio ?: return null
        val gainA = if (e.lautheit) a.gainDb else 0.0
        val gainB = if (e.lautheit) b.gainDb else 0.0
        return Regie.pruefen(audio, rate, plan.takte, pa, pb, plan.ausS, plan.einS, gainA, gainB, plan.rezept)
    }
}
