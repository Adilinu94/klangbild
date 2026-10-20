#include "dsp/effects.h"

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <string>

#include "dsp/fft.h"
#include "dsp/filters.h"
#include "dsp/mixing.h"   // kRate, kChannels

namespace klangbild::dsp {

namespace {

constexpr std::size_t ch = static_cast<std::size_t>(kChannels);

/// uebergang.NASS: Pegel der Effektfahnen.
float wetLevel(std::string_view kind) {
    if (kind == "hall") return static_cast<float>(0.8);
    if (kind == "echo") return static_cast<float>(1.3);
    if (kind == "delay") return static_cast<float>(1.1);
    if (kind == "pingpong") return static_cast<float>(1.4);
    throw std::invalid_argument("unbekannter Effekt: " + std::string(kind));
}

}  // namespace

std::vector<float> wetSignal(std::string_view type, std::span<const float> send, double beatN, std::span<const float> hallIr) {
    const std::size_t n = send.size() / ch;
    if (type == "hall") {
        const float level = wetLevel("hall");
        const std::size_t irFrames = hallIr.size() / ch;
        if (n == 0 || irFrames == 0) return {};
        std::vector<float> out((n + irFrames - 1) * ch);
        for (std::size_t c = 0; c < ch; ++c) {
            std::vector<double> x(n), h(irFrames);
            for (std::size_t i = 0; i < n; ++i) x[i] = static_cast<double>(send[i * ch + c]);
            for (std::size_t i = 0; i < irFrames; ++i) h[i] = static_cast<double>(hallIr[i * ch + c]);
            const std::vector<double> wet = convolve(x, h);
            for (std::size_t i = 0; i < wet.size(); ++i) out[i * ch + c] = level * static_cast<float>(wet[i]);   // NASS * float32(...)
        }
        return out;
    }

    // Art + Prozent: "echo50", "delay100", "pingpong75"
    std::size_t digits = type.size();
    while (digits > 0 && type[digits - 1] >= '0' && type[digits - 1] <= '9') --digits;
    const std::string_view kind = type.substr(0, digits);
    const int percent = std::stoi(std::string(type.substr(digits)));   // Python: int("") wirft; stoi ebenso

    // verz = max(1, int(round(schlag_n * prozent / 100)))   (Python round: halbe Werte zur geraden Zahl)
    const int delay = std::max(1, static_cast<int>(std::nearbyint(beatN * percent / 100.0)));
    const double feedback = kind == "echo" ? 0.7 : (kind == "pingpong" ? 0.55 : 0.35);
    const int repeats = static_cast<int>(std::ceil(std::log(0.01) / std::log(feedback)));   // bis -40 dB
    const std::size_t frames = n + static_cast<std::size_t>(repeats) * static_cast<std::size_t>(delay);
    std::vector<float> wet(frames * ch, 0.0f);
    for (int k = 1; k <= repeats; ++k) {
        const float gain = static_cast<float>(std::pow(feedback, k));   // np.float32(rueck ** k)
        const std::size_t offset = static_cast<std::size_t>(k) * static_cast<std::size_t>(delay);
        if (kind == "pingpong") {   // abwechselnd links/rechts, Mono-Summe der Quelle
            const std::size_t target = static_cast<std::size_t>(k % 2);
            for (std::size_t i = 0; i < n; ++i) {
                const float mean = (send[i * ch] + send[i * ch + 1]) / 2.0f;   // send.mean(axis=1) in float32
                wet[(offset + i) * ch + target] += mean * gain;
            }
        } else {
            for (std::size_t i = 0; i < n; ++i)
                for (std::size_t c = 0; c < ch; ++c) wet[(offset + i) * ch + c] += send[i * ch + c] * gain;
        }
    }
    if (kind == "echo")   // Echo dunkel und weich, Delay klar
        wet = filterSignal(butterworthLowpass(4, 3000.0, kRate), wet.data(), frames, kChannels);
    const float level = wetLevel(kind);   // wirft bei unbekannter Art (KeyError im Prototyp)
    for (float& v : wet) v = level * v;
    return wet;
}

}  // namespace klangbild::dsp
