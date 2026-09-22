# *- bash -*
# Minimal resident-program reference for the third G2 fix candidate (design
# doc, Conformance status): a single node, no Supervisor at all (one is
# optional, see SUPERVISOR_PORT), with only a control port fed from outside.
# Exists to check, with a real debasher_exec run, exactly what pieza 1 is
# responsible for (control_ports/halted files, staying alive after a halt
# closes, a clean exit on SIGTERM) with nothing else that could relaunch
# it: debasher_chaos_ref.sh's own Supervisor, polling every 0.5s, races an
# external SIGTERM against its own PID check and can relaunch a node that
# is exiting cleanly but has not written its .finished file yet (found
# 2026-09-22, not yet designed around); this program has no such thing to
# race against.

debasher_halt_ref_shared_dirs()
{
    :
}

debasher_halt_ref_program_type()
{
    program_type "resident"
}

########
solo_document()
{
    document_process "A single node with only a control port, fed from outside; no Supervisor in this program at all."
}

solo_explain_opts()
{
    explain_opt "-trigger" "<fifo>" "externally fed control fifo"
}

solo_identify_cmdline_opts()
{
    :
}

solo_define_opts()
{
    local optlist=""
    define_fifo_opt "-trigger" "solo_trigger" optlist || return 1
    save_opt_list optlist
}

solo_heredoc_py()
{
    cat <<'EOF'
from debasher_runtime_lib import FBPProcess


class Solo(FBPProcess):
    INPUT_PORTS = ["trigger"]
    CONTROL_PORTS = ["trigger"]

    def process_data(self, port_name, packet):
        pass

    def capture_node_state(self):
        return {}

    def restore_node_state(self, node_state):
        pass

    def initialize_runtime(self):
        pass


Solo().run()
EOF
}

########
debasher_halt_ref_program()
{
    add_debasher_process "solo" "cpus=1 mem=32 time=00:10:00"
}
