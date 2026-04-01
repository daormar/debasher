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

# Remove directory for temporaries
echo "**** Remove directory used to store temporary files..."
rm -rf $tmpdir
