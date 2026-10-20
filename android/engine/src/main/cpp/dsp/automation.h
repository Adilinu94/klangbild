// Automationskurven fuer die Anzeige und Loop-Plan (BAUPLAN-ANDROID T5.12).
//
// Port von uebergang.kurven, uebergang.kurven_eigen und uebergang._loop_plan.
// Werte 0..1 an KURVEN_PUNKTE Stellen, auf drei Nachkommastellen gerundet wie im Prototyp.
//
// Nur fuer Baker und Oberflaeche, nie im Audio-Callback.
#pragma once

#include <array>
#include <map>
#include <string>
#include <string_view>
#include <vector>

#include "dsp/envelopes.h"
#include "dsp/settings.h"

namespace klangbild::dsp {

/// uebergang.KURVEN_PUNKTE: Stuetzstellen der Anzeigekurven.
inline constexpr int kAutomationPoints = 64;

/// Ein Loop-Abschnitt in Achteln der Blende (`uebergang._loop_plan`).
struct LoopSection {
    int from = 0;
    int to = 0;
    int size = 0;
};

/// `uebergang._loop_plan`: Loop-Abschnitte (von, bis, Groesse in Achteln). Wirft bei `loop` "keiner"
/// und "auto" wie der Prototyp (`int("auto")`).
std::vector<LoopSection> loopPlan(const Settings& settings, int bars);

/// `uebergang.kurven`: je Seite ("a", "b") und Parameter die Kurve.
struct Automation {
    std::map<std::string, Curve> a;
    std::map<std::string, Curve> b;
};

/// `uebergang.kurven(art, takte, e)`: `kind` ist "eigen", "eq", "filter", "echo", "schnitt" oder
/// "crossfade". Die Stem-Arten aus `STEM_PLAN` folgen mit M11 und werfen hier.
Automation automation(std::string_view kind, int bars, const Settings& settings);

}  // namespace klangbild::dsp
