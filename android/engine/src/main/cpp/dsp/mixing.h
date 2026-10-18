// Feste Uebergangsarten: Crossfade, EQ-Bass-Tausch, Filter, Echo, Schnitt (BAUPLAN-ANDROID T5.3).
//
// Port von mix._fade_segment, uebergang._baender, uebergang._echo und uebergang.mischen.
// Signale sind Stereo, float32, interleaved (L,R,L,R,...), wie die PCM-Puffer der Engine.
// Jede Rechnung folgt dem Datentyp von numpy: float32-Arrays mit Python-Skalaren bleiben float32;
// Multiplikation und Addition werden nicht zu FMA verschmolzen (-ffp-contract=off, sources.cmake).
//
// Nur fuer Baker und Host-Test, nie im Audio-Callback.
#pragma once

#include <cstddef>
#include <span>
#include <string_view>
#include <vector>

namespace klangbild::dsp {

/// Abtastrate des Hoertests und aller Uebergaenge (config.ABTASTRATE_HOERTEST).
inline constexpr int kRate = 44100;
/// Stereo interleaved.
inline constexpr int kChannels = 2;

/// `mix._fade_segment`: Crossfade `a` -> `b` ueber die gemeinsame Laenge. Ohne `bassSwap` equipotent
/// (cos/sin). Mit `bassSwap` tauscht das Tiefband (unter `splitHz`) hart an der Mitte, waehrend das
/// Hochband equipotent ueberblendet. `a` und `b` werden auf die kuerzere Laenge gekuerzt.
std::vector<float> fadeSegment(std::span<const float> a, std::span<const float> b, int rate, bool bassSwap,
                               double splitHz = 200.0);

/// `uebergang._echo`: A spielt `beatN` Frames, dann folgt eine Echo-Fahne (Verzoegerung `beatN`,
/// Rueckkopplung 0,7, hoechstens 16 Wiederholungen). Laenge wie die Eingabe.
std::vector<float> echo(std::span<const float> a, int beatN);

/// `uebergang.mischen`: mischt zwei taktsynchrone Abschnitte nach `kind`:
/// "eq", "filter", "echo", "schnitt"; jede andere Angabe (auch "crossfade") ist ein equipotenter
/// Crossfade. `bars` ist die Zahl der Takte des Abschnitts (nur fuer "echo"). Laenge = die kuerzere Eingabe.
std::vector<float> mix(std::string_view kind, std::span<const float> a, std::span<const float> b, int bars);

}  // namespace klangbild::dsp
