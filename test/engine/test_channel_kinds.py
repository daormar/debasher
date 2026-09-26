"""
Real debasher_exec runs of small programs, written by each test, that the
checks of the fifo tags refuse when the program is loaded (see the design
doc's "Channel kinds declared with the fifo"): nothing is launched.
"""

import subprocess
from pathlib import Path

from resident_run import (
    DEBASHER_EXEC,
    real_run,
)

pytestmark = real_run


_NODE_PY = '''
from debasher_runtime_lib import FBPProcess


class {cls}(FBPProcess):
    INPUT_PORTS = {inputs}
    OUTPUT_PORTS = {outputs}
    CONTROL_PORTS = {control}
    EXTERNAL_PORTS = {external}

    def process_data(self, port_name, packet):
        pass

    def capture_node_state(self):
        return {{}}

    def restore_node_state(self, node_state):
        pass

    def initialize_runtime(self):
        pass


{cls}().run()
'''


def _resident_process(name, explain, define, inputs, outputs, control=(), external=()):
    # The class of a node is named after its process, in CamelCase, which
    # for these one-word names is the name capitalized.
    source = _NODE_PY.format(
        cls=name.capitalize(),
        inputs=list(inputs),
        outputs=list(outputs),
        control=list(control),
        external=list(external),
    )
    return f"""
{name}_document()
{{
    document_process "{name}"
}}

{name}_explain_opts()
{{
{explain}
}}

{name}_identify_cmdline_opts()
{{
    :
}}

{name}_define_opts()
{{
    local optlist=""
{define}
    save_opt_list optlist
}}

{name}_heredoc_py()
{{
    cat <<'EOF'
{source}
EOF
}}
"""


def _run(tmp_path, pfile):
    outdir = tmp_path / "out"
    assert DEBASHER_EXEC.exists(), "bin/debasher_exec not built: run make install first"
    result = subprocess.run(
        [str(DEBASHER_EXEC), "--pfile", str(pfile), "--outdir", str(outdir)],
        capture_output=True,
        text=True,
    )
    return result, outdir


def _launched(outdir):
    return list(Path(outdir).glob("__exec__/*/*.id"))


def test_a_resident_program_with_a_node_that_no_round_can_reach_is_refused(tmp_path):
    """
    a and b are fed from outside and fan in to c, but only a has a control
    channel: no round can reach b.
    """
    pfile = tmp_path / "debasher_unreachable_ref.sh"
    pfile.write_text(
        """
debasher_unreachable_ref_shared_dirs()
{
    :
}

debasher_unreachable_ref_program_type()
{
    program_type "resident"
}
"""
        + _resident_process(
            "a",
            '    explain_opt "-trigger" "<fifo>" "control"\n'
            '    explain_opt "-ext" "<fifo>" "from outside"\n'
            '    explain_opt "-outc" "<fifo>" "to c"',
            '    define_fifo_opt "-trigger" "a_trigger" optlist --control || return 1\n'
            '    define_fifo_opt "-ext" "a_ext" optlist --external || return 1\n'
            '    define_fifo_opt "-outc" "a_to_c" optlist || return 1',
            inputs=["trigger", "ext"],
            outputs=["outc"],
            control=["trigger"],
            external=["ext"],
        )
        + _resident_process(
            "b",
            '    explain_opt "-ext" "<fifo>" "from outside"\n'
            '    explain_opt "-outc" "<fifo>" "to c"',
            '    define_fifo_opt "-ext" "b_ext" optlist --external || return 1\n'
            '    define_fifo_opt "-outc" "b_to_c" optlist || return 1',
            inputs=["ext"],
            outputs=["outc"],
            external=["ext"],
        )
        + _resident_process(
            "c",
            '    explain_opt "-from_a" "<fifo>" "from a"\n'
            '    explain_opt "-from_b" "<fifo>" "from b"',
            '    define_opt_from_proc_out "-from_a" "a" "-outc" optlist || return 1\n'
            '    define_opt_from_proc_out "-from_b" "b" "-outc" optlist || return 1',
            inputs=["from_a", "from_b"],
            outputs=[],
        )
        + """
debasher_unreachable_ref_program()
{
    add_debasher_process "a" "cpus=1 mem=32 time=00:10:00"
    add_debasher_process "b" "cpus=1 mem=32 time=00:10:00"
    add_debasher_process "c" "cpus=1 mem=32 time=00:10:00"
}
"""
    )

    result, outdir = _run(tmp_path, pfile)

    assert result.returncode != 0, result.stdout
    assert "Error: no round can reach b:" in result.stderr, result.stderr
    assert _launched(outdir) == []


def test_a_general_program_with_a_fifo_tag_is_refused(tmp_path):
    pfile = tmp_path / "debasher_tagged_general_ref.sh"
    pfile.write_text(
        """
debasher_tagged_general_ref_shared_dirs()
{
    :
}

writer_document()
{
    document_process "writer"
}

writer_explain_opts()
{
    explain_opt "-outf" "<fifo>" "output"
}

writer_identify_cmdline_opts()
{
    :
}

writer_define_opts()
{
    local optlist=""
    define_fifo_opt "-outf" "writer_out" optlist --external || return 1
    save_opt_list optlist
}

writer()
{
    :
}

debasher_tagged_general_ref_program()
{
    add_debasher_process "writer" "cpus=1 mem=32 time=00:10:00"
}
"""
    )

    result, outdir = _run(tmp_path, pfile)

    assert result.returncode != 0, result.stdout
    assert "is tagged --external, which only a 'resident' program may use" in result.stderr, result.stderr
    assert _launched(outdir) == []
