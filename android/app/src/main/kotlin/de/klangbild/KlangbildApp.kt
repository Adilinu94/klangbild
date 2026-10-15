package de.klangbild

import android.app.Application

/**
 * Anwendungskern. Hält den Motor und die Diagnose (BAUPLAN §6.4, §12.5).
 *
 * Bis M4 bewusst klein: die Engine startet mit dem ersten [de.klangbild.playback]
 * (T4.1), die Absturzdatei kommt in T12.5.
 */
class KlangbildApp : Application()
