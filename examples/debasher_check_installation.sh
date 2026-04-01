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
    local pfile="${debasher_datadir}/programs/${progname}.sh"
    local outdir="${tmpdir}/${progname}"

    echo -n "**** Checking ${progname}.sh ... "

    local debasher_exec_out="${tmpdir}/${progname}_exec.out"
    "${debasher_bindir}/debasher_exec" --pfile "${pfile}" \
                                       --outdir "${outdir}" \
                                       --sched "${sched}" \
                                       --builtinsched-cpus "${bs_cpus}" \
                                       --builtinsched-mem "${bs_mem}" \
                                       --conda-support \
                                       --wait > "${debasher_exec_out}" 2>&1
    local ret=$?
    if test $? -eq 0 ; then
        local debasher_status_out="${tmpdir}/${progname}_status.out"
        "${debasher_bindir}/debasher_status" -d "${outdir}" > "${debasher_status_out}" 2>&1
        ret=$?
    fi

    if test $ret -eq 0 ; then
        echo "OK"
        echo ""
        return 0
    else
        echo "Failed"
        echo ""
        return 1
    fi
}

########
# Check the DeBasher package

# Create directory for temporary files
echo "**** Creating directory for temporary files..."
echo ""
tmpdir=`mktemp -d $HOME/debasher_installcheck_XXXXXX`
# trap "rm -rf $tmpdir 2>/dev/null" EXIT
echo "Temporary files will be stored in ${tmpdir}"
echo ""

# Start checks
ret=0

# Check debasher_hello_world program
progname="debasher_hello_world"
sched="BUILTIN"
bs_cpus=1
bs_mem=128
check_program "${tmpdir}" "${progname}" "${sched}" "${bs_cpus}" "${bs_mem}" || ret=1

# Check debasher_hello_world program
progname="debasher_hello_world_py"
sched="BUILTIN"
bs_cpus=1
bs_mem=128
check_program "${tmpdir}" "${progname}" "${sched}" "${bs_cpus}" "${bs_mem}" || ret=1

if test $ret -ne 0 ; then
    print_checks_failed_message "${tmpdir}"
    echo ""
else
    # Remove directory for temporaries
    echo "**** Remove directory used to store temporary files..."
    rm -rf $tmpdir
fi
