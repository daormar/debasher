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
    local sched=$3
    local bs_cpus=$4
    local bs_mem=$5
    local additional_opts=$6
    local pfile="${debasher_datadir}/programs/${progname}.sh"
    local outdir="${tmpdir}/${progname}"

    echo -n "## Checking ${progname}.sh ... "

    local debasher_exec_out="${tmpdir}/${progname}_exec.out"
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
        local debasher_status_out="${tmpdir}/${progname}_status.out"
        timeout -v 10s "${debasher_bindir}/debasher_status" -d "${outdir}" > "${debasher_status_out}" 2>&1
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
            echo "Unexepected error, see additional information in ${tmpdir}, aborting..."
            echo ""
            exit 1
    esac
}

########
# Check the DeBasher package

# Create directory for temporary files
echo "# Creating directory for temporary files..."
echo ""
tmpdir=`mktemp -d $HOME/debasher_installcheck_XXXXXX`
# trap "rm -rf $tmpdir 2>/dev/null" EXIT
echo "Temporary files will be stored in ${tmpdir}"
echo ""

# Start checks
echo "# Checks Execution"
echo ""
checks_passed=0
checks_timedout=0
checks_failed=0

# Check debasher_hello_world program
progname="debasher_hello_world"
sched="BUILTIN"
bs_cpus=2
bs_mem=128
check_program "${tmpdir}" "${progname}" "${sched}" "${bs_cpus}" "${bs_mem}"
ret=$?
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
check_program "${tmpdir}" "${progname}" "${sched}" "${bs_cpus}" "${bs_mem}"
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
check_program "${tmpdir}" "${progname}" "${sched}" "${bs_cpus}" "${bs_mem}" "-n 10"
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
if check_program "${tmpdir}" "${progname}" "${sched}" "${bs_cpus}" "${bs_mem}" "-num-a 1 -num-b 2"; then
    ((checks_passed++))
else
    ((checks_failed++))
fi

# Check debasher_array_example program
progname="debasher_array_example"
sched="BUILTIN"
bs_cpus=4
bs_mem=128
check_program "${tmpdir}" "${progname}" "${sched}" "${bs_cpus}" "${bs_mem}" "-c 1"
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
check_program "${tmpdir}" "${progname}" "${sched}" "${bs_cpus}" "${bs_mem}" "-s Hello\ World!"
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
check_program "${tmpdir}" "${progname}" "${sched}" "${bs_cpus}" "${bs_mem}" "-c 1"
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
check_program "${tmpdir}" "${progname}" "${sched}" "${bs_cpus}" "${bs_mem}" "-n 4"
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
check_program "${tmpdir}" "${progname}" "${sched}" "${bs_cpus}" "${bs_mem}" "-n 4"
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
check_program "${tmpdir}" "${progname}" "${sched}" "${bs_cpus}" "${bs_mem}" "-n 4"
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
check_program "${tmpdir}" "${progname}" "${sched}" "${bs_cpus}" "${bs_mem}" "-c 40 -f $(printf '%q ' "${telegram_data_file}")"
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
check_program "${tmpdir}" "${progname}" "${sched}" "${bs_cpus}" "${bs_mem}" "-c 40 -f $(printf '%q ' "${telegram_data_file}")"
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
check_program "${tmpdir}" "${progname}" "${sched}" "${bs_cpus}" "${bs_mem}" "-c 40 -f $(printf '%q ' "${telegram_data_file}")"
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
check_program "${tmpdir}" "${progname}" "${sched}" "${bs_cpus}" "${bs_mem}" "-c 40 -f $(printf '%q ' "${telegram_data_file}")"
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

# Summary
echo "# Summary"
echo ""
echo "Total Checks: $((checks_passed + checks_timedout + checks_failed)) ; Passed: ${checks_passed} ; Timed Out: ${checks_timedout} ; Failed: ${checks_failed}"
echo ""

if test $checks_failed -gt 0 ; then
    print_checks_failed_message "${tmpdir}"
    echo ""
else
    # Remove directory for temporaries
    echo "# Remove directory used to store temporary files..."
    rm -rf $tmpdir
    echo ""
fi
