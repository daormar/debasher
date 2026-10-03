# DeBasher package
# Copyright (C) 2019-2026 Daniel Ortiz-Mart\'inez
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public License
# as published by the Free Software Foundation; either version 3
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program; If not, see <http://www.gnu.org/licenses/>.


# *- bash -*

# debasher_claude starts Claude Code on a DeBasher program saved in its home
# directory, with what DeBasher gives it: the MCP server (debasher_mcp),
# talking to the backend of the web UI at the URL given; the permissions of
# its tools (debasher_mcp --claude-settings); and the plugin of DeBasher, whose
# skills help with the web UI, design a program, write the code of its
# processes and their tests, and review that code. The session starts in the
# home directory, with one of those skills when a mode is given.

########
print_desc()
{
    echo "debasher_claude starts Claude Code on a DeBasher program"
    echo "type \"debasher_claude --help\" to get usage information"
}

########
usage()
{
    echo "debasher_claude            --home-dir <string> [--url <string>]"
    echo "                           [--mode <string>] [--prompt <string>]"
    echo "                           [--dry-run] [--help] [-- <claude options>]"
    echo ""
    echo "--home-dir <string>        Home directory of the program, where the web"
    echo "                           UI saved it"
    echo "--url <string>             URL of the backend of the web UI (default:"
    echo "                           ${DEFAULT_URL})"
    echo "--mode <string>            Skill that the session starts with: help (the"
    echo "                           web UI and DeBasher), design (the processes and"
    echo "                           their connections), implement (the code of the"
    echo "                           processes and their tests) or review (feedback"
    echo "                           on the code and the tests); without it, the"
    echo "                           session starts with none, and any of them can"
    echo "                           be called later as /debasher:<mode>"
    echo "--prompt <string>          First message of the session, given to the"
    echo "                           skill of the mode when there is one"
    echo "--dry-run                  Print the command that starts Claude Code"
    echo "                           instead of running it"
    echo "--help                     Display this help and exit"
    echo ""
    echo "What follows -- is passed to Claude Code as it is. DEBASHER_CLAUDE_CMD"
    echo "names the command of Claude Code (default: claude)."
}

########
read_pars()
{
    home_dir_given=0
    url="${DEFAULT_URL}"
    mode=""
    prompt=""
    dry_run=0
    claude_args=()
    while [ $# -ne 0 ]; do
        case $1 in
            "--help") usage
                      exit 0
                      ;;
            "--home-dir") shift
                          if [ $# -ne 0 ]; then
                              home_dir=$1
                              home_dir_given=1
                          fi
                          ;;
            "--url") shift
                     if [ $# -ne 0 ]; then
                         url=$1
                     fi
                     ;;
            "--mode") shift
                      if [ $# -ne 0 ]; then
                          mode=$1
                      fi
                      ;;
            "--prompt") shift
                        if [ $# -ne 0 ]; then
                            prompt=$1
                        fi
                        ;;
            "--dry-run") dry_run=1
                         ;;
            "--") shift
                  claude_args=("$@")
                  break
                  ;;
            *) echo "Error: unknown option $1" >&2
               print_desc >&2
               exit 1
               ;;
        esac
        shift
    done
}

########
check_pars()
{
    if [ ${home_dir_given} -eq 0 ]; then
        echo "Error: --home-dir option should be given" >&2
        exit 1
    fi

    if [ ! -d "${home_dir}" ]; then
        echo "Error: ${home_dir} is not a directory" >&2
        exit 1
    fi

    # The tools of the MCP server work on a program saved in its home
    # directory, as the web UI saves it.
    if [ ! -f "${home_dir}/.debasher/program.json" ]; then
        echo "Error: no program is saved in ${home_dir}: save it from the web UI first" >&2
        exit 1
    fi

    case "${mode}" in
        ""|"help"|"design"|"implement"|"review") ;;
        *) echo "Error: unknown mode ${mode}: it should be help, design, implement or review" >&2
           exit 1
           ;;
    esac
}

########
resolve_claude()
{
    CLAUDE="${DEBASHER_CLAUDE_CMD:-claude}"
    if [ ${dry_run} -eq 0 ] && ! command -v "${CLAUDE}" >/dev/null 2>&1; then
        echo "Error: Claude Code was not found (${CLAUDE})" >&2
        echo "Install it (see https://claude.com/claude-code), or point" >&2
        echo "DEBASHER_CLAUDE_CMD at it" >&2
        exit 1
    fi
}

########
json_string()
{
    # A JSON string holding $1: backslashes and double quotes escaped.
    local value=$1
    value=${value//\\/\\\\}
    value=${value//\"/\\\"}
    printf '"%s"' "${value}"
}

########

DEFAULT_URL="http://127.0.0.1:8000"

read_pars "$@"

check_pars

resolve_claude

home_dir=$(cd "${home_dir}" && pwd)

# The name of the server, which names its tools mcp__debasher__<tool>, has to
# be the one that the permissions name (SERVER_NAME in claudeSettings.ts of
# the MCP server).
mcp_config="{\"mcpServers\":{\"debasher\":{\"command\":$(json_string "${debasher_bindir}/debasher_mcp"),\"args\":[\"--url\",$(json_string "${url}")]}}}"

if ! settings=$("${debasher_bindir}/debasher_mcp" --claude-settings); then
    echo "Error: debasher_mcp could not give the settings of Claude Code" >&2
    exit 1
fi

system_prompt="You work on the DeBasher program whose home directory is ${home_dir}, the current directory: give it as home_dir to the tools of the debasher MCP server, which talk to the backend of the web UI at ${url}. The user may have the program open in the editor of the web UI, which loads again what your tools save."

# Without symbolic links, as Claude Code compares the paths it reads with the
# rule below.
if ! plugin_dir=$(cd "${debasher_pkgdatadir}/claude/plugin" 2>/dev/null && pwd -P); then
    echo "Error: the plugin of DeBasher is missing from ${debasher_pkgdatadir}/claude/plugin" >&2
    exit 1
fi

# The skills read the reference of the plugin, outside the home directory,
# which Claude Code is allowed to read, and only to read, without asking (an
# absolute path is written with a leading "//" in a rule).
command=("${CLAUDE}"
         --plugin-dir "${plugin_dir}"
         --allowedTools "Read(/${plugin_dir}/**)"
         --mcp-config "${mcp_config}"
         --settings "${settings}"
         --append-system-prompt "${system_prompt}")

command+=("${claude_args[@]}")

# The first message: the skill of the mode, which takes the prompt as its
# arguments, or else the prompt alone. Claude Code takes a single one, after
# "--", so that an option that takes several values (--allowedTools, ...)
# never takes it as one of them.
first_message="${prompt}"
if [ -n "${mode}" ]; then
    first_message="/debasher:${mode}${prompt:+ ${prompt}}"
fi
if [ -n "${first_message}" ]; then
    command+=(-- "${first_message}")
fi

if [ ${dry_run} -eq 1 ]; then
    echo "cd $(printf '%q' "${home_dir}") && $(printf '%q ' "${command[@]}")"
    exit 0
fi

cd "${home_dir}" || exit 1

exec "${command[@]}"
