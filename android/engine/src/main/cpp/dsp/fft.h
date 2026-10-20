// FFT und schnelle Faltung (BAUPLAN-ANDROID T5.6).
//
// Eine kleine Radix-2-FFT in double und Overlap-Add-Faltung dafuer (der Prototyp nutzt
// scipy.signal.oaconvolve). Statt KissFFT als Fremdquelle einzubinden: Die Laengen im Baker sind
// Zweierpotenzen, und double ist genauer als die float32-FFT von scipy. Bei Bedarf laesst sich die
// Klasse spaeter gegen KissFFT tauschen, die Schnittstelle bleibt klein.
//
// Nur fuer Baker und Host-Test, nie im Audio-Callback (allokiert).
#pragma once

#include <complex>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace klangbild::dsp {

/// Komplexe FFT fester Laenge `n` (Zweierpotenz). Die Vorwaertstransformation hat keinen Faktor, die
/// Rueckwaertstransformation teilt durch `n` (wie numpy). Tabellen werden im Konstruktor angelegt.
class Fft {
public:
    explicit Fft(std::size_t n);

    std::size_t size() const { return n_; }
    void forward(std::complex<double>* data) const { transform(data, false); }
    void inverse(std::complex<double>* data) const { transform(data, true); }

private:
    void transform(std::complex<double>* data, bool inverse) const;

    std::size_t n_;
    std::vector<std::complex<double>> twiddle_;   // exp(-2*pi*i*k/n), k < n/2
    std::vector<std::uint32_t> reverse_;          // Bit-Umkehr-Reihenfolge
};

/// Kleinste Zweierpotenz >= n (n >= 1).
std::size_t nextPowerOfTwo(std::size_t n);

/// Volle lineare Faltung `x * h` (Laenge x + h - 1) per Overlap-Add. `fftSize` = 0 waehlt automatisch
/// (mindestens doppelt so lang wie `h`); sonst eine Zweierpotenz >= 2 * h.size() zum Testen.
/// Ist eine Eingabe leer, ist das Ergebnis leer.
std::vector<double> convolve(const std::vector<double>& x, const std::vector<double>& h, std::size_t fftSize = 0);

}  // namespace klangbild::dsp
