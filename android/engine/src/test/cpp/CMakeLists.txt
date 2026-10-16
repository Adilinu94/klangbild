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
