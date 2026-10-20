// Loop-Wahl: wo und wie lang klingt ein Loop sauber? (BAUPLAN-ANDROID T5.9)
//
// Port von uebergang._beat_merkmale, _aehnlich, loop_waehlen und loop_im_original.
// Klangbild je Schlag: 16 logarithmische Baender (40 Hz - 16 kHz) aus einer 4096-FFT.
//
// Nur fuer Regie und Baker, nie im Audio-Callback.
#pragma once

#include <cstddef>
#include <optional>
#include <span>
#include <vector>

namespace klangbild::dsp {

/// `uebergang._beat_merkmale`: eine Zeile je Viertel, 16 Baender in dB.
std::vector<std::vector<double>> beatFeatures(std::span<const float> x, std::span<const double> taktN,
                                              int channels = 2, int rate = 44100);

/// `uebergang._aehnlich`: mittlere Kosinus-Aehnlichkeit der Klangfarbe von Schlag `i` und `j`
/// ueber `n` Schlaege, gewichtet mit dem Pegelabstand (0..1).
double similarity(const std::vector<std::vector<double>>& features, int i, int j, int n);

/// Ergebnis von `loop_waehlen`: Start-Takt, Laenge in Takten, Guete 0..1.
struct LoopChoice {
    int start = 0;
    int bars = 0;
    double quality = 0.0;
};

/// `uebergang.loop_waehlen`: sauberster Loop in `a`. `meiden` markiert Takte mit Gesang (optional),
/// `sizes` sind die erlaubten Laengen (leer = {8,4,2,1}), `window` begrenzt den Startbereich
/// (0 = ganze Laenge).
LoopChoice chooseLoop(std::span<const float> a, std::span<const double> taktN,
                      std::optional<std::span<const int>> meiden = std::nullopt,
                      std::span<const int> sizes = {}, int window = 0, int channels = 2, int rate = 44100);

/// `uebergang.loop_im_original`: dasselbe fuer eine Blende ab Takt `i`, aus dem ungedehnten Audio
/// (vergleicht auch die Takte hinter der Blende).
LoopChoice loopInOriginal(std::span<const float> puffer, std::span<const double> rasterS, int i, int bars,
                          std::optional<std::span<const int>> meiden = std::nullopt, int rate = 44100);

}  // namespace klangbild::dsp
