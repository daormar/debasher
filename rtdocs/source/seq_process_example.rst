Sequential Processes Example
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

    # This module shows sequential processes: code that a process runs as a
    # step with seq_execute, instead of being a process that the scheduler
    # launches. The process "calculate" runs two steps, one after another,
    # from its own implementation. The first one, "double", is Python code,
    # which only becomes a function that a step can run because the program
    # declares it with add_debasher_seq_process; its computational
    # specifications are asked from Slurm when the program runs under it.
    # The second one, "add_one", is an alias of "increment", a sequential
    # process written in Bash. The process checks the result itself, so that
    # a step that misbehaves makes it fail.

    #################
    # CFG FUNCTIONS #
    #################

    ########
    debasher_seq_process_example_shared_dirs()
    {
        :
    }

    #####################
    # PROGRAM PROCESSES #
    #####################

    ########
    calculate_document()
    {
        document_process "Computes 2n+1 with two steps: one in Python and one alias of a step in Bash."
    }

    ########
    calculate_explain_opts()
    {
        # -n option
        local description="Number to transform"
        explain_opt "-n" "<int>" "$description"

        # -outd option
        local description="Output directory"
        explain_opt "-outd" "<file>" "$description"
    }

    ########
    calculate_identify_cmdline_opts()
    {
        opt_is_cmdline "-n"
    }

    ########
    calculate_define_opts()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local process_name=$3
        local process_outdir=$4
        local optlist=""

        # -n option
        define_cmdline_opt "$cmdline" "-n" optlist || return 1

        # -outd option
        define_opt "-outd" "${process_outdir}" optlist || return 1

        # Save option list
        save_opt_list optlist
    }

    ########
    calculate()
    {
        # Initialize variables
        local n=$(read_opt_value_from_func_args "-n" "$@")
        local outd=$(read_opt_value_from_func_args "-outd" "$@")

        # First step: double the number, in Python
        seq_execute double "${n}" "${outd}/doubled.txt" || return 1
        local doubled=$(cat "${outd}/doubled.txt")

        # Second step: add one, through an alias of a step in Bash
        seq_execute add_one "${doubled}" "${outd}/result.txt" || return 1
        local result=$(cat "${outd}/result.txt")

        # Check the result
        if [ "${result}" -ne $((2 * n + 1)) ]; then
            echo "Error: expected $((2 * n + 1)) and got ${result}" >&2
            return 1
        fi
        echo "Result: ${result}"
    }

    ########################
    # SEQUENTIAL PROCESSES #
    ########################

    ########
    double_document()
    {
        document_process "Writes twice the number it is given into a file."
    }

    ########
    double_heredoc_py()
    {
        cat <<'EOF'
    import sys
    value = int(sys.argv[1])
    with open(sys.argv[2], 'w') as f:
        f.write(str(2 * value))
    EOF
    }

    ########
    increment_document()
    {
        document_process "Writes the number it is given plus one into a file."
    }

    ########
    increment()
    {
        local value=$1
        local outf=$2

        echo $((value + 1)) > "${outf}"
    }

    #################################
    # PROGRAM DEFINED BY THE MODULE #
    #################################

    ########
    debasher_seq_process_example_program()
    {
        add_debasher_process "calculate" "cpus=1 mem=64 time=00:05:00"
        add_debasher_seq_process "double" "cpus=1 mem=32 time=00:01:00"
        add_debasher_seq_process "increment" ""
        add_debasher_seq_process "add_one" "" "alias=increment"
    }
