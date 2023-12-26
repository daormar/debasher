bin_SCRIPTS= debasher_lib debasher_exec debasher_exec_batch		\
debasher_stop debasher_status debasher_stats debasher_process_debug	\
debasher_doc_mod debasher_proc_dataset debasher_reformat_status

libexec_SCRIPTS= debasher_builtin_sched_lib debasher_lib_utils		\
debasher_lib_sched debasher_lib_sched_slurm debasher_lib_sched_builtin	\
debasher_lib_sched_procs debasher_lib_processes debasher_lib_programs	\
debasher_lib_modules debasher_lib_opts debasher_lib_conda		\
debasher_lib_docker debasher_get_vars_and_funcs debasher_check		\
db_get_reexec_procs_due_to_deps debasher_solve_knapsack_bb		\
debasher_solve_knapsack_ga

CLEANFILES = $(bin_SCRIPTS) $(libexec_SCRIPTS)

python_PYTHON= debasher_prg_lib.py debasher_knapsack_ga.py

EXTRA_DIST = debasher_lib.sh debasher_lib_utils.sh			\
debasher_lib_sched.sh debasher_lib_sched_procs.sh			\
debasher_lib_sched_slurm.sh debasher_lib_sched_builtin			\
debasher_lib_processes.sh debasher_lib_programs.sh			\
debasher_lib_modules.sh debasher_lib_opts.sh debasher_lib_conda.sh	\
debasher_lib_docker.sh debasher_builtin_sched_lib.sh debasher_exec.sh	\
debasher_exec_batch.sh debasher_get_vars_and_funcs.sh debasher_check.py	\
debasher_stop.sh debasher_status.sh debasher_stats.sh			\
debasher_process_debug.sh debasher_doc_mod.sh debasher_proc_dataset.sh	\
db_get_reexec_procs_due_to_deps.py debasher_reformat_status.py		\
debasher_solve_knapsack_bb.py debasher_solve_knapsack_ga.py		\
debasher_knapsack_ga.py

# Build using suffix rules (portable)
SUFFIXES= .sh .py .r .R

.sh :
	rm -f $@
	echo "#! " $(BASH) > $@
	echo "debasher_pkgname=\"$(PACKAGE_NAME)\"" >> $@
	echo "debasher_version=\"$(PACKAGE_VERSION)\"" >> $@
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
	echo "JAVA=\"$(JAVA)\"" >> $@
	echo "DOT=\"$(DOT)\"" >> $@
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
