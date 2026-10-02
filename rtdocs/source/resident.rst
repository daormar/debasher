.. _resident:

Resident DeBasher Programs
==========================

The programs described in the previous sections are *general
programs*: each of their processes runs once, on a batch of inputs,
and ends. DeBasher runs a second type of program, the *resident
program*, whose processes are long-lived and keep a state of their
own. They exchange messages through FIFOs while they run, possibly in
cycles, and they react to what is written into the program from
outside, one message at a time.

A resident program is the right tool when data keeps arriving and
has to be processed as it comes: files that land in a directory, a
stream of requests, a person who types into the program. In exchange
for writing its processes as Python classes that follow a few rules,
a resident program gets the following from DeBasher:

* **Recovery from crashes.** A process that crashes is relaunched and
  returns to the state it would have had without the crash, and the
  other processes keep running meanwhile.
* **Consistent snapshots.** At any moment, the state of every process
  can be saved together, as a consistent picture of the whole program.
* **Stop and resume.** A program can be stopped in order and, later,
  launched again, every process resuming where it stopped.
* **Failures detected, never silent.** When a guarantee cannot be
  kept, the program says so instead of carrying on with wrong state.

This section explains what a resident program is made of, how to write
one, and how to run, stop, resume and inspect it. The Python classes
that a resident program is built from are documented in the
:ref:`resident-nodes-api` Section. A resident program can also be
built and run from the web interface (see the :ref:`webui` Section).

Concepts
--------

A resident program is a DeBasher module like any other, whose
``program_type`` method declares it resident (see the
:ref:`implem` Section). What changes is what its processes are and how
they run:

* **Nodes.** Every process of a resident program but its
  ``Supervisor`` (see below) is a *node*: a Python class, written in the
  ``heredoc_py`` method of the process, that derives from
  ``FBPProcess``, a class of DeBasher's runtime library. The node runs
  until it is told to stop.
* **Ports and channels.** The options of a node that are connected to
  a FIFO are its *ports*. A *channel* is the one-way connection, made
  of a FIFO, from an output port of one node to an input port of
  another (or of the same node, a *self-loop*). Every message is one
  line of JSON.
* **Messages from outside.** A node acts only in reaction to what it
  receives, so the activity of a program starts with something written
  into it from outside: an *external port* is an input port fed from
  outside the program, by a person or by another program.
* **Snapshots and checkpoints.** A *snapshot* saves the state of
  every node together, as a *checkpoint* of each node, by passing a
  marker along the channels. It starts at an *initiator*, a node that
  receives the order to start it on a *control port*.
* **Input log.** Every node records what it receives since its latest
  checkpoint. A node that crashes is relaunched, restores its latest
  checkpoint and processes again what its input log holds, in the
  same order, which takes it back to the state it had.
* **The Supervisor.** A resident program may have one ``Supervisor``,
  a process that watches the nodes through the heartbeats they send
  it, relaunches a node that goes down, and relays the orders to take a
  snapshot or to stop to the initiators.

A resident program always runs with the built-in scheduler, on a
single machine: ``debasher_exec`` refuses another scheduler for it.

A First Example
---------------

The ``webui_running_sum`` program, which can be found in the
``data/webui_programs`` folder of the repository, is about the
smallest useful resident program. Its node, ``Accumulate``, reads
numbers written into its external port, and writes out the running sum
after each one. A ``Supervisor``, ``Sup``, watches it. The whole module
is shown in the :doc:`webui_running_sum` page; below we go through its
parts.

The module declares that its program is resident:

.. literalinclude:: ../../data/webui_programs/webui_running_sum/webui_running_sum.sh
   :language: bash
   :start-at: webui_running_sum_program_type()
   :end-before: Accumulate_document()

``Accumulate`` defines its options as any process does, but every one
of them is a FIFO:

.. literalinclude:: ../../data/webui_programs/webui_running_sum/webui_running_sum.sh
   :language: bash
   :start-at: Accumulate_define_opts()
   :end-before: Accumulate_heredoc_py()

* ``-numbers`` is the external port where the numbers arrive. The node
  reads it, and the ``--external`` tag says that it is written from
  outside the program.
* ``-outsum`` is an output port, written by the node. No other node
  reads it, so its other end is left for someone outside the program.
* ``-outhb`` is the channel on which the node sends its heartbeats to
  the ``Supervisor``.
* ``-trigger`` is the control port on which the ``Supervisor`` tells
  the node to start a snapshot or a stop, which makes ``Accumulate``
  an initiator.

The code of the node is a Python class named after its process,
written in the ``heredoc_py`` method of the process:

.. literalinclude:: ../../data/webui_programs/webui_running_sum/webui_running_sum.sh
   :language: bash
   :start-at: Accumulate_heredoc_py()
   :end-before: Sup_document()

The node state is the sum, ``self.total``. ``process_data`` receives
each number as a Python value, already decoded from JSON, updates the
sum and sends it on ``outsum``. ``capture_node_state`` and
``restore_node_state`` turn that state into a value that JSON can
serialize and back, so that it can be saved in a checkpoint.

The ``Supervisor`` needs no code: an empty subclass of
``Supervisor`` is enough. Its options connect it to the heartbeat
channel of every node, to the control port of every initiator
(``-outAccumulate_trig``, tagged ``--control``, since it carries
orders), and to a *manual trigger port*, ``-manual``, where the tools
described below write their orders:

.. literalinclude:: ../../data/webui_programs/webui_running_sum/webui_running_sum.sh
   :language: bash
   :start-at: Sup_define_opts()
   :end-before: webui_running_sum_program()

Running the Example
^^^^^^^^^^^^^^^^^^^

A resident program is launched with ``debasher_exec``, as any other.
The command returns as soon as its processes are launched, and they
keep running:

::

    $ debasher_exec --pfile webui_running_sum.sh --outdir out
    $ debasher_status -d out
    PROCESS: Accumulate ; STATUS: IN-PROGRESS
    PROCESS: Sup ; STATUS: IN-PROGRESS
    ...

The FIFOs of the program are in ``out/__fifos__``, in a directory
named after the process that defines each one. To see the sums, a
reader has to be attached to ``outsum``; then every number is written
into ``numbers`` as one line of JSON, a ``DATA`` message whose
``payload`` is the number:

::

    $ cat out/__fifos__/Accumulate/sum &
    $ echo '{"type": "DATA", "payload": 1}' > out/__fifos__/Accumulate/numbers
    $ echo '{"type": "DATA", "payload": 2}' > out/__fifos__/Accumulate/numbers
    $ echo '{"type": "DATA", "payload": 3}' > out/__fifos__/Accumulate/numbers

The reader prints what the node writes: a ``HELLO`` line, which every
node writes first on each output port, and the running sums, each
numbered with ``seq``:

::

    {"type": "HELLO", "payload": {}}
    {"type": "DATA", "seq": 1, "payload": 1}
    {"type": "DATA", "seq": 2, "payload": 3}
    {"type": "DATA", "seq": 3, "payload": 6}

``debasher_stop_resident`` stops the program in order: every node
saves its state in one last snapshot before it stops. Launching the
program again with the same output directory resumes it:

::

    $ debasher_stop_resident -d out
    Every node of out stopped cleanly.
    $ debasher_exec --pfile webui_running_sum.sh --outdir out
    $ cat out/__fifos__/Accumulate/sum &
    $ echo '{"type": "DATA", "payload": 4}' > out/__fifos__/Accumulate/numbers

The node remembers the sum it had, and writes ``10``. To start again
from scratch instead, the program is stopped and reset with
``debasher_reset_resident`` (see `Stopping, Resuming and Resetting`_
below).

Writing a Node
--------------

A node is a Python class that derives from ``FBPProcess`` (or from one
of its subclasses in the runtime library, ``DirectoryWatcher`` and
``ProgramLauncher``, described below), written in the ``heredoc_py``
method of its process. The code of the method creates the node and
calls its ``run`` method, which returns only when the node is told to
stop.

The class is named after its process in CamelCase: every part of the
process name between dots and underscores, with its first letter in
upper case (``counter`` gives ``Counter``, ``org.ns.count_words``
gives ``OrgNsCountWords``). Naming processes in CamelCase in the first
place (``Counter``) gives the process and its class the same name.
When the program is loaded, DeBasher checks that the Python code
defines exactly one such class and that its name hides no Python
builtin nor name of the runtime library, so a process called
``supervisor`` or ``type_error`` has to be renamed.

The Hooks of a Node
^^^^^^^^^^^^^^^^^^^

A node redefines four methods, its *hooks*, which the framework calls:

* ``process_data(port_name, packet)``: processes one message,
  ``packet``, received on the input port ``port_name``. It is the only
  place from which the node sends, with ``send_data(port_name,
  payload)``; calling ``send_data`` anywhere else raises an error.
* ``capture_node_state()``: returns the *node state*, everything that
  ``process_data`` keeps from one message to the next, as a value that
  JSON can serialize. It is called when a snapshot is taken.
* ``restore_node_state(node_state)``: sets the node state back from
  what ``capture_node_state`` returned, when the node starts from a
  checkpoint. The constructor sets the initial state, for a node that
  starts with no checkpoint.
* ``initialize_runtime()``: opens what the node uses and is not part of
  its state, such as a connection or an open file, every time the node
  starts.

The options of the process are available in ``self.opts``, a
dictionary from the name of each option, without its dash, to its
value; ``self.log`` is a logger that writes to the standard error of
the process, which ``debasher_get_sched_out`` shows. A node that
receives on several input ports and needs messages from more than one
of them keeps what it has received in its node state, and decides in
``process_data`` when it has enough: the framework delivers each
message as it arrives.

Rules That a Node Follows
^^^^^^^^^^^^^^^^^^^^^^^^^

Recovery calls ``process_data`` again for every message received since
the latest checkpoint, and cannot tell a replay from the first
execution. The guarantees of a resident program hold only if the code
of every node follows these rules:

* **process_data is deterministic.** Given the same node state and the
  same messages, it produces the same new state and sends the same
  messages. It must not depend on the time, on random numbers, or on
  reading something outside the program that is not part of the node
  state or of the messages. What varies has to enter the node as a
  message (see `Observing the Outside World`_ below).
* **The node state is complete.** Everything that influences what the
  node does later is returned by ``capture_node_state``, and
  ``restore_node_state`` rebuilds it exactly.
* **Effects outside the program are idempotent.** Whatever
  ``process_data`` does besides sending messages (writing a file
  elsewhere, calling a service) may be done more than once.
* **Messages are JSON.** What a node sends is any value that JSON can
  serialize, of any size.

A node that has to wait between two steps calls ``self.sleep(seconds)``
instead of ``time.sleep``: it does not wait during a replay, and it
returns early when the node is told to stop.

Ports and Channels
------------------

The ports of a node are declared only once, in the options of its
process, and the engine gives them to the node when it launches it;
the class declares none. The rule is that the process that writes a
FIFO defines it:

* An **output port** is an option named ``-out...`` that the node
  defines with ``define_fifo_opt``. The node writes it.
* An **input port** is an option connected, with
  ``define_opt_from_proc_out``, to the output port of another node (or
  of the node itself). If no node reads an output port, its other end
  is left for someone outside the program to read.
* A FIFO written from outside the program is the exception: the node
  that reads it defines it, with a tag that says what it carries.
  ``--external`` makes it an **external port**, which carries data;
  ``--control`` makes it a **control port**, which carries only orders
  to start a snapshot or a stop.

The Supervisor defines the control ports of the initiators that it
writes (with ``--control``) and its own manual trigger port, and it
reads the heartbeat channel that every node defines. When a program is
loaded, DeBasher checks, before launching anything, that every FIFO
follows these rules and that the marker of a snapshot can reach every
node from an initiator. The tags are refused in a general program, and
the ``--mirror`` option of ``define_fifo_opt`` is refused in a resident
program, whose nodes keep their own input log.

Writing Into a Program From Outside
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Whoever writes into an external port writes one line of JSON per
message, ``{"type": "DATA", "payload": ...}``, in a single write, as
the ``echo`` of the example does. A line longer than ``PIPE_BUF`` bytes
(4096 on Linux) may be split by the operating system when several
writers write at once. A source that numbers its messages, adding
``"seq": 1``, ``"seq": 2``, and so on, lets the node detect a message
lost on its way in; the node ignores a message with a number that it
has already seen.

What enters from outside cannot be regenerated by any node, so
delivery at that boundary is at most once: inside the program, the
guarantees start from the moment a node records a message in its input
log. A reader attached to an output port read outside the program has
to go on reading, or the node that writes it stops with an error once
``OUT_BACKLOG_FAIL_BYTES`` of messages are waiting.

The Supervisor
--------------

A resident program has at most one ``Supervisor``. It is optional, but
without it the program loses three things: nobody relaunches a node
that goes down, nobody relays the orders of the manual trigger port to
the initiators, and nobody holds the FIFOs of the channels between
nodes. That last one matters when both ends of a channel crash
together: the ``Supervisor`` keeps the FIFO open, so that what it held
waits for the relaunched reader instead of being lost. The flag
``-no-hold-fifos``, which a module may offer as a command line option of
its ``Supervisor``, turns it off.

The ``Supervisor`` declares a node down when its heartbeats stop for
``HEARTBEAT_TIMEOUT_SECS`` (30 seconds by default), or at once when
its process is gone, and relaunches it. A node that goes down again
after ``MAX_RELAUNCH_ATTEMPTS`` relaunches (three by default) with no
heartbeat in between is given up on, and the ``Supervisor`` stops the
rest of the program in order. A node whose recovery takes long, such as one with a large
input log to replay, is given more time before its first heartbeat
through the computational specification ``startup_timeout_s``, in
seconds:

.. code-block:: bash

    add_debasher_process "Counter" "cpus=1 mem=256 time=01:00:00 startup_timeout_s=120"

The ``Supervisor`` itself is not supervised, and keeps no state: if it
dies, the nodes go on running, and it is relaunched by stopping and
launching the program again.

Stopping, Resuming and Resetting
--------------------------------

A resident program does not end on its own: its nodes run until they
are told to stop. Four tools act on a running or stopped program from
outside it; they are described in the :ref:`tools` Section.

* ``debasher_snapshot_resident -d <outdir>`` takes a snapshot: every
  node saves a checkpoint and prunes its input log. With ``--every
  <secs>`` it goes on taking one every so many seconds, until the
  program stops. **A program should take snapshots regularly**: the
  input log of a node holds everything it received since its latest
  checkpoint, and a node whose log reaches ``INPUT_LOG_MAX_BYTES``
  (100 MiB by default) stops with an error.
* ``debasher_stop_resident -d <outdir>`` stops the program in order:
  every node saves its state in one last snapshot, and then stops.
  ``debasher_stop``, the tool for general programs, also works, but it
  kills every process at once, and what the FIFOs held may be lost.
* Launching the program again with ``debasher_exec`` and the same
  output directory resumes it: every node restores the checkpoint of
  the stop, and processes again what it received after it, if
  anything.
* ``debasher_reset_resident -d <outdir>`` takes a stopped program back
  to its first run: it moves the checkpoints, the input logs and the
  outputs of every node under ``__reset__/<timestamp>/`` in the output
  directory (or deletes them, with ``--delete``), so that the next
  launch starts every node afresh. It always resets the whole program,
  never one node.
* ``debasher_inspect_resident -d <outdir> -p <process> summary`` shows
  what a node keeps: its checkpoints, the size of its input log, its
  health and its notice. The commands ``checkpoint <epoch>`` and
  ``log`` show a checkpoint and the latest records of the input log,
  and ``notices`` the notices of every node at once.

Observing the Outside World
---------------------------

Some nodes have to watch something outside the program: a directory
where files arrive, a queue, the batch runs that they started. What
such a node sees is different every time that it looks, so looking
cannot happen in ``process_data``, which a replay calls again. It
happens in the hook ``observe``, which a class may define: the
framework calls it on a thread of its own every
``OBSERVE_INTERVAL_SECS`` seconds, only while the node is running.
``observe`` brings what it sees into the node with
``self.inject(payload)``, which records it in the input log, as if it
had arrived on a port named ``OBSERVE_PORT``, and ``process_data``
then decides what to do about it:

.. code-block:: python

    import os

    from debasher_runtime_lib import FBPProcess


    class Watch(FBPProcess):
        OBSERVE_PORT = "arrivals"

        def __init__(self):
            super().__init__()
            # The node state: the files already sent.
            self.seen = set()
            # What observe() has brought in, in this start of the node
            # only, so that each file is brought in once.
            self.brought_in = set()

        def observe(self):
            for name in sorted(os.listdir(self.opts["dir"])):
                if name not in self.brought_in:
                    self.inject({"file": name})
                    self.brought_in.add(name)

        def process_data(self, port_name, packet):
            if packet["file"] not in self.seen:
                self.seen.add(packet["file"])
                self.send_data("outfiles", packet["file"])

        def capture_node_state(self):
            return {"seen": sorted(self.seen)}

        def restore_node_state(self, node_state):
            self.seen = set(node_state["seen"])

        def initialize_runtime(self):
            pass


    Watch().run()

``brought_in`` is not part of the node state: a node that starts
again brings every file in again, and ``process_data``, which keeps in
the node state what it has already acted on, drops the repetitions.

``DirectoryWatcher``, a class of the runtime library, does this for a
directory: it watches ``WATCH_DIR`` (or the directory that the option
``-watchdir`` of the process gives), and sends a request on its output
port ``outrequests`` for every file whose name matches ``PATTERN``
once the file is complete, that is, once its size and modification
time stop changing. A module that only needs to set those attributes
derives from it with no code of its own. The :doc:`webui_watch_tally`
shows a complete program with a ``DirectoryWatcher``, and its tests.

Notices
^^^^^^^

A node can leave a message for the person who watches the program,
such as that its configuration file is missing, with
``self.set_notice(text, level="info")`` (``level`` is ``info`` or
``warning``), and take it away with ``self.clear_notice()``. A node
has at most one notice, and a new one replaces the previous one. The
notice is not part of the node state: every start of the node begins
without one, so a notice that follows from the node state is set
again in ``restore_node_state``. ``debasher_inspect_resident`` shows
the notices, and the web interface marks the node that has one.

Batch Runs From a Node
----------------------

A resident program processes a stream of messages; a general program
processes a batch of inputs and ends. A *launcher node* joins the two:
for every request that it receives, it launches the same general
program with the options of the request, in a run directory of its
own, and it can tell a node downstream when each of those *batch
runs* ends. A bioinformatics system is the typical case: every time a
sequencing file arrives, the pipeline that analyses it runs once for
it.

A launcher node is a subclass of ``ProgramLauncher`` that names the
general program in ``PFILE``, as a path relative to the directory of
its own module (the directories of ``DEBASHER_MOD_DIR`` are searched
too):

.. code-block:: python

    from debasher_runtime_lib import ProgramLauncher


    class Launch(ProgramLauncher):
        PFILE = "../webui_batch_greet/webui_batch_greet.sh"


    Launch().run()

Every input port of a launcher node receives requests. A request is a
JSON object with the options of the general program and, optionally,
the name of its run directory:

::

    {"opts": {"-text": "world", "-secs": "5"}, "run": "r1"}

The run directories go under the output directory of the launcher
process, unless the class sets ``RUNS_ROOT``. When its process has an
output port ``-outdone``, the node sends on it
``{"run": ..., "status": ..., "exit_code": ...}`` for every batch run
that ends, with ``status`` set to ``finished`` or ``failed``.
``MAX_CONCURRENT_RUNS`` (one by default) says how many batch runs run
at a time, and ``BATCH_SCHED`` which scheduler they use (the built-in
one by default); a program sets them for one process with the
computational specifications ``max_concurrent_runs`` and
``batch_sched``. ``debasher_inspect_resident ... runs`` lists the batch
runs of a launcher node and their states. The
:doc:`webui_batch_launcher` shows a complete program with a launcher
node.

Limits of a Node
----------------

A few class attributes of ``FBPProcess`` limit the resources of a
node. A module may redefine them in its class, and a program may set
them for one of its processes, over what the class says, in the
computational specifications that it gives to ``add_debasher_process``,
next to ``cpus``, ``mem`` and ``time``:

* ``input_log_max_mb`` sets ``INPUT_LOG_MAX_BYTES``, the size that the
  input log may reach (100 MiB by default).
* ``out_backlog_max_mb`` sets ``OUT_BACKLOG_MAX_BYTES``, the size of
  the messages sent and not yet written into the FIFOs over which a
  node skips a checkpoint (8 MiB by default).
* ``out_backlog_fail_mb`` sets ``OUT_BACKLOG_FAIL_BYTES``, the size of
  those messages over which ``send_data`` raises an error (64 MiB by
  default).
* ``gil_switch_interval_ms`` sets ``GIL_SWITCH_INTERVAL_SECS`` (0.5 ms
  by default).

For example:

.. code-block:: bash

    add_debasher_process "Counter" "cpus=1 mem=256 time=01:00:00 input_log_max_mb=500"

DeBasher checks, when it loads the program, that each value given is a
positive number.

What Is Guaranteed and What Is Not
----------------------------------

When the rules for writing a node above are followed, a resident
program gives these guarantees:

* On every channel, messages arrive in the order in which they were
  sent, and with no failure every message is delivered once.
* A node that crashes (killed, out of memory, an uncaught exception)
  and is relaunched returns to the state it would have had without the
  crash, and its readers receive neither duplicates nor gaps.
* A snapshot captures a consistent state of every node, and an orderly
  stop followed by a new launch loses nothing.
* A crashed node is detected within a bounded time when the program
  has a ``Supervisor``.
* When a guarantee cannot be kept, the failure is reported, never
  silent.

And these are its limits:

* It survives the crash of processes, not of the machine: nothing is
  forced to disk, so a power loss may lose the last seconds of
  checkpoints and input logs.
* If both ends of a channel crash while no process holds its FIFO (in
  a program without a ``Supervisor``, or with ``-no-hold-fifos``),
  what the FIFO held may be lost; the reader then reports the gap.
* What enters from outside is delivered at most once (see `Writing
  Into a Program From Outside`_ above).
* A node that is alive but stuck, in an endless loop for example, goes
  on sending heartbeats and is not detected.
* A resident program runs on a single machine, with the built-in
  scheduler: Slurm is not supported.

Examples
--------

The examples below can be found in the ``data/webui_programs`` folder
of the repository. They were built with the web interface, and
``make installcheck`` runs them.

.. toctree::

   webui_running_sum

   webui_batch_launcher

   webui_watch_tally
