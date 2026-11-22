# AUTOMATICALLY GENERATED DEBASHER SCRIPT


webui_stream_stall_document()
{
    debasher::document_module "Example built with the web UI: a resident program to try by hand, whose node Acquire reads a fake stream of reads that can stall, as the stream of a sequencer may do with the process alive, and notices it, so that the Supervisor relaunches it; a second node tallies the reads and decides on each."
}


webui_stream_stall_shared_dirs()
{
    :
}


webui_stream_stall_program_type()
{
    debasher::program_type "resident"
}


Acquire_document()
{
    debasher::document_process "Reads a fake stream of reads, and reads written by hand into -reads, and sends each one to Tally. It raises when the stream gives nothing for -stall-timeout-s, so that the Supervisor relaunches it and the relaunch reconnects. The stream stalls once a file stall exists in the output directory of the process, or after -stall-after reads of a connection."
}


Acquire_explain_opts()
{
    debasher::explain_opt "-reads" "<string>" "reads written from outside the program, one per message"
    debasher::explain_opt "-chunk-interval-ms" "<string>" "milliseconds between two reads of the stream (20 by default)"
    debasher::explain_opt "-stall-after" "<string>" "reads after which every connection stalls (0, never, by default)"
    debasher::explain_opt "-stall-timeout-s" "<string>" "seconds with no read after which the node raises (5 by default)"
    debasher::explain_opt "-outreads" "<string>" "every read, to Tally"
    debasher::explain_opt "-outhb" "<string>" "heartbeat channel to the Supervisor"
    debasher::explain_opt "-control" "<string>" "control port of this initiator"
}


Acquire_identify_cmdline_opts()
{
    debasher::opt_is_non_mandatory_cmdline "-chunk-interval-ms"
    debasher::opt_is_non_mandatory_cmdline "-stall-after"
    debasher::opt_is_non_mandatory_cmdline "-stall-timeout-s"
}


Acquire_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    debasher::define_fifo_opt "-reads" "reads" optlist --external || return 1
    debasher::define_cmdline_opt_if_given "${cmdline}" "-chunk-interval-ms" optlist || return 1
    debasher::define_cmdline_opt_if_given "${cmdline}" "-stall-after" optlist || return 1
    debasher::define_cmdline_opt_if_given "${cmdline}" "-stall-timeout-s" optlist || return 1
    debasher::define_fifo_opt "-outreads" "acquired" optlist || return 1
    debasher::define_fifo_opt "-outhb" "Acquire_hb" optlist || return 1
    debasher::define_opt_from_proc_out "-control" "Sup" "-outAcquire_initiator" optlist || return 1

    save_opt_list optlist
}


Acquire_heredoc_py()
{
    cat <<'EOF'
from debasher_runtime_lib import FBPProcess

import os
import time



class FakeStream:
    """A stand-in for the stream of reads of a sequencer, such as the one
    that readfish reads from MinKNOW: one read every `interval` seconds. It
    can stall, giving no more data without closing, as the real one may do
    with the process still alive. It stalls once the file `stall_path`
    exists, which a new connection removes, or after `stall_after` reads
    (0: never)."""

    # Each read carries a signal of this many characters, so that the
    # stream moves about 50 KiB per second at its default pace
    SIGNAL_CHARS = 1000
    # At most this many reads in one poll, so that a long pause does not
    # bring in a burst without limit
    MAX_READS_PER_POLL = 500

    def __init__(self, connection, interval, stall_after, stall_path):
        self.connection = connection
        self.interval = interval
        self.stall_after = stall_after
        self.stall_path = stall_path
        self.opened_at = time.monotonic()
        self.given = 0
        self.stalled = False
        # A new connection is what clears a passing stall
        if os.path.exists(stall_path):
            os.remove(stall_path)

    def poll(self):
        """The reads that are due since the last poll, or none if stalled."""
        if self.stall_after and self.given >= self.stall_after:
            self.stalled = True
        if os.path.exists(self.stall_path):
            self.stalled = True
        if self.stalled:
            return []
        due = int((time.monotonic() - self.opened_at) / self.interval) if self.interval else self.given + 1
        if self.stall_after:
            due = min(due, self.stall_after)
        due = min(due, self.given + self.MAX_READS_PER_POLL)
        reads = [self._make_read(i) for i in range(self.given, due)]
        self.given = max(self.given, due)
        return reads

    def _make_read(self, i):
        return {
            "id": f"read-{self.connection}-{i}",
            "channel": i % 512 + 1,
            "length": 200 + (i * 7919) % 4800,
            "signal": "ACGT"[i % 4] * self.SIGNAL_CHARS,
        }


class Acquire(FBPProcess):
    # What observe() takes from the stream reaches process_data under this
    # name
    OBSERVE_PORT = "stream"
    OBSERVE_INTERVAL_SECS = 0.2

    def __init__(self):
        super().__init__()
        self.interval = float(self.opts.get("chunk-interval-ms", "20")) / 1000
        self.stall_after = int(self.opts.get("stall-after", "0"))
        self.stall_timeout = float(self.opts.get("stall-timeout-s", "5"))
        self.stream = None

    def _count_connection(self, path):
        try:
            with open(path) as f:
                count = int(f.read().strip() or 0)
        except FileNotFoundError:
            count = 0
        count += 1
        with open(path, "w") as f:
            f.write(f"{count}\n")
        return count

    def process_data(self, port_name, packet):
        # A read from the stream, or one written by hand into -reads
        self.send_data("outreads", packet)

    def capture_node_state(self):
        return {}

    def restore_node_state(self, node_state):
        pass

    def initialize_runtime(self):
        # The stream and its files are the outside world, not node state:
        # each incarnation opens a connection of its own, as readfish
        # reconnects to MinKNOW when it starts again
        outdir = os.environ.get("DEBASHER_PROCESS_OUTDIR", ".")
        connection = self._count_connection(os.path.join(outdir, "connections"))
        self.stream = FakeStream(connection, self.interval, self.stall_after, os.path.join(outdir, "stall"))
        self.last_progress = time.monotonic()

    def observe(self):
        reads = self.stream.poll()
        for read in reads:
            self.inject(read)
        now = time.monotonic()
        if reads:
            self.last_progress = now
        elif now - self.last_progress > self.stall_timeout:
            # A stream that stalls keeps the process alive and doing
            # nothing; raising makes the node unhealthy, so that the
            # Supervisor relaunches it and the relaunch reconnects
            self.set_notice(
                f"the stream gave no read for {self.stall_timeout:g} s, after "
                f"{self.stream.given} reads of connection {self.stream.connection}",
                level="warning",
            )
            raise RuntimeError(f"stream stalled for {self.stall_timeout:g} s")


Acquire().run()
EOF
}


Tally_document()
{
    debasher::document_process "Counts the reads by channel, keeps the ids of the last ones, and sends a decision for each read, as readfish takes one."
}


Tally_explain_opts()
{
    debasher::explain_opt "-inreads" "<string>" "the reads of Acquire"
    debasher::explain_opt "-outdecisions" "<string>" "a decision for each read, read outside the program"
    debasher::explain_opt "-outhb" "<string>" "heartbeat channel to the Supervisor"
}


Tally_identify_cmdline_opts()
{
    :
}


Tally_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    debasher::define_opt_from_proc_out "-inreads" "Acquire" "-outreads" optlist || return 1
    debasher::define_fifo_opt "-outdecisions" "decisions" optlist || return 1
    debasher::define_fifo_opt "-outhb" "Tally_hb" optlist || return 1

    save_opt_list optlist
}


Tally_heredoc_py()
{
    cat <<'EOF'
from debasher_runtime_lib import FBPProcess


class Tally(FBPProcess):
    # How many of the last read ids the node keeps
    RECENT_IDS = 10
    # A notice with the totals every so many reads
    NOTICE_EVERY = 100

    def __init__(self):
        super().__init__()
        # The node state: the reads seen by channel (keys are strings, as a
        # checkpoint gives them back), the ids of the last ones, the total
        self.counts = {}
        self.recent = []
        self.total = 0

    def _set_totals_notice(self):
        self.set_notice(f"{self.total} reads on {len(self.counts)} channels")

    def process_data(self, port_name, packet):
        channel = str(packet.get("channel", 0))
        self.counts[channel] = self.counts.get(channel, 0) + 1
        self.recent.append(packet.get("id"))
        del self.recent[: -self.RECENT_IDS]
        self.total += 1
        # A decision for each read, as readfish takes one: a short read is
        # ejected from its pore, a long one is sequenced to the end
        decision = "unblock" if packet.get("length", 0) < 1000 else "stop_receiving"
        self.send_data(
            "outdecisions",
            {"id": packet.get("id"), "decision": decision, "channel_reads": self.counts[channel]},
        )
        if self.total % self.NOTICE_EVERY == 0:
            self._set_totals_notice()

    def capture_node_state(self):
        # Returned without a copy: the runtime takes one when it captures
        return {"counts": self.counts, "recent": self.recent, "total": self.total}

    def restore_node_state(self, node_state):
        self.counts = node_state["counts"]
        self.recent = node_state["recent"]
        self.total = node_state["total"]
        self._set_totals_notice()

    def initialize_runtime(self):
        pass


Tally().run()
EOF
}


Sup_document()
{
    debasher::document_process "Watches Acquire and Tally and relaunches them if they go down."
}


Sup_explain_opts()
{
    debasher::explain_opt "-Acquire_hb" "<string>" "heartbeat channel of Acquire"
    debasher::explain_opt "-outAcquire_initiator" "<string>" "initiator port to Acquire"
    debasher::explain_opt "-Tally_hb" "<string>" "heartbeat channel of Tally"
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
    debasher::define_opt_from_proc_out "-Tally_hb" "Tally" "-outhb" optlist || return 1
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


webui_stream_stall_program()
{
    add_debasher_process "Acquire" "cpus=1 mem=256 time=01:00:00 out_backlog_max_mb=0.5 out_backlog_fail_mb=1" ""
    add_debasher_process "Tally" "cpus=1 mem=256 time=01:00:00 input_log_max_mb=4" ""
    add_debasher_process "Sup" "cpus=1 mem=256 time=01:00:00" ""
}
