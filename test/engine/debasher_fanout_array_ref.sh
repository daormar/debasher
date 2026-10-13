# *- bash -*
# The program of debasher_fanout_tasks_ref.sh with worker written as an
# array, without an option generator, whose number of tasks the task
# shaping option -w gives: start, collect and the Supervisor, processes
# without an option generator too, ask the engine for the number of tasks of
# worker with get_process_num_tasks, which runs the _define_opts method of
# worker again when it is asked before its turn. Each node finds as many
# ports as worker has tasks, and a node relaunched by the Supervisor asks
# again, inside its task, and gets the same number.

debasher_fanout_array_ref_shared_dirs()
{
    :
}

debasher_fanout_array_ref_program_type()
{
    program_type "resident"
}

########
start_document()
{
    document_process "Fan-out: sends each message from outside to the next task of worker, in turn."
}

start_explain_opts()
{
    explain_opt "-ext" "<fifo>" "externally fed input fifo"
    explain_opt "-trigger" "<fifo>" "control fifo from the supervisor"
    explain_opt "-outf-ith" "<fifo>" "output fifo to the i'th task of worker"
    explain_opt "-outhb" "<fifo>" "heartbeat fifo to the supervisor"
}

start_identify_cmdline_opts()
{
    :
}

start_define_opts()
{
    local cmdline=$1
    local optlist=""
    define_fifo_opt "-ext" "start_ext" optlist --external || return 1
    define_opt_from_proc_out "-trigger" "sup" "-outtrig" optlist || return 1
    local w i
    w=$(get_process_num_tasks "worker") || return 1
    for (( i = 0; i < w; i++ )); do
        define_fifo_opt "-outf${i}" "start_out_${i}" optlist || return 1
    done
    define_fifo_opt "-outhb" "start_hb" optlist || return 1
    save_opt_list optlist
}

start_heredoc_py()
{
    cat <<'EOF'
import re

from debasher_runtime_lib import FBPProcess


class Start(FBPProcess):
    HEARTBEAT_INTERVAL_SECONDS = 0.2

    def __init__(self):
        super().__init__()
        # The node state: how many messages it has sent. The task that gets
        # the next one follows from it, so that a replay sends every message
        # to the same task as the first time.
        self.sent = 0

    def process_data(self, port_name, packet):
        # One output port for each task of worker
        num_tasks = sum(1 for port in self.OUTPUT_PORTS if re.fullmatch(r"outf[0-9]+", port))
        self.send_data(f"outf{self.sent % num_tasks}", packet)
        self.sent += 1

    def capture_node_state(self):
        return {"sent": self.sent}

    def restore_node_state(self, node_state):
        self.sent = node_state["sent"]

    def initialize_runtime(self):
        pass


Start().run()
EOF
}

########
worker_document()
{
    document_process "Array of -w tasks: task i reads the i'th output of start and forwards what it gets to collect."
}

worker_explain_opts()
{
    explain_opt "-inf" "<fifo>" "input fifo from start"
    explain_opt "-outf" "<fifo>" "output fifo to collect"
    explain_opt "-outhb" "<fifo>" "heartbeat fifo to the supervisor"
}

worker_explain_task_shaping_opts()
{
    explain_task_shaping_opt "-w" "<int>" "number of tasks"
}

worker_identify_cmdline_opts()
{
    :
}

worker_define_opts()
{
    local cmdline=$1
    local w task_idx
    w=$(debasher::read_opt_value_from_line "${cmdline}" "-w") || return 1
    for (( task_idx = 0; task_idx < w; task_idx++ )); do
        local optlist=""
        define_opt_from_proc_out "-inf" "start" "-outf${task_idx}" optlist || return 1
        define_fifo_opt "-outf" "worker_out_${task_idx}" optlist || return 1
        define_fifo_opt "-outhb" "worker_hb_${task_idx}" optlist || return 1
        save_opt_list optlist
    done
}

worker_heredoc_py()
{
    cat <<'EOF'
from debasher_runtime_lib import FBPProcess


class Worker(FBPProcess):
    HEARTBEAT_INTERVAL_SECONDS = 0.2

    def process_data(self, port_name, packet):
        self.send_data("outf", packet)

    def capture_node_state(self):
        return {}

    def restore_node_state(self, node_state):
        pass

    def initialize_runtime(self):
        pass


Worker().run()
EOF
}

########
collect_document()
{
    document_process "Fan-in: counts what arrives from each task of worker."
}

collect_explain_opts()
{
    explain_opt "-ind-ith" "<fifo>" "input fifo from the i'th task of worker"
    explain_opt "-outhb" "<fifo>" "heartbeat fifo to the supervisor"
}

collect_identify_cmdline_opts()
{
    :
}

collect_define_opts()
{
    local cmdline=$1
    local optlist=""
    local w i
    w=$(get_process_num_tasks "worker") || return 1
    for (( i = 0; i < w; i++ )); do
        define_opt_from_proc_task_out "-ind${i}" "worker" "${i}" "-outf" optlist || return 1
    done
    define_fifo_opt "-outhb" "collect_hb" optlist || return 1
    save_opt_list optlist
}

collect_heredoc_py()
{
    cat <<'EOF'
from debasher_runtime_lib import FBPProcess


class Collect(FBPProcess):
    HEARTBEAT_INTERVAL_SECONDS = 0.2

    def __init__(self):
        super().__init__()
        # The node state: how many messages have arrived on each port.
        self.counts = {}

    def process_data(self, port_name, packet):
        self.counts[port_name] = self.counts.get(port_name, 0) + 1

    def capture_node_state(self):
        return {"counts": dict(self.counts)}

    def restore_node_state(self, node_state):
        self.counts = dict(node_state["counts"])

    def initialize_runtime(self):
        pass


Collect().run()
EOF
}

########
sup_document()
{
    document_process "Supervises start, every task of worker and collect; relays a manual trigger from outside to start."
}

sup_explain_opts()
{
    explain_opt "-hb_start" "<fifo>" "start's heartbeat fifo"
    explain_opt "-hb-ith" "<fifo>" "heartbeat fifo of the i'th task of worker"
    explain_opt "-hb_collect" "<fifo>" "collect's heartbeat fifo"
    explain_opt "-outtrig" "<fifo>" "trigger fifo to start"
    explain_opt "-manual" "<fifo>" "externally fed manual trigger fifo"
}

sup_identify_cmdline_opts()
{
    :
}

sup_define_opts()
{
    local cmdline=$1
    local optlist=""
    define_opt_from_proc_out "-hb_start" "start" "-outhb" optlist || return 1
    local w i
    w=$(get_process_num_tasks "worker") || return 1
    for (( i = 0; i < w; i++ )); do
        define_opt_from_proc_task_out "-hb${i}" "worker" "${i}" "-outhb" optlist || return 1
    done
    define_opt_from_proc_out "-hb_collect" "collect" "-outhb" optlist || return 1
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
    # Comfortably above the nodes' HEARTBEAT_INTERVAL_SECONDS (0.2 s), so
    # that a relaunched node has time to start before its first heartbeat
    # is due.
    HEARTBEAT_TIMEOUT_SECS = 3


Sup().run()
EOF
}

########
debasher_fanout_array_ref_program()
{
    add_debasher_process "start" "cpus=1 mem=32 time=00:10:00"
    add_debasher_process "worker" "cpus=1 mem=32 time=00:10:00"
    add_debasher_process "collect" "cpus=1 mem=32 time=00:10:00"
    add_debasher_process "sup" "cpus=1 mem=32 time=00:10:00"
}
