"""
The tool debasher_build: it loads the Python file of a program, which
defines one Program named as the file, and writes the program into the
directory of the file or the one given.
"""

from pathlib import Path

import pytest

pytest.importorskip("pydantic")

from api import persistence  # noqa: E402
from debasher import DefinitionError  # noqa: E402
from debasher.build import load_program, main  # noqa: E402

_HELLO = Path(__file__).parent / "data" / "hello_world"


def _program_file(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / f"{name}.py"
    path.write_text("from debasher import Process, Program\n" + body)
    return path


def test_the_file_defines_one_program_named_as_the_file(tmp_path):
    path = _program_file(tmp_path, "prg", 'prg = Program("prg")\nprg.add(Process("work"))\n')

    assert load_program(path).name == "prg"


def test_a_file_that_defines_no_program_is_refused(tmp_path):
    path = _program_file(tmp_path, "prg", 'work = Process("work")\n')

    with pytest.raises(DefinitionError, match="defines no Program"):
        load_program(path)


def test_a_file_that_defines_two_programs_is_refused(tmp_path):
    path = _program_file(tmp_path, "prg", 'a = Program("a")\nb = Program("b")\n')

    with pytest.raises(DefinitionError, match="more than one Program"):
        load_program(path)


def test_a_program_not_named_as_its_file_is_refused(tmp_path):
    path = _program_file(tmp_path, "other", 'prg = Program("prg")\n')

    with pytest.raises(DefinitionError, match="named after its program"):
        load_program(path)


def test_a_missing_or_non_python_file_is_refused(tmp_path):
    with pytest.raises(DefinitionError, match="does not exist"):
        load_program(tmp_path / "none.py")
    (tmp_path / "prg.sh").write_text("")
    with pytest.raises(DefinitionError, match="not a Python file"):
        load_program(tmp_path / "prg.sh")


def test_the_file_can_import_files_beside_it(tmp_path):
    (tmp_path / "helpers.py").write_text("NAME = 'work'\n")
    path = _program_file(tmp_path, "prg", 'from helpers import NAME\nprg = Program("prg")\nprg.add(Process(NAME))\n')

    assert load_program(path).processes[0].name == "work"


def test_the_tool_writes_the_program_into_the_directory_of_the_file(tmp_path, capsys):
    path = _program_file(tmp_path, "prg", 'prg = Program("prg")\nprg.add(Process("work", code="work.sh"))\n')
    (tmp_path / "work.sh").write_text("work()\n{\n    :\n}\n")

    assert main([str(path)]) == 0

    assert capsys.readouterr().out.strip() == str(tmp_path / "prg.sh")
    assert persistence.load_program(str(tmp_path)).processes[0].name == "work"


def test_the_tool_writes_into_the_directory_given(tmp_path, capsys):
    home = tmp_path / "home"

    assert main([str(_HELLO / "webui_hello_world_py.py"), "-o", str(home)]) == 0

    assert capsys.readouterr().out.strip() == str(home / "webui_hello_world_py.sh")
    assert persistence.load_program(str(home)).name == "webui_hello_world_py"


def test_the_tool_reports_a_refused_program_and_fails(tmp_path, capsys):
    path = _program_file(tmp_path, "prg", 'other = Program("other")\n')

    assert main([str(path)]) == 1

    assert "debasher_build: " in capsys.readouterr().err
    assert not (tmp_path / persistence.METADATA_DIRNAME).exists()
