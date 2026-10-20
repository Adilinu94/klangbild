package de.klangbild.wiedergabe

import de.klangbild.core.TitelAnalyse
import java.io.File

/** Analyse je Titel als kleine JSON-Datei (`filesDir/analyse/<id>.json`). */
class AnalyseSpeicher(private val ordner: File) {

    fun lade(id: Long): TitelAnalyse? {
        val datei = File(ordner, "$id.json")
        if (!datei.isFile) return null
        return try {
            TitelAnalyse.aus(datei.readText())
        } catch (e: Exception) {
            null
        }
    }

    fun sichere(id: Long, analyse: TitelAnalyse) {
        try {
            ordner.mkdirs()
            File(ordner, "$id.json").writeText(analyse.json())
        } catch (e: Exception) {
            // Zwischenspeicher ist Komfort, kein Muss.
        }
    }
}
