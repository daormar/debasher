# AUTOMATICALLY GENERATED DEBASHER SCRIPT


webui_watch_tally_document()
{
    debasher::document_module "Example built with the web UI: a resident program whose DirectoryWatcher watches the directory given by -watchdir and, for each text file there once it is complete, has a node count the files seen so far and write the count out."
}


webui_watch_tally_shared_dirs()
{
    :
}


webui_watch_tally_program_type()
{
    debasher::program_type "resident"
}


Watch_document()
{
    debasher::document_process "Watches the directory given by -watchdir and sends a request for each text file there, once it is complete."
}


Watch_explain_opts()
{
    debasher::explain_opt "-watchdir" "<string>" "directory to watch, given on the command line"
    debasher::explain_opt "-outrequests" "<string>" "one request for each complete text file"
    debasher::explain_opt "-outhb" "<string>" "heartbeat channel to the Supervisor"
    debasher::explain_opt "-trigger" "<string>" "control port of this initiator"
}


Watch_identify_cmdline_opts()
{
    debasher::opt_is_cmdline "-watchdir"
}


Watch_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    debasher::define_cmdline_opt "${cmdline}" "-watchdir" optlist || return 1
    debasher::define_fifo_opt "-outrequests" "requests" optlist || return 1
    debasher::define_fifo_opt "-outhb" "Watch_hb" optlist || return 1
    debasher::define_opt_from_proc_out "-trigger" "Sup" "-outWatch_trig" optlist || return 1

    save_opt_list optlist
}


Watch_heredoc_py()
{
    cat <<'EOF'
from debasher_runtime_lib import DirectoryWatcher


class Watch(DirectoryWatcher):
    # Only text files count; a file whose name starts with a dot never does.
    PATTERN = "*.txt"


Watch().run()
EOF
}


Tally_document()
{
    debasher::document_process "Counts the files requested so far, and writes the count out with the name of each file."
}


Tally_explain_opts()
{
    debasher::explain_opt "-inrequests" "<string>" "the requests of Watch"
    debasher::explain_opt "-outtally" "<string>" "the name of each file with the number of files seen so far, read outside the program"
    debasher::explain_opt "-outhb" "<string>" "heartbeat channel to the Supervisor"
}


Tally_identify_cmdline_opts()
{
    :
}


Tally_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    debasher::define_opt_from_proc_out "-inrequests" "Watch" "-outrequests" optlist || return 1
    debasher::define_fifo_opt "-outtally" "tally" optlist || return 1
    debasher::define_fifo_opt "-outhb" "Tally_hb" optlist || return 1

    save_opt_list optlist
}


Tally_heredoc_py()
{
    cat <<'EOF'
from debasher_runtime_lib import FBPProcess


class Tally(FBPProcess):
    def __init__(self):
        super().__init__()
        # The node state: how many files have been requested so far.
        self.seen = 0

    def process_data(self, port_name, packet):
        self.seen += 1
        self.send_data("outtally", {"run": packet["run"], "seen": self.seen})

    def capture_node_state(self):
        return {"seen": self.seen}

    def restore_node_state(self, node_state):
        self.seen = node_state["seen"]

    def initialize_runtime(self):
        pass


Tally().run()
EOF
}


Sup_document()
{
    debasher::document_process "Watches Watch and Tally and relaunches them if they go down."
}


Sup_explain_opts()
{
    debasher::explain_opt "-Watch_hb" "<string>" "heartbeat channel of Watch"
    debasher::explain_opt "-outWatch_trig" "<string>" "trigger port to Watch"
    debasher::explain_opt "-Tally_hb" "<string>" "heartbeat channel of Tally"
    debasher::explain_opt "-manual" "<string>" "manual trigger port, written from outside the program"
    debasher::explain_flag "-no-hold-fifos" "do not hold the FIFOs of the business channels"
}


Sup_identify_cmdline_opts()
{
    debasher::opt_is_non_mandatory_cmdline "-no-hold-fifos"
}


Sup_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    debasher::define_opt_from_proc_out "-Watch_hb" "Watch" "-outhb" optlist || return 1
    debasher::define_fifo_opt "-outWatch_trig" "Sup_Watch_trig" optlist --control || return 1
    debasher::define_opt_from_proc_out "-Tally_hb" "Tally" "-outhb" optlist || return 1
    debasher::define_fifo_opt "-manual" "Sup_manual" optlist --control || return 1
    debasher::define_cmdline_flag_if_given "${cmdline}" "-no-hold-fifos" optlist || return 1

    save_opt_list optlist
}


Sup_heredoc_py()
{
    cat <<'EOF'
from debasher_runtime_lib import Supervisor


class Sup(Supervisor):
    pass


Sup().run()
EOF
}


webui_watch_tally_program()
{
    add_debasher_process "Watch" "cpus=1 mem=256 time=01:00:00" ""
    add_debasher_process "Tally" "cpus=1 mem=256 time=01:00:00" ""
    add_debasher_process "Sup" "cpus=1 mem=256 time=01:00:00" ""
}
