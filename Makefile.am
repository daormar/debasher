ACLOCAL_AMFLAGS = -I m4
EXTRA_DIST = m4 reconf configure COPYING.LESSER README.md
SUBDIRS = m4 engine api frontend doc data test

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

# Complexity of the Bash functions of the engine, hotspots of the code and
# its change coupling, see test/Makefile.am.
.PHONY: bash-complexity hotspots coupling
bash-complexity hotspots coupling:
	$(MAKE) -C test $@
