Host Workflow Example With Forced Execution
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

    # Load modules
    load_debasher_module "debasher_host_workflow"

    # This module also reuses the host1 and host2 processes from the
    # host workflow example, but adds the force=yes attribute to host1.
    # This attribute tells DeBasher to always execute host1's tasks
    # again on every run, even when a previous, successful output for
    # them is already present in the output directory, which is useful
    # for processes whose result can legitimately change between runs,
    # such as one that simply reports the host it ran on.

    debasher_host_workflow_force_program()
    {
        add_debasher_process "host1" "cpus=1 mem=32 time=00:10:00 throttle=64" "force=yes"
        add_debasher_process "host2" "cpus=1 mem=32 time=00:10:00 throttle=64"
    }
