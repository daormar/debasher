import pytest

from api.models import (
    AdditionalSpecs,
    ComputationalSpecs,
    OptionsHandler,
    Position,
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
        (dict(label="-with"), "can't be a fanout family"),
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
        label="-outfith",
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
    assert "step_heredoc_py()" in script
    assert script.index('add_debasher_process "count"') < script.index(
        'add_debasher_seq_process "step" "cpus=1 mem=32 time=00:01:00" ""'
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
