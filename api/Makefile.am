apidir = $(pkgdatadir)/api
dist_api_DATA = main.py models.py persistence.py requirements.txt

routersdir = $(apidir)/routers
dist_routers_DATA = routers/__init__.py routers/processes.py routers/workflows.py

bin_SCRIPTS = debasher_webui

CLEANFILES = debasher_webui

EXTRA_DIST = .gitignore README.md debasher_webui.sh

debasher_webui: debasher_webui.sh
	rm -f $@
	echo "#! " $(BASH) > $@
	echo "debasher_pkgdatadir=\"$(pkgdatadir)\"" >> $@
	echo "debasher_default_python=\"$(PYTHON)\"" >> $@
	cat $< >> $@
	chmod ugo+x $@

clean-local:
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true

dist-hook:
	rm -rf $(distdir)/.venv
	find $(distdir) -name __pycache__ -type d -exec rm -rf {} +
