package de.klangbild.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

/**
 * Farb- und Schrift-Tokens nach `ui/DIRECTION.md` (Nothing-Richtung, Rev. 2):
 * schwarzes Panel, weisse Daten, ein Rot fuer den Auto-DJ. Doto/Space kommen als
 * Dateien spaeter; bis dahin traegt die System-Monospace alle Daten und Labels.
 */
object Kb {
    val Schwarz = Color(0xFF000000)
    val Flaeche = Color(0xFF111111)
    val FlaecheHoch = Color(0xFF1A1A1A)
    val Weiss = Color(0xFFFFFFFF)
    val TextHell = Color(0xFFE8E8E8)
    val TextMittel = Color(0xFF999999)
    val TextDunkel = Color(0xFF666666)
    val Rot = Color(0xFFD71921)
    val Gruen = Color(0xFF4A9E5C)
    val Gelb = Color(0xFFD4A843)
    val Raster = Color(0xFF333333)
}

private val Schema = darkColorScheme(
    primary = Kb.Rot,
    onPrimary = Kb.Weiss,
    background = Kb.Schwarz,
    onBackground = Kb.TextHell,
    surface = Kb.Flaeche,
    onSurface = Kb.TextHell,
    surfaceVariant = Kb.FlaecheHoch,
    onSurfaceVariant = Kb.TextMittel,
)

@Composable
fun KlangbildThema(inhalt: @Composable () -> Unit) {
    MaterialTheme(colorScheme = Schema, content = inhalt)
}
