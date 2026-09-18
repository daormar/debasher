EXTRA_DIST = lib_utils.bats lib_processes.bats lib_programs.bats	\
conftest.py test_envelope.py test_fbpprocess.py

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
