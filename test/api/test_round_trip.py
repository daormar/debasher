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

import subprocess
import tempfile
from pathlib import Path

import pytest

# The API reads and writes programs with pydantic 2 (api/requirements.txt).
# A pytest whose Python has an older one, such as that of the system, skips
# this module instead of failing it.
import pydantic  # noqa: E402

if int(pydantic.VERSION.split(".")[0]) < 2:
    pytest.skip(
        f"the API needs pydantic 2, and the Python of this pytest has {pydantic.VERSION}: "
        "create the virtual environment of api/README.md, install pytest into it, and "
        "run ./configure PYTEST=<venv>/bin/pytest",
        allow_module_level=True,
    )

from api import paths, persistence, script_generation
from api.models import (
    AdditionalMethods,
    AdditionalSpecs,
    ComputationalSpecs,
    ExecutionOptions,
    NodeCode,
    OptionsHandler,
    Position,
    Program,
    ProgramEdge,
    ProgramOption,
    ProgramProcess,
    SeqComputationalSpecs,
    SeqProcess,
)
from api.program_import import import_program_from_script

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROGRAMS_DIR = _REPO_ROOT / "data" / "programs"
_EXAMPLE_MODULES = sorted(_PROGRAMS_DIR.glob("*.sh"))


def _option_exclusions(process, option, connected) -> set[str]:
    """The fields of an option left out of the comparison (see
    _canonical_program): a shared_dir option keeps its directory as its
    value, connected or not."""
    excluded = {"id", "countSourceOptionId"}
    if (process.id, option.id) in connected and option.channel != "shared_dir":
        excluded.add("value")
    return excluded


def _canonical_program(program: Program) -> dict:
    """
    The part of `program` that a module can carry, in a form that two
    programs can be compared by: processes keyed by name and options by
    label (import gives both new ids and follows the order of the
    module documentation), connections named by process and option.
    What lives only in the program metadata is left out: ids, positions,
    groups, environment variables, execution and program options, the
    three directories, the shared directories reachable through loaded
    modules, which only import fills, and the value of a connected input,
    its connection sentinel, which the frontend derives from the edges
    compared here.
    """
    processes_by_id = {process.id: process for process in program.processes}
    connected = {
        (edge.targetProcessId, edge.targetOptionId)
        for edge in program.edges
    }

    def option_label(process_id: str, option_id: str) -> str:
        process = processes_by_id[process_id]
        return next(option.label for option in process.options if option.id == option_id)

    processes = {}
    for process in program.processes:
        labels_by_id = {option.id: option.label for option in process.options}
        options = {
            option.label: option.model_dump(exclude=_option_exclusions(process, option, connected))
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

    seq_processes = {
        seq_process.name: seq_process.model_dump(exclude={"id", "groupSource"})
        for seq_process in program.seqProcesses
    }

    top = program.model_dump(
        include={"name", "description", "preamble", "sharedDirs"}
    )

    return {"program": top, "processes": processes, "seqProcesses": seq_processes, "edges": edges}


def _write_script(directory: str, program: Program) -> None:
    """Write the generated script of `program` into `directory`, as a save does."""
    (Path(directory) / f"{program.name}.sh").write_text(script_generation.generate_script(program))


def _generate_and_import(program: Program, debasher_mod_dir: str) -> Program:
    with tempfile.TemporaryDirectory() as tmp_dir:
        _write_script(tmp_dir, program)
        persistence.copy_ext_alias_files(program, tmp_dir)
        return import_program_from_script(Path(tmp_dir) / f"{program.name}.sh", debasher_mod_dir)


# --- From a module to the model and back ---------------------------------


@pytest.mark.parametrize("module", _EXAMPLE_MODULES, ids=lambda module: module.name)
def test_import_is_a_fixed_point_of_the_round_trip(module):
    debasher_mod_dir = str(_PROGRAMS_DIR)

    imported = import_program_from_script(module, debasher_mod_dir)
    reimported = _generate_and_import(imported, debasher_mod_dir)

    assert _canonical_program(reimported) == _canonical_program(imported)


def test_the_sequential_process_of_a_module_is_imported():
    # A fixed point alone would not catch a sequential process lost on
    # every import
    module = _PROGRAMS_DIR / "debasher_cycle_dyn_sched.sh"

    imported = import_program_from_script(module, str(_PROGRAMS_DIR))

    seq_processes = {seq_process.name: seq_process for seq_process in imported.seqProcesses}
    assert list(seq_processes) == ["transformation_b"]
    assert seq_processes["transformation_b"].language == "python"
    assert "f.write(str(value + 2))" in seq_processes["transformation_b"].code
    assert seq_processes["transformation_b"].computationalSpecs == SeqComputationalSpecs(
        cpus=1, mem=32, time="00:01:00"
    )
    # Its code is that of the sequential process only, never also in the
    # code of the process that runs it
    worker = next(process for process in imported.processes if process.name == "worker")
    assert "transformation_b" not in worker.code.replace("seq_execute_slurm transformation_b", "")


def test_the_task_shaping_option_of_a_module_is_imported():
    module = _PROGRAMS_DIR / "debasher_dynamic_fanout.sh"

    imported = import_program_from_script(module, str(_PROGRAMS_DIR))

    processes = {process.name: process for process in imported.processes}
    worker_options = {option.label: option for option in processes["worker"].options}
    assert worker_options["-w"].taskShaping
    assert worker_options["-w"].commandLine and worker_options["-w"].mandatory
    assert not worker_options["-inf"].taskShaping
    # dispatch reads -w in its process function too, so it is an option of
    # its task
    dispatch_options = {option.label: option for option in processes["dispatch"].options}
    assert not dispatch_options["-w"].taskShaping


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
        [_option("-id", value="${array[$task_idx]}"), _option("-outf", value="${process_outdir}/out_${task_idx}")],
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
        [_option("-inf", value="[dispatch;-outfith]"), _option("-outf", value="${process_outdir}/out_${task_idx}")],
        optionsHandler=OptionsHandler(mode="array", arrayCode="array=(0 1)"),
    )
    program = _program("rt_fanout", [dispatch, worker], [_edge("dispatch", "-outfith", "worker", "-inf")])

    _assert_model_round_trip(program, tmp_path)


def test_task_shaping_options_survive_the_round_trip(tmp_path):
    # A task shaping option is read only by the options handler: by the code
    # that builds the array or by the code that counts the tasks. The count
    # of a fanout family, which its task reads, is an option of the task
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
        [
            _option("-w", dataType="int", commandLine=True, mandatory=True, taskShaping=True),
            _option("-inf", value="[dispatch;-outfith]"),
            _option("-outf", value="${process_outdir}/out_${task_idx}"),
        ],
        optionsHandler=OptionsHandler(
            mode="array",
            arrayCode='local w=$(get_cmdline_opt "${cmdline}" "-w")\narray=($(seq 0 $((w - 1))))',
        ),
    )
    counter = _process(
        "counter",
        [
            _option("-n", dataType="int", commandLine=True, mandatory=True, taskShaping=True),
            _option("-outf", value="${process_outdir}/out_${task_idx}"),
        ],
        optionsHandler=OptionsHandler(mode="generator", generatorSizeCode='get_cmdline_opt "${cmdline}" "-n"'),
    )
    program = _program(
        "rt_shaping", [dispatch, worker, counter], [_edge("dispatch", "-outfith", "worker", "-inf")]
    )

    _assert_model_round_trip(program, tmp_path)


def test_a_self_loop_survives_the_round_trip(tmp_path):
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


def test_a_label_edge_generates_the_same_script_as_a_line(tmp_path):
    writer = _process("writer", [_option("-outf", channel="fifo", value="writer_fifo")])
    reader = _process("reader", [_option("-inf", value="[writer;-outf]")])
    edge = _edge("writer", "-outf", "reader", "-inf")

    def program_with(display: str) -> Program:
        return _program("rt_label", [writer, reader], [edge.model_copy(update={"display": display})])

    label_program = program_with("label")

    assert script_generation.generate_script(label_program) == script_generation.generate_script(
        program_with("line")
    )
    _assert_model_round_trip(label_program, tmp_path)


def test_code_of_a_namespaced_process_in_another_language_survives_the_round_trip(tmp_path):
    # A Bash variable name cannot contain the "." of a namespace, so the
    # code has to be written as a heredoc function, not as a variable.
    pyproc = _process(
        "mymodule.pyproc",
        [_option("-s", value="hi")],
        language="python",
        code="import sys\nprint(sys.argv)",
    )
    rproc = _process(
        "mymodule.rproc",
        [_option("-s", value="hi")],
        language="r",
        code="print(commandArgs())",
    )
    program = _program("rt_namespaced_heredoc", [pyproc, rproc], [])

    _assert_model_round_trip(program, tmp_path)


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


def test_shared_and_task_subdirectories_survive_the_round_trip(tmp_path):
    split = _process(
        "split",
        [
            _option("-outd", channel="shared_dir", value="shared", subpath="${task_idx}"),
            _option("-outp", channel="process_outdir", subpath="${array[$task_idx]}"),
        ],
        optionsHandler=OptionsHandler(mode="array", arrayCode="array=(a b)"),
    )
    gen = _process(
        "gen",
        [_option("-outp", channel="process_outdir", subpath="part_${task_idx}")],
        optionsHandler=OptionsHandler(mode="generator", generatorSizeCode="echo 2"),
    )
    merge = _process(
        "merge",
        [
            _option("-ind", channel="shared_dir", value="shared"),
            _option("-outdir", channel="process_outdir"),
        ],
    )
    program = _program(
        "rt_subdirs",
        [split, gen, merge],
        [_edge("split", "-outd", "merge", "-ind")],
        sharedDirs=["shared"],
    )

    _assert_model_round_trip(program, tmp_path)


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


def test_sequential_processes_survive_the_round_trip(tmp_path):
    caller = _process(
        "caller",
        [],
        code='caller()\n{\n    seq_execute bashstep "$@"\n    seq_execute pystep 1\n}',
    )
    program = _program(
        "rt_seq",
        [caller],
        [],
        seqProcesses=[
            SeqProcess(
                id="bashstep",
                name="bashstep",
                description="A step in Bash",
                language="bash",
                code="bashstep()\n{\n    echo bash step\n}",
            ),
            SeqProcess(
                id="pystep",
                name="pystep",
                description="A step in Python",
                language="python",
                code="import sys\nprint(sys.argv)",
                computationalSpecs=SeqComputationalSpecs(cpus=2, mem=128, time="00:02:00"),
            ),
        ],
    )

    _assert_model_round_trip(program, tmp_path)


# A module whose aliases run plain functions of its own, which are neither
# processes nor sequential processes: a process alias of "greet" and a
# sequential alias of "increment", which "calc" runs as a step.
_ALIAS_TARGET_MODULE = r"""
greet()
{
    echo "hello from greet"
}

increment()
{
    echo $(( $1 + 1 )) > "$2"
}

greeter_document()
{
    debasher::document_process "Greets."
}

greeter_explain_opts()
{
    :
}

greeter_define_opts()
{
    local optlist=""
    save_opt_list optlist
}

calc_document()
{
    debasher::document_process "Adds one with a step."
}

calc_explain_opts()
{
    explain_opt "-outd" "<file>" "output directory"
}

calc_define_opts()
{
    local process_outdir=$4
    local optlist=""
    define_opt "-outd" "${process_outdir}" optlist || return 1
    save_opt_list optlist
}

calc()
{
    local outd=$(read_opt_value_from_func_args "-outd" "$@")
    seq_execute add_one 4 "${outd}/result.txt"
}

rt_alias_target_program()
{
    add_debasher_process "greeter" "cpus=1 mem=32 time=00:01:00" "alias=greet"
    add_debasher_process "calc" "cpus=1 mem=32 time=00:01:00"
    add_debasher_seq_process "add_one" "" "alias=increment"
}
"""


def test_a_plain_function_that_an_alias_runs_survives_the_round_trip_and_runs(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    module = source_dir / "rt_alias_target.sh"
    module.write_text(_ALIAS_TARGET_MODULE)

    imported = import_program_from_script(module, "")

    # The generated module defines the targets, so that it loads and runs
    saved_dir = tmp_path / "saved"
    saved_dir.mkdir()
    _write_script(str(saved_dir), imported)
    script = (saved_dir / "rt_alias_target.sh").read_text()
    assert script.count("greet()") == 1
    assert script.count("increment()") == 1

    reimported = import_program_from_script(saved_dir / "rt_alias_target.sh", "")
    assert _canonical_program(reimported) == _canonical_program(imported)

    debasher_exec = paths.find_bin_tool("debasher_exec")
    assert debasher_exec is not None
    outdir = tmp_path / "out"
    run = subprocess.run(
        [str(debasher_exec), "--pfile", str(saved_dir / "rt_alias_target.sh"),
         "--outdir", str(outdir), "--sched", "BUILTIN"],
        capture_output=True, text=True, timeout=120,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    assert (outdir / "calc" / "result.txt").read_text().strip() == "5"
    assert "hello from greet" in (outdir / "__exec__" / "greeter" / "greeter.stdout").read_text()


# --- Resident programs -----------------------------------------------------

_ENGINE_TEST_DIR = _REPO_ROOT / "test" / "engine"

# The resident reference modules of test/engine that the web UI can hold:
# the others give their Supervisor code of its own, or write their option
# definitions outside the grammar of import, and import refuses them (see
# test_resident_import.py).
_RESIDENT_MODULES = [_ENGINE_TEST_DIR / "debasher_halt_ref.sh"]


@pytest.mark.parametrize("module", _RESIDENT_MODULES, ids=lambda module: module.name)
def test_a_resident_module_that_the_web_ui_can_hold_is_a_fixed_point_of_the_round_trip(module):
    debasher_mod_dir = str(_ENGINE_TEST_DIR)

    imported = import_program_from_script(module, debasher_mod_dir)
    reimported = _generate_and_import(imported, debasher_mod_dir)

    assert imported.programType == "resident"
    assert _canonical_program(reimported) == _canonical_program(imported)


def _node(name: str, kind: str, options: list[ProgramOption], **fields) -> ProgramProcess:
    defaults = dict(
        language="python",
        code="",
        nodeKind=kind,
        nodeCode=None if kind == "Supervisor" else NodeCode(),
    )
    return _process(name, options, **(defaults | fields))


def test_a_resident_program_survives_the_round_trip(tmp_path):
    counter = _node(
        "counter",
        "FBPProcess",
        [
            _option("-ext", channel="fifo", fifoTag="external", value="counter_ext"),
            _option("-loop", value="[counter;-outloop]"),
            _option("-limit", value="10"),
            _option("-n", dataType="int", commandLine=True, mandatory=True),
            _option("-outloop", channel="fifo", value="counter_loop"),
            _option("-outf", channel="fifo", value="counter_out"),
        ],
        initiator=True,
        nodeCode=NodeCode(
            preamble="import json\n\n# The step of the count\nSTEP = 1",
            classBody=(
                "HEARTBEAT_INTERVAL_SECONDS = 1\n\ndef __init__(self):\n    super().__init__()\n"
                "    self.count = 0\n\ndef _limit(self):\n    return int(self.opts[\"limit\"])"
            ),
            processData=(
                "# Every packet counts\nself.count += STEP\nif self.count < self._limit():\n"
                '    self.send_data("outloop", self.count)\nself.send_data("outf", json.dumps(packet))'
            ),
            captureNodeState='return {"count": self.count}',
            restoreNodeState='self.count = node_state["count"]',
            initializeRuntime="pass",
        ),
        computationalSpecs=ComputationalSpecs(
            cpus=1,
            mem=64,
            time="00:05:00",
            input_log_max_mb=50,
            out_backlog_max_mb=4,
            out_backlog_fail_mb=32,
            gil_switch_interval_ms=1,
            startup_timeout_s=30,
        ),
    )
    launch = _node(
        "launch",
        "ProgramLauncher",
        [_option("-requests", value="[counter;-outf]"), _option("-outdone", channel="fifo", value="launch_done")],
        nodeCode=NodeCode(classBody='PFILE = "batch.sh"'),
        computationalSpecs=ComputationalSpecs(
            cpus=1, mem=64, time="00:05:00", max_concurrent_runs=2, batch_sched="SLURM"
        ),
    )
    watch = _node(
        "watch",
        "DirectoryWatcher",
        [_option("-watchdir", value="/data/incoming"), _option("-outrequests", channel="fifo", value="watch_req")],
        initiator=True,
        nodeCode=NodeCode(classBody='PATTERN = "*.bam"'),
    )
    sink = _node(
        "sink",
        "FBPProcess",
        [_option("-done", value="[launch;-outdone]"), _option("-req", value="[watch;-outrequests]")],
        nodeCode=NodeCode(processData="pass", captureNodeState="return {}", restoreNodeState="pass", initializeRuntime="pass"),
    )
    sup = _node(
        "sup",
        "Supervisor",
        [],
        computationalSpecs=ComputationalSpecs(cpus=1, mem=64, time="00:05:00", heartbeat_timeout_s=20, startup_timeout_s=60),
    )
    program = _program(
        "rt_resident",
        [counter, launch, watch, sink, sup],
        [
            _edge("counter", "-outloop", "counter", "-loop"),
            _edge("counter", "-outf", "launch", "-requests"),
            _edge("launch", "-outdone", "sink", "-done"),
            _edge("watch", "-outrequests", "sink", "-req"),
        ],
        programType="resident",
    )

    _assert_model_round_trip(program, tmp_path)


@pytest.mark.parametrize(
    "with_supervisor, array_initiator",
    [(True, False), (True, True), (False, False), (False, True)],
    ids=["supervisor", "supervisor-array-initiator", "no-supervisor", "no-supervisor-array-initiator"],
)
def test_the_wiring_of_an_array_survives_the_round_trip(tmp_path, with_supervisor, array_initiator):
    from test_resident_generation import _fanout

    _assert_model_round_trip(_fanout(with_supervisor, array_initiator), tmp_path)
