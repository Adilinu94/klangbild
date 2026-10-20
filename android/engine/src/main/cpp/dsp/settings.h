// Einstellungen, soweit die DSP-Funktionen sie lesen (BAUPLAN-ANDROID T5.4 ff.).
//
// Gegenstueck zu einstellungen.Einstellungen im Python-Prototyp. Hier steht nur, was Huellkurven, Loops und
// `mischen_eigen` brauchen; die Regie und die Oberflaeche (Kotlin, :core) haben ihre eigene, vollstaendige Form
// und fuellen dieses Struct beim Uebergeben an den Baker. Die Werte der Auswahlfelder sind die gleichen
// Bezeichner wie im Prototyp (z. B. "nahtlos", "bass_mitte"): sie sind Daten, keine Namen im Code.
#pragma once

#include <string>

namespace klangbild::dsp {

struct Settings {
    std::string art = "auto";         // art: Uebergangsart (nur loop_info liest sie)
    std::string volume = "nahtlos";   // lautstaerke: Verlauf der Fader (nahtlos, linear, hart_aus, drop, ...)
    std::string eq = "bass_mitte";    // eq: Bass-/Band-Tausch (profi, bass_mitte, drei_band, ...); Standard wie Python
    std::string filter = "keiner";    // filter: tp_aus, hp_ein, hp_aus_reso, ...
    std::string effect = "keiner";    // effekt: z. B. "echo75_ende_aus", "hall_ende_ab"
    std::string effectIn = "keiner";  // effekt_ein: "keiner", "hall", "rueckhall"
    std::string loop = "keiner";      // loop: "1", "2", "4", ..., "rolle", "auto", "keiner"
    std::string trick = "keiner";     // trick: "bremse", "riser", "wechsel", "teaser", ...
    int bassBar = -1;                 // bass_takt: Takt des Bass-Tauschs (-1 = Standard)
    int vocalBar = -1;                // gesang_takt: Takt, auf den Gesangs-/Drop-Uebergaben zielen
    int loopStart = -1;               // loop_start
    int loopIn = 0;                   // loop_ein: B-Intro-Schleife, Takte
    int loopInTimes = 0;              // loop_ein_mal: Wiederholungen
    bool keylock = true;              // keylock: Tonhoehe halten beim Dehnen (Warp/Loop)
    std::string ausstieg = "outro";   // ausstieg: outro, phrase, vor_ende
    int vorEndeTakte = 16;            // vor_ende_takte
    std::string einstieg = "intro";   // einstieg: intro, drop
    std::string weiterAb = "phrase";  // weiter_ab: takt, phrase
    int takte = 16;                   // takte: Laenge der Blende
    int weiterTakte = 8;              // weiter_takte: Laenge bei WEITER
    double maxBpm = 5.0;              // max_bpm: erlaubter Tempo-Abstand
    std::string tempoModus = "rampe"; // tempo_modus: b_an_a, a_an_b, rampe, vorlauf
    bool stems = true;                // stems: Stem-Uebergaenge erlaubt
    std::string modus = "ausgewogen"; // modus: manuell, kurz, ausgewogen, lang (Regie)
};

}  // namespace klangbild::dsp
