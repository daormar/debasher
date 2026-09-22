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
import signal
import subprocess
import threading
import time

from debasher_runtime_envelope import TYPE_CLOSE, TYPE_INTERACT
from debasher_runtime_transport import _PortWorker, _STOP


#####################
# Supervisor        #
#####################
#
# A class of its own, distinct from FBPProcess: it does not take part in
# the barrier protocol as a business node, so it shares only
# _PortWorker's generic thread-per-port plumbing, none of FBPProcess's
# barrier/checkpoint/input-log logic. Watches a fixed set of nodes
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
        # joining its own thread from inside stop_threads()). Also set
        # directly by a SIGTERM handler (see run() and _on_stop_signal):
        # unlike FBPProcess, nothing else here needs to tell "resolved
        # naturally" apart from "told to stop", so one event covers both.
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
        budget) and no shutdown escalation is still in flight, or until
        told to stop by signal (see _on_stop_signal): a graceful-stop tool
        that finds a Supervisor stops it first, before touching any node
        it watches, precisely so it cannot relaunch one out from under it.
        """
        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGTERM, self._on_stop_signal)

        self.start_threads()
        self._all_resolved.wait()
        self.stop_threads()

    def _on_stop_signal(self, signum, frame):
        """
        The SIGTERM handler run() installs (see FBPProcess's own, same
        reasoning: minimal, no lock touched here, actually stopping
        happens on run()'s own thread once its wait returns).
        """
        self._all_resolved.set()

    def start_threads(self):
        super().start_threads()
        self._checker_thread = threading.Thread(target=self._check_loop, name="checker")
        self._checker_thread.start()

    def stop_threads(self, timeout=None, close=True):
        self._checker_stop.set()
        super().stop_threads(timeout, close)
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
                # trigger) only ever carries INTERACT by design, so a
                # DATA/BARRIER here is a protocol violation, not something
                # to crash the process over.
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
            last_seen = self._last_heartbeat[node_name]
        if already_down:
            # Already declared down and (by default) already being
            # relaunched: don't call on_node_down again for the same
            # outage every tick, only once HEARTBEAT_TIMEOUT_SECS has
            # passed with still no real heartbeat (_on_heartbeat resets
            # last_seen the same way a genuine one would). Without this,
            # a relaunch that itself dies before its first heartbeat
            # would stay "down" forever, never re-declared and never
            # counted against MAX_RELAUNCH_ATTEMPTS.
            if time.time() - last_seen > self.HEARTBEAT_TIMEOUT_SECS:
                with self._lock:
                    self._down.discard(node_name)
                self._declare_down(node_name)
            return

        if not self._node_pid_alive(node_name):
            self._declare_down(node_name)
            return

        if time.time() - last_seen > self.HEARTBEAT_TIMEOUT_SECS:
            self._declare_down(node_name)

    def _declare_down(self, node_name):
        with self._lock:
            if node_name in self._down:
                return
            self._down.add(node_name)
            self._relaunch_attempts[node_name] += 1
            attempts = self._relaunch_attempts[node_name]
            # A fresh grace period starts now, the same reasoning as
            # __init__'s own seeding: the incarnation on_node_down is
            # about to start has HEARTBEAT_TIMEOUT_SECS to send its
            # first heartbeat before _check_node treats it as down
            # again, instead of being stuck "down" forever if it never
            # does.
            self._last_heartbeat[node_name] = time.time()

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

    def _drops_after_close(self, tag):
        """
        A Supervisor reader delivers what follows a CLOSE. A node that closed
        its channel may crash later or be relaunched, and must still be heard;
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
        #
        # stdout/stderr also go to DEVNULL, not just stdin: left alone,
        # Popen has them inherit this Supervisor's own (this process's
        # own launch script pipes them into tee, see
        # debasher_builtin_sched::_execute_funct_plus_postfunct), so the
        # relaunch command, and in turn the resident process it
        # backgrounds, would hold that pipe's write end open for as long
        # as the relaunched node keeps running, long after the
        # Supervisor's own process has actually exited. Found 2026-09-22
        # by a real debasher_exec run: a graceful stop signal (see
        # _on_stop_signal) made the Supervisor's own Python interpreter
        # exit cleanly, but its wrapper script never got past its own
        # `wait` for that pipeline, since tee never saw EOF on a pipe a
        # relaunched node was still holding open; debasher_stop's hard
        # kill never surfaced this, since it always kills the relaunched
        # node too, which closes the leaked fd as a side effect.
        proc = subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
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
