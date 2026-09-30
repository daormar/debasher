# AUTOMATICALLY GENERATED DEBASHER SCRIPT


webui_batch_launcher_document()
{
    debasher::document_module "Example built with the web UI: a resident program whose launcher node runs the general program webui_batch_greet once for each request written into its external input, and whose other node reports on each batch run that ends."
}


webui_batch_launcher_shared_dirs()
{
    :
}


webui_batch_launcher_program_type()
{
    debasher::program_type "resident"
}


Sup_document()
{
    debasher::document_process "Watches Launch and Report and relaunches them if they go down."
}


Sup_explain_opts()
{
    debasher::explain_opt "-Launch_hb" "<string>" "heartbeat channel of Launch"
    debasher::explain_opt "-outLaunch_trig" "<string>" "trigger port to Launch"
    debasher::explain_opt "-Report_hb" "<string>" "heartbeat channel of Report"
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

    debasher::define_opt_from_proc_out "-Launch_hb" "Launch" "-outhb" optlist || return 1
    debasher::define_fifo_opt "-outLaunch_trig" "Sup_Launch_trig" optlist --control || return 1
    debasher::define_opt_from_proc_out "-Report_hb" "Report" "-outhb" optlist || return 1
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


Launch_document()
{
    debasher::document_process "Runs webui_batch_greet once for each request, and sends a notice when each batch run ends."
}


Launch_explain_opts()
{
    debasher::explain_opt "-requests" "<string>" "requests written from outside the program, one batch run each: {\"opts\": {\"-text\": ..., \"-secs\": ...}, \"run\": ...}"
    debasher::explain_opt "-outdone" "<string>" "a notice for each batch run that ends"
    debasher::explain_opt "-outhb" "<string>" "heartbeat channel to the Supervisor"
    debasher::explain_opt "-trigger" "<string>" "control port of this initiator"
}


Launch_identify_cmdline_opts()
{
    :
}


Launch_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    debasher::define_fifo_opt "-requests" "requests" optlist --external || return 1
    debasher::define_fifo_opt "-outdone" "done" optlist || return 1
    debasher::define_fifo_opt "-outhb" "Launch_hb" optlist || return 1
    debasher::define_opt_from_proc_out "-trigger" "Sup" "-outLaunch_trig" optlist || return 1

    save_opt_list optlist
}


Launch_heredoc_py()
{
    cat <<'EOF'
from debasher_runtime_lib import ProgramLauncher


class Launch(ProgramLauncher):
    # The general program to run, next to this program's home directory.
    PFILE = "../webui_batch_greet/webui_batch_greet.sh"


Launch().run()
EOF
}


Report_document()
{
    debasher::document_process "Counts the batch runs that finish and those that fail, reports each end, and leaves a warning notice while some batch run has failed."
}


Report_explain_opts()
{
    debasher::explain_opt "-done" "<string>" "the notices of the batch runs that end"
    debasher::explain_opt "-outreport" "<string>" "one line for each batch run that ends, with how many finished and failed so far, read outside the program"
    debasher::explain_opt "-outhb" "<string>" "heartbeat channel to the Supervisor"
}


Report_identify_cmdline_opts()
{
    :
}


Report_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    debasher::define_opt_from_proc_out "-done" "Launch" "-outdone" optlist || return 1
    debasher::define_fifo_opt "-outreport" "report" optlist || return 1
    debasher::define_fifo_opt "-outhb" "Report_hb" optlist || return 1

    save_opt_list optlist
}


Report_heredoc_py()
{
    cat <<'EOF'
from debasher_runtime_lib import FBPProcess


class Report(FBPProcess):
    def __init__(self):
        super().__init__()
        # The node state: how many batch runs finished and failed.
        self.counts = {"finished": 0, "failed": 0}

    def report_failures(self):
        # A notice for whoever watches the program while some batch run has failed.
        if self.counts.get("failed"):
            self.set_notice(f"{self.counts['failed']} batch run(s) failed", level="warning")

    def process_data(self, port_name, packet):
        status = packet["status"]
        self.counts[status] = self.counts.get(status, 0) + 1
        self.send_data("outreport", {"run": packet["run"], "status": status, **self.counts})
        self.report_failures()

    def capture_node_state(self):
        return dict(self.counts)

    def restore_node_state(self, node_state):
        self.counts = dict(node_state)
        # The notice is not part of the node state: it is set again from it.
        self.report_failures()

    def initialize_runtime(self):
        pass


Report().run()
EOF
}


webui_batch_launcher_program()
{
    add_debasher_process "Sup" "cpus=1 mem=256 time=01:00:00" ""
    add_debasher_process "Launch" "cpus=1 mem=256 time=01:00:00" ""
    add_debasher_process "Report" "cpus=1 mem=256 time=01:00:00" ""
}
