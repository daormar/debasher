FIFO Array Example using Generators
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

    # This module combines the two previous examples: its processes
    # are arrays of tasks created with generators, and each pair of
    # tasks with the same index is connected by a FIFO. A generator
    # cannot call define_fifo_opt, so "producer_generate_opts" uses
    # define_fifo_opt_generator instead, which also takes the index of
    # the task that owns the FIFO. Each task declares its own FIFO,
    # whose name includes the task index so that the names do not
    # clash. On the reading side, "consumer_generate_opts" connects
    # task i to the FIFO of producer task i with
    # define_opt_from_proc_task_out.

    producer_document()
    {
        document_process "Executes an array of n tasks. Each task writes a sequence of numbers to its own FIFO."
    }

    producer_explain_opts()
    {
        # -n option
        local description="Number of tasks"
        explain_opt "-n" "<int>" "$description"

        # -id option
        local description="task id"
        explain_opt "-id" "<int>" "$description"

        # -outf option
        local description="output fifo"
        explain_opt "-outf" "<string>" "$description"
    }

    producer_identify_cmdline_opts()
    {
        opt_is_cmdline "-n"
    }

    producer_generate_opts_size()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local process_name=$3
        local process_outdir=$4

        debasher::read_opt_value_from_line "${cmdline}" "-n"
    }

    producer_generate_opts()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local process_name=$3
        local process_outdir=$4
        local task_idx=$5
        local optlist=""

        # -id option
        define_opt "-id" "${task_idx}" optlist || return 1

        # -outf option (one fifo per task, owned by that task)
        define_fifo_opt_generator "-outf" "producer_fifo_${task_idx}" "${task_idx}" optlist || return 1

        save_opt_list optlist
    }

    producer()
    {
        # Initialize variables
        local id=$(read_opt_value_from_func_args "-id" "$@")
        local outf=$(read_opt_value_from_func_args "-outf" "$@")

        # Write the numbers from 1 to 10*(id+1) to the fifo
        seq 1 $(( 10 * (id + 1) )) > "${outf}"
    }

    consumer_document()
    {
        document_process "Executes an array of n tasks. Each task adds up the numbers read from the FIFO of the producer task with the same index."
    }

    consumer_explain_opts()
    {
        # -n option
        local description="Number of tasks"
        explain_opt "-n" "<int>" "$description"

        # -id option
        local description="task id"
        explain_opt "-id" "<int>" "$description"

        # -inf option
        local description="input fifo"
        explain_opt "-inf" "<string>" "$description"

        # -outf option
        local description="output file"
        explain_opt "-outf" "<file>" "$description"
    }

    consumer_identify_cmdline_opts()
    {
        opt_is_cmdline "-n"
    }

    consumer_generate_opts_size()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local process_name=$3
        local process_outdir=$4

        debasher::read_opt_value_from_line "${cmdline}" "-n"
    }

    consumer_generate_opts()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local process_name=$3
        local process_outdir=$4
        local task_idx=$5
        local optlist=""

        # -id option
        define_opt "-id" "${task_idx}" optlist || return 1

        # -inf option
        define_opt_from_proc_task_out "-inf" "producer" "${task_idx}" "-outf" optlist || return 1

        # -outf option
        define_opt "-outf" "${process_outdir}/${task_idx}" optlist || return 1

        save_opt_list optlist
    }

    consumer()
    {
        # Initialize variables
        local inf=$(read_opt_value_from_func_args "-inf" "$@")
        local outf=$(read_opt_value_from_func_args "-outf" "$@")

        # Add up the numbers read from the fifo
        awk '{ sum += $1 } END { print sum }' < "${inf}" > "${outf}"
    }

    debasher_fifo_generator_example_program()
    {
        add_debasher_process "producer" "cpus=1 mem=32 time=00:01:00"
        add_debasher_process "consumer" "cpus=1 mem=32 time=00:01:00"
    }
