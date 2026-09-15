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
