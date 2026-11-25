ACLOCAL_AMFLAGS = -I m4
EXTRA_DIST = m4 reconf configure COPYING.LESSER README.md NEWS.md
SUBDIRS = m4 engine api sdk frontend doc data test

# Like "make dist", but also vendors a freshly-built frontend/dist/ into
# the tarball (see frontend/Makefile.am's dist-hook and configure.ac's
# npm check), so the result can be configured/installed without npm on
# the machine that consumes it, e.g. a bioconda build with no network
# access. Requires npm on the machine running this target.
.PHONY: dist-vendored
dist-vendored:
	$(MAKE) -C frontend all
	$(MAKE) dist DEBASHER_VENDOR_FRONTEND=yes

# CRAP report of the Python code (see test/Makefile.am) and of the
# frontend (see frontend/Makefile.am).
.PHONY: crap
crap:
	$(MAKE) -C test crap
	@echo
	$(MAKE) -C frontend crap

# Complexity of the Bash functions of the engine, hotspots of the code, its
# change coupling, the depth of its modules and its duplication, see
# test/Makefile.am.
.PHONY: bash-complexity hotspots coupling module-depth duplication
bash-complexity hotspots coupling module-depth duplication:
	$(MAKE) -C test $@

# List of the targets worth calling by hand, with what each one does: the
# standard ones of Automake and those defined above.
.PHONY: help
help:
	@echo "Build and install:"
	@echo "  all              build everything (the default target)"
	@echo "  install          install under the prefix given to configure"
	@echo "  uninstall        remove what install put in place"
	@echo "  clean            remove what all built"
	@echo "  distclean        clean, and also remove what configure generated"
	@echo ""
	@echo "Tests:"
	@echo "  check            run the bats, pytest and frontend (vitest) tests"
	@echo "  installcheck     run the example programs against the installation"
	@echo ""
	@echo "Distribution:"
	@echo "  dist             build the source tarball"
	@echo "  distcheck        build the tarball, then build and test it apart"
	@echo "  dist-vendored    like dist, but with a built frontend/dist inside"
	@echo "                   (installable without npm; needs npm here)"
	@echo ""
	@echo "Code analysis reports (see test/utils/README.md):"
	@echo "  crap             CRAP score of the Python code and of the frontend"
	@echo "  bash-complexity  complexity of the Bash functions of the engine"
	@echo "  hotspots         files both complex and often changed"
	@echo "  coupling         files that change together in the same commits"
	@echo "  module-depth     depth of the modules against their interface"
	@echo "  duplication      fragments and functions written twice"
