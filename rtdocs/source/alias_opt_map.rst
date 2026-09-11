Alias Option Map Example
^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

    # Load modules
    load_debasher_module "debasher_hello_world"

    # This process is an alias of "hello_world" (see
    # data/programs/debasher_hello_world.sh), whose implementation reads
    # its greeting string from a "-s" option. Here the process is meant to
    # expose a more descriptive "-msg" option on the command line instead
    # of "-s". Since the two option names never coexist within one
    # program, a plain alias (see debasher_hello_world_alias.sh) cannot
    # reconcile them: whatever _define_opts puts into the optlist under
    # "-msg" would reach "hello_world"'s implementation as "-msg", not
    # the "-s" it actually reads.
    #
    # The "alias_opt_map" additional spec attribute solves exactly this:
    # it renames "-msg" into "-s" right before delegating to "hello_world",
    # while _explain_opts/_identify_cmdline_opts/_define_opts below keep
    # using "-msg" throughout, as if no renaming were involved at all.

    hello_world_msg_document()
    {
        document_process "Prints a hello world message, illustrating the alias_opt_map additional spec attribute."
    }

    hello_world_msg_explain_opts()
    {
        # -msg option
        local description="String to be displayed ('Hello World!' by default)"
        explain_opt "-msg" "<string>" "$description"
    }

    hello_world_msg_identify_cmdline_opts()
    {
        opt_is_non_mandatory_cmdline "-msg"
    }

    hello_world_msg_define_opts()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local process_name=$3
        local process_outdir=$4
        local optlist=""

        # -msg option
        define_cmdline_opt_if_given "${cmdline}" "-msg" optlist || return 1

        # Save option list
        save_opt_list optlist
    }

    debasher_hello_world_alias_opt_map_program()
    {
        add_debasher_process "hello_world_msg" "cpus=1 mem=32 time=00:01:00" "alias=hello_world;alias_opt_map=-msg:-s"
    }
