// Bäcker-Schnittstelle fuer die App (BAUPLAN-ANDROID §4.5, M6.5/M8b).
//
// Kotlin plant, C++ rendert: `parseBakeAnfrage` liest den Uebergangsplan als JSON,
// `bakeTransition` backt ihn und liefert PCM plus Info-JSON.
#pragma once

#include <span>
#include <string>
#include <string_view>
#include <vector>

#include "dsp/backen.h"
#include "dsp/raster.h"
#include "dsp/settings.h"

namespace klangbild {

struct BakeAnfrage {
    dsp::Eintrag a;
    dsp::Eintrag b;
    dsp::Settings einst;
    double abS = 0.0;
    double ausS = 0.0;
    double einS = 0.0;
    bool weiter = false;
};

struct BakeErgebnis {
    bool ok = false;
    std::string fehler;
    std::vector<float> audio;   // Spur B inklusive Blende (Stereo interleaved)
    long long startN = 0;       // Blendenbeginn im Puffer von A
    std::vector<double> orig;   // Spur.orig von B
    std::vector<double> buf;    // Spur.buf von B
    std::string info;           // JSON wie `uebergang.backen` info
};

/// Liest den Uebergangsplan (JSON nach §4.5). Wirft `JsonFehler` bei kaputtem Inhalt.
BakeAnfrage parseBakeAnfrage(std::string_view plan);

/// Backt den Uebergang. `aAudio`/`bAudio` sind Stereo interleaved, `hallIr` die Hall-IR.
BakeErgebnis bakeTransition(const BakeAnfrage& anfrage, std::span<const float> aAudio,
                            std::span<const float> bAudio, std::span<const float> hallIr,
                            std::span<const float> riserNoise, int rate = 44100);

/// Info-JSON eines Ergebnisses (auch fuer Tests).
std::string infoJson(const dsp::BackInfo& info);

}  // namespace klangbild
