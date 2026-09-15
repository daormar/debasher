import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

# api/ ships its .py files as-is (dist_*_DATA in api/Makefile.am), so they
# are never installed as a package; import a standalone module (one with
# no `from .foo import` of its own, e.g. paths.py) straight from the
# source tree instead.
sys.path.insert(0, str(_REPO_ROOT / "api"))

# Modules that import from each other with package-relative imports
# (e.g. program_import.py's "from .doc_mod import ...") need a real
# parent package to resolve those against -- api/__init__.py makes "api"
# one -- so those are imported as "api.<module>" instead, with the repo
# root on the path.
sys.path.insert(0, str(_REPO_ROOT))
