package de.klangbild.wiedergabe

import android.app.Application
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import de.klangbild.bibliothek.Titel
import de.klangbild.core.PcmCache
import de.klangbild.engine.AutoDjPlayer
import de.klangbild.engine.Player
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

/**
 * Bruecke zwischen Oberflaeche und Engine (M9): haelt den Player, den Auto-DJ und den
 * zuletzt gelesenen Zustand. Dekodieren und Datei-I/O laufen auf [Dispatchers.Default],
 * der Zustand wird viermal pro Sekunde aus `poll` gelesen (BAUPLAN §5.4).
 */
class Spielmodell(app: Application) : AndroidViewModel(app) {

    private val cache = PcmCache(File(app.filesDir, "pcm"))
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

    init {
        viewModelScope.launch {
            while (true) {
                zustand = player.zustand()
                delay(250)
            }
        }
    }

    fun spiele(t: Titel) {
        if (laedt) return
        laedt = true
        fehler = null
        titel = t
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
            } else if (this@Spielmodell.fehler == null) {
                this@Spielmodell.fehler = "Titel laesst sich nicht oeffnen"
            }
            laedt = false
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
