apidir = $(pkgdatadir)/api
dist_api_DATA = main.py models.py requirements.txt

routersdir = $(apidir)/routers
dist_routers_DATA = routers/__init__.py routers/workflows.py

EXTRA_DIST = .gitignore

clean-local:
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true

dist-hook:
	rm -rf $(distdir)/.venv
	find $(distdir) -name __pycache__ -type d -exec rm -rf {} +
