"""
Tests for the programs built with the web UI that ship with DeBasher, in
data/webui_programs/, and for loading a program from a home directory
other than the one it was saved in, which is what makes shipping them
possible.

Each program there is a home directory as the web UI saves it: the
program metadata in .debasher/program.json and the generated script
next to it. Such a program is loaded, never imported, so these tests
check what loading relies on: the metadata loads, it names no directory
of the machine it was built on, and the generated script is the one
that script generation writes from it today.
"""

import shutil
from pathlib import Path

import pytest

from api import persistence, script_generation

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WEBUI_PROGRAMS_DIR = _REPO_ROOT / "data" / "webui_programs"
_WEBUI_PROGRAMS = sorted(
    path.parent.parent
    for path in _WEBUI_PROGRAMS_DIR.glob(f"*/{persistence.METADATA_DIRNAME}/{persistence.PROGRAM_FILENAME}")
)


def test_there_are_webui_programs():
    assert _WEBUI_PROGRAMS


@pytest.mark.parametrize("home_dir", _WEBUI_PROGRAMS, ids=lambda path: path.name)
def test_a_webui_program_loads_from_where_it_is(home_dir):
    program = persistence.load_program(str(home_dir))

    assert program.homeDir == str(home_dir.resolve())
    assert program.outputDir == ""
    assert program.sourceDir == ""


@pytest.mark.parametrize("home_dir", _WEBUI_PROGRAMS, ids=lambda path: path.name)
def test_the_script_of_a_webui_program_is_up_to_date(home_dir):
    program = persistence.load_program(str(home_dir))

    shipped = (home_dir / f"{program.name}.sh").read_text()

    assert shipped == script_generation.generate_script(program)


def test_loading_takes_the_home_directory_from_where_the_program_is(tmp_path):
    original = _WEBUI_PROGRAMS[0]
    moved = tmp_path / "moved"
    shutil.copytree(original, moved)

    program = persistence.load_program(str(moved))

    assert program.homeDir == str(moved.resolve())
