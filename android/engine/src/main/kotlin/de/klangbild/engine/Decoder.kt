package de.klangbild.engine

import android.media.AudioFormat
import android.media.MediaCodec
import android.media.MediaExtractor
import android.media.MediaFormat
import de.klangbild.core.AudioKonverter
import de.klangbild.core.PcmCache
import de.klangbild.core.PcmDatei
import java.io.File
import kotlin.math.min
import kotlin.math.pow

/**
 * Dekodiert eine Audiodatei nach Stereo/44,1 kHz und legt sie im PCM-Cache ab (BAUPLAN §4.3).
 *
 * Ablauf: MediaExtractor → MediaCodec → float je Kanal → Stereo → lineares Resampling →
 * `gain_db` → PCM-Cache. Geschrieben wird **fortschreitend** in 1-s-Blöcken; der Speicher
 * bleibt dadurch klein (vorher sammelte der Decoder den ganzen Titel und lief bei langen
 * Stücken in einen OutOfMemoryError). [beiBlock] meldet nach jedem Block die Gesamtzahl der
 * Frames, damit der Player schon nach der ersten Sekunde starten kann.
 *
 * Blockiert (CPU und I/O): im Planer-Thread aufrufen, nie im UI- oder Audio-Thread.
 */
class Decoder(private val zielRate: Int = 44100) {

    data class Ergebnis(val frames: Int, val rate: Int)

    fun dekodiere(
        datei: File,
        cache: PcmCache,
        trackId: Int,
        gainDb: Double = 0.0,
        beiBlock: ((Int) -> Unit)? = null,
    ): Ergebnis {
        val extraktor = MediaExtractor()
        var codec: MediaCodec? = null
        var ziel: PcmDatei? = null
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

            cache.loesche(trackId)
            val dateiZiel = cache.anlegen(trackId, 0, 0, zielRate)
            ziel = dateiZiel

            var kanaele = format.getInteger(MediaFormat.KEY_CHANNEL_COUNT)
            var rate = format.getInteger(MediaFormat.KEY_SAMPLE_RATE)
            var floatPcm = lesePcmFloat(format)
            val gain = if (gainDb != 0.0) 10.0.pow(gainDb / 20.0).toFloat() else 1f

            var strom: Strom? = null
            var gesamt = 0
            val sammler = FloatSammler(BLOCK_FRAMES * 4)

            fun schreibe() {
                val roh = sammler.nehmen() ?: return
                val stereo = AudioKonverter.aufStereo(roh, kanaele)
                val wandler = strom ?: Strom(rate, zielRate, gain).also { strom = it }
                val gewandelt = wandler.wandle(stereo)
                if (gewandelt.isEmpty()) return
                dateiZiel.schreibeBlock(gewandelt, 2)
                gesamt += gewandelt.size / 2
                beiBlock?.invoke(gesamt)
            }

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
                        schreibe()
                        strom = null
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
                                if (sammler.frames(kanaele) >= BLOCK_FRAMES) schreibe()
                            }
                        }
                        codec.releaseOutputBuffer(ausgabeIndex, false)
                        if (info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0) ausgabeFertig = true
                    }
                }
            }

            schreibe()
            strom?.let { rest ->
                val letzte = rest.rest()
                if (letzte.isNotEmpty()) {
                    dateiZiel.schreibeBlock(letzte, 2)
                    gesamt += letzte.size / 2
                }
            }
            dateiZiel.close()
            ziel = null
            return Ergebnis(gesamt, zielRate)
        } finally {
            try {
                ziel?.close()
            } catch (_: Exception) {
                // Datei war schon geschlossen.
            }
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

    /** Wachsender float-Puffer; wird bei rund einer Sekunde geleert, also klein gehalten. */
    private class FloatSammler(kapazitaet: Int) {
        private var daten = FloatArray(kapazitaet)
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

        fun frames(kanaele: Int): Int = laenge / kanaele

        fun nehmen(): FloatArray? {
            if (laenge == 0) return null
            val aus = daten.copyOf(laenge)
            laenge = 0
            return aus
        }
    }

    /**
     * Lineares Resampling ueber Blockgrenzen (ADR-014): behaelt einen Frame Ueberhang und die
     * Bruchposition, sonst gäbe es an jeder Blockgrenze einen Sprung.
     */
    private class Strom(private val von: Int, private val nach: Int, private val gain: Float) {
        private val schritt = von.toDouble() / nach
        private var position = 0.0
        private var ueberhang = FloatArray(0)

        fun wandle(eingang: FloatArray): FloatArray {
            if (von == nach) {
                if (gain == 1f) return eingang
                val aus = eingang.copyOf()
                for (i in aus.indices) aus[i] *= gain
                return aus
            }
            val daten = if (ueberhang.isEmpty()) eingang else ueberhang + eingang
            val frames = daten.size / 2
            val aus = FloatArray((frames / schritt).toInt() * 2 + 2)
            var n = 0
            var p = position
            while (true) {
                val i = p.toInt()
                if (i >= frames - 1) break
                val f = (p - i).toFloat()
                val a0 = daten[i * 2]
                val a1 = daten[i * 2 + 1]
                val b0 = daten[(i + 1) * 2]
                val b1 = daten[(i + 1) * 2 + 1]
                aus[n++] = (a0 + (b0 - a0) * f) * gain
                aus[n++] = (a1 + (b1 - a1) * f) * gain
                p += schritt
            }
            val verbraucht = min(p.toInt(), frames - 1)
            ueberhang = daten.copyOfRange(verbraucht * 2, daten.size)
            position = p - verbraucht
            return aus.copyOf(n)
        }

        /** Letzten Ueberhang ausgeben, damit das Ende nicht fehlt. */
        fun rest(): FloatArray {
            if (ueberhang.isEmpty()) return FloatArray(0)
            val aus = ueberhang.copyOf()
            for (i in aus.indices) aus[i] *= gain
            ueberhang = FloatArray(0)
            return aus
        }
    }

    private companion object {
        const val TIMEOUT_US = 10_000L
        const val BLOCK_FRAMES = 44100
    }
}
