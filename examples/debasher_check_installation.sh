# *- bash -*

########
print_test_failed_message()
{
    local tmpdir=$1

    echo "================================================"
    echo " Test failed!"
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
    else
        echo "Failed"
        print_test_failed_message "${tmpdir}"
        exit 1
    fi

    echo ""
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

# Check debasher_hello_world program
progname="debasher_hello_world"
sched="BUILTIN"
bs_cpus=1
bs_mem=128
check_program "${tmpdir}" "${progname}" "${sched}" "${bs_cpus}" "${bs_mem}"

# Check debasher_hello_world program
progname="debasher_hello_world_py"
sched="BUILTIN"
bs_cpus=1
bs_mem=128
check_program "${tmpdir}" "${progname}" "${sched}" "${bs_cpus}" "${bs_mem}"

# Remove directory for temporaries
echo "**** Remove directory used to store temporary files..."
rm -rf $tmpdir
