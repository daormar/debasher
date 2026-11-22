from debasher_runtime_lib import FBPProcess

import os
import re
import shlex
import subprocess
import sys
import time


class Acquire(FBPProcess):
    """Runs readfish as a child process and watches its log: progress and
    the phase of the sequencer become events for Report, and a readfish
    that is alive but gives no reads is ended, so that the Supervisor
    relaunches this node and the new incarnation starts a new readfish,
    which connects again."""

    # What observe() takes from the log of readfish reaches process_data
    # under this name
    OBSERVE_PORT = "readfish"
    OBSERVE_INTERVAL_SECS = 1.0

    # One line per batch of reads that readfish decided on, and one per
    # change of phase of the sequencer; a mux scan is a phase in which the
    # silence of readfish is legitimate
    BATCH_LINE = re.compile(r"(\d+)R/[\d.]+s; Avg: .*?; Seq:([\d,]+); Unb:([\d,]+); Pro:([\d,]+)")
    PHASE_LINE = re.compile(r"Protocol phase changed to (PHASE_\w+)")
    SEQUENCING = "PHASE_SEQUENCING"

    def __init__(self):
        super().__init__()
        self.command = self.opts.get("command") or self._default_command()
        self.stall_timeout = float(self.opts.get("stall-timeout-s", "60"))
        self.scan_timeout = float(self.opts.get("scan-timeout-s", "900"))
        self.start_timeout = float(self.opts.get("start-timeout-s", "300"))
        self.max_attempts = int(self.opts.get("max-attempts", "5"))
        self.child = None
        self.log_file = None
        self.partial = ""

    def _default_command(self):
        # The stand-in next to the module, run by the Python of this node
        return f"{shlex.quote(sys.executable)} fake_readfish.py"

    def _resolve_command(self):
        """The arguments of -command, with a relative path that names a file
        next to the module taken from there, as -watchdir and -pfile are:
        the child runs in the output directory of the process, not in the
        directory of the module."""
        module_dir = os.environ.get("DEBASHER_PROCESS_MODULE_DIR", ".")
        argv = []
        for arg in shlex.split(self.command):
            path = os.path.join(module_dir, arg)
            argv.append(path if not os.path.isabs(arg) and "/" not in arg[:1] and os.path.isfile(path) else arg)
        return argv

    def _outdir(self):
        return os.environ.get("DEBASHER_PROCESS_OUTDIR", ".")

    def _path(self, name):
        return os.path.join(self._outdir(), name)

    def _read_count(self, name):
        try:
            with open(self._path(name)) as f:
                return int(f.read().strip() or 0)
        except (FileNotFoundError, ValueError):
            return 0

    def _write_count(self, name, value):
        with open(self._path(name), "w") as f:
            f.write(f"{value}\n")

    # -- the child --

    @staticmethod
    def _start_time_of(pid):
        """The start time of the process `pid` as ps prints it, or None when
        there is no such process; with the pid it tells a process from a
        later one that reuses its pid."""
        try:
            out = subprocess.run(
                ["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True, check=False,
                env={**os.environ, "LC_ALL": "C", "TZ": "UTC0"},
            ).stdout.strip()
        except OSError:
            return None
        return out or None

    def _kill_earlier_child(self):
        # A kill -9 of this node leaves its readfish running: the next
        # incarnation would start a second one on the same device. The file
        # child.pid names the earlier child as pid@start, and it is killed if
        # it is still that process
        try:
            with open(self._path("child.pid")) as f:
                pid, start = f.read().strip().split("@", 1)
        except (FileNotFoundError, ValueError):
            return
        if self._start_time_of(int(pid)) == start:
            self.log.warning("killing the readfish of an earlier incarnation, pid %s", pid)
            try:
                os.kill(int(pid), 9)
            except OSError:
                pass

    def _start_child(self):
        self._kill_earlier_child()
        self.log_path = self._path(f"readfish.{self.incarnation}.log")
        argv = self._resolve_command()
        self.log.info("starting %s, its output in %s", " ".join(argv), self.log_path)
        with open(self.log_path, "w") as out:
            # In the process group of this node, so that what stops or kills
            # the node reaches it too; its working directory is the output
            # directory of the process, where an operator leaves the files
            # that the stand-in obeys
            self.child = subprocess.Popen(
                argv, stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, cwd=self._outdir(),
            )
        with open(self._path("child.pid"), "w") as f:
            f.write(f"{self.child.pid}@{self._start_time_of(self.child.pid) or ''}\n")
        self.log_file = open(self.log_path)
        self.started_at = time.time()

    def _stop_child(self):
        child, self.child = self.child, None
        if child is None or child.poll() is not None:
            return
        child.terminate()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()

    def _new_lines(self):
        data = self.log_file.read()
        if not data:
            return []
        lines = (self.partial + data).split("\n")
        self.partial = lines.pop()
        return lines

    # -- the events --

    def _event(self, kind, **fields):
        return {"kind": kind, "t": time.time(), "incarnation": self.incarnation, **fields}

    def _end(self, kind, reason, **fields):
        """Ends this incarnation: an event, a notice, the attempts counted,
        the child stopped, and an exception that ends the observation
        thread and so the process, which the Supervisor relaunches."""
        if not self.progressed:
            self._write_count("attempts", self.attempts + 1)
        self.set_notice(reason, level="warning")
        self.inject(self._event(kind, reason=reason, **fields))
        self._stop_child()
        raise RuntimeError(reason)

    def _stalled(self, now):
        """The reason the incarnation is stuck, or None while it is not."""
        if not self.progressed:
            silence = now - self.started_at
            if silence > self.start_timeout:
                return f"readfish gave no batch of reads for {silence:.0f} s since its start"
            return None
        if self.phase == self.SEQUENCING:
            silence = now - self.last_progress
            if silence > self.stall_timeout:
                return f"readfish gave no batch of reads for {silence:.0f} s in {self.phase}"
        else:
            # A mux scan takes minutes; only one that never ends is a stall
            silence = now - self.phase_changed
            if silence > self.scan_timeout:
                return f"readfish has been in {self.phase} for {silence:.0f} s"
        return None

    # -- node hooks --

    def process_data(self, port_name, packet):
        # An event of readfish from observe(), or a note written by hand
        # into -notes, which Report records like the events
        if isinstance(packet, dict) and "kind" not in packet:
            packet = {"kind": "note", **packet}
        self.send_data("outevents", packet)

    def capture_node_state(self):
        return {}

    def restore_node_state(self, node_state):
        pass

    def initialize_runtime(self):
        # readfish and its log are the outside world, not node state: each
        # incarnation starts a readfish of its own, which connects anew, as
        # readfish restarted by hand does. The counters that have to outlive
        # an incarnation are files of the output directory of the process
        self.incarnation = self._read_count("launches") + 1
        self._write_count("launches", self.incarnation)
        self.attempts = self._read_count("attempts")
        self.phase = None
        self.progressed = False
        self.last_progress = None
        self.exhausted = False
        # The counters of readfish, as its last batch line gives them
        self.counters = {"seq": 0, "unb": 0, "pro": 0}
        self._start_child()
        self.phase_changed = self.started_at
        self.announce = True
        if any(os.path.basename(arg).startswith("fake_readfish") for arg in shlex.split(self.command)):
            self.set_notice("running the stand-in fake_readfish.py, not readfish: give -command")

    def observe(self):
        if self.announce:
            # From the observation thread, not from initialize_runtime: an
            # input is brought in only by observe()
            self.announce = False
            self.inject(self._event("started", command=self.command, attempts=self.attempts))
        now = time.time()
        batches = reads = 0
        for line in self._new_lines():
            m = self.BATCH_LINE.search(line)
            if m:
                batches += 1
                reads += int(m.group(1))
                self.counters["seq"], self.counters["unb"], self.counters["pro"] = (
                    int(m.group(i).replace(",", "")) for i in (2, 3, 4)
                )
                continue
            m = self.PHASE_LINE.search(line)
            if m:
                self.phase = m.group(1)
                self.phase_changed = now
                self.inject(self._event("phase", phase=self.phase))
        if batches:
            self.last_progress = now
            if not self.progressed:
                self.progressed = True
                if self.phase is None:
                    self.phase = self.SEQUENCING
                if self.attempts or self.exhausted:
                    # Reads again: the relaunches that found nothing are over
                    self.attempts = 0
                    self.exhausted = False
                    self._write_count("attempts", 0)
                    self.clear_notice()
            self.inject(self._event("progress", batches=batches, reads=reads, **self.counters))
        if self.exhausted:
            return
        if self.child.poll() is not None:
            self._end("exited", f"readfish ended with code {self.child.returncode}", exit_code=self.child.returncode)
        reason = self._stalled(now)
        if reason is None:
            return
        if not self.progressed and self.attempts >= self.max_attempts:
            # Relaunching for ever would fix nothing: the sequencer is gone
            # or unreachable. The node stays, alive by choice, with a notice
            # and an event, for an operator to act and relaunch it by hand
            self.exhausted = True
            reason = (
                f"{reason}, after {self.attempts} relaunches with no reads: not relaunching "
                "readfish again; check the sequencer and relaunch this node"
            )
            self.set_notice(reason, level="warning")
            self.inject(self._event("exhausted", reason=reason, attempts=self.attempts))
            return
        self._end("stall", reason, phase=self.phase)

    def run(self):
        # The child ends with the node, whether the node ends by a stall
        # (run() raises), by a stop (run() returns) or by any other error
        try:
            super().run()
        finally:
            self._stop_child()


Acquire().run()
