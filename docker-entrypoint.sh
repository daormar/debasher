#!/bin/bash
# Entry point of the DeBasher demo image (see Dockerfile).
#
# Before starting the web UI, copies each program of
# data/webui_programs, installed under the package's data directory,
# into the demo directory, where the "debasher" user can load, change,
# save and run it. A program already there is left as it is, so the
# changes made to it survive a restart, and one added to
# data/webui_programs in a newer image shows up on the next start. The
# programs are copied side by side, as they are installed, so that the
# relative path by which one names another still resolves.

set -euo pipefail

shipped_dir=/usr/local/share/debasher/webui_programs
demo_dir="${DEBASHER_DEMO_DIR:-/data}/webui_programs"

if [ -d "${shipped_dir}" ]; then
    if mkdir -p "${demo_dir}" 2>/dev/null && [ -w "${demo_dir}" ]; then
        # Writable by everyone, as the demo directory is: on the host,
        # its owner is rarely the uid of "debasher"
        chmod a+rwx "${demo_dir}" 2>/dev/null || true
        for prg in "${shipped_dir}"/*/; do
            name=$(basename "${prg}")
            if [ ! -e "${demo_dir}/${name}" ]; then
                cp -R "${prg%/}" "${demo_dir}/${name}"
                chmod -R a+rwX "${demo_dir}/${name}"
            fi
        done
    else
        echo "Warning: ${demo_dir} is not writable, the example programs are not copied there" >&2
    fi
fi

exec debasher_webui "$@"
