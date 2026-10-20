# Quellen der DSP-Bibliothek (BAUPLAN-ANDROID M5). Eine Liste fuer beide Builds:
#  - Geraet: engine/src/main/cpp/CMakeLists.txt haengt sie an die Bibliothek `klangbild`
#  - Host-Test: engine/src/test/cpp/CMakeLists.txt baut daraus die Bibliothek `klangbild_dsp`
# Header-only-Teile (curves.h) stehen hier nicht.
set(KLANGBILD_DSP_SOURCES
    ${CMAKE_CURRENT_LIST_DIR}/filters.cpp
    ${CMAKE_CURRENT_LIST_DIR}/mixing.cpp
    ${CMAKE_CURRENT_LIST_DIR}/envelopes.cpp
    ${CMAKE_CURRENT_LIST_DIR}/sweep.cpp
    ${CMAKE_CURRENT_LIST_DIR}/fft.cpp
    ${CMAKE_CURRENT_LIST_DIR}/effects.cpp
    ${CMAKE_CURRENT_LIST_DIR}/level.cpp
    ${CMAKE_CURRENT_LIST_DIR}/automation.cpp
    ${CMAKE_CURRENT_LIST_DIR}/resample.cpp
    ${CMAKE_CURRENT_LIST_DIR}/warp.cpp
    ${CMAKE_CURRENT_LIST_DIR}/loop.cpp
    ${CMAKE_CURRENT_LIST_DIR}/loopchoice.cpp
    ${CMAKE_CURRENT_LIST_DIR}/introloop.cpp
    ${CMAKE_CURRENT_LIST_DIR}/tricks.cpp
    ${CMAKE_CURRENT_LIST_DIR}/mischen_eigen.cpp
    ${CMAKE_CURRENT_LIST_DIR}/raster.cpp
    ${CMAKE_CURRENT_LIST_DIR}/limiter.cpp
    ${CMAKE_CURRENT_LIST_DIR}/backen.cpp
)

# numpy verschmilzt a*b + c nie zu einem FMA; Clang auf ARM taete es standardmaessig, und die Haupt-CMake
# setzt fuer das ganze Ziel -ffp-contract=fast. Fuer gleiche Rundung wie die Python-Referenz bekommen die
# DSP-Quellen -ffp-contract=off als Datei-Option; sie steht nach den Ziel-Optionen und gewinnt
# (BAUPLAN §13, float32 vs. float64). Gilt in dem Verzeichnis, das diese Datei einbindet.
if(CMAKE_CXX_COMPILER_ID MATCHES "Clang|GNU")
    set_source_files_properties(${KLANGBILD_DSP_SOURCES} PROPERTIES COMPILE_OPTIONS "-ffp-contract=off")
endif()
