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
            # nothing; raising ends the process with an error, so that
            # the Supervisor relaunches it and the relaunch reconnects
            self.set_notice(
                f"the stream gave no read for {self.stall_timeout:g} s, after "
                f"{self.stream.given} reads of connection {self.stream.connection}",
                level="warning",
            )
            raise RuntimeError(f"stream stalled for {self.stall_timeout:g} s")


Acquire().run()
