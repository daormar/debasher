# AUTOMATICALLY GENERATED DEBASHER SCRIPT


webui_readfish_document()
{
    debasher::document_module "Example built with the web UI: a resident program around readfish, the adaptive sampling tool of nanopore sequencing. Acquire runs readfish as a child process and ends it when its stream of reads dies in silence, so that the Supervisor relaunches it; Watch sends each file that the sequencer writes to Launch, which summarizes it with the general program webui_read_lengths; Report joins what readfish says and what the files show in one timeline. Without a sequencer, Acquire runs a stand-in."
}


webui_readfish_shared_dirs()
{
    :
}


webui_readfish_program_type()
{
    debasher::program_type "resident"
}


Sup_document()
{
    debasher::document_process "Watches Acquire, Watch, Launch and Report and relaunches them if they go down."
}


Sup_explain_opts()
{
    debasher::explain_opt "-Acquire_hb" "<string>" "heartbeat channel of Acquire"
    debasher::explain_opt "-outAcquire_initiator" "<string>" "initiator port to Acquire"
    debasher::explain_opt "-Watch_hb" "<string>" "heartbeat channel of Watch"
    debasher::explain_opt "-outWatch_initiator" "<string>" "initiator port to Watch"
    debasher::explain_opt "-Launch_hb" "<string>" "heartbeat channel of Launch"
    debasher::explain_opt "-Report_hb" "<string>" "heartbeat channel of Report"
    debasher::explain_opt "-manual" "<string>" "manual trigger port, written from outside the program"
    debasher::explain_flag "-no-hold-fifos" "do not hold the FIFOs of the business channels"
}


Sup_identify_cmdline_opts()
{
    debasher::opt_is_non_mandatory_cmdline "-no-hold-fifos"
}


Sup_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    debasher::define_opt_from_proc_out "-Acquire_hb" "Acquire" "-outhb" optlist || return 1
    debasher::define_fifo_opt "-outAcquire_initiator" "Sup_Acquire_initiator" optlist --control || return 1
    debasher::define_opt_from_proc_out "-Watch_hb" "Watch" "-outhb" optlist || return 1
    debasher::define_fifo_opt "-outWatch_initiator" "Sup_Watch_initiator" optlist --control || return 1
    debasher::define_opt_from_proc_out "-Launch_hb" "Launch" "-outhb" optlist || return 1
    debasher::define_opt_from_proc_out "-Report_hb" "Report" "-outhb" optlist || return 1
    debasher::define_fifo_opt "-manual" "Sup_manual" optlist --control || return 1
    debasher::define_cmdline_flag_if_given "${cmdline}" "-no-hold-fifos" optlist || return 1

    save_opt_list optlist
}


Sup_heredoc_py()
{
    cat <<'EOF'
from debasher_runtime_lib import Supervisor


class Sup(Supervisor):
    pass


Sup().run()
EOF
}


Acquire_document()
{
    debasher::document_process "Runs readfish (the command of -command; by default the stand-in fake_readfish.py next to this program) as a child process and reads its log: each batch of reads and each change of phase of the sequencer go to Report as events. In the sequencing phase, -stall-timeout-s seconds with no batch is a stall; in a mux scan, only -scan-timeout-s seconds are; a readfish that gives nothing for -start-timeout-s seconds after its start, or that ends, is one too. On a stall the node ends readfish and raises, and the Supervisor relaunches it; after -max-attempts relaunches with no reads at all it stops raising and leaves a notice. Notes written by hand into -notes go to Report like the events."
}


Acquire_explain_opts()
{
    debasher::explain_opt "-command" "<string>" "the command that runs readfish, without --log-file (the stand-in by default)"
    debasher::explain_opt "-stall-timeout-s" "<string>" "seconds without a batch of reads, in the sequencing phase, that make a stall (60 by default)"
    debasher::explain_opt "-scan-timeout-s" "<string>" "seconds in a mux scan or another phase that is not sequencing that make a stall (900 by default)"
    debasher::explain_opt "-start-timeout-s" "<string>" "seconds after the start of readfish without a first batch that make a stall (300 by default)"
    debasher::explain_opt "-max-attempts" "<string>" "relaunches in a row with no reads at all after which the node stops raising and leaves a notice (5 by default)"
    debasher::explain_opt "-notes" "<string>" "notes written from outside the program, one per message"
    debasher::explain_opt "-outevents" "<string>" "the events of readfish and the notes, to Report"
    debasher::explain_opt "-outhb" "<string>" "heartbeat channel to the Supervisor"
    debasher::explain_opt "-control" "<string>" "control port of this initiator"
}


Acquire_identify_cmdline_opts()
{
    debasher::opt_is_non_mandatory_cmdline "-command"
    debasher::opt_is_non_mandatory_cmdline "-stall-timeout-s"
    debasher::opt_is_non_mandatory_cmdline "-scan-timeout-s"
    debasher::opt_is_non_mandatory_cmdline "-start-timeout-s"
    debasher::opt_is_non_mandatory_cmdline "-max-attempts"
}


Acquire_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    debasher::define_cmdline_opt_if_given "${cmdline}" "-command" optlist || return 1
    debasher::define_cmdline_opt_if_given "${cmdline}" "-stall-timeout-s" optlist || return 1
    debasher::define_cmdline_opt_if_given "${cmdline}" "-scan-timeout-s" optlist || return 1
    debasher::define_cmdline_opt_if_given "${cmdline}" "-start-timeout-s" optlist || return 1
    debasher::define_cmdline_opt_if_given "${cmdline}" "-max-attempts" optlist || return 1
    debasher::define_fifo_opt "-notes" "notes" optlist --external || return 1
    debasher::define_fifo_opt "-outevents" "events" optlist || return 1
    debasher::define_fifo_opt "-outhb" "Acquire_hb" optlist || return 1
    debasher::define_opt_from_proc_out "-control" "Sup" "-outAcquire_initiator" optlist || return 1

    save_opt_list optlist
}


Acquire_heredoc_py()
{
    cat <<'EOF'
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
            # Counted from the last batch, or from the return to this phase
            # after a scan, whichever is later: the silence of the scan is
            # not a silence of the sequencing
            silence = now - max(self.last_progress, self.phase_changed)
            if silence > self.stall_timeout:
                return f"readfish gave no batch of reads for {silence:.0f} s in {self.phase}"
        else:
            # A mux scan takes minutes; only one that never ends is a stall
            silence = now - self.phase_changed
            if silence > self.scan_timeout:
                return f"readfish has been in {self.phase} for {silence:.0f} s"
        return None

    # -- node hooks --

    def run(self):
        # The child ends with the node, whether the node ends by a stall
        # (run() raises), by a stop (run() returns) or by any other error
        try:
            super().run()
        finally:
            self._stop_child()

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


Acquire().run()
EOF
}


Watch_document()
{
    debasher::document_process "Watches the directory given by -watchdir, where the sequencer writes its read files, and sends a request for each file once it is complete."
}


Watch_explain_opts()
{
    debasher::explain_opt "-watchdir" "<string>" "directory where the read files arrive, given on the command line"
    debasher::explain_opt "-outrequests" "<string>" "one request for each complete read file"
    debasher::explain_opt "-outhb" "<string>" "heartbeat channel to the Supervisor"
    debasher::explain_opt "-control" "<string>" "control port of this initiator"
}


Watch_identify_cmdline_opts()
{
    debasher::opt_is_cmdline "-watchdir"
}


Watch_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    debasher::define_cmdline_opt "${cmdline}" "-watchdir" optlist || return 1
    debasher::define_fifo_opt "-outrequests" "requests" optlist || return 1
    debasher::define_fifo_opt "-outhb" "Watch_hb" optlist || return 1
    debasher::define_opt_from_proc_out "-control" "Sup" "-outWatch_initiator" optlist || return 1

    save_opt_list optlist
}


Watch_heredoc_py()
{
    cat <<'EOF'
from debasher_runtime_lib import DirectoryWatcher


class Watch(DirectoryWatcher):
    # Every file of the directory counts (PATTERN "*"): the directory is the
    # one where the sequencer writes its read files, such as fast5_pass, and
    # holds nothing else. A file whose name starts with a dot never counts.
    pass


Watch().run()
EOF
}


Launch_document()
{
    debasher::document_process "Runs webui_read_lengths once for each read file, with conda support, so that the first batch run creates the conda environment of its process and the rest find it, and sends a message when each batch run ends."
}


Launch_explain_opts()
{
    debasher::explain_opt "-pfile" "<string>" "the general program to run, next to this program's home directory"
    debasher::explain_opt "-requests" "<string>" "the requests of Watch, one batch run each"
    debasher::explain_opt "-outdone" "<string>" "a message for each batch run that ends"
    debasher::explain_opt "-outhb" "<string>" "heartbeat channel to the Supervisor"
}


Launch_identify_cmdline_opts()
{
    :
}


Launch_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    debasher::define_opt "-pfile" "../webui_read_lengths/webui_read_lengths.sh" optlist || return 1
    debasher::define_opt_from_proc_out "-requests" "Watch" "-outrequests" optlist || return 1
    debasher::define_fifo_opt "-outdone" "done" optlist || return 1
    debasher::define_fifo_opt "-outhb" "Launch_hb" optlist || return 1

    save_opt_list optlist
}


Launch_heredoc_py()
{
    cat <<'EOF'
from debasher_runtime_lib import ProgramLauncher


class Launch(ProgramLauncher):
    pass


Launch().run()
EOF
}


Report_document()
{
    debasher::document_process "Keeps one timeline of the run: the launches, stalls and phases of readfish from the events of Acquire, and the summary of each read file from the batch runs of Launch. It writes it to timeline.json in its output directory, and sends on -outtimeline each incident, each file and a status line every -status-every-s seconds of event time."
}


Report_explain_opts()
{
    debasher::explain_opt "-inevents" "<string>" "the events of Acquire"
    debasher::explain_opt "-indone" "<string>" "the messages of the batch runs that end"
    debasher::explain_opt "-status-every-s" "<string>" "seconds of event time between two status lines (60 by default)"
    debasher::explain_opt "-outtimeline" "<string>" "the incidents, the files and the status lines, read outside the program"
    debasher::explain_opt "-outhb" "<string>" "heartbeat channel to the Supervisor"
}


Report_identify_cmdline_opts()
{
    debasher::opt_is_non_mandatory_cmdline "-status-every-s"
}


Report_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    debasher::define_opt_from_proc_out "-inevents" "Acquire" "-outevents" optlist || return 1
    debasher::define_opt_from_proc_out "-indone" "Launch" "-outdone" optlist || return 1
    debasher::define_cmdline_opt_if_given "${cmdline}" "-status-every-s" optlist || return 1
    debasher::define_fifo_opt "-outtimeline" "timeline" optlist || return 1
    debasher::define_fifo_opt "-outhb" "Report_hb" optlist || return 1

    save_opt_list optlist
}


Report_heredoc_py()
{
    cat <<'EOF'
from debasher_runtime_lib import FBPProcess

import json
import os


class Report(FBPProcess):
    """Joins the two streams of the program in one timeline: what readfish
    says (through Acquire: progress, phases, stalls, relaunches) and what
    the read files show (through Launch: the summary of each batch run).
    The timeline is the state of the node, kept by its checkpoints, and is
    written to timeline.json in its output directory."""

    # The output of the general program that a batch run of Launch runs,
    # inside the run directory
    SUMMARY_PATH = os.path.join("read_lengths", "summary.json")
    # How many incidents the timeline keeps
    MAX_INCIDENTS = 1000

    def __init__(self):
        super().__init__()
        self.status_every = float(self.opts.get("status-every-s", "60"))
        # The node state
        self.state = {
            "incarnations": 0,
            "stalls": 0,
            "exits": 0,
            "exhausted": False,
            "phase": None,
            "last_progress_t": None,
            "totals": {"batches": 0, "reads": 0, "seq": 0, "unb": 0, "pro": 0},
            "incidents": [],
            "files": [],
            "status_t": None,
        }

    def _timeline_path(self):
        return os.path.join(os.environ.get("DEBASHER_PROCESS_OUTDIR", "."), "timeline.json")

    def _write_timeline(self):
        # Rewritten whole from the state, through a rename, so that a replay
        # writes the same file and a reader never sees a half one
        path = self._timeline_path()
        with open(path + ".tmp", "w") as f:
            json.dump(self.state, f, indent=1)
        os.replace(path + ".tmp", path)

    def _emit(self, payload):
        self.send_data("outtimeline", payload)

    def _incident(self, event):
        incidents = self.state["incidents"]
        incidents.append(event)
        del incidents[: -self.MAX_INCIDENTS]
        self._emit(event)
        self._write_timeline()

    def _set_notice_from_state(self):
        s = self.state
        if s["exhausted"]:
            self.set_notice("readfish gives no reads after its relaunches; the sequencer needs attention", level="warning")
        else:
            self.set_notice(
                f"{s['incarnations']} readfish launch(es), {s['stalls']} stall(s), "
                f"{len(s['files'])} file(s) processed"
            )

    def _on_event(self, event):
        kind = event.get("kind")
        s = self.state
        if kind == "progress":
            # Batches and reads add up across incarnations; the counters of
            # readfish (Seq, Unb, Pro) start again with each one, so the
            # latest values are kept
            totals = s["totals"]
            totals["batches"] += event.get("batches", 0)
            totals["reads"] += event.get("reads", 0)
            for key in ("seq", "unb", "pro"):
                totals[key] = event.get(key, totals[key])
            s["last_progress_t"] = event.get("t")
            # A status line every status_every seconds of event time, not of
            # the clock of this node, which a replay does not see
            t = event.get("t")
            if t is not None and (s["status_t"] is None or t - s["status_t"] >= self.status_every):
                s["status_t"] = t
                self._emit({"kind": "status", "t": t, "phase": s["phase"], "incarnation": event.get("incarnation"), **s["totals"]})
                self._write_timeline()
            return
        if kind == "started":
            s["incarnations"] += 1
            s["exhausted"] = False
        elif kind == "stall":
            s["stalls"] += 1
        elif kind == "exited":
            s["exits"] += 1
        elif kind == "exhausted":
            s["exhausted"] = True
        elif kind == "phase":
            s["phase"] = event.get("phase")
        self._incident(event)
        self._set_notice_from_state()

    def _summary_of(self, done):
        """The summary that the batch run of `done` wrote, as a memo in the
        output directory of this process: a run directory may be removed or
        reused later, and a replay has to record what was read the first
        time, so the summary is read from the memo when there is one and
        written to it the first time."""
        memo = os.path.join(os.environ.get("DEBASHER_PROCESS_OUTDIR", "."), "summaries", f"{done['run']}.json")
        try:
            with open(memo) as f:
                return json.load(f)
        except (OSError, ValueError):
            pass
        with open(os.path.join(done["run_dir"], self.SUMMARY_PATH)) as f:
            summary = json.load(f)
        os.makedirs(os.path.dirname(memo), exist_ok=True)
        with open(memo + ".tmp", "w") as f:
            json.dump(summary, f)
        os.replace(memo + ".tmp", memo)
        return summary

    def _on_done(self, done):
        record = {"kind": "file", "run": done.get("run"), "status": done.get("status"), "exit_code": done.get("exit_code")}
        if done.get("status") == "finished":
            try:
                record.update(self._summary_of(done))
            except (OSError, ValueError, KeyError, TypeError) as e:
                record["status"] = "no summary"
                record["error"] = str(e)
        self.state["files"].append(record)
        self._emit(record)
        self._write_timeline()
        self._set_notice_from_state()

    def process_data(self, port_name, packet):
        if not isinstance(packet, dict):
            self.log.warning("dropping a message that is not an object on %s: %r", port_name, packet)
            return
        if port_name == "indone":
            self._on_done(packet)
        else:
            self._on_event(packet)

    def capture_node_state(self):
        # Returned without a copy: the runtime takes one when it captures
        return self.state

    def restore_node_state(self, node_state):
        self.state = node_state
        self._set_notice_from_state()

    def initialize_runtime(self):
        pass


Report().run()
EOF
}


webui_readfish_program()
{
    add_debasher_process "Sup" "cpus=1 mem=256 time=01:00:00" ""
    add_debasher_process "Acquire" "cpus=1 mem=256 time=01:00:00" ""
    add_debasher_process "Watch" "cpus=1 mem=256 time=01:00:00" ""
    add_debasher_process "Launch" "cpus=1 mem=256 time=01:00:00 max_concurrent_runs=2 batch_conda_support=yes" ""
    add_debasher_process "Report" "cpus=1 mem=256 time=01:00:00" ""
}
