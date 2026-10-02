# Programs built with the web UI: one home directory each, with its
# program metadata (.debasher/program.json) and its generated script.
# nobase_ keeps that layout under webuiprgdir, so that the web UI can
# load an installed program from its own directory, and debasher_test
# can run the tests in its test directory.
webuiprgdir = $(datadir)/$(PACKAGE)/webui_programs
nobase_webuiprg_DATA = webui_batch_greet/webui_batch_greet.sh	\
webui_batch_greet/.debasher/program.json			\
webui_batch_greet/test/greet.bats				\
webui_batch_launcher/webui_batch_launcher.sh			\
webui_batch_launcher/.debasher/program.json			\
webui_fifo_sum/webui_fifo_sum.sh				\
webui_fifo_sum/.debasher/program.json				\
webui_running_sum/webui_running_sum.sh				\
webui_running_sum/.debasher/program.json			\
webui_running_sum/test/test_accumulate.py			\
webui_watch_tally/webui_watch_tally.sh				\
webui_watch_tally/.debasher/program.json			\
webui_watch_tally/test/test_watch_tally.py			\
webui_conda_example/webui_conda_example.sh			\
webui_conda_example/.debasher/program.json			\
webui_conda_example/test/python_version.bats

EXTRA_DIST = $(nobase_webuiprg_DATA)
