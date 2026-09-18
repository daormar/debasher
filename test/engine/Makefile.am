EXTRA_DIST = lib_utils.bats lib_processes.bats lib_programs.bats	\
lib_mirror.bats						\
conftest.py test_envelope.py test_fbpprocess.py test_thread_topology.py	\
test_barrier.py test_checkpoint.py test_run.py

check-local:
if HAVE_BATS
	ENGINE_BUILDDIR="$(abs_top_builddir)/engine" $(BATS) $(srcdir)
else
	@echo "bats not found - skipping engine bats tests"
endif
if HAVE_PYTEST
	$(PYTEST) $(srcdir)
else
	@echo "pytest not found - skipping engine python tests"
endif
