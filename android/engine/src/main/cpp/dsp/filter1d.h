// 1-D-Filter wie scipy.ndimage (BAUPLAN-ANDROID T5.7/M6).
//
// maximum_filter1d, minimum_filter1d und uniform_filter1d mit mode="reflect" (Halb-Sample-
// Symmetrie, der Rand wird gespiegelt und wiederholt). Gleitendes Fenster in O(n) statt O(n*size).
#pragma once

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <deque>
#include <vector>

namespace klangbild::dsp {

/// scipy.ndimage "reflect": ... b a | a b c d | d c ... (Rand doppelt).
inline std::size_t reflectIndex(long long i, std::size_t n) {
    if (n <= 1) return 0;
    const long long periode = static_cast<long long>(2 * n);
    long long k = i % periode;
    if (k < 0) k += periode;
    return static_cast<std::size_t>(k < static_cast<long long>(n) ? k : periode - 1 - k);
}

/// Gepolsterte Kopie fuer ein Fenster der Breite `size` (ungerade): ext[j] = a[reflect(j - half)].
inline std::vector<float> reflected(const std::vector<float>& a, int size) {
    const int half = size / 2;
    std::vector<float> ext(a.size() + 2 * static_cast<std::size_t>(half));
    for (std::size_t j = 0; j < ext.size(); ++j) {
        ext[j] = a[reflectIndex(static_cast<long long>(j) - half, a.size())];
    }
    return ext;
}

inline std::vector<float> maximumFilter1d(const std::vector<float>& a, int size) {
    if (a.empty() || size <= 1) return a;
    const std::vector<float> ext = reflected(a, size);
    std::vector<float> aus(a.size());
    std::deque<std::size_t> dq;
    for (std::size_t j = 0; j < ext.size(); ++j) {
        while (!dq.empty() && ext[dq.back()] <= ext[j]) dq.pop_back();
        dq.push_back(j);
        if (dq.front() + static_cast<std::size_t>(size) <= j) dq.pop_front();
        if (j + 1 >= static_cast<std::size_t>(size)) aus[j + 1 - static_cast<std::size_t>(size)] = ext[dq.front()];
    }
    return aus;
}

inline std::vector<float> minimumFilter1d(const std::vector<float>& a, int size) {
    if (a.empty() || size <= 1) return a;
    const std::vector<float> ext = reflected(a, size);
    std::vector<float> aus(a.size());
    std::deque<std::size_t> dq;
    for (std::size_t j = 0; j < ext.size(); ++j) {
        while (!dq.empty() && ext[dq.back()] >= ext[j]) dq.pop_back();
        dq.push_back(j);
        if (dq.front() + static_cast<std::size_t>(size) <= j) dq.pop_front();
        if (j + 1 >= static_cast<std::size_t>(size)) aus[j + 1 - static_cast<std::size_t>(size)] = ext[dq.front()];
    }
    return aus;
}

inline std::vector<float> uniformFilter1d(const std::vector<float>& a, int size) {
    if (a.empty() || size <= 1) return a;
    const std::vector<float> ext = reflected(a, size);
    std::vector<float> aus(a.size());
    double summe = 0.0;
    for (std::size_t j = 0; j < ext.size(); ++j) {
        summe += static_cast<double>(ext[j]);
        if (j >= static_cast<std::size_t>(size)) summe -= static_cast<double>(ext[j - static_cast<std::size_t>(size)]);
        if (j + 1 >= static_cast<std::size_t>(size)) {
            aus[j + 1 - static_cast<std::size_t>(size)] = static_cast<float>(summe / static_cast<double>(size));
        }
    }
    return aus;
}

}  // namespace klangbild::dsp
