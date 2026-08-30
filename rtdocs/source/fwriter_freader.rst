File Writer and File Reader Example
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

    file_writer_document()
    {
        document_process "Prints a string to a file."
    }

    file_writer_explain_opts()
    {
        # -s option
        local description="String to be displayed"
        explain_opt "-s" "<string>" "$description"

        # -outf option
        local description="output file"
        explain_opt "-outf" "<string>" "$description"
    }

    file_writer_identify_cmdline_opts()
    {
        opt_is_cmdline "-s"
    }

    file_writer_define_opts()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local process_name=$3
        local process_outdir=$4
        local optlist=""

        # Define option for output file
        local filename="${process_outdir}/out.txt"
        define_opt "-outf" "${filename}" optlist || return 1

        # Save option list
        save_opt_list optlist
    }

    file_writer()
    {
        # Initialize variables
        local str=$(read_opt_value_from_func_args "-s" "$@")
        local outf=$(read_opt_value_from_func_args "-outf" "$@")

        # Write string to file
        echo "${str}" > "${outf}"
    }

    file_reader_document()
    {
        document_process "Reads a string from a file."
    }

    file_reader_explain_opts()
    {
        # -inf option
        local description="input file"
        explain_opt "-inf" "<string>" "$description"
    }

    file_reader_identify_cmdline_opts()
    {
        :
    }

    file_reader_define_opts()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local process_name=$3
        local process_outdir=$4
        local optlist=""

        # Define option for input file
        define_opt_from_proc_out "-inf" "file_writer" "-outf" optlist || return 1

        # Save option list
        save_opt_list optlist
    }

    file_reader()
    {
        # Initialize variables
        local inf=$(read_opt_value_from_func_args "-inf" "$@")

        # Read string from file
        cat < "${inf}"
    }

    debasher_file_example_program()
    {
        add_debasher_process "file_writer" "cpus=1 mem=32 time=00:01:00"
        add_debasher_process "file_reader" "cpus=1 mem=32 time=00:01:00"
    }
