// Denormale Zahlen im Audio-Thread abschalten (BAUPLAN-ANDROID §3.3, djay §50):
// Flush-to-Zero (FTZ), auf x86 zusaetzlich Denormals-Are-Zero (DAZ). Das Register gilt je Thread,
// also im Callback-Thread und in Baker-Threads einmal setzen.
//
// Aufruf ist billig und allokationsfrei, darf im Callback stehen.
#pragma once

#include <cstdint>

#if defined(__SSE__) || defined(_M_X64)
#include <xmmintrin.h>
#endif

namespace klangbild {

inline void enableFlushToZero() noexcept {
#if defined(__aarch64__)
    // FPCR.FZ ist Bit 24.
    uint64_t fpcr = 0;
    __asm__ __volatile__("mrs %0, fpcr" : "=r"(fpcr));
    fpcr |= (uint64_t{1} << 24);
    __asm__ __volatile__("msr fpcr, %0" : : "r"(fpcr));
#elif defined(__SSE__) || defined(_M_X64)
    // MXCSR: FTZ = Bit 15, DAZ = Bit 6.
    _mm_setcsr(_mm_getcsr() | 0x8040u);
#endif
}

}  // namespace klangbild
