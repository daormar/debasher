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
  primitives (define_opt[_from_proc_out[_task_out]|_from_shared_dir],
  define_infile_opt, define_indir_opt,
  define_cmdline_opt[_if_given], define_cmdline_infile_opt[_if_given],
  define_cmdline_indir_opt[_if_given],
  define_cmdline_flag_if_given, define_flag, define_value_desc_opt,
  define_fifo_opt[_generator] — all of them just other ways to define
  an option's value, not something exotic). A body that's exactly the
  standard boilerplate header/footer
  plus a flat sequence of those calls with literal label/proc/opt
  arguments round-trips structurally, so it's parsed into "standard"
  mode option values plus real connections.
- A loop, or any other statement outside that grammar, falls back to
  "manual" mode with _define_opts kept verbatim — UNLESS it matches
  script_generation.py's own fixed "array" shape exactly: the standard
  header minus its "local optlist=..." line, then arbitrary user code
  (kept verbatim as arrayCode) building a fixed-name array ("array"),
  then an optional `local task_idx` and a
  `for task_idx in "${!array[@]}"; do` loop whose body is itself just
  a plain option-definition body (its own `local optlist=""`, the same
  closed grammar of option-definition primitives as "standard" mode,
  parsed the same way, with the same "task_idx" for a task-indexed
  connection as a generator body, and `save_opt_list optlist`), then
  `done` and nothing else. Every option is defined inside the loop this
  way, even one whose value doesn't depend on task_idx: array mode
  never hoists a task_idx-independent option out as a one-time "shared
  prefix". That round-trips into "array" mode; anything that deviates from this exact
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
from pathlib import Path

from .debasher_constants import (
    PROCESS_METHOD_DEFINE_OPTS_SUFFIX,
    PROCESS_METHOD_GENERATE_OPTS_SIZE_SUFFIX,
    PROCESS_METHOD_GENERATE_OPTS_SUFFIX,
    TASK_IDX_VAR,
)
from .doc_mod import run_get_verbatim_func_source
from .markdown_parsing import (
    function_body_lines,
    function_header_name,
    join_verbatim_body_lines,
    verbatim_function_body_lines,
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
class SharedDirRef:
    # Exactly one of the two is set: a literal directory name resolved
    # directly from the source text, or the name of a variable whose
    # value (the actual directory name) program_import.py resolves
    # later via debasher_doc_mod --resolve-var — this module never
    # executes anything to find out.
    literal_name: str | None = None
    var_name: str | None = None


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
    # Subset of fifo_labels whose define_fifo_opt[_generator] call carried
    # a trailing "--mirror" token — program_import.py sets their option's
    # `mirror` from this. Recovered the same way as fifo_labels itself
    # (best-effort in "manual" mode, exact otherwise).
    mirrored_fifo_labels: set[str] = field(default_factory=set)
    # The fifo tag of each fifo whose define_fifo_opt[_generator] call
    # carried one as its last token ("external" or "control", see
    # script_generation.py's _fifo_tag_flag), by option label: that of a
    # fanout family for a call in one of its blocks. Scanned from the source
    # in every mode (see scan_fifo_tags), since a tag says nothing about the
    # shape of the function.
    fifo_tags: dict[str, str] = field(default_factory=dict)
    # Labels defined via define_procspec_opt — program_import.py sets
    # their option's fromProcessSpec (not channel — see
    # ProgramOption.fromProcessSpec's own docstring for why) from these.
    # Additive, like shared_dir_refs below: a matched label also keeps
    # its ordinary option_values[label] entry, holding the spec
    # attribute's name itself (e.g. "cpus") rather than its runtime
    # value, which only the process_spec the engine passes in at
    # schedule time can resolve.
    procspec_labels: set[str] = field(default_factory=set)
    # Fanout family option label (e.g. "-outf-ith") -> the label of the
    # command-line option on the SAME process that supplies its runtime
    # count (e.g. "-w") — see script_generation.py's
    # _fanout_definition_lines/_FANOUT_SUFFIX. Only ever populated for
    # "standard" mode (see _parse_primitive_calls's allow_fanout_blocks);
    # program_import.py resolves the label into an actual
    # ProgramOption.countSourceOptionId once both options have real ids.
    fanout_count_source_labels: dict[str, str] = field(default_factory=dict)
    # Option label -> SharedDirRef, for every define_opt_from_shared_dir
    # call (see the dispatch in _parse_primitive_calls). Additive: a
    # matched label also keeps its ordinary option_values[label] entry
    # (a synthesized "$(debasher::get_absolute_shdirname ...)"
    # expression — see _parse_primitive_calls), so an option
    # program_import.py can't confirm against a real shared directory
    # still round-trips as a plain value rather than vanishing.
    shared_dir_refs: dict[str, SharedDirRef] = field(default_factory=dict)
    # Labels defined via define_opt_from_process_outdir, whose option gets
    # channel "process_outdir" (see program_import.py).
    process_outdir_labels: set[str] = field(default_factory=set)
    # Option label -> the subpath that its define_opt_from_shared_dir or
    # define_opt_from_process_outdir call gives with --subdir, as written
    # (a Bash word, carried through unevaluated, like a value).
    subpaths: dict[str, str] = field(default_factory=dict)


_HEADER_BOILERPLATE_RES = [
    re.compile(r"^local\s+cmdline=\$1$"),
    re.compile(r"^local\s+process_spec=\$2$"),
    re.compile(r"^local\s+process_name=\$3$"),
    re.compile(r"^local\s+process_outdir=\$4$"),
    re.compile(rf"^local\s+{TASK_IDX_VAR}=\$5$"),  # only present on _generate_opts
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
_EMBEDDED_VAR_RE = re.compile(r"\$\{(?P<braced>[A-Za-z_][A-Za-z0-9_]*)\}|\$(?P<bare>[A-Za-z_][A-Za-z0-9_]*)")


def _strip_one_quote_layer(text: str) -> str:
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        return text[1:-1]
    return text


def _resolve_embedded_refs(expr: str, locals_table: dict[str, str], known_local_names: set[str]) -> str | None:
    """
    Substitutes every ${name}/$name occurrence *embedded* in `expr` (as
    opposed to a bare whole-string reference — see _VAR_REF_RE) that
    names an already-resolved local with that local's own (already
    self-contained) text — e.g. geno-debasher's
    `local abs_datadir=`get_absolute_shdirname "${DATADIR_BASENAME}"``
    then `local outfile="${abs_datadir}"/out.bam`: without this, a
    define_opt using `$outfile` as its value would inline "${abs_datadir}"/out.bam
    verbatim — a dangling reference, since script_generation.py never
    re-emits a local's own declaration, only the option value ultimately
    built from it.

    Returns None if `expr` embeds a reference to a *different* local
    name that wasn't itself resolved this way (known to be a local at
    all, i.e. in `known_local_names`, but not in `locals_table`) —
    leaving that reference as literal text would dangle the same way, so
    the caller must reject the whole body rather than guess. A reference
    to anything else — a header arg (cmdline/process_spec/process_name/
    process_outdir/task_idx) or a genuinely global name sourced from
    elsewhere — is left untouched either way, since those are equally
    available once regenerated; they're just never local-scoped to the
    function.
    """
    unresolved = False

    def substitute(match: re.Match) -> str:
        nonlocal unresolved
        name = match.group("braced") or match.group("bare")
        if name in locals_table:
            return locals_table[name]
        if name in known_local_names:
            unresolved = True
        return match.group(0)

    resolved = _EMBEDDED_VAR_RE.sub(substitute, expr)
    return None if unresolved else resolved


def _chase_local_value(
    value_text: str, locals_table: dict[str, str], known_local_names: set[str]
) -> tuple[str, bool]:
    """
    Resolves every local reference in a define_opt/define_fifo_opt value
    token — whether it's a *bare* whole-string reference (e.g. "$outfile",
    the common case, produced by chasing an intermediate local per
    _LOCAL_ASSIGN_RE) or one *embedded* alongside other literal text (e.g.
    "${abs_datadir}/normal.bam", skipping the intermediate local) — into
    self-contained text, via _resolve_embedded_refs (a bare reference is
    just the embedded case spanning the whole string). Returns
    (value_text, False) instead — the caller must reject the whole body —
    if the token references a local that itself couldn't be resolved to
    something self-contained: leaving that reference as literal text
    would dangle, since script_generation.py never re-emits a local's own
    declaration.
    """
    resolved = _resolve_embedded_refs(value_text, locals_table, known_local_names)
    if resolved is None:
        return value_text, False
    return resolved, True


_DEFINE_OPTS_CALL_RE = re.compile(
    r"^(?:debasher::)?(?P<func>define_cmdline_flag_if_given|define_cmdline_infile_opt_if_given|"
    r"define_cmdline_indir_opt_if_given|define_cmdline_opt_if_given|define_cmdline_infile_opt|"
    r"define_cmdline_indir_opt|"
    r"define_cmdline_opt|define_value_desc_opt|define_fifo_opt_generator|define_fifo_opt|"
    r"define_flag|define_opt_from_proc_task_out|define_opt_from_proc_out|"
    r"define_opt_from_shared_dir|define_opt_from_process_outdir|define_procspec_opt|"
    r"define_infile_opt|define_indir_opt|define_opt)"
    r"(?:\s+(?P<args>.*?))?\s*(?:\|\|.*)?$"
)
_TOKEN_RE = re.compile(r'"(?P<q>[^"]*)"|(?P<bare>\S+)')

# Expected exact token count per call, matching each function's real
# positional-argument signature (engine/debasher_lib_opts).
_CALL_TOKEN_COUNTS = {
    "define_cmdline_flag_if_given": 3,  # <cmdline> <label> <optlist>
    "define_cmdline_opt_if_given": 3,
    "define_cmdline_opt": 3,
    "define_cmdline_infile_opt": 3,  # <cmdline> <label> <optlist>
    "define_cmdline_infile_opt_if_given": 3,
    "define_cmdline_indir_opt": 3,
    "define_cmdline_indir_opt_if_given": 3,
    "define_flag": 2,  # <label> <optlist>
    "define_value_desc_opt": 2,  # <label> <optlist>
    "define_fifo_opt": 3,  # <label> <fifoname> <optlist> [--mirror, stripped before this check]
    "define_fifo_opt_generator": 4,  # <label> <fifoname> <task_idx> <optlist> [--mirror, stripped before this check]
    "define_opt_from_proc_out": 4,  # <label> <proc> <opt> <optlist>
    "define_opt_from_proc_task_out": 5,  # <label> <proc> <task_idx> <opt> <optlist>
    "define_opt_from_shared_dir": 3,  # <label> <shdirname> <optlist> [--subdir <subpath>, stripped before this check]
    "define_opt_from_process_outdir": 2,  # <label> <optlist> [--subdir <subpath>, stripped before this check]
    "define_procspec_opt": 4,  # <process_spec> <label> <specname> <optlist>
    "define_opt": 3,  # <label> <value> <optlist>
    "define_infile_opt": 4,  # <label> <value> <optlist> <process_name>
    "define_indir_opt": 4,
}

# The only task index a define_opt_from_proc_task_out call round-trips
# through the app with: "${task_idx}" or "$task_idx".
_TASK_IDX_REF_RE = re.compile(rf"^\$\{{?{TASK_IDX_VAR}\}}?$")

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
# Best-effort companion to _FIFO_SCAN_RE: same call, but only when its
# line also carries a trailing "--mirror" token (see
# script_generation.py's _option_definition_line).
_MIRRORED_FIFO_SCAN_RE = re.compile(
    r'(?:debasher::)?define_fifo_opt(?:_generator)?\s+"(?P<label>[^"]*)"[^\n]*--mirror\b'
)
# The same call with a trailing fifo tag, which only a resident program
# writes.
_TAGGED_FIFO_SCAN_RE = re.compile(
    r'(?:debasher::)?define_fifo_opt(?:_generator)?\s+"(?P<label>[^"]*)"[^\n]*--(?P<tag>external|control)\b'
)
# The tokens that may end a define_fifo_opt[_generator] call after its
# positional arguments: its mirror, or its fifo tag.
_FIFO_TRAILING_FLAGS = (("--mirror", False), ("--external", False), ("--control", False))
# The process_spec argument comes first (typically "${process_spec}", one
# token with no internal space) — skipped the same way
# _TASK_CONNECTION_SCAN_RE skips a task-index argument. Unlike
# _FIFO_SCAN_RE/_VALUE_DESC_SCAN_RE, the specname argument is captured
# too (like _SHARED_DIR_SCAN_RE's own dirname) — it's always a clean
# literal right there in the call regardless of what else in the body
# caused the fallback, so recovering it here is exact, not a guess.
_PROCSPEC_SCAN_RE = re.compile(
    r'(?:debasher::)?define_procspec_opt\s+[^\s]+\s+"(?P<label>[^"]*)"\s+"(?P<specname>[^"]*)"'
)


def _tokenize(args: str) -> list[tuple[str, bool]]:
    """
    Splits a call's argument text into (text, is_literal) pairs.
    Double-quoted text with no "$"/backtick inside is literal — usable
    as a static label/proc/opt name; anything else (bare words,
    interpolated strings) is not, but its raw text is still returned
    since a value argument (unlike a label/proc/opt one) is carried
    through unevaluated regardless of literalness.

    Adjacent matches with no gap between them (e.g. "${abs_datadir}"/out.bam,
    a quoted piece directly concatenated with a bare one, no space) are one
    shell word, not two — merged into a single (non-literal) token so a
    later embedded-reference resolution (_resolve_embedded_refs) sees the
    whole value at once, same as if it had all been written inside one
    pair of quotes.
    """
    tokens: list[tuple[str, bool]] = []
    prev_end: int | None = None
    for match in _TOKEN_RE.finditer(args):
        if match.group("q") is not None:
            text = match.group("q")
            is_literal = "$" not in text and "`" not in text
        else:
            text = match.group("bare")
            is_literal = False

        if tokens and match.start() == prev_end:
            prev_text, _ = tokens[-1]
            tokens[-1] = (prev_text + text, False)
        else:
            tokens.append((text, is_literal))
        prev_end = match.end()
    return tokens


# Fanout block (see script_generation.py's _fanout_definition_lines).
# Written by script_generation.py as:
#     local <var>=$(debasher::read_opt_value_from_line "${cmdline}" "<count_label>")
#     for ((i=0; i<<var>; i++)); do
#         <one define_opt or define_opt_from_proc_task_out call, label "<base>${i}">
#     done
# but `declare -f` always reprints a for loop's "do" on its own line
# (verified against real bash — same as _ARRAY_FOR_RE/_ARRAY_DO_LINE's
# "for task_idx in ...; do" below), so the shape actually recovered here is
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


def _shared_dir_ref_from_arg(arg: str) -> SharedDirRef:
    var_match = _VAR_REF_RE.match(arg)
    if var_match:
        return SharedDirRef(var_name=var_match.group("name"))
    return SharedDirRef(literal_name=arg)


_SHARED_DIR_SCAN_RE = re.compile(
    r'(?:debasher::)?define_opt_from_shared_dir\s+"(?P<label>[^"]+)"\s+"(?P<arg>[^"]*)"'
)


_PROCESS_OUTDIR_SCAN_RE = re.compile(r'(?:debasher::)?define_opt_from_process_outdir\s+"(?P<label>[^"]+)"')
# The same calls, and define_opt_from_shared_dir, when their line also
# carries "--subdir" and a quoted subpath.
_SUBPATH_SCAN_RE = re.compile(
    r'(?:debasher::)?define_opt_from_(?:shared_dir|process_outdir)\s+"(?P<label>[^"]+)"[^\n]*--subdir\s+"(?P<subpath>[^"]*)"'
)


def scan_process_outdir_labels(source: str) -> set[str]:
    """Best-effort companion to scan_connections/..., same reasoning."""
    return {match.group("label") for match in _PROCESS_OUTDIR_SCAN_RE.finditer(source)}


def scan_subpaths(source: str) -> dict[str, str]:
    """Best-effort companion to scan_connections/..., same reasoning."""
    return {match.group("label"): match.group("subpath") for match in _SUBPATH_SCAN_RE.finditer(source)}


def scan_shared_dir_refs(source: str) -> dict[str, SharedDirRef]:
    """Best-effort companion to scan_connections/..., same reasoning."""
    return {
        match.group("label"): _shared_dir_ref_from_arg(match.group("arg"))
        for match in _SHARED_DIR_SCAN_RE.finditer(source)
    }


def _fanout_for_re(var: str) -> re.Pattern:
    return re.compile(rf'^for\s+\(\(i=0;\s*i<{re.escape(var)};\s*i\+\+\)\)$')


# The consumer side of a scatter connection (see script_generation.py's
# "Case B" branch in _option_definition_line): an array- or
# generator-mode process's own option, connected to a "standard"
# process's fanout family, referencing the member picked by the index of
# its own task, e.g. "-outf${task_idx}". Only meaningful when
# allow_fanout_consumer is set.
_FANOUT_CONSUMER_OPT_RE = re.compile(rf'^(?P<base>-[^"$]+)\$\{{{TASK_IDX_VAR}\}}$')


def _try_parse_fanout_block(
    body: list[str], start: int
) -> tuple[int, str, str, str | None, ConnectionRef | None, bool] | None:
    """
    Recognizes one fanout-family block (see the comment above
    _FANOUT_COUNT_RE) starting at body[start]. Returns (lines consumed,
    fanout option label (e.g. "-outf-ith"), count-source option label
    (e.g. "-w"), literal value text or None, ConnectionRef or None, is a
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
    # A fifo tag (see scan_fifo_tags) ends a define_fifo_opt of a family
    # the same way as that of a single option.
    if func == "define_fifo_opt" and tokens and tokens[-1] in _FIFO_TRAILING_FLAGS[1:]:
        tokens = tokens[:-1]
    if len(tokens) != _CALL_TOKEN_COUNTS.get(func, -1):
        return None

    count_label = count_match.group("count_label")

    if func in ("define_opt", "define_fifo_opt"):
        label_match = _FANOUT_BLOCK_LABEL_RE.match(tokens[0][0])
        if label_match is None or tokens[-1][0] != "optlist":
            return None
        fanout_label = f"{label_match.group('base')}-ith"
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
        fanout_label = f"{label_match.group('base')}-ith"
        connection = ConnectionRef(
            option_label=fanout_label,
            source_process=tokens[1][0],
            source_option=tokens[3][0],
        )
        return (5, fanout_label, count_label, None, connection, False)

    return None


@dataclass
class _OptionFacts:
    """
    What parsing a function body learns of the options of a process: the
    part of OptionHandlerResult that does not depend on the mode of the
    options handler (see _result), with the same meaning for each field.
    """

    values: dict[str, str] = field(default_factory=dict)
    connections: list[ConnectionRef] = field(default_factory=list)
    value_descriptor_labels: set[str] = field(default_factory=set)
    fifo_labels: set[str] = field(default_factory=set)
    mirrored_fifo_labels: set[str] = field(default_factory=set)
    procspec_labels: set[str] = field(default_factory=set)
    fanout_count_source_labels: dict[str, str] = field(default_factory=dict)
    shared_dir_refs: dict[str, SharedDirRef] = field(default_factory=dict)
    process_outdir_labels: set[str] = field(default_factory=set)
    subpaths: dict[str, str] = field(default_factory=dict)


@dataclass
class _ParseState:
    """What _parse_primitive_calls keeps while it goes through a body: the
    facts it has learned, and the locals it can chase an expression
    through (see _chase_local_value)."""

    facts: _OptionFacts
    locals_table: dict[str, str]
    known_local_names: set[str]
    allow_fanout_consumer: bool
    # The subpath given with --subdir to the call being recorded, if any
    # (see _strip_trailing_flags)
    subpath: str | None = None

    def chase(self, text: str) -> tuple[str, bool]:
        return _chase_local_value(text, self.locals_table, self.known_local_names)


def _is_skipped_line(line: str) -> bool:
    """A blank line, a comment, or the fixed header or footer of an option
    definition function, which say nothing of the options."""
    return (
        not line
        or bool(_COMMENT_RE.match(line))
        or any(regex.match(line) for regex in _HEADER_BOILERPLATE_RES)
        or any(regex.match(line) for regex in _FOOTER_BOILERPLATE_RES)
    )


def _record_local(state: _ParseState, line: str) -> bool:
    """Records a `local NAME=EXPR` line, for later values to be chased
    through; False if `line` is not one."""
    local_match = _LOCAL_ASSIGN_RE.match(line)
    if not local_match:
        return False
    name = local_match.group("name")
    expr = _strip_one_quote_layer(local_match.group("expr"))
    resolved = _resolve_embedded_refs(expr, state.locals_table, state.known_local_names)
    if resolved is not None:
        state.locals_table[name] = resolved
    state.known_local_names.add(name)
    return True


def _record_fanout_block(state: _ParseState, fanout_match) -> None:
    _consumed, fanout_label, count_label, value_text, connection, is_fifo = fanout_match
    state.facts.fanout_count_source_labels[fanout_label] = count_label
    if connection is not None:
        state.facts.connections.append(connection)
    else:
        state.facts.values[fanout_label] = value_text
        if is_fifo:
            state.facts.fifo_labels.add(fanout_label)


def _strip_trailing_flags(func: str, tokens: list) -> tuple[list, bool, str | None]:
    """
    The positional arguments of a call, whether it is mirrored, and the
    subpath that it gives with --subdir, if any. A
    define_fifo_opt[_generator] call may carry one extra trailing
    "--mirror" token beyond its ordinary positional args (see
    script_generation.py's _option_definition_line), or a fifo tag in the
    same place (see scan_fifo_tags, which recovers it); a
    define_opt_from_shared_dir or define_opt_from_process_outdir call may
    end with "--subdir <subpath>". All of them are stripped before the
    exact positional-count check, same as every other primitive here.
    """
    if func in ("define_opt_from_shared_dir", "define_opt_from_process_outdir"):
        if len(tokens) >= 2 and tokens[-2] == ("--subdir", False):
            return tokens[:-2], False, tokens[-1][0]
        return tokens, False, None
    tokens, mirrored = _strip_trailing_fifo_flags(func, tokens)
    return tokens, mirrored, None


def _strip_trailing_fifo_flags(func: str, tokens: list) -> tuple[list, bool]:
    """
    The positional arguments of a define_fifo_opt[_generator] call, and
    whether it is mirrored (see _strip_trailing_flags).
    """
    if func not in ("define_fifo_opt", "define_fifo_opt_generator"):
        return tokens, False
    mirrored = bool(tokens) and tokens[-1] == ("--mirror", False)
    if mirrored:
        tokens = tokens[:-1]
    if tokens and tokens[-1] in _FIFO_TRAILING_FLAGS[1:]:
        tokens = tokens[:-1]
    return tokens, mirrored


# One function for each family of calls of the grammar: each records what the
# call says of its option in the state, and returns False when the call is
# outside the grammar after all.


def _record_connection(state: _ParseState, func: str, tokens: list, mirrored: bool) -> bool:
    label, proc, opt = tokens[0], tokens[1], tokens[-2]
    opt_ok = opt[1]
    fanout_consumer_base = None
    if not opt_ok and func == "define_opt_from_proc_out" and state.allow_fanout_consumer:
        consumer_match = _FANOUT_CONSUMER_OPT_RE.match(opt[0])
        if consumer_match is not None:
            fanout_consumer_base = consumer_match.group("base")
            opt_ok = True
    if not (label[1] and proc[1] and opt_ok):
        return False
    # define_opt_from_proc_task_out's args are <label> <proc> <task_idx>
    # <opt> <optlist>, one more than the plain define_opt_from_proc_out,
    # with task_idx in between. Only "connect to my own task"
    # (${task_idx}/$task_idx) round-trips through the app: script_generation.py
    # always regenerates exactly that (see TASK_IDX_VAR), never an
    # arbitrary expression, so anything else isn't this grammar at all.
    if func == "define_opt_from_proc_task_out" and not _TASK_IDX_REF_RE.match(tokens[2][0]):
        return False
    state.facts.connections.append(
        ConnectionRef(
            option_label=label[0],
            source_process=proc[0],
            source_option=f"{fanout_consumer_base}-ith" if fanout_consumer_base is not None else opt[0],
            task_indexed=func == "define_opt_from_proc_task_out",
        )
    )
    return True


def _record_literal(state: _ParseState, func: str, tokens: list, mirrored: bool) -> bool:
    # define_infile_opt (define_indir_opt) is define_opt for an input file
    # (directory), whose value the engine resolves against the module's
    # directory; script_generation.py writes it for every "file"-typed
    # ("dir"-typed) input given as a literal, so it holds a value exactly
    # like define_opt's.
    label, value = tokens[0], tokens[1]
    if not label[1]:
        return False
    value_text, ok = state.chase(value[0])
    if not ok:
        return False
    state.facts.values[label[0]] = value_text
    return True


def _record_shared_dir(state: _ParseState, func: str, tokens: list, mirrored: bool) -> bool:
    label, shdirname = tokens[0], tokens[1]
    if not label[1]:
        return False
    state.facts.shared_dir_refs[label[0]] = _shared_dir_ref_from_arg(shdirname[0])
    # Kept as the option's ordinary value too (see
    # OptionHandlerResult.shared_dir_refs): a synthesized, behavior-
    # preserving expression, used only if program_import.py can't confirm
    # shared_dir_refs[label] against a real shared directory.
    value = f'$(debasher::get_absolute_shdirname "{shdirname[0]}")'
    if state.subpath:
        state.facts.subpaths[label[0]] = state.subpath
        value = f"{value}/{state.subpath}"
    state.facts.values[label[0]] = value
    return True


def _record_process_outdir(state: _ParseState, func: str, tokens: list, mirrored: bool) -> bool:
    # The process output directory, or a task subdirectory of it: nothing
    # to capture but the label and the subpath, its option gets channel
    # "process_outdir" (see program_import.py).
    label = tokens[0]
    if not label[1]:
        return False
    state.facts.process_outdir_labels.add(label[0])
    if state.subpath:
        state.facts.subpaths[label[0]] = state.subpath
    return True


def _record_value_desc(state: _ParseState, func: str, tokens: list, mirrored: bool) -> bool:
    # Its value is an engine-synthesized descriptor for the process's own
    # output, consumed elsewhere via define_opt_from_proc_out: nothing to
    # capture but the label, so its option gets channel "value_desc"
    # instead (see program_import.py).
    label = tokens[0]
    if not label[1]:
        return False
    state.facts.value_descriptor_labels.add(label[0])
    return True


def _record_fifo(state: _ParseState, func: str, tokens: list, mirrored: bool) -> bool:
    # Unlike define_value_desc_opt, the fifo name IS a real, user-chosen
    # value (not engine-synthesized), kept the same way as a plain
    # define_opt's value, alongside marking the option's channel as "fifo".
    label, value = tokens[0], tokens[1]
    if not label[1]:
        return False
    value_text, ok = state.chase(value[0])
    if not ok:
        return False
    state.facts.values[label[0]] = value_text
    state.facts.fifo_labels.add(label[0])
    if mirrored:
        state.facts.mirrored_fifo_labels.add(label[0])
    return True


def _record_procspec(state: _ParseState, func: str, tokens: list, mirrored: bool) -> bool:
    # <process_spec> <label> <specname> <optlist>. specname isn't chased
    # through locals (unlike define_opt/define_fifo_opt's value):
    # script_generation.py always regenerates it as a literal, never a
    # computed expression, so anything else isn't this grammar at all.
    label, specname = tokens[1], tokens[2]
    if not (label[1] and specname[1]):
        return False
    state.facts.values[label[0]] = specname[0]
    state.facts.procspec_labels.add(label[0])
    return True


def _record_flag(state: _ParseState, func: str, tokens: list, mirrored: bool) -> bool:
    return tokens[0][1]


def _record_cmdline(state: _ParseState, func: str, tokens: list, mirrored: bool) -> bool:
    # The seven define_cmdline_* variants: <cmdline_ref> <label> <optlist>.
    return tokens[1][1]


_CALL_RECORDERS = {
    "define_opt_from_proc_out": _record_connection,
    "define_opt_from_proc_task_out": _record_connection,
    "define_opt": _record_literal,
    "define_infile_opt": _record_literal,
    "define_indir_opt": _record_literal,
    "define_opt_from_shared_dir": _record_shared_dir,
    "define_opt_from_process_outdir": _record_process_outdir,
    "define_value_desc_opt": _record_value_desc,
    "define_fifo_opt": _record_fifo,
    "define_fifo_opt_generator": _record_fifo,
    "define_procspec_opt": _record_procspec,
    "define_flag": _record_flag,
}


def _parse_primitive_calls(
    body: list[str],
    allow_fanout_blocks: bool = False,
    allow_fanout_consumer: bool = False,
    initial_locals: dict[str, str] | None = None,
    initial_known_local_names: set[str] | None = None,
) -> _OptionFacts | None:
    """
    Parses a function body against the closed grammar of option-
    definition primitives, and returns what it learns of the options
    (_OptionFacts). It is used for _define_opts (standard and, inside
    the loop, array mode) and (per-task) _generate_opts bodies alike,
    which all share the same call vocabulary. None means the body
    contains something outside that grammar (control flow, a computed
    call target, an unsupported call).

    `allow_fanout_blocks` (only ever set for a "standard" _define_opts
    body — see resolve_options_handler) additionally recognizes the
    fanout-family block shape (see _try_parse_fanout_block).

    `allow_fanout_consumer` (only ever set for an array-mode loop body
    or a generator body, see _parse_array_define_opts and
    _resolve_generator) additionally accepts a define_opt_from_proc_out
    whose connected option name is "<base>${task_idx}" instead of a
    plain literal, reconstructing it as a connection to that "standard"
    process's "<base>-ith" fanout family.

    `initial_locals`/`initial_known_local_names` seed the local-chasing
    state (see _resolve_embedded_refs/_chase_local_value) — only ever
    set for an array-mode loop body, whose preceding arrayCode section
    is otherwise kept opaque/verbatim (see _parse_array_define_opts):
    without this, a local declared there (e.g. geno-debasher's
    `local abs_splitdir=`get_absolute_shdirname ...``, used by a loop-
    body option built as `"${abs_splitdir}"/name_${contig}.bam`) would
    look like a genuinely global name to the loop body's own parse,
    since it never saw the declaration — letting a dangling reference
    to it through instead of correctly rejecting the body to "manual".
    """
    state = _ParseState(
        facts=_OptionFacts(),
        locals_table=dict(initial_locals) if initial_locals else {},
        known_local_names=set(initial_known_local_names) if initial_known_local_names else set(),
        allow_fanout_consumer=allow_fanout_consumer,
    )

    i = 0
    while i < len(body):
        line = body[i]

        if _is_skipped_line(line):
            i += 1
            continue

        if allow_fanout_blocks:
            fanout_match = _try_parse_fanout_block(body, i)
            if fanout_match is not None:
                _record_fanout_block(state, fanout_match)
                i += fanout_match[0]
                continue

        if _record_local(state, line):
            i += 1
            continue

        call_match = _DEFINE_OPTS_CALL_RE.match(line)
        if not call_match:
            # Control flow (if/for/while/case/...), a computed call target,
            # or any other statement outside the known grammar.
            return None

        func = call_match.group("func")
        tokens, mirrored, state.subpath = _strip_trailing_flags(func, _tokenize(call_match.group("args") or ""))
        if len(tokens) != _CALL_TOKEN_COUNTS[func]:
            return None
        if not _CALL_RECORDERS.get(func, _record_cmdline)(state, func, tokens, mirrored):
            return None

        i += 1

    return state.facts


def _parse_function_source(
    source: str,
    allow_fanout_blocks: bool = False,
    allow_fanout_consumer: bool = False,
) -> _OptionFacts | None:
    body = function_body_lines(source)
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
_ARRAY_FOR_RE = re.compile(rf'^for\s+{TASK_IDX_VAR}\s+in\s+"\$\{{!array\[@\]\}}"$')
# The declaration that script generation writes right before that loop,
# so that the loop variable is local to _define_opts. Optional: a
# module written by hand may leave it out, and it is never part of
# arrayCode either way.
_ARRAY_LOCAL_IDX_RE = re.compile(rf"^local\s+{TASK_IDX_VAR}$")
_ARRAY_DO_LINE = "do"
_ARRAY_DONE_LINE = "done"

# Verbatim counterpart to _ARRAY_FOR_RE: the normalized `declare -f` body
# _ARRAY_FOR_RE matches against always has "for ...; do" split across two
# lines (bash's own declare -f pretty-printing), but a hand/DeBasher-
# authored source overwhelmingly writes it as a single "for ...; do"
# line instead (see e.g. share/debasher/programs/debasher_array_example.
# sh) -- so this optionally allows the same trailing "; do" inline.
_VERBATIM_ARRAY_FOR_RE = re.compile(rf'^for\s+{TASK_IDX_VAR}\s+in\s+"\$\{{!array\[@\]\}}"\s*(?:;\s*do)?$')


def _scan_locals(lines: list[str]) -> tuple[dict[str, str], set[str]]:
    """
    Extracts `local NAME=EXPR` assignments from `lines` (in order,
    chasing each against the ones before it — see
    _resolve_embedded_refs) without validating anything else about
    `lines` — used only to seed _parse_primitive_calls's local-chasing
    state for a loop body from its own arrayCode section, which is
    otherwise left opaque/verbatim (see _parse_array_define_opts).
    """
    locals_table: dict[str, str] = {}
    known_local_names: set[str] = set()
    for line in lines:
        local_match = _LOCAL_ASSIGN_RE.match(line)
        if not local_match:
            continue
        name = local_match.group("name")
        expr = _strip_one_quote_layer(local_match.group("expr"))
        resolved = _resolve_embedded_refs(expr, locals_table, known_local_names)
        if resolved is not None:
            locals_table[name] = resolved
        known_local_names.add(name)
    return locals_table, known_local_names


def _array_code_end(lines: list[str], for_index: int, normalize) -> int:
    """
    Where arrayCode ends in `lines`, the part of an array-mode body after
    its header: at the loop (`for_index`), or at the `local task_idx`
    declaration right before it, skipping any blank or comment lines in
    between. `normalize` turns a line into the form the regexes match.
    """
    i = for_index - 1
    while i >= 0 and (not normalize(lines[i]) or normalize(lines[i]).startswith("#")):
        i -= 1
    if i >= 0 and _ARRAY_LOCAL_IDX_RE.match(normalize(lines[i])):
        return i
    return for_index


def _parse_array_define_opts(source: str) -> tuple[str, _OptionFacts] | None:
    """
    Recognizes script_generation.py's exact array-mode shape (see
    _add_array_opts_func) in a _define_opts body: the standard header
    minus "local optlist=...", then arbitrary user code (kept verbatim
    as the returned arrayCode), then an optional `local task_idx`, then
    `for task_idx in "${!array[@]}"; do`, then a loop body that's itself
    just a plain option-definition body (`local optlist=""`, a flat
    sequence of option-definition primitives, `save_opt_list optlist`),
    parsed by _parse_primitive_calls exactly like a standard/generator
    body (its own header/footer-boilerplate skipping handles those two
    lines), then `done` and nothing else.

    None for anything that deviates from that — a different loop shape,
    trailing statements after the loop, a stray non-primitive call in
    the loop body, etc. — leaving the caller to fall back to "manual".
    """
    body = function_body_lines(source)
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

    code_end = _array_code_end(rest, for_index, lambda line: line)
    array_code = "\n".join(rest[:code_end]).strip()
    loop_body = rest[for_index + 2:-1]

    # array_code precedes the loop and is otherwise kept opaque/verbatim
    # (arbitrary user code) — but a local it declares (e.g. geno-
    # debasher's `local abs_splitdir=`get_absolute_shdirname ...``) may
    # still be referenced by a loop-body option's own local (see
    # _resolve_embedded_refs), so its locals are scanned (not otherwise
    # parsed/validated) to seed the loop body's chasing state.
    seed_locals, seed_known_local_names = _scan_locals(rest[:code_end])

    # allow_fanout_consumer: the loop body may connect to a "standard"
    # process's fanout family via "<base>${task_idx}" (see
    # _FANOUT_CONSUMER_OPT_RE); array mode has no fanout family
    # options of its own, so allow_fanout_blocks stays off.
    facts = _parse_primitive_calls(
        loop_body,
        allow_fanout_consumer=True,
        initial_locals=seed_locals,
        initial_known_local_names=seed_known_local_names,
    )
    if facts is None:
        return None
    return array_code, facts


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


def scan_fifo_tags(source: str) -> dict[str, str]:
    """
    The fifo tag of every define_fifo_opt[_generator] call of `source` that
    carries one, by option label. A call in a fanout-family block, whose
    label is "<base>${i}", gives the tag to the family, "<base>-ith".
    """
    tags = {}
    for match in _TAGGED_FIFO_SCAN_RE.finditer(source):
        label = match.group("label")
        family = _FANOUT_BLOCK_LABEL_RE.match(label)
        tags[f"{family.group('base')}-ith" if family else label] = match.group("tag")
    return tags


def scan_mirrored_fifo_labels(source: str) -> set[str]:
    """Best-effort companion to scan_fifo_labels, same reasoning."""
    return {match.group("label") for match in _MIRRORED_FIFO_SCAN_RE.finditer(source)}


def scan_procspec_values(source: str) -> dict[str, str]:
    """
    Best-effort companion to scan_connections, for the same reason —
    but unlike scan_value_descriptor_labels/scan_fifo_labels, the spec
    attribute name is captured too (see _PROCSPEC_SCAN_RE), the same way
    scan_shared_dir_refs captures its own dirname: label -> spec
    attribute name, doubling as the option's option_values entry so a
    process that falls back to "manual" still shows the right dropdown
    selection instead of a blank one.
    """
    return {
        match.group("label"): match.group("specname")
        for match in _PROCSPEC_SCAN_RE.finditer(source)
    }


def scan_procspec_labels(source: str) -> set[str]:
    """Best-effort companion to scan_connections/scan_value_descriptor_labels, same reasoning."""
    return set(scan_procspec_values(source))


def _extract_generator_size_code(source: str) -> str | None:
    """
    Returns _generate_opts_size's body, verbatim (declare -f-normalized —
    see function_body_lines — so relative indentation within it is
    flattened, same as arrayCode via _parse_array_define_opts), minus the
    fixed header script_generation.py's _add_generate_opts_size_func
    always emits ahead of it (the same header as _define_opts minus
    "local optlist=" — engine calls this with the same 4 positional args,
    see debasher::_define_opts_generator). None if the header isn't
    present in that exact form, or the source isn't a well-formed
    function dump.
    """
    body = function_body_lines(source)
    if body is None:
        return None
    if len(body) < len(_ARRAY_HEADER_RES):
        return None
    for regex, line in zip(_ARRAY_HEADER_RES, body):
        if not regex.match(line):
            return None
    return "\n".join(body[len(_ARRAY_HEADER_RES):]).strip()


def _verbatim_whole_function(script_path: Path, code: str, debasher_mod_dir: str) -> str:
    """
    Best-effort upgrade of a whole `declare -f` function dump to its
    exact original source, comments and indentation intact (see
    doc_mod.run_get_verbatim_func_source) -- mirrors program_import.
    _verbatim_code/routers/processes._verbatim_code, used here for
    manualCode, which -- unlike arrayCode/generatorSizeCode -- is
    embedded as a complete function definition, header included (see
    script_generation.py's "manual" mode, which returns handler.
    manualCode as-is with no re-wrapping). Falls back to `code` unchanged
    whenever the upgrade isn't available.
    """
    if not code:
        return code
    funcname = function_header_name(code)
    if funcname is None:
        return code
    verbatim = run_get_verbatim_func_source(script_path, funcname, debasher_mod_dir)
    return verbatim if verbatim else code


def _skip_verbatim_header(body: list[str]) -> int | None:
    """
    Finds where the shared _ARRAY_HEADER_RES 4-line boilerplate ends
    within a verbatim function body, tolerating any number of leading
    blank/comment-only lines before it -- e.g. a "# Initialize
    variables" comment, which is how virtually every DeBasher-authored
    process introduces its header (see share/debasher/programs/*.sh).
    Matching straight against body[:4] (as if the header always were the
    body's literal first 4 lines, true of the normalized `declare -f`
    body this mirrors, since declare -f strips comments entirely) would
    essentially never match a verbatim body in practice.

    None if no such 4-line run immediately follows the leading blank/
    comment lines.
    """
    start = 0
    while start < len(body) and (not body[start].strip() or body[start].strip().startswith("#")):
        start += 1
    end = start + len(_ARRAY_HEADER_RES)
    if end > len(body):
        return None
    for regex, line in zip(_ARRAY_HEADER_RES, body[start:end]):
        if not regex.match(line.strip()):
            return None
    return end


def _verbatim_header_stripped_body(script_path: Path, code: str, debasher_mod_dir: str) -> str | None:
    """
    Best-effort verbatim counterpart to _extract_generator_size_code's
    normalized header-stripping: recovers the exact original body of the
    function whose `declare -f` dump is `code`, with the shared
    _ARRAY_HEADER_RES boilerplate (_define_opts_func_header's 4 fixed
    lines) removed from the front -- matched against each line's own
    stripped text, so the author's original indentation never affects
    whether the header is recognized -- keeping every remaining line
    exactly as written otherwise.

    None if `code` is empty, has no resolvable function name, the
    verbatim source can't be recovered at all, or that verbatim source
    doesn't happen to start with the same 4-line header in that exact
    form -- the caller falls back to the already-normalized value in
    every such case, same as if this verbatim upgrade didn't exist.
    """
    if not code:
        return None
    funcname = function_header_name(code)
    if funcname is None:
        return None
    verbatim = run_get_verbatim_func_source(script_path, funcname, debasher_mod_dir)
    if not verbatim:
        return None
    body = verbatim_function_body_lines(verbatim)
    if body is None:
        return None
    header_end = _skip_verbatim_header(body)
    if header_end is None:
        return None
    return join_verbatim_body_lines(body[header_end:])


def _find_verbatim_array_for_index(rest: list[str]) -> int | None:
    """
    Verbatim counterpart to matching _ARRAY_FOR_RE at a fixed index: the
    "; do" may be inline (see _VERBATIM_ARRAY_FOR_RE) or on its own next
    line (_ARRAY_DO_LINE, same as the normalized shape) -- either is
    accepted. None if no line matches the for-loop shape at all, or one
    does but isn't actually followed by a "do" either way (malformed).
    """
    for i, line in enumerate(rest):
        stripped = line.strip()
        if not _VERBATIM_ARRAY_FOR_RE.match(stripped):
            continue
        if stripped.endswith("do"):
            return i
        if i + 1 < len(rest) and rest[i + 1].strip() == _ARRAY_DO_LINE:
            return i
        return None
    return None


def _verbatim_array_code(script_path: Path, code: str, debasher_mod_dir: str) -> str | None:
    """
    Best-effort verbatim counterpart to _parse_array_define_opts's own
    header/loop-boundary trim: same idea as _verbatim_header_stripped_body,
    but additionally cuts off at the "for task_idx in ..." loop marker
    (see _ARRAY_FOR_RE), and at the "local task_idx" right before it
    when there is one: arrayCode is only ever the code *before* that loop;
    script_generation.py's _add_array_opts_func re-emits the loop itself
    fresh from the process's parsed options, never from stored text.
    """
    if not code:
        return None
    funcname = function_header_name(code)
    if funcname is None:
        return None
    verbatim = run_get_verbatim_func_source(script_path, funcname, debasher_mod_dir)
    if not verbatim:
        return None
    body = verbatim_function_body_lines(verbatim)
    if body is None:
        return None
    header_end = _skip_verbatim_header(body)
    if header_end is None:
        return None
    rest = body[header_end:]
    for_index = _find_verbatim_array_for_index(rest)
    if for_index is None:
        return None
    return join_verbatim_body_lines(rest[:_array_code_end(rest, for_index, str.strip)])


def resolve_options_handler(
    option_handler_code: dict[str, str], script_path: Path, debasher_mod_dir: str = ""
) -> OptionHandlerResult:
    result = _resolve_options_handler_mode(option_handler_code, script_path, debasher_mod_dir)
    result.fifo_tags = scan_fifo_tags("\n".join(option_handler_code.values()))
    return result


def _result(handler: OptionsHandler, facts: _OptionFacts | None = None) -> OptionHandlerResult:
    """The result of resolving an options handler, with the facts learned
    of its options, none for a handler whose options are unknown."""
    facts = facts or _OptionFacts()
    return OptionHandlerResult(
        handler=handler,
        option_values=facts.values,
        connections=facts.connections,
        value_descriptor_labels=facts.value_descriptor_labels,
        fifo_labels=facts.fifo_labels,
        mirrored_fifo_labels=facts.mirrored_fifo_labels,
        procspec_labels=facts.procspec_labels,
        fanout_count_source_labels=facts.fanout_count_source_labels,
        shared_dir_refs=facts.shared_dir_refs,
        process_outdir_labels=facts.process_outdir_labels,
        subpaths=facts.subpaths,
    )


def _scanned_facts(source: str) -> _OptionFacts:
    """
    What can still be recovered, on a best-effort basis, of the options of
    a function that does not fit the grammar: a process that falls back to
    "manual" still shouldn't show a connected, value-descriptor, fifo or
    process-spec option as if it were a fixed-value one just because its
    call happened to sit inside whatever unparseable statement caused the
    fallback.
    """
    return _OptionFacts(
        values=scan_procspec_values(source),
        connections=scan_connections(source),
        value_descriptor_labels=scan_value_descriptor_labels(source),
        fifo_labels=scan_fifo_labels(source),
        mirrored_fifo_labels=scan_mirrored_fifo_labels(source),
        procspec_labels=scan_procspec_labels(source),
        shared_dir_refs=scan_shared_dir_refs(source),
        process_outdir_labels=scan_process_outdir_labels(source),
        subpaths=scan_subpaths(source),
    )


def _resolve_generator(
    generate_opts_size: str, generate_opts: str | None, script_path: Path, debasher_mod_dir: str
) -> OptionHandlerResult:
    generator_size_code = _extract_generator_size_code(generate_opts_size)
    # allow_fanout_consumer: like array mode, a generator's per-task body
    # may connect to a "standard" process's fanout family via
    # "<base>${task_idx}" (see _FANOUT_CONSUMER_OPT_RE and
    # script_generation.py's _FANOUT_PARTNER_MODES); generator mode has no
    # fanout family options of its own, so allow_fanout_blocks stays off.
    facts = _parse_function_source(generate_opts, allow_fanout_consumer=True) if generate_opts else None

    # A _generate_opts_size with no _generate_opts alongside it can't
    # actually retrieve a task's options at run time (the engine always
    # needs the latter once the former exists): it is treated as an
    # incomplete generator, with no facts, rather than guessing further.
    if generator_size_code is not None and (facts is not None or not generate_opts):
        verbatim_size_code = _verbatim_header_stripped_body(script_path, generate_opts_size, debasher_mod_dir)
        handler = OptionsHandler(
            mode="generator",
            generatorSizeCode=verbatim_size_code if verbatim_size_code is not None else generator_size_code,
        )
        return _result(handler, facts)

    # generate_opts doesn't fit the primitive-call grammar:
    # script_generation.py can't reproduce it, so this falls back to manual
    # with everything kept verbatim.
    combined = f"{generate_opts_size}\n\n{generate_opts}" if generate_opts else generate_opts_size
    combined_verbatim = _verbatim_whole_function(script_path, generate_opts_size, debasher_mod_dir)
    if generate_opts:
        combined_verbatim = f"{combined_verbatim}\n\n{_verbatim_whole_function(script_path, generate_opts, debasher_mod_dir)}"
    return _result(OptionsHandler(mode="manual", manualCode=combined_verbatim), _scanned_facts(combined))


def _resolve_define_opts(define_opts: str, script_path: Path, debasher_mod_dir: str) -> OptionHandlerResult:
    # allow_fanout_blocks: a "standard" body may contain one or more
    # fanout-family blocks (see _try_parse_fanout_block) interleaved among
    # the flat primitive calls.
    facts = _parse_function_source(define_opts, allow_fanout_blocks=True)
    if facts is not None:
        return _result(OptionsHandler(mode="standard"), facts)

    # Not the flat "standard" grammar: try script_generation.py's fixed
    # array-mode shape (see _parse_array_define_opts) before giving up to
    # "manual".
    array_parsed = _parse_array_define_opts(define_opts)
    if array_parsed is not None:
        array_code, facts = array_parsed
        verbatim_array_code = _verbatim_array_code(script_path, define_opts, debasher_mod_dir)
        handler = OptionsHandler(
            mode="array",
            arrayCode=verbatim_array_code if verbatim_array_code is not None else array_code,
        )
        return _result(handler, facts)

    manual_code = _verbatim_whole_function(script_path, define_opts, debasher_mod_dir)
    return _result(OptionsHandler(mode="manual", manualCode=manual_code), _scanned_facts(define_opts))


def _resolve_options_handler_mode(
    option_handler_code: dict[str, str], script_path: Path, debasher_mod_dir: str = ""
) -> OptionHandlerResult:
    """The mode of the options handler of a process, from the shape of its
    option definition functions, with what they say of its options: a
    generator, then a standard or array _define_opts, else manual."""
    generate_opts_size = option_handler_code.get(PROCESS_METHOD_GENERATE_OPTS_SIZE_SUFFIX)
    if generate_opts_size:
        generate_opts = option_handler_code.get(PROCESS_METHOD_GENERATE_OPTS_SUFFIX)
        return _resolve_generator(generate_opts_size, generate_opts, script_path, debasher_mod_dir)
    define_opts = option_handler_code.get(PROCESS_METHOD_DEFINE_OPTS_SUFFIX)
    if define_opts:
        return _resolve_define_opts(define_opts, script_path, debasher_mod_dir)
    return _result(OptionsHandler(mode="standard"))
