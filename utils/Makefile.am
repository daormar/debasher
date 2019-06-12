SCRIPTS_TO_BE_BUILT= panpipe_lib panpipe_builtin_sched_lib pipe_exec	\
pipe_exec_batch pipe_check pipe_status pipe_stats pipe_step_debug	\
panpipe_doc_mod pipe_software_test get_reexec_steps_due_to_deps		\
solve_knapsack_bb solve_knapsack_ga

bin_SCRIPTS = $(SCRIPTS_TO_BE_BUILT)

CLEANFILES = $(SCRIPTS_TO_BE_BUILT)

python_PYTHON= knapsack_ga.py

EXTRA_DIST = panpipe_lib.sh panpipe_builtin_sched_lib.sh pipe_exec.sh	\
pipe_exec_batch.sh pipe_check.py pipe_status.sh pipe_stats.sh		\
pipe_step_debug.sh panpipe_doc_mod.sh pipe_software_test.sh		\
get_reexec_steps_due_to_deps.py solve_knapsack_bb.py			\
solve_knapsack_ga.py knapsack_ga.py

# Build rules for libraries
panpipe_lib: panpipe_lib.sh
	rm -f $@
	cat panpipe_lib.sh >> $@

# Build using suffix rules (portable)
SUFFIXES= .sh .py .r .R

.sh :
	rm -f $@
	echo "#! " $(BASH) > $@
	echo "panpipe_pkgname=\""$(PACKAGE_NAME)"\"" >> $@
	echo "panpipe_version=\""$(PACKAGE_VERSION)"\"" >> $@
	echo "panpipe_bindir="$(prefix)/bin/ >> $@
	echo "panpipe_datadir="$(datadir)/$(PACKAGE_NAME) >> $@
	echo "BASH="$(BASH) >> $@
	echo "AWK="$(AWK) >> $@
	echo "SORT="$(SORT) >> $@
	echo "sortpars=\""$(sortpars)"\"" >> $@
	echo "sortT=\""$(sortT)"\"" >> $@
	echo "UNIQ="$(UNIQ) >> $@
	echo "GREP="$(GREP) >> $@
	echo "SED="$(SED) >> $@
	echo "BASENAME="$(BASENAME) >> $@
	echo "DIRNAME="$(DIRNAME) >> $@
	echo "SPLIT="$(SPLIT) >> $@
	echo "CUT="$(CUT) >> $@
	echo "HEAD="$(HEAD) >> $@
	echo "TAIL="$(TAIL) >> $@
	echo "DIFF="$(DIFF) >> $@
	echo "FIND="$(FIND) >> $@
	echo "WC="$(WC) >> $@
	echo "MKTEMP="$(MKTEMP) >> $@
	echo "MKFIFO="$(MKFIFO) >> $@
	echo "FLOCK="$(FLOCK) >> $@
	echo "GZIP="$(GZIP) >> $@
	echo "QSUB=\""$(QSUB)"\"" >> $@
	echo "QSUB_WORKS=\""$(QSUB_WORKS)"\"" >> $@
	echo "QSUB_TERSE_OPT=\""$(QSUB_TERSE_OPT)"\"" >> $@
	echo "QSTAT="$(QSTAT) >> $@
	echo "QSTAT_J_OPT=\""$(QSTAT_J_OPT)"\"" >> $@
	echo "QRLS="$(QRLS) >> $@
	echo "SRUN="$(SRUN) >> $@
	echo "SBATCH="$(SBATCH) >> $@
	echo "SQUEUE="$(SQUEUE) >> $@
	echo "SACCT="$(SACCT) >> $@
	echo "SCONTROL="$(SCONTROL) >> $@
	echo "WGET="$(WGET) >> $@
	echo "PANDOC="$(PANDOC) >> $@
	echo "PYTHON="$(PYTHON) >> $@
	echo "JAVA="$(JAVA) >> $@
	echo "DISABLE_SCHEDULERS="$(DISABLE_SCHEDULERS) >> $@
	cat $< >> $@
	chmod ugo+x $@

.py:
	rm -f $@
	echo "#! " $(PYTHON) > $@
	echo "import sys" >> $@
	echo "sys.path.append(\"$(pythondir)\")" >> $@	
	cat $< >> $@
	chmod ugo+x $@

.r:
	rm -f $@
	echo "#! " $(RSCRIPT) > $@
	cat $< >> $@
	chmod ugo+x $@

.R:
	rm -f $@
	echo "#! " $(RSCRIPT) > $@
	cat $< >> $@
	chmod ugo+x $@
