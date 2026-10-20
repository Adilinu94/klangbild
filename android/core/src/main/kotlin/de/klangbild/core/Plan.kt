package de.klangbild.core

import java.lang.Math.rint
import kotlin.math.abs
import kotlin.math.min

/** Merkmale eines Songs fuer den Planer (Port von `plan.Track`). */
data class Track(
    val id: Int,
    val pfad: String,
    val bpm: Double?,
    val camelot: String?,
    val energieDb: Double? = null,
    val vektor: List<Double>? = null,
    val energie: Double? = null,
    val genre: String? = null,
)

/**
 * Auto-DJ-Planer (Port von `prototyp/klangbild/plan.py`).
 *
 * Note eines Uebergangs = gewichtete Summe aus Harmonie (Camelot), Klang und Energie-Reise.
 * Tempo ist ein hartes Gate (hier: absolute BPM-Grenze, weil Keylock den Ausgleich erlaubt).
 * Determinismus: Gleichstaende bricht die kleinere Track-ID.
 */
object Planer {
    const val GEWICHT_HARMONIE = 0.40
    const val GEWICHT_KLANG = 0.35
    const val GEWICHT_ENERGIE = 0.25
    const val HARMONIE_EXAKT = 1.0
    const val HARMONIE_NACHBAR = 0.6
    const val HARMONIE_FREMD = 0.0
    const val ENERGIE_MAX_SPRUNG_DB = 12.0

    /** `keyestimate.camelot_nachbarn`: Nachbarn auf dem Camelot-Rad. */
    fun camelotNachbarn(code: String): Set<String> {
        if (code.length < 2 || !code.dropLast(1).all { it.isDigit() }) return setOf(code)
        val nummer = code.dropLast(1).toInt()
        val modus = code.last()
        val anderer = if (modus == 'B') 'A' else 'B'
        val nachbarn = mutableSetOf<String>()
        for (abstand in -1..1) {
            val n = ((nummer - 1 + abstand) % 12 + 12) % 12 + 1
            nachbarn.add("$n$modus")
        }
        nachbarn.add("$nummer$anderer")
        return nachbarn
    }

    /** `plan.harmonie_note`: Note 0..1 und Begruendung zweier Camelot-Codes. */
    fun harmonieNote(ziel: String?, kandidat: String?): Pair<Double, String> {
        if (ziel.isNullOrEmpty() || kandidat.isNullOrEmpty()) return HARMONIE_FREMD to "fremd"
        if (ziel == kandidat) return HARMONIE_EXAKT to "gleiche Tonart"
        if (kandidat in camelotNachbarn(ziel)) return HARMONIE_NACHBAR to "Camelot-Nachbar"
        return HARMONIE_FREMD to "fremd"
    }

    /** `plan.energie_note`: Note aus dem Lautstaerke-Sprung; unbekannt ist neutral 0,5. */
    fun energieNote(zielDb: Double?, kandidatDb: Double?, maxSprung: Double = ENERGIE_MAX_SPRUNG_DB): Pair<Double, String> {
        if (zielDb == null || kandidatDb == null) return 0.5 to "Energie unbekannt"
        val sprung = abs(kandidatDb - zielDb)
        if (sprung >= maxSprung) return 0.0 to "Energie-Sprung"
        return (1.0 - sprung / maxSprung) to "Energie passend"
    }

    /**
     * `plan.rangliste`: die `n` besten naechsten Songs. `harmonie` = "streng" (nur gleiche
     * Tonart/Nachbar, falls vorhanden), "locker" (Harmonie zaehlt mit) oder "aus".
     */
    fun rangliste(
        aktuell: Track,
        kandidaten: List<Track>,
        maxBpm: Double,
        harmonie: String = "locker",
        n: Int = 6,
        bonus: ((Track, Track) -> Double)? = null,
    ): List<Track> {
        if (kandidaten.isEmpty()) return emptyList()
        val basis = aktuell.bpm ?: 0.0

        // Doppel-/Halbtempo mischt mit (85 <-> 170).
        fun abstand(k: Track): Double {
            val b = k.bpm ?: basis
            return minOf(abs(b * 1.0 - basis), abs(b * 2.0 - basis), abs(b * 0.5 - basis))
        }

        var pool = kandidaten.filter { abstand(it) <= maxBpm + 1e-9 }
        if (pool.isEmpty()) {
            return kandidaten.sortedWith(compareBy({ abstand(it) }, { it.id })).take(n)
        }
        if (harmonie == "streng") {
            val passend = pool.filter { harmonieNote(aktuell.camelot, it.camelot).second != "fremd" }
            if (passend.isNotEmpty()) pool = passend
        }

        fun wert(k: Track): Double {
            val harm = if (harmonie != "aus") harmonieNote(aktuell.camelot, k.camelot).first else 0.5
            val energie = if (aktuell.energie != null && k.energie != null) {
                1.0 - min(1.0, 2.0 * abs(aktuell.energie - k.energie))
            } else {
                energieNote(aktuell.energieDb, k.energieDb).first
            }
            val tempo = 1.0 - abstand(k) / maxOf(maxBpm, 1.0)
            var summe = 0.35 * harm + 0.4 * energie + 0.25 * tempo
            if (!aktuell.genre.isNullOrEmpty() && !k.genre.isNullOrEmpty() && aktuell.genre != k.genre) {
                summe -= 0.2
            }
            if (bonus != null) summe = 0.8 * summe + 0.2 * bonus(aktuell, k)
            return summe
        }

        return pool.sortedWith(compareByDescending<Track> { wert(it) }.thenBy { it.id }).take(n)
    }

    /** `plan.naechster`: bester naechster Song. */
    fun naechster(
        aktuell: Track,
        kandidaten: List<Track>,
        maxBpm: Double,
        harmonie: String = "locker",
        bonus: ((Track, Track) -> Double)? = null,
    ): Track? = rangliste(aktuell, kandidaten, maxBpm, harmonie, 1, bonus).firstOrNull()

    /**
     * `plan.sortiere_alle` ohne Paarnoten: gierig ueber [rangliste]. Start ist `startId` oder
     * der groesste Tempo-Cluster (gerundetes BPM, wie `autodj.lade_tracks`).
     */
    fun sortiereAlle(
        tracks: List<Track>,
        maxBpm: Double,
        harmonie: String = "locker",
        startId: Int? = null,
        bonus: ((Track, Track) -> Double)? = null,
    ): List<Int> {
        if (tracks.isEmpty()) return emptyList()
        val index = tracks.associateBy { it.id }
        var start = startId?.takeIf { it in index }
        if (start == null) {
            val zaehler = LinkedHashMap<Long, Int>()
            for (t in tracks) {
                val gerundet = rint(t.bpm ?: 0.0).toLong()   // Python round: halbe Werte zur geraden Zahl
                zaehler[gerundet] = (zaehler[gerundet] ?: 0) + 1
            }
            var bestesBpm = 0L
            var besteZahl = -1
            for ((bpm, zahl) in zaehler) {
                if (zahl > besteZahl) {
                    besteZahl = zahl
                    bestesBpm = bpm
                }
            }
            start = tracks.first { rint(it.bpm ?: 0.0).toLong() == bestesBpm }.id
        }
        var aktuell = index.getValue(start)
        val uebrig = tracks.filter { it.id != start }.toMutableList()
        val folge = mutableListOf(start)
        while (uebrig.isNotEmpty()) {
            val naechster = rangliste(aktuell, uebrig, maxBpm, harmonie, 1, bonus).firstOrNull() ?: break
            uebrig.removeAll { it.id == naechster.id }
            folge.add(naechster.id)
            aktuell = naechster
        }
        return folge
    }
}
