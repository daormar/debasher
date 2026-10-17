EXTRA_DIST = .gitignore conftest.py examples.py test_hello_world.py	\
test_program.py test_build.py test_channels_and_tasks.py		\
test_dynamic_fanout_fifos.py test_resident.py test_running_sum.py	\
test_examples.py test_skip_py.py test_conda_envs.py

if HAVE_PYTEST
check-local:
	$(PYTEST) $(srcdir)
else
check-local:
	@echo "pytest not found - skipping sdk unit tests"
endif
