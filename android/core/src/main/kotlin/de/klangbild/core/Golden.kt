package de.klangbild.core

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.abs
import kotlin.math.sqrt

/**
 * Leser der Python-Golden-Daten (BAUPLAN-ANDROID §12.2, Aufgabe T0.3).
 *
 * Der Golden-Export (`prototyp/klangbild/golden.py`, Aufgabe T0.2) schreibt je
 * Fall eine `<name>.json` und – für lange Audio-Arrays – eine `<name>.f32`
 * (float32 little endian, C-order, Stereo L/R interleaved). Diese Klasse lädt
 * beides und vergleicht mit den Toleranzen aus §12.3.
 *
 * Regeln:
 * - Nur lesen. Der Ordner ist ein Eingabedatenbestand, kein Cache.
 * - Fehlende `.f32`-Dateien sind kein Testfehler, sondern ein Hinweis: der
 *   vollständige Satz entsteht mit `python -m klangbild golden <ziel>`
 *   (deterministisch aus denselben Quellen). Der Reader meldet das klar.
 */
class Golden(val dir: File) {

    private val json = Json { ignoreUnknownKeys = true; isLenient = false }

    init {
        require(dir.isDirectory) { "Golden-Ordner fehlt: ${dir.absolutePath}" }
    }

    /** Ein einzelner Fall: Kopf (function/inputs/expected/tolerance) und Dateiname. */
    data class Case(
        val name: String,
        val function: String,
        val inputs: JsonObject,
        val expected: JsonElement,
        val tolerance: String,
    )

    private val cache = HashMap<String, JsonObject>()

    /** Liest `<name>.json` und baut den Fall. */
    fun case(name: String): Case {
        val body = raw(name)
        return Case(
            name = name,
            function = body["function"]!!.jsonPrimitive.content,
            inputs = body["inputs"]!!.jsonObject,
            expected = body["expected"]!!,
            tolerance = body["tolerance"]?.jsonPrimitive?.content ?: "values",
        )
    }

    /** Rohgehalt von `<name>.json` einschließlich `format_version`. */
    fun raw(name: String): JsonObject =
        cache.getOrPut(name) {
            val file = File(dir, "$name.json")
            require(file.isFile) { "Golden-Fall fehlt: ${file.absolutePath}" }
            json.parseToJsonElement(file.readText(Charsets.UTF_8)).jsonObject
        }

    /** Namen aller Fälle (ohne Endung), sortiert. */
    fun caseNames(): List<String> =
        dir.listFiles { f -> f.isFile && f.name.endsWith(".json") }
            ?.map { it.name.removeSuffix(".json") }
            ?.sorted()
            ?: emptyList()

    fun hasCase(name: String): Boolean = File(dir, "$name.json").isFile

    /** Manifest (T0.2): Fälle, Dateien, Toleranzen, Gaps. */
    fun manifest(): JsonObject = raw("manifest")

    /**
     * Liest ein float32-Array aus einer `.f32`-Datei.
     *
     * `shape` kommt aus dem JSON-Verweis (z. B. `[44100, 2]`); C-order bedeutet
     * hier Stereo L/R interleaved. Der Rückgabewert ist flach (row-major), genau
     * so, wie der Verweis `count` zählt.
     */
    fun f32(fileName: String, shape: List<Int>): FloatArray {
        val file = File(dir, fileName)
        require(file.isFile) {
            "Binärarray fehlt: $fileName. Der vollständige Golden-Satz entsteht mit " +
                "`python -m klangbild golden <ziel>` (siehe testdata/golden/.gitignore)."
        }
        val bytes = file.readBytes()
        val count = shape.fold(1) { a, b -> a * b }
        require(bytes.size == count * 4) {
            "$fileName: ${bytes.size} Bytes passen nicht zu shape=$shape (erwartet ${count * 4})."
        }
        val buffer = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
        return FloatArray(count) { buffer.getFloat() }
    }

    /**
     * Folgt einem Verweis-Objekt des Exports (`{"file","dtype","shape",...}`) und
     * liefert die flachen Werte. Andere Gestalten (JSON-Zahlen) werden als
     * Doppelwerte gelesen, damit derselbe Vergleich für beide Quellen gilt.
     */
    fun values(element: JsonElement): DoubleArray {
        if (element is JsonObject && element["dtype"]?.jsonPrimitive?.content == "float32-le") {
            val shape = element["shape"]!!.jsonArray.map { it.jsonPrimitive.intOrNull ?: error("shape") }
            // Datei EINMAL lesen: f32() im Lambda wuerde je Element erneut von
            // der Platte lesen (O(n^2) auf ~100k Samples).
            val roh = f32(element["file"]!!.jsonPrimitive.content, shape)
            return DoubleArray(roh.size) { roh[it].toDouble() }
        }
        return toDoubles(element)
    }

    companion object {
        /** Wandelt ein JSON-Element rekursiv in flache Doppelwerte (None/Null/Wörter → Fehler). */
        fun toDoubles(element: JsonElement): DoubleArray {
            val out = ArrayList<Double>()
            fun walk(e: JsonElement) {
                when (e) {
                    is JsonArray -> e.forEach(::walk)
                    is JsonPrimitive -> when {
                        e is JsonNull -> error("Null in einem Zahlenarray")
                        e.isString -> out.add(e.content.toDouble())
                        else -> out.add(e.doubleOrNull ?: error("keine Zahl: ${e.content}"))
                    }
                    else -> error("Verschachteltes Objekt in einem Zahlenarray")
                }
            }
            walk(element)
            return out.toDoubleArray()
        }

        fun toDoubles(element: JsonElement, fallback: DoubleArray): DoubleArray =
            if (element is JsonNull) fallback else toDoubles(element)

        /** Wahrheitswert eines JSON-Primitivs. */
        fun bool(element: JsonElement): Boolean =
            element.jsonPrimitive.booleanOrNull ?: error("kein Wahrheitswert: ${element.jsonPrimitive.content}")
    }

    // --- Vergleich nach §12.3 -------------------------------------------------

    /** Absolute Obergrenze (Kurven, Hüllkurven, Planwerte). */
    fun assertValues(name: String, expected: JsonElement, actual: DoubleArray) =
        assertClose(name, expected, actual, absTol = 1e-6, rmsFloorDb = null)

    /** DSP-Vergleich: max. Abweichung 1e-4, RMS-Differenz < −80 dBFS. */
    fun assertDsp(name: String, expected: JsonElement, actual: DoubleArray) =
        assertClose(name, expected, actual, absTol = 1e-4, rmsFloorDb = -80.0)

    /** Hall (FFT-Faltung): RMS-Differenz < −70 dBFS. */
    fun assertReverb(name: String, expected: JsonElement, actual: DoubleArray) =
        assertClose(name, expected, actual, absTol = null, rmsFloorDb = -70.0)

    /**
     * Vergleicht Zahlenreihen nach der im Fall vermerkten Toleranz.
     *
     * `absTol` prüft das größte Einzelsample, `rmsFloorDb` die Energie der
     * Differenz gegen die Energie der Referenz (RMS-Differenz in dBFS, negativ).
     */
    fun assertClose(
        name: String,
        expected: JsonElement,
        actual: DoubleArray,
        absTol: Double?,
        rmsFloorDb: Double?,
    ) {
        val ref = values(expected)
        require(ref.size == actual.size) { "$name: Länge ${actual.size}, erwartet ${ref.size}" }
        var maxAbs = 0.0
        var fehler = 0.0
        var bezug = 0.0
        for (i in ref.indices) {
            val d = actual[i] - ref[i]
            maxAbs = maxOf(maxAbs, abs(d))
            fehler += d * d
            bezug += ref[i] * ref[i]
        }
        if (absTol != null) {
            require(maxAbs <= absTol) { "$name: max. Abweichung $maxAbs > $absTol" }
        }
        if (rmsFloorDb != null) {
            val rmsDb = if (bezug <= 0.0) {
                if (fehler <= 1e-30) -200.0 else 20.0
            } else {
                10.0 * kotlin.math.log10(fehler / bezug)
            }
            require(rmsDb <= rmsFloorDb) { "$name: RMS-Differenz $rmsDb dBFS > $rmsFloorDb" }
        }
    }

    /** RMS eines flachen Arrays (Stereo interleaved) für Größenordnungsprüfungen. */
    fun rms(values: DoubleArray): Double =
        if (values.isEmpty()) 0.0 else sqrt(values.sumOf { it * it } / values.size)
}
