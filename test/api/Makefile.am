EXTRA_DIST = conftest.py test_paths.py

if HAVE_PYTEST
check-local:
	$(PYTEST) $(srcdir)
else
check-local:
	@echo "pytest not found - skipping api unit tests"
endif
