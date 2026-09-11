Subprogram Example
^^^^^^^^^^^^^^^^^^

.. code-block:: bash

    # Load modules
    load_debasher_module "debasher_array_example"
    load_debasher_module "debasher_fifo_example"

    # This module shows how to build a larger program out of two
    # existing ones instead of declaring processes from scratch. It
    # loads both debasher_array_example and debasher_fifo_example and
    # calls add_debasher_program for each inside its own program
    # method, so running debasher_subprogram_example schedules all four
    # processes defined by those two modules (array_writer,
    # array_reader, fifo_writer and fifo_reader) together. This is the
    # same mechanism used to compose the array and fifo examples seen
    # earlier into a single workflow, useful when a program is
    # naturally assembled from reusable building blocks.

    debasher_subprogram_example_program()
    {
        add_debasher_program "debasher_array_example"
        add_debasher_program "debasher_fifo_example"
    }
