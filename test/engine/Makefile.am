EXTRA_DIST = lib_utils.bats lib_processes.bats lib_programs.bats

if HAVE_BATS
check-local:
	ENGINE_BUILDDIR="$(abs_top_builddir)/engine" $(BATS) $(srcdir)
else
check-local:
	@echo "bats not found - skipping engine unit tests"
endif
