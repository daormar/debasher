# *- bash -*
# Resident-program reference with a node whose startup is long, for a real
# debasher_exec run: slow takes a while over every message it processes, so a
# relaunch that replays its input log is silent for longer than the heartbeat
# timeout of the Supervisor. Its computational specifications give it a
# startup deadline (startup_timeout_s) that covers the replay, which the
# engine passes to the Supervisor.

debasher_startup_ref_shared_dirs()
{
    :
}

debasher_startup_ref_program_type()
{
    program_type "resident"
}

########
slow_document()
{
    document_process "Takes a while over every message that arrives from outside."
}

slow_explain_opts()
{
    explain_opt "-ext" "<fifo>" "externally fed input fifo"
    explain_opt "-trigger" "<fifo>" "externally fed control fifo"
    explain_opt "-outhb" "<fifo>" "heartbeat fifo to the supervisor"
}

slow_identify_cmdline_opts()
{
    :
}

slow_define_opts()
{
    local optlist=""
    define_fifo_opt "-ext" "slow_ext" optlist --external || return 1
    define_fifo_opt "-trigger" "slow_trigger" optlist --control || return 1
    define_fifo_opt "-outhb" "slow_hb" optlist || return 1
    save_opt_list optlist
}

slow_heredoc_py()
{
    cat <<'EOF'
import time

from debasher_runtime_lib import FBPProcess


class Slow(FBPProcess):
    HEARTBEAT_INTERVAL_SECONDS = 0.2
    # The work each message takes, live and in a replay alike.
    WORK_SECS = 0.5

    def __init__(self):
        super().__init__()
        self.processed = 0

    def process_data(self, port_name, packet):
        time.sleep(self.WORK_SECS)
        self.processed += 1

    def capture_node_state(self):
        return {"processed": self.processed}

    def restore_node_state(self, node_state):
        self.processed = node_state["processed"]

    def initialize_runtime(self):
        pass


Slow().run()
EOF
}

########
sup_document()
{
    document_process "Supervises slow."
}

sup_explain_opts()
{
    explain_opt "-hb_slow" "<fifo>" "slow's heartbeat fifo"
}

sup_identify_cmdline_opts()
{
    :
}

sup_define_opts()
{
    local optlist=""
    define_opt_from_proc_out "-hb_slow" "slow" "-outhb" optlist || return 1
    save_opt_list optlist
}

sup_heredoc_py()
{
    cat <<'EOF'
from debasher_runtime_lib import Supervisor


class Sup(Supervisor):
    HEARTBEAT_CHECK_INTERVAL_SECS = 0.5


Sup().run()
EOF
}

########
debasher_startup_ref_program()
{
    add_debasher_process "slow" "cpus=1; mem=32; time=00:10:00; startup_timeout_s=30"
    add_debasher_process "sup" "cpus=1; mem=32; time=00:10:00; heartbeat_timeout_s=2"
}
