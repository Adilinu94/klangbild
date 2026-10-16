plugins {
    alias(libs.plugins.kotlin.jvm)
    alias(libs.plugins.kotlin.serialization)
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
    // JSON: dieselben Formate wie der Desktop (BAUPLAN §4.2): Einstellungen,
    // Profile, Golden-Daten. Golden-Export schreibt striktes JSON (kein NaN).
    implementation(libs.kotlinx.serialization.json)

    // compileOnly: JUnit-API nur für die Golden-Tests hier, nicht für :app.
    compileOnly(libs.junit.jupiter.api)
    testImplementation(libs.junit.jupiter)
    testImplementation(libs.junit.jupiter.params)
    testRuntimeOnly(libs.junit.jupiter.engine)
    testRuntimeOnly(libs.junit.platform.launcher)
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
    // Der Golden-Leser findet den Datenbestand über diese Eigenschaft (T0.3).
    // Fehlt er, überspringen die Leser-Tests statt falsch rot zu werden.
    systemProperty("klangbild.goldendir", rootProject.layout.projectDirectory.dir("testdata/golden").asFile.absolutePath)
    testLogging {
        events("passed", "skipped", "failed")
    }
}
