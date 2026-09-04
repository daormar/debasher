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
  frontend's "generator" mode. Its body typically uses the exact same
  closed grammar of primitive calls as a plain _define_opts (just called
  once per task, with a task_idx argument available to it), so it's
  parsed the same way into per-option values/connections; only a body
  that can't be parsed that way falls back to "manual" with the pair
  kept verbatim.
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

_ECHO_LINE_RE = re.compile(r"^echo\s+(?P<expr>.*)$")


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


def _parse_primitive_calls(
    body: list[str],
    idx_var: str = "task_idx",
) -> tuple[dict[str, str], list[ConnectionRef], set[str], set[str]] | None:
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
    """
    idx_re = _idx_var_re(idx_var)
    values: dict[str, str] = {}
    connections: list[ConnectionRef] = []
    value_descriptor_labels: set[str] = set()
    fifo_labels: set[str] = set()
    locals_table: dict[str, str] = {}

    for line in body:
        if not line or _COMMENT_RE.match(line):
            continue
        if any(regex.match(line) for regex in _HEADER_BOILERPLATE_RES):
            continue
        if any(regex.match(line) for regex in _FOOTER_BOILERPLATE_RES):
            continue

        local_match = _LOCAL_ASSIGN_RE.match(line)
        if local_match:
            locals_table[local_match.group("name")] = _strip_one_quote_layer(local_match.group("expr"))
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
            if not (label[1] and proc[1] and opt[1]):
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
                    source_option=opt[0],
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

    return values, connections, value_descriptor_labels, fifo_labels


def _parse_function_source(
    source: str,
) -> tuple[dict[str, str], list[ConnectionRef], set[str], set[str]] | None:
    body = _function_body_lines(source)
    if body is None:
        return None
    return _parse_primitive_calls(body)


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

    parsed = _parse_primitive_calls(loop_body, idx_var="idx")
    if parsed is None:
        return None
    values, connections, value_descriptor_labels, fifo_labels = parsed
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


def _extract_generator_size(source: str) -> str | None:
    """
    Returns _generate_opts_size's size expression, if it's the one shape
    script_generation.py's _add_generate_opts_size_func can reproduce: a
    single `echo <expr>` statement (any `local` assignments ahead of it
    inlined by bare-reference substitution). None for anything more
    elaborate (multiple statements, no echo) — that case falls back to
    "manual" instead, since regenerating it would lose that logic.
    """
    body = _function_body_lines(source)
    if body is None:
        return None

    locals_table: dict[str, str] = {}
    statements: list[str] = []
    for line in body:
        if not line or _COMMENT_RE.match(line) or any(regex.match(line) for regex in _HEADER_BOILERPLATE_RES):
            continue
        local_match = _LOCAL_ASSIGN_RE.match(line)
        if local_match:
            locals_table[local_match.group("name")] = _strip_one_quote_layer(local_match.group("expr"))
            continue
        statements.append(line)

    if len(statements) != 1:
        return None

    echo_match = _ECHO_LINE_RE.match(statements[0])
    if not echo_match:
        return None

    expr = echo_match.group("expr").strip()
    expr = _strip_one_quote_layer(expr)
    var_ref_match = _VAR_REF_RE.match(expr)
    if var_ref_match and var_ref_match.group("name") in locals_table:
        expr = locals_table[var_ref_match.group("name")]
    return expr


def resolve_options_handler(option_handler_code: dict[str, str]) -> OptionHandlerResult:
    generate_opts = option_handler_code.get(PROCESS_METHOD_GENERATE_OPTS_SUFFIX)
    generate_opts_size = option_handler_code.get(PROCESS_METHOD_GENERATE_OPTS_SIZE_SUFFIX)
    define_opts = option_handler_code.get(PROCESS_METHOD_DEFINE_OPTS_SUFFIX)

    if generate_opts_size:
        generator_size = _extract_generator_size(generate_opts_size)
        parsed = _parse_function_source(generate_opts) if generate_opts else None

        if generator_size is not None and parsed is not None:
            values, connections, value_descriptor_labels, fifo_labels = parsed
            return OptionHandlerResult(
                handler=OptionsHandler(mode="generator", generatorSize=generator_size),
                option_values=values,
                connections=connections,
                value_descriptor_labels=value_descriptor_labels,
                fifo_labels=fifo_labels,
            )

        if generator_size is not None and not generate_opts:
            # _generate_opts_size with no _generate_opts alongside it can't
            # actually retrieve a task's options at run time (the engine
            # always needs the latter once the former exists) — treat it as
            # an incomplete generator rather than guessing further.
            return OptionHandlerResult(
                handler=OptionsHandler(mode="generator", generatorSize=generator_size),
            )

        # Either generate_opts_size isn't a single codegen-able
        # expression, or generate_opts doesn't fit the primitive-call
        # grammar — script_generation.py can't reproduce either, so this
        # falls back to manual with everything kept verbatim.
        combined = f"{generate_opts_size}\n\n{generate_opts}" if generate_opts else generate_opts_size
        return OptionHandlerResult(
            handler=OptionsHandler(mode="manual", manualCode=combined),
            connections=scan_connections(combined),
            value_descriptor_labels=scan_value_descriptor_labels(combined),
            fifo_labels=scan_fifo_labels(combined),
        )

    if define_opts:
        parsed = _parse_function_source(define_opts)
        if parsed is not None:
            values, connections, value_descriptor_labels, fifo_labels = parsed
            return OptionHandlerResult(
                handler=OptionsHandler(mode="standard"),
                option_values=values,
                connections=connections,
                value_descriptor_labels=value_descriptor_labels,
                fifo_labels=fifo_labels,
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
