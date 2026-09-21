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
import sys
import os
import json
import logging
import queue
import threading

from debasher_runtime_envelope import (
    TYPE_CLOSE,
    TYPE_HELLO,
    decode_envelope,
    encode_barrier,
    encode_close,
    encode_data,
    encode_hello,
    encode_interact,
)


#####################
# _PortWorker       #
#####################
#
# Thread-per-port plumbing shared by FBPProcess and Supervisor: argv
# parsing into self.opts, a logger, one reader thread per declared input
# port pushing tagged envelopes onto a single shared inbound queue, one
# writer thread per declared output port with its own outbound queue,
# and start_threads()/stop_threads() to manage all of it. Carries no
# barrier, checkpoint or input-log logic: that is FBPProcess-
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
    """
    Writes the whole text (a str, or bytes that are already encoded) to a
    blocking fd, coping with partial writes.
    """
    data = text.encode("utf-8") if isinstance(text, str) else bytes(text)
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
        # Whether the writers say CLOSE when they stop, decided by stop_threads().
        self._close_on_stop = True

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

    def _open_fifos(self):
        """
        Opens the fifo of every declared port that is not open yet, so that
        calling it again does nothing. A fifo keeps what was written to it
        and not yet read only while some process holds it open, and a node
        holds it from the moment it opens it: a class whose startup takes a
        while before its threads can run (FBPProcess restores a checkpoint
        and replays a log) opens its fifos first, so that its neighbors'
        messages wait for it in the fifos even if the neighbors crash
        meanwhile.
        """
        for tag, option_name in self._input_ports().items():
            if tag not in self._reader_fds:
                self._reader_fds[tag] = _open_fifo_reader(self.opts[option_name])
        for tag, option_name in self._output_ports().items():
            if tag not in self._writer_fds:
                self._writer_fds[tag] = _open_fifo_writer(self.opts[option_name])

    def start_threads(self):
        """
        Opens every fifo that is not open yet (see _open_fifos), then starts
        one reader thread per declared input port, one writer thread per
        declared output port, and the brain thread. Nothing here waits for a
        peer: every endpoint holds both ends of its fifo (see
        _open_fifo_reader and _open_fifo_writer), so the channel outlives the
        crash of either process and the processes can start in any order.

        Brain and reader threads are not daemons: this process is meant to
        keep running until explicitly told to stop, and stop_threads() can
        always wake and join them. Writer threads are daemons, because one
        can stay blocked in a write while its peer is down and must never
        keep the process alive.
        """
        self._open_fifos()

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

    def stop_threads(self, timeout=None, close=True):
        """
        Signals every thread to stop and waits for them. A reader blocked
        in read() is woken by a blank line written through its own ghost
        write end (that write is non-blocking, so a full pipe cannot hold
        this up: a reader with a full pipe in front of it is not blocked).
        A writer sends what is already queued, then CLOSE, and ends; one
        that cannot finish because its peer is down and the pipe is full is
        abandoned after `timeout` (WRITER_STOP_TIMEOUT_SECS if none is
        given), and its descriptors are left open for it.

        CLOSE tells the peer that this writer has finished for good, so a
        caller that stops for any other reason passes close=False and the
        writers send nothing after what is queued. A halt is such a reason:
        the node is resumed later, and a peer that had read a CLOSE would
        take it for a finished one.
        """
        self._close_on_stop = close
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

    def _drops_after_close(self, tag):
        """
        Whether the reader of `tag`, once its writer has sent CLOSE, goes on
        reading but drops everything that follows (the default), or delivers
        it as usual. CLOSE says that the writer has finished for good, so
        what a later incarnation of it sends can only repeat what was already
        delivered, or be a fault of its own: it must not reach the node. The
        reader keeps reading instead of ending so that such an incarnation
        never blocks on a full pipe, and so that its thread stays alive,
        which is what the heartbeat checks. Supervisor overrides it: a node
        that closes its channel and is later relaunched must still be heard,
        and it decides whether a node finished for good from the node's own
        .finished file instead.
        """
        return True

    def _closed_at_start(self, tag):
        """
        Whether the reader of `tag` starts already past a CLOSE, that is,
        in the mode in which it drops what its writer sends (see
        _drops_after_close). A node relaunched after its writer had said
        CLOSE knows it from what it recovered, and asks for it here. It has
        no effect on a class that delivers what follows a CLOSE.
        """
        return False

    def _on_arrival(self, tag, envelope, line):
        """
        Called by a reader thread with every envelope that the transport
        does not consume itself (everything but HELLO), in the order in
        which that thread read them, and the only way an item gets onto the
        inbound queue. `line` is the text exactly as it arrived. The base
        class puts (tag, type, payload) on the queue and has no use for the
        text; a subclass overrides this to do something with each item at
        the moment it arrives, before the thread that processes it can see
        it.
        """
        self._inbound_queue.put((tag, envelope.type, envelope.payload))

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
            # Set once the writer has sent CLOSE and this class drops what
            # follows it (see _drops_after_close). From then on the loop only
            # reads: nothing is decoded, logged or queued, so not even a
            # corrupt line can stop it. The first line warns, since a writer
            # that says something after CLOSE is either a new incarnation of
            # it or at fault.
            closed = self._closed_at_start(tag) and self._drops_after_close(tag)
            warned = False
            for line in fifo:
                if self._stopping.is_set():
                    break
                line = line.rstrip("\n")
                if not line:
                    continue

                if closed:
                    if not warned:
                        self.log.warning(
                            "reader for %r: its writer sent something after CLOSE (a new "
                            "incarnation of it?), dropping everything that follows",
                            tag,
                        )
                        warned = True
                    else:
                        self.log.debug("reader for %r dropped a line sent after CLOSE", tag)
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

                self._on_arrival(tag, envelope, line)
                if envelope.type == TYPE_CLOSE and self._drops_after_close(tag):
                    closed = True

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
                if self._close_on_stop:
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
