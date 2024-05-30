.. _implem:

Implementing DeBasher Programs
==============================

This section is devoted to explain the procedure of implementing new
DeBasher programs. There are four main aspects involved. First, creating
and configuring a new module to store the program and the different
processes it executes. Second, implementing the processes
themselves. Third, handling command-line and process options for the
processes. And finally, incorporating the processes into the program.

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

The whole code will be added to a single module file called
``debasher_file_example.sh`` (the ``.sh`` extension is added because the
module will only contain Bash code).

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

Module Configuration
--------------------

The first step to implement DeBasher programs is to define the required
modules. In our example, there will only be one module, the
``debasher_file_example`` module, which will be stored in the
``debasher_file_example.sh`` file.

For a particular module, it is possible to define certain methods,
allowing to incorporate specific functionality. One example of this
would be to provide basic documentation about the module. To achieve
this goal, the ``document`` method can be defined:

.. code-block:: bash

    debasher_file_example_document()
    {
        module_description "This module implements a simple program with two processes, one writes a string to a file and the other one reads it and prints it to the standard output."
    }

One important tool to configure a particular module is to load other
modules. For this purpose, the ``load_debasher_module`` function can be
used.

For our example we do not need to load modules or further model
configuration. However, for additional information about the module
configuration API, please read the :ref:`mod-conf` Section.

Process Implementation
----------------------

The process constitutes the basic reusability unit of DeBasher. This
means that a given process can potentially be used in multiple programs,
while other elements such as the program network determined by the
configuration of the process options are program-dependent.

A DeBasher process has a name, and it is implemented by means of a
function with such a name. For instance, if we want to implement the
``file_writer`` process, we would start with the following code:

.. code-block:: bash

    file_writer()
    {
        # Add process code here
    }

A DeBasher process can have input and output options, that are provided
to the process as if it was a standard UNIX command.

So, when implementing a process, we should figure out the input and
output options it is going to work with. Such options should be read at
the very beginning of the process implementation. For this purpose, we
use the ``read_opt_value_from_func_args`` API function. This function
takes the name of a particular option and the input parameters of the
process being implemented, and returns the value associated to the
option.

Going back to the ``file_writer`` process, we want it to take a string
as input and write it to a file. As a result, it will receive two
options:

* ``-s <string>``: indicates the string that should be stored in a file.
* ``-outf <string>``: determines the name of the file where the input
  string will be written.

**It is important to stress out that in DeBasher, the name of the output
options should always start with** ``-out`` **or** ``--out`` **.**

Given the two process options mentioned above, we can proceed with the
implementation of the ``file_writer`` process as follows:

.. code-block:: bash

    file_writer()
    {
        # Initialize variables
        local str=$(read_opt_value_from_func_args "-s" "$@")
        local outf=$(read_opt_value_from_func_args "-outf" "$@")

        # Add process code here
    }

From this point, it is trivial to finish the code, since we only need to
write the given string to the output file:

.. code-block:: bash

    file_writer()
    {
        # Initialize variables
        local str=$(read_opt_value_from_func_args "-s" "$@")
        local outf=$(read_opt_value_from_func_args "-outf" "$@")

        # Write string to file
        echo "${str}" > "${outf}"
    }


On the other hand, the ``file_reader`` process should take a file name
as input and write its content to the standard output. Assuming that the
name of the input option is ``-inf``, the implementation of the process
would look as follows:

.. code-block:: bash

    file_reader()
    {
        # Initialize variables
        local inf=$(read_opt_value_from_func_args "-inf" "$@")

        # Read string from file
        cat < "${inf}"
    }


Command-Line Option Explanation
-------------------------------

Once a particular process has been implemented, it is necessary to
ensure that it receives the input and output options it needs. Some of
those options could be generated by other processes, but others may need
to be provided in the command-line.

In this section we explain how the command-line options are handled for
a DeBasher program. In particular, command-line options should be
provided when executing the program with ``debasher_exec``. If we
execute ``debasher_exec`` with the ``--show-cmdline-opts`` flag, a
description of the process options is displayed. This description is
collaboratively generated by the ``explain_cmdline_opts`` method
implemented for the different processes.

Below we show the result of executing ``debasher_exec`` with the
``--show-cmdline-opts`` flag for the ``debasher_file_example``
module (only the part of the output related to the command-line options
is shown):

::

    # Command line options for the program...
    CATEGORY: GENERAL
    -s <string> String to be displayed [file_writer]

In this case, the program only defines one command-line option, ``-s``,
for the ``file_writer`` process. For this purpose, we define the
``explain_cmdline_opts`` method for the process, with the following
code:

.. code-block:: bash

    file_writer_explain_cmdline_opts()
    {
        # -s option
        local description="String to be displayed"
        explain_cmdline_opt "-s" "<string>" "$description"
    }

On the other hand, the ``file_reader`` process will not require any
command line option. In those cases, we can define the corresponding
``explain_cmdline_opts`` method for the process as follows:

.. code-block:: bash

    file_reader_explain_cmdline_opts()
    {
        :
    }


Option Definition/Generation
----------------------------

After implementing the process and documenting its command-line options,
we can proceed to add the code that will specify the particular options
that the process receives. This step, when completed for all of the
processes, can be seen as defining the program network.

There are two alternatives to specify the process options, using the
``define_opts`` method, or using the ``generate_opts`` method. The
second one is more suited to those situations where we define a process
array (see the :ref:`Examples` Section).

Alternative 1: Implement the ``define_opts`` method
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Regarding the ``define_opts`` method, below it is shown a template of
the function that should be completed when defining the options for a
process called ``processname``:

.. code-block:: bash

    processname_define_opts()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local process_name=$3
        local process_outdir=$4
        local optlist=""

        # ADD CODE HERE...

        # Save option list
        save_opt_list optlist
    }

The function receives four input parameters that can be used when
necessary within the function. We store those input parameters into the
following variables:

* ``cmdline``: contains a serialized version of the command-line options
  provided to the program. This variable will be useful to take the
  required command-line options and pass them to the process.
* ``process_spec``: contains the process specification, including for
  instance the amount of memory and number of CPUs assigned to the
  process. This information can also be relevant when defining the
  process options.
* ``process_name``: this variable will contain the name of the process.
* ``process_outdir``: this variable stores the full path of the output
  directory for the process.

Using the previous elements, the goal of the function is to create a
string in the ``optlist`` variable that ends up containing the options
that our program needs to receive. For this purpose, DeBasher provides
specific helper functions (See the API's :ref:`proc-opts` Section).

**IMPORTANT_NOTE**: the variable used to store the option list should
always have the ``optlist`` substring as suffix. For instance,
``my_optlist`` would be a correct name for the variable, but
``list_of_options`` would not.

Let us assume that ``processname`` should work with the following
options:

* ``-n``: an integer value taken from the command line.
* ``-i``: this option takes the value of the output option ``-out`` of
  another process called ``previous_process``. This results in a program
  network where ``processname`` and ``previous_process`` are connected.
* ``-outf``: this option will store the name of the output file
  generated by the process. More specifically, we want to store this
  output in a file called ``out.txt`` in the output directory of
  ``processname``.

Taking into account the previous requirements, the implementation of the
``define_opts`` method for ``processname`` would look as follows:

.. code-block:: bash

    processname_define_opts()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local process_name=$3
        local process_outdir=$4
        local optlist=""

        # -n option
        define_cmdline_opt "$cmdline" "-n" optlist || return 1

        # -i option
        define_opt_from_proc_out "-i" "previous_process" "-out" optlist || return 1

        # -outf option
        local filename="${process_outdir}/out.txt"
        define_opt "-outf" "${filename}" optlist || return 1

        # Save option list
        save_opt_list optlist
    }

In the previous code snippet we have used three DeBasher API functions
which will add options to the ``optlist`` variable. At the end of the
function, ``optlist`` is saved by means of the ``save_opt_list`` API
function. The three new functions are:

* ``define_cmdline_opt``: this function copies the value of the ``-n``
  option given in the command line (the command line is stored in the
  ``cmdline`` variable) to the ``optlist`` variable.

* ``define_opt_from_proc_out``: this function defines the ``-i`` option
  using the same value of the ``-out`` option of ``previous_process``.

* ``define_opt``: this function takes as input the name of the option to
  be defined, its value and the name of the option list variable to
  store the result. In the example, it is used to define the option
  ``-outf`` with a value determined by the ``filename`` variable.

Alternative 2: Implement the ``generate_opts`` method
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

On the other hand, option definition can also be performed by means of
the ``generate_opts`` method. TBD

.. code-block:: bash

    processname_generate_opts_size()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local process_name=$3
        local process_outdir=$4

        # ADD CODE HERE...
        # local opts_size = ...

        echo ${opts_size}
    }

    processname_generate_opts()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local process_name=$3
        local process_outdir=$4
        local task_idx=$5
        local optlist=""

        # ADD CODE HERE...

        # Save option list
        save_opt_list optlist
    }

Option Definition for ``debasher_file_example``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

    file_writer_define_opts()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local process_name=$3
        local process_outdir=$4
        local optlist=""

        # -s option
        define_cmdline_opt "$cmdline" "-s" optlist || return 1

        # Define option for output file
        local filename="${process_outdir}/out.txt"
        define_opt "-outf" "${filename}" optlist || return 1

        # Save option list
        save_opt_list optlist
    }

.. code-block:: bash

    file_reader_define_opts()
    {
        # Initialize variables
        local cmdline=$1
        local optlist=""

        # Define option for input file
        define_opt_from_proc_out "-inf" "file_writer" "-outf" optlist || return 1

        # Save option list
        save_opt_list optlist
    }


.. _program_definition:

Program Definition
------------------

Once the processes involved in our program have been implemented, we can
proceed with the definition of the program itself.

Defining a program is extremely simple. For this purpose, we only need
to implement the ``program`` method for the ``debasher_file_example``
module. This method will incorporate into the program the processes to
be executed. To add a process to a program we can use the
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

When defining a program, it is also possible to add another
programs. This can be achieved by means of the ``add_debasher_program``
API function. An example of this is provided in the :ref:`Examples`
Section.

Further Process, Program and Module Characterization
----------------------------------------------------

The program defined by the ``debasher_file_example`` module only uses
the most basic functionality provided by DeBasher. However, as it was
mentioned above, DeBasher works with three main entities: processes,
programs and modules, and it offers multiple alternatives to fully
characterize them.

Instead of incorporating additional detailed explanations here, it can
be more useful to provide a list of examples exploiting different
aspects of the Debasher's functionality. Such examples are described in
the :ref:`Examples` Section.

Reusing Processes and Programs
------------------------------

Code reuse is a fundamental element of DeBasher. As it was explained
above, the basic reusability unit is the process. This does not include
the configuration of process options (i.e. the program network), since
it may be highly dependent on the particular program.

When implementing a new program, we can use the ``load_debasher_module``
API function to load previously implemented modules. This function will
load all of the functions characterizing the processes participating in
the loaded modules.

**HINT**: when executing the ``load_debasher_module`` API function, the
modules will be loaded from the current directory if they
exist. Otherwise, they are searched in the directories indicated in the
``DEBASHER_MOD_DIR`` environment variable (using the ``:`` symbol as
separator).

After loading the required modules, the option related code can be
modified just by redefining the corresponding functions.

For instance, let us assume that we want to create an alternative
version of the ``debasher_file_example`` module discussed above. In the
new version, the ``file_writer`` program no longer reads the input
string from the command line, but it always print the "Hello World!"
string to the output file.

If we create a new module called ``debasher_file_example_alternative``,
we would only need to put the following code in the
``debasher_file_example_alternative.sh`` file:

.. code-block:: bash

    load_debasher_module "debasher_file_example"

    file_writer_explain_cmdline_opts()
    {
        :
    }

    file_writer_define_opts()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local process_name=$3
        local process_outdir=$4
        local optlist=""

        # -s option
        define_opt "-s" "Hello World!" optlist || return 1

        # Define option for output file
        local filename="${process_outdir}/out.txt"
        define_opt "-outf" "${filename}" optlist || return 1

        # Save option list
        save_opt_list optlist
    }

    debasher_file_example_alternative_program()
    {
        add_debasher_process "file_writer" "cpus=1 mem=32 time=00:01:00"
        add_debasher_process "file_reader" "cpus=1 mem=32 time=00:01:00"
    }

As it can be seen, only the option-related code of the ``file_writer``
required modification (the code related to the ``file_reader`` process
remains unchanged).

Another way to reuse code would be to add whole programs when defining
the ``program`` method. For this purpose, we could use the
``add_debasher_program`` API function, as it was explained in the
:ref:`program_definition` Section.

.. _Examples:

Examples
--------

.. toctree::

   fwriter_freader
