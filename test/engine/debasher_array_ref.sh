# *- bash -*
# Resident-program reference with an array process, for a real
# debasher_exec run: start fans out to the three tasks of worker, and
# collect fans in from them. start is the only initiator (its control port
# is fed from outside), so a round reaches every task of worker through
# the fifos, and collect through the fifos of the tasks. There is no
# Supervisor. It checks that each task keeps its own files next to the
# others' (checkpoints_<idx>, halted_<idx>, ...) and that
# debasher_stop_resident stops every task.

DEBASHER_ARRAY_REF_NUM_WORKERS=3

debasher_array_ref_shared_dirs()
{
    :
}

debasher_array_ref_program_type()
{
    program_type "resident"
}

########
start_document()
{
    document_process "Initiator: fans out to every task of worker; its control port is fed from outside."
}

start_explain_opts()
{
    explain_opt "-trigger" "<fifo>" "externally fed control fifo"
    explain_opt "-outfith" "<fifo>" "output fifo to the i'th task of worker"
}

start_identify_cmdline_opts()
{
    :
}

start_define_opts()
{
    local optlist=""
    define_fifo_opt "-trigger" "start_trigger" optlist || return 1
    local i
    for (( i = 0; i < DEBASHER_ARRAY_REF_NUM_WORKERS; i++ )); do
        define_fifo_opt "-outf${i}" "start_out_${i}" optlist || return 1
    done
    save_opt_list optlist
}

start_heredoc_py()
{
    cat <<'EOF'
from debasher_runtime_lib import FBPProcess


class Start(FBPProcess):
    INPUT_PORTS = ["trigger"]
    CONTROL_PORTS = ["trigger"]
    OUTPUT_PORTS = ["outf0", "outf1", "outf2"]

    def process_data(self, port_name, packet):
        pass

    def capture_node_state(self):
        return {}

    def restore_node_state(self, node_state):
        pass

    def initialize_runtime(self):
        pass


Start().run()
EOF
}

########
worker_document()
{
    document_process "Array of tasks: task i reads the i'th output of start and writes to its own fifo."
}

worker_explain_opts()
{
    explain_opt "-inf" "<fifo>" "input fifo from start"
    explain_opt "-outf" "<fifo>" "output fifo to collect"
}

worker_identify_cmdline_opts()
{
    :
}

worker_define_opts()
{
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4

    local idx
    for (( idx = 0; idx < DEBASHER_ARRAY_REF_NUM_WORKERS; idx++ )); do
        local optlist=""
        define_opt_from_proc_out "-inf" "start" "-outf${idx}" optlist || return 1
        define_fifo_opt "-outf" "worker_out_${idx}" optlist || return 1
        save_opt_list optlist
    done
}

worker_heredoc_py()
{
    cat <<'EOF'
from debasher_runtime_lib import FBPProcess


class Worker(FBPProcess):
    INPUT_PORTS = ["inf"]
    OUTPUT_PORTS = ["outf"]

    def process_data(self, port_name, packet):
        pass

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
    document_process "Fans in from every task of worker."
}

collect_explain_opts()
{
    explain_opt "-indith" "<fifo>" "input fifo from the i'th task of worker"
}

collect_identify_cmdline_opts()
{
    :
}

collect_define_opts()
{
    local optlist=""
    local i
    for (( i = 0; i < DEBASHER_ARRAY_REF_NUM_WORKERS; i++ )); do
        define_opt_from_proc_task_out "-ind${i}" "worker" "${i}" "-outf" optlist || return 1
    done
    save_opt_list optlist
}

collect_heredoc_py()
{
    cat <<'EOF'
from debasher_runtime_lib import FBPProcess


class Collect(FBPProcess):
    INPUT_PORTS = ["ind0", "ind1", "ind2"]

    def process_data(self, port_name, packet):
        pass

    def capture_node_state(self):
        return {}

    def restore_node_state(self, node_state):
        pass

    def initialize_runtime(self):
        pass


Collect().run()
EOF
}

########
debasher_array_ref_program()
{
    add_debasher_process "start" "cpus=1 mem=32 time=00:10:00"
    add_debasher_process "worker" "cpus=1 mem=32 time=00:10:00"
    add_debasher_process "collect" "cpus=1 mem=32 time=00:10:00"
}
