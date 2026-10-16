EXTRA_DIST = .gitignore conftest.py test_hello_world.py test_program.py test_build.py \
test_channels_and_tasks.py test_dynamic_fanout_fifos.py test_resident.py \
data/hello_world/hello_world.py data/hello_world/webui_hello_world_py.py \
data/dynamic_fanout_fifos/webui_dynamic_fanout_fifos.py \
data/dynamic_fanout_fifos/aggregate.sh data/dynamic_fanout_fifos/count.sh \
data/dynamic_fanout_fifos/dynamic_fanout_dispatcher.py \
data/dynamic_fanout_fifos/fragment.sh data/dynamic_fanout_fifos/generate.sh \
data/dynamic_fanout_fifos/worker.sh data/dynamic_fanout_fifos/worker_tasks.sh \
data/running_sum/webui_running_sum.py data/running_sum/accumulate.py

if HAVE_PYTEST
check-local:
	$(PYTEST) $(srcdir)
else
check-local:
	@echo "pytest not found - skipping sdk unit tests"
endif
