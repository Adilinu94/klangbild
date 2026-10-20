package de.klangbild.ui

import android.content.ContentUris
import android.content.Context
import android.graphics.Bitmap
import android.provider.MediaStore
import android.util.LruCache
import android.util.Size
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import de.klangbild.bibliothek.Titel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import java.util.Locale

/**
 * Cover aus den Tags der Datei (MediaStore-Thumbnail, API 29+). Ein LruCache haelt die
 * Bitmaps je Album, damit die Liste beim Scrollen nicht neu dekodiert.
 */
object Cover {

    private val cache = LruCache<Long, Bitmap>(64)

    suspend fun laden(context: Context, titelId: Long, albumId: Long): Bitmap? = withContext(Dispatchers.IO) {
        cache.get(albumId)?.let { return@withContext it }
        val bild = try {
            val uri = ContentUris.withAppendedId(MediaStore.Audio.Media.EXTERNAL_CONTENT_URI, titelId)
            context.contentResolver.loadThumbnail(uri, Size(256, 256), null)
        } catch (_: Exception) {
            null
        }
        if (bild != null) cache.put(albumId, bild)
        bild
    }
}

/** Quadratisches Cover; ohne Bild der Anfangsbuchstabe in Doto-Manier (Monospace). */
@Composable
fun CoverBild(t: Titel, groesse: Dp, modifier: Modifier = Modifier, rund: Boolean = false) {
    val context = LocalContext.current
    var bild by remember(t.id) { mutableStateOf<Bitmap?>(null) }
    LaunchedEffect(t.id) { bild = Cover.laden(context, t.id, t.albumId) }

    val form = if (rund) CircleShape else RoundedCornerShape(4.dp)
    Box(
        modifier = modifier
            .size(groesse)
            .clip(form)
            .background(Kb.FlaecheHoch),
        contentAlignment = Alignment.Center,
    ) {
        val geladen = bild
        if (geladen != null) {
            Image(
                bitmap = geladen.asImageBitmap(),
                contentDescription = t.titel,
                modifier = Modifier.fillMaxSize(),
                contentScale = ContentScale.Crop,
            )
        } else {
            Text(
                text = t.titel.take(1).uppercase(Locale.getDefault()),
                fontFamily = FontFamily.Monospace,
                fontSize = (groesse.value * 0.42f).sp,
                color = Kb.TextMittel,
            )
        }
    }
}

/**
 * Runde Scheibe fuer den Player (Rev. 2, Vinyl-Metapher): dreht langsam bei Wiedergabe.
 * Der Winkel laeuft nur im Grafikebenen-Block, also ohne Neuzeichnen der Inhalte.
 */
@Composable
fun CoverScheibe(t: Titel, laeuft: Boolean, groesse: Dp = 230.dp) {
    val context = LocalContext.current
    var bild by remember(t.id) { mutableStateOf<Bitmap?>(null) }
    LaunchedEffect(t.id) { bild = Cover.laden(context, t.id, t.albumId) }

    var winkel by remember { mutableFloatStateOf(0f) }
    LaunchedEffect(laeuft) {
        while (laeuft) {
            delay(16)
            winkel = (winkel + 0.25f) % 360f
        }
    }

    Box(
        modifier = Modifier
            .size(groesse)
            .graphicsLayer { rotationZ = winkel }
            .clip(CircleShape)
            .background(Kb.FlaecheHoch),
        contentAlignment = Alignment.Center,
    ) {
        val geladen = bild
        if (geladen != null) {
            Image(
                bitmap = geladen.asImageBitmap(),
                contentDescription = t.titel,
                modifier = Modifier.fillMaxSize(),
                contentScale = ContentScale.Crop,
            )
        } else {
            Text(
                text = t.titel.take(1).uppercase(Locale.getDefault()),
                fontFamily = FontFamily.Monospace,
                fontSize = (groesse.value * 0.3f).sp,
                color = Kb.TextMittel,
            )
        }
        Box(Modifier.size(groesse * 0.18f).background(Kb.Schwarz, CircleShape))
        Box(Modifier.size(groesse * 0.03f).background(Kb.Weiss, CircleShape))
    }
}
