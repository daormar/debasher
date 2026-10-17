# Programs built with the web UI: one home directory each, with its
# artifact (the topology file program.yaml and the files it names) and its
# generated script. nobase_ keeps that layout under webuiprgdir, so that
# the web UI can load an installed program from its own directory, and
# debasher_test can run the tests in its test directory.
webuiprgdir = $(datadir)/$(PACKAGE)/webui_programs
nobase_webuiprg_DATA = webui_batch_greet/greet.sh	\
webui_batch_greet/program.yaml	\
webui_batch_greet/test/greet.bats	\
webui_batch_greet/webui_batch_greet.sh	\
webui_batch_launcher/Launch.py	\
webui_batch_launcher/Report.py	\
webui_batch_launcher/program.yaml	\
webui_batch_launcher/webui_batch_launcher.sh	\
webui_conda_example/program.yaml	\
webui_conda_example/python_version.sh	\
webui_conda_example/python_version_conda_envs.sh	\
webui_conda_example/test/python_version.bats	\
webui_conda_example/webui_conda_example.sh	\
webui_conda_envs/program.yaml	\
webui_conda_envs/python_version.sh	\
webui_conda_envs/webui_conda_envs.sh	\
webui_dynamic_fanout_fifos/aggregate.sh	\
webui_dynamic_fanout_fifos/count.sh	\
webui_dynamic_fanout_fifos/dynamic_fanout_dispatcher.py	\
webui_dynamic_fanout_fifos/fragment.sh	\
webui_dynamic_fanout_fifos/generate.sh	\
webui_dynamic_fanout_fifos/program.yaml	\
webui_dynamic_fanout_fifos/webui_dynamic_fanout_fifos.sh	\
webui_dynamic_fanout_fifos/worker.sh	\
webui_dynamic_fanout_fifos/worker_tasks.py	\
webui_fifo_sum/numbers.sh	\
webui_fifo_sum/program.yaml	\
webui_fifo_sum/sum.sh	\
webui_fifo_sum/webui_fifo_sum.sh	\
webui_hello_world/hello_world.sh	\
webui_hello_world/program.yaml	\
webui_hello_world/webui_hello_world.sh	\
webui_hello_world_py/hello_world.py	\
webui_hello_world_py/program.yaml	\
webui_hello_world_py/webui_hello_world_py.sh	\
webui_running_sum/Accumulate.py	\
webui_running_sum/program.yaml	\
webui_running_sum/test/test_accumulate.py	\
webui_running_sum/webui_running_sum.sh	\
webui_skip_py/program.yaml	\
webui_skip_py/value_reader.sh	\
webui_skip_py/value_reader_skip.py	\
webui_skip_py/value_writer.sh	\
webui_skip_py/webui_skip_py.sh	\
webui_watch_tally/Tally.py	\
webui_watch_tally/Watch.py	\
webui_watch_tally/program.yaml	\
webui_watch_tally/test/test_watch_tally.py	\
webui_watch_tally/webui_watch_tally.sh

EXTRA_DIST = $(nobase_webuiprg_DATA)
