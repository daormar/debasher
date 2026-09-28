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

# Prints, as one JSON object, what one node of a resident program keeps in its
# execdir: the files half of debasher_inspect_resident, which finds the node
# in its program, tells the state of its task and passes both on. It only
# reads, and reads each file by the rules with which the node reads it when
# it recovers, with the code of the runtime library rather than a copy of
# those rules.

# import modules
import argparse
import json
import os
import sys
import time

from debasher_runtime_fbp import FBPProcess
from debasher_runtime_inputlog import BadLine, _InputLogReader
from debasher_runtime_launcher import (
    _batch_run_state,
    _read_registrations,
    _registrations_dir_of,
    program_status,
)


class InspectError(Exception):
    """An error of usage or setup, reported with exit code 1."""


def _execdir_entry(execdir, name, task_idx):
    """The path of `name` in the execdir, as the runtime names it for a task
    of an array (see _execdir_entry in debasher_runtime_transport.py)."""
    return os.path.join(execdir, name if task_idx is None else f"{name}_{task_idx}")


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except FileNotFoundError:
        return None


def _read_json(path):
    """The JSON value in `path`, or None if the file is not there."""
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return None


# --- the files of a node ------------------------------------------------------


class Node:
    """The files of one node, a process or one task of an array process."""

    def __init__(self, execdir, task_idx):
        self.execdir = execdir
        self.task_idx = task_idx

    def entry(self, name):
        return _execdir_entry(self.execdir, name, self.task_idx)

    def checkpoints(self):
        """[(epoch, path)] of the checkpoints that the node retains, oldest
        first."""
        directory = self.entry("checkpoints")
        try:
            names = os.listdir(directory)
        except FileNotFoundError:
            return []
        epochs = []
        for name in names:
            if not name.endswith(".json"):
                continue
            try:
                epochs.append(int(name[: -len(".json")]))
            except ValueError:
                continue
        return [(epoch, os.path.join(directory, f"{epoch}.json")) for epoch in sorted(epochs)]

    def latest_capture_pos(self):
        """The capture_pos of the newest checkpoint of the schema version of
        the runtime library, or None if there is none. A checkpoint pruned
        while it is read is skipped."""
        for _epoch, path in reversed(self.checkpoints()):
            checkpoint = _read_json(path)
            if checkpoint is None:
                continue
            if checkpoint.get("schema_version") != FBPProcess.CHECKPOINT_SCHEMA_VERSION:
                return None
            return checkpoint.get("capture_pos")
        return None

    def halted_epoch(self):
        try:
            with open(self.entry("halted")) as f:
                return int(f.read().strip())
        except (FileNotFoundError, ValueError):
            return None

    def node_info(self):
        """The node info file as the node last wrote it, with its age and
        whether it is stale, or None if the node has never written one."""
        info = _read_json(self.entry("node_info"))
        if info is None:
            return None
        age = time.time() - info["updated_at"]
        info["age_secs"] = age
        info["stale"] = age > 2 * info["heartbeat_interval_secs"]
        return info

    def input_log(self):
        return _InputLogReader(self.entry("log"))


# --- the commands -------------------------------------------------------------


def summary(node, process, task_state):
    capture_pos = node.latest_capture_pos()
    info = node.node_info()

    log = node.input_log()
    segments = log.segments()
    input_log = {
        "bytes": sum(size for _, size in segments),
        "max_bytes": info["limits"]["input_log_max_bytes"] if info else None,
        "segments": len(segments),
        "first_pos": None,
        "last_pos": None,
        "to_replay": 0,
    }
    try:
        input_log["first_pos"] = log.first_pos()
        input_log["last_pos"] = log.last_pos()
    except ValueError as exc:
        input_log["error"] = str(exc)
    if input_log["last_pos"] is not None:
        input_log["to_replay"] = max(0, input_log["last_pos"] - (capture_pos or 0))

    return {
        "process": process,
        "task": node.task_idx,
        "task_state": task_state,
        "checkpoints": [
            {"epoch": epoch, "written_at": _mtime(path)} for epoch, path in node.checkpoints()
        ],
        "capture_pos": capture_pos,
        "halted_epoch": node.halted_epoch(),
        "input_log": input_log,
        "node_info": info,
    }


def _count_by_port(messages):
    """{port: {"messages": n, "bytes": size}} for {port: [message, ...]}."""
    return {
        port: {"messages": len(items), "bytes": sum(len(json.dumps(item)) for item in items)}
        for port, items in messages.items()
    }


def checkpoint(node, epoch):
    retained = node.checkpoints()
    path = dict(retained).get(epoch)
    content = _read_json(path) if path is not None else None
    if content is None:
        epochs = ", ".join(str(e) for e, _ in node.checkpoints()) or "none"
        raise InspectError(f"the node retains no checkpoint of epoch {epoch} (it retains: {epochs})")

    schema_version = content.get("schema_version")
    result = {
        "epoch": epoch,
        "path": path,
        "written_at": _mtime(path),
        "schema_version": schema_version,
        "readable": schema_version == FBPProcess.CHECKPOINT_SCHEMA_VERSION,
    }
    if result["readable"]:
        result.update(
            {
                "capture_pos": content["capture_pos"],
                "closed_ports": content["closed_ports"],
                "out_seq": content["out_seq"],
                "last_seq": content["last_seq"],
                "node_state": content["node_state"],
                "channel_state": _count_by_port(content["channel_state"]),
                "out_backlog": _count_by_port(content["out_backlog"]),
            }
        )
    return result


def log(node, port, last):
    records = []
    for item in node.input_log().records_backwards():
        if len(records) >= last:
            break
        if isinstance(item, BadLine):
            records.append({"segment": item.path, "line": item.lineno, "error": item.error})
            continue
        if port is not None and item.port != port:
            continue
        records.append(
            {
                "pos": item.pos,
                "port": item.port,
                "type": item.envelope.type,
                "seq": item.envelope.seq,
                "payload": item.envelope.payload,
            }
        )
    records.reverse()
    return {"capture_pos": node.latest_capture_pos(), "records": records}


def runs(node, process_outdir, debasher_status):
    info = node.node_info()
    if info is None:
        raise InspectError("the node has never written its node info file: it has not started yet")
    launcher = info.get("launcher")
    if info["runtime_class"] != "ProgramLauncher" or launcher is None:
        raise InspectError(f"the node is not a launcher node (its class derives from {info['runtime_class']})")

    single_process = launcher["process"] is not None
    result = []
    for pos, run in _read_registrations(_registrations_dir_of(process_outdir)):
        run_dir = os.path.join(launcher["runs_root"], run)
        state, exit_code = _batch_run_state(
            run_dir, single_process, lambda d: program_status(debasher_status, d)
        )
        result.append(
            {"pos": pos, "run": run, "run_dir": run_dir, "state": state, "exit_code": exit_code}
        )
    return {"runs_root": launcher["runs_root"], "runs": result}


# --- the command line ---------------------------------------------------------


def _non_negative_int(text):
    value = int(text)
    if value < 0:
        raise argparse.ArgumentTypeError(f"{text} is negative")
    return value


def _positive_int(text):
    value = int(text)
    if value <= 0:
        raise argparse.ArgumentTypeError(f"{text} is not positive")
    return value


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise InspectError(message)


def build_arg_parser():
    parser = _Parser(prog="debasher_inspect_node", add_help=False)
    parser.add_argument("--process", required=True)
    parser.add_argument("--task-idx", type=_non_negative_int)
    parser.add_argument("--task-state", required=True)
    parser.add_argument("--execdir", required=True)
    parser.add_argument("--process-outdir", required=True)
    parser.add_argument("--debasher-status", required=True)
    commands = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)
    commands.add_parser("summary", add_help=False)
    checkpoint_parser = commands.add_parser("checkpoint", add_help=False)
    checkpoint_parser.add_argument("epoch", type=int)
    log_parser = commands.add_parser("log", add_help=False)
    log_parser.add_argument("--port")
    log_parser.add_argument("--last", type=_positive_int, default=100)
    commands.add_parser("runs", add_help=False)
    return parser


def run_command(argv):
    """The JSON value that the command in `argv` prints. Raises InspectError
    on an error of usage or setup."""
    args = build_arg_parser().parse_args(argv)
    node = Node(args.execdir, args.task_idx)
    if args.command == "summary":
        return summary(node, args.process, args.task_state)
    if args.command == "checkpoint":
        return checkpoint(node, args.epoch)
    if args.command == "log":
        return log(node, args.port, args.last)
    return runs(node, args.process_outdir, args.debasher_status)


def main(argv):
    try:
        result = run_command(argv)
    except InspectError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
