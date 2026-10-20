# Nativer Kern: libklangbild.so (BAUPLAN §3.2, §5).
#
# Oboe, Decoder, PCM-Cache, Timeline, Feeder, Baker, DSP und Analyse-DSP liegen
# in einem gemeinsamen CMake-Projekt, damit die Host-Tests (src/test/cpp) genau
# dieselben Quellen kompilieren wie das Geraet (djay-Lehre §74: wenige große
# Bibliotheken laden schneller).
cmake_minimum_required(VERSION 3.22)
project(klangbild LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

add_library(klangbild SHARED
    jni_bridge.cpp
    oboe_output.cpp
)

# DSP-Port (M5): dieselbe Quellenliste wie der Host-Test.
include(${CMAKE_CURRENT_SOURCE_DIR}/dsp/sources.cmake)
target_sources(klangbild PRIVATE ${KLANGBILD_DSP_SOURCES})

# Oboe als Quellcode (Apache-2.0), statisch gelinkt wie bei djay §61: nur so ist
# auch oboe::resampler::MultiChannelResampler nutzbar (im Prefab-Paket privat).
# Liegt unter third_party/oboe (Version 1.11.0). Holen:
#   git clone --branch 1.11.0 --depth 1 https://github.com/google/oboe third_party/oboe
# Signalsmith Stretch (MIT) liegt unter third_party/signalsmith-stretch (Quelle aus dem
# python-stretch-0.3.1-Sdist, also dieselbe Version wie die Desktop-Referenz).
# KissFFT (BSD-3) folgt bei Bedarf.
set(KLANGBILD_OBOE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/third_party/oboe)
if(NOT EXISTS ${KLANGBILD_OBOE_DIR}/CMakeLists.txt)
    message(FATAL_ERROR
        "Oboe fehlt unter ${KLANGBILD_OBOE_DIR}. Holen mit: "
        "git clone --branch 1.11.0 --depth 1 https://github.com/google/oboe ${KLANGBILD_OBOE_DIR}")
endif()
add_subdirectory(${KLANGBILD_OBOE_DIR} oboe-build)
target_link_libraries(klangbild oboe)

if(NOT DEFINED KLINGBILD_TEST)
    target_compile_options(klangbild PRIVATE
        -fvisibility=hidden
        -ffile-prefix-map=${CMAKE_CURRENT_SOURCE_DIR}=.
    )
endif()

# clang/gcc-Flachen: -O3 und -ffp-contract=fast (djay §50).
# KEIN -ffast-math: das wuerde die NaN-Pruefungen der Analyse kippen (§3.3).
if(CMAKE_CXX_COMPILER_ID MATCHES "Clang|GNU")
    target_compile_options(klangbild PRIVATE -O3 -ffp-contract=fast -Wall -Wextra)
    target_compile_definitions(klangbild PRIVATE KLINGBILD_IS_CLANG=1)
elseif(MSVC)
    target_compile_options(klangbild PRIVATE /O2 /W4)
endif()

find_library(klangbild-log-lib log)
if(klangbild-log-lib)
    target_link_libraries(klangbild ${klangbild-log-lib})
endif()

target_include_directories(klangbild PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_CURRENT_SOURCE_DIR}/third_party/signalsmith-stretch
)
