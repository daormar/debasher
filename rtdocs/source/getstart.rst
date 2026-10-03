Getting Started
===============

Installing DeBasher and use it to implement a simple program is very
easy as it is shown below.

.. _installation:

Installation
------------

DeBasher is developed on Linux, and tested on Linux, on macOS and on
Windows through WSL2, which runs a Linux system inside Windows: on
each of them every change is built and its tests run. The
requirements are listed first, then how to meet them on each system,
and then how to build and install the package, which is the same
everywhere.

Requirements
^^^^^^^^^^^^

* Bash 4.3 or newer, which runs every script of DeBasher.
* Python 3.
* The usual command line tools of a Linux system: those of GNU
  coreutils (``realpath`` and ``timeout`` among them), ``grep``,
  ``sed``, ``awk`` and ``find``, and ``flock``, from util-linux.
* Graphviz, whose ``dot`` command draws the graphs of programs.
* The autotools, to configure the package: autoconf 2.71 or newer and
  automake; and ``make``, to build it.
* For the web interface, which is optional (see the :ref:`webui`
  Section): Node.js 22.12 or newer, with npm, to build it, and a
  Python virtual environment for its server. Without npm,
  ``configure`` leaves the web interface out, as it does when given
  ``--disable-frontend``.

Some features need further software, described in `Third Party
Software`_ below.

Linux
^^^^^

On Ubuntu (or Debian), the required packages are installed with:

::

    $ sudo apt install autoconf automake make git graphviz python3 python3-venv

Bash, coreutils and util-linux are part of every installation. The
Node.js package of the distribution is usually older than 22.12; a
newer one is installed from `nodejs.org <https://nodejs.org/>`__ or
with `nvm <https://github.com/nvm-sh/nvm>`__. Other distributions have
packages of the same names, or close to them.

Windows
^^^^^^^

DeBasher runs inside WSL2, the Linux system of Windows, and is tested
there with Ubuntu 24.04. WSL2 is installed, with an Ubuntu
distribution, from a PowerShell opened as administrator:

::

    > wsl --install

Then, in a terminal of that Ubuntu, follow the instructions for Linux
above. Keep the sources of DeBasher, your programs and their output
directories in the file system of Linux (under your home directory
there), not in the drives of Windows that WSL2 mounts under
``/mnt/c``: DeBasher creates FIFOs and locks files, which those drives
may not support, and reaching them from Linux is much slower. The web
interface, started inside WSL2, is reached from a browser of Windows
at ``http://localhost:8000/``, since WSL2 forwards the ports of
``localhost`` to Windows.

macOS
^^^^^

The steps below install everything that DeBasher needs, and make the
command line tools that it finds behave as those of Linux do. They are
the steps with which DeBasher is tested on macOS 15, on Apple silicon.
If something fails, please report it on the `issues page
<https://github.com/daormar/debasher/issues>`__ of the project.

#. Install the command line tools of Xcode, which provide ``git`` and
   ``make``:

   ::

       $ xcode-select --install

#. Install `Homebrew <https://brew.sh/>`__, and with it the rest of
   the requirements:

   ::

       $ brew install bash coreutils findutils gnu-sed grep gawk flock \
           autoconf automake graphviz python node

   macOS ships Bash 3.2 and has no ``flock``, and its ``sed``, ``grep``,
   ``find`` and the tools of coreutils are those of BSD, which differ
   in details from the GNU ones that DeBasher is tested with.

#. Put the Bash of Homebrew and the GNU tools first in the ``PATH``,
   under their usual names (Homebrew installs the GNU tools with a
   ``g`` prefix, ``gsed`` or ``gtimeout``, and keeps the usual names in
   ``gnubin`` directories), for example in ``~/.zprofile``:

   ::

       BREW="$(brew --prefix)"
       export PATH="$BREW/opt/coreutils/libexec/gnubin:$BREW/opt/findutils/libexec/gnubin:$BREW/opt/gnu-sed/libexec/gnubin:$BREW/opt/grep/libexec/gnubin:$BREW/bin:$PATH"

   ``configure`` takes the first ``bash`` of the ``PATH``, which every
   script of DeBasher then runs with, and refuses one older than 4.3;
   ``bash --version`` shows which one comes first.

#. Build and install the package as described below, and run
   ``make installcheck``, which runs the examples of DeBasher and says
   whether they work.

Mirror taps (the ``--mirror`` option of ``define_fifo_opt``) rely on
how Linux and macOS treat a FIFO opened for both reading and writing.
On macOS, a mirror tap whose reader is gone takes a second longer to
stop.

Building and Installing
^^^^^^^^^^^^^^^^^^^^^^^

Once the requirements are available, the package is built and
installed with the following steps:

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

#. Optionally, type ``make installcheck`` to check the installation:
   it runs the example programs with the installed tools.

#. You can remove the program binaries and object files from the
   source code directory by typing ``make clean``.

By default the files are installed under the ``/usr/local`` directory
(or similar, depending on the OS you use); however, since Step 5
requires root privileges, another directory can be specified during Step
3 by typing:

::

    $ ./configure --prefix=<absolute-installation-path>

For example, if ``user1`` wants to install the DeBasher package in
the directory ``/home/user1/debasher``, the sequence of commands to
execute should be the following:

::

    $ ./reconf
    $ ./configure --prefix=/home/user1/debasher
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
how the popular "Hello World!" program can be implemented. We will
define a DeBasher module called ``debasher_hello_world``, that will be
stored in a file with the same name and Bash extension,
``debasher_hello_world.sh``. The file will have the following content:

..
  NOTE: indent code block in emacs adding n spaces: C-u n C-x TAB

.. code-block:: bash

    hello_world_document()
    {
        document_process "Prints a hello world message."
    }

    hello_world_explain_opts()
    {
        # -s option
        local description="String to be displayed ('Hello World!' by default)"
        explain_opt "-s" "<string>" "$description"
    }

    hello_world_identify_cmdline_opts()
    {
        opt_is_non_mandatory_cmdline "-s"
    }

    hello_world_define_opts()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local process_name=$3
        local process_outdir=$4
        local optlist=""

        # -s option
        define_cmdline_opt_if_given "${cmdline}" "-s" optlist || return 1

        # Save option list
        save_opt_list optlist
    }

    hello_world()
    {
        # Initialize variables
        local str=$(read_opt_value_from_func_args "-s" "$@")

        if [ "${str}" = "${DEBASHER_OPT_NOT_FOUND}" ]; then
            str="Hello World!"
        fi

        # Show message
        echo "${str}"
    }

    debasher_hello_world_program()
    {
        add_debasher_process "hello_world" "cpus=1 mem=32 time=00:01:00"
    }

**DeBasher works with three main entities: processes, programs and
modules. A program is composed of a set of processes. A module is a file
storing multiple processes and one program**. Processes and modules are
identified by a particular name, and their specific behavior is defined
by means of a set of functions. The program associated with a particular
module is also defined by means of a function.

DeBasher adopts an object-oriented programming (OOP) approach, where
each function implements a specific method. Function names have two
parts, first, the name of the program or module, and second, a suffix
identifying the method. For instance, the function
``hello_world_define_opts`` implements the method ``define_opts`` for the
``hello_world`` process.

In the "Hello World!" example shown above, we have a module named
``debasher_hello_world`` that is stored in the
``debasher_hello_world.sh`` file. The module internally defines a
program that executes the process ``hello_world``.  Below we describe
the functions involved:

* ``hello_world_document``: this function implements the ``document``
  method for ``hello_world``, which provides a short description of
  what the process does via the ``document_process`` API function.

* ``hello_world_explain_opts``: this function implements the
  ``explain_opts`` method for ``hello_world``. Such method defines the
  options that the process receives. In particular,
  ``hello_world`` receives the ``-s`` option, which allows to specify
  the string to be shown. To document the option, the
  ``explain_opt`` API function is used.

* ``hello_world_identify_cmdline_opts``: this function implements the
  ``identify_cmdline_opts`` method for ``hello_world``. This method
  indicates, from the set of process options, which ones should be
  provided by the user when executing the workflow. In this case, the
  user should provide the ``-s`` option via command-line.

* ``hello_world_define_opts``: the ``define_opts`` method allows to
  define the options that will be provided to the ``hello_world``
  process, which will be implemented by the function of the same name
  (see next item below). Those options are not necessarily the same as
  the command-line options. Indeed, the function receives as input the
  command-line options, and will use the ``optlist`` variable to store
  the process options. In summary, the ``hello_world_define_opts``
  function forwards the ``-s`` command-line option, if given, using the
  ``define_cmdline_opt_if_given`` API function; if ``-s`` was not
  provided, the process option is simply left undefined. The
  ``save_opt_list`` function saves the set of options once all of them
  are defined.

* ``hello_world``: this function implements the process itself (in this
  case the function name does not incorporate any
  suffix). ``hello_world`` reads its options using the
  ``read_opt_value_from_func_args`` API function. Here, only the ``-s``
  option should be read and stored into the ``str`` variable; if it was
  not defined, ``str`` defaults to ``"Hello World!"``. Finally, the
  content of the ``str`` variable is printed to the standard output.

* ``debasher_hello_world_program``: the ``program`` method allows to
  define the processes involved in the execution of the program defined
  by the ``debasher_hello_world`` module. In this case, only one
  process is involved, ``hello_world``, which is added to the program by
  means of the ``add_debasher_process`` function.

To know the details of the DeBasher functions mentioned above, please
refer to the :ref:`API` Section.

In order to execute the program, DeBasher incorporates the
``debasher_exec`` tool. Provided that the ``debasher_hello_world.sh``
module file is in the current directory and that ``debasher_exec`` is
included in the ``PATH`` variable, we can execute the following:

::

    $ debasher_exec --pfile debasher_hello_world.sh --outdir out

The previous command executes the ``debasher_hello_world.sh`` using
``out`` as the output directory (see the :ref:`outdstruct` Section for
more details). Since the output of the program is just a string printed
to the standard output by the ``hello_world`` process, we can now use
the ``debasher_get_stdout`` command to visualize such a string. For this
purpose, we should provide the name of the output directory and the name
of the process whose standard output we want to visualize:

::

    $ debasher_get_stdout -d out -p hello_world

The output of the previous command is:

::

    Hello World!

On the other hand, it is also possible to inspect the scheduler
output. The scheduler output includes the error output of a particular
process, and also some scheduling-related information, while its
standard output goes to the file that ``debasher_get_stdout`` shows. The
scheduler output is useful for debugging. To visualize the scheduler
output we can use the following command:

::

    $ debasher_get_sched_out -d out -p hello_world

The output returned by the command is:

.. code-block:: bash

    Process started at 07/30/24 18:17:06
    * Resetting output directory for process...
    Function hello_world successfully executed
    Process finished at 07/30/24 18:17:06

Using the Web Interface
-----------------------

The same kind of program can also be built without writing its module
by hand, with the DeBasher web interface. Once its Python dependencies
are installed (see the :ref:`webui` Section), it is started with:

::

    $ debasher_webui

and opened in a browser at the address that it prints, such as
``http://127.0.0.1:8000/#token=...``, which holds its token. There, "Create
new program" starts an empty program, where processes are added and
their options connected on a canvas; "Save" writes the program and its
generated module into a directory, and the "Run" menu runs it with
``debasher_exec``, coloring each process by its status as the run goes
on.
