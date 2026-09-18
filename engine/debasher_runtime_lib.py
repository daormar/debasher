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
import io
import sys
import re
import os
import json
import logging
from collections import namedtuple

# Constants
DEBASHER_SHUTDOWN_TOKEN = "__SHUTDOWN_TOKEN__"

#####################
# CONTROL ENVELOPE  #
#####################
#
# JSON Lines wire format for communication between resident processes
# (FBPProcess/Supervisor), see to_do_resident.md point 1. Three sibling
# envelope types, always encoded as their own single-line JSON object --
# a BARRIER or INTERACT message is never nested inside DATA's payload,
# so a reader can dispatch on "type" alone, without ever interpreting
# "payload".

TYPE_DATA = "DATA"
TYPE_BARRIER = "BARRIER"
TYPE_INTERACT = "INTERACT"

_VALID_TYPES = (TYPE_DATA, TYPE_BARRIER, TYPE_INTERACT)

Envelope = namedtuple("Envelope", ["type", "payload"])


def encode_data(payload):
    """
    Encodes a DATA envelope. `payload` is free-form, whatever the
    business logic wants to send; must be JSON-serializable.
    """
    return _encode(TYPE_DATA, payload)


def encode_barrier(epoch, halt=False):
    """
    Encodes a BARRIER envelope (a Chandy-Lamport marker). `epoch`
    identifies the snapshot round. `halt=True` reuses the same marker
    for an ordered shutdown instead of a snapshot (point 8).
    """
    return _encode(TYPE_BARRIER, {"epoch": epoch, "halt": halt})


def encode_interact(command, args=None):
    """
    Encodes an INTERACT envelope. `command` names the action (e.g.
    "start_snapshot", "shutdown", "heartbeat", "checkpoint_saved"); the
    command catalog is deliberately open-ended (point 1).
    """
    return _encode(TYPE_INTERACT, {"command": command, "args": args or {}})


def _encode(envelope_type, payload):
    # No trailing newline: writing one (one write per line to the FIFO)
    # is the caller's job, keeping this symmetric with json.dumps itself.
    return json.dumps({"type": envelope_type, "payload": payload})


def decode_envelope(line):
    """
    Decodes one JSON-line envelope (as produced by encode_data/
    encode_barrier/encode_interact) into an Envelope(type, payload)
    namedtuple. Raises json.JSONDecodeError on malformed JSON, ValueError
    if "type"/"payload" is missing or "type" is not one of
    DATA/BARRIER/INTERACT.
    """
    obj = json.loads(line)

    if "type" not in obj or "payload" not in obj:
        raise ValueError(f"envelope missing 'type' or 'payload': {line!r}")

    envelope_type = obj["type"]
    if envelope_type not in _VALID_TYPES:
        raise ValueError(f"unknown envelope type: {envelope_type!r}")

    return Envelope(type=envelope_type, payload=obj["payload"])


#####################
# FBPProcess        #
#####################
#
# Base class for a long-running, stateful "resident" process (see
# to_do_resident.md, point 2). This slice covers only the skeleton: argv
# parsing into self.opts, INPUT_PORTS/OUTPUT_PORTS validation, and
# self.log. Threads, barrier logic, INTERACT dispatch and the startup
# sequence (point 6) are later slices, layered on top of this.


def _parse_opts(argv):
    """
    Parses argv into a name -> value dict, following DeBasher's own
    "-optname value" CLI convention (see debasher_lib_opts.sh) -- one or
    two leading dashes, both stripped, so "-inf"/"--inf" both become the
    key "inf". `argv` is expected in the raw sys.argv shape a Python
    heredoc receives from debasher::_create_heredoc_func_body: element 0
    is "-c" (python's own placeholder for a "-c script" invocation),
    followed eventually by a "--" marker and then the actual option
    pairs; everything up to and including that marker is ignored. If no
    "--" marker is present, element 0 alone is skipped instead (the
    shape a plain sys.argv, or a hand-built argv missing the marker,
    would have).
    """
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = argv[1:]

    opts = {}
    it = iter(argv)
    for name in it:
        if not name.startswith("-"):
            raise ValueError(f"expected an option name starting with '-', got {name!r}")
        try:
            value = next(it)
        except StopIteration:
            raise ValueError(f"option {name!r} is missing its value") from None
        opts[name.lstrip("-")] = value
    return opts


class FBPProcess:
    """
    Base class for resident processes. A subclass declares its ports via
    the INPUT_PORTS/OUTPUT_PORTS class attributes (option names, without
    their leading dash(es), e.g. INPUT_PORTS = ["inf"]) and overrides
    process_data/capture_state/restore_state/initialize_runtime.
    """

    INPUT_PORTS = []
    OUTPUT_PORTS = []

    DEFAULT_LOG_LEVEL = "INFO"

    def __init__(self, argv=None, opts=None):
        if opts is not None:
            # Direct injection, mainly for tests: skips argv parsing
            # entirely, so a test doesn't need to build a realistic
            # fake argv just to get a usable instance.
            self.opts = dict(opts)
        else:
            self.opts = _parse_opts(list(sys.argv) if argv is None else argv)

        self._check_declared_ports()
        self.log = self._make_logger()

    def _check_declared_ports(self):
        for port in list(self.INPUT_PORTS) + list(self.OUTPUT_PORTS):
            if port not in self.opts:
                raise ValueError(
                    f"{type(self).__name__}: port {port!r} is declared in "
                    f"INPUT_PORTS/OUTPUT_PORTS but there is no -{port} "
                    f"option (got: {sorted(self.opts)})"
                )

    def _make_logger(self):
        level_name = self.opts.get("log-level", self.DEFAULT_LOG_LEVEL).upper()
        logger = logging.getLogger(type(self).__name__)
        logger.setLevel(level_name)
        if not logger.handlers:
            handler = logging.StreamHandler(sys.stderr)
            handler.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)-8s [%(threadName)s] %(message)s")
            )
            logger.addHandler(handler)
        logger.propagate = False
        return logger

    # -- subclass extension points (points 2, 5) --

    def process_data(self, port_name, packet):
        raise NotImplementedError

    def capture_state(self):
        raise NotImplementedError

    def restore_state(self, state):
        raise NotImplementedError

    def initialize_runtime(self):
        raise NotImplementedError
