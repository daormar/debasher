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
import json
from collections import namedtuple


#####################
# CONTROL ENVELOPE  #
#####################
#
# JSON Lines wire format for communication between resident processes
# (FBPProcess/Supervisor). Sibling envelope types, always encoded as their
# own single-line JSON object: a BARRIER or INTERACT message is never
# nested inside DATA's payload, so a reader can dispatch on "type" alone,
# without ever interpreting "payload". DATA, BARRIER and INTERACT carry
# the messages themselves. CLOSE and HELLO belong to the transport: a
# writer sends HELLO as the first line of every incarnation of itself (so
# its reader can discard a fragment left by the previous one) and CLOSE
# when it stops on purpose.

TYPE_DATA = "DATA"
TYPE_BARRIER = "BARRIER"
TYPE_INTERACT = "INTERACT"
TYPE_CLOSE = "CLOSE"
TYPE_HELLO = "HELLO"

_VALID_TYPES = (TYPE_DATA, TYPE_BARRIER, TYPE_INTERACT, TYPE_CLOSE, TYPE_HELLO)

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
    for an ordered shutdown instead of a snapshot.
    """
    return _encode(TYPE_BARRIER, {"epoch": epoch, "halt": halt})


def encode_interact(command, args=None):
    """
    Encodes an INTERACT envelope. `command` names the action (e.g.
    "start_snapshot", "shutdown", "heartbeat", "checkpoint_saved"); the
    command catalog is deliberately open-ended.
    """
    return _encode(TYPE_INTERACT, {"command": command, "args": args or {}})


def encode_close():
    """
    Encodes a CLOSE envelope: sent by a writer, as its very last line,
    when it stops on purpose. A reader that sees it knows nothing more
    will ever come through that channel from that writer. Without it,
    silence means either that the writer finished or that it crashed and
    will be relaunched, and nothing in the fifo tells the two apart.
    """
    return _encode(TYPE_CLOSE, {})


def encode_hello():
    """
    Encodes a HELLO envelope. A writer sends it as the first thing it does
    every time it starts, in one write together with a leading newline
    (see _PortWorker._writer_loop). If the previous incarnation of the
    writer died in the middle of a message, what it left in the fifo is an
    unterminated fragment: the newline turns it into a line of its own,
    and the reader, which tolerates one unparsable line only when a HELLO
    follows it, drops it.
    """
    return _encode(TYPE_HELLO, {})


def _encode(envelope_type, payload):
    # No trailing newline: writing one (one write per line to the FIFO)
    # is the caller's job, keeping this symmetric with json.dumps itself.
    return json.dumps({"type": envelope_type, "payload": payload})


def decode_envelope(line):
    """
    Decodes one JSON-line envelope (as produced by encode_data/
    encode_barrier/encode_interact/encode_close/encode_hello) into an
    Envelope(type, payload) namedtuple. Raises json.JSONDecodeError on
    malformed JSON, ValueError if "type"/"payload" is missing or "type"
    is not one of the valid envelope types.
    """
    return _envelope_from_obj(json.loads(line), line)


def _envelope_from_obj(obj, what):
    """
    Validates an envelope that is already a decoded JSON value and returns
    it as an Envelope(type, payload). `what` says where it came from (the
    line, or a place in a file) and is only used in the error messages.
    """
    if not isinstance(obj, dict) or "type" not in obj or "payload" not in obj:
        raise ValueError(f"envelope missing 'type' or 'payload': {what!r}")

    envelope_type = obj["type"]
    if envelope_type not in _VALID_TYPES:
        raise ValueError(f"unknown envelope type: {envelope_type!r}")

    return Envelope(type=envelope_type, payload=obj["payload"])
