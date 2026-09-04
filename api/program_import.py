import re
import uuid
from pathlib import Path
from typing import Literal

from .debasher_constants import (
    PROCESS_METHOD_DEFINE_OPTS_SUFFIX,
    PROCESS_METHOD_GENERATE_OPTS_SIZE_SUFFIX,
    PROCESS_METHOD_GENERATE_OPTS_SUFFIX,
)
from .doc_mod import parse_module_markdown, run_doc_mod
from .markdown_parsing import ProcessInfoOption, parse_proc_info_markdown
from .models import (
    AdditionalSpecs,
    ComputationalSpecs,
    ExecutionOptions,
    OptionsHandler,
    Position,
    Program,
    ProgramEdge,
    ProgramOption,
    ProgramProcess,
)
from .option_handler_import import ConnectionRef, resolve_options_handler

# Default layout for imported processes: debasher_doc_mod's output
# carries no position information, so processes are laid out in layers
# by data-flow depth (see _layout_processes) instead of just stacking
# them in script-declaration order.
_PROCESS_START_X = 100.0
_PROCESS_START_Y = 100.0
_PROCESS_X_SPACING = 220.0
_PROCESS_Y_SPACING = 160.0

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


# Modes whose resolved OptionsHandler guarantees a task N to actually
# pull from — mirrors script_generation.py's own _TASK_INDEXED_MODES.
_TASK_INDEXED_MODES = {"generator", "array"}


def _downgrade_unverifiable_task_indexed_connections(
    processes: list[ProgramProcess],
    pending_connections: list[tuple[str, ConnectionRef]],
    option_handler_code_by_process: dict[str, dict[str, str]],
) -> None:
    """
    A define_opt_from_proc_task_out "${idx_var}" connection only means
    "my task N pairs with the source's task N" if the source process is
    itself generator- or array-shaped, i.e. guaranteed to have a task N
    at all — script_generation.py only ever regenerates that for a pair
    both in _TASK_INDEXED_MODES (see _option_definition_line in
    script_generation.py). A process that resolved to "generator" or
    "array" mode via such a connection into a source outside that set
    (or an unrecognized one, e.g. a different module's) can't be
    faithfully regenerated that way, so it's downgraded to "manual"
    here, with its option-handler source kept verbatim — mirroring
    resolve_options_handler's own fallback for an unparseable body.
    """
    processes_by_name = {process.name: process for process in processes}

    for target_name, connection in pending_connections:
        if not connection.task_indexed:
            continue

        target = processes_by_name.get(target_name)
        if target is None or target.optionsHandler.mode not in _TASK_INDEXED_MODES:
            continue

        source = processes_by_name.get(connection.source_process)
        if source is not None and source.optionsHandler.mode in _TASK_INDEXED_MODES:
            continue

        raw = option_handler_code_by_process.get(target_name, {})
        if target.optionsHandler.mode == "generator":
            generate_opts_size = raw.get(PROCESS_METHOD_GENERATE_OPTS_SIZE_SUFFIX, "")
            generate_opts = raw.get(PROCESS_METHOD_GENERATE_OPTS_SUFFIX)
            combined = f"{generate_opts_size}\n\n{generate_opts}" if generate_opts else generate_opts_size
        else:  # "array"
            combined = raw.get(PROCESS_METHOD_DEFINE_OPTS_SUFFIX, "")
        target.optionsHandler = OptionsHandler(mode="manual", manualCode=combined)


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
    recovery rules and their limits — a loop-shaped _define_opts
    round-trips into "array" mode only when it matches
    script_generation.py's exact fixed shape; anything else with a loop,
    other control flow, or a real per-task generator that doesn't verify
    (see _downgrade_unverifiable_task_indexed_connections) falls back to
    "manual" with its source kept verbatim, executing exactly as it
    originally did but without necessarily recovering every connection
    for the canvas). The preamble is
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
    name, description, process_chunks = parse_module_markdown(markdown)

    processes: list[ProgramProcess] = []
    pending_connections: list[tuple[str, ConnectionRef]] = []
    option_handler_code_by_process: dict[str, dict[str, str]] = {}

    for process_name, chunk in process_chunks:
        info = parse_proc_info_markdown(chunk)
        options = [_to_program_option(option) for option in info.options]
        option_handler_code_by_process[process_name] = info.optionHandler

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

        # Resolve each recovered fanout family's count-source label (see
        # OptionHandlerResult.fanout_count_source_labels) into the
        # actual sibling ProgramOption's id, now that both have real
        # ones — mirrors OptionEditor.tsx's own dropdown, which stores
        # the same kind of same-process option reference.
        for fanout_label, count_source_label in result.fanout_count_source_labels.items():
            fanout_option = next((option for option in options if option.label == fanout_label), None)
            count_source_option = next((option for option in options if option.label == count_source_label), None)
            if fanout_option is not None and count_source_option is not None:
                fanout_option.countSourceOptionId = count_source_option.id

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

    _downgrade_unverifiable_task_indexed_connections(processes, pending_connections, option_handler_code_by_process)

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
