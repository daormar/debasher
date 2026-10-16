# Programs described with the Python SDK: one directory each, with the
# description named after the program (<name>.py) and the files of its
# processes beside it. nobase_ keeps that layout under sdkprgdir, so that
# debasher_build can build an installed example from its own directory
# (into another, as make installcheck does).
sdkprgdir = $(datadir)/$(PACKAGE)/sdk_programs/python
nobase_sdkprg_DATA = sdk_hello_world_py/sdk_hello_world_py.py		\
sdk_hello_world_py/hello_world.py					\
sdk_dynamic_fanout_fifos/sdk_dynamic_fanout_fifos.py			\
sdk_dynamic_fanout_fifos/aggregate.sh					\
sdk_dynamic_fanout_fifos/count.sh					\
sdk_dynamic_fanout_fifos/dynamic_fanout_dispatcher.py			\
sdk_dynamic_fanout_fifos/fragment.sh					\
sdk_dynamic_fanout_fifos/generate.sh					\
sdk_dynamic_fanout_fifos/worker.sh					\
sdk_dynamic_fanout_fifos/worker_tasks.sh				\
sdk_running_sum/sdk_running_sum.py					\
sdk_running_sum/accumulate.py

EXTRA_DIST = $(nobase_sdkprg_DATA)
