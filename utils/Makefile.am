SCRIPTS_TO_BE_BUILT= panpipe_lib panpipe_exec panpipe_exec_batch	\
panpipe_check panpipe_stop panpipe_status panpipe_stats			\
panpipe_process_debug panpipe_doc_mod panpipe_proc_dataset		\
panpipe_software_test panpipe_reformat_status panpipe_solve_knapsack_bb	\
panpipe_solve_knapsack_ga

bin_SCRIPTS = $(SCRIPTS_TO_BE_BUILT)

libexec_SCRIPTS = panpipe_builtin_sched_lib panpipe_lib_utils		\
panpipe_lib_sched panpipe_lib_sched_slurm panpipe_lib_sched_builtin	\
panpipe_lib_sched_procs panpipe_lib_processes panpipe_lib_pipelines	\
panpipe_lib_modules panpipe_lib_opts panpipe_lib_conda			\
pp_get_reexec_procs_due_to_deps

CLEANFILES = $(SCRIPTS_TO_BE_BUILT)

python_PYTHON= panpipe_ppl_lib.py panpipe_knapsack_ga.py

EXTRA_DIST = panpipe_lib.sh panpipe_lib_utils.sh panpipe_lib_sched.sh	\
panpipe_lib_sched_procs.sh panpipe_lib_sched_slurm.sh			\
panpipe_lib_sched_builtin panpipe_lib_process_exec.sh			\
panpipe_lib_processes.sh panpipe_lib_pipelines.sh			\
panpipe_lib_modules.sh panpipe_lib_opts.sh panpipe_lib_conda.sh		\
panpipe_builtin_sched_lib.sh panpipe_exec.sh panpipe_exec_batch.sh	\
panpipe_check.py panpipe_stop.sh panpipe_status.sh panpipe_stats.sh	\
panpipe_process_debug.sh panpipe_doc_mod.sh panpipe_proc_dataset.sh	\
panpipe_software_test.sh pp_get_reexec_procs_due_to_deps.py		\
panpipe_reformat_status.py panpipe_solve_knapsack_bb.py			\
panpipe_solve_knapsack_ga.py panpipe_knapsack_ga.py

# Build using suffix rules (portable)
SUFFIXES= .sh .py .r .R

.sh :
	rm -f $@
	echo "#! " $(BASH) > $@
	echo "panpipe_pkgname=\"$(PACKAGE_NAME)\"" >> $@
	echo "panpipe_version=\"$(PACKAGE_VERSION)\"" >> $@
	echo "panpipe_bindir=\"$(bindir)\"" >> $@
	echo "panpipe_libexecdir=\"$(libexecdir)\"" >> $@
	echo "panpipe_datadir=\"$(datadir)/$(PACKAGE_NAME)\"" >> $@
	echo "BASH=\"$(BASH)\"" >> $@
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
	echo "CUT=\"$(CUT)\"" >> $@
	echo "HEAD=\"$(HEAD)\"" >> $@
	echo "TAIL=\"$(TAIL)\"" >> $@
	echo "DIFF=\"$(DIFF)\"" >> $@
	echo "FIND=\"$(FIND)\"" >> $@
	echo "WC=\"$(WC)\"" >> $@
	echo "MKTEMP=\"$(MKTEMP)\"" >> $@
	echo "MKFIFO=\"$(MKFIFO)\"" >> $@
	echo "FLOCK=\"$(FLOCK)\"" >> $@
	echo "TEE=\"$(TEE)\"" >> $@
	echo "GZIP=\"$(GZIP)\"" >> $@
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
	echo "JAVA=\"$(JAVA)\"" >> $@
	echo "DISABLE_SCHEDULERS=\"$(DISABLE_SCHEDULERS)\"" >> $@
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
