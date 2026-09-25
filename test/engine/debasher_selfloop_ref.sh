# *- bash -*
# Resident-program reference with a self-loop, for a real debasher_exec run:
# counter emits on its own, a step at a time. A message from outside says how
# many steps to take; each call to process_data sends one value to sink and
# sends counter itself the message that triggers the next step, until its
# node state says to stop. A Supervisor watches counter and sink and relays a
# manual trigger to counter, the only initiator. A round goes round the loop
# like any other channel, and a relaunch of counter replays its input log and
# resends, with the same numbers, what the loop held when it died.

debasher_selfloop_ref_shared_dirs()
{
    :
}

debasher_selfloop_ref_program_type()
{
    program_type "resident"
}

########
counter_document()
{
    document_process "Counts from 0 to the limit that arrives from outside, one step per message it sends itself, and sends each value to sink."
}

counter_explain_opts()
{
    explain_opt "-ext" "<fifo>" "externally fed input fifo, with the limit"
    explain_opt "-trigger" "<fifo>" "control fifo from the supervisor"
    explain_opt "-self" "<fifo>" "input fifo from counter itself"
    explain_opt "-outself" "<fifo>" "output fifo to counter itself"
    explain_opt "-outsink" "<fifo>" "output fifo to sink"
    explain_opt "-outhb" "<fifo>" "heartbeat fifo to the supervisor"
}

counter_identify_cmdline_opts()
{
    :
}

counter_define_opts()
{
    local optlist=""
    define_fifo_opt "-ext" "counter_ext" optlist --external || return 1
    define_opt_from_proc_out "-trigger" "sup" "-outtrig" optlist || return 1
    define_opt_from_proc_out "-self" "counter" "-outself" optlist || return 1
    define_fifo_opt "-outself" "counter_self" optlist || return 1
    define_fifo_opt "-outsink" "counter_to_sink" optlist || return 1
    define_fifo_opt "-outhb" "counter_hb" optlist || return 1
    save_opt_list optlist
}

counter_heredoc_py()
{
    cat <<'EOF'
from debasher_runtime_lib import FBPProcess


class Counter(FBPProcess):
    HEARTBEAT_INTERVAL_SECONDS = 0.2
    # The pace of the loop: long enough for a test to kill counter while it
    # counts. sleep() does not wait while counter replays its log.
    STEP_SECS = 0.01

    def __init__(self):
        super().__init__()
        # The node state: the limit, once it has arrived from outside.
        self.limit = None

    def process_data(self, port_name, packet):
        if port_name == "ext":
            self.limit = packet["limit"]
            self.send_data("outself", 0)
            return
        # A step of the loop
        self.sleep(self.STEP_SECS)
        self.send_data("outsink", packet)
        if packet + 1 < self.limit:
            self.send_data("outself", packet + 1)

    def capture_node_state(self):
        return {"limit": self.limit}

    def restore_node_state(self, node_state):
        self.limit = node_state["limit"]

    def initialize_runtime(self):
        pass


Counter().run()
EOF
}

########
sink_document()
{
    document_process "Receives the values of counter; its input log is the trace a test reads."
}

sink_explain_opts()
{
    explain_opt "-from_counter" "<fifo>" "input fifo from counter"
    explain_opt "-outhb" "<fifo>" "heartbeat fifo to the supervisor"
}

sink_identify_cmdline_opts()
{
    :
}

sink_define_opts()
{
    local optlist=""
    define_opt_from_proc_out "-from_counter" "counter" "-outsink" optlist || return 1
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
    document_process "Supervises counter and sink; relays a manual trigger from outside to counter."
}

sup_explain_opts()
{
    explain_opt "-hb_counter" "<fifo>" "counter's heartbeat fifo"
    explain_opt "-hb_sink" "<fifo>" "sink's heartbeat fifo"
    explain_opt "-outtrig" "<fifo>" "trigger fifo to counter"
    explain_opt "-manual" "<fifo>" "externally fed manual trigger fifo"
}

sup_identify_cmdline_opts()
{
    :
}

sup_define_opts()
{
    local optlist=""
    define_opt_from_proc_out "-hb_counter" "counter" "-outhb" optlist || return 1
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
    # Comfortably above the nodes' HEARTBEAT_INTERVAL_SECONDS (0.2 s), so
    # that a relaunched node has time to start before its first heartbeat
    # is due.
    HEARTBEAT_TIMEOUT_SECS = 3


Sup().run()
EOF
}

########
debasher_selfloop_ref_program()
{
    add_debasher_process "counter" "cpus=1 mem=32 time=00:10:00"
    add_debasher_process "sink" "cpus=1 mem=32 time=00:10:00"
    add_debasher_process "sup" "cpus=1 mem=32 time=00:10:00"
}
