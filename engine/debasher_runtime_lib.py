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
import io
import sys
import re
import os
import json
import logging
import queue
import threading
from collections import namedtuple

# Constants
DEBASHER_SHUTDOWN_TOKEN = "__SHUTDOWN_TOKEN__"

#####################
# CONTROL ENVELOPE  #
#####################
#
# JSON Lines wire format for communication between resident processes
# (FBPProcess/Supervisor). Three sibling envelope types, always encoded
# as their own single-line JSON object -- a BARRIER or INTERACT message
# is never nested inside DATA's payload, so a reader can dispatch on
# "type" alone, without ever interpreting "payload".

TYPE_DATA = "DATA"
TYPE_BARRIER = "BARRIER"
TYPE_INTERACT = "INTERACT"

_VALID_TYPES = (TYPE_DATA, TYPE_BARRIER, TYPE_INTERACT)

Envelope = namedtuple("Envelope", ["type", "payload"])


def encode_data(payload):
    """
    Encodes a DATA envelope. `payload` is free-form, whatever the
    business logic wants to send; must be JSON-serializable.
    """
    return _encode(TYPE_DATA, payload)


def encode_barrier(epoch, halt=False):
    """
    Encodes a BARRIER envelope (a Chandy-Lamport marker). `epoch`
    identifies the snapshot round. `halt=True` reuses the same marker
    for an ordered shutdown instead of a snapshot.
    """
    return _encode(TYPE_BARRIER, {"epoch": epoch, "halt": halt})


def encode_interact(command, args=None):
    """
    Encodes an INTERACT envelope. `command` names the action (e.g.
    "start_snapshot", "shutdown", "heartbeat", "checkpoint_saved"); the
    command catalog is deliberately open-ended.
    """
    return _encode(TYPE_INTERACT, {"command": command, "args": args or {}})


def _encode(envelope_type, payload):
    # No trailing newline: writing one (one write per line to the FIFO)
    # is the caller's job, keeping this symmetric with json.dumps itself.
    return json.dumps({"type": envelope_type, "payload": payload})


def decode_envelope(line):
    """
    Decodes one JSON-line envelope (as produced by encode_data/
    encode_barrier/encode_interact) into an Envelope(type, payload)
    namedtuple. Raises json.JSONDecodeError on malformed JSON, ValueError
    if "type"/"payload" is missing or "type" is not one of
    DATA/BARRIER/INTERACT.
    """
    obj = json.loads(line)

    if "type" not in obj or "payload" not in obj:
        raise ValueError(f"envelope missing 'type' or 'payload': {line!r}")

    envelope_type = obj["type"]
    if envelope_type not in _VALID_TYPES:
        raise ValueError(f"unknown envelope type: {envelope_type!r}")

    return Envelope(type=envelope_type, payload=obj["payload"])


#####################
# FBPProcess        #
#####################
#
# Base class for a long-running, stateful "resident" process. Covers,
# so far: the skeleton (argv parsing into self.opts, INPUT_PORTS/
# OUTPUT_PORTS validation, self.log) and the thread topology
# (reader/writer per port, brain, heartbeat). Barrier logic, INTERACT
# dispatch and the checkpoint/recovery startup sequence are later
# additions, layered on top of this -- _on_barrier/_on_interact below
# are deliberately still stubs.

# Sentinel put on a queue to tell its consumer thread to stop, rather
# than reusing e.g. None (a legitimate DATA payload).
_STOP = object()


def _parse_opts(argv):
    """
    Parses argv into a name -> value dict, following DeBasher's own
    "-optname value" CLI convention (see debasher_lib_opts.sh) -- one or
    two leading dashes, both stripped, so "-inf"/"--inf" both become the
    key "inf". `argv` is expected in the raw sys.argv shape a Python
    heredoc receives from debasher::_create_heredoc_func_body: element 0
    is "-c" (python's own placeholder for a "-c script" invocation),
    followed eventually by a "--" marker and then the actual option
    pairs; everything up to and including that marker is ignored. If no
    "--" marker is present, element 0 alone is skipped instead (the
    shape a plain sys.argv, or a hand-built argv missing the marker,
    would have).
    """
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = argv[1:]

    opts = {}
    it = iter(argv)
    for name in it:
        if not name.startswith("-"):
            raise ValueError(f"expected an option name starting with '-', got {name!r}")
        try:
            value = next(it)
        except StopIteration:
            raise ValueError(f"option {name!r} is missing its value") from None
        opts[name.lstrip("-")] = value
    return opts


class FBPProcess:
    """
    Base class for resident processes. A subclass declares its ports via
    the INPUT_PORTS/OUTPUT_PORTS class attributes (option names, without
    their leading dash(es), e.g. INPUT_PORTS = ["inf"]) and overrides
    process_data/capture_state/restore_state/initialize_runtime.
    """

    INPUT_PORTS = []
    OUTPUT_PORTS = []

    # Name of the OUTPUT_PORTS entry wired to the supervisor's heartbeat
    # channel, if any. A supervisor is optional (0 or 1 per resident
    # program): leave this None to run without one, in which case
    # checkpoints are still written, just never announced anywhere.
    SUPERVISOR_PORT = None

    DEFAULT_LOG_LEVEL = "INFO"
    HEARTBEAT_INTERVAL_SECONDS = 5
    CHECKPOINT_SCHEMA_VERSION = 1
    CHECKPOINT_RETENTION = 3

    def __init__(self, argv=None, opts=None):
        if opts is not None:
            # Direct injection, mainly for tests: skips argv parsing
            # entirely, so a test doesn't need to build a realistic
            # fake argv just to get a usable instance.
            self.opts = dict(opts)
        else:
            self.opts = _parse_opts(list(sys.argv) if argv is None else argv)

        self._check_declared_ports()
        self.log = self._make_logger()

        # Shared inbound queue: every reader thread pushes onto this one,
        # the brain thread is its only consumer. One outbound queue per
        # output port instead: a slow/stalled neighbor on one port must
        # only block that port's own writer thread, never the others or
        # the brain.
        self._inbound_queue = queue.Queue()
        self._outbound_queues = {port: queue.Queue() for port in self.OUTPUT_PORTS}

        self._reader_threads = {}
        self._writer_threads = {}
        self._brain_thread = None
        self._heartbeat_thread = None
        self._heartbeat_stop = threading.Event()

        # Chandy-Lamport barrier round in progress, if any (None = none).
        self._barrier_epoch = None
        self._barrier_halt = False
        self._barrier_pending = set()
        self._barrier_state = None
        self._barrier_channel_buffers = {}
        # Highest epoch this node has ever closed; -1 means none yet, so
        # the first round it self-initiates is epoch 0. A restored
        # checkpoint's epoch must seed this on startup (not yet built,
        # see the checkpoint-persistence/startup-sequence slices), or a
        # relaunched node would start renumbering from 0 again.
        self._last_epoch = -1

        # Set once an epoch closes with halt=True; watched (not acted on
        # here -- see _on_epoch_closed) by whatever orchestrates shutdown.
        self._halted = threading.Event()

    def _check_declared_ports(self):
        for port in list(self.INPUT_PORTS) + list(self.OUTPUT_PORTS):
            if port not in self.opts:
                raise ValueError(
                    f"{type(self).__name__}: port {port!r} is declared in "
                    f"INPUT_PORTS/OUTPUT_PORTS but there is no -{port} "
                    f"option (got: {sorted(self.opts)})"
                )

    def _make_logger(self):
        level_name = self.opts.get("log-level", self.DEFAULT_LOG_LEVEL).upper()
        logger = logging.getLogger(type(self).__name__)
        logger.setLevel(level_name)
        if not logger.handlers:
            handler = logging.StreamHandler(sys.stderr)
            handler.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)-8s [%(threadName)s] %(message)s")
            )
            logger.addHandler(handler)
        logger.propagate = False
        return logger

    # -- startup sequence --

    def run(self):
        """
        Full startup sequence: find the most recent checkpoint if any
        -> restore_state()/defaults -> initialize_runtime() ->
        start_threads() (opens every FIFO, starts every worker thread)
        -> wait until told to stop (an epoch closing with halt=True) ->
        stop every thread, from this (the calling) thread rather than
        the brain thread that actually set the stop signal.

        Log drain (replaying the message log from the checkpoint's
        saved offset, before accepting live traffic) is not
        implemented yet -- it depends on the message log itself,
        which hasn't been built.
        """
        checkpoint = self._load_latest_checkpoint()
        if checkpoint is not None:
            epoch, state = checkpoint
            self.restore_state(state)
            self._last_epoch = epoch
            self.log.info("restored checkpoint for epoch %s", epoch)
        else:
            self.log.info("no checkpoint found, starting with default values")

        self.initialize_runtime()

        # TODO: once the message log exists, drain it here (from the
        # checkpoint's saved offset, invoking process_data() for each
        # message in order) before starting the reader threads below.

        self.start_threads()
        self._halted.wait()
        self.stop_threads()

    def _load_latest_checkpoint(self):
        """
        Returns (epoch, state) for the highest-epoch checkpoint in this
        process's checkpoints directory, or None if there isn't one yet
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

        return checkpoint["epoch"], checkpoint["state"]

    # -- thread topology --

    def start_threads(self):
        """
        Starts one reader thread per INPUT_PORTS entry, one writer
        thread per OUTPUT_PORTS entry, the brain thread and the
        heartbeat thread. Threads are not daemonic: this process is
        meant to keep running until explicitly told to stop, not to be
        silently killed when some unrelated main thread happens to
        exit.
        """
        for port in self.INPUT_PORTS:
            thread = threading.Thread(
                target=self._reader_loop, args=(port,), name=f"reader:{port}"
            )
            self._reader_threads[port] = thread
            thread.start()

        for port in self.OUTPUT_PORTS:
            thread = threading.Thread(
                target=self._writer_loop, args=(port,), name=f"writer:{port}"
            )
            self._writer_threads[port] = thread
            thread.start()

        self._brain_thread = threading.Thread(target=self._brain_loop, name="brain")
        self._brain_thread.start()

        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, name="heartbeat")
        self._heartbeat_thread.start()

    def stop_threads(self, timeout=None):
        """
        Signals the brain, writer and heartbeat threads to stop and
        waits for every thread (including readers) to finish. Reader
        threads have no sentinel of their own -- they stop on their
        FIFO's EOF, i.e. once its writer closes it, so this only waits
        for that to have already happened (or already be happening).
        """
        self._inbound_queue.put(_STOP)
        for q in self._outbound_queues.values():
            q.put(_STOP)
        self._heartbeat_stop.set()

        for thread in [
            *self._reader_threads.values(),
            *self._writer_threads.values(),
            self._brain_thread,
            self._heartbeat_thread,
        ]:
            if thread is not None:
                thread.join(timeout)

    def _reader_loop(self, port_name):
        path = self.opts[port_name]
        self.log.debug("reader for port %r opening %r", port_name, path)
        with open(path, "r") as fifo:
            for line in fifo:
                line = line.rstrip("\n")
                if not line:
                    continue
                envelope = decode_envelope(line)
                self._inbound_queue.put((port_name, envelope.type, envelope.payload))
        self.log.debug("reader for port %r closed (EOF)", port_name)

    def _writer_loop(self, port_name):
        path = self.opts[port_name]
        out_queue = self._outbound_queues[port_name]
        self.log.debug("writer for port %r opening %r", port_name, path)
        with open(path, "w") as fifo:
            while True:
                item = out_queue.get()
                if item is _STOP:
                    break
                fifo.write(item + "\n")
                fifo.flush()
        self.log.debug("writer for port %r stopped", port_name)

    def _brain_loop(self):
        while True:
            item = self._inbound_queue.get()
            if item is _STOP:
                break
            port_name, envelope_type, payload = item
            if envelope_type == TYPE_DATA:
                if port_name in self._barrier_pending:
                    # A barrier round is open and this port's marker for
                    # it hasn't arrived yet: this DATA is in transit from
                    # before the sender's own snapshot, so it belongs to
                    # the channel's state, not to normal processing.
                    self._barrier_channel_buffers[port_name].append(payload)
                else:
                    self.process_data(port_name, payload)
            elif envelope_type == TYPE_BARRIER:
                self._on_barrier(port_name, payload)
            elif envelope_type == TYPE_INTERACT:
                self._on_interact(payload)
        self.log.debug("brain thread stopped")

    def _heartbeat_loop(self):
        while not self._heartbeat_stop.wait(self.HEARTBEAT_INTERVAL_SECONDS):
            self.log.debug("heartbeat tick, healthy=%s", self._all_threads_alive())
        self.log.debug("heartbeat thread stopped")

    def _all_threads_alive(self):
        """
        True only if every reader, writer and the brain thread are
        still alive. A Python thread killed by an uncaught exception
        dies silently without crashing the process, so this passive
        check is what actually catches that, rather than requiring
        reader/writer threads to report anything themselves.
        """
        threads = [*self._reader_threads.values(), *self._writer_threads.values()]
        if self._brain_thread is not None:
            threads.append(self._brain_thread)
        return all(thread.is_alive() for thread in threads)

    def send_data(self, port_name, payload):
        """Enqueues a DATA envelope for port_name's writer thread to send."""
        self._outbound_queues[port_name].put(encode_data(payload))

    def _send_barrier(self, port_name, epoch, halt=False):
        self._outbound_queues[port_name].put(encode_barrier(epoch, halt=halt))

    def _send_interact(self, port_name, command, args=None):
        self._outbound_queues[port_name].put(encode_interact(command, args))

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
        self._barrier_state = self.capture_state()
        for out_port in self.OUTPUT_PORTS:
            # The supervisor channel never sees a BARRIER: it doesn't
            # take part in the barrier protocol, only in INTERACT.
            if out_port == self.SUPERVISOR_PORT:
                continue
            self._send_barrier(out_port, epoch, halt=halt)

        pending = set(self.INPUT_PORTS)
        pending.discard(arrived_port)
        self._barrier_pending = pending
        self._barrier_channel_buffers = {port: [] for port in pending}

    def _close_barrier_round(self):
        epoch = self._barrier_epoch
        halt = self._barrier_halt
        state = self._barrier_state
        channel_buffers = self._barrier_channel_buffers

        self._last_epoch = max(self._last_epoch, epoch)
        self._barrier_epoch = None
        self._barrier_halt = False
        self._barrier_state = None
        self._barrier_pending = set()
        self._barrier_channel_buffers = {}

        self._on_epoch_closed(epoch, halt, state, channel_buffers)

    def _on_epoch_closed(self, epoch, halt, state, channel_buffers):
        path = self._save_checkpoint(epoch, state, channel_buffers)
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
        execdir = os.environ.get("DEBASHER_PROCESS_EXECDIR")
        if not execdir:
            raise RuntimeError(
                f"{type(self).__name__}: DEBASHER_PROCESS_EXECDIR is not set in the "
                "environment, cannot locate this process's checkpoints directory (only "
                "set by the engine's builtin scheduler when it launches a process)"
            )
        return os.path.join(execdir, "checkpoints")

    def _save_checkpoint(self, epoch, state, channel_buffers):
        checkpoints_dir = self._checkpoints_dir()
        os.makedirs(checkpoints_dir, exist_ok=True)

        checkpoint = {
            "schema_version": self.CHECKPOINT_SCHEMA_VERSION,
            "epoch": epoch,
            "state": state,
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

    # -- subclass extension points --

    def process_data(self, port_name, packet):
        raise NotImplementedError

    def capture_state(self):
        raise NotImplementedError

    def restore_state(self, state):
        raise NotImplementedError

    def initialize_runtime(self):
        raise NotImplementedError
