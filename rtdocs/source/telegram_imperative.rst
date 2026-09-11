Telegram Example Using an Imperative Style
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

    # Load modules
    load_debasher_module "debasher_telegram_jobsteps"

    # This variant loads the "debasher_telegram_jobsteps" module, whose
    # decomposer and recomposer processes communicate through a plain
    # file, and abandons the declarative process graph altogether.
    # Instead of declaring decomposer and recomposer as two separate
    # DeBasher processes, a single new process named telegram invokes
    # their bodies directly with seq_execute, one after another, from
    # within one function. This gives the implementation ordinary
    # imperative control flow, such as checking whether decomposer
    # produced any words at all and skipping the call to recomposer
    # entirely when the input file was empty, a branch that would be
    # awkward to express as a dependency between two independently
    # scheduled processes.

    telegram_document()
    {
        debasher::document_process "Telegram Problem."
    }

    telegram_explain_opts()
    {
        # -f option
        local description="File to be processed"
        explain_opt "-f" "<file>" "$description"

        # -c option
        local description="Line length in characters"
        explain_opt "-c" "<int>" "$description"

        # -out-processdir option
        local description="output directory"
        explain_opt "-out-processdir" "<file>" "$description"
    }

    telegram_identify_cmdline_opts()
    {
        opt_is_cmdline "-f"
        opt_is_cmdline "-c"
    }

    telegram_define_opts()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local process_name=$3
        local process_outdir=$4
        local optlist=""

        # Define the -out-processdir option, the output directory for the process
        define_opt "-out-processdir" "${process_outdir}" optlist || return 1

        # -f option
        define_cmdline_opt "$cmdline" "-f" optlist || return 1

        # -c option
        define_cmdline_opt "$cmdline" "-c" optlist || return 1

        # Save option list
        save_opt_list optlist
    }

    telegram()
    {
        # Initialize variables
        local outd=$(read_opt_value_from_func_args "-out-processdir" "$@")
        local file=$(read_opt_value_from_func_args "-f" "$@")
        local char_lim=$(read_opt_value_from_func_args "-c" "$@")

        # Execute decomposer
        seq_execute decomposer -f "${file}" -outf "${outd}"/words.txt || return 1

        # Obtain number of lines of decomposer output
        local nlines=$(wc -l "${outd}"/words.txt | awk '{print $1}')

        if [ "${nlines}" -eq 0 ]; then
            echo "Warning: Decomposer's output is empty" >&2
            echo -n "${outd}"/output.txt || return 1
        else
            # Execute recomposer
            seq_execute recomposer -c "${char_lim}" -inf "${outd}"/words.txt -outf "${outd}"/output.txt || return 1
        fi
    }

    debasher_telegram_imperative_program()
    {
        add_debasher_process "telegram"  "cpus=1 mem=32 time=00:05:00"
    }
