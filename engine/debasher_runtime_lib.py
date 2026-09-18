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
