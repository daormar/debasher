Telegram Example
^^^^^^^^^^^^^^^^

.. code-block:: bash

    # The "telegram problem" splits an input file into words and then
    # regroups those words into lines whose length never exceeds a
    # given character limit. This baseline solution uses two DeBasher
    # processes connected through a FIFO: "decomposer" reads the input
    # file with awk and writes one word per line into the FIFO, while
    # "recomposer" reads from that FIFO and greedily packs the words
    # into fixed width lines once the accumulated length would exceed
    # the limit. Since both processes are wired through a FIFO instead
    # of a plain file, they run concurrently: recomposer starts
    # consuming words as soon as decomposer produces them, without
    # waiting for the whole file to be split first.

    decomposer_document()
    {
        debasher::document_process "Telegram Problem Decomposer module."
    }

    decomposer_explain_opts()
    {
        # -f option
        local description="File to be processed"
        explain_opt "-f" "<file>" "$description"

        # -outf option
        local description="output fifo"
        explain_opt "-outf" "<string>" "$description"
    }

    decomposer_identify_cmdline_opts()
    {
        opt_is_cmdline "-f"
    }

    decomposer_define_opts()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local process_name=$3
        local process_outdir=$4
        local optlist=""

        # Define option for decomposer FIFO
        local fifoname="dc_fifo"
        define_fifo_opt "-outf" "${fifoname}" optlist || return 1

        # -f option
        define_cmdline_opt "$cmdline" "-f" optlist || return 1

        # Save option list
        save_opt_list optlist
    }

    decomposer()
    {
        # Initialize variables
        local outf=$(read_opt_value_from_func_args "-outf" "$@")
        local file=$(read_opt_value_from_func_args "-f" "$@")

        # Decompose input
        awk '{for(i=1;i<=NF;++i) print $i}' "${file}" > "${outf}" || return 1
    }

    recomposer_document()
    {
        debasher::document_process "Telegram Problem Recomposer module."
    }

    recomposer_explain_opts()
    {
        # -c option
        local description="Line length in characters"
        explain_opt "-c" "<int>" "$description"

        # -inf option
        local description="input fifo"
        explain_opt "-inf" "<string>" "$description"

        # -outf option
        local description="output file"
        explain_opt "-outf" "<file>" "$description"
    }

    recomposer_identify_cmdline_opts()
    {
        opt_is_cmdline "-c"
    }

    recomposer_define_opts()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local process_name=$3
        local process_outdir=$4
        local optlist=""

        # Define name of output file
        local outf="${process_outdir}/output.txt"
        define_opt "-outf" "${outf}" optlist || return 1

        # -c option
        define_cmdline_opt "$cmdline" "-c" optlist || return 1

        # Define option for decomposer FIFO
        define_opt_from_proc_out "-inf" "decomposer" "-outf" optlist || return 1

        # Save option list
        save_opt_list optlist
    }

    recompose()
    {
        local char_lim=$1
        local file=$2

        awk -v char_lim="${char_lim}" 'BEGIN{len=0}
                 {
                  if(len + length($0) <= char_lim)
                  {
                    if(len > 0) printf" "
                    printf"%s", $0
                    len = len + length($0)
                  }
                  else
                  {
                    printf"\n%s",$0
                    len = length($0)
                  }
                  if(len+1 <= char_lim)
                   len = len + 1
                 }' "${file}"
    }

    recomposer()
    {
        # Initialize variables
        local outf=$(read_opt_value_from_func_args "-outf" "$@")
        local char_lim=$(read_opt_value_from_func_args "-c" "$@")
        local inf=$(read_opt_value_from_func_args "-inf" "$@")

        # Recompose input
        recompose "${char_lim}" "${inf}" > "${outf}" || return 1
    }

    debasher_telegram_program()
    {
        add_debasher_process "decomposer" "cpus=1 mem=32 time=00:05:00"
        add_debasher_process "recomposer" "cpus=1 mem=32 time=00:05:00"
    }
