import re
from typing import Literal

from pydantic import BaseModel, Field

from .debasher_constants import (
    PROCESS_METHOD_DEFINE_OPT_DEPS_SUFFIX,
    PROCESS_METHOD_DEFINE_OPTS_SUFFIX,
    PROCESS_METHOD_GENERATE_OPTS_SIZE_SUFFIX,
    PROCESS_METHOD_GENERATE_OPTS_SUFFIX,
)

# Parses the Markdown produced by debasher::_show_process_documentation
# (engine/debasher_lib_processes.sh) for a single process, e.g.:
#
#   ## generate
#
#   ### Description
#   Generates a text file of a given size and random content.
#
#   ### Process Options
#   - `-outf` <string> output file
#   - `-v` verbose flag (command-line)
#
#   ### Process Methods
#   - `generate_document`
#
#   ### Process Variables
#
#   ### Process Implementation
#   ```bash
#   generate ()
#   { ... }
#   ```
#
# Shared by routers/processes.py (prefilling a process from an
# already-declared preamble function) and program_import.py (importing a
# whole program from an existing script's debasher_doc_mod output, which
# concatenates one of these blocks per process under a "# <module>"
# title).

_OPTION_LINE_RE = re.compile(r"^-\s*`(?P<label>[^`]+)`\s*(?P<rest>.*)$")
# debasher::_show_proc_opts (engine/debasher_lib_processes) prints the
# option's type right after the label, verbatim from whatever was passed
# as debasher::explain_opt's own $2 — angle-bracket-wrapped by
# convention throughout every script in data/programs ("<int>",
# "<string>", ...) — and only present at all when the option was
# declared with debasher::explain_opt (typed) rather than
# debasher::explain_flag. This is purely the value's type: how it's
# *delivered* (a plain value, a value descriptor, a fifo — see
# ProgramOption.channel in models.py) is a separate, independent axis,
# recovered instead from _define_opts/_generate_opts source by
# option_handler_import.py — an option's declared type and its actual
# channel can legitimately diverge (e.g. a mandatory cmdline int that's
# actually sourced from a fifo internally), so this section shouldn't
# try to encode both into one type keyword. "file" is included here
# (unlike value_desc/fifo) because there's no dedicated primitive call
# to recover it from _define_opts — a file-path option is defined with
# the exact same debasher::define_opt as any other string, so a
# declaration is the only place it can come from at all.
_OPTION_TYPE_RE = re.compile(r"^<(?P<type>int|float|string|file)>\s+(?P<rest>.*)$")
_OPTION_FLAGS_RE = re.compile(r"^(?P<desc>.*?)\s*\((?P<flags>[^)]*)\)\s*$")
_CODE_FENCE_START_RE = re.compile(r"^```(?P<lang>\S*)\s*$")

_PROCESS_LANGUAGES: set[str] = {"bash", "python", "perl", "r", "groovy"}

# debasher::_show_proc_opt_handler (engine/debasher_lib_processes) dumps
# one ```bash ... ``` block per option-handler function it finds for the
# process — any of _define_opts, _define_opt_deps, _generate_opts_size,
# _generate_opts — each as its own `declare -f` fence, back to back
# under a single "### Process Option Handler" heading. Longer suffixes
# are checked first only for readability; none of these four suffixes is
# actually a suffix of another, so match order doesn't affect the result.
_OPT_HANDLER_FUNC_SUFFIXES = [
    PROCESS_METHOD_GENERATE_OPTS_SIZE_SUFFIX,
    PROCESS_METHOD_DEFINE_OPT_DEPS_SUFFIX,
    PROCESS_METHOD_DEFINE_OPTS_SUFFIX,
    PROCESS_METHOD_GENERATE_OPTS_SUFFIX,
]
_FUNC_HEADER_RE = re.compile(r"^(?P<name>\S+)\s*\(\)")

OptionDataType = Literal["int", "float", "string", "file", "None"]
ProcessLanguage = Literal["bash", "python", "perl", "r", "groovy"]


class ProcessInfoOption(BaseModel):
    label: str
    dataType: OptionDataType
    description: str
    commandLine: bool
    mandatory: bool


class ProcessInfo(BaseModel):
    description: str
    options: list[ProcessInfoOption]
    language: ProcessLanguage
    code: str
    # Reserved method suffix (e.g. PROCESS_METHOD_DEFINE_OPTS_SUFFIX) ->
    # raw `declare -f` source (header + body) for that option-handler
    # function, for whichever of them the process actually defines. Only
    # populated when the Markdown was produced with --show-opthnd; empty
    # otherwise (see option_handler_import.py for what recovers from it).
    optionHandler: dict[str, str] = Field(default_factory=dict)


def split_markdown_sections(markdown: str) -> dict[str, list[str]]:
    """Group lines under their nearest "### <title>" heading."""
    sections: dict[str, list[str]] = {}
    current: str | None = None

    for line in markdown.splitlines():
        if line.startswith("### "):
            current = line[len("### "):].strip()
            sections[current] = []
        elif line.startswith("## "):
            current = None
        elif current is not None:
            sections[current].append(line)

    return sections


def parse_options(lines: list[str]) -> list[ProcessInfoOption]:
    options = []

    for line in lines:
        line_match = _OPTION_LINE_RE.match(line)
        if not line_match:
            continue

        label = line_match.group("label").strip()
        rest = line_match.group("rest")

        data_type: OptionDataType = "None"
        type_match = _OPTION_TYPE_RE.match(rest)
        if type_match:
            data_type = type_match.group("type")  # type: ignore[assignment]
            rest = type_match.group("rest")

        flags_match = _OPTION_FLAGS_RE.match(rest)
        if flags_match:
            description = flags_match.group("desc").strip()
            flags = [flag.strip() for flag in flags_match.group("flags").split(",")]
        else:
            description = rest.strip()
            flags = []

        options.append(
            ProcessInfoOption(
                label=label,
                dataType=data_type,
                description=description,
                commandLine="command-line" in flags,
                mandatory="mandatory" in flags,
            )
        )

    return options


def parse_code(lines: list[str]) -> tuple[ProcessLanguage, str]:
    language: ProcessLanguage = "bash"
    code_lines: list[str] = []
    in_fence = False

    for line in lines:
        if not in_fence:
            fence_match = _CODE_FENCE_START_RE.match(line)
            if fence_match:
                in_fence = True
                candidate = fence_match.group("lang")
                if candidate in _PROCESS_LANGUAGES:
                    language = candidate  # type: ignore[assignment]
        elif line.strip() == "```":
            break
        else:
            code_lines.append(line)

    return language, "\n".join(code_lines)


def parse_code_blocks(lines: list[str]) -> list[str]:
    """
    Like parse_code, but returns every ```<lang> ... ``` fenced block in
    `lines` (fence lines excluded) rather than just the first — for
    sections that may concatenate several of them back to back, such as
    "Process Option Handler".
    """
    blocks: list[str] = []
    current: list[str] | None = None

    for line in lines:
        if current is None:
            if _CODE_FENCE_START_RE.match(line):
                current = []
        elif line.strip() == "```":
            blocks.append("\n".join(current))
            current = None
        else:
            current.append(line)

    return blocks


def parse_option_handler(lines: list[str]) -> dict[str, str]:
    """Classifies each block from parse_code_blocks by the reserved
    method suffix its function name (first line, "<funcname> ()") ends
    with. A block whose name matches none of them is ignored."""
    handlers: dict[str, str] = {}

    for block in parse_code_blocks(lines):
        header_match = _FUNC_HEADER_RE.match(block.strip())
        if not header_match:
            continue
        funcname = header_match.group("name")
        for suffix in _OPT_HANDLER_FUNC_SUFFIXES:
            if funcname.endswith(suffix):
                handlers[suffix] = block
                break

    return handlers


def parse_proc_info_markdown(markdown: str) -> ProcessInfo:
    sections = split_markdown_sections(markdown)

    description = "\n".join(sections.get("Description", [])).strip()
    options = parse_options(sections.get("Process Options", []))
    language, code = parse_code(sections.get("Process Implementation", []))
    option_handler = parse_option_handler(sections.get("Process Option Handler", []))

    return ProcessInfo(
        description=description,
        options=options,
        language=language,
        code=code,
        optionHandler=option_handler,
    )
