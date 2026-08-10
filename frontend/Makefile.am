if BUILD_FRONTEND

FRONTEND_STAMP = .build-stamp

# Rebuild only when package.json, the lockfile, or source files change
$(FRONTEND_STAMP): package.json package-lock.json \
                    $(shell find $(srcdir)/src -type f 2>/dev/null)
	$(NPM) ci
	$(NPM) run build
	touch $@

all-local: $(FRONTEND_STAMP)

install-data-local: $(FRONTEND_STAMP)
	$(MKDIR_P) $(DESTDIR)$(pkgdatadir)/web
	cp -r dist/. $(DESTDIR)$(pkgdatadir)/web/

uninstall-local:
	rm -rf $(DESTDIR)$(pkgdatadir)/web

clean-local:
	rm -rf dist $(FRONTEND_STAMP)

distclean-local:
	rm -rf node_modules

endif

EXTRA_DIST = src public index.html package.json package-lock.json \
             vite.config.js tsconfig.json

dist-hook:
	rm -rf $(distdir)/node_modules
	rm -rf $(distdir)/dist
