import sys
from pathlib import Path

# Das Paket liegt eine Ebene ueber den Tests und wird nicht installiert.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
