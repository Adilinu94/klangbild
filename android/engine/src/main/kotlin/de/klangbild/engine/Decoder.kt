package de.klangbild.engine

import android.media.AudioFormat
import android.media.MediaCodec
import android.media.MediaExtractor
import android.media.MediaFormat
import de.klangbild.core.AudioKonverter
import de.klangbild.core.PcmCache
import de.klangbild.core.PcmDatei
import java.io.File
import kotlin.math.pow

/**
 * Dekodiert eine Audiodatei nach Stereo/44,1 kHz und legt sie im PCM-Cache ab (BAUPLAN §4.3).
 *
 * Ablauf: MediaExtractor → MediaCodec → float je Kanal → Stereo → lineares Resampling →
 * `gain_db` → PCM-Cache (1-s-Blöcke). Der Limiter aus §4.3 Schritt 3 folgt, sobald
 * `dsp/begrenzen` über JNI erreichbar ist.
 *
 * Blockiert (CPU und I/O): im Planer-Thread aufrufen, nie im UI- oder Audio-Thread.
 */
class Decoder(private val zielRate: Int = 44100) {

    data class Ergebnis(val datei: PcmDatei, val frames: Int, val rate: Int)

    fun dekodiere(datei: File, cache: PcmCache, trackId: Int, gainDb: Double = 0.0): Ergebnis {
        val extraktor = MediaExtractor()
        var codec: MediaCodec? = null
        try {
            extraktor.setDataSource(datei.absolutePath)
            val spur = (0 until extraktor.trackCount).firstOrNull { index ->
                extraktor.getTrackFormat(index).getString(MediaFormat.KEY_MIME)?.startsWith("audio/") == true
            } ?: throw IllegalArgumentException("Keine Audiospur in ${datei.name}")
            val format = extraktor.getTrackFormat(spur)
            extraktor.selectTrack(spur)

            val mime = format.getString(MediaFormat.KEY_MIME)
                ?: throw IllegalArgumentException("Kein MIME-Typ in ${datei.name}")
            codec = MediaCodec.createDecoderByType(mime)
            codec.configure(format, null, null, 0)
            codec.start()

            var kanaele = format.getInteger(MediaFormat.KEY_CHANNEL_COUNT)
            var rate = format.getInteger(MediaFormat.KEY_SAMPLE_RATE)
            var floatPcm = lesePcmFloat(format)

            val sammler = FloatSammler()
            val info = MediaCodec.BufferInfo()
            var eingabeFertig = false
            var ausgabeFertig = false

            while (!ausgabeFertig) {
                if (!eingabeFertig) {
                    val eingabeIndex = codec.dequeueInputBuffer(TIMEOUT_US)
                    if (eingabeIndex >= 0) {
                        val puffer = codec.getInputBuffer(eingabeIndex)
                            ?: throw IllegalStateException("Kein Eingabepuffer")
                        val groesse = extraktor.readSampleData(puffer, 0)
                        if (groesse < 0) {
                            codec.queueInputBuffer(eingabeIndex, 0, 0, 0, MediaCodec.BUFFER_FLAG_END_OF_STREAM)
                            eingabeFertig = true
                        } else {
                            codec.queueInputBuffer(eingabeIndex, 0, groesse, extraktor.sampleTime, 0)
                            extraktor.advance()
                        }
                    }
                }

                when (val ausgabeIndex = codec.dequeueOutputBuffer(info, TIMEOUT_US)) {
                    MediaCodec.INFO_OUTPUT_FORMAT_CHANGED -> {
                        val neu = codec.outputFormat
                        kanaele = neu.getInteger(MediaFormat.KEY_CHANNEL_COUNT)
                        rate = neu.getInteger(MediaFormat.KEY_SAMPLE_RATE)
                        floatPcm = lesePcmFloat(neu)
                    }
                    MediaCodec.INFO_TRY_AGAIN_LATER -> Unit
                    else -> if (ausgabeIndex >= 0) {
                        if (info.size > 0) {
                            val puffer = codec.getOutputBuffer(ausgabeIndex)
                            if (puffer != null) {
                                val bytes = ByteArray(info.size)
                                puffer.position(info.offset)
                                puffer.limit(info.offset + info.size)
                                puffer.get(bytes)
                                sammler.hinzu(
                                    if (floatPcm) AudioKonverter.pcmFloatZuFloat(bytes)
                                    else AudioKonverter.pcm16ZuFloat(bytes),
                                )
                            }
                        }
                        codec.releaseOutputBuffer(ausgabeIndex, false)
                        if (info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0) ausgabeFertig = true
                    }
                }
            }

            val roh = sammler.zusammen()
            val stereo = AudioKonverter.aufStereo(roh, kanaele)
            val gewandelt = AudioKonverter.resampleLinear(stereo, 2, rate, zielRate)
            if (gainDb != 0.0) {
                val faktor = 10.0.pow(gainDb / 20.0).toFloat()
                for (i in gewandelt.indices) gewandelt[i] *= faktor
            }

            val ziel = cache.anlegen(trackId, 0, gewandelt.size / 2, zielRate)
            var von = 0
            while (von < gewandelt.size) {
                val bis = minOf(von + BLOCK_FRAMES * 2, gewandelt.size)
                ziel.schreibeBlock(gewandelt.copyOfRange(von, bis), 2)
                von = bis
            }
            ziel.close()
            return Ergebnis(ziel, gewandelt.size / 2, zielRate)
        } finally {
            try {
                codec?.stop()
            } catch (_: Exception) {
                // Codec war nicht gestartet oder schon gestoppt.
            }
            codec?.release()
            extraktor.release()
        }
    }

    private fun lesePcmFloat(format: MediaFormat): Boolean {
        if (!format.containsKey(MediaFormat.KEY_PCM_ENCODING)) return false
        return format.getInteger(MediaFormat.KEY_PCM_ENCODING) == AudioFormat.ENCODING_PCM_FLOAT
    }

    /** Wachsendes float-Array ohne O(n²): Kapazität verdoppeln. */
    private class FloatSammler {
        private var daten = FloatArray(1 shl 16)
        private var laenge = 0

        fun hinzu(teil: FloatArray) {
            if (laenge + teil.size > daten.size) {
                var neu = daten.size
                while (neu < laenge + teil.size) neu *= 2
                daten = daten.copyOf(neu)
            }
            teil.copyInto(daten, laenge)
            laenge += teil.size
        }

        fun zusammen(): FloatArray = daten.copyOf(laenge)
    }

    private companion object {
        const val TIMEOUT_US = 10_000L
        const val BLOCK_FRAMES = 44100
    }
}
