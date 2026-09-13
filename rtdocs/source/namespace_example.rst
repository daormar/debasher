Namespace Example
^^^^^^^^^^^^^^^^^^

.. code-block:: bash

    # This module reimplements the hello_world process introduced in
    # the Quickstart guide, but naming it "mymodule.hello_world"
    # instead of plain "hello_world". A process name can optionally
    # be qualified with one or more "namespace.name" prefixes (see the
    # following example for more than one level), where each
    # dot-separated part follows the usual naming rules (it must start
    # with a letter or underscore, followed by letters, digits or
    # underscores). This is recommended for modules meant to be shared
    # with other people, since it prevents the process names they
    # define from colliding with those defined by other DeBasher
    # modules. See the :ref:`process naming <process-naming>` note in
    # the Implementation Section for details.

    mymodule.hello_world_document()
    {
        document_process "Prints a hello world message. The process is \
    named using the 'namespace.name' convention, recommended for modules \
    meant to be shared, so that their process names do not collide with \
    those defined by other DeBasher modules."
    }

    mymodule.hello_world_explain_opts()
    {
        # -s option
        local description="String to be displayed ('Hello World!' by default)"
        explain_opt "-s" "<string>" "$description"
    }

    mymodule.hello_world_identify_cmdline_opts()
    {
        opt_is_non_mandatory_cmdline "-s"
    }

    mymodule.hello_world_define_opts()
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

    mymodule.hello_world()
    {
        # Initialize variables
        local str=$(read_opt_value_from_func_args "-s" "$@")

        if [ "${str}" = "${DEBASHER_OPT_NOT_FOUND}" ]; then
            str="Hello World!"
        fi

        # Show message
        echo "${str}"
    }

    debasher_namespace_example_program()
    {
        add_debasher_process "mymodule.hello_world" "cpus=1 mem=32 time=00:01:00"
    }
