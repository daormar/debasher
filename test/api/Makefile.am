EXTRA_DIST = conftest.py test_fs_browse.py test_paths.py test_doc_mod.py test_markdown_parsing.py test_program_import.py test_round_trip.py test_script_generation.py test_webui_programs.py

if HAVE_PYTEST
check-local:
	$(PYTEST) $(srcdir)
else
check-local:
	@echo "pytest not found - skipping api unit tests"
endif
