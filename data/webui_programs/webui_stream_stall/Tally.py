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
