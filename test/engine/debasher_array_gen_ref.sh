# *- bash -*
# The same resident program as debasher_array_ref.sh, except that worker
# produces the options of its tasks with an option generator
# (worker_generate_opts_size and worker_generate_opts) instead of defining
# them in a loop: the rest of the engine only needs to know how many tasks
# there are, so everything else behaves the same.

DEBASHER_ARRAY_GEN_REF_NUM_WORKERS=3

debasher_array_gen_ref_shared_dirs()
{
    :
}

debasher_array_gen_ref_program_type()
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
    define_fifo_opt "-trigger" "start_trigger" optlist --control || return 1
    local i
    for (( i = 0; i < DEBASHER_ARRAY_GEN_REF_NUM_WORKERS; i++ )); do
        define_fifo_opt "-outf${i}" "start_out_${i}" optlist || return 1
    done
    save_opt_list optlist
}

start_heredoc_py()
{
    cat <<'EOF'
from debasher_runtime_lib import FBPProcess


class Start(FBPProcess):
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

worker_generate_opts_size()
{
    echo "${DEBASHER_ARRAY_GEN_REF_NUM_WORKERS}"
}

worker_generate_opts()
{
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local task_idx=$5
    local optlist=""

    define_opt_from_proc_out "-inf" "start" "-outf${task_idx}" optlist || return 1
    define_fifo_opt_generator "-outf" "worker_out_${task_idx}" "${task_idx}" optlist || return 1
    save_opt_list optlist
}

worker_heredoc_py()
{
    cat <<'EOF'
from debasher_runtime_lib import FBPProcess


class Worker(FBPProcess):
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
    for (( i = 0; i < DEBASHER_ARRAY_GEN_REF_NUM_WORKERS; i++ )); do
        define_opt_from_proc_task_out "-ind${i}" "worker" "${i}" "-outf" optlist || return 1
    done
    save_opt_list optlist
}

collect_heredoc_py()
{
    cat <<'EOF'
from debasher_runtime_lib import FBPProcess


class Collect(FBPProcess):
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
debasher_array_gen_ref_program()
{
    add_debasher_process "start" "cpus=1 mem=32 time=00:10:00"
    add_debasher_process "worker" "cpus=1 mem=32 time=00:10:00"
    add_debasher_process "collect" "cpus=1 mem=32 time=00:10:00"
}
