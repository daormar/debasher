.. _webui:

DeBasher Web Interface
======================

The web interface lets you build, run and observe a DeBasher program
from a browser, without writing its module by hand. Each process is a
box on a canvas, each connection between an output and an input is an
edge between two boxes, and the web interface translates the drawing
into a DeBasher module, the *generated script*, which it runs with the
same tools described in the previous sections. It knows both types of
program, general and resident (see the :ref:`resident` Section).

This section explains how to start the web interface, how to build a
program with it, and how to run and observe general and resident
programs.

Starting the Web Interface
--------------------------

The web interface is installed with the rest of DeBasher, unless
``configure`` is given ``--disable-frontend``. Building it needs
``npm`` and Node.js 22.12 or newer; ``configure`` looks for ``node``
next to ``npm``, and a different one is given with
``NODE=/path/to/node``.

Its server needs the ``fastapi`` and ``uvicorn`` Python packages, which
``make install`` does not install. They are installed once, in a
virtual environment:

::

    $ python3 -m venv ~/debasher-venv
    $ ~/debasher-venv/bin/pip install -r <prefix>/share/debasher/api/requirements.txt

``debasher_webui`` then starts the server, with that virtual
environment activated (or with ``DEBASHER_WEBUI_PYTHON`` set to the
interpreter of the environment):

::

    $ source ~/debasher-venv/bin/activate
    $ debasher_webui
    $ debasher_webui --host 127.0.0.1 --port 8000

and the web interface is at ``http://127.0.0.1:8000/``. The server
runs in the foreground until it is stopped, for example with
``Ctrl-C``; stopping it stops no program that it launched.

The server has no authentication, and runs every program as the user
who started it: whoever can reach it can run anything as that user.
By default it listens only on ``127.0.0.1``, the local machine; to
reach it from another machine, forward the port over SSH rather than
giving ``--host`` a public address.

Where a Program Lives
---------------------

A program built with the web interface uses two directories:

* Its **home directory**, where the web interface saves it: the
  program as the web interface sees it, in ``.debasher/program.json``;
  the generated script, ``<name>.sh``, a DeBasher module like any
  other, which ``debasher_exec`` and the rest of the tools can use
  without the web interface; and the files that the program needs,
  which the "Program files" panel manages.
* Its **output directory**, where the engine writes when the program
  runs (see the :ref:`outdstruct` Section).

The two must be different directories. A program is saved with the
"Save" button, and loaded again from its home directory with "Load
program". Nothing is kept in the browser: a program that has not been
saved is lost when its tab is closed.

The Home Screen
---------------

The home screen offers three ways to open a program:

* **Create new program** asks for its name and its type, "General
  program" or "Resident program". The type cannot be changed later.
* **Load program** opens a program saved with the web interface, from
  its home directory.
* **Import program** opens a DeBasher module written by hand (a
  ``.sh`` file), which the engine loads and describes. The
  ``DEBASHER_MOD_DIR`` field says where to find the modules that it
  loads. The imported program opens in the editor, and is saved into a
  home directory of its own.

Import keeps the processes, their options and connections, their code,
methods and specifications, and the descriptions, but not the layout,
nor the comments of the option definitions, which come back written the
way the web interface writes them. A module that is maintained by hand
is best kept by hand; import is the way into the web interface for a
module written without it.

The examples of the ``data/webui_programs`` folder, installed under
``<prefix>/share/debasher/webui_programs``, are programs built with the
web interface, one home directory each, which "Load program" opens.
An installed one is usually not writable, so save it into a home
directory of your own before changing it.

Building a Program
------------------

The editor shows the canvas, with the "Inspector" on its right, which
edits the selected process, and a toolbar above:

* **Env vars**: the environment of the engine's tools, in particular
  ``DEBASHER_MOD_DIR``, where the modules that the preamble loads are
  looked for.
* **Preamble**: Bash code written at the top of the generated script,
  typically ``load_debasher_module`` lines for the modules whose
  processes the program uses.
* **Description**: the description of the program.
* **Shared dirs**: the shared directories that the program declares.
* **Sequential processes**: the code that the processes run as steps
  (see `Sequential Processes`_ below). A resident program has none.
* **Add process**: adds a process, by name. The names of the processes
  that the modules of the preamble define are suggested, and choosing
  one brings its options and code in.
* **Add program**: brings every process of another program saved with
  the web interface into this one (see `Groups`_ below).
* **Save**, **Run** (the menu described in `Running a General
  Program`_ below) and **Close**, which goes back to the home screen.

The name of the program, at the left of the toolbar, can be edited in
place. It names the generated script and prefixes the functions of the
module.

Processes and Options
^^^^^^^^^^^^^^^^^^^^^

Selecting a process on the canvas shows it in the Inspector, where its
name, description, options, code and specifications are edited. The
Delete key removes the selected process or connection.

An option is added by its label, which starts with a dash: a label
that starts with ``-out`` or ``--out`` makes an output, and any other
an input, as the engine requires. Its editor sets:

* its **data type** (int, float, string or file, or "None (flag)" for
  an input that takes no value);
* whether it is a **command line** option, given when the program is
  run (and whether it is mandatory), or whether its value is taken
  from an attribute of the **process specifications**, such as
  ``cpus``;
* its **channel**, how its value is delivered: a direct value; a
  value descriptor, the path of a file where an output writes a value
  for the processes connected to it; a FIFO; or a shared directory;
* its **value**, for a direct value, which is a Bash word such as
  ``10`` or ``${idx}``, written into the generated script as it is.

The **code** of a process is written in Bash, Python, Perl, R or
Groovy, and its other methods (``skip``, ``post``, ``conda_envs``,
``docker_imgs``, and the rest of the process methods described in the
:ref:`implem` Section) are edited with "Configure additional methods".
The **specifications** are the computational ones (CPUs, memory and
time) and, for a general program, the additional ones: process
dependencies, ``force``, and an alias or an external alias.

Options Handler Modes
^^^^^^^^^^^^^^^^^^^^^

The options handler of a process says how it defines its options, and
so how many tasks it runs:

* **standard**: one task.
* **array**: one task for each element of a Bash array named ``array``,
  which code written with "Configure" builds; the values of the options
  can use its index, ``${idx}``.
* **generator**: one task for each index from 0 to the number that
  code written with "Configure" prints.
* **manual**: the option definition function is written whole, by
  hand (general programs only).

An option of a standard process whose label ends in ``ith``, such as
``-outfith``, is a *fanout family*: it stands for as many numbered
options (``-outf0``, ``-outf1``, ...) as a command line option of the
same process says, and it connects to an array or generator process,
one option for each task.

Connections
^^^^^^^^^^^

A connection is drawn by dragging from the handle of an output, along
the bottom of a process, to the handle of an input, along the top of
another process or of the same one. The canvas accepts a connection
only when the engine would:

* an input takes a single connection, and none at all if it is a flag,
  a command line option or an option taken from the process
  specifications (those have a hollow handle, tagged ``cmdline``,
  ``spec`` or ``flag``);
* a connection that is not from a FIFO makes the input wait for the
  output's process to finish, so a cycle made only of such connections
  is refused; a cycle through a FIFO is allowed, since both ends of a
  FIFO run at the same time.

Connections from a FIFO are dashed, and one from a fanout family to
the tasks of an array widens into a wedge. The "Legend" in the corner
of the canvas explains every mark, color and kind of edge.

Groups
^^^^^^

"Add program" brings in every process of another program saved with
the web interface. In a general program they form a *group*, drawn
with a border of its own color and a badge, which the generated script
declares with a single ``add_debasher_program`` of the other program's
module, so that the other program stays the one place where they are
defined. Changing a process of the group, removing one, or connecting
one of its inputs to something new asks first, and then dissolves the
group: its processes are then written into the generated script one by
one. The same holds for a sequential process that the group brought in.

Sequential Processes
^^^^^^^^^^^^^^^^^^^^

The sequential processes of a general program (see :ref:`steps`) are
not drawn on the canvas: they have no options and no connections. The
"Sequential processes" dialog of the toolbar lists them, adds, renames
and removes them, and edits the one selected: its name, description,
computational specifications, alias, and code, in Bash or in another
language. A new one starts with a Bash function of its name that does
nothing. Saving the dialog checks the names (not blank, not that of a
process or of another sequential process, valid as a process name) and
that the Bash code of each one defines a function of its name, which
the step runs.

The web interface does not read the code of the processes: renaming or
removing a sequential process does not change the calls to
``seq_execute`` that name it. "Add program" brings the sequential
processes of the other program into the same group as its processes.

Program Files
^^^^^^^^^^^^^

The "Program files" panel, in the corner of the canvas, manages the
files of the home directory: it shows, edits, uploads, renames, moves
and deletes them, and creates directories. It never shows the files
that belong to the engine or to the web interface, and the generated
script is shown read only, since every save writes it again.

Running a General Program
-------------------------

The "Run" menu of the toolbar runs the program and acts on its run:

* **Set output directory**, **Set execution options** (the scheduler
  and the other options of ``debasher_exec``) and **Set program
  options** (the values of the command line options).
* **Check program options** and **Validate program** run
  ``debasher_exec --check-proc-opts`` and ``debasher_exec --validate``
  (see the :ref:`exec` Section), and show what they print.
* **Run tests** saves the program and runs its business tests, the
  files ``test/*.bats`` and ``test/test_*.py`` of its home directory,
  with ``debasher_test`` (see the :ref:`tools` Section), and shows
  whether they passed and what they printed. It is not offered while a
  run is in progress. The right-button menu of a process offers **Add
  test**, which asks for the name of a new test file in ``test/`` (it
  proposes one), says what it will write, and, once confirmed, writes a
  first test for that process and opens it in the program files panel:
  a test that runs the process with placeholders for its options, or,
  for a node of a resident program, one that builds the node and feeds
  it a packet, or observes for it. Every place to fill in is marked
  with a ``TODO`` comment; fill them in, then remove the line that
  makes each new test fail on purpose. A file that already exists is
  opened, never overwritten.
* **Run program** saves the program and launches it with
  ``debasher_exec``. A program that the engine refuses is reported at
  once, with what ``debasher_exec`` printed.
* **Get program status** shows what ``debasher_status`` prints.
* **Stop program** runs ``debasher_stop``.
* **Reset output directory** deletes everything inside the output
  directory.
* **Talk to FIFOs**, while the program runs, lets you act as the other
  end of its FIFOs that no process reads or writes: what you type is
  written into an input FIFO, and each line written is paired with the
  line read back from an output FIFO.

Every five seconds the web interface reads ``debasher_status`` on the
output directory and colors each process by its status: green when it
has finished, yellow while it is in progress, red when it did not
finish, and gray while it waits to run. An indicator in the corner of
the canvas follows the run. The right-button menu of a process shows
what its process left in the output directory: "Show stdout", "Show
scheduler output", "Show options" and "Show inputs and outputs" (where
each file can be opened); "Watch FIFO" shows live what the process
writes into an output FIFO whose option has "Mirror" set; and "Stop
process" stops that process alone. For a process that ran as several
tasks, the task is chosen first.

A run belongs to its output directory, not to the browser tab: closing
the tab, leaving the editor or stopping the server stops nothing, and
leaving the editor during a run says where the run goes on. To follow
or stop it again, load the program: its status comes from the output
directory, whoever launched the run, from the web interface or from
the command line. While a run is in progress, the web interface
refuses to save the program, to reset the output directory or to
change it.

Resident Programs in the Web Interface
--------------------------------------

A resident program is built on the same canvas, with the differences
that its type brings (see the :ref:`resident` Section for what a
resident program is).

Nodes
^^^^^

"Add process" asks for the *node kind* of the new process:
``FBPProcess``, a node whose code processes what arrives on its ports;
``ProgramLauncher``, which launches a general program for each request
it receives; ``DirectoryWatcher``, which sends a request for each file
that arrives in a directory; or ``Supervisor``, at most one per
program. A mark in the head of each node shows its kind.

"Edit node code" in the Inspector edits the Python code of a node in
parts: the *node preamble* (imports, helper functions), the *class
body* (class attributes, the constructor with the initial node state,
helper methods), and one body for each hook, ``process_data``,
``capture_node_state``, ``restore_node_state``, ``initialize_runtime``
and ``observe``. The class declaration, named after the process, and
the lines that create the node and run it are written by the web
interface. For a ``ProgramLauncher`` or a ``DirectoryWatcher``, whose
classes already implement every hook, the editor shows the code that
the node inherits, read only, and what mostly needs setting is class
attributes, such as ``PFILE`` for a launcher node.

The "Initiator" checkbox of the Inspector makes a node an initiator,
where snapshots start; a program made of independent parts needs one
initiator in each. The ``Supervisor`` needs no code: only its name, its
description and its computational specifications are edited. The
Inspector also offers, in the computational specifications, the limits
of a node and the other specifications of resident programs (see the
:ref:`resident` Section).

Options and the Supervisor Wiring
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The options of a node are of four sorts, each drawn in its own way:

* a **business output**, a FIFO that the node writes. With no
  connection, it is read outside the program, and an arrow below its
  handle says so: something outside has to read it.
* a **business input**, connected to a business output.
* an **external input**, a FIFO written from outside the program,
  where the activity of the program comes in, marked with an arrow
  above its handle. It takes no connection.
* a **configuration option**, with a hollow handle, whose value is
  direct, comes from the command line or from the specifications.

The channels between the ``Supervisor`` and the nodes (the heartbeat
channels, and the control ports of the initiators) are the
*Supervisor wiring*. The web interface writes them into the generated
script by itself, and draws them, dotted and read only, only when
"Show Supervisor wiring" is chosen in the right-button menu of the
``Supervisor``.

Running, Stopping and Resuming
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

"Run program" launches a resident program, always with the built-in
scheduler, and launches it again, resuming every node, after it has
been stopped. The indicator of the canvas says whether the program is
*live*, *stopped in order* or *stopped abruptly*, and the "Run" menu
changes accordingly:

* **Stop program** stops it in order, with
  ``debasher_stop_resident``, and says whether the stop was orderly or
  had to fall back to killing the program.
* **Kill program** kills every process at once, with
  ``debasher_stop``, for a program that is stuck; what its FIFOs held
  may be lost.
* **Take snapshot** takes a snapshot of every node. "Set execution
  options" also sets a *snapshot period*: with one, every launch from
  the web interface also starts ``debasher_snapshot_resident --every``,
  which a resident program needs so that the input logs of its nodes
  do not grow until they stop them.
* **Reset program state**, while the program is stopped, runs
  ``debasher_reset_resident``, so that the next launch starts every node
  afresh.
* **Talk to FIFOs**, while the program is live, writes messages into an
  external input and reads, continuously, what a business output that
  no node reads carries. A message is written as JSON, or as text sent
  as a string, and the transcript shows what was written and what was
  read in the order in which it happened.

When the output directory holds the state of an earlier run and the
program changed since that run was launched, "Run program" asks
whether to resume the old state with the changed program, or to reset
the state and start afresh: a node resumed with code other than the
code that produced its state may not resume correctly. A change of a
description asks nothing.

The right-button menu of a node offers, besides the entries of a
general program but "Watch FIFO":

* **Show node state**: what ``debasher_inspect_resident`` shows of the
  node, its summary, its checkpoints and its input log.
* **Show batch runs**, for a launcher node: its batch runs and their
  states, with the log, the status and the directory of each.
* **Restart node**: stops the node, which then resumes from its latest
  checkpoint and its input log, relaunched by the ``Supervisor``, or by
  the web interface when the program has none.
* **Relaunch node**, in a program without a ``Supervisor``: relaunches
  the tasks of the node that are down.

A node with a notice (see the :ref:`resident` Section) shows a mark, an
``i`` or a ``!``, whose tooltip gives the text; "Show node state"
gives it too.

Like a run of a general program, a resident program lives in its
output directory, not in the tab: it goes on running when the tab is
closed or the server stops, and loading the program shows it again as
it is.
