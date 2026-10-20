#include "dsp/filters.h"

#include <algorithm>
#include <cmath>
#include <complex>
#include <numbers>
#include <stdexcept>

namespace klangbild::dsp {

Sos butterworthLowpass(int order, double cutoffHz, int rate) {
    if (order < 2 || (order % 2) != 0) throw std::invalid_argument("butterworthLowpass: gerade Ordnung >= 2 noetig");
    const double nyquist = static_cast<double>(rate) / 2.0;
    if (!(0.0 < cutoffHz && cutoffHz < nyquist)) return {};   // mix._sos: None

    // scipy.signal.butter -> iirfilter: analoger Prototyp (buttap), Vorverzerrung, lp2lp, bilinear, zpk2sos.
    const double wn = cutoffHz / nyquist;
    const double fs = 2.0;                                   // scipy rechnet digital mit fs = 2
    const double warped = 2.0 * fs * std::tan(std::numbers::pi * wn / fs);
    const double fs2 = 2.0 * fs;                             // Bilinear: (fs2 + p) / (fs2 - p)

    // Pole des analogen Prototyps in der linken Halbebene: exp(i*pi*(2k + N + 1) / (2N)), k = 0..N-1.
    std::vector<std::complex<double>> analog;
    for (int k = 0; k < order; ++k) {
        const double angle = std::numbers::pi * static_cast<double>(2 * k + order + 1) / static_cast<double>(2 * order);
        analog.emplace_back(std::cos(angle), std::sin(angle));
    }
    // lp2lp: Pole * warped; die Verstaerkung waechst mit warped^Grad (Grad = Zahl der Pole, keine analogen Nullstellen).
    double gain = std::pow(warped, order);
    std::vector<std::complex<double>> digital;
    std::complex<double> denominator = 1.0;
    for (const auto& p : analog) {
        const std::complex<double> pw = p * warped;
        digital.push_back((fs2 + pw) / (fs2 - pw));
        denominator *= (fs2 - pw);
    }
    gain /= denominator.real();   // k_z = k * real(prod(fs2 - z) / prod(fs2 - p)), keine analogen Nullstellen

    // zpk2sos: konjugierte Polpaare je Abschnitt, Nullstellen alle bei -1 ([1, 2, 1]). Der Abschnitt mit
    // den am weitesten vom Einheitskreis entfernten Polen (kleinstes |p|^2) steht vorn; die Verstaerkung
    // sitzt im ersten Abschnitt (sos[0, :3] *= k).
    Sos sos;
    for (const auto& p : digital) {
        if (p.imag() > 0.0) {
            Biquad s;
            s.b0 = 1.0;
            s.b1 = 2.0;
            s.b2 = 1.0;
            s.a1 = -2.0 * p.real();
            s.a2 = std::norm(p);
            sos.push_back(s);
        }
    }
    std::stable_sort(sos.begin(), sos.end(), [](const Biquad& a, const Biquad& b) { return a.a2 < b.a2; });
    sos.front().b0 *= gain;
    sos.front().b1 *= gain;
    sos.front().b2 *= gain;
    return sos;
}

namespace {

/// Ein Durchlauf der Kaskade ueber `x` mit Anfangszustand `zi` (zwei Werte je Abschnitt); in place.
/// Reihenfolge wie scipy `_sosfilt`: je Abschnitt Direktform II transponiert.
void run(const Sos& sos, std::vector<double>& x, std::vector<double>& zi) {
    for (std::size_t s = 0; s < sos.size(); ++s) {
        const Biquad& q = sos[s];
        double z0 = zi[2 * s];
        double z1 = zi[2 * s + 1];
        for (double& sample : x) {
            const double in = sample;
            const double out = q.b0 * in + z0;
            z0 = q.b1 * in - q.a1 * out + z1;
            z1 = q.b2 * in - q.a2 * out;
            sample = out;
        }
        zi[2 * s] = z0;
        zi[2 * s + 1] = z1;
    }
}

}  // namespace

void sosfilt(const Sos& sos, std::vector<double>& x) {
    std::vector<double> zi(2 * sos.size(), 0.0);
    run(sos, x, zi);
}

std::vector<double> sosfiltZi(const Sos& sos) {
    // scipy: zi[s] = scale * lfilter_zi(b, a); scale *= sum(b) / sum(a).
    std::vector<double> zi(2 * sos.size(), 0.0);
    double scale = 1.0;
    for (std::size_t s = 0; s < sos.size(); ++s) {
        const Biquad& q = sos[s];
        // lfilter_zi fuer ein Biquad: (I - A^T) zi = B mit B = b[1:] - a[1:] * b0 (geschlossene Loesung).
        const double bb0 = q.b1 - q.a1 * q.b0;
        const double bb1 = q.b2 - q.a2 * q.b0;
        const double z0 = (bb0 + bb1) / (1.0 + q.a1 + q.a2);
        const double z1 = bb1 - q.a2 * z0;
        zi[2 * s] = scale * z0;
        zi[2 * s + 1] = scale * z1;
        scale *= (q.b0 + q.b1 + q.b2) / (1.0 + q.a1 + q.a2);
    }
    return zi;
}

std::optional<std::vector<double>> sosfiltfilt(const Sos& sos, const std::vector<double>& x) {
    // ntaps = 2 * n_sections + 1, abzueglich der Abschnitte mit b2 == 0 und a2 == 0; padlen = 3 * ntaps.
    std::size_t zerosB2 = 0, zerosA2 = 0;
    for (const Biquad& q : sos) {
        if (q.b2 == 0.0) ++zerosB2;
        if (q.a2 == 0.0) ++zerosA2;
    }
    const std::size_t ntaps = 2 * sos.size() + 1 - std::min(zerosB2, zerosA2);
    const std::size_t edge = 3 * ntaps;
    if (x.size() <= edge) return std::nullopt;   // scipy: ValueError

    // Ungerade Fortsetzung: links 2*x[0] - x[edge..1], rechts 2*x[-1] - x[-2..-(edge+1)].
    const std::size_t n = x.size();
    std::vector<double> ext(n + 2 * edge);
    for (std::size_t i = 0; i < edge; ++i) ext[i] = 2.0 * x[0] - x[edge - i];
    std::copy(x.begin(), x.end(), ext.begin() + static_cast<std::ptrdiff_t>(edge));
    for (std::size_t i = 0; i < edge; ++i) ext[edge + n + i] = 2.0 * x[n - 1] - x[n - 2 - i];

    const std::vector<double> zi = sosfiltZi(sos);
    // vorwaerts, Zustand = zi * ext[0]
    std::vector<double> state(zi.size());
    for (std::size_t i = 0; i < zi.size(); ++i) state[i] = zi[i] * ext.front();
    run(sos, ext, state);
    // rueckwaerts, Zustand = zi * letzter Wert der Vorwaertsausgabe
    std::reverse(ext.begin(), ext.end());
    for (std::size_t i = 0; i < zi.size(); ++i) state[i] = zi[i] * ext.front();
    run(sos, ext, state);
    std::reverse(ext.begin(), ext.end());
    return std::vector<double>(ext.begin() + static_cast<std::ptrdiff_t>(edge),
                               ext.begin() + static_cast<std::ptrdiff_t>(edge + n));
}

std::vector<float> filterSignal(const Sos& sos, const float* signal, std::size_t frames, int channels) {
    const std::size_t stride = static_cast<std::size_t>(channels);
    std::vector<float> out(frames * stride);
    if (sos.empty()) {
        std::copy(signal, signal + frames * stride, out.begin());   // _sos lieferte None: das Signal bleibt
        return out;
    }
    std::vector<double> channel(frames);
    for (int c = 0; c < channels; ++c) {
        for (std::size_t i = 0; i < frames; ++i) channel[i] = static_cast<double>(signal[i * stride + static_cast<std::size_t>(c)]);
        std::vector<double> filtered;
        if (auto zeroPhase = sosfiltfilt(sos, channel)) {
            filtered = std::move(*zeroPhase);
        } else {
            filtered = channel;   // zu kurz fuer die Polsterung: kausales sosfilt
            sosfilt(sos, filtered);
        }
        for (std::size_t i = 0; i < frames; ++i) out[i * stride + static_cast<std::size_t>(c)] = static_cast<float>(filtered[i]);
    }
    return out;
}

BandSplit bandSplit(const float* signal, std::size_t frames, int channels, int rate, double splitHz) {
    BandSplit out;
    const std::size_t total = frames * static_cast<std::size_t>(channels);
    out.low = filterSignal(butterworthLowpass(4, splitHz, rate), signal, frames, channels);   // FILTER_ORDNUNG = 4
    out.high.resize(total);
    for (std::size_t k = 0; k < total; ++k) out.high[k] = signal[k] - out.low[k];             // (signal - low), beides float32
    return out;
}

}  // namespace klangbild::dsp
