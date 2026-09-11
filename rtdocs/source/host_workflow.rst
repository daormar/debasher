Host Workflow Example
^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

    # This module runs two arrays of tasks that report which host they
    # executed on, useful for checking how tasks are distributed across
    # machines when using a real cluster scheduler such as SLURM
    # instead of the builtin one. host1 uses the generator method to
    # create "-n" tasks, each printing its own hostname to standard
    # output and to a file. host2 also uses the generator method to
    # create the same number of tasks, each reading the matching host1
    # task's output through define_opt_from_proc_task_out and printing
    # the hostname again. The following two examples build on this same
    # host1 and host2 pair to change how their tasks are scheduled
    # relative to each other.

    host1_document()
    {
        document_process "Executes an array of n tasks. Each task creates a file containing host name."
    }

    host1_explain_opts()
    {
        # -n option
        local description="Number of array tasks"
        explain_opt "-n" "<int>" "$description"

        # -id option
        local description="process id"
        explain_opt "-id" "<int>" "$description"

        # -outf option
        local description="output file"
        explain_opt "-outf" "<file>" "$description"
    }

    host1_identify_cmdline_opts()
    {
        opt_is_cmdline "-n"
    }

    host1_generate_opts_size()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local process_name=$3
        local process_outdir=$4

        # -n option
        local n_opt=$(get_cmdline_opt "$cmdline" "-n")

        echo ${n_opt}
    }

    host1_generate_opts()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local process_name=$3
        local process_outdir=$4
        local task_idx=$5
        local optlist=""

        # -id option
        define_opt "-id" ${task_idx} optlist || return 1

        # -outf option
        define_opt "-outf" "${process_outdir}/outf_${task_idx}" optlist || return 1

        # Save option list
        save_opt_list optlist
    }

    host1()
    {
        # Initialize variables
        local id=$(read_opt_value_from_func_args "-id" "$@")
        local outf=$(read_opt_value_from_func_args "-outf" "$@")

        # Show host name
        local hname=$(hostname)
        echo "${id}: ${hname}"

        # Create file
        echo "${id}" > "${outf}"
    }

    host2_document()
    {
        document_process "Executes an array of tasks, one per host1 task, printing the host name for each."
    }

    host2_explain_opts()
    {
        # -n option
        local description="Number of array tasks"
        explain_opt "-n" "<int>" "$description"
    }

    host2_identify_cmdline_opts()
    {
        opt_is_cmdline "-n"
    }

    host2_generate_opts_size()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local process_name=$3
        local process_outdir=$4

        # -n option
        local n_opt=$(get_cmdline_opt "$cmdline" "-n")

        echo "${n_opt}"
    }

    host2_generate_opts()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local process_name=$3
        local process_outdir=$4
        local task_idx=$5
        local optlist=""

        # -id option
        define_opt "-id" ${task_idx} optlist || return 1

        # -inf option
        define_opt_from_proc_task_out "-inf" "host1" "${task_idx}" "-outf" optlist || return 1

        # Save option list
        save_opt_list optlist
    }

    host2()
    {
        # Initialize variables
        local id=$(read_opt_value_from_func_args "-id" "$@")
        local inf=$(read_opt_value_from_func_args "-inf" "$@")

        # Show host name
        local hname=$(hostname)
        echo "${id}: ${hname}"
    }

    debasher_host_workflow_program()
    {
        add_debasher_process "host1" "cpus=1 mem=32 time=00:10:00 throttle=64"
        add_debasher_process "host2" "cpus=1 mem=32 time=00:10:00 throttle=64"
    }
