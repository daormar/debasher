import re
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .debasher_constants import (
    PROCESS_METHOD_DEFINE_OPTS_SUFFIX,
    PROCESS_METHOD_GENERATE_OPTS_SIZE_SUFFIX,
    PROCESS_METHOD_GENERATE_OPTS_SUFFIX,
)
from .doc_mod import (
    parse_module_markdown,
    parse_program_type,
    run_doc_mod,
    run_doc_mod_all_shared_dirs,
    run_doc_mod_resolve_vars,
    run_get_verbatim_func_source,
    split_seq_process_chunks,
)
from .additional_methods_import import resolve_additional_methods
from .markdown_parsing import (
    ProcessInfoOption,
    function_header_name,
    parse_proc_info_markdown,
    split_function_blocks,
)
from .models import (
    AdditionalSpecs,
    AliasOptMapping,
    ComputationalSpecs,
    ExecutionOptions,
    OptionsHandler,
    Position,
    Program,
    ProgramEdge,
    ProgramOption,
    ProgramProcess,
    SeqAdditionalSpecs,
    SeqComputationalSpecs,
    SeqProcess,
)
from .option_handler_import import ConnectionRef, SharedDirRef, resolve_options_handler
from .resident_import import import_resident_processes
from .script_generation import SCRIPT_HEADER

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
    # The specifications that the nodes of a resident program read, which
    # debasher_doc_mod prints only when the process gives them.
    resident = {name: _to_float(raw[name]) for name in _RESIDENT_NUMERIC_SPECS if name in raw}
    if "max_concurrent_runs" in resident and resident["max_concurrent_runs"] is not None:
        resident["max_concurrent_runs"] = int(resident["max_concurrent_runs"])
    return ComputationalSpecs(
        cpus=_to_float(cpus) if cpus is not None else None,
        mem=_to_float(mem) if mem is not None else None,
        time=raw.get("time"),
        batch_sched=raw.get("batch_sched"),
        **resident,
    )


_RESIDENT_NUMERIC_SPECS = (
    "input_log_max_mb",
    "out_backlog_max_mb",
    "out_backlog_fail_mb",
    "gil_switch_interval_ms",
    "startup_timeout_s",
    "max_concurrent_runs",
    "heartbeat_timeout_s",
)


def _to_alias_opt_map(raw_value: str | None) -> list[AliasOptMapping]:
    """
    Parses the engine's "alias_opt_map" attribute value
    ("OLD:NEW[,OLD:NEW...]", see
    debasher::_validate_alias_opt_map in
    engine/debasher_lib_programs.sh) into the app's typed pairs.
    """
    if not raw_value:
        return []
    mappings = []
    for pair in raw_value.split(","):
        old, _, new = pair.partition(":")
        mappings.append(AliasOptMapping(fromLabel=old, toLabel=new))
    return mappings


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
        aliasOptMap=_to_alias_opt_map(raw.get("alias_opt_map")),
        externalAlias=raw.get("ext_alias"),
    )


def _verbatim_code(script_path: Path, code: str, debasher_mod_dir: str) -> str:
    """
    Best-effort upgrade of a process's `declare -f`-derived `code` (from
    debasher_doc_mod's Markdown, see parse_proc_info_markdown) to its
    exact original source -- comments and indentation intact -- via
    debasher_get_verbatim_func_source, run against the same script this
    program is being imported from.

    `code` may bundle more than one function -- debasher::_show_proc_
    implem_bash_func pulls in any same-script helper the exec function
    calls alongside it (see split_function_blocks) -- so each is
    resolved and upgraded independently and rejoined the same way,
    rather than resolving a single function name from `code`'s first
    line and upgrading the whole blob to just that one function's
    source (which would silently drop every other function in it).
    Falls back to a given function's own block unchanged whenever its
    upgrade isn't possible (see routers/processes.py's twin
    _verbatim_code for why: no header line to resolve a function name
    from, tool missing, or the underlying scan failing).
    """
    if not code:
        return code
    upgraded_blocks = []
    for block in split_function_blocks(code):
        funcname = function_header_name(block)
        verbatim = run_get_verbatim_func_source(script_path, funcname, debasher_mod_dir) if funcname else None
        upgraded_blocks.append(verbatim if verbatim else block)
    return "\n\n".join(upgraded_blocks)


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

    A script that script_generation.py wrote starts with its
    SCRIPT_HEADER line, which is not part of the preamble: it is left
    out, with the blank lines after it, so that importing a generated
    script and generating it again does not add one more header to the
    preamble every time.
    """
    try:
        lines = script_path.read_text().splitlines()
    except OSError:
        return ""

    if lines and lines[0] == SCRIPT_HEADER:
        lines = lines[1:]
        while lines and not lines[0].strip():
            lines = lines[1:]

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
    here, using `option_handler_code_by_process`'s already-`declare -f`-
    normalized source (mirroring resolve_options_handler's own fallback
    for an unparseable body) rather than resolve_options_handler's exact
    original source — this downgrade only fires for the rare
    unverifiable-connection case, so it hasn't been worth threading
    script_path/debasher_mod_dir through here too just to upgrade it the
    same way.
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


def _resolve_shared_dir_refs(
    processes: list[ProgramProcess],
    pending_shared_dir_refs: list[tuple[str, str, SharedDirRef]],
    script_path: Path,
    debasher_mod_dir: str,
) -> list[str]:
    """
    Tags each option named in `pending_shared_dir_refs` as
    channel="shared_dir" once its SharedDirRef (see
    option_handler_import.py) resolves to a name that's actually part of
    the program's real reachable shared-directory set
    (--show-all-shdirs) — a defensive cross-check, since in principle a
    variable could resolve to something that isn't a real shared
    directory at all. A ref that fails this check (an unresolved
    variable, or a name --show-all-shdirs doesn't know about) is left
    alone — the option keeps the plain literal value
    resolve_options_handler already gave it, exactly as if the ref had
    never been recognized.

    Returns the program's full reachable set (Program.
    availableSharedDirs) — computed here since it's already needed for
    the cross-check, off the same debasher_doc_mod call
    run_doc_mod_all_shared_dirs makes; empty (skipping that call
    entirely) when there's nothing to resolve.
    """
    if not pending_shared_dir_refs:
        return []

    all_shared_dirs = run_doc_mod_all_shared_dirs(script_path, debasher_mod_dir)
    all_shared_dirs_set = set(all_shared_dirs)

    var_names = sorted({ref.var_name for _, _, ref in pending_shared_dir_refs if ref.var_name})
    resolved_vars = run_doc_mod_resolve_vars(script_path, var_names, debasher_mod_dir) if var_names else {}

    processes_by_name = {process.name: process for process in processes}
    for process_name, option_label, ref in pending_shared_dir_refs:
        name = ref.literal_name if ref.literal_name is not None else resolved_vars.get(ref.var_name, "")
        if not name or name not in all_shared_dirs_set:
            continue
        process = processes_by_name.get(process_name)
        if process is None:
            continue
        option = next((o for o in process.options if o.label == option_label), None)
        if option is None:
            continue
        option.channel = "shared_dir"
        option.value = name

    return all_shared_dirs


def _build_shared_dir_edges(processes: list[ProgramProcess]) -> list[ProgramEdge]:
    """
    Synthesizes one edge for every (output, input) pair of "shared_dir"
    options naming the identical directory, across the whole program —
    mirrors what hand-connecting them in the canvas would produce (see
    frontend/src/models/connections.ts's isValidEdge's fan-in rule), so an
    imported program's canvas shows the same writer/reader relationships
    a hand-built one would. Purely documentary: script_generation.py's
    "shared_dir" codegen branch ignores connections entirely, so a
    program with N writers and M readers of the same directory gets
    N*M edges here, same as the editor's own fan-in already allows.
    """
    options_by_value: dict[str, list[tuple[ProgramProcess, ProgramOption]]] = {}
    for process in processes:
        for option in process.options:
            if option.channel == "shared_dir" and option.value:
                options_by_value.setdefault(option.value, []).append((process, option))

    edges: list[ProgramEdge] = []
    for owned_options in options_by_value.values():
        outputs = [pair for pair in owned_options if pair[1].direction == "output"]
        inputs = [pair for pair in owned_options if pair[1].direction == "input"]
        for source_process, source_option in outputs:
            for target_process, target_option in inputs:
                if source_process is target_process:
                    continue
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


def _to_seq_process(name: str, chunk: str, script_path: Path, debasher_mod_dir: str) -> SeqProcess:
    """
    A sequential process from its section of the module documentation (see
    doc_mod.split_seq_process_chunks), with its code replaced by its
    verbatim source as the code of a process is, and only the
    specifications that a sequential process has (see SeqComputationalSpecs
    and SeqAdditionalSpecs).
    """
    info = parse_proc_info_markdown(chunk)
    comp = _to_computational_specs(info.computationalSpecs)
    add = _to_additional_specs(info.additionalSpecs)
    return SeqProcess(
        id=str(uuid.uuid4()),
        name=name,
        description=info.description,
        language=info.language,
        code=_verbatim_code(script_path, info.code, debasher_mod_dir),
        computationalSpecs=SeqComputationalSpecs(cpus=comp.cpus, mem=comp.mem, time=comp.time),
        additionalSpecs=SeqAdditionalSpecs(
            alias=add.alias, aliasOptMap=add.aliasOptMap, externalAlias=add.externalAlias
        ),
    )


@dataclass
class _ReadModule:
    """What import reads of a module before it lays out its processes: its
    header, its processes and their connections, as for a general program."""

    name: str
    description: str
    shared_dirs: list[str]
    program_type: str
    processes: list[ProgramProcess]
    edges: list[ProgramEdge]
    available_shared_dirs: list[str]
    seq_processes: list[SeqProcess]


def _read_module(script_path: Path, debasher_mod_dir: str) -> _ReadModule:
    """Reads the processes of a module and their connections (see
    import_program_from_script), with no step of its own for a resident
    program."""
    markdown = run_doc_mod(script_path, debasher_mod_dir)
    name, description, shared_dirs, chunks = parse_module_markdown(markdown)
    process_chunks, seq_process_chunks = split_seq_process_chunks(chunks)
    program_type = parse_program_type(markdown)

    processes: list[ProgramProcess] = []
    pending_connections: list[tuple[str, ConnectionRef]] = []
    pending_shared_dir_refs: list[tuple[str, str, SharedDirRef]] = []
    option_handler_code_by_process: dict[str, dict[str, str]] = {}

    for process_name, chunk in process_chunks:
        info = parse_proc_info_markdown(chunk)
        options = [_to_program_option(option) for option in info.options]
        option_handler_code_by_process[process_name] = info.optionHandler

        result = resolve_options_handler(info.optionHandler, script_path, debasher_mod_dir)
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
            # interactive.sh's worker, whose "-threshold" is an input
            # fifo that something outside the program writes).
            if option.direction == "output" and option.label in result.value_descriptor_labels:
                option.channel = "value_desc"
            if option.label in result.fifo_labels:
                option.channel = "fifo"
            if option.label in result.mirrored_fifo_labels:
                option.mirror = True
            # The fifo tag of a resident program ("external" or "control"),
            # written where a general program writes --mirror.
            if option.channel == "fifo":
                option.fifoTag = result.fifo_tags.get(option.label)
            # Not a channel (see ProgramOption.fromProcessSpec) — a
            # process-spec-sourced option is an ordinary literal once
            # resolved, this only flags where the value in `option.value`
            # (the spec attribute's name, e.g. "cpus") came from.
            if option.label in result.procspec_labels:
                option.fromProcessSpec = True

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
        pending_shared_dir_refs.extend(
            (process_name, option_label, ref) for option_label, ref in result.shared_dir_refs.items()
        )

        processes.append(
            ProgramProcess(
                id=str(uuid.uuid4()),
                name=process_name,
                description=info.description,
                # The module says nothing about positions: the frontend
                # places the imported processes (see programLayout.ts).
                position=Position(x=0, y=0),
                options=options,
                optionsHandler=result.handler,
                language=info.language,
                code=_verbatim_code(script_path, info.code, debasher_mod_dir),
                computationalSpecs=_to_computational_specs(info.computationalSpecs),
                additionalSpecs=_to_additional_specs(info.additionalSpecs),
                additionalMethods=resolve_additional_methods(info.methods, script_path, debasher_mod_dir),
            )
        )

    _downgrade_unverifiable_task_indexed_connections(processes, pending_connections, option_handler_code_by_process)

    available_shared_dirs = _resolve_shared_dir_refs(
        processes, pending_shared_dir_refs, script_path, debasher_mod_dir
    )

    edges = _build_edges(processes, pending_connections) + _build_shared_dir_edges(processes)
    return _ReadModule(
        name=name,
        description=description,
        shared_dirs=shared_dirs,
        program_type=program_type,
        processes=processes,
        edges=edges,
        available_shared_dirs=available_shared_dirs,
        seq_processes=[
            _to_seq_process(seq_process_name, chunk, script_path, debasher_mod_dir)
            for seq_process_name, chunk in seq_process_chunks
        ],
    )


# The name of the module that read_preamble_processes writes around a
# preamble: a name that a module loaded by a preamble is unlikely to take.
_PREAMBLE_MODULE_NAME = "webui_preamble_processes"


def read_preamble_processes(
    preamble: str, process_names: list[str], debasher_mod_dir: str = ""
) -> tuple[list[ProgramProcess], list[ProgramEdge]]:
    """
    The processes that a preamble defines, `process_names` (see
    debasher_list_proc_names), and their connections, read as those of a
    resident module made of the preamble and a program that adds every one
    of them, so that a node can be read together with its Supervisor (see
    resident_import.reuse_node). Nothing is refused here.
    """
    if not process_names:
        return [], []
    name = _PREAMBLE_MODULE_NAME
    added = "\n".join(f'    add_debasher_process "{process}" ""' for process in process_names)
    module = (
        f"{preamble}\n\n"
        f"{name}_document()\n{{\n    :\n}}\n\n"
        f"{name}_shared_dirs()\n{{\n    :\n}}\n\n"
        f'{name}_program_type()\n{{\n    program_type "resident"\n}}\n\n'
        f"{name}_program()\n{{\n{added}\n}}\n"
    )
    with tempfile.TemporaryDirectory() as tmp_dir:
        script_path = Path(tmp_dir) / f"{name}.sh"
        script_path.write_text(module)
        read = _read_module(script_path, debasher_mod_dir)
    return read.processes, read.edges


def import_program_from_script(script_path: Path, debasher_mod_dir: str = "") -> Program:
    """
    Import a Program from an existing DeBasher script by running
    debasher_doc_mod over it and parsing the Markdown it generates.

    Beyond the program's name/description/shared directories (see
    parse_module_markdown, which requires debasher_doc_mod's
    --show-shdirs output, one of run_doc_mod's DEFAULT_FLAGS) and each
    process's name, description, options, and implementation code, each
    process's
    options-handler mode, per-option values, and any process-to-process
    connections it implies are recovered on a best-effort basis by
    statically parsing its _define_opts/_generate_opts_size/
    _generate_opts source (see option_handler_import.py for the
    recovery rules and their limits: a loop-shaped _define_opts
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
    document (execution/program options) is left at its blank/default
    value for the user to fill in.

    `debasher_mod_dir`, if given, is both forwarded to debasher_doc_mod
    (see run_doc_mod) and carried over into the imported program's own
    envVars, so it keeps working for that program afterwards (e.g. when
    running it, or re-fetching a process's info from its preamble).
    """
    read = _read_module(script_path, debasher_mod_dir)
    processes, edges = read.processes, read.edges
    if read.program_type == "resident":
        # Turns the processes into nodes and removes the Supervisor wiring,
        # or refuses the program (see resident_import.py).
        edges = import_resident_processes(processes, edges)

    return Program(
        id=str(uuid.uuid4()),
        name=read.name,
        programType=read.program_type,
        description=read.description,
        preamble=_extract_preamble(script_path),
        envVars={"DEBASHER_MOD_DIR": debasher_mod_dir} if debasher_mod_dir else {},
        homeDir="",
        outputDir="",
        sourceDir=str(script_path.resolve().parent),
        # Matches the frontend's ExecutionOptionsEditor/createEmptyProgram
        # default, so an imported program still gets a real --sched value
        # (see routers/execution.py) if it's run without ever opening
        # that dialog.
        executionOptions=ExecutionOptions(scheduler="BUILTIN"),
        programOptions={},
        sharedDirs=read.shared_dirs,
        availableSharedDirs=read.available_shared_dirs,
        processes=processes,
        seqProcesses=read.seq_processes,
        edges=edges,
    )
