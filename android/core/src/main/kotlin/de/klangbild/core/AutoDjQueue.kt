package de.klangbild.core

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.double
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.io.File
import kotlin.math.max
import kotlin.math.min
import kotlin.random.Random

/**
 * Warteschlange und Lernen des Auto-DJ (Port von `live.Wiedergabe.einreihen/entfernen/verschieben/
 * leeren/weiter/_lernen/bewerten/sortieren`).
 *
 * Die Gewichte je Rezept lernen lokal: +0,3 je durchgehoertem, -1 je abgebrochenem Uebergang
 * (Bereich -5..+3). `sortieren` legt die ganze Bibliothek in die beste Reihenfolge.
 */
class AutoDjQueue(bibliothek: Set<Int> = emptySet(), var lernDatei: File? = null) {

    private var ids: Set<Int> = bibliothek
    val warteschlange: MutableList<Int> = mutableListOf()
    val vorlieben: MutableMap<String, Double> = mutableMapOf()

    init {
        laden()
    }

    fun bibliothekSetzen(neu: Set<Int>) {
        ids = neu
        warteschlange.removeAll { it !in neu }
    }

    /** `einreihen`: true, wenn der Titel in der Bibliothek liegt. */
    fun einreihen(id: Int): Boolean {
        if (id !in ids) return false
        warteschlange.add(id)
        return true
    }

    fun entfernen(index: Int): Boolean {
        if (index !in warteschlange.indices) return false
        warteschlange.removeAt(index)
        return true
    }

    fun leeren() = warteschlange.clear()

    fun verschieben(index: Int, richtung: Int): Boolean {
        val ziel = index + richtung
        if (index !in warteschlange.indices || ziel !in warteschlange.indices) return false
        val tausch = warteschlange[index]
        warteschlange[index] = warteschlange[ziel]
        warteschlange[ziel] = tausch
        return true
    }

    /** `weiter`: naechster Titel aus der Warteschlange (ohne Auto-DJ-Sonderfall). */
    fun naechster(): Int? = if (warteschlange.isEmpty()) null else warteschlange.removeAt(0)

    /** `_lernen`: Gewicht je Rezept, geklemmt auf -5..+3. */
    fun lernen(rezept: String, gut: Boolean) {
        vorlieben[rezept] = min(3.0, max(-5.0, (vorlieben[rezept] ?: 0.0) + if (gut) 0.3 else -1.0))
        speichern()
    }

    /** `bewerten`: Schulnote 1 (sehr gut) .. 6; 1 bis 3 zaehlt wie durchgehoert. Gibt die Datensatznote 1..5. */
    fun bewerten(rezept: String, schulnote: Int): Double {
        lernen(rezept, schulnote <= 3)
        return 1.0 + (6 - schulnote) * 0.8
    }

    /**
     * `sortieren`: ganze Bibliothek in die beste Reihenfolge (ohne den aktuellen Titel). Mit
     * [paarnoten] ueber `plan.set_planen`, sonst gierig ueber `plan.sortiere_alle`.
     */
    fun sortieren(
        tracks: List<Track>,
        e: Einstellungen,
        aktuellId: Int? = null,
        profile: (Int) -> Profil? = { null },
        paarnoten: Paarnoten? = null,
        neu: Boolean = false,
        zufall: Random? = null,
    ): List<Int> {
        // Saubere Mischstellen: Ende von A und Anfang von B ohne Gesang mischen sich besser.
        val sauber = HashMap<Int, Pair<Double, Double>>()
        for (t in tracks) {
            val p = profile(t.id) ?: continue
            val g = p.gesang() ?: continue
            if (g.size >= 16) {
                sauber[t.id] = (1.0 - mittel(g, 0, 16)) to (1.0 - mittel(g, g.size - 16, g.size))
            }
        }
        val bonus = { a: Track, b: Track ->
            val sa = sauber[a.id] ?: (0.5 to 0.5)
            val sb = sauber[b.id] ?: (0.5 to 0.5)
            sa.second * sb.first
        }
        val planerTracks = tracks.map { AutoDjWahl.planTrack(it, energieLevel = profile(it.id)?.energielevel()) }
        val folge = if (paarnoten != null) {
            val start = Planer.startTitel(planerTracks, aktuellId) ?: return emptyList()
            Planer.setPlanen(
                planerTracks, start, e.maxBpm, e.harmonie,
                { a, b -> paarnoten.note(a, b) },
                { a, b -> paarnoten.rezept(a, b) },
                e.setBogen,
                if (neu) (zufall ?: Random.Default) else null,
            )
        } else {
            Planer.sortiereAlle(planerTracks, e.maxBpm, e.harmonie, aktuellId, bonus)
        }
        return folge.filter { it != aktuellId }
    }

    private fun mittel(x: DoubleArray, von: Int, bis: Int): Double {
        val a = max(0, von)
        val b = min(bis, x.size)
        if (b <= a) return 0.0
        var s = 0.0
        for (i in a until b) s += x[i]
        return s / (b - a)
    }

    private fun laden() {
        val f = lernDatei ?: return
        try {
            if (!f.isFile) return
            for ((schluessel, wert) in JSON.parseToJsonElement(f.readText(Charsets.UTF_8)).jsonObject) {
                vorlieben[schluessel] = wert.jsonPrimitive.double
            }
        } catch (_: Exception) {
            vorlieben.clear()
        }
    }

    private fun speichern() {
        val f = lernDatei ?: return
        try {
            val inhalt = buildJsonObject {
                for ((schluessel, wert) in vorlieben.toSortedMap()) put(schluessel, JsonPrimitive(wert))
            }
            f.parentFile?.mkdirs()
            f.writeText(JSON.encodeToString(JsonObject.serializer(), inhalt), Charsets.UTF_8)
        } catch (_: Exception) {
            // Lernen ist ein Bonus; ein Schreibfehler darf den Mixer nicht stoppen.
        }
    }

    companion object {
        private val JSON = Json { ignoreUnknownKeys = true; isLenient = false }
    }
}
