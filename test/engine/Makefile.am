EXTRA_DIST = lib_utils.bats lib_processes.bats lib_programs.bats	\
lib_mirror.bats builtin_sched_lib.bats				\
conftest.py test_envelope.py test_fbpprocess.py test_thread_topology.py	\
test_barrier.py test_checkpoint.py test_run.py test_supervisor.py	\
test_input_log.py test_arrival_positions.py test_recovery.py test_send_data.py	\
test_dedup.py test_out_backlog.py test_close_seq.py		\
resident_run.py chaos_ref.py debasher_chaos_ref.sh		\
test_chaos.py test_guarantees.py test_stop_resident.py		\
test_halt_ref.py debasher_halt_ref.sh				\
test_array_ref.py debasher_array_ref.sh debasher_array_gen_ref.sh	\
test_fanout_cmdline_ref.py debasher_fanout_cmdline_ref.sh		\
test_selfloop_ref.py debasher_selfloop_ref.sh			\
test_startup_ref.py debasher_startup_ref.sh			\
test_resume_ref.py debasher_resume_ref.sh			\
test_launcher.py test_launcher_ref.py debasher_launcher_ref.sh	\
debasher_launcher_batch.sh					\
test_observe.py test_watcher.py test_watch_ref.py			\
debasher_watch_ref.sh debasher_watch_batch.sh			\
test_channel_kinds.py

check-local:
if HAVE_BATS
	ENGINE_BUILDDIR="$(abs_top_builddir)/engine" $(BATS) $(srcdir)
else
	@echo "bats not found - skipping engine bats tests"
endif
if HAVE_PYTEST
	$(PYTEST) $(srcdir)
else
	@echo "pytest not found - skipping engine python tests"
endif
