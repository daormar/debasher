from debasher_runtime_lib import FBPProcess


class Report(FBPProcess):
    def __init__(self):
        super().__init__()
        # The node state: how many batch runs finished and failed.
        self.counts = {"finished": 0, "failed": 0}

    def report_failures(self):
        # A notice for whoever watches the program while some batch run has failed.
        if self.counts.get("failed"):
            self.set_notice(f"{self.counts['failed']} batch run(s) failed", level="warning")

    def process_data(self, port_name, packet):
        status = packet["status"]
        self.counts[status] = self.counts.get(status, 0) + 1
        self.send_data("outreport", {"run": packet["run"], "status": status, **self.counts})
        self.report_failures()

    def capture_node_state(self):
        return dict(self.counts)

    def restore_node_state(self, node_state):
        self.counts = dict(node_state)
        # The notice is not part of the node state: it is set again from it.
        self.report_failures()

    def initialize_runtime(self):
        pass


Report().run()
