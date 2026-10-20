#include "dsp/fft.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <numbers>
#include <stdexcept>

namespace klangbild::dsp {

std::size_t nextPowerOfTwo(std::size_t n) {
    std::size_t p = 1;
    while (p < n) p <<= 1;
    return p;
}

Fft::Fft(std::size_t n) : n_(n) {
    if (n < 1 || (n & (n - 1)) != 0) throw std::invalid_argument("Fft: Laenge muss eine Zweierpotenz sein");
    twiddle_.resize(n / 2);
    for (std::size_t k = 0; k < n / 2; ++k) {
        const double angle = -2.0 * std::numbers::pi * static_cast<double>(k) / static_cast<double>(n);   // direkt, nicht rekursiv: genau
        twiddle_[k] = {std::cos(angle), std::sin(angle)};
    }
    reverse_.resize(n);
    std::size_t bits = 0;
    while ((std::size_t{1} << bits) < n) ++bits;
    for (std::size_t i = 0; i < n; ++i) {
        std::uint32_t r = 0;
        for (std::size_t b = 0; b < bits; ++b)
            if (i & (std::size_t{1} << b)) r |= 1u << (bits - 1 - b);
        reverse_[i] = r;
    }
}

void Fft::transform(std::complex<double>* data, bool inverse) const {
    for (std::size_t i = 0; i < n_; ++i)
        if (i < reverse_[i]) std::swap(data[i], data[reverse_[i]]);
    for (std::size_t len = 2; len <= n_; len <<= 1) {
        const std::size_t half = len / 2;
        const std::size_t step = n_ / len;
        for (std::size_t start = 0; start < n_; start += len) {
            for (std::size_t j = 0; j < half; ++j) {
                std::complex<double> w = twiddle_[j * step];
                if (inverse) w = std::conj(w);
                const std::complex<double> u = data[start + j];
                const std::complex<double> v = data[start + j + half] * w;
                data[start + j] = u + v;
                data[start + j + half] = u - v;
            }
        }
    }
    if (inverse) {
        const double scale = 1.0 / static_cast<double>(n_);
        for (std::size_t i = 0; i < n_; ++i) data[i] *= scale;
    }
}

std::vector<double> convolve(const std::vector<double>& x, const std::vector<double>& h, std::size_t fftSize) {
    if (x.empty() || h.empty()) return {};
    const std::size_t outLen = x.size() + h.size() - 1;
    std::size_t size = fftSize != 0 ? fftSize : nextPowerOfTwo(2 * h.size());
    if (size < 2 * h.size() || (size & (size - 1)) != 0) throw std::invalid_argument("convolve: fftSize");
    if (fftSize == 0 && outLen <= size) size = nextPowerOfTwo(outLen);   // passt in einen Block
    const std::size_t block = size - h.size() + 1;                        // Eingabeblock je FFT
    const Fft fft(size);
    std::vector<std::complex<double>> spectrumH(size, 0.0);
    for (std::size_t i = 0; i < h.size(); ++i) spectrumH[i] = h[i];
    fft.forward(spectrumH.data());

    std::vector<double> out(outLen, 0.0);
    std::vector<std::complex<double>> buffer(size);
    for (std::size_t pos = 0; pos < x.size(); pos += block) {
        const std::size_t len = std::min(block, x.size() - pos);
        std::fill(buffer.begin(), buffer.end(), std::complex<double>(0.0, 0.0));
        for (std::size_t i = 0; i < len; ++i) buffer[i] = x[pos + i];
        fft.forward(buffer.data());
        for (std::size_t i = 0; i < size; ++i) buffer[i] *= spectrumH[i];
        fft.inverse(buffer.data());
        const std::size_t keep = std::min(len + h.size() - 1, outLen - pos);
        for (std::size_t i = 0; i < keep; ++i) out[pos + i] += buffer[i].real();
    }
    return out;
}

}  // namespace klangbild::dsp
