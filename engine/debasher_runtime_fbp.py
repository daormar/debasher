"""
DeBasher package
Copyright 2019-2026 Daniel Ortiz-Mart\'inez

This library is free software; you can redistribute it and/or
modify it under the terms of the GNU Lesser General Public License
as published by the Free Software Foundation; either version 3
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Lesser General Public License for more details.

You should have received a copy of the GNU Lesser General Public License
along with this program; If not, see <http://www.gnu.org/licenses/>.
"""

# *- python -*

# import modules
import os
import copy
import dataclasses
import json
import signal
import sys
import threading
import time

from debasher_runtime_envelope import (
    TYPE_BARRIER,
    TYPE_CLOSE,
    TYPE_DATA,
    TYPE_INTERACT,
    decode_envelope,
    encode_data,
)
from debasher_runtime_transport import _PortWorker, _STOP
from debasher_runtime_inputlog import LogCapReached, _InputLog

# What a replay has asked of the notice so far when it has asked nothing
# (see FBPProcess._replayed_notice), which None, a request to clear it,
# cannot stand for.
_NO_NOTICE_REQUEST = object()


#####################
# Rounds            #
#####################


@dataclasses.dataclass
class _Checkpoint:
    """
    What a round captures at a node, and the fields of its checkpoint file,
    with the same names. channel_state fills while the round is open; the
    rest is taken when the round opens.
    """

    epoch: int
    node_state: object
    capture_pos: int = 0
    closed_ports: frozenset = frozenset()
    out_seq: dict = dataclasses.field(default_factory=dict)
    last_seq: dict = dataclasses.field(default_factory=dict)
    out_backlog: dict = dataclasses.field(default_factory=dict)
    channel_state: dict = dataclasses.field(default_factory=dict)

    def to_dict(self, schema_version):
        """The checkpoint as the JSON object of its file."""
        return {
            "schema_version": schema_version,
            "epoch": self.epoch,
            "capture_pos": self.capture_pos,
            "closed_ports": sorted(self.closed_ports),
            "out_seq": dict(self.out_seq),
            "last_seq": dict(self.last_seq),
            "out_backlog": self.out_backlog,
            "node_state": self.node_state,
            "channel_state": self.channel_state,
        }

    @classmethod
    def from_dict(cls, data, schema_version, where):
        """
        The checkpoint that the JSON object `data` of the file `where` holds.
        Raises ValueError if it was written with another schema version, and
        KeyError, naming the field, if a field that it reads is missing.
        """
        if data["schema_version"] != schema_version:
            raise ValueError(
                f"checkpoint {where} has schema version {data['schema_version']!r}, "
                f"expected {schema_version!r}"
            )
        # The channel state is not read: a restore never uses it (the input
        # log holds those messages above capture_pos).
        return cls(
            epoch=data["epoch"],
            node_state=data["node_state"],
            capture_pos=data["capture_pos"],
            closed_ports=frozenset(data["closed_ports"]),
            out_seq=data["out_seq"],
            last_seq=data["last_seq"],
            out_backlog=data["out_backlog"],
        )


@dataclasses.dataclass
class _Round:
    """
    The round open at a node: whether it is a halt, the input ports whose
    marker it still waits for, and what it captured when it opened.
    """

    halt: bool
    pending: set
    capture: _Checkpoint

    @property
    def epoch(self):
        return self.capture.epoch


def _checkpoint_epochs(checkpoints_dir):
    """The epochs of the checkpoint files `<epoch>.json` in `checkpoints_dir`."""
    epochs = []
    for name in os.listdir(checkpoints_dir):
        if not name.endswith(".json"):
            continue
        try:
            epochs.append(int(name[: -len(".json")]))
        except ValueError:
            continue
    return epochs


#####################
# FBPProcess        #
#####################
#
# Base class for a long-running, stateful "resident" process. Adds, on
# top of _PortWorker's generic thread-per-port plumbing: INPUT_PORTS/
# OUTPUT_PORTS declaration, the heartbeat thread, Chandy-Lamport barrier
# logic, INTERACT dispatch, checkpointing, the input log and the
# checkpoint/recovery startup sequence (run()).


class FBPProcess(_PortWorker):
    """
    The base class of every node of a resident program. A module defines a
    node with a subclass, named after its process in CamelCase, that
    redefines the four hooks process_data(), capture_node_state(),
    restore_node_state() and initialize_runtime(), and whose Python code
    creates it and calls run(): `Counter().run()`.

    The ports of the node are the options of its process connected to a
    FIFO, named without their leading dash (`inf` for `-inf`). The engine
    gives them to the node from the options of its module, so the class
    declares none. Every option of the process is in `self.opts`, a dict
    from the name of the option, without its dash, to its value, a
    string; a flag, an option given with no value, is True when it is
    given, and its name has to be listed in the class attribute `FLAGS`
    (for example `FLAGS = ("verbose",)`). `self.log` is a logger from the
    standard `logging` module, which writes to the standard error of the
    process.

    A node acts only in reaction to what it receives: the framework calls
    process_data() once for each message, and a node sends only from
    there. After a crash, the node is restored from its latest checkpoint
    and process_data() is called again for every message received since,
    in the same order, so that the node returns to the state it had.
    """

    # Its ports are option names, without their leading dash(es) (e.g.
    # "inf" for -inf). A node run by the engine takes them from the options
    # of its module (see _take_ports_from_engine); a node built without the
    # engine, as the unit tests build them, declares them in the class
    # attributes below.

    INPUT_PORTS = []
    OUTPUT_PORTS = []

    # The INPUT_PORTS entries that carry only INTERACT commands (from the
    # Supervisor, or from whoever writes commands into a fifo of this node).
    # They are read like any other, but take no part in the barrier, in any
    # round, and a CLOSE on them does not close them: their writer may come
    # back.
    CONTROL_PORTS = []

    # The INPUT_PORTS entries fed only from outside the program (a source
    # with no other business port of this program upstream of it), which
    # therefore never carries a marker: a round waits for it like any other
    # port, unless it is declared here, in which case the round never
    # depends on it. A CLOSE on it still closes it for good, like on any
    # other business port, since (unlike a control port) its writer is not
    # expected to come back. A source that does know the protocol may still
    # write the marker of the round the initiator opened: it is then read
    # like any other, opening or settling a round exactly as if the port
    # were not declared here.
    EXTERNAL_PORTS = []

    # Name of the OUTPUT_PORTS entry wired to the supervisor's heartbeat
    # channel, if any. A supervisor is optional (0 or 1 per resident
    # program): leave this None to run without one, in which case
    # checkpoints are still written, just never announced anywhere.
    SUPERVISOR_PORT = None

    #: How often, in seconds, the node tells the Supervisor of the program
    #: that it is alive.
    HEARTBEAT_INTERVAL_SECONDS = 5

    # The observation of the outside world (see observe()): the name of the
    # port under which what the node observes reaches process_data, which is
    # not a fifo and so not one of its input ports, or None for a node that
    # observes only to act; and how often observe() runs.
    #: The name under which what observe() brings in with inject() reaches
    #: process_data(), as its `port_name`. It is not a FIFO and not one of the
    #: ports of the node. None, the default, for a node that observes only to
    #: act, which cannot call inject().
    OBSERVE_PORT = None
    #: How often, in seconds, observe() runs.
    OBSERVE_INTERVAL_SECS = 1.0

    # The GIL switch interval of the node's process (sys.setswitchinterval),
    # set when run() starts; None keeps Python's own, 5 ms. A reader thread
    # that has taken a block from its fifo needs the GIL back before it can
    # log the block, and while process_data computes it may wait up to this
    # long, with the block only in memory, where the death of the process
    # loses it (see the Contract's limits). A short interval keeps that wait
    # short, at no cost that a measurement tells apart from noise. It applies
    # to the whole process, which the node has to itself.
    #: The GIL switch interval of the process of the node, in seconds (0.5 ms
    #: by default). A program sets it for one of its processes with the
    #: computational specification `gil_switch_interval_ms`.
    GIL_SWITCH_INTERVAL_SECS = 0.0005
    CHECKPOINT_SCHEMA_VERSION = 2
    CHECKPOINT_RETENTION = 3

    # Size limits of the input log (see _InputLog). The cap on all its
    # segments together is a safety net, never the normal way old history
    # goes away (that is pruning by position after each checkpoint): if it is
    # reached, the node has gone so long without closing an epoch that pruning
    # could not keep up (no periodic or triggered snapshot), a real problem to
    # surface as an error, not something to paper over by discarding history
    # that a recovery may need. A segment is closed, and a new one started,
    # when it reaches the second size.
    #: The size, in bytes, that the input log of the node may reach (100 MiB
    #: by default). The log holds what the node received since its latest
    #: checkpoint, so it only reaches this size when no snapshot has been
    #: taken for a long time; the node then stops with an error. A program
    #: sets it for one of its processes with the computational specification
    #: `input_log_max_mb`.
    INPUT_LOG_MAX_BYTES = 100 * 1024 * 1024
    # The size at which a segment of the input log is closed, at most: a
    # quarter of INPUT_LOG_MAX_BYTES when that is less (see _open_input_log).
    INPUT_LOG_SEGMENT_BYTES = 4 * 1024 * 1024

    # Total size, across every output port, of the DATA that send_data has
    # numbered but the writer thread has not yet finished writing (the
    # outbound backlog, see _unwritten). The first limit only decides how
    # big a single checkpoint is allowed to grow: over it, _save_checkpoint
    # skips writing that checkpoint rather than raising, since the previous
    # one plus the replay of the input log after it regenerate every output
    # since, so nothing is lost by waiting for a smaller round while a
    # neighbor is slow for a while. The second one bounds the memory the
    # backlog takes: send_data raises rather than go over it, since a
    # backlog that keeps growing means that a reader is not reading (it was
    # stopped, is down or stuck, or is slower than this node for good), and
    # a loud failure is better than a node that eats the memory of the
    # machine. A replay of the input log waits for room instead, since it
    # can run faster than a writer thread can write, whoever the reader is.
    #: The size, in bytes, of what send_data() has taken and the node has not
    #: yet written into its FIFOs, since their readers are slow, over which
    #: the node skips a checkpoint and waits for the next round (8 MiB by
    #: default). A program sets it for one of its processes with the
    #: computational specification `out_backlog_max_mb`.
    OUT_BACKLOG_MAX_BYTES = 8 * 1024 * 1024
    #: The size, in bytes, of what send_data() has taken and the node has not
    #: yet written into its FIFOs, over which send_data() raises, since a
    #: reader of the node is not reading, or waits for room while the node
    #: replays its input log (64 MiB by default). A program sets it for one
    #: of its processes with the computational specification
    #: `out_backlog_fail_mb`.
    OUT_BACKLOG_FAIL_BYTES = 64 * 1024 * 1024
    # How often a replay that waits for room in the outbound backlog looks
    # at it again (see _wait_for_room_in_backlog).
    _BACKLOG_POLL_SECS = 0.01
    # The notice of a node (see set_notice): its levels, and the length at
    # which its text is cut.
    NOTICE_LEVELS = ("info", "warning")
    #: The length at which set_notice() cuts the text of a notice.
    NOTICE_MAX_CHARS = 1000

    # The class of the runtime library that a node derives from, which its
    # node info file names (see _write_node_info): a subclass in the runtime
    # library that a module derives from in turn sets its own.
    _RUNTIME_CLASS = "FBPProcess"

    # The computational specifications of a process that set the limits
    # above for that process of a program (see _PortWorker._apply_comp_specs).
    _COMP_SPEC_ATTRS = {
        "input_log_max_mb": ("INPUT_LOG_MAX_BYTES", 1024 * 1024),
        "out_backlog_max_mb": ("OUT_BACKLOG_MAX_BYTES", 1024 * 1024),
        "out_backlog_fail_mb": ("OUT_BACKLOG_FAIL_BYTES", 1024 * 1024),
        "gil_switch_interval_ms": ("GIL_SWITCH_INTERVAL_SECS", 0.001),
    }

    # The field of DEBASHER_PROCESS_PORTS that gives each of the class
    # attributes above that name ports (see
    # _PortWorker._take_ports_from_engine).
    _PORT_FIELDS = {
        "input": "INPUT_PORTS",
        "output": "OUTPUT_PORTS",
        "control": "CONTROL_PORTS",
        "external": "EXTERNAL_PORTS",
        "supervisor": "SUPERVISOR_PORT",
    }

    def __init__(self, argv=None, opts=None):
        super().__init__(argv, opts)

        self._heartbeat_thread = None
        self._heartbeat_stop = threading.Event()
        # When this incarnation started its threads (see start_threads).
        self._started_at = None

        # The observation thread, started only for a class that defines
        # observe(), and what wakes it before its interval (observe_now).
        self._observe_thread = None
        self._observe_stop = threading.Event()
        self._observe_wake = threading.Event()
        observe_port = self._observe_port()
        if observe_port is not None and observe_port in self.INPUT_PORTS:
            raise ValueError(
                f"{type(self).__name__}: OBSERVE_PORT names {observe_port!r}, which is one of "
                "its input ports: what the node observes is not read from a fifo, and "
                "process_data has to tell it apart from what arrives on its ports"
            )

        # The Chandy-Lamport round open at this node, None when there is none.
        self._round = None
        # Highest epoch this node has closed or abandoned; -1 means none
        # yet, so the first round it self-initiates is epoch 0. run() seeds
        # it from the restored checkpoint, or a relaunched node would start
        # renumbering from 0 again.
        self._last_epoch = -1

        # The input ports whose writer has said CLOSE, as far as the brain
        # thread has processed: the position of a CLOSE in the input log
        # decides, so what the reader threads have already read but the
        # brain has not reached does not count. Once the threads run, only
        # the brain thread changes it; run() fills it from the checkpoint
        # and the input log before they start.
        self._closed_ports = set()
        # What it held when the threads started, which the readers of those
        # ports start out knowing (see _closed_at_start).
        self._closed_at_start_ports = frozenset()

        # The sender's own counter of each output port: the number of the
        # last DATA that send_data numbered on it, 0 before the first one.
        # Restored from the checkpoint (before initialize_runtime(), see
        # run()) so that a replay regenerates the same numbers a crashed
        # incarnation had already used. Only the thread inside process_data()
        # ever calls send_data (see it below), so this needs no lock.
        self._out_seq = {}
        # The receiver's own view of the last DATA number it has processed on
        # each input port, updated by the brain thread as it dispatches each
        # one (mirrors _current_pos, but per channel): what a round's capture
        # takes for the checkpoint, which is why it lags behind
        # _accepted_seq below. Restored from the checkpoint before
        # initialize_runtime(), like _out_seq.
        self._last_seq = {}
        # The reader threads' own view of the same thing, ahead of _last_seq:
        # updated at arrival, under _arrival_lock, before a DATA is logged or
        # queued, so that a duplicate produced by a replay is dropped before
        # either happens. Restored at startup from the checkpoint's
        # last_seq plus whatever the input log holds after capture_pos (see
        # _replay_input_log), since that is what the reader threads had
        # already accepted, whether the brain had processed it or not.
        self._accepted_seq = {}
        # DATA that send_data has numbered and queued but the writer thread
        # has not yet finished writing (the outbound backlog): {tag: [(seq,
        # line), ...]}, in the order send_data queued them, so the entry at
        # index 0 is always the next one _on_written can confirm. A single
        # kill -9 destroys the outbound queue itself, so a round's capture
        # copies this (decoded, see _snapshot_out_backlog) into the
        # checkpoint, and recovery re-enqueues it with the same numbers
        # before anything else is sent (see _restore_out_backlog). Touched by
        # both the thread inside process_data() (send_data appends) and the
        # writer threads (_on_written pops), hence the lock.
        self._unwritten = {}
        # The size of every line in _unwritten together, kept up to date
        # with it (under the same lock) so that send_data checks
        # OUT_BACKLOG_FAIL_BYTES at no cost.
        self._unwritten_bytes = 0
        # The same, for each output port, which the node info file reports
        # (see _write_node_info) with no need to go through the backlog.
        self._unwritten_port_bytes = {}
        self._out_backlog_lock = threading.Lock()
        # Whether this replay has already said that it waits for room in the
        # outbound backlog (see _wait_for_room_in_backlog).
        self._replay_wait_warned = False
        # The epoch of the first round whose checkpoint was skipped because
        # of the size of the outbound backlog, since the last one written;
        # None while checkpoints are being written. Only the brain thread
        # writes it; a reader thread reads it to explain an input log that
        # reached its cap (see _on_arrivals).
        self._checkpoints_skipped_since = None

        # Every envelope that a reader thread queues gets a position and a record
        # in the input log before the brain thread can see it. The lock makes
        # taking the position, writing the record and queuing the envelope a
        # single step, so that the order of the positions, of the log and of
        # the queue is one and the same. It also keeps pruning from running
        # while a record is being appended. The log is opened by run(), or by
        # start_threads() when the node is driven without run().
        self._arrival_lock = threading.Lock()
        self._input_log = None
        # Position of the envelope that the brain thread is processing, 0 before
        # the first one. Only the brain thread reads or writes it.
        self._current_pos = 0
        # Identity of the thread that is inside process_data() right now, None
        # between calls (see send_data).
        self._handler_thread = None

        # Set once an epoch closes with halt=True: keeps a trigger from
        # opening another round in this incarnation (see _on_trigger); the
        # marker of a peer still opens one. Never itself stops a thread.
        self._halted = threading.Event()
        # Set only by the SIGTERM handler run() installs (see
        # _on_stop_signal): the actual "stop now" signal that run() waits
        # on, decided entirely outside this node, typically by an external
        # tool once every node's halted marker exists (see "Ordered
        # shutdown" and "`debasher_stop_resident`" in
        # doc/design_doc_resident.md).
        self._stop_requested = threading.Event()
        # Whether the node is replaying its input log (see
        # _replay_input_log). Internal: a module never sees it, so that
        # neither its node state nor what it sends can depend on it; sleep()
        # and set_notice() are what use it.
        self._replaying = False
        # The notice of the node as its notice file holds it, {"level",
        # "text"}, or None without one, and what a replay asked for last,
        # applied once it ends (_NO_NOTICE_REQUEST while it asked nothing).
        # The comparison with it, the write of the file and its rename go
        # under _notice_lock, so that the file always holds the notice that
        # was set last, whatever thread set it.
        self._notice = None
        self._replayed_notice = _NO_NOTICE_REQUEST
        self._notice_lock = threading.Lock()

    def _port_field_value(self, attribute, items):
        """
        A list of ports, except SUPERVISOR_PORT, a single port or None (see
        _PortWorker._take_ports_from_engine).
        """
        if attribute == "SUPERVISOR_PORT":
            return items[0] if items else None
        return items

    def _input_ports(self):
        return {port: port for port in self.INPUT_PORTS}

    def _check_declared_ports(self):
        super()._check_declared_ports()
        unknown = [port for port in self.CONTROL_PORTS if port not in self.INPUT_PORTS]
        if unknown:
            raise ValueError(
                f"{type(self).__name__}: CONTROL_PORTS names {unknown}, which are not in INPUT_PORTS "
                f"(got: {list(self.INPUT_PORTS)})"
            )
        unknown = [port for port in self.EXTERNAL_PORTS if port not in self.INPUT_PORTS]
        if unknown:
            raise ValueError(
                f"{type(self).__name__}: EXTERNAL_PORTS names {unknown}, which are not in INPUT_PORTS "
                f"(got: {list(self.INPUT_PORTS)})"
            )
        if self.SUPERVISOR_PORT is not None and self.SUPERVISOR_PORT not in self.OUTPUT_PORTS:
            raise ValueError(
                f"{type(self).__name__}: SUPERVISOR_PORT names {self.SUPERVISOR_PORT!r}, which is "
                f"not in OUTPUT_PORTS (got: {list(self.OUTPUT_PORTS)})"
            )

    def _output_ports(self):
        return {port: port for port in self.OUTPUT_PORTS}

    # -- startup sequence --

    def run(self):
        """
        Runs the node until it is told to stop. The Python code of the
        process calls it once, after creating the node. It restores the
        node from its latest checkpoint with restore_node_state(), calls
        initialize_runtime(), calls process_data() again for every message
        received since that checkpoint, and then processes what arrives.
        """
        # Full startup sequence: install the SIGTERM handler -> open every
        # FIFO -> find the most recent checkpoint if any ->
        # restore_node_state()/defaults, and the sender counters with it (see
        # _out_seq) -> initialize_runtime() -> open the input log -> start
        # the writer threads, after the restored backlog is queued, so that it
        # reaches a neighbor before what the replay sends again, and so that
        # what the replay sends drains while it replays -> replay what the
        # log holds after the checkpoint (all of it if there is no
        # checkpoint, since the node state is then the default one) ->
        # start_threads() (starts the other threads) -> wait until told to
        # stop (SIGTERM, from outside this process; see _on_stop_signal and
        # _stop_requested) -> stop every thread, from this (the calling)
        # thread rather than the one that actually delivered the signal. A
        # halt closing its epoch is not part of this wait (see
        # _on_epoch_closed): it behaves like an ordinary snapshot, and this
        # node keeps running until told to stop by signal, whether or not it
        # ever halted.
        #
        # A signal handler can only be installed from the main thread; a
        # node driven by run() on a background thread (every test that does
        # this) has no real SIGTERM to catch anyway, and simulates the stop
        # request by setting _stop_requested directly, the same way other
        # tests simulate an external INTERACT arriving.
        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGTERM, self._on_stop_signal)

        if self.GIL_SWITCH_INTERVAL_SECS is not None:
            sys.setswitchinterval(self.GIL_SWITCH_INTERVAL_SECS)

        # The FIFOs are held from the very first moment of the recovery, not
        # from the moment the threads start. Restoring and replaying can take
        # a while, and a FIFO keeps what its neighbors sent only while some
        # process holds it open, which during that time may be the neighbor
        # alone: if it crashed too, everything it had sent would be destroyed.
        self._open_fifos()

        # Each incarnation starts with no notice: one of an earlier
        # incarnation may speak of a fault fixed since.
        self._remove_notice_file()

        # A node that lacks a port its class relies on runs, but does nothing
        # useful: it says so to whoever watches the program
        problem = self._wiring_problem()
        if problem is not None:
            self.log.warning("%s", problem)
            self.set_notice(problem, level="warning")

        checkpoint = self._load_latest_checkpoint()
        capture_pos = 0
        if checkpoint is not None:
            capture_pos = checkpoint.capture_pos
            self.restore_node_state(checkpoint.node_state)
            self._last_epoch = checkpoint.epoch
            self._closed_ports = set(checkpoint.closed_ports)
            self._out_seq = dict(checkpoint.out_seq)
            self._last_seq = dict(checkpoint.last_seq)
            # The reader threads' own counters start at the same point; if the
            # log holds DATA after capture_pos, _replay_input_log advances them
            # past it, to what the reader threads had already accepted before
            # the crash, whether the brain had processed it or not.
            self._accepted_seq = dict(checkpoint.last_seq)
            # What was numbered but not yet written reaches a neighbor before
            # anything process_data() sends again while replaying the log.
            self._restore_out_backlog(checkpoint.out_backlog)
            self.log.info("restored checkpoint for epoch %s", checkpoint.epoch)
        else:
            self.log.info("no checkpoint found, starting with default values")

        self.initialize_runtime()

        self._open_input_log(capture_pos)
        self._start_writer_threads()
        self._replay_input_log(capture_pos)

        # The threads that are not daemons keep the process alive, so a
        # failure while they start has to stop them, or the process would
        # stay up doing nothing, and deaf to a SIGTERM.
        try:
            self.start_threads()
        except BaseException:
            self.stop_threads(close=False)
            raise
        self._stop_requested.wait()
        # A halt is an orderly stop that the whole program is resumed from
        # later, not the end of this node. CLOSE is what a writer says when
        # it has finished for good, and a peer that read one at a halt would
        # take this node for a finished one when it comes back. This is why
        # close=False here does not depend on whether this node ever
        # halted: the only way run() ever gets past the wait above is an
        # external stop signal, which carries the same "come back later"
        # meaning regardless.
        self.stop_threads(close=False)

    def _on_stop_signal(self, signum, frame):
        """
        The SIGTERM handler run() installs. Deliberately minimal (a signal
        handler runs on the main thread, interrupting whatever bytecode was
        executing there, so it must not touch a lock some other code might
        already hold): only sets the event run() is waiting on. Actually
        stopping every thread happens on run()'s own thread, after its wait
        returns, same as it always has.
        """
        self._stop_requested.set()

    def _load_latest_checkpoint(self):
        """
        Returns the _Checkpoint of the highest epoch in this process's
        checkpoints directory, or None if there is none yet (a brand new
        process, or one that has never closed an epoch). Raises ValueError
        if its schema version is not this class's, and KeyError if a field
        that it reads is missing: a real incompatibility, never papered over by falling
        back to an older checkpoint or a default value.
        """
        checkpoints_dir = self._checkpoints_dir()
        if not os.path.isdir(checkpoints_dir):
            return None
        epochs = _checkpoint_epochs(checkpoints_dir)
        if not epochs:
            return None

        path = os.path.join(checkpoints_dir, f"{max(epochs)}.json")
        with open(path) as f:
            data = json.load(f)
        try:
            return _Checkpoint.from_dict(data, self.CHECKPOINT_SCHEMA_VERSION, path)
        except ValueError as exc:
            raise ValueError(f"{type(self).__name__}: {exc}") from None

    # -- thread topology --

    def start_threads(self):
        """
        Starts everything _PortWorker.start_threads() already does
        (reader/writer/brain threads), plus this class's own heartbeat
        thread. The input log has to be open before any reader thread
        runs: run() opens it after recovering a checkpoint, and a node
        that is driven without run() gets it opened here, empty of any
        checkpoint. Also writes this incarnation's control ports file (see
        _write_control_ports_file), since self.opts is enough for that on
        its own, with no need to wait for any of the above, and its first
        node info file (see _write_node_info), before the heartbeat thread
        that writes it again is started.
        """
        self._write_control_ports_file()
        if self._input_log is None:
            self._open_input_log(0)
        self._closed_at_start_ports = frozenset(self._closed_ports)
        super().start_threads()
        self._started_at = time.time()
        self._report_node_info(self._all_threads_alive())
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, name="heartbeat")
        self._heartbeat_thread.start()
        if self._observes():
            self._observe_thread = threading.Thread(target=self._observe_loop, name="observer")
            self._observe_thread.start()

    def _control_ports_path(self):
        return self._execdir_entry("control_ports")

    def _write_control_ports_file(self):
        """
        Writes, one per line, the fifo path of every one of this node's
        CONTROL_PORTS: how an external tool with no other knowledge of this
        program finds where to write a trigger for it, the same way it
        already finds a node's PID from its `.id` file (see debasher_stop).
        Written even when there are none (an empty file), so that its mere
        absence still means "this incarnation hasn't started yet". Atomic
        (temp file + rename), the same pattern _save_checkpoint uses,
        though nothing here changes after this first write of an
        incarnation.
        """
        os.makedirs(self._execdir(), exist_ok=True)
        path = self._control_ports_path()
        tmp_path = f"{path}.tmp"
        with open(tmp_path, "w") as f:
            for port in self.CONTROL_PORTS:
                f.write(self.opts[port] + "\n")
        os.replace(tmp_path, path)

    def _node_info_path(self):
        return self._execdir_entry("node_info")

    def _node_info_extra(self):
        """What a subclass of the runtime library adds to the node info file,
        under names of its own: nothing here."""
        return {}

    def _write_node_info(self, healthy):
        """
        Writes the node info file: what a tool outside the node (see
        debasher_inspect_resident) needs to know of it and cannot read
        anywhere else. The limits in force, which the class and the
        computational specifications of the process decide, and the size of
        the outbound backlog, which lives only in memory, and whose copy in a
        checkpoint is missing precisely when it grows too large. Written when
        the threads start and again at every tick of the heartbeat thread,
        with `healthy` as that tick found it. Atomic (temp file + rename),
        like a checkpoint. Nothing in the node reads it back: it is not part
        of the state of the node.
        """
        with self._out_backlog_lock:
            out_backlog_bytes = dict(self._unwritten_port_bytes)
        info = {
            "runtime_class": self._RUNTIME_CLASS,
            "started_at": self._started_at,
            "heartbeat_interval_secs": self.HEARTBEAT_INTERVAL_SECONDS,
            "limits": {
                "input_log_max_bytes": self.INPUT_LOG_MAX_BYTES,
                "out_backlog_max_bytes": self.OUT_BACKLOG_MAX_BYTES,
                "out_backlog_fail_bytes": self.OUT_BACKLOG_FAIL_BYTES,
                "gil_switch_interval_secs": self.GIL_SWITCH_INTERVAL_SECS,
            },
            **self._node_info_extra(),
            "updated_at": time.time(),
            "healthy": healthy,
            "out_backlog_bytes": out_backlog_bytes,
            "checkpoints_skipped_since": self._checkpoints_skipped_since,
        }
        path = self._node_info_path()
        tmp_path = f"{path}.tmp"
        with open(tmp_path, "w") as f:
            json.dump(info, f)
        os.replace(tmp_path, path)

    def _report_node_info(self, healthy):
        """Writes the node info file. One that cannot be written is not a
        reason to stop the node: it only reports, so the node goes on and
        its file goes stale."""
        try:
            self._write_node_info(healthy)
        except OSError as exc:
            self.log.warning("cannot write the node info file: %r", exc)

    def stop_threads(self, timeout=None, close=True):
        """
        Signals the heartbeat thread to stop, then defers to
        _PortWorker.stop_threads() for the reader/writer/brain threads,
        then joins the heartbeat thread too.
        """
        self._heartbeat_stop.set()
        self._observe_stop.set()
        self._observe_wake.set()
        if self._observe_thread is not None:
            self._observe_thread.join(timeout)
        super().stop_threads(timeout, close)
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout)
        if self._input_log is not None:
            self._input_log.close()

    def _all_threads_alive(self):
        alive = super()._all_threads_alive()
        if self._observe_thread is not None:
            alive = alive and self._observe_thread.is_alive()
        return alive

    # -- observation of the outside world --

    def _observes(self):
        return type(self).observe is not FBPProcess.observe

    def _observe_port(self):
        """The name under which inject() brings what the node observes to
        process_data, or None if it has none. A subclass may decide it from
        its ports."""
        return self.OBSERVE_PORT

    def _observe_loop(self):
        while not self._observe_stop.is_set():
            self.observe()
            self._observe_wake.wait(self.OBSERVE_INTERVAL_SECS)
            self._observe_wake.clear()
        self.log.debug("observation thread stopped")

    def observe_now(self):
        """Makes observe() run now, and not at the end of its interval."""
        self._observe_wake.set()

    def inject(self, payload):
        """
        Brings `payload`, something that observe() saw, into the node as a
        message: process_data() receives it with OBSERVE_PORT as its
        `port_name`. The message is recorded like any other, so that a
        replay after a crash receives it again without looking at the
        world again. It returns once the message is recorded. It raises
        when called from process_data(), since an input made by processing
        would be made again by every replay, or when the class has no
        OBSERVE_PORT; and ValueError when `payload` holds NaN or an
        infinity, which JSON does not have.
        """
        # Writes it to the input log and queues it for the brain thread, as
        # a reader thread does with what it reads from a fifo, in the same
        # order across every port (see _on_arrivals). Returning once it is
        # logged means that whatever observe() records afterwards (that it
        # reported something, for example) never gets ahead of what the
        # node has logged.
        if self._handler_thread == threading.get_ident():
            raise RuntimeError(
                f"{type(self).__name__}: inject() brings in what observe() sees; "
                "process_data() sends with send_data()"
            )
        port = self._observe_port()
        if port is None:
            raise RuntimeError(
                f"{type(self).__name__}: inject() needs OBSERVE_PORT, the name under which "
                "what the node observes reaches process_data"
            )
        line = encode_data(payload)
        self._on_arrivals(port, [(decode_envelope(line), line)])

    def _closed_at_start(self, tag):
        return tag in self._closed_at_start_ports

    def _drops_after_close(self, tag):
        # The writer of a control port may come back after saying CLOSE, and
        # what it sends then must be heard.
        return tag not in self.CONTROL_PORTS

    def _types_of_port(self, tag):
        # A control port carries only commands; a business port, and an
        # external one (whose source may write the marker of a round),
        # messages and markers.
        if tag in self.CONTROL_PORTS:
            return (TYPE_INTERACT,)
        return (TYPE_DATA, TYPE_BARRIER)

    def _on_arrival(self, tag, envelope, line):
        self._on_arrivals(tag, [(envelope, line)])

    def _on_arrivals(self, tag, envelopes):
        """
        Records in the input log, and then queues for the brain thread, the
        envelopes of one block that a reader thread has taken from its fifo, all
        of them in one write (see _log_arrivals). The lock keeps
        the positions in the log in the order in which the brain thread gets
        the envelopes, across the reader threads of every port.
        """
        with self._arrival_lock:
            if self._input_log is None:
                raise RuntimeError(
                    f"{type(self).__name__}: an envelope arrived before the input log was opened"
                )
            accepted, close_checks, gap = self._filter_by_seq(tag, envelopes)
            positions = self._log_arrivals(tag, accepted)
            self._queue_arrivals(tag, accepted, positions)
            # A CLOSE is checked only now, after it is itself durably logged
            # and queued, unlike a DATA gap: nothing ever sends CLOSE a second
            # time, so losing it here to an early raise would leave this
            # port's writer looking unfinished forever, rather than reporting
            # one lost message and moving on.
            self._check_close_claims(tag, close_checks)
            if gap is not None:
                raise gap

    def _filter_by_seq(self, tag, envelopes):
        """
        Returns the (envelope, line) pairs of `envelopes` to log, what each CLOSE
        among them has to be checked against, and the error of a gap, if any.

        No duplicates across a crash: a DATA that carries a number not above
        the last one this channel's reader has already accepted is a
        duplicate, produced by a replay on the sender's side, and is dropped
        here, before it is ever logged or queued, so that it is never
        processed twice. One that skips over a number is a message this
        channel will never see: a real loss, not a duplicate, so it is never
        silent. The envelopes before it are logged and queued, as they would be
        one by one, and then it raises, before it is itself logged or queued.
        A DATA with no number (from a source, or a plain _PortWorker) is not
        part of the numbering and is always accepted; only DATA is sequenced
        (BARRIER/INTERACT carry no seq of their own; CLOSE carries the
        sender's last one instead, see _check_close_claims).
        """
        accepted_envelopes = []
        close_checks = []
        for envelope, line in envelopes:
            if envelope.type == TYPE_DATA and envelope.seq is not None:
                accepted = self._accepted_seq.get(tag, 0)
                if envelope.seq <= accepted:
                    self.log.debug(
                        "reader for %r dropped a duplicate: seq %s is not above %s "
                        "already accepted",
                        tag,
                        envelope.seq,
                        accepted,
                    )
                    continue
                if envelope.seq > accepted + 1:
                    missing = (
                        f"{accepted + 1}"
                        if envelope.seq == accepted + 2
                        else f"{accepted + 1} to {envelope.seq - 1}"
                    )
                    gap = ValueError(
                        f"{type(self).__name__}: gap in the sequence numbers on {tag!r}: "
                        f"expected {accepted + 1}, got {envelope.seq}, missing {missing}"
                    )
                    return accepted_envelopes, close_checks, gap
                self._accepted_seq[tag] = envelope.seq
            if envelope.type == TYPE_CLOSE:
                close_checks.append((envelope, self._accepted_seq.get(tag, 0)))
            accepted_envelopes.append((envelope, line))
        return accepted_envelopes, close_checks, None

    def _log_arrivals(self, tag, accepted):
        """
        Writes the envelopes `accepted` in the input log, in one write, and
        returns their positions: the records are in the file before the
        brain thread can see them. If this raises, the exception ends
        the reader thread, which is how the heartbeat notices: after a failed
        write none of them is queued, and at the size cap only the
        ones logged before it are.
        """
        # Every envelope of the block goes in one write, so that none of them
        # waits in memory for the others to be logged: what a reader has taken
        # from its fifo and not yet logged is lost if the process dies (see the
        # Contract's limits). A write cut short by the death of the process
        # leaves the records it wrote whole and a torn tail, which recovery
        # ignores.
        try:
            return self._input_log.append_many([(tag, line) for _, line in accepted])
        except LogCapReached as exc:
            self._queue_arrivals(tag, accepted, exc.positions)
            skipped_since = self._checkpoints_skipped_since
            if skipped_since is None:
                raise
            # Rounds do close here, but none has written a checkpoint
            # for a while, so nothing has been pruned: the real cause is
            # a reader of this node that is not keeping up.
            raise LogCapReached(
                f"{exc}; the cause here: no checkpoint has been "
                f"written since epoch {skipped_since}, because the outbound backlog "
                f"is over OUT_BACKLOG_MAX_BYTES ({self.OUT_BACKLOG_MAX_BYTES}): a "
                "reader of this node is not keeping up with it",
                exc.positions,
            ) from None

    def _queue_arrivals(self, tag, accepted, positions):
        """Queues for the brain thread the envelopes that were given `positions`."""
        for pos, (envelope, _) in zip(positions, accepted):
            self._inbound_queue.put((pos, tag, envelope.type, envelope.payload, envelope.seq))

    def _check_close_claims(self, tag, close_checks):
        """Raises if a CLOSE claims to have sent more than was accepted."""
        for envelope, accepted in close_checks:
            claimed = envelope.payload.get("last_seq")
            if claimed is not None and claimed > accepted:
                missing = f"{accepted + 1}" if claimed == accepted + 1 else f"{accepted + 1} to {claimed}"
                raise ValueError(
                    f"{type(self).__name__}: {tag!r} closed for good after sending up "
                    f"to {claimed}, but only {accepted} was ever accepted here, "
                    f"missing {missing}"
                )

    def _brain_loop(self):
        while True:
            queued = self._inbound_queue.get()
            if queued is _STOP:
                break
            pos, port_name, envelope_type, payload, seq = queued
            self._current_pos = pos
            if envelope_type == TYPE_DATA:
                if seq is not None:
                    self._last_seq[port_name] = seq
                if self._round is not None and port_name in self._round.pending:
                    # A barrier round is open and this port's marker for
                    # it hasn't arrived yet: this DATA was sent before
                    # its sender's own snapshot and arrives after this
                    # node's, so it is in transit at the cut and part of
                    # the round's channel state. Only a copy is recorded
                    # here (taken now, so that process_data() cannot
                    # alter it through the packet it is handed): the
                    # message itself is still processed right below,
                    # like any other and in arrival order.
                    self._round.capture.channel_state[port_name].append(
                        copy.deepcopy(payload)
                    )
                self._run_process_data(port_name, payload)
            elif envelope_type == TYPE_BARRIER:
                self._on_barrier(port_name, payload)
            elif envelope_type == TYPE_INTERACT:
                self._on_interact(payload)
            elif envelope_type == TYPE_CLOSE:
                self._on_close(port_name)
        self.log.debug("brain thread stopped")

    def _run_process_data(self, port_name, packet):
        """
        Calls process_data() for one message, on the calling thread, and marks
        that thread as the one that may send while the call lasts (see
        send_data). Both the brain thread and the thread that replays the
        input log go through here.
        """
        self._handler_thread = threading.get_ident()
        try:
            self.process_data(port_name, packet)
        finally:
            self._handler_thread = None

    def sleep(self, seconds):
        """
        Waits `seconds`, from process_data(), to set the pace of a node that
        emits on its own through a self-loop. It does not wait while the
        node replays its input log after a crash, where the pace would only
        delay the recovery, and it returns early once the node is told to
        stop. Use it instead of time.sleep(): it changes only when the next
        step comes, never the node state or what is sent.
        """
        if self._replaying:
            return
        self._stop_requested.wait(seconds)

    # -- the notice --

    def set_notice(self, text, level="info"):
        """
        Leaves a notice for whoever watches the program, such as that the
        configuration file of the node is missing. A node has at most one
        notice, and a new one replaces the one it had. `level` is "info" or
        "warning"; a text longer than NOTICE_MAX_CHARS is cut, with a
        warning in the log. It may be called from any hook and any thread.
        The notice is not part of the node state, and each incarnation of
        the node starts without one, so a notice that follows from the node
        state is set again in restore_node_state(). A notice that cannot be
        written leaves a warning in the log and does not stop the node.
        debasher_inspect_resident shows it, and the web interface marks the
        node that has one.
        """
        # It goes to the notice file of the node. While the node replays its
        # input log only the last request counts, applied once the replay
        # ends.
        if level not in self.NOTICE_LEVELS:
            raise ValueError(
                f"{type(self).__name__}: the level of a notice is one of {list(self.NOTICE_LEVELS)}, "
                f"not {level!r}"
            )
        text = str(text)
        if len(text) > self.NOTICE_MAX_CHARS:
            self.log.warning(
                "the text of a notice has %d characters, cut at NOTICE_MAX_CHARS (%d)",
                len(text),
                self.NOTICE_MAX_CHARS,
            )
            text = text[: self.NOTICE_MAX_CHARS]
        self._request_notice({"level": level, "text": text})

    def clear_notice(self):
        """Takes away the notice of the node, if it has one (see set_notice)."""
        self._request_notice(None)

    def _request_notice(self, notice):
        with self._notice_lock:
            if self._replaying:
                self._replayed_notice = notice
                return
            self._write_notice(notice)

    def _apply_replayed_notice(self):
        """Applies what the replay that just ended asked for last, if
        anything: a long replay costs one write."""
        with self._notice_lock:
            notice, self._replayed_notice = self._replayed_notice, _NO_NOTICE_REQUEST
            if notice is not _NO_NOTICE_REQUEST:
                self._write_notice(notice)

    def _notice_path(self):
        return self._execdir_entry("notice")

    def _write_notice(self, notice):
        """
        Makes the notice file hold `notice`, or removes it for None, unless
        it already does. Atomic (temp file + rename), like the node info
        file. Called with _notice_lock held. A file that cannot be written
        is not a reason to stop the node: a notice only reports. The copy in
        memory then stays as it was, so asking for this notice again tries
        the write again.
        """
        if notice == self._notice:
            return
        path = self._notice_path()
        try:
            if notice is None:
                self._remove_if_present(path)
            else:
                os.makedirs(self._execdir(), exist_ok=True)
                tmp_path = f"{path}.tmp"
                with open(tmp_path, "w") as f:
                    json.dump({**notice, "set_at": time.time()}, f)
                os.replace(tmp_path, path)
        except OSError as exc:
            self.log.warning("cannot write the notice file: %r", exc)
            return
        self._notice = notice

    @staticmethod
    def _remove_if_present(path):
        try:
            os.remove(path)
        except FileNotFoundError:
            pass

    def _wiring_problem(self):
        """
        What the ports of the node lack for its class to do its work, or
        None. A class of the runtime library that relies on a port by the
        name it gives it (DirectoryWatcher, ProgramLauncher) redefines it;
        run() turns the answer into a warning notice at every start.
        """
        return None

    def _remove_notice_file(self):
        with self._notice_lock:
            try:
                self._remove_if_present(self._notice_path())
            except OSError as exc:
                self.log.warning("cannot remove the notice file: %r", exc)
            self._notice = None

    def send_data(self, tag, payload):
        """
        Sends `payload`, any value that JSON can serialize, on the output
        port `tag`. It raises ValueError when `payload` holds NaN or an
        infinity, which JSON does not have (a float result that can be one
        is sent as None or as a string), and when `tag` is not one of its
        output ports. A node acts only in reaction to
        what it receives, so it may be called only from process_data(), and
        raises anywhere else. It also raises when what
        the node has not yet written into its FIFOs would go over
        OUT_BACKLOG_FAIL_BYTES; while the node replays its input log, it
        waits for room instead. When it raises, nothing is sent.
        """
        # The message is numbered with this channel's next sequence number
        # (see _out_seq). "Only from process_data()"
        # means on the thread that is running it: the brain thread, or the
        # thread that called run() while it replays the input log. That
        # keeps the messages a node sends, and the state it captures, in the
        # order in which it processed what it received, which is what a
        # replay reproduces: restored from the same checkpoint, it renumbers
        # what it sends again exactly the same way.
        if self._handler_thread != threading.get_ident():
            raise RuntimeError(
                f"{type(self).__name__}: send_data() called outside process_data(), "
                "or from a thread other than the one running it: a node sends only "
                "in reaction to a message that it receives"
            )
        if tag not in self._outbound_queues:
            raise ValueError(
                f"{type(self).__name__}: send_data() on {tag!r}, which is not one of "
                f"its output ports: {sorted(self._outbound_queues)}"
            )
        seq = self._out_seq.get(tag, 0) + 1
        line = encode_data(payload, seq=seq)
        if self._replaying:
            self._wait_for_room_in_backlog(len(line))
        with self._out_backlog_lock:
            if self._unwritten_bytes + len(line) > self.OUT_BACKLOG_FAIL_BYTES:
                port_bytes = self._unwritten_port_bytes.get(tag, 0)
                raise RuntimeError(
                    f"{type(self).__name__}: the outbound backlog would go over "
                    f"OUT_BACKLOG_FAIL_BYTES ({self.OUT_BACKLOG_FAIL_BYTES} bytes) with this "
                    f"message on {tag!r}, which holds {port_bytes} bytes not yet written: "
                    "a reader of this node is not reading (it was stopped, is down or "
                    "stuck, or is slower than this node)"
                )
            self._add_to_out_backlog(tag, seq, line)
        self._out_seq[tag] = seq
        self._outbound_queues[tag].put(line)

    def _wait_for_room_in_backlog(self, size):
        """
        Returns once a message of `size` bytes fits under
        OUT_BACKLOG_FAIL_BYTES, or the backlog is empty, so that a message
        larger than the limit gets its error instead of waiting for ever, or
        the node is told to stop, which send_data then reports as the error
        that it is: the backlog is still over the limit.
        """
        while not self._stop_requested.is_set():
            with self._out_backlog_lock:
                if (
                    not self._unwritten_bytes
                    or self._unwritten_bytes + size <= self.OUT_BACKLOG_FAIL_BYTES
                ):
                    return
            if not self._replay_wait_warned:
                self._replay_wait_warned = True
                self.log.warning(
                    "the replay of the input log waits for room in the outbound backlog, "
                    "over OUT_BACKLOG_FAIL_BYTES (%d bytes): a reader of this node is not "
                    "keeping up with it",
                    self.OUT_BACKLOG_FAIL_BYTES,
                )
            self._stop_requested.wait(self._BACKLOG_POLL_SECS)

    def _on_written(self, tag, line):
        """
        The writer thread has finished writing `line`. If it is the numbered
        DATA line send_data is still waiting to see written (always the
        oldest one queued for `tag`, since a queue is FIFO and _unwritten is
        only ever appended to in that same order), it leaves the backlog: a
        crash from here on no longer loses it, since it already reached the
        fifo (see the Contract's limits on that). A BARRIER, an INTERACT or a
        CLOSE line never matches, and changes nothing here.
        """
        with self._out_backlog_lock:
            backlog = self._unwritten.get(tag)
            if backlog and backlog[0][1] == line:
                backlog.pop(0)
                self._unwritten_bytes -= len(line)
                self._unwritten_port_bytes[tag] -= len(line)

    def _add_to_out_backlog(self, tag, seq, line):
        """Appends a numbered DATA line to the outbound backlog of `tag`,
        keeping its sizes up to date. The caller holds _out_backlog_lock."""
        self._unwritten.setdefault(tag, []).append((seq, line))
        self._unwritten_bytes += len(line)
        self._unwritten_port_bytes[tag] = self._unwritten_port_bytes.get(tag, 0) + len(line)

    def _close_payload(self, tag):
        """
        `_out_seq[tag]`, 0 if this port never sent anything: by the time a
        writer thread is about to send CLOSE, the brain thread has already
        stopped (a finished writer means run() is on its way out), so
        nothing can bump this again and reading it here needs no lock.
        """
        return self._out_seq.get(tag, 0)

    def _restore_out_backlog(self, out_backlog):
        """
        Re-enqueues, with their original numbers, the DATA that a round's
        capture found still unwritten (see _snapshot_out_backlog): what
        send_data had already numbered before the crash but the writer
        thread had not yet gotten to. Called by run(), before anything else
        is sent, so these reach a neighbor ahead of whatever process_data()
        sends again while replaying the input log. Bypasses send_data itself
        (its numbering has already happened, and this does not run from
        inside process_data()).
        """
        for tag, entries in out_backlog.items():
            for entry in entries:
                seq = entry["seq"]
                line = encode_data(entry["payload"], seq=seq)
                with self._out_backlog_lock:
                    self._add_to_out_backlog(tag, seq, line)
                self._outbound_queues[tag].put(line)

    def _snapshot_out_backlog(self):
        """
        A round's own copy of _unwritten, taken at the capture (see
        _open_round): {tag: [{"seq":, "payload":}, ...]}, decoded
        fresh from each line rather than kept as the line itself, so the
        checkpoint holds plain values, not escaped JSON text, and a port
        with nothing unwritten is left out entirely.
        """
        with self._out_backlog_lock:
            return {
                tag: [{"seq": seq, "payload": decode_envelope(line).payload} for seq, line in entries]
                for tag, entries in self._unwritten.items()
                if entries
            }

    def _heartbeat_loop(self):
        # The first heartbeat goes out one interval after the threads start,
        # not at once: a heartbeat resets the relaunch budget of the node at
        # the Supervisor, so it has to show that the node has been healthy
        # for a while, not only that it started. A node whose reader fails on
        # the first live message after every relaunch (a gap in the sequence
        # numbers that no relaunch can fill) must use up its budget.
        while not self._heartbeat_stop.wait(self.HEARTBEAT_INTERVAL_SECONDS):
            healthy = self._all_threads_alive()
            self.log.debug("heartbeat tick, healthy=%s", healthy)
            # Only ever reports "alive" if every thread still is (passive
            # health reporting, see _all_threads_alive). A supervisor
            # is optional (SUPERVISOR_PORT is None if there is none), and
            # an unhealthy process simply stops sending, rather than
            # actively announcing its own bad health.
            if healthy and self.SUPERVISOR_PORT is not None:
                self._send_interact(self.SUPERVISOR_PORT, "heartbeat")
            self._report_node_info(healthy)
        self.log.debug("heartbeat thread stopped")

    def _on_barrier(self, port_name, payload):
        """
        A marker settles its port in the round it belongs to. A marker of
        another round opens it, if _round_may_open allows it, replacing the
        round that is open; otherwise it is ignored.
        """
        epoch = payload["epoch"]
        halt = payload["halt"]

        if self._round is not None and epoch == self._round.epoch:
            self._round.pending.discard(port_name)
        elif self._round_may_open(epoch, halt, f"the marker of round {epoch} on port {port_name!r}"):
            self._switch_to_round(epoch, halt, arrived_port=port_name)
        else:
            return

        if not self._round.pending:
            self._close_round()

    def _round_may_open(self, epoch, halt, what):
        """
        Whether a round that reaches this node, other than the open one, may
        open, replacing the open round if there is one. Rounds do not overlap
        on a node: a newer round replaces an older one (see
        _abandon_round), unless the older one is a halt and the newer
        one is not, since a halt is never given up for a snapshot. A round
        older than the open one, or one that this node has closed or
        abandoned, is stale. When the answer is no, the reason is logged,
        `what` naming what brought the round.
        """
        if self._round is None:
            if epoch <= self._last_epoch:
                self.log.warning("ignoring %s: that round is over", what)
                return False
        elif epoch < self._round.epoch:
            self.log.warning("ignoring %s: round %s replaced it", what, self._round.epoch)
            return False
        elif self._round.halt and not halt:
            self.log.warning("ignoring %s: the halt of round %s is open", what, self._round.epoch)
            return False
        return True

    def _switch_to_round(self, epoch, halt, arrived_port):
        """Abandons the open round, if any, and opens the round of `epoch`."""
        if self._round is not None:
            self._abandon_round(replaced_by=epoch)
        self._open_round(epoch, halt, arrived_port)

    def _on_close(self, port_name):
        """
        The writer of `port_name` has finished for good, so no marker will
        ever come from it. If a round is open and this port was still
        pending, it stops being so, and the round closes if it was the last
        one; what was already recorded for the port stays in the round's
        channel state. Ports that are closed when a round opens are left
        out of it altogether (see _open_round).
        """
        if port_name in self.CONTROL_PORTS:
            self.log.debug("the writer of control port %r said CLOSE, which changes nothing", port_name)
            return
        self._closed_ports.add(port_name)
        self.log.debug("port %r was closed by its writer", port_name)
        if self._round is not None and port_name in self._round.pending:
            self._round.pending.discard(port_name)
            if not self._round.pending:
                self._close_round()

    def _on_interact(self, payload):
        command = payload["command"]
        if command in ("start_snapshot", "shutdown"):
            args = payload.get("args")
            epoch = args.get("epoch") if isinstance(args, dict) else None
            if epoch is not None and (not isinstance(epoch, int) or isinstance(epoch, bool)):
                self.log.warning("ignoring a trigger: its epoch %r is not an integer", epoch)
                return
            self._on_trigger(halt=command == "shutdown", epoch=epoch)
        else:
            # The command catalog is deliberately open-ended: an
            # unrecognized command is a forward-compatibility concern,
            # not a reason to abort an otherwise-healthy process.
            self.log.warning("ignoring unrecognized INTERACT command: %r", command)

    def _on_trigger(self, halt, epoch=None):
        """
        What an initiator does with a trigger, a shutdown when `halt`: opens
        the round of `epoch`, or of a number of its own when the trigger
        carries none (see _own_round_epoch), replacing the open round when
        the rules of rounds allow it, and closes it at once when no port is
        pending. Ignores the trigger once the node has halted.
        """
        if self._halted.is_set():
            self.log.warning("ignoring a trigger: this node has already halted")
            return

        if epoch is None:
            epoch = self._own_round_epoch(halt)
            if epoch is None:
                return
        elif self._round is not None and epoch == self._round.epoch:
            # In a cycle, the marker of another initiator can get here before
            # the trigger of the same round.
            self.log.warning("ignoring the trigger of round %s: that round is already open", epoch)
            return
        # A numbered trigger was numbered outside the node, the same for every
        # initiator it reaches, so it follows the rule of a marker: ignoring a
        # newer one would leave this initiator alone on an older round while
        # the others open the new one.
        elif not self._round_may_open(epoch, halt, f"the trigger of round {epoch}"):
            return

        self._switch_to_round(epoch, halt, arrived_port=None)
        if not self._round.pending:
            self._close_round()

    def _own_round_epoch(self, halt):
        """
        The epoch of the round that a trigger without an epoch starts, the
        one after the last this node closed, abandoned or has open, or None
        if the trigger is to be ignored. It replaces an open snapshot, so
        that an initiator whose marker was lost, and whose round would
        otherwise stay open for ever, gets out of it at its next trigger;
        the number has to be above the open one for the nodes that have
        that round open to replace it too. It is ignored if a halt is open:
        a halt is never given up, and a second one adds nothing.
        """
        if self._round is None:
            return self._last_epoch + 1
        if self._round.halt:
            self.log.warning("ignoring a trigger: the halt of round %s is open", self._round.epoch)
            return None
        return self._round.epoch + 1

    def _open_round(self, epoch, halt, arrived_port):
        """
        Opens the round of `epoch` at this node: captures the node state and
        the bookkeeping, forwards the marker, and waits for the pending ports
        (see below; never `arrived_port`, the port of the marker that opened
        it, if a marker did).
        """
        capture = _Checkpoint(
            epoch=epoch,
            node_state=self.capture_node_state(),
            capture_pos=self._current_pos,
            closed_ports=frozenset(self._closed_ports),
            out_seq=dict(self._out_seq),
            last_seq=dict(self._last_seq),
            out_backlog=self._snapshot_out_backlog(),
        )
        for out_port in self.OUTPUT_PORTS:
            # The supervisor channel never sees a BARRIER: it doesn't
            # take part in the barrier protocol, only in INTERACT.
            if out_port == self.SUPERVISOR_PORT:
                continue
            self._send_barrier(out_port, epoch, halt=halt)

        # A control port carries no markers, a port fed only from outside the
        # program carries none either (unless its source knows the protocol,
        # in which case _on_barrier accepts it like any other), and a port
        # whose writer has finished sends no more, so the round does not
        # wait for any of the three. The brain thread's own set decides, in
        # the order of the input log: a CLOSE that the reader threads have
        # already logged but that comes after this envelope does not count yet.
        pending = set(self.INPUT_PORTS) - set(self.CONTROL_PORTS) - set(self.EXTERNAL_PORTS)
        pending.discard(arrived_port)
        pending -= self._closed_ports
        capture.channel_state = {port: [] for port in pending}
        self._round = _Round(halt=halt, pending=pending, capture=capture)

    def _abandon_round(self, replaced_by):
        """
        Drops the round in progress because a newer one reached this node:
        what it had captured is discarded and no checkpoint is written for
        its epoch, which this node will not use again. The markers that it
        already sent stay sent; the nodes downstream drop the round the same
        way when the newer marker reaches them.
        """
        self.log.warning(
            "abandoning round %s: round %s reached this node while it was open",
            self._round.epoch,
            replaced_by,
        )
        self._last_epoch = max(self._last_epoch, self._round.epoch)
        self._round = None

    def _close_round(self):
        """Closes the open round and hands what it captured to _on_epoch_closed."""
        closed = self._round
        self._last_epoch = max(self._last_epoch, closed.epoch)
        self._round = None
        self._on_epoch_closed(closed.capture, closed.halt)

    def _on_epoch_closed(self, checkpoint, halt):
        """
        Writes the checkpoint of a closed round and tells the Supervisor; on
        a halt, also sets _halted and writes the halted marker.
        """
        epoch = checkpoint.epoch
        path = self._save_checkpoint(checkpoint)
        if path is None:
            # Over OUT_BACKLOG_MAX_BYTES: _save_checkpoint already warned and
            # wrote nothing. The round still closed as far as the rest of the
            # program is concerned (its markers were sent when it opened);
            # only this node's own persistence of it falls back to whatever
            # its previous checkpoint was, plus a longer replay later.
            if self._checkpoints_skipped_since is None:
                self._checkpoints_skipped_since = epoch
        else:
            self._checkpoints_skipped_since = None
            self.log.info("checkpoint saved for epoch %s at %s", epoch, path)
            if self.SUPERVISOR_PORT is not None:
                self._send_interact(
                    self.SUPERVISOR_PORT, "checkpoint_saved", {"epoch": epoch, "path": path}
                )

        if halt:
            # A halt round closing has no effect of its own: this node keeps
            # running, exactly like after any other round (see run()).
            # _halted keeps a trigger from opening another round (see
            # _on_trigger); the marker of a peer still opens one, which
            # rewrites the halted marker if it is a halt too. Actually
            # stopping is up to whoever sends this process a SIGTERM later.
            self._halted.set()
            self._write_halted_marker(epoch)
            self.log.info(
                "epoch %s closed with halt=True, no trigger will open another round; "
                "waiting for an external stop signal",
                epoch,
            )

    def _checkpoints_dir(self):
        return self._execdir_entry("checkpoints")

    def _halted_marker_path(self):
        return self._execdir_entry("halted")

    def _write_halted_marker(self, epoch):
        """
        Marks this incarnation as having closed a halt round, for an
        external tool to notice with no other knowledge of this node's
        state: its content is the epoch, so that a tool that recorded the
        epoch on disk before it triggered a round can tell this apart from
        a marker left over from an earlier halt this node has since been
        resumed from (never cleared: nothing here ever reads it back).
        Atomic (temp file + rename), same as a checkpoint; unlike one, it
        is not schema-versioned or pruned, since only its latest content
        is ever meaningful.
        """
        os.makedirs(self._execdir(), exist_ok=True)
        path = self._halted_marker_path()
        tmp_path = f"{path}.tmp"
        with open(tmp_path, "w") as f:
            f.write(str(epoch))
        os.replace(tmp_path, path)

    def _save_checkpoint(self, checkpoint):
        """
        Writes `checkpoint`, unless the outbound backlog it would carry is
        over OUT_BACKLOG_MAX_BYTES: then it writes nothing and returns None,
        with a warning, rather than a checkpoint whose own file could grow
        without bound. Whatever checkpoint this node had before stays the
        latest one on disk; its own replay of the input log, next time it
        starts, only grows longer, never wrong. Returns the path written.
        """
        epoch = checkpoint.epoch
        backlog_bytes = sum(
            len(json.dumps(entry))
            for entries in checkpoint.out_backlog.values()
            for entry in entries
        )
        if backlog_bytes > self.OUT_BACKLOG_MAX_BYTES:
            self.log.warning(
                "epoch %s: the outbound backlog is %d bytes, over OUT_BACKLOG_MAX_BYTES "
                "(%d); not writing this checkpoint, the previous one plus a longer "
                "replay will cover it",
                epoch,
                backlog_bytes,
                self.OUT_BACKLOG_MAX_BYTES,
            )
            return None

        checkpoints_dir = self._checkpoints_dir()
        os.makedirs(checkpoints_dir, exist_ok=True)

        final_path = os.path.join(checkpoints_dir, f"{epoch}.json")
        tmp_path = f"{final_path}.tmp"
        with open(tmp_path, "w") as f:
            json.dump(checkpoint.to_dict(self.CHECKPOINT_SCHEMA_VERSION), f)
        os.replace(tmp_path, final_path)

        self._prune_old_checkpoints(checkpoints_dir)

        return final_path

    def _prune_old_checkpoints(self, checkpoints_dir):
        epochs = sorted(_checkpoint_epochs(checkpoints_dir), reverse=True)
        for old_epoch in epochs[self.CHECKPOINT_RETENTION :]:
            os.remove(os.path.join(checkpoints_dir, f"{old_epoch}.json"))

        self._prune_input_log(checkpoints_dir, epochs[: self.CHECKPOINT_RETENTION])

    # -- input log --
    #
    # The log lives in this process's own directory and is written by its own
    # reader threads as envelopes arrive, never by the neighbor that sent them:
    # the process that ever needs to replay it is the one relaunched after a
    # crash, itself, so there is no reason for it to live anywhere else. See
    # _InputLog for the format.

    def _open_input_log(self, capture_pos):
        """
        Opens the input log and recovers what earlier incarnations left in it.
        `capture_pos` is the position that the restored checkpoint reflects
        (0 if there is none). Raises ValueError if the log does not reach it
        (see _InputLog.recover).
        """
        # The log of a node with a checkpoint always reaches its capture_pos:
        # the envelope at that position was logged before the brain thread saw
        # it, recover deletes only a segment with no complete record, and
        # pruning never deletes the last segment. One that does not was lost or
        # cut, and starting from the checkpoint would silently lose what the
        # node processed after it.
        # Pruning deletes only segments that are closed, so the cap has to
        # hold several of them: a segment larger than the cap would never
        # close, and nothing would ever be pruned however many rounds close.
        log = _InputLog(
            self._execdir_entry("log"),
            self.INPUT_LOG_MAX_BYTES,
            min(self.INPUT_LOG_SEGMENT_BYTES, self.INPUT_LOG_MAX_BYTES // 4),
        )
        log.recover(must_reach=capture_pos)
        self._input_log = log

    def _replay_input_log(self, capture_pos):
        """
        Re-executes process_data() on every DATA record of the input log above
        `capture_pos`, in log order, which is the order in which the brain
        thread processed them, and restores the closed ports and the counters
        of sequence numbers to what they were before the crash. Raises
        ValueError on a DATA on a port already closed, or if the log cannot be
        trusted (see _InputLog.replay). Reads from disk only.
        """
        replayed = 0
        self._replaying = True
        try:
            for record in self._input_log.replay(capture_pos):
                if record.envelope.type == TYPE_CLOSE:
                    # It only closes its port; a control port is never closed.
                    if record.port not in self.CONTROL_PORTS:
                        self._closed_ports.add(record.port)
                    continue
                # A BARRIER or an INTERACT acted on a round, which is not node
                # state: a round that closed after the checkpoint is over for
                # the program, and one open at the crash is lost with it (see
                # the Contract's limits).
                if record.envelope.type != TYPE_DATA:
                    continue
                # Nothing is logged after a CLOSE, so this means that the log
                # or the checkpoint is corrupt.
                if record.port in self._closed_ports:
                    raise ValueError(
                        f"{type(self).__name__}: the input log holds a DATA record at position "
                        f"{record.pos} on port {record.port!r}, which had already received CLOSE; "
                        "nothing is logged after a CLOSE, so the log or the checkpoint is corrupt"
                    )
                self._current_pos = record.pos
                # Records reach the log in accepted order (_on_arrivals,
                # _filter_by_seq), so a plain overwrite restores the counters.
                if record.envelope.seq is not None:
                    self._last_seq[record.port] = record.envelope.seq
                    self._accepted_seq[record.port] = record.envelope.seq
                self._run_process_data(record.port, record.envelope.payload)
                replayed += 1
        finally:
            self._replaying = False
        self._apply_replayed_notice()
        if replayed:
            self.log.info(
                "replayed %d records of the input log after position %s", replayed, capture_pos
            )
        if self._closed_ports:
            self.log.info("input ports closed by their writers: %s", sorted(self._closed_ports))

    def _prune_input_log(self, checkpoints_dir, kept_epochs):
        """
        Deletes the segments of the input log that no kept checkpoint needs:
        those whose records all lie at or below the capture_pos of the
        oldest kept checkpoint. Raises RuntimeError, before deleting
        anything, if that checkpoint cannot be read. Without an open log
        there is nothing to prune.
        """
        if self._input_log is None or not kept_epochs:
            return
        # Read from the file, not kept in memory: the node would otherwise
        # have to keep the positions of its kept checkpoints in step with the
        # files that hold them, for a value needed once per round.
        path = os.path.join(checkpoints_dir, f"{min(kept_epochs)}.json")
        try:
            with open(path) as f:
                capture_pos = json.load(f)["capture_pos"]
        except (OSError, ValueError, KeyError) as exc:
            raise RuntimeError(
                f"{type(self).__name__}: cannot read {path} to learn how far the input log "
                f"can be pruned: {exc!r}"
            ) from exc
        with self._arrival_lock:
            self._input_log.prune(capture_pos)

    # -- subclass extension points --

    def process_data(self, port_name, packet):
        """
        Processes one message, `packet`, received on the input port
        `port_name` (or under OBSERVE_PORT, from observe()). `packet` is
        the value that the sender gave to send_data(), already decoded from
        JSON. It is the only place from which the node sends, with
        send_data(). It must be deterministic: given the same node state
        and the same messages, it makes the same new state and sends the
        same messages, since a replay after a crash calls it again for
        every message received since the latest checkpoint. It must not
        depend on the time, on randomness or on reads from outside the
        program, and whatever it does outside its FIFOs (writing a file,
        calling a service) may be done more than once.
        """
        raise NotImplementedError

    def capture_node_state(self):
        """
        Returns the node state: everything that process_data() keeps from
        one message to the next, as a value that JSON can serialize. It is
        called when a snapshot is taken, and what it returns is saved in a
        checkpoint of the node.
        """
        raise NotImplementedError

    def restore_node_state(self, node_state):
        """
        Sets the node state from `node_state`, what capture_node_state()
        returned, when the node starts from a checkpoint. It must rebuild
        the state exactly. It is not called when the node starts with no
        checkpoint, so the constructor sets the initial state. It cannot
        send.
        """
        raise NotImplementedError

    def initialize_runtime(self):
        """
        Opens what the node uses and is not part of its state, such as a
        connection or an open file, before it processes any message. It is
        called at every start of the node, after restore_node_state(). It
        cannot send.
        """
        raise NotImplementedError

    def observe(self):
        """
        Optional. Looks at the outside world (a directory, a queue, the
        batch runs of a launcher node) and brings what it sees into the node
        with inject(). It runs on a thread of its own, every
        OBSERVE_INTERVAL_SECS or when observe_now() is called, only while
        the node is running, never while it replays its input log. What it
        sees is different every time, so it cannot happen in
        process_data(): it enters as an input, which a replay receives
        again. After a crash, observe() may bring in again what it had
        already brought in, so process_data() keeps in the node state what
        it has acted on, and drops a repetition. If observe() raises, the
        node stops sending heartbeats, as a node that crashed does.
        """
