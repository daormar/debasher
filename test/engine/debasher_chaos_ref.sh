# *- bash -*
# Chaos test reference program: fanin has two input ports, one external
# (ext, EXTERNAL_PORTS) and one closing a 2-node cycle (loop_in, fed by
# loop). fanin forwards a tagged copy of everything it processes, on either
# port, to sink: sink's own input log is then the exact, deduplicated,
# ordered record of what fanin actually saw, which is what the verifier
# reads after a run. fanin is the sole initiator, triggered by the
# Supervisor's manual trigger channel (fed from outside).

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
    explain_opt "-to_loop" "<fifo>" "output fifo to loop"
    explain_opt "-to_sink" "<fifo>" "output fifo to sink"
    explain_opt "-hb" "<fifo>" "heartbeat fifo to the supervisor"
}

fanin_identify_cmdline_opts()
{
    :
}

fanin_define_opts()
{
    local optlist=""
    define_fifo_opt "-ext" "fanin_ext" optlist || return 1
    define_opt_from_proc_out "-loop_in" "loop" "-to_fanin" optlist || return 1
    define_opt_from_proc_out "-trigger" "sup" "-trig_fanin" optlist || return 1
    define_fifo_opt "-to_loop" "fanin_to_loop" optlist || return 1
    define_fifo_opt "-to_sink" "fanin_to_sink" optlist || return 1
    define_fifo_opt "-hb" "fanin_hb" optlist || return 1
    save_opt_list optlist
}

fanin_heredoc_py()
{
    cat <<'EOF'
from debasher_runtime_lib import FBPProcess


class Fanin(FBPProcess):
    INPUT_PORTS = ["ext", "loop_in", "trigger"]
    OUTPUT_PORTS = ["to_loop", "to_sink", "hb"]
    CONTROL_PORTS = ["trigger"]
    EXTERNAL_PORTS = ["ext"]
    SUPERVISOR_PORT = "hb"
    HEARTBEAT_INTERVAL_SECONDS = 0.2

    def process_data(self, port_name, packet):
        self.send_data("to_sink", {"port": port_name, "value": packet})
        if port_name == "ext":
            self.send_data("to_loop", packet)

    def capture_node_state(self):
        return {}

    def restore_node_state(self, node_state):
        pass

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
    explain_opt "-to_fanin" "<fifo>" "output fifo to fanin"
    explain_opt "-hb" "<fifo>" "heartbeat fifo to the supervisor"
}

loop_identify_cmdline_opts()
{
    :
}

loop_define_opts()
{
    local optlist=""
    define_opt_from_proc_out "-from_fanin" "fanin" "-to_loop" optlist || return 1
    define_fifo_opt "-to_fanin" "loop_to_fanin" optlist || return 1
    define_fifo_opt "-hb" "loop_hb" optlist || return 1
    save_opt_list optlist
}

loop_heredoc_py()
{
    cat <<'EOF'
from debasher_runtime_lib import FBPProcess


class Loop(FBPProcess):
    INPUT_PORTS = ["from_fanin"]
    OUTPUT_PORTS = ["to_fanin", "hb"]
    SUPERVISOR_PORT = "hb"
    HEARTBEAT_INTERVAL_SECONDS = 0.2

    def process_data(self, port_name, packet):
        self.send_data("to_fanin", packet)

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
    explain_opt "-hb" "<fifo>" "heartbeat fifo to the supervisor"
}

sink_identify_cmdline_opts()
{
    :
}

sink_define_opts()
{
    local optlist=""
    define_opt_from_proc_out "-from_fanin" "fanin" "-to_sink" optlist || return 1
    define_fifo_opt "-hb" "sink_hb" optlist || return 1
    save_opt_list optlist
}

sink_heredoc_py()
{
    cat <<'EOF'
from debasher_runtime_lib import FBPProcess


class Sink(FBPProcess):
    INPUT_PORTS = ["from_fanin"]
    OUTPUT_PORTS = ["hb"]
    SUPERVISOR_PORT = "hb"
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
    explain_opt "-trig_fanin" "<fifo>" "trigger fifo to fanin"
    explain_opt "-manual" "<fifo>" "externally fed manual trigger fifo"
}

sup_identify_cmdline_opts()
{
    :
}

sup_define_opts()
{
    local optlist=""
    define_opt_from_proc_out "-hb_fanin" "fanin" "-hb" optlist || return 1
    define_opt_from_proc_out "-hb_loop" "loop" "-hb" optlist || return 1
    define_opt_from_proc_out "-hb_sink" "sink" "-hb" optlist || return 1
    define_fifo_opt "-trig_fanin" "sup_trig_fanin" optlist || return 1
    define_fifo_opt "-manual" "sup_manual" optlist || return 1
    save_opt_list optlist
}

sup_heredoc_py()
{
    cat <<'EOF'
from debasher_runtime_lib import Supervisor


class Sup(Supervisor):
    NODE_PORTS = {"fanin": "hb_fanin", "loop": "hb_loop", "sink": "hb_sink"}
    TRIGGER_PORT = ["trig_fanin"]
    MANUAL_TRIGGER_PORT = "manual"
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
