// Signalsmith Stretch: ein Dehn-Aufruf wie python-stretch (BAUPLAN-ANDROID T6.1/T6.3).
//
// Der Desktop dehnt ueber `python_stretch`: seek -> process -> flush -> reset, je Aufruf ein
// eigenstaendiges Stueck. Diese Datei bildet genau diese Aufrufreihenfolge nach (Binding
// `signalsmith-bindings.cpp`, Version 0.3.1) und liefert dieselbe Ausgabelaenge
// `round(n / faktor)`.
//
// Nur fuer Baker und Host-Test, nie im Audio-Callback.
#pragma once

#include <span>
#include <vector>

namespace klangbild::dsp {

/// `uebergang._dehnen(stueck, faktor)` fuer Stereo interleaved. `faktor` wird wie im Prototyp
/// float32 (python-stretch speichert `timeFactor` als float). Rueckgabe: `round(Frames/faktor)` Frames.
std::vector<float> dehnen(std::span<const float> stueck, double faktor, int rate = 44100, int channels = 2);

}  // namespace klangbild::dsp
