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
