// Rundung wie Python (BAUPLAN-ANDROID): round(v, n) ueber die Dezimaldarstellung, nicht ueber v*10^n.
#pragma once

#include <cstdio>
#include <cstdlib>

namespace klangbild::dsp {

inline double roundTo(double v, int stellen) {
    char text[64];
    std::snprintf(text, sizeof text, "%.*f", stellen, v);
    return std::strtod(text, nullptr);
}

}  // namespace klangbild::dsp
