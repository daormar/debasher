"""
DeBasher package
Copyright 2019-2026 Daniel Ortiz-Mart\'inez

This library is free software; you can redistribute it and/or
modify it under the terms of the GNU Lesser General Public License
as published by the Free Software Foundation; either version 3
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Lesser General Public License for more details.

You should have received a copy of the GNU Lesser General Public License
along with this program; If not, see <http://www.gnu.org/licenses/>.
"""

# *- python -*

# import modules
import fnmatch
import os

from debasher_runtime_fbp import FBPProcess


#####################
# DirectoryWatcher  #
#####################
#
# A node that watches a directory and sends a request for each new file
# that arrives there, once the file is complete (see "Observing the outside
# world" in doc/design_doc_resident.md). Its observe() looks at the
# directory and brings each complete file in as an input; its process_data
# sends the request, once per file, whatever a crash makes observe() bring
# in again.


class DirectoryWatcher(FBPProcess):
    """
    WATCH_DIR is the directory to watch: an absolute path, or one relative to
    the directory of the module that declares the node; an option of the
    node named WATCH_DIR_OPTION (-watchdir), if it has one, gives it instead,
    for a directory that the command line chooses. The files are those whose
    name matches PATTERN, never one whose name starts with a dot, which is how
    a file that is still being written is often named.

    A file is complete once its size and its modification time have stayed
    the same for STABLE_OBSERVATIONS observations in a row, OBSERVE_INTERVAL_SECS
    apart. A module whose files are complete in another way (a companion file,
    a rename at the end of a copy) redefines is_complete().

    For each complete file, the node sends on REQUESTS_PORT what
    request_for() makes of its path: by default a request for a launcher node
    (see ProgramLauncher), with the path as the value of FILE_OPTION and the
    name of the file without its extension as the name of the run.
    """

    WATCH_DIR = None
    WATCH_DIR_OPTION = "watchdir"
    PATTERN = "*"
    STABLE_OBSERVATIONS = 2
    OBSERVE_PORT = "arrivals"
    REQUESTS_PORT = "outrequests"
    FILE_OPTION = "-infile"

    def __init__(self, argv=None, opts=None):
        super().__init__(argv, opts)
        self._watch_dir = self._find_watch_dir()
        # The node state: the files for which a request has been sent, so
        # that a file brought in again is requested once.
        self._requested = set()
        # What observe() remembers between two observations, in this
        # incarnation only: the size and modification time of each file,
        # with how many observations in a row they have not changed, and the
        # files it has brought in. A relaunched node brings the complete
        # files in again, which process_data drops.
        self._stability = {}
        self._brought_in = set()

    def _find_watch_dir(self):
        watch_dir = self.opts.get(self.WATCH_DIR_OPTION) or self.WATCH_DIR
        if not watch_dir:
            raise ValueError(
                f"{type(self).__name__}: no directory to watch: neither WATCH_DIR nor an "
                f"option -{self.WATCH_DIR_OPTION}"
            )
        if not os.path.isabs(watch_dir):
            module_dir = os.environ.get("DEBASHER_PROCESS_MODULE_DIR")
            if not module_dir:
                raise RuntimeError(
                    f"{type(self).__name__}: DEBASHER_PROCESS_MODULE_DIR is not set in the "
                    "environment, cannot resolve the directory to watch against the directory "
                    "of the module (only set by the engine's builtin scheduler when it launches "
                    "a process)"
                )
            watch_dir = os.path.join(module_dir, watch_dir)
        return watch_dir

    # -- node hooks --

    def initialize_runtime(self):
        pass

    def capture_node_state(self):
        return {"requested": sorted(self._requested)}

    def restore_node_state(self, node_state):
        self._requested = set(node_state["requested"])

    def process_data(self, port_name, packet):
        if port_name != self.OBSERVE_PORT:
            return
        path = packet.get("file") if isinstance(packet, dict) else None
        if path is None:
            self.log.error("dropping an arrival with no file: %r", packet)
            return
        if path in self._requested:
            return
        self._requested.add(path)
        if self.REQUESTS_PORT in self.OUTPUT_PORTS:
            self.send_data(self.REQUESTS_PORT, self.request_for(path))

    # -- what a module may redefine --

    def request_for(self, path):
        """The request sent for the complete file at `path`."""
        name = os.path.splitext(os.path.basename(path))[0]
        return {"opts": {self.FILE_OPTION: path}, "run": name}

    def is_complete(self, path, stable_observations):
        """Whether the file at `path` is complete, after its size and
        modification time have not changed for `stable_observations`
        observations in a row."""
        return stable_observations >= self.STABLE_OBSERVATIONS

    # -- the observation of the directory --

    def observe(self):
        try:
            names = sorted(os.listdir(self._watch_dir))
        except FileNotFoundError:
            self.log.warning("the directory to watch, %s, does not exist yet", self._watch_dir)
            return
        present = set()
        for name in names:
            if name.startswith(".") or not fnmatch.fnmatch(name, self.PATTERN):
                continue
            path = os.path.join(self._watch_dir, name)
            try:
                st = os.stat(path)
            except FileNotFoundError:
                continue
            if not os.path.isfile(path):
                continue
            present.add(path)
            signature = (st.st_size, st.st_mtime_ns)
            previous = self._stability.get(path)
            stable = previous[1] + 1 if previous is not None and previous[0] == signature else 1
            self._stability[path] = (signature, stable)
            if path not in self._brought_in and self.is_complete(path, stable):
                self.inject({"file": path})
                self._brought_in.add(path)
        for path in list(self._stability):
            if path not in present:
                del self._stability[path]
