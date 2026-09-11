Hello World Alias Example
^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

    # Load modules
    load_debasher_module "debasher_hello_world"

    # This module illustrates the plain "alias" additional spec
    # attribute. It loads debasher_hello_world and declares a new
    # process, hello_world_alternative, whose document, explain_opts,
    # identify_cmdline_opts and define_opts methods duplicate those of
    # hello_world exactly, still using the "-s" option. The
    # alias=hello_world attribute then tells DeBasher to execute
    # hello_world's own implementation for this process instead of
    # requiring a hello_world_alternative function. Since both
    # processes share the same option name, no renaming is needed
    # here: compare it with the alias_opt_map example, where the alias
    # process exposes a different option name and a translation step
    # becomes necessary.

    hello_world_alternative_document()
    {
        document_process "Prints a hello world message."
    }

    hello_world_alternative_explain_opts()
    {
        # -s option
        local description="String to be displayed ('Hello World!' by default)"
        explain_opt "-s" "<string>" "$description"
    }

    hello_world_alternative_identify_cmdline_opts()
    {
        opt_is_non_mandatory_cmdline "-s"
    }

    hello_world_alternative_define_opts()
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

    debasher_hello_world_alias_program()
    {
        add_debasher_process "hello_world_alternative" "cpus=1 mem=32 time=00:01:00" "alias=hello_world"
    }
