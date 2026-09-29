# AUTOMATICALLY GENERATED DEBASHER SCRIPT


webui_running_sum_document()
{
    debasher::document_module "Example built with the web UI: a resident program whose node keeps the running sum of the numbers written into its external input, and writes each new sum out."
}


webui_running_sum_shared_dirs()
{
    :
}


webui_running_sum_program_type()
{
    debasher::program_type "resident"
}


Accumulate_document()
{
    debasher::document_process "Keeps the running sum of the numbers it receives, and sends each new sum out."
}


Accumulate_explain_opts()
{
    debasher::explain_opt "-numbers" "<string>" "numbers written from outside the program, one per message"
    debasher::explain_opt "-outsum" "<string>" "the running sum after each number, read outside the program"
    debasher::explain_opt "-outhb" "<string>" "heartbeat channel to the Supervisor"
    debasher::explain_opt "-trigger" "<string>" "control port of this initiator"
}


Accumulate_identify_cmdline_opts()
{
    :
}


Accumulate_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    debasher::define_fifo_opt "-numbers" "numbers" optlist --external || return 1
    debasher::define_fifo_opt "-outsum" "sum" optlist || return 1
    debasher::define_fifo_opt "-outhb" "Accumulate_hb" optlist || return 1
    debasher::define_opt_from_proc_out "-trigger" "Sup" "-outAccumulate_trig" optlist || return 1

    save_opt_list optlist
}


Accumulate_heredoc_py()
{
    cat <<'EOF'
from debasher_runtime_lib import FBPProcess


class Accumulate(FBPProcess):
    def __init__(self):
        super().__init__()
        # The node state: the sum of every number received so far.
        self.total = 0

    def process_data(self, port_name, packet):
        self.total += packet
        self.send_data("outsum", self.total)

    def capture_node_state(self):
        return {"total": self.total}

    def restore_node_state(self, node_state):
        self.total = node_state["total"]

    def initialize_runtime(self):
        pass


Accumulate().run()
EOF
}


Sup_document()
{
    debasher::document_process "Watches Accumulate and relaunches it if it goes down."
}


Sup_explain_opts()
{
    debasher::explain_opt "-Accumulate_hb" "<string>" "heartbeat channel of Accumulate"
    debasher::explain_opt "-outAccumulate_trig" "<string>" "trigger port to Accumulate"
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

    debasher::define_opt_from_proc_out "-Accumulate_hb" "Accumulate" "-outhb" optlist || return 1
    debasher::define_fifo_opt "-outAccumulate_trig" "Sup_Accumulate_trig" optlist --control || return 1
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


webui_running_sum_program()
{
    add_debasher_process "Accumulate" "cpus=1 mem=256 time=01:00:00" ""
    add_debasher_process "Sup" "cpus=1 mem=256 time=01:00:00" ""
}
