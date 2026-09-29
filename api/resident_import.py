"""
Import of a resident program (see "Script generation and import of a
resident program" in doc/design_doc_webui.md), on top of that of a general
one: program_import.py reads the processes, their options and their
connections as for any program, and this module turns them into the nodes
of a resident program, or refuses the program.

- The code of every process is decomposed into the parts of a node (see
  resident_node_code.decompose_heredoc), which also gives its node kind.
- The Supervisor wiring is recognized by the roles of the ends of each fifo
  and removed (see resident_supervisor_wiring.strip_wiring), which also says
  which nodes are initiators.
- Whatever the web UI cannot hold is refused, the whole program at once,
  with an explanation for each place that does not fit: a resident program
  has no counterpart of the manual mode of a general one, since the parts
  of a node already cover what a node can do.
"""

import ast
from dataclasses import dataclass

from .models import ProgramEdge, ProgramProcess
from .resident_node_code import decompose_heredoc
from .resident_supervisor_wiring import strip_wiring


class ResidentImportRefused(RuntimeError):
    """A resident program that the web UI cannot hold, which the engine runs
    as it is. Its message lists every place that does not fit, and how to
    change the code to fit it."""


@dataclass
class _Problem:
    process: str
    line: int | None
    text: str

    def __str__(self) -> str:
        where = f"{self.process}, line {self.line}" if self.line else self.process
        return f"- {where}: {self.text}."


def _quoted_strings(source: str) -> dict[str, int]:
    """Every string constant of a heredoc, with the line of its first use."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    found: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.setdefault(node.value, node.lineno)
    return found


def _check_process(process: ProgramProcess) -> list[_Problem]:
    """What a process of a resident program holds that the web UI does not
    offer in one."""
    problems = []
    if process.optionsHandler.mode == "manual":
        problems.append(
            _Problem(
                process.name,
                None,
                "its option definition functions are outside what import understands, which "
                "a general program keeps in manual mode, a mode that a resident program does "
                "not offer: write them as flat calls of the define_* functions, or as the loop "
                "of an array",
            )
        )
    specs = process.additionalSpecs
    if specs.force or specs.processdeps or specs.alias or specs.externalAlias or specs.aliasOptMap:
        problems.append(
            _Problem(
                process.name,
                None,
                "it has additional specifications (force, processdeps, an alias or an external "
                "alias), which a resident program does not offer: remove them",
            )
        )
    if any(value for value in process.additionalMethods.model_dump().values()):
        problems.append(
            _Problem(
                process.name,
                None,
                "it has additional methods (reset_outfiles, post, outdir_basename, skip, "
                "conda_envs or docker_imgs), which a resident program does not offer: remove them",
            )
        )
    return problems


def import_resident_processes(processes: list[ProgramProcess], edges: list[ProgramEdge]) -> list[ProgramEdge]:
    """
    Turns the processes of an imported resident program into nodes, in
    place, and returns the connections that are not part of the Supervisor
    wiring. Raises ResidentImportRefused, listing every node that does not
    fit, when the web UI cannot hold the program.
    """
    problems: list[_Problem] = []
    decomposed = {}

    for process in processes:
        if process.language != "python" or not process.code:
            problems.append(
                _Problem(
                    process.name,
                    None,
                    "its code is not a Python heredoc, which every process of a resident program has",
                )
            )
            continue
        result = decompose_heredoc(process.code)
        decomposed[process.name] = result
        process.nodeKind = result.kind
        problems.extend(_Problem(process.name, misfit.line, f"{misfit.problem}; {misfit.fix}") for misfit in result.misfits)
        problems.extend(_check_process(process))

    stripped = strip_wiring(processes, edges)
    problems.extend(_Problem("the Supervisor wiring", None, problem) for problem in stripped.problems)

    # The code of a node that names a port of the wiring would stop working
    # once script generation writes the wiring again, under labels of its
    # own: the runtime gives each port the label of its option, without its
    # dash.
    for process in processes:
        ports = {label.lstrip("-") for label in stripped.removed_labels.get(process.name, set())}
        quoted = _quoted_strings(process.code)
        for port in sorted(ports & quoted.keys()):
            problems.append(
                _Problem(
                    process.name,
                    quoted[port],
                    f'the code names "{port}", a port of the Supervisor wiring, whose label script '
                    "generation may change; the runtime already handles that port by its role, so "
                    "remove the reference",
                )
            )

    if problems:
        problems.sort(key=lambda problem: (problem.process, problem.line or 0))
        raise ResidentImportRefused(
            "The web UI cannot hold this resident program, which the engine runs as it is. "
            "Change the code of these processes to fit the parts of a node, and import it again:\n"
            + "\n".join(str(problem) for problem in problems)
        )

    for process in processes:
        process.nodeCode = decomposed[process.name].code
        process.initiator = process.name in stripped.initiators
        process.language = "python"
        process.code = ""
    return stripped.edges
