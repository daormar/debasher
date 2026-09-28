"""Tests for engine/debasher_prg_lib.py, which reads the files a run leaves
in its output directory to check the program and draw its graphs."""

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "debasher_prg_lib", Path(__file__).resolve().parents[2] / "engine" / "debasher_prg_lib.py"
)
prg_lib = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(prg_lib)


def _write_procspec(tmp_path, lines):
    prefix = tmp_path / "program"
    (tmp_path / f"program.{prg_lib.PROCSPEC_FEXT}").write_text("".join(line + "\n" for line in lines))
    return str(prefix)


def test_a_process_with_no_dependencies_is_read(tmp_path):
    prefix = _write_procspec(tmp_path, [
        "writer cpus=1 mem=32 time=00:01:00",
        "reader cpus=1 mem=32 time=00:01:00 ||| processdeps=afterok:writer",
    ])
    graph = prg_lib.DependencyGraph(prefix)
    assert graph.syntax_ok() is True
    assert [dep.processname for dep in graph.processdeps_map["reader"]] == ["writer"]
    assert graph.processdeps_map["writer"] == []


def test_a_malformed_dependency_is_reported(tmp_path):
    prefix = _write_procspec(tmp_path, [
        "writer cpus=1 mem=32 time=00:01:00",
        "reader cpus=1 mem=32 time=00:01:00 ||| processdeps=afterok",
    ])
    assert prg_lib.DependencyGraph(prefix).syntax_ok() is False


def test_mixed_dependency_separators_are_reported(tmp_path):
    prefix = _write_procspec(tmp_path, [
        "a cpus=1 mem=32 time=00:01:00",
        "b cpus=1 mem=32 time=00:01:00",
        "c cpus=1 mem=32 time=00:01:00 ||| processdeps=afterok:a,afterok:b?afterok:a",
    ])
    assert prg_lib.DependencyGraph(prefix).syntax_ok() is False


def test_the_options_of_a_task_keep_the_spaces_of_their_values(tmp_path):
    sep = prg_lib.ARG_SEP
    elem = prg_lib.ASSOC_ARRAY_ELEM_SEP
    (tmp_path / f"program.{prg_lib.PRGOPTS_EXHAUSTIVE_FEXT}").write_text(
        f"writer{elem}{prg_lib.ASSOC_ARRAY_KEY_LEN} -> 1\n"
        f"writer{elem}0 -> -outf{sep}/data/a b/out.txt\n"
    )
    (tmp_path / f"program.{prg_lib.FIFOS_FEXT}").write_text("")
    graph = prg_lib.ProcessGraph(str(tmp_path / "program"))
    assert graph.prgopts_exh["writer"][0] == ["-outf", "/data/a b/out.txt"]
    assert "/data/a b/out.txt" in graph.process_out_values
