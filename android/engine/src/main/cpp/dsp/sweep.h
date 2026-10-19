// Zeitvariabler DJ-Filter (Sweep) und Baender-Gewichtung (BAUPLAN-ANDROID T5.5).
//
// Port von uebergang._biquads, _sweep und _baender_gewichten. Der Sweep rechnet in double (scipy
// sosfilt mit float64-Koeffizienten und -Zustand) und rundet je Block auf float32, genau wie der
// Prototyp. Stereo, interleaved.
//
// Nur fuer Baker und Host-Test, nie im Audio-Callback.
#pragma once

#include <array>
#include <span>
#include <vector>

#include "dsp/filters.h"

namespace klangbild::dsp {

enum class SweepKind { Lowpass, Highpass };

/// 4-poliger Butterworth als 2 RBJ-Biquads je Block (`uebergang._biquads`): `fc` je Block in Hz.
/// `resonance`: zweite Stufe mit Q = 4 statt 1,3066 (Resonanzspitze, ca. +10 dB).
std::vector<std::array<Biquad, 2>> sweepBiquads(std::span<const double> fc, SweepKind kind, bool resonance);

/// `uebergang._sweep(x, menge, art, reso)`: `amount` je Frame, 0 = offen, 1 = zu (Tiefpass 200 Hz,
/// Hochpass 2 kHz). Ist `amount` leer oder sein Maximum unter 1e-3, kommt `x` unveraendert zurueck.
/// Am offenen Anfang bzw. Ende (amount < 0,05) wird ueber 10 ms ins ungefilterte Signal uebergeblendet.
/// `x` hat zwei Kanaele; `amount.size()` muss der Zahl der Frames entsprechen.
/// Fuer Signale unter 2 Frames wirft der Prototyp selbst; hier bleibt dort die Randueberblendung aus.
std::vector<float> sweep(std::span<const float> x, std::span<const float> amount, SweepKind kind, bool resonance = false);

/// `uebergang._baender_gewichten`: gewichtet Tief-, Mittel- und Hochband (< 200 Hz, 200 bis 2000 Hz,
/// > 2000 Hz) je Frame. Ein Nullzeiger laesst das Band unveraendert; sind alle null, kommt `x` zurueck.
std::vector<float> weightBands(std::span<const float> x, const std::vector<float>* low, const std::vector<float>* mid,
                               const std::vector<float>* high);

}  // namespace klangbild::dsp
