# Programs built with the web UI: one home directory each, with its
# program metadata (.debasher/program.json) and its generated script.
# nobase_ keeps that layout under webuiprgdir, so that the web UI can
# load an installed program from its own directory.
webuiprgdir = $(datadir)/$(PACKAGE)/webui_programs
nobase_webuiprg_DATA = webui_fifo_sum/webui_fifo_sum.sh	\
webui_fifo_sum/.debasher/program.json

EXTRA_DIST = $(nobase_webuiprg_DATA)
