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


# --- the process graph ----------------------------------------------------------


def _process_graph_output(tmp_path, capsys):
    """The process graph of a writer of a file with a flag, an array of two
    tasks with a fifo each, and a reader of the file and of the fifo of the
    first task of the array, as ProcessGraph prints it, with the separators
    of the node names made short: "~" between an option and its process,
    "@" before a task index, "#HUB" for the hub of an array."""
    sep = prg_lib.ARG_SEP
    elem = prg_lib.ASSOC_ARRAY_ELEM_SEP
    num = prg_lib.ASSOC_ARRAY_KEY_LEN
    (tmp_path / f"program.{prg_lib.PRGOPTS_EXHAUSTIVE_FEXT}").write_text(
        f"writer{elem}{num} -> 1\n"
        f"writer{elem}0 -> -outf{sep}/out/writer/out.txt{sep}-v\n"
        f"reader{elem}{num} -> 1\n"
        f"reader{elem}0 -> -inf{sep}/out/writer/out.txt{sep}-inf2{sep}/out/__fifos__/arr/f0\n"
        f"arr{elem}{num} -> 2\n"
        f"arr{elem}0 -> -outf{sep}/out/__fifos__/arr/f0\n"
        f"arr{elem}1 -> -outf{sep}/out/__fifos__/arr/f1\n"
    )
    (tmp_path / f"program.{prg_lib.FIFOS_FEXT}").write_text(f"arr/f0 arr{elem}0 reader{elem}0\n")
    prg_lib.ProcessGraph(str(tmp_path / "program")).print()
    return (
        capsys.readouterr()
        .out.replace(prg_lib.PROCESS_TASKIDX_SEP, "@")
        .replace(prg_lib.OPT_PROCESS_SEP, "~")
        .replace(prg_lib.OPTPROC_HUB_SUFFIX, "#HUB")
    )


def test_a_connected_option_gives_an_arc_from_the_output_of_the_writer_to_the_input_of_the_reader(tmp_path, capsys):
    out = _process_graph_output(tmp_path, capsys)
    assert '"writer" -> "-outf~writer@0" ;' in out
    assert '"-outf~writer@0" -> "-inf~reader@0" ;' in out
    assert '"-inf~reader@0" -> "reader" ;' in out


def test_the_options_of_an_array_go_through_a_hub_and_a_fifo_gives_dashed_arcs(tmp_path, capsys):
    out = _process_graph_output(tmp_path, capsys)
    assert 'node [shape = point]; "-outf~arr#HUB"' in out
    assert '"arr" -> "-outf~arr#HUB" [ style=dashed ] ;' in out
    assert '"-outf~arr#HUB" -> "-outf~arr@0" [ style=dashed ] ;' in out
    assert '"-outf~arr#HUB" -> "-outf~arr@1" ;' in out
    assert '"-outf~arr@0" -> "-inf2~reader@0" [ style=dashed ] ;' in out


def test_a_flag_is_an_input_of_its_process_and_connects_to_nothing(tmp_path, capsys):
    out = _process_graph_output(tmp_path, capsys)
    assert '"-v~writer@0" -> "writer" ;' in out
    assert '"-outf~writer@0" -> "-v~writer@0"' not in out


def test_each_process_is_a_cluster_with_its_options(tmp_path, capsys):
    out = _process_graph_output(tmp_path, capsys)
    cluster = out[out.index('subgraph "cluster_writer"'):]
    cluster = cluster[: cluster.index("}")]
    assert '"writer";' in cluster and '"-outf~writer@0";' in cluster and '"-v~writer@0";' in cluster
