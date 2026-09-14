import sys
from pathlib import Path

# api/ ships its .py files as-is (dist_*_DATA in api/Makefile.am), so they
# are never installed as a package; import them straight from the source
# tree instead.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "api"))
