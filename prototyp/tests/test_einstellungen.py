"""Tests fuer einstellungen.py - Grenzen, Auswahl, Speichern."""

from __future__ import annotations

from klangbild import einstellungen as es


def test_ungueltiges_wird_ignoriert_grenzen_geklemmt():
    e = es.aus_dict({"takte": 7, "art": "x", "max_bpm": -3, "keylock": 0, "unbekannt": 1})
    assert e.takte == 16 and e.art == "auto" and e.max_bpm == 0.0 and e.keylock is False


def test_speichern_und_laden(tmp_path):
    pfad = tmp_path / "e.json"
    es.speichern(pfad, es.Einstellungen(takte=24, tempo_modus="b_an_a"))
    assert es.laden(pfad) == es.Einstellungen(takte=24, tempo_modus="b_an_a")
    assert es.laden(tmp_path / "fehlt.json") == es.Einstellungen()


def test_bausteine_der_eigenen_kombination():
    e = es.aus_dict({"art": "eigen", "lautstaerke": "mitte", "eq": "drei_band", "filter": "tp_ein_hp_aus",
                     "effekt": "delay75_ende_ab", "effekt_ein": "hall", "loop": "rolle"})
    assert (e.art, e.lautstaerke, e.eq, e.filter, e.effekt, e.effekt_ein, e.loop) == (
        "eigen", "mitte", "drei_band", "tp_ein_hp_aus", "delay75_ende_ab", "hall", "rolle")
    assert es.aus_dict({"effekt": "hall_irgendwann", "loop": "3"}).effekt == "keiner"
    assert len(es.EFFEKT) == 1 + 9 * 3


def test_automatisch_im_stil_manuell_ist_die_regie():
    from klangbild.einstellungen import Einstellungen, regie_einst

    assert regie_einst(Einstellungen(modus="manuell", art="eq")) is None
    r = regie_einst(Einstellungen(modus="manuell", art="auto"))
    assert r is not None and r.modus == "ausgewogen"
    assert regie_einst(Einstellungen(modus="lang", art="eq")).modus == "lang"
