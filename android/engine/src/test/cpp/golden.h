// Leser der Python-Golden-Daten fuer die C++-Host-Tests (BAUPLAN-ANDROID
// Aufg. T0.3, §12.1).
//
// Der Golden-Export (`prototyp/klangbild/golden.py`, T0.2) schreibt je Fall
// eine `<name>.json` und - fuer lange Audio-Arrays - eine `<name>.f32`
// (float32 little endian, C-order, Stereo L/R interleaved). Dieser Header
// laedt beides und vergleicht mit den Toleranzen aus §12.3.
//
// Bewusst eigenstaendig: kein Drittanbieter-JSON, kein nlohmann-Abhaengigkeit.
// Das Format des Exports ist strikt (sortierte Schluessel, keine NaN - die
// stehen als "-inf"/"inf"/"nan"), darum reicht ein kleiner Parser.
//
// Regeln:
// - Nur lesen. Der Ordner ist ein Eingabedatenbestand, kein Cache.
// - Fehlende `.f32`-Dateien sind kein Testfehler, sondern ein Hinweis: der
//   vollstaendige Satz entsteht mit `python -m klangbild golden <ziel>`.

#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <limits>
#include <map>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace klangbild::test {

class GoldenError : public std::runtime_error {
public:
    explicit GoldenError(const std::string& text) : std::runtime_error(text) {}
};

// --- Minimaler JSON-Wert ---------------------------------------------------

struct Json {
    enum class Kind { Null, Bool, Number, String, Array, Object };

    Kind kind = Kind::Null;
    bool boolean = false;
    double number = 0.0;
    std::string text;
    std::vector<Json> items;                    // Array
    std::map<std::string, Json> members;         // Object

    bool is_null() const { return kind == Kind::Null; }
    bool is_number() const { return kind == Kind::Number; }
    bool is_string() const { return kind == Kind::String; }
    bool is_array() const { return kind == Kind::Array; }
    bool is_object() const { return kind == Kind::Object; }

    const Json& at(const std::string& key) const {
        auto it = members.find(key);
        if (it == members.end()) throw GoldenError("JSON-Schluessel fehlt: " + key);
        return it->second;
    }

    bool has(const std::string& key) const { return members.find(key) != members.end(); }

    double as_double() const {
        if (kind == Kind::Number) return number;
        if (kind == Kind::String) {
            // Der Export schreibt nicht endliche Werte als Text.
            if (text == "-inf") return -std::numeric_limits<double>::infinity();
            if (text == "inf") return std::numeric_limits<double>::infinity();
            if (text == "nan") return std::numeric_limits<double>::quiet_NaN();
            return std::stod(text);
        }
        throw GoldenError("Kein Zahlenwert.");
    }

    std::string as_string() const {
        if (kind != Kind::String) throw GoldenError("Kein Textwert.");
        return text;
    }

    bool as_bool() const {
        if (kind != Kind::Bool) throw GoldenError("Kein Wahrheitswert.");
        return boolean;
    }

    // Flache Liste aller Zahlen in einem (ggf. verschachtelten) Array.
    void flatten(std::vector<double>& out) const {
        if (kind == Kind::Array) {
            for (const auto& e : items) e.flatten(out);
        } else if (kind == Kind::Number || kind == Kind::String) {
            out.push_back(as_double());
        } else {
            throw GoldenError("Kein Zahlen-Array.");
        }
    }

    std::vector<double> numbers() const {
        std::vector<double> out;
        flatten(out);
        return out;
    }
};

// --- Parser ----------------------------------------------------------------

class JsonParser {
public:
    explicit JsonParser(std::string_view text) : text_(text) {}

    Json parse() {
        skip_ws();
        Json wert = value();
        skip_ws();
        if (pos_ != text_.size()) throw GoldenError("Unerwarteter Rest im JSON.");
        return wert;
    }

private:
    std::string_view text_;
    size_t pos_ = 0;

    void skip_ws() {
        while (pos_ < text_.size() &&
               (text_[pos_] == ' ' || text_[pos_] == '\t' ||
                text_[pos_] == '\n' || text_[pos_] == '\r')) {
            ++pos_;
        }
    }

    char peek() {
        if (pos_ >= text_.size()) throw GoldenError("JSON endet zu frueh.");
        return text_[pos_];
    }

    Json value() {
        char c = peek();
        if (c == '{') return object();
        if (c == '[') return array();
        if (c == '"') { Json j; j.kind = Json::Kind::String; j.text = string(); return j; }
        if (c == 't' || c == 'f') return boolean();
        if (c == 'n') { literal("null"); return Json{}; }
        return number();
    }

    void literal(std::string_view wort) {
        if (text_.substr(pos_, wort.size()) != wort) throw GoldenError("Falsches Literal.");
        pos_ += wort.size();
    }

    Json boolean() {
        Json j;
        j.kind = Json::Kind::Bool;
        if (peek() == 't') { literal("true"); j.boolean = true; }
        else { literal("false"); j.boolean = false; }
        return j;
    }

    Json number() {
        size_t start = pos_;
        while (pos_ < text_.size()) {
            char c = text_[pos_];
            if ((c >= '0' && c <= '9') || c == '-' || c == '+' || c == '.' ||
                c == 'e' || c == 'E') {
                ++pos_;
            } else {
                break;
            }
        }
        if (start == pos_) throw GoldenError("Keine Zahl an Position " + std::to_string(pos_));
        Json j;
        j.kind = Json::Kind::Number;
        j.number = std::stod(std::string(text_.substr(start, pos_ - start)));
        return j;
    }

    std::string string() {
        if (peek() != '"') throw GoldenError("Kein Textbeginn.");
        ++pos_;
        std::string out;
        while (pos_ < text_.size()) {
            char c = text_[pos_++];
            if (c == '"') return out;
            if (c != '\\') { out.push_back(c); continue; }
            if (pos_ >= text_.size()) break;
            char e = text_[pos_++];
            switch (e) {
                case '"': out.push_back('"'); break;
                case '\\': out.push_back('\\'); break;
                case '/': out.push_back('/'); break;
                case 'b': out.push_back('\b'); break;
                case 'f': out.push_back('\f'); break;
                case 'n': out.push_back('\n'); break;
                case 'r': out.push_back('\r'); break;
                case 't': out.push_back('\t'); break;
                case 'u': {
                    // Nur der BMP-Bereich, hier reichen ASCII-Zeichen.
                    unsigned code = 0;
                    for (int i = 0; i < 4 && pos_ < text_.size(); ++i) {
                        char h = text_[pos_++];
                        code = code * 16 + (h <= '9' ? h - '0' : (h | 0x20) - 'a' + 10);
                    }
                    if (code < 0x80) {
                        out.push_back(static_cast<char>(code));
                    } else {
                        // UTF-8-Kodierung fuer Zeichen bis 0xFFFF.
                        if (code < 0x800) {
                            out.push_back(static_cast<char>(0xC0 | (code >> 6)));
                            out.push_back(static_cast<char>(0x80 | (code & 0x3F)));
                        } else {
                            out.push_back(static_cast<char>(0xE0 | (code >> 12)));
                            out.push_back(static_cast<char>(0x80 | ((code >> 6) & 0x3F)));
                            out.push_back(static_cast<char>(0x80 | (code & 0x3F)));
                        }
                    }
                    break;
                }
                default: out.push_back(e);
            }
        }
        throw GoldenError("Text endet ohne Anfuehrungszeichen.");
    }

    Json array() {
        Json j;
        j.kind = Json::Kind::Array;
        ++pos_;  // '['
        skip_ws();
        if (peek() == ']') { ++pos_; return j; }
        while (true) {
            skip_ws();
            j.items.push_back(value());
            skip_ws();
            char c = peek();
            if (c == ',') { ++pos_; continue; }
            if (c == ']') { ++pos_; return j; }
            throw GoldenError("Array falsch getrennt.");
        }
    }

    Json object() {
        Json j;
        j.kind = Json::Kind::Object;
        ++pos_;  // '{'
        skip_ws();
        if (peek() == '}') { ++pos_; return j; }
        while (true) {
            skip_ws();
            std::string key = string();
            skip_ws();
            if (peek() != ':') throw GoldenError("Doppelpunkt fehlt.");
            ++pos_;
            skip_ws();
            j.members.emplace(std::move(key), value());
            skip_ws();
            char c = peek();
            if (c == ',') { ++pos_; continue; }
            if (c == '}') { ++pos_; return j; }
            throw GoldenError("Objekt falsch getrennt.");
        }
    }
};

// --- Golden-Ordner ---------------------------------------------------------

struct GoldenCase {
    std::string name;
    std::string function;
    Json inputs;
    Json expected;
    std::string tolerance;
};

class Golden {
public:
    explicit Golden(std::string dir) : dir_(std::move(dir)) {
        std::ifstream probe(dir_ + "/manifest.json");
        if (!probe.good()) throw GoldenError("Golden-Ordner fehlt oder leer: " + dir_);
    }

    const std::string& dir() const { return dir_; }

    Json raw(const std::string& name) {
        auto it = cache_.find(name);
        if (it != cache_.end()) return it->second;
        std::ifstream file(dir_ + "/" + name + ".json");
        if (!file.good()) throw GoldenError("Golden-Fall fehlt: " + name);
        std::stringstream puffer;
        puffer << file.rdbuf();
        Json wert = JsonParser(puffer.str()).parse();
        cache_[name] = wert;
        return wert;
    }

    GoldenCase case_of(const std::string& name) {
        Json body = raw(name);
        GoldenCase c;
        c.name = name;
        c.function = body.at("function").as_string();
        c.inputs = body.at("inputs");
        c.expected = body.at("expected");
        c.tolerance = body.has("tolerance") ? body.at("tolerance").as_string() : "values";
        return c;
    }

    // Liest ein float32-Array (Stereo L/R interleaved, C-order) als flache Liste.
    std::vector<float> f32(const std::string& file_name, const std::vector<int>& shape) {
        std::ifstream file(dir_ + "/" + file_name, std::ios::binary);
        if (!file.good()) {
            throw GoldenError(
                "Binaerarray fehlt: " + file_name +
                ". Der vollstaendige Satz entsteht mit `python -m klangbild golden <ziel>`.");
        }
        std::vector<char> roh((std::istreambuf_iterator<char>(file)),
                              std::istreambuf_iterator<char>());
        size_t count = 1;
        for (int d : shape) count *= static_cast<size_t>(d);
        if (roh.size() != count * 4) {
            throw GoldenError(file_name + ": Groesse passt nicht zur Form.");
        }
        std::vector<float> aus(count);
        std::memcpy(aus.data(), roh.data(), roh.size());
        return aus;
    }

    // Folgt einem Verweis-Objekt {"dtype":"float32-le","file":...,"shape":[...]}
    // und liefert die flachen Werte; sonst werden die JSON-Zahlen gelesen.
    std::vector<double> values(const Json& element) {
        if (element.is_object() && element.has("dtype") &&
            element.at("dtype").as_string() == "float32-le") {
            std::vector<int> shape;
            for (const auto& d : element.at("shape").items) {
                shape.push_back(static_cast<int>(d.as_double()));
            }
            std::vector<float> roh = f32(element.at("file").as_string(), shape);
            return std::vector<double>(roh.begin(), roh.end());
        }
        return element.numbers();
    }

    // --- Vergleich nach §12.3 ---------------------------------------------

    // Kurven/Huellen/Planwerte: absolute Obergrenze 1e-6.
    void expect_values(const std::string& name, const Json& erwartet,
                       const std::vector<double>& ist) {
        expect_close(name, erwartet, ist, 1e-6, 0.0);
    }

    // DSP: max. Abweichung 1e-4, RMS-Differenz < -80 dBFS.
    void expect_dsp(const std::string& name, const Json& erwartet,
                    const std::vector<double>& ist) {
        expect_close(name, erwartet, ist, 1e-4, -80.0);
    }

    // Hall (FFT-Faltung): RMS-Differenz < -70 dBFS.
    void expect_reverb(const std::string& name, const Json& erwartet,
                       const std::vector<double>& ist) {
        expect_close(name, erwartet, ist, -1.0, -70.0);
    }

    void expect_close(const std::string& name, const Json& erwartet,
                      const std::vector<double>& ist,
                      double abs_tol, double rms_floor_db) {
        std::vector<double> ref = values(erwartet);
        if (ref.size() != ist.size()) {
            throw GoldenError(name + ": Laenge " + std::to_string(ist.size()) +
                              ", erwartet " + std::to_string(ref.size()));
        }
        double max_abs = 0.0, fehler = 0.0, bezug = 0.0;
        for (size_t i = 0; i < ref.size(); ++i) {
            double d = ist[i] - ref[i];
            max_abs = std::max(max_abs, std::abs(d));
            fehler += d * d;
            bezug += ref[i] * ref[i];
        }
        if (abs_tol >= 0.0 && max_abs > abs_tol) {
            throw GoldenError(name + ": max. Abweichung " + std::to_string(max_abs) +
                              " > " + std::to_string(abs_tol));
        }
        if (rms_floor_db != 0.0) {
            double rms_db;
            if (bezug <= 0.0) {
                rms_db = (fehler <= 1e-30) ? -200.0 : 20.0;
            } else {
                rms_db = 10.0 * std::log10(fehler / bezug);
            }
            if (rms_db > rms_floor_db) {
                throw GoldenError(name + ": RMS-Differenz " + std::to_string(rms_db) +
                                  " dBFS > " + std::to_string(rms_floor_db));
            }
        }
    }

private:
    std::string dir_;
    std::map<std::string, Json> cache_;
};

}  // namespace klangbild::test
