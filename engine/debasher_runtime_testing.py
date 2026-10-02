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
import ast
import contextlib
import json
import linecache
import os
import re
import subprocess
import sys
import tempfile
import types

from debasher_runtime_envelope import decode_envelope
from debasher_runtime_fbp import FBPProcess
from debasher_runtime_launcher import ProgramLauncher
from debasher_runtime_supervisor import Supervisor
from debasher_runtime_watcher import DirectoryWatcher


################
# Node harness #
################
#
# Builds a node of a resident program without the engine, so that a node
# test (a pytest test of the business logic of the node, run by
# debasher_test) can feed it packets and look at what it sends and at its
# node state (see "Testing a node without the engine" in
# doc/design_doc_resident.md). No FIFO is opened and no thread started:
# the test calls the hooks of the node on its own thread.
#
# The harness reaches into the internals of FBPProcess (the thread allowed
# to send, the outbound queues and backlog), so that a node test does not
# have to, and those internals can change without breaking the tests of
# the programs.

# The node kinds that the harness does not build: what makes them what
# they are (launching general programs, supervising the nodes) is not
# driven by process_data and observe() alone
_REFUSED_KINDS = (Supervisor, ProgramLauncher)

# The heredoc of each process, by program file and process name, taken
# once per test session: loading the module is what costs time
_source_cache = {}


def load_node(process, opts=None, inputs=(), outputs=()):
    """
    Builds the node of the process `process` of the program file that
    DEBASHER_TEST_PFILE names, and returns it as a NodeUnderTest.

    `opts` gives the options of the node, by name with or without the
    leading dash; a value True is a flag. `inputs` and `outputs` are its
    ports that the test feeds and reads, named as their options without
    the dash. A port that the test leaves out is not a port of the node
    under test. The node gets a placeholder for the option of each port,
    whose FIFO is never opened, and initialize_runtime() is called, as
    run() does before any thread starts. The directory of the program file
    is the directory of the module of the node, against which a relative
    path, such as the WATCH_DIR of a DirectoryWatcher, is resolved.
    """
    pfile = os.environ.get("DEBASHER_TEST_PFILE")
    if not pfile:
        raise RuntimeError(
            "load_node: DEBASHER_TEST_PFILE is not set: run the tests with "
            "debasher_test, or set it to the program file"
        )
    node_class = _node_class(process, _node_source(pfile, process))
    module_dir = os.path.dirname(os.path.abspath(pfile))
    under_test = NodeUnderTest(node_class, opts or {}, list(inputs), list(outputs), module_dir)
    with under_test._node_env():
        under_test.node.initialize_runtime()
    return under_test


def _node_source(pfile, process):
    """The text of the Python heredoc of `process`, as the engine runs it."""
    key = (pfile, process)
    if key not in _source_cache:
        libexecdir = os.environ.get("DEBASHER_LIBEXECDIR")
        if not libexecdir:
            raise RuntimeError(
                "load_node: DEBASHER_LIBEXECDIR is not set: run the tests with "
                "debasher_test, which sets it"
            )
        result = subprocess.run(
            [os.path.join(libexecdir, "debasher_get_node_source"), pfile, process],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"load_node: cannot get the code of the process {process!r} of "
                f"{pfile}:\n{result.stderr}"
            )
        _source_cache[key] = result.stdout
    return _source_cache[key]


def _node_class(process, source):
    """
    Runs the heredoc `source` as a module of its own, without the line
    that would start the node, and returns the class of the node.
    """
    filename = f"<heredoc of {process}>"
    tree = ast.parse(source, filename=filename)
    class_names = {stmt.name for stmt in tree.body if isinstance(stmt, ast.ClassDef)}
    tree.body = [stmt for stmt in tree.body if not _is_run_line(stmt, class_names)]
    for stmt in tree.body:
        if _starts_a_node(stmt):
            raise ValueError(
                f"load_node: the heredoc of {process!r} starts its node at line "
                f"{stmt.lineno} in a form the harness does not recognize: end it "
                f"with the line <Name>().run(), alone, or put that line under "
                f'if __name__ == "__main__":'
            )

    # A real module, registered under its name, so that what looks a class
    # up by its __module__ (dataclasses, pickle, typing) finds it; the
    # source goes into linecache, so that a traceback shows its lines
    module_name = "debasher_node_under_test_" + re.sub(r"\W", "_", process)
    module = types.ModuleType(module_name)
    module.__file__ = filename
    sys.modules[module_name] = module
    linecache.cache[filename] = (len(source), None, source.splitlines(True), filename)
    exec(compile(tree, filename, "exec"), module.__dict__)

    classes = [
        value
        for value in vars(module).values()
        if isinstance(value, type)
        and value.__module__ == module_name
        and issubclass(value, (FBPProcess, Supervisor))
    ]
    if len(classes) != 1:
        raise ValueError(
            f"load_node: the heredoc of {process!r} defines {len(classes)} classes "
            "that derive from a class of the runtime library, where a node has one"
        )
    node_class = classes[0]
    for kind in _REFUSED_KINDS:
        if issubclass(node_class, kind):
            raise ValueError(
                f"load_node: {node_class.__name__} is a {kind.__name__}: the harness "
                "builds a subclass of FBPProcess or of DirectoryWatcher"
            )
    return node_class


def _is_run_line(stmt, class_names):
    """Whether `stmt` is the line <Name>().run() of a class of the heredoc."""
    if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Call):
        return False
    call = stmt.value
    return (
        not call.args
        and not call.keywords
        and isinstance(call.func, ast.Attribute)
        and call.func.attr == "run"
        and isinstance(call.func.value, ast.Call)
        and isinstance(call.func.value.func, ast.Name)
        and call.func.value.func.id in class_names
        and not call.func.value.args
        and not call.func.value.keywords
    )


def _is_main_guard(stmt):
    """Whether `stmt` is if __name__ == "__main__":, which a module of
    the harness never runs."""
    test = getattr(stmt, "test", None)
    return (
        isinstance(stmt, ast.If)
        and isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == "__name__"
        and len(test.comparators) == 1
        and isinstance(test.comparators[0], ast.Constant)
        and test.comparators[0].value == "__main__"
    )


def _starts_a_node(stmt):
    """
    Whether the top-level statement `stmt` calls a method run() with no
    arguments, as a node is started, outside a definition and outside
    if __name__ == "__main__":, which would start a node while the harness
    runs the heredoc. A call with arguments, such as subprocess.run([...]),
    starts no node.
    """
    if isinstance(stmt, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) or _is_main_guard(stmt):
        return False
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "run"
        and not node.args
        and not node.keywords
        for node in ast.walk(stmt)
    )


def _json_round_trip(value):
    """`value` as a JSON reader gets it: a tuple becomes a list, a key a
    string."""
    return json.loads(json.dumps(value))


class NodeUnderTest:
    """
    A node built by load_node: `feed` calls its process_data, `observe`
    its observe(), `sent` gives what it sent, `restart` builds it again
    from its node state, and `node` is the instance itself.
    """

    def __init__(self, node_class, opts, inputs, outputs, module_dir=None):
        self._node_class = node_class
        self._opts = dict(opts)
        self._inputs = inputs
        self._outputs = outputs
        self._module_dir = module_dir
        # The execdir of the node, where it may leave a notice: nothing is
        # written into the program directory
        self._tmpdir = tempfile.TemporaryDirectory(prefix="debasher_node_")
        self._sent = {port: [] for port in outputs}

        with self._node_env(), self._argv():
            self.node = node_class()
        # The pace of a node is not business logic
        self.node.sleep = lambda seconds: None
        # What inject() brings in, which in a run goes to the input log and
        # then to the brain thread (see observe below); inject() keeps its
        # own checks
        self._injected = []
        self.node._on_arrivals = lambda port, items: self._injected.extend(
            envelope.payload for envelope, _ in items
        )

    @contextlib.contextmanager
    def _node_env(self):
        """
        The environment that the engine gives a node, while the node runs
        code: its ports, its execdir, and neither computational
        specifications nor a task index. Restored afterwards, since two
        nodes under test share the environment of the test.
        """
        env = {
            "DEBASHER_PROCESS_PORTS": f"input={','.join(self._inputs)};output={','.join(self._outputs)}",
            "DEBASHER_PROCESS_EXECDIR": self._tmpdir.name,
            "DEBASHER_PROCESS_COMP_SPECS": None,
            "DEBASHER_PROCESS_TASK_IDX": None,
            "DEBASHER_PROCESS_MODULE_DIR": self._module_dir,
        }
        saved = {name: os.environ.get(name) for name in env}
        try:
            for name, value in env.items():
                _set_env(name, value)
            yield
        finally:
            for name, value in saved.items():
                _set_env(name, value)

    @contextlib.contextmanager
    def _argv(self):
        """
        The argv from which the node parses its options, in the shape that
        the engine gives it: the class of a node takes no argument, and
        its constructor reads sys.argv.
        """
        args = {name.lstrip("-"): value for name, value in self._opts.items()}
        for port in self._inputs + self._outputs:
            args.setdefault(port, os.path.join(self._tmpdir.name, "ports", port))
        argv = ["-c", "--"]
        for name, value in args.items():
            if value is True:
                argv.append(f"-{name}")
            elif value is not False and value is not None:
                argv += [f"-{name}", str(value)]
        saved = sys.argv
        sys.argv = argv
        try:
            yield
        finally:
            sys.argv = saved

    def feed(self, port, packet):
        """
        Calls process_data(port, packet) on this thread, the one allowed to
        send while the call lasts, as the brain thread is. The packet first
        makes a round trip through JSON, so that the node gets what would
        arrive through a FIFO. `port` is an input port of the node under
        test, or its OBSERVE_PORT, for something that observe() would have
        brought in.
        """
        observe_port = self.node._observe_port()
        if port not in self._inputs and (observe_port is None or port != observe_port):
            raise ValueError(
                f"feed: {port!r} is neither an input port of the node under test "
                f"(inputs: {self._inputs}) nor its observe port ({observe_port})"
            )
        try:
            with self._node_env():
                self.node._run_process_data(port, _json_round_trip(packet))
        finally:
            self._collect_sent()

    def observe(self):
        """
        Runs observe() once on this thread, as the observation thread would
        at the end of an interval, and then calls process_data, in order,
        with what it brought in with inject(), under OBSERVE_PORT, as the
        brain thread would. Returns what observe() brought in, after the
        same round trip through JSON as a message.
        """
        if not self.node._observes():
            raise ValueError(f"observe: {self._node_class.__name__} does not define observe()")
        self._injected.clear()
        with self._node_env():
            self.node.observe()
        injected = list(self._injected)
        try:
            with self._node_env():
                for payload in injected:
                    self.node._run_process_data(self.node._observe_port(), payload)
        finally:
            self._collect_sent()
        return injected

    def _collect_sent(self):
        """
        Takes off the outbound queues what send_data queued, keeping its
        payloads, and counts each line as written, so that the outbound
        backlog never fills.
        """
        for port, outbound in self.node._outbound_queues.items():
            while not outbound.empty():
                line = outbound.get_nowait()
                self.node._on_written(port, line)
                self._sent[port].append(decode_envelope(line).payload)

    def sent(self, port):
        """The payloads that the node has sent on `port` since it was built."""
        if port not in self._sent:
            raise ValueError(
                f"sent: {port!r} is not an output port of the node under test "
                f"(outputs: {self._outputs})"
            )
        return list(self._sent[port])

    def restart(self):
        """
        Builds the node again from its node state, as recovery does: the
        state makes a round trip through JSON, as a checkpoint does, and a
        new node with the same options and ports restores it and then runs
        initialize_runtime(). Raises AssertionError when the new node
        captures a state other than the one it was restored from.
        """
        with self._node_env():
            node_state = _json_round_trip(self.node.capture_node_state())
        restarted = NodeUnderTest(self._node_class, self._opts, self._inputs, self._outputs, self._module_dir)
        with restarted._node_env():
            restarted.node.restore_node_state(_json_round_trip(node_state))
            restarted.node.initialize_runtime()
            recaptured = _json_round_trip(restarted.node.capture_node_state())
        if recaptured != node_state:
            raise AssertionError(
                f"restart: {self._node_class.__name__} restored the node state "
                f"{node_state!r} and then captured {recaptured!r}"
            )
        return restarted


def _set_env(name, value):
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value
