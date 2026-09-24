# *- bash -*
# Resident-program reference with a launcher node, for a real debasher_exec
# run: every request that arrives from outside at launch starts a batch run
# of debasher_launcher_batch.sh, which launch finds next to this module, as
# an external alias would be, in a run directory of its own; launch tells
# sink when each one ends. A Supervisor watches launch and sink and relays a
# manual trigger to launch. The batch runs use the scheduler that
# DEBASHER_LAUNCHER_REF_SCHED names when debasher_exec loads the program,
# BUILTIN by default.

debasher_launcher_ref_shared_dirs()
{
    :
}

debasher_launcher_ref_program_type()
{
    program_type "resident"
}

########
launch_document()
{
    document_process "Launches the batch program once for each request, and tells sink when each batch run ends."
}

launch_explain_opts()
{
    explain_opt "-requests" "<fifo>" "externally fed fifo of requests"
    explain_opt "-runs_done" "<fifo>" "fifo on which the node learns that a batch run ended"
    explain_opt "-trigger" "<fifo>" "control fifo from the supervisor"
    explain_opt "-outdone" "<fifo>" "output fifo to sink, one notice per batch run"
    explain_opt "-outhb" "<fifo>" "heartbeat fifo to the supervisor"
}

launch_identify_cmdline_opts()
{
    :
}

launch_define_opts()
{
    local optlist=""
    define_fifo_opt "-requests" "launch_requests" optlist --external || return 1
    define_fifo_opt "-runs_done" "launch_runs_done" optlist --external || return 1
    define_opt_from_proc_out "-trigger" "sup" "-outtrig" optlist || return 1
    define_fifo_opt "-outdone" "launch_done" optlist || return 1
    define_fifo_opt "-outhb" "launch_hb" optlist || return 1
    save_opt_list optlist
}

launch_heredoc_py()
{
    cat <<'EOF'
from debasher_runtime_lib import ProgramLauncher


class Launch(ProgramLauncher):
    PFILE = "debasher_launcher_batch.sh"
    HEARTBEAT_INTERVAL_SECONDS = 0.2
    LAUNCH_CHECK_INTERVAL_SECS = 0.2
    STATUS_CHECK_INTERVAL_SECS = 0.5


Launch().run()
EOF
}

########
sink_document()
{
    document_process "Receives the notices of launch; its input log is the trace a test reads."
}

sink_explain_opts()
{
    explain_opt "-from_launch" "<fifo>" "input fifo from launch"
    explain_opt "-outhb" "<fifo>" "heartbeat fifo to the supervisor"
}

sink_identify_cmdline_opts()
{
    :
}

sink_define_opts()
{
    local optlist=""
    define_opt_from_proc_out "-from_launch" "launch" "-outdone" optlist || return 1
    define_fifo_opt "-outhb" "sink_hb" optlist || return 1
    save_opt_list optlist
}

sink_heredoc_py()
{
    cat <<'EOF'
from debasher_runtime_lib import FBPProcess


class Sink(FBPProcess):
    HEARTBEAT_INTERVAL_SECONDS = 0.2

    def process_data(self, port_name, packet):
        pass

    def capture_node_state(self):
        return {}

    def restore_node_state(self, node_state):
        pass

    def initialize_runtime(self):
        pass


Sink().run()
EOF
}

########
sup_document()
{
    document_process "Supervises launch and sink; relays a manual trigger from outside to launch."
}

sup_explain_opts()
{
    explain_opt "-hb_launch" "<fifo>" "launch's heartbeat fifo"
    explain_opt "-hb_sink" "<fifo>" "sink's heartbeat fifo"
    explain_opt "-outtrig" "<fifo>" "trigger fifo to launch"
    explain_opt "-manual" "<fifo>" "externally fed manual trigger fifo"
}

sup_identify_cmdline_opts()
{
    :
}

sup_define_opts()
{
    local optlist=""
    define_opt_from_proc_out "-hb_launch" "launch" "-outhb" optlist || return 1
    define_opt_from_proc_out "-hb_sink" "sink" "-outhb" optlist || return 1
    define_fifo_opt "-outtrig" "sup_trig" optlist --control || return 1
    define_fifo_opt "-manual" "sup_manual" optlist --control || return 1
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
debasher_launcher_ref_program()
{
    add_debasher_process "launch" "cpus=1; mem=32; time=00:10:00; batch_sched=${DEBASHER_LAUNCHER_REF_SCHED:-BUILTIN}"
    add_debasher_process "sink" "cpus=1 mem=32 time=00:10:00"
    add_debasher_process "sup" "cpus=1 mem=32 time=00:10:00"
}
