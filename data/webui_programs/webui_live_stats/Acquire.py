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
