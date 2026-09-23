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
import json
import signal
import sys
import threading

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
    Base class for resident processes. A subclass declares its ports via
    the INPUT_PORTS/OUTPUT_PORTS class attributes (option names, without
    their leading dash(es), e.g. INPUT_PORTS = ["inf"]) and overrides
    process_data/capture_node_state/restore_node_state/initialize_runtime.
    """

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

    HEARTBEAT_INTERVAL_SECONDS = 5

    # The GIL switch interval of the node's process (sys.setswitchinterval),
    # set when run() starts; None keeps Python's own, 5 ms. A reader thread
    # that has taken a block from its fifo needs the GIL back before it can
    # log the block, and while process_data computes it may wait up to this
    # long, with the block only in memory, where the death of the process
    # loses it (see the Contract's limits). A short interval keeps that wait
    # short, at no cost that a measurement tells apart from noise. It applies
    # to the whole process, which the node has to itself.
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
    INPUT_LOG_MAX_BYTES = 100 * 1024 * 1024
    INPUT_LOG_SEGMENT_BYTES = 4 * 1024 * 1024

    # Total size, across every output port, of the DATA that send_data has
    # numbered but the writer thread has not yet finished writing (G5's
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
    # machine.
    OUT_BACKLOG_MAX_BYTES = 8 * 1024 * 1024
    OUT_BACKLOG_FAIL_BYTES = 64 * 1024 * 1024

    # The computational specifications of a process that set the limits
    # above for that process of a program (see _PortWorker._apply_comp_specs).
    _COMP_SPEC_ATTRS = {
        "input_log_max_mb": ("INPUT_LOG_MAX_BYTES", 1024 * 1024),
        "out_backlog_max_mb": ("OUT_BACKLOG_MAX_BYTES", 1024 * 1024),
        "out_backlog_fail_mb": ("OUT_BACKLOG_FAIL_BYTES", 1024 * 1024),
        "gil_switch_interval_ms": ("GIL_SWITCH_INTERVAL_SECS", 0.001),
    }

    def __init__(self, argv=None, opts=None):
        super().__init__(argv, opts)

        self._heartbeat_thread = None
        self._heartbeat_stop = threading.Event()

        # Chandy-Lamport barrier round in progress, if any (None = none).
        self._barrier_epoch = None
        self._barrier_halt = False
        self._barrier_pending = set()
        self._barrier_node_state = None
        self._barrier_channel_buffers = {}
        # The input ports that had received CLOSE when the round in progress
        # captured the node state (see _closed_ports).
        self._barrier_closed_ports = frozenset()
        # Position of the item whose processing captured the node state of the
        # round in progress (see _current_pos).
        self._barrier_capture_pos = 0
        # The sender counters (see _out_seq) as they stood when the round in
        # progress captured the node state.
        self._barrier_out_seq = {}
        # The receiver counters (see _last_seq) as they stood when the round
        # in progress captured the node state.
        self._barrier_last_seq = {}
        # The outbound backlog (see _unwritten) as it stood when the round in
        # progress captured the node state: {tag: [{"seq":, "payload":}, ...]},
        # decoded fresh from each line, so it shares nothing with a payload
        # the module may still hold and go on mutating.
        self._barrier_out_backlog = {}
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
        # takes for the checkpoint (G5), which is why it lags behind
        # _accepted_seq below. Restored from the checkpoint before
        # initialize_runtime(), like _out_seq.
        self._last_seq = {}
        # The reader threads' own view of the same thing, ahead of _last_seq:
        # updated at arrival, under _arrival_lock, before a DATA is logged or
        # queued, so that a duplicate produced by a replay is dropped before
        # either happens (G5). Restored at startup from the checkpoint's
        # last_seq plus whatever the input log holds after capture_pos (see
        # _replay_input_log), since that is what the reader threads had
        # already accepted, whether the brain had processed it or not.
        self._accepted_seq = {}
        # DATA that send_data has numbered and queued but the writer thread
        # has not yet finished writing (G5's outbound backlog): {tag: [(seq,
        # line), ...]}, in the order send_data queued them, so the entry at
        # index 0 is always the next one _on_written can confirm. A single
        # kill -9 destroys the outbound queue itself, so a round's capture
        # copies this (decoded, see _barrier_out_backlog) into the
        # checkpoint, and recovery re-enqueues it with the same numbers
        # before anything else is sent (see _restore_out_backlog). Touched by
        # both the thread inside process_data() (send_data appends) and the
        # writer threads (_on_written pops), hence the lock.
        self._unwritten = {}
        # The size of every line in _unwritten together, kept up to date
        # with it (under the same lock) so that send_data checks
        # OUT_BACKLOG_FAIL_BYTES at no cost.
        self._unwritten_bytes = 0
        self._out_backlog_lock = threading.Lock()
        # The epoch of the first round whose checkpoint was skipped because
        # of the size of the outbound backlog, since the last one written;
        # None while checkpoints are being written. Only the brain thread
        # writes it; a reader thread reads it to explain an input log that
        # reached its cap (see _on_arrivals).
        self._checkpoints_skipped_since = None

        # Every item that a reader thread queues gets a position and a record
        # in the input log before the brain thread can see it. The lock makes
        # taking the position, writing the record and queuing the item a
        # single step, so that the order of the positions, of the log and of
        # the queue is one and the same. It also keeps pruning from running
        # while a record is being appended. The log is opened by run(), or by
        # start_threads() when the node is driven without run().
        self._arrival_lock = threading.Lock()
        self._input_log = None
        # Position of the item that the brain thread is processing, 0 before
        # the first one. Only the brain thread reads or writes it.
        self._current_pos = 0
        # Identity of the thread that is inside process_data() right now, None
        # between calls (see send_data).
        self._handler_thread = None

        # Set once an epoch closes with halt=True: blocks _start_barrier_round
        # from opening any further round (see _on_epoch_closed), which keeps
        # this incarnation's halted marker file (see _write_halted_marker)
        # pointing at its final epoch. Never itself stops a thread.
        self._halted = threading.Event()
        # Set only by the SIGTERM handler run() installs (see
        # _on_stop_signal): the actual "stop now" signal that run() waits
        # on, decided entirely outside this node, typically by an external
        # tool once every node's halted marker exists (see the Contract's
        # Conformance status, "G2 is violated during an ordered shutdown",
        # third candidate).
        self._stop_requested = threading.Event()

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

    def _output_ports(self):
        return {port: port for port in self.OUTPUT_PORTS}

    # -- startup sequence --

    def run(self):
        """
        Full startup sequence: install the SIGTERM handler -> open every
        FIFO -> find the most recent checkpoint if any ->
        restore_node_state()/defaults, and the sender counters with it (see
        _out_seq) -> initialize_runtime() -> open the input log and replay
        what it holds after the checkpoint (all of it if there is no
        checkpoint, since the node state is then the default one) ->
        start_threads() (starts every worker thread) -> wait until told to
        stop (SIGTERM, from outside this process; see _on_stop_signal and
        _stop_requested) -> stop every thread, from this (the calling)
        thread rather than the one that actually delivered the signal. A
        halt closing its epoch is not part of this wait any more (see
        _on_epoch_closed): it behaves like an ordinary snapshot, and this
        node keeps running until told to stop by signal, whether or not it
        ever halted.
        """
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

        checkpoint = self._load_latest_checkpoint()
        capture_pos = 0
        if checkpoint is not None:
            epoch, node_state, capture_pos, closed_ports, out_seq, last_seq, out_backlog = checkpoint
            self.restore_node_state(node_state)
            self._last_epoch = epoch
            self._closed_ports = set(closed_ports)
            self._out_seq = dict(out_seq)
            self._last_seq = dict(last_seq)
            # The reader threads' own counters start at the same point; if the
            # log holds DATA after capture_pos, _replay_input_log advances them
            # past it, to what the reader threads had already accepted before
            # the crash, whether the brain had processed it or not.
            self._accepted_seq = dict(last_seq)
            # What was numbered but not yet written reaches a neighbor before
            # anything process_data() sends again while replaying the log.
            self._restore_out_backlog(out_backlog)
            self.log.info("restored checkpoint for epoch %s", epoch)
        else:
            self.log.info("no checkpoint found, starting with default values")

        self.initialize_runtime()

        self._open_input_log(capture_pos)
        self._replay_input_log(capture_pos)

        self.start_threads()
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
        Returns (epoch, node_state, capture_pos, closed_ports, out_seq,
        last_seq, out_backlog) for the highest-epoch checkpoint in this
        process's checkpoints directory,
        or None if there isn't one yet (a brand new process, or one that has
        never closed an epoch). Raises ValueError if the checkpoint's schema
        version doesn't match this class's, or KeyError if a field this
        class now requires is missing (an older checkpoint, from before that
        field existed): a real incompatibility, not something to silently
        paper over by falling back to an older checkpoint or a default value.
        """
        checkpoints_dir = self._checkpoints_dir()
        if not os.path.isdir(checkpoints_dir):
            return None

        epochs = []
        for name in os.listdir(checkpoints_dir):
            if not name.endswith(".json"):
                continue
            try:
                epochs.append(int(name[: -len(".json")]))
            except ValueError:
                continue

        if not epochs:
            return None

        path = os.path.join(checkpoints_dir, f"{max(epochs)}.json")
        with open(path) as f:
            checkpoint = json.load(f)

        if checkpoint["schema_version"] != self.CHECKPOINT_SCHEMA_VERSION:
            raise ValueError(
                f"{type(self).__name__}: checkpoint {path} has schema version "
                f"{checkpoint['schema_version']!r}, expected "
                f"{self.CHECKPOINT_SCHEMA_VERSION!r}"
            )

        return (
            checkpoint["epoch"],
            checkpoint["node_state"],
            checkpoint["capture_pos"],
            checkpoint["closed_ports"],
            checkpoint["out_seq"],
            checkpoint["last_seq"],
            checkpoint["out_backlog"],
        )

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
        its own, with no need to wait for any of the above.
        """
        self._write_control_ports_file()
        if self._input_log is None:
            self._open_input_log(0)
        self._closed_at_start_ports = frozenset(self._closed_ports)
        super().start_threads()
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, name="heartbeat")
        self._heartbeat_thread.start()

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

    def stop_threads(self, timeout=None, close=True):
        """
        Signals the heartbeat thread to stop, then defers to
        _PortWorker.stop_threads() for the reader/writer/brain threads,
        then joins the heartbeat thread too.
        """
        self._heartbeat_stop.set()
        super().stop_threads(timeout, close)
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout)
        if self._input_log is not None:
            self._input_log.close()

    def _closed_at_start(self, tag):
        return tag in self._closed_at_start_ports

    def _drops_after_close(self, tag):
        # The writer of a control port may come back after saying CLOSE, and
        # what it sends then must be heard.
        return tag not in self.CONTROL_PORTS

    def _on_arrival(self, tag, envelope, line):
        self._on_arrivals(tag, [(envelope, line)])

    def _on_arrivals(self, tag, items):
        """
        Records in the input log, and then queues for the brain thread, the
        items of one block that a reader thread has taken from its fifo, all
        of them in one write (see _InputLog.append_many): until then they
        exist only in this process, and are lost if it dies. The lock keeps
        the positions in the log in the order in which the brain thread gets
        the items, across the reader threads of every port.
        """
        with self._arrival_lock:
            if self._input_log is None:
                raise RuntimeError(
                    f"{type(self).__name__}: an item arrived before the input log was opened"
                )
            # G5: a DATA that carries a number not above the last one this
            # channel's reader has already accepted is a duplicate, produced
            # by a replay on the sender's side, and is dropped here, before it
            # is ever logged or queued, so that it is never processed twice.
            # One that skips over a number is a message this channel will
            # never see: a real loss, not a duplicate, so it is never silent
            # (G8). The items before it are logged and queued, as they would
            # be one by one, and then it raises, before it is itself logged
            # or queued. A DATA with no number (from a source, or a plain
            # _PortWorker) is not part of the numbering and is always
            # accepted; only DATA is sequenced (BARRIER/INTERACT carry no seq
            # of their own; CLOSE carries the sender's last one instead,
            # checked below, once CLOSE itself is durably recorded, since
            # nothing sends it twice).
            accepted_items = []
            close_checks = []
            gap = None
            for envelope, line in items:
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
                        break
                    self._accepted_seq[tag] = envelope.seq
                if envelope.type == TYPE_CLOSE:
                    close_checks.append((envelope, self._accepted_seq.get(tag, 0)))
                accepted_items.append((envelope, line))

            # The records are in the file, in one write, before the brain
            # thread can see the items. If this raises, the exception ends
            # the reader thread, which is how the heartbeat notices: after a
            # failed write none of these items is queued, and at the size cap
            # only the ones logged before it are.
            try:
                positions = self._input_log.append_many([(tag, line) for _, line in accepted_items])
            except LogCapReached as exc:
                for pos, (envelope, _) in zip(exc.positions, accepted_items):
                    self._inbound_queue.put((pos, tag, envelope.type, envelope.payload, envelope.seq))
                skipped_since = self._checkpoints_skipped_since
                if skipped_since is None:
                    raise
                # Rounds do close here, but none has written a checkpoint
                # for a while, so nothing has been pruned: the real cause is
                # a reader of this node that is not keeping up.
                raise LogCapReached(
                    f"{exc}; here the cause is not the rounds: no checkpoint has been "
                    f"written since epoch {skipped_since}, because the outbound backlog "
                    f"is over OUT_BACKLOG_MAX_BYTES ({self.OUT_BACKLOG_MAX_BYTES}): a "
                    "reader of this node is not keeping up with it",
                    exc.positions,
                ) from None
            for pos, (envelope, _) in zip(positions, accepted_items):
                self._inbound_queue.put((pos, tag, envelope.type, envelope.payload, envelope.seq))

            # G5/G8: a CLOSE that carries the sender's last number is checked
            # only now, after it is itself durably logged and queued, unlike
            # a DATA gap: nothing ever sends CLOSE a second time, so losing
            # it here to an early raise would leave this port's writer
            # looking unfinished forever, rather than reporting one lost
            # message and moving on.
            for envelope, accepted in close_checks:
                claimed = envelope.payload.get("last_seq")
                if claimed is not None and claimed > accepted:
                    missing = f"{accepted + 1}" if claimed == accepted + 1 else f"{accepted + 1} to {claimed}"
                    raise ValueError(
                        f"{type(self).__name__}: {tag!r} closed for good after sending up "
                        f"to {claimed}, but only {accepted} was ever accepted here, "
                        f"missing {missing}"
                    )

            if gap is not None:
                raise gap

    def _brain_loop(self):
        while True:
            item = self._inbound_queue.get()
            if item is _STOP:
                break
            pos, port_name, envelope_type, payload, seq = item
            self._current_pos = pos
            if envelope_type == TYPE_DATA:
                if seq is not None:
                    self._last_seq[port_name] = seq
                if port_name in self._barrier_pending:
                    # A barrier round is open and this port's marker for
                    # it hasn't arrived yet: this DATA was sent before
                    # its sender's own snapshot and arrives after this
                    # node's, so it is in transit at the cut and part of
                    # the round's channel state. Only a copy is recorded
                    # here (taken now, so that process_data() cannot
                    # alter it through the packet it is handed): the
                    # message itself is still processed right below,
                    # like any other and in arrival order.
                    self._barrier_channel_buffers[port_name].append(
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

    def send_data(self, tag, payload):
        """
        Sends a DATA message on the output port `tag`, numbered with this
        channel's next sequence number (see _out_seq and G5 in the
        Contract). A node acts only in reaction to what it receives, so
        this is allowed only inside process_data(), on the thread that is
        running it: the brain thread, or the thread that called run() while
        it replays the input log. From anywhere else it raises, and nothing
        is sent or numbered. That keeps the messages a node sends, and the
        state it captures, in the order in which it processed what it
        received, which is what a replay reproduces: restored from the same
        checkpoint, it renumbers what it sends again exactly the same way.
        It also raises, again with nothing sent or numbered, if the message
        would take the outbound backlog over OUT_BACKLOG_FAIL_BYTES.
        """
        if self._handler_thread != threading.get_ident():
            raise RuntimeError(
                f"{type(self).__name__}: send_data() called outside process_data(), "
                "or from a thread other than the one running it: a node sends only "
                "in reaction to a message that it receives"
            )
        seq = self._out_seq.get(tag, 0) + 1
        line = encode_data(payload, seq=seq)
        with self._out_backlog_lock:
            if self._unwritten_bytes + len(line) > self.OUT_BACKLOG_FAIL_BYTES:
                port_bytes = sum(len(entry) for _, entry in self._unwritten.get(tag, []))
                raise RuntimeError(
                    f"{type(self).__name__}: the outbound backlog would go over "
                    f"OUT_BACKLOG_FAIL_BYTES ({self.OUT_BACKLOG_FAIL_BYTES} bytes) with this "
                    f"message on {tag!r}, which holds {port_bytes} bytes not yet written: "
                    "a reader of this node is not reading (it was stopped, is down or "
                    "stuck, or is slower than this node)"
                )
            self._unwritten.setdefault(tag, []).append((seq, line))
            self._unwritten_bytes += len(line)
        self._out_seq[tag] = seq
        self._outbound_queues[tag].put(line)

    def _on_written(self, tag, item):
        """
        The writer thread has finished writing `item`. If it is the numbered
        DATA line send_data is still waiting to see written (always the
        oldest one queued for `tag`, since a queue is FIFO and _unwritten is
        only ever appended to in that same order), it leaves the backlog: a
        crash from here on no longer loses it, since it already reached the
        fifo (see the Contract's limits on that). A BARRIER, an INTERACT or a
        CLOSE line never matches, and changes nothing here.
        """
        with self._out_backlog_lock:
            backlog = self._unwritten.get(tag)
            if backlog and backlog[0][1] == item:
                backlog.pop(0)
                self._unwritten_bytes -= len(item)

    def _close_payload(self, tag):
        """
        `_out_seq[tag]`, 0 if this port never sent anything: by the time a
        writer thread is about to send CLOSE, the brain thread has already
        stopped (a finished writer means run() is on its way out), so
        nothing can bump this again and reading it here needs no lock (G5).
        """
        return self._out_seq.get(tag, 0)

    def _restore_out_backlog(self, out_backlog):
        """
        Re-enqueues, with their original numbers, the DATA that a round's
        capture found still unwritten (see _barrier_out_backlog): what
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
                    self._unwritten.setdefault(tag, []).append((seq, line))
                    self._unwritten_bytes += len(line)
                self._outbound_queues[tag].put(line)

    def _snapshot_out_backlog(self):
        """
        A round's own copy of _unwritten, taken at the capture (see
        _open_barrier_round): {tag: [{"seq":, "payload":}, ...]}, decoded
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
        while not self._heartbeat_stop.wait(self.HEARTBEAT_INTERVAL_SECONDS):
            healthy = self._all_threads_alive()
            self.log.debug("heartbeat tick, healthy=%s", healthy)
            # Only ever reports "alive" if every thread still is (passive
            # health reporting, see _all_threads_alive) -- a supervisor
            # is optional (SUPERVISOR_PORT is None if there is none), and
            # an unhealthy process simply stops sending, rather than
            # actively announcing its own bad health.
            if healthy and self.SUPERVISOR_PORT is not None:
                self._send_interact(self.SUPERVISOR_PORT, "heartbeat")
        self.log.debug("heartbeat thread stopped")

    def _on_barrier(self, port_name, payload):
        """
        A marker settles its port in the round it belongs to. A marker of
        another round opens it, if _round_may_open allows it, replacing the
        round that is open; otherwise it is ignored.
        """
        epoch = payload["epoch"]
        halt = payload["halt"]

        if epoch == self._barrier_epoch:
            self._barrier_pending.discard(port_name)
        elif self._round_may_open(epoch, halt, f"the marker of round {epoch} on port {port_name!r}"):
            self._enter_barrier_round(epoch, halt, arrived_port=port_name)
        else:
            return

        if not self._barrier_pending:
            self._close_barrier_round()

    def _round_may_open(self, epoch, halt, what):
        """
        Whether a round that reaches this node, other than the open one, may
        open, replacing the open round if there is one. Rounds do not overlap
        on a node: a newer round replaces an older one (see
        _abandon_barrier_round), unless the older one is a halt and the newer
        one is not, since a halt is never given up for a snapshot. A round
        older than the open one, or one that this node has closed or
        abandoned, is stale. When the answer is no, the reason is logged,
        `what` naming what brought the round.
        """
        if self._barrier_epoch is None:
            if epoch <= self._last_epoch:
                self.log.warning("ignoring %s: that round is over", what)
                return False
        elif epoch < self._barrier_epoch:
            self.log.warning("ignoring %s: round %s replaced it", what, self._barrier_epoch)
            return False
        elif self._barrier_halt and not halt:
            self.log.warning("ignoring %s: the halt of round %s is open", what, self._barrier_epoch)
            return False
        return True

    def _enter_barrier_round(self, epoch, halt, arrived_port):
        if self._barrier_epoch is not None:
            self._abandon_barrier_round(replaced_by=epoch)
        self._open_barrier_round(epoch, halt, arrived_port)

    def _on_close(self, port_name):
        """
        The writer of `port_name` has finished for good, so no marker will
        ever come from it. If a round is open and this port was still
        pending, it stops being so, and the round closes if it was the last
        one; what was already recorded for the port stays in the round's
        channel state. Ports that are closed when a round opens are left
        out of it altogether (see _open_barrier_round).
        """
        if port_name in self.CONTROL_PORTS:
            self.log.debug("the writer of control port %r said CLOSE, which changes nothing", port_name)
            return
        self._closed_ports.add(port_name)
        self.log.debug("port %r was closed by its writer", port_name)
        if port_name in self._barrier_pending:
            self._barrier_pending.discard(port_name)
            if not self._barrier_pending:
                self._close_barrier_round()

    def _on_interact(self, payload):
        command = payload["command"]
        if command in ("start_snapshot", "shutdown"):
            args = payload.get("args")
            epoch = args.get("epoch") if isinstance(args, dict) else None
            if epoch is not None and (not isinstance(epoch, int) or isinstance(epoch, bool)):
                self.log.warning("ignoring a trigger: its epoch %r is not an integer", epoch)
                return
            self._start_barrier_round(halt=command == "shutdown", epoch=epoch)
        else:
            # The command catalog is deliberately open-ended: an
            # unrecognized command is a forward-compatibility concern,
            # not a reason to abort an otherwise-healthy process.
            self.log.warning("ignoring unrecognized INTERACT command: %r", command)

    def _start_barrier_round(self, halt, epoch=None):
        """
        Opens a barrier round as its initiator (triggered by INTERACT,
        not by a peer's own BARRIER arriving on some input port): no
        input port has closed yet at this point, unlike the peer-
        triggered case in _on_barrier, so every declared input port
        (including this node's own, if a cycle loops back to it) starts
        out pending, and the initiator only closes its part once the
        marker it just sent comes back around, the same as any other
        node would. A node that has halted starts no more rounds.

        A trigger that carries its epoch was numbered outside the node,
        the same for every initiator it reaches, and follows the rule of
        a marker (see _round_may_open): ignoring a newer one would leave
        this initiator alone on an older round while the others open the
        new one. It is ignored if its round is already open, which in a
        cycle happens when the marker of another initiator gets here
        first. A trigger without an epoch is numbered by the node itself
        (see _own_round_epoch).
        """
        if self._halted.is_set():
            self.log.warning("ignoring a trigger: this node has already halted")
            return

        if epoch is None:
            epoch = self._own_round_epoch(halt)
            if epoch is None:
                return
        elif epoch == self._barrier_epoch:
            self.log.warning("ignoring the trigger of round %s: that round is already open", epoch)
            return
        elif not self._round_may_open(epoch, halt, f"the trigger of round {epoch}"):
            return

        self._enter_barrier_round(epoch, halt, arrived_port=None)
        if not self._barrier_pending:
            self._close_barrier_round()

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
        if self._barrier_epoch is None:
            return self._last_epoch + 1
        if self._barrier_halt:
            self.log.warning("ignoring a trigger: the halt of round %s is open", self._barrier_epoch)
            return None
        return self._barrier_epoch + 1

    def _open_barrier_round(self, epoch, halt, arrived_port):
        self._barrier_epoch = epoch
        self._barrier_halt = halt
        self._barrier_node_state = self.capture_node_state()
        self._barrier_capture_pos = self._current_pos
        self._barrier_closed_ports = frozenset(self._closed_ports)
        self._barrier_out_seq = dict(self._out_seq)
        self._barrier_last_seq = dict(self._last_seq)
        self._barrier_out_backlog = self._snapshot_out_backlog()
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
        # already logged but that comes after this item does not count yet.
        pending = set(self.INPUT_PORTS) - set(self.CONTROL_PORTS) - set(self.EXTERNAL_PORTS)
        pending.discard(arrived_port)
        pending -= self._closed_ports
        self._barrier_pending = pending
        self._barrier_channel_buffers = {port: [] for port in pending}

    def _abandon_barrier_round(self, replaced_by):
        """
        Drops the round in progress because a newer one reached this node:
        what it had captured is discarded and no checkpoint is written for
        its epoch, which this node will not use again. The markers that it
        already sent stay sent; the nodes downstream drop the round the same
        way when the newer marker reaches them.
        """
        self.log.warning(
            "abandoning round %s: round %s reached this node while it was open",
            self._barrier_epoch,
            replaced_by,
        )
        self._last_epoch = max(self._last_epoch, self._barrier_epoch)
        self._reset_barrier_round()

    def _reset_barrier_round(self):
        self._barrier_epoch = None
        self._barrier_halt = False
        self._barrier_node_state = None
        self._barrier_pending = set()
        self._barrier_channel_buffers = {}
        self._barrier_capture_pos = 0
        self._barrier_closed_ports = frozenset()
        self._barrier_out_seq = {}
        self._barrier_last_seq = {}
        self._barrier_out_backlog = {}

    def _close_barrier_round(self):
        epoch = self._barrier_epoch
        halt = self._barrier_halt
        node_state = self._barrier_node_state
        channel_buffers = self._barrier_channel_buffers
        capture_pos = self._barrier_capture_pos
        closed_ports = self._barrier_closed_ports
        out_seq = self._barrier_out_seq
        last_seq = self._barrier_last_seq
        out_backlog = self._barrier_out_backlog

        self._last_epoch = max(self._last_epoch, epoch)
        self._reset_barrier_round()

        self._on_epoch_closed(
            epoch,
            halt,
            node_state,
            channel_buffers,
            capture_pos,
            closed_ports,
            out_seq,
            last_seq,
            out_backlog,
        )

    def _on_epoch_closed(
        self,
        epoch,
        halt,
        node_state,
        channel_buffers,
        capture_pos,
        closed_ports,
        out_seq,
        last_seq,
        out_backlog,
    ):
        path = self._save_checkpoint(
            epoch,
            node_state,
            channel_buffers,
            capture_pos,
            closed_ports,
            out_seq,
            last_seq,
            out_backlog,
        )
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
            # A halt round closing has no effect of its own any more: this
            # node keeps running, exactly like after any other round (see
            # run()). _halted only blocks _start_barrier_round from opening
            # a further one, which is what keeps the marker this writes
            # pointing at this incarnation's final epoch; actually stopping
            # is entirely up to whoever sends this process a SIGTERM later.
            self._halted.set()
            self._write_halted_marker(epoch)
            self.log.info(
                "epoch %s closed with halt=True, no more rounds will open; "
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

    def _save_checkpoint(
        self,
        epoch,
        node_state,
        channel_buffers,
        capture_pos,
        closed_ports,
        out_seq,
        last_seq,
        out_backlog,
    ):
        """
        Writes the checkpoint, unless the outbound backlog it would carry is
        over OUT_BACKLOG_MAX_BYTES: then it writes nothing and returns None,
        with a warning, rather than a checkpoint whose own file could grow
        without bound. Whatever checkpoint this node had before stays the
        latest one on disk; its own replay of the input log, next time it
        starts, only grows longer, never wrong.
        """
        backlog_bytes = sum(
            len(json.dumps(entry)) for entries in out_backlog.values() for entry in entries
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

        checkpoint = {
            "schema_version": self.CHECKPOINT_SCHEMA_VERSION,
            "epoch": epoch,
            "capture_pos": capture_pos,
            "closed_ports": sorted(closed_ports),
            "out_seq": dict(out_seq),
            "last_seq": dict(last_seq),
            "out_backlog": out_backlog,
            "node_state": node_state,
            "channel_state": channel_buffers,
        }

        final_path = os.path.join(checkpoints_dir, f"{epoch}.json")
        tmp_path = f"{final_path}.tmp"
        with open(tmp_path, "w") as f:
            json.dump(checkpoint, f)
        os.replace(tmp_path, final_path)

        self._prune_old_checkpoints(checkpoints_dir)

        return final_path

    def _prune_old_checkpoints(self, checkpoints_dir):
        epochs = []
        for name in os.listdir(checkpoints_dir):
            if not name.endswith(".json"):
                continue
            try:
                epochs.append(int(name[: -len(".json")]))
            except ValueError:
                continue

        epochs.sort(reverse=True)
        for old_epoch in epochs[self.CHECKPOINT_RETENTION :]:
            os.remove(os.path.join(checkpoints_dir, f"{old_epoch}.json"))

        self._prune_input_log(checkpoints_dir, epochs[: self.CHECKPOINT_RETENTION])

    # -- input log --
    #
    # The log lives in this process's own directory and is written by its own
    # reader threads as items arrive, never by the neighbor that sent them:
    # the process that ever needs to replay it is the one relaunched after a
    # crash, itself, so there is no reason for it to live anywhere else. See
    # _InputLog for the format.

    def _open_input_log(self, capture_pos):
        """
        Opens the input log and recovers what earlier incarnations left in it.
        `capture_pos` is the position that the restored checkpoint reflects
        (0 if there is none), so that numbering goes on after it.
        """
        log = _InputLog(
            self._execdir_entry("log"),
            self.INPUT_LOG_MAX_BYTES,
            self.INPUT_LOG_SEGMENT_BYTES,
        )
        log.recover(capture_pos)
        self._input_log = log

    def _replay_input_log(self, capture_pos):
        """
        Re-executes process_data() on every DATA record of the input log with
        a position above `capture_pos`, in log order: what the node had
        received and processed, or had received and was still to process,
        since the node state its checkpoint holds. That order is the one in which
        the brain thread processed them before, so a node that is sensitive
        to how messages from different ports interleave ends where it was.
        A CLOSE record only adds its port to the closed ports, which the
        checkpoint restored as they were when it captured the node state
        (a control port is never added, since it is never closed).
        Nothing is logged after a CLOSE, so a DATA record on a port that is
        already closed means that the log or the checkpoint is corrupt, and
        it is an error. The other kinds of item are not replayed. A numbered
        DATA record also advances _last_seq and _accepted_seq (G5) for its
        port, to what they already were before the crash: records only ever
        reach the log in accepted order (see _on_arrival), so this is a
        plain overwrite, the same as _current_pos, never a max(). This reads
        from disk and never writes to the log.
        """
        replayed = 0
        for record in self._input_log.replay(capture_pos):
            if record.envelope.type == TYPE_CLOSE:
                if record.port not in self.CONTROL_PORTS:
                    self._closed_ports.add(record.port)
                continue
            if record.envelope.type != TYPE_DATA:
                continue
            if record.port in self._closed_ports:
                raise ValueError(
                    f"{type(self).__name__}: the input log holds a DATA record at position "
                    f"{record.pos} on port {record.port!r}, which had already received CLOSE; "
                    "nothing is logged after a CLOSE, so the log or the checkpoint is corrupt"
                )
            self._current_pos = record.pos
            if record.envelope.seq is not None:
                self._last_seq[record.port] = record.envelope.seq
                self._accepted_seq[record.port] = record.envelope.seq
            self._run_process_data(record.port, record.envelope.payload)
            replayed += 1
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
        oldest kept checkpoint. That value is read from the checkpoint's file
        on every call, which costs about a quarter of what writing it did. A
        checkpoint that cannot be read aborts the prune with an error.
        Without an open log there is nothing to prune.
        """
        if self._input_log is None or not kept_epochs:
            return
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
        raise NotImplementedError

    def capture_node_state(self):
        raise NotImplementedError

    def restore_node_state(self, node_state):
        raise NotImplementedError

    def initialize_runtime(self):
        raise NotImplementedError
