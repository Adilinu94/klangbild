# ADR-015 · Stimmung per Zero-Shot im Einbettungsraum, Gemma 4 optional

**Status:** angenommen
**Datum:** 08.10.2026
**Ergänzt:** ADR-006

## Kontext

Die Architektur sah vor: „Stimmungs-Label: Gemma 4 aus dem Vektor". Ein
Sprachmodell kann aber keinen 256-dimensionalen Vektor lesen. Außerdem ist
Gemma 4 E2B/E4B mehrere Gigabyte groß. Für eine App zu 7,99 Euro ist das ein
schwerer Download, und die Verteilung (Play Asset Delivery) ist nicht geplant.

EmbeddingGemma 2 legt Text und Audio in **denselben** Vektorraum.

## Entscheidung

- **Stimmung:** Die Stimmungswörter („ruhig", „euphorisch", „melancholisch" …)
  werden als Text eingebettet. Ein Song bekommt die Labels, deren Text-Vektor
  seinem Audio-Vektor am nächsten liegt (Zero-Shot). Dafür braucht es kein
  Sprachmodell.
- **Suche mit Worten:** Die Anfrage wird als Text eingebettet und direkt gegen
  die Audio-Vektoren gesucht.
- **Gemma 4** nur noch für „Wunsch in Worten" (Wunsch → Planer-Parameter),
  „Set benennen" und „Wahl erklären". Als **optionaler Download**, erst ab
  Phase 6.

## Alternativen

1. **Gemma 4 liest den Vektor.** Verworfen: technisch nicht möglich.
2. **Gemma 4 hört das Audio direkt.** Möglich (Gemma 4 nimmt Audio), aber
   langsam und teuer pro Song. Verworfen für die Bibliotheksanalyse.
3. **Zero-Shot im gemeinsamen Raum.** **Gewählt.**

## Konsequenzen

- Der Kern (Auswahl, Suche, Stimmung) braucht nur EmbeddingGemma 2.
- Ob Text und Musik-Audio gut genug zueinander liegen, ist **nicht belegt**:
  Phase 0.1 prüft genau das.
- EmbeddingGemma 2 steht laut Google unter **Apache 2.0** (die Gemma-Terms
  gelten nur für Gemma 4). Damit ist der offene Lizenzpunkt geschlossen.

## Belege

- EmbeddingGemma 2 Developer Guide (Apache 2.0, Audio 16 kHz mono, 768 Dim.,
  MRL bis 128): https://developers.googleblog.com/embeddinggemma-2-the-developer-guide/
- `ARCHITEKTUR-KLANGBILD.md` §3, §4

## Ergänzung 08.10.2026 · Belege und Fallen

**Belege (Modellkarte und Developer Guide, 08.10.2026):**
- **Lizenz Apache 2.0** bestätigt; zusätzlich gilt die **Gemma Prohibited Use
  Policy**. Der frühere offene Lizenzpunkt ist damit geschlossen.
- **Modulare Stufen:** 270 M (nur Text), 440 M (Text+Bild), **570 M (Text+Audio)**,
  740 M (alles). Für Klangbild wird nur Text **und** Audio geladen → **570 M**.
- **MRL: 768 / 512 / 256 / 128.** 256 ist der empfohlene Boden für Audio
  (bei 128 fällt die multimodale Qualität auf etwa 75 %).
- **Audio: mono, 16 kHz, 25 Token je Sekunde, höchstens ~327 s** – 20-Sekunden-
  Ausschnitte kosten rund 500 Token (Fenster 8.192).

**Vier Fallen, die Phase 0.1 sonst falsch bewerten:**
1. Nach dem Kürzen auf 256 **re-normalisieren** – ein gekürzter, nicht
   normalisierter Vektor verschlechtert das Ranking **still**.
2. **Niemals float16** – der Aktivitätsbereich überschreitet den Wertebereich;
   Ergebnis ist NaN oder stille Verschlechterung. Nur **bfloat16 oder float32**.
3. **Task-Präfixe gelten nur für Text.** Audio wird **ohne** Präfix eingebettet,
   Text bekommt einen symmetrischen Präfix (SentenceSimilarity bzw.
   Classification). Welche Kombination bewertet wird, steht **vor** dem Test fest.
4. Abfrage und eingebettete Songs müssen **dieselbe** Dimension haben.
