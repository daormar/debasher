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

    $ debasher_exec_process [-q] <prgfile> <processname> [-- [<process_opts>]]

``debasher_exec_process`` loads the module given by ``<prgfile>`` and
executes a single one of its processes, ``<processname>``, directly in
the foreground, bypassing ``debasher_exec`` and any scheduler. It is
mainly useful to debug a process implementation in isolation.

* If ``-- <process_opts>`` is omitted, the tool does not execute the
  process. Instead, it prints the process's option documentation (the
  same information ``debasher_doc_mod --show-opts`` would show for
  it) and exits.

* If ``--`` is given, everything after it is passed as the process's
  own command line options, and the process is executed. The tool
  then exits with the exit status of the process.

* ``-q`` drops the progress messages of the tool (such as the
  ``Loading module ...`` lines), so that the standard error holds only
  what the process and the module write, and the errors.

debasher_test
^^^^^^^^^^^^^

::

    $ debasher_test [--conda-support] [--docker-support] <prgdir>

``debasher_test`` runs the business tests of a program: tests of what
each process does with the values of its options, run on its own
with ``debasher_exec_process``, outside any run. It applies to a
program in a directory of its own, ``<prgdir>``, of any name. For a
program saved by the web UI, the program file is the script named
after the program in its metadata (``.debasher/program.json``); for a
program written by hand, it is the only ``*.sh`` file at the top of
``<prgdir>``, and the tool refuses a directory with several. The tests are the
files ``<prgdir>/test/*.bats``, which the tool runs with bats, and, for
the nodes of a resident program, the files ``<prgdir>/test/test_*.py``,
which it runs with pytest.

A bats test loads the helper library whose path the tool exports as
``DEBASHER_BATS_HELPERS``, and runs a process with
``debasher_process <processname> [<process_opts>]``. Since no output
directory is involved, the test gives every option the process reads,
with the files it writes placed under the temporary directory of the
test. For example, for a process ``greet`` that writes a greeting
into the file given by ``-outf``::

    load "${DEBASHER_BATS_HELPERS}"

    @test "greet writes the greeting into its file" {
        run debasher_process greet -text Ann -secs 0 \
            -outf "${BATS_TEST_TMPDIR}/greeting.txt"
        [ "${status}" -eq 0 ]
        [ "$(cat "${BATS_TEST_TMPDIR}/greeting.txt")" = "Hello, Ann!" ]
    }

A node of a resident program is tested without running it: no FIFO is
opened and no ``Supervisor`` is involved. A pytest test builds the node
with ``load_node`` of the module ``debasher_runtime_testing``, naming
the ports whose traffic it checks, gives it packets with ``feed`` and
reads what it sent on a port with ``sent``. ``restart`` builds the node
again from its node state, as recovery after a crash does, and fails
when the restored node does not capture the same state. For example,
for a node ``Accumulate`` that sends the running sum of the numbers it
receives::

    from debasher_runtime_testing import load_node

    def test_running_sum():
        node = load_node("Accumulate", inputs=["numbers"], outputs=["outsum"])
        node.feed("numbers", 3)
        node.feed("numbers", 4)
        assert node.sent("outsum") == [3, 7]

    def test_restart_keeps_the_sum():
        node = load_node("Accumulate", inputs=["numbers"], outputs=["outsum"])
        node.feed("numbers", 3)
        node = node.restart()
        node.feed("numbers", 4)
        assert node.sent("outsum") == [7]

``load_node`` also takes ``opts``, the options of the node by name.
A node that observes the outside world, such as a
``DirectoryWatcher``, is tested with ``observe``: it runs the
``observe`` method of the node once and returns what it brought in,
which the node then processes as in a run. The test can change the
outside world between two calls, for example put a file in the
directory that a ``DirectoryWatcher`` watches (given with
``opts={"watchdir": ...}``) and observe twice, since a file counts
only once it has stayed the same for two observations in a row. A
``ProgramLauncher`` and the ``Supervisor`` cannot be tested this way.

A process that activates a Conda environment runs in it in a test as
in a run. ``--conda-support`` and ``--docker-support`` create the Conda
environments and pull the Docker images that the processes declare
before the tests, as ``debasher_exec`` does before a run with the same
options; without them, they have to exist already, and a test of such
a process starts with ``debasher_skip_without_conda_env <name>``, which
skips it, with its reason, where conda or the environment is missing.
**Run tests** in the web interface passes those options when the
program has conda or docker support.

The exit status of ``debasher_test`` is 0 when every test passed, 1
when a test failed, 2 when the tests could not be run (for instance,
``<prgdir>`` has no program file, or bats or pytest is not installed)
and 77 when the program has no tests. ``DEBASHER_BATS`` and
``DEBASHER_PYTEST`` give the bats and the pytest to run instead of
those found when DeBasher was configured. Running the tests writes
nothing into ``<prgdir>``. The programs ``webui_batch_greet`` (bats
tests), ``webui_running_sum`` and ``webui_watch_tally`` (pytest
tests, the second of a ``DirectoryWatcher``), installed under
``<prefix>/share/debasher/webui_programs``, carry examples.

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
process. Like ``debasher_stats`` and ``debasher_stop``, it takes the
processes of the program from ``program.procspec`` in the output
directory, not from the module, so it reports the processes that ran
even if the module changed since.

debasher_stats
^^^^^^^^^^^^^^^

``debasher_stats`` reports, for the processes of a DeBasher program,
their status and the elapsed time in seconds until completion. For an
array process, it gives the total time of its finished tasks followed by
the time of each one (``<total> : <idx>-><time> ; ...``), and the total
is ``UNKNOWN`` when the time of any of its tasks is. It is
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

Resident Program Control
------------------------

The tools below act on a resident program, running or stopped, given
its output directory with ``-d <string>``. The :ref:`resident` Section
explains what they are for; ``debasher_status`` also works on a
resident program.

debasher_stop_resident
^^^^^^^^^^^^^^^^^^^^^^

``debasher_stop_resident`` stops a running resident program in order:
every node saves its state in one last snapshot and then stops, so
that the next ``debasher_exec`` on the same output directory resumes
it. ``debasher_stop`` would kill every process at once instead.

::

    $ debasher_stop_resident -d <string> [-x <string>] [--timeout <int>]

* ``-x <string>``: comma-separated nodes to leave running: a process
  name (every task, if it is an array) or ``<process>:<idx>`` (one
  task of an array).
* ``--timeout <int>``: seconds to wait for the stop to complete (60 by
  default), after which the tool falls back to ``debasher_stop`` and
  fails.

debasher_snapshot_resident
^^^^^^^^^^^^^^^^^^^^^^^^^^

``debasher_snapshot_resident`` takes a snapshot of a running resident
program: every node saves a checkpoint and prunes its input log.

::

    $ debasher_snapshot_resident -d <string> [--timeout <int> | --every <int>]

* ``--timeout <int>``: seconds to wait for the snapshot to complete at
  every node (60 by default).
* ``--every <int>``: take a snapshot every ``<int>`` seconds, until no
  node of the program is running.

debasher_reset_resident
^^^^^^^^^^^^^^^^^^^^^^^

``debasher_reset_resident`` takes a stopped resident program back to
its first run: it moves the checkpoints, input logs, notices and
process outputs of every node under ``__reset__/<timestamp>/`` in the
output directory, so that the next ``debasher_exec`` starts every node
afresh. It refuses while any process of the program is running.

::

    $ debasher_reset_resident -d <string> [--delete]

* ``--delete``: delete the state of the nodes instead of setting it
  aside.

debasher_inspect_resident
^^^^^^^^^^^^^^^^^^^^^^^^^

``debasher_inspect_resident`` shows, in JSON, what a node of a resident
program keeps, and changes nothing. It works on a running program as
well as on a stopped one.

::

    $ debasher_inspect_resident -d <string> -p <string> [-t <int>] <command>
    $ debasher_inspect_resident -d <string> notices

``-p <string>`` gives the process and ``-t <int>`` the index of the
task, for an array process. The commands are:

* ``summary``: the state of the node (alive, down, finished or not
  launched), its checkpoints, the size of its input log against its
  limit, its health and its notice.
* ``checkpoint <int>``: a checkpoint that the node keeps, given by its
  epoch, as ``summary`` lists them.
* ``log [--port <string>] [--last <int>]``: the latest records of the
  input log (100 by default), or those of one port.
* ``runs``: the batch runs of a launcher node, with their states.
* ``notices``: the notices of every node of the program (with ``-d``
  alone).

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
:ref:`implem` Section). Passing ``--watch`` follows the file as it
grows (like ``tail -f``) instead of printing its current contents and
exiting, which is useful for monitoring a process that is still
running.

debasher_get_sched_out
^^^^^^^^^^^^^^^^^^^^^^^

``debasher_get_sched_out`` shows the scheduler output for a process,
which includes its error output together with scheduling-related
information, and is therefore useful for debugging. Its standard output
is not included: ``debasher_get_stdout`` shows it.
It is introduced in the :ref:`quickstart_example` Section. As with
``debasher_get_stdout``, it takes ``-d <string>`` and ``-p <string>``,
plus an optional ``-t <int>`` to select an individual task of a task
array, and supports ``--watch`` to follow the file as it grows instead
of printing its current contents and exiting.

debasher_get_fifo_mirror
^^^^^^^^^^^^^^^^^^^^^^^^^

``debasher_get_fifo_mirror`` shows the mirrored content of a process's
FIFO, i.e. a copy of everything the owning process wrote into it,
provided the FIFO was declared with the mirroring option of
``define_fifo_opt``/``define_fifo_opt_generator`` on an output option
(see the :ref:`implem` Section for more information about FIFOs) and
the owning process has already run.

Its options are:

* ``-d <string>``: output directory for program processes.
* ``-p <string>``: name of the process owning the mirrored FIFO.
* ``-f <string>``: name of the FIFO, as given to ``define_fifo_opt``.
* ``-t <int>``: accepted for uniformity with ``debasher_get_stdout``
  and ``debasher_get_sched_out``, and ignored: the name of a FIFO
  already tells apart the FIFOs of the tasks of an array.
* ``--watch``: follow the file as it grows (like ``tail -f``) instead
  of printing its current contents and exiting.

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
(omitted, every process the module defines is documented). The report
always opens with the module's name and description, followed by a
``Program Type`` section giving the program type (``general`` or
``resident``). The remaining options select which information is
included in the report:

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

``debasher_webui`` launches the DeBasher web interface (see the
:ref:`webui` Section): a server that exposes the workflow API and,
once the frontend has been built and installed, also serves it, so
that both are available from a single process at
``http://<host>:<port>/``. The server obeys only the requests that
carry its token: it prints the address of the web interface with the
token (``http://<host>:<port>/#token=<token>``), to open once in a
browser, and leaves the token for ``debasher_mcp`` in a file readable
only by the user (``webui-<port>.token`` under
``$XDG_RUNTIME_DIR/debasher``, or ``~/.debasher/run``).

::

    $ debasher_webui [--host <string>] [--port <int>] [--token <string>]

* ``--host <string>``: address to bind to (``127.0.0.1`` by default).
* ``--port <int>``: port to listen on (``8000`` by default).
* ``--token <string>``: the token, instead of a new random one at every
  start. The ``DEBASHER_WEBUI_TOKEN`` environment variable gives it as
  well, without showing it to the other users of the machine in the
  list of processes.

The tool requires the ``fastapi`` and ``uvicorn`` Python packages for
whichever ``python3`` interpreter is first found on ``PATH``. If they
are not installed, ``debasher_webui`` prints instructions for creating
a virtual environment, installing them there, and either activating
that environment before running the tool or pointing it directly at
the environment's interpreter through the ``DEBASHER_WEBUI_PYTHON``
environment variable.

debasher_mcp
^^^^^^^^^^^^

``debasher_mcp`` runs the MCP server of DeBasher, which offers to an AI
agent, such as Claude Code, what the web interface offers to a person:
reading a program, editing it, running it and following its run,
writing and running its business tests (see `debasher_test`_), and
managing the files of its home directory, as tools
of the Model Context Protocol. The agent starts it and talks to it over its
standard input and output. It is a client of the server that
``debasher_webui`` launches, which has to be running, and it edits programs
with the same rules as the editor of the web interface: each tool that
edits a program applies its edits whole or not at all, refuses a save over
changes saved elsewhere since it read the program, and, called with
``dry_run``, answers with what it would change and saves nothing.

::

    $ debasher_mcp [--url <string>] [--claude-settings]

* ``--url <string>``: URL of the server of the web interface
  (``http://127.0.0.1:8000`` by default).
* ``--claude-settings``: prints the settings of Claude Code that
  `debasher_claude`_ passes, the permissions of the tools of the server,
  and exits.

It sends the token of the server with every request, which it reads by
itself from the file that ``debasher_webui`` leaves for its port (see
`debasher_webui`_), so neither its command line nor its registration
with an agent holds the token. It does so only for a server on the local
machine that is still running.

The tool needs Node.js: it runs under the ``node`` named by the
``DEBASHER_MCP_NODE`` environment variable, or else the one found when
DeBasher was configured, or else the first one on ``PATH``. To make it
available to Claude Code, for example::

    $ claude mcp add debasher -- debasher_mcp --url http://127.0.0.1:8000

To start Claude Code on one program, with this server already set up,
see `debasher_claude`_.

debasher_claude
^^^^^^^^^^^^^^^

``debasher_claude`` starts Claude Code on a program saved with the web
interface, in its home directory, with everything DeBasher gives it: the
MCP server (see `debasher_mcp`_) talking to the server of the web
interface, the permissions of its tools, and the plugin of DeBasher,
whose skills help with the web interface and DeBasher
(``/debasher:help``), with the design of a program, its processes and
their connections (``/debasher:design``), and with the code of the
processes and their tests (``/debasher:implement``). The editor of the
web interface, if the program is open there, loads what Claude Code
saves. It uses your own installation and account of Claude Code.

::

    $ debasher_claude --home-dir <string> [--url <string>]
                      [--mode <string>] [--prompt <string>] [--dry-run]
                      [-- <claude options>]

* ``--home-dir <string>``: home directory of the program.
* ``--url <string>``: URL of the server of the web interface
  (``http://127.0.0.1:8000`` by default).
* ``--mode <string>``: the skill the session starts with, ``help``,
  ``design`` or ``implement``. Any of them can be called later in the
  same session.
* ``--prompt <string>``: the first message of the session, given to the
  skill of the mode when there is one.
* ``--dry-run``: prints the command that starts Claude Code instead of
  running it.

What follows ``--`` is passed to Claude Code as it is, and the
``DEBASHER_CLAUDE_CMD`` environment variable names its command
(``claude`` by default). Tools that only read run without asking; those
that edit, validate, test or run the program ask until you allow them,
and those that delete files or program state, or stop or restart
something, always ask. Claude Code may not edit by hand what DeBasher
keeps in ``.debasher``. For example::

    $ debasher_claude --home-dir ~/programs/my_program --mode design
