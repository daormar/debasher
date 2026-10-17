"""
What the SDK writes from a description, and what it refuses: the
processes and the program as the user gives them, the connections from
the sources of the inputs, the ids from the names, the positions from
the layout of the editor, and the errors that name the process and the
option concerned.
"""

from pathlib import Path

import pytest

pytest.importorskip("pydantic")

from api import persistence  # noqa: E402
from debasher import DefinitionError, Process, Program, in_outdir  # noqa: E402

from examples import SDK_PROGRAMS_DIR  # noqa: E402

_HELLO_WORLD = SDK_PROGRAMS_DIR / "sdk_hello_world_py" / "hello_world.py"


def _code(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text)
    return path


def _bash_process(tmp_path: Path, name: str, description: str = "") -> Process:
    return Process(name, code=_code(tmp_path, f"{name}.sh", f"{name}()\n{{\n    :\n}}\n"), description=description)


# --- the model ---------------------------------------------------------------


def test_a_process_carries_its_code_and_the_language_of_its_file(tmp_path):
    hello = Process("hello", code=_HELLO_WORLD)
    prg = Program("prg")
    prg.add(hello)

    process = prg.to_model().processes[0]
    assert process.language == "python"
    assert process.code == _HELLO_WORLD.read_text().rstrip("\n")
    assert process.computationalSpecs.cpus is None
    assert process.additionalSpecs.externalAlias is None


def test_a_relative_code_path_is_taken_from_the_directory_of_the_file_that_defines_the_process(tmp_path):
    (tmp_path / "defs").mkdir()
    _code(tmp_path / "defs", "work.sh", "work()\n{\n    :\n}\n")
    _code(tmp_path, "defs/make_it.py", "from debasher import Process\nwork = Process('work', code='work.sh')\n")
    from debasher.build import load_program  # noqa: F401

    namespace = {}
    exec(compile((tmp_path / "defs" / "make_it.py").read_text(), str(tmp_path / "defs" / "make_it.py"), "exec"), namespace)

    assert namespace["work"].code_path == tmp_path / "defs" / "work.sh"


def test_the_specifications_are_those_of_the_use_of_the_process_in_the_program(tmp_path):
    work = _bash_process(tmp_path, "work")
    small = Program("small")
    small.add(work, cpus=1, mem=256, time="00:01:00")
    big = Program("big")
    big.add(work, cpus=8, mem=16000, processdeps="afterok:other", force=True)
    big.add(_bash_process(tmp_path, "other"))

    small_specs = small.to_model().processes[0]
    big_specs = big.to_model().processes[0]
    assert (small_specs.computationalSpecs.cpus, small_specs.computationalSpecs.mem) == (1, 256)
    assert small_specs.computationalSpecs.time == "00:01:00"
    assert small_specs.additionalSpecs.force is False
    assert (big_specs.computationalSpecs.cpus, big_specs.computationalSpecs.mem) == (8, 16000)
    assert big_specs.additionalSpecs.processdeps == "afterok:other"
    assert big_specs.additionalSpecs.force is True


def test_the_options_keep_their_order_and_their_fields(tmp_path):
    work = _bash_process(tmp_path, "work")
    work.output("-outf", "file", "the result", in_outdir("result.txt"))
    work.cmdline_opt("-n", "int", "how many")
    work.cmdline_opt("-label", "string", "a label", mandatory=False)
    work.cmdline_flag("-verbose", "say more")
    work.input("-inf", "file", "a fixed input", value="data/input.txt")
    prg = Program("prg")
    prg.add(work)

    options = prg.to_model().processes[0].options
    assert [option.label for option in options] == ["-outf", "-n", "-label", "-verbose", "-inf"]
    outf, n, label, verbose, inf = options
    assert (outf.direction, outf.dataType, outf.value) == ("output", "file", "${process_outdir}/result.txt")
    assert (n.direction, n.commandLine, n.mandatory) == ("input", True, True)
    assert (label.commandLine, label.mandatory) == (True, False)
    assert (verbose.dataType, verbose.commandLine) == ("None", True)
    assert (inf.commandLine, inf.value) == (False, "data/input.txt")


def test_a_connection_comes_from_the_source_of_an_input(tmp_path):
    writer = _bash_process(tmp_path, "writer")
    outf = writer.output("-outf", "file", "what it writes", in_outdir("f.txt"))
    reader = _bash_process(tmp_path, "reader")
    reader.input("-inf", "file", "what it reads", source=outf)
    prg = Program("prg")
    prg.add(writer)
    prg.add(reader)

    model = prg.to_model()
    (edge,) = model.edges
    writer_model, reader_model = model.processes
    assert edge.sourceProcessId == writer_model.id
    assert edge.sourceOptionId == writer_model.options[0].id
    assert edge.targetProcessId == reader_model.id
    assert edge.targetOptionId == reader_model.options[0].id
    assert edge.display == "line"


def test_a_source_may_be_given_by_name_as_a_module_names_it(tmp_path):
    writer = _bash_process(tmp_path, "writer")
    writer.output("-outf", "file", "what it writes", in_outdir("f.txt"))
    reader = _bash_process(tmp_path, "reader")
    reader.input("-inf", "file", "what it reads", source=("writer", "-outf"), display="label")
    prg = Program("prg")
    prg.add(writer)
    prg.add(reader)

    (edge,) = prg.to_model().edges
    assert edge.sourceProcessId == prg.to_model().processes[0].id
    assert edge.display == "label"


def test_a_fan_in_gives_one_connection_per_source(tmp_path):
    a = _bash_process(tmp_path, "a")
    a.output("-outf", "file", "", in_outdir("a.txt"))
    b = _bash_process(tmp_path, "b")
    b.output("-outf", "file", "", in_outdir("b.txt"))
    gather = _bash_process(tmp_path, "gather")
    gather.input("-inf", "file", "", source=[a["-outf"], ("b", "-outf")])
    prg = Program("prg")
    for process in (a, b, gather):
        prg.add(process)

    edges = prg.to_model().edges
    assert len(edges) == 2
    assert {edge.sourceProcessId for edge in edges} == {p.id for p in prg.to_model().processes[:2]}


def test_the_ids_come_from_the_names_so_that_two_builds_agree(tmp_path):
    def build():
        writer = _bash_process(tmp_path, "writer")
        writer.output("-outf", "file", "", in_outdir("f.txt"))
        reader = _bash_process(tmp_path, "reader")
        reader.input("-inf", "file", "", source=writer["-outf"])
        prg = Program("prg")
        prg.add(writer)
        prg.add(reader)
        return prg.to_model()

    assert build().model_dump() == build().model_dump()


def test_processes_are_laid_out_as_the_editor_lays_out_an_imported_program(tmp_path):
    writer = _bash_process(tmp_path, "writer")
    writer.output("-outf", "file", "", in_outdir("f.txt"))
    reader = _bash_process(tmp_path, "reader")
    reader.input("-inf", "file", "", source=writer["-outf"])
    other = _bash_process(tmp_path, "other")
    prg = Program("prg")
    prg.add(reader)
    prg.add(writer)
    prg.add(other, position=(500, 700))

    positions = {p.name: (p.position.x, p.position.y) for p in prg.to_model().processes}
    assert positions == {"writer": (100, 100), "reader": (100, 260), "other": (500, 700)}


def test_the_program_carries_what_a_run_is_given(tmp_path):
    prg = Program(
        "prg",
        description="A program.",
        program_options={"-n": "3"},
        preamble="load_debasher_module other",
        env_vars={"DEBASHER_MOD_DIR": "/mods"},
        shared_dirs=["shared"],
        scheduler="SLURM",
        conda_support=True,
    )
    prg.add(_bash_process(tmp_path, "work"))

    model = prg.to_model()
    assert model.name == "prg"
    assert model.description == "A program."
    assert model.programOptions == {"-n": "3"}
    assert model.preamble == "load_debasher_module other"
    assert model.envVars == {"DEBASHER_MOD_DIR": "/mods"}
    assert model.sharedDirs == ["shared"]
    assert model.executionOptions.scheduler == "SLURM"
    assert model.executionOptions.condaSupport is True
    assert model.executionOptions.dockerSupport is False
    assert model.programType == "general"


def test_a_process_without_code_takes_it_from_a_loaded_module():
    prg = Program("prg", preamble="load_debasher_module mymodule")
    prg.add(Process("mymodule.hello_world"))

    process = prg.to_model().processes[0]
    assert process.code == ""
    assert process.language == "bash"


# --- scripts (external aliases) ---------------------------------------------


def test_a_script_is_an_external_alias_copied_beside_the_module(tmp_path):
    source = tmp_path / "src"
    (source / "tools").mkdir(parents=True)
    _code(source / "tools", "tool.py", "print('hi')\n")
    tool = Process("tool", script="./tools/tool.py", base_dir=source)
    prg = Program("prg")
    prg.add(tool)
    home = tmp_path / "home"

    prg.write(home)

    process = persistence.load_program(str(home)).processes[0]
    assert process.additionalSpecs.externalAlias == "./tools/tool.py"
    assert process.language == "python"
    assert process.code == "print('hi')"
    assert (home / "tools" / "tool.py").read_text() == "print('hi')\n"
    assert "ext_alias=./tools/tool.py" in (home / "prg.sh").read_text()


def test_a_script_in_the_home_directory_is_not_copied_onto_itself(tmp_path):
    _code(tmp_path, "tool.sh", "echo hi\n")
    tool = Process("tool", script="tool.sh", base_dir=tmp_path)
    prg = Program("prg")
    prg.add(tool)

    prg.write(tmp_path)

    assert (tmp_path / "tool.sh").read_text() == "echo hi\n"


def test_a_script_outside_the_base_directory_is_copied_by_its_name(tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    _code(elsewhere, "tool.sh", "echo hi\n")
    base = tmp_path / "base"
    base.mkdir()
    tool = Process("tool", script="../elsewhere/tool.sh", base_dir=base)
    prg = Program("prg")
    prg.add(tool)
    home = tmp_path / "home"

    prg.write(home)

    assert persistence.load_program(str(home)).processes[0].additionalSpecs.externalAlias == "tool.sh"
    assert (home / "tool.sh").is_file()


def test_an_absolute_script_is_referred_to_as_it_is_and_not_copied(tmp_path):
    script = _code(tmp_path, "tool.sh", "echo hi\n")
    tool = Process("tool", script=script)
    prg = Program("prg")
    prg.add(tool)
    home = tmp_path / "home"

    prg.write(home)

    assert persistence.load_program(str(home)).processes[0].additionalSpecs.externalAlias == str(script)
    assert not (home / "tool.sh").exists()


# --- writing -----------------------------------------------------------------


def test_write_leaves_the_metadata_and_the_module_and_returns_the_module(tmp_path):
    prg = Program("prg")
    prg.add(_bash_process(tmp_path, "work", description="Works."))
    home = tmp_path / "home"

    script = prg.write(home)

    assert script == home / "prg.sh"
    assert (home / persistence.TOPOLOGY_FILENAME).is_file()
    assert 'debasher::document_process "Works."' in script.read_text()
    assert persistence.load_program(str(home)).digest


def test_writing_the_same_program_again_keeps_its_digest(tmp_path):
    prg = Program("prg")
    prg.add(_bash_process(tmp_path, "work"))
    home = tmp_path / "home"

    prg.write(home)
    digest = persistence.load_program(str(home)).digest
    prg.write(home)

    assert persistence.load_program(str(home)).digest == digest


def test_writing_a_changed_program_changes_its_digest(tmp_path):
    prg = Program("prg")
    work = prg.add(_bash_process(tmp_path, "work"))
    home = tmp_path / "home"
    prg.write(home)
    digest = persistence.load_program(str(home)).digest

    work.cmdline_opt("-n", "int", "how many")
    prg.write(home)

    assert persistence.load_program(str(home)).digest != digest


def test_what_script_generation_refuses_is_refused_with_its_message(tmp_path):
    work = _bash_process(tmp_path, "work")
    work.cmdline_opt("-n", "int", "how many")
    work["-n"].channel = "fifo"
    prg = Program("prg")
    prg.add(work)

    with pytest.raises(DefinitionError, match="can't be both command-line"):
        prg.write(tmp_path / "home")
    assert not (tmp_path / "home").exists()


# --- what the SDK refuses ------------------------------------------------------


@pytest.mark.parametrize("name", ["1st", "a-b", "a b", "a..b", "", "a_define_opts", "hello_py"])
def test_a_name_the_engine_would_refuse_is_refused(name):
    with pytest.raises(DefinitionError, match="cannot name a process"):
        Process(name)


@pytest.mark.parametrize("name", ["org.mymodule.hello", "_x1"])
def test_a_qualified_name_is_accepted(name):
    assert Process(name).name == name


@pytest.mark.parametrize("name", ["a.b", "1st", ""])
def test_a_program_name_has_no_dots(name):
    with pytest.raises(DefinitionError, match="cannot name a program"):
        Program(name)


def test_a_process_gives_its_code_in_one_way(tmp_path):
    with pytest.raises(DefinitionError, match="more than one way"):
        Process("work", code="work.sh", script="work.py")


def test_a_code_file_with_an_unknown_extension_needs_a_language():
    with pytest.raises(DefinitionError, match="tells no language"):
        Process("work", code="work.txt")
    assert Process("work", code="work.txt", language="bash").language == "bash"


def test_a_missing_code_file_is_reported_when_the_program_is_written(tmp_path):
    prg = Program("prg")
    prg.add(Process("work", code=tmp_path / "missing.sh"))

    with pytest.raises(DefinitionError, match="cannot read its code file"):
        prg.write(tmp_path / "home")


def test_an_option_is_declared_once(tmp_path):
    work = _bash_process(tmp_path, "work")
    work.cmdline_opt("-n", "int", "")

    with pytest.raises(DefinitionError, match='declares option "-n" twice'):
        work.cmdline_opt("-n", "int", "")


def test_a_label_starts_with_a_dash(tmp_path):
    with pytest.raises(DefinitionError, match='a label starts with "-"'):
        _bash_process(tmp_path, "work").cmdline_opt("n", "int", "")


def test_an_output_is_told_by_its_label(tmp_path):
    work = _bash_process(tmp_path, "work")
    with pytest.raises(DefinitionError, match='starts with "-out"'):
        work.output("-result", "file", "")
    with pytest.raises(DefinitionError, match="is an output for the engine"):
        work.input("-outf", "file", "")


def test_an_unknown_data_type_is_refused(tmp_path):
    with pytest.raises(DefinitionError, match='unknown data type "text"'):
        _bash_process(tmp_path, "work").cmdline_opt("-s", "text", "")


def test_an_input_has_a_value_or_a_source(tmp_path):
    writer = _bash_process(tmp_path, "writer")
    outf = writer.output("-outf", "file", "", in_outdir("f.txt"))
    with pytest.raises(DefinitionError, match="both a value and a source"):
        _bash_process(tmp_path, "reader").input("-inf", "file", "", value="x", source=outf)


def test_a_process_is_added_once(tmp_path):
    work = _bash_process(tmp_path, "work")
    prg = Program("prg")
    prg.add(work)

    with pytest.raises(DefinitionError, match="added twice"):
        prg.add(work)
    with pytest.raises(DefinitionError, match='already has a process named "work"'):
        prg.add(_bash_process(tmp_path, "work"))


def test_a_source_process_has_to_be_in_the_program(tmp_path):
    writer = _bash_process(tmp_path, "writer")
    outf = writer.output("-outf", "file", "", in_outdir("f.txt"))
    reader = _bash_process(tmp_path, "reader")
    reader.input("-inf", "file", "", source=outf)
    prg = Program("prg")
    prg.add(reader)

    with pytest.raises(DefinitionError, match='"writer", which program "prg" does not add'):
        prg.to_model()


def test_a_source_by_name_has_to_exist(tmp_path):
    writer = _bash_process(tmp_path, "writer")
    reader = _bash_process(tmp_path, "reader")
    reader.input("-inf", "file", "", source=("writer", "-outf"))
    prg = Program("prg")
    prg.add(writer)
    prg.add(reader)

    with pytest.raises(DefinitionError, match="has no such option"):
        prg.to_model()


def test_a_source_is_an_output(tmp_path):
    writer = _bash_process(tmp_path, "writer")
    n = writer.cmdline_opt("-n", "int", "")
    reader = _bash_process(tmp_path, "reader")
    reader.input("-inf", "file", "", source=n)
    prg = Program("prg")
    prg.add(writer)
    prg.add(reader)

    with pytest.raises(DefinitionError, match="which is an input"):
        prg.to_model()


def test_a_source_is_an_option_or_a_name_pair(tmp_path):
    with pytest.raises(DefinitionError, match="A source is the output option"):
        _bash_process(tmp_path, "reader").input("-inf", "file", "", source="writer")


def test_an_unknown_option_field_is_refused(tmp_path):
    with pytest.raises(DefinitionError, match="unknown field"):
        _bash_process(tmp_path, "work").opt("-x", "int", "", colour="red")
