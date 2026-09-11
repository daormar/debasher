Hello World External Alias Example
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

    # This module shows the "ext_alias" additional spec attribute,
    # which delegates a process's execution to an external script file
    # rather than to another DeBasher process or an embedded language
    # variable. The document, explain_opts, identify_cmdline_opts and
    # define_opts methods for hello_world are defined here exactly as
    # in the Quickstart guide, still reading the "-s" option, but no
    # hello_world Bash function is provided. Instead,
    # ext_alias=./hello_world.py points DeBasher to a standalone Python
    # file (see data/programs/hello_world.py) that parses "-s" on its
    # own and prints the greeting. Contrast this with
    # debasher_hello_world_py.sh, where the Python source lives inline
    # in a hello_world_py variable instead of a separate file.

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

    debasher_hello_world_ext_alias_program()
    {
        add_debasher_process "hello_world" "cpus=1 mem=32 time=00:01:00" "ext_alias=./hello_world.py"
    }
