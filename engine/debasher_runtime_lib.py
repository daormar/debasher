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

# The runtime library of resident programs: the module that the Python
# heredocs of a program import (from debasher_runtime_lib import FBPProcess).
# The code itself lives in modules of their own, one layer each, and every
# module imports only from the ones before it:
#
#   debasher_runtime_envelope    the wire format: envelope types, encode and decode
#   debasher_runtime_transport   argv parsing, fifo endpoints and _PortWorker, the
#                                thread-per-port plumbing
#   debasher_runtime_inputlog    _InputLog, the durable input history of a node
#   debasher_runtime_fbp         FBPProcess
#   debasher_runtime_supervisor  Supervisor
#
# Every name that this module offered before the split is still available
# here, so nothing that imports it has to know about the layers. The names
# with a leading underscore are not part of what module authors use: they
# are here because the tests reach them through this module. _write_all is
# left out on purpose: whoever patches it has to patch the module that looks
# it up, and a patch on this one would silently do nothing.

# import modules
from debasher_runtime_envelope import (
    TYPE_BARRIER,
    TYPE_CLOSE,
    TYPE_DATA,
    TYPE_HELLO,
    TYPE_INTERACT,
    Envelope,
    decode_envelope,
    encode_barrier,
    encode_close,
    encode_data,
    encode_hello,
    encode_interact,
    _envelope_from_obj,
)
from debasher_runtime_transport import _STOP, _PortWorker, _parse_opts
from debasher_runtime_inputlog import LogRecord, _InputLog
from debasher_runtime_fbp import FBPProcess
from debasher_runtime_supervisor import Supervisor, _MANUAL_TRIGGER_TAG
from debasher_runtime_launcher import ProgramLauncher

# Constants
DEBASHER_SHUTDOWN_TOKEN = "__SHUTDOWN_TOKEN__"

__all__ = [
    "DEBASHER_SHUTDOWN_TOKEN",
    "TYPE_BARRIER",
    "TYPE_CLOSE",
    "TYPE_DATA",
    "TYPE_HELLO",
    "TYPE_INTERACT",
    "Envelope",
    "decode_envelope",
    "encode_barrier",
    "encode_close",
    "encode_data",
    "encode_hello",
    "encode_interact",
    "LogRecord",
    "FBPProcess",
    "Supervisor",
]
