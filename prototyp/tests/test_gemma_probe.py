"""Gemma-Versuch ohne Modell: Antworten lesen, Faelle beschreiben, Wahl in der Fallliste."""

from klangbild import gemma_probe, uebergangstest


def test_json_aus_der_antwort():
    assert gemma_probe.json_aus('```json\n{"note": 4, "grund": "passt"}\n```') == {"note": 4, "grund": "passt"}
    assert gemma_probe.json_aus("keine Ahnung") == {}


def test_bereiche_fasst_takte_zusammen():
    assert gemma_probe._bereiche([0, 1, 1, 0, 0, 0, 0, 1, 1]) == "1-2, 7-8"
    assert gemma_probe._bereiche([0, 0]) == "keine"


def test_beschreibung_nennt_rezept_und_songs():
    m = {"a": {"titel": "A", "bpm": 174.0, "camelot": "8A"}, "b": {"titel": "B", "bpm": 175.0, "camelot": "9A"},
         "stil": "kurz", "spielanteil": "lang", "weiter": False,
         "info": {"rezept": "double_drop", "takte": 16, "blende_s": 22.0, "stems": True, "sync": True,
                  "energie_schritt": 1.5, "grund": "Double Drop"}}
    text = gemma_probe.beschreibung(m)
    assert "double_drop" in text and "„A“ (174 BPM, Tonart 8A)" in text


def test_gemma_faelle_je_paar_einmal_mit_gemma():
    f = uebergangstest.faelle_planen(list(range(20)), 6, 1, gemma=True)
    assert len(f) == 12 and sum(x.get("gemma", False) for x in f) == 6
    assert all(x["rang"] == 0 for x in f)


def test_einstellungen_nur_erlaubte_felder_und_saetze_gueltig():
    import json

    from klangbild import gemma_probe as g

    assert g.gueltig({"modus": "kurz"}) == {"modus": "kurz"} and g.gueltig({}) == {}
    assert g.gueltig({"modus": "quatsch"}) is None and g.gueltig({"takte": 8}) is None
    saetze = json.loads(g.SAETZE.read_text(encoding="utf-8"))
    assert len(saetze) == 60 and all(g.gueltig(soll) == soll for _, soll in saetze)
