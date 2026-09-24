# *- bash -*
# Chaos test reference program: fanin has two input ports, one external
# (ext, tagged --external) and one closing a 2-node cycle (loop_in, fed by
# loop). fanin forwards a tagged copy of everything it processes, on either
# port, to sink: sink's own input log is then the exact, deduplicated,
# ordered record of what fanin actually saw, which is what the verifier
# reads after a run. Each copy also carries fanin's node state (how many
# messages it has processed on that port, and a digest of the order in
# which it processed every message, across ports), so that the trace also
# shows whether a relaunch or a resume restored it and replayed that order.
# fanin is the sole initiator, triggered by the Supervisor's manual trigger
# channel (fed from outside). The Supervisor holds the fifos of the business
# channels unless the program is given -no_hold_fifos.

debasher_chaos_ref_shared_dirs()
{
    :
}

debasher_chaos_ref_program_type()
{
    program_type "resident"
}

########
fanin_document()
{
    document_process "Fan-in over ext (external) and loop_in (closes the cycle with loop); forwards a tagged copy of everything to sink, and echoes ext into the loop."
}

fanin_explain_opts()
{
    explain_opt "-ext" "<fifo>" "externally fed input fifo"
    explain_opt "-loop_in" "<fifo>" "input fifo from loop, closes the cycle"
    explain_opt "-trigger" "<fifo>" "control fifo from the supervisor"
    explain_opt "-outloop" "<fifo>" "output fifo to loop"
    explain_opt "-outsink" "<fifo>" "output fifo to sink"
    explain_opt "-outhb" "<fifo>" "heartbeat fifo to the supervisor"
}

fanin_identify_cmdline_opts()
{
    :
}

fanin_define_opts()
{
    local optlist=""
    define_fifo_opt "-ext" "fanin_ext" optlist --external || return 1
    define_opt_from_proc_out "-loop_in" "loop" "-outfanin" optlist || return 1
    define_opt_from_proc_out "-trigger" "sup" "-outtrig_fanin" optlist || return 1
    define_fifo_opt "-outloop" "fanin_to_loop" optlist || return 1
    define_fifo_opt "-outsink" "fanin_to_sink" optlist || return 1
    define_fifo_opt "-outhb" "fanin_hb" optlist || return 1
    save_opt_list optlist
}

fanin_heredoc_py()
{
    cat <<'EOF'
import hashlib

from debasher_runtime_lib import FBPProcess


class Fanin(FBPProcess):
    HEARTBEAT_INTERVAL_SECONDS = 0.2

    def __init__(self):
        super().__init__()
        # The node state: how many messages it has processed on each port,
        # and a digest of every message it has processed, on any port, in
        # the order it processed them, which makes the node sensitive to
        # how its ports interleave. Every copy sent to sink carries both,
        # so that sink's trace shows whether a relaunch, or a resume after
        # a halt, restored the state and replayed that order exactly.
        self.counts = {}
        self.digest = ""

    def process_data(self, port_name, packet):
        self.counts[port_name] = self.counts.get(port_name, 0) + 1
        self.digest = hashlib.sha256(f"{self.digest}|{port_name}:{packet}".encode()).hexdigest()
        self.send_data(
            "outsink",
            {
                "port": port_name,
                "value": packet,
                "count": self.counts[port_name],
                "digest": self.digest,
            },
        )
        if port_name == "ext":
            self.send_data("outloop", packet)

    def capture_node_state(self):
        return {"counts": dict(self.counts), "digest": self.digest}

    def restore_node_state(self, node_state):
        self.counts = dict(node_state["counts"])
        self.digest = node_state["digest"]

    def initialize_runtime(self):
        pass


Fanin().run()
EOF
}

########
loop_document()
{
    document_process "Echoes whatever it receives from fanin straight back to it, closing the cycle."
}

loop_explain_opts()
{
    explain_opt "-from_fanin" "<fifo>" "input fifo from fanin"
    explain_opt "-outfanin" "<fifo>" "output fifo to fanin"
    explain_opt "-outhb" "<fifo>" "heartbeat fifo to the supervisor"
}

loop_identify_cmdline_opts()
{
    :
}

loop_define_opts()
{
    local optlist=""
    define_opt_from_proc_out "-from_fanin" "fanin" "-outloop" optlist || return 1
    define_fifo_opt "-outfanin" "loop_to_fanin" optlist || return 1
    define_fifo_opt "-outhb" "loop_hb" optlist || return 1
    save_opt_list optlist
}

loop_heredoc_py()
{
    cat <<'EOF'
from debasher_runtime_lib import FBPProcess


class Loop(FBPProcess):
    HEARTBEAT_INTERVAL_SECONDS = 0.2

    def process_data(self, port_name, packet):
        self.send_data("outfanin", packet)

    def capture_node_state(self):
        return {}

    def restore_node_state(self, node_state):
        pass

    def initialize_runtime(self):
        pass


Loop().run()
EOF
}

########
sink_document()
{
    document_process "Records nothing itself: its own input log is the verified trace fanin produced."
}

sink_explain_opts()
{
    explain_opt "-from_fanin" "<fifo>" "input fifo from fanin"
    explain_opt "-outhb" "<fifo>" "heartbeat fifo to the supervisor"
}

sink_identify_cmdline_opts()
{
    :
}

sink_define_opts()
{
    local optlist=""
    define_opt_from_proc_out "-from_fanin" "fanin" "-outsink" optlist || return 1
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
    document_process "Supervises fanin, loop and sink; relays a manual trigger from outside to fanin."
}

sup_explain_opts()
{
    explain_opt "-hb_fanin" "<fifo>" "fanin's heartbeat fifo"
    explain_opt "-hb_loop" "<fifo>" "loop's heartbeat fifo"
    explain_opt "-hb_sink" "<fifo>" "sink's heartbeat fifo"
    explain_opt "-outtrig_fanin" "<fifo>" "trigger fifo to fanin"
    explain_opt "-manual" "<fifo>" "externally fed manual trigger fifo"
    explain_flag "-no_hold_fifos" "do not hold the fifos of the business channels"
}

sup_identify_cmdline_opts()
{
    opt_is_non_mandatory_cmdline "-no_hold_fifos"
}

sup_define_opts()
{
    local cmdline=$1
    local optlist=""
    define_cmdline_flag_if_given "${cmdline}" "-no_hold_fifos" optlist
    define_opt_from_proc_out "-hb_fanin" "fanin" "-outhb" optlist || return 1
    define_opt_from_proc_out "-hb_loop" "loop" "-outhb" optlist || return 1
    define_opt_from_proc_out "-hb_sink" "sink" "-outhb" optlist || return 1
    define_fifo_opt "-outtrig_fanin" "sup_trig_fanin" optlist --control || return 1
    define_fifo_opt "-manual" "sup_manual" optlist --control || return 1
    save_opt_list optlist
}

sup_heredoc_py()
{
    cat <<'EOF'
from debasher_runtime_lib import Supervisor


class Sup(Supervisor):
    HEARTBEAT_CHECK_INTERVAL_SECS = 0.5
    # Comfortably above HEARTBEAT_INTERVAL_SECONDS (0.2s on every node),
    # not equal to it: a relaunched node's heartbeat thread only sends
    # its first heartbeat after waiting one full interval from
    # start_threads(), on top of its own real startup and replay time,
    # so a timeout with no margin over that interval falsely declares a
    # healthy, freshly relaunched node down again before it ever gets
    # the chance to prove itself (reproduced with a real debasher_exec
    # run: HEARTBEAT_TIMEOUT_SECS == HEARTBEAT_INTERVAL_SECONDS made a
    # perfectly healthy relaunched sink loop through "down, relaunching"
    # until it exceeded MAX_RELAUNCH_ATTEMPTS, and the Supervisor never
    # resolved).
    HEARTBEAT_TIMEOUT_SECS = 3


Sup().run()
EOF
}

########
debasher_chaos_ref_program()
{
    add_debasher_process "fanin" "cpus=1 mem=32 time=00:10:00"
    add_debasher_process "loop" "cpus=1 mem=32 time=00:10:00"
    add_debasher_process "sink" "cpus=1 mem=32 time=00:10:00"
    add_debasher_process "sup" "cpus=1 mem=32 time=00:10:00"
}
