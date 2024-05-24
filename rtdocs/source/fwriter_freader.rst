File Writer and File Reader Example
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

    file_writer_document()
    {
        process_description "Prints a string to a file."
    }

    file_writer_explain_cmdline_opts()
    {
        :
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
        local outf=$(read_opt_value_from_func_args "-outf" "$@")

        # Write string to file
        echo "Hello World" > "${outf}"
    }

    file_reader_document()
    {
        process_description "Reads a string from a file."
    }

    file_reader_explain_cmdline_opts()
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
