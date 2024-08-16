Subprogram Example
^^^^^^^^^^^^^^^^^^

.. code-block:: bash

    # Load modules
    load_debasher_module "debasher_array_example"
    load_debasher_module "debasher_fifo_example"

    debasher_subprogram_example_program()
    {
        add_debasher_program "debasher_array_example" "test"
        add_debasher_program "debasher_fifo_example" "test"
    }
