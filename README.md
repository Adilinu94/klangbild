# Klangbild

Ein normaler Musik-Player für eigene Dateien (Vorbild Poweramp) mit einem
zuschaltbaren Auto-DJ, der die Übergänge selbst setzt — Auswahl nach **Klang**,
komplett lokal, ohne Abo und ohne Cloud.

**Stand: 08.10.2026 · Projektphase: 0 (PC-Prototyp)**

---

## Erste Schritte

Wenn du neu im Projekt bist, lies in dieser Reihenfolge:

1. [`PRODUKT-KLANGBILD.md`](PRODUKT-KLANGBILD.md) — was das Produkt ist, für wen,
   was bewusst nicht gebaut wird, Tötungskriterien.
2. [`ROADMAP-KLANGBILD.md`](ROADMAP-KLANGBILD.md) — **die einzige gültige
   Roadmap**, Phase 0 bis 6, jedes Tor mit festgelegter Schwelle.
3. [`adr/README.md`](adr/README.md) — alle Entscheidungen mit Begründung.
4. [`prototyp/README.md`](prototyp/README.md) — wie der PC-Prototyp läuft.

---

## Dokumentenlandkarte

| Datei | Inhalt | Status |
|---|---|---|
| `PRODUKT-KLANGBILD.md` | Produkt, Zielgruppe, Funktionen, Risiken, Monetarisierung | gültig, Korrekturzeilen vom 08.10.2026 |
| `ARCHITEKTUR-KLANGBILD.md` | Module, Datenmodell, Ablauf | gültig, Werkzeugtabellen auf ADR-012 korrigiert |
| `ROADMAP-KLANGBILD.md` | Phase 0–6 mit Toren | **einzige gültige Roadmap** |
| `ANDROID-AUTODJ-TOOLCHAIN-2026.md` | ausführliche Werkzeug- und Lizenzrecherche | gültig (Recherchestand) |
| `PROTOKOLLE.md` | Register: Quellen, Lizenzen, Zahlen, Messplan, offene Punkte | gültig, Ergänzungen 08.10.2026 |
| `adr/` | Entscheidungsprotokoll ADR-001 … ADR-017 | gültig; ADR-005 abgelöst, ADR-008 ausgelagert |
| `WISSEN-POWERAMP-ARCHITEKTUR.md` | Reverse-Engineering-Wissen über Poweramp | gültig, Hintergrundwissen |
| `poweramp-java-handover/` | dekompilierte Quellen (nur Studium) | gültig, nicht unser Code |
| `prototyp/` | Phase-0.0/0.1-Code | **in Arbeit** |

**Ausgelagert** (liegt unter `G:\AI Agentur\`, gehört zum Produkt Belegkasten):
`ADR-008-archiv-bleibt-frei.md`, `PRODUKT-BELEGKASTEN.md`.

---

## Projektregeln

1. **Korrektur, nicht Überschreiben.** Wird eine frühere Aussage geändert, bleibt
   die alte Zeile stehen und bekommt eine **Korrekturzeile** mit Datum.
2. **Jede Aussage trägt einen Sicherheitsgrad** (`belegt`, `geschlossen`,
   `vermutet`) — siehe `PROTOKOLLE.md` §10.
3. **Kein stiller ADR-Wechsel.** Eine Entscheidung, die eine andere ablöst, bekommt
   eine eigene Nummer und verweist auf die abgelöste (`adr/README.md`).
4. **Lizenz vor Bau.** Kein AGPL/GPL-Code im Produkt; die Modell-Lizenzen sind
   belegt, nicht vermutet (`PROTOKOLLE.md` §2.2).
5. **Erst messen, dann bauen.** Jede Phase endet an einem Tor; ist es nicht
   erfüllt, wird nicht weitergebaut.

---

## Aktueller Stand (08.10.2026)

- **Phase 0 läuft.** Der PC-Prototyp analysiert eine Sammlung, bettet Ausschnitte
  ein und macht Nachbarn und Textsuche blind bewertbar.
- **Testsammlung:** `D:\Music\Chill` (501 Dateien, 290 FLAC / 208 MP3 / 2 WAV /
  1 M4A, 11,5 GB).
- **Offene Tore** mit festgelegten Schwellen: Phase 0.1 (Vektoren für Musik),
  Phase 0.2 (BPM/Downbeat/Tonart).

## Nichts zur Weitergabe

Gekaufte Musik, Modellgewichte und gerenderte Mixe aus gekauften Songs bleiben
lokal. Öffentlich werden nur Mixe aus **frei lizenzierter** Musik mit
Lizenz-Tabelle (Phase 2).
