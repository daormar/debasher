.. _exec:

Executing DeBasher Programs
===========================

This section explains how DeBasher programs are executed from the
command line, with ``debasher_exec``, and what every run leaves
behind: the structure of the output directory, the status of each
process, and how a program is run again, stopped or measured. In the
web interface the "Run" menu does all of this (see the :ref:`webui`
Section), with the same tools and the same output directory, so this
section is also what happens underneath when a program runs there.

.. _prg_exec:

Program Execution
-----------------

DeBasher incorporates a specific tool to execute programs called
``debasher_exec``. The command provides help about its available options
if executed as follows:

::

    $ debasher_exec --help

``debasher_exec`` only has two mandatory input options:

* ``--pfile <string>``: allows to define the DeBasher file specifying
  the program to be executed. A relative path is looked for in the
  current directory and, if it is not there, in the directories of the
  ``DEBASHER_MOD_DIR`` environment variable, as ``load_debasher_module``
  does for a module. The other tools that take a program file
  (``debasher_exec_process``, ``debasher_doc_mod`` and
  ``debasher_proc_dataset``) look for it in the same way.

* ``--outdir <string>``: specifies the name of the output directory.

Visualizing Command Line Options for a Program
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The command line options for the DeBasher program defined by the
``--pfile`` option should be provided to ``debasher_exec``. In order to
visualize such command line options, we can use the
``--show-cmdline-opts`` option. Assuming that we are working with the
"Hello World!" program described in the :ref:`quickstart_example`
Section, we can execute the following:

::

    $ debasher_exec --pfile debasher_hello_world.sh --outdir out --show-cmdline-opts

The output of the previous command incorporates a section related to the
program's input options. For the ``debasher_hello_world`` program,
this section contains the following:

::

   # Command line options for the program...
   CATEGORY: GENERAL
   -s <string> String to be displayed ('Hello World!' by default) [hello_world]

Command line options can be divided into different categories, being the
"GENERAL" category the default one. In this case, the "GENERAL" category
contains the ``-s`` option, that is used to provide the string to be
displayed by the ``debasher_hello_world`` program. Additionally, the
process receiving the ``-s`` option (``hello_world``) is specified
within square brackets.

An option given with the empty string as its value (``-s ""``) is
given, with that value. An option that takes a value cannot be
followed by another option: ``-s -verbose`` stops the preparation of
the run with an error that names both, since a value cannot start with
``-`` or ``--`` followed by an ASCII letter or an underscore.

Troubleshooting Process Options
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When working with complex programs, composed of many processes and
connections between them, it is useful to ensure that all the options
are passed correctly. ``debasher_exec`` incorporates two options that
are useful for that purpose:

* ``--check-proc-opts``: when providing this option, ``debasher_exec``
  only checks if all the options are available for the different
  processes that compose a program. If there are options missing, an
  error message is shown. Otherwise, the options are shown and the tool
  finishes its execution. It writes the options it computes into a
  temporary directory, not into the output directory.

* ``--validate``: this option carries out all the necessary steps to
  execute a DeBasher program, with the exception of the execution
  itself, and shows the current status of the different processes
  involved in the program. This includes the option checking process
  that can be done using the ``--check-proc-opts`` option. With the
  built-in scheduler, it also checks that the computational resources of
  each process fit the limits given with ``--builtinsched-cpus`` and
  ``--builtinsched-mem``. A program that passes the validation is not
  refused for its options or for the resources of a single task, but a
  run with ``--builtinsched-oneshot`` (every resident program runs so)
  is still refused when its tasks together do not fit. It
  also refuses a program with a process whose interpreter is not there
  (see the :ref:`implem_bash` Section), which ``--check-proc-opts`` and
  ``--show-cmdline-opts`` still accept, and a dependency other than
  ``none`` or ``after`` between processes linked by FIFOs (see the
  ``define_opt_deps`` method in the :ref:`implem_bash` Section). The
  files that describe an
  execution (see :ref:`outdstruct`) go into a temporary directory, which
  it removes, so it leaves those of an earlier execution as they were,
  and it leaves no graph in ``__graphs__``.

Executing Programs Using the Built-In Scheduler
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

``debasher_exec`` incorporates the ``--sched`` option to specify which
scheduler is used to orchestrate program execution. DeBasher
incorporates a built-in scheduler that can be activated for the "Hello
Word!" program as follows:

::

    $ debasher_exec --pfile debasher_hello_world.sh --outdir out --sched BUILTIN

When using the built-in scheduler, it is possible to specify the number
of CPUs and the amount of RAM that is available. For this purpose, the
following two options can be used:

* ``--builtinsched-cpus <int>``: this option allows to specify the
  number CPUs available for the built-in scheduler. A value of -1 (the
  default) means unlimited CPUs.

* ``--builtinsched-mem <int>``: indicates the amount of RAM in MB that
  can be used by the built-in scheduler. A value of -1 (the default)
  means unlimited memory.

* ``--builtinsched-oneshot``: launches every task of the program at
  once and returns without waiting for them, for programs whose
  processes are linked by FIFOs only. It refuses a dependency other than
  ``none`` or ``after``, a throttle below the number of tasks of an
  array, and a budget too small to launch every task at once. A
  resident program always runs in this mode.

A resident program (see the :ref:`resident` Section) always runs with
the built-in scheduler, which ``debasher_exec`` selects on its own for
it, refusing any other. Its processes are meant to run until they are
stopped, so ``debasher_exec`` launches all of them at once and returns
without waiting for them; the resources given with the two options
above must be enough for every task of every process together, each
task of an array counted on its own. When they are not,
``debasher_exec`` launches nothing and stops with an error that says
how many of the tasks fit.

If the script of a process cannot be written, or one of its tasks
cannot be launched, ``debasher_exec`` launches nothing more and stops
with an error, under either scheduler; what it launched before goes on,
and ``debasher_status`` shows it.

Executing Programs Using External Schedulers
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

It is also possible to combine ``debasher_exec`` with external
schedulers. Currently, DeBasher provides support for the well known
`Slurm scheduler <https://slurm.schedmd.com/>`__.

Slurm
"""""

To make Slurm work in combination with DeBasher, it is necessary to
install and properly configure the scheduler in the machine where
DeBasher will be executed. DeBasher looks for Slurm when a program is
run, not when it is installed: if the ``--sched`` option is not given,
``debasher_exec`` uses Slurm whenever ``sbatch`` is found in the
``PATH``, and the built-in scheduler otherwise.

If Slurm and DeBasher are correctly configured, then we can combine them
by means of the following command:

::

    $ debasher_exec --pfile debasher_hello_world.sh --outdir out --sched SLURM

A program that uses FIFOs cannot run with Slurm: the two ends of a FIFO
only meet when they run on the same machine, which the jobs of Slurm
are not bound to, so ``debasher_exec`` refuses such a program and
suggests the built-in scheduler.

A program on the built-in scheduler can still send some of its steps
to Slurm, through ``srun``: those of a sequential process declared with
``sched=SLURM`` (see :ref:`seq_processes`), and those run with
``seq_execute_slurm``. ``debasher_exec`` refuses to start a program
with a ``sched=SLURM`` sequential process on a machine where ``srun``
is not found, whatever ``--sched`` says.

.. _outdstruct:

Structure of the Output Directory
---------------------------------

When executing ``debasher_exec``, it is necessary to specify the output
directory of the program to be executed. Assuming that we executed a
DeBasher program composed of two processes ``a`` and ``b``, and that the
name of output directory generated by ``debasher_exec`` was ``out``, its
content will be:

.. code-block:: text

    out
    ├── a
    │   ├── file1
    │   ├── file2
    │   └── ...
    ├── b
    │   ├── file1
    │   ├── file2
    │   └── ...
    ├── __exec__
    │   ├── a
    │   │   ├── a
    │   │   ├── a.finished       (depends on execution status)
    │   │   ├── a.id             (depends on execution status)
    │   │   ├── a.opts           (depends on execution status)
    │   │   ├── a.sched_out      (depends on execution status)
    │   │   └── a.stdout         (depends on execution status)
    │   └── b
    │       ├── b
    │       ├── b.finished       (depends on execution status)
    │       ├── b.id             (depends on execution status)
    │       ├── b.opts           (depends on execution status)
    │       ├── b.sched_out      (depends on execution status)
    │       └── b.stdout         (depends on execution status)
    ├── __fifos__
    │   ├── a
    │   │   ├── fifo1
    │   │   ├── fifo2
    │   │   └── ...
    │   └── b
    │       ├── fifo1
    │       ├── fifo2
    │       └── ...
    ├── __graphs__
    │   ├── dependency_graph.dot
    │   ├── dependency_graph.eps
    │   ├── dependency_graph.pdf
    │   ├── process_graph.dot (optional)
    │   ├── process_graph.eps (optional)
    │   └── process_graph.pdf (optional)
    ├── .exec_context.sh
    ├── .sched_opts
    ├── command_line.sh
    ├── lock
    ├── program.fifos
    ├── program.opts
    ├── program.opts_old
    └── program.procspec

As it is shown in the previous diagram, ``debasher_exec`` generates the
following directories:

* ``a``: stores the output files of process ``a``. It is not mandatory
  that process ``a`` stores any output files, but the directory is
  automatically created by ``debasher_exec``.

* ``b``: it is the output directory of process ``b``.

* ``__exec__``: stores the execution information for the different
  processes. Contains one directory per process. For a given process,
  the following files are created:

     * ``<process_name>``: contains the code to be executed.
     * ``<process_name>.finished``: this file is created to signal that
       the execution of the process has finished.
     * ``<process_name>.id``: this file is created when the process
       starts its execution and contains an identifier of the process
       created by the scheduler being used.
     * ``<process_name>.opts``: the options the process received, one
       per line.
     * ``<process_name>.sched_out``: this file contains all the
       output related to process execution, including the error output
       and also some additional information generated by the scheduler.
       The standard output of the process is not included, it goes to
       the ``.stdout`` file only.
     * ``<process_name>.stdout``: this file contains the standard output
       generated by the execution of the process.

* ``__fifos__``: stores the FIFOs used by each process if there are
  any. See :ref:`implem_bash` Section for more details about using FIFOs in
  DeBasher programs.

* ``__graphs__``: contains certain graphical representations of the
  program being executed. ``debasher_exec`` always generates a
  dependency graph showing process dependencies
  (``dependency_graph.eps`` and``dependency_graph.pdf``
  file). Optionally, it can also generate a process graph
  (``process_graph.eps`` and ``process_graph.pdf``), where the
  relationship between process options is shown. The process graph is
  generated if the option ``--gen-proc-graph`` is provided to
  ``debasher_exec``. For both diagrams, a version in `Graphviz
  <https://graphviz.org/>`__ format is also provided (files with ``dot``
  extension). The graphs are left by an execution only: ``--validate``
  draws them too, but leaves none in the output directory.

In addition to this, the output directory will contain the following
files automatically generated by ``debasher_exec``:

* ``command_line.sh``: stores the working directory and the command
  line used to execute the program.

* ``lock``: ``debasher_exec`` locks this file while it prepares or runs
  the program, so that no two executions work on the same output
  directory at once.

* ``.exec_context.sh``: the variables and functions of the engine and
  the program, as ``debasher_exec`` loaded them, which the script of
  every process in ``__exec__`` starts with.

* ``.sched_opts``: the options of every task of every process, which
  each task reads when it starts.

* ``program.fifos``: contains information about the FIFOs used by the
  program. See :ref:`implem_bash` Section for more details about using FIFOs in
  DeBasher programs.

* ``program.opts``: contains, for each process, its number of tasks and
  the options of its first tasks (up to ten). At the end of an
  execution it is copied to ``program.opts_old``, and the next
  execution compares the two to run again the processes whose options
  changed, assuming that the tasks of an array are alike.

* ``program.procspec``: contains a specification for each process
  executed within a given program. Such specification incorporates the
  resources utilized by each process, as well as its process
  dependencies (e.g. the execution of a process may depend on the
  successful completion of another process).

``debasher_exec`` writes the files that describe an execution
(``.exec_context.sh``, ``.sched_opts``, ``command_line.sh``, the
``program.*`` files but ``program.opts_old``, and ``__graphs__``) into a
``.prep.<suffix>`` directory of the output directory first, and moves
them to their place only once the preparation of the execution has
passed all its checks: an execution refused while it is prepared, for
example for a missing option, leaves the files of the earlier execution
as they were. The directory is removed when the files are moved, or when
``debasher_exec`` exits before that; one left behind by a killed
``debasher_exec`` can be deleted.

The processes of a program use absolute paths into its output
directory. The tools that read an execution (``debasher_status``,
``debasher_stats``, ``debasher_get_stdout``, ...) work on the output
directory wherever it is, for instance after moving it elsewhere, but
``debasher_exec`` refuses to run a program again in an output directory
that was moved or copied from where it ran.

Process Status Visualization
----------------------------

During or after the execution of a DeBasher program, it is possible to
use the ``debasher_status`` tool to get information about the execution
status of each process involved in the program.

We can apply ``debasher_status`` to check the status of the process
involved in the "Hello World!" program previously executed:

::

    $ debasher_status -d out

The output of the tool is:

::

    PROCESS: hello_world ; STATUS: FINISHED
    * SUMMARY: num_processes= 1 ; finished= 1 ; inprogress= 0 ; unfinished= 0 ; unfinished_but_runnable= 0 ; todo= 0

``debasher_status`` show the status of the ``hello_world`` process as
``FINISHED``. The tool also shows a summary of the all of the processes
statuses involved in the program.

DeBasher works with the following process statuses:

* ``finished``: the process successfully completed execution.
* ``inprogress``: the process is currently being executed.
* ``unfinished``: the process did not successfully complete execution.
* ``unfinished_but_runnable``: the process has not completed execution
  yet, and is not being executed. However, it can resume its execution.
* ``todo``: the process has not yet started execution.

The ``debasher_status`` tool can also show the status of an individual
process using the ``-p`` option:

::

    $ debasher_status -d out -p hello_world

.. _rerun:

Running a Program Again
-----------------------

Executing ``debasher_exec`` again on the same output directory resumes
the program instead of starting it from scratch: it launches the
processes that did not finish (for an array, only the tasks that did
not finish, unless the array is one of the processes listed below), and
leaves alone the ones that finished. A process skipped
by its ``skip`` method counts as finished, and one whose ``skip`` method
fails (exit status 2 or more) fails. The output of
``debasher_exec`` lists, after "Printing list of processes to rerun",
the processes that it runs again whole, finished or not: every task of
such a process runs again, including the tasks of an unfinished array
that had already finished. They are these:

* a process with ``force=yes`` among its additional specifications
  (see the :ref:`implem_bash` Section), which runs in every execution;
* a process whose options changed since the last execution, as
  ``program.opts`` and ``program.opts_old`` give them (see
  :ref:`outdstruct`). The options are compared, not the files they
  name: a file changed in place under the same path is not a change;
* with the ``--rerun-outdated-procs`` option of ``debasher_exec``, a
  process whose code is older than the modules of the program;
* a process at one end of a FIFO whose other end runs again, since both
  ends have to run together;
* a process that writes a FIFO that no process of the program reads
  (one read outside the program, as with "Talk to FIFOs" in the web
  interface), once it has finished: DeBasher cannot tell whether the
  reader outside got what it needed, so it runs that process in every
  execution;
* a process that ran after another one that has not finished: it runs
  again on what that one leaves this time. This happens with the
  dependency types that let a process run after another one that
  failed, ``afterany`` and ``after``, and with ``afterok`` within a
  list joined by ``?``. For instance, if ``report`` depends on ``grade``
  with ``afterany``, and ``grade`` fails, ``report`` still runs, with
  what ``grade`` left; once the problem is fixed, the next execution
  runs ``grade`` and then ``report`` again. A process that depends on
  another with ``afternotok``, which is there for when it fails, is
  not run again. Under Slurm, if this execution cannot submit that
  other process (because its own dependencies can no longer hold), it
  does not submit the dependent one either: the dependent keeps its
  files but is no longer counted as finished, and runs again in a later
  execution that launches the process it depends on.

Every process that depends on one of those runs again too, and so on.

To run the whole program again from scratch, empty its output
directory first (in the web interface, "Reset output directory" in the
Run menu).

Program Stop
------------

When a DeBasher program is being executed, it is possible to stop a
given process or the whole program by means of the ``debasher_stop``
tool.

For this purpose, the name of the output directory and, optionally, the
name of a specific process should be provided.

The following command stops the ``hello_word`` process that compose the
"Hello World!" program that was mentioned above:

::

    $ debasher_stop -d out -p hello_world

To stop the whole program, the ``-p`` option is omitted:

::

    $ debasher_stop -d out

Program Statistics Generation
-----------------------------

The ``debasher_stats`` tool allows to generate statistics for a DeBasher
program. Specifically, the tool report process statuses and the elapsed
time in seconds until completion (if the process was executed).

Again, the execution of this tool requires to provide the output
directory of the program and, optionally, the name of the process for
which we want to obtain the statistics.

This command shows statistics for the ``hello_world`` process that
belongs to the "Hello World!" program that we executed at the
:ref:`prg_exec` Section:

::

    $ debasher_stats -d out -p hello_world

To get statistics for all processes, we can simply type:

::

    $ debasher_stats -d out
