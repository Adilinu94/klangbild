package de.klangbild.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import de.klangbild.bibliothek.Titel
import de.klangbild.wiedergabe.Spielmodell
import java.util.Locale

private val MONO = FontFamily.Monospace

private fun zeitText(sekunden: Long): String =
    String.format(Locale.US, "%d:%02d", sekunden / 60, sekunden % 60)

/**
 * Bibliothek als Flughafentafel (T9.2): Nummer, Titel, Interpret, Dauer. Ein Tipp startet
 * den Titel und oeffnet den Player. Der Mini-Player sitzt ueber dem unteren Rand.
 */
@Composable
fun BibliothekBildschirm(
    titel: List<Titel>,
    modell: Spielmodell,
    onOeffnen: (Titel) -> Unit,
) {
    var suche by remember { mutableStateOf("") }
    val gefiltert = remember(titel, suche) {
        if (suche.isBlank()) titel
        else titel.filter {
            it.titel.contains(suche, ignoreCase = true) || it.kuenstler.contains(suche, ignoreCase = true)
        }
    }
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Kb.Schwarz)
            .systemBarsPadding(),
    ) {
        Column(modifier = Modifier.padding(horizontal = 20.dp, vertical = 12.dp)) {
            Text("KLINGBILD", fontFamily = MONO, fontSize = 28.sp, color = Kb.Weiss)
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("ALLE TITEL", fontFamily = MONO, fontSize = 11.sp, color = Kb.TextMittel)
                Text(
                    text = String.format(Locale.US, "%d", gefiltert.size),
                    fontFamily = MONO,
                    fontSize = 11.sp,
                    color = Kb.TextMittel,
                )
            }
            BasicTextField(
                value = suche,
                onValueChange = { suche = it },
                singleLine = true,
                textStyle = TextStyle(color = Kb.TextHell, fontFamily = MONO, fontSize = 14.sp),
                cursorBrush = SolidColor(Kb.Rot),
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 12.dp),
                decorationBox = { innen ->
                    if (suche.isEmpty()) {
                        Text("SUCHE", fontFamily = MONO, fontSize = 12.sp, color = Kb.TextDunkel)
                    }
                    innen()
                },
            )
        }
        Kopfzeile()
        LazyColumn(modifier = Modifier.weight(1f)) {
            itemsIndexed(gefiltert) { index, t ->
                Zeile(index + 1, t) { onOeffnen(t) }
            }
        }
        modell.fehler?.let {
            Text(it, modifier = Modifier.padding(20.dp), fontFamily = MONO, fontSize = 12.sp, color = Kb.Rot)
        }
        MiniPlayer(modell, onOeffnen)
    }
}

@Composable
private fun Kopfzeile() {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 20.dp, vertical = 6.dp),
    ) {
        Text("NR", modifier = Modifier.width(44.dp), fontFamily = MONO, fontSize = 10.sp, color = Kb.TextDunkel)
        Text("TITEL", modifier = Modifier.weight(1f), fontFamily = MONO, fontSize = 10.sp, color = Kb.TextDunkel)
        Text("DAUER", fontFamily = MONO, fontSize = 10.sp, color = Kb.TextDunkel)
    }
    Box(modifier = Modifier.fillMaxWidth().height(1.dp).background(Kb.Raster))
}

@Composable
private fun Zeile(nummer: Int, t: Titel, onKlick: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onKlick)
            .padding(horizontal = 20.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = String.format(Locale.US, "%03d", nummer),
            modifier = Modifier.width(40.dp),
            fontFamily = MONO,
            fontSize = 12.sp,
            color = Kb.TextDunkel,
        )
        CoverBild(t, 40.dp, modifier = Modifier.padding(end = 12.dp))
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = t.titel,
                fontFamily = MONO,
                fontSize = 15.sp,
                color = Kb.TextHell,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                text = t.kuenstler,
                fontFamily = MONO,
                fontSize = 11.sp,
                color = Kb.TextMittel,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
        Text(t.dauerText, fontFamily = MONO, fontSize = 12.sp, color = Kb.TextMittel)
    }
    Box(modifier = Modifier.fillMaxWidth().height(1.dp).background(Kb.FlaecheHoch))
}

@Composable
private fun MiniPlayer(modell: Spielmodell, onOeffnen: (Titel) -> Unit) {
    val t = modell.titel ?: return
    val (position, dauer) = modell.zeit()
    val anteil = if (dauer > 0) (position.toFloat() / dauer).coerceIn(0f, 1f) else 0f

    Column(modifier = Modifier.fillMaxWidth().background(Kb.Flaeche)) {
        Box(modifier = Modifier.fillMaxWidth().height(2.dp).background(Kb.Raster)) {
            Box(modifier = Modifier.fillMaxWidth(anteil).height(2.dp).background(Kb.Rot))
        }
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .clickable { onOeffnen(t) }
                .padding(horizontal = 20.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            CoverBild(t, 36.dp, modifier = Modifier.padding(end = 12.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text(t.titel, fontFamily = MONO, fontSize = 13.sp, color = Kb.TextHell, maxLines = 1)
                Text(t.kuenstler, fontFamily = MONO, fontSize = 10.sp, color = Kb.TextMittel, maxLines = 1)
            }
            Knopf(
                text = if (modell.zustand.laeuft) "PAUSE" else "PLAY",
                breit = false,
            ) { if (modell.zustand.laeuft) modell.pause() else modell.weiter() }
        }
    }
}

/** Player (T9.2/T9.3a): Titel, Segment-Fortschritt, Zeiten, drei Befehle. */
@Composable
fun PlayerBildschirm(modell: Spielmodell, onZurueck: () -> Unit) {
    val t = modell.titel
    val (position, dauer) = modell.zeit()
    val anteil = if (dauer > 0) (position.toFloat() / dauer).coerceIn(0f, 1f) else 0f

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Kb.Schwarz)
            .systemBarsPadding()
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(20.dp),
    ) {
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(
                "ZURUECK",
                modifier = Modifier.clickable(onClick = onZurueck).padding(4.dp),
                fontFamily = MONO,
                fontSize = 12.sp,
                color = Kb.TextMittel,
            )
            Text(
                text = if (modell.laedt) "LAEDT" else "SPUR ${modell.zustand.spur}",
                fontFamily = MONO,
                fontSize = 12.sp,
                color = if (modell.laedt) Kb.Gelb else Kb.TextDunkel,
            )
        }

        Column(
            modifier = Modifier.weight(1f),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            if (t != null) {
                CoverScheibe(t, modell.zustand.laeuft)
                Spacer(Modifier.height(28.dp))
            }
            Text(
                text = (t?.titel ?: "KEIN TITEL").uppercase(),
                fontFamily = MONO,
                fontSize = 30.sp,
                color = Kb.Weiss,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            Spacer(Modifier.height(6.dp))
            Text(
                text = t?.kuenstler ?: "",
                fontFamily = MONO,
                fontSize = 13.sp,
                color = Kb.TextMittel,
            )
        }

        Segmente(anteil, onSeek = { modell.springeZu(it) })
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(zeitText(position), fontFamily = MONO, fontSize = 13.sp, color = Kb.TextHell)
            Text(zeitText(dauer), fontFamily = MONO, fontSize = 13.sp, color = Kb.TextMittel)
        }

        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Knopf(if (modell.zustand.laeuft) "PAUSE" else "PLAY") {
                if (modell.zustand.laeuft) modell.pause() else modell.weiter()
            }
            Knopf("STOPP") { modell.stoppe() }
        }
        Text(
            text = String.format(
                Locale.US,
                "POS %d · UNDERFLOWS %d",
                modell.zustand.position,
                modell.zustand.underflows,
            ),
            fontFamily = MONO,
            fontSize = 10.sp,
            color = Kb.TextDunkel,
        )
    }
}

/** Segmentierter Fortschritt (Rev. 2): gespielt weiss, offen dunkel, 48 Segmente. Tippen sucht. */
@Composable
private fun Segmente(anteil: Float, anzahl: Int = 48, onSeek: ((Float) -> Unit)? = null) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .height(28.dp)
            .then(
                if (onSeek != null) {
                    Modifier.pointerInput(Unit) {
                        detectTapGestures { stelle ->
                            onSeek((stelle.x / size.width).coerceIn(0f, 1f))
                        }
                    }
                } else {
                    Modifier
                },
            ),
        horizontalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        for (i in 0 until anzahl) {
            val an = i / (anzahl - 1f) <= anteil
            Box(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxHeight()
                    .background(if (an) Kb.Weiss else Kb.Raster),
            )
        }
    }
}

@Composable
private fun RowScope.Knopf(text: String, breit: Boolean = true, onKlick: () -> Unit) {
    Button(
        onClick = onKlick,
        modifier = if (breit) Modifier.weight(1f) else Modifier,
        shape = androidx.compose.foundation.shape.RoundedCornerShape(4.dp),
        colors = ButtonDefaults.buttonColors(
            containerColor = Kb.FlaecheHoch,
            contentColor = Kb.TextHell,
        ),
    ) {
        Text(text, fontFamily = MONO, fontSize = 13.sp)
    }
}
