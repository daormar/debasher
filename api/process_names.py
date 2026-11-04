"""
The rule of the engine for a process name (debasher::_is_valid_processname
in engine/debasher_lib_programs.sh), in one place for every door that
checks one: the router of the editor (routers/processes.py) and the Python
SDK, which does not import the routers since they need FastAPI.
"""

import re

from .debasher_constants import RESERVED_HEREDOC_SUFFIXES, RESERVED_PROCESS_METHOD_SUFFIXES

# Parts of letters, digits and underscores, separated by dots
_PROCESS_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z_0-9]*(\.[a-zA-Z_][a-zA-Z_0-9]*)*$")

# The marker with which the engine turns a qualified name into the name of
# a variable
NSSEP_MARKER = "__NSSEP__"


def _reserved_name_endings() -> list[str]:
    """
    The endings that a process name may not have: the suffix of each
    method, which carries its underscore ("_define_opts"), and that of
    each heredoc language, which does not ("py"). The empty suffix of the
    exec method, which every name ends with, is skipped as the engine
    skips it.
    """
    return [s for s in RESERVED_PROCESS_METHOD_SUFFIXES if s] + [f"_{s}" for s in RESERVED_HEREDOC_SUFFIXES]


def process_name_problem(name: str) -> str | None:
    """
    Why the engine would refuse `name` as the name of a process, or None
    when it would take it: the function of a process "a_post" would be
    the post method of a process "a". The reason is a clause that follows
    '"<name>" cannot name a process: ' in a message.
    """
    if not _PROCESS_NAME_RE.match(name):
        return (
            "a name is made of letters, digits and underscores, starts with a letter "
            'or an underscore, and may be qualified with dot-separated namespaces ("org.mymodule.name").'
        )
    for ending in _reserved_name_endings():
        if name.endswith(ending):
            return f'it ends in "{ending}", which the engine reserves for a method of a process.'
    if NSSEP_MARKER in name:
        return f'"{NSSEP_MARKER}" is a marker of the engine.'
    return None
