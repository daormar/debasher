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
import copy
import json
import logging
import queue
import subprocess
import threading
import time
from collections import namedtuple

# Constants
DEBASHER_SHUTDOWN_TOKEN = "__SHUTDOWN_TOKEN__"

#####################
# CONTROL ENVELOPE  #
#####################
#
# JSON Lines wire format for communication between resident processes
# (FBPProcess/Supervisor). Sibling envelope types, always encoded as their
# own single-line JSON object: a BARRIER or INTERACT message is never
# nested inside DATA's payload, so a reader can dispatch on "type" alone,
# without ever interpreting "payload". DATA, BARRIER and INTERACT carry
# the messages themselves. CLOSE and HELLO belong to the transport: a
# writer sends HELLO as the first line of every incarnation of itself (so
# its reader can discard a fragment left by the previous one) and CLOSE
# when it stops on purpose.

TYPE_DATA = "DATA"
TYPE_BARRIER = "BARRIER"
TYPE_INTERACT = "INTERACT"
TYPE_CLOSE = "CLOSE"
TYPE_HELLO = "HELLO"

_VALID_TYPES = (TYPE_DATA, TYPE_BARRIER, TYPE_INTERACT, TYPE_CLOSE, TYPE_HELLO)

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


def encode_close():
    """
    Encodes a CLOSE envelope: sent by a writer, as its very last line,
    when it stops on purpose. A reader that sees it knows nothing more
    will ever come through that channel from that writer. Without it,
    silence means either that the writer finished or that it crashed and
    will be relaunched, and nothing in the fifo tells the two apart.
    """
    return _encode(TYPE_CLOSE, {})


def encode_hello():
    """
    Encodes a HELLO envelope. A writer sends it as the first thing it does
    every time it starts, in one write together with a leading newline
    (see _PortWorker._writer_loop). If the previous incarnation of the
    writer died in the middle of a message, what it left in the fifo is an
    unterminated fragment: the newline turns it into a line of its own,
    and the reader, which tolerates one unparsable line only when a HELLO
    follows it, drops it.
    """
    return _encode(TYPE_HELLO, {})


def _encode(envelope_type, payload):
    # No trailing newline: writing one (one write per line to the FIFO)
    # is the caller's job, keeping this symmetric with json.dumps itself.
    return json.dumps({"type": envelope_type, "payload": payload})


def decode_envelope(line):
    """
    Decodes one JSON-line envelope (as produced by encode_data/
    encode_barrier/encode_interact/encode_close/encode_hello) into an
    Envelope(type, payload) namedtuple. Raises json.JSONDecodeError on
    malformed JSON, ValueError if "type"/"payload" is missing or "type"
    is not one of the valid envelope types.
    """
    obj = json.loads(line)

    if "type" not in obj or "payload" not in obj:
        raise ValueError(f"envelope missing 'type' or 'payload': {line!r}")

    envelope_type = obj["type"]
    if envelope_type not in _VALID_TYPES:
        raise ValueError(f"unknown envelope type: {envelope_type!r}")

    return Envelope(type=envelope_type, payload=obj["payload"])


#####################
# _PortWorker       #
#####################
#
# Thread-per-port plumbing shared by FBPProcess and Supervisor: argv
# parsing into self.opts, a logger, one reader thread per declared input
# port pushing tagged envelopes onto a single shared inbound queue, one
# writer thread per declared output port with its own outbound queue,
# and start_threads()/stop_threads() to manage all of it. Carries no
# barrier, checkpoint or message-log logic -- that is FBPProcess-
# specific, layered on top by it alone; Supervisor does not take part in
# the barrier protocol at all, but reuses this same base.

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


def _open_fifo_reader(path):
    """
    Opens a fifo for the process that reads it and returns (real read end,
    ghost write end). Holding a write end of its own means the reader never
    sees EOF, whether its peer finished or crashed: a fifo delivers no
    signal that tells the two apart, so any such event would be ambiguous,
    and the peer's liveness is decided elsewhere (heartbeats, CLOSE). The
    ghost end is non-blocking and is only ever used to wake the reader
    (see _PortWorker.stop_threads).

    The order never blocks, whatever the state of the peer: a read-only
    open with O_NONBLOCK returns at once even with no writer around, and
    the write-only open that follows finds the reader just opened. O_RDWR
    is not used because POSIX leaves it undefined for fifos.
    """
    rfd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    try:
        gfd = os.open(path, os.O_WRONLY)
    except BaseException:
        os.close(rfd)
        raise
    os.set_blocking(rfd, True)
    os.set_blocking(gfd, False)
    return rfd, gfd


def _open_fifo_writer(path):
    """
    Opens a fifo for the process that writes it and returns (real write end,
    ghost read end). Holding a read end of its own means the writer never
    gets EPIPE: while its peer is down, what it writes waits in the pipe
    (which the ghost end keeps alive, unread data included) and the writer
    only blocks once the pipe is full, until a reader comes back. Same
    non-blocking open order as _open_fifo_reader.
    """
    gfd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    try:
        wfd = os.open(path, os.O_WRONLY)
    except BaseException:
        os.close(gfd)
        raise
    return wfd, gfd


def _write_all(fd, text):
    """Writes the whole text to a blocking fd, coping with partial writes."""
    data = text.encode("utf-8")
    while data:
        data = data[os.write(fd, data) :]


class _PortWorker:
    """
    A subclass supplies _input_ports()/_output_ports(), each returning a
    dict {tag: option_name}. The tag is whatever identity the subclass's
    own dispatch logic actually cares about: a port name for FBPProcess
    (its barrier logic treats every input port interchangeably), a node
    name for Supervisor (its detection/relaunch logic acts on a specific
    supervised node, not "which port").
    """

    DEFAULT_LOG_LEVEL = "INFO"

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
        self._outbound_queues = {tag: queue.Queue() for tag in self._output_ports()}

        self._reader_threads = {}
        self._writer_threads = {}
        self._brain_thread = None

        # The fifo file descriptors of every port, opened by start_threads()
        # and closed by stop_threads() once the thread using them is gone:
        # tag -> (real end, ghost end).
        self._reader_fds = {}
        self._writer_fds = {}
        self._stopping = threading.Event()

    def _input_ports(self):
        raise NotImplementedError

    def _output_ports(self):
        raise NotImplementedError

    def _check_declared_ports(self):
        option_names = list(self._input_ports().values()) + list(self._output_ports().values())
        for option_name in option_names:
            if option_name not in self.opts:
                raise ValueError(
                    f"{type(self).__name__}: port option {option_name!r} is declared "
                    f"but there is no -{option_name} option (got: {sorted(self.opts)})"
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

    # -- thread topology --

    # How long stop_threads() waits for each writer thread when it is not
    # given a timeout of its own. A writer only fails to finish in time when
    # its peer is down and the fifo is full, since a write then blocks until a
    # reader comes back; writer threads are daemons, so abandoning one never
    # keeps the process alive.
    WRITER_STOP_TIMEOUT_SECS = 5

    def start_threads(self):
        """
        Opens every fifo, then starts one reader thread per declared input
        port, one writer thread per declared output port, and the brain
        thread. Nothing here waits for a peer: every endpoint holds both
        ends of its fifo (see _open_fifo_reader and _open_fifo_writer), so
        the channel outlives the crash of either process and the processes
        can start in any order.

        Brain and reader threads are not daemons: this process is meant to
        keep running until explicitly told to stop, and stop_threads() can
        always wake and join them. Writer threads are daemons, because one
        can stay blocked in a write while its peer is down and must never
        keep the process alive.
        """
        for tag, option_name in self._input_ports().items():
            self._reader_fds[tag] = _open_fifo_reader(self.opts[option_name])
        for tag, option_name in self._output_ports().items():
            self._writer_fds[tag] = _open_fifo_writer(self.opts[option_name])

        for tag, option_name in self._input_ports().items():
            thread = threading.Thread(
                target=self._reader_loop, args=(tag, option_name), name=f"reader:{tag}"
            )
            self._reader_threads[tag] = thread
            thread.start()

        for tag, option_name in self._output_ports().items():
            thread = threading.Thread(
                target=self._writer_loop,
                args=(tag, option_name),
                name=f"writer:{tag}",
                daemon=True,
            )
            self._writer_threads[tag] = thread
            thread.start()

        self._brain_thread = threading.Thread(target=self._brain_loop, name="brain")
        self._brain_thread.start()

    def stop_threads(self, timeout=None):
        """
        Signals every thread to stop and waits for them. A reader blocked
        in read() is woken by a blank line written through its own ghost
        write end (that write is non-blocking, so a full pipe cannot hold
        this up: a reader with a full pipe in front of it is not blocked).
        A writer sends what is already queued, then CLOSE, and ends; one
        that cannot finish because its peer is down and the pipe is full is
        abandoned after `timeout` (WRITER_STOP_TIMEOUT_SECS if none is
        given), and its descriptors are left open for it.
        """
        self._stopping.set()
        self._inbound_queue.put(_STOP)
        for q in self._outbound_queues.values():
            q.put(_STOP)

        for _, ghost_fd in self._reader_fds.values():
            try:
                os.write(ghost_fd, b"\n")
            except OSError:
                pass

        for thread in [*self._reader_threads.values(), self._brain_thread]:
            if thread is not None:
                thread.join(timeout)

        writer_timeout = self.WRITER_STOP_TIMEOUT_SECS if timeout is None else timeout
        for tag, thread in self._writer_threads.items():
            thread.join(writer_timeout)
            if thread.is_alive():
                self.log.warning(
                    "writer for %r did not finish within %s s (its peer is probably "
                    "down and the fifo is full), abandoning it",
                    tag,
                    writer_timeout,
                )

        self._close_finished_fifos()

    def _close_finished_fifos(self):
        """Closes the descriptors of every port whose thread has ended."""
        for threads, fds in (
            (self._reader_threads, self._reader_fds),
            (self._writer_threads, self._writer_fds),
        ):
            for tag in list(fds):
                thread = threads.get(tag)
                if thread is not None and thread.is_alive():
                    continue
                for fd in fds.pop(tag):
                    try:
                        os.close(fd)
                    except OSError:
                        pass

    def _ends_on_close(self, tag):
        """
        Whether the reader of `tag` ends its loop when the writer sends
        CLOSE (the default), or keeps listening after it. Supervisor
        overrides it: a node that closes its channel and is later
        relaunched must still be heard, and it decides whether a node
        finished for good from the node's own .finished file instead.
        """
        return True

    def _reader_loop(self, tag, option_name):
        rfd, _ = self._reader_fds[tag]
        self.log.debug("reader for %r reading %r", tag, self.opts[option_name])

        # The descriptor stays open when this file object closes: it belongs
        # to start_threads()/stop_threads().
        with os.fdopen(
            rfd, "r", encoding="utf-8", errors="replace", newline="\n", closefd=False
        ) as fifo:
            # An unparsable line is tolerated once, provided the next line
            # is a HELLO: it is then the fragment left by a writer that died
            # in the middle of a message (see encode_hello). Anything else
            # is a corrupt stream, never skipped silently.
            fragment = None
            for line in fifo:
                if self._stopping.is_set():
                    break
                line = line.rstrip("\n")
                if not line:
                    continue

                try:
                    envelope = decode_envelope(line)
                except json.JSONDecodeError:
                    if fragment is not None:
                        raise ValueError(
                            f"{type(self).__name__}: two unparsable lines in a row on "
                            f"{tag!r}: {fragment[:60]!r} and {line[:60]!r}"
                        ) from None
                    fragment = line
                    continue

                if envelope.type == TYPE_HELLO:
                    if fragment is not None:
                        self.log.warning(
                            "reader for %r dropped %d bytes left by a writer that died "
                            "in the middle of a message",
                            tag,
                            len(fragment),
                        )
                        fragment = None
                    continue

                if fragment is not None:
                    raise ValueError(
                        f"{type(self).__name__}: unparsable line on {tag!r} not followed "
                        f"by HELLO: {fragment[:60]!r}"
                    )

                self._inbound_queue.put((tag, envelope.type, envelope.payload))
                if envelope.type == TYPE_CLOSE and self._ends_on_close(tag):
                    break

        self.log.debug("reader for %r stopped", tag)

    def _writer_loop(self, tag, option_name):
        wfd, _ = self._writer_fds[tag]
        out_queue = self._outbound_queues[tag]
        self.log.debug("writer for %r writing %r", tag, self.opts[option_name])

        # The first thing every incarnation of a writer sends, in one write
        # so that it is atomic: a newline, which ends any unterminated
        # fragment a previous incarnation may have left in the fifo, and a
        # HELLO line, which tells the reader that such a leftover is an
        # artifact of a crash and can be dropped (see encode_hello).
        _write_all(wfd, "\n" + encode_hello() + "\n")
        while True:
            item = out_queue.get()
            if item is _STOP:
                _write_all(wfd, encode_close() + "\n")
                break
            _write_all(wfd, item + "\n")
        self.log.debug("writer for %r stopped", tag)

    def _brain_loop(self):
        raise NotImplementedError

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

    def _execdir(self):
        execdir = os.environ.get("DEBASHER_PROCESS_EXECDIR")
        if not execdir:
            raise RuntimeError(
                f"{type(self).__name__}: DEBASHER_PROCESS_EXECDIR is not set in the "
                "environment, cannot locate this process's own directory (only set "
                "by the engine's builtin scheduler when it launches a process)"
            )
        return execdir

    def send_data(self, tag, payload):
        """Enqueues a DATA envelope for tag's writer thread to send."""
        self._outbound_queues[tag].put(encode_data(payload))

    def _send_barrier(self, tag, epoch, halt=False):
        self._outbound_queues[tag].put(encode_barrier(epoch, halt=halt))

    def _send_interact(self, tag, command, args=None):
        self._outbound_queues[tag].put(encode_interact(command, args))


#####################
# FBPProcess        #
#####################
#
# Base class for a long-running, stateful "resident" process. Adds, on
# top of _PortWorker's generic thread-per-port plumbing: INPUT_PORTS/
# OUTPUT_PORTS declaration, the heartbeat thread, Chandy-Lamport barrier
# logic, INTERACT dispatch, checkpointing, the message log and the
# checkpoint/recovery startup sequence (run()).


class FBPProcess(_PortWorker):
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

    HEARTBEAT_INTERVAL_SECONDS = 5
    CHECKPOINT_SCHEMA_VERSION = 1
    CHECKPOINT_RETENTION = 3

    # Safety cap only, never the normal pruning mechanism (that's tied to
    # checkpoint retention -- see _prune_old_checkpoints): if a single
    # input port's un-pruned log segments exceed this many bytes, the
    # process never closed an epoch for long enough that pruning could
    # keep up, which is a real problem (no periodic/triggered snapshot)
    # to surface as a hard error, not something to paper over by
    # silently discarding log data a future recovery might need.
    MESSAGE_LOG_MAX_BYTES = 100 * 1024 * 1024

    def __init__(self, argv=None, opts=None):
        super().__init__(argv, opts)

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

    def _input_ports(self):
        return {port: port for port in self.INPUT_PORTS}

    def _output_ports(self):
        return {port: port for port in self.OUTPUT_PORTS}

    # -- startup sequence --

    def run(self):
        """
        Full startup sequence: find the most recent checkpoint if any
        -> restore_state()/defaults -> initialize_runtime() -> (if
        restored) drain the message log -> start_threads() (opens
        every FIFO, starts every worker thread) -> wait until told to
        stop (an epoch closing with halt=True) -> stop every thread,
        from this (the calling) thread rather than the brain thread
        that actually set the stop signal.
        """
        checkpoint = self._load_latest_checkpoint()
        restored_epoch = None
        if checkpoint is not None:
            epoch, state = checkpoint
            self.restore_state(state)
            self._last_epoch = epoch
            restored_epoch = epoch
            self.log.info("restored checkpoint for epoch %s", epoch)
        else:
            self.log.info("no checkpoint found, starting with default values")

        self.initialize_runtime()

        if restored_epoch is not None:
            self._drain_message_log(restored_epoch)

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
        Starts everything _PortWorker.start_threads() already does
        (reader/writer/brain threads), plus this class's own heartbeat
        thread.
        """
        super().start_threads()
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, name="heartbeat")
        self._heartbeat_thread.start()

    def stop_threads(self, timeout=None):
        """
        Signals the heartbeat thread to stop, then defers to
        _PortWorker.stop_threads() for the reader/writer/brain threads,
        then joins the heartbeat thread too.
        """
        self._heartbeat_stop.set()
        super().stop_threads(timeout)
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout)

    def _brain_loop(self):
        while True:
            item = self._inbound_queue.get()
            if item is _STOP:
                break
            port_name, envelope_type, payload = item
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
                # Logged here, on the brain thread, right before
                # process_data() actually runs, not in the reader
                # thread that received it. self._last_epoch is only
                # ever advanced on this same brain thread (barrier
                # round closing), so reading it here is race-free by
                # construction; reading it from a reader thread
                # raced against that update in practice (found by
                # testing, not reasoning) and could mislabel a
                # message with the epoch just before it actually
                # closed, making a real replay gap after a crash.
                self._log_received_data(port_name, payload)
                self.process_data(port_name, payload)
            elif envelope_type == TYPE_BARRIER:
                self._on_barrier(port_name, payload)
            elif envelope_type == TYPE_INTERACT:
                self._on_interact(payload)
            elif envelope_type == TYPE_CLOSE:
                self.log.debug("port %r was closed by its writer", port_name)
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
        return os.path.join(self._execdir(), "checkpoints")

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
            self._prune_message_log_epoch(old_epoch)

    # -- message log --
    #
    # Each input port's own log lives under this process's own directory,
    # written by this same process's reader threads as messages arrive --
    # never the neighbor that sent them. The process that ever needs to
    # replay a log is always the one relaunched after a crash, i.e.
    # itself, never its neighbor, so there is no reason for the log to
    # live anywhere else, and no separate process/fifo tap is needed to
    # produce it (unlike the engine's generic --mirror, which stays a
    # purely manual debug-inspection tool, untouched by any of this).

    def _log_dir(self, port_name):
        return os.path.join(self._execdir(), "log", port_name)

    def _log_segment_path(self, port_name, epoch):
        return os.path.join(self._log_dir(port_name), f"{epoch}.log")

    def _log_received_data(self, port_name, payload):
        # Messages received while a barrier round is open (still pending
        # on this port) are logged the same as any other: replay only
        # ever needs "everything received since the last checkpoint",
        # regardless of which epoch's round it happened to arrive during.
        epoch = self._last_epoch + 1
        log_dir = self._log_dir(port_name)
        os.makedirs(log_dir, exist_ok=True)
        with open(self._log_segment_path(port_name, epoch), "a") as f:
            f.write(json.dumps(payload))
            f.write("\n")

        self._check_message_log_size(port_name, log_dir)

    def _check_message_log_size(self, port_name, log_dir):
        total = sum(
            os.path.getsize(os.path.join(log_dir, name)) for name in os.listdir(log_dir)
        )
        if total > self.MESSAGE_LOG_MAX_BYTES:
            raise RuntimeError(
                f"{type(self).__name__}: message log for port {port_name!r} exceeds "
                f"{self.MESSAGE_LOG_MAX_BYTES} bytes with no checkpoint pruning having "
                "kept up -- this means an epoch is never closing (no periodic or "
                "triggered snapshot), a real problem to fix, not something to silently "
                "discard log data over"
            )

    def _prune_message_log_epoch(self, epoch):
        for port_name in self.INPUT_PORTS:
            try:
                os.remove(self._log_segment_path(port_name, epoch))
            except FileNotFoundError:
                # This port simply received nothing during that epoch.
                pass

    def _drain_message_log(self, checkpoint_epoch):
        """
        Replays every DATA message logged after checkpoint_epoch, for
        every input port, invoking process_data() for each in order.
        Reads straight from disk, never from a fifo, so it can never
        end up re-logging what it is replaying.
        """
        for port_name in self.INPUT_PORTS:
            log_dir = self._log_dir(port_name)
            if not os.path.isdir(log_dir):
                continue

            epochs = []
            for name in os.listdir(log_dir):
                if not name.endswith(".log"):
                    continue
                try:
                    epoch = int(name[: -len(".log")])
                except ValueError:
                    continue
                if epoch > checkpoint_epoch:
                    epochs.append(epoch)
            epochs.sort()

            for epoch in epochs:
                with open(self._log_segment_path(port_name, epoch)) as f:
                    for line in f:
                        line = line.rstrip("\n")
                        if not line:
                            continue
                        self.process_data(port_name, json.loads(line))

    # -- subclass extension points --

    def process_data(self, port_name, packet):
        raise NotImplementedError

    def capture_state(self):
        raise NotImplementedError

    def restore_state(self, state):
        raise NotImplementedError

    def initialize_runtime(self):
        raise NotImplementedError


#####################
# Supervisor        #
#####################
#
# A class of its own, distinct from FBPProcess: it does not take part in
# the barrier protocol as a business node, so it shares only
# _PortWorker's generic thread-per-port plumbing, none of FBPProcess's
# barrier/checkpoint/message-log logic. Watches a fixed set of nodes
# (NODE_PORTS) for heartbeat/checkpoint_saved INTERACT traffic, detects
# failure (heartbeat timeout, or a dead PID as a faster, certain
# shortcut -- a live PID is never, by itself, evidence of health),
# relaunches a downed node up to a bounded number of times, and can
# trigger snapshot/shutdown on one or more configured initiators,
# including an escalation to a hard kill of the whole program if a
# permanently failed node leaves part of the graph unreachable by an
# ordinary ordered shutdown.

# Tag for the (optional) external manual-trigger input port in the
# shared inbound queue -- distinct from any real node name in NODE_PORTS
# by construction (Python identifiers can't contain spaces).
_MANUAL_TRIGGER_TAG = "manual trigger"


class Supervisor(_PortWorker):
    """
    A subclass declares NODE_PORTS = {node: option_name} (one entry per
    supervised node's heartbeat channel), where node is either a string
    (the name of a non-array process) or a (process_name, task_idx)
    tuple (one task of an array process), and optionally TRIGGER_PORT
    (a list of output option names, one per initiator to send
    start_snapshot/shutdown to) and MANUAL_TRIGGER_PORT (a single input
    option name for an external manual trigger, relayed verbatim to
    every TRIGGER_PORT entry).
    """

    NODE_PORTS = {}
    TRIGGER_PORT = []
    MANUAL_TRIGGER_PORT = None

    HEARTBEAT_TIMEOUT_SECS = 30
    HEARTBEAT_CHECK_INTERVAL_SECS = 5
    MAX_RELAUNCH_ATTEMPTS = 3
    FORCE_STOP_TIMEOUT_SECS = 60

    def __init__(self, argv=None, opts=None):
        self._check_node_names()
        super().__init__(argv, opts)

        self._lock = threading.Lock()
        now = time.time()
        # Seeded to "now", not 0: a node that simply hasn't had time yet
        # to send its first heartbeat must not be declared down before
        # HEARTBEAT_TIMEOUT_SECS has genuinely elapsed.
        self._last_heartbeat = {node: now for node in self.NODE_PORTS}
        self._relaunch_attempts = {node: 0 for node in self.NODE_PORTS}
        self._down = set()
        self._done = set()
        self._given_up = set()
        self._active_escalations = 0

        self._checker_thread = None
        self._checker_stop = threading.Event()
        # Set once every node is resolved (done, or given up on) and no
        # shutdown escalation is still in flight -- watched by run(),
        # not acted on by the checker thread itself (which would deadlock
        # joining its own thread from inside stop_threads()).
        self._all_resolved = threading.Event()

    def _check_node_names(self):
        for node in self.NODE_PORTS:
            if isinstance(node, str):
                continue
            is_task = (
                isinstance(node, tuple)
                and len(node) == 2
                and isinstance(node[0], str)
                and isinstance(node[1], int)
                and not isinstance(node[1], bool)
                and node[1] >= 0
            )
            if not is_task:
                raise ValueError(
                    f"{type(self).__name__}: NODE_PORTS key {node!r} must be a process "
                    "name (str) or a (process_name, task_idx) tuple with a natural "
                    "task_idx"
                )

    def _input_ports(self):
        ports = dict(self.NODE_PORTS)
        if self.MANUAL_TRIGGER_PORT is not None:
            ports[_MANUAL_TRIGGER_TAG] = self.MANUAL_TRIGGER_PORT
        return ports

    def _output_ports(self):
        return {port: port for port in self.TRIGGER_PORT}

    # -- startup sequence --

    def run(self):
        """
        Supervisor carries no state of its own to restore -- it always
        starts fresh. Runs until every supervised node is resolved
        (cleanly done, or given up on after exhausting its relaunch
        budget) and no shutdown escalation is still in flight.
        """
        self.start_threads()
        self._all_resolved.wait()
        self.stop_threads()

    def start_threads(self):
        super().start_threads()
        self._checker_thread = threading.Thread(target=self._check_loop, name="checker")
        self._checker_thread.start()

    def stop_threads(self, timeout=None):
        self._checker_stop.set()
        super().stop_threads(timeout)
        if self._checker_thread is not None:
            self._checker_thread.join(timeout)

    # -- brain loop: heartbeat/checkpoint_saved from nodes, manual trigger --

    def _brain_loop(self):
        while True:
            item = self._inbound_queue.get()
            if item is _STOP:
                break
            tag, envelope_type, payload = item
            if envelope_type == TYPE_CLOSE:
                self.log.debug("%r closed its channel", tag)
                continue
            if envelope_type != TYPE_INTERACT:
                # Every Supervisor channel (node heartbeat or manual
                # trigger) only ever carries INTERACT by design (point 1's
                # channel topology) -- a DATA/BARRIER here is a protocol
                # violation, not something to crash the process over.
                self.log.warning(
                    "ignoring unexpected %r envelope on %r (Supervisor channels "
                    "only ever carry INTERACT)",
                    envelope_type,
                    tag,
                )
                continue

            if tag == _MANUAL_TRIGGER_TAG:
                self._on_manual_trigger(payload)
            else:
                self._on_node_interact(tag, payload)
        self.log.debug("brain thread stopped")

    def _on_manual_trigger(self, payload):
        # A pure relay: Supervisor does not validate or interpret
        # `command`, matching the deliberately open-ended INTERACT
        # catalog convention used everywhere else in this design -- the
        # real safety net is the initiator's own _on_interact, one hop
        # further down (unrecognized command logged and ignored, never
        # aborts).
        command = payload["command"]
        args = payload.get("args")
        for port in self.TRIGGER_PORT:
            self._send_interact(port, command, args)

    def _on_node_interact(self, node_name, payload):
        command = payload["command"]
        if command == "heartbeat":
            self._on_heartbeat(node_name)
        elif command == "checkpoint_saved":
            self.log.info("node %r saved a checkpoint: %s", node_name, payload.get("args"))
        else:
            self.log.warning(
                "ignoring unrecognized INTERACT command from node %r: %r", node_name, command
            )

    def _on_heartbeat(self, node_name):
        with self._lock:
            self._last_heartbeat[node_name] = time.time()
            self._down.discard(node_name)
            # A real heartbeat is proof of actual recovery (unlike a
            # merely-live PID, see _node_pid_alive) -- this is what
            # distinguishes a node crash-looping right after every
            # relaunch (never reaches here, budget keeps draining) from
            # one that fails rarely over a long run and always recovers.
            self._relaunch_attempts[node_name] = 0

    # -- failure detection --

    def _check_loop(self):
        while not self._checker_stop.wait(self.HEARTBEAT_CHECK_INTERVAL_SECS):
            self._check_once()

    def _check_once(self):
        for node_name in self.NODE_PORTS:
            self._check_node(node_name)
        self._maybe_resolve()

    def _check_node(self, node_name):
        with self._lock:
            if node_name in self._done or node_name in self._given_up:
                return

        # Checked unconditionally, every tick, regardless of "down"
        # status: cheap (one stat() call), and this is what lets a
        # node's clean completion be noticed within one
        # HEARTBEAT_CHECK_INTERVAL_SECS rather than waiting for a full
        # HEARTBEAT_TIMEOUT_SECS, and what keeps an intentional ordered
        # shutdown from ever looking like a crash.
        if os.path.exists(self._node_finished_file(node_name)):
            with self._lock:
                self._done.add(node_name)
                self._down.discard(node_name)
            self.log.info("node %r finished cleanly", node_name)
            return

        with self._lock:
            already_down = node_name in self._down
        if already_down:
            # Already declared down and (by default) already being
            # relaunched -- don't call on_node_down again for the same
            # outage every tick; only a real heartbeat (_on_heartbeat)
            # clears this.
            return

        if not self._node_pid_alive(node_name):
            self._declare_down(node_name)
            return

        with self._lock:
            last_seen = self._last_heartbeat[node_name]
        if time.time() - last_seen > self.HEARTBEAT_TIMEOUT_SECS:
            self._declare_down(node_name)

    def _declare_down(self, node_name):
        with self._lock:
            if node_name in self._down:
                return
            self._down.add(node_name)
            self._relaunch_attempts[node_name] += 1
            attempts = self._relaunch_attempts[node_name]

        if attempts > self.MAX_RELAUNCH_ATTEMPTS:
            with self._lock:
                self._given_up.add(node_name)
            self.log.error(
                "node %r exceeded %s relaunch attempts, giving up",
                node_name,
                self.MAX_RELAUNCH_ATTEMPTS,
            )
            self.on_node_permanently_failed(node_name)
        else:
            self.log.warning(
                "node %r is down (attempt %s/%s), relaunching",
                node_name,
                attempts,
                self.MAX_RELAUNCH_ATTEMPTS,
            )
            self.on_node_down(node_name)

    def _maybe_resolve(self):
        with self._lock:
            resolved = len(self._done) + len(self._given_up) == len(self.NODE_PORTS)
            no_escalation_pending = self._active_escalations == 0
        if resolved and no_escalation_pending:
            self._all_resolved.set()

    # -- paths shared with the engine's own conventions --

    def _program_dir(self):
        # DEBASHER_PROCESS_EXECDIR is this Supervisor's own
        # __exec__/<name>/ directory; every sibling node's own directory
        # hangs off the same __exec__ parent, one level up.
        return os.path.dirname(self._execdir())

    def _program_outdir(self):
        # debasher_stop -d wants the program's own base output
        # directory, i.e. the parent of __exec__ itself -- confirmed
        # against debasher::get_prg_exec_dir_given_basedir
        # (<dirname>/__exec__/<processname>), no new engine export
        # needed.
        return os.path.dirname(self._program_dir())

    # A node is identified by a NODE_PORTS key that is either a plain
    # string (the name of a non-array process) or a (process_name,
    # task_idx) tuple (one task of an array process).

    @staticmethod
    def _node_process_name(node):
        return node if isinstance(node, str) else node[0]

    @staticmethod
    def _node_task_idx(node):
        return None if isinstance(node, str) else node[1]

    def _node_file_stem(self, node):
        # Same naming as the engine's own per-task files
        # (debasher::_get_array_taskid_filename,
        # debasher::_get_task_finished_filename): "<process>_<idx>" for a
        # task of an array process, plain "<process>" otherwise.
        idx = self._node_task_idx(node)
        name = self._node_process_name(node)
        return name if idx is None else f"{name}_{idx}"

    def _node_exec_dir(self, node):
        return os.path.join(self._program_dir(), self._node_process_name(node))

    def _node_finished_file(self, node):
        return os.path.join(self._node_exec_dir(node), f"{self._node_file_stem(node)}.finished")

    def _node_id_file(self, node):
        return os.path.join(self._node_exec_dir(node), f"{self._node_file_stem(node)}.id")

    def _launch_process_command(self, node):
        libexecdir = os.environ.get("DEBASHER_LIBEXECDIR")
        if not libexecdir:
            raise RuntimeError(
                f"{type(self).__name__}: DEBASHER_LIBEXECDIR is not set in the "
                "environment, cannot locate debasher_launch_process (only set by "
                "the engine's builtin scheduler when it launches a process)"
            )
        command = [
            os.path.join(libexecdir, "debasher_launch_process"),
            "-d",
            self._program_outdir(),
            "-p",
            self._node_process_name(node),
        ]
        idx = self._node_task_idx(node)
        if idx is not None:
            command += ["-t", str(idx)]
        return command

    def _node_pid_alive(self, node_name):
        """
        True unless the node's own .id file unambiguously shows its PID
        is gone -- the fast path for "definitely gone" (see
        _check_node), never evidence of health by itself. Deliberately
        conservative: no .id file yet (not launched yet) or an
        unreadable one does NOT count as dead here, only an existing,
        readable PID that really doesn't exist any more does.
        """
        try:
            with open(self._node_id_file(node_name)) as f:
                pid = int(f.read().strip())
        except (FileNotFoundError, ValueError):
            return True

        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def _ends_on_close(self, tag):
        """
        A Supervisor reader never ends on CLOSE. A node that closed its
        channel may crash later or be relaunched, and must still be heard;
        whether a node is done for good is decided from its own .finished
        file (see _check_node), and the manual trigger channel is written
        by an external actor that opens, writes and closes per message.
        """
        return False

    # -- subclass extension points --

    def on_node_down(self, node_name):
        """
        Default: relaunch the node through debasher_launch_process, an
        installed engine tool that calls the built-in scheduler's own
        launch function (debasher_builtin_sched::_launch), so a relaunch
        is identical to the original launch: it sets the per-launch
        variables (which .id file to write, which task index) for the
        process being launched and puts it in its own process group.
        Merely re-executing the generated script instead would inherit
        this Supervisor's own values of those variables, so the
        relaunched node would write its PID into the Supervisor's .id
        file, never its own. Overridable for a node that needs something
        non-standard.
        """
        command = self._launch_process_command(node_name)
        # Non-blocking, so the checker thread keeps watching the other
        # nodes; a short-lived thread waits for the launcher itself (it
        # returns as soon as the relaunched process has written its PID
        # file, not when that process ends) to reap it and report a
        # failure to launch.
        proc = subprocess.Popen(command, stdin=subprocess.DEVNULL)
        threading.Thread(
            target=self._reap_launcher,
            args=(node_name, proc),
            name=f"launcher:{node_name}",
            daemon=True,
        ).start()

    def _reap_launcher(self, node_name, proc):
        returncode = proc.wait()
        if returncode != 0:
            self.log.error(
                "launching node %r failed (debasher_launch_process exit code %s)",
                node_name,
                returncode,
            )

    def on_node_permanently_failed(self, node_name):
        """
        Default: escalate in two phases, in a background thread (so the
        checker thread that triggered this keeps running and noticing
        other nodes reaching "done" meanwhile): (1) ask every configured
        TRIGGER_PORT initiator for an ordinary ordered shutdown, which
        cleanly covers whatever part of the graph remains reachable;
        (2) if not every node has resolved within FORCE_STOP_TIMEOUT_SECS
        (the signature of a graph left disconnected by this node's
        death), fall back to `debasher_stop`, an existing, unmodified
        engine tool that ends the whole program regardless of the
        graph's connectivity.
        """
        with self._lock:
            self._active_escalations += 1
        thread = threading.Thread(
            target=self._escalate_shutdown, name=f"escalate:{node_name}"
        )
        thread.start()

    def _escalate_shutdown(self):
        try:
            for port in self.TRIGGER_PORT:
                self._send_interact(port, "shutdown")

            deadline = time.monotonic() + self.FORCE_STOP_TIMEOUT_SECS
            while time.monotonic() < deadline:
                with self._lock:
                    if len(self._done) + len(self._given_up) == len(self.NODE_PORTS):
                        return
                time.sleep(1)

            with self._lock:
                if len(self._done) + len(self._given_up) == len(self.NODE_PORTS):
                    return

            self.log.error(
                "not every node resolved within %ss of the shutdown escalation, "
                "forcing debasher_stop",
                self.FORCE_STOP_TIMEOUT_SECS,
            )
            subprocess.run(["debasher_stop", "-d", self._program_outdir()])
        finally:
            with self._lock:
                self._active_escalations -= 1
            self._maybe_resolve()
