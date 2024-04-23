Getting Started
===============

Installing DeBasher and use it to implement a simple program is very
easy as it is shown below.

.. _installation:

Installation
------------

Basic Installation Procedure
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

To install DeBasher, first you need to install the autotools (autoconf,
autoconf-archive, automake and libtool packages in Ubuntu). DeBasher
requires Bash 4.0 or above as well as Python 3.x to work. If you are
planning to use DeBasher on a Windows platform, you also need to install
the `Cygwin <https://www.cygwin.com/>`__ environment. Alternatively, the
tool can also be installed on Mac OS X systems using `MacPorts
<https://www.macports.org/>`__. Finally, the Graphviz package is also
required so as to generate graphic information about programs.

Assuming Ubuntu is being used, the required packages can be installed as
follows:

::

    $ sudo apt install autoconf autoconf-archive automake libtool graphviz

On the other hand, some of the functionality incorporated by
DeBasher requires the previous installation of third-party
software (`see below <#third-party-software>`__).

Once the autotools are available (as well as other required
software such as Cygwin or MacPorts), you can proceed with the
installation of the tool by following the next sequence of steps:

#. Obtain the package using git:

   ::

   $ git clone https://github.com/daormar/debasher.git

   Or `download it in a zip
   file <https://github.com/daormar/debasher/archive/master.zip>`__

#. ``cd`` to the directory containing the package's source code
   and type ``./reconf``.

#. Type ``./configure`` to configure the package.

#. Type ``make`` to compile the package.

#. Type ``make install`` to install the programs and any data
   files and documentation.

#. You can remove the program binaries and object files from the
   source code directory by typing ``make clean``.

By default the files are installed under the ``/usr/local`` directory
(or similar, depending on the OS you use); however, since Step 5
requires root privileges, another directory can be specified during Step
3 by typing:

::

    $ configure --prefix=<absolute-installation-path>

For example, if ``user1`` wants to install the DeBasher package in
the directory ``/home/user1/debasher``, the sequence of commands to
execute should be the following:

::

    $ ./reconf
    $ configure --prefix=/home/user1/debasher
    $ make
    $ make install

The installation directory can be the same directory where the
DeBasher package was decompressed.

Third Party Software
^^^^^^^^^^^^^^^^^^^^

Slurm
"""""

DeBasher can be configured to use `Slurm <https://slurm.schedmd.com/>`__
as a workload scheduler.  Slurm is particularly indicated to execute
large pipelines or to execute pipelines in high performance computing
environments.

Conda
"""""

DeBasher provides support for automated installation of `Conda
<https://conda.io/>`__ packages. Such packages are organized in
environments and (optionally) used within DeBasher software modules.

Docker
""""""

DeBasher also provides support for `Docker <https://www.docker.com/>`__
containers, favoring reproducibility of results.

.. _quickstart_example:

Quickstart Example
------------------

In order to provide a quick DeBasher usage example, we are going to see
how the popular "Hello World!" program can be implemented. If we call
our program ``debasher_hello_world``, we should create a file with the
same name and Bash extension, ``debasher_hello_world.sh``, with the
following content:

..
  NOTE: indent code block in emacs adding n spaces: C-u n C-x TAB

.. code-block:: bash

    hello_world_explain_cmdline_opts()
    {
        # -s option
        local description="String to be displayed ('Hello World!' by default)"
        explain_cmdline_opt "-s" "<string>" "$description"
    }

    hello_world_define_opts()
    {
        # Initialize variables
        local cmdline=$1
        local optlist=""

        # Obtain value of -s option
        local str=$(get_cmdline_opt "${cmdline}" "-s")

        # -s option
        if [ "${str}" = "${OPT_NOT_FOUND}" ]; then
            define_opt "-s" "Hello World!" optlist || return 1
        else
            define_opt "-s" "$str" optlist || return 1
        fi

        # Save option list
        save_opt_list optlist
    }

    hello_world()
    {
        # Initialize variables
        local str=$(read_opt_value_from_func_args "-s" "$@")

        # Show message
        echo "${str}"
    }

    debasher_hello_world_program()
    {
        add_debasher_process "hello_world" "cpus=1 mem=32 time=00:01:00"
    }

DeBasher works with two main entities: processes and programs. A program
is composed of a set of processes. Processes and programs are identified
by a particular name, and their specific behavior is defined by means of
a set of functions. DeBasher adopts an object-oriented programming (OOP)
approach, where each function implements a specific method. Function
names have two parts, first, the name of the program or function, and
second, a suffix identifying the method. For instance, the function
``hello_world_define_opts`` implement the method ``define_opts`` for the
``hello_world`` process.

In the "Hello World!" example shown above, we have a program called
``debasher_hello_world``, which executes the process ``hello_world``.
Below we describe the functions involved:

* ``hello_world_explain_cmdline_opts``: this function implements the
  ``explain_cmdline_opts`` method for ``hello_world``. Such method
  defines the command line options that can be provided to the
  process. In particular, ``hello_world`` may receive the ``-s`` option,
  which allows to specify the string to be shown. To document the
  option, the ``explain_cmdline_opt`` API function is used.

* ``hello_world_explain_define_opts``: the ``define_opts`` method allows
  to define the options that will be provided to the ``hello_world``
  process, which will be implemented by the function of the same name
  (see next item below). Those options are not necessarily the same as
  the command-line options. Indeed, the function receives as input the
  command-line options, and will use the ``optlist`` variable to store
  the process options. In summary, the
  ``hello_world_explain_define_opts`` will retrieve the value of the
  ``-s`` command-line option (using the ``get_cmdline_opt`` API
  function) and store it into the ``str`` variable.  If ``-s`` was not
  provided, it will pass the option ``-s "Hello World!"`` to the
  ``hello_world`` function. Otherwise, it will pass the option ``-s
  "$str"``. The code uses the ``define_opt`` API function to register
  options and the ``save_opt_list`` function to save the set of options
  when all of them are defined.

* ``hello_world``: this function implements the process itself (in this
  case the function name does not incorporate any
  suffix). ``hello_world`` reads its options using the
  ``read_opt_value_from_func_args`` API function. Here, only the ``-s``
  option should be read and stored into the ``str`` variable. Finally,
  the content of the ``str`` variable is printed to the standard output.

* ``debasher_hello_world_program``: the ``program`` method allows to
  define the processes involved in the execution of the
  ``debasher_hello_world`` program. In this case, only one process is
  involved, ``hello_world``, which is added to the program by means of
  the ``add_debasher_process`` function.

To know the details of the DeBasher functions mentioned above, please
refer to the :ref:`API` Section.

In order to execute the program, DeBasher incorporates the
``debasher_exec`` tool.
