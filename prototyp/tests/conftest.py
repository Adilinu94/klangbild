import sys
from pathlib import Path

import pytest

# Das Paket liegt eine Ebene ueber den Tests und wird nicht installiert.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def _kein_echter_cache(tmp_path, monkeypatch):
    """Tests sehen nie die echten Profile/Stems der Bibliothek: Test-Titel 1, 2, ... haetten sonst
    die Profile echter 4-Minuten-Songs mit denselben IDs (Plaene hinter dem Ende des Test-Audios)."""
    from klangbild import profil, stems

    monkeypatch.setattr(profil, "CACHE", tmp_path / "profil")
    monkeypatch.setattr(stems, "CACHE", tmp_path / "stems")
    monkeypatch.setattr(stems, "VORRAT", tmp_path / "stem_vorrat")
