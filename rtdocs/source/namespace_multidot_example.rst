Namespace Example With Several Levels
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

    # This module reproduces the same hello_world process as the
    # previous namespace example, but naming it
    # "org.mymodule.hello_world" instead of "mymodule.hello_world".
    # The namespace prefix is not limited to a single level: any
    # number of dot-separated parts is allowed, each one following
    # the usual naming rules. This can be useful to organize process
    # names hierarchically (for instance, an organization name
    # followed by a module name) rather than for uniqueness itself,
    # since a single, sufficiently specific namespace already prevents
    # collisions on its own.

    org.mymodule.hello_world_document()
    {
        document_process "Prints a hello world message. The process is \
    named using more than one dot-separated namespace level \
    ('org.mymodule.name'), showing that the namespace prefix is not \
    limited to a single level."
    }

    org.mymodule.hello_world_explain_opts()
    {
        # -s option
        local description="String to be displayed ('Hello World!' by default)"
        explain_opt "-s" "<string>" "$description"
    }

    org.mymodule.hello_world_identify_cmdline_opts()
    {
        opt_is_non_mandatory_cmdline "-s"
    }

    org.mymodule.hello_world_define_opts()
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

    org.mymodule.hello_world()
    {
        # Initialize variables
        local str=$(read_opt_value_from_func_args "-s" "$@")

        if [ "${str}" = "${DEBASHER_OPT_NOT_FOUND}" ]; then
            str="Hello World!"
        fi

        # Show message
        echo "${str}"
    }

    debasher_namespace_multidot_example_program()
    {
        add_debasher_process "org.mymodule.hello_world" "cpus=1 mem=32 time=00:01:00"
    }
