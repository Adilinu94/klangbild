// Blende backen: A -> B rendern (BAUPLAN-ANDROID M6.5).
//
// Port von uebergang.backen ohne Stems (M11) und ohne Keylock (M6.3): Art, Laenge, Sync,
// Vorlauf, Intro-Loop, Warp, Mischung, Nachlauf, Limiter, Spur-Zeitrechnung und Info.
//
// Nur fuer Baker, nie im Audio-Callback.
#pragma once

#include <optional>
#include <span>
#include <string>
#include <vector>

#include "dsp/automation.h"
#include "dsp/loop.h"
#include "dsp/loopchoice.h"
#include "dsp/raster.h"
#include "dsp/settings.h"

namespace klangbild::dsp {

/// `info` aus `uebergang.backen` (nur die Felder ohne Stems).
struct BackInfo {
    std::string art;
    int takte = 0;
    bool sync = false;
    double bpmA = 0.0;
    double bpmB = 0.0;
    std::string modus;
    bool stems = false;
    std::string hinweis;
    double blendeS = 0.0;
    double aOrigStart = 0.0;
    double bOrigStart = 0.0;
    double aOrigProS = 1.0;
    bool hatVorlauf = false;
    double vorlaufS = 0.0;
    int vorlaufTakte = 0;
    std::vector<double> rasterS;
    Automation kurven;
    std::vector<LoopInfo> aLoop;
    bool hatLoopWahl = false;
    LoopChoice loopWahl;
    bool hatIntroLoop = false;
    int introTakte = 0;
    int introMal = 0;
};

struct Gebacken {
    long long startN = 0;   // Blendenbeginn im Puffer von A
    Spur spur;              // B, Puffer beginnt mit der Blende
    BackInfo info;
};

/// `uebergang.backen(a, b, b_audio, e, ab_s, weiter, aus_s, ein_s)`.
/// Stem-Uebergaenge werfen (M11). `hallIr` und `riserNoise` wie bei `mischenEigen`.
Gebacken backen(const Spur& a, const Eintrag& b, std::span<const float> bAudio, const Settings& e, double abS,
                bool weiter = false, std::optional<double> ausS = std::nullopt,
                std::optional<double> einS = std::nullopt, std::span<const float> hallIr = {},
                std::span<const float> riserNoise = {}, int rate = 44100);

}  // namespace klangbild::dsp
