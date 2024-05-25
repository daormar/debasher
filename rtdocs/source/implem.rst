.. _implem:

Implementing DeBasher Programs
==============================

This section is devoted to explain the procedure of implementing new
DeBasher programs. There are three main aspects involved in this
procedure. First, implementing the different processes participating in
the program. Second, handling command-line and process options. And
finally, defining which processes will compose the program.

More specifically, the implementation of a DeBasher program can be
carried out in a process-wise manner. For each process, we will define a
set of Bash functions governing the process behavior and its
corresponding options. Option definition will implicitly define a
network connecting the inputs and outputs of the different processes.

The following sections explain how to implement a simple program with
two processes: ``file_writer`` and ``file_reader``. We will call this
process ``debasher_file_example``. The ``file_writer`` process takes a
string as input and writes it to a file. The ``file_reader`` process
takes this file and prints its content to the standard output.

The whole code will be added to a single file called
``debasher_file_example.sh`` (the program name plus the ``.sh``
extension).

A process graph generated with ``debasher_exec`` using its
``--gen-proc-graph`` for the ``debasher_file_example.sh`` program would
look as follows:

.. image:: images/file_example_graph.png
  :width: 120
  :align: center

The graph shows the two processes involved in the program (using
rectangles) as well as their input and output options (using ellipses)
and how such options are connected, implicitly defining the program
network.

Although it is not mandatory, it is recommended that the implementation
is made in the same order in which the sections appear.

Process Implementation
----------------------

TBD

Command-Line Option Explanation
-------------------------------

TBD

Option Definition/Generation
----------------------------

TBD

Program Definition
------------------

Once the processes involved in the ``debasher_file_example`` program
have been implemented, we can proceed with the definition of the program
itself.

Defining a program is extremely simple. For this purpose, we only need
to implement the ``program`` method for ``debasher_file_example``. This
method will incorporate into the program the processes to be
executed. To add a process to a program we can use the
``add_debasher_process`` function:

.. code-block:: bash

    debasher_file_example_program()
    {
        add_debasher_process "file_writer" "cpus=1 mem=32 time=00:01:00"
        add_debasher_process "file_reader" "cpus=1 mem=32 time=00:01:00"
    }

When adding a process to a program, we can provide information about the
resources that the process requires. In the given example, both the
``file_writer`` and the ``file_reader`` processes will require 1 CPU,
32MBs of RAM a 1 minute for their execution.

Further Process and Program Characterization
--------------------------------------------

TBD

Examples
--------

.. toctree::

   fwriter_freader
