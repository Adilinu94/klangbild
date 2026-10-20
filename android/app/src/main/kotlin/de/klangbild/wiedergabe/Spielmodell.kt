package de.klangbild.wiedergabe

import android.app.Application
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import de.klangbild.bibliothek.Titel
import de.klangbild.core.Abtastung
import de.klangbild.core.Einstellungen
import de.klangbild.core.Lautheit
import de.klangbild.core.PcmCache
import de.klangbild.core.PcmDatei
import de.klangbild.core.Profil
import de.klangbild.core.ProfilBau
import de.klangbild.core.RegiePlanung
import de.klangbild.core.Taktraster
import de.klangbild.core.TitelAnalyse
import de.klangbild.core.TonartSchaetzung
import de.klangbild.engine.AutoDjPlayer
import de.klangbild.engine.BeatThis
import de.klangbild.engine.Player
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import kotlin.math.roundToInt

/**
 * Bruecke zwischen Oberflaeche und Engine (M9): haelt den Player, den Auto-DJ und den
 * zuletzt gelesenen Zustand. Dekodieren und Datei-I/O laufen auf [Dispatchers.Default],
 * der Zustand wird viermal pro Sekunde aus `poll` gelesen (BAUPLAN §5.4).
 */
class Spielmodell(app: Application) : AndroidViewModel(app) {

    private val cache = PcmCache(File(app.filesDir, "pcm"))
    private val analysen = AnalyseSpeicher(File(app.filesDir, "analyse"))
    private val player = Player(cache)
    val autoDj = AutoDjPlayer(player, cache)

    var zustand by mutableStateOf(Player.Zustand(0, 0, 0, false, 0))
        private set
    var titel by mutableStateOf<Titel?>(null)
        private set
    var laedt by mutableStateOf(false)
        private set
    var fehler by mutableStateOf<String?>(null)
        private set

    /** 64 RMS-Segmente des laufenden Titels (0..1), sobald der Cache vollstaendig ist. */
    var wellenform by mutableStateOf<FloatArray?>(null)
        private set

    /** Tonart und Lautheit des laufenden Titels; null, solange keine Analyse vorliegt. */
    var analyse by mutableStateOf<TitelAnalyse?>(null)
        private set

    /** Profil des laufenden Titels fuer die Regie (aus [analyse]); null ohne Takte. */
    var profil by mutableStateOf<Profil?>(null)
        private set

    /** Zuletzt geplanter Uebergang (Konsole zeigt ihn an, Start erfolgt getrennt). */
    data class Uebergang(val plan: RegiePlanung.Plan, val ziel: Titel, val punkte: Double)

    var uebergang by mutableStateOf<Uebergang?>(null)
        private set

    private var liste: List<Titel> = emptyList()
    private var index = -1
    private var amEnde = false

    init {
        viewModelScope.launch {
            while (true) {
                zustand = player.zustand()
                pruefeEnde()
                delay(250)
            }
        }
    }

    /** Am Titelende automatisch den naechsten der Liste starten (fortlaufende Wiedergabe). */
    private fun pruefeEnde() {
        val dauer = zustand.dauer
        if (dauer <= 0 || !zustand.laeuft || laedt) return
        if (zustand.position < dauer - 44100) {
            amEnde = false
            return
        }
        if (amEnde) return
        amEnde = true
        naechster()
    }

    fun naechster() {
        if (liste.isEmpty()) return
        index = (index + 1) % liste.size
        spiele(liste[index])
    }

    fun vorheriger() {
        if (liste.isEmpty()) return
        index = (index - 1 + liste.size) % liste.size
        spiele(liste[index])
    }

    fun spiele(t: Titel, alle: List<Titel> = emptyList()) {
        if (laedt) return
        if (alle.isNotEmpty()) {
            liste = alle
            index = alle.indexOf(t)
        }
        amEnde = false
        laedt = true
        fehler = null
        titel = t
        wellenform = null
        analyse = analysen.lade(t.id)
        profil = analyse?.zuProfil()
        zustand = Player.Zustand(0, 0, 0, false, 0)
        viewModelScope.launch {
            val ok = try {
                withContext(Dispatchers.Default) {
                    player.spiele(File(t.pfad), t.id)
                }
            } catch (fehler: Throwable) {
                this@Spielmodell.fehler = "Wiedergabe fehlgeschlagen: ${fehler.message}"
                false
            }
            if (ok) {
                zustand = player.zustand()
                wellenform = withContext(Dispatchers.Default) { forme(t.id) }
                if (analyse == null || analyse?.beats.isNullOrEmpty() ||
                    analyse?.downbeats.isNullOrEmpty() || analyse?.raster.isNullOrEmpty() ||
                    analyse?.takte.isNullOrEmpty()
                ) {
                    val gefunden = analysiere(t)
                    if (titel?.id == t.id && gefunden != null) {
                        analyse = gefunden
                        profil = gefunden.zuProfil()
                    }
                }
            } else if (this@Spielmodell.fehler == null) {
                this@Spielmodell.fehler = "Titel laesst sich nicht oeffnen"
            }
            laedt = false
        }
    }

    /**
     * Rechnet Tonart, Lautheit, Beats, Raster und Profil eines Titels aus dem PCM-Cache
     * und legt das Ergebnis ab. Null, wenn kein Cache vorliegt (Titel nie gespielt).
     */
    suspend fun analysiere(t: Titel): TitelAnalyse? = withContext(Dispatchers.Default) {
        val datei = cache.finde(t.id.toInt()) ?: return@withContext null
        val ergebnis = PcmDatei.oeffnen(datei)?.use { pcm ->
            val tonart = TonartSchaetzung.schaetzen(TonartSchaetzung.chromaAusCache(pcm))
            val lufs = Lautheit.ausCache(pcm)
            val schlaege = BeatThis.holen(getApplication()).analysiere(Abtastung.mono22050(pcm))
            val abstaende = schlaege.beats.toList().zipWithNext { a, b -> b - a }.sorted()
            val mittel = abstaende.getOrNull(abstaende.size / 2)
            val bpm = if (mittel != null && mittel > 0.25f) (60f / mittel).roundToInt() else null
            val raster = if (bpm != null) {
                Taktraster.taktraster(
                    schlaege.downbeats.map { it.toDouble() },
                    bpm.toDouble(),
                    pcm.frames().toDouble() / 44100.0,
                ).map { it.toFloat() }
            } else {
                emptyList()
            }
            // Ganze Spur nur bei kurzen Titeln in den Speicher (Stereo float).
            val profil = if (bpm != null && pcm.frames() <= 15_000_000) {
                ProfilBau.profil(
                    pcm.lese(0, pcm.frames()),
                    schlaege.downbeats.map { it.toDouble() },
                    bpm.toDouble(),
                )
            } else {
                null
            }
            TitelAnalyse(
                tonart.name,
                tonart.camelot,
                lufs.takeIf { it.isFinite() },
                bpm,
                schlaege.beats.toList(),
                schlaege.downbeats.toList(),
                raster,
                profil?.takte?.map { it.toFloat() } ?: emptyList(),
                profil?.gesamt?.map { it.toFloat() } ?: emptyList(),
                profil?.baender?.map { reihe -> reihe.map { it.toFloat() } } ?: emptyList(),
                profil?.chroma?.map { reihe -> reihe.map { it.toFloat() } } ?: emptyList(),
            )
        }
        if (ergebnis != null) analysen.sichere(t.id, ergebnis)
        ergebnis
    }

    /**
     * Plant die Ueberblendung vom laufenden Titel auf [naechster]: bewertet alle Takte des
     * Zieltitels gegen den naechsten Takt des laufenden Titels, in Laengen von 8 und 16 Takten.
     * Das Zielprofil wird bei Bedarf frisch gerechnet (Titel muss im Cache liegen).
     */
    suspend fun plane(naechster: Titel): Uebergang? = withContext(Dispatchers.Default) {
        val a = analyse ?: return@withContext null
        val pa = profil ?: return@withContext null
        val analyseB = analysen.lade(naechster.id) ?: analysiere(naechster) ?: return@withContext null
        val pb = analyseB.zuProfil() ?: return@withContext null
        val e = Einstellungen()

        val tonartOk = a.camelot == analyseB.camelot ||
            a.camelot in TonartSchaetzung.camelotNachbarn(analyseB.camelot)
        val jetztS = zustand.position.toDouble() / 44100.0
        val i = pa.takte.indexOfLast { it <= jetztS }.coerceAtLeast(0).coerceAtMost(maxOf(0, pa.n - 2))

        var bester: Uebergang? = null
        for (laenge in intArrayOf(8, 16)) {
            if (i + laenge > pa.n) continue
            for (j in 0..maxOf(0, pb.n - laenge)) {
                val (punkte, teile, _) = RegiePlanung.bewerten(
                    pa, pb, i, j, laenge, e, tonartOk = tonartOk,
                )
                if (bester == null || punkte > bester.punkte) {
                    val plan = RegiePlanung.Plan(
                        ausS = pa.takte[i],
                        einS = pb.takte[j],
                        takte = laenge,
                        einst = e,
                        rezept = "blende",
                        grund = teile.joinToString(" "),
                        punkte = punkte,
                    )
                    bester = Uebergang(plan, naechster, punkte)
                }
            }
        }
        bester?.also { uebergang = it }
    }

    fun verwerfeUebergang() {
        uebergang = null
    }

    /** Plant den Uebergang auf den naechsten Titel der aktuellen Liste. */
    fun planeNaechsten() {
        if (liste.isEmpty() || index < 0) return
        val ziel = liste[(index + 1) % liste.size]
        if (ziel.id == titel?.id) return
        viewModelScope.launch { plane(ziel) }
    }

    /** RMS-Kurve aus dem PCM-Cache (64 Segmente, auf das Maximum normiert). */
    private fun forme(trackId: Long, anzahl: Int = 64): FloatArray? {
        val datei = cache.finde(trackId.toInt()) ?: return null
        val pcm = de.klangbild.core.PcmDatei.oeffnen(datei) ?: return null
        return pcm.use {
            val frames = it.frames()
            if (frames <= 0) return@use null
            val proTeil = (frames / anzahl).coerceAtLeast(1)
            val werte = FloatArray(anzahl)
            var maximum = 1e-6f
            for (i in 0 until anzahl) {
                val teil = it.lese(i * proTeil, proTeil)
                var summe = 0.0
                for (wert in teil) summe += wert * wert
                val rms = kotlin.math.sqrt(summe / teil.size.coerceAtLeast(1)).toFloat()
                werte[i] = rms
                if (rms > maximum) maximum = rms
            }
            for (i in werte.indices) werte[i] = (werte[i] / maximum).coerceIn(0f, 1f)
            werte
        }
    }

    fun pause() = player.pause()

    fun weiter() = player.weiter()

    fun stoppe() {
        player.stoppe()
        zustand = Player.Zustand(0, 0, 0, false, 0)
    }

    /** Springt an die Stelle [anteil] (0..1) des laufenden Titels. */
    fun springeZu(anteil: Float) {
        val dauer = if (zustand.dauer > 0) {
            zustand.dauer
        } else {
            (titel?.dauerMs ?: 0L) * 44100L / 1000L
        }
        if (dauer <= 0) return
        player.springeZu((dauer * anteil.coerceIn(0f, 1f)).toLong())
    }

    /** Position und Dauer in Sekunden; vor dem ersten Block zaehlt die MediaStore-Dauer. */
    fun zeit(): Pair<Long, Long> {
        val dauer = if (zustand.dauer > 0) zustand.dauer / 44100L else (titel?.dauerMs ?: 0L) / 1000L
        return zustand.position / 44100L to dauer
    }
}
