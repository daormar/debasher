# *- bash -*

# The tool that writes a program described in Python with the SDK (see
# debasher/build.py): a launcher that chooses the Python to run it with,
# as debasher_webui does, since the SDK needs the dependencies of the API
# of the web UI (pydantic 2), which usually live in a virtual environment.
# Built by sdk/python/Makefile.am with the directories of the installation
# in front of this file.

########
resolve_python()
{
    # Prefer an explicit override, then whatever "python3" resolves to on
    # the PATH (an activated virtual environment), falling back to the
    # interpreter found at configure time.
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
    if ! "${PYTHON}" -c "import pydantic; assert int(pydantic.VERSION.split('.')[0]) >= 2" >/dev/null 2>&1; then
        echo "Error: the Python packages required by the SDK are not installed" >&2
        echo "for interpreter: ${PYTHON}" >&2
        echo "" >&2
        echo "Install them into a virtual environment, then run debasher_build with" >&2
        echo "that environment activated:" >&2
        echo "" >&2
        echo "    python3 -m venv /path/to/debasher-venv" >&2
        echo "    source /path/to/debasher-venv/bin/activate" >&2
        echo "    pip install -r \"${debasher_pkgdatadir}/api/requirements.txt\"" >&2
        echo "    debasher_build <program>.py" >&2
        echo "" >&2
        echo "If activating isn't practical, point debasher_build at the interpreter" >&2
        echo "directly instead, as for debasher_webui:" >&2
        echo "" >&2
        echo "    DEBASHER_WEBUI_PYTHON=/path/to/debasher-venv/bin/python3 debasher_build <program>.py" >&2
        exit 1
    fi
}

########

resolve_python

check_deps

# The package `debasher` is installed in the Python directory of the
# package; in the source tree it is beside this launcher, before any
# installation.
sdk_pythonpath="${debasher_pythondir}"
tool_dir=$(cd "$(dirname "$0")" && pwd)
if [ -f "${tool_dir}/debasher/__init__.py" ]; then
    sdk_pythonpath="${tool_dir}:${sdk_pythonpath}"
fi

PYTHONPATH="${sdk_pythonpath}${PYTHONPATH:+:${PYTHONPATH}}" \
    exec "${PYTHON}" -m debasher.build "$@"
