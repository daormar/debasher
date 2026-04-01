SUBDIRS= programs conda_envs

EXTRA_DIST = debasher_check_installation.sh

installcheck-local: debasher_check_installation
	./debasher_check_installation

# Build using suffix rules (portable)
SUFFIXES= .sh

.sh :
	rm -f $@
	echo "#! " $(BASH) > $@
	echo "debasher_pkgname=\"$(PACKAGE_NAME)\"" >> $@
	echo "debasher_version=\"$(PACKAGE_VERSION)\"" >> $@
	echo "debasher_bugreport=\"$(PACKAGE_BUGREPORT)\"" >> $@
	echo "debasher_bindir=\"$(bindir)\"" >> $@
	echo "debasher_libexecdir=\"$(libexecdir)\"" >> $@
	echo "debasher_datadir=\"$(datadir)/$(PACKAGE_NAME)\"" >> $@
	echo "BASH=\"$(BASH)\"" >> $@
	echo "ECHO=\"$(ECHO)\"" >> $@
	echo "AWK=\"$(AWK)\"" >> $@
	echo "SORT=\"$(SORT)\"" >> $@
	echo "sortpars=\"$(sortpars)\"" >> $@
	echo "sortT=\"$(sortT)\"" >> $@
	echo "UNIQ=\"$(UNIQ)\"" >> $@
	echo "GREP=\"$(GREP)\"" >> $@
	echo "SED=\"$(SED)\"" >> $@
	echo "TR=\"$(TR)\"" >> $@
	echo "BASENAME=\"$(BASENAME)\"" >> $@
	echo "DIRNAME=\"$(DIRNAME)\"" >> $@
	echo "REALPATH=\"$(REALPATH)\"" >> $@
	echo "SPLIT=\"$(SPLIT)\"" >> $@
	echo "CAT=\"$(CAT)\"" >> $@
	echo "RM=\"$(RM_CMD)\"" >> $@
	echo "MV=\"$(MV)\"" >> $@
	echo "CP=\"$(CP)\"" >> $@
	echo "CUT=\"$(CUT)\"" >> $@
	echo "HEAD=\"$(HEAD)\"" >> $@
	echo "TAIL=\"$(TAIL)\"" >> $@
	echo "DIFF=\"$(DIFF)\"" >> $@
	echo "FIND=\"$(FIND)\"" >> $@
	echo "WC=\"$(WC)\"" >> $@
	echo "MKDIR=\"$(MKDIR)\"" >> $@
	echo "MKTEMP=\"$(MKTEMP)\"" >> $@
	echo "MKFIFO=\"$(MKFIFO)\"" >> $@
	echo "FLOCK=\"$(FLOCK)\"" >> $@
	echo "TEE=\"$(TEE)\"" >> $@
	echo "GZIP=\"$(GZIP)\"" >> $@
	echo "SLEEP=\"$(SLEEP)\"" >> $@
	echo "SEQ=\"$(SEQ)\"" >> $@
	echo "DOCKER=\"$(DOCKER)\"" >> $@
	echo "QSUB=\"$(QSUB)\"" >> $@
	echo "QSUB_WORKS=\"$(QSUB_WORKS)\"" >> $@
	echo "QSUB_TERSE_OPT=\"$(QSUB_TERSE_OPT)\"" >> $@
	echo "QSTAT=\"$(QSTAT)\"" >> $@
	echo "QSTAT_J_OPT=\"$(QSTAT_J_OPT)\"" >> $@
	echo "QRLS=\"$(QRLS)\"" >> $@
	echo "SRUN=\"$(SRUN)\"" >> $@
	echo "SCANCEL=\"$(SCANCEL)\"" >> $@
	echo "SBATCH=\"$(SBATCH)\"" >> $@
	echo "SQUEUE=\"$(SQUEUE)\"" >> $@
	echo "SACCT=\"$(SACCT)\"" >> $@
	echo "SCONTROL=\"$(SCONTROL)\"" >> $@
	echo "WGET=\"$(WGET)\"" >> $@
	echo "PANDOC=\"$(PANDOC)\"" >> $@
	echo "PYTHON=\"$(PYTHON)\"" >> $@
	echo "RSCRIPT=\"$(RSCRIPT)\"" >> $@
	echo "PERL=\"$(PERL)\"" >> $@
	echo "GROOVY=\"$(GROOVY)\"" >> $@
	echo "JAVA=\"$(JAVA)\"" >> $@
	echo "DOT=\"$(DOT)\"" >> $@
	echo "DISABLE_SCHEDULERS=\"$(DISABLE_SCHEDULERS)\"" >> $@
	cat $< >> $@
	chmod ugo+x $@
