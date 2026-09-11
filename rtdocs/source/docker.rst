Docker Example
^^^^^^^^^^^^^^

.. code-block:: bash

    # This module shows how a process can run inside a Docker container
    # managed by DeBasher itself. docker_example_docker_imgs declares
    # the "library/hello-world" image with pull_docker_img, and the
    # docker_example process simply runs "docker run hello-world" and
    # redirects its output to a file. DeBasher takes care of pulling
    # the declared image before the process executes, so the process
    # code can assume it is already available locally.

    docker_example_document()
    {
        document_process "Runs the hello-world Docker image and writes its output to a file."
    }

    docker_example_explain_opts()
    {
        # -outf option
        local description="output file"
        explain_opt "-outf" "<file>" "$description"
    }

    docker_example_identify_cmdline_opts()
    {
        :
    }

    docker_example_define_opts()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local process_name=$3
        local process_outdir=$4
        local optlist=""

        # Define name of output file
        define_opt "-outf" "${process_outdir}/hello_world.txt" optlist || return 1

        # Save option list
        save_opt_list optlist
    }

    docker_example()
    {
        # Initialize variables
        local outf=$(read_opt_value_from_func_args "-outf" "$@")

        # Write python version to file
        docker run hello-world > "${outf}" || return 1
    }

    docker_example_docker_imgs()
    {
        pull_docker_img "library/hello-world"
    }

    debasher_docker_example_program()
    {
        add_debasher_process "docker_example" "cpus=1 mem=32 time=00:01:00"
    }
