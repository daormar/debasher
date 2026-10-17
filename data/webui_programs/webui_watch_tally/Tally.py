from debasher_runtime_lib import FBPProcess


class Tally(FBPProcess):
    def __init__(self):
        super().__init__()
        # The node state: how many files have been requested so far.
        self.seen = 0

    def process_data(self, port_name, packet):
        self.seen += 1
        self.send_data("outtally", {"run": packet["run"], "seen": self.seen})

    def capture_node_state(self):
        return {"seen": self.seen}

    def restore_node_state(self, node_state):
        self.seen = node_state["seen"]

    def initialize_runtime(self):
        pass


Tally().run()
