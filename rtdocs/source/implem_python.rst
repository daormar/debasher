.. _implem_python:

Describing a Program in Python
==============================

This section explains how to describe a program in Python with the SDK
of DeBasher, for whoever prefers code to a canvas and Python to Bash.
The SDK is a library with which processes are defined, with their code,
their options and their connections, and a program that adds them; the
tool ``debasher_build`` turns the Python description of a program, the
Python file named after it (``<name>.py``) that defines its processes
and the program, into the same saved program and the same module that
the web interface saves, so that the program opens in the editor and
runs with ``debasher_exec`` like any other. The SDK executes nothing
itself and generates no Bash of its own: what it writes is what the
editor would write for the same program, and the code of each process
stays in a file of its own language beside the Python description. Read
the :ref:`concepts` Section first for what a program is made of; this
section says how each piece is written in Python.

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
  does, and puts the Python directory of the installation, which holds
  the package, on its path, so that the Python description it loads
  imports ``debasher`` with nothing more. This is all that is needed to
  build a program.
* To use the library by hand, in a Python session or a test, ``import
  debasher`` works as it is when DeBasher was configured with the prefix
  of the Python itself (a virtual environment, or a conda environment
  with its own Python). The conda package of DeBasher keeps the package
  in a Python directory of its own and puts that directory in
  ``PYTHONPATH`` when the environment is activated. With another prefix, put the Python
  directory of the installation in ``PYTHONPATH``
  (``<prefix>/lib/python3.X/site-packages``).

A first program
---------------

The hello world of the :ref:`quickstart` Section, with its process in
Python, is shipped as ``sdk_hello_world_py`` among the examples of the
SDK (the ``data/sdk_programs/python`` folder of the repository,
installed under ``<prefix>/share/debasher/sdk_programs/python``), a
directory with the Python description and the code of the process:

.. literalinclude:: ../../data/sdk_programs/python/sdk_hello_world_py/sdk_hello_world_py.py
   :language: python
   :start-at: from debasher

``Process`` defines a process with its name, its description, the file
of its code, ``hello_world.py``, and the options that its tasks receive,
each with its label, its data type and its description (``opt``, or
``flag`` for a flag). The extension of the file tells its language
(``.sh``, ``.py``, ``.pl``, ``.r``, ``.groovy``); the file holds what
the code box of the editor holds, the whole script of a process in
Python, or, for a process in Bash, the function named as the process
with its helper functions. ``interface`` says what the process receives
from outside the program: here ``-s`` comes from the command line, and
is optional. ``Program`` defines the program, named as the file, and
``add`` adds the process with the specifications of its use, as
``add_debasher_process`` does in a module. The file calls nothing: it
defines, as a module defines, and the tool does the rest.

Building and running
--------------------

::

    $ debasher_build sdk_hello_world_py.py
    /path/to/sdk_hello_world_py/sdk_hello_world_py.sh

``debasher_build`` loads the file, finds the program it defines and
writes it beside the file: the program as the web interface saves it,
the topology file ``program.yaml`` (see the :ref:`program-yaml`
Section), which names the file of each process where the Python
description has it, and the module ``sdk_hello_world_py.sh``, exactly
what the "Save" button of the editor writes (``-o <dir>`` writes them
elsewhere, with a copy of each process file). The file is named after
its program, as a module is, and defines one program; anything else is
an error that says so. A file of a process is written where the Python
description has it, relative to its directory, and a file outside that
directory by its name alone; ``debasher_build`` refuses, before writing
anything, two files of the program with different contents that end up
at one path (two ``run.sh`` from different directories), and a file, or
a script that it copies beside the module, at the path of the module, of
``program.yaml``, or of a name that DeBasher manages. From here the
program is one more: it runs with ``debasher_exec``, its state is
followed with ``debasher_status``, and its directory opens in the web
interface with "Load program", where it shows on the canvas with its
processes laid out as those of an imported module are.

::

    $ debasher_exec --pfile sdk_hello_world_py.sh --outdir out -s "Hello from Python" --wait
    $ debasher_get_stdout -d out -p hello_world
    Hello from Python

The Python description is never run with ``python`` and never given to
``debasher_exec``; after a change to it, ``debasher_build`` is run again
with the file, ``debasher_build sdk_hello_world_py.py``. Given the
directory of a saved program instead, or its ``program.yaml``, or
nothing inside it, ``debasher_build`` writes the module again from
``program.yaml`` and the files of the processes, whoever saved them (see
the :ref:`tools` Section); ``-o`` goes with a Python description only. A
directory that holds the Python description of its program, as the one
written beside the file does, is not built this way, since the build
would ignore a change to the Python description: the tool refuses it and
names the command to run.

A Python description may import the Python files beside it: while
``debasher_build`` loads the file, it puts the directory of the file
first on ``sys.path``, so that ``import helpers`` imports the
``helpers.py`` of that directory. A file named as a module that the tool
has already loaded is the exception: the SDK (``debasher``), the API of
the web interface (``api``), ``yaml``, ``pydantic`` and their
dependencies, and the modules of the standard library that they use
(``json``, ``argparse`` and others). Python takes such a module from
those it has loaded and does not look for it again, so ``import api``
gets the API of the web interface, not the ``api.py`` beside the
Python description, and nothing says so. Give such a file another name.

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

A process is written in three parts, as a module keeps them apart (the
:ref:`sdk-api` Section lists every class and function):

* **What does not change: the constructor.** ``Process`` takes the name,
  the code, the description, the options that its tasks receive
  (``options=[opt(...), flag(...)]``), the environments and the methods
  of a task. Nothing changes them once the process is created: they go
  with the code, which reads its options by their labels. ``code=``
  names the file of the process, which the topology file names in turn,
  where the Python description has it: the module embeds it when it is
  Bash, and runs it as it is, as an external alias of the file, in any
  other language. ``script=`` names a file that the module runs as it is
  too, an executable with the interpreter of its extension, but that the
  user owns: the editor shows a ``code=`` file as the code of the
  process and writes it when it saves, and leaves a ``script=`` file
  alone (the dispatcher); the external alias of the :ref:`implem_bash`
  Section. ``alias=`` runs the code of another process under this one's
  name and options (``alias_opt_map={"-x": "-y"}`` renames the options
  it passes on, as the alias option map of a module does), and a process
  with none of them takes its code from a module that the preamble of
  the program loads (``Program(..., preamble="load_debasher_module
  ...")``). The data types are those of the editor (``int``, ``float``,
  ``string``, ``file``, ``dir``). A label is ``-`` or ``--`` followed by
  an ASCII letter or an underscore, as the engine requires, and the SDK
  refuses any other. The direction of an option comes from its label, as
  the engine reads it: an output starts with ``-out`` or ``--out``. An
  option is reached again by its label, ``generate["-outf"]``.
* **What comes from outside: the interface.** ``interface`` names the
  options whose value comes from the command line of the run, each
  ``"mandatory"`` or ``"optional"`` (``cmdline=``), the task shaping
  options, which only the tasks file of an array or a generator reads,
  with their data type and description (``shaping=``), and, in a
  resident program, the inputs fed by a FIFO from outside the program
  (``external=``). This is narrower than the interface of the
  :ref:`concepts` Section, which is every option of the process: the
  options themselves are listed in the constructor, and ``interface``
  only says which of them the run gives from outside.
* **The tasks and their values: the task options.** ``task_options``
  gives every other option its value (``values=``): a string is a
  literal value (``in_outdir("counts.txt")`` is the file of that name in
  the process output directory), ``True`` sets a flag, ``connect``
  connects an input to the output of another process, ``fifo`` delivers
  an option through a FIFO of a given name (``mirror=True`` keeps a copy
  of what passes through it, which ``debasher_get_fifo_mirror`` reads),
  ``outdir`` names the process output directory or a task subdirectory
  of it (``subpath="${task_idx}"``), and ``shared_dir``, ``procspec``
  and ``value_desc`` give the other option channels of the editor.

The interface and the task options are given apart, and each call
replaces what was given before, so a process defined in one place can be
connected otherwise, or made an array, by a program that gives them
again. Every option that a task receives is given in exactly one place
(on the command line, fed from outside, or in ``values=``), task shaping
options need an array or a generator, and the build says what breaks
these rules. The example shows, besides these three parts:

* **Connections.** ``connect`` names the output an input reads, as the
  module does in ``define_opt_from_proc_out``: the option of another
  process, or the name of the process and the label of the option,
  ``("generate", "-outf")``, which lets a process be defined before the
  one it reads; a list of sources is a fan-in. The program derives its
  connections from the processes it adds, and an input that reads a
  process the program does not add is an error.
* **Families.** An option whose label ends in ``-ith`` stands for one
  option per task of the array or generator at the other end
  (``-outf-ith`` for ``-outf0``, ``-outf1``, ...), as in the editor;
  ``count=`` of ``task_options`` names the command line option of the
  same process that counts them, and without it the family is counted
  by the tasks of the process it is connected to.
* **Arrays and generators.** ``task_options(array=...)`` and
  ``task_options(generator=...)`` give a process several tasks, the
  array and generator modes of the options handler of the editor,
  shaped by the file they name. A Python file (``.py``) defines a
  function ``tasks(run)``, which returns the elements of the array, or
  the number of tasks of a generator, from the command line of the run:
  ``worker_tasks.py`` gives one element per worker,

  .. literalinclude:: ../../data/sdk_programs/python/sdk_dynamic_fanout_fifos/worker_tasks.py
     :language: python

  and any other file is Bash, the code that the editor accepts in that
  mode (see :ref:`tasks_in_python` for what ``run`` holds and how the
  module calls the function). Either way the code runs when
  ``debasher_exec`` prepares a run, as it does for a program of the
  editor, since the tasks depend on the command line of each run, and
  only the shape of the tasks comes from it: the values of the options
  of each task are still the Bash words of ``values=``, such as
  ``outdir(subpath="${task_idx}")`` or ``fifo("dispatch_fifo_${i}")``.
* **The program.** ``Program`` takes the description text of the
  program, the program options that a run is given (what "Set program
  options" of the editor holds), the preamble, the environment that the
  web interface gives the tools of the engine (``env_vars``, of which
  only ``DEBASHER_MOD_DIR`` is read), the shared directories and the
  execution options of the editor by name (``scheduler``,
  ``conda_support``, ...); ``add`` takes the process and the
  specifications of its use there: ``cpus``, ``mem``, ``time`` (1 CPU,
  256 megabytes and ``01:00:00`` for those not given, as the editor
  gives a new process), the explicit dependencies
  (``processdeps="afterok:count"``), ``force``, and ``position`` on the
  canvas when the layout of the editor is not wanted.

Skipping tasks, and the environments of a process
-------------------------------------------------

The additional methods of a process (``skip``, ``post``,
``reset_outfiles``) are given as files, each with the Bash body that the
editor takes. The skip method may be a Python file instead, with a
function ``skip(task)`` that returns ``True`` to skip the task and
``False`` to run it. The skip example of the :ref:`implem_bash` Section,
shipped as ``sdk_skip_py``, skips the process that reads a sum when the
sum is odd:

.. literalinclude:: ../../data/sdk_programs/python/sdk_skip_py/sdk_skip_py.py
   :language: python
   :start-at: from debasher

.. literalinclude:: ../../data/sdk_programs/python/sdk_skip_py/value_reader_skip.py
   :language: python

``task.value`` (``task.value(label, default)`` for a default) reads an
option of the task as ``read_opt_value_from_func_args`` does, so the
value that a value descriptor holds comes back as it is. The function
runs inside the task, with the options of the task, before anything of
its process output directory is touched; an error in it (an exception, a
value that is not ``True`` or ``False``) fails the task instead of
running it. Only ``skip`` takes a Python file: any other method given
one is an error.

The Conda environments and the Docker images of a process are data:
``conda_envs=`` takes the name of each environment and its yml file,
and ``docker_imgs=`` a list of images, from which the module writes the
lines that prepare them when the run has conda or docker support
(``conda_support=True`` or ``docker_support=True`` in ``Program``, or
``--conda-support`` or ``--docker-support`` given to ``debasher_exec``).
The yml file is found in the directories that ``DEBASHER_YML_DIR``
lists, else among those installed with DeBasher, where ``py27.yml`` is,
and not beside the Python description. ``sdk_conda_envs`` activates the
environment ``py27``, which its runs create if it does not exist:

.. literalinclude:: ../../data/sdk_programs/python/sdk_conda_envs/sdk_conda_envs.py
   :language: python
   :start-at: python_version =
   :end-before: python_version.task_options

A path given to ``conda_envs=`` or ``docker_imgs=`` is a method file
with the Bash body instead, as for the other methods.

A tasks file and a skip file in Python run with the Python of DeBasher,
not inside the Conda environment or the Docker image of the process, so
the packages they import are those of that Python.

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
``accumulate.py``, written as the node code editor of the web interface shows
it: the import of its node kind, the class derived from ``FBPProcess``,
``ProgramLauncher`` or ``DirectoryWatcher`` with its hooks, and the line that
runs it. The build splits the file into the parts that the editor keeps, so a
file that the editor could not hold is refused with what to change. Its ports
are its options: an external input, written from outside the program, is given
in its interface (``external={"-numbers": "numbers"}``, the label and the name
of the FIFO), and an output is a ``fifo`` of its task options.
``initiator=True``, given to ``add``, makes the node an initiator, the node
where a round starts (see the :ref:`resident` Section), which depends on how the
program connects it. The ``Supervisor`` is added without a file, since the
module writes its whole class and the channels between it and the nodes. The
specifications of a node (``input_log_max_mb``, ``heartbeat_timeout_s``, ...) go
to ``add`` with the others.

What the SDK does not do
------------------------

* It does not run a program: ``debasher_exec`` does, from the command
  line or from the editor, so that building a program never executes
  it.
* It does not read a program: the way from a module or from the editor
  into Python does not exist. A program edited and saved in the editor
  keeps its Python description as it was; the code of a process edited
  there goes into the file that the Python description names, since the
  topology file names the same file, and survives the next build, while
  a change to the options, the connections or the specifications goes
  into ``program.yaml`` only and is written over by the next build.
* It shapes no tasks itself: a tasks file in Python is run by the
  engine when it prepares a run, and only shapes the tasks; the values
  of the options, the preamble and the bodies of ``post`` and
  ``reset_outfiles`` stay Bash, as the engine reads them. The manual
  mode of the editor, a whole ``define_opts`` written by hand, is not
  offered: a program that needs it is written as a module (see the
  :ref:`implem_bash` Section).
