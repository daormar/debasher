Option Dependencies Example
^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

    # This module shows how a process changes, with its define_opt_deps
    # method, the type of the dependency that DeBasher infers from one
    # of its options. stream_writer writes into a FIFO that
    # stream_reader reads, and stream_reader copies what it reads into a
    # file that stream_report reads. By default, the FIFO gives no
    # dependency, so that both ends start together, and the file gives
    # an "afterok" dependency, so that the report would only run if the
    # reader succeeded. stream_reader asks instead for an "after"
    # dependency, to be launched once the writer has started, and
    # stream_report for an "afterany" dependency, to run once the reader
    # has ended, whether it succeeded or failed. The method receives the
    # name of the option and the name of the process that produces its
    # value, and prints the type to use, "none" for no dependency, or
    # nothing to keep the inferred type.

    stream_writer_document()
    {
        document_process "Prints a string to a FIFO."
    }

    stream_writer_explain_opts()
    {
        # -outf option
        local description="output fifo"
        explain_opt "-outf" "<string>" "$description"
    }

    stream_writer_identify_cmdline_opts()
    {
        :
    }

    stream_writer_define_opts()
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

    stream_writer()
    {
        # Initialize variables
        local outf=$(read_opt_value_from_func_args "-outf" "$@")

        # Write string to FIFO
        echo "Hello World" > "${outf}"
    }

    stream_reader_document()
    {
        document_process "Reads a string from a FIFO and writes it to a file."
    }

    stream_reader_explain_opts()
    {
        # -inf option
        local description="input fifo"
        explain_opt "-inf" "<string>" "$description"

        # -outf option
        local description="output file"
        explain_opt "-outf" "<file>" "$description"
    }

    stream_reader_identify_cmdline_opts()
    {
        :
    }

    stream_reader_define_opts()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local process_name=$3
        local process_outdir=$4
        local optlist=""

        # Define option for input FIFO
        define_opt_from_proc_out "-inf" "stream_writer" "-outf" optlist || return 1

        # Define option for output file
        local filename="${process_outdir}/received.txt"
        define_opt "-outf" "${filename}" optlist || return 1

        # Save option list
        save_opt_list optlist
    }

    stream_reader_define_opt_deps()
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

    stream_reader()
    {
        # Initialize variables
        local inf=$(read_opt_value_from_func_args "-inf" "$@")
        local outf=$(read_opt_value_from_func_args "-outf" "$@")

        # Copy string from FIFO to file
        cat < "${inf}" > "${outf}"
    }

    stream_report_document()
    {
        document_process "Reports what the reader received, whether it succeeded or failed."
    }

    stream_report_explain_opts()
    {
        # -inf option
        local description="input file"
        explain_opt "-inf" "<file>" "$description"
    }

    stream_report_identify_cmdline_opts()
    {
        :
    }

    stream_report_define_opts()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local process_name=$3
        local process_outdir=$4
        local optlist=""

        # Define option for input file
        define_opt_from_proc_out "-inf" "stream_reader" "-outf" optlist || return 1

        # Save option list
        save_opt_list optlist
    }

    stream_report_define_opt_deps()
    {
        # Initialize variables
        local opt=$1
        local producer_process=$2

        case ${opt} in
            "-inf")
                echo "afterany"
                ;;
            *)
                echo ""
                ;;
        esac
    }

    stream_report()
    {
        # Initialize variables
        local inf=$(read_opt_value_from_func_args "-inf" "$@")

        # Report what the reader received
        if [ -s "${inf}" ]; then
            echo "Received: $(cat "${inf}")"
        else
            echo "Nothing was received"
        fi
    }

    debasher_define_opt_deps_example_program()
    {
        add_debasher_process "stream_writer" "cpus=1 mem=32 time=00:01:00"
        add_debasher_process "stream_reader" "cpus=1 mem=32 time=00:01:00"
        add_debasher_process "stream_report" "cpus=1 mem=32 time=00:01:00"
    }
