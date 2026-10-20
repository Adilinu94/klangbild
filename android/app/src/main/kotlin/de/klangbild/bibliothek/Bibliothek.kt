package de.klangbild.bibliothek

import android.content.Context
import android.provider.MediaStore
import java.util.Locale

/** Ein Titel der Geraete-Bibliothek (MediaStore, §6.5). */
data class Titel(
    val id: Long,
    val pfad: String,
    val titel: String,
    val kuenstler: String,
    val dauerMs: Long,
    val albumId: Long = 0L,
) {
    val dauerText: String
        get() {
            val s = dauerMs / 1000
            return String.format(Locale.US, "%d:%02d", s / 60, s % 60)
        }
}

/** Liest alle Musikdateien des Geraets; blockiert, also nicht auf dem Main-Thread aufrufen. */
object Bibliothek {

    fun lesen(context: Context): List<Titel> {
        val spalten = arrayOf(
            MediaStore.Audio.Media._ID,
            MediaStore.Audio.Media.DATA,
            MediaStore.Audio.Media.TITLE,
            MediaStore.Audio.Media.ARTIST,
            MediaStore.Audio.Media.DURATION,
            MediaStore.Audio.Media.ALBUM_ID,
        )
        val aus = mutableListOf<Titel>()
        context.contentResolver.query(
            MediaStore.Audio.Media.EXTERNAL_CONTENT_URI,
            spalten,
            "${MediaStore.Audio.Media.IS_MUSIC} != 0",
            null,
            "${MediaStore.Audio.Media.TITLE} COLLATE NOCASE ASC",
        )?.use { zeiger ->
            while (zeiger.moveToNext()) {
                val pfad = zeiger.getString(1) ?: continue
                if (pfad.isEmpty()) continue
                aus += Titel(
                    id = zeiger.getLong(0),
                    pfad = pfad,
                    titel = zeiger.getString(2) ?: "?",
                    kuenstler = zeiger.getString(3) ?: "?",
                    dauerMs = zeiger.getLong(4),
                    albumId = zeiger.getLong(5),
                )
            }
        }
        return aus
    }
}
