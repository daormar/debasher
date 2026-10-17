from debasher_runtime_lib import FBPProcess


class Accumulate(FBPProcess):
    def __init__(self):
        super().__init__()
        # The node state: the sum of every number received so far.
        self.total = 0

    def process_data(self, port_name, packet):
        self.total += packet
        self.send_data("outsum", self.total)

    def capture_node_state(self):
        return {"total": self.total}

    def restore_node_state(self, node_state):
        self.total = node_state["total"]

    def initialize_runtime(self):
        pass


Accumulate().run()
