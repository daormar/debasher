# *- bash -*

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
progname=debasher_hello_world
pfile="${debasher_datadir}/programs/${progname}.sh"
outdir="${tmpdir}/${progname}"
echo "**** Checking ${progname}.sh ..."
echo ""

"${debasher_bindir}/debasher_exec" --pfile "${pfile}" \
                                   --outdir "${outdir}" \
                                   --sched BUILTIN \
                                   --builtinsched-cpus 1 \
                                   --builtinsched-mem 128 \
                                   --builtinsched-debug \
                                   --conda-support \
                                   --wait
ret=$?
if test $? -eq 0 ; then
    debasher_status_out="${tmpdir}/${progname}_status.out"
    "${debasher_bindir}/debasher_status" -d "${outdir}" > "${debasher_status_out}" 2>&1
    ret=$?
fi

if test $ret -eq 0 ; then
    echo "... Done"
else
    echo "================================================"
    echo " Test failed!"
    echo " See additional information in ${tmpdir}"
    echo " Please report to "${debasher_bugreport}
    echo "================================================"
    exit 1
fi

echo ""

# Remove directory for temporaries
echo "**** Remove directory used to store temporary files..."
rm -rf $tmpdir
