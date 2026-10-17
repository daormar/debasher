.. _implem_python:

Describing a Program in Python
==============================

This section explains how to describe a program in Python with the SDK
of DeBasher, for whoever prefers code to a canvas and Python to Bash.
The SDK is a library with which processes are defined, with their
options and their connections, and a program that adds them; the tool
``debasher_build`` turns the description into the same saved program
and the same module that the web interface saves, so that the program
opens in the editor and runs with ``debasher_exec`` like any other. The
SDK executes nothing itself and generates no Bash of its own: what it
writes is what the editor would write for the same program, and the
code of each process stays in a file of its own language beside the
description. Read the :ref:`concepts` Section first for what a program
is made of; this section says how each piece is written in Python.

Installing and importing the SDK
--------------------------------

The SDK is the Python package ``debasher``, installed with the rest of
DeBasher (see the :ref:`installation` Section). It needs the Python
packages of the web interface (``pydantic`` among them), installed into
a virtual environment as the :ref:`webui` Section explains, and it is
found in two ways:

* ``debasher_build`` finds it on its own: it runs with the Python that
  ``DEBASHER_WEBUI_PYTHON`` names, else with ``python3`` on the ``PATH``
  (that of an activated virtual environment), as ``debasher_webui``
  does, and puts the directory of the package on its path, so that the
  description it loads imports ``debasher`` with nothing more. This is
  all that is needed to build a program.
* To use the library by hand, in a Python session or a test, ``import
  debasher`` works as it is when DeBasher was configured with the prefix
  of the Python itself (a virtual environment, or a conda environment
  with its own Python). The conda package of DeBasher keeps the package
  in a directory of its own and puts it in ``PYTHONPATH`` when the
  environment is activated. With another prefix, put the Python
  directory of the installation in ``PYTHONPATH``
  (``<prefix>/lib/python3.X/site-packages``).

A first program
---------------

The hello world of the :ref:`quickstart` Section, with its process in
Python, is shipped as ``sdk_hello_world_py`` among the examples of the
SDK (the ``data/sdk_programs/python`` folder of the repository,
installed under ``<prefix>/share/debasher/sdk_programs/python``), a
directory with the description and the code of the process:

.. literalinclude:: ../../data/sdk_programs/python/sdk_hello_world_py/sdk_hello_world_py.py
   :language: python
   :start-at: from debasher

The description reads like a module. ``Process`` defines a process with
its name, its description and the file of its code, ``hello_world.py``,
whose extension tells its language (``.sh``, ``.py``, ``.pl``, ``.r``,
``.groovy``); the file holds what the code box of the editor holds, the
whole script of a process in Python, or, for a process in Bash, the
function named as the process with its helper functions. The methods of
the process declare its options: here one command line option, ``-s``,
with its data type, its description and whether it is mandatory.
``Program`` defines the program, named as the file, and ``add`` adds the
process with the specifications of its use, as ``add_debasher_process``
does in a module. The file calls nothing: it defines, as a module
defines, and the tool does the rest.

Building and running
--------------------

::

    $ debasher_build sdk_hello_world_py.py
    /path/to/sdk_hello_world_py/sdk_hello_world_py.sh

``debasher_build`` loads the file, finds the program it defines and
writes it beside the file: the program as the web interface saves it,
the topology file ``program.yaml``, which names the file of each process
where the description has it, and the module ``sdk_hello_world_py.sh``,
exactly what the "Save" button of the editor writes (``-o <dir>`` writes
them elsewhere, with a copy of each process file). The file is named
after its program, as a module is, and defines one program; anything
else is an error that says so. From
here the program is one more: it runs with ``debasher_exec``, its state
is followed with ``debasher_status``, and its directory opens in the
web interface with "Load program", where it shows on the canvas with
its processes laid out as those of an imported module are.

::

    $ debasher_exec --pfile sdk_hello_world_py.sh --outdir out -s "Hello from Python" --wait
    $ debasher_get_stdout -d out -p hello_world
    Hello from Python

The Python file is never run with ``python`` and never given to
``debasher_exec``; after a change to it, ``debasher_build`` is run
again.

Processes, options and connections
----------------------------------

The fan-out to a pool of workers of the :ref:`design_patterns` Section,
as ``webui_dynamic_fanout_fifos`` builds it in the web interface, is
shipped as ``sdk_dynamic_fanout_fifos`` and shows the rest: a generated
file is counted and cut into fragments, which a dispatcher streams
through FIFOs to a pool of workers, and a last process merges their
counts.

.. literalinclude:: ../../data/sdk_programs/python/sdk_dynamic_fanout_fifos/sdk_dynamic_fanout_fifos.py
   :language: python
   :start-at: from debasher

The pieces, in the order a process is written:

* **Where the code is.** ``code=`` names the file of the process, which
  the topology file names in turn, where the description has it, and
  the generated module embeds, as it embeds the code box of the editor.
  ``script=`` names
  a file that the module runs as it is, an executable with the
  interpreter of its extension, which stays outside the module and is
  copied beside it (the dispatcher): the external alias of the
  :ref:`implem_bash` Section. ``alias=`` runs the code of another
  process under this one's name and options
  (``alias_opt_map={"-x": "-y"}`` renames the options it passes on, as
  the alias option map of a module does), and a process with none
  of them takes its code from a module that the preamble of the program
  loads (``Program(..., preamble="load_debasher_module ...")``).
* **Options.** Every option is declared by a method that says where its
  value comes from and how it is delivered, with the data types of the
  editor (``int``, ``float``, ``string``, ``file``, ``dir``):
  ``cmdline_opt`` for a value of the command line of the run
  (``mandatory=False`` for an optional one, ``shaping=True`` for a task
  shaping option), ``cmdline_flag`` for a flag, ``input`` for an input
  with a literal value or connected to an output, ``output`` for an
  output, whose value names what the process produces
  (``in_outdir("counts.txt")`` is the file of that name in the process
  output directory), ``fifo_output`` and ``fifo_input`` for an option
  delivered through a FIFO of a given name (``mirror=True`` keeps the
  copy of what is written that ``debasher_get_fifo_mirror`` reads),
  ``outdir_opt`` for an output
  that names the process output directory or a task subdirectory of it
  (``subpath="${task_idx}"``), ``shared_dir_opt``, ``procspec_opt`` and
  ``value_desc_output`` for the other option channels of the editor, and
  ``opt`` for any option with its fields given by name. The direction of
  an option comes from its label, as the engine reads it: an output
  starts with ``-out``. An option is reached again by its label,
  ``generate["-outf"]``.
* **Connections.** An input names the output it reads, as the module
  does in ``define_opt_from_proc_out``: ``source=`` takes the option of
  another process, or the name of the process and the label of the
  option, ``("generate", "-outf")``, which lets a process be defined
  before the one it reads; a list of sources is a fan-in. The program
  derives its connections from the inputs of the processes it adds, and
  an input that reads a process the program does not add is an error.
* **Families.** An option whose label ends in ``-ith`` stands for one
  option per task of the array or generator at the other end
  (``-outf-ith`` for ``-outf0``, ``-outf1``, ...), as in the editor;
  ``count_source=`` names the command line option of the same process
  that counts them, and without it the family is counted by the tasks
  of the process it is connected to.
* **Arrays and generators.** ``Array`` and ``Generator`` are processes
  with several tasks, the array and generator modes of the options
  handler of the editor, and ``tasks=`` names a Bash file with the code
  that the editor accepts in that mode: for an array, the code that
  builds the array of its tasks from the command line of the run
  (``worker_tasks.sh``, one element per worker); for a generator, the
  code that prints the number of tasks. That code runs when
  ``debasher_exec`` prepares a run, as it does for a program of the
  editor, since the tasks depend on the command line of each run. The
  additional methods of a process (``skip``, ``post``,
  ``reset_outfiles``, ``outdir_basename``, ``conda_envs``,
  ``docker_imgs``) are Bash files too, each with the body that the
  editor takes.
* **The program.** ``Program`` takes the description, the program
  options that a run is given (what "Set program options" of the editor
  holds), the preamble, the environment variables, the shared
  directories and the execution options of the editor by name
  (``scheduler``, ``conda_support``, ...); ``add`` takes the process and
  the specifications of its use there: ``cpus``, ``mem``, ``time``, the
  explicit dependencies (``processdeps="afterok:count"``), ``force``,
  and ``position`` on the canvas when the layout of the editor is not
  wanted.

A resident program
------------------

A resident program (see the :ref:`resident` Section) is a ``Program``
with ``resident=True`` that adds nodes instead of processes. The running
sum of that Section, shipped as ``sdk_running_sum``, has one node and a
Supervisor:

.. literalinclude:: ../../data/sdk_programs/python/sdk_running_sum/sdk_running_sum.py
   :language: python
   :start-at: from debasher

A ``Node`` is given as a Python file with the class of the node,
``accumulate.py``, written as the node code editor of the web interface
shows it: the import of its node kind, the class derived from
``FBPProcess``, ``ProgramLauncher`` or ``DirectoryWatcher`` with its
hooks, and the line that runs it. ``initiator=True`` makes the node an
initiator, the node where a round starts (see the :ref:`resident`
Section). The build splits the file into the parts that the editor
keeps, so a file that the editor could not hold is refused with what to
change. Its ports are its options: an external
input, written from outside the program, is ``fifo_input(...,
external=True)``, and an output is ``fifo_output``. The ``Supervisor``
is added without a file, since the module writes its whole class and
the channels between it and the nodes. The specifications of a node
(``input_log_max_mb``, ``heartbeat_timeout_s``, ...) go to ``add`` with
the others.

What the SDK does not do
------------------------

* It does not run a program: ``debasher_exec`` does, from the command
  line or from the editor, so that building a program never executes
  it.
* It does not read a program: the way from a module or from the editor
  into Python does not exist. A program edited and saved in the editor
  keeps its Python file as it was; the code of a process edited there
  goes into the file that the description names, since the topology
  file names the same file, and survives the next build, while a change
  to the options, the connections or the specifications goes into
  ``program.yaml`` only and is written over by the next build.
* It computes no dynamic options in Python: the code that shapes the
  tasks of an array or a generator is the Bash that the editor accepts,
  in a file. The manual mode of the editor, a whole ``define_opts``
  written by hand, is not offered either.
