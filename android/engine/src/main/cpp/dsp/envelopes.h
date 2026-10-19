// Huellkurven der Art "eigen" (BAUPLAN-ANDROID T5.4): alle Fader-, EQ-, Filter- und Effekt-Verlaeufe
// einer Blende an `n` Stellen. Port von uebergang._huellen.
//
// Werte 0..1, float32 wie im Prototyp (numpy: float32-Arrays mit Python-Skalaren bleiben float32).
// Nicht gesetzte Kurven (`std::nullopt`) sind inaktiv und werden nicht gerechnet. Filter: 0 offen, 1 zu.
//
// Nur fuer Baker und Host-Test, nie im Audio-Callback.
#pragma once

#include <optional>
#include <vector>

#include "dsp/settings.h"

namespace klangbild::dsp {

using Curve = std::vector<float>;

struct Envelopes {
    Curve aVol, bVol;                                  // a_vol, b_vol: Lautstaerke (immer vorhanden)
    std::optional<Curve> aLow, bLow;                   // a_tief, b_tief: Tiefband (EQ)
    std::optional<Curve> aMid, bMid;                   // a_mitte, b_mitte
    std::optional<Curve> aHigh, bHigh;                 // a_hoch, b_hoch
    std::optional<Curve> aLowpass, aHighpass;          // a_tp, a_hp: Filter auf A
    std::optional<Curve> bLowpass, bHighpass;          // b_tp, b_hp: Filter auf B
    std::optional<Curve> aSend, bSend;                 // a_send, b_send: Effekt-Send
    std::optional<Curve> wetOff;                       // nass_ab: Ausblenden der Effektfahne
    std::optional<double> bReverse;                    // b_rueck: Anteil der Blende, an dem B einsetzt (Rueckhall)
};

/// `uebergang._huellen(e, takte, n, kante)`. `bars` = Takte der Blende, `n` = Stuetzstellen,
/// `edge` = Anteil der Blende fuer "harte" Kanten (KANTE_S * RATE / n bei Ton, 0,01 bei der Anzeige).
/// Wirft `std::invalid_argument` bei unbekannter `volume` oder `filter` (wie KeyError im Prototyp).
Envelopes envelopes(const Settings& settings, int bars, int n, double edge);

}  // namespace klangbild::dsp
