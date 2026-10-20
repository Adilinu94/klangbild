# Host-Tests der nativen Engine (BAUPLAN-ANDROID §12.1).
#
# Diese Quellen laufen NUR auf dem PC (GoogleTest), nicht auf dem Geraet.
# Sie kompilieren denselben Header (golden.h) wie die spaeteren DSP-Tests und
# lesen die Python-Referenzdaten aus android/testdata/golden (T0.2).
#
# Aufruf ueber den Gradle-Task hostTest in :engine:
#   ./gradlew :engine:hostTest
# Direkt:
#   cmake -S android/engine/src/test/cpp -B build -DKLINGBILD_GOLDENDIR=<...>
#   cmake --build build && cmake --build build --target test
cmake_minimum_required(VERSION 3.22)
project(klangbild_hosttest LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

# Der Golden-Ordner wird von Gradle gesetzt. Ohne Angabe ein sinnvoller Default
# relativ zu diesem Ordner (android/testdata/golden).
if(NOT DEFINED KLINGBILD_GOLDENDIR)
    set(KLINGBILD_GOLDENDIR "${CMAKE_CURRENT_SOURCE_DIR}/../../../testdata/golden")
endif()
message(STATUS "Golden-Ordner: ${KLINGBILD_GOLDENDIR}")

# GoogleTest per FetchContent (BAUPLAN §12.1). Version aus dem Katalog (1.17.0).
# Braucht beim ersten Lauf Netzwerkzugriff auf dem Build-PC, nicht auf dem Geraet.
include(FetchContent)
FetchContent_Declare(
    googletest
    GIT_REPOSITORY https://github.com/google/googletest.git
    GIT_TAG        v1.17.0
    GIT_SHALLOW    TRUE
)
# Windows: gemeinsame CRT, damit gtest_static und unser Test zusammenpassen.
set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(googletest)

enable_testing()

add_executable(klangbild_hosttest
    golden_test.cpp
)

target_include_directories(klangbild_hosttest PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}
)

# Denselben Golden-Ordner auch als Umgebungsvariable, falls direkter Aufruf.
target_compile_definitions(klangbild_hosttest PRIVATE
    KLINGBILD_GOLDENDIR_DEFAULT="${KLINGBILD_GOLDENDIR}"
)

target_link_libraries(klangbild_hosttest PRIVATE
    GTest::gtest_main
)

include(GoogleTest)
gtest_discover_tests(klangbild_hosttest)

# Der Gradle-Task hostTest ruft `--build ... --target test` auf. Diesen Target
# legt CTest selbst an (enable_testing() oben), darum hier NICHT erneut anlegen
# (sonst Konflikt). gtest_discover_tests haengt die Faelle dort ein.

# Callback-Logik, OutputRing, Rampen (BAUPLAN T1.1/T1.2): dieselben Header wie das Geraet
# (src/main/cpp). Eigenes Test-Ziel, weil es weder Oboe noch die Golden-Daten braucht.
find_package(Threads REQUIRED)
add_executable(playback_core_test
    playback_core_test.cpp
)
target_compile_definitions(playback_core_test PRIVATE KLINGBILD_TEST=1)
target_include_directories(playback_core_test PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/../../main/cpp
)
if(CMAKE_CXX_COMPILER_ID MATCHES "Clang|GNU")
    target_compile_options(playback_core_test PRIVATE -Wall -Wextra -Wno-unused-parameter)
elseif(MSVC)
    target_compile_options(playback_core_test PRIVATE /W4)
endif()
target_link_libraries(playback_core_test PRIVATE GTest::gtest_main Threads::Threads)
gtest_discover_tests(playback_core_test)

# DSP-Port (BAUPLAN M5): Golden-Tests der portierten Funktionen. Dieselben Quellen wie auf dem Geraet
# (src/main/cpp/dsp); die Liste steht in dsp/sources.cmake und dient beiden Builds.
include(${CMAKE_CURRENT_SOURCE_DIR}/../../main/cpp/dsp/sources.cmake)
if(KLANGBILD_DSP_SOURCES)
    add_library(klangbild_dsp STATIC ${KLANGBILD_DSP_SOURCES})
    target_include_directories(klangbild_dsp PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/../../main/cpp)
    if(CMAKE_CXX_COMPILER_ID MATCHES "Clang|GNU")
        target_compile_options(klangbild_dsp PRIVATE -Wall -Wextra)
    elseif(MSVC)
        target_compile_options(klangbild_dsp PRIVATE /W4)
    endif()
endif()
add_executable(dsp_golden_test
    dsp_golden_test.cpp
)
target_include_directories(dsp_golden_test PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_CURRENT_SOURCE_DIR}/../../main/cpp
)
target_compile_definitions(dsp_golden_test PRIVATE
    KLINGBILD_GOLDENDIR_DEFAULT="${KLINGBILD_GOLDENDIR}"
    KLINGBILD_HALL_IR_ASSET="${CMAKE_CURRENT_SOURCE_DIR}/../../main/assets/hall_ir.f32"
)
if(CMAKE_CXX_COMPILER_ID MATCHES "Clang|GNU")
    target_compile_options(dsp_golden_test PRIVATE -Wall -Wextra -Wno-unused-parameter)
elseif(MSVC)
    target_compile_options(dsp_golden_test PRIVATE /W4)
endif()
target_link_libraries(dsp_golden_test PRIVATE GTest::gtest_main)
if(TARGET klangbild_dsp)
    target_link_libraries(dsp_golden_test PRIVATE klangbild_dsp)
endif()
gtest_discover_tests(dsp_golden_test)
