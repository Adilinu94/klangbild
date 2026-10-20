#include "dsp/stretch.h"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <vector>

#include "stretch/signalsmith-stretch.h"

namespace klangbild::dsp {
namespace {

/// Puffer wie im python-stretch-Binding: der Zugriff laeuft ueber einen Offset.
template <typename Sample>
class OffsetBuffer {
public:
    class Channel {
    public:
        Channel(Sample* daten, int offset) : daten_(daten), offset_(offset) {}
        Sample& operator[](int i) { return daten_[i + offset_]; }

    private:
        Sample* daten_;
        int offset_;
    };

    OffsetBuffer(std::vector<std::vector<Sample>>& kanaele, std::size_t laenge)
        : kanaele_(kanaele), laenge_(laenge) {}

    Channel operator[](int kanal) { return Channel(kanaele_[static_cast<std::size_t>(kanal)].data(), offset_); }
    std::size_t size() const { return laenge_; }
    void reset() { offset_ = 0; }
    void setOffset(int offset) { offset_ = offset; }
    int getOffset() const { return offset_; }

private:
    std::vector<std::vector<Sample>>& kanaele_;
    std::size_t laenge_;
    int offset_ = 0;
};

}  // namespace

std::vector<float> dehnen(std::span<const float> stueck, double faktor, int rate, int channels) {
    const std::size_t frames = stueck.size() / static_cast<std::size_t>(std::max(1, channels));
    if (frames == 0) return {};

    using Stretch = signalsmith::stretch::SignalsmithStretch<float>;
    Stretch stretch;   // wie python-stretch: Standard-Konstruktor
    stretch.presetDefault(channels, static_cast<float>(rate));

    const float timeFactor = static_cast<float>(faktor);
    const int inputLatency = stretch.inputLatency();
    const int tailSamples = stretch.outputLatency();
    const std::size_t inputLength = frames;
    const std::size_t outputLength = static_cast<std::size_t>(
        std::llround(static_cast<double>(inputLength) / static_cast<double>(timeFactor)));
    const std::size_t paddedInput = inputLength + static_cast<std::size_t>(inputLatency);
    const std::size_t paddedOutput = outputLength + static_cast<std::size_t>(tailSamples);

    std::vector<std::vector<float>> ein(static_cast<std::size_t>(channels),
                                        std::vector<float>(paddedInput, 0.0f));
    std::vector<std::vector<float>> aus(static_cast<std::size_t>(channels),
                                        std::vector<float>(paddedOutput, 0.0f));
    for (std::size_t i = 0; i < inputLength; ++i) {
        for (int c = 0; c < channels; ++c) {
            ein[static_cast<std::size_t>(c)][i] = stueck[i * static_cast<std::size_t>(channels) +
                                                         static_cast<std::size_t>(c)];
        }
    }

    OffsetBuffer<float> inBuffer(ein, paddedInput);
    OffsetBuffer<float> outBuffer(aus, outputLength);
    stretch.seek(inBuffer, inputLatency, static_cast<double>(timeFactor));
    inBuffer.setOffset(inputLatency);
    stretch.process(inBuffer, static_cast<int>(inputLength), outBuffer, static_cast<int>(outputLength));
    outBuffer.setOffset(static_cast<int>(outputLength));
    stretch.flush(outBuffer, tailSamples);
    stretch.reset();

    std::vector<float> ergebnis(outputLength * static_cast<std::size_t>(channels));
    for (std::size_t i = 0; i < outputLength; ++i) {
        for (int c = 0; c < channels; ++c) {
            ergebnis[i * static_cast<std::size_t>(channels) + static_cast<std::size_t>(c)] =
                aus[static_cast<std::size_t>(c)][i + static_cast<std::size_t>(tailSamples)];
        }
    }
    return ergebnis;
}

}  // namespace klangbild::dsp
