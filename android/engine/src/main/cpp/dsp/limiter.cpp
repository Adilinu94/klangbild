#include "dsp/limiter.h"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <vector>

#include "dsp/filter1d.h"

namespace klangbild::dsp {

void begrenzen(std::vector<float>& x, long long bis, double decke, int rate, int channels) {
    const std::size_t kan = static_cast<std::size_t>(std::max(1, channels));
    const long long frames = static_cast<long long>(x.size() / kan);
    bis = std::clamp<long long>(bis, 0, frames);
    if (bis <= 0) return;

    std::vector<float> spitze(static_cast<std::size_t>(bis));
    for (long long i = 0; i < bis; ++i) {
        float wert = 0.0f;
        for (std::size_t c = 0; c < kan; ++c) {
            wert = std::max(wert, std::abs(x[static_cast<std::size_t>(i) * kan + c]));
        }
        spitze[static_cast<std::size_t>(i)] = wert;
    }

    const int fenster = static_cast<int>(0.02 * static_cast<double>(rate)) | 1;   // 20 ms, ungerade
    const long long blk = 1LL << 16;
    std::vector<long long> starten;   // np.unique(... // blk) * blk
    for (long long i = 0; i < bis; ++i) {
        if (spitze[static_cast<std::size_t>(i)] > static_cast<float>(decke)) {
            const long long start = (i / blk) * blk;
            if (starten.empty() || starten.back() != start) starten.push_back(start);
        }
    }

    for (long long start : starten) {
        const long long lo = std::max<long long>(0, start - 2LL * fenster);
        const long long hi = std::min<long long>(bis, start + blk + 2LL * fenster);
        const long long ende = std::min<long long>(bis, start + blk);
        const std::vector<float> teil(spitze.begin() + static_cast<std::ptrdiff_t>(lo),
                                      spitze.begin() + static_cast<std::ptrdiff_t>(hi));
        const std::vector<float> maximum = maximumFilter1d(teil, fenster);
        std::vector<float> g(maximum.size());
        for (std::size_t k = 0; k < g.size(); ++k) {
            g[k] = static_cast<float>(std::min(1.0, decke / std::max(static_cast<double>(maximum[k]), 1e-9)));
        }
        g = minimumFilter1d(g, fenster);
        g = uniformFilter1d(g, fenster);
        for (long long i = start; i < ende; ++i) {
            const float gain = g[static_cast<std::size_t>(i - lo)];
            for (std::size_t c = 0; c < kan; ++c) x[static_cast<std::size_t>(i) * kan + c] *= gain;
        }
    }
}

}  // namespace klangbild::dsp
