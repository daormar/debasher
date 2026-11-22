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
