// Kleiner JSON-Leser fuer den Uebergangsplan (BAUPLAN-ANDROID §4.5).
//
// Bewusst eigenstaendig (kein Drittanbieter): Das Format ist unser eigenes, strikt und klein.
// Nur lesen; geschrieben wird mit den Helfern am Ende (Info-JSON).
#pragma once

#include <cmath>
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <map>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace klangbild {

class JsonFehler : public std::runtime_error {
public:
    explicit JsonFehler(const std::string& text) : std::runtime_error(text) {}
};

struct Json {
    enum class Art { Null, Bool, Zahl, Text, Liste, Objekt };

    Art art = Art::Null;
    bool wahr = false;
    double zahl = 0.0;
    std::string text;
    std::vector<Json> eintraege;                 // Liste
    std::map<std::string, Json> mitglieder;      // Objekt

    bool istNull() const { return art == Art::Null; }
    bool istZahl() const { return art == Art::Zahl; }
    bool istText() const { return art == Art::Text; }
    bool istListe() const { return art == Art::Liste; }
    bool istObjekt() const { return art == Art::Objekt; }

    const Json& at(const std::string& schluessel) const {
        auto it = mitglieder.find(schluessel);
        if (it == mitglieder.end()) throw JsonFehler("JSON-Schluessel fehlt: " + schluessel);
        return it->second;
    }
    const Json* finde(const std::string& schluessel) const {
        auto it = mitglieder.find(schluessel);
        return it == mitglieder.end() ? nullptr : &it->second;
    }
    bool hat(const std::string& schluessel) const { return mitglieder.find(schluessel) != mitglieder.end(); }

    double alsZahl() const {
        if (art == Art::Zahl) return zahl;
        if (art == Art::Text) {
            if (text == "-inf") return -std::numeric_limits<double>::infinity();
            if (text == "inf") return std::numeric_limits<double>::infinity();
            if (text == "nan") return std::numeric_limits<double>::quiet_NaN();
            return std::stod(text);
        }
        throw JsonFehler("Kein Zahlenwert.");
    }
    std::string alsText() const {
        if (art != Art::Text) throw JsonFehler("Kein Textwert.");
        return text;
    }
    bool alsWahr() const {
        if (art != Art::Bool) throw JsonFehler("Kein Wahrheitswert.");
        return wahr;
    }
    void flach(std::vector<double>& aus) const {
        if (art == Art::Liste) {
            for (const auto& e : eintraege) e.flach(aus);
        } else if (art == Art::Zahl || art == Art::Text) {
            aus.push_back(alsZahl());
        } else {
            throw JsonFehler("Kein Zahlen-Array.");
        }
    }
    std::vector<double> zahlen() const {
        std::vector<double> aus;
        flach(aus);
        return aus;
    }
};

class JsonLeser {
public:
    explicit JsonLeser(std::string_view text) : text_(text) {}

    Json lesen() {
        leerraum();
        Json wert = wert_();
        leerraum();
        if (pos_ != text_.size()) throw JsonFehler("Unerwarteter Rest im JSON.");
        return wert;
    }

private:
    std::string_view text_;
    std::size_t pos_ = 0;

    void leerraum() {
        while (pos_ < text_.size()) {
            const char c = text_[pos_];
            if (c == ' ' || c == '\t' || c == '\n' || c == '\r') {
                ++pos_;
            } else {
                break;
            }
        }
    }
    char schau() {
        if (pos_ >= text_.size()) throw JsonFehler("JSON endet zu frueh.");
        return text_[pos_];
    }
    Json wert_() {
        const char c = schau();
        if (c == '{') return objekt();
        if (c == '[') return liste();
        if (c == '"') {
            Json j;
            j.art = Json::Art::Text;
            j.text = zeichenkette();
            return j;
        }
        if (c == 't' || c == 'f') return wahrheitswert();
        if (c == 'n') {
            wort("null");
            return Json{};
        }
        return zahl_();
    }
    void wort(std::string_view w) {
        if (text_.substr(pos_, w.size()) != w) throw JsonFehler("Falsches Literal.");
        pos_ += w.size();
    }
    Json wahrheitswert() {
        Json j;
        j.art = Json::Art::Bool;
        if (schau() == 't') {
            wort("true");
            j.wahr = true;
        } else {
            wort("false");
            j.wahr = false;
        }
        return j;
    }
    Json zahl_() {
        const std::size_t start = pos_;
        while (pos_ < text_.size()) {
            const char c = text_[pos_];
            if ((c >= '0' && c <= '9') || c == '-' || c == '+' || c == '.' || c == 'e' || c == 'E') {
                ++pos_;
            } else {
                break;
            }
        }
        if (start == pos_) throw JsonFehler("Keine Zahl an Position " + std::to_string(pos_));
        Json j;
        j.art = Json::Art::Zahl;
        j.zahl = std::stod(std::string(text_.substr(start, pos_ - start)));
        return j;
    }
    std::string zeichenkette() {
        if (schau() != '"') throw JsonFehler("Kein Textbeginn.");
        ++pos_;
        std::string aus;
        while (pos_ < text_.size()) {
            const char c = text_[pos_++];
            if (c == '"') return aus;
            if (c != '\\') {
                aus.push_back(c);
                continue;
            }
            if (pos_ >= text_.size()) break;
            const char e = text_[pos_++];
            switch (e) {
                case '"': aus.push_back('"'); break;
                case '\\': aus.push_back('\\'); break;
                case '/': aus.push_back('/'); break;
                case 'b': aus.push_back('\b'); break;
                case 'f': aus.push_back('\f'); break;
                case 'n': aus.push_back('\n'); break;
                case 'r': aus.push_back('\r'); break;
                case 't': aus.push_back('\t'); break;
                case 'u': {
                    unsigned code = 0;
                    for (int i = 0; i < 4 && pos_ < text_.size(); ++i) {
                        const char h = text_[pos_++];
                        code = code * 16 + (h <= '9' ? h - '0' : (h | 0x20) - 'a' + 10);
                    }
                    if (code < 0x80) {
                        aus.push_back(static_cast<char>(code));
                    } else if (code < 0x800) {
                        aus.push_back(static_cast<char>(0xC0 | (code >> 6)));
                        aus.push_back(static_cast<char>(0x80 | (code & 0x3F)));
                    } else {
                        aus.push_back(static_cast<char>(0xE0 | (code >> 12)));
                        aus.push_back(static_cast<char>(0x80 | ((code >> 6) & 0x3F)));
                        aus.push_back(static_cast<char>(0x80 | (code & 0x3F)));
                    }
                    break;
                }
                default: aus.push_back(e);
            }
        }
        throw JsonFehler("Text endet ohne Anfuehrungszeichen.");
    }
    Json liste() {
        Json j;
        j.art = Json::Art::Liste;
        ++pos_;
        leerraum();
        if (schau() == ']') {
            ++pos_;
            return j;
        }
        while (true) {
            leerraum();
            j.eintraege.push_back(wert_());
            leerraum();
            const char c = schau();
            if (c == ',') {
                ++pos_;
                continue;
            }
            if (c == ']') {
                ++pos_;
                return j;
            }
            throw JsonFehler("Liste falsch getrennt.");
        }
    }
    Json objekt() {
        Json j;
        j.art = Json::Art::Objekt;
        ++pos_;
        leerraum();
        if (schau() == '}') {
            ++pos_;
            return j;
        }
        while (true) {
            leerraum();
            std::string schluessel = zeichenkette();
            leerraum();
            if (schau() != ':') throw JsonFehler("Doppelpunkt fehlt.");
            ++pos_;
            leerraum();
            j.mitglieder.emplace(std::move(schluessel), wert_());
            leerraum();
            const char c = schau();
            if (c == ',') {
                ++pos_;
                continue;
            }
            if (c == '}') {
                ++pos_;
                return j;
            }
            throw JsonFehler("Objekt falsch getrennt.");
        }
    }
};

inline Json parseJson(std::string_view text) { return JsonLeser(text).lesen(); }

// --- Schreiben -------------------------------------------------------------

inline std::string jsonText(std::string_view text) {
    std::string aus = "\"";
    for (const char c : text) {
        switch (c) {
            case '"': aus += "\\\""; break;
            case '\\': aus += "\\\\"; break;
            case '\n': aus += "\\n"; break;
            case '\r': aus += "\\r"; break;
            case '\t': aus += "\\t"; break;
            default:
                if (static_cast<unsigned char>(c) < 0x20) {
                    char puffer[8];
                    std::snprintf(puffer, sizeof puffer, "\\u%04x", static_cast<unsigned>(c));
                    aus += puffer;
                } else {
                    aus.push_back(c);
                }
        }
    }
    aus.push_back('"');
    return aus;
}

/// Zahl mit genug Stellen fuer einen verlustfreien Rundlauf (double).
inline std::string jsonZahl(double v) {
    char puffer[40];
    std::snprintf(puffer, sizeof puffer, "%.17g", v);
    return puffer;
}

}  // namespace klangbild
