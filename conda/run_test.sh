#!/bin/bash
set -euo pipefail

datadir="${PREFIX}/share/debasher"
tmpdir=$(mktemp -d)
trap 'rm -rf "${tmpdir}"' EXIT

# Every absolute path that configure wrote into an installed script, the
# shebang included, points inside this environment: a path of the build
# machine would not exist, or would be another tool, where the package
# runs.
echo "## Tool paths of the installed scripts"
leaks=$(grep -HnE '^(#! +/|[A-Z][A-Z_]*="/)' \
             "${PREFIX}"/bin/debasher_* "${PREFIX}"/libexec/debasher_* \
             "${PREFIX}"/lib/debasher/debasher_* |
            grep -vF "${PREFIX}/" || true)
if [ -n "${leaks}" ]; then
    echo "Paths outside ${PREFIX}:" >&2
    echo "${leaks}" >&2
    exit 1
fi

# Runs the general program of the module $1 to its end, and checks that
# every process finished: debasher_status exits with 0 only then.
run_program()
{
    local pfile=$1
    shift
    local outdir="${tmpdir}/$(basename "${pfile}" .sh)"
    echo "## Running $(basename "${pfile}")"
    debasher_exec --pfile "${pfile}" --outdir "${outdir}" --sched BUILTIN \
                  --builtinsched-cpus 2 --builtinsched-mem 256 "$@" --wait
    debasher_status -d "${outdir}"
}

run_program "${datadir}/programs/debasher_hello_world.sh"
run_program "${datadir}/programs/debasher_hello_world_py.sh"
run_program "${datadir}/programs/debasher_fifo_example.sh"
run_program "${datadir}/webui_programs/webui_batch_greet/webui_batch_greet.sh" \
            -text world -secs 0

# The web UI's server starts, and serves the frontend and the API.
echo "## Web UI"
port=18765
# The server obeys only the requests that carry its token, which it takes from
# DEBASHER_WEBUI_TOKEN when the variable is set; the page itself needs none.
token=conda-test-token
DEBASHER_WEBUI_TOKEN="${token}" \
    debasher_webui --host 127.0.0.1 --port "${port}" > "${tmpdir}/webui.log" 2>&1 &
webui_pid=$!
ok=no
for _ in $(seq 60); do
    if curl -fsS "http://127.0.0.1:${port}/" > "${tmpdir}/index.html" 2>/dev/null; then
        ok=yes
        break
    fi
    sleep 1
done
if [ "${ok}" = yes ]; then
    grep -q '<div id="root">' "${tmpdir}/index.html" || ok=no
    # Without the token, the API refuses the request.
    status=$(curl -sS -o /dev/null -w '%{http_code}' -X POST \
                  -H 'Content-Type: application/json' -d '{}' \
                  "http://127.0.0.1:${port}/api/programs/load")
    [ "${status}" = 401 ] || ok=no
    curl -fsS -X POST -H 'Content-Type: application/json' \
         -H "Authorization: Bearer ${token}" \
         -d "{\"inputDir\": \"${datadir}/webui_programs/webui_running_sum\"}" \
         "http://127.0.0.1:${port}/api/programs/load" |
        grep -q '"name":"webui_running_sum"' || ok=no
fi
kill "${webui_pid}" 2>/dev/null || true
wait "${webui_pid}" 2>/dev/null || true
if [ "${ok}" != yes ]; then
    cat "${tmpdir}/webui.log" >&2
    exit 1
fi
echo "## All checks passed"
