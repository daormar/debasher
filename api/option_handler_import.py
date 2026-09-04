"""
Recovers a process's OptionsHandler (and any process-to-process
connections implied by it) from the raw `declare -f` source of its
_define_opts/_generate_opts_size/_generate_opts functions — exposed by
debasher_doc_mod's --show-opthnd flag and pulled out per-function by
markdown_parsing.parse_option_handler.

Design (see program_import.py for how this plugs into the rest of the
import):

- _generate_opts_size and _generate_opts are meant to be provided
  jointly — the engine always calls the latter to retrieve a task's
  options once it has decided a process uses the generator mechanism at
  all (i.e. once _generate_opts_size exists), regardless of the
  size-only fast path some internal callers take — so that pair is the
  frontend's "generator" mode. _generate_opts_size's body, minus its
  fixed header (the same _define_opts header minus "local optlist=" —
  the engine calls it with the same 4 positional args, see
  debasher::_define_opts_generator), is kept verbatim as
  generatorSizeCode (like arrayCode for array mode)
  rather than matched against a grammar — its only contract is that it
  echoes the task count, so any implementation round-trips as long as
  that header is present in its exact fixed form (see
  _extract_generator_size_code). _generate_opts itself typically uses
  the exact same closed grammar of primitive calls as a plain
  _define_opts (just called once per task, with a task_idx argument
  available to it), so it's parsed the same way into per-option
  values/connections; only a body that can't be parsed that way falls
  back to "manual" with the pair kept verbatim.
- _define_opts is matched against the grammar of option-definition
  primitives (define_opt[_from_proc_out[_task_out]],
  define_cmdline_opt[_if_given], define_cmdline_flag_if_given,
  define_flag, define_value_desc_opt, define_fifo_opt[_generator] — all
  of them just other ways to define an option's value, not something
  exotic). A body that's exactly the standard boilerplate header/footer
  plus a flat sequence of those calls with literal label/proc/opt
  arguments round-trips structurally, so it's parsed into "standard"
  mode option values plus real connections.
- A loop, or any other statement outside that grammar, falls back to
  "manual" mode with _define_opts kept verbatim — UNLESS it matches
  script_generation.py's own fixed "array" shape exactly: the standard
  header minus its "local optlist=..." line, then arbitrary user code
  (kept verbatim as arrayCode) building a fixed-name array ("array"),
  then a `for idx in "${!array[@]}"; do` loop whose body is itself just
  a plain option-definition body — its own `local optlist=""`, the same
  closed grammar of option-definition primitives as "standard" mode
  (parsed the same way, just with "idx" in place of "task_idx" for a
  task-indexed connection), `save_opt_list optlist` — then `done` and
  nothing else. Every option is defined inside the loop this way, even
  one whose value doesn't depend on idx — array mode never hoists an
  idx-independent option out as a one-time "shared prefix". That
  round-trips into "array" mode; anything that deviates from this exact
  shape (a different loop form, extra statements after the loop, a
  differently named array/index, a hoisted option, ...) still falls
  back to "manual" as before, with the whole _define_opts kept verbatim
  (see _parse_array_define_opts).
- Both fallback (and generator's own unparseable-body fallback) still
  get a best-effort secondary scan for define_opt_from_proc_out/
  _task_out calls anywhere in the text, regardless of what surrounds
  them: for a process that falls back, script generation re-emits the
  captured source verbatim rather than deriving it from option
  values/edges, so a recovered edge there is purely a visual/documentary
  hint in the canvas — a wrong or missed one costs a click, not script
  correctness — which makes it safe to be permissive about.
"""

import re
from dataclasses import dataclass, field

from .debasher_constants import (
    PROCESS_METHOD_DEFINE_OPTS_SUFFIX,
    PROCESS_METHOD_GENERATE_OPTS_SIZE_SUFFIX,
    PROCESS_METHOD_GENERATE_OPTS_SUFFIX,
)
from .models import OptionsHandler


@dataclass
class ConnectionRef:
    option_label: str
    source_process: str
    source_option: str
    # True for a define_opt_from_proc_task_out "${task_idx}" connection —
    # program_import.py checks the source process actually resolved to
    # "generator" mode before trusting it, since script_generation.py
    # only ever regenerates ${task_idx} for that combination (see
    # _add_opts_definition_func).
    task_indexed: bool = False


@dataclass
class OptionHandlerResult:
    handler: OptionsHandler
    # Option label -> literal/expression value text, recovered only for
    # "standard"/"generator" modes (raw, unevaluated — codegen re-embeds
    # it as-is).
    option_values: dict[str, str] = field(default_factory=dict)
    connections: list[ConnectionRef] = field(default_factory=list)
    # Labels defined via define_value_desc_opt/define_fifo_opt[_generator]
    # — program_import.py sets their option's channel ("value_desc"/
    # "fifo") from these, independent of dataType. There's no
    # explain_opt-level signal for this (an option's declared type and
    # its actual delivery channel can legitimately diverge, e.g. a
    # mandatory cmdline int that's really sourced from a fifo), so this
    # is the sole source, recovered the same way as connections are —
    # best-effort in "manual" mode, exact otherwise.
    value_descriptor_labels: set[str] = field(default_factory=set)
    fifo_labels: set[str] = field(default_factory=set)
    # Fanout family option label (e.g. "-outfith") -> the label of the
    # command-line option on the SAME process that supplies its runtime
    # count (e.g. "-w") — see script_generation.py's
    # _fanout_definition_lines/_FANOUT_SUFFIX. Only ever populated for
    # "standard" mode (see _parse_primitive_calls's allow_fanout_blocks);
    # program_import.py resolves the label into an actual
    # ProgramOption.countSourceOptionId once both options have real ids.
    fanout_count_source_labels: dict[str, str] = field(default_factory=dict)


_HEADER_BOILERPLATE_RES = [
    re.compile(r"^local\s+cmdline=\$1$"),
    re.compile(r"^local\s+process_spec=\$2$"),
    re.compile(r"^local\s+process_name=\$3$"),
    re.compile(r"^local\s+process_outdir=\$4$"),
    re.compile(r"^local\s+task_idx=\$5$"),  # only present on _generate_opts
    re.compile(r'^local\s+optlist=("")?$'),
]
_FOOTER_BOILERPLATE_RES = [
    re.compile(r"^save_opt_list\s+optlist$"),
    re.compile(r"^return(\s+0)?$"),
]
_COMMENT_RE = re.compile(r"^#")

# A plain "local <name>=<expr>" line ahead of a call that uses it as a
# value, e.g. `local outf="${process_outdir}/${process_name}.out"` then
# `define_opt "-outf" "${outf}" optlist`: common enough (see
# debasher_value_pass_example.sh) to special-case rather than force
# every process using it into manual mode. Only a value token that's a
# *bare* reference to such a local — "${name}" or "$name" and nothing
# else — is substituted, with the local's own right-hand side text
# (quotes stripped, unevaluated); referencing it as part of a larger
# string, or a local whose value itself isn't a plain literal/expression
# line, isn't chased further and is left to the manual-mode fallback.
_LOCAL_ASSIGN_RE = re.compile(r"^local\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)=(?P<expr>.*)$")
_VAR_REF_RE = re.compile(r"^\$\{?(?P<name>[A-Za-z_][A-Za-z0-9_]*)\}?$")


def _strip_one_quote_layer(text: str) -> str:
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        return text[1:-1]
    return text


_DEFINE_OPTS_CALL_RE = re.compile(
    r"^(?:debasher::)?(?P<func>define_cmdline_flag_if_given|define_cmdline_opt_if_given|"
    r"define_cmdline_opt|define_value_desc_opt|define_fifo_opt_generator|define_fifo_opt|"
    r"define_flag|define_opt_from_proc_task_out|define_opt_from_proc_out|define_opt)"
    r"(?:\s+(?P<args>.*?))?\s*(?:\|\|.*)?$"
)
_TOKEN_RE = re.compile(r'"(?P<q>[^"]*)"|(?P<bare>\S+)')

# Expected exact token count per call, matching each function's real
# positional-argument signature (engine/debasher_lib_opts).
_CALL_TOKEN_COUNTS = {
    "define_cmdline_flag_if_given": 3,  # <cmdline> <label> <optlist>
    "define_cmdline_opt_if_given": 3,
    "define_cmdline_opt": 3,
    "define_flag": 2,  # <label> <optlist>
    "define_value_desc_opt": 2,  # <label> <optlist>
    "define_fifo_opt": 3,  # <label> <fifoname> <optlist>
    "define_fifo_opt_generator": 4,  # <label> <fifoname> <task_idx> <optlist>
    "define_opt_from_proc_out": 4,  # <label> <proc> <opt> <optlist>
    "define_opt_from_proc_task_out": 5,  # <label> <proc> <task_idx> <opt> <optlist>
    "define_opt": 3,  # <label> <value> <optlist>
}

def _idx_var_re(idx_var: str) -> re.Pattern:
    return re.compile(rf"^\$\{{?{re.escape(idx_var)}\}}?$")

_CONNECTION_SCAN_RE = re.compile(
    r'(?:debasher::)?define_opt_from_proc_out\s+"(?P<label>[^"]*)"\s+'
    r'"(?P<proc>[^"]*)"\s+"(?P<opt>[^"]*)"'
)
# The per-task variant (used by real generator/array generate_opts or
# define_opts loop bodies, see debasher_generator_example.sh) takes the
# connected task index as its 3rd argument instead — same connection,
# one arg later.
_TASK_CONNECTION_SCAN_RE = re.compile(
    r'(?:debasher::)?define_opt_from_proc_task_out\s+"(?P<label>[^"]*)"\s+'
    r'"(?P<proc>[^"]*)"\s+[^\s]+\s+"(?P<opt>[^"]*)"'
)
_VALUE_DESC_SCAN_RE = re.compile(r'(?:debasher::)?define_value_desc_opt\s+"(?P<label>[^"]*)"')
_FIFO_SCAN_RE = re.compile(r'(?:debasher::)?define_fifo_opt(?:_generator)?\s+"(?P<label>[^"]*)"')


def _function_body_lines(source: str) -> list[str] | None:
    """
    Strips a `declare -f` dump ("<name> ()\\n{\\n ... \\n}") down to its
    body, one stripped statement per line. None if the source doesn't
    have that exact three-part shape (header, opening brace, closing
    brace) — declare -f always produces it, so this only trips on
    malformed/truncated input.

    declare -f also reprints every simple statement with its trailing
    ";" statement terminator, even when the original source had one
    statement per line and never needed it (bash normalizes this) — so
    a single trailing ";" is stripped from each line here rather than
    threading that through every regex below.
    """
    lines = source.splitlines()
    if len(lines) < 3:
        return None
    if lines[1].strip() != "{" or lines[-1].strip() != "}":
        return None

    body = []
    for line in lines[2:-1]:
        stripped = line.strip()
        if stripped.endswith(";"):
            stripped = stripped[:-1].rstrip()
        body.append(stripped)
    return body


def _tokenize(args: str) -> list[tuple[str, bool]]:
    """
    Splits a call's argument text into (text, is_literal) pairs.
    Double-quoted text with no "$"/backtick inside is literal — usable
    as a static label/proc/opt name; anything else (bare words,
    interpolated strings) is not, but its raw text is still returned
    since a value argument (unlike a label/proc/opt one) is carried
    through unevaluated regardless of literalness.
    """
    tokens = []
    for match in _TOKEN_RE.finditer(args):
        if match.group("q") is not None:
            text = match.group("q")
            tokens.append((text, "$" not in text and "`" not in text))
        else:
            tokens.append((match.group("bare"), False))
    return tokens


# Fanout block (see script_generation.py's _fanout_definition_lines).
# Written by script_generation.py as:
#     local <var>=$(debasher::read_opt_value_from_line "${cmdline}" "<count_label>")
#     for ((i=0; i<<var>; i++)); do
#         <one define_opt or define_opt_from_proc_task_out call, label "<base>${i}">
#     done
# but `declare -f` always reprints a for loop's "do" on its own line
# (verified against real bash — same as _ARRAY_FOR_RE/_ARRAY_DO_LINE's
# "for idx in ...; do" below), so the shape actually recovered here is
# five lines: the count-read, the bare "for ((...))" header, "do", the
# one inner call, "done". Recognized as a unit (see
# _try_parse_fanout_block) only when allow_fanout_blocks is set — i.e.
# only inside a "standard"-mode _define_opts body, never inside
# array/generator ones, which have no notion of a fanout family option.
_FANOUT_COUNT_RE = re.compile(
    r'^local\s+(?P<var>[A-Za-z_][A-Za-z0-9_]*)=\$\(debasher::read_opt_value_from_line'
    r'\s+"\$\{cmdline\}"\s+"(?P<count_label>[^"]*)"\)$'
)
_FANOUT_BLOCK_LABEL_RE = re.compile(r'^(?P<base>-[^"$]+)\$\{i\}$')
_FANOUT_DO_LINE = "do"
_FANOUT_DONE_LINE = "done"


def _fanout_for_re(var: str) -> re.Pattern:
    return re.compile(rf'^for\s+\(\(i=0;\s*i<{re.escape(var)};\s*i\+\+\)\)$')


def _fanout_consumer_opt_re(idx_var: str) -> re.Pattern:
    # The consumer side of a scatter connection (see
    # script_generation.py's "Case B" branch in _option_definition_line):
    # an ARRAY-mode process's own option, connected to a "standard"
    # process's fanout family, referencing the member picked by the
    # array's own per-task loop variable — e.g. "-outf${idx}" for
    # idx_var="idx". Only meaningful when allow_fanout_consumer is set.
    return re.compile(rf'^(?P<base>-[^"$]+)\$\{{{re.escape(idx_var)}\}}$')


def _try_parse_fanout_block(
    body: list[str], start: int
) -> tuple[int, str, str, str | None, ConnectionRef | None, bool] | None:
    """
    Recognizes one fanout-family block (see the comment above
    _FANOUT_COUNT_RE) starting at body[start]. Returns (lines consumed,
    fanout option label — e.g. "-outfith", count-source option label —
    e.g. "-w", literal value text or None, ConnectionRef or None, is a
    fifo name rather than a plain value); the value/connection pair is
    mutually exclusive, matching define_opt/define_fifo_opt (scatter,
    unconnected) vs define_opt_from_proc_task_out (gather, connected to
    an array-mode process's per-task output) respectively — the last
    element is only ever True for a define_fifo_opt scatter (see
    data/programs/debasher_dynamic_fanout_fifos.sh's dispatch). None if
    body[start:] doesn't match this exact shape, leaving the caller to
    fall back to normal single-line parsing of body[start] itself.
    """
    if start + 4 >= len(body):
        return None

    count_match = _FANOUT_COUNT_RE.match(body[start])
    if not count_match:
        return None
    count_var = count_match.group("var")

    if not _fanout_for_re(count_var).match(body[start + 1]):
        return None
    if body[start + 2] != _FANOUT_DO_LINE:
        return None
    if body[start + 4] != _FANOUT_DONE_LINE:
        return None

    call_match = _DEFINE_OPTS_CALL_RE.match(body[start + 3])
    if not call_match:
        return None
    func = call_match.group("func")
    tokens = _tokenize(call_match.group("args") or "")
    if len(tokens) != _CALL_TOKEN_COUNTS.get(func, -1):
        return None

    count_label = count_match.group("count_label")

    if func in ("define_opt", "define_fifo_opt"):
        label_match = _FANOUT_BLOCK_LABEL_RE.match(tokens[0][0])
        if label_match is None or tokens[-1][0] != "optlist":
            return None
        fanout_label = f"{label_match.group('base')}ith"
        return (5, fanout_label, count_label, tokens[1][0], None, func == "define_fifo_opt")

    if func == "define_opt_from_proc_task_out":
        label_match = _FANOUT_BLOCK_LABEL_RE.match(tokens[0][0])
        if (
            label_match is None
            or not tokens[1][1]
            or tokens[2][0] not in ("${i}", "$i")
            or not tokens[3][1]
            or tokens[-1][0] != "optlist"
        ):
            return None
        fanout_label = f"{label_match.group('base')}ith"
        connection = ConnectionRef(
            option_label=fanout_label,
            source_process=tokens[1][0],
            source_option=tokens[3][0],
        )
        return (5, fanout_label, count_label, None, connection, False)

    return None


def _parse_primitive_calls(
    body: list[str],
    idx_var: str = "task_idx",
    allow_fanout_blocks: bool = False,
    allow_fanout_consumer: bool = False,
) -> tuple[dict[str, str], list[ConnectionRef], set[str], set[str], dict[str, str]] | None:
    """
    Parses a function body against the closed grammar of option-
    definition primitives — used for _define_opts (standard and, inside
    the loop, array mode) and (per-task) _generate_opts bodies alike,
    which all share the same call vocabulary. None means the body
    contains something outside that grammar (control flow, a computed
    call target, an unsupported call).

    `idx_var` names the only bare loop-index reference a
    define_opt_from_proc_task_out call round-trips through the app for
    — "task_idx" for a generator body (the default), "idx" for an array
    loop body (see _parse_array_define_opts).

    `allow_fanout_blocks` (only ever set for a "standard" _define_opts
    body — see resolve_options_handler) additionally recognizes the
    fanout-family block shape (see _try_parse_fanout_block).

    `allow_fanout_consumer` (only ever set for an array-mode loop
    body's `idx_var="idx"` — see _parse_array_define_opts) additionally
    accepts a define_opt_from_proc_out whose connected option name is
    "<base>${idx_var}" instead of a plain literal, reconstructing it as
    a connection to that "standard" process's "<base>ith" fanout family.
    """
    idx_re = _idx_var_re(idx_var)
    fanout_consumer_re = _fanout_consumer_opt_re(idx_var) if allow_fanout_consumer else None
    values: dict[str, str] = {}
    connections: list[ConnectionRef] = []
    value_descriptor_labels: set[str] = set()
    fifo_labels: set[str] = set()
    fanout_count_source_labels: dict[str, str] = {}
    locals_table: dict[str, str] = {}

    i = 0
    while i < len(body):
        line = body[i]

        if not line or _COMMENT_RE.match(line):
            i += 1
            continue
        if any(regex.match(line) for regex in _HEADER_BOILERPLATE_RES):
            i += 1
            continue
        if any(regex.match(line) for regex in _FOOTER_BOILERPLATE_RES):
            i += 1
            continue

        if allow_fanout_blocks:
            fanout_match = _try_parse_fanout_block(body, i)
            if fanout_match is not None:
                consumed, fanout_label, count_label, value_text, connection, is_fifo = fanout_match
                fanout_count_source_labels[fanout_label] = count_label
                if connection is not None:
                    connections.append(connection)
                else:
                    values[fanout_label] = value_text
                    if is_fifo:
                        fifo_labels.add(fanout_label)
                i += consumed
                continue

        local_match = _LOCAL_ASSIGN_RE.match(line)
        if local_match:
            locals_table[local_match.group("name")] = _strip_one_quote_layer(local_match.group("expr"))
            i += 1
            continue

        call_match = _DEFINE_OPTS_CALL_RE.match(line)
        if not call_match:
            # Control flow (if/for/while/case/...), a computed call
            # target, or any other statement outside the known grammar.
            return None

        func = call_match.group("func")
        tokens = _tokenize(call_match.group("args") or "")
        if len(tokens) != _CALL_TOKEN_COUNTS[func]:
            return None

        if func in ("define_opt_from_proc_out", "define_opt_from_proc_task_out"):
            label, proc, opt = tokens[0], tokens[1], tokens[-2]
            opt_ok = opt[1]
            fanout_consumer_base = None
            if not opt_ok and func == "define_opt_from_proc_out" and fanout_consumer_re is not None:
                consumer_match = fanout_consumer_re.match(opt[0])
                if consumer_match is not None:
                    fanout_consumer_base = consumer_match.group("base")
                    opt_ok = True
            if not (label[1] and proc[1] and opt_ok):
                return None
            # define_opt_from_proc_task_out's args are <label> <proc>
            # <task_idx> <opt> <optlist> — one more than the plain
            # define_opt_from_proc_out, with task_idx in between. Only
            # "connect to my own task" (${idx_var}/$idx_var) round-trips
            # through the app — script_generation.py always regenerates
            # exactly that (see _task_idx_var), never an arbitrary
            # expression — so anything else isn't this grammar at all.
            if func == "define_opt_from_proc_task_out" and not idx_re.match(tokens[2][0]):
                return None
            connections.append(
                ConnectionRef(
                    option_label=label[0],
                    source_process=proc[0],
                    source_option=f"{fanout_consumer_base}ith" if fanout_consumer_base is not None else opt[0],
                    task_indexed=func == "define_opt_from_proc_task_out",
                )
            )
        elif func == "define_opt":
            label, value = tokens[0], tokens[1]
            if not label[1]:
                return None
            value_text = value[0]
            var_ref_match = _VAR_REF_RE.match(value_text)
            if var_ref_match and var_ref_match.group("name") in locals_table:
                value_text = locals_table[var_ref_match.group("name")]
            values[label[0]] = value_text
        elif func == "define_value_desc_opt":
            # Its value is an engine-synthesized descriptor for the
            # process's own output, consumed elsewhere via
            # define_opt_from_proc_out — nothing to capture but the
            # label, so its option gets channel "value_desc" instead
            # (see program_import.py).
            label = tokens[0]
            if not label[1]:
                return None
            value_descriptor_labels.add(label[0])
        elif func in ("define_fifo_opt", "define_fifo_opt_generator"):
            # Unlike define_value_desc_opt, the fifo name IS a real,
            # user-chosen value (not engine-synthesized) — kept the same
            # way as a plain define_opt's value — alongside marking the
            # option's channel as "fifo".
            label, value = tokens[0], tokens[1]
            if not label[1]:
                return None
            value_text = value[0]
            var_ref_match = _VAR_REF_RE.match(value_text)
            if var_ref_match and var_ref_match.group("name") in locals_table:
                value_text = locals_table[var_ref_match.group("name")]
            values[label[0]] = value_text
            fifo_labels.add(label[0])
        elif func == "define_flag":
            label = tokens[0]
            if not label[1]:
                return None
        else:  # the three define_cmdline_* variants: <cmdline_ref> <label> <optlist>
            label = tokens[1]
            if not label[1]:
                return None

        i += 1

    return values, connections, value_descriptor_labels, fifo_labels, fanout_count_source_labels


def _parse_function_source(
    source: str,
    allow_fanout_blocks: bool = False,
    allow_fanout_consumer: bool = False,
) -> tuple[dict[str, str], list[ConnectionRef], set[str], set[str], dict[str, str]] | None:
    body = _function_body_lines(source)
    if body is None:
        return None
    return _parse_primitive_calls(
        body,
        allow_fanout_blocks=allow_fanout_blocks,
        allow_fanout_consumer=allow_fanout_consumer,
    )


# _define_opts_func_header() without the "local optlist=..." line — array
# mode has no persistent optlist to declare up front (see
# _add_array_opts_func: each loop iteration declares its own, fresh).
_ARRAY_HEADER_RES = [
    re.compile(r"^local\s+cmdline=\$1$"),
    re.compile(r"^local\s+process_spec=\$2$"),
    re.compile(r"^local\s+process_name=\$3$"),
    re.compile(r"^local\s+process_outdir=\$4$"),
]
_ARRAY_FOR_RE = re.compile(r'^for\s+idx\s+in\s+"\$\{!array\[@\]\}"$')
_ARRAY_DO_LINE = "do"
_ARRAY_DONE_LINE = "done"


def _parse_array_define_opts(
    source: str,
) -> tuple[str, dict[str, str], list[ConnectionRef], set[str], set[str]] | None:
    """
    Recognizes script_generation.py's exact array-mode shape (see
    _add_array_opts_func) in a _define_opts body: the standard header
    minus "local optlist=...", then arbitrary user code (kept verbatim
    as the returned arrayCode), then `for idx in "${!array[@]}"; do`,
    then a loop body that's itself just a plain option-definition body
    — `local optlist=""`, a flat sequence of option-definition
    primitives, `save_opt_list optlist` — parsed by _parse_primitive_calls
    exactly like a standard/generator body (its own header/footer-
    boilerplate skipping handles those two lines; "idx" replaces
    "task_idx" as the task-index variable a connection may use), then
    `done` and nothing else.

    None for anything that deviates from that — a different loop shape,
    trailing statements after the loop, a stray non-primitive call in
    the loop body, etc. — leaving the caller to fall back to "manual".
    """
    body = _function_body_lines(source)
    if body is None:
        return None

    if len(body) <= len(_ARRAY_HEADER_RES):
        return None
    for regex, line in zip(_ARRAY_HEADER_RES, body):
        if not regex.match(line):
            return None
    rest = body[len(_ARRAY_HEADER_RES):]

    for_index = next((i for i, line in enumerate(rest) if _ARRAY_FOR_RE.match(line)), None)
    if for_index is None:
        return None
    if for_index + 1 >= len(rest) or rest[for_index + 1] != _ARRAY_DO_LINE:
        return None
    if rest[-1] != _ARRAY_DONE_LINE:
        return None

    array_code = "\n".join(rest[:for_index]).strip()
    loop_body = rest[for_index + 2:-1]

    # allow_fanout_consumer: the loop body may connect to a "standard"
    # process's fanout family via "<base>${idx}" (see
    # _fanout_consumer_opt_re) — array mode has no fanout family
    # options of its own, so allow_fanout_blocks stays off.
    parsed = _parse_primitive_calls(loop_body, idx_var="idx", allow_fanout_consumer=True)
    if parsed is None:
        return None
    values, connections, value_descriptor_labels, fifo_labels, _fanout_count_source_labels = parsed
    return array_code, values, connections, value_descriptor_labels, fifo_labels


def scan_connections(source: str) -> list[ConnectionRef]:
    return [
        ConnectionRef(
            option_label=match.group("label"),
            source_process=match.group("proc"),
            source_option=match.group("opt"),
        )
        for regex in (_CONNECTION_SCAN_RE, _TASK_CONNECTION_SCAN_RE)
        for match in regex.finditer(source)
    ]


def scan_value_descriptor_labels(source: str) -> set[str]:
    """
    Best-effort companion to scan_connections, for the same reason: a
    process that falls back to "manual"/opaque capture still shouldn't
    show a value-descriptor option as if it were a fixed-value one just
    because its define_value_desc_opt call happened to sit inside
    whatever unparseable statement caused the fallback.
    """
    return {match.group("label") for match in _VALUE_DESC_SCAN_RE.finditer(source)}


def scan_fifo_labels(source: str) -> set[str]:
    """Best-effort companion to scan_connections/scan_value_descriptor_labels, same reasoning."""
    return {match.group("label") for match in _FIFO_SCAN_RE.finditer(source)}


def _extract_generator_size_code(source: str) -> str | None:
    """
    Returns _generate_opts_size's body, verbatim (declare -f-normalized —
    see _function_body_lines — so relative indentation within it is
    flattened, same as arrayCode via _parse_array_define_opts), minus the
    fixed header script_generation.py's _add_generate_opts_size_func
    always emits ahead of it (the same header as _define_opts minus
    "local optlist=" — engine calls this with the same 4 positional args,
    see debasher::_define_opts_generator). None if the header isn't
    present in that exact form, or the source isn't a well-formed
    function dump.
    """
    body = _function_body_lines(source)
    if body is None:
        return None
    if len(body) < len(_ARRAY_HEADER_RES):
        return None
    for regex, line in zip(_ARRAY_HEADER_RES, body):
        if not regex.match(line):
            return None
    return "\n".join(body[len(_ARRAY_HEADER_RES):]).strip()


def resolve_options_handler(option_handler_code: dict[str, str]) -> OptionHandlerResult:
    generate_opts = option_handler_code.get(PROCESS_METHOD_GENERATE_OPTS_SUFFIX)
    generate_opts_size = option_handler_code.get(PROCESS_METHOD_GENERATE_OPTS_SIZE_SUFFIX)
    define_opts = option_handler_code.get(PROCESS_METHOD_DEFINE_OPTS_SUFFIX)

    if generate_opts_size:
        generator_size_code = _extract_generator_size_code(generate_opts_size)
        parsed = _parse_function_source(generate_opts) if generate_opts else None

        if generator_size_code is not None and parsed is not None:
            values, connections, value_descriptor_labels, fifo_labels, _fanout_count_source_labels = parsed
            return OptionHandlerResult(
                handler=OptionsHandler(mode="generator", generatorSizeCode=generator_size_code),
                option_values=values,
                connections=connections,
                value_descriptor_labels=value_descriptor_labels,
                fifo_labels=fifo_labels,
            )

        if generator_size_code is not None and not generate_opts:
            # _generate_opts_size with no _generate_opts alongside it can't
            # actually retrieve a task's options at run time (the engine
            # always needs the latter once the former exists) — treat it as
            # an incomplete generator rather than guessing further.
            return OptionHandlerResult(
                handler=OptionsHandler(mode="generator", generatorSizeCode=generator_size_code),
            )

        # generate_opts doesn't fit the primitive-call grammar —
        # script_generation.py can't reproduce it, so this falls back to
        # manual with everything kept verbatim.
        combined = f"{generate_opts_size}\n\n{generate_opts}" if generate_opts else generate_opts_size
        return OptionHandlerResult(
            handler=OptionsHandler(mode="manual", manualCode=combined),
            connections=scan_connections(combined),
            value_descriptor_labels=scan_value_descriptor_labels(combined),
            fifo_labels=scan_fifo_labels(combined),
        )

    if define_opts:
        # allow_fanout_blocks: a "standard" body may contain one or more
        # fanout-family blocks (see _try_parse_fanout_block) interleaved
        # among the flat primitive calls.
        parsed = _parse_function_source(define_opts, allow_fanout_blocks=True)
        if parsed is not None:
            values, connections, value_descriptor_labels, fifo_labels, fanout_count_source_labels = parsed
            return OptionHandlerResult(
                handler=OptionsHandler(mode="standard"),
                option_values=values,
                connections=connections,
                value_descriptor_labels=value_descriptor_labels,
                fifo_labels=fifo_labels,
                fanout_count_source_labels=fanout_count_source_labels,
            )

        # Not the flat "standard" grammar — try script_generation.py's
        # fixed array-mode shape (see _parse_array_define_opts) before
        # giving up to "manual".
        array_parsed = _parse_array_define_opts(define_opts)
        if array_parsed is not None:
            array_code, values, connections, value_descriptor_labels, fifo_labels = array_parsed
            return OptionHandlerResult(
                handler=OptionsHandler(mode="array", arrayCode=array_code),
                option_values=values,
                connections=connections,
                value_descriptor_labels=value_descriptor_labels,
                fifo_labels=fifo_labels,
            )

        return OptionHandlerResult(
            handler=OptionsHandler(mode="manual", manualCode=define_opts),
            connections=scan_connections(define_opts),
            value_descriptor_labels=scan_value_descriptor_labels(define_opts),
            fifo_labels=scan_fifo_labels(define_opts),
        )

    return OptionHandlerResult(handler=OptionsHandler(mode="standard"))
