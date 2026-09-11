Telegram Example Using Job Steps
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

    # Load modules
    load_debasher_module "debasher_telegram"

    # This variant loads the base "debasher_telegram" module and keeps
    # its two processes, decomposer and recomposer, but overrides both
    # _define_opts functions so decomposer writes its word list to a
    # plain intermediate file instead of the FIFO used in the
    # baseline. Since a regular file has no blocking semantics,
    # recomposer can only start reading once decomposer has finished
    # writing the whole file, turning the concurrent streamed pipeline
    # into two sequential steps that exchange a complete file between
    # them. This illustrates how a program can reuse a module's
    # processes while changing only how their options connect them,
    # without touching the process bodies themselves.

    decomposer_define_opts()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local process_name=$3
        local process_outdir=$4
        local optlist=""

        # -f option
        define_cmdline_opt "$cmdline" "-f" optlist || return 1

        # Define name of output file
        local outf="${process_outdir}/words.txt"
        define_opt "-outf" "${outf}" optlist || return 1

        # Save option list
        save_opt_list optlist
    }

    recomposer_define_opts()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local process_name=$3
        local process_outdir=$4
        local optlist=""

        # -c option
        define_cmdline_opt "$cmdline" "-c" optlist || return 1

        # -inf option
        define_opt_from_proc_out "-inf" "decomposer" "-outf" optlist || return 1

        # Define name of output file
        local outf="${process_outdir}/output.txt"
        define_opt "-outf" "${outf}" optlist || return 1

        # Save option list
        save_opt_list optlist
    }

    debasher_telegram_jobsteps_program()
    {
        add_debasher_program "debasher_telegram"
    }
