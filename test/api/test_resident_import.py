"""
Import of a resident program (see "Script generation and import of a
resident program" in doc/design_doc_webui.md): the heredoc of a node
decomposed into its parts, the fifo tags and the program type read back,
and what import refuses, with an explanation for each place that does not
fit. The round trip of whole programs is in test_round_trip.py.
"""

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

from api.doc_mod import parse_program_type
from api.models import NodeCode
from api.option_handler_import import scan_fifo_tags
from api.program_import import import_program_from_script, read_preamble_processes
from api.resident_import import ResidentImportRefused, preamble_node_kinds, reuse_node
from api.resident_node_code import decompose_heredoc
from api.script_generation import generate_script

from test_resident_generation import _relay

_ENGINE_TEST_DIR = Path(__file__).resolve().parents[2] / "test" / "engine"


# --- the parts of a heredoc ---------------------------------------------------


def test_a_heredoc_written_by_hand_is_decomposed_into_the_parts_of_a_node():
    source = '''from debasher_runtime_lib import FBPProcess as Base
import os


class Counter(Base):
    """A counter."""
    STEP = 2

    def process_data(self, port_name, packet):
        # count
        self.n += self.STEP
    # between methods

    def helper(self):
        return self.n

    def capture_node_state(self):
        return {"n": self.n}

    def restore_node_state(self, state):
        self.n = state["n"]


if __name__ == "__main__":
    Counter().run()
'''
    result = decompose_heredoc(source)

    assert result.kind == "FBPProcess"
    assert result.misfits == []
    assert result.code == NodeCode(
        # An import of the node kind in another form stays in the preamble.
        preamble="from debasher_runtime_lib import FBPProcess as Base\nimport os",
        # A method with the name of a hook and another signature stays in
        # the class body, as an ordinary method.
        classBody=(
            '"""A counter."""\nSTEP = 2\n\n# between methods\n\ndef helper(self):\n    return self.n\n\n'
            'def restore_node_state(self, state):\n    self.n = state["n"]'
        ),
        processData="# count\nself.n += self.STEP",
        captureNodeState='return {"n": self.n}',
    )


def test_the_import_of_the_node_kind_in_the_form_that_script_generation_writes_is_left_out():
    result = decompose_heredoc(
        "from debasher_runtime_lib import DirectoryWatcher\nimport glob\n\n\n"
        "class Watch(DirectoryWatcher):\n    PATTERN = '*.bam'\n\n\nWatch().run()\n"
    )

    assert result.kind == "DirectoryWatcher"
    assert result.code.preamble == "import glob"
    assert result.code.classBody == "PATTERN = '*.bam'"


@pytest.mark.parametrize(
    "source, line, problem",
    [
        (
            "from debasher_runtime_lib import FBPProcess\n\n\n@deco\nclass Counter(FBPProcess):\n    pass\n\n\nCounter().run()\n",
            4,
            "has a decorator",
        ),
        (
            "from debasher_runtime_lib import FBPProcess\n\n\nclass Counter(FBPProcess, Mixin):\n    pass\n\n\nCounter().run()\n",
            4,
            "more than one base",
        ),
        (
            "from debasher_runtime_lib import FBPProcess\n\n\nclass Counter(FBPProcess):\n    pass\n\n\nCounter().run()\nprint('bye')\n",
            9,
            "code after the class",
        ),
        (
            "from debasher_runtime_lib import FBPProcess\n\n\nclass Counter(FBPProcess):\n"
            "    def process_data(self, port_name, packet):\n        pass\n    handler = process_data\n\n\nCounter().run()\n",
            7,
            "uses process_data, which it follows",
        ),
        (
            "from debasher_runtime_lib import Supervisor\n\n\nclass Sup(Supervisor):\n    HEARTBEAT_TIMEOUT_SECS = 3\n\n\nSup().run()\n",
            5,
            "the Supervisor has code of its own",
        ),
        ("class Counter(:\n", 1, "not valid Python"),
    ],
    ids=["decorator", "two-bases", "code-after-the-class", "hook-used-before", "supervisor-code", "syntax"],
)
def test_what_the_parts_of_a_node_cannot_hold_is_a_misfit_with_its_line(source, line, problem):
    misfits = decompose_heredoc(source).misfits

    assert [misfit.line for misfit in misfits] == [line]
    assert problem in misfits[0].problem
    assert misfits[0].fix


# --- what import reads back ---------------------------------------------------


def test_the_fifo_tags_are_read_back_for_single_options_and_fanout_families():
    source = (
        'debasher::define_fifo_opt "-ext" "x_ext" optlist --external || return 1;\n'
        'debasher::define_fifo_opt "-outf" "x_out" optlist || return 1;\n'
        'debasher::define_fifo_opt "-outworker_trig${i}" "t_${i}" optlist --control || return 1;\n'
    )

    assert scan_fifo_tags(source) == {"-ext": "external", "-outworker_trigith": "control"}


def test_the_program_type_is_read_from_the_module_documentation():
    assert parse_program_type("# relay\n\n## Program Type\n\n`resident`\n\n## counter\n") == "resident"
    assert parse_program_type("# relay\n\n## Program Type\n\n`general`\n") == "general"
    assert parse_program_type("# relay\n\n## Shared Directories\n") == "general"


# --- what import refuses ------------------------------------------------------


def _refusal(module: Path, debasher_mod_dir: str = "") -> str:
    with pytest.raises(ResidentImportRefused) as refused:
        import_program_from_script(module, debasher_mod_dir)
    return str(refused.value)


def test_a_supervisor_with_code_of_its_own_is_refused_with_its_lines():
    message = _refusal(_ENGINE_TEST_DIR / "debasher_chaos_ref.sh", str(_ENGINE_TEST_DIR))

    assert message.startswith("The web UI cannot hold this resident program, which the engine runs as it is.")
    assert "- sup, line 5: the Supervisor has code of its own" in message


def test_option_definitions_outside_the_grammar_are_refused_rather_than_kept_manual():
    message = _refusal(_ENGINE_TEST_DIR / "debasher_array_ref.sh", str(_ENGINE_TEST_DIR))

    assert "- worker: its option definition functions are outside what import understands" in message


def test_a_control_port_written_from_outside_with_a_supervisor_is_refused():
    message = _refusal(_ENGINE_TEST_DIR / "debasher_startup_ref.sh", str(_ENGINE_TEST_DIR))

    assert '- slow: option "-trigger" is a control port written from outside the program' in message


def test_code_that_names_a_port_of_the_wiring_is_refused():
    program = _relay()
    program.processes[0].nodeCode.processData = 'self.send_data("outhb", packet)'

    with tempfile.TemporaryDirectory() as tmp_dir:
        module = Path(tmp_dir) / "relay.sh"
        module.write_text(generate_script(program))
        message = _refusal(module)

    assert 'the code names "outhb", a port of the Supervisor wiring' in message


# --- a node of a module, reused ------------------------------------------------

_LAUNCHER_PREAMBLE = 'load_debasher_module "debasher_launcher_ref.sh"'
_LAUNCHER_NAMES = ["launch", "sink", "sup"]


def test_the_nodes_of_a_preamble_are_suggested_with_their_kinds_and_never_its_supervisor():
    processes, edges = read_preamble_processes(_LAUNCHER_PREAMBLE, _LAUNCHER_NAMES, str(_ENGINE_TEST_DIR))

    assert preamble_node_kinds(processes, edges) == {"launch": "ProgramLauncher", "sink": "FBPProcess"}


def test_a_reused_node_brings_its_code_and_options_without_the_wiring_nor_its_connections():
    processes, edges = read_preamble_processes(_LAUNCHER_PREAMBLE, _LAUNCHER_NAMES, str(_ENGINE_TEST_DIR))

    launch = reuse_node(processes, edges, "launch")

    assert launch.nodeKind == "ProgramLauncher"
    assert launch.nodeCode.classBody.startswith('PFILE = "debasher_launcher_batch.sh"')
    assert launch.initiator is False
    assert [(o.label, o.channel, o.fifoTag, o.value) for o in launch.options] == [
        ("-requests", "fifo", "external", "launch_requests"),
        ("-outdone", "fifo", None, "launch_done"),
    ]


def test_a_reused_node_loses_the_connections_of_the_program_it_comes_from():
    processes, edges = read_preamble_processes(_LAUNCHER_PREAMBLE, _LAUNCHER_NAMES, str(_ENGINE_TEST_DIR))

    sink = reuse_node(processes, edges, "sink")

    assert [(o.label, o.value) for o in sink.options] == [("-from_launch", "")]


def test_a_node_that_does_not_fit_is_refused_alone_and_its_neighbors_are_still_reused(tmp_path):
    # The Supervisor of the launcher module has code of its own, which import
    # refuses, and a node of this module has a decorated class.
    program = _relay()
    module = generate_script(program).replace("class Sink(FBPProcess):", "@decorate\nclass Sink(FBPProcess):")
    (tmp_path / "relay.sh").write_text(module)
    preamble = 'load_debasher_module "relay.sh"'
    processes, edges = read_preamble_processes(preamble, ["counter", "sink", "sup"], str(tmp_path))

    with pytest.raises(ResidentImportRefused, match=r'(?s)the node "sink".*- sink, line 4: the class of the node has a decorator'):
        reuse_node(processes, edges, "sink")

    processes, edges = read_preamble_processes(preamble, ["counter", "sink", "sup"], str(tmp_path))
    assert reuse_node(processes, edges, "counter").nodeKind == "FBPProcess"


def test_a_supervisor_or_a_process_that_is_not_a_node_is_not_reused():
    processes, edges = read_preamble_processes(_LAUNCHER_PREAMBLE, _LAUNCHER_NAMES, str(_ENGINE_TEST_DIR))

    with pytest.raises(ResidentImportRefused, match="no node named"):
        reuse_node(processes, edges, "sup")
