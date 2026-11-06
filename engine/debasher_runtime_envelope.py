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
# the messages themselves. A DATA also carries a "seq", the sender's
# per-channel counter (see FBPProcess.send_data), unless it comes from a
# plain _PortWorker or from outside the program, neither of which numbers
# what it sends. CLOSE and HELLO belong to the transport: a
# writer sends HELLO as the first line of every incarnation of itself (so
# its reader can discard a fragment left by the previous one) and CLOSE
# when it has finished for good. A halt is not that, since the node is
# resumed later, so a halt sends no CLOSE.

TYPE_DATA = "DATA"
TYPE_BARRIER = "BARRIER"
TYPE_INTERACT = "INTERACT"
TYPE_CLOSE = "CLOSE"
TYPE_HELLO = "HELLO"

_VALID_TYPES = (TYPE_DATA, TYPE_BARRIER, TYPE_INTERACT, TYPE_CLOSE, TYPE_HELLO)

Envelope = namedtuple("Envelope", ["type", "payload", "seq"], defaults=[None])


def encode_data(payload, seq=None):
    """
    Encodes a DATA envelope. `payload` is free-form, whatever the
    business logic wants to send; must be JSON-serializable, with no NaN
    or infinity, which JSON does not have (ValueError). `seq` is the
    sender's per-channel counter for this message; omitted (not even the
    key) when the sender is not one that numbers what it sends.
    """
    obj = {"type": TYPE_DATA}
    if seq is not None:
        obj["seq"] = seq
    obj["payload"] = payload
    return json.dumps(obj, allow_nan=False)


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


def encode_close(last_seq=None):
    """
    Encodes a CLOSE envelope: sent by a writer, as its very last line,
    when it has finished for good. A reader that sees it knows nothing
    more will ever come through that channel from that writer. Without
    it, silence means either that the writer finished or that it stopped
    and will be relaunched (after a crash, or after a halt), and nothing
    in the fifo tells the two apart. That is why a halt sends none.
    `last_seq` is the sender's own count of the last numbered `DATA` it
    ever sent on this channel: the receiver can then tell a message
    lost between there and here from a channel that simply never
    carried that many, which a later gap in the numbers could otherwise
    never reveal, since none is coming after a CLOSE. Left out (an empty
    payload) when the sender is not one that numbers what it sends.
    """
    payload = {} if last_seq is None else {"last_seq": last_seq}
    return _encode(TYPE_CLOSE, payload)


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
    # Strict JSON, as in encode_data: no NaN or infinity on the wire.
    return json.dumps({"type": envelope_type, "payload": payload}, allow_nan=False)


def decode_envelope(line):
    """
    Decodes one JSON-line envelope (as produced by encode_data/
    encode_barrier/encode_interact/encode_close/encode_hello) into an
    Envelope(type, payload, seq) namedtuple ("seq" is None unless the line
    carries one, which only a numbered DATA does). Raises
    json.JSONDecodeError on malformed JSON, ValueError if "type"/"payload"
    is missing, "type" is not one of the valid envelope types, or a field
    has the wrong type for its envelope (see _check_fields).
    """
    return _envelope_from_obj(json.loads(line), line)


def _envelope_from_obj(obj, what):
    """
    Validates an envelope that is already a decoded JSON value and returns
    it as an Envelope(type, payload, seq). `what` says where it came from
    (the line, or a place in a file) and is only used in the error
    messages.
    """
    if not isinstance(obj, dict) or "type" not in obj or "payload" not in obj:
        raise ValueError(f"envelope missing 'type' or 'payload': {what!r}")

    envelope_type = obj["type"]
    if envelope_type not in _VALID_TYPES:
        raise ValueError(f"unknown envelope type: {envelope_type!r}")

    problem = _check_fields(envelope_type, obj["payload"], obj.get("seq"))
    if problem is not None:
        raise ValueError(f"malformed {envelope_type} envelope, {problem}: {what!r}")

    return Envelope(type=envelope_type, payload=obj["payload"], seq=obj.get("seq"))


def _is_int(value):
    # A bool is an int to Python, never to the protocol.
    return isinstance(value, int) and not isinstance(value, bool)


def _check_fields(envelope_type, payload, seq):
    """
    What is wrong with the fields of an envelope of `envelope_type`, or
    None: the fields that the engine reads, with the types that the
    encoders above give them. The arguments of an INTERACT are left to the
    handler of its command, since the catalog of commands is open.
    """
    if seq is not None and not _is_int(seq):
        return f"its seq {seq!r} is not an integer"
    if envelope_type == TYPE_DATA:
        return None
    if not isinstance(payload, dict):
        return f"its payload {payload!r} is not an object"
    if envelope_type == TYPE_BARRIER:
        if not _is_int(payload.get("epoch")):
            return f"its epoch {payload.get('epoch')!r} is not an integer"
        if not isinstance(payload.get("halt"), bool):
            return f"its halt {payload.get('halt')!r} is not a boolean"
    elif envelope_type == TYPE_INTERACT:
        if not isinstance(payload.get("command"), str):
            return f"its command {payload.get('command')!r} is not a string"
    elif envelope_type == TYPE_CLOSE:
        if "last_seq" in payload and not _is_int(payload["last_seq"]):
            return f"its last_seq {payload['last_seq']!r} is not an integer"
    return None
