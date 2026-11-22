# AUTOMATICALLY GENERATED DEBASHER SCRIPT


webui_live_stats_document()
{
    debasher::document_module "Example built with the web UI: a non-durable resident program, whose node Acquire reads a fake stream of readings and whose node Stats keeps live statistics over them in memory, with the wall clock, as a program that keeps no state worth recovering: a crash or a stop loses the window and the counts, and the node starts again. A Supervisor relaunches a node that goes down."
}


webui_live_stats_shared_dirs()
{
    :
}


webui_live_stats_program_type()
{
    debasher::program_type "resident" "non-durable"
}


Acquire_document()
{
    debasher::document_process "Reads a fake stream of readings, one every -interval-ms, and readings written by hand into -readings, and sends each one to Stats with its source."
}


Acquire_explain_opts()
{
    debasher::explain_opt "-readings" "<string>" "readings written from outside the program, one per message"
    debasher::explain_opt "-interval-ms" "<string>" "milliseconds between two readings of the stream (50 by default)"
    debasher::explain_opt "-outreadings" "<string>" "every reading, to Stats"
    debasher::explain_opt "-outhb" "<string>" "heartbeat channel to the Supervisor"
    debasher::explain_opt "-control" "<string>" "control port of this initiator"
}


Acquire_identify_cmdline_opts()
{
    debasher::opt_is_non_mandatory_cmdline "-interval-ms"
}


Acquire_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    debasher::define_fifo_opt "-readings" "readings" optlist --external || return 1
    debasher::define_cmdline_opt_if_given "${cmdline}" "-interval-ms" optlist || return 1
    debasher::define_fifo_opt "-outreadings" "acquired" optlist || return 1
    debasher::define_fifo_opt "-outhb" "Acquire_hb" optlist || return 1
    debasher::define_opt_from_proc_out "-control" "Sup" "-outAcquire_initiator" optlist || return 1

    save_opt_list optlist
}


Acquire_heredoc_py()
{
    cat <<'EOF'
from debasher_runtime_lib import FBPProcess

import time


class FakeStream:
    """A stand-in for a stream of readings from an instrument: one reading
    every `interval` seconds since the connection opened, with a value that
    follows from its index, so that the stream is the same in every run."""

    # At most this many readings in one poll, so that a long pause does not
    # bring in a burst without limit
    MAX_READINGS_PER_POLL = 500

    def __init__(self, interval):
        self.interval = interval
        self.opened_at = time.monotonic()
        self.given = 0

    def poll(self):
        """The readings that are due since the last poll."""
        due = int((time.monotonic() - self.opened_at) / self.interval) if self.interval else self.given + 1
        due = min(due, self.given + self.MAX_READINGS_PER_POLL)
        readings = [self._make_reading(i) for i in range(self.given, due)]
        self.given = max(self.given, due)
        return readings

    def _make_reading(self, i):
        return {"source": "stream", "t": i, "value": (i * 7919) % 1000 / 10.0}


class Acquire(FBPProcess):
    # What observe() takes from the stream reaches process_data under this
    # name
    OBSERVE_PORT = "stream"
    OBSERVE_INTERVAL_SECS = 0.2

    def __init__(self):
        super().__init__()
        self.interval = float(self.opts.get("interval-ms", "50")) / 1000
        self.stream = None

    def process_data(self, port_name, packet):
        # A reading from the stream, or one written by hand into -readings,
        # which gets a source of its own if it names none
        if isinstance(packet, dict) and "source" not in packet:
            packet = {"source": "hand", **packet}
        self.send_data("outreadings", packet)

    def initialize_runtime(self):
        # Each incarnation opens a connection of its own: the program is
        # non-durable, so nothing of the earlier one is restored
        self.stream = FakeStream(self.interval)

    def observe(self):
        for reading in self.stream.poll():
            self.inject(reading)


Acquire().run()
EOF
}


Stats_document()
{
    debasher::document_process "Keeps, for each source of readings, their count and mean and a window of the last -window-s seconds, in memory and with the wall clock, and sends the running statistics of each reading; every so many readings it sets a notice with the rate of the stream and appends a summary line to summary.jsonl in its output directory, which outlives the node."
}


Stats_explain_opts()
{
    debasher::explain_opt "-inreadings" "<string>" "the readings of Acquire"
    debasher::explain_opt "-window-s" "<string>" "seconds of readings kept in the window (10 by default)"
    debasher::explain_opt "-outstats" "<string>" "the running statistics of each reading, read outside the program"
    debasher::explain_opt "-outhb" "<string>" "heartbeat channel to the Supervisor"
}


Stats_identify_cmdline_opts()
{
    debasher::opt_is_non_mandatory_cmdline "-window-s"
}


Stats_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    debasher::define_opt_from_proc_out "-inreadings" "Acquire" "-outreadings" optlist || return 1
    debasher::define_cmdline_opt_if_given "${cmdline}" "-window-s" optlist || return 1
    debasher::define_fifo_opt "-outstats" "stats" optlist || return 1
    debasher::define_fifo_opt "-outhb" "Stats_hb" optlist || return 1

    save_opt_list optlist
}


Stats_heredoc_py()
{
    cat <<'EOF'
from debasher_runtime_lib import FBPProcess

import collections
import json
import os
import time


class Stats(FBPProcess):
    # A notice and a summary line every so many readings of the stream
    NOTICE_EVERY = 100

    def __init__(self):
        super().__init__()
        self.window_secs = float(self.opts.get("window-s", "10"))
        # The state of the node, in memory only: the program is non-durable,
        # so a crash or a stop loses it and the node starts again from here.
        # Per source: the count and the sum of the readings, and the window
        # of the last ones with the time at which each arrived
        self.counts = {}
        self.sums = {}
        self.windows = {}

    def _summary_path(self):
        # The output directory of the process outlives the node, unlike its
        # state; the engine keeps it across launches
        return os.path.join(os.environ.get("DEBASHER_PROCESS_OUTDIR", "."), "summary.jsonl")

    def _window_stats(self, source, now):
        """The readings of `source` in the last window_secs, and their rate
        per second and mean; the clock is fine here, since nothing is
        replayed in a non-durable program."""
        window = self.windows[source]
        while window and now - window[0][0] > self.window_secs:
            window.popleft()
        count = len(window)
        mean = round(sum(value for _, value in window) / count, 3) if count else None
        return count, round(count / self.window_secs, 3), mean

    def process_data(self, port_name, packet):
        if not isinstance(packet, dict) or not isinstance(packet.get("value"), (int, float)):
            self.log.warning("dropping a reading with no numeric value: %r", packet)
            return
        source = str(packet.get("source", "hand"))
        value = packet["value"]
        now = time.monotonic()
        self.counts[source] = self.counts.get(source, 0) + 1
        self.sums[source] = self.sums.get(source, 0) + value
        self.windows.setdefault(source, collections.deque()).append((now, value))
        self.send_data(
            "outstats",
            {
                "source": source,
                "value": value,
                "count": self.counts[source],
                "mean": round(self.sums[source] / self.counts[source], 3),
            },
        )
        if source == "stream" and self.counts[source] % self.NOTICE_EVERY == 0:
            window_count, rate, window_mean = self._window_stats(source, now)
            self.set_notice(
                f"stream: {self.counts[source]} readings since this incarnation started, "
                f"{window_count} in the last {self.window_secs:g} s ({rate}/s), mean {window_mean}"
            )
            with open(self._summary_path(), "a") as f:
                f.write(json.dumps({
                    "at": time.time(),
                    "count": self.counts[source],
                    "window_count": window_count,
                    "rate_per_s": rate,
                    "window_mean": window_mean,
                }) + "\n")

    def initialize_runtime(self):
        pass


Stats().run()
EOF
}


Sup_document()
{
    debasher::document_process "Watches Acquire and Stats and relaunches them, with their initial state, if they go down."
}


Sup_explain_opts()
{
    debasher::explain_opt "-Acquire_hb" "<string>" "heartbeat channel of Acquire"
    debasher::explain_opt "-outAcquire_initiator" "<string>" "initiator port to Acquire"
    debasher::explain_opt "-Stats_hb" "<string>" "heartbeat channel of Stats"
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
    debasher::define_opt_from_proc_out "-Stats_hb" "Stats" "-outhb" optlist || return 1
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


webui_live_stats_program()
{
    add_debasher_process "Acquire" "cpus=1 mem=256 time=01:00:00" ""
    add_debasher_process "Stats" "cpus=1 mem=256 time=01:00:00 inbound_queue_max_mb=4" ""
    add_debasher_process "Sup" "cpus=1 mem=256 time=01:00:00" ""
}
