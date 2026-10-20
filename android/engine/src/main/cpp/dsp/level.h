// Pegel je Takt und Buckel-Deckelung (BAUPLAN-ANDROID T5.7).
//
// Port von uebergang._takt_db, uebergang._deckeln und uebergang._trocken.
// Signale sind Stereo, float32, interleaved (L,R,L,R,...); gerechnet wird in double, wie im
// Prototyp, erst das Ergebnis wird float32.
//
// Nur fuer Baker und Host-Test, nie im Audio-Callback (allokiert, braucht die ganze Blende).
#pragma once

#include <span>
#include <vector>

#include "dsp/envelopes.h"

namespace klangbild::dsp {

/// `uebergang._takt_db`: Pegel je Takt in dBFS (mittlere Leistung beider Kanaele).
/// `taktN` sind Taktgrenzen in Frames, begrenzt auf die Laenge von `x`; Ergebnis hat
/// `taktN.size() - 1` Werte. Leer, wenn `taktN` weniger als zwei Grenzen hat.
std::vector<double> taktDb(std::span<const float> x, std::span<const int> taktN);

/// `uebergang._deckeln`: je Takt hoechstens so laut wie der lautere der beiden Songs (`ra`, `rb`)
/// plus `toleranz`, hoechstens `maxDb` leiser. Nur absenken, weich ueber die Taktmitten.
/// Liefert eine Kopie von `y`, wenn nichts zu deckeln ist. `ra`/`rb` duerfen kuerzer sein.
std::vector<float> deckeln(std::span<const float> y, std::span<const float> ra, std::span<const float> rb,
                           std::span<const int> taktN, double toleranz = 1.5, double maxDb = 6.0);

/// `uebergang._trocken`: je Band EQ-Kurve x Fader, je Band gegen Buckel gedeckelt und summiert.
/// `a` und `b` muessen dieselbe Laenge haben wie die Kurven in `h`.
std::vector<float> trocken(std::span<const float> a, std::span<const float> b, const Envelopes& h,
                           std::span<const int> taktN);

}  // namespace klangbild::dsp
