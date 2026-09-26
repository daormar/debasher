"""
Round-trip tests for the translation between the web UI's program model
and a DeBasher module, run against the real engine tools that ship in
engine/ (debasher_doc_mod, debasher_get_proc_info,
debasher_get_verbatim_func_source), like test_program_import.py.

Two properties are checked:

- From a module to the model and back: importing each example module
  of data/programs/, generating its script and importing that script
  again gives back the same model. Import is therefore a fixed point
  of the round trip: nothing is lost, added or changed by it (a header
  line added to the preamble, an extra level of indentation in a body,
  a description run by Bash, ...).

- From the model to a module and back: a program built here, covering
  the shapes script generation writes (every options handler mode,
  option channel and kind of connection), comes back from generation
  and import as it was, apart from what lives only in the program
  metadata (see _canonical_program).
"""

import tempfile
from pathlib import Path

import pytest

from api import persistence
from api.models import (
    AdditionalMethods,
    AdditionalSpecs,
    ComputationalSpecs,
    ExecutionOptions,
    OptionsHandler,
    Position,
    Program,
    ProgramEdge,
    ProgramOption,
    ProgramProcess,
)
from api.program_import import import_program_from_script

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROGRAMS_DIR = _REPO_ROOT / "data" / "programs"
_EXAMPLE_MODULES = sorted(_PROGRAMS_DIR.glob("*.sh"))


def _canonical_program(program: Program) -> dict:
    """
    The part of `program` that a module can carry, in a form that two
    programs can be compared by: processes keyed by name and options by
    label (import gives both new ids and follows the order of the
    module documentation), connections named by process and option.
    What lives only in the program metadata is left out: ids, positions,
    groups, environment variables, execution and program options, the
    three directories, and the shared directories reachable through
    loaded modules, which only import fills.
    """
    processes_by_id = {process.id: process for process in program.processes}

    def option_label(process_id: str, option_id: str) -> str:
        process = processes_by_id[process_id]
        return next(option.label for option in process.options if option.id == option_id)

    processes = {}
    for process in program.processes:
        labels_by_id = {option.id: option.label for option in process.options}
        options = {
            option.label: option.model_dump(exclude={"id", "countSourceOptionId"})
            | {"countSource": labels_by_id.get(option.countSourceOptionId)}
            for option in process.options
        }
        processes[process.name] = process.model_dump(
            exclude={"id", "position", "options", "groupSource"}
        ) | {"options": options}

    edges = sorted(
        (
            processes_by_id[edge.sourceProcessId].name,
            option_label(edge.sourceProcessId, edge.sourceOptionId),
            processes_by_id[edge.targetProcessId].name,
            option_label(edge.targetProcessId, edge.targetOptionId),
        )
        for edge in program.edges
    )

    top = program.model_dump(
        include={"name", "description", "preamble", "sharedDirs"}
    )

    return {"program": top, "processes": processes, "edges": edges}


def _generate_and_import(program: Program, debasher_mod_dir: str) -> Program:
    with tempfile.TemporaryDirectory() as tmp_dir:
        persistence.save_script(tmp_dir, program)
        persistence.copy_ext_alias_files(program, tmp_dir)
        return import_program_from_script(Path(tmp_dir) / f"{program.name}.sh", debasher_mod_dir)


# --- From a module to the model and back ---------------------------------


@pytest.mark.parametrize("module", _EXAMPLE_MODULES, ids=lambda module: module.name)
def test_import_is_a_fixed_point_of_the_round_trip(module):
    debasher_mod_dir = str(_PROGRAMS_DIR)

    imported = import_program_from_script(module, debasher_mod_dir)
    reimported = _generate_and_import(imported, debasher_mod_dir)

    assert _canonical_program(reimported) == _canonical_program(imported)


# --- From the model to a module and back ---------------------------------


def _option(label: str, **fields) -> ProgramOption:
    defaults = dict(
        id=f"opt{label}",
        label=label,
        direction="output" if label.startswith("-out") else "input",
        dataType="string",
        description=f"description of {label}",
        value="",
        commandLine=False,
    )
    return ProgramOption(**(defaults | fields))


def _process(name: str, options: list[ProgramOption], **fields) -> ProgramProcess:
    for option in options:
        option.id = f"{name}{option.id}"
    defaults = dict(
        id=name,
        name=name,
        description=f"description of {name}",
        position=Position(x=0, y=0),
        options=options,
        optionsHandler=OptionsHandler(mode="standard"),
        language="bash",
        code=f"{name}()\n{{\n    echo {name}\n}}",
        computationalSpecs=ComputationalSpecs(cpus=1, mem=64, time="00:05:00"),
        additionalSpecs=AdditionalSpecs(force=False),
    )
    return ProgramProcess(**(defaults | fields))


def _edge(source: str, source_label: str, target: str, target_label: str) -> ProgramEdge:
    return ProgramEdge(
        id=f"{source}{source_label}-{target}{target_label}",
        sourceProcessId=source,
        sourceOptionId=f"{source}opt{source_label}",
        targetProcessId=target,
        targetOptionId=f"{target}opt{target_label}",
    )


def _program(name: str, processes: list[ProgramProcess], edges: list[ProgramEdge], **fields) -> Program:
    defaults = dict(
        id=name,
        name=name,
        description=f"description of {name}",
        preamble="",
        envVars={},
        outputDir="",
        executionOptions=ExecutionOptions(scheduler="BUILTIN"),
        programOptions={},
        processes=processes,
        edges=edges,
    )
    return Program(**(defaults | fields))


def _assert_model_round_trip(program: Program, tmp_path: Path) -> None:
    reimported = _generate_and_import(program, str(tmp_path))
    assert _canonical_program(reimported) == _canonical_program(program)


def test_standard_mode_options_survive_the_round_trip(tmp_path):
    (tmp_path / "data.txt").write_text("x\n")
    writer = _process(
        "writer",
        [
            _option("-n", value="3"),
            _option("-c", dataType="int", commandLine=True, mandatory=True),
            _option("-opt", commandLine=True),
            _option("-inf", dataType="file", commandLine=True, mandatory=True),
            _option("-data", dataType="file", value="data.txt"),
            _option("-v", dataType="None"),
            _option("-verbose", dataType="None", commandLine=True),
            _option("-cpus", value="cpus", fromProcessSpec=True),
            _option("-outf", channel="fifo", value="writer_fifo", mirror=True),
            _option("-outv", channel="value_desc"),
        ],
    )
    reader = _process(
        "reader",
        [
            _option("-inf", value="[writer;-outf]"),
            _option("-inv", value="[writer;-outv]"),
            _option("-ctl", channel="fifo", value="reader_ctl"),
        ],
    )
    program = _program(
        "rt_standard",
        [writer, reader],
        [_edge("writer", "-outf", "reader", "-inf"), _edge("writer", "-outv", "reader", "-inv")],
    )

    _assert_model_round_trip(program, tmp_path)


def test_every_options_handler_mode_survives_the_round_trip(tmp_path):
    arrayproc = _process(
        "arrayproc",
        [_option("-id", value="${array[$idx]}"), _option("-outf", value="${process_outdir}/out_${idx}")],
        optionsHandler=OptionsHandler(mode="array", arrayCode="# One task per id\narray=(a b c)"),
    )
    genproc = _process(
        "genproc",
        [
            _option("-inf", value="[arrayproc;-outf]"),
            _option("-outf", value="${process_outdir}/out_${task_idx}"),
        ],
        optionsHandler=OptionsHandler(mode="generator", generatorSizeCode="echo 3"),
    )
    manualproc = _process(
        "manualproc",
        [_option("-x")],
        optionsHandler=OptionsHandler(
            mode="manual",
            manualCode=(
                "manualproc_define_opts()\n"
                "{\n"
                "    local cmdline=$1\n"
                "    local process_spec=$2\n"
                "    local process_name=$3\n"
                "    local process_outdir=$4\n"
                "    local optlist=\"\"\n"
                "\n"
                "    if true; then\n"
                "        define_opt \"-x\" \"1\" optlist || return 1\n"
                "    fi\n"
                "\n"
                "    save_opt_list optlist\n"
                "}"
            ),
        ),
    )
    program = _program(
        "rt_modes",
        [arrayproc, genproc, manualproc],
        [_edge("arrayproc", "-outf", "genproc", "-inf")],
    )

    _assert_model_round_trip(program, tmp_path)


def test_a_fanout_family_survives_the_round_trip(tmp_path):
    dispatch = _process(
        "dispatch",
        [
            _option("-w", dataType="int", commandLine=True, mandatory=True),
            _option("-outfith", value="${process_outdir}/part_${i}"),
        ],
    )
    dispatch.options[1].countSourceOptionId = dispatch.options[0].id
    worker = _process(
        "worker",
        [_option("-inf", value="[dispatch;-outfith]"), _option("-outf", value="${process_outdir}/out_${idx}")],
        optionsHandler=OptionsHandler(mode="array", arrayCode="array=(0 1)"),
    )
    program = _program("rt_fanout", [dispatch, worker], [_edge("dispatch", "-outfith", "worker", "-inf")])

    _assert_model_round_trip(program, tmp_path)


def test_a_self_loop_survives_the_round_trip_and_keeps_its_layer(tmp_path):
    counter = _process(
        "counter",
        [
            _option("-self", value="[counter;-outself]"),
            _option("-outself", channel="fifo", value="counter_self"),
            _option("-outsink", channel="fifo", value="counter_sink"),
        ],
    )
    sink = _process("sink", [_option("-in", value="[counter;-outsink]")])
    program = _program(
        "rt_selfloop",
        [counter, sink],
        [_edge("counter", "-outself", "counter", "-self"), _edge("counter", "-outsink", "sink", "-in")],
    )

    _assert_model_round_trip(program, tmp_path)

    # The self-loop does not push its process down: it stays in the first
    # layer, above the process it feeds.
    reimported = _generate_and_import(program, str(tmp_path))
    y = {process.name: process.position.y for process in reimported.processes}
    assert y["counter"] < y["sink"]
    assert y["counter"] == min(y.values())


def test_shared_directories_survive_the_round_trip(tmp_path):
    writer = _process("writer", [_option("-outd", channel="shared_dir", value="shared")])
    reader = _process("reader", [_option("-ind", channel="shared_dir", value="shared")])
    program = _program(
        "rt_shared",
        [writer, reader],
        [_edge("writer", "-outd", "reader", "-ind")],
        sharedDirs=["shared"],
    )

    reimported = _generate_and_import(program, str(tmp_path))
    canonical = _canonical_program(reimported)
    assert canonical == _canonical_program(program)
    assert reimported.availableSharedDirs == ["shared"]


def test_code_methods_specs_and_texts_survive_the_round_trip(tmp_path):
    pyproc = _process(
        "pyproc",
        [_option("-s", description='a "quoted" $value with `backquotes` and a \\ backslash')],
        description="Writes `out.txt` for $USER",
        language="python",
        code="import sys\nprint(sys.argv)",
        computationalSpecs=ComputationalSpecs(cpus=2, mem=512, time="01:00:00"),
        additionalSpecs=AdditionalSpecs(force=True, processdeps="afterok:other"),
        additionalMethods=AdditionalMethods(
            postCode='echo "post"\nif true; then\n    echo nested\nfi',
            skipCode="return 1",
        ),
    )
    other = _process("other", [])
    program = _program(
        "rt_texts",
        [pyproc, other],
        [],
        description="A program whose texts hold `backquotes` and $dollars",
        preamble="# Preamble comment\nMY_CONSTANT=1",
    )

    _assert_model_round_trip(program, tmp_path)
