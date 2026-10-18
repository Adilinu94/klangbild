// Filter und Bandteilung (BAUPLAN-ANDROID T5.2).
//
// Port von mix._sos, mix._filtern und mix.band_teilen. Wie scipy: Butterworth als Kaskade von
// Biquads (SOS), nullphasige Filterung mit `sosfiltfilt` (BAUPLAN §5.8). Gerechnet wird in double,
// genau wie der Prototyp (`np.asarray(signal, dtype=np.float64)`); erst das Ergebnis wird float32.
//
// Nur fuer Baker und Host-Test, nie im Audio-Callback (allokiert, nullphasig = braucht das ganze Fenster).
#pragma once

#include <cstddef>
#include <optional>
#include <vector>

namespace klangbild::dsp {

/// Ein Biquad (Direktform II transponiert), a0 = 1.
struct Biquad {
    double b0 = 1.0, b1 = 0.0, b2 = 0.0;
    double a1 = 0.0, a2 = 0.0;
};

/// Kaskade von Biquads, wie eine `sos`-Matrix aus scipy (Zeilen: b0 b1 b2 a0=1 a1 a2).
using Sos = std::vector<Biquad>;

/// `scipy.signal.butter(order, cutoffHz / (rate / 2), btype="low", output="sos")` (mix._sos).
/// `order` muss gerade und >= 2 sein. Liegt `cutoffHz` nicht in (0, rate/2), kommt eine leere
/// Kaskade zurueck (der Prototyp liefert dort None und filtert nicht).
Sos butterworthLowpass(int order, double cutoffHz, int rate);

/// `scipy.signal.sosfilt(sos, x)` mit Nullzustand, ueber ein Signal (ein Kanal), in place.
void sosfilt(const Sos& sos, std::vector<double>& x);

/// `scipy.signal.sosfilt_zi(sos)`: Anfangszustand je Abschnitt fuer einen Sprung von 0 auf 1.
/// Ergebnis: zwei Zustaende je Abschnitt (z0, z1).
std::vector<double> sosfiltZi(const Sos& sos);

/// `scipy.signal.sosfiltfilt(sos, x)` mit den Standardwerten (padtype "odd", padlen = 3 * ntaps).
/// Ist `x` nicht laenger als `padlen`, wirft scipy ValueError; hier `std::nullopt`.
std::optional<std::vector<double>> sosfiltfilt(const Sos& sos, const std::vector<double>& x);

/// Ergebnis von `band_teilen`: Tief- und Hochband im Format der Eingabe (interleaved).
struct BandSplit {
    std::vector<float> low;
    std::vector<float> high;
};

/// `mix.band_teilen`: zerlegt `signal` (`frames` Frames, `channels` Kanaele interleaved, Mono oder
/// Stereo) bei `splitHz` in (low, high). low = nullphasiges Tiefpassfilter 4. Ordnung, high = signal - low.
/// Zu kurze Signale (<= 15 Samples) laufen wie im Prototyp ueber das kausale `sosfilt`.
BandSplit bandSplit(const float* signal, std::size_t frames, int channels, int rate, double splitHz = 200.0);

}  // namespace klangbild::dsp
