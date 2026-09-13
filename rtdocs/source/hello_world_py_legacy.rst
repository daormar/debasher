Hello World Example in Python (Legacy)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

    # This module reimplements the hello_world process introduced in
    # the Quickstart guide, but instead of a hello_world Bash function
    # it defines a hello_world_py variable holding a Python script.
    # DeBasher looks up a variable named after the process with a
    # language suffix (here "_py") whenever no matching Bash function
    # is found, and runs its contents through the configured Python
    # interpreter.
    #
    # This variable-based form is kept for backwards compatibility
    # (it is, for instance, the form shown in the supplementary
    # material of the DeBasher paper), but it cannot be used with a
    # namespaced process name, since a variable name cannot contain
    # the "." namespace separator. See the following example for the
    # function-based form, which supports namespaced process names and
    # is otherwise equivalent.

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

    debasher_hello_world_py_legacy_program()
    {
        add_debasher_process "hello_world" "cpus=1 mem=32 time=00:01:00"
    }
