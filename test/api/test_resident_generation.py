"""
Script generation of a resident program (see "Script generation and import
of a resident program" in doc/design_doc_webui.md): the heredoc of a node
assembled from its parts, the fixed class of the Supervisor, the Supervisor
wiring derived from the nodes and the initiators, the fifo tags, the
program type and the specifications of a node, and what script generation
refuses. The modules generated here are also checked by the engine itself,
with debasher_exec --debug, which loads a resident program and validates it
without launching anything.
"""

import subprocess

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

from api import paths
from api.models import (
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
)
from api.resident_node_code import node_class_name, node_heredoc, normalized_part
from api.script_generation import generate_script

_ARRAY_CODE = (
    'local w=$(debasher::read_opt_value_from_line "${cmdline}" "-w")\n'
    "local -a array=()\n"
    'for ((j=0; j<w; j++)); do array+=("$j"); done'
)

_SINK_CODE = NodeCode(
    processData="pass",
    captureNodeState="return {}",
    restoreNodeState="pass",
    initializeRuntime="pass",
)


def _process(name, kind, options=(), mode="standard", **fields):
    defaults = {
        "id": name,
        "name": name,
        "description": f"the {name} node",
        "position": Position(x=0, y=0),
        "options": list(options),
        "optionsHandler": OptionsHandler(mode=mode, arrayCode=_ARRAY_CODE if mode == "array" else None),
        "language": "python",
        "code": "",
        "computationalSpecs": ComputationalSpecs(cpus=1, mem=32, time="00:10:00"),
        "additionalSpecs": AdditionalSpecs(force=False),
        "nodeKind": kind,
        # A copy for every node, so that a test that changes the code of one
        # changes nothing else.
        "nodeCode": None if kind == "Supervisor" else _SINK_CODE.model_copy(),
    }
    return ProgramProcess(**{**defaults, **fields})


def _option(option_id, label, direction, **fields):
    defaults = {
        "id": option_id,
        "label": label,
        "direction": direction,
        "dataType": "string",
        "description": label,
        "value": "",
        "commandLine": False,
    }
    return ProgramOption(**{**defaults, **fields})


def _edge(source, source_option, target, target_option):
    return ProgramEdge(
        id=f"{source_option}->{target_option}",
        sourceProcessId=source,
        sourceOptionId=source_option,
        targetProcessId=target,
        targetOptionId=target_option,
    )


def _program(name, processes, edges=()):
    return Program(
        id=name,
        name=name,
        programType="resident",
        preamble="",
        envVars={},
        outputDir="",
        executionOptions=ExecutionOptions(scheduler="BUILTIN"),
        programOptions={},
        processes=processes,
        edges=list(edges),
    )


def _relay(with_supervisor=True):
    """counter, an initiator with an external input, feeds sink."""
    counter = _process(
        "counter",
        "FBPProcess",
        [
            _option("c-ext", "-ext", "input", channel="fifo", fifoTag="external", value="counter_ext"),
            _option("c-outf", "-outf", "output", channel="fifo", value="counter_out"),
        ],
        initiator=True,
        computationalSpecs=ComputationalSpecs(
            cpus=1, mem=32, time="00:10:00", input_log_max_mb=50, startup_timeout_s=30
        ),
    )
    sink = _process("sink", "FBPProcess", [_option("s-in", "-inf", "input", value="[counter;-outf]")])
    processes = [counter, sink]
    if with_supervisor:
        processes.append(
            _process(
                "sup",
                "Supervisor",
                computationalSpecs=ComputationalSpecs(cpus=1, mem=32, time="00:10:00", heartbeat_timeout_s=20),
            )
        )
    return _program("relay", processes, [_edge("counter", "c-outf", "sink", "s-in")])


def _fanout(with_supervisor=True, array_initiator=False):
    """start scatters to the tasks of worker, as many as -w says, and
    collect gathers from them."""
    start = _process(
        "start",
        "FBPProcess",
        [
            _option("s-w", "-w", "input", dataType="int", commandLine=True, mandatory=True),
            _option("s-ext", "-ext", "input", channel="fifo", fifoTag="external", value="start_ext"),
            _option("s-outf", "-outfith", "output", channel="fifo", value="start_out_${i}", countSourceOptionId="s-w"),
        ],
        initiator=True,
    )
    worker = _process(
        "worker",
        "FBPProcess",
        [
            _option("w-in", "-inf", "input", value="[start;-outfith]"),
            _option("w-outf", "-outf", "output", channel="fifo", value="worker_out_${idx}"),
        ],
        mode="array",
        initiator=array_initiator,
    )
    collect = _process(
        "collect",
        "FBPProcess",
        [
            _option("k-w", "-w", "input", dataType="int", commandLine=True, mandatory=True),
            _option("k-in", "-indith", "input", value="[worker;-outf]", countSourceOptionId="k-w"),
        ],
    )
    processes = [start, worker, collect]
    if with_supervisor:
        processes.append(_process("sup", "Supervisor"))
    edges = [_edge("start", "s-outf", "worker", "w-in"), _edge("worker", "w-outf", "collect", "k-in")]
    return _program("fan", processes, edges)


def _function(script, name):
    """The body of the Bash function `name` of a generated module."""
    lines = script.splitlines()
    start = lines.index(f"{name}()")
    end = lines.index("}", start)
    return "\n".join(line.strip() for line in lines[start + 2 : end])


# --- the code of a node -------------------------------------------------------


def test_the_class_of_a_node_is_named_after_its_process():
    assert node_class_name("counter") == "Counter"
    assert node_class_name("org.ns.count_words") == "OrgNsCountWords"


def test_a_part_is_kept_without_its_shared_indentation_and_its_blank_ends():
    assert normalized_part("\n\n    a = 1\n\n    if a:\n        b = 2\n\n") == "a = 1\n\nif a:\n    b = 2"


def test_the_heredoc_of_a_node_assembles_its_parts_in_order():
    process = _process(
        "counter",
        "FBPProcess",
        nodeCode=NodeCode(
            preamble="import json\n",
            classBody="    LIMIT = 3\n",
            processData="self.send_data('outf', packet)",
            restoreNodeState="self.n = node_state",
        ),
    )

    assert node_heredoc(process) == (
        "from debasher_runtime_lib import FBPProcess\n"
        "\n"
        "import json\n"
        "\n"
        "\n"
        "class Counter(FBPProcess):\n"
        "    LIMIT = 3\n"
        "\n"
        "    def process_data(self, port_name, packet):\n"
        "        self.send_data('outf', packet)\n"
        "\n"
        "    def restore_node_state(self, node_state):\n"
        "        self.n = node_state\n"
        "\n"
        "\n"
        "Counter().run()"
    )


def test_a_node_with_no_code_gets_a_class_with_pass():
    process = _process("watch", "DirectoryWatcher", nodeCode=NodeCode())

    assert "class Watch(DirectoryWatcher):\n    pass\n" in node_heredoc(process)


def test_the_supervisor_has_its_fixed_class():
    script = generate_script(_relay())

    heredoc = script[script.index("sup_heredoc_py()") :]
    assert "class Sup(Supervisor):\n    pass\n\n\nSup().run()" in heredoc


# --- the Supervisor wiring ----------------------------------------------------


def test_the_wiring_of_a_program_with_a_supervisor():
    script = generate_script(_relay())

    counter = _function(script, "counter_define_opts")
    assert 'debasher::define_fifo_opt "-ext" "counter_ext" optlist --external || return 1' in counter
    assert 'debasher::define_fifo_opt "-outhb" "counter_hb" optlist || return 1' in counter
    assert 'debasher::define_opt_from_proc_out "-trigger" "sup" "-outcounter_trig" optlist || return 1' in counter
    sink = _function(script, "sink_define_opts")
    assert 'debasher::define_fifo_opt "-outhb" "sink_hb" optlist || return 1' in sink
    assert "-trigger" not in sink
    sup = _function(script, "sup_define_opts")
    assert 'debasher::define_opt_from_proc_out "-counter_hb" "counter" "-outhb" optlist || return 1' in sup
    assert 'debasher::define_opt_from_proc_out "-sink_hb" "sink" "-outhb" optlist || return 1' in sup
    assert 'debasher::define_fifo_opt "-outcounter_trig" "sup_counter_trig" optlist --control || return 1' in sup
    assert 'debasher::define_fifo_opt "-manual" "sup_manual" optlist --control || return 1' in sup
    assert 'debasher::define_cmdline_flag_if_given "${cmdline}" "-no-hold-fifos" optlist || return 1' in sup
    assert 'debasher::opt_is_non_mandatory_cmdline "-no-hold-fifos"' in _function(script, "sup_identify_cmdline_opts")


def test_without_a_supervisor_an_initiator_has_a_control_port_written_from_outside():
    script = generate_script(_relay(with_supervisor=False))

    counter = _function(script, "counter_define_opts")
    assert 'debasher::define_fifo_opt "-trigger" "counter_trigger" optlist --control || return 1' in counter
    assert "-outhb" not in script
    assert "sup_" not in script


def test_the_supervisor_reads_the_heartbeats_of_an_array_as_a_fanout_family():
    script = generate_script(_fanout())

    worker = _function(script, "worker_define_opts")
    assert 'debasher::define_fifo_opt "-outhb" "worker_hb_${idx}" optlist || return 1' in worker
    sup = _function(script, "sup_define_opts")
    assert 'local w=$(debasher::read_opt_value_from_line "${cmdline}" "-w")' in sup
    assert 'debasher::define_opt_from_proc_task_out "-worker_hb${i}" "worker" "${i}" "-outhb" optlist || return 1' in sup
    assert 'debasher::define_cmdline_opt "${cmdline}" "-w" optlist || return 1' in sup
    assert 'debasher::opt_is_cmdline "-w"' in _function(script, "sup_identify_cmdline_opts")


def test_the_supervisor_sends_to_the_tasks_of_an_array_initiator_as_a_fanout_family():
    script = generate_script(_fanout(array_initiator=True))

    worker = _function(script, "worker_define_opts")
    assert 'debasher::define_opt_from_proc_out "-trigger" "sup" "-outworker_trig${idx}" optlist || return 1' in worker
    sup = _function(script, "sup_define_opts")
    assert (
        'debasher::define_fifo_opt "-outworker_trig${i}" "sup_worker_trig_${i}" optlist --control || return 1'
        in sup
    )


# --- the module ---------------------------------------------------------------


def test_the_module_declares_a_resident_program_and_the_specifications_of_its_nodes():
    script = generate_script(_relay())

    assert 'debasher::program_type "resident"' in _function(script, "relay_program_type")
    program = _function(script, "relay_program")
    assert 'add_debasher_process "counter" "cpus=1 mem=32 time=00:10:00 input_log_max_mb=50 startup_timeout_s=30" ""' in program
    assert 'add_debasher_process "sup" "cpus=1 mem=32 time=00:10:00 heartbeat_timeout_s=20" ""' in program


def test_a_general_program_has_no_program_type_function():
    program = _relay()
    program.programType = "general"
    for process in program.processes:
        process.nodeKind = None
        process.language = "bash"
        process.code = f"{process.name}()\n{{\n    :\n}}"

    assert "_program_type()" not in generate_script(program)


# --- what script generation refuses -------------------------------------------


def _refused(program, match):
    with pytest.raises(ValueError, match=match):
        generate_script(program)


def test_a_second_supervisor_is_refused():
    program = _relay()
    program.processes.append(_process("monitor", "Supervisor"))
    _refused(program, "at most one Supervisor")


def test_the_manual_mode_is_refused():
    program = _relay()
    program.processes[1].optionsHandler = OptionsHandler(mode="manual", manualCode=":")
    _refused(program, "manual mode")


def test_an_option_of_the_user_with_a_label_of_the_wiring_is_refused():
    program = _relay()
    program.processes[1].options.append(_option("s-hb", "-outhb", "output", channel="fifo", value="x"))
    _refused(program, "label of the")


def test_a_channel_that_is_not_a_fifo_is_refused():
    program = _relay()
    program.processes[1].options.append(_option("s-v", "-outv", "output", channel="value_desc"))
    _refused(program, "value_desc")


def test_a_supervisor_with_options_of_its_own_is_refused():
    program = _relay()
    program.processes[2].options.append(_option("x", "-x", "input"))
    _refused(program, "takes no options of its own")


def test_an_array_that_reaches_no_counted_fanout_family_is_refused_with_a_supervisor():
    program = _fanout()
    start = program.processes[0]
    start.options[2].countSourceOptionId = None
    program.processes[2].options[1].countSourceOptionId = None
    _refused(program, "reaches no fanout family")


# --- what the engine says of the generated modules ----------------------------

_DEBASHER_EXEC = paths.find_bin_tool("debasher_exec")


@pytest.mark.skipif(_DEBASHER_EXEC is None, reason="debasher_exec not installed: run make install")
@pytest.mark.parametrize(
    "program, program_opts",
    [
        (_relay(), []),
        (_relay(with_supervisor=False), []),
        (_fanout(), ["-w", "3"]),
        (_fanout(with_supervisor=False), ["-w", "3"]),
        (_fanout(array_initiator=True), ["-w", "3"]),
    ],
    ids=["relay", "relay-no-supervisor", "fanout", "fanout-no-supervisor", "fanout-array-initiator"],
)
def test_the_engine_accepts_the_generated_module(tmp_path, program, program_opts):
    pfile = tmp_path / f"{program.name}.sh"
    pfile.write_text(generate_script(program))

    result = subprocess.run(
        [
            str(_DEBASHER_EXEC),
            "--pfile",
            str(pfile),
            "--outdir",
            str(tmp_path / "out"),
            "--sched",
            "BUILTIN",
            "--debug",
            *program_opts,
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
