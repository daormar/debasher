Live Stats Example
^^^^^^^^^^^^^^^^^^

A non-durable resident program (see "Durable and Non-Durable Programs"
in the :ref:`resident` Section) to try by hand what that mode gives and
what it gives up. Its node ``Acquire`` reads a fake stream of readings,
one every ``-interval-ms`` milliseconds (50 by default), and sends each
one to a second node, ``Stats``, together with the readings written by
hand into its external port. ``Stats`` keeps, for each source of
readings, their count and mean and a window of the last ``-window-s``
seconds (10 by default), in memory and with the wall clock, and sends
the running statistics of each reading. Every 100 readings of the
stream it sets a notice with the rate of the stream and appends a
summary line to ``summary.jsonl`` in its output directory. A
``Supervisor``, ``Sup``, watches both.

Nothing of this is worth keeping across a crash: the window is rebuilt
by the next seconds of the stream, and the counts since the start are
a convenience. So the program is declared non-durable, and its nodes
write neither of the two hooks of the state. ``Stats`` reads the clock
in ``process_data``, which a durable program forbids, since nothing is
replayed here. What has to outlive the node, the summary, goes into a
file of its output directory, which the engine keeps across launches
and ``debasher_reset_resident`` takes away. The specification
``inbound_queue_max_mb=4`` of ``Stats`` bounds what it has read and not
yet processed, the limit that this mode has instead of the cap of an
input log.

.. literalinclude:: ../../data/webui_programs/webui_live_stats/webui_live_stats.sh
   :language: bash

The program is launched as in the :ref:`resident` Section, and the
statistics of ``Stats`` are read outside it, into a file. No snapshots
are taken: the program has no rounds.

::

    $ debasher_exec --pfile webui_live_stats.sh --outdir out
    $ while true; do cat out/__fifos__/Stats/stats; done > stats.jsonl &

Things to try with it:

* **A reading written by hand.** It gets the source ``hand``, so its
  statistics are its own: ``grep hand stats.jsonl`` shows
  ``{"source": "hand", "value": 5, "count": 1, "mean": 5.0}`` after

  ::

      $ echo '{"type": "DATA", "payload": {"value": 5}}' > out/__fifos__/Acquire/readings

* **The notice and the summary.** ``debasher_inspect_resident -d out
  notices`` shows, every 100 readings of the stream, how many readings
  arrived since the incarnation of ``Stats`` started, how many in the
  last 10 s, their rate and their mean, and ``out/Stats/summary.jsonl``
  gets a line with the same figures.
* **A crash.** ``kill -9`` on the process group of ``Stats`` (the PID in
  its ``.id`` file leads the group):

  ::

      $ kill -9 -- -$(cut -d@ -f1 out/__exec__/Stats/Stats.id)

  ``Sup`` relaunches it at its next check, with its initial state: the
  next notice counts the readings from 0 again, while
  ``summary.jsonl`` keeps its earlier lines, and ``stats.jsonl`` shows
  the counts starting again. What ``Acquire`` sent while ``Stats`` was
  down waited in the FIFO, which ``Acquire`` and ``Sup`` held, and
  reaches the new incarnation: the first readings after the relaunch
  are those. Nothing is replayed, and nothing reports what the crash
  lost of the state.
* **What a node keeps.** ``debasher_inspect_resident -d out -p Stats
  summary`` says that the program is non-durable, with no checkpoints
  and an empty input log, and the execdir of each node,
  ``out/__exec__/Stats``, has no ``checkpoints`` or ``log`` directory,
  however long the program runs. ``debasher_snapshot_resident -d out``
  refuses the program.
* **Stopping and starting again.** ``debasher_stop_resident -d out``
  says that the program is non-durable and stops its nodes without a
  halt. The next ``debasher_exec`` with the same output directory starts
  every node afresh: the counts begin at 0, and ``summary.jsonl`` goes
  on where it was. ``debasher_reset_resident -d out`` takes the summary
  away with the rest of what the processes left.
* **A change of mode.** Edit ``program_type "resident" "non-durable"``
  in the module into ``program_type "resident"`` and launch it again
  over the same output directory: ``debasher_exec`` refuses, since a
  program does not change its mode over the state of a run, and names
  ``debasher_reset_resident``.

The program carries node tests in its ``test`` directory, which
``debasher_test`` runs (see the :ref:`tools` Section): they call
``observe`` to check that ``Acquire`` sends the readings of the stream
with their source, feed it a reading written by hand to check that it
gets the source ``hand``, feed readings to ``Stats`` and check its counts
and means, the readings it drops, the summary it writes and the readings
that its window forgets. There is no restart test and no replay test:
the harness refuses ``restart`` and ``check_replay`` for a node of a
non-durable program.

.. literalinclude:: ../../data/webui_programs/webui_live_stats/test/test_live_stats.py
   :language: python
