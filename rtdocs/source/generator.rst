Process Array Example using Generators
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

    array_writer_explain_cmdline_opts()
    {
        # -c option
        local description="Sleep time in seconds"
        explain_cmdline_req_opt "-c" "<int>" "$description"
    }

    array_writer_generate_opts_size()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local process_name=$3
        local process_outdir=$4
        local optlist=""

        echo 4
    }

    array_writer_generate_opts()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local process_name=$3
        local process_outdir=$4
        local task_idx=$5
        local optlist=""

        # -c option
        define_cmdline_opt "$cmdline" "-c" optlist || return 1

        # -id option
        define_opt "-id" $task_idx optlist || return 1

        # -outf option
        define_opt "-outf" "${process_outdir}/${task_idx}" optlist || return 1

        save_opt_list optlist
    }

    array_writer()
    {
        # Initialize variables
        local sleep_time=$(read_opt_value_from_func_args "-c" "$@")
        local id=$(read_opt_value_from_func_args "-id" "$@")
        local outf=$(read_opt_value_from_func_args "-outf" "$@")

        # Sleep some time
        sleep ${sleep_time}

        # Create file
        echo $id > "${outf}"
    }

    array_writer_reset_outfiles()
    {
        # Initialize variables
        local outf=$(read_opt_value_from_func_args "-outf" "$@")

        # Remove output file
        if [ -f "${outf}" ]; then
            rm "${outf}"
        fi
    }

    array_reader_explain_cmdline_opts()
    {
        :
    }

    array_reader_generate_opts_size()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local process_name=$3
        local process_outdir=$4
        local optlist=""

        echo 4
    }

    array_reader_generate_opts()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local process_name=$3
        local process_outdir=$4
        local task_idx=$5
        local optlist=""

        # -id option
        define_opt "-id" $task_idx optlist || return 1

        # -infile option
        define_opt_from_proc_task_out "-infile" "array_writer" "${task_idx}" "-outf" optlist || return 1

        # -outdir option
        define_opt "-outdir" "${process_outdir}" optlist || return 1

        save_opt_list optlist
    }

    array_reader()
    {
        # Initialize variables
        local id=$(read_opt_value_from_func_args "-id" "$@")
        local infile=$(read_opt_value_from_func_args "-infile" "$@")
        local outd=$(read_opt_value_from_func_args "-outdir" "$@")

        # Copy content of infile to auxiliary file
        cat "${infile}" > "${outd}"/${id}_aux

        # Copy content of infile to final file
        cat "${outd}"/${id}_aux > "${outd}"/${id}
    }

    array_reader_post()
    {
        logmsg "Cleaning directory..."

        # Initialize variables
        local id=$(read_opt_value_from_func_args "-id" "$@")
        local outd=$(read_opt_value_from_func_args "-outdir" "$@")

        # Remove auxiliary file
        rm "${outd}"/${id}_aux

        logmsg "Cleaning finished"
    }

    debasher_generator_example_program()
    {
        add_debasher_process "array_writer" "cpus=1 mem=32 time=00:01:00,00:02:00 throttle=2"
        add_debasher_process "array_reader" "cpus=1 mem=32 time=00:01:00 throttle=4"
    }
