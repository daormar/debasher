FIFO Writer and FIFO Reader Example
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

    fifo_writer_document()
    {
        process_description "Prints a string to a FIFO."
    }

    fifo_writer_explain_cmdline_opts()
    {
        :
    }

    fifo_writer_define_opts()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local process_name=$3
        local process_outdir=$4
        local optlist=""

        # Define option for FIFO
        local fifoname="fifo"
        define_fifo_opt "-outf" "${fifoname}" optlist || return 1

        # Save option list
        save_opt_list optlist
    }

    fifo_writer()
    {
        # Initialize variables
        local outf=$(read_opt_value_from_func_args "-outf" "$@")

        # Write string to FIFO
        echo "Hello World" > "${outf}"
    }

    fifo_reader_document()
    {
        process_description "Reads a string from a FIFO."
    }

    fifo_reader_explain_cmdline_opts()
    {
        :
    }

    fifo_reader_define_opts()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local process_name=$3
        local process_outdir=$4
        local optlist=""

        # Define option for input FIFO
        define_opt_from_proc_out "-inf" "fifo_writer" "-outf" optlist || return 1

        # Save option list
        save_opt_list optlist
    }

    fifo_reader_define_opt_deps()
    {
        # Initialize variables
        local opt=$1
        local producer_process=$2

        case ${opt} in
            "-inf")
                echo "after"
                ;;
            *)
                echo ""
                ;;
        esac
    }

    fifo_reader()
    {
        # Initialize variables
        local inf=$(read_opt_value_from_func_args "-inf" "$@")

        # Read string from FIFO
        cat < "${inf}"
    }

    debasher_fifo_example_program()
    {
        add_debasher_process "fifo_writer" "cpus=1 mem=32 time=00:01:00"
        add_debasher_process "fifo_reader" "cpus=1 mem=32 time=00:01:00"
    }
