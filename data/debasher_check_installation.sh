# *- bash -*

########
print_checks_failed_message()
{
    local tmpdir=$1

    echo "================================================"
    echo " There were failed checks!"
    echo " See additional information in ${tmpdir}"
    echo " Please report to "${debasher_bugreport}
    echo "================================================"
}

########
check_program()
{
    local tmpdir=$1
    local progname=$2
    local outdirname=$3
    local sched=$4
    local bs_cpus=$5
    local bs_mem=$6
    local additional_opts=$7

    check_program_file "${tmpdir}" "${debasher_datadir}/programs/${progname}.sh" "${outdirname}" \
                       "${sched}" "${bs_cpus}" "${bs_mem}" "${additional_opts}"
}

########
# Runs the general program of the module `pfile` to its end, and checks that
# every process finished.
check_program_file()
{
    local tmpdir=$1
    local pfile=$2
    local outdirname=$3
    local sched=$4
    local bs_cpus=$5
    local bs_mem=$6
    local additional_opts=$7
    local outdir="${tmpdir}/${outdirname}"

    echo -n "## Checking $("${BASENAME}" "${pfile}") ... "

    local debasher_exec_out="${tmpdir}/${outdirname}_exec.out"
    "${debasher_bindir}/debasher_exec" --pfile "${pfile}" \
                                       --outdir "${outdir}" \
                                       --sched "${sched}" \
                                       --builtinsched-cpus "${bs_cpus}" \
                                       --builtinsched-mem "${bs_mem}" \
                                       --conda-support \
                                       ${additional_opts} \
                                       --wait > "${debasher_exec_out}" 2>&1
    local ret=$?
    if test $ret -eq 0 ; then
        local debasher_status_out="${tmpdir}/${outdirname}_status.out"
        "${TIMEOUT}" -v 10s "${debasher_bindir}/debasher_status" -d "${outdir}" > "${debasher_status_out}" 2>&1
        ret=$?
    fi

    case $ret in
        0)
            echo "OK"
            echo ""
            return 0
            ;;
        1)
            echo "Failed"
            echo ""
            return 1
            ;;
        124)
            echo "Timed Out"
            echo ""
            return 124
            ;;
        *)
            echo "Unexepected error (code $ret), see additional information in ${tmpdir}, aborting..."
            echo ""
            exit 1
    esac
}

########
# Waits up to `seconds` for debasher_status to report every process of the
# run in `outdir` with the status counted by `field` in its summary
# ("inprogress" or "finished"), keeping its last output in `status_out`.
wait_for_every_process()
{
    local outdir=$1
    local field=$2
    local seconds=$3
    local status_out=$4
    local i summary total count

    for ((i = 0; i < seconds; i++)); do
        "${debasher_bindir}/debasher_status" -d "${outdir}" > "${status_out}" 2>&1
        summary=$("${GREP}" "SUMMARY" "${status_out}")
        total=$("${ECHO}" "${summary}" | "${SED}" 's/.*num_processes= \([0-9]*\).*/\1/')
        count=$("${ECHO}" "${summary}" | "${SED}" "s/.* ${field}= \([0-9]*\).*/\1/")
        if [ -n "${total}" ] && [ "${total}" -gt 0 ] && [ "${count}" = "${total}" ]; then
            return 0
        fi
        "${SLEEP}" 1
    done
    return 1
}

########
# Checks the resident program of the module `pfile`, which does not end on
# its own: launches it, waits until every node is alive, and stops it in an
# orderly way, after which every node has to be finished. Given an external
# input `input_fifo`, it also writes each of `input_payloads` into it as a
# DATA message, and waits until the output read outside the program
# `output_fifo` carries a DATA message whose payload is `expected_payload`.
check_resident_program()
{
    local tmpdir=$1
    local pfile=$2
    local outdirname=$3
    local input_fifo=$4
    local input_payloads=$5
    local output_fifo=$6
    local expected_payload=$7
    local outdir="${tmpdir}/${outdirname}"
    local status_out="${tmpdir}/${outdirname}_status.out"
    local timeout_secs=30
    local ret=0

    echo -n "## Checking $("${BASENAME}" "${pfile}") (resident) ... "

    # debasher_exec returns once the nodes are launched, which go on
    # running.
    "${debasher_bindir}/debasher_exec" --pfile "${pfile}" \
                                       --outdir "${outdir}" \
                                       > "${tmpdir}/${outdirname}_exec.out" 2>&1 || ret=1

    if test $ret -eq 0 ; then
        wait_for_every_process "${outdir}" "inprogress" ${timeout_secs} "${status_out}" || ret=124
    fi

    local reader_pid=""
    if test $ret -eq 0 && test -n "${input_fifo}" ; then
        local fifos_dir="${outdir}/__fifos__"
        local input_path=$("${FIND}" "${fifos_dir}" -name "${input_fifo}")
        local output_path=$("${FIND}" "${fifos_dir}" -name "${output_fifo}")
        local output_file="${tmpdir}/${outdirname}_output.out"

        # Something outside has to read an output read outside the program,
        # or its node's outbound backlog grows.
        "${CAT}" "${output_path}" > "${output_file}" &
        reader_pid=$!

        # Opening the fifo waits for its node to open its end, so each
        # write is bounded in time.
        local payload
        for payload in ${input_payloads}; do
            "${TIMEOUT}" ${timeout_secs}s "${BASH}" -c 'printf "{\"type\": \"DATA\", \"payload\": %s}\n" "$1" > "$2"' \
                    _ "${payload}" "${input_path}" || { ret=124; break; }
        done

        if test $ret -eq 0 ; then
            ret=124
            local i
            for ((i = 0; i < timeout_secs; i++)); do
                if "${GREP}" -q -F "\"payload\": ${expected_payload}}" "${output_file}" 2>/dev/null; then
                    ret=0
                    break
                fi
                "${SLEEP}" 1
            done
        fi
    fi

    # Stopped in any case, so that nothing is left running: after --timeout,
    # debasher_stop_resident falls back to a hard kill, and fails.
    "${debasher_bindir}/debasher_stop_resident" -d "${outdir}" --timeout ${timeout_secs} \
                                                > "${tmpdir}/${outdirname}_stop.out" 2>&1
    if test $? -ne 0 && test $ret -eq 0 ; then
        ret=1
    fi
    if test $ret -eq 0 ; then
        wait_for_every_process "${outdir}" "finished" ${timeout_secs} "${status_out}" || ret=1
    fi

    # The node closes its end when it stops, which ends the reader; one
    # left waiting is not.
    if test -n "${reader_pid}" ; then
        kill "${reader_pid}" 2>/dev/null
        wait "${reader_pid}" 2>/dev/null
    fi

    case $ret in
        0)
            echo "OK"
            ;;
        124)
            echo "Timed Out"
            ;;
        *)
            echo "Failed"
            ;;
    esac
    echo ""
    return $ret
}

########
# Check the DeBasher package

# Create directory for temporary files
echo "# Creating directory for temporary files..."
echo ""
tmpdir=$(mktemp -d $HOME/debasher_installcheck_XXXXXX)
# trap "rm -rf $tmpdir 2>/dev/null" EXIT
echo "Temporary files will be stored in ${tmpdir}"
echo ""

# Start checks
echo "# Checks using BUILTIN Scheduler"
echo ""
checks_passed=0
checks_timedout=0
checks_failed=0

# Check debasher_hello_world program
progname="debasher_hello_world"
sched="BUILTIN"
bs_cpus=2
bs_mem=128
check_program "${tmpdir}" "${progname}" "${progname}_builtin" "${sched}" "${bs_cpus}" "${bs_mem}"
case $? in
    0)
        ((checks_passed++))
        ;;
    1)
        ((checks_failed++))
        ;;
    124)
        ((checks_timedout++))
        ;;
esac

# Check debasher_namespace_example program
progname="debasher_namespace_example"
sched="BUILTIN"
bs_cpus=2
bs_mem=128
check_program "${tmpdir}" "${progname}" "${progname}_builtin" "${sched}" "${bs_cpus}" "${bs_mem}" "--gen-proc-graph"
case $? in
    0)
        ((checks_passed++))
        ;;
    1)
        ((checks_failed++))
        ;;
    124)
        ((checks_timedout++))
        ;;
esac

# Check debasher_namespace_multidot_example program
progname="debasher_namespace_multidot_example"
sched="BUILTIN"
bs_cpus=2
bs_mem=128
check_program "${tmpdir}" "${progname}" "${progname}_builtin" "${sched}" "${bs_cpus}" "${bs_mem}" "--gen-proc-graph"
case $? in
    0)
        ((checks_passed++))
        ;;
    1)
        ((checks_failed++))
        ;;
    124)
        ((checks_timedout++))
        ;;
esac

# Check debasher_hello_world_py program
progname="debasher_hello_world_py"
sched="BUILTIN"
bs_cpus=2
bs_mem=128
check_program "${tmpdir}" "${progname}" "${progname}_builtin" "${sched}" "${bs_cpus}" "${bs_mem}"
case $? in
    0)
        ((checks_passed++))
        ;;
    1)
        ((checks_failed++))
        ;;
    124)
        ((checks_timedout++))
        ;;
esac

# Check debasher_hello_world_py_legacy program
progname="debasher_hello_world_py_legacy"
sched="BUILTIN"
bs_cpus=2
bs_mem=128
check_program "${tmpdir}" "${progname}" "${progname}_builtin" "${sched}" "${bs_cpus}" "${bs_mem}"
case $? in
    0)
        ((checks_passed++))
        ;;
    1)
        ((checks_failed++))
        ;;
    124)
        ((checks_timedout++))
        ;;
esac

# Check debasher_hello_world_alias_func program
progname="debasher_hello_world_alias"
sched="BUILTIN"
bs_cpus=2
bs_mem=128
check_program "${tmpdir}" "${progname}" "${progname}_builtin" "${sched}" "${bs_cpus}" "${bs_mem}"
case $? in
    0)
        ((checks_passed++))
        ;;
    1)
        ((checks_failed++))
        ;;
    124)
        ((checks_timedout++))
        ;;
esac

# Check debasher_hello_world_alias_extern program
progname="debasher_hello_world_ext_alias"
sched="BUILTIN"
bs_cpus=2
bs_mem=128
check_program "${tmpdir}" "${progname}" "${progname}_builtin" "${sched}" "${bs_cpus}" "${bs_mem}"
case $? in
    0)
        ((checks_passed++))
        ;;
    1)
        ((checks_failed++))
        ;;
    124)
        ((checks_timedout++))
        ;;
esac

# Check debasher_hello_world_alias_opt_map program
progname="debasher_hello_world_alias_opt_map"
sched="BUILTIN"
bs_cpus=2
bs_mem=128
check_program "${tmpdir}" "${progname}" "${progname}_builtin" "${sched}" "${bs_cpus}" "${bs_mem}"
case $? in
    0)
        ((checks_passed++))
        ;;
    1)
        ((checks_failed++))
        ;;
    124)
        ((checks_timedout++))
        ;;
esac

# Check debasher_cycle program
progname="debasher_cycle"
sched="BUILTIN"
bs_cpus=2
bs_mem=128
check_program "${tmpdir}" "${progname}" "${progname}_builtin" "${sched}" "${bs_cpus}" "${bs_mem}" "-n 10"
case $? in
    0)
        ((checks_passed++))
        ;;
    1)
        ((checks_failed++))
        ;;
    124)
        ((checks_timedout++))
        ;;
esac

# Check debasher_value_pass_example program
progname="debasher_value_pass_example"
sched="BUILTIN"
bs_cpus=2
bs_mem=128
if check_program "${tmpdir}" "${progname}" "${progname}_builtin" "${sched}" "${bs_cpus}" "${bs_mem}" "-num-a 1 -num-b 2"; then
    ((checks_passed++))
else
    ((checks_failed++))
fi

# Check debasher_skip_example program
progname="debasher_skip_example"
sched="BUILTIN"
bs_cpus=2
bs_mem=128
check_program "${tmpdir}" "${progname}" "${progname}_builtin" "${sched}" "${bs_cpus}" "${bs_mem}" "-num-a 1 -num-b 2"
case $? in
    0)
        ((checks_passed++))
        ;;
    1)
        ((checks_failed++))
        ;;
    124)
        ((checks_timedout++))
        ;;
esac

# Check debasher_explicit_deps_example program
progname="debasher_explicit_deps_example"
sched="BUILTIN"
bs_cpus=2
bs_mem=128
check_program "${tmpdir}" "${progname}" "${progname}_builtin" "${sched}" "${bs_cpus}" "${bs_mem}" "-num-a 1 -num-b 2"
case $? in
    0)
        ((checks_passed++))
        ;;
    1)
        ((checks_failed++))
        ;;
    124)
        ((checks_timedout++))
        ;;
esac

# Check debasher_array_example_original program
progname="debasher_array_example_original"
sched="BUILTIN"
bs_cpus=4
bs_mem=128
check_program "${tmpdir}" "${progname}" "${progname}_builtin" "${sched}" "${bs_cpus}" "${bs_mem}" "-c 1"
case $? in
    0)
        ((checks_passed++))
        ;;
    1)
        ((checks_failed++))
        ;;
    124)
        ((checks_timedout++))
        ;;
esac

# Check debasher_array_example program
progname="debasher_array_example"
sched="BUILTIN"
bs_cpus=4
bs_mem=128
check_program "${tmpdir}" "${progname}" "${progname}_builtin" "${sched}" "${bs_cpus}" "${bs_mem}" "-c 1"
case $? in
    0)
        ((checks_passed++))
        ;;
    1)
        ((checks_failed++))
        ;;
    124)
        ((checks_timedout++))
        ;;
esac

# Check debasher_file_example program
progname="debasher_file_example"
sched="BUILTIN"
bs_cpus=2
bs_mem=128
check_program "${tmpdir}" "${progname}" "${progname}_builtin" "${sched}" "${bs_cpus}" "${bs_mem}" "-s Hello\ World!"
case $? in
    0)
        ((checks_passed++))
        ;;
    1)
        ((checks_failed++))
        ;;
    124)
        ((checks_timedout++))
        ;;
esac

# Check debasher_fifo_example program
progname="debasher_fifo_example"
sched="BUILTIN"
bs_cpus=2
bs_mem=128
check_program "${tmpdir}" "${progname}" "${progname}_builtin" "${sched}" "${bs_cpus}" "${bs_mem}"
case $? in
    0)
        ((checks_passed++))
        ;;
    1)
        ((checks_failed++))
        ;;
    124)
        ((checks_timedout++))
        ;;
esac

# Check debasher_define_opt_deps_example program
progname="debasher_define_opt_deps_example"
sched="BUILTIN"
bs_cpus=3
bs_mem=128
check_program "${tmpdir}" "${progname}" "${progname}_builtin" "${sched}" "${bs_cpus}" "${bs_mem}"
case $? in
    0)
        ((checks_passed++))
        ;;
    1)
        ((checks_failed++))
        ;;
    124)
        ((checks_timedout++))
        ;;
esac

# Check debasher_generator_example program
progname="debasher_generator_example"
sched="BUILTIN"
bs_cpus=4
bs_mem=128
check_program "${tmpdir}" "${progname}" "${progname}_builtin" "${sched}" "${bs_cpus}" "${bs_mem}" "-c 1"
case $? in
    0)
        ((checks_passed++))
        ;;
    1)
        ((checks_failed++))
        ;;
    124)
        ((checks_timedout++))
        ;;
esac

# Check debasher_fifo_generator_example program
progname="debasher_fifo_generator_example"
sched="BUILTIN"
bs_cpus=4
bs_mem=128
check_program "${tmpdir}" "${progname}" "${progname}_builtin" "${sched}" "${bs_cpus}" "${bs_mem}" "-n 4"
case $? in
    0)
        ((checks_passed++))
        ;;
    1)
        ((checks_failed++))
        ;;
    124)
        ((checks_timedout++))
        ;;
esac

# Check debasher_subprogram_example program
progname="debasher_subprogram_example"
sched="BUILTIN"
bs_cpus=4
bs_mem=128
check_program "${tmpdir}" "${progname}" "${progname}_builtin" "${sched}" "${bs_cpus}" "${bs_mem}" "-c 1"
case $? in
    0)
        ((checks_passed++))
        ;;
    1)
        ((checks_failed++))
        ;;
    124)
        ((checks_timedout++))
        ;;
esac

# Check debasher_host_workflow program
progname="debasher_host_workflow"
sched="BUILTIN"
bs_cpus=4
bs_mem=1024
check_program "${tmpdir}" "${progname}" "${progname}_builtin" "${sched}" "${bs_cpus}" "${bs_mem}" "-n 4"
case $? in
    0)
        ((checks_passed++))
        ;;
    1)
        ((checks_failed++))
        ;;
    124)
        ((checks_timedout++))
        ;;
esac

# Check debasher_host_workflow_expl_deps program
progname="debasher_host_workflow_expl_deps"
sched="BUILTIN"
bs_cpus=4
bs_mem=1024
check_program "${tmpdir}" "${progname}" "${progname}_builtin" "${sched}" "${bs_cpus}" "${bs_mem}" "-n 4"
case $? in
    0)
        ((checks_passed++))
        ;;
    1)
        ((checks_failed++))
        ;;
    124)
        ((checks_timedout++))
        ;;
esac

# Check debasher_host_workflow_force program
progname="debasher_host_workflow_force"
sched="BUILTIN"
bs_cpus=4
bs_mem=1024
check_program "${tmpdir}" "${progname}" "${progname}_builtin" "${sched}" "${bs_cpus}" "${bs_mem}" "-n 4"
case $? in
    0)
        ((checks_passed++))
        ;;
    1)
        ((checks_failed++))
        ;;
    124)
        ((checks_timedout++))
        ;;
esac

# Check debasher_telegram program
progname="debasher_telegram"
sched="BUILTIN"
bs_cpus=4
bs_mem=128
telegram_data_file="${tmpdir}/telegram_data.txt"
"${debasher_libexecdir}/debasher_gen_telegram_data" -n 100 -l 10 -w 10 > "${telegram_data_file}"
check_program "${tmpdir}" "${progname}" "${progname}_builtin" "${sched}" "${bs_cpus}" "${bs_mem}" "-c 40 -f $(printf '%q ' "${telegram_data_file}")"
case $? in
    0)
        ((checks_passed++))
        ;;
    1)
        ((checks_failed++))
        ;;
    124)
        ((checks_timedout++))
        ;;
esac

# Check debasher_telegram_jobsteps program
progname="debasher_telegram_jobsteps"
sched="BUILTIN"
bs_cpus=4
bs_mem=128
telegram_data_file="${tmpdir}/telegram_data.txt"
"${debasher_libexecdir}/debasher_gen_telegram_data" -n 100 -l 10 -w 10 > "${telegram_data_file}"
check_program "${tmpdir}" "${progname}" "${progname}_builtin" "${sched}" "${bs_cpus}" "${bs_mem}" "-c 40 -f $(printf '%q ' "${telegram_data_file}")"
case $? in
    0)
        ((checks_passed++))
        ;;
    1)
        ((checks_failed++))
        ;;
    124)
        ((checks_timedout++))
        ;;
esac

# Check debasher_telegram_imperative program
progname="debasher_telegram_imperative"
sched="BUILTIN"
bs_cpus=4
bs_mem=128
telegram_data_file="${tmpdir}/telegram_data.txt"
"${debasher_libexecdir}/debasher_gen_telegram_data" -n 100 -l 10 -w 10 > "${telegram_data_file}"
check_program "${tmpdir}" "${progname}" "${progname}_builtin" "${sched}" "${bs_cpus}" "${bs_mem}" "-c 40 -f $(printf '%q ' "${telegram_data_file}")"
case $? in
    0)
        ((checks_passed++))
        ;;
    1)
        ((checks_failed++))
        ;;
    124)
        ((checks_timedout++))
        ;;
esac

# Check debasher_telegram_morrison program
progname="debasher_telegram_morrison"
sched="BUILTIN"
bs_cpus=4
bs_mem=128
telegram_data_file="${tmpdir}/telegram_data.txt"
"${debasher_libexecdir}/debasher_gen_telegram_data" -n 100 -l 10 -w 10 > "${telegram_data_file}"
check_program "${tmpdir}" "${progname}" "${progname}_builtin" "${sched}" "${bs_cpus}" "${bs_mem}" "-c 40 -f $(printf '%q ' "${telegram_data_file}")"
case $? in
    0)
        ((checks_passed++))
        ;;
    1)
        ((checks_failed++))
        ;;
    124)
        ((checks_timedout++))
        ;;
esac

# Check debasher_conda_example
progname="debasher_conda_example"
sched="BUILTIN"
bs_cpus=4
bs_mem=1024
check_program "${tmpdir}" "${progname}" "${progname}_builtin" "${sched}" "${bs_cpus}" "${bs_mem}" "-n 4"
case $? in
    0)
        ((checks_passed++))
        ;;
    1)
        ((checks_failed++))
        ;;
    124)
        ((checks_timedout++))
        ;;
esac

# Check debasher_docker_example
progname="debasher_docker_example"
sched="BUILTIN"
bs_cpus=4
bs_mem=1024
check_program "${tmpdir}" "${progname}" "${progname}_builtin" "${sched}" "${bs_cpus}" "${bs_mem}" "-n 4"
case $? in
    0)
        ((checks_passed++))
        ;;
    1)
        ((checks_failed++))
        ;;
    124)
        ((checks_timedout++))
        ;;
esac

# Check debasher_dynamic_fanout
progname="debasher_dynamic_fanout"
sched="BUILTIN"
bs_cpus=4
bs_mem=1024
check_program "${tmpdir}" "${progname}" "${progname}_builtin" "${sched}" "${bs_cpus}" "${bs_mem}" "-l 200 -c 20 -b 20 -w 5"
case $? in
    0)
        ((checks_passed++))
        ;;
    1)
        ((checks_failed++))
        ;;
    124)
        ((checks_timedout++))
        ;;
esac

# Check debasher_dynamic_fanout_fifos
progname="debasher_dynamic_fanout_fifos"
sched="BUILTIN"
bs_cpus=7 # increased number of cpus to be able to allocate all processes
bs_mem=1024
check_program "${tmpdir}" "${progname}" "${progname}_builtin" "${sched}" "${bs_cpus}" "${bs_mem}" "-l 200 -c 20 -b 20 -w 5"
case $? in
    0)
        ((checks_passed++))
        ;;
    1)
        ((checks_failed++))
        ;;
    124)
        ((checks_timedout++))
        ;;
esac

# Check debasher_dynamic_fanout_fifos_gen
progname="debasher_dynamic_fanout_fifos_gen"
sched="BUILTIN"
bs_cpus=7 # increased number of cpus to be able to allocate all processes
bs_mem=1024
check_program "${tmpdir}" "${progname}" "${progname}_builtin" "${sched}" "${bs_cpus}" "${bs_mem}" "-l 200 -c 20 -b 20 -w 5"
case $? in
    0)
        ((checks_passed++))
        ;;
    1)
        ((checks_failed++))
        ;;
    124)
        ((checks_timedout++))
        ;;
esac

# Checks of the programs built with the web UI
echo "# Checks of the programs built with the web UI"
echo ""

# Check webui_fifo_sum, a general program; the web UI gives each process
# 256 MB by default
progname="webui_fifo_sum"
sched="BUILTIN"
bs_cpus=2
bs_mem=512
check_program_file "${tmpdir}" "${debasher_datadir}/webui_programs/${progname}/${progname}.sh" \
                   "${progname}_builtin" "${sched}" "${bs_cpus}" "${bs_mem}" "-n 10"
case $? in
    0)
        ((checks_passed++))
        ;;
    1)
        ((checks_failed++))
        ;;
    124)
        ((checks_timedout++))
        ;;
esac

# Check webui_running_sum, a resident program: the running sum of 1, 2 and 3
# is 6
progname="webui_running_sum"
check_resident_program "${tmpdir}" "${debasher_datadir}/webui_programs/${progname}/${progname}.sh" \
                       "${progname}" "numbers" "1 2 3" "sum" "6"
case $? in
    0)
        ((checks_passed++))
        ;;
    1)
        ((checks_failed++))
        ;;
    124)
        ((checks_timedout++))
        ;;
esac

# Check webui_batch_greet, the general program that webui_batch_launcher runs
progname="webui_batch_greet"
sched="BUILTIN"
bs_cpus=1
bs_mem=256
check_program_file "${tmpdir}" "${debasher_datadir}/webui_programs/${progname}/${progname}.sh" \
                   "${progname}_builtin" "${sched}" "${bs_cpus}" "${bs_mem}" "-text world -secs 0"
case $? in
    0)
        ((checks_passed++))
        ;;
    1)
        ((checks_failed++))
        ;;
    124)
        ((checks_timedout++))
        ;;
esac

# Check webui_batch_launcher, a resident program with a launcher node: one
# request runs webui_batch_greet, installed next to it, and Report reports
# the batch run that finished
progname="webui_batch_launcher"
check_resident_program "${tmpdir}" "${debasher_datadir}/webui_programs/${progname}/${progname}.sh" \
                       "${progname}" "requests" '{"opts":{"-text":"world","-secs":"0"},"run":"r1"}' \
                       "report" '{"run": "r1", "status": "finished", "finished": 1, "failed": 0}'
case $? in
    0)
        ((checks_passed++))
        ;;
    1)
        ((checks_failed++))
        ;;
    124)
        ((checks_timedout++))
        ;;
esac

# Check execution using SLURM if available: SBATCH is the name of the tool,
# looked for in the PATH when the program runs, as the engine does
if command -v "${SBATCH}" > /dev/null 2>&1; then
    echo "# Checks using SLURM Scheduler"
    echo ""

    # Check debasher_dynamic_fanout
    progname="debasher_dynamic_fanout"
    sched="SLURM"
    bs_cpus=1   # Not used with SLURM scheduler
    bs_mem=1024 # Not used with SLURM scheduler
    check_program "${tmpdir}" "${progname}" "${progname}_slurm" "${sched}" "${bs_cpus}" "${bs_mem}" "-l 200 -c 20 -b 20 -w 5"
    case $? in
        0)
            ((checks_passed++))
            ;;
        1)
            ((checks_failed++))
            ;;
        124)
            ((checks_timedout++))
            ;;
    esac
fi

# Summary
echo "# Summary"
echo ""
echo "Total Checks: $((checks_passed + checks_timedout + checks_failed)) ; Passed: ${checks_passed} ; Timed Out: ${checks_timedout} ; Failed: ${checks_failed}"
echo ""

# A check that failed or timed out fails the script, and so make
# installcheck
if test $checks_failed -gt 0 || test $checks_timedout -gt 0 ; then
    print_checks_failed_message "${tmpdir}"
    echo ""
    exit 1
else
    # Remove directory for temporaries
    echo "# Remove directory used to store temporary files..."
    rm -rf $tmpdir
    echo ""
fi
