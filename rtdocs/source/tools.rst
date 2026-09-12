.. _tools:

DeBasher Tools
==============

Besides the Bash API used to define programs (see the :ref:`API`
Section), DeBasher installs a set of standalone command-line tools
that execute, monitor, inspect and manage DeBasher programs. This
section describes each of these tools. Some of them are already
introduced, in context, in the :ref:`quickstart_example` and
:ref:`exec` Sections; they are described here again for completeness.
Every tool accepts a ``--help`` option that prints a summary of its
usage.

Program Execution
------------------

debasher_exec
^^^^^^^^^^^^^

``debasher_exec`` is the main tool used to execute a DeBasher program.
It is described in detail in the :ref:`exec` Section, which covers,
among other topics, its two mandatory options (``--pfile <string>``,
the module file defining the program to execute, and ``--outdir
<string>``, the output directory), how to select and configure a
scheduler, how to inspect a program's command line options before
running it, and the structure of the output directory that the tool
generates.

debasher_exec_process
^^^^^^^^^^^^^^^^^^^^^^

::

    $ debasher_exec_process <prgfile> <processname> [-- [<process_opts>]]

``debasher_exec_process`` loads the module given by ``<prgfile>`` and
executes a single one of its processes, ``<processname>``, directly in
the foreground, bypassing ``debasher_exec`` and any scheduler. It is
mainly useful to debug a process implementation in isolation.

* If ``-- <process_opts>`` is omitted, the tool does not execute the
  process. Instead, it prints the process's option documentation (the
  same information ``debasher_doc_mod --show-opts`` would show for
  it) and exits.

* If ``--`` is given, everything after it is passed as the process's
  own command line options, and the process is executed.

debasher_proc_dataset
^^^^^^^^^^^^^^^^^^^^^^

``debasher_proc_dataset`` generates, for a set of dataset samples, one
``debasher_exec`` command line per sample. It does not execute the
program itself: it prints the generated command lines to standard
output, so that they can be inspected, redirected to a script, or
piped into a job submission tool.

Its options are:

* ``--pfile <string>``: module file defining the program to be
  executed for each sample.
* ``--sched <string>``: scheduler used to execute the program.
* ``--prg-sopts <string>``: file containing, one line per sample, the
  program options specific to that sample (e.g. its input and output
  file names). This option is mandatory.
* ``--prg-opts <string>``: file containing program options common to
  every sample (e.g. resource-related options), appended to each
  generated command line.
* ``--dflt-nodes <string>``: default set of nodes used to execute the
  program.

For example, given a ``samples.txt`` file with one line of
sample-specific options per sample:

::

    $ debasher_proc_dataset --pfile debasher_file_example.sh --sched SLURM \
        --prg-sopts samples.txt --prg-opts common_opts.txt > run_samples.sh

Process Monitoring and Control
-------------------------------

debasher_status
^^^^^^^^^^^^^^^^

``debasher_status`` shows the execution status of the processes of a
DeBasher program. It is described in the :ref:`exec` Section, in its
`Process Status Visualization` part. In addition to the ``-d
<string>`` (output directory) and ``-p <string>`` (name of a specific
process) options covered there, ``debasher_status`` also accepts
``-i``, which additionally shows the scheduler id assigned to each
process.

debasher_stats
^^^^^^^^^^^^^^^

``debasher_stats`` reports, for the processes of a DeBasher program,
their status and the elapsed time in seconds until completion. It is
described in the :ref:`exec` Section, in its `Program Statistics
Generation` part. As with ``debasher_status``, the output directory is
given with ``-d <string>`` and, optionally, a single process can be
selected with ``-p <string>``.

debasher_stop
^^^^^^^^^^^^^^

``debasher_stop`` stops the execution of a running DeBasher program,
or of a single one of its processes. It is described in the
:ref:`exec` Section, in its `Program Stop` part. The output directory
is given with ``-d <string>``; a specific process to stop can be given
with ``-p <string>``, and is otherwise omitted to stop the whole
program.

debasher_reformat_status
^^^^^^^^^^^^^^^^^^^^^^^^^

``debasher_reformat_status`` reformats the output of ``debasher_status``
into a single, fixed-width status line, one column per process. This
is convenient for compact monitoring or logging, since it condenses
the multi-line output of ``debasher_status`` into one row of process
names and one row (or, optionally, just one row) of their statuses.

By default the tool reads ``debasher_status`` output from standard
input, so both tools are normally combined with a pipe:

::

    $ debasher_status -d out | debasher_reformat_status -f 1 -l 12

Its options are:

* ``-p <string>``: file containing ``debasher_status`` output to
  reformat; if not given, the input is read from standard input.
* ``-f <int>``: output format. ``1`` prints a header row (process
  names) followed by a row of statuses; ``2`` prints only the row of
  statuses.
* ``-l <int>``: field length; every process name and status is
  padded or truncated to this length.
* ``-e <string>``: comma-separated list of process names to exclude
  from the output.

Retrieving Process Output
---------------------------

debasher_get_stdout
^^^^^^^^^^^^^^^^^^^^

``debasher_get_stdout`` shows the standard output generated by a
process. It is introduced in the :ref:`quickstart_example` Section.
Its ``-d <string>`` and ``-p <string>`` options select, respectively,
the program's output directory and the process whose standard output
should be shown. An additional ``-t <int>`` option can be used to
select an individual task when the process is part of a task array
(see the description of the ``generate_opts`` method in the
:ref:`implem` Section).

debasher_get_sched_out
^^^^^^^^^^^^^^^^^^^^^^^

``debasher_get_sched_out`` shows the scheduler output for a process,
which includes its standard and error output together with
scheduling-related information, and is therefore useful for debugging.
It is introduced in the :ref:`quickstart_example` Section. As with
``debasher_get_stdout``, it takes ``-d <string>`` and ``-p <string>``,
plus an optional ``-t <int>`` to select an individual task of a task
array.

debasher_get_fifo_mirror
^^^^^^^^^^^^^^^^^^^^^^^^^

``debasher_get_fifo_mirror`` shows the mirrored content of a process's
FIFO, i.e. a copy of everything written to or read from it, provided
the FIFO was declared with the mirroring option of
``define_fifo_opt``/``define_fifo_opt`` (see the :ref:`implem`
Section for more information about FIFOs) and the owning process has
already run.

Its options are:

* ``-d <string>``: output directory for program processes.
* ``-p <string>``: name of the process owning the mirrored FIFO.
* ``-f <string>``: name of the FIFO, as given to ``define_fifo_opt``.
* ``-t <int>``: index of the task array, if the owning process is part
  of one.

Module and Process Documentation
-----------------------------------

debasher_doc_mod
^^^^^^^^^^^^^^^^^

``debasher_doc_mod`` generates Markdown documentation for a module and
its processes directly from their code, without having to read
through the module's own source file. It is introduced in the
:ref:`implem` Section:

::

    $ debasher_doc_mod -m debasher_file_example.sh -s file_writer \
        --show-opts --show-opthnd --show-impl --show-specs --show-meths

The ``-m <string>`` option gives the module file, and the optional
``-s <string>`` option restricts the output to a single process
(omitted, every process the module defines is documented). The
remaining options select which information is included in the report:

* ``--show-opts``: process options, as documented by ``explain_opts``.
* ``--show-opthnd``: the option-handler method actually used
  (``define_opts``, or the ``generate_opts_size``/``generate_opts``
  pair).
* ``--show-impl``: the process implementation itself.
* ``--show-specs``: the process's computational and additional
  specifications.
* ``--show-meths``: the names of the `Process Methods` the process
  defines.
* ``--show-meths-with-code``: like ``--show-meths``, but prints the
  full code of each method instead of just its name.
* ``--show-vars``: process variables information.
* ``--show-vars-with-values``: like ``--show-vars``, but also shows
  the value of each variable (only meaningful for a non-Bash
  implementation).
* ``--show-shdirs``: shared directories defined directly by the
  module.
* ``--show-all-shdirs``: every shared directory reachable from the
  program (the module plus every module it loads, transitively).
* ``--show-all-envvars``: every variable newly bound while loading the
  module (the module plus every module it loads, transitively),
  excluding names already set beforehand and the engine's own internal
  bookkeeping.
* ``--resolve-var <string>``: shows the value of a variable already
  set after loading the module; can be given multiple times.

Web Interface
----------------

debasher_webui
^^^^^^^^^^^^^^^

``debasher_webui`` launches the DeBasher web interface: a server that
exposes the workflow API and, once the frontend has been built and
installed, also serves it, so that both are available from a single
process at ``http://<host>:<port>/``.

::

    $ debasher_webui [--host <string>] [--port <int>]

* ``--host <string>``: address to bind to (``127.0.0.1`` by default).
* ``--port <int>``: port to listen on (``8000`` by default).

The tool requires the ``fastapi`` and ``uvicorn`` Python packages for
whichever ``python3`` interpreter is first found on ``PATH``. If they
are not installed, ``debasher_webui`` prints instructions for creating
a virtual environment, installing them there, and either activating
that environment before running the tool or pointing it directly at
the environment's interpreter through the ``DEBASHER_WEBUI_PYTHON``
environment variable.
