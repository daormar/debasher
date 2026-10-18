"""
Tests of the topology file (api/topology.py): the conversion between the
program model and the artifact in both directions, the reading and
writing of the YAML, and what the module refuses.

The round trip is checked on every program shipped under
data/webui_programs/, loaded from its artifact: taken apart into a
topology and its files, written, read and put together again, the
program is the one that was loaded, apart from the value of a connected
input, which the frontend derives from the connections.
"""

import json
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

from api import persistence, topology
from api.models import (
    AdditionalMethods,
    AdditionalSpecs,
    ComputationalSpecs,
    CondaEnv,
    ExecutionOptions,
    NodeCode,
    OptionsHandler,
    Position,
    Program,
    ProgramEdge,
    ProgramOption,
    ProgramProcess,
)
from api.topology import TopologyError, dumps, join, loads, split

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WEBUI_PROGRAMS = sorted(
    path.parent for path in (_REPO_ROOT / "data" / "webui_programs").glob(f"*/{persistence.TOPOLOGY_FILENAME}")
)


# --- helpers ------------------------------------------------------------------


def _canonical(program: Program) -> dict:
    """`program` in a form that two programs with different ids can be
    compared by: processes by name, options by label, the count source by
    label, connections by names, and the value of a connected input left
    out, as are the paths of the files, which a program not loaded from a
    topology file does not have, and the newlines that end a code, which a
    file keeps and the program model does not."""

    def without_final_newlines(dumped: dict) -> dict:
        for key, value in dumped.items():
            if isinstance(value, str) and key.endswith(("code", "Code")):
                dumped[key] = value.rstrip("\n")
            elif isinstance(value, dict):
                without_final_newlines(value)
        return dumped

    processes_by_id = {process.id: process for process in program.processes}
    connected = {(edge.targetProcessId, edge.targetOptionId) for edge in program.edges}

    def label(process_id, option_id):
        return next(option.label for option in processes_by_id[process_id].options if option.id == option_id)

    processes = {}
    for process in program.processes:
        labels = {option.id: option.label for option in process.options}
        options = {}
        for option in process.options:
            excluded = {"id", "countSourceOptionId"}
            if (process.id, option.id) in connected:
                excluded.add("value")
            options[option.label] = option.model_dump(exclude=excluded) | {
                "countSource": labels.get(option.countSourceOptionId)
            }
        processes[process.name] = without_final_newlines(process.model_dump(exclude={"id", "options", "files"})) | {
            "options": options
        }
    edges = sorted(
        (
            processes_by_id[edge.sourceProcessId].name,
            label(edge.sourceProcessId, edge.sourceOptionId),
            processes_by_id[edge.targetProcessId].name,
            label(edge.targetProcessId, edge.targetOptionId),
            edge.display,
        )
        for edge in program.edges
    )
    seq_processes = {seq.name: without_final_newlines(seq.model_dump(exclude={"id", "files"})) for seq in program.seqProcesses}
    return program.model_dump(exclude={"id", "digest", "homeDir", "processes", "seqProcesses", "edges"}) | {
        "processes": processes,
        "seqProcesses": seq_processes,
        "edges": edges,
    }


def _round_trip(program: Program) -> Program:
    """`program` taken apart, written, read and put together again, with
    the copy of every script given as the file on disk would be."""
    taken_apart = split(program)
    scripts = {
        process.additionalSpecs.externalAlias: process.code + "\n"
        for process in [*program.processes, *program.seqProcesses]
        if process.additionalSpecs.externalAlias
    }
    return join(loads(dumps(taken_apart.topology)), scripts | taken_apart.files)


def _option(label: str, **fields) -> ProgramOption:
    defaults = {
        "id": f"id-{label}",
        "direction": "output" if label.startswith("-out") else "input",
        "dataType": "file",
        "description": f"the {label} option",
        "value": "",
        "commandLine": False,
        "mandatory": False,
    }
    return ProgramOption(**(defaults | {"label": label} | fields))


def _process(name: str, options: list[ProgramOption] | None = None, **fields) -> ProgramProcess:
    defaults = {
        "id": f"id-{name}",
        "description": f"The {name} process.",
        "position": Position(x=10, y=20),
        "options": options or [],
        "optionsHandler": OptionsHandler(mode="standard"),
        "language": "bash",
        "code": f"{name}()\n{{\n    :\n}}",
        "computationalSpecs": ComputationalSpecs(cpus=1, mem=32, time="00:01:00"),
        "additionalSpecs": AdditionalSpecs(force=False),
    }
    return ProgramProcess(**(defaults | {"name": name} | fields))


def _edge(source: str, source_label: str, target: str, target_label: str, display: str = "line") -> ProgramEdge:
    return ProgramEdge(
        id=f"edge-{source}-{source_label}-{target}-{target_label}",
        sourceProcessId=f"id-{source}",
        sourceOptionId=f"id-{source_label}",
        targetProcessId=f"id-{target}",
        targetOptionId=f"id-{target_label}",
        display=display,
    )


def _program(name: str, processes: list[ProgramProcess], edges: list[ProgramEdge] | None = None, **fields) -> Program:
    defaults = {
        "id": f"id-{name}",
        "description": "",
        "preamble": "",
        "envVars": {},
        "outputDir": "",
        "executionOptions": ExecutionOptions(scheduler="BUILTIN"),
        "programOptions": {},
        "edges": edges or [],
    }
    return Program(**(defaults | {"name": name, "processes": processes} | fields))


# --- the round trip ----------------------------------------------------------


@pytest.mark.parametrize("home_dir", _WEBUI_PROGRAMS, ids=lambda path: path.name)
def test_a_shipped_program_survives_the_round_trip(home_dir):
    program = persistence.load_program(str(home_dir))
    program.homeDir = ""

    assert _canonical(_round_trip(program)) == _canonical(program)


@pytest.mark.parametrize("home_dir", _WEBUI_PROGRAMS, ids=lambda path: path.name)
def test_the_topology_of_a_shipped_program_holds_no_code_and_no_ids(home_dir):
    program = persistence.load_program(str(home_dir))
    text = dumps(split(program).topology)

    assert "revision" not in text
    assert "homeDir" not in text
    assert "id:" not in text.replace("id: ", "")  # the id of a group is the one id the file holds
    for process in program.processes:
        if process.code:
            assert process.code not in text
            assert f"{process.name}." in text or process.files.code


def test_two_joins_of_the_same_topology_give_the_same_ids():
    program = persistence.load_program(str(_WEBUI_PROGRAMS[0]))
    first = _round_trip(program)
    second = _round_trip(program)

    assert first.model_dump() == second.model_dump()
    assert first.id == program.id  # a shipped program is loaded from its topology file, with the same ids


def test_the_code_goes_to_files_named_after_the_processes():
    program = _program(
        "count_words",
        [
            _process("count", code="count()\n{\n    wc -w\n}"),
            _process(
                "worker",
                language="python",
                code="print('hi')",
                optionsHandler=OptionsHandler(mode="array", arrayCode="local array=(1 2)"),
                additionalMethods=AdditionalMethods(skipCode="return 1", condaEnvsCode="echo py27 py27.yml"),
            ),
        ],
    )

    taken_apart = split(program)

    assert taken_apart.files == {
        "count.sh": "count()\n{\n    wc -w\n}\n",
        "worker.py": "print('hi')\n",
        "worker_tasks.sh": "local array=(1 2)\n",
        "worker_skip.sh": "return 1\n",
        "worker_conda_envs.sh": "echo py27 py27.yml\n",
    }
    worker = taken_apart.topology.processes["worker"]
    assert (worker.code, worker.mode, worker.tasks) == ("worker.py", "array", "worker_tasks.sh")
    assert worker.methods == {"skip": "worker_skip.sh", "conda_envs": "worker_conda_envs.sh"}
    assert worker.language is None  # the extension says it


def test_a_bash_process_named_as_its_program_does_not_take_the_name_of_the_script():
    program = _program("count", [_process("count")])

    taken_apart = split(program)

    assert taken_apart.topology.processes["count"].code == "count_process.sh"
    assert list(taken_apart.files) == ["count_process.sh"]


def test_the_paths_a_process_was_loaded_with_are_kept():
    program = _program("prg", [_process("count")])
    text = (
        "schema_version: 1\nname: prg\nprocesses:\n  count:\n    code: src/wc.sh\n    mode: array\n"
        "    tasks: src/wc_tasks.sh\n    methods: {skip: src/never.sh}\n"
    )
    files = {"src/wc.sh": "count() { :; }\n", "src/wc_tasks.sh": "local array=(1)\n", "src/never.sh": "return 1\n"}

    joined = join(loads(text), files)
    taken_apart = split(joined)

    assert joined.processes[0].files.model_dump() == {
        "code": "src/wc.sh",
        "tasks": "src/wc_tasks.sh",
        "methods": {"skip": "src/never.sh"},
    }
    assert taken_apart.files == files
    assert program.processes[0].files.code == ""  # a process not loaded from a topology file


def test_a_script_is_named_and_not_written():
    program = _program(
        "prg",
        [
            _process(
                "dispatch",
                language="python",
                code="a copy of the script",
                additionalSpecs=AdditionalSpecs(force=False, externalAlias="./tools/dispatch.py"),
            )
        ],
    )

    taken_apart = split(program)

    assert taken_apart.files == {}
    assert taken_apart.topology.processes["dispatch"].script == "./tools/dispatch.py"
    joined = join(taken_apart.topology, {"./tools/dispatch.py": "the script\n"})
    assert joined.processes[0].additionalSpecs.externalAlias == "./tools/dispatch.py"
    assert (joined.processes[0].language, joined.processes[0].code) == ("python", "the script")
    assert join(taken_apart.topology, {}).processes[0].code == ""


def test_connections_are_kept_on_the_inputs_that_read_them():
    program = _program(
        "prg",
        [
            _process("a", [_option("-outf", value="${process_outdir}/a.txt")]),
            _process("b", [_option("-outg", value="${process_outdir}/b.txt")]),
            _process("c", [_option("-inf"), _option("-ing")]),
        ],
        [_edge("a", "-outf", "c", "-inf", "label"), _edge("a", "-outf", "c", "-ing"), _edge("b", "-outg", "c", "-ing")],
    )

    taken_apart = split(program)

    c = taken_apart.topology.processes["c"].options
    assert c["-inf"].from_ == "a.-outf"
    assert c["-inf"].display == "label"
    assert c["-ing"].from_ == ["a.-outf", "b.-outg"]
    assert c["-ing"].display is None
    assert "from: a.-outf" in dumps(taken_apart.topology)
    assert _canonical(_round_trip(program)) == _canonical(program)


def test_a_connected_shared_dir_input_keeps_the_name_of_its_directory():
    program = _program(
        "prg",
        [
            _process("a", [_option("-outd", channel="shared_dir", value="summary")]),
            _process("b", [_option("-ind", channel="shared_dir", value="summary")]),
        ],
        [_edge("a", "-outd", "b", "-ind")],
    )

    taken_apart = split(program)

    b = taken_apart.topology.processes["b"].options["-ind"]
    assert (b.value, b.from_) == ("summary", "a.-outd")
    assert _canonical(_round_trip(program)) == _canonical(program)


def test_a_namespaced_source_is_read():
    text = (
        "schema_version: 1\nname: prg\nprocesses:\n  org.ns.a:\n    options:\n"
        "      -outf: {type: file, value: x}\n  b:\n    options:\n      -inf: {type: file, from: org.ns.a.-outf}\n"
    )

    joined = join(loads(text), {})

    assert len(joined.edges) == 1
    assert joined.edges[0].sourceProcessId == joined.processes[0].id


def test_a_fanout_family_counts_by_label():
    options = [
        _option("-w", dataType="int", commandLine=True, mandatory=True),
        _option("-outf-ith", channel="fifo", value="fifo_${i}", countSourceOptionId="id--w"),
    ]
    program = _program("prg", [_process("dispatch", options)])

    taken_apart = split(program)

    assert taken_apart.topology.processes["dispatch"].options["-outf-ith"].count_source == "-w"
    joined = _round_trip(program)
    w, family = joined.processes[0].options
    assert family.countSourceOptionId == w.id


def test_the_mandatory_of_a_command_line_option_is_the_default():
    text = (
        "schema_version: 1\nname: prg\nprocesses:\n  p:\n    options:\n"
        "      -l: {type: int, cmdline: true}\n"
        "      -v: {type: flag, cmdline: true}\n"
        "      --log: {type: string, cmdline: true, mandatory: false}\n"
        "      -inf: {type: file}\n"
    )

    options = {option.label: option for option in join(loads(text), {}).processes[0].options}

    assert options["-l"].mandatory is True
    assert options["-v"].mandatory is False
    assert options["-v"].dataType == "None"
    assert options["--log"].mandatory is False
    assert options["-inf"].mandatory is False
    written = dumps(split(join(loads(text), {})).topology)
    assert "mandatory: true" not in written
    assert "mandatory: false" in written  # of --log only
    assert written.count("mandatory") == 1


def test_a_node_is_a_whole_python_file():
    node = _process(
        "accumulate",
        [_option("-numbers", channel="fifo", fifoTag="external", value="numbers")],
        language="python",
        code="",
        nodeKind="FBPProcess",
        initiator=True,
        nodeCode=NodeCode(classBody="def __init__(self):\n    super().__init__()\n    self.total = 0", processData="self.total += packet"),
    )
    supervisor = _process("sup", language="python", code="", nodeKind="Supervisor")
    program = _program("sums", [node, supervisor], programType="resident")

    taken_apart = split(program)

    assert list(taken_apart.files) == ["accumulate.py"]
    assert "class Accumulate(FBPProcess):" in taken_apart.files["accumulate.py"]
    assert taken_apart.topology.type == "resident"
    assert taken_apart.topology.processes["sup"].code is None
    assert taken_apart.topology.processes["accumulate"].initiator is True
    joined = _round_trip(program)
    assert joined.processes[0].nodeCode == node.nodeCode
    assert joined.processes[0].code == ""
    assert joined.processes[1].nodeKind == "Supervisor"
    assert _canonical(joined) == _canonical(program)


def test_a_process_without_a_position_is_placed_in_layers():
    text = (
        "schema_version: 1\nname: prg\nprocesses:\n  a:\n    options:\n      -outf: {type: file, value: x}\n"
        "  b:\n    position: {x: 5, y: 6}\n    options:\n      -inf: {type: file, from: a.-outf}\n"
    )

    a, b = join(loads(text), {}).processes

    assert (b.position.x, b.position.y) == (5, 6)
    assert (a.position.x, a.position.y) == (100, 100)


# --- the YAML -----------------------------------------------------------------


def test_bash_words_are_written_and_read_as_strings():
    program = _program(
        "prg",
        [
            _process(
                "p",
                [
                    _option("-n", dataType="int", value="200", description="yes"),
                    _option("-outf", value="${process_outdir}/out.txt"),
                    _option("-inf", value="1e3"),
                ],
            )
        ],
        programOptions={"-n": "200", "-flag": "no", "-x": "null"},
        preamble="load_debasher_module a\nload_debasher_module b",
    )

    text = dumps(split(program).topology)
    joined = join(loads(text), split(program).files)

    assert text.startswith("# yaml-language-server: $schema=")
    assert "preamble: |-\n  load_debasher_module a\n  load_debasher_module b\n" in text
    assert joined.programOptions == {"-n": "200", "-flag": "no", "-x": "null"}
    values = {option.label: option.value for option in joined.processes[0].options}
    assert values == {"-n": "200", "-outf": "${process_outdir}/out.txt", "-inf": "1e3"}
    assert joined.processes[0].options[0].description == "yes"


def test_a_hand_written_number_is_read_as_a_string_and_a_count_as_a_number():
    text = "schema_version: 1\nname: prg\nprogram_options: {-n: 200}\nprocesses:\n  p:\n    specs: {cpus: 2, mem: 32}\n    initiator: no\n"

    joined = join(loads(text), {})

    assert joined.programOptions == {"-n": "200"}
    assert (joined.processes[0].computationalSpecs.cpus, joined.processes[0].computationalSpecs.mem) == (2.0, 32.0)


def test_defaults_are_not_written():
    program = _program("prg", [_process("p", [_option("-inf")])])

    text = dumps(split(program).topology)

    assert "execution" not in text
    assert "mirror" not in text
    assert "channel" not in text
    assert "force" not in text
    assert "initiator" not in text


def test_the_json_schema_names_the_version_and_refuses_unknown_keys():
    schema = topology.json_schema()

    assert schema["properties"]["schema_version"]["type"] == "integer"
    assert schema["additionalProperties"] is False
    assert "from" in schema["$defs"]["TopologyOption"]["properties"]


# --- what is refused ---------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("schema_version: 1\nname: prg\nname: other\n", "given twice"),
        ("schema_version: 1\nname: prg\nprocesses:\n  p:\n    options: {-a: {type: file}, -a: {type: file}}\n", "given twice"),
        ("schema_version: 1\nname: prg\nprocesss: {}\n", "does not fit its schema"),
        ("schema_version: 1\nname: prg\nprocesses:\n  p:\n    options:\n      -inf: {type: file, mirrored: true}\n", "mirrored"),
        ("schema_version: 2\nname: prg\n", "written for schema version 2"),
        ("name: prg\n", "schema_version"),
        ("schema_version: 0\nname: prg\n", "not a version"),
        ("- a\n- b\n", "not a topology file"),
        ("schema_version: 1\nname: prg\nprocesses: [\n", "not a topology file"),
    ],
)
def test_a_topology_file_that_cannot_be_read_is_refused(text, message):
    with pytest.raises(TopologyError, match=message):
        loads(text)


@pytest.mark.parametrize(
    ("text", "files", "message"),
    [
        (
            "schema_version: 1\nname: prg\nprocesses:\n  b:\n    options:\n      -inf: {type: file, from: a.-outf}\n",
            {},
            'reads from "a", which is no process',
        ),
        (
            "schema_version: 1\nname: prg\nprocesses:\n  a: {}\n  b:\n    options:\n      -inf: {type: file, from: a.-outf}\n",
            {},
            "has no such option",
        ),
        (
            "schema_version: 1\nname: prg\nprocesses:\n  b:\n    options:\n      -inf: {type: file, from: nothing}\n",
            {},
            "is not a source",
        ),
        (
            "schema_version: 1\nname: prg\nprocesses:\n  b:\n    options:\n      -outf-ith: {type: file, count_source: -w}\n",
            {},
            "no option of the process",
        ),
        ("schema_version: 1\nname: prg\nprocesses:\n  b:\n    code: b.sh\n", {}, "names the file b.sh, which is missing"),
        ("schema_version: 1\nname: prg\nprocesses:\n  b:\n    tasks: b_tasks.sh\n", {"b_tasks.sh": ""}, "no mode"),
        ("schema_version: 1\nname: prg\nprocesses:\n  b:\n    mode: array\n", {}, "names no tasks file"),
        (
            "schema_version: 1\nname: prg\nprocesses:\n  b:\n    mode: manual\n    tasks: b_tasks.py\n",
            {"b_tasks.py": ""},
            "manual mode, whose tasks file is a Bash function",
        ),
        (
            "schema_version: 1\nname: prg\nprocesses:\n  b:\n    methods: {post: b_post.py}\n",
            {"b_post.py": ""},
            "the post method is a Bash body",
        ),
        (
            "schema_version: 1\nname: prg\nprocesses:\n  b:\n    methods: {conda_envs: b_envs.sh}\n    conda_envs: {py27: py27.yml}\n",
            {"b_envs.sh": "define_conda_env py27 py27.yml\n"},
            "both conda_envs and a conda_envs method file",
        ),
        ("schema_version: 1\nname: prg\nprocesses:\n  b:\n    code: b.txt\n", {"b.txt": ""}, "says no language"),
        ("schema_version: 1\nname: prg\nprocesses:\n  b:\n    code: b.sh\n    alias: a\n", {"b.sh": ""}, "give one of them"),
        ("schema_version: 1\nname: prg\nprocesses:\n  b:\n    alias_opt_map: {-a: -b}\n", {}, "without an alias"),
        ("schema_version: 1\nname: prg\ntype: resident\nprocesses:\n  s:\n    kind: Supervisor\n    code: s.py\n", {"s.py": ""}, "Supervisor"),
        (
            "schema_version: 1\nname: prg\ntype: resident\nprocesses:\n  n:\n    kind: FBPProcess\n    code: n.py\n",
            {"n.py": "print('not a node')\n"},
            "does not fit the parts of a node",
        ),
    ],
)
def test_a_topology_that_names_what_does_not_exist_is_refused(text, files, message):
    with pytest.raises(TopologyError, match=message):
        join(loads(text), files)


def test_a_file_with_an_explicit_language_is_read():
    text = "schema_version: 1\nname: prg\nprocesses:\n  b:\n    code: b.txt\n    language: perl\n"

    joined = join(loads(text), {"b.txt": "print 1;\n"})

    assert (joined.processes[0].language, joined.processes[0].code) == ("perl", "print 1;")
    assert split(joined).topology.processes["b"].language == "perl"


def test_a_tasks_file_and_a_skip_file_in_python_are_read_as_python():
    text = (
        "schema_version: 1\nname: prg\nprocesses:\n  w:\n    code: w.sh\n    mode: array\n"
        "    tasks: py/w_tasks.py\n    methods: {skip: py/w_skip.py, post: w_post.sh}\n"
    )
    files = {
        "w.sh": "w() { :; }\n",
        "py/w_tasks.py": "def tasks(run):\n    return [1, 2]\n",
        "py/w_skip.py": "def skip(task):\n    return False\n",
        "w_post.sh": "echo post\n",
    }

    joined = join(loads(text), files)

    process = joined.processes[0]
    assert (process.optionsHandler.language, process.optionsHandler.arrayCode) == (
        "python",
        "def tasks(run):\n    return [1, 2]",
    )
    assert (process.additionalMethods.skipLanguage, process.additionalMethods.skipCode) == (
        "python",
        "def skip(task):\n    return False",
    )
    assert split(joined).files == files


def test_a_tasks_file_takes_the_extension_of_its_language():
    process = _process(
        "w",
        optionsHandler=OptionsHandler(mode="generator", generatorSizeCode="def tasks(run):\n    return 2", language="python"),
        additionalMethods=AdditionalMethods(skipCode="def skip(task):\n    return True", skipLanguage="python"),
    )
    taken_apart = split(_program("prg", [process]))
    assert taken_apart.topology.processes["w"].tasks == "w_tasks.py"
    assert taken_apart.topology.processes["w"].methods == {"skip": "w_skip.py"}

    # A file loaded in one language and changed to the other is written
    # under the default name of the new one
    process.files.tasks = "tasks/w.sh"
    process.files.methods = {"skip": "w_skip.sh"}
    taken_apart = split(_program("prg", [process]))
    assert taken_apart.topology.processes["w"].tasks == "w_tasks.py"
    assert taken_apart.topology.processes["w"].methods == {"skip": "w_skip.py"}

    process.optionsHandler.language = "bash"
    assert split(_program("prg", [process])).topology.processes["w"].tasks == "tasks/w.sh"


def test_the_conda_environments_and_docker_images_as_data_survive_the_round_trip():
    process = _process(
        "w",
        additionalMethods=AdditionalMethods(
            condaEnvs=[CondaEnv(name="py27", file="py27.yml"), CondaEnv(name="r4", file="envs/r4.yml")],
            dockerImgs=["library/hello-world", "ubuntu:24.04"],
        ),
    )
    program = _program("prg", [process])

    taken_apart = split(program)
    assert "conda_envs:\n      py27: py27.yml\n      r4: envs/r4.yml" in dumps(taken_apart.topology)
    assert taken_apart.topology.processes["w"].methods == {}
    assert _canonical(_round_trip(program)) == _canonical(program)


def test_the_published_schema_is_the_one_of_the_model():
    published = _REPO_ROOT / "rtdocs" / "source" / "_static" / "schema" / f"program-{topology.SCHEMA_VERSION}.json"

    assert json.loads(published.read_text()) == topology.json_schema()
    assert topology.SCHEMA_URL.endswith(f"/_static/schema/program-{topology.SCHEMA_VERSION}.json")
