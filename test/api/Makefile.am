EXTRA_DIST = conftest.py test_paths.py test_markdown_parsing.py test_program_import.py

if HAVE_PYTEST
check-local:
	$(PYTEST) $(srcdir)
else
check-local:
	@echo "pytest not found - skipping api unit tests"
endif
