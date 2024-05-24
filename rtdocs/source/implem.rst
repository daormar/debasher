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
two processes: ``file_writer`` and ``file_reader``. The ``file_writer``
process takes a string as input and writes it to a file. The
``file_reader`` process takes this file and prints its content to the
standard output.

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

TBD

Additional Process and Program Characterization
-----------------------------------------------

TBD

Examples
--------

.. toctree::

   fwriter_freader
