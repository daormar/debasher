"""
The examples described with the SDK that ship under
data/sdk_programs/python, each the program that the web UI saved under
data/webui_programs with another name: loaded for the tests that
compare the two, as the web UI's twin (the name, the description text and
the positions of the editor, which the examples do not carry).
"""

from pathlib import Path

from api import persistence
from debasher import Program
from debasher.build import load_program

REPO_ROOT = Path(__file__).resolve().parents[3]
SDK_PROGRAMS_DIR = REPO_ROOT / "data" / "sdk_programs" / "python"
WEBUI_PROGRAMS_DIR = REPO_ROOT / "data" / "webui_programs"

# The example, and the program of the web UI it is the twin of
TWINS = {
    "sdk_hello_world_py": "webui_hello_world_py",
    "sdk_dynamic_fanout_fifos": "webui_dynamic_fanout_fifos",
    "sdk_running_sum": "webui_running_sum",
    "sdk_skip_py": "webui_skip_py",
    "sdk_conda_envs": "webui_conda_envs",
}


def example_file(name: str) -> Path:
    return SDK_PROGRAMS_DIR / name / f"{name}.py"


def webui_home(name: str) -> Path:
    return WEBUI_PROGRAMS_DIR / TWINS[name]


def as_webui_twin(name: str) -> Program:
    """The example `name` as the program of the web UI it reproduces: the
    same name, description text and positions, which are the only things
    the two are meant to differ in."""
    program = load_program(example_file(name))
    shipped = persistence.load_program(str(webui_home(name)))
    program.name = shipped.name
    program.description = shipped.description
    positions = {process.name: (process.position.x, process.position.y) for process in shipped.processes}
    for member in program._members:
        member.position = positions[member.process.name]
    return program
