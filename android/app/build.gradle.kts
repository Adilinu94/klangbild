plugins {
    alias(libs.plugins.android.application)
    // AGP 9 bringt Kotlin-Unterstuetzung mit (org.jetbrains.kotlin.android entfaellt).
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.ksp)
}

// :app: Compose-Oberflaeche, MediaSessionService, KlangbildPlayer,
// AutoDjController, Room, WorkManager (BAUPLAN §3.2).
group = "de.klangbild"
version = "0.3.0"

android {
    namespace = "de.klangbild"
    compileSdk = 37

    defaultConfig {
        applicationId = "de.klangbild"   // Platzhalter, vor dem Store-Eintrag festzulegen (E2)
        minSdk = 29
        targetSdk = 37
        versionCode = 1
        versionName = "0.1.0"

        // BAUPLAN §3.3: arm64-v8a für das Gerät, x86_64 nur für Emulator-Tests.
        ndk {
            abiFilters += listOf("arm64-v8a", "x86_64")
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
        debug {
            isMinifyEnabled = false
        }
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    // Nativer Code liegt nur in :engine (ein CMake-Projekt, ein libklangbild.so,
    // djay-Lehre §74). Die App bindet das AAR ein und lädt darüber die Bibliothek.

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    packaging {
        jniLibs.useLegacyPackaging = false
        resources.excludes += setOf(
            "META-INF/LICENSE.md",
            "META-INF/LICENSE-notice.md",
            "META-INF/NOTICE.md",
            "META-INF/DEPENDENCIES",
        )
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
    }
}

dependencies {
    implementation(project(":core"))
    implementation(project(":engine"))

    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.navigation.compose)

    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.ui.graphics)
    implementation(libs.compose.foundation)
    implementation(libs.compose.material3)
    implementation(libs.compose.ui.tooling.preview)
    debugImplementation(libs.compose.ui.tooling)

    implementation(libs.media3.session)
    implementation(libs.media3.common)
    implementation(libs.media3.ui)

    implementation(libs.room.runtime)
    implementation(libs.room.ktx)
    ksp(libs.room.compiler)
    implementation(libs.work.runtime.ktx)

    implementation(libs.coil.compose)
    implementation(libs.coil.core)
    implementation(libs.reorderable)

    // M10 (T10.6): ONNX Runtime Android (Beat This! small0). Erst dort dazunehmen:
    // dessen Manifest fordert INTERNET an, was BAUPLAN §0 Regel 6 verbietet.

    testImplementation(libs.junit.jupiter)
    testRuntimeOnly(libs.junit.jupiter.engine)
    testRuntimeOnly(libs.junit.platform.launcher)
    androidTestImplementation(platform(libs.compose.bom))
    androidTestImplementation(libs.androidx.test.junit)
    androidTestImplementation(libs.compose.ui.test.junit4)
    debugImplementation(libs.compose.ui.test.manifest)
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}
