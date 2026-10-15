plugins {
    alias(libs.plugins.kotlin.jvm)
}

// :core ist reines Kotlin/JVM (BAUPLAN §3.2). Alle Tests laufen auf dem PC in
// Sekunden, ohne Geraet. Portiert aus prototyp/klangbild/*.py.
group = "de.klangbild"
version = "0.3.0"

kotlin {
    jvmToolchain(17)
    compilerOptions {
        // Goldene-Tests vergleichen Bit fuer Bit gegen Python-Ausgaben:
        // keine nicht-deterministischen Optimierungen, keine Streuung.
        allWarningsAsErrors = true
    }
}

dependencies {
    // compileOnly: JUnit-API nur für die Golden-Tests hier, nicht für :app.
    compileOnly(libs.junit.jupiter.api)
    testImplementation(libs.junit.jupiter)
    testImplementation(libs.junit.jupiter.params)
    testRuntimeOnly(libs.junit.jupiter.engine)
    testRuntimeOnly(libs.junit.platform.launcher)
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
    testLogging {
        events("passed", "skipped", "failed")
    }
}
