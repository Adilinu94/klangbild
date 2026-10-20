#include "bake_api.h"

#include <array>
#include <cstddef>
#include <exception>
#include <map>
#include <string>
#include <vector>

#include "dsp/automation.h"
#include "json.h"

namespace klangbild {
namespace {

void liesText(const Json& e, const char* schluessel, std::string& ziel) {
    if (const Json* v = e.finde(schluessel)) {
        if (v->istText()) ziel = v->text;
    }
}

void liesZahl(const Json& e, const char* schluessel, double& ziel) {
    if (const Json* v = e.finde(schluessel)) {
        if (v->istZahl()) ziel = v->zahl;
    }
}

void liesGanz(const Json& e, const char* schluessel, int& ziel) {
    if (const Json* v = e.finde(schluessel)) {
        if (v->istZahl()) ziel = static_cast<int>(v->zahl);
    }
}

void liesWahr(const Json& e, const char* schluessel, bool& ziel) {
    if (const Json* v = e.finde(schluessel)) {
        if (v->art == Json::Art::Bool) ziel = v->wahr;
    }
}

dsp::Settings settingsAus(const Json& e) {
    dsp::Settings s;
    liesText(e, "art", s.art);
    liesText(e, "lautstaerke", s.volume);
    liesText(e, "eq", s.eq);
    liesText(e, "filter", s.filter);
    liesText(e, "effekt", s.effect);
    liesText(e, "effekt_ein", s.effectIn);
    liesText(e, "loop", s.loop);
    liesText(e, "trick", s.trick);
    liesGanz(e, "bass_takt", s.bassBar);
    liesGanz(e, "gesang_takt", s.vocalBar);
    liesGanz(e, "loop_start", s.loopStart);
    liesGanz(e, "loop_ein", s.loopIn);
    liesGanz(e, "loop_ein_mal", s.loopInTimes);
    liesWahr(e, "keylock", s.keylock);
    liesText(e, "ausstieg", s.ausstieg);
    liesGanz(e, "vor_ende_takte", s.vorEndeTakte);
    liesText(e, "einstieg", s.einstieg);
    liesText(e, "weiter_ab", s.weiterAb);
    liesGanz(e, "takte", s.takte);
    liesGanz(e, "weiter_takte", s.weiterTakte);
    liesZahl(e, "max_bpm", s.maxBpm);
    liesText(e, "tempo_modus", s.tempoModus);
    liesWahr(e, "stems", s.stems);
    liesText(e, "modus", s.modus);
    return s;
}

dsp::Eintrag eintragAus(const Json& j) {
    dsp::Eintrag e;
    if (const Json* v = j.finde("id"); v != nullptr && v->istZahl()) e.id = static_cast<int>(v->zahl);
    liesText(j, "pfad", e.pfad);
    liesZahl(j, "bpm", e.bpm);
    liesText(j, "camelot", e.camelot);
    if (const Json* v = j.finde("downbeats")) e.downbeats = v->zahlen();
    if (const Json* v = j.finde("abschnitte")) e.abschnitte = v->zahlen();
    if (const Json* v = j.finde("fein")) {
        for (const Json& paar : v->eintraege) {
            const std::vector<double> werte = paar.zahlen();
            if (werte.size() == 2) e.fein.push_back({werte[0], werte[1]});
        }
    }
    return e;
}

std::string liste(const std::vector<double>& werte) {
    std::string s = "[";
    for (std::size_t i = 0; i < werte.size(); ++i) {
        if (i != 0) s += ",";
        s += jsonZahl(werte[i]);
    }
    s += "]";
    return s;
}

std::string kurvenSeite(const std::map<std::string, dsp::Curve>& seite) {
    std::string s = "{";
    bool erst = true;
    for (const auto& [name, kurve] : seite) {
        if (!erst) s += ",";
        erst = false;
        s += jsonText(name) + ":[";
        for (std::size_t i = 0; i < kurve.size(); ++i) {
            if (i != 0) s += ",";
            s += jsonZahl(static_cast<double>(kurve[i]));
        }
        s += "]";
    }
    s += "}";
    return s;
}

std::string kurvenJson(const dsp::Automation& k) {
    return "{\"a\":" + kurvenSeite(k.a) + ",\"b\":" + kurvenSeite(k.b) + "}";
}

}  // namespace

BakeAnfrage parseBakeAnfrage(std::string_view plan) {
    const Json wurzel = parseJson(plan);
    if (!wurzel.istObjekt()) throw JsonFehler("Uebergangsplan ist kein Objekt.");
    BakeAnfrage anfrage;
    if (const Json* j = wurzel.finde("a")) anfrage.a = eintragAus(*j);
    if (const Json* j = wurzel.finde("b")) anfrage.b = eintragAus(*j);
    if (const Json* j = wurzel.finde("einst")) anfrage.einst = settingsAus(*j);
    if (const Json* j = wurzel.finde("abS"); j != nullptr && j->istZahl()) anfrage.abS = j->zahl;
    if (const Json* j = wurzel.finde("ausS"); j != nullptr && j->istZahl()) anfrage.ausS = j->zahl;
    if (const Json* j = wurzel.finde("einS"); j != nullptr && j->istZahl()) anfrage.einS = j->zahl;
    if (const Json* j = wurzel.finde("weiter"); j != nullptr && j->art == Json::Art::Bool) anfrage.weiter = j->wahr;
    return anfrage;
}

BakeErgebnis bakeTransition(const BakeAnfrage& anfrage, std::span<const float> aAudio,
                            std::span<const float> bAudio, std::span<const float> hallIr,
                            std::span<const float> riserNoise, int rate) {
    BakeErgebnis ergebnis;
    try {
        dsp::Spur spur = dsp::rohSpur(anfrage.a, std::vector<float>(aAudio.begin(), aAudio.end()), rate);
        std::vector<float> bPuffer(bAudio.begin(), bAudio.end());
        dsp::Gebacken gebacken = dsp::backen(
            spur, anfrage.b, bPuffer, anfrage.einst, anfrage.abS, anfrage.weiter, anfrage.ausS,
            anfrage.einS, hallIr, riserNoise, rate);
        ergebnis.ok = true;
        ergebnis.startN = gebacken.startN;
        ergebnis.orig = std::move(gebacken.spur.orig);
        ergebnis.buf = std::move(gebacken.spur.buf);
        ergebnis.audio = std::move(gebacken.spur.puffer);
        ergebnis.info = infoJson(gebacken.info);
    } catch (const std::exception& fehler) {
        ergebnis.ok = false;
        ergebnis.fehler = fehler.what();
    }
    return ergebnis;
}

std::string infoJson(const dsp::BackInfo& i) {
    std::string s = "{";
    s += "\"art\":" + jsonText(i.art);
    s += ",\"takte\":" + std::to_string(i.takte);
    s += ",\"sync\":" + std::string(i.sync ? "true" : "false");
    s += ",\"bpm_a\":" + jsonZahl(i.bpmA);
    s += ",\"bpm_b\":" + jsonZahl(i.bpmB);
    s += ",\"modus\":" + jsonText(i.modus);
    s += ",\"stems\":" + std::string(i.stems ? "true" : "false");
    if (!i.hinweis.empty()) s += ",\"hinweis\":" + jsonText(i.hinweis);
    s += ",\"blende_s\":" + jsonZahl(i.blendeS);
    s += ",\"a_orig_start\":" + jsonZahl(i.aOrigStart);
    s += ",\"b_orig_start\":" + jsonZahl(i.bOrigStart);
    s += ",\"a_orig_pro_s\":" + jsonZahl(i.aOrigProS);
    if (i.hatVorlauf) {
        s += ",\"vorlauf_s\":" + jsonZahl(i.vorlaufS);
        s += ",\"vorlauf_takte\":" + std::to_string(i.vorlaufTakte);
    }
    s += ",\"raster_s\":" + liste(i.rasterS);
    s += ",\"kurven\":" + kurvenJson(i.kurven);
    s += ",\"a_loop\":[";
    for (std::size_t k = 0; k < i.aLoop.size(); ++k) {
        if (k != 0) s += ",";
        const dsp::LoopInfo& l = i.aLoop[k];
        s += "{\"von\":" + jsonZahl(l.von) + ",\"bis\":" + jsonZahl(l.bis) + ",\"quelle\":" + jsonZahl(l.quelle) +
             ",\"laenge\":" + jsonZahl(l.laenge) + "}";
    }
    s += "]";
    if (i.hatLoopWahl) {
        s += ",\"loop_wahl\":{\"start_takt\":" + std::to_string(i.loopWahl.start) +
             ",\"schlaege\":" + std::to_string(4 * i.loopWahl.bars) + ",\"guete\":" + jsonZahl(i.loopWahl.quality) + "}";
    }
    if (i.hatIntroLoop) {
        s += ",\"b_intro_loop\":{\"takte\":" + std::to_string(i.introTakte) + ",\"mal\":" +
             std::to_string(i.introMal) + "}";
    }
    s += "}";
    return s;
}

}  // namespace klangbild
