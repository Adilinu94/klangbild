package de.klangbild

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

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
            }
        }
    }
}
