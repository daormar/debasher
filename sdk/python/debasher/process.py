"""
A process as the SDK describes it: its name, where its code is, its
options and, through the sources of its inputs, its connections. A process
is defined on its own, outside any program, as a process of a module is:
a program adds it (see program.py), and the same process can be added to
several programs.

A process defines one task from its declared options; an Array or a
Generator defines several, with the code of the options handler that the
editor accepts, kept in a file (`tasks=`), in Bash or in Python.

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


def func_language(path: Path | None) -> str:
    """The language of a tasks file or a skip file, by its extension, as the
    topology file tells it: Python for `.py`, Bash for any other."""
    return "python" if path is not None and path.suffix == ".py" else "bash"


def _conda_envs_data(process_name: str, conda_envs) -> dict[str, str]:
    """The Conda environments given as data, name to yml file; empty when
    none are, or when a method file is given instead."""
    if conda_envs is None or isinstance(conda_envs, (str, Path)):
        return {}
    if not isinstance(conda_envs, dict) or not all(
        isinstance(name, str) and name and isinstance(file, str) and file for name, file in conda_envs.items()
    ):
        raise DefinitionError(
            f'Process "{process_name}": conda_envs is a dict of the name of each Conda environment to '
            'its yml file ({"py27": "py27.yml"}), or the path of a method file.'
        )
    return dict(conda_envs)


def _docker_imgs_data(process_name: str, docker_imgs) -> list[str]:
    """The Docker images given as data; empty when none are, or when a
    method file is given instead."""
    if docker_imgs is None or isinstance(docker_imgs, (str, Path)):
        return []
    if not isinstance(docker_imgs, (list, tuple)) or not all(isinstance(img, str) and img for img in docker_imgs):
        raise DefinitionError(
            f'Process "{process_name}": docker_imgs is a list of Docker images (["ubuntu:24.04"]), or '
            "the path of a method file."
        )
    return list(docker_imgs)


# A source of an input: the output option it reads, or the name of the
# process and the label of the output, as a hand-written module names them.
Source = Union["Option", tuple[str, str]]


class Option:
    """
    One option of a process, with the fields of the program model that
    script generation reads. Created through the methods of Process, never
    directly.

    Its attributes are the process it belongs to (`process`), its label
    (`label`), its data type (`data_type`), its description
    (`description`), its value (`value`), its option channel (`channel`)
    and its direction (`direction`, "input" or "output", from its label),
    and the other fields that `Process.opt` takes, under the same names
    (`sources` for `source`), with their defaults when the method that
    created it gives none.
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
      extension (.sh, .py, .pl, .r or .R, .groovy) or by `language`: a Bash
      function named as the process, with its helper functions, or the
      whole script of another language. The topology file names the
      file, which the editor shows and edits as the code of the process;
      the module embeds it when it is Bash, and runs it as it is (an
      external alias of the file) in any other language.
    - `script`, a file that the module runs as it is, with the interpreter
      of its extension (the external alias of the engine): the file stays
      outside the module, copied beside it when the program is written
      elsewhere.
    - `alias`, the name of another process whose code this one runs under
      its own name and options.
    - none of them: the code of a process of that name that a module
      loaded by the preamble of the program provides.

    `language` (bash, python, perl, r or groovy) gives the language of
    the process when the extension of its file does not tell it. A
    `script` or an `alias` may rename the options that the process
    passes on with `alias_opt_map`, the name of each option of this
    process to the one that the code expects (`{"-x": "-y"}`), as the
    alias option map of a module does.

    The additional methods of the process are given as files too, each
    with the body that the editor takes: `skip` (whether a task is
    skipped), a Bash body, or a skip file in Python (`.py`) that defines
    `skip(task)`; `post` (run after the process), `reset_outfiles` (what
    to remove before a rerun) and `outdir_basename` (the name of the
    process output directory), Bash bodies. The environments that the
    process declares are data: `conda_envs`, a dict of the name of each
    Conda environment to its yml file, and `docker_imgs`, a list of
    Docker images; a path given instead is a file with the Bash body of
    the method.

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
        skip: str | Path | None = None,
        post: str | Path | None = None,
        reset_outfiles: str | Path | None = None,
        outdir_basename: str | Path | None = None,
        conda_envs: str | Path | dict[str, str] | None = None,
        docker_imgs: str | Path | list[str] | tuple[str, ...] | None = None,
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
        # The script as given: when relative, it is also how the module
        # refers to it (see Program.write)
        self.script_given = str(script) if script is not None else None
        self.script_path = self._resolve(script)
        self.alias = alias
        self.alias_opt_map = dict(alias_opt_map or {})
        self.language = language or self._language_of(self.code_path or self.script_path) or "bash"
        # The environments given as data, and the files of the additional
        # methods, by the field of the program model that holds each body
        self.conda_envs = _conda_envs_data(name, conda_envs)
        self.docker_imgs = _docker_imgs_data(name, docker_imgs)
        self.method_paths: dict[str, Path] = {}
        for field, path in (
            ("skipCode", skip),
            ("postCode", post),
            ("resetOutfilesCode", reset_outfiles),
            ("outdirBasenameCode", outdir_basename),
            ("condaEnvsCode", conda_envs),
            ("dockerImgsCode", docker_imgs),
        ):
            if isinstance(path, (str, Path)):
                self.method_paths[field] = self._resolve(path)
        for field, path in self.method_paths.items():
            if field != "skipCode" and func_language(path) == "python":
                raise DefinitionError(
                    f'Process "{name}": {path.name} is a Python file, and only the skip method '
                    "takes one; give the body of this method in Bash."
                )
        self.skip_language = func_language(self.method_paths.get("skipCode"))
        self.tasks_path: Path | None = None
        self.tasks_language = "bash"
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
        """The option of the process with the label `label`, such as
        `generate["-outf"]`, to give as the source of an input; KeyError
        when the process has none."""
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
        self._check_direction(label, "output")
        return self.opt(label, data_type, description, value=value, count_source=count_source)

    def fifo_output(
        self,
        label: str,
        data_type: str,
        description: str,
        name: str,
        mirror: bool = False,
        count_source: Option | str | None = None,
    ) -> Option:
        """An output written to a FIFO named `name`, mirrored into a log file
        for the canvas to watch if asked; or a family of FIFOs, one per
        value of the index (`"dispatch_fifo_${i}"`), counted by
        `count_source`."""
        self._check_direction(label, "output")
        return self.opt(
            label, data_type, description, value=name, channel="fifo", mirror=mirror, count_source=count_source
        )

    def fifo_input(self, label: str, data_type: str, description: str, name: str, external: bool = False) -> Option:
        """An input read from a FIFO named `name`, which the process opens
        itself rather than receives through a connection; in a resident
        program, an external input (`external`), written from outside the
        program."""
        return self._input(
            label, data_type, description, value=name, channel="fifo", fifo_tag="external" if external else None
        )

    def outdir_opt(self, label: str, description: str, subpath: str = "") -> Option:
        """An output that names the process output directory of the process,
        or a task subdirectory of it (`subpath`, a Bash word such as
        `"${task_idx}"`), for another process to read through a connection."""
        self._check_direction(label, "output")
        return self.opt(label, "dir", description, channel="process_outdir", subpath=subpath)

    def shared_dir_opt(
        self,
        label: str,
        data_type: str,
        description: str,
        shared_dir: str,
        subpath: str = "",
        source: Source | list[Source] | None = None,
    ) -> Option:
        """An option whose value is a shared directory of the program, named
        by `shared_dir` (one of the shared directories of the Program), or a
        shared subdirectory of it (`subpath`). A `source` only draws the
        sharing on the canvas: the engine orders the processes by the
        directory itself."""
        return self.opt(
            label, data_type, description, value=shared_dir, channel="shared_dir", subpath=subpath, source=source
        )

    def procspec_opt(self, label: str, data_type: str, description: str, attribute: str) -> Option:
        """An input whose value is an attribute of the specifications of the
        process in the program, such as `"cpus"`."""
        return self._input(label, data_type, description, value=attribute, from_process_spec=True)

    def value_desc_output(self, label: str, data_type: str, description: str) -> Option:
        """An output delivered as a value descriptor, which the engine
        synthesizes for the process."""
        self._check_direction(label, "output")
        return self.opt(label, data_type, description, channel="value_desc")

    def _check_direction(self, label: str, direction: str) -> None:
        if option_direction(label) != direction:
            if direction == "output":
                raise DefinitionError(
                    f'Option "{label}" of process "{self.name}": the engine takes an output from its '
                    'label, which starts with "-out" or "--out".'
                )
            raise DefinitionError(
                f'Option "{label}" of process "{self.name}": a label that starts with "-out" or '
                '"--out" is an output for the engine.'
            )

    def _input(self, label: str, data_type: str, description: str, **fields) -> Option:
        self._check_direction(label, "input")
        return self.opt(label, data_type, description, **fields)


class _TaskedProcess(Process):
    """A process with several tasks, shaped by the code of its options
    handler, which `tasks` names: a Bash file, as the editor accepts it,
    or a tasks file in Python (`.py`), which defines `tasks(run)`."""

    def __init__(self, name: str, *args, tasks: str | Path | None = None, **kwargs):
        super().__init__(name, *args, **kwargs)
        if tasks is None:
            raise DefinitionError(
                f'Process "{name}" is {self._article} {self.mode} and gives no tasks= file, the code of '
                "its options handler."
            )
        self.tasks_path = self._resolve(tasks)
        self.tasks_language = func_language(self.tasks_path)


class Array(_TaskedProcess):
    """
    An array process: `tasks` is a Bash file that builds the array of its
    tasks, under the name `array`, from the command line and the files of
    the run (`local w=$(debasher::read_opt_value_from_line "${cmdline}"
    "-w")`, then `array+=(...)`), or a Python file whose `tasks(run)`
    returns the elements (`range(int(run.value("-w")))`); every option is
    defined once per element, with `${task_idx}` and `${array[$task_idx]}`
    at hand in its value. It is the array mode of the options handler of
    the editor. It takes the arguments of a Process, and `tasks`.
    """

    mode = "array"
    _article = "an"


class Generator(_TaskedProcess):
    """
    An option generator: `tasks` is a Bash file that prints the number of
    tasks, from the command line and the files of the run, or a Python
    file whose `tasks(run)` returns it; the options of each task are
    defined from its index, `${task_idx}`, in their values. It is the
    generator mode of the options handler of the editor. It takes the
    arguments of a Process, and `tasks`.
    """

    mode = "generator"
    _article = "a"


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


class Node(Process):
    """
    A node of a resident program: a process whose code is a Python file
    with the class of the node, derived from a class of the runtime
    library (`FBPProcess`, `ProgramLauncher` or `DirectoryWatcher`), as
    the generated module writes it: the import of the node kind, the
    node preamble, the class with its hooks, and the line that runs it.
    The SDK splits the file into the parts of the program model with the
    same code as import, and refuses what the web UI could not hold. An
    initiator is a node where a round starts.
    """

    def __init__(
        self,
        name: str,
        code: str | Path,
        initiator: bool = False,
        description: str = "",
        base_dir: str | Path | None = None,
    ):
        super().__init__(name, code=code, description=description, language="python", base_dir=base_dir)
        self.initiator = initiator

    def __repr__(self) -> str:
        return f'Node("{self.name}")'


class Supervisor(Process):
    """
    The Supervisor of a resident program, which watches its nodes and
    relaunches one that goes down. It has no code and no options of its
    own: script generation writes its whole class and its wiring.
    """

    def __init__(self, name: str, description: str = "", base_dir: str | Path | None = None):
        super().__init__(name, description=description, language="python", base_dir=base_dir)

    def __repr__(self) -> str:
        return f'Supervisor("{self.name}")'
