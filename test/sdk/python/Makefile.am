EXTRA_DIST = conftest.py test_hello_world.py test_program.py test_build.py \
data/hello_world/hello_world.py data/hello_world/webui_hello_world_py.py

if HAVE_PYTEST
check-local:
	$(PYTEST) $(srcdir)
else
check-local:
	@echo "pytest not found - skipping sdk unit tests"
endif
