Hello World Example in Python
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

    # This module reimplements the hello_world process introduced in
    # the Quickstart guide, but instead of a hello_world Bash function
    # it defines a hello_world_py variable holding a Python script.
    # DeBasher looks up a variable named after the process with a
    # language suffix (here "_py") whenever no matching Bash function
    # is found, and runs its contents through the configured Python
    # interpreter. All the other methods (document, explain_opts,
    # identify_cmdline_opts and define_opts) stay in Bash exactly as
    # before: only the process body itself moves to Python, showing
    # that a process implementation can be written in a different
    # language while its option handling remains in Bash.

    hello_world_document()
    {
        document_process "Prints a hello world message."
    }

    hello_world_explain_opts()
    {
        # -s option
        local description="String to be displayed ('Hello World!' by default)"
        explain_opt "-s" "<string>" "$description"
    }

    hello_world_identify_cmdline_opts()
    {
        opt_is_non_mandatory_cmdline "-s"
    }

    hello_world_define_opts()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local process_name=$3
        local process_outdir=$4
        local optlist=""

        # -s option
        define_cmdline_opt_if_given "${cmdline}" "-s" optlist || return 1

        # Save option list
        save_opt_list optlist
    }

    hello_world_py=$(cat <<'EOF'
    import argparse

    # Create the parser
    parser = argparse.ArgumentParser()

    # Add the "-s" option with a string argument
    parser.add_argument(
        '-s',
        type=str,
        default='Hello World!',
        help='String to be displayed'
    )

    # Parse the arguments
    args = parser.parse_args()

    # Access the value of "-s"
    s = args.s

    # Print message
    print(s)
    EOF
    )

    debasher_hello_world_py_program()
    {
        add_debasher_process "hello_world" "cpus=1 mem=32 time=00:01:00"
    }
