import sys
from pathlib import Path

# engine/*.py files (e.g. debasher_runtime_lib.py) are python_PYTHON-installed
# verbatim, with no build-time transformation, so testing straight from the
# source tree is faithful to what actually ships -- no "built artifact vs.
# source" distinction here the way there is for engine/*.sh (see
# test/engine/*.bats, which do need ENGINE_BUILDDIR).
_ENGINE_DIR = Path(__file__).resolve().parents[2] / "engine"
sys.path.insert(0, str(_ENGINE_DIR))
