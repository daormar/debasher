# *- bash -*
# Resident-program reference for the limit of the outbound backlog, for a
# real debasher_exec run: src forwards every message it gets from outside to
# sink, and its computational specifications give it a small limit
# (out_backlog_fail_mb). With sink frozen, src goes over the limit and fails;
# once relaunched, its replay waits for room until sink reads again. The
# heartbeat timeout of the Supervisor is long enough for sink to stay frozen
# that long without being declared down.

debasher_backlog_ref_shared_dirs()
{
    :
}

debasher_backlog_ref_program_type()
{
    program_type "resident"
}

########
src_document()
{
    document_process "Forwards to sink every message that arrives from outside."
}

src_explain_opts()
{
    explain_opt "-ext" "<fifo>" "externally fed input fifo"
    explain_opt "-trigger" "<fifo>" "externally fed control fifo"
    explain_opt "-outsink" "<fifo>" "fifo to sink"
    explain_opt "-outhb" "<fifo>" "heartbeat fifo to the supervisor"
}

src_identify_cmdline_opts()
{
    :
}

src_define_opts()
{
    local optlist=""
    define_fifo_opt "-ext" "src_ext" optlist --external || return 1
    define_fifo_opt "-trigger" "src_trigger" optlist --control || return 1
    define_fifo_opt "-outsink" "src_sink" optlist || return 1
    define_fifo_opt "-outhb" "src_hb" optlist || return 1
    save_opt_list optlist
}

src_heredoc_py()
{
    cat <<'EOF'
from debasher_runtime_lib import FBPProcess


class Src(FBPProcess):
    HEARTBEAT_INTERVAL_SECONDS = 0.2

    def process_data(self, port_name, packet):
        self.send_data("outsink", packet)

    def capture_node_state(self):
        return {}

    def restore_node_state(self, node_state):
        pass

    def initialize_runtime(self):
        pass


Src().run()
EOF
}

########
sink_document()
{
    document_process "Takes what src sends; its input log holds it."
}

sink_explain_opts()
{
    explain_opt "-insrc" "<fifo>" "fifo from src"
    explain_opt "-outhb" "<fifo>" "heartbeat fifo to the supervisor"
}

sink_identify_cmdline_opts()
{
    :
}

sink_define_opts()
{
    local optlist=""
    define_opt_from_proc_out "-insrc" "src" "-outsink" optlist || return 1
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
    document_process "Supervises src and sink."
}

sup_explain_opts()
{
    explain_opt "-hb_src" "<fifo>" "src's heartbeat fifo"
    explain_opt "-hb_sink" "<fifo>" "sink's heartbeat fifo"
}

sup_identify_cmdline_opts()
{
    :
}

sup_define_opts()
{
    local optlist=""
    define_opt_from_proc_out "-hb_src" "src" "-outhb" optlist || return 1
    define_opt_from_proc_out "-hb_sink" "sink" "-outhb" optlist || return 1
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
debasher_backlog_ref_program()
{
    add_debasher_process "src" "cpus=1; mem=32; time=00:10:00; startup_timeout_s=60; out_backlog_fail_mb=1"
    add_debasher_process "sink" "cpus=1; mem=32; time=00:10:00"
    add_debasher_process "sup" "cpus=1; mem=32; time=00:10:00; heartbeat_timeout_s=20"
}
