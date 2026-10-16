"""
The Python SDK of DeBasher: a program is described in Python and written
as the program metadata and the generated module that the web UI saves,
which `debasher_exec` runs as any other program.

A file of the user defines processes, with their options and their
connections, and one Program that adds them with the specifications of
their use; it calls nothing, as a hand-written module calls nothing. The
tool `debasher_build` loads the file and writes the program. The SDK
executes nothing itself: what runs the program is `debasher_exec`.
"""

from ._paths import locate_api as _locate_api

_locate_api()

from .errors import DefinitionError  # noqa: E402
from .process import Array, Generator, Node, Option, Process, Supervisor, in_outdir  # noqa: E402
from .program import Program  # noqa: E402

__all__ = ["Array", "DefinitionError", "Generator", "Node", "Option", "Process", "Program", "Supervisor", "in_outdir"]
