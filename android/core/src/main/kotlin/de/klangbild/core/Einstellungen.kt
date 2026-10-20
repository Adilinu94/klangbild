package de.klangbild.core

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull

/**
 * Einstellungen des Auto-Mix (Port von `prototyp/klangbild/einstellungen.py`).
 *
 * Eine Datenklasse mit den Standardwerten des Prototyps. [ausDict] prueft jeden Wert gegen
 * seine erlaubten Auswahlen und Grenzen: die Oberflaeche ist eine Vertrauensgrenze, kaputte
 * Werte duerfen den Mixer nicht stoppen (unbekanntes und ungueltiges wird ignoriert).
 */
data class Einstellungen(
    val modus: String = "ausgewogen",
    val spielanteil: String = "lang",
    val experimente: String = "klassisch",
    val takte: Int = 16,
    val art: String = "auto",
    val ausstieg: String = "outro",
    val vorEndeTakte: Int = 16,
    val einstieg: String = "intro",
    val tempoModus: String = "rampe",
    val maxBpm: Double = 5.0,
    val keylock: Boolean = true,
    val harmonie: String = "locker",
    val weiterTakte: Int = 8,
    val weiterAb: String = "phrase",
    val lautheit: Boolean = true,
    val stems: Boolean = true,
    val stemsVorrat: String = "alle",
    val lautstaerke: String = "nahtlos",
    val eq: String = "bass_mitte",
    val filter: String = "keiner",
    val effekt: String = "keiner",
    val effektEin: String = "keiner",
    val loop: String = "keiner",
    val trick: String = "keiner",
    val bassTakt: Int = -1,
    val loopStart: Int = -1,
    val loopEin: Int = 0,
    val loopEinMal: Int = 0,
    val gesangTakt: Int = -1,
    val kritiker: Boolean = false,
    val setBogen: String = "gleichmaessig",
) {
    /** Wie `dataclasses.asdict` im Prototyp: Schluessel in Feldreihenfolge, snake_case. */
    fun toMap(): Map<String, Any?> = linkedMapOf(
        "modus" to modus,
        "spielanteil" to spielanteil,
        "experimente" to experimente,
        "takte" to takte,
        "art" to art,
        "ausstieg" to ausstieg,
        "vor_ende_takte" to vorEndeTakte,
        "einstieg" to einstieg,
        "tempo_modus" to tempoModus,
        "max_bpm" to maxBpm,
        "keylock" to keylock,
        "harmonie" to harmonie,
        "weiter_takte" to weiterTakte,
        "weiter_ab" to weiterAb,
        "lautheit" to lautheit,
        "stems" to stems,
        "stems_vorrat" to stemsVorrat,
        "lautstaerke" to lautstaerke,
        "eq" to eq,
        "filter" to filter,
        "effekt" to effekt,
        "effekt_ein" to effektEin,
        "loop" to loop,
        "trick" to trick,
        "bass_takt" to bassTakt,
        "loop_start" to loopStart,
        "loop_ein" to loopEin,
        "loop_ein_mal" to loopEinMal,
        "gesang_takt" to gesangTakt,
        "kritiker" to kritiker,
        "set_bogen" to setBogen,
    )

    /** Eine Kopie mit genau einem geaenderten Feld (`dataclasses.replace`). */
    fun mit(feld: String, wert: Any): Einstellungen = when (feld) {
        "modus" -> copy(modus = wert as String)
        "spielanteil" -> copy(spielanteil = wert as String)
        "experimente" -> copy(experimente = wert as String)
        "takte" -> copy(takte = wert as Int)
        "art" -> copy(art = wert as String)
        "ausstieg" -> copy(ausstieg = wert as String)
        "vor_ende_takte" -> copy(vorEndeTakte = wert as Int)
        "einstieg" -> copy(einstieg = wert as String)
        "tempo_modus" -> copy(tempoModus = wert as String)
        "max_bpm" -> copy(maxBpm = wert as Double)
        "keylock" -> copy(keylock = wert as Boolean)
        "harmonie" -> copy(harmonie = wert as String)
        "weiter_takte" -> copy(weiterTakte = wert as Int)
        "weiter_ab" -> copy(weiterAb = wert as String)
        "lautheit" -> copy(lautheit = wert as Boolean)
        "stems" -> copy(stems = wert as Boolean)
        "stems_vorrat" -> copy(stemsVorrat = wert as String)
        "lautstaerke" -> copy(lautstaerke = wert as String)
        "eq" -> copy(eq = wert as String)
        "filter" -> copy(filter = wert as String)
        "effekt" -> copy(effekt = wert as String)
        "effekt_ein" -> copy(effektEin = wert as String)
        "loop" -> copy(loop = wert as String)
        "trick" -> copy(trick = wert as String)
        "bass_takt" -> copy(bassTakt = wert as Int)
        "loop_start" -> copy(loopStart = wert as Int)
        "loop_ein" -> copy(loopEin = wert as Int)
        "loop_ein_mal" -> copy(loopEinMal = wert as Int)
        "gesang_takt" -> copy(gesangTakt = wert as Int)
        "kritiker" -> copy(kritiker = wert as Boolean)
        "set_bogen" -> copy(setBogen = wert as String)
        else -> this
    }

    companion object {
        /** `einstellungen.regie_einst`: Regie-Einstellungen oder null, wenn der Nutzer alles vorgibt. */
        fun regieEinst(e: Einstellungen): Einstellungen? =
            if (e.modus != "manuell") e else if (e.art == "auto") e.copy(modus = "ausgewogen") else null

        /**
         * `einstellungen.aus_dict`: uebernimmt nur gueltige Werte. Jeder Wert wird wie im
         * Prototyp geprueft (Python-`int`, `float`, `bool`); Fehler ueberspringen das Feld.
         */
        fun ausDict(roh: Map<String, JsonElement>, basis: Einstellungen = Einstellungen()): Einstellungen {
            var e = basis
            for ((name, element) in roh) {
                val wert: Any = when {
                    name in Auswahl.alle -> element.alsText()?.takeIf { it in Auswahl.alle.getValue(name) }
                        ?: continue
                    name == "takte" || name == "weiter_takte" -> {
                        val i = element.alsGanzzahl() ?: continue
                        if (i !in Takte) continue
                        i
                    }
                    name in Grenzen -> {
                        val x = element.alsKommazahl() ?: continue
                        val (lo, hi) = Grenzen.getValue(name)
                        val geklemmt = x.coerceIn(lo, hi)
                        if (name in GanzzahlGrenzen) geklemmt.toInt() else geklemmt
                    }
                    else -> {
                        val standard = e.toMap()[name] as? Boolean ?: continue
                        element.alsWahrheitswert() ?: standard
                    }
                }
                e = e.mit(name, wert)
            }
            return e
        }
    }
}

/** Auswahllisten des Prototyps (`einstellungen.AUSWAHL`). */
object Auswahl {
    val arten = listOf(
        "auto", "eigen", "eq", "crossfade", "filter", "echo", "schnitt",
        "drums_zuerst", "acapella", "gesangsschutz", "gesang_zuerst", "double_drop", "melodie_zuerst",
    )
    val lautstaerke = listOf(
        "nahtlos", "linear", "ueberlappung", "hart_ein", "hart_aus", "hart_beide",
        "mitte", "frueh", "spaet", "letzter_takt", "drop", "doppel", "mitte_weich",
    )
    val eq = listOf(
        "keiner", "profi", "bass_mitte", "bass_anfang", "bass_ende", "drei_band", "bass_schnell", "bass_lang",
        "bass_takt",
    )
    val filter = listOf(
        "keiner", "tp_aus", "tp_ein", "tp_beide", "hp_aus", "hp_ein", "hp_beide",
        "tp_ein_hp_aus", "hp_ein_tp_aus", "hp_aus_reso", "tp_aus_reso",
    )
    val effektTypen = listOf(
        "hall", "echo50", "echo75", "echo100", "delay50", "delay75", "delay100", "pingpong50", "pingpong75",
    )
    val effektModi = listOf("mitte_aus", "ende_ab", "ende_aus")
    val effekt = listOf("keiner") + effektTypen.flatMap { t -> effektModi.map { m -> "${t}_$m" } }
    val effektEin = listOf("keiner", "hall", "rueckhall")
    val loop = listOf("keiner", "auto", "1", "2", "4", "8", "16", "32", "rolle")
    val trick = listOf("keiner", "bremse", "spinback", "riser", "flanger", "teaser", "phaser", "gate", "crush", "wechsel")
    val experimente = listOf("klassisch", "kreativ", "wild")
    val modi = listOf("manuell", "kurz", "ausgewogen", "lang")

    val alle: Map<String, List<String>> = linkedMapOf(
        "modus" to modi,
        "spielanteil" to listOf("schnell", "lang"),
        "art" to arten,
        "lautstaerke" to lautstaerke,
        "eq" to eq,
        "filter" to filter,
        "effekt" to effekt,
        "effekt_ein" to effektEin,
        "loop" to loop,
        "trick" to trick,
        "experimente" to experimente,
        "ausstieg" to listOf("outro", "phrase", "vor_ende"),
        "einstieg" to listOf("intro", "drop"),
        "tempo_modus" to listOf("b_an_a", "a_an_b", "rampe", "vorlauf"),
        "harmonie" to listOf("streng", "locker", "aus"),
        "weiter_ab" to listOf("takt", "phrase"),
        "stems_vorrat" to listOf("aus", "upload", "alle"),
        "set_bogen" to listOf("gleichmaessig", "aufbauen", "welle"),
    )
}

/** Erlaubte Blendenlaengen (`einstellungen.TAKTE`). */
val Takte: List<Int> = listOf(1, 2, 4, 8, 16, 24, 32)

/** Wertebereiche (`einstellungen.GRENZEN`); die Ausgabe ist ganzzahlig ausser bei `max_bpm`. */
val Grenzen: Map<String, Pair<Double, Double>> = linkedMapOf(
    "max_bpm" to (0.0 to 10.0),
    "vor_ende_takte" to (1.0 to 64.0),
    "bass_takt" to (-1.0 to 32.0),
    "loop_start" to (-1.0 to 64.0),
    "loop_ein" to (0.0 to 16.0),
    "loop_ein_mal" to (0.0 to 8.0),
    "gesang_takt" to (-1.0 to 96.0),
)

/** Grenzen, deren Ergebnis `int(...)` wird (alle ausser `max_bpm`). */
val GanzzahlGrenzen: Set<String> = Grenzen.keys - "max_bpm"

// --- Python-Werte aus JSON -----------------------------------------------------

/** `v` als Text, sonst null (Python vergleicht `v in tuple`; Zahlen passen dort nicht). */
internal fun JsonElement.alsText(): String? =
    (this as? JsonPrimitive)?.takeIf { it.isString }?.content

/** Python-`int(v)`: Text muss ganzzahlig sein, Fliesskomma wird zur Null hin abgeschnitten. */
internal fun JsonElement.alsGanzzahl(): Int? {
    val p = this as? JsonPrimitive ?: return null
    if (p is JsonNull) return null
    p.booleanOrNull?.let { return if (it) 1 else 0 }
    p.intOrNull?.let { return it }
    if (p.isString) return p.content.trim().toIntOrNull()
    val d = p.doubleOrNull ?: return null
    return truncate(d)
}

/** Python-`float(v)`. */
internal fun JsonElement.alsKommazahl(): Double? {
    val p = this as? JsonPrimitive ?: return null
    if (p is JsonNull) return null
    p.booleanOrNull?.let { return if (it) 1.0 else 0.0 }
    if (p.isString) return p.content.trim().toDoubleOrNull()
    return p.doubleOrNull
}

/** Python-`bool(v)`: Text nicht leer, Zahl ungleich 0, Liste/Objekt nicht leer, null ist falsch. */
internal fun JsonElement.alsWahrheitswert(): Boolean? = when (this) {
    is JsonNull -> false
    is JsonPrimitive -> {
        val wahrheitswert = booleanOrNull
        val text = if (isString) content else null
        when {
            wahrheitswert != null -> wahrheitswert
            text != null -> text.isNotEmpty()
            else -> doubleOrNull?.let { it != 0.0 } ?: false
        }
    }
    is JsonArray -> isNotEmpty()
    is JsonObject -> isNotEmpty()
}

private fun truncate(d: Double): Int? = when {
    d.isNaN() || d.isInfinite() -> null
    d >= Int.MAX_VALUE || d <= Int.MIN_VALUE -> null
    else -> d.toInt()
}
