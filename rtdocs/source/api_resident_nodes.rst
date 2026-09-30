.. _resident-nodes-api:

Resident Node Classes (Python)
==============================

.. default-role:: literal

The processes of a resident program (see the :ref:`resident` Section)
are Python classes that derive from the classes below, which the
module imports from ``debasher_runtime_lib``:

.. code-block:: python

    from debasher_runtime_lib import FBPProcess

Only what a module uses is listed: the hooks that a node redefines,
the methods that it calls, and the class attributes that it may set.
A subclass sets a class attribute for every process that uses it;
some of them can also be set for one process of a program, in the
computational specifications that ``add_debasher_process`` gives it,
as the description of each says.

FBPProcess
----------

.. autoclass:: debasher_runtime_lib.FBPProcess()

Hooks
^^^^^

.. automethod:: debasher_runtime_lib.FBPProcess.process_data

.. automethod:: debasher_runtime_lib.FBPProcess.capture_node_state

.. automethod:: debasher_runtime_lib.FBPProcess.restore_node_state

.. automethod:: debasher_runtime_lib.FBPProcess.initialize_runtime

.. automethod:: debasher_runtime_lib.FBPProcess.observe

Methods
^^^^^^^

.. automethod:: debasher_runtime_lib.FBPProcess.run

.. automethod:: debasher_runtime_lib.FBPProcess.send_data

.. automethod:: debasher_runtime_lib.FBPProcess.sleep

.. automethod:: debasher_runtime_lib.FBPProcess.inject

.. automethod:: debasher_runtime_lib.FBPProcess.observe_now

.. automethod:: debasher_runtime_lib.FBPProcess.set_notice

.. automethod:: debasher_runtime_lib.FBPProcess.clear_notice

Class attributes
^^^^^^^^^^^^^^^^

.. autoattribute:: debasher_runtime_lib.FBPProcess.OBSERVE_PORT

.. autoattribute:: debasher_runtime_lib.FBPProcess.OBSERVE_INTERVAL_SECS

.. autoattribute:: debasher_runtime_lib.FBPProcess.HEARTBEAT_INTERVAL_SECONDS

.. autoattribute:: debasher_runtime_lib.FBPProcess.INPUT_LOG_MAX_BYTES

.. autoattribute:: debasher_runtime_lib.FBPProcess.OUT_BACKLOG_MAX_BYTES

.. autoattribute:: debasher_runtime_lib.FBPProcess.OUT_BACKLOG_FAIL_BYTES

.. autoattribute:: debasher_runtime_lib.FBPProcess.GIL_SWITCH_INTERVAL_SECS

.. autoattribute:: debasher_runtime_lib.FBPProcess.NOTICE_MAX_CHARS

DirectoryWatcher
----------------

.. autoclass:: debasher_runtime_lib.DirectoryWatcher()

Methods a module may redefine
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. automethod:: debasher_runtime_lib.DirectoryWatcher.request_for

.. automethod:: debasher_runtime_lib.DirectoryWatcher.is_complete

Class attributes
^^^^^^^^^^^^^^^^

.. autoattribute:: debasher_runtime_lib.DirectoryWatcher.WATCH_DIR

.. autoattribute:: debasher_runtime_lib.DirectoryWatcher.WATCH_DIR_OPTION

.. autoattribute:: debasher_runtime_lib.DirectoryWatcher.PATTERN

.. autoattribute:: debasher_runtime_lib.DirectoryWatcher.STABLE_OBSERVATIONS

.. autoattribute:: debasher_runtime_lib.DirectoryWatcher.REQUESTS_PORT

.. autoattribute:: debasher_runtime_lib.DirectoryWatcher.FILE_OPTION

ProgramLauncher
---------------

.. autoclass:: debasher_runtime_lib.ProgramLauncher()

Class attributes
^^^^^^^^^^^^^^^^

.. autoattribute:: debasher_runtime_lib.ProgramLauncher.PFILE

.. autoattribute:: debasher_runtime_lib.ProgramLauncher.PROCESS

.. autoattribute:: debasher_runtime_lib.ProgramLauncher.RUNS_ROOT

.. autoattribute:: debasher_runtime_lib.ProgramLauncher.DONE_PORT

.. autoattribute:: debasher_runtime_lib.ProgramLauncher.MAX_CONCURRENT_RUNS

.. autoattribute:: debasher_runtime_lib.ProgramLauncher.BATCH_SCHED

.. autoattribute:: debasher_runtime_lib.ProgramLauncher.STATUS_CHECK_INTERVAL_SECS

Supervisor
----------

.. autoclass:: debasher_runtime_lib.Supervisor()

Methods a module may redefine
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. automethod:: debasher_runtime_lib.Supervisor.on_node_down

.. automethod:: debasher_runtime_lib.Supervisor.on_node_permanently_failed

Class attributes
^^^^^^^^^^^^^^^^

.. autoattribute:: debasher_runtime_lib.Supervisor.HEARTBEAT_TIMEOUT_SECS

.. autoattribute:: debasher_runtime_lib.Supervisor.HEARTBEAT_CHECK_INTERVAL_SECS

.. autoattribute:: debasher_runtime_lib.Supervisor.STARTUP_TIMEOUT_SECS

.. autoattribute:: debasher_runtime_lib.Supervisor.MAX_RELAUNCH_ATTEMPTS

.. autoattribute:: debasher_runtime_lib.Supervisor.FORCE_STOP_TIMEOUT_SECS
