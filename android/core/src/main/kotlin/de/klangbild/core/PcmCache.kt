package de.klangbild.core

import java.io.Closeable
import java.io.File
import java.io.RandomAccessFile
import java.lang.Math.rint
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * PCM-Cache je Titel (BAUPLAN §4.3): dekodiertes Audio als int16 in einer Datei.
 *
 * Kopf (16 Byte): Magic `KBPC`, Version u16, Kanäle u16 (=2), Rate u32 (=44100), Frames u32.
 * Danach Samples als int16 little endian, Stereo interleaved. Der Schreiber erhöht `frames` nach
 * jedem Block (fortschreitendes Schreiben); Leser sehen nie mehr als `frames`.
 */
class PcmDatei private constructor(private val datei: File, private var zugriff: RandomAccessFile) : Closeable {

    /** Kopf der Datei. */
    data class Kopf(val version: Int, val channels: Int, val rate: Int, val frames: Int)

    fun kopf(): Kopf {
        zugriff.seek(0)
        val kopfBytes = ByteArray(KOPF_BYTES)
        zugriff.readFully(kopfBytes)
        val puffer = ByteBuffer.wrap(kopfBytes).order(ByteOrder.LITTLE_ENDIAN)
        val magic = String(kopfBytes, 0, 4, Charsets.US_ASCII)
        require(magic == MAGIC) { "Kein PCM-Cache: ${datei.name}" }
        val version = puffer.getShort(4).toInt() and 0xFFFF
        val kanaele = puffer.getShort(6).toInt() and 0xFFFF
        val rate = puffer.getInt(8)
        val frames = puffer.getInt(12)
        return Kopf(version, kanaele, rate, frames)
    }

    /** Frames, die bereits geschrieben sind. */
    fun frames(): Int = kopf().frames

    /** Liest `anzahl` Frames ab `vonFrame` (Stereo interleaved). Kurze Reste werden mit 0 gefüllt. */
    fun lese(vonFrame: Int, anzahl: Int): FloatArray {
        val k = kopf()
        val kan = k.channels
        val aus = FloatArray(anzahl * kan)
        if (anzahl <= 0) return aus
        val verfuegbar = (k.frames - vonFrame).coerceAtLeast(0).coerceAtMost(anzahl)
        if (verfuegbar <= 0) return aus
        val bytes = ByteArray(verfuegbar * kan * 2)
        zugriff.seek(KOPF_BYTES.toLong() + vonFrame.toLong() * kan * 2L)
        zugriff.readFully(bytes)
        val puffer = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
        for (i in 0 until verfuegbar * kan) aus[i] = puffer.getShort().toFloat() / 32767.0f
        return aus
    }

    /** Hängt einen Block an und aktualisiert `frames` im Kopf (fortschreitendes Schreiben). */
    fun schreibeBlock(daten: FloatArray, kanaele: Int) {
        require(kanaele > 0 && daten.size % kanaele == 0) { "Block passt nicht zu den Kanälen." }
        val frames = daten.size / kanaele
        val bytes = ByteArray(daten.size * 2)
        val puffer = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
        for (wert in daten) {
            val gerundet = rint(wert.toDouble() * 32767.0).toInt().coerceIn(-32768, 32767)
            puffer.putShort(gerundet.toShort())
        }
        val alt = kopf()
        require(alt.channels == kanaele) { "Kanalzahl passt nicht zum Kopf." }
        zugriff.seek(KOPF_BYTES.toLong() + alt.frames.toLong() * kanaele * 2L)
        zugriff.write(bytes)
        zugriff.seek(12)
        val kopfFrames = ByteBuffer.allocate(4).order(ByteOrder.LITTLE_ENDIAN).putInt(alt.frames + frames).array()
        zugriff.write(kopfFrames)
    }

    override fun close() {
        try {
            zugriff.fd.sync()
        } catch (_: Exception) {
            // Synchronschreiben ist nur fuer die Dauerhaftigkeit noetig, nicht fuer Leser.
        }
        zugriff.close()
    }

    companion object {
        const val MAGIC = "KBPC"
        const val VERSION = 1
        const val KOPF_BYTES = 16

        fun anlegen(datei: File, rate: Int = 44100, kanaele: Int = 2): PcmDatei {
            datei.parentFile?.mkdirs()
            var zugriff = RandomAccessFile(datei, "rw")
            if (datei.length() >= KOPF_BYTES) {
                try {
                    val vorhanden = PcmDatei(datei, zugriff).kopf()
                    if (vorhanden.channels == kanaele && vorhanden.rate == rate) return PcmDatei(datei, zugriff)
                } catch (_: Exception) {
                    // Ungueltiger Kopf: unten neu anlegen.
                }
                zugriff.close()
                datei.delete()
                zugriff = RandomAccessFile(datei, "rw")
            }
            zugriff.setLength(0)
            val kopf = ByteBuffer.allocate(KOPF_BYTES).order(ByteOrder.LITTLE_ENDIAN)
            kopf.put(MAGIC.toByteArray(Charsets.US_ASCII))
            kopf.putShort(VERSION.toShort())
            kopf.putShort(kanaele.toShort())
            kopf.putInt(rate)
            kopf.putInt(0)
            zugriff.write(kopf.array())
            zugriff.fd.sync()
            return PcmDatei(datei, zugriff)
        }

        fun oeffnen(datei: File): PcmDatei? {
            if (!datei.isFile || datei.length() < KOPF_BYTES) return null
            val zugriff = try {
                RandomAccessFile(datei, "r")
            } catch (_: Exception) {
                return null
            }
            return try {
                val dateiObj = PcmDatei(datei, zugriff)
                dateiObj.kopf()
                dateiObj
            } catch (_: Exception) {
                zugriff.close()
                null
            }
        }
    }
}

/**
 * Verwaltet die PCM-Dateien im App-Speicher (`filesDir/pcm`). Höchstens [maxDateien] bleiben;
 * die ältesten fliegen zuerst raus. Dateiname: `<trackId>_<startFrame>_<frames>.pcm`.
 */
class PcmCache(val ordner: File, val maxDateien: Int = 4) {

    fun dateiName(trackId: Int, startFrame: Int, frames: Int): String = "${trackId}_${startFrame}_${frames}.pcm"

    fun datei(trackId: Int, startFrame: Int, frames: Int): File = File(ordner, dateiName(trackId, startFrame, frames))

    fun anlegen(trackId: Int, startFrame: Int, frames: Int, rate: Int = 44100): PcmDatei =
        PcmDatei.anlegen(datei(trackId, startFrame, frames), rate, 2)

    /** Gebackene Blende zwischen zwei Titeln; eigener Name, kollidiert nicht mit Titel-IDs. */
    fun blendeDatei(aId: Int, bId: Int): File = File(ordner, "blende_${aId}_${bId}.pcm")

    fun anlegenBlende(aId: Int, bId: Int, rate: Int = 44100): PcmDatei =
        PcmDatei.anlegen(blendeDatei(aId, bId), rate, 2)

    fun oeffnen(trackId: Int, startFrame: Int, frames: Int): PcmDatei? =
        PcmDatei.oeffnen(datei(trackId, startFrame, frames))

    fun alle(): List<File> =
        ordner.listFiles { f -> f.isFile && f.name.endsWith(".pcm") }?.sortedBy { it.lastModified() } ?: emptyList()

    /** Löscht alle Cache-Dateien eines Titels (vor einem neuen Dekodieren). */
    fun loesche(trackId: Int) {
        ordner.listFiles { f -> f.isFile && f.name.startsWith("${trackId}_") }?.forEach { it.delete() }
    }

    /** Findet die neueste Cache-Datei eines Titels (Dateiname beginnt mit `<trackId>_`). */
    fun finde(trackId: Int): File? =
        ordner.listFiles { f -> f.isFile && f.name.startsWith("${trackId}_") && f.name.endsWith(".pcm") }
            ?.maxByOrNull { it.lastModified() }

    /** Löscht die ältesten ungeschützten Dateien, bis nur noch [maxDateien] übrig sind. */
    fun aufraeumen(behalten: Collection<String> = emptyList()) {
        val geschuetzt = behalten.toSet()
        val alle = alle()   // aelteste zuerst
        var ueberzaehlig = alle.size - maxDateien
        for (datei in alle) {
            if (ueberzaehlig <= 0) break
            if (datei.name in geschuetzt) continue
            datei.delete()
            ueberzaehlig--
        }
    }
}
