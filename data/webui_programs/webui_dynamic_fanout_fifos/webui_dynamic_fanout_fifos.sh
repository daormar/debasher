# AUTOMATICALLY GENERATED DEBASHER SCRIPT


webui_dynamic_fanout_fifos_document()
{
    debasher::document_module "Example built with the web UI: a generated file is counted and cut into fragments, which a dispatcher streams through FIFOs to a pool of workers, and a last process merges their counts."
}


webui_dynamic_fanout_fifos_shared_dirs()
{
    :
}


count_document()
{
    debasher::document_process "Counts characters of an input file in a conventional way. This process is added for debugging purposes."
}


count_explain_opts()
{
    debasher::explain_opt "-inf" "<file>" "input file"
    debasher::explain_opt "-outf" "<file>" "output file"
}


count_identify_cmdline_opts()
{
    :
}


count_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    debasher::define_opt_from_proc_out "-inf" "generate" "-outf" optlist || return 1
    debasher::define_opt "-outf" "${process_outdir}/counts.txt" optlist || return 1

    save_opt_list optlist
}


########
count_chars() {
    local inf="$1"

    awk '
        {
            n = length($0)
            for (i = 1; i <= n; i++) {
                c = substr($0, i, 1)
                count[c]++
            }
        }
        END {
            for (c in count) print c","count[c]
        }
    ' "$inf"
}

########
count()
{
    # Initialize variables
    local inf=$(read_opt_value_from_func_args "-inf" "$@")
    local outf=$(read_opt_value_from_func_args "-outf" "$@")

    # Extract counts
    count_chars "${inf}" | sort > "${outf}"
}


generate_document()
{
    debasher::document_process "Generates a text file of a given size and random content."
}


generate_explain_opts()
{
    debasher::explain_opt "-outf" "<file>" "output file"
    debasher::explain_opt "-l" "<int>" "Length of file in lines"
    debasher::explain_opt "-c" "<int>" "Length of each line in characters"
}


generate_identify_cmdline_opts()
{
    debasher::opt_is_cmdline "-l"
    debasher::opt_is_cmdline "-c"
}


generate_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    debasher::define_opt "-outf" "${process_outdir}/file.txt" optlist || return 1
    debasher::define_cmdline_opt "${cmdline}" "-l" optlist || return 1
    debasher::define_cmdline_opt "${cmdline}" "-c" optlist || return 1

    save_opt_list optlist
}


########
generate()
{
    # Initialize variables
    local numlines=$(read_opt_value_from_func_args "-l" "$@")
    local numchars=$(read_opt_value_from_func_args "-c" "$@")
    local outf=$(read_opt_value_from_func_args "-outf" "$@")

    # Clear/create the output file
    > "$outf"

    local bytes_needed=$(( (numchars * numlines * 3 / 4) + numlines * 4 + 64 ))

    head -c "$bytes_needed" /dev/urandom | base64 | tr -d '\n' | \
        fold -w "$numchars" | head -n "$numlines" > "$outf"
}


fragment_document()
{
    debasher::document_process "Fragments an input file into a given number of equally sized blocks, inverting the file lines."
}


fragment_explain_opts()
{
    debasher::explain_opt "-outd" "<dir>" "name of output directory"
    debasher::explain_opt "-outf" "<file>" "output fifo"
    debasher::explain_opt "-inf" "<file>" "input file"
    debasher::explain_opt "-b" "<int>" "Number of blocks"
}


fragment_identify_cmdline_opts()
{
    debasher::opt_is_cmdline "-b"
}


fragment_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    debasher::define_opt "-outd" "${process_outdir}" optlist || return 1
    debasher::define_fifo_opt "-outf" "fragment_fifo" optlist || return 1
    debasher::define_opt_from_proc_out "-inf" "generate" "-outf" optlist || return 1
    debasher::define_cmdline_opt "${cmdline}" "-b" optlist || return 1

    save_opt_list optlist
}


########
fragment()
{
    # Initialize variables
    local numblocks=$(read_opt_value_from_func_args "-b" "$@")
    local inf=$(read_opt_value_from_func_args "-inf" "$@")
    local outd=$(read_opt_value_from_func_args "-outd" "$@")
    local outf=$(read_opt_value_from_func_args "-outf" "$@")

    # Count the total number of lines in the input file
    local total_lines
    total_lines=$(wc -l < "$inf")

    # Calculate how many lines correspond to each block (rounded up)
    local lines_per_block=$(( (total_lines + numblocks - 1) / numblocks ))

    # Open the output FIFO once, for the whole process
    exec 3> "$outf"

    # Fragment file
    local i start_line end_line count blockfile
    for ((i = 0; i < numblocks; i++)); do
        start_line=$(( i * lines_per_block + 1 ))
        [ "$start_line" -gt "$total_lines" ] && break   # no more lines left

        end_line=$(( start_line + lines_per_block - 1 ))
        [ "$end_line" -gt "$total_lines" ] && end_line="$total_lines"
        count=$(( end_line - start_line + 1 ))

        blockfile="$outd/blk${i}.txt"

        # Extract lines [start_line, end_line] using tail + head,
        # instead of reading and writing line by line in bash.
        tail -n "+$start_line" "$inf" | head -n "$count" > "$blockfile"

        echo "$blockfile" >&3   # announce this block as soon as it's ready
    done

    exec 3>&-
}


aggregate_document()
{
    debasher::document_process "Aggregates worker results."
}


aggregate_explain_opts()
{
    debasher::explain_opt "-outf" "<file>" "output file"
    debasher::explain_opt "-w" "<int>" "Number of workers."
    debasher::explain_opt "-ind-ith" "<dir>" "i'th input directory"
}


aggregate_identify_cmdline_opts()
{
    debasher::opt_is_cmdline "-w"
}


aggregate_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    debasher::define_opt "-outf" "${process_outdir}/result.txt" optlist || return 1
    debasher::define_cmdline_opt "${cmdline}" "-w" optlist || return 1
    local w=$(debasher::read_opt_value_from_line "${cmdline}" "-w")
    for ((i=0; i<w; i++)); do
        debasher::define_opt_from_proc_task_out "-ind${i}" "worker" "${i}" "-outd" optlist || return 1
    done

    save_opt_list optlist
}


########
merge_counts() {
    local count_files=("$@")

    awk -F',' '
        {
            total[$1] += $2
        }
        END {
            for (c in total) print c","total[c]
        }
    ' "${count_files[@]}"
}

########
aggregate()
{
    # Initialize variables
    local outf=$(read_opt_value_from_func_args "-outf" "$@")
    local w=$(read_opt_value_from_func_args "-w" "$@")
    local dirs=()
    for ((i=0; i<w; i++)); do
        dirs+=($(read_opt_value_from_func_args "-ind$i" "$@"))
    done

    # Clear/create the output file
    > "$outf"

    # Collect all count files (blk${i}.txt.counts, or whatever naming
    # convention the workers used) across all directories. Order doesn't
    # matter here since aggregation is a sum, not a concatenation.
    local count_files=()
    local d f
    for d in "${dirs[@]}"; do
        for f in "$d"/blk*.txt; do
            [ -e "$f" ] || continue
            count_files+=("$f")
        done
    done

    if [ "${#count_files[@]}" -eq 0 ]; then
        echo "Warning: no count files found in any directory" >&2
        return 1
    fi

    merge_counts "${count_files[@]}" | sort > "$outf"
}


dispatch_document()
{
    debasher::document_process "Dispatches file blocks to workers."
}


dispatch_explain_opts()
{
    debasher::explain_opt "-outf-ith" "<file>" "i'th output fifo"
    debasher::explain_opt "-w" "<int>" "Number of workers."
    debasher::explain_opt "-inf" "<file>" "input fifo"
    debasher::explain_opt "--log-level" "<string>" "Logging verbosity. Choices: DEBUG, INFO, WARNING, ERROR, CRITICAL (default: INFO)."
}


dispatch_identify_cmdline_opts()
{
    debasher::opt_is_cmdline "-w"
    debasher::opt_is_non_mandatory_cmdline "--log-level"
}


dispatch_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    local w=$(debasher::read_opt_value_from_line "${cmdline}" "-w")
    for ((i=0; i<w; i++)); do
        debasher::define_fifo_opt "-outf${i}" "dispatch_fifo_${i}" optlist || return 1
    done
    debasher::define_cmdline_opt "${cmdline}" "-w" optlist || return 1
    debasher::define_opt_from_proc_out "-inf" "fragment" "-outf" optlist || return 1
    debasher::define_cmdline_opt_if_given "${cmdline}" "--log-level" optlist || return 1

    save_opt_list optlist
}


worker_document()
{
    debasher::document_process "Executes an array of w tasks. Each task takes a list of text files and generates another file for each one."
}


worker_explain_opts()
{
    debasher::explain_opt "-outd" "<dir>" "directory of the task, below the output directory of the process"
    debasher::explain_opt "-inf" "<file>" "input fifo"
}


worker_explain_task_shaping_opts()
{
    debasher::explain_task_shaping_opt "-w" "<int>" "Number of workers."
}


worker_identify_cmdline_opts()
{
    :
}


worker_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4

    local array
    debasher::tasks_from_file array "worker_tasks.py" "${cmdline}" "${process_name}" "${process_outdir}" || return 1

    local task_idx
    for task_idx in "${!array[@]}"; do
        local optlist=""
        debasher::define_opt_from_process_outdir "-outd" optlist --subdir "${task_idx}" || return 1
        debasher::define_opt_from_proc_out "-inf" "dispatch" "-outf${task_idx}" optlist || return 1
        save_opt_list optlist
    done
}


########
count_chars() {
    local inf="$1"

    awk '
        {
            n = length($0)
            for (i = 1; i <= n; i++) {
                c = substr($0, i, 1)
                count[c]++
            }
        }
        END {
            for (c in count) print c","count[c]
        }
    ' "$inf"
}

########
worker_task()
{
    local inf=$1
    local outf=$2

    count_chars "${inf}" > "${outf}"
}

########
worker()
{
    # Initialize variables
    local inf=$(read_opt_value_from_func_args "-inf" "$@")
    local outd=$(read_opt_value_from_func_args "-outd" "$@")

    # Read the input file line by line (each line is a file path)
    while IFS= read -r filepath; do
        [ -z "$filepath" ] && continue
        [ -e "$filepath" ] || continue

        local base
        base=$(basename "$filepath")

        # Execute worker task
        worker_task "$filepath" "$outd/$base" || return 1
    done < "$inf"
}


webui_dynamic_fanout_fifos_program()
{
    add_debasher_process "count" "cpus=1 mem=32 time=00:01:00" ""
    add_debasher_process "generate" "cpus=1 mem=32 time=00:01:00" ""
    add_debasher_process "fragment" "cpus=1 mem=32 time=00:01:00" "processdeps=afterok:count"
    add_debasher_process "aggregate" "cpus=1 mem=32 time=00:01:00" ""
    add_debasher_process "dispatch" "cpus=1 mem=32 time=00:01:00" "ext_alias=./dynamic_fanout_dispatcher.py"
    add_debasher_process "worker" "cpus=1 mem=32 time=00:01:00" ""
}
