# *- bash -*
# Resident-program reference with a fan-out and a fan-in sized from the
# command line, for a real debasher_exec run: start sends what arrives from
# outside to the -w tasks of worker, one after another, and collect fans in
# from them, with as many ports as -w says, written with the "ith"
# convention of general programs (-outfith, -indith). A Supervisor watches
# every node, every task of worker included, and relays a manual trigger to
# start. It declares no port: the engine gives it its ports from the options
# of its module, as it gives each node its own, so the number of nodes it
# watches follows -w too.

debasher_fanout_cmdline_ref_shared_dirs()
{
    :
}

debasher_fanout_cmdline_ref_program_type()
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
    explain_opt "-w" "<int>" "number of tasks of worker"
    explain_opt "-ext" "<fifo>" "externally fed input fifo"
    explain_opt "-trigger" "<fifo>" "control fifo from the supervisor"
    explain_opt "-outfith" "<fifo>" "output fifo to the i'th task of worker"
    explain_opt "-outhb" "<fifo>" "heartbeat fifo to the supervisor"
}

start_identify_cmdline_opts()
{
    opt_is_cmdline "-w"
}

start_define_opts()
{
    local cmdline=$1
    local optlist=""
    define_cmdline_opt "$cmdline" "-w" optlist || return 1
    define_fifo_opt "-ext" "start_ext" optlist --external || return 1
    define_opt_from_proc_out "-trigger" "sup" "-outtrig" optlist || return 1
    local w=$(debasher::read_opt_value_from_line "${cmdline}" "-w")
    local i
    for (( i = 0; i < w; i++ )); do
        define_fifo_opt "-outf${i}" "start_out_${i}" optlist || return 1
    done
    define_fifo_opt "-outhb" "start_hb" optlist || return 1
    save_opt_list optlist
}

start_heredoc_py()
{
    cat <<'EOF'
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
        self.send_data(f"outf{self.sent % int(self.opts['w'])}", packet)
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
    explain_opt "-w" "<int>" "number of tasks"
    explain_opt "-inf" "<fifo>" "input fifo from start"
    explain_opt "-outf" "<fifo>" "output fifo to collect"
    explain_opt "-outhb" "<fifo>" "heartbeat fifo to the supervisor"
}

worker_identify_cmdline_opts()
{
    opt_is_cmdline "-w"
}

worker_define_opts()
{
    local cmdline=$1
    local w=$(debasher::read_opt_value_from_line "${cmdline}" "-w")
    local idx
    for (( idx = 0; idx < w; idx++ )); do
        local optlist=""
        define_cmdline_opt "$cmdline" "-w" optlist || return 1
        define_opt_from_proc_out "-inf" "start" "-outf${idx}" optlist || return 1
        define_fifo_opt "-outf" "worker_out_${idx}" optlist || return 1
        define_fifo_opt "-outhb" "worker_hb_${idx}" optlist || return 1
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
    explain_opt "-w" "<int>" "number of tasks of worker"
    explain_opt "-indith" "<fifo>" "input fifo from the i'th task of worker"
    explain_opt "-outhb" "<fifo>" "heartbeat fifo to the supervisor"
}

collect_identify_cmdline_opts()
{
    opt_is_cmdline "-w"
}

collect_define_opts()
{
    local cmdline=$1
    local optlist=""
    define_cmdline_opt "$cmdline" "-w" optlist || return 1
    local w=$(debasher::read_opt_value_from_line "${cmdline}" "-w")
    local i
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
    explain_opt "-w" "<int>" "number of tasks of worker"
    explain_opt "-hb_start" "<fifo>" "start's heartbeat fifo"
    explain_opt "-hbith" "<fifo>" "heartbeat fifo of the i'th task of worker"
    explain_opt "-hb_collect" "<fifo>" "collect's heartbeat fifo"
    explain_opt "-outtrig" "<fifo>" "trigger fifo to start"
    explain_opt "-manual" "<fifo>" "externally fed manual trigger fifo"
}

sup_identify_cmdline_opts()
{
    opt_is_cmdline "-w"
}

sup_define_opts()
{
    local cmdline=$1
    local optlist=""
    define_cmdline_opt "$cmdline" "-w" optlist || return 1
    define_opt_from_proc_out "-hb_start" "start" "-outhb" optlist || return 1
    local w=$(debasher::read_opt_value_from_line "${cmdline}" "-w")
    local i
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
debasher_fanout_cmdline_ref_program()
{
    add_debasher_process "start" "cpus=1 mem=32 time=00:10:00"
    add_debasher_process "worker" "cpus=1 mem=32 time=00:10:00"
    add_debasher_process "collect" "cpus=1 mem=32 time=00:10:00"
    add_debasher_process "sup" "cpus=1 mem=32 time=00:10:00"
}
