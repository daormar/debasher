# *- bash -*
# Resident-program reference with no fifo from outside the program, for a
# real debasher_exec run: solo is triggered only by the Supervisor, which
# has no manual trigger. Checks that a new run on the same output directory
# after a halt resumes every node, which nothing but the program type can
# tell debasher_exec here (no fifo from outside marks a process to rerun),
# and that a node keeps its output directory when it is launched again.

debasher_resume_ref_shared_dirs()
{
    :
}

debasher_resume_ref_program_type()
{
    program_type "resident"
}

########
solo_document()
{
    document_process "A node triggered only by the Supervisor."
}

solo_explain_opts()
{
    explain_opt "-trigger" "<fifo>" "control fifo from the supervisor"
    explain_opt "-outhb" "<fifo>" "heartbeat fifo to the supervisor"
}

solo_identify_cmdline_opts()
{
    :
}

solo_define_opts()
{
    local optlist=""
    define_opt_from_proc_out "-trigger" "sup" "-outtrig" optlist || return 1
    define_fifo_opt "-outhb" "solo_hb" optlist || return 1
    save_opt_list optlist
}

solo_heredoc_py()
{
    cat <<'EOF'
from debasher_runtime_lib import FBPProcess


class Solo(FBPProcess):
    HEARTBEAT_INTERVAL_SECONDS = 0.2

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
sup_document()
{
    document_process "Supervises solo and triggers it; has no manual trigger."
}

sup_explain_opts()
{
    explain_opt "-hb_solo" "<fifo>" "solo's heartbeat fifo"
    explain_opt "-outtrig" "<fifo>" "trigger fifo to solo"
}

sup_identify_cmdline_opts()
{
    :
}

sup_define_opts()
{
    local optlist=""
    define_opt_from_proc_out "-hb_solo" "solo" "-outhb" optlist || return 1
    define_fifo_opt "-outtrig" "sup_trig" optlist --control || return 1
    save_opt_list optlist
}

sup_heredoc_py()
{
    cat <<'EOF'
from debasher_runtime_lib import Supervisor


class Sup(Supervisor):
    HEARTBEAT_CHECK_INTERVAL_SECS = 0.5
    HEARTBEAT_TIMEOUT_SECS = 3


Sup().run()
EOF
}

########
debasher_resume_ref_program()
{
    add_debasher_process "solo" "cpus=1 mem=32 time=00:10:00"
    add_debasher_process "sup" "cpus=1 mem=32 time=00:10:00"
}
