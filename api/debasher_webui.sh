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

########
print_desc()
{
    echo "debasher_webui launches the DeBasher web interface (API + UI)"
    echo "type \"debasher_webui --help\" to get usage information"
}

########
usage()
{
    echo "debasher_webui             [--host <string>] [--port <int>]"
    echo "                           [--help]"
    echo ""
    echo "--host <string>            Address to bind to (default: 127.0.0.1)"
    echo "--port <int>               Port to listen on (default: 8000)"
    echo "--help                     Display this help and exit"
}

########
read_pars()
{
    host="127.0.0.1"
    port="8000"
    while [ $# -ne 0 ]; do
        case $1 in
            "--help") usage
                      exit 1
                      ;;
            "--host") shift
                      if [ $# -ne 0 ]; then
                          host=$1
                      fi
                      ;;
            "--port") shift
                      if [ $# -ne 0 ]; then
                          port=$1
                      fi
                      ;;
        esac
        shift
    done
}

########
resolve_python()
{
    # Prefer an explicit override, then whatever "python3" resolves to on
    # PATH (so an activated virtual environment is picked up automatically,
    # matching wherever the dependencies were pip-installed), falling back
    # to the interpreter found at configure time.
    if [ -n "${DEBASHER_WEBUI_PYTHON:-}" ]; then
        PYTHON="${DEBASHER_WEBUI_PYTHON}"
    elif command -v python3 >/dev/null 2>&1; then
        PYTHON="python3"
    else
        PYTHON="${debasher_default_python}"
    fi
}

########
check_deps()
{
    if ! "${PYTHON}" -c "import fastapi, uvicorn" >/dev/null 2>&1; then
        echo "Error: the Python packages required by the web interface are not installed" >&2
        echo "for interpreter: ${PYTHON}" >&2
        echo "" >&2
        echo "Install them into a virtual environment, then run debasher_webui with" >&2
        echo "that environment activated:" >&2
        echo "" >&2
        echo "    python3 -m venv /path/to/debasher-venv" >&2
        echo "    source /path/to/debasher-venv/bin/activate" >&2
        echo "    pip install -r \"${debasher_pkgdatadir}/api/requirements.txt\"" >&2
        echo "    debasher_webui" >&2
        echo "" >&2
        echo "When you're done, leave the virtual environment with: deactivate" >&2
        echo "" >&2
        echo "If activating isn't practical (e.g. launching from a systemd unit), point" >&2
        echo "debasher_webui at the interpreter directly instead:" >&2
        echo "" >&2
        echo "    DEBASHER_WEBUI_PYTHON=/path/to/debasher-venv/bin/python3 debasher_webui" >&2
        exit 1
    fi
}

########

read_pars "$@"

resolve_python

check_deps

# DEBASHER_WEBUI_STATIC_DIR tells api/main.py where the built frontend
# was installed, since it no longer sits next to main.py once installed.
export DEBASHER_WEBUI_STATIC_DIR="${debasher_pkgdatadir}/web"

echo "Once started, open http://${host}:${port}/ in your browser to use the web interface." >&2

exec "${PYTHON}" -m uvicorn api.main:app \
     --app-dir "${debasher_pkgdatadir}" \
     --host "${host}" \
     --port "${port}"
