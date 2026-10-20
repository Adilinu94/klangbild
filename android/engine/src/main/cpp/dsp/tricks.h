// DJ-Tricks im Uebergang (BAUPLAN-ANDROID T5.11).
//
// Port von uebergang._abspielen, _bremse, _spinback, _flanger, _phaser, _gate, _crush,
// _rueckhall und _riser. Alle arbeiten auf Stereo, float32, interleaved.
//
// Nur fuer Baker und Host-Test, nie im Audio-Callback.
#pragma once

#include <cstddef>
#include <span>
#include <vector>

namespace klangbild::dsp {

/// `_abspielen`: `a` an gebrochenen Sample-Positionen, linear interpoliert (np.interp, Rand konstant).
std::vector<float> abspielen(std::span<const float> a, std::span<const double> pos);

/// `_bremse`: Tape-Stop ueber die letzten `n` Frames (Tonhoehe faellt mit).
std::vector<float> bremse(std::span<const float> a, long long n);

/// `_spinback`: Backspin ueber die letzten `n` Frames (+1 -> -5 -> 0 Samples je Frame).
std::vector<float> spinback(std::span<const float> a, long long n);

/// `_flanger`: A plus wandering copy (1-5 ms, LFO 2 Takte), Anteil `depth` 0..1 je Frame (float64 wie im
/// Prototyp, intern float32).
std::vector<float> flanger(std::span<const float> a, std::span<const double> depth, double beatN);

/// `_phaser`: vier Allpaesse (300 Hz - 3 kHz, LFO 2 Takte) plus Original, Anteil `depth`.
std::vector<float> phaser(std::span<const float> a, std::span<const double> depth, double beatN);

/// `_gate`: A in den letzten zwei Takten im Achtel-Takt an/aus, im letzten in Sechzehnteln.
std::vector<float> gate(std::span<const float> a, std::span<const double> taktN);

/// `_crush`: Bitcrusher 16 -> 7 Bit mit Sample-and-Hold, Anteil nach `depth`.
std::vector<float> crush(std::span<const float> a, std::span<const double> depth);

/// `_rueckhall`: der Hall von B's erstem Schlag ab Frame `p`, rueckwaerts (schwillt bis `p` an).
/// `hallIr` ist die Hall-Impulsantwort (interleaved, wie `uebergang._hall_ir`).
std::vector<float> rueckhall(std::span<const float> b, int p, double beatN, std::span<const float> hallIr);

/// `_riser`: Rauschen mit Hochpass-Sweep ueber die letzten `m` Frames, Pegel bis `level`.
/// `noise` liefert `m` Frames Rauschen (interleaved). Der Prototyp zieht es aus `default_rng(3)`;
/// Zufall ist nicht bitgleich portierbar, darum kommt es von aussen (Test: Python-Rauschen).
std::vector<float> riser(int frames, int m, double level, std::span<const float> noise);

}  // namespace klangbild::dsp
