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
:ref:`implem_bash` Section). What changes is what its processes are and how
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
* **Durability mode.** A resident program is *durable*, the default,
  where its nodes keep the input logs and checkpoints above and come
  back from a crash or a stop with the state they had, or
  *non-durable*, where they keep neither and start again with their
  initial state (see `Durable and Non-Durable Programs`_ below).

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
* ``-control`` is the control port on which the ``Supervisor`` tells
  the node to start a snapshot or a stop, which makes ``Accumulate``
  an initiator.

The code of the node is a Python class named after its process,
written in the ``heredoc_py`` method of the process:

.. literalinclude:: ../../data/webui_programs/webui_running_sum/webui_running_sum.sh
   :language: bash
   :start-at: Accumulate_heredoc_py()
   :end-before: Sup_document()

The web interface keeps the class in a file of the home directory of
the program, ``Accumulate.py``, which is what you edit, in the editor,
in the "Program files" panel or by hand; the ``heredoc_py`` method of
the module is written again from it when the program is saved.

The node state is the sum, ``self.total``. ``process_data`` receives
each number as a Python value, already decoded from JSON, updates the
sum and sends it on ``outsum``. ``capture_node_state`` and
``restore_node_state`` turn that state into a value that JSON can
serialize and back, so that it can be saved in a checkpoint.

The ``Supervisor`` needs no code of its own: an empty subclass of
``Supervisor``, followed by the line that runs it, is enough. Its
options connect it to the heartbeat channel of every node, to an
*initiator port* for every initiator (``-outAccumulate_initiator``,
tagged ``--control``, since it carries orders, and read by the
``-control`` port of ``Accumulate``), and to a *manual trigger port*,
``-manual``, where the tools described below write their orders:

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
``supervisor`` or ``type_error`` has to be renamed. It also checks
that the code has the line ``Counter().run()``, with the name of the
class and no arguments, at the top level or under
``if __name__ == "__main__":``, in a node and in the ``Supervisor``
alike. Without that line the process would end at once having started
nothing, so a program that lacks it is refused, as is one that creates
and runs the node in another way.

The Hooks of a Node
^^^^^^^^^^^^^^^^^^^

A node redefines four methods, its *hooks*, which the framework calls:

* ``process_data(port_name, packet)``: processes one message,
  ``packet``, received on the input port ``port_name``. It is the only
  place from which the node sends, with ``send_data(port_name,
  payload)``; calling ``send_data`` anywhere else raises an error.
* ``capture_node_state()``: returns the *node state*, everything that
  ``process_data`` keeps from one message to the next, as a value that
  JSON can serialize. It is called when a snapshot is taken, and the
  framework copies what it returns at once, so it may return the
  objects of the node themselves (a list or a dictionary that
  ``process_data`` goes on changing) without copying them.
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
the process, which ``debasher_get_sched_out`` shows for the latest
launch of the node (the ``Supervisor`` keeps the last lines of the
earlier ones in its own log, see `The Supervisor`_ below). A node that
receives on several input ports and needs messages from more than one
of them keeps what it has received in its node state, and decides in
``process_data`` when it has enough: the framework delivers each
message as it arrives.

Rules That a Node Follows
^^^^^^^^^^^^^^^^^^^^^^^^^

In a durable program, recovery calls ``process_data`` again for every
message received since the latest checkpoint, and cannot tell a replay
from the first execution. The guarantees of a resident program hold only
if the code of every node follows these rules (in a non-durable program
only the last one applies, see `Durable and Non-Durable Programs`_
below):

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
  elsewhere, calling a service) may be done more than once. No test can
  check this in general.
* **Messages are JSON.** What a node sends is any value that JSON can
  serialize, of any size, with no NaN or infinity among its numbers,
  which JSON does not have: ``send_data`` raises ``ValueError`` on one,
  and sends nothing.

Nothing checks the first three rules when the program runs, while
``send_data`` enforces the last. The tests of the program can catch
breaches of the first two with ``check_replay`` of
``debasher_runtime_testing``, and of the round trip of the node state
with ``restart`` (see the :ref:`tools` Section).

A node that has to wait between two steps calls ``self.sleep(seconds)``
instead of ``time.sleep``: it does not wait during a replay, and it
returns early when the node is told to stop.

Durable and Non-Durable Programs
--------------------------------

A resident program declares its durability mode as the second argument
of ``program_type``:

.. code-block:: bash

    live_stats_program_type()
    {
        program_type "resident" "non-durable"
    }

Without a second argument, or with ``"durable"``, the program is
*durable*: every node keeps an input log and checkpoints, a node that
crashes is relaunched from its latest checkpoint and processes again
what it received since, an orderly stop halts every node in one round so
that the next launch resumes the program with nothing lost, and the
program takes snapshots regularly so that the input logs do not grow
until their cap (see `Stopping, Resuming and Resetting`_ below). It
needs the rules of the previous section: a deterministic
``process_data``, a complete node state, idempotent effects outside the
program.

A *non-durable* program has none of that: no input log, no checkpoints
and no rounds. It is for programs whose nodes keep state that is not
worth keeping across a crash (statistics over the last minutes of a
stream, a cache that the stream rebuilds) or that cannot be captured,
and that want the model of a node all the same: the hooks, the ports,
``observe`` and ``inject``, the notices, the ``Supervisor``, the launcher
and watcher nodes, the web interface. In a non-durable program:

* A node is written the same way, but ``capture_node_state`` and
  ``restore_node_state`` are never called and need not be written, and
  ``process_data`` may use the clock, random numbers or anything else
  outside the program: nothing is replayed. What has to outlive the node
  goes into a file of its output directory (``DEBASHER_PROCESS_OUTDIR``),
  which the engine keeps across launches and ``debasher_reset_resident``
  takes away.
* A node that crashes is relaunched by the ``Supervisor`` with its initial
  state. The crash loses the state of the node, what it had read and not
  yet processed, and what it had sent and not yet written; what its
  channels held reaches the new incarnation, as long as some process
  holds the FIFO (the other end, or the ``Supervisor``). Nothing reports a
  lost message: the sequence numbers are not compared, since nothing
  remembers them across a relaunch.
* ``debasher_stop_resident`` stops the program without a halt: every node
  processes what it had read and ends, and the next launch starts every
  node afresh. ``debasher_snapshot_resident`` refuses the program, and
  ``debasher_inspect_resident`` has no checkpoint or input log to show.
* The input log cap gives way to a bound on what a node has read and not
  yet processed, ``inbound_queue_max_mb`` (see `Limits of a Node`_
  below): over it, the readers of the node wait, and the pressure goes
  back into the FIFOs and the writers.
* A launcher node still launches each request once, since its queue is
  on disk; a request in flight at a crash is lost, and the end of a batch
  run may be announced twice. A relaunched watcher sends a request again
  for every complete file still in its directory, which the launcher
  drops. Its tests cannot use ``restart`` or ``check_replay`` (see the
  :ref:`tools` Section).

The :doc:`webui_live_stats` is such a program, to try by hand: live
statistics over a fake stream, kept in memory and with the clock.

A program does not change its mode over the state of a run:
``debasher_exec`` refuses to launch a program declared in one mode over an
output directory with the state of a run in the other, and names
``debasher_reset_resident``, after which the mode may change. Of the
guarantees of `What Is Guaranteed and What Is Not`_, a non-durable
program keeps the order and the delivery of the messages with no failure
and the detection of a crashed node; the recovery of a node, the
consistent snapshots and the resume after a stop belong to the durable
mode.

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

The Supervisor defines an *initiator port* for each initiator that it
writes to (with ``--control``), which the initiator reads as its
control port, and its own manual trigger port, and it reads the
heartbeat channel that every node defines. A Supervisor with a manual
trigger port has to have at least one initiator port, since an order
written there would reach no node. When a program is
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

Each line is strict JSON in UTF-8. A line that is not JSON, or not
valid UTF-8, stops the node from reading that port, with the error in
its log, rather than reaching the node altered. A line that is JSON
but not a well-formed message (no ``type`` or ``payload``, an unknown
``type``, a ``seq`` that is not an integer), or a message of a type
that the port does not carry, is dropped with a warning in the log of
the node, which goes on reading the port: an external port takes
``DATA`` messages, and a control port only the orders that the tools
below write. NaN and the infinities are not JSON either: the node reads
them, but fails as soon as it sends such a value on.

What enters from outside cannot be regenerated by any node, so
delivery at that boundary is at most once: inside the program, the
guarantees start from the moment a node records a message in its input
log. A reader attached to an output port read outside the program has
to go on reading, or the node that writes it stops with an error once
``OUT_BACKLOG_FAIL_BYTES`` of messages are waiting; while the node
replays its input log, it waits for that reader instead (see "The
Supervisor" below).

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
``HEARTBEAT_TIMEOUT_SECS`` (30 seconds by default), or at once when its
process is gone, and relaunches it. The relaunch rewrites the scheduler
output of the node, so the warning that the ``Supervisor`` logs when it
relaunches a node carries the last 20 lines of that output, where the
cause of the crash usually is.
``debasher_get_sched_out -d <outdir> -p <supervisor process>`` shows
them, attempt after attempt, until the next launch of the program,
which rewrites it. A node relaunched by hand
(``debasher_launch_process``, or "Relaunch node" in the web interface,
in a program without a ``Supervisor``) keeps nothing: read its
scheduler output before. A node that goes down again after
``MAX_RELAUNCH_ATTEMPTS`` relaunches (three by default) with no
heartbeat in between is given up on: the ``Supervisor`` kills it, if it
still runs, and stops the rest of the program in order with
``debasher_stop_resident``. If that stop does not end within
``FORCE_STOP_TIMEOUT_SECS`` (60 seconds by default), every process of
the program, the ``Supervisor`` included, is killed, as with
``debasher_stop``, and what the FIFOs held may be lost; the log of the
``Supervisor`` then ends with the warning of the tool, which says
``forcing debasher_stop``. A node that cannot recover, such as one whose
input log was lost, fails the same way at every relaunch, so the
``Supervisor`` gives up on it (see `Stopping, Resuming and Resetting`_
below). The error that the ``Supervisor`` logs when it gives up on a
node ends with the command that shows the scheduler output of its last
attempt, which holds the cause:
``debasher_get_sched_out -d <outdir> -p <process>``, with ``-t <idx>``
for a task. A node whose recovery takes long, such as one with a large
input log to replay, is given more time before its first heartbeat,
while it is alive, through the computational specification
``startup_timeout_s``, in seconds; a node whose process ends during its
startup is declared down at once whatever its ``startup_timeout_s``:

.. code-block:: bash

    add_debasher_process "Counter" "cpus=1 mem=256 time=01:00:00 startup_timeout_s=120"

A replay goes at the pace of the readers of the node: once
``OUT_BACKLOG_FAIL_BYTES`` of what it sends again is waiting, it waits
for room, with no heartbeats meanwhile, so a slow reader is one more
reason to raise ``startup_timeout_s``. A reader that never reads keeps
the node in its startup until the ``Supervisor`` declares it down and
relaunches it or, in a program without a ``Supervisor``, until the node
is stopped. The nodes of a cycle that replay at once, each over the
limit, wait on each other in the same way, and a node with a self-loop
waits on itself.

The ``Supervisor`` itself is not supervised, and keeps no state: if it
dies, the nodes go on running, and it is relaunched by stopping and
launching the program again. A ``Supervisor`` one of whose own threads
fails does not go on half working, deaf to the heartbeats: it stops
with the error in its log (``debasher_get_sched_out``), and the nodes
go on running, unsupervised, until the program is stopped and launched
again.

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
  every node saves its state in one last snapshot, and then stops (a
  non-durable program stops without that snapshot, see `Durable and
  Non-Durable Programs`_ above). ``debasher_stop``, the tool for general
  programs, also works, but it kills every process at once, and what
  the FIFOs held may be lost.
* Launching the program again with ``debasher_exec`` and the same output
  directory resumes it: every node restores the checkpoint of the stop,
  and processes again what it received after it, if anything. In a
  non-durable program the launch starts every node afresh, over the
  files its process left, and ``debasher_exec`` refuses to launch a
  program in one mode over the state of a run in the other (see `Durable
  and Non-Durable Programs`_ above). A node whose input log was lost or
  cut (removed, emptied, or ending before the position of its latest
  checkpoint) refuses to start rather than silently lose what it
  processed after that checkpoint: its error, which
  ``debasher_get_sched_out`` shows, names the log and both positions.
  With a ``Supervisor``, every relaunch fails the same way, at once,
  until the ``Supervisor`` gives up on the node and stops the program,
  with an error that names the ``debasher_get_sched_out`` command that
  shows this log; without one, the task fails. The way out is
  ``debasher_reset_resident``, which starts the whole program afresh.
  The input logs are never cleaned by hand: snapshots prune them.
* ``debasher_reset_resident -d <outdir>`` takes a stopped program back
  to its first run: it moves the checkpoints, the input logs and the
  outputs of every node under ``__reset__/<timestamp>/`` in the output
  directory (or deletes them, with ``--delete``), so that the next
  launch starts every node afresh. It always resets the whole program,
  never one node. It refuses while a batch run of a launcher node is
  still in progress (see `Batch Runs From a Node`_): wait for it to
  end, or stop it with ``debasher_stop -d <run directory>``.
* ``debasher_inspect_resident -d <outdir> -p <process> summary`` shows
  what a node keeps: its checkpoints, the size of its input log, its
  outbound backlog and its notice. The commands ``checkpoint <epoch>``
  and ``log`` show a checkpoint and the latest records of the input log,
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
directory: it watches the directory that the option ``-watchdir`` of the
process gives (relative to the directory of the module, unless it is
absolute), and sends a request on its output port ``outrequests`` for
every file whose name matches ``PATTERN`` once the file is complete,
that is, once its size and modification time stop changing. A file is
known by its path until a clean start of the program, so one that
arrives again under the same name gets no request: the directory has to
receive names that do not repeat. A module that only needs to set
``PATTERN`` derives from it with no methods of its own, and runs it as
any other node. The :doc:`webui_watch_tally` shows a complete program
with a ``DirectoryWatcher``, and its tests.

If ``observe`` raises, the process of the node ends with an error, as it
does when any of its threads dies, and the ``Supervisor`` relaunches it
(in a program without one, the node is down until it is relaunched by
hand). A node whose source can stall while its process stays alive (a
stream that gives no more data and does not close) raises in ``observe``
once it has seen nothing for too long, and the relaunch reconnects. The
:doc:`webui_stream_stall` shows such a node, and lets you try a stall, a
frozen node and the limits of a node by hand. The :doc:`webui_readfish`
does the same around a real tool, readfish, whose stream of reads from a
sequencer dies in silence now and then: its node runs readfish as a
child process, reads its log, tells the silence of a scan of the pores
from a stall, and bounds the relaunches of a readfish that never gives a
read.

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
the notices, and the web interface marks the node that has one. A
``DirectoryWatcher`` without the output port ``-outrequests``, and a
``ProgramLauncher`` without an input port, leave a warning notice of
their own when they start, since they would otherwise run doing
nothing useful.

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

A launcher node is a subclass of ``ProgramLauncher``, which usually
needs no code of its own:

.. code-block:: python

    from debasher_runtime_lib import ProgramLauncher


    class Launch(ProgramLauncher):
        pass


    Launch().run()

The option ``-pfile`` of its process names the general program, as a
path relative to the directory of its own module (the directories of
``DEBASHER_MOD_DIR`` are searched too). A module that always launches
the same program fixes it in the ``define_opts`` of the process:

.. code-block:: bash

    debasher::define_opt "-pfile" "../webui_batch_greet/webui_batch_greet.sh" optlist || return 1

``-pfile`` is not a file option (define it with ``define_opt`` or
``define_cmdline_opt``, not ``define_cmdline_infile_opt``), so that the
engine leaves a relative name as it is. An absolute path is accepted
with a warning, since it ties the program to one machine. With the
option ``-process``, the node launches that process of the general
program alone, with ``debasher_exec_process``, instead of the whole
program. Nothing then schedules or prepares the batch runs, so
``batch_sched``, ``batch_conda_support`` and ``batch_docker_support``
are ignored, and the environments that the process declares have to
exist already.

Every input port of a launcher node receives requests. A request is a
JSON object with two optional fields: ``opts``, the options of the
general program (names with their dash, values as strings), and
``run``, the name of its run directory:

::

    {"opts": {"-text": "world", "-secs": "5"}, "run": "r1"}

Without ``opts``, the program is launched with no options; without
``run``, the run directory is named after the position of the request.
A request may not give an option that ``debasher_exec`` reads itself,
such as ``--outdir``, ``--wait`` or ``--conda-support``: the node drops
it, and logs why.
Other fields of a request are ignored, and do not reach the message
on ``-outdone``: a node downstream knows a batch run by its ``run``.

A run directory belongs to the request that created it: a later
request that names the run directory of an earlier one is dropped, and
the node logs why. To run a batch run again under the same name,
remove its run directory and send the request again: the node skips
the earlier registration, and the new request becomes the batch run of
that directory. A run directory removed with no new request is skipped
too: the node logs an error (once each time it starts), does not
launch it again nor report it on ``-outdone``, and
``debasher_inspect_resident ... runs`` leaves it out.

The run directories go under the output directory of the launcher
process, unless the option ``-runsdir`` gives another root, which has to
be an absolute path. When its process has an output port ``-outdone``,
the node sends on it ``{"run": ..., "run_dir": ..., "status": ...,
"exit_code": ...}`` for every batch run that ends, with ``run_dir`` the
absolute path of the run directory, where a node downstream finds the
results, and ``status`` set to ``finished`` or ``failed``.
``MAX_CONCURRENT_RUNS`` (one by default) says how many batch runs run at
a time, ``BATCH_SCHED`` which scheduler they use (the built-in one by
default), and ``BATCH_CONDA_SUPPORT`` and ``BATCH_DOCKER_SUPPORT``
whether they are prepared with conda or docker support (neither by
default): ``debasher_exec`` is then given ``--conda-support`` or
``--docker-support``, so that the environments and images that the
processes of the general program declare exist before they run, as a run
by hand with the same options prepares them (see the :doc:`conda` and
:doc:`docker`); conda keeps an environment by its name, so the
first batch run that needs one creates it and the rest find it. A
program sets the four for one process with the computational
specifications ``max_concurrent_runs``, ``batch_sched``,
``batch_conda_support`` and ``batch_docker_support`` (the last two
``yes`` or ``no``). The first is a positive whole number: the engine
checks it when it loads the program, and the node when it is created.
Under Slurm the node gives ``debasher_exec`` the option ``--wait``:
the ``debasher_exec`` of every batch run that runs stays alive on the
machine of the node until the jobs of its program have ended, and its
exit status becomes the ``exit_code`` of the batch run (0 when every
process finished, 3 when some did not, 1 on an error such as options
that the program refuses). ``MAX_CONCURRENT_RUNS`` bounds how many of
those processes wait at once. A batch run is a program of its own: the
options of the run of the resident program, such as its own
``--conda-support``, do not reach it, and a request cannot give them in
``opts`` either, so only ``batch_conda_support`` and
``batch_docker_support`` prepare its environments; and stopping the
resident program, or its launcher node, does not stop the
batch runs in progress, which go on and are reported on ``-outdone``
when the node comes back. ``debasher_stop -d <run directory>`` stops
one, and ``debasher_reset_resident`` refuses while one is in progress.
A batch run that ends while the node is
down is still reported on ``-outdone`` when the node comes back.
``debasher_inspect_resident ... runs`` lists the batch runs of a
launcher node and their states. The :doc:`webui_batch_launcher` shows a
complete program with a launcher node.

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
  those messages over which ``send_data`` raises an error, since a
  reader is not reading (64 MiB by default). The error names the output
  port that holds the most of those messages, whose reader is the one to
  look at; it need not be the port of the message that went over the
  limit. While the node replays its
  input log, ``send_data`` waits for room instead. A single message
  larger than the limit never fits: ``send_data`` raises at once, live
  or in a replay, with an error that names the size of the message, its
  port and the limit. The replay sends that message again, so the node
  fails the same way at every relaunch, until the program is stopped
  and launched again with a larger ``out_backlog_fail_mb`` for that
  process, or the node sends smaller messages.
* ``gil_switch_interval_ms`` sets ``GIL_SWITCH_INTERVAL_SECS`` (0.5 ms
  by default).
* ``inbound_queue_max_mb`` sets ``INBOUND_QUEUE_MAX_BYTES``, the size of
  the messages that a node of a non-durable program has read and not yet
  processed over which its readers wait (100 MiB by default); in a
  durable program the input log cap bounds them instead.

For example:

.. code-block:: bash

    add_debasher_process "Counter" "cpus=1 mem=256 time=01:00:00 input_log_max_mb=500"

DeBasher checks, when it loads the program, that each value given is a
positive number.

The :doc:`webui_stream_stall` sets small limits on its input log and
its outbound backlog on purpose, so that each of them can be reached
by hand.

What Is Guaranteed and What Is Not
----------------------------------

When the rules for writing a node above are followed, a durable
resident program gives these guarantees (a non-durable one keeps the
first and the fourth, see `Durable and Non-Durable Programs`_ above):

* On every channel, messages arrive in the order in which they were
  sent, and with no failure every message is delivered once.
* A node that crashes (killed, out of memory, an exception in any of its
  threads, which ends its process) and is relaunched returns to the
  state it would have had without the crash, and its readers receive
  neither duplicates nor gaps.
* A snapshot captures a consistent state of every node, and an orderly
  stop followed by a new launch loses nothing.
* A crashed node is detected within a bounded time when the program
  has a ``Supervisor``.
* When a guarantee cannot be kept, the failure is reported, never
  silent.

And these are its limits:

* It survives the crash of processes, not of the machine: nothing is
  forced to disk, so a power loss may lose the last seconds of
  checkpoints and input logs. If what is lost is the end of an input
  log that a checkpoint of its node already reflects, the node
  refuses to start (see `Stopping, Resuming and Resetting`_ above).
* If both ends of a channel crash while no process holds its FIFO (in
  a program without a ``Supervisor``, or with ``-no-hold-fifos``),
  what the FIFO held may be lost; the reader then reports the gap.
* What enters from outside is delivered at most once (see `Writing
  Into a Program From Outside`_ above).
* A node that is alive but stuck, in an endless loop for example, goes
  on sending heartbeats and is not detected. A source that stalls with
  the node alive is detected only if ``observe`` checks its progress and
  raises, as the node ``Acquire`` of the :doc:`webui_stream_stall` does
  with its stream.
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

   webui_stream_stall

   webui_live_stats

   webui_readfish
