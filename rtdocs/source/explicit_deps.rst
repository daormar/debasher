Explicit Process Dependencies Example
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

    # Load modules
    load_debasher_module "debasher_value_pass"

    debasher_explicit_deps_example_program()
    {
        add_debasher_process "value_writer" "cpus=1 mem=32 time=00:01:00"
        add_debasher_process "value_reader" "cpus=1 mem=32 time=00:01:00" "processdeps=afterok:value_writer"
    }
