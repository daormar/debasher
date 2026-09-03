Program with Cycles
^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

    process_a_explain_opts()
    {
        # -n option
        local description="Number of cycles to execute"
        explain_opt "-n" "<int>" "$description"

        # -inf option
        local description="input fifo"
        explain_opt "-inf" "<int>" "$description"

        # -outf option
        local description="output fifo"
        explain_opt "-outf" "<int>" "$description"
    }

    process_a_identify_cmdline_opts()
    {
        opt_is_cmdline "-n"
    }

    process_a_define_opts()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local process_name=$3
        local process_outdir=$4
        local optlist=""

        # -n option
        define_cmdline_opt "$cmdline" "-n" optlist || return 1

        # Define option for output FIFO
        local fifoname="proc_a_fifo"
        define_fifo_opt "-outf" "${fifoname}" optlist || return 1

        # Define option for input FIFO
        define_opt_from_proc_out "-inf" "process_b" "-outf" optlist || return 1

        # Save option list
        save_opt_list optlist
    }

    process_a()
    {
        # Initialize variables
        local n=$(read_opt_value_from_func_args "-n" "$@")
        local inf=$(read_opt_value_from_func_args "-inf" "$@")
        local outf=$(read_opt_value_from_func_args "-outf" "$@")

        # Increase value iteratively until is greater than n
        local value=1
        while [ "${value}" -le "${n}" ]; do
            echo "${value}" > "${outf}"
            echo "Sent value ${value}"
            value=$(cat "${inf}")
            echo "Received value ${value}"
            echo ""
        done

        # Send shutdown token
        echo "${DEBASHER_SHUTDOWN_TOKEN}" > "${outf}"
    }

    process_b_document()
    {
        document_process "Executes a process reading and writing from fifos."
    }

    process_b_explain_opts()
    {
        # -inf option
        local description="input fifo"
        explain_opt "-inf" "<int>" "$description"

        # -outf option
        local description="output fifo"
        explain_opt "-outf" "<int>" "$description"
    }

    process_b_identify_cmdline_opts()
    {
        :
    }

    process_b_define_opts()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local process_name=$3
        local process_outdir=$4
        local optlist=""

        # Define option for output FIFO
        local fifoname="proc_b_fifo"
        define_fifo_opt "-outf" "${fifoname}" optlist || return 1

        # Define option for input FIFO
        define_opt_from_proc_out "-inf" "process_a" "-outf" optlist || return 1

        # Save option list
        save_opt_list optlist
    }

    process_b()
    {
        local inf=$(read_opt_value_from_func_args "-inf" "$@")
        local outf=$(read_opt_value_from_func_args "-outf" "$@")

        # Execute loop until the shutdown token is received
        while true; do
            value=$(cat "${inf}")
            echo "Received value ${value}"
            if [ "${value}" = "${DEBASHER_SHUTDOWN_TOKEN}" ]; then
                break
            fi
            value=$((value + 1))
            echo "Transformed value ${value}"
            echo ""
            echo "${value}" > "${outf}"
        done
    }

    debasher_cycle_program()
    {
        add_debasher_process "process_a" "cpus=1 mem=32 time=00:10:00"
        add_debasher_process "process_b" "cpus=1 mem=32 time=00:10:00"
    }
