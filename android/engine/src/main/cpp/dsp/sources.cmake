# Quellen der DSP-Bibliothek (BAUPLAN-ANDROID M5). Eine Liste fuer beide Builds:
#  - Geraet: engine/src/main/cpp/CMakeLists.txt haengt sie an die Bibliothek `klangbild`
#  - Host-Test: engine/src/test/cpp/CMakeLists.txt baut daraus die Bibliothek `klangbild_dsp`
# Header-only-Teile (curves.h) stehen hier nicht.
set(KLANGBILD_DSP_SOURCES
    ${CMAKE_CURRENT_LIST_DIR}/filters.cpp
)
