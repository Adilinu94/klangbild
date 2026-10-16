import java.util.Properties

plugins {
    alias(libs.plugins.android.library)
    // AGP 9 bringt Kotlin-Unterstuetzung mit (org.jetbrains.kotlin.android entfaellt).
}

// :engine: ein nativer Bibliothekskern (libklangbild.so) plus die JNI-Fassade
// (BAUPLAN §3.2). Oboe und Decoder liegen hier, die App fasst sie nur an.
group = "de.klangbild"
version = "0.3.0"

android {
    namespace = "de.klangbild.engine"
    compileSdk = 37

    defaultConfig {
        minSdk = 29
        // NDK r28 oder neuer: 16-KB-Seitenausrichtung ist ab r28 Standard (BAUPLAN §3.3)
        ndk {
            abiFilters += listOf("arm64-v8a", "x86_64")
        }
        ndkVersion = "28.2.13676358"
        externalNativeBuild {
            cmake {
                // Denormals aus und -O3 fuer Baker und Callback (djay §50), KEIN -ffast-math.
                cppFlags += "-O3 -ffp-contract=fast -Wall -Wextra -Wno-unused-parameter"
                arguments += listOf("-DCMAKE_CXX_STANDARD=20")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }

    externalNativeBuild {
        cmake {
            path = file("src/main/cpp/CMakeLists.txt")
            version = "3.22.1"
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    testOptions {
        // Host-C++-Tests laufen ueber CMake (Task hostTest), nicht als Unit-Test.
        unitTests.all { it.enabled = false }
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
        allWarningsAsErrors = true
    }
}

dependencies {
    implementation(libs.media3.common)
    testImplementation(libs.junit.jupiter)
    testRuntimeOnly(libs.junit.jupiter.engine)
    testRuntimeOnly(libs.junit.platform.launcher)
}

// ---------------------------------------------------------------------------
// Host-Tests (BAUPLAN §12.1): C++-Golden-Tests gegen Python-Referenzdaten.
// Laufen auf dem PC ueber CMake + GoogleTest, nicht auf dem Geraet.
// Voraussetzung: Host-Compiler (MSVC/MinGW/clang) und ein auffindbares CMake.
// ---------------------------------------------------------------------------

/**
 * Liefert den Android-SDK-Pfad aus local.properties oder ANDROID_HOME, oder null.
 *
 * `java.util.Properties` loest die in local.properties ueblichen Escapes auf
 * (`sdk.dir=C\:\\Users\\...`), ein einfaches Zeilen-Lesen nicht.
 */
fun sdkPfad(): String? {
    val lokal = rootProject.file("local.properties")
    if (lokal.isFile) {
        val props = Properties()
        lokal.inputStream().use { props.load(it) }
        val wert = props.getProperty("sdk.dir")?.trim()
        if (!wert.isNullOrBlank()) return wert
    }
    return System.getenv("ANDROID_HOME") ?: System.getenv("ANDROID_SDK_ROOT")
}

/** Liefert den Pfad zu einem auffindbaren Host-CMake, oder null. */
fun hostCmake(): String? {
    val prop = project.findProperty("klangbild.cmake") as String?
    if (prop != null) return prop
    val sdk = sdkPfad() ?: return null
    val cms = file("$sdk/cmake").listFiles() ?: return null
    val exe = if (System.getProperty("os.name").startsWith("Win", true)) "cmake.exe" else "cmake"
    val beste = cms
        .filter { it.isDirectory && it.name.firstOrNull()?.isDigit() == true }
        .map { d -> d to d.name.split(".").takeWhile { it.toIntOrNull() != null }.joinToString(".") { it.padStart(4, '0') } }
        .maxByOrNull { (_, sortierung) -> sortierung }?.first ?: return null
    val pfad = file("${beste.absolutePath}/bin/$exe")
    return pfad.takeIf { it.isFile }?.absolutePath
}

val hostTest = tasks.register("hostTest") {
    group = "verification"
    description = "Baut und laeuft die C++-Golden-Tests auf dem Host (CMake + GoogleTest)."

    // Pfade als einfache Werte festhalten (configuration-cache-fest).
    val quelleDir = file("src/test/cpp").absolutePath
    val cmakeListe = "$quelleDir/CMakeLists.txt"
    val bau = layout.buildDirectory.dir("hosttest").get().asFile.absolutePath
    val goldendaten = rootProject.layout.projectDirectory.dir("testdata/golden").asFile.absolutePath
    val exe = hostCmake()

    inputs.dir(quelleDir)
    inputs.dir(goldendaten)
    outputs.dir(bau)

    val ueberspringen = project.findProperty("klangbild.skipHostTest") == "true"
    onlyIf { !ueberspringen }

    // Dieser Task ruft externe Prozesse auf und liest den SDK-Pfad aus der
    // Umgebung; er ist bewusst nicht configuration-cache-faehig (Gradle-API).
    notCompatibleWithConfigurationCache("Ruft CMake/CTest als externe Prozesse auf.")

    doLast {
        check(File(cmakeListe).exists()) { "Host-Test-Quelle fehlt: $cmakeListe" }
        val cmake = exe ?: throw GradleException(
            "Kein Host-CMake gefunden. SDK-CMake installieren oder " +
                "-Pklangbild.cmake=<pfad/zum/cmake> setzen."
        )

        fun prozess(vararg argumente: String) {
            val p = ProcessBuilder(*argumente).redirectErrorStream(true).start()
            val ausgabe = p.inputStream.bufferedReader().readText()
            val code = p.waitFor()
            if (code != 0) {
                throw GradleException(
                    "Host-Prozess mit Code $code beendet: ${argumente.joinToString(" ")}\n$ausgabe"
                )
            }
        }

        prozess(
            cmake, "-S", quelleDir, "-B", bau,
            "-DCMAKE_BUILD_TYPE=Release",
            "-DKLINGBILD_GOLDENDIR=$goldendaten"
        )
        prozess(cmake, "--build", bau, "--config", "Release", "--parallel")
        prozess(cmake, "--build", bau, "--config", "Release", "--target", "test")
    }
}
