// Kurven fuer Ueberblendungen (BAUPLAN-ANDROID T5.1).
//
// Port von mix.equal_power_blende, uebergang._rampe und mix._bass_rampen. Gleiche
// Rechenreihenfolge und gleiche Genauigkeit wie numpy (BAUPLAN §13): Ausdruecke mit
// float32-Arrays und Python-Skalaren bleiben in float32, np.linspace/np.cos laufen in float64.
//
// Reines C++20 ohne Android-Abhaengigkeit; laeuft im Host-Test und im Baker, nie im Callback.
#pragma once

#include <algorithm>
#include <cmath>
#include <numbers>
#include <vector>

namespace klangbild::dsp {

/// Ein Kurvenpaar: `out` blendet aus (1 -> 0), `in` blendet ein (0 -> 1).
struct CurvePair {
    std::vector<float> out;
    std::vector<float> in;
};

/// `mix.equal_power_blende`: cos/sin ueber [0, pi/2), `n` Punkte (Endpunkt nicht enthalten), also
/// out[0] = 1, in[0] = 0 und out^2 + in^2 = 1. `n <= 0` liefert leere Kurven.
inline CurvePair equalPowerBlend(int n) {
    CurvePair c;
    if (n <= 0) return c;
    c.out.resize(static_cast<std::size_t>(n));
    c.in.resize(static_cast<std::size_t>(n));
    // np.linspace(0, pi/2, n, endpoint=False): Schritt (stop - start) / n, Wert i * Schritt (float64).
    const double step = (std::numbers::pi / 2.0) / static_cast<double>(n);
    for (int i = 0; i < n; ++i) {
        const double phase = static_cast<double>(i) * step;
        c.out[static_cast<std::size_t>(i)] = static_cast<float>(std::cos(phase));
        c.in[static_cast<std::size_t>(i)] = static_cast<float>(std::sin(phase));
    }
    return c;
}

/// `uebergang._rampe`: equipotente Einblendkurve (0 -> 1) zwischen den Anteilen `from`..`to` der
/// Laenge. Python liefert die Form (n, 1); hier die n Werte (der Kanal wird beim Anwenden
/// gebroadcastet).
inline std::vector<float> ramp(int n, double from, double to) {
    std::vector<float> r(static_cast<std::size_t>(std::max(n, 0)));
    // t = (np.arange(n) / max(1, n)).astype(np.float32): Division in float64, dann float32.
    const double denom = static_cast<double>(std::max(1, n));
    // Python-Skalare sind "schwach" (NEP 50): `t - von` und `/ max(1e-9, bis - von)` rechnen in float32.
    const float vonF = static_cast<float>(from);
    const float spanF = static_cast<float>(std::max(1e-9, to - from));
    const float halfPi = static_cast<float>(std::numbers::pi);
    for (int i = 0; i < n; ++i) {
        const float t = static_cast<float>(static_cast<double>(i) / denom);
        float x = (t - vonF) / spanF;
        x = std::clamp(x, 0.0f, 1.0f);
        r[static_cast<std::size_t>(i)] = std::sin(x * halfPi / 2.0f);   // np.sin(x * np.pi / 2), float32
    }
    return r;
}

/// `mix._bass_rampen`: Bass-Uebergabe mit hartem Tausch an der Blendenmitte und einer ~10-ms-
/// Raised-Cosine-Flanke darum. `out` behaelt das Tiefband in der ersten Haelfte, `in` in der zweiten.
///
/// Fuer `n == 1` wirft der Python-Code selbst (Slice-Laengen passen nicht); das kommt nie vor und
/// wird hier nicht nachgebildet: es entstehen die Kurven fuer n == 1 mit gekappten Grenzen.
inline CurvePair bassRamps(int n, int rate) {
    CurvePair c;
    if (n <= 0) return c;
    const int mid = n / 2;
    int flank = std::max(1, static_cast<int>(0.010 * static_cast<double>(rate)));   // 10 ms, int() schneidet ab
    flank = std::min(flank, std::max(1, mid));
    c.out.assign(static_cast<std::size_t>(n), 0.0f);
    c.in.assign(static_cast<std::size_t>(n), 0.0f);
    const auto clampIndex = [n](int i) { return std::clamp(i, 0, n); };
    for (int i = 0; i < clampIndex(mid + flank); ++i) c.out[static_cast<std::size_t>(i)] = 1.0f;   // aus[: mitte + flanke]
    for (int i = clampIndex(mid - flank); i < n; ++i) c.in[static_cast<std::size_t>(i)] = 1.0f;      // ein[mitte - flanke:]
    // ramp = 0.5 - 0.5 * np.cos(np.linspace(0, pi, 2*flanke, endpoint=False)).astype(np.float32)
    const double step = std::numbers::pi / static_cast<double>(2 * flank);
    for (int k = 0; k < 2 * flank; ++k) {
        const int i = mid - flank + k;
        if (i < 0 || i >= n) continue;
        const float cosine = static_cast<float>(std::cos(static_cast<double>(k) * step));
        const float rampValue = 0.5f - 0.5f * cosine;
        c.out[static_cast<std::size_t>(i)] = 1.0f - rampValue;
        c.in[static_cast<std::size_t>(i)] = rampValue;
    }
    return c;
}

}  // namespace klangbild::dsp
