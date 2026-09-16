if INSTALL_FRONTEND

if BUILD_FRONTEND
FRONTEND_STAMP = .build-stamp
else
# No npm: frontend/dist/ is expected to already be present, vendored into
# this source tree by "make dist-vendored" (see the root Makefile.am and
# the dist-hook below). Nothing to build, so no stamp file to depend on.
FRONTEND_STAMP =
endif

if BUILD_FRONTEND
# Rebuild only when package.json, the lockfile, or source files change
$(FRONTEND_STAMP): package.json package-lock.json \
                    $(shell find $(srcdir)/src -type f 2>/dev/null)
	$(NPM) ci
	$(NPM) run build
	touch $@

all-local: $(FRONTEND_STAMP)

check-local: $(FRONTEND_STAMP)
	$(NPM) run test

clean-local:
	rm -rf dist $(FRONTEND_STAMP)
endif

install-data-local: $(FRONTEND_STAMP)
	$(MKDIR_P) $(DESTDIR)$(pkgdatadir)/web
	cp -r dist/. $(DESTDIR)$(pkgdatadir)/web/

uninstall-local:
	rm -rf $(DESTDIR)$(pkgdatadir)/web

distclean-local:
	rm -rf node_modules

endif

EXTRA_DIST = src public index.html package.json package-lock.json \
             vite.config.ts tsconfig.json tsconfig.app.json tsconfig.node.json

# "make dist" always ships pure sources (no dist/), matching autotools
# convention: a tarball you still need npm to build. "make dist-vendored"
# (see the root Makefile.am) sets DEBASHER_VENDOR_FRONTEND=yes to also
# embed an already-built frontend/dist/ in the tarball, so it can later be
# configured/installed without npm at all (configure.ac falls back to
# installing that prebuilt dist/ as-is when npm isn't found).
dist-hook:
	rm -rf $(distdir)/node_modules
	rm -rf $(distdir)/dist
	if test "x$(DEBASHER_VENDOR_FRONTEND)" = "xyes"; then \
	  $(MKDIR_P) $(distdir)/dist; \
	  cp -r dist/. $(distdir)/dist/; \
	  : > $(distdir)/dist/.vendored; \
	fi
