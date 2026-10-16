"""
A resident program as the SDK describes it: nodes given as Python files
with their class, the Supervisor, the limits of a node among the
specifications of its use, and what the SDK refuses of them.
"""

from pathlib import Path

import pytest

pytest.importorskip("pydantic")

from debasher import DefinitionError, Node, Process, Program, Supervisor  # noqa: E402

_ACCUMULATE = Path(__file__).parent / "data" / "running_sum" / "accumulate.py"


def _node_file(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text)
    return path


_LAUNCHER = """from debasher_runtime_lib import ProgramLauncher


class Launch(ProgramLauncher):
    program = "greet"


Launch().run()
"""


def test_a_node_is_split_into_the_parts_of_its_class(tmp_path):
    acc = Node("Accumulate", code=_ACCUMULATE, initiator=True)
    prg = Program("prg", resident=True)
    prg.add(acc)

    process = prg.to_model().processes[0]
    assert process.nodeKind == "FBPProcess"
    assert process.initiator is True
    assert process.language == "python"
    assert process.code == ""
    assert process.nodeCode.preamble == ""
    assert process.nodeCode.classBody.startswith("def __init__(self):")
    assert process.nodeCode.processData == 'self.total += packet\nself.send_data("outsum", self.total)'
    assert process.nodeCode.captureNodeState == 'return {"total": self.total}'


def test_the_node_kind_comes_from_the_base_class_of_the_file(tmp_path):
    launch = Node("Launch", code=_node_file(tmp_path, "launch.py", _LAUNCHER))
    prg = Program("prg", resident=True)
    prg.add(launch)

    process = prg.to_model().processes[0]
    assert process.nodeKind == "ProgramLauncher"
    assert process.initiator is False
    assert process.nodeCode.classBody == 'program = "greet"'


def test_a_supervisor_has_no_code_and_no_parts(tmp_path):
    prg = Program("prg", resident=True)
    prg.add(Supervisor("Sup", description="Watches."))

    process = prg.to_model().processes[0]
    assert (process.nodeKind, process.nodeCode, process.code, process.language) == ("Supervisor", None, "", "python")
    assert process.description == "Watches."
    assert process.options == []


def test_a_resident_program_is_marked_as_such_with_its_snapshot_period(tmp_path):
    prg = Program("prg", resident=True, snapshot_every_secs="30")
    prg.add(Node("Acc", code=_ACCUMULATE))

    model = prg.to_model()
    assert model.programType == "resident"
    assert model.executionOptions.snapshotEverySecs == "30"


def test_a_general_program_has_no_snapshot_period():
    assert Program("prg").to_model().executionOptions.snapshotEverySecs == ""


def test_the_specifications_of_a_node_go_with_its_computational_specifications(tmp_path):
    prg = Program("prg", resident=True)
    prg.add(Node("Acc", code=_ACCUMULATE), cpus=1, input_log_max_mb=64, heartbeat_timeout_s=5.5)

    specs = prg.to_model().processes[0].computationalSpecs
    assert (specs.cpus, specs.input_log_max_mb, specs.heartbeat_timeout_s) == (1, 64, 5.5)
    assert specs.out_backlog_max_mb is None


def test_the_module_of_a_resident_program_is_written(tmp_path):
    acc = Node("Accumulate", code=_ACCUMULATE, initiator=True)
    acc.fifo_input("-numbers", "string", "", "numbers", external=True)
    acc.fifo_output("-outsum", "string", "", "sum")
    prg = Program("prg", resident=True)
    prg.add(acc)
    prg.add(Supervisor("Sup"))

    module = prg.write(tmp_path / "home").read_text()
    assert 'debasher::program_type "resident"' in module
    assert "class Accumulate(FBPProcess):" in module
    assert 'debasher::define_fifo_opt "-numbers" "numbers" optlist --external || return 1' in module
    assert "class Sup(Supervisor):" in module


# --- what is refused -----------------------------------------------------------


def test_a_node_file_that_does_not_fit_the_parts_is_refused_with_its_misfits(tmp_path):
    source = _node_file(
        tmp_path,
        "bad.py",
        "from debasher_runtime_lib import FBPProcess\n\n\nclass Bad(FBPProcess):\n    pass\n\n\nprint('extra')\nBad().run()\n",
    )
    prg = Program("prg", resident=True)
    prg.add(Node("Bad", code=source))

    with pytest.raises(DefinitionError, match=r"does not fit the parts of a node.*\n  line 8: there is code after the class"):
        prg.to_model()


def test_a_node_file_without_a_node_class_is_refused(tmp_path):
    prg = Program("prg", resident=True)
    prg.add(Node("Plain", code=_node_file(tmp_path, "plain.py", "print('hi')\n")))

    with pytest.raises(DefinitionError, match="defines 0 classes that derive from a class of the runtime library"):
        prg.to_model()


def test_a_node_file_that_defines_a_supervisor_is_refused(tmp_path):
    source = _node_file(
        tmp_path, "sup.py", "from debasher_runtime_lib import Supervisor\n\n\nclass Sup(Supervisor):\n    pass\n\n\nSup().run()\n"
    )
    prg = Program("prg", resident=True)
    prg.add(Node("Sup", code=source))

    with pytest.raises(DefinitionError, match="a Supervisor is added with Supervisor"):
        prg.to_model()


def test_a_missing_node_file_is_reported_when_the_program_is_written(tmp_path):
    prg = Program("prg", resident=True)
    prg.add(Node("Acc", code=tmp_path / "none.py"))

    with pytest.raises(DefinitionError, match="cannot read its node file"):
        prg.to_model()


def test_a_resident_program_adds_nodes_only(tmp_path):
    prg = Program("prg", resident=True)

    with pytest.raises(DefinitionError, match="is not a node"):
        prg.add(Process("work", code="work.sh"))


def test_a_general_program_adds_no_node(tmp_path):
    prg = Program("prg")

    with pytest.raises(DefinitionError, match="only a resident program adds"):
        prg.add(Node("Acc", code=_ACCUMULATE))
    with pytest.raises(DefinitionError, match="only a resident program adds"):
        prg.add(Supervisor("Sup"))


def test_the_specifications_of_a_node_are_known_names_and_for_nodes_only(tmp_path):
    resident = Program("prg", resident=True)
    with pytest.raises(DefinitionError, match="unknown specification\\(s\\) colour"):
        resident.add(Node("Acc", code=_ACCUMULATE), colour="red")
    general = Program("general")
    with pytest.raises(DefinitionError, match="which only a node of a resident program reads"):
        general.add(Process("work", code="work.sh"), heartbeat_timeout_s=5)


def test_what_resident_generation_refuses_is_refused_with_its_message(tmp_path):
    acc = Node("Acc", code=_ACCUMULATE)
    acc.output("-outf", "file", "a file", "x.txt")
    acc["-outf"].channel = "value_desc"
    prg = Program("prg", resident=True)
    prg.add(acc)

    with pytest.raises(DefinitionError, match='uses the option channel "value_desc", which a resident program does not offer'):
        prg.write(tmp_path / "home")
