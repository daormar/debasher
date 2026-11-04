"""
A process as the SDK describes it, in the three groups of parts of "What a
program may give again" in doc/design_doc_engine.md: its invariant part,
given to the constructor with its name (its code, its description, the
options that its tasks receive, its environments and the methods of a
task), which nothing changes afterwards; its interface (`interface`), what
it receives from outside the program; and its task options
(`task_options`), the shape of its tasks and the value of each option of
a task. The last two are the variable part: each call replaces its part
whole, so that a program that adds a process defined elsewhere gives them
again.

A process is defined on its own, outside any program, as a process of a
module is: a program adds it (see program.py). The vocabulary is that of
the program model of the web UI (see "Processes and options" in
doc/design_doc_webui.md): the label is the option's name for the engine,
such as "-infile", the data type is what the option carries, and its
direction comes from its label, as the engine reads it, an output being a
label that starts with "-out" or "--out".
"""

from __future__ import annotations

import inspect
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Union

from api.process_names import option_label_problem, process_name_problem
from api.topology import LANGUAGE_BY_EXTENSION

from .errors import DefinitionError

DATA_TYPES = ("int", "float", "string", "file", "dir")


def check_process_name(name: str) -> None:
    """Refuses a name that the engine would refuse, with the rule that the
    editor checks too."""
    problem = process_name_problem(name)
    if problem is not None:
        raise DefinitionError(f'"{name}" cannot name a process: {problem}')


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


def is_family(label: str) -> bool:
    """Whether a label stands for a fanout family, one option per task at
    the other end of its connection."""
    return label.endswith("-ith")


def func_language(path: Path | None) -> str:
    """The language of a tasks file or a skip file, by its extension, as the
    topology file tells it: Python for `.py`, Bash for any other."""
    return "python" if path is not None and path.suffix == ".py" else "bash"


# --- the received options -----------------------------------------------------


@dataclass(frozen=True)
class _ReceivedOption:
    """An option of the list given to a process, before the process exists."""

    label: str
    data_type: str
    description: str


def opt(label: str, data_type: str, description: str = "") -> _ReceivedOption:
    """An option that a task of the process receives, for the `options` of
    a process: its label, "-" or "--" followed by an ASCII letter or an
    underscore, as the engine takes it, its data type (int, float, string,
    file, dir) and its description."""
    return _ReceivedOption(label, data_type, description)


def flag(label: str, description: str = "") -> _ReceivedOption:
    """A flag that a task of the process receives, an option with no value
    (its data type is "None" in the program model), with a label as that of
    `opt` and its description."""
    return _ReceivedOption(label, "None", description)


class Option:
    """
    A received option of a process, reached by its label
    (`generate["-outf"]`) to name it as the source of a connection. Its
    attributes are the process (`process`), the label (`label`), the data
    type (`data_type`), the description (`description`) and the direction
    (`direction`, "input" or "output", from the label).
    """

    def __init__(self, process: Process, label: str, data_type: str, description: str):
        self.process = process
        self.label = label
        self.data_type = data_type
        self.description = description
        self.direction = option_direction(label)

    def __repr__(self) -> str:
        return f'Option("{self.process.name}", "{self.label}")'


# --- the kinds of value of the task options -----------------------------------

# A source of a connection: the output option it reads, or the name of the
# process and the label of the output, as a hand-written module names them.
Source = Union[Option, tuple[str, str]]


@dataclass(frozen=True)
class _Value:
    """The value of an option in the task options, in one of the kinds of
    value of the process contract; `direction` is the one it requires, if
    any."""

    kind: str
    value: str = ""
    channel: str = "none"
    subpath: str = ""
    mirror: bool = False
    from_spec: bool = False
    sources: tuple = ()
    display: str = "line"
    direction: str | None = None


def connect(source: Source | list[Source], display: str = "line") -> _Value:
    """An input connected to an output of another process: the option
    (`generate["-outf"]`) or the name of the process and the label of the
    option; a list of sources is a fan-in. `display="label"` draws the
    connection as a label edge on the canvas."""
    if display not in ("line", "label"):
        raise DefinitionError(f'A connection is displayed as "line" or "label", not "{display}".')
    return _Value("connection", sources=tuple(_as_sources(source)), display=display, direction="input")


def outdir(subpath: str = "") -> _Value:
    """An output that names the process output directory of the process, or
    a task subdirectory of it (`subpath`, a Bash word such as
    `"${task_idx}"`), for another process to read through a connection."""
    return _Value("process output directory", channel="process_outdir", subpath=subpath, direction="output")


def shared_dir(name: str, subpath: str = "", source: Source | list[Source] | None = None) -> _Value:
    """An option whose value is the shared directory `name` of the program,
    or a shared subdirectory of it (`subpath`). A `source` only draws the
    sharing on the canvas: the engine orders the processes by the directory
    itself."""
    sources = tuple(_as_sources(source)) if source is not None else ()
    return _Value("shared directory", value=name, channel="shared_dir", subpath=subpath, sources=sources)


def procspec(attribute: str) -> _Value:
    """An input whose value is an attribute of the specifications of the use
    of the process, such as `"cpus"`."""
    return _Value("specification attribute", value=attribute, from_spec=True, direction="input")


def value_desc() -> _Value:
    """An output delivered as a value descriptor, which the engine
    synthesizes for the process."""
    return _Value("value descriptor", channel="value_desc", direction="output")


def fifo(name: str, mirror: bool = False) -> _Value:
    """An option delivered through a FIFO named `name`, between two
    processes of the program or opened by the process itself (a family of
    FIFOs names one per index, `"dispatch_fifo_${i}"`); an output may be
    mirrored into a log file for the canvas to watch."""
    return _Value("FIFO", value=name, channel="fifo", mirror=mirror)


def _as_sources(source) -> list[Source]:
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


@dataclass(frozen=True)
class _Interface:
    """The interface of a process: its command line options (label to
    mandatory), its task shaping options (label to data type and
    description) and its external FIFOs (label to FIFO name)."""

    cmdline: dict
    shaping: dict
    external: dict


@dataclass(frozen=True)
class _TaskOptions:
    """The task options of a process: the value of each option by label,
    the mode and the tasks file of an array or a generator, and the count
    source of each fanout family by label."""

    values: dict
    mode: str
    tasks_path: Path | None
    count: dict


# The attributes of the invariant part, which nothing changes once the
# process is created
_INVARIANT = frozenset(
    {
        "name", "description", "base_dir", "code_path", "script_given", "script_path", "alias",
        "alias_opt_map", "options", "conda_envs", "docker_imgs", "method_paths",
        "skip_language",
    }
)


class Process:
    """
    A process: its name, qualified with dot-separated namespaces if
    wanted, and its invariant part, which nothing changes afterwards:

    - where its code is, as one of: `code`, a process file, which the
      editor owns, in the language that its extension tells (.sh, .py,
      .pl, .r or .R, .groovy): a Bash function named as the process, with
      its helper functions, which the module embeds with the library of
      the engine at hand, or the whole script of another language, which
      the module runs as it is (an external alias of the file); `script`,
      a file that the user owns and the module runs as it is, with the
      interpreter of its extension (the external alias of the engine),
      copied beside the module when the program is written elsewhere;
      `alias`, the name of another process whose code this one runs under
      its own name and options; or none of them, for the code of a process
      of that name that a module loaded by the preamble of the program
      provides. A `script` or an `alias` may rename the options that the
      process passes on with `alias_opt_map`, the label of each option of
      this process to the one that the code expects (`{"-x": "-y"}`).
    - `description`, its description text.
    - `options`, the options that its tasks receive, a list of `opt(...)`
      and `flag(...)`; a label that ends in "-ith" is a fanout family.
    - the methods of a task, as files with the body that the editor takes:
      `skip` (whether a task is skipped), a Bash body, or a skip file in
      Python (`.py`) that defines `skip(task)`; `post` (run after the
      body) and `reset_outfiles` (what to remove before a rerun), Bash
      bodies.
    - its environments: `conda_envs`, a dict of the name of each Conda
      environment to its yml file, and `docker_imgs`, a list of Docker
      images; a path given instead is a file with the Bash body of the
      method.

    A relative path is taken from the directory of the Python file that
    creates the process (`base_dir` names another directory).
    `interface(...)` and `task_options(...)` give the variable part.
    """

    def __init__(
        self,
        name: str,
        code: str | Path | None = None,
        script: str | Path | None = None,
        alias: str | None = None,
        description: str = "",
        options: list[_ReceivedOption] | tuple[_ReceivedOption, ...] = (),
        alias_opt_map: dict[str, str] | None = None,
        base_dir: str | Path | None = None,
        skip: str | Path | None = None,
        post: str | Path | None = None,
        reset_outfiles: str | Path | None = None,
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
        self.name = name
        self.description = description
        self.base_dir = Path(base_dir) if base_dir is not None else _caller_dir()
        self.code_path = self._resolve(code)
        # The script as given: when relative, it is also how the module
        # refers to it (see Program.write)
        self.script_given = str(script) if script is not None else None
        self.script_path = self._resolve(script)
        self.alias = alias
        self.alias_opt_map = MappingProxyType(dict(alias_opt_map or {}))
        # The language is that of the extension, which loading reads again
        self._check_language(self.code_path or self.script_path)
        self.options = self._received_options(options)
        # The environments given as data, and the files of the methods, by
        # the name of the method in the topology file
        self.conda_envs = MappingProxyType(_conda_envs_data(name, conda_envs))
        self.docker_imgs = tuple(_docker_imgs_data(name, docker_imgs))
        method_paths: dict[str, Path] = {}
        for method, path in (
            ("skip", skip),
            ("post", post),
            ("reset_outfiles", reset_outfiles),
            ("conda_envs", conda_envs),
            ("docker_imgs", docker_imgs),
        ):
            if isinstance(path, (str, Path)):
                method_paths[method] = self._resolve(path)
        for method, path in method_paths.items():
            if method != "skip" and func_language(path) == "python":
                raise DefinitionError(
                    f'Process "{name}": {path.name} is a Python file, and only the skip method '
                    "takes one; give the body of this method in Bash."
                )
        self.method_paths = MappingProxyType(method_paths)
        self.skip_language = func_language(method_paths.get("skip"))
        self._interface = _Interface({}, {}, {})
        self._task_options = _TaskOptions({}, "standard", None, {})
        self._frozen = True

    def __setattr__(self, attribute, value):
        if getattr(self, "_frozen", False) and attribute in _INVARIANT:
            raise DefinitionError(
                f'Process "{self.name}": {attribute} belongs to the invariant part of the process, '
                "which nothing changes once the process is created."
            )
        super().__setattr__(attribute, value)

    def __repr__(self) -> str:
        return f'Process("{self.name}")'

    def _resolve(self, path) -> Path | None:
        if path is None:
            return None
        path = Path(path)
        return path if path.is_absolute() else self.base_dir / path

    def _check_language(self, path: Path | None) -> None:
        if path is not None and path.suffix[1:] not in LANGUAGE_BY_EXTENSION:
            raise DefinitionError(
                f'Process "{self.name}": the extension of {path.name} tells no language (.sh, .py, '
                ".pl, .r or .R, .groovy)."
            )

    def _received_options(self, options) -> tuple[Option, ...]:
        received: list[Option] = []
        for spec in options:
            if not isinstance(spec, _ReceivedOption):
                raise DefinitionError(
                    f'Process "{self.name}": its options are given with opt(...) and flag(...), not {spec!r}.'
                )
            self._check_label(spec.label)
            self._check_data_type(spec.label, spec.data_type, allow_flag=True)
            if any(option.label == spec.label for option in received):
                raise DefinitionError(f'Process "{self.name}" lists option "{spec.label}" twice.')
            received.append(Option(self, spec.label, spec.data_type, spec.description))
        return tuple(received)

    def _check_label(self, label: str) -> None:
        problem = option_label_problem(label)
        if problem is not None:
            raise DefinitionError(f'Option "{label}" of process "{self.name}": {problem}')

    def _check_data_type(self, label: str, data_type: str, allow_flag: bool) -> None:
        if data_type in DATA_TYPES or (allow_flag and data_type == "None"):
            return
        raise DefinitionError(
            f'Option "{label}" of process "{self.name}": unknown data type "{data_type}" (one of '
            + ", ".join(DATA_TYPES)
            + (', or a flag(...)).' if allow_flag else ").")
        )

    # --- options -------------------------------------------------------------

    def __getitem__(self, label: str) -> Option:
        """The received option of the process with the label `label`, such
        as `generate["-outf"]`, to give as the source of a connection;
        DefinitionError when the process has none."""
        return self._received(label, "an option")

    def _find(self, label: str) -> Option | None:
        return next((option for option in self.options if option.label == label), None)

    def _received(self, label: str, what: str) -> Option:
        option = self._find(label)
        if option is None:
            raise DefinitionError(
                f'Process "{self.name}": {what} names "{label}", which is not an option that the '
                "process receives (see its options=)."
            )
        return option

    # --- the interface -------------------------------------------------------

    def interface(
        self,
        cmdline: dict[str, str] | None = None,
        shaping: dict[str, tuple[str, str]] | None = None,
        external: dict[str, str] | None = None,
    ) -> Process:
        """
        Gives what the process receives from outside the program, replacing
        any interface given before:

        - `cmdline`, the received options whose value comes from the
          command line of the run, each "mandatory" or "optional" (a flag
          is "optional");
        - `shaping`, the task shaping options, each with its data type and
          its description (`{"-w": ("int", "Number of workers.")}`), which
          the tasks file of an array or a generator reads and no task
          receives;
        - `external`, the received inputs that a FIFO fed from outside the
          program delivers, each with the name of its FIFO, in a resident
          program.

        Returns the process.
        """
        cmdline = dict(cmdline or {})
        shaping = dict(shaping or {})
        external = dict(external or {})
        mandatory: dict[str, bool] = {}
        for label, kind in cmdline.items():
            option = self._received(label, "the command line of its interface")
            if kind not in ("mandatory", "optional"):
                raise DefinitionError(
                    f'Option "{label}" of process "{self.name}": a command line option is "mandatory" or '
                    f'"optional", not "{kind}".'
                )
            if option.data_type == "None" and kind == "mandatory":
                raise DefinitionError(f'Option "{label}" of process "{self.name}": a flag is "optional".')
            if option.direction != "input":
                raise DefinitionError(
                    f'Option "{label}" of process "{self.name}" is an output, which the command line does not give.'
                )
            mandatory[label] = kind == "mandatory"
        for label, spec in shaping.items():
            if any(option.label == label for option in self.options):
                raise DefinitionError(
                    f'Option "{label}" of process "{self.name}" is received by its tasks, and a task shaping '
                    "option is received by none: remove it from options= or from shaping."
                )
            if not (isinstance(spec, tuple) and len(spec) == 2 and all(isinstance(part, str) for part in spec)):
                raise DefinitionError(
                    f'Option "{label}" of process "{self.name}": a task shaping option is given as its data '
                    'type and its description, ("int", "Number of workers.").'
                )
            self._check_label(label)
            self._check_data_type(label, spec[0], allow_flag=False)
            if option_direction(label) != "input":
                raise DefinitionError(
                    f'Option "{label}" of process "{self.name}": a task shaping option is an input, and the '
                    'engine takes a label that starts with "-out" or "--out" as an output.'
                )
        for label, name in external.items():
            option = self._received(label, "the external FIFOs of its interface")
            if option.direction != "input":
                raise DefinitionError(
                    f'Option "{label}" of process "{self.name}" is an output, and an external FIFO is an '
                    "input fed from outside the program."
                )
            if not isinstance(name, str) or not name:
                raise DefinitionError(
                    f'Option "{label}" of process "{self.name}": an external FIFO is given the name of its FIFO.'
                )
            if label in cmdline:
                raise DefinitionError(
                    f'Option "{label}" of process "{self.name}" is both on the command line and fed from outside.'
                )
        self._interface = _Interface(mandatory, shaping, external)
        return self

    # --- the task options ----------------------------------------------------

    def task_options(
        self,
        values: dict[str, str | bool | _Value] | None = None,
        array: str | Path | None = None,
        generator: str | Path | None = None,
        count: dict[str, str] | None = None,
    ) -> Process:
        """
        Gives the shape of the tasks of the process and the value of each
        option of a task, replacing any task options given before:

        - one task, without `array` and `generator`; several, with a tasks
          file: `array`, a Bash file that builds the array of the tasks,
          under the name `array`, or a Python file whose `tasks(run)`
          returns its elements, after which every option is defined once
          per element, with `${task_idx}` and `${array[$task_idx]}` at
          hand in its value; `generator`, a Bash file that prints the
          number of tasks, or a Python file whose `tasks(run)` returns it,
          the options of each task being defined from `${task_idx}`;
        - `values`, the value of each received option that is neither on
          the command line nor fed from outside: a string, a literal value
          (see in_outdir), `True` for a flag set in every task, or one of
          connect, outdir, shared_dir, procspec, value_desc and fifo;
        - `count`, the count source of each fanout family, the label of a
          command line option of the process; a family without one is
          counted by the tasks of the process at the other end of its
          connection.

        Returns the process.
        """
        values = dict(values or {})
        count = dict(count or {})
        if array is not None and generator is not None:
            raise DefinitionError(f'Process "{self.name}" gives both array= and generator=: give one.')
        for label, value in values.items():
            option = self._received(label, "its task options")
            self._check_value(option, value)
        for label, source in count.items():
            option = self._received(label, "the count of its task options")
            if not is_family(label):
                raise DefinitionError(
                    f'Option "{label}" of process "{self.name}" is given a count, which only a fanout family '
                    '(a label that ends in "-ith") takes.'
                )
            if not isinstance(source, str):
                raise DefinitionError(
                    f'Option "{label}" of process "{self.name}": a count is the label of a command line '
                    "option of the process."
                )
        mode, tasks = ("array", array) if array is not None else ("generator", generator) if generator is not None else ("standard", None)
        self._task_options = _TaskOptions(values, mode, self._resolve(tasks), count)
        return self

    def _check_value(self, option: Option, value) -> None:
        where = f'Option "{option.label}" of process "{self.name}"'
        if value is True:
            if option.data_type != "None":
                raise DefinitionError(f"{where} is not a flag, and only a flag is set with True.")
            return
        if option.data_type == "None":
            raise DefinitionError(f"{where} is a flag, which is set in every task with True and given nothing else.")
        if isinstance(value, str):
            return
        if not isinstance(value, _Value):
            raise DefinitionError(
                f"{where}: a value is a string, True for a flag, or one of connect, outdir, shared_dir, "
                f"procspec, value_desc and fifo, not {value!r}."
            )
        if value.direction is not None and value.direction != option.direction:
            raise DefinitionError(f"{where} is an {option.direction}, and a {value.kind} is an {value.direction}.")
        if value.mirror and option.direction != "output":
            raise DefinitionError(f"{where} is an input, and only an output FIFO is mirrored.")

    # --- what the program reads ----------------------------------------------

    @property
    def mode(self) -> str:
        """The mode of the options handler: standard, array or generator."""
        return self._task_options.mode

    @property
    def tasks_path(self) -> Path | None:
        return self._task_options.tasks_path

    def check_parts(self) -> None:
        """
        Checks the parts of the process against each other, as the program
        model is built, since they may be given in any order: an option on
        the command line or fed from outside has no value in the task
        options, every received option is on the command line, fed from
        outside or given a value, task shaping options need an array or a
        generator, and a count names a command line option of the process.
        """
        interface, task_options = self._interface, self._task_options
        outside = {**{label: "on the command line" for label in interface.cmdline},
                   **{label: "fed from outside" for label in interface.external}}
        for label in task_options.values:
            if label in outside:
                raise DefinitionError(
                    f'Option "{label}" of process "{self.name}" is {outside[label]} and has a value in its task '
                    "options too: give it in one place."
                )
        missing = [option.label for option in self.options if option.label not in outside and option.label not in task_options.values]
        if missing:
            raise DefinitionError(
                f'Process "{self.name}": option(s) {", ".join(missing)} are neither on the command line, nor '
                "fed from outside, nor given a value in its task options."
            )
        if interface.shaping and task_options.mode == "standard":
            raise DefinitionError(
                f'Process "{self.name}" has task shaping options ({", ".join(interface.shaping)}) and one task: '
                "only the tasks file of an array or a generator reads them."
            )
        for label, source in task_options.count.items():
            if source not in interface.cmdline:
                raise DefinitionError(
                    f'Option "{label}" of process "{self.name}" is counted by "{source}", which is not a command '
                    "line option of the process."
                )


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
    same code as import, and refuses what the web UI could not hold. Its
    ports are its options, given its interface and its task options as
    those of any process. Whether it is an initiator, where a round
    starts, is said when a program adds it.
    """

    def __init__(
        self,
        name: str,
        code: str | Path,
        description: str = "",
        options: list[_ReceivedOption] | tuple[_ReceivedOption, ...] = (),
        base_dir: str | Path | None = None,
    ):
        super().__init__(
            name, code=code, description=description, options=options, base_dir=base_dir
        )

    def __repr__(self) -> str:
        return f'Node("{self.name}")'


class Supervisor(Process):
    """
    The Supervisor of a resident program, which watches its nodes and
    relaunches one that goes down. It has no code and no options of its
    own: script generation writes its whole class and its wiring.
    """

    def __init__(self, name: str, description: str = "", base_dir: str | Path | None = None):
        super().__init__(name, description=description, base_dir=base_dir)

    def __repr__(self) -> str:
        return f'Supervisor("{self.name}")'

    def interface(self, *args, **kwargs) -> Process:
        raise DefinitionError(f'Supervisor "{self.name}" has no options, and so no interface.')

    def task_options(self, *args, **kwargs) -> Process:
        raise DefinitionError(f'Supervisor "{self.name}" has no options, and so no task options.')
