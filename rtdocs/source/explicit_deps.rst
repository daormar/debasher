Explicit Process Dependencies Example
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

    # Load modules
    load_debasher_module "debasher_value_pass_example"

    # This module reuses the value_writer and value_reader processes
    # from the value pass example, but declares their execution order
    # explicitly instead of relying on the dependency DeBasher infers
    # from define_opt_from_proc_out. The processdeps=afterok:value_writer
    # attribute on value_reader states directly that it must run only
    # after value_writer finishes successfully. Compare this with
    # debasher_host_workflow_expl_deps.sh, where the same processdeps
    # attribute is used with the aftercorr keyword to keep array tasks
    # paired by index instead of imposing a plain success order.

    debasher_explicit_deps_example_program()
    {
        add_debasher_process "value_writer" "cpus=1 mem=32 time=00:01:00"
        add_debasher_process "value_reader" "cpus=1 mem=32 time=00:01:00" "processdeps=afterok:value_writer"
    }
