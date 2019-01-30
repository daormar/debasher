SCRIPTS_TO_BE_BUILT= bam_utils_lib exec_pipeline exec_pipeline_batch	\
check_pipeline pipeline_software_test get_analysis_status

bin_SCRIPTS = $(SCRIPTS_TO_BE_BUILT)

CLEANFILES = $(SCRIPTS_TO_BE_BUILT)

EXTRA_DIST = bam_utils_lib.sh exec_pipeline.sh exec_pipeline_batch.sh	\
check_pipeline.py pipeline_software_test.sh get_analysis_status.sh

# Build rules for libraries
bam_utils_lib: bam_utils_lib.sh
	rm -f $@
	cat bam_utils_lib.sh >> $@

# Build using suffix rules (portable)
SUFFIXES= .sh .py .r .R

.sh :
	rm -f $@
	echo "#! " $(BASH) > $@
	echo "pkgname=\""$(PACKAGE_NAME)"\"" >> $@
	echo "version=\""$(PACKAGE_VERSION)"\"" >> $@
	echo "bindir="$(prefix)/bin/ >> $@
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
	echo "HEAD="$(HEAD) >> $@
	echo "TAIL="$(TAIL) >> $@
	echo "DIFF="$(DIFF) >> $@
	echo "FIND="$(FIND) >> $@
	echo "WC="$(WC) >> $@
	echo "MKTEMP="$(MKTEMP) >> $@
	echo "FLOCK="$(FLOCK) >> $@
	echo "QSUB=\""$(QSUB)"\"" >> $@
	echo "QSUB_WORKS=\""$(QSUB_WORKS)"\"" >> $@
	echo "QSUB_TERSE_OPT=\""$(QSUB_TERSE_OPT)"\"" >> $@
	echo "QSTAT="$(QSTAT) >> $@
	echo "QSTAT_J_OPT=\""$(QSTAT_J_OPT)"\"" >> $@
	echo "QRLS="$(QRLS) >> $@
	echo "SRUN="$(SRUN) >> $@
	echo "SBATCH="$(SBATCH) >> $@
	echo "SQUEUE="$(SQUEUE) >> $@
	echo "WGET="$(WGET) >> $@
	echo "PANDOC="$(PANDOC) >> $@
	echo "PYTHON="$(PYTHON) >> $@
	echo "JAVA="$(JAVA) >> $@
	echo "DISABLE_SCHEDULERS="$(DISABLE_SCHEDULERS) >> $@
	echo "SAMTOOLS="$(SAMTOOLS) >> $@
	echo "PLATYPUS_HOME_DIR="$(PLATYPUS_HOME_DIR) >> $@
	echo "FACETS_HOME_DIR="$(FACETS_HOME_DIR) >> $@
	echo "ICGCSTOR_HOME_DIR="$(ICGCSTOR_HOME_DIR) >> $@
	echo "ASPERA_HOME_DIR="$(ASPERA_HOME_DIR) >> $@
	echo "EGADECRYPT_HOME_DIR="$(EGADECRYPT_HOME_DIR) >> $@
	cat $< >> $@
	chmod ugo+x $@

.py:
	rm -f $@
	echo "#! " $(PYTHON) > $@
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
