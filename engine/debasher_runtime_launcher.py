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
import json
import os
import subprocess
import time
import uuid

from debasher_runtime_fbp import FBPProcess


#####################
# ProgramLauncher   #
#####################
#
# A node that launches a general program, or a single process of a module,
# once for each request it receives, each in a run directory of its own (see
# "ProgramLauncher: batch runs from a node" in doc/design_doc_resident.md).
# process_data only registers a batch run; the node's observe() launches the
# registered ones from what their run directories say, so that the queue is
# on disk and a relaunched node finds it as it was, and brings in the end of
# each one as an input.

# The files a launcher node keeps in a run directory
_LAUNCH_FILE = "launch.json"
_PID_FILE = "launcher.pid"
_EXIT_CODE_FILE = "exit_code"
_NOTIFIED_FILE = "notified"
_LOG_FILE = "launcher.log"

# The exit codes of debasher_status (see DEBASHER_PROGRAM_*_EXIT_CODE in
# engine/debasher_lib.sh) that the state of a batch run looks for: every
# process finished, and some in progress. Any other means that the program
# did not finish.
_PROGRAM_FINISHED = 0
_PROGRAM_IN_PROGRESS = 2

# The directory, in the output directory of its process, where a launcher
# node keeps its own bookkeeping: the identifier of its life and the list of
# its registrations. Its name starts with a dot, which no run directory may,
# so that the two never clash.
_BOOKKEEPING_DIR = ".launcher"

# The options of the process, without their dash, that set up a launcher
# node: the general program (required), the process of it to launch alone,
# and the runs root, an absolute path.
_PFILE_OPTION = "pfile"
_PROCESS_OPTION = "process"
_RUNS_ROOT_OPTION = "runsdir"

# The options that debasher_exec reads itself (see read_pars in
# engine/debasher_exec.sh), which a request may not give: they follow
# --pfile, --outdir and --sched on its command line, and the last one
# given wins
_DEBASHER_EXEC_OPTIONS = frozenset({
    "--help", "--version", "--pfile", "--outdir", "--sched",
    "--builtinsched-cpus", "--builtinsched-mem", "--builtinsched-oneshot",
    "--builtinsched-debug", "--dflt-nodes", "--dflt-throttle",
    "--rerun-outdated-procs", "--conda-support", "--docker-support",
    "--gen-proc-graph", "--show-cmdline-opts", "--check-proc-opts",
    "--validate", "--debug", "--wait",
})


def _write_json_atomically(path, obj):
    """Writes `obj` to `path` through a temporary file renamed into place, so
    that a reader sees the old content or the new one, never half of it."""
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w") as f:
        json.dump(obj, f)
    os.replace(tmp_path, path)


def _read_json(path):
    with open(path) as f:
        return json.load(f)


def _pid_start_time(pid):
    """
    The start time of the process `pid` as the engine records it for a task
    of the built-in scheduler (see debasher::_builtin_sched_pid_start_time in
    engine/debasher_lib_sched_builtin.sh): what "ps -o lstart=" gives with
    the locale and the time zone fixed, so that whoever reads it gets the
    same text, its blanks turned into "_". None when there is no such
    process, or no ps to ask.
    """
    try:
        result = subprocess.run(
            ["ps", "-o", "lstart=", "-p", str(pid)],
            env={**os.environ, "LC_ALL": "C", "TZ": "UTC0"},
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    words = result.stdout.split()
    if result.returncode != 0 or not words:
        return None
    return "_".join(words)


def _launch_id(pid):
    """
    What launcher.pid keeps of the shell of a batch run with process id
    `pid`: "<pid>@<start time>". A process id alone does not name the shell
    for good: once it has ended, the system may give the same id to another
    process, which would then be taken for a shell that still runs, and the
    batch run would never end. Without ps to ask, the process id alone; a
    shell that has already ended gets an empty start time, and never runs.
    """
    start = _pid_start_time(pid)
    if start is not None:
        return f"{pid}@{start}"
    return f"{pid}" if _pid_exists(pid) else f"{pid}@"


def _pid_exists(pid):
    """Whether a process with id `pid` exists that this user can signal: a
    process of another user is never the shell of a batch run."""
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    return True


def _shell_alive(launch_id):
    """
    Whether the shell that `launch_id` (see _launch_id) names still runs: a
    process with its id exists, this user can signal it, and, when the id has
    a start time, it started at that time. A start time that cannot be read
    now, with no ps to ask, leaves the process id alone to decide, as does an
    id without one, as an earlier launch wrote it.
    """
    pid_text, has_start, recorded = launch_id.partition("@")
    pid = int(pid_text)
    if not _pid_exists(pid):
        return False
    if not has_start:
        return True
    if not recorded:
        return False
    current = _pid_start_time(pid)
    return current is None or current == recorded


def _read_launch_id(path):
    """The id in launcher.pid (see _launch_id), or None when there is none,
    or none that gives a process id."""
    try:
        with open(path) as f:
            launch_id = f.read().strip()
        int(launch_id.partition("@")[0])
    except (FileNotFoundError, ValueError):
        return None
    return launch_id


def _read_exit_code(run_dir):
    try:
        with open(os.path.join(run_dir, _EXIT_CODE_FILE)) as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return None


def _registrations_dir_of(process_outdir):
    """Where a launcher node lists its registrations, in the output directory
    of its process."""
    return os.path.join(process_outdir, _BOOKKEEPING_DIR, "registrations")


def _read_registrations(registrations_dir):
    """The batch runs registered in `registrations_dir`, (position, run), in
    the order of their positions; none if it does not exist."""
    try:
        names = os.listdir(registrations_dir)
    except FileNotFoundError:
        return []
    registrations = []
    for name in names:
        if not name.endswith(".json"):
            continue
        try:
            pos = int(name[: -len(".json")])
            run = _read_json(os.path.join(registrations_dir, name))["run"]
        except (ValueError, KeyError, OSError):
            continue
        registrations.append((pos, run))
    return sorted(registrations)


def _read_launch_pos(run_dir):
    """The position of the request that wrote the launch.json of `run_dir`,
    or None when there is no launch.json."""
    try:
        return _read_json(os.path.join(run_dir, _LAUNCH_FILE)).get("pos")
    except FileNotFoundError:
        return None


def _batch_run_state(run_dir, single_process, program_status):
    """
    The state of the batch run of `run_dir`, from what the directory holds
    alone, so that the node that launched it, a relaunched node and a tool
    outside the node (debasher_inspect_resident) find the same one. Returns
    (state, exit code): ("registered", None), never launched; ("running",
    None); ("finished", 0) or ("failed", code), once it has ended, whether
    its exit code is already in `exit_code` or follows from what
    debasher_status says; or ("stopped", None), stopped before it ended
    together with the shell that ran it, and to be launched again.

    `single_process` is whether the batch run is a single process, run with
    debasher_exec_process, which has nothing to resume from.
    `program_status(run_dir)` is the exit code of debasher_status on the
    directory, or None if the caller does not ask it now, which counts as
    in progress.

    The PID of the shell is read before its exit code: a shell writes it
    before it ends, so one found gone had written it already, and one that
    has ended but not yet been waited for, whose PID still shows as alive,
    is never taken for a running one once its exit code is there.
    """
    launch_id = _read_launch_id(os.path.join(run_dir, _PID_FILE))
    alive = launch_id is not None and _shell_alive(launch_id)
    exit_code = _read_exit_code(run_dir)
    if exit_code is not None:
        return ("finished", 0) if exit_code == 0 else ("failed", exit_code)
    if launch_id is None:
        return ("registered", None)
    if alive:
        return ("running", None)
    if single_process:
        return ("stopped", None)
    return _state_from_program_status(program_status(run_dir))


def _state_from_program_status(status):
    """
    The state of a batch run whose debasher_exec is gone without leaving
    its exit code, from the exit code of debasher_status on its run
    directory (None when not asked, which counts as in progress): running
    while something of the program is in progress, finished if everything
    finished, and else stopped, to be launched again.
    """
    if status is None or status == _PROGRAM_IN_PROGRESS:
        return ("running", None)
    if status == _PROGRAM_FINISHED:
        return ("finished", 0)
    return ("stopped", None)


def program_status(debasher_status, run_dir):
    """The exit code of `debasher_status` (the path of the tool) on a run
    directory."""
    result = subprocess.run(
        [debasher_status, "-d", run_dir],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode


class ProgramLauncher(FBPProcess):
    """
    A node that launches a general program once for each request that it
    receives, each in a run directory of its own, and can tell a node
    downstream when each of those batch runs ends.

    Three options of the process set it up. -pfile, required, names the
    general program to launch. A relative name is looked for as a module
    that the module declaring the node loads: in the directory of that
    module, then in the directories of DEBASHER_MOD_DIR. An absolute one is
    accepted with a warning. -process names a process of that program to
    launch alone, with debasher_exec_process, instead of the whole program.
    -runsdir, an absolute path, is where the run directories go; without
    it, they go in the output directory of the process. -pfile is a plain
    option (define_opt, or define_cmdline_opt for a value that the command
    line gives), never a file option, so that the engine leaves a relative
    name as it is. A module that always launches the same program fixes
    -pfile in the define_opts of its process.

    Every input port that carries data is a port of requests. A request is
    a JSON object with two optional fields: `opts`, the options of the
    general program (names with their leading dash, values as strings),
    and `run`, the name of its run directory, a relative path none of whose
    parts is empty or starts with a dot:
    `{"opts": {"-bam": "/data/s17.bam"}, "run": "s17"}`. Without `opts`,
    the program is launched with no options; without `run`, the run
    directory is named after the position of the request. Other fields are
    ignored. A request that does not follow this, that gives an option
    that debasher_exec reads itself (those of debasher_exec --help, such as
    --outdir, --sched, --wait or --debug), as a name or as a value, or
    whose run
    directory belongs to another request, is logged as an error and
    dropped.

    If the node has an output port DONE_PORT, observe() brings in the end
    of every batch run under the name RUNS_DONE_PORT (its observe port,
    which is not a fifo), and the node sends on DONE_PORT a message for
    each, `{"run": ..., "run_dir": ..., "status": ..., "exit_code": ...}`,
    with `run_dir` the absolute path of the run directory, and `status`
    "finished" for an exit code of 0 and "failed" for any other.

    A launcher node cannot be a task of an array process.
    """

    RUNS_DONE_PORT = "runs_done"
    #: The output port on which the end of each batch run is sent, if the
    #: node has it.
    DONE_PORT = "outdone"
    _RUNTIME_CLASS = "ProgramLauncher"
    #: How many batch runs run at a time, a positive whole number, and so,
    #: under Slurm, how many debasher_exec wait at once on the machine of the
    #: node. A program sets it for a process in its computational
    #: specifications, `max_concurrent_runs`, which the engine checks when it
    #: loads the program; the node refuses to start with any other value, in
    #: the specifications or in the class body.
    MAX_CONCURRENT_RUNS = 1
    #: The scheduler the batch runs use, given to debasher_exec as `--sched`:
    #: the built-in one by default, as for the resident program itself, so
    #: that the batch runs do not depend on the scheduler a machine would
    #: pick on its own. A program sets it for a process in its computational
    #: specifications, `batch_sched` (BUILTIN or SLURM). Under SLURM the node
    #: also gives debasher_exec `--wait`, so that it waits for the jobs, alive
    #: on the machine of the node, and its exit code is the end of the run.
    BATCH_SCHED = "BUILTIN"
    #: How often, at most, in seconds, observe() asks debasher_status how a
    #: batch run is going, for a batch run whose shell is gone without its
    #: exit code, as after a restart of the machine (OBSERVE_INTERVAL_SECS is
    #: how often it looks at the run directories).
    STATUS_CHECK_INTERVAL_SECS = 5.0

    _COMP_SPEC_ATTRS = {
        **FBPProcess._COMP_SPEC_ATTRS,
        "max_concurrent_runs": ("MAX_CONCURRENT_RUNS", 1),
        "batch_sched": ("BATCH_SCHED", None),
    }

    def __init__(self, argv=None, opts=None):
        super().__init__(argv, opts)
        pfile = self.opts.get(_PFILE_OPTION)
        if not pfile:
            raise ValueError(
                f"{type(self).__name__}: the general program to launch is not set: the "
                f"process has no option -{_PFILE_OPTION}, or an empty one: give it the general "
                "program as its value (in the define_opts of the process), or define it as a "
                "command line option"
            )
        self._pfile = self._find_pfile(pfile)
        # None launches the whole program
        self._process = self.opts.get(_PROCESS_OPTION) or None
        # The tasks of an array would share the bookkeeping of the node
        if self._get_task_idx() is not None:
            raise ValueError(f"{type(self).__name__}: a launcher node cannot be a task of an array process")
        # A count of batch runs: 0.5 would let no batch run start. It comes
        # as a float from the computational specifications
        count = self.MAX_CONCURRENT_RUNS
        if not (isinstance(count, (int, float)) and float(count).is_integer() and count >= 1):
            raise ValueError(
                f"{type(self).__name__}: max_concurrent_runs, {count!r}, is not a positive whole "
                "number: set the computational specification max_concurrent_runs, or "
                "MAX_CONCURRENT_RUNS in the class body, to 1 or more"
            )
        self.MAX_CONCURRENT_RUNS = int(self.MAX_CONCURRENT_RUNS)
        runs_root = self.opts.get(_RUNS_ROOT_OPTION)
        if runs_root and not os.path.isabs(runs_root):
            raise ValueError(
                f"{type(self).__name__}: the runs root given by -{_RUNS_ROOT_OPTION}, "
                f"{runs_root}, is not an absolute path"
            )
        # The node state: the positions of the requests whose batch run has
        # had its end announced on DONE_PORT, so that an end reported twice
        # is announced once.
        self._announced = set()
        self._life_id = None
        # The batch runs this incarnation launched: run directory -> Popen of
        # its shell, waited for once it ends so that none is left a zombie.
        self._children = {}
        # When debasher_status was last asked about a run directory, to ask
        # at most once every STATUS_CHECK_INTERVAL_SECS.
        self._status_checked_at = {}
        # The registered batch runs whose launch.json is gone, already
        # logged by this incarnation, so that each is logged once.
        self._missing_runs = set()

    # -- paths --

    def _find_pfile(self, pfile):
        """
        The general program `pfile` as an absolute path. Raises ValueError
        when it is not found, and RuntimeError when the environment lacks
        what the search needs.
        """
        # Accepted, but it ties the program to one machine
        if os.path.isabs(pfile):
            self.log.warning(
                "the general program uses an absolute path (%s). This program is not "
                "portable across machines",
                pfile,
            )
            if not os.path.isfile(pfile):
                raise ValueError(f"{type(self).__name__}: the general program {pfile} is not a file")
            return pfile
        module_dir = os.environ.get("DEBASHER_PROCESS_MODULE_DIR")
        if not module_dir:
            raise RuntimeError(
                f"{type(self).__name__}: DEBASHER_PROCESS_MODULE_DIR is not set in the "
                "environment, cannot resolve the general program against the directory "
                "of the module (only set by the engine's builtin scheduler when it "
                "launches a process)"
            )
        # The engine's own search, which looks in the current directory and
        # then in DEBASHER_MOD_DIR: run from the directory of the module, it
        # finds the program as that module would find a module it loads
        result = subprocess.run(
            [self._libexec_tool("debasher_resolve_pfile"), pfile],
            cwd=module_dir,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise ValueError(
                f"{type(self).__name__}: the general program {pfile} is not a file in the "
                f"directory of the module nor in DEBASHER_MOD_DIR: {result.stderr.strip()}"
            )
        return result.stdout.strip()

    def _outdir(self):
        outdir = os.environ.get("DEBASHER_PROCESS_OUTDIR")
        if not outdir:
            raise RuntimeError(
                f"{type(self).__name__}: DEBASHER_PROCESS_OUTDIR is not set in the environment, "
                "cannot locate the output directory of this process (only set by the engine's "
                "builtin scheduler when it launches a process)"
            )
        return outdir

    def _runs_root(self):
        """The absolute path under which the run directories go: the option
        -runsdir, else the output directory of the process."""
        return self.opts.get(_RUNS_ROOT_OPTION) or self._outdir()

    def _bookkeeping_path(self, *names):
        return os.path.join(self._outdir(), _BOOKKEEPING_DIR, *names)

    def _get_node_info_extra(self):
        """What debasher_inspect_resident needs to find the batch runs of
        the node and tell their states."""
        return {
            "launcher": {
                "runs_root": self._runs_root(),
                "process": self._process,
            }
        }

    def _registrations_dir(self):
        return _registrations_dir_of(self._outdir())

    def _run_dir(self, run):
        return os.path.join(self._runs_root(), run)

    def _find_wiring_problem(self):
        if not [port for port in self.INPUT_PORTS if port not in self.CONTROL_PORTS]:
            return (
                "no input port: the node never receives a request, so it never launches "
                "a batch run (add an input option, such as -requests)"
            )
        return None

    # -- node hooks --

    def initialize_runtime(self):
        """
        Reads the identifier of this life of the node, or creates it the
        first time the node starts in a life. It is kept in a file, not in
        the node state: a node that crashed before its first checkpoint would
        otherwise make up another one in its replay.
        """
        os.makedirs(self._registrations_dir(), exist_ok=True)
        path = self._bookkeeping_path("life_id")
        try:
            with open(path) as f:
                self._life_id = f.read().strip()
        except FileNotFoundError:
            self._life_id = None
        if not self._life_id:
            self._life_id = uuid.uuid4().hex
            tmp_path = f"{path}.tmp"
            with open(tmp_path, "w") as f:
                f.write(self._life_id + "\n")
            os.replace(tmp_path, path)

    def capture_node_state(self):
        return {"announced": sorted(self._announced)}

    def restore_node_state(self, node_state):
        self._announced = set(node_state["announced"])

    def process_data(self, port_name, packet):
        if port_name == self.RUNS_DONE_PORT:
            self._on_run_ended(packet)
        else:
            self._register(packet)

    # -- registration --

    def _request_error(self, packet):
        """What is wrong with a request, or None if nothing is."""
        if not isinstance(packet, dict):
            return "a request is a JSON object"
        opts = packet.get("opts", {})
        if not isinstance(opts, dict):
            return "opts is not a JSON object"
        for name, value in opts.items():
            if not isinstance(name, str) or not name.startswith("-"):
                return f"option {name!r} does not start with a dash"
            if name in _DEBASHER_EXEC_OPTIONS:
                return (
                    f"option {name!r} is an option of debasher_exec, which the launcher runs "
                    "itself, not of the general program: remove it from opts"
                )
            if not isinstance(value, str):
                return f"the value of option {name!r} is not a string"
            # debasher_exec reads its arguments one by one, so it would take
            # such a value for its own option
            if value in _DEBASHER_EXEC_OPTIONS:
                return (
                    f"the value of option {name!r} is an option of debasher_exec, which would "
                    "take it for its own: give another value"
                )
        run = packet.get("run")
        if run is not None:
            if not isinstance(run, str) or not run:
                return "run is not a non-empty string"
            parts = run.split("/")
            if run.startswith("/") or any(part in ("", ".", "..") for part in parts):
                return f"run {run!r} is not a relative path of plain names"
            if any(part.startswith(".") for part in parts):
                return f"run {run!r} has a name starting with a dot"
        return None

    def _register(self, packet):
        """
        Registers the batch run that a request asks for: launch.json in its
        run directory, and the registration in the node's list. A run
        directory belongs to the request that registered it; a request of the
        same life at the same position of the input log is that request,
        processed again by a replay, and any other is dropped. Both writes
        are idempotent, so a replay writes the same content again.
        """
        error = self._request_error(packet)
        if error is not None:
            self.log.error("dropping the request at position %s: %s", self._current_pos, error)
            return
        pos = self._current_pos
        run = packet.get("run") or str(pos)
        run_dir = self._run_dir(run)
        record = {"life_id": self._life_id, "pos": pos, "opts": packet.get("opts", {})}

        launch_path = os.path.join(run_dir, _LAUNCH_FILE)
        try:
            owner = _read_json(launch_path)
        except FileNotFoundError:
            owner = None
        if owner is not None and (owner.get("life_id"), owner.get("pos")) != (self._life_id, pos):
            self.log.error(
                "dropping the request at position %s: run directory %s belongs to another request",
                pos,
                run_dir,
            )
            return
        os.makedirs(run_dir, exist_ok=True)
        _write_json_atomically(launch_path, record)
        _write_json_atomically(os.path.join(self._registrations_dir(), f"{pos}.json"), {"run": run})
        self.observe_now()

    # -- end of a batch run --

    def _on_run_ended(self, packet):
        """
        Announces on DONE_PORT the end of a batch run that observe()
        brought in: `packet` is what _report_end gave inject(),
        {"run": <name of the run>, "pos": <position of its request>,
        "exit_code": <int>}, as the input log gives it back, live or in a
        replay. Sends {"run", "run_dir", "status", "exit_code"} once for
        each request; drops, with an error, a packet without run or
        position.
        """
        run = packet.get("run") if isinstance(packet, dict) else None
        pos = packet.get("pos") if isinstance(packet, dict) else None
        # Only a hand-written record lacks them: _report_end gives both
        if run is None or not isinstance(pos, int):
            self.log.error("dropping an end of a batch run with no run or position: %r", packet)
            return
        # The same end brought in twice, by a node that went down between
        # inject() and `notified`, and the replay of both, are announced
        # once. By the position of the request, not by the name of the
        # run: a run directory removed by hand may be named again by a
        # later request
        if pos in self._announced:
            return
        self._announced.add(pos)
        # observe() brings ends in only with DONE_PORT, but a log written
        # while the node had the port may be replayed after it lost it
        if self.DONE_PORT in self.OUTPUT_PORTS:
            exit_code = packet.get("exit_code")
            status = "finished" if exit_code == 0 else "failed"
            self.send_data(
                self.DONE_PORT,
                {"run": run, "run_dir": self._run_dir(run), "status": status, "exit_code": exit_code},
            )

    # -- the observation of the batch runs --

    def _observe_port(self):
        """RUNS_DONE_PORT if the node has DONE_PORT to send done messages
        on, so that observe() brings in the end of each batch run; None
        otherwise, and observe() only launches."""
        return self.RUNS_DONE_PORT if self.DONE_PORT in self.OUTPUT_PORTS else None

    def observe(self):
        self._check_runs()

    def _registrations(self):
        """The registered batch runs, (position, run), in the order of their
        positions."""
        return _read_registrations(self._registrations_dir())

    def _check_runs(self):
        """
        One pass over the registered batch runs: collects the exit codes of
        those that ended, reports their ends, and launches what the free
        slots allow, in the order of the positions.
        """
        self._reap_children()
        running = 0
        to_launch = []
        for pos, run in self._registrations():
            run_dir = self._run_dir(run)
            launch_pos = _read_launch_pos(run_dir)
            # The node writes launch.json before the registration, so only a
            # change by hand under the runs root leaves it missing: the
            # batch run is skipped, not launched without its options
            if launch_pos is None:
                if run not in self._missing_runs:
                    self._missing_runs.add(run)
                    self.log.error("skipping the batch run %s: its run directory %s has no %s", run, run_dir, _LAUNCH_FILE)
                continue
            # A later request registered the same run directory again, once
            # it was removed: the directory is that request's batch run
            if launch_pos != pos:
                continue
            state, exit_code = _batch_run_state(run_dir, self._process is not None, self._program_status)
            if state in ("finished", "failed"):
                if not os.path.exists(os.path.join(run_dir, _EXIT_CODE_FILE)):
                    self._end_run(run_dir, exit_code)
                self._report_end(run, run_dir, pos)
            elif state == "running":
                running += 1
            else:
                to_launch.append(run_dir)
        for run_dir in to_launch:
            if running >= self.MAX_CONCURRENT_RUNS:
                break
            self._launch(run_dir)
            running += 1

    def _reap_children(self):
        """
        Waits for the shells of the batch runs that this incarnation launched
        and that have ended, so that none is left a zombie. How a batch run
        ended is not learned here: its shell wrote it into the run directory
        before it ended (see _batch_run_state).
        """
        for run_dir, child in list(self._children.items()):
            if child.poll() is not None:
                del self._children[run_dir]

    def _program_status(self, run_dir):
        """
        The exit code of debasher_status on a run directory, asked at most
        once every STATUS_CHECK_INTERVAL_SECS for each; None when it was
        asked more recently than that, which _batch_run_state counts as in
        progress.
        """
        now = time.monotonic()
        last = self._status_checked_at.get(run_dir)
        if last is not None and now - last < self.STATUS_CHECK_INTERVAL_SECS:
            return None
        self._status_checked_at[run_dir] = now
        return program_status(self._tool("debasher_status"), run_dir)

    @staticmethod
    def _end_run(run_dir, exit_code):
        tmp_path = os.path.join(run_dir, f"{_EXIT_CODE_FILE}.tmp")
        with open(tmp_path, "w") as f:
            f.write(f"{exit_code}\n")
        os.replace(tmp_path, os.path.join(run_dir, _EXIT_CODE_FILE))

    def _tool(self, name):
        bindir = os.environ.get("DEBASHER_BINDIR")
        if not bindir:
            raise RuntimeError(
                f"{type(self).__name__}: DEBASHER_BINDIR is not set in the environment, "
                f"cannot locate {name} (only set by the engine's builtin scheduler when it "
                "launches a process)"
            )
        return os.path.join(bindir, name)

    def _libexec_tool(self, name):
        libexecdir = os.environ.get("DEBASHER_LIBEXECDIR")
        if not libexecdir:
            raise RuntimeError(
                f"{type(self).__name__}: DEBASHER_LIBEXECDIR is not set in the environment, "
                f"cannot locate {name} (only set by the engine's builtin scheduler when it "
                "launches a process)"
            )
        return os.path.join(libexecdir, name)

    # The shell commands that run a batch run and write its exit code into
    # its run directory, $1, through a temporary file renamed into place,
    # before the shell ends: only the parent of a process learns its exit
    # code, and written there it outlives a crash of the node, and any
    # process can read it (see _batch_run_state). The exit code is the end
    # of the batch run, since debasher_exec waits for its program, and a
    # single process ends with its process.
    _RECORD_EXIT_CODE = (
        'dir=$1; shift; "$@"; code=$?; '
        'echo "$code" > "$dir/exit_code.tmp" && mv "$dir/exit_code.tmp" "$dir/exit_code"'
    )

    def _launch(self, run_dir):
        """
        Launches the batch run of a run directory, with the options of its
        request, in a session of its own, so that it outlives a crash of the
        node and a stop of the resident program: the program with
        debasher_exec, which run again on a directory skips the processes
        that had finished, or, with -process, that process alone with
        debasher_exec_process, from the run directory.
        """
        record = _read_json(os.path.join(run_dir, _LAUNCH_FILE))
        opts = []
        for name, value in record.get("opts", {}).items():
            opts += [name, value]
        if self._process is None:
            # Under the built-in scheduler debasher_exec waits for the
            # program on its own; under Slurm it only does with --wait
            wait = ["--wait"] if self.BATCH_SCHED == "SLURM" else []
            args = [
                "/bin/sh",
                "-c",
                self._RECORD_EXIT_CODE,
                "debasher_launcher",
                run_dir,
                self._tool("debasher_exec"),
                "--pfile",
                self._pfile,
                "--outdir",
                run_dir,
                "--sched",
                self.BATCH_SCHED,
                *wait,
                *opts,
            ]
        else:
            args = [
                "/bin/sh",
                "-c",
                self._RECORD_EXIT_CODE,
                "debasher_launcher",
                run_dir,
                self._tool("debasher_exec_process"),
                self._pfile,
                self._process,
                "--",
                *opts,
            ]
        with open(os.path.join(run_dir, _LOG_FILE), "a") as log_file:
            child = subprocess.Popen(
                args,
                cwd=run_dir,
                stdin=subprocess.DEVNULL,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        self._children[run_dir] = child
        tmp_path = os.path.join(run_dir, f"{_PID_FILE}.tmp")
        with open(tmp_path, "w") as f:
            f.write(f"{_launch_id(child.pid)}\n")
        os.replace(tmp_path, os.path.join(run_dir, _PID_FILE))
        self.log.info("launched the batch run in %s (pid %s)", run_dir, child.pid)

    def _report_end(self, run, run_dir, pos):
        """
        Brings the end of a batch run into the node (inject), and only then,
        once it is logged, marks the run directory as notified, so that a
        crash in between reports it again, and never loses it. A node without
        DONE_PORT reports nothing.
        """
        notified = os.path.join(run_dir, _NOTIFIED_FILE)
        if os.path.exists(notified) or self._observe_port() is None:
            return
        with open(os.path.join(run_dir, _EXIT_CODE_FILE)) as f:
            exit_code = int(f.read().strip())
        self.inject({"run": run, "pos": pos, "exit_code": exit_code})
        with open(notified, "w"):
            pass
