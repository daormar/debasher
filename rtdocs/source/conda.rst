Conda Example
^^^^^^^^^^^^^

.. code-block:: bash

    # This module shows how a process can run inside a Conda
    # environment managed by DeBasher itself. conda_example_conda_envs
    # declares the py27 environment from a py27.yml file using
    # define_conda_env, and the conda_example process activates it with
    # conda_activate before running python and deactivates it
    # afterward. When the program runs with --conda-support, DeBasher
    # creates the environment from the given file if it does not exist
    # yet, so the process code only needs to assume it exists.

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

        # Activate conda environment (conda_activate loads the shell
        # functions of conda first if the shell running the process does
        # not have them)
        conda_activate py27 || return 1

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

The process activates its environment itself, so a process may use
several environments, each for a part of its work. It does so with
``conda_activate <name>`` rather than with ``conda activate``:
``conda activate`` is a shell function that conda adds to the shells
it was set up for, which the shell running a process may lack (under a
service, a Slurm job or ``debasher_exec_process``). ``conda_activate``
loads those functions first when they are missing, from the conda
executable named by ``CONDA_EXE`` or else from the one found when
DeBasher was configured (``./configure CONDA_CMD=<conda executable>``
gives another), and then activates the environment. After it,
``conda`` itself (``conda deactivate``, another ``conda activate``)
can be used.

The program ``webui_conda_example``, built with the web interface and
installed under ``<prefix>/share/debasher/webui_programs``, does the
same, and carries a test of its process that ``debasher_test`` runs
(see the :ref:`tools` Section); the test is skipped where the ``py27``
environment does not exist:

.. literalinclude:: ../../data/webui_programs/webui_conda_example/test/python_version.bats
   :language: bash
