package de.klangbild

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.lifecycle.viewmodel.compose.viewModel
import de.klangbild.bibliothek.Bibliothek
import de.klangbild.bibliothek.Titel
import de.klangbild.ui.BibliothekBildschirm
import de.klangbild.ui.Kb
import de.klangbild.ui.KlangbildThema
import de.klangbild.ui.PlayerBildschirm
import de.klangbild.wiedergabe.Spielmodell
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Einzige Activity der App (M9): Bibliothek und Player, dazwischen nur ein Zustand
 * (`offen`). Der Motor liegt im [Spielmodell]; die Activity haelt nichts davon.
 */
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        setContent { KlangbildThema { Oberflaeche() } }
    }
}

private fun erlaubnis(): String =
    if (Build.VERSION.SDK_INT >= 33) Manifest.permission.READ_MEDIA_AUDIO
    else Manifest.permission.READ_EXTERNAL_STORAGE

private fun hatErlaubnis(context: Context): Boolean =
    ContextCompat.checkSelfPermission(context, erlaubnis()) == PackageManager.PERMISSION_GRANTED

@Composable
private fun Oberflaeche() {
    val context = LocalContext.current
    val modell: Spielmodell = viewModel()
    var erlaubt by remember { mutableStateOf(hatErlaubnis(context)) }
    var titel by remember { mutableStateOf(emptyList<Titel>()) }
    var offen by remember { mutableStateOf(false) }

    val frager = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { erlaubt = it }
    LaunchedEffect(erlaubt) {
        if (erlaubt) titel = withContext(Dispatchers.IO) { Bibliothek.lesen(context) }
    }

    when {
        !erlaubt -> ZugriffBildschirm { frager.launch(erlaubnis()) }
        offen -> PlayerBildschirm(modell) { offen = false }
        else -> BibliothekBildschirm(titel, modell, onOeffnen = { t ->
            modell.spiele(t)
            offen = true
        })
    }
}

@Composable
private fun ZugriffBildschirm(onFragen: () -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Kb.Schwarz)
            .systemBarsPadding()
            .padding(24.dp),
        verticalArrangement = Arrangement.Center,
    ) {
        Text("KLINGBILD", fontFamily = FontFamily.Monospace, fontSize = 32.sp, color = Kb.Weiss)
        Spacer(Modifier.height(12.dp))
        Text(
            text = "Die Bibliothek liest nur Dateien auf diesem Geraet.",
            fontFamily = FontFamily.Monospace,
            fontSize = 12.sp,
            color = Kb.TextMittel,
        )
        Spacer(Modifier.height(20.dp))
        Button(onClick = onFragen) {
            Text("MUSIK-ZUGRIFF", fontFamily = FontFamily.Monospace)
        }
    }
}
