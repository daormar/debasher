"""
What the SDK writes from a description, and what it refuses: the
processes and the program as the user gives them, each process with its
invariant part, its interface and its task options, the connections from
the sources of the task options, the ids from the names, the positions
from the layout of the editor, and the errors that name the process and
the option concerned.
"""

from pathlib import Path

import pytest

pytest.importorskip("pydantic")

from api import persistence  # noqa: E402
from debasher import (  # noqa: E402
    DefinitionError,
    Process,
    Program,
    connect,
    fifo,
    flag,
    in_outdir,
    opt,
    outdir,
    procspec,
    shared_dir,
    value_desc,
)

from examples import SDK_PROGRAMS_DIR  # noqa: E402

_HELLO_WORLD = SDK_PROGRAMS_DIR / "sdk_hello_world_py" / "hello_world.py"


def _code(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text)
    return path


def _bash_process(tmp_path: Path, name: str, description: str = "", options=()) -> Process:
    return Process(
        name, code=_code(tmp_path, f"{name}.sh", f"{name}()\n{{\n    :\n}}\n"), description=description, options=options
    )


def _writer_and_reader(tmp_path: Path, source=None, display="line"):
    """A process that writes a file and another that reads it, connected
    by `source` (the option of the writer when None)."""
    writer = _bash_process(tmp_path, "writer", options=[opt("-outf", "file", "what it writes")])
    writer.task_options(values={"-outf": in_outdir("f.txt")})
    reader = _bash_process(tmp_path, "reader", options=[opt("-inf", "file", "what it reads")])
    reader.task_options(values={"-inf": connect(source if source is not None else writer["-outf"], display=display)})
    return writer, reader


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


def test_the_options_keep_their_order_and_take_their_fields_from_the_interface_and_the_task_options(tmp_path):
    work = _bash_process(
        tmp_path,
        "work",
        options=[
            opt("-outf", "file", "the result"),
            opt("-n", "int", "how many"),
            opt("-label", "string", "a label"),
            flag("-verbose", "say more"),
            opt("-inf", "file", "a fixed input"),
            flag("-fast", "always fast"),
        ],
    )
    work.interface(cmdline={"-n": "mandatory", "-label": "optional", "-verbose": "optional"})
    work.task_options(values={"-outf": in_outdir("result.txt"), "-inf": "data/input.txt", "-fast": True})
    prg = Program("prg")
    prg.add(work)

    options = prg.to_model().processes[0].options
    assert [option.label for option in options] == ["-outf", "-n", "-label", "-verbose", "-inf", "-fast"]
    outf, n, label, verbose, inf, fast = options
    assert (outf.direction, outf.dataType, outf.value) == ("output", "file", "${process_outdir}/result.txt")
    assert (n.direction, n.commandLine, n.mandatory) == ("input", True, True)
    assert (label.commandLine, label.mandatory) == (True, False)
    assert (verbose.dataType, verbose.commandLine, verbose.mandatory) == ("None", True, False)
    assert (inf.commandLine, inf.value) == (False, "data/input.txt")
    assert (fast.dataType, fast.commandLine) == ("None", False)


def test_each_kind_of_value_gives_its_channel(tmp_path):
    work = _bash_process(
        tmp_path,
        "work",
        options=[
            opt("-outd", "dir", "the task directory"),
            opt("-shared", "dir", "a shared directory"),
            opt("-cpus", "int", "the cpus of the process"),
            opt("-outv", "int", "a value"),
            opt("-outf", "file", "a stream"),
            opt("-inf", "file", "a stream it opens"),
        ],
    )
    work.task_options(
        values={
            "-outd": outdir(subpath="${task_idx}"),
            "-shared": shared_dir("data", subpath="sub"),
            "-cpus": procspec("cpus"),
            "-outv": value_desc(),
            "-outf": fifo("out_fifo", mirror=True),
            "-inf": fifo("in_fifo"),
        }
    )
    prg = Program("prg", shared_dirs=["data"])
    prg.add(work)

    outd, shared, cpus, outv, outf, inf = prg.to_model().processes[0].options
    assert (outd.channel, outd.subpath) == ("process_outdir", "${task_idx}")
    assert (shared.channel, shared.value, shared.subpath) == ("shared_dir", "data", "sub")
    assert (cpus.fromProcessSpec, cpus.value) == (True, "cpus")
    assert outv.channel == "value_desc"
    assert (outf.channel, outf.value, outf.mirror) == ("fifo", "out_fifo", True)
    assert (inf.channel, inf.value, inf.mirror) == ("fifo", "in_fifo", False)


def test_a_connection_comes_from_the_source_of_an_input(tmp_path):
    writer, reader = _writer_and_reader(tmp_path)
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
    writer, reader = _writer_and_reader(tmp_path, source=("writer", "-outf"), display="label")
    prg = Program("prg")
    prg.add(writer)
    prg.add(reader)

    (edge,) = prg.to_model().edges
    assert edge.sourceProcessId == prg.to_model().processes[0].id
    assert edge.display == "label"


def test_a_fan_in_gives_one_connection_per_source(tmp_path):
    a = _bash_process(tmp_path, "a", options=[opt("-outf", "file")])
    a.task_options(values={"-outf": in_outdir("a.txt")})
    b = _bash_process(tmp_path, "b", options=[opt("-outf", "file")])
    b.task_options(values={"-outf": in_outdir("b.txt")})
    gather = _bash_process(tmp_path, "gather", options=[opt("-inf", "file")])
    gather.task_options(values={"-inf": connect([a["-outf"], ("b", "-outf")])})
    prg = Program("prg")
    for process in (a, b, gather):
        prg.add(process)

    edges = prg.to_model().edges
    assert len(edges) == 2
    assert {edge.sourceProcessId for edge in edges} == {p.id for p in prg.to_model().processes[:2]}


def test_the_ids_come_from_the_names_so_that_two_builds_agree(tmp_path):
    def build():
        writer, reader = _writer_and_reader(tmp_path)
        prg = Program("prg")
        prg.add(writer)
        prg.add(reader)
        return prg.to_model()

    assert build().model_dump() == build().model_dump()


def test_processes_are_laid_out_as_the_editor_lays_out_an_imported_program(tmp_path):
    writer, reader = _writer_and_reader(tmp_path)
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


def test_an_alias_and_its_option_map_go_into_the_additional_specifications(tmp_path):
    work = Process("work", alias="mymodule.base", alias_opt_map={"-x": "-y"}, options=[opt("-x", "int")])
    work.interface(cmdline={"-x": "mandatory"})
    prg = Program("prg", preamble="load_debasher_module mymodule")
    prg.add(work)

    specs = prg.to_model().processes[0].additionalSpecs
    assert specs.alias == "mymodule.base"
    assert [(m.fromLabel, m.toLabel) for m in specs.aliasOptMap] == [("-x", "-y")]


# --- the variable part ---------------------------------------------------------


def test_the_interface_is_replaced_whole_when_given_again(tmp_path):
    work = _bash_process(tmp_path, "work", options=[opt("-n", "int"), opt("-m", "int")])
    work.interface(cmdline={"-n": "mandatory", "-m": "mandatory"})
    work.interface(cmdline={"-n": "optional"})
    work.task_options(values={"-m": "3"})
    prg = Program("prg")
    prg.add(work)

    n, m = prg.to_model().processes[0].options
    assert (n.commandLine, n.mandatory) == (True, False)
    assert (m.commandLine, m.value) == (False, "3")


def test_the_task_options_are_replaced_whole_when_given_again(tmp_path):
    _code(tmp_path, "tasks.sh", "array=(a b)\n")
    work = _bash_process(tmp_path, "work", options=[opt("-outf", "file")])
    work.interface(shaping={"-w": ("int", "Number of workers.")})
    work.task_options(array=tmp_path / "tasks.sh", values={"-outf": in_outdir("a.txt")})
    work.interface()
    work.task_options(values={"-outf": in_outdir("b.txt")})
    prg = Program("prg")
    prg.add(work)

    process = prg.to_model().processes[0]
    assert process.optionsHandler.mode == "standard"
    assert [(o.label, o.value) for o in process.options] == [("-outf", "${process_outdir}/b.txt")]


def test_a_task_shaping_option_follows_the_received_options(tmp_path):
    _code(tmp_path, "tasks.py", "def tasks(run):\n    return range(int(run.value('-w')))\n")
    work = _bash_process(tmp_path, "work", options=[opt("-outd", "dir")])
    work.interface(shaping={"-w": ("int", "Number of workers.")})
    work.task_options(array=tmp_path / "tasks.py", values={"-outd": outdir(subpath="${task_idx}")})
    prg = Program("prg")
    prg.add(work)

    process = prg.to_model().processes[0]
    assert (process.optionsHandler.mode, process.optionsHandler.language) == ("array", "python")
    assert [o.label for o in process.options] == ["-outd", "-w"]
    w = process.options[1]
    assert (w.commandLine, w.mandatory, w.taskShaping, w.description) == (True, True, True, "Number of workers.")


def test_a_library_process_is_given_its_variable_part_by_the_program_that_adds_it(tmp_path):
    work = _bash_process(tmp_path, "work", options=[opt("-n", "int")])
    prg = Program("prg")
    prg.add(work)
    with pytest.raises(DefinitionError, match="-n are neither on the command line"):
        prg.to_model()

    work.interface(cmdline={"-n": "mandatory"})
    assert prg.to_model().processes[0].options[0].commandLine is True


# --- writing -----------------------------------------------------------------


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


def test_a_script_takes_an_alias_option_map(tmp_path):
    _code(tmp_path, "tool.sh", "echo hi\n")
    tool = Process("tool", script="tool.sh", base_dir=tmp_path, alias_opt_map={"-a": "-b"}, options=[opt("-a", "int")])
    tool.interface(cmdline={"-a": "mandatory"})
    prg = Program("prg")
    prg.add(tool)

    specs = prg.to_model().processes[0].additionalSpecs
    assert specs.externalAlias == "tool.sh"
    assert [(m.fromLabel, m.toLabel) for m in specs.aliasOptMap] == [("-a", "-b")]


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


def test_write_leaves_the_artifact_and_the_module_and_returns_the_module(tmp_path):
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
    work = prg.add(_bash_process(tmp_path, "work", options=[opt("-n", "int", "how many")]))
    work.task_options(values={"-n": "3"})
    home = tmp_path / "home"
    prg.write(home)
    digest = persistence.load_program(str(home)).digest

    work.task_options(values={"-n": "4"})
    prg.write(home)

    assert persistence.load_program(str(home)).digest != digest


def test_what_script_generation_refuses_is_refused_with_its_message(tmp_path):
    # A family whose two ends are processes with one task each: nothing
    # counts it
    writer = _bash_process(tmp_path, "writer", options=[opt("-outf-ith", "file")])
    writer.task_options(values={"-outf-ith": in_outdir("f${i}.txt")})
    reader = _bash_process(tmp_path, "reader", options=[opt("-inf", "file")])
    reader.task_options(values={"-inf": connect(writer["-outf-ith"])})
    prg = Program("prg")
    prg.add(writer)
    prg.add(reader)

    with pytest.raises(DefinitionError, match="no tasks to count"):
        prg.write(tmp_path / "home")
    assert not (tmp_path / "home").exists()


# --- what the SDK refuses ------------------------------------------------------


# The rule is that of the API, which the editor checks too; each case
# of the rule is tested in test/api/test_process_names.py
@pytest.mark.parametrize(
    "name", ["1st", "a-b", "a b", "a..b", "", "a_define_opts", "a_slurm_sigterm_handler", "a_outdir_basename", "hello_py", "a__NSSEP__b"]
)
def test_a_name_the_engine_would_refuse_is_refused_with_the_reason_of_the_api(name):
    from api.process_names import process_name_problem

    with pytest.raises(DefinitionError) as refusal:
        Process(name)
    assert str(refusal.value) == f'"{name}" cannot name a process: {process_name_problem(name)}'


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


def test_an_alias_option_map_goes_with_a_script_or_an_alias(tmp_path):
    with pytest.raises(DefinitionError, match="alias_opt_map without a script or an alias"):
        Process("work", code="work.sh", alias_opt_map={"-a": "-b"})


def test_a_code_file_whose_extension_tells_no_language_is_refused():
    with pytest.raises(DefinitionError, match="tells no language"):
        Process("work", code="work.txt")


def test_a_missing_code_file_is_reported_when_the_program_is_written(tmp_path):
    prg = Program("prg")
    prg.add(Process("work", code=tmp_path / "missing.sh"))

    with pytest.raises(DefinitionError, match="cannot read its code file"):
        prg.write(tmp_path / "home")


def test_the_invariant_part_is_not_changed_once_the_process_is_created(tmp_path):
    work = _bash_process(tmp_path, "work", options=[opt("-n", "int")])
    with pytest.raises(DefinitionError, match="invariant part"):
        work.options = ()
    with pytest.raises(DefinitionError, match="invariant part"):
        work.code_path = tmp_path / "other.sh"


def test_an_option_is_listed_once(tmp_path):
    with pytest.raises(DefinitionError, match='lists option "-n" twice'):
        _bash_process(tmp_path, "work", options=[opt("-n", "int"), opt("-n", "int")])


def test_a_label_starts_with_a_dash(tmp_path):
    with pytest.raises(DefinitionError, match='a label starts with "-"'):
        _bash_process(tmp_path, "work", options=[opt("n", "int")])


def test_an_unknown_data_type_is_refused(tmp_path):
    with pytest.raises(DefinitionError, match='unknown data type "text"'):
        _bash_process(tmp_path, "work", options=[opt("-s", "text")])


def test_the_options_are_given_with_opt_and_flag(tmp_path):
    with pytest.raises(DefinitionError, match=r"given with opt\(...\) and flag\(...\)"):
        _bash_process(tmp_path, "work", options=["-n"])


def test_the_interface_and_the_task_options_name_received_options(tmp_path):
    work = _bash_process(tmp_path, "work", options=[opt("-n", "int")])
    with pytest.raises(DefinitionError, match='names "-m", which is not an option that the process receives'):
        work.interface(cmdline={"-m": "mandatory"})
    with pytest.raises(DefinitionError, match='names "-m", which is not an option that the process receives'):
        work.task_options(values={"-m": "3"})


def test_a_command_line_option_is_mandatory_or_optional_and_a_flag_optional(tmp_path):
    work = _bash_process(tmp_path, "work", options=[opt("-n", "int"), flag("-v")])
    with pytest.raises(DefinitionError, match='"mandatory" or "optional", not "yes"'):
        work.interface(cmdline={"-n": "yes"})
    with pytest.raises(DefinitionError, match='a flag is "optional"'):
        work.interface(cmdline={"-v": "mandatory"})


def test_a_task_shaping_option_is_received_by_no_task(tmp_path):
    work = _bash_process(tmp_path, "work", options=[opt("-w", "int")])
    with pytest.raises(DefinitionError, match="a task shaping option is received by none"):
        work.interface(shaping={"-w": ("int", "Number of workers.")})


def test_an_external_fifo_is_an_input(tmp_path):
    work = _bash_process(tmp_path, "work", options=[opt("-outf", "string")])
    with pytest.raises(DefinitionError, match="an external FIFO is an input"):
        work.interface(external={"-outf": "out"})


def test_a_kind_of_value_fits_the_direction_of_the_option(tmp_path):
    writer, _ = _writer_and_reader(tmp_path)
    work = _bash_process(tmp_path, "work", options=[opt("-outf", "file"), opt("-inf", "file")])
    with pytest.raises(DefinitionError, match="is an output, and a connection is an input"):
        work.task_options(values={"-outf": connect(writer["-outf"])})
    with pytest.raises(DefinitionError, match="is an input, and a value descriptor is an output"):
        work.task_options(values={"-inf": value_desc()})


def test_true_is_for_a_flag_and_a_flag_takes_nothing_else(tmp_path):
    work = _bash_process(tmp_path, "work", options=[opt("-n", "int"), flag("-v")])
    with pytest.raises(DefinitionError, match="only a flag is set with True"):
        work.task_options(values={"-n": True})
    with pytest.raises(DefinitionError, match="is a flag, which is set in every task with True"):
        work.task_options(values={"-v": "yes"})


def test_a_count_is_for_a_family_and_names_a_command_line_option(tmp_path):
    work = _bash_process(tmp_path, "work", options=[opt("-outf", "file"), opt("-outf-ith", "file"), opt("-w", "int")])
    with pytest.raises(DefinitionError, match="which only a fanout family"):
        work.task_options(values={"-outf": "x"}, count={"-outf": "-w"})
    work.task_options(values={"-outf": "x", "-outf-ith": "y${i}", "-w": "3"}, count={"-outf-ith": "-w"})
    prg = Program("prg")
    prg.add(work)
    with pytest.raises(DefinitionError, match='counted by "-w", which is not a command line option'):
        prg.to_model()


def test_an_option_from_outside_has_no_value_in_the_task_options(tmp_path):
    work = _bash_process(tmp_path, "work", options=[opt("-n", "int")])
    work.interface(cmdline={"-n": "mandatory"})
    work.task_options(values={"-n": "3"})
    prg = Program("prg")
    prg.add(work)

    with pytest.raises(DefinitionError, match="is on the command line and has a value in its task options too"):
        prg.to_model()


def test_task_shaping_options_need_an_array_or_a_generator(tmp_path):
    work = _bash_process(tmp_path, "work")
    work.interface(shaping={"-w": ("int", "Number of workers.")})
    prg = Program("prg")
    prg.add(work)

    with pytest.raises(DefinitionError, match="only the tasks file of an array or a generator reads them"):
        prg.to_model()


def test_an_array_and_a_generator_are_not_both_given(tmp_path):
    with pytest.raises(DefinitionError, match="both array= and generator="):
        _bash_process(tmp_path, "work").task_options(array="a.sh", generator="g.sh")


def test_a_process_is_added_once(tmp_path):
    work = _bash_process(tmp_path, "work")
    prg = Program("prg")
    prg.add(work)

    with pytest.raises(DefinitionError, match="added twice"):
        prg.add(work)
    with pytest.raises(DefinitionError, match='already has a process named "work"'):
        prg.add(_bash_process(tmp_path, "work"))


def test_a_source_process_has_to_be_in_the_program(tmp_path):
    _, reader = _writer_and_reader(tmp_path)
    prg = Program("prg")
    prg.add(reader)

    with pytest.raises(DefinitionError, match='"writer", which program "prg" does not add'):
        prg.to_model()


def test_a_source_by_name_has_to_exist(tmp_path):
    writer, reader = _writer_and_reader(tmp_path, source=("writer", "-outx"))
    prg = Program("prg")
    prg.add(writer)
    prg.add(reader)

    with pytest.raises(DefinitionError, match="has no such option"):
        prg.to_model()


def test_a_source_is_an_output(tmp_path):
    writer = _bash_process(tmp_path, "writer", options=[opt("-n", "int")])
    writer.interface(cmdline={"-n": "mandatory"})
    _, reader = _writer_and_reader(tmp_path, source=writer["-n"])
    prg = Program("prg")
    prg.add(writer)
    prg.add(reader)

    with pytest.raises(DefinitionError, match="which is an input"):
        prg.to_model()


def test_a_source_is_an_option_or_a_name_pair():
    with pytest.raises(DefinitionError, match="A source is the output option"):
        connect("writer")


def test_an_unknown_label_is_refused_where_the_option_is_named(tmp_path):
    work = _bash_process(tmp_path, "work", options=[opt("-outf", "file")])
    with pytest.raises(DefinitionError, match='names "-outx", which is not an option that the process receives'):
        work["-outx"]


def test_the_containers_of_the_invariant_part_cannot_be_changed_in_place(tmp_path):
    work = Process("work", code=_code(tmp_path, "work.sh", "work()\n{\n    :\n}\n"),
                   conda_envs={"py27": "py27.yml"}, docker_imgs=["ubuntu"])
    with pytest.raises(TypeError):
        work.conda_envs["other"] = "other.yml"
    with pytest.raises(AttributeError):
        work.docker_imgs.append("debian")


def test_a_script_whose_extension_tells_no_language_is_refused():
    with pytest.raises(DefinitionError, match="tells no language"):
        Process("tool", script="tool.txt")


@pytest.mark.parametrize(
    "arguments, message",
    [
        ({"cmdline": {"-outf": "mandatory"}}, "is an output, which the command line does not give"),
        ({"cmdline": {"-n": "mandatory"}, "external": {"-n": "n"}}, "both on the command line and fed from outside"),
        ({"external": {"-n": ""}}, "an external FIFO is given the name of its FIFO"),
        ({"shaping": {"-w": "int"}}, "given as its data type and its description"),
        ({"shaping": {"-w": ("None", "x")}}, 'unknown data type "None"'),
        ({"shaping": {"-outw": ("int", "x")}}, "a task shaping option is an input"),
        ({"shaping": {"w": ("int", "x")}}, 'a label starts with "-"'),
    ],
)
def test_what_the_interface_refuses(tmp_path, arguments, message):
    work = _bash_process(tmp_path, "work", options=[opt("-n", "int"), opt("-outf", "file")])
    with pytest.raises(DefinitionError, match=message):
        work.interface(**arguments)


@pytest.mark.parametrize(
    "arguments, message",
    [
        ({"values": {"-n": 3}}, "a value is a string, True for a flag, or one of"),
        ({"values": {"-n": fifo("x", mirror=True)}}, "only an output FIFO is mirrored"),
        ({"values": {"-outf-ith": "x"}, "count": {"-outf-ith": 3}}, "a count is the label of a command line option"),
    ],
)
def test_what_the_task_options_refuse(tmp_path, arguments, message):
    work = _bash_process(tmp_path, "work", options=[opt("-n", "int"), opt("-outf-ith", "file")])
    with pytest.raises(DefinitionError, match=message):
        work.task_options(**arguments)


def test_building_runs_none_of_the_code_of_the_processes(tmp_path):
    marker = tmp_path / "ran"
    write_marker = f"open({str(marker)!r}, 'w').close()\n"
    work = Process("work", code=_code(tmp_path, "work.py", write_marker),
                   skip=_code(tmp_path, "work_skip.py", write_marker + "def skip(task):\n    return False\n"),
                   options=[opt("-outd", "dir")])
    work.task_options(array=_code(tmp_path, "work_tasks.py", write_marker + "def tasks(run):\n    return [1]\n"),
                      values={"-outd": outdir(subpath="${task_idx}")})
    prg = Program("prg")
    prg.add(work)

    prg.write(tmp_path / "home")

    assert not marker.exists()


def test_a_refused_program_leaves_the_home_directory_as_it_was(tmp_path):
    home = tmp_path / "home"
    good = Program("prg")
    good.add(_bash_process(tmp_path, "work"))
    good.write(home)
    before = {path.relative_to(home): path.read_bytes() for path in home.rglob("*") if path.is_file()}

    writer = _bash_process(tmp_path, "writer", options=[opt("-outf-ith", "file")])
    writer.task_options(values={"-outf-ith": in_outdir("f${i}.txt")})
    reader = _bash_process(tmp_path, "reader", options=[opt("-inf", "file")])
    reader.task_options(values={"-inf": connect(writer["-outf-ith"])})
    bad = Program("prg")
    bad.add(writer)
    bad.add(reader)
    with pytest.raises(DefinitionError):
        bad.write(home)

    assert {path.relative_to(home): path.read_bytes() for path in home.rglob("*") if path.is_file()} == before


def test_a_process_named_as_a_method_of_the_module_is_refused_when_the_program_is_written(tmp_path):
    prg = Program("prg")
    prg.add(_bash_process(tmp_path, "prg_program"))

    with pytest.raises(DefinitionError, match='is named as the method "_program" of the module of program "prg"'):
        prg.write(tmp_path / "home")
    assert not (tmp_path / "home").exists()
