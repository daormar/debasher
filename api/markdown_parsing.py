import re
from typing import Literal

from pydantic import BaseModel

# Parses the Markdown produced by debasher::_show_process_documentation
# (engine/debasher_lib_processes.sh) for a single process, e.g.:
#
#   ## generate
#
#   ### Description
#   Generates a text file of a given size and random content.
#
#   ### Process Options
#   - `-outf` string output file
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
# option's type as a bare word right after the label, with no markup
# around it — only present at all when the option was declared with
# debasher::explain_opt (typed) rather than debasher::explain_flag.
_OPTION_TYPE_RE = re.compile(r"^(?P<type>int|float|string)\s+(?P<rest>.*)$")
_OPTION_FLAGS_RE = re.compile(r"^(?P<desc>.*?)\s*\((?P<flags>[^)]*)\)\s*$")
_CODE_FENCE_START_RE = re.compile(r"^```(?P<lang>\S*)\s*$")

_PROCESS_LANGUAGES: set[str] = {"bash", "python", "perl", "r", "groovy"}

OptionDataType = Literal["int", "float", "string", "None"]
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


def parse_proc_info_markdown(markdown: str) -> ProcessInfo:
    sections = split_markdown_sections(markdown)

    description = "\n".join(sections.get("Description", [])).strip()
    options = parse_options(sections.get("Process Options", []))
    language, code = parse_code(sections.get("Process Implementation", []))

    return ProcessInfo(
        description=description,
        options=options,
        language=language,
        code=code,
    )
