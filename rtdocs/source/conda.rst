Conda Example
^^^^^^^^^^^^^

.. code-block:: bash

    conda_example_document()
    {
        document_process "Prints Python version to file \`python_ver.txt\`."
    }

    conda_example_explain_opts()
    {
        # -outf option
        local description="output file"
        explain_opt "-outf" "<file>" "$description"
    }

    conda_example_identify_cmdline_opts()
    {
        :
    }

    conda_example_define_opts()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local process_name=$3
        local process_outdir=$4
        local optlist=""

        # Define name of output file
        define_opt "-outf" "${process_outdir}/python_ver.txt" optlist || return 1

        # Save option list
        save_opt_list optlist
    }

    conda_example()
    {
        # Initialize variables
        local outf=$(read_opt_value_from_func_args "-outf" "$@")

        # Activate conda environment
        conda activate py27 || return 1

        # Write python version to file
        python --version > "${outf}" 2>&1 || return 1

        # Deactivate conda environment
        conda deactivate
    }

    conda_example_conda_envs()
    {
        define_conda_env py27 py27.yml
    }

    debasher_conda_example_program()
    {
        add_debasher_process "conda_example" "cpus=1 mem=32 time=00:01:00"
    }
