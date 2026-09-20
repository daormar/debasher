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
import threading

from debasher_runtime_envelope import TYPE_BARRIER, TYPE_CLOSE, TYPE_DATA, TYPE_INTERACT
from debasher_runtime_transport import _PortWorker, _STOP
from debasher_runtime_inputlog import _InputLog


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

    # Name of the OUTPUT_PORTS entry wired to the supervisor's heartbeat
    # channel, if any. A supervisor is optional (0 or 1 per resident
    # program): leave this None to run without one, in which case
    # checkpoints are still written, just never announced anywhere.
    SUPERVISOR_PORT = None

    HEARTBEAT_INTERVAL_SECONDS = 5
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
        self._barrier_processed_upto = 0
        # Highest epoch this node has ever closed; -1 means none yet, so
        # the first round it self-initiates is epoch 0. A restored
        # checkpoint's epoch must seed this on startup (not yet built,
        # see the checkpoint-persistence/startup-sequence slices), or a
        # relaunched node would start renumbering from 0 again.
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

        # Set once an epoch closes with halt=True; watched (not acted on
        # here -- see _on_epoch_closed) by whatever orchestrates shutdown.
        self._halted = threading.Event()

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

    def _output_ports(self):
        return {port: port for port in self.OUTPUT_PORTS}

    # -- startup sequence --

    def run(self):
        """
        Full startup sequence: find the most recent checkpoint if any
        -> restore_node_state()/defaults -> initialize_runtime() -> open the
        input log and replay what it holds after the checkpoint (all of
        it if there is no checkpoint, since the node state is then the
        default one) -> start_threads() (opens every FIFO, starts every
        worker thread) -> wait until told to stop (an epoch closing with
        halt=True) -> stop every thread, from this (the calling) thread
        rather than the brain thread that actually set the stop signal.
        """
        checkpoint = self._load_latest_checkpoint()
        processed_upto = 0
        if checkpoint is not None:
            epoch, node_state, processed_upto, closed_ports = checkpoint
            self.restore_node_state(node_state)
            self._last_epoch = epoch
            self._closed_ports = set(closed_ports)
            self.log.info("restored checkpoint for epoch %s", epoch)
        else:
            self.log.info("no checkpoint found, starting with default values")

        self.initialize_runtime()

        self._open_input_log(processed_upto)
        self._replay_input_log(processed_upto)

        self.start_threads()
        self._halted.wait()
        # A halt is an orderly stop that the whole program is resumed from
        # later, not the end of this node. CLOSE is what a writer says when
        # it has finished for good, and a peer that read one at a halt would
        # take this node for a finished one when it comes back.
        self.stop_threads(close=False)

    def _load_latest_checkpoint(self):
        """
        Returns (epoch, node_state, processed_upto, closed_ports) for the highest-epoch
        checkpoint in this process's checkpoints directory, or None if there isn't one yet
        (a brand new process, or one that has never closed an epoch).
        Raises ValueError if the checkpoint's schema version doesn't
        match this class's -- a real incompatibility, not something to
        silently paper over by falling back to an older checkpoint.
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
            checkpoint["processed_upto"],
            checkpoint["closed_ports"],
        )

    # -- thread topology --

    def start_threads(self):
        """
        Starts everything _PortWorker.start_threads() already does
        (reader/writer/brain threads), plus this class's own heartbeat
        thread. The input log has to be open before any reader thread
        runs: run() opens it after recovering a checkpoint, and a node
        that is driven without run() gets it opened here, empty of any
        checkpoint.
        """
        if self._input_log is None:
            self._open_input_log(0)
        self._closed_at_start_ports = frozenset(self._closed_ports)
        super().start_threads()
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, name="heartbeat")
        self._heartbeat_thread.start()

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
        with self._arrival_lock:
            if self._input_log is None:
                raise RuntimeError(
                    f"{type(self).__name__}: an item arrived before the input log was opened"
                )
            # The record is in the file, in one write, before the brain thread
            # can see the item. If this raises (the size cap, or a failed
            # write), the exception ends the reader thread, which is how the
            # heartbeat notices: the item that was being read is not queued.
            pos = self._input_log.append(tag, line)
            self._inbound_queue.put((pos, tag, envelope.type, envelope.payload))

    def _brain_loop(self):
        while True:
            item = self._inbound_queue.get()
            if item is _STOP:
                break
            pos, port_name, envelope_type, payload = item
            self._current_pos = pos
            if envelope_type == TYPE_DATA:
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
                self.process_data(port_name, payload)
            elif envelope_type == TYPE_BARRIER:
                self._on_barrier(port_name, payload)
            elif envelope_type == TYPE_INTERACT:
                self._on_interact(payload)
            elif envelope_type == TYPE_CLOSE:
                self._on_close(port_name)
        self.log.debug("brain thread stopped")

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
        epoch = payload["epoch"]
        halt = payload["halt"]

        if self._barrier_epoch is None:
            self._open_barrier_round(epoch, halt, arrived_port=port_name)
        else:
            if epoch != self._barrier_epoch:
                raise ValueError(
                    f"{type(self).__name__}: got a BARRIER for epoch {epoch!r} on port "
                    f"{port_name!r} while epoch {self._barrier_epoch!r} is still open"
                )
            self._barrier_pending.discard(port_name)

        if not self._barrier_pending:
            self._close_barrier_round()

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
        if command == "start_snapshot":
            self._start_barrier_round(halt=False)
        elif command == "shutdown":
            self._start_barrier_round(halt=True)
        else:
            # The command catalog is deliberately open-ended: an
            # unrecognized command is a forward-compatibility concern,
            # not a reason to abort an otherwise-healthy process.
            self.log.warning("ignoring unrecognized INTERACT command: %r", command)

    def _start_barrier_round(self, halt):
        """
        Opens a barrier round as its initiator (triggered by INTERACT,
        not by a peer's own BARRIER arriving on some input port): no
        input port has closed yet at this point, unlike the peer-
        triggered case in _on_barrier, so every declared input port
        (including this node's own, if a cycle loops back to it) starts
        out pending -- the initiator only closes its part once the
        marker it just sent comes back around, the same as any other
        node would.
        """
        if self._barrier_epoch is not None:
            raise ValueError(
                f"{type(self).__name__}: asked to start a new barrier round while "
                f"epoch {self._barrier_epoch!r} is still open"
            )

        epoch = self._last_epoch + 1
        self._open_barrier_round(epoch, halt, arrived_port=None)
        if not self._barrier_pending:
            self._close_barrier_round()

    def _open_barrier_round(self, epoch, halt, arrived_port):
        self._barrier_epoch = epoch
        self._barrier_halt = halt
        self._barrier_node_state = self.capture_node_state()
        self._barrier_processed_upto = self._current_pos
        self._barrier_closed_ports = frozenset(self._closed_ports)
        for out_port in self.OUTPUT_PORTS:
            # The supervisor channel never sees a BARRIER: it doesn't
            # take part in the barrier protocol, only in INTERACT.
            if out_port == self.SUPERVISOR_PORT:
                continue
            self._send_barrier(out_port, epoch, halt=halt)

        # A control port carries no markers, and a port whose writer has
        # finished sends no more, so the round does not wait for either. The brain thread's own set decides, in the order of
        # the input log: a CLOSE that the reader threads have already logged
        # but that comes after this item does not count yet.
        pending = set(self.INPUT_PORTS) - set(self.CONTROL_PORTS)
        pending.discard(arrived_port)
        pending -= self._closed_ports
        self._barrier_pending = pending
        self._barrier_channel_buffers = {port: [] for port in pending}

    def _close_barrier_round(self):
        epoch = self._barrier_epoch
        halt = self._barrier_halt
        node_state = self._barrier_node_state
        channel_buffers = self._barrier_channel_buffers
        processed_upto = self._barrier_processed_upto
        closed_ports = self._barrier_closed_ports

        self._last_epoch = max(self._last_epoch, epoch)
        self._barrier_epoch = None
        self._barrier_halt = False
        self._barrier_node_state = None
        self._barrier_pending = set()
        self._barrier_channel_buffers = {}
        self._barrier_processed_upto = 0
        self._barrier_closed_ports = frozenset()

        self._on_epoch_closed(epoch, halt, node_state, channel_buffers, processed_upto, closed_ports)

    def _on_epoch_closed(self, epoch, halt, node_state, channel_buffers, processed_upto, closed_ports):
        path = self._save_checkpoint(epoch, node_state, channel_buffers, processed_upto, closed_ports)
        self.log.info("checkpoint saved for epoch %s at %s", epoch, path)

        if self.SUPERVISOR_PORT is not None:
            self._send_interact(
                self.SUPERVISOR_PORT, "checkpoint_saved", {"epoch": epoch, "path": path}
            )

        if halt:
            # Runs on the brain thread itself, so it can't call
            # stop_threads() directly here (that joins the brain thread,
            # which would deadlock joining itself) -- just signal, and
            # leave actually stopping every thread to whatever orchestrates
            # shutdown from outside the brain thread (the startup-sequence
            # slice's run(), most likely).
            self.log.info("epoch %s closed with halt=True, signalling for shutdown", epoch)
            self._halted.set()

    def _checkpoints_dir(self):
        return os.path.join(self._execdir(), "checkpoints")

    def _save_checkpoint(self, epoch, node_state, channel_buffers, processed_upto, closed_ports):
        checkpoints_dir = self._checkpoints_dir()
        os.makedirs(checkpoints_dir, exist_ok=True)

        checkpoint = {
            "schema_version": self.CHECKPOINT_SCHEMA_VERSION,
            "epoch": epoch,
            "processed_upto": processed_upto,
            "closed_ports": sorted(closed_ports),
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

    def _open_input_log(self, processed_upto):
        """
        Opens the input log and recovers what earlier incarnations left in it.
        `processed_upto` is the position that the restored checkpoint reflects
        (0 if there is none), so that numbering goes on after it.
        """
        log = _InputLog(
            os.path.join(self._execdir(), "log"),
            self.INPUT_LOG_MAX_BYTES,
            self.INPUT_LOG_SEGMENT_BYTES,
        )
        log.recover(processed_upto)
        self._input_log = log

    def _replay_input_log(self, processed_upto):
        """
        Re-executes process_data() on every DATA record of the input log with
        a position above `processed_upto`, in log order: what the node had
        received and processed, or had received and was still to process,
        since the node state its checkpoint holds. That order is the one in which
        the brain thread processed them before, so a node that is sensitive
        to how messages from different ports interleave ends where it was.
        A CLOSE record only adds its port to the closed ports, which the
        checkpoint restored as they were when it captured the node state
        (a control port is never added, since it is never closed).
        Nothing is logged after a CLOSE, so a DATA record on a port that is
        already closed means that the log or the checkpoint is corrupt, and
        it is an error. The other kinds of item are not replayed. This reads
        from disk and never writes to the log.
        """
        replayed = 0
        for record in self._input_log.replay(processed_upto):
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
            self.process_data(record.port, record.envelope.payload)
            replayed += 1
        if replayed:
            self.log.info(
                "replayed %d records of the input log after position %s", replayed, processed_upto
            )
        if self._closed_ports:
            self.log.info("input ports closed by their writers: %s", sorted(self._closed_ports))

    def _prune_input_log(self, checkpoints_dir, kept_epochs):
        """
        Deletes the segments of the input log that no kept checkpoint needs:
        those whose records all lie at or below the processed_upto of the
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
                processed_upto = json.load(f)["processed_upto"]
        except (OSError, ValueError, KeyError) as exc:
            raise RuntimeError(
                f"{type(self).__name__}: cannot read {path} to learn how far the input log "
                f"can be pruned: {exc!r}"
            ) from exc
        with self._arrival_lock:
            self._input_log.prune(processed_upto)

    # -- subclass extension points --

    def process_data(self, port_name, packet):
        raise NotImplementedError

    def capture_node_state(self):
        raise NotImplementedError

    def restore_node_state(self, node_state):
        raise NotImplementedError

    def initialize_runtime(self):
        raise NotImplementedError
