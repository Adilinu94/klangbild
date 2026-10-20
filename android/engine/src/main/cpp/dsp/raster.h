// Taktraster, Ausstieg und Einstieg (BAUPLAN-ANDROID M6.4).
//
// Port von uebergang._ext, raster, regulaer, taktraster, _periode, _naechster_index,
// _phrase_bei, ausstieg und einstieg sowie uebergang.Spur (nur die Zeitrechnung).
//
// Nur fuer Regie und Baker, nie im Audio-Callback.
#pragma once

#include <array>
#include <cstddef>
#include <optional>
#include <span>
#include <string>
#include <vector>

#include "dsp/settings.h"

namespace klangbild::dsp {

inline constexpr int kPhrase = 8;       // uebergang.PHRASE
inline constexpr double kDriftS = 16.0; // uebergang.DRIFT_S

/// `uebergang.Eintrag` (nur die Felder, die das Raster braucht).
struct Eintrag {
    int id = 0;
    std::string pfad;
    double bpm = 0.0;
    std::string camelot;
    std::vector<double> downbeats;
    std::vector<double> abschnitte;
    std::vector<std::array<double, 2>> fein;   // anker.fein: [[t, dt], ...]
};

/// `uebergang._ext`: np.interp mit linearer Fortsetzung ueber beide Enden.
double ext(double x, const std::vector<double>& xp, const std::vector<double>& fp);

/// `uebergang.raster`: Taktzeiten, mit der Taktlaenge am Ende bis `bisS` fortgesetzt.
std::vector<double> raster(std::span<const double> takte, double bisS);

/// `uebergang.regulaer`: EIN Taktraster je Song aus den Downbeats (Tempo aus `bpm`, Eins aus der
/// Mehrheit, Lage lokal nachgefuehrt).
std::vector<double> regulaer(std::span<const double> downbeats, double bpm, double bisS);

/// `uebergang.taktraster`: `regulaer` plus Fein-Anker (`Eintrag.fein`, np.interp).
std::vector<double> taktraster(const Eintrag& eintrag, double bisS);

/// `uebergang._periode`: lokale Taktlaenge (Mittel der Abstaende nahe am Median, +-`halb` Takte).
double periode(std::span<const double> t, int i, int halb = 8);

/// `uebergang.Spur`: Zeitrechnung Original <-> Puffer (und optional das Audio).
struct Spur {
    Eintrag eintrag;
    long long frames = 0;          // Pufferlaenge in Frames
    std::vector<double> orig;      // Takte in Originalzeit
    std::vector<double> buf;       // dieselben Takte in Pufferzeit
    std::vector<float> puffer;     // optional: Stereo, interleaved

    double zuPuffer(double t) const { return ext(t, orig, buf); }
    double zuOriginal(double t) const { return ext(t, buf, orig); }
};

/// `uebergang.Spur.roh(eintrag, puffer)`: Raster aus `taktraster`, Orig = Puffer.
Spur rohSpur(const Eintrag& eintrag, std::vector<float> puffer, int rate = 44100);

/// Ergebnis von `ausstieg`/`einstieg`: Raster und Index des Takts.
struct Cut {
    std::vector<double> raster;
    int index = 0;
};

/// `uebergang.ausstieg(a, e, takte, ab_s, weiter, aus_s)`.
Cut ausstieg(const Spur& a, const Settings& e, int takte, double abS, bool weiter = false,
             std::optional<double> ausS = std::nullopt, int rate = 44100);

/// `uebergang.einstieg(b, b_samples, e, ein_s)`.
Cut einstieg(const Eintrag& b, long long bSamples, const Settings& e,
             std::optional<double> einS = std::nullopt, int rate = 44100);

}  // namespace klangbild::dsp
