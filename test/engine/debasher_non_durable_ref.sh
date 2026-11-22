# *- bash -*
# Reference program of the non-durable mode (see "The non-durable mode" in
# doc/design_doc_resident.md): count reads an external port, ext, counts
# what it receives in memory, with no hooks of the state, and sends sink a
# copy of each message with its count; sink appends each copy to a file of
# its own output directory, trace.jsonl, since a non-durable node keeps no
# input log that a test could read as the trace. A relaunch of count
# starts its count again from 1, which the trace shows. sup supervises
# both and has a manual trigger port, which it drops every trigger of. Its
# class has no body of its own, so that the web UI can import the program.

debasher_non_durable_ref_shared_dirs()
{
    :
}

debasher_non_durable_ref_program_type()
{
    program_type "resident" "non-durable"
}

########
count_document()
{
    document_process "Counts what arrives on ext, in memory, and forwards each message with its count to sink."
}

count_explain_opts()
{
    explain_opt "-ext" "<fifo>" "externally fed input fifo"
    explain_opt "-trigger" "<fifo>" "control fifo from the supervisor"
    explain_opt "-outsink" "<fifo>" "output fifo to sink"
    explain_opt "-outhb" "<fifo>" "heartbeat fifo to the supervisor"
}

count_identify_cmdline_opts()
{
    :
}

count_define_opts()
{
    local optlist=""
    define_fifo_opt "-ext" "count_ext" optlist --external || return 1
    define_opt_from_proc_out "-trigger" "sup" "-outtrig_count" optlist || return 1
    define_fifo_opt "-outsink" "count_to_sink" optlist || return 1
    define_fifo_opt "-outhb" "count_hb" optlist || return 1
    save_opt_list optlist
}

count_heredoc_py()
{
    cat <<'EOF'
from debasher_runtime_lib import FBPProcess


class Count(FBPProcess):
    HEARTBEAT_INTERVAL_SECS = 0.2

    def __init__(self):
        super().__init__()
        # In memory only: a non-durable node writes no hook of the state,
        # and a relaunch starts again from 0
        self.count = 0

    def process_data(self, port_name, packet):
        self.count += 1
        self.send_data("outsink", {"value": packet, "count": self.count})

    def initialize_runtime(self):
        pass


Count().run()
EOF
}

########
sink_document()
{
    document_process "Appends every message it receives to trace.jsonl in its output directory."
}

sink_explain_opts()
{
    explain_opt "-from_count" "<fifo>" "input fifo from count"
    explain_opt "-outhb" "<fifo>" "heartbeat fifo to the supervisor"
}

sink_identify_cmdline_opts()
{
    :
}

sink_define_opts()
{
    local optlist=""
    define_opt_from_proc_out "-from_count" "count" "-outsink" optlist || return 1
    define_fifo_opt "-outhb" "sink_hb" optlist || return 1
    save_opt_list optlist
}

sink_heredoc_py()
{
    cat <<'EOF'
import json
import os

from debasher_runtime_lib import FBPProcess


class Sink(FBPProcess):
    HEARTBEAT_INTERVAL_SECS = 0.2

    def process_data(self, port_name, packet):
        # The trace of the run, in the output directory of the process,
        # which the engine keeps across launches of the node
        with open(os.path.join(os.environ["DEBASHER_PROCESS_OUTDIR"], "trace.jsonl"), "a") as f:
            f.write(json.dumps(packet) + "\n")
            f.flush()

    def initialize_runtime(self):
        pass


Sink().run()
EOF
}

########
sup_document()
{
    document_process "Supervises count and sink; drops the triggers of its manual trigger port, since the program is non-durable."
}

sup_explain_opts()
{
    explain_opt "-hb_count" "<fifo>" "count's heartbeat fifo"
    explain_opt "-hb_sink" "<fifo>" "sink's heartbeat fifo"
    explain_opt "-outtrig_count" "<fifo>" "trigger fifo to count"
    explain_opt "-manual" "<fifo>" "externally fed manual trigger fifo"
}

sup_identify_cmdline_opts()
{
    :
}

sup_define_opts()
{
    local optlist=""
    define_opt_from_proc_out "-hb_count" "count" "-outhb" optlist || return 1
    define_opt_from_proc_out "-hb_sink" "sink" "-outhb" optlist || return 1
    define_fifo_opt "-outtrig_count" "sup_trig_count" optlist --control || return 1
    define_fifo_opt "-manual" "sup_manual" optlist --control || return 1
    save_opt_list optlist
}

sup_heredoc_py()
{
    cat <<'EOF'
from debasher_runtime_lib import Supervisor


class Sup(Supervisor):
    pass


Sup().run()
EOF
}

########
debasher_non_durable_ref_program()
{
    add_debasher_process "count" "cpus=1 mem=32 time=00:10:00"
    add_debasher_process "sink" "cpus=1 mem=32 time=00:10:00"
    add_debasher_process "sup" "cpus=1 mem=32 time=00:10:00"
}
