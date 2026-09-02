import os
import re
import subprocess
import uuid
from pathlib import Path
from typing import Literal

from . import paths
from .markdown_parsing import ProcessInfoOption, parse_proc_info_markdown
from .models import (
    AdditionalSpecs,
    ComputationalSpecs,
    ExecutionOptions,
    Position,
    Program,
    ProgramEdge,
    ProgramOption,
    ProgramProcess,
)
from .option_handler_import import ConnectionRef, resolve_options_handler

_DOC_MOD_TOOL_NAME = "debasher_doc_mod"

# Editor convenience: a script that hangs while loading (a broken/looping
# preamble) should just fail the import rather than block the request.
_DOC_MOD_TIMEOUT_SECS = 20

# Default layout for imported processes: debasher_doc_mod's output
# carries no position information, so processes are laid out in layers
# by data-flow depth (see _layout_processes) instead of just stacking
# them in script-declaration order.
_PROCESS_START_X = 100.0
_PROCESS_START_Y = 100.0
_PROCESS_X_SPACING = 220.0
_PROCESS_Y_SPACING = 160.0

_MODULE_TITLE_RE = re.compile(r"^# (?P<name>.+)$")
_PROCESS_HEADING_RE = re.compile(r"^## (?P<name>.+)$")

# A top-level bash function definition header — "name()", "name ()",
# "name() {", or the same with a leading "function " keyword — anchored
# to column 0 since that's how every function is written throughout
# data/programs (including the occasional brace-on-the-same-line style,
# e.g. debasher_dynamic_fanout.sh's count_chars() {).
_FUNCTION_DEF_RE = re.compile(r"^(?:function\s+)?[A-Za-z_][A-Za-z0-9_]*\s*\(\s*\)\s*\{?\s*$")


def _option_direction(label: str) -> Literal["input", "output"]:
    """Mirrors frontend/src/models/option.ts's getOptionDirection."""
    return "output" if label.startswith("-out") or label.startswith("--out") else "input"


def _to_program_option(info: ProcessInfoOption) -> ProgramOption:
    return ProgramOption(
        id=str(uuid.uuid4()),
        label=info.label,
        direction=_option_direction(info.label),
        dataType=info.dataType,
        description=info.description,
        value="",
        commandLine=info.commandLine,
        mandatory=info.mandatory,
    )


def _synthesized_option(label: str) -> ProgramOption:
    """
    A minimal stand-in ProgramOption for a label that a recovered
    connection references but that debasher_doc_mod's "Process Options"
    section never declared — expected for array-mode processes, whose
    per-task options (e.g. an -id or a connected -in built directly in
    generate_opts) commonly aren't pre-declared via explain_opt at all
    (see debasher_host_workflow.sh's host2, whose "-inf" only exists
    inside generate_opts). Without this, such a connection would have
    nowhere in the canvas to attach its edge to.
    """
    return ProgramOption(
        id=str(uuid.uuid4()),
        label=label,
        direction=_option_direction(label),
        dataType="string",
        description="",
        value="",
        commandLine=False,
        mandatory=False,
    )


def _to_float(raw: str) -> float | None:
    try:
        return float(raw)
    except ValueError:
        return None


def _to_computational_specs(raw: dict[str, str]) -> ComputationalSpecs:
    """
    Maps debasher::_show_proc_specs's raw "### Computational
    Specifications" attribute dict (engine attribute names: cpus, mem,
    time, plus nodes/account/partition/throttle which ComputationalSpecs
    doesn't model and are ignored here) onto the app's typed
    ComputationalSpecs.
    """
    cpus = raw.get("cpus")
    mem = raw.get("mem")
    return ComputationalSpecs(
        cpus=_to_float(cpus) if cpus is not None else None,
        mem=_to_float(mem) if mem is not None else None,
        time=raw.get("time"),
    )


def _to_additional_specs(raw: dict[str, str]) -> AdditionalSpecs:
    """
    Maps debasher::_show_proc_specs's raw "### Additional
    Specifications" attribute dict onto the app's typed AdditionalSpecs.
    "force" (engine value "yes" — see script_generation.py's
    _additional_specs_str) is treated as a boolean by presence alone, so
    unlike the other fields it isn't passed through by value.
    """
    return AdditionalSpecs(
        force="force" in raw,
        processdeps=raw.get("processdeps"),
        alias=raw.get("alias"),
        externalAlias=raw.get("ext_alias"),
    )


def _parse_module_markdown(markdown: str) -> tuple[str, str, list[tuple[str, str]]]:
    """
    Split debasher_doc_mod's output into the module name, its
    description, and a (process name, per-process Markdown) pair for
    each "## <process>" section — each of which
    markdown_parsing.parse_proc_info_markdown can parse on its own,
    exactly as it does for a single-process debasher_get_proc_info
    block.
    """
    name = ""
    description_lines: list[str] = []
    processes: list[tuple[str, str]] = []

    current_process_name: str | None = None
    current_process_lines: list[str] = []

    def flush_process() -> None:
        if current_process_name is not None:
            processes.append((current_process_name, "\n".join(current_process_lines)))

    lines = markdown.splitlines()
    start = 0
    if lines:
        title_match = _MODULE_TITLE_RE.match(lines[0])
        if title_match:
            name = title_match.group("name").strip()
            start = 1

    for line in lines[start:]:
        heading_match = _PROCESS_HEADING_RE.match(line)
        if heading_match:
            flush_process()
            current_process_name = heading_match.group("name").strip()
            current_process_lines = []
        elif current_process_name is not None:
            current_process_lines.append(line)
        else:
            description_lines.append(line)
    flush_process()

    description = "\n".join(description_lines).strip()

    return name, description, processes


def _extract_preamble(script_path: Path) -> str:
    """
    Heuristic recovery of the program's preamble: debasher_doc_mod's
    Markdown carries no such notion at all (it only ever *runs* the
    script's _program function to register processes, so whatever
    precedes the first function definition — a shebang, comments,
    `source`/`load_debasher_module` calls, constants — is just skipped
    over rather than documented anywhere). Since the frontend's own
    preamble is exactly "raw bash inserted verbatim before every
    function definition" (see script_generation.py's _add_preamble),
    everything in the script itself up to (not including) its first
    top-level function definition is that same thing, read back out.
    """
    try:
        lines = script_path.read_text().splitlines()
    except OSError:
        return ""

    for index, line in enumerate(lines):
        if _FUNCTION_DEF_RE.match(line):
            return "\n".join(lines[:index]).rstrip()

    return "\n".join(lines).rstrip()


def run_doc_mod(script_path: Path, debasher_mod_dir: str = "") -> str:
    """
    Run debasher_doc_mod over `script_path` and return its Markdown
    documentation (program name/description, and per-process
    description/options/implementation).

    `debasher_mod_dir`, if given, is forwarded as DEBASHER_MOD_DIR so
    the script's own `load_debasher_module` calls (for shared modules
    outside its own directory) can resolve — mirroring how
    routers/execution.py's _debasher_env and routers/processes.py's
    _run_preamble_tool forward it from a program's own envVars. Here
    there's no program yet, so it comes straight from the import
    request instead.
    """
    tool = paths.find_bin_tool(_DOC_MOD_TOOL_NAME)
    if tool is None:
        raise RuntimeError(f"{_DOC_MOD_TOOL_NAME} tool not found")

    env = os.environ.copy()
    env["DEBASHER_MOD_DIR"] = debasher_mod_dir

    try:
        result = subprocess.run(
            [
                str(tool),
                "-m",
                str(script_path),
                "--show-opts",
                "--show-opthnd",
                "--show-impl",
                "--show-specs",
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=_DOC_MOD_TIMEOUT_SECS,
        )
    except subprocess.TimeoutExpired as err:
        raise RuntimeError(f"Timed out running {_DOC_MOD_TOOL_NAME} on {script_path}") from err

    if result.returncode != 0:
        raise RuntimeError(
            f"{_DOC_MOD_TOOL_NAME} failed on {script_path}: {result.stderr.strip()}"
        )

    return result.stdout


def _build_edges(
    processes: list[ProgramProcess],
    pending_connections: list[tuple[str, ConnectionRef]],
) -> list[ProgramEdge]:
    """
    Resolves each recovered ConnectionRef — process/option names, as
    parsed from source — against the actual processes/options built for
    this import (which have ids). A connection naming a process that
    isn't part of this program (e.g. one from a different, separately-
    loaded module) is silently dropped rather than left dangling. An
    option that IS part of this program's processes but was never
    declared via explain_opt — array-mode processes routinely define
    per-task options (e.g. an -id, or a connected -in) directly inside
    generate_opts with no matching explain_opt call, so debasher_doc_mod
    never lists them — gets a minimal synthesized ProgramOption instead,
    so the edge still has somewhere to attach in the canvas.
    """
    processes_by_name = {process.name: process for process in processes}
    edges: list[ProgramEdge] = []

    for target_process_name, connection in pending_connections:
        target_process = processes_by_name.get(target_process_name)
        source_process = processes_by_name.get(connection.source_process)
        if target_process is None or source_process is None:
            continue

        target_option = next(
            (option for option in target_process.options if option.label == connection.option_label),
            None,
        )
        if target_option is None:
            target_option = _synthesized_option(connection.option_label)
            target_process.options.append(target_option)

        source_option = next(
            (option for option in source_process.options if option.label == connection.source_option),
            None,
        )
        if source_option is None:
            source_option = _synthesized_option(connection.source_option)
            source_process.options.append(source_option)

        edges.append(
            ProgramEdge(
                id=str(uuid.uuid4()),
                sourceProcessId=source_process.id,
                sourceOptionId=source_option.id,
                targetProcessId=target_process.id,
                targetOptionId=target_option.id,
            )
        )

    return edges


def _layout_processes(processes: list[ProgramProcess], edges: list[ProgramEdge]) -> None:
    """
    Positions processes in layers by data-flow depth, so a process
    feeding another's input via a recovered connection is placed above
    it (smaller y) rather than in raw script-declaration order — mutates
    each process's `position` in place.

    Layer assignment is longest-path relaxation (Bellman-Ford-style): a
    target's layer is pushed below its source's on every pass, repeated
    until nothing changes. DeBasher explicitly allows cyclic process
    dependencies (e.g. debasher_cycle_state.sh), which would make that
    relaxation loop forever chasing an ever-growing layer around the
    cycle — so passes are capped at len(processes): every node can gain
    at most one extra layer per full pass over all edges, so that many
    passes is always enough to reach the fixpoint for the acyclic part
    of the graph, and for a cyclic part it just guarantees termination
    with a bounded (not necessarily "correct", since no single layering
    is correct for a cycle) result rather than hanging.

    Processes sharing a layer are placed side by side, left to right in
    their original script order, for a deterministic layout.
    """
    layer = {process.id: 0 for process in processes}

    for _ in range(len(processes)):
        changed = False
        for edge in edges:
            if edge.sourceProcessId not in layer or edge.targetProcessId not in layer:
                continue
            candidate = layer[edge.sourceProcessId] + 1
            if candidate > layer[edge.targetProcessId]:
                layer[edge.targetProcessId] = candidate
                changed = True
        if not changed:
            break

    next_x_by_layer: dict[int, float] = {}
    for process in processes:
        process_layer = layer[process.id]
        x = next_x_by_layer.get(process_layer, _PROCESS_START_X)
        process.position = Position(x=x, y=_PROCESS_START_Y + process_layer * _PROCESS_Y_SPACING)
        next_x_by_layer[process_layer] = x + _PROCESS_X_SPACING


def import_program_from_script(script_path: Path, debasher_mod_dir: str = "") -> Program:
    """
    Import a Program from an existing DeBasher script by running
    debasher_doc_mod over it and parsing the Markdown it generates.

    Beyond the program's name/description and each process's name,
    description, options, and implementation code, each process's
    options-handler mode, per-option values, and any process-to-process
    connections it implies are recovered on a best-effort basis by
    statically parsing its _define_opts/_generate_opts_size/
    _generate_opts source (see option_handler_import.py for the
    recovery rules and their limits — in particular, a process whose
    option definition uses control flow or a real per-task generator
    falls back to "manual"/"array" mode with its source kept verbatim,
    executing exactly as it originally did but without necessarily
    recovering every connection for the canvas). The preamble is
    recovered too, heuristically, by reading `script_path` itself rather
    than debasher_doc_mod's Markdown (see _extract_preamble). Each
    process's computational/additional specs are recovered from
    debasher_doc_mod's --show-specs output (see _to_computational_specs/
    _to_additional_specs). Everything else debasher_doc_mod doesn't
    document — execution/program options — is left at its blank/default
    value for the user to fill in.

    `debasher_mod_dir`, if given, is both forwarded to debasher_doc_mod
    (see run_doc_mod) and carried over into the imported program's own
    envVars, so it keeps working for that program afterwards (e.g. when
    running it, or re-fetching a process's info from its preamble).
    """
    markdown = run_doc_mod(script_path, debasher_mod_dir)
    name, description, process_chunks = _parse_module_markdown(markdown)

    processes: list[ProgramProcess] = []
    pending_connections: list[tuple[str, ConnectionRef]] = []

    for process_name, chunk in process_chunks:
        info = parse_proc_info_markdown(chunk)
        options = [_to_program_option(option) for option in info.options]

        result = resolve_options_handler(info.optionHandler)
        for option in options:
            value = result.option_values.get(option.label)
            if value is not None:
                option.value = value
            # channel is independent of dataType (see models.py): a
            # value_desc option is always output-direction (that call
            # defines an output's own value — the consuming side just
            # connects normally, it never marks itself value_desc), but
            # fifo isn't direction-restricted — a process can legitimately
            # open an *input* on a fifo it rendezvous on by name rather
            # than a plain connection (see debasher_cycle_trigger_
            # interactive.sh's worker, whose "-threshold" is a genuine
            # mandatory cmdline int internally sourced from a fifo).
            if option.direction == "output" and option.label in result.value_descriptor_labels:
                option.channel = "value_desc"
            if option.label in result.fifo_labels:
                option.channel = "fifo"

        pending_connections.extend((process_name, connection) for connection in result.connections)

        processes.append(
            ProgramProcess(
                id=str(uuid.uuid4()),
                name=process_name,
                description=info.description,
                position=Position(x=_PROCESS_START_X, y=_PROCESS_START_Y),
                options=options,
                optionsHandler=result.handler,
                language=info.language,
                code=info.code,
                computationalSpecs=_to_computational_specs(info.computationalSpecs),
                additionalSpecs=_to_additional_specs(info.additionalSpecs),
            )
        )

    edges = _build_edges(processes, pending_connections)
    _layout_processes(processes, edges)

    return Program(
        id=str(uuid.uuid4()),
        name=name,
        description=description,
        preamble=_extract_preamble(script_path),
        envVars={"DEBASHER_MOD_DIR": debasher_mod_dir} if debasher_mod_dir else {},
        homeDir="",
        outputDir="",
        sourceDir=str(script_path.resolve().parent),
        executionOptions=ExecutionOptions(scheduler=""),
        programOptions={},
        processes=processes,
        edges=edges,
    )
