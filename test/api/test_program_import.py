"""
End-to-end tests for api/program_import.py's import_program_from_script,
run against the real engine tools (debasher_doc_mod,
debasher_get_verbatim_func_source) that ship in engine/ -- these are
shell-parsing tools, so a real subprocess round-trip against a real
script on disk is what actually exercises them, rather than a mock.

Each fixture script below reproduces, in miniature, one of the bugs
found while debugging the frontend's "import program" feature against
data/programs/debasher_dynamic_fanout*.sh:

- a process's code must keep every function debasher::_show_proc_
  implem_bash_func bundled alongside it (a same-script helper the
  process calls), not just one of them (see program_import.py's
  _verbatim_code / markdown_parsing.split_function_blocks).
- a sibling process's code must NOT be pulled in just because its name
  also happens to be used as a local variable, or appears as a word
  inside a string or an embedded other-language script (see
  engine/debasher_lib_processes.sh's debasher::_collect_func_deps).
"""

import re
import textwrap
from pathlib import Path

from api.program_import import import_program_from_script


def _process_boilerplate(name: str, exec_body_lines: list[str]) -> str:
    """A process definition with no options -- the minimum debasher_doc_mod
    needs to document and recover a process's implementation.

    Built by joining plain, already-unindented lines (rather than an
    f-string run through textwrap.dedent) since exec_body_lines is
    itself multi-line content substituted into a template: dedent looks
    at the common leading whitespace of the *final* joined text, and a
    template placeholder's own indentation only ever applies to the
    first line of whatever multi-line value fills it -- silently
    leaving the rest of that value's lines under-indented relative to
    the rest of the template.
    """
    return "\n".join(
        [
            f"{name}_document()",
            "{",
            f'    document_process "{name} process."',
            "}",
            "",
            f"{name}_explain_opts()",
            "{",
            "    :",
            "}",
            "",
            f"{name}_identify_cmdline_opts()",
            "{",
            "    :",
            "}",
            "",
            f"{name}_define_opts()",
            "{",
            "    local cmdline=$1",
            "    local process_spec=$2",
            "    local process_name=$3",
            "    local process_outdir=$4",
            '    local optlist=""',
            "    save_opt_list optlist",
            "}",
            "",
            f"{name}()",
            "{",
            *exec_body_lines,
            "}",
        ]
    )


def _write_script(tmp_path: Path, basename: str, process_defs: str, process_names: list[str]) -> Path:
    add_lines = [
        f'    add_debasher_process "{name}" "cpus=1 mem=32 time=00:01:00"' for name in process_names
    ]
    script = "\n".join(
        [
            f"{basename}_shared_dirs()",
            "{",
            "    :",
            "}",
            "",
            process_defs,
            "",
            f"{basename}_program()",
            "{",
            *add_lines,
            "}",
            "",
        ]
    )
    script_path = tmp_path / f"{basename}.sh"
    script_path.write_text(script)
    return script_path


def _code_function_headers(code: str) -> list[str]:
    return re.findall(r"^([A-Za-z_][A-Za-z0-9_.]*)\s*\(\)", code, re.M)


def test_import_keeps_every_function_a_process_depends_on(tmp_path):
    helper = "\n".join(["helper()", "{", "    :", "}"])
    main_proc = _process_boilerplate("main_proc", ["    helper"])

    script = _write_script(tmp_path, "sample_helper", helper + "\n" + main_proc, ["main_proc"])

    program = import_program_from_script(script, "")

    [process] = program.processes
    # The helper must still be there -- upgrading main_proc's code to
    # its verbatim source must not silently drop it -- and the
    # process's own exec function must be the last one in the blob
    # (see debasher::_show_proc_implem_bash_func), not overwritten by
    # or confused with the helper's.
    assert _code_function_headers(process.code) == ["helper", "main_proc"]


def test_import_does_not_pull_in_a_sibling_process_via_a_shadowing_local_variable(tmp_path):
    sibling = _process_boilerplate("count", ["    :"])
    fragment = _process_boilerplate(
        "fragment",
        ["    local i count", "    count=$(( 1 + 1 ))", '    echo "${count}"'],
    )

    script = _write_script(
        tmp_path, "sample_shadow", sibling + "\n" + fragment, ["count", "fragment"]
    )

    program = import_program_from_script(script, "")

    fragment_process = next(p for p in program.processes if p.name == "fragment")
    assert _code_function_headers(fragment_process.code) == ["fragment"]


def test_import_does_not_pull_in_a_sibling_process_named_only_inside_a_string(tmp_path):
    sibling = _process_boilerplate("count", ["    :"])
    count_chars = textwrap.dedent("""\
        count_chars()
        {
            awk '
                {
                    count[$1]++
                }
                END {
                    for (c in count) print c, count[c]
                }
            '
        }""")
    worker = _process_boilerplate("worker", ['    count_chars "$1"'])

    script = _write_script(
        tmp_path,
        "sample_string",
        sibling + "\n" + count_chars + "\n" + worker,
        ["count", "worker"],
    )

    program = import_program_from_script(script, "")

    worker_process = next(p for p in program.processes if p.name == "worker")
    # count_chars is a real dependency (worker calls it); count is not
    # -- the only place its name appears in count_chars's body is as an
    # awk array, inside a single-quoted script.
    assert _code_function_headers(worker_process.code) == ["count_chars", "worker"]
