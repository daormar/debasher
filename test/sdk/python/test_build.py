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

from examples import example_file  # noqa: E402


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


def test_a_file_whose_name_cannot_name_a_program_is_told_to_take_the_name_of_the_program(tmp_path):
    path = _program_file(tmp_path, "hello-world", 'prg = Program("hello_world")\n')

    with pytest.raises(DefinitionError) as refusal:
        load_program(path)

    assert "rename the file to hello_world.py" in str(refusal.value)
    assert 'Program("hello-world")' not in str(refusal.value)


def test_the_tool_writes_the_program_into_the_directory_of_the_file(tmp_path, capsys):
    path = _program_file(tmp_path, "prg", 'prg = Program("prg")\nprg.add(Process("work", code="work.sh"))\n')
    (tmp_path / "work.sh").write_text("work()\n{\n    :\n}\n")

    assert main([str(path)]) == 0

    assert capsys.readouterr().out.strip() == str(tmp_path / "prg.sh")
    assert persistence.load_program(str(tmp_path)).processes[0].name == "work"


def test_the_tool_writes_into_the_directory_given(tmp_path, capsys):
    home = tmp_path / "home"

    assert main([str(example_file("sdk_hello_world_py")), "-o", str(home)]) == 0

    assert capsys.readouterr().out.strip() == str(home / "sdk_hello_world_py.sh")
    assert persistence.load_program(str(home)).name == "sdk_hello_world_py"


def test_the_tool_reports_a_refused_program_and_fails(tmp_path, capsys):
    path = _program_file(tmp_path, "prg", 'other = Program("other")\n')

    assert main([str(path)]) == 1

    assert "debasher_build: " in capsys.readouterr().err
    assert not (tmp_path / persistence.METADATA_DIRNAME).exists()


# --- building again from the artifact -----------------------------------------


def _saved_program(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    main([str(example_file("sdk_hello_world_py")), "-o", str(home)])
    return home


def test_a_program_deleted_down_to_its_artifact_is_built_again_identically(tmp_path, capsys):
    home = _saved_program(tmp_path)
    module = home / "sdk_hello_world_py.sh"
    before = module.read_text()
    files_before = {path.name: path.read_text() for path in home.iterdir() if path.is_file()}
    module.unlink()
    capsys.readouterr()

    assert main([str(home)]) == 0

    assert capsys.readouterr().out.strip() == str(module)
    assert module.read_text() == before
    assert {path.name: path.read_text() for path in home.iterdir() if path.is_file()} == files_before


def test_the_topology_file_or_the_current_directory_names_the_program_to_build_again(tmp_path, monkeypatch):
    home = _saved_program(tmp_path)
    module = home / "sdk_hello_world_py.sh"

    module.unlink()
    assert main([str(home / "program.yaml")]) == 0
    assert module.is_file()

    module.unlink()
    monkeypatch.chdir(home)
    assert main([]) == 0
    assert module.is_file()


def _target(home: Path, form: str, monkeypatch) -> list[str]:
    """The arguments of a rebuild of `home` in one of its three forms."""
    if form == "directory":
        return [str(home)]
    if form == "topology file":
        return [str(home / "program.yaml")]
    monkeypatch.chdir(home)
    return []


@pytest.mark.parametrize("form", ["directory", "topology file", "no target"])
def test_a_rebuild_of_a_directory_that_holds_the_description_of_its_program_is_refused(
    tmp_path, capsys, monkeypatch, form
):
    # Built from the artifact, a change to the description would be ignored
    path = _program_file(tmp_path, "prg", 'prg = Program("prg", description="one")\nprg.add(Process("work", code="work.sh"))\n')
    (tmp_path / "work.sh").write_text("work()\n{\n    :\n}\n")
    main([str(path)])
    path.write_text(path.read_text().replace('"one"', '"two"'))
    module = (tmp_path / "prg.sh").read_text()
    capsys.readouterr()

    assert main(_target(tmp_path, form, monkeypatch)) == 1

    assert "holds prg.py, the description of its program" in capsys.readouterr().err
    assert (tmp_path / "prg.sh").read_text() == module


def test_a_file_of_the_artifact_named_as_the_description_does_not_stop_a_rebuild(tmp_path):
    # The code of a process outside the directory of the description goes
    # into the home directory under its name alone, here prg.py
    (tmp_path / "src").mkdir()
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "prg.py").write_text("print('work')\n")
    path = _program_file(tmp_path / "src", "prg", 'prg = Program("prg")\nprg.add(Process("work", code="../lib/prg.py"))\n')
    home = tmp_path / "home"
    main([str(path), "-o", str(home)])
    assert (home / "prg.py").is_file()

    assert main([str(home)]) == 0


def test_a_topology_file_edited_by_hand_is_written_again_in_the_form_of_the_backend(tmp_path):
    import yaml

    home = _saved_program(tmp_path)
    topology_file = home / "program.yaml"
    written = topology_file.read_text()
    module = (home / "sdk_hello_world_py.sh").read_text()
    topology_file.write_text("# edited by hand\n" + yaml.safe_dump(yaml.safe_load(written), sort_keys=True, indent=4))

    assert main([str(home)]) == 0

    assert topology_file.read_text() == written
    assert (home / "sdk_hello_world_py.sh").read_text() == module


def test_a_topology_file_that_cannot_be_read_is_reported(tmp_path, capsys):
    home = _saved_program(tmp_path)
    (home / "program.yaml").write_text("name: [unclosed\n")
    capsys.readouterr()

    assert main([str(home)]) == 1

    assert "debasher_build: cannot read the program in" in capsys.readouterr().err


def test_a_program_that_script_generation_refuses_is_reported_on_a_rebuild(tmp_path, capsys):
    home = _saved_program(tmp_path)
    topology_file = home / "program.yaml"
    # A process named as the method "_program" of the module
    topology_file.write_text(topology_file.read_text().replace("  hello_world:\n", "  sdk_hello_world_py_program:\n"))
    capsys.readouterr()

    assert main([str(home)]) == 1

    assert 'is named as the method "_program"' in capsys.readouterr().err


def test_a_directory_with_no_program_and_an_outdir_with_a_directory_are_refused(tmp_path, capsys):
    assert main([str(tmp_path)]) == 1
    assert "No program found" in capsys.readouterr().err

    home = _saved_program(tmp_path)
    capsys.readouterr()
    assert main([str(home), "-o", str(tmp_path / "elsewhere")]) == 1
    assert "-o goes with a Python file" in capsys.readouterr().err


def test_the_schema_of_the_topology_file_is_printed(capsys):
    import json

    from api.topology import json_schema

    assert main(["--schema"]) == 0

    assert json.loads(capsys.readouterr().out) == json_schema()


# The launcher is built by make beside its source; a source tree that has
# not been built has none
_LAUNCHER = Path(__file__).resolve().parents[3] / "sdk" / "python" / "debasher_build"


@pytest.mark.skipif(not _LAUNCHER.is_file(), reason="the launcher debasher_build is not built")
@pytest.mark.parametrize("name", ["debasher", "yaml"])
def test_a_description_named_as_a_module_that_the_sdk_imports_builds_from_its_directory(tmp_path, name):
    # Run from the directory of the description, `python -m` would import
    # the description in place of the module of that name
    import os
    import subprocess
    import sys

    (tmp_path / "a.sh").write_text("a()\n{\n    :\n}\n")
    _program_file(tmp_path, name, f'prg = Program("{name}")\nprg.add(Process("a", code="a.sh"))\n')

    result = subprocess.run(
        [str(_LAUNCHER), f"{name}.py"],
        cwd=tmp_path,
        env={**os.environ, "DEBASHER_WEBUI_PYTHON": sys.executable},
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert (tmp_path / f"{name}.sh").is_file()
