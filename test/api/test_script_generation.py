import pytest

from api.models import (
    AdditionalSpecs,
    ComputationalSpecs,
    OptionsHandler,
    Position,
    ProcessFiles,
    ProgramOption,
    ProgramProcess,
)
from api.script_generation import _option_definition_line


def _make_process(options):
    return ProgramProcess(
        id="p1",
        name="count",
        description="",
        position=Position(x=0, y=0),
        options=options,
        optionsHandler=OptionsHandler(mode="standard"),
        language="bash",
        code="",
        computationalSpecs=ComputationalSpecs(),
        additionalSpecs=AdditionalSpecs(force=False),
    )


def _make_file_option(direction, label="-outf", value="${process_outdir}/counts.txt"):
    return ProgramOption(
        id="o1",
        label=label,
        direction=direction,
        dataType="file",
        description="",
        value=value,
        commandLine=False,
    )


def test_output_file_option_uses_plain_define_opt():
    # An output-direction "file" option (e.g. "-outf" for a process's
    # own not-yet-created result file) must not go through
    # define_infile_opt: that validates the value against an existing
    # file on disk, which a file the process itself will create at run
    # time never is (see debasher::define_infile_opt in
    # engine/debasher_lib_opts.sh) -- this is the bug
    # debasher::_check_opt_names_vs_explain's sweep surfaced (via
    # data/programs/debasher_dynamic_fanout_fifos.sh's "count" process
    # aborting with "file ... does not exist").
    option = _make_file_option("output")
    process = _make_process([option])

    lines = _option_definition_line(process, option, {}, {})

    assert len(lines) == 1
    assert "debasher::define_opt " in lines[0]
    assert "define_infile_opt" not in lines[0]


def test_input_file_option_still_uses_define_infile_opt():
    option = _make_file_option("input", label="-inf")
    process = _make_process([option])

    lines = _option_definition_line(process, option, {}, {})

    assert len(lines) == 1
    assert "debasher::define_infile_opt " in lines[0]


def test_a_dir_option_uses_the_directory_variants():
    # A "dir" input is checked to name an existing directory, which the
    # "file" variants would refuse, given as a value or on the command
    # line, and an optional one only when it is given.
    literal = _make_file_option("input", label="-ref", value="refdir").model_copy(update={"dataType": "dir"})
    mandatory = literal.model_copy(update={"label": "-ind", "commandLine": True, "mandatory": True})
    optional = mandatory.model_copy(update={"label": "-opt", "mandatory": False})
    process = _make_process([literal, mandatory, optional])

    assert _option_definition_line(process, literal, {}, {}) == [
        'debasher::define_indir_opt "-ref" "refdir" optlist "count" || return 1'
    ]
    assert _option_definition_line(process, mandatory, {}, {}) == [
        'debasher::define_cmdline_indir_opt "${cmdline}" "-ind" optlist || return 1'
    ]
    assert _option_definition_line(process, optional, {}, {}) == [
        'debasher::define_cmdline_indir_opt_if_given "${cmdline}" "-opt" optlist || return 1'
    ]


def test_an_output_dir_option_uses_plain_define_opt():
    option = _make_file_option("output", label="-outd", value="${process_outdir}/d").model_copy(update={"dataType": "dir"})
    process = _make_process([option])

    assert _option_definition_line(process, option, {}, {}) == [
        'debasher::define_opt "-outd" "${process_outdir}/d" optlist || return 1'
    ]


def test_the_edges_alone_say_what_is_connected():
    # The value of an input is not looked at to tell whether it is
    # connected: an edge into it connects it, even with no connection
    # sentinel in its value, and a value that looks like one, with no
    # edge, is a literal value.
    option = _make_file_option("input", label="-inf", value="")
    process = _make_process([option])
    connections = {("p1", "o1"): [("producer", "-outf", "standard")]}

    connected = _option_definition_line(process, option, {}, connections)
    stale = _option_definition_line(
        process, option.model_copy(update={"value": "[producer;-outf]", "dataType": "string"}), {}, {}
    )

    assert connected == ['debasher::define_opt_from_proc_out "-inf" "producer" "-outf" optlist || return 1']
    assert stale == ['debasher::define_opt "-inf" "[producer;-outf]" optlist || return 1']


def test_command_line_option_with_an_option_channel_is_refused():
    # A command-line option takes its value from the command line only
    # (the engine refuses one defined otherwise), so a model option that
    # is both command-line and a fifo would produce a module the engine
    # rejects: script generation refuses it instead.
    option = ProgramOption(
        id="o1",
        label="-threshold",
        direction="input",
        dataType="int",
        channel="fifo",
        description="",
        value="threshold_fifo",
        commandLine=True,
        mandatory=True,
    )
    process = _make_process([option])

    with pytest.raises(ValueError, match="command-line and delivered through channel"):
        _option_definition_line(process, option, {}, {})


# --- Task shaping options -------------------------------------------------

from api.script_generation import (  # noqa: E402
    _add_explain_opts_func,
    _add_explain_task_shaping_opts_func,
    _add_identify_cmdline_opts_func,
)


def _shaping_option(**fields):
    defaults = dict(
        id="ow",
        label="-w",
        direction="input",
        dataType="int",
        description="Number of workers.",
        value="",
        commandLine=True,
        mandatory=True,
        taskShaping=True,
    )
    return ProgramOption(**(defaults | fields))


def test_a_task_shaping_option_is_declared_apart_and_never_defined():
    shaping = _shaping_option()
    task_option = _make_file_option("input", label="-inf")
    process = _make_process([shaping, task_option])

    assert _add_explain_task_shaping_opts_func(process) == [
        "count_explain_task_shaping_opts()",
        "{",
        '    debasher::explain_task_shaping_opt "-w" "<int>" "Number of workers."',
        "}",
    ]
    assert not any("-w" in line for line in _add_explain_opts_func(process))
    assert not any("-w" in line for line in _add_identify_cmdline_opts_func(process))
    assert _option_definition_line(process, shaping, {}, {}) == []


def test_a_process_without_task_shaping_options_gets_no_method_for_them():
    process = _make_process([_make_file_option("input", label="-inf")])

    assert _add_explain_task_shaping_opts_func(process) == []


def test_explain_opts_of_a_process_with_only_task_shaping_options_is_empty():
    process = _make_process([_shaping_option()])

    assert _add_explain_opts_func(process) == ["count_explain_opts()", "{", "    :", "}"]
    assert _add_identify_cmdline_opts_func(process) == ["count_identify_cmdline_opts()", "{", "    :", "}"]


@pytest.mark.parametrize(
    "fields, message",
    [
        (dict(mandatory=False), "must be a mandatory command-line option"),
        (dict(commandLine=False, mandatory=False), "must be a mandatory command-line option"),
        (dict(dataType="None"), "can't be a flag"),
        (dict(label="-outw", direction="output"), "can't be an output"),
        (dict(fromProcessSpec=True), "from the command line only"),
        (dict(label="-w-ith"), "can't be a fanout family"),
    ],
)
def test_a_task_shaping_option_that_the_engine_would_not_take_is_refused(fields, message):
    process = _make_process([_shaping_option(**fields)])

    with pytest.raises(ValueError, match=message):
        _add_explain_task_shaping_opts_func(process)


def test_a_task_shaping_option_cannot_count_a_fanout_family():
    from api.script_generation import _fanout_count_source_option

    count = _shaping_option()
    family = ProgramOption(
        id="of",
        label="-outf-ith",
        direction="output",
        dataType="file",
        description="",
        value="${process_outdir}/part_${i}",
        commandLine=False,
        countSourceOptionId="ow",
    )
    process = _make_process([count, family])

    with pytest.raises(ValueError, match="a task shaping option, which no task receives"):
        _fanout_count_source_option(process, family)


# --- Sequential processes ------------------------------------------------

from api.models import (  # noqa: E402
    ExecutionOptions,
    GroupSource,
    Program,
    SeqAdditionalSpecs,
    SeqComputationalSpecs,
    SeqProcess,
)
from api.script_generation import _stub_processes_missing_code, generate_script  # noqa: E402


def _seq_program(seq_processes, processes=(), **fields):
    defaults = dict(
        id="prog",
        name="prog",
        preamble="",
        envVars={},
        outputDir="",
        executionOptions=ExecutionOptions(scheduler="BUILTIN"),
        programOptions={},
        processes=list(processes),
        seqProcesses=list(seq_processes),
        edges=[],
    )
    return Program(**(defaults | fields))


def test_a_sequential_process_is_written_after_the_processes_and_added_with_its_specs():
    step = SeqProcess(
        id="s",
        name="step",
        description="Adds two.",
        language="python",
        code="print(2)",
        computationalSpecs=SeqComputationalSpecs(cpus=1, mem=32, time="00:01:00"),
    )
    script = generate_script(_seq_program([step], [_make_process([])]), skip_redundant_check=True)

    assert script.index("count_document()") < script.index("step_document()")
    assert 'debasher::document_process "Adds two."' in script
    # A sequential process in Python is run from its process file, as a
    # process is (see with_code_files_referenced)
    assert "step_heredoc_py()" not in script
    assert script.index('add_debasher_process "count"') < script.index(
        'add_debasher_seq_process "step" "cpus=1 mem=32 time=00:01:00" "ext_alias=step.py"'
    )


def test_a_sequential_process_with_an_alias_gets_no_code():
    alias = SeqProcess(
        id="a",
        name="aliased",
        code="aliased()\n{\n    :\n}",
        additionalSpecs=SeqAdditionalSpecs(alias="target"),
    )
    script = generate_script(_seq_program([alias]), skip_redundant_check=True)

    assert "aliased()" not in script
    assert 'add_debasher_seq_process "aliased" "" "alias=target"' in script


def test_the_scheduler_of_the_steps_of_a_sequential_process_is_written_in_sched():
    step = SeqProcess(
        id="s",
        name="heavy",
        code="heavy()\n{\n    :\n}",
        computationalSpecs=SeqComputationalSpecs(cpus=4),
        additionalSpecs=SeqAdditionalSpecs(sched="SLURM"),
    )
    script = generate_script(_seq_program([step]), skip_redundant_check=True)

    assert 'add_debasher_seq_process "heavy" "cpus=4" "sched=SLURM"' in script


def test_a_name_shared_by_a_process_and_a_sequential_process_is_refused():
    clash = SeqProcess(id="c", name="count", code="count()\n{\n    :\n}")
    with pytest.raises(ValueError, match="has the name of a process"):
        generate_script(_seq_program([clash], [_make_process([])]), skip_redundant_check=True)


def test_two_sequential_processes_with_one_name_are_refused():
    first = SeqProcess(id="a", name="step")
    second = SeqProcess(id="b", name="step")
    with pytest.raises(ValueError, match="Two sequential processes"):
        generate_script(_seq_program([first, second]), skip_redundant_check=True)


def test_a_resident_program_with_a_sequential_process_is_refused():
    step = SeqProcess(id="s", name="step")
    with pytest.raises(ValueError, match="resident program"):
        generate_script(_seq_program([step], programType="resident"), skip_redundant_check=True)


def test_an_intact_group_adds_its_sequential_processes_with_its_add_debasher_program():
    group = GroupSource(programName="other", groupId="g", groupSize=2, sourceDir="/other")
    process = _make_process([]).model_copy(update={"groupSource": group})
    step = SeqProcess(id="s", name="step", code="step()\n{\n    :\n}", groupSource=group)
    script = generate_script(_seq_program([step], [process]), skip_redundant_check=True)

    assert script.count('add_debasher_program "other"') == 1
    assert "add_debasher_seq_process" not in script
    assert 'add_debasher_process "count"' not in script


def test_a_group_missing_its_sequential_process_is_generated_member_by_member():
    group = GroupSource(programName="other", groupId="g", groupSize=2, sourceDir="/other")
    process = _make_process([]).model_copy(update={"groupSource": group})
    script = generate_script(_seq_program([], [process]), skip_redundant_check=True)

    assert "add_debasher_program" not in script
    assert 'add_debasher_process "count"' in script


def test_a_sequential_process_without_code_gets_a_stub_for_reading_environment_variables():
    step = SeqProcess(id="s", name="step")
    stubbed = _stub_processes_missing_code(_seq_program([step]))

    assert stubbed.seqProcesses[0].code == "step()\n{\n    :\n}"


# --- The code of an alias target -------------------------------------------

_INCREMENT = "increment()\n{\n    echo $(( $1 + 1 ))\n}"


def test_the_code_of_a_plain_function_that_aliases_run_is_written_once():
    first = SeqProcess(id="a", name="add_one", code=_INCREMENT, additionalSpecs=SeqAdditionalSpecs(alias="increment"))
    second = SeqProcess(id="b", name="plus_one", code=_INCREMENT, additionalSpecs=SeqAdditionalSpecs(alias="increment"))
    script = generate_script(_seq_program([first, second]), skip_redundant_check=True)

    assert script.count("increment()") == 1
    assert script.index("increment()") < script.index("prog_program()")


def test_the_code_of_an_alias_is_not_written_when_the_target_is_a_process_of_the_program():
    target = _make_process([]).model_copy(update={"code": "count()\n{\n    :\n}"})
    alias = SeqProcess(id="a", name="alias", code="count()\n{\n    :\n}", additionalSpecs=SeqAdditionalSpecs(alias="count"))
    script = generate_script(_seq_program([alias], [target]), skip_redundant_check=True)

    assert script.count("count()") == 1


def test_the_code_of_an_alias_is_not_written_when_it_does_not_define_the_target():
    # As an alias created in the web UI, whose code is its own template
    alias = SeqProcess(
        id="a", name="add_one", code="add_one()\n{\n    :\n}", additionalSpecs=SeqAdditionalSpecs(alias="increment")
    )
    script = generate_script(_seq_program([alias]), skip_redundant_check=True)

    assert "add_one()" not in script
    assert "increment()" not in script


def test_the_code_of_an_external_alias_is_never_written():
    alias = SeqProcess(
        id="a", name="ext", code=_INCREMENT, additionalSpecs=SeqAdditionalSpecs(externalAlias="increment.sh")
    )
    script = generate_script(_seq_program([alias]), skip_redundant_check=True)

    assert "increment()" not in script


def _make_dir_option(direction, label, channel, value="", subpath=""):
    return ProgramOption(
        id="o1",
        label=label,
        direction=direction,
        dataType="string",
        description="",
        value=value,
        commandLine=False,
        channel=channel,
        subpath=subpath,
    )


def test_a_shared_directory_and_a_process_output_directory_are_written_with_their_subpath():
    shared = _make_dir_option("output", "-outd", "shared_dir", value="data", subpath="${task_idx}")
    plain_shared = _make_dir_option("input", "-ind", "shared_dir", value="data")
    outdir = _make_dir_option("output", "-outp", "process_outdir", subpath="${array[$task_idx]}")
    plain_outdir = _make_dir_option("output", "-outq", "process_outdir")
    process = _make_process([shared, plain_shared, outdir, plain_outdir])

    assert _option_definition_line(process, shared, {}, {}) == [
        'debasher::define_opt_from_shared_dir "-outd" "data" optlist --subdir "${task_idx}" || return 1'
    ]
    assert _option_definition_line(process, plain_shared, {}, {}) == [
        'debasher::define_opt_from_shared_dir "-ind" "data" optlist || return 1'
    ]
    assert _option_definition_line(process, outdir, {}, {}) == [
        'debasher::define_opt_from_process_outdir "-outp" optlist --subdir "${array[$task_idx]}" || return 1'
    ]
    assert _option_definition_line(process, plain_outdir, {}, {}) == [
        'debasher::define_opt_from_process_outdir "-outq" optlist || return 1'
    ]


def test_a_process_output_directory_on_an_input_is_refused():
    option = _make_dir_option("input", "-ind", "process_outdir")
    with pytest.raises(ValueError, match="only an output"):
        _option_definition_line(_make_process([option]), option, {}, {})


def test_a_subpath_on_an_option_of_another_channel_is_refused():
    option = _make_dir_option("output", "-outf", "none", value="x", subpath="${task_idx}")
    with pytest.raises(ValueError, match="has a subpath"):
        _option_definition_line(_make_process([option]), option, {}, {})


def test_an_output_taken_from_the_process_specifications_is_refused():
    option = _make_dir_option("output", "-outn", "none", value="cpus")
    option.fromProcessSpec = True
    with pytest.raises(ValueError, match="is an output"):
        _option_definition_line(_make_process([option]), option, {}, {})


# --- The channel of a connected input --------------------------------------

from api.models import ProgramEdge  # noqa: E402


def _connected_program(target_channel, source_channel="fifo"):
    """counter writes -outf, on `source_channel`; reader reads it through
    -in, an input on `target_channel`."""
    counter = _make_process([
        ProgramOption(id="out", label="-outf", direction="output", dataType="int", channel=source_channel,
                      description="", value="nums" if source_channel != "none" else "${process_outdir}/n",
                      commandLine=False)
    ]).model_copy(update={"id": "c", "name": "counter"})
    reader = _make_process([
        ProgramOption(id="in", label="-in", direction="input", dataType="int", channel=target_channel,
                      description="", value="nums" if target_channel != "none" else "",
                      commandLine=False)
    ]).model_copy(update={"id": "r", "name": "reader"})
    edge = ProgramEdge(id="e", sourceProcessId="c", sourceOptionId="out", targetProcessId="r", targetOptionId="in")
    return _seq_program([], [counter, reader], sharedDirs=["nums"], edges=[edge])


def test_a_connected_input_reads_its_connection():
    script = generate_script(_connected_program("none"), skip_redundant_check=True)
    assert 'debasher::define_opt_from_proc_out "-in" "counter" "-outf" optlist' in script


@pytest.mark.parametrize("target_channel, source_channel", [("fifo", "fifo"), ("shared_dir", "fifo")])
def test_a_connected_input_on_a_channel_that_would_hide_its_connection_is_refused(target_channel, source_channel):
    # The input would take its value from its own channel, and the
    # connection would be lost: a FIFO of its own that nothing writes
    with pytest.raises(ValueError, match="a connected input receives what the output delivers"):
        generate_script(_connected_program(target_channel, source_channel), skip_redundant_check=True)


def test_a_connected_input_names_the_shared_directory_that_it_reads():
    script = generate_script(_connected_program("shared_dir", "shared_dir"), skip_redundant_check=True)
    assert 'debasher::define_opt_from_shared_dir "-in" "nums" optlist' in script


# --- Fanout families counted by the tasks of another process ---------------


def _family_program(family_direction, partner_modes, count_source=False):
    """fam, a standard process, has a fanout family connected to one task
    option of each partner, in the mode given for it: an input family
    reads the first partner, an output family is read by every one."""
    is_input = family_direction == "input"
    options = [
        ProgramOption(id="fam", label="-ind-ith" if is_input else "-outf-ith", direction=family_direction,
                      dataType="string", description="", value="" if is_input else "part_${i}",
                      commandLine=False, countSourceOptionId="w" if count_source else None),
    ]
    if count_source:
        options.append(ProgramOption(id="w", label="-w", direction="input", dataType="int", description="",
                                     value="", commandLine=True, mandatory=True))
    fam = _make_process(options).model_copy(update={"id": "f", "name": "fam"})
    processes, edges = [fam], []
    for index, mode in enumerate(partner_modes):
        name = f"partner{index}"
        partner = _make_process([
            ProgramOption(id="t", label="-outf" if is_input else "-inf", direction="output" if is_input else "input",
                          dataType="string", description="", value="out_${task_idx}" if is_input else "",
                          commandLine=False)
        ]).model_copy(update={
            "id": name,
            "name": name,
            "optionsHandler": OptionsHandler(mode=mode, generatorSizeCode="echo 2", arrayCode="array=(a b)"),
        })
        processes.append(partner)
        if is_input:
            edges.append(ProgramEdge(id=f"e{index}", sourceProcessId=name, sourceOptionId="t",
                                     targetProcessId="f", targetOptionId="fam"))
        else:
            edges.append(ProgramEdge(id=f"e{index}", sourceProcessId="f", sourceOptionId="fam",
                                     targetProcessId=name, targetOptionId="t"))
        if is_input:
            break
    return _seq_program([], processes, edges=edges)


@pytest.mark.parametrize("partner_mode", ["generator", "array"])
@pytest.mark.parametrize("family_direction, var", [("input", "n_ind"), ("output", "n_outf")])
def test_a_family_without_count_source_counts_the_tasks_of_the_process_at_its_other_end(
    family_direction, var, partner_mode
):
    script = generate_script(_family_program(family_direction, [partner_mode]), skip_redundant_check=True)

    assert f"    local {var}\n    {var}=$(debasher::get_process_num_tasks \"partner0\") || return 1\n" in script
    assert f"    for ((i=0; i<{var}; i++)); do\n" in script


@pytest.mark.parametrize(
    "family_direction, reason",
    [
        # An input family refuses the connection itself first
        ("input", r'connected to "partner0", which is not "array"- or "generator"-mode'),
        ("output", r'"partner0", which is in "manual" mode and has no tasks to count'),
    ],
)
def test_a_family_without_count_source_connected_to_a_manual_process_is_refused(family_direction, reason):
    with pytest.raises(ValueError, match=reason):
        generate_script(_family_program(family_direction, ["manual"]), skip_redundant_check=True)


@pytest.mark.parametrize("family_direction", ["input", "output"])
def test_a_family_with_a_count_source_option_keeps_reading_it(family_direction):
    script = generate_script(
        _family_program(family_direction, ["generator"], count_source=True), skip_redundant_check=True
    )

    assert 'local w=$(debasher::read_opt_value_from_line "${cmdline}" "-w")' in script
    assert "get_process_num_tasks" not in script


def test_an_output_family_without_count_source_nor_connection_is_refused():
    with pytest.raises(ValueError, match="has no count source option and no connection"):
        generate_script(_family_program("output", []), skip_redundant_check=True)


def test_an_output_family_without_count_source_read_by_two_processes_is_refused():
    with pytest.raises(ValueError, match=r"is read by several processes \(partner0, partner1\)"):
        generate_script(_family_program("output", ["generator", "generator"]), skip_redundant_check=True)


def test_a_family_whose_count_source_option_is_gone_is_refused_with_the_way_out():
    program = _family_program("input", ["generator"])
    program.processes[0].options[0].countSourceOptionId = "removed"

    with pytest.raises(ValueError, match="an option that the process does not have"):
        generate_script(program, skip_redundant_check=True)


# --- the process files that the module refers to ------------------------------


def _python_process(name="hello", **fields):
    defaults = dict(
        id=f"id-{name}",
        name=name,
        description="",
        position=Position(x=0, y=0),
        options=[],
        optionsHandler=OptionsHandler(mode="standard"),
        language="python",
        code="print('hi')",
        computationalSpecs=ComputationalSpecs(),
        additionalSpecs=AdditionalSpecs(force=False),
    )
    return ProgramProcess(**(defaults | fields))


def test_a_process_of_another_language_is_run_from_its_process_file():
    script = generate_script(_seq_program([], [_python_process()]), skip_redundant_check=True)

    assert '"ext_alias=hello.py"' in script
    assert "hello_heredoc_py()" not in script
    assert "print('hi')" not in script


def test_the_process_file_a_process_was_loaded_with_is_the_one_referred_to():
    process = _python_process(files=ProcessFiles(code="src/hello_world.py"))

    script = generate_script(_seq_program([], [process]), skip_redundant_check=True)

    assert '"ext_alias=src/hello_world.py"' in script


def test_a_bash_process_and_a_process_without_code_stay_as_they_are():
    bash = _make_process([])
    bash = bash.model_copy(update={"code": "count()\n{\n    :\n}"})
    nothing = _python_process("later", code="")

    script = generate_script(_seq_program([], [bash, nothing]), skip_redundant_check=True)

    assert "ext_alias" not in script
    assert "count()\n{\n    :\n}" in script


def test_a_process_with_an_alias_of_its_own_keeps_it():
    process = _python_process(additionalSpecs=AdditionalSpecs(force=False, externalAlias="./tools/hello.py"))

    script = generate_script(_seq_program([], [process]), skip_redundant_check=True)

    assert '"ext_alias=./tools/hello.py"' in script
    assert "ext_alias=hello.py" not in script
