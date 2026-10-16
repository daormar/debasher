import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]

# The package `debasher` is in sdk/python, and it imports the API of the
# web UI as `api`, a package at the root of the repository (see
# sdk/python/debasher/_paths.py).
sys.path.insert(0, str(_REPO_ROOT / "sdk" / "python"))
sys.path.insert(0, str(_REPO_ROOT))
