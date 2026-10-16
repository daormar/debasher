"""
A process as the SDK describes it: its name, where its code is, its
options and, through the sources of its inputs, its connections. A process
is defined on its own, outside any program, as a process of a module is:
a program adds it (see program.py), and the same process can be added to
several programs.

Every option is declared by a method of the process that gives it its
value source (the command line, a connection, a literal value) and its
option channel, with the vocabulary of the program model of the web UI
(see "Processes and options" in doc/design_doc_webui.md): the label is the
option's name for the engine, such as "-infile", the data type is what
the option carries, and its direction comes from its label, as the engine
reads it, an output being a label that starts with "-out" or "--out".
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path
from typing import Union

from .errors import DefinitionError

DATA_TYPES = ("int", "float", "string", "file", "dir")

# The language of a code file, from its extension: the same rule by which
# the engine chooses the interpreter of an external alias.
LANGUAGES_BY_EXTENSION = {
    ".sh": "bash",
    ".py": "python",
    ".pl": "perl",
    ".r": "r",
    ".R": "r",
    ".groovy": "groovy",
}

# The rule of the engine for a process name (debasher::_is_valid_processname
# in engine/debasher_lib_programs.sh, mirrored by the backend): parts of
# letters, digits and underscores, separated by dots.
_PROCESS_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z_0-9]*(\.[a-zA-Z_][a-zA-Z_0-9]*)*$")


def check_process_name(name: str) -> None:
    """Refuses a name that the engine would refuse."""
    from api.debasher_constants import RESERVED_HEREDOC_SUFFIXES, RESERVED_PROCESS_METHOD_SUFFIXES

    if not _PROCESS_NAME_RE.match(name):
        raise DefinitionError(
            f'"{name}" cannot name a process: a name is made of letters, digits and '
            "underscores, starts with a letter or an underscore, and may be qualified "
            'with dot-separated namespaces ("org.mymodule.name").'
        )
    # The suffixes of the methods carry their underscore ("_define_opts");
    # those of the heredoc languages do not ("py"). The empty suffix of
    # the exec method, which every name ends with, is skipped as the
    # engine skips it.
    suffixes = [s for s in RESERVED_PROCESS_METHOD_SUFFIXES if s] + [f"_{s}" for s in RESERVED_HEREDOC_SUFFIXES]
    for suffix in suffixes:
        if name.endswith(suffix):
            raise DefinitionError(
                f'"{name}" cannot name a process: it ends in "{suffix}", which the engine '
                "reserves for a method of a process."
            )
    if "__NSSEP__" in name:
        raise DefinitionError(f'"{name}" cannot name a process: "__NSSEP__" is a marker of the engine.')


# A program name is the name of its module and the prefix of the module
# methods (`<name>_program`), so it has the form of a process name without
# namespaces; the engine reserves no suffix of it.
_PROGRAM_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z_0-9]*$")


def check_program_name(name: str) -> None:
    if not _PROGRAM_NAME_RE.match(name):
        raise DefinitionError(
            f'"{name}" cannot name a program: a name is made of letters, digits and '
            "underscores, and starts with a letter or an underscore."
        )


def in_outdir(name: str = "") -> str:
    """
    The value of an output kept in the process output directory: the path
    of `name` under it, or the directory itself when `name` is empty, as a
    Bash word that the engine expands when the option is defined.
    """
    return "${process_outdir}/" + name if name else "${process_outdir}"


def option_direction(label: str) -> str:
    """The direction that the engine reads from a label."""
    return "output" if label.startswith("-out") or label.startswith("--out") else "input"


# A source of an input: the output option it reads, or the name of the
# process and the label of the output, as a hand-written module names them.
Source = Union["Option", tuple[str, str]]


class Option:
    """
    One option of a process, with the fields of the program model that
    script generation reads. Created through the methods of Process, never
    directly.
    """

    def __init__(self, process: Process, label: str, data_type: str, description: str, **fields):
        self.process = process
        self.label = label
        self.data_type = data_type
        self.description = description
        self.value: str = fields.pop("value", "")
        self.channel: str = fields.pop("channel", "none")
        self.subpath: str = fields.pop("subpath", "")
        self.mirror: bool = fields.pop("mirror", False)
        self.fifo_tag: str | None = fields.pop("fifo_tag", None)
        self.command_line: bool = fields.pop("command_line", False)
        self.mandatory: bool = fields.pop("mandatory", False)
        self.from_process_spec: bool = fields.pop("from_process_spec", False)
        self.task_shaping: bool = fields.pop("task_shaping", False)
        # An option of the same process, or its label, whose value counts a
        # fanout family; None counts the tasks of the process at the other
        # end of its connections.
        self.count_source: Option | str | None = fields.pop("count_source", None)
        # The outputs this input reads: one, or several for a fan-in.
        self.sources: list[Source] = _as_sources(fields.pop("source", None))
        # How the canvas draws its connections: a line, or a label edge.
        self.display: str = fields.pop("display", "line")
        if fields:
            raise DefinitionError(
                f'Option "{label}" of process "{process.name}": unknown field(s) '
                + ", ".join(sorted(fields))
            )
        self.direction = option_direction(label)

    def __repr__(self) -> str:
        return f'Option("{self.process.name}", "{self.label}")'


def _as_sources(source) -> list[Source]:
    if source is None:
        return []
    if isinstance(source, (list, tuple)) and not (len(source) == 2 and isinstance(source[0], str)):
        return [_as_source(item) for item in source]
    return [_as_source(source)]


def _as_source(source) -> Source:
    if isinstance(source, Option):
        return source
    if isinstance(source, tuple) and len(source) == 2 and all(isinstance(part, str) for part in source):
        return source
    raise DefinitionError(
        f"A source is the output option of a process, or a tuple (process name, "
        f"option label), not {source!r}."
    )


class Process:
    """
    A process: its name, qualified with dot-separated namespaces if
    wanted, its description, and where its code is, as one of:

    - `code`, a file in the language of the process, told by its
      extension (.sh, .py, .pl, .r, .groovy): a Bash function named as
      the process, with its helper functions, or the whole script of
      another language. The file is read when the program is written and
      its text goes into the program metadata and into the module, as the
      code box of the editor does.
    - `script`, a file that the module runs as it is, with the interpreter
      of its extension (the external alias of the engine): the file stays
      outside the module, copied beside it when the program is written
      elsewhere.
    - `alias`, the name of another process whose code this one runs under
      its own name and options.
    - none of them: the code of a process of that name that a module
      loaded by the preamble of the program provides.

    A relative path is taken from the directory of the Python file that
    creates the process (`base_dir` names another directory).
    """

    mode = "standard"

    def __init__(
        self,
        name: str,
        code: str | Path | None = None,
        script: str | Path | None = None,
        alias: str | None = None,
        description: str = "",
        language: str | None = None,
        alias_opt_map: dict[str, str] | None = None,
        base_dir: str | Path | None = None,
    ):
        check_process_name(name)
        given = [kind for kind, value in (("code", code), ("script", script), ("alias", alias)) if value]
        if len(given) > 1:
            raise DefinitionError(
                f'Process "{name}" gives its code in more than one way ({", ".join(given)}): give one.'
            )
        if alias_opt_map and not (script or alias):
            raise DefinitionError(f'Process "{name}" has an alias_opt_map without a script or an alias.')
        if language is not None and language not in LANGUAGES_BY_EXTENSION.values():
            raise DefinitionError(
                f'Process "{name}": unknown language "{language}" (one of '
                + ", ".join(sorted(set(LANGUAGES_BY_EXTENSION.values())))
                + ")."
            )
        self.name = name
        self.description = description
        self.base_dir = Path(base_dir) if base_dir is not None else _caller_dir()
        self.code_path = self._resolve(code)
        self.script_path = self._resolve(script)
        self.alias = alias
        self.alias_opt_map = dict(alias_opt_map or {})
        self.language = language or self._language_of(self.code_path or self.script_path) or "bash"
        self.options: list[Option] = []

    def __repr__(self) -> str:
        return f'Process("{self.name}")'

    def _resolve(self, path) -> Path | None:
        if path is None:
            return None
        path = Path(path)
        return path if path.is_absolute() else self.base_dir / path

    def _language_of(self, path: Path | None) -> str | None:
        if path is None:
            return None
        language = LANGUAGES_BY_EXTENSION.get(path.suffix)
        if language is None:
            raise DefinitionError(
                f'Process "{self.name}": the extension of {path.name} tells no language; give '
                "language= (bash, python, perl, r or groovy)."
            )
        return language

    # --- options -------------------------------------------------------------

    def __getitem__(self, label: str) -> Option:
        for option in self.options:
            if option.label == label:
                return option
        raise KeyError(f'Process "{self.name}" has no option "{label}".')

    def opt(self, label: str, data_type: str = "string", description: str = "", **fields) -> Option:
        """
        An option with the fields of the program model given by name (value,
        channel, subpath, mirror, fifo_tag, command_line, mandatory,
        from_process_spec, task_shaping, count_source, source, display);
        the other methods are this one with the fields of one case set.
        A flag has the data type "None".
        """
        if not label.startswith("-"):
            raise DefinitionError(f'Option "{label}" of process "{self.name}": a label starts with "-".')
        if data_type not in DATA_TYPES and data_type != "None":
            raise DefinitionError(
                f'Option "{label}" of process "{self.name}": unknown data type "{data_type}" (one of '
                + ", ".join(DATA_TYPES)
                + ', or "None" for a flag).'
            )
        if any(option.label == label for option in self.options):
            raise DefinitionError(f'Process "{self.name}" declares option "{label}" twice.')
        option = Option(self, label, data_type, description, **fields)
        self.options.append(option)
        return option

    def cmdline_opt(
        self, label: str, data_type: str, description: str, mandatory: bool = True, shaping: bool = False
    ) -> Option:
        """An input whose value comes from the command line of the run; a
        task shaping option (`shaping`) is read by the options handler only."""
        if shaping and not mandatory:
            raise DefinitionError(
                f'Option "{label}" of process "{self.name}": a task shaping option is mandatory.'
            )
        return self._input(
            label, data_type, description, command_line=True, mandatory=mandatory, task_shaping=shaping
        )

    def cmdline_flag(self, label: str, description: str) -> Option:
        """A flag of the command line of the run, which has no value."""
        return self._input(label, "None", description, command_line=True)

    def input(
        self,
        label: str,
        data_type: str,
        description: str,
        value: str = "",
        source: Source | list[Source] | None = None,
        count_source: Option | str | None = None,
        display: str = "line",
    ) -> Option:
        """
        An input: connected to the output of another process (`source`, one
        or, for a fan-in, several), or with a literal value, or, for a
        family of inputs (a label ending in "-ith"), counted by an option of
        this process (`count_source`) or by the tasks of the process it
        reads.
        """
        if value and source:
            raise DefinitionError(
                f'Option "{label}" of process "{self.name}" has both a value and a source.'
            )
        return self._input(
            label, data_type, description, value=value, source=source, count_source=count_source,
            display=display,
        )

    def output(
        self, label: str, data_type: str, description: str, value: str = "", count_source: Option | str | None = None
    ) -> Option:
        """An output, with the value that names what the process produces
        (see in_outdir), or a family of outputs counted by `count_source`."""
        if option_direction(label) != "output":
            raise DefinitionError(
                f'Option "{label}" of process "{self.name}": the engine takes an output from its '
                'label, which starts with "-out" or "--out".'
            )
        return self.opt(label, data_type, description, value=value, count_source=count_source)

    def _input(self, label: str, data_type: str, description: str, **fields) -> Option:
        if option_direction(label) != "input":
            raise DefinitionError(
                f'Option "{label}" of process "{self.name}": a label that starts with "-out" or '
                '"--out" is an output for the engine.'
            )
        return self.opt(label, data_type, description, **fields)


def _caller_dir() -> Path:
    """The directory of the file of the user that is creating a process: the
    first frame outside this package, or the current directory when there
    is none with a file (an interactive session)."""
    package_dir = Path(__file__).resolve().parent
    for frame in inspect.stack()[1:]:
        filename = frame.filename
        if not filename or filename.startswith("<"):
            continue
        path = Path(filename).resolve()
        if package_dir not in path.parents:
            return path.parent
    return Path.cwd()
