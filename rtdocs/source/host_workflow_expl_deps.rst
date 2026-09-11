Host Workflow Example With Explicit Dependencies
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

    # Load modules
    load_debasher_module "debasher_host_workflow"

    # This module reuses the host1 and host2 processes from the host
    # workflow example, but declares their dependency explicitly with
    # the "aftercorr" keyword instead of leaving it to be inferred from
    # define_opt_from_proc_task_out. processdeps=aftercorr:host1 on
    # host2 tells DeBasher that each host2 task must run only after the
    # host1 task with the same array index has finished, keeping the
    # pairing between the two arrays while still allowing different
    # indices to run independently of each other.

    debasher_host_workflow_expl_deps_program()
    {
        add_debasher_process "host1" "cpus=1 mem=32 time=00:10:00 throttle=64" "processdeps=none"
        add_debasher_process "host2" "cpus=1 mem=32 time=00:10:00 throttle=64" "processdeps=aftercorr:host1"
    }
