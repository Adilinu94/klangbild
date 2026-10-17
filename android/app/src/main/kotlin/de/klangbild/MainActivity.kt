package de.klangbild

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import de.klangbild.engine.NativeEngine
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Einzige Activity der App (M0: leeres Gerüst).
 *
 * Die Oberfläche kommt mit M9 (T9.1 ff., Screen 01–09 nach
 * `ui/mockups/klangbild.html`). Bis dahin zeigt sie nur den Gerüst-Status,
 * damit der Build prüfbar ist.
 */
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        setContent { KlangbildGeruest() }
    }
}

@Composable
private fun KlangbildGeruest() {
    MaterialTheme {
        Scaffold { innen ->
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(innen)
                    .padding(24.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text(
                    text = "KLINGBILD",
                    fontSize = 40.sp,
                    fontFamily = FontFamily.Monospace,
                )
                Text(
                    text = "GERUEST · M0",
                    fontSize = 14.sp,
                    fontFamily = FontFamily.Monospace,
                )
                Text(
                    text = "Modul :app läuft. :core und :engine sind gebaut, " +
                        "die Motor-Oberfläche folgt ab M9.",
                    fontSize = 12.sp,
                    fontFamily = FontFamily.Default,
                )
                EngineDiagnose()
            }
        }
    }
}

/**
 * Diagnose für den Engine-Spike (M1, T1.4): Stream starten, Sinus spielen oder pausieren und
 * die Zähler aus `NativeEngine.poll` zeigen. Wird mit M9 durch die echte Oberfläche ersetzt.
 */
@Composable
private fun EngineDiagnose() {
    val scope = rememberCoroutineScope()
    var running by remember { mutableStateOf(false) }
    var playing by remember { mutableStateOf(false) }
    var status by remember { mutableStateOf("Stream aus") }
    var text by remember { mutableStateOf("") }

    // 10-mal pro Sekunde lesen (kein JNI je Frame, BAUPLAN §5.4).
    LaunchedEffect(running) {
        val werte = LongArray(NativeEngine.POLL_SIZE)
        while (running) {
            NativeEngine.poll(werte)
            val frames = werte[NativeEngine.POLL_HEARD_FRAME]
            text = "Frames ${frames}  (${frames / 44100} s)\n" +
                "Underflows ${werte[NativeEngine.POLL_UNDERFLOWS]}\n" +
                "Spielt ${if (werte[NativeEngine.POLL_PLAYING] == 1L) "ja" else "nein"}"
            delay(100)
        }
    }

    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Button(
            onClick = {
                scope.launch {
                    if (!running) {
                        val ok = withContext(Dispatchers.Default) { NativeEngine.start() }
                        running = ok
                        status = if (ok) "Stream läuft" else "Stream ließ sich nicht öffnen"
                    } else {
                        withContext(Dispatchers.Default) { NativeEngine.stop() }
                        running = false
                        playing = false
                        status = "Stream aus"
                    }
                }
            },
        ) { Text(if (running) "STOP" else "START") }
        Button(
            enabled = running,
            onClick = {
                playing = !playing
                NativeEngine.setPlaying(playing)
            },
        ) { Text(if (playing) "PAUSE" else "SPIELEN") }
    }
    Text(text = status, fontSize = 12.sp, fontFamily = FontFamily.Monospace)
    if (running) Text(text = text, fontSize = 14.sp, fontFamily = FontFamily.Monospace)
}
