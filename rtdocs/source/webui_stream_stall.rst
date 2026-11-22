Stream Stall Example
^^^^^^^^^^^^^^^^^^^^

A resident program to try by hand what a resident program does when
something goes wrong. Its node ``Acquire`` reads a fake stream of
reads, as a tool such as readfish reads the stream of a sequencer, and
sends each read to a second node, ``Tally``, which counts the reads by
channel and sends a decision for each one. A ``Supervisor``, ``Sup``,
watches both.

The stream can stall: it gives no more data, and it does not close. The
process of ``Acquire`` stays alive, so nothing would notice. Its
``observe`` method notices instead: when the stream gives nothing for
``-stall-timeout-s`` seconds (5 by default), it leaves a warning notice
and raises an exception, which ends its process with an error. ``Sup``
relaunches it, and the relaunch opens a new connection. The stream
stalls when a file ``stall`` exists in the output directory of
``Acquire``, which a new connection removes, or after ``-stall-after``
reads of every connection (0, never, by default).

The limits of the two nodes are small on purpose (see "Limits of a
Node" in the :ref:`resident` Section): ``Acquire`` has
``out_backlog_max_mb=0.5`` and ``out_backlog_fail_mb=1``, and ``Tally``
has ``input_log_max_mb=4``. At the default pace of the stream, about
50 reads a second of about 1 KiB each, the backlog limits of
``Acquire`` are reached within 20 s once ``Tally`` stops reading, and
the cap of the input log of ``Tally`` a little over a minute after
the start if no round prunes it.

.. literalinclude:: ../../data/webui_programs/webui_stream_stall/webui_stream_stall.sh
   :language: bash

The program is launched as in the :ref:`resident` Section, and the
decisions of ``Tally`` are read outside it, into a file, since there
are about 50 a second. A relaunch of ``Tally`` leaves the FIFO with no
writer for a moment, which ends a plain ``cat``, so the reader opens it
again in a loop. Rounds every 10 seconds prune the input logs; with
them, and a reader, the program runs for as long as it is left. Run
from the web interface, it starts those rounds by itself: its
execution options give a snapshot every 10 seconds.

::

    $ debasher_exec --pfile webui_stream_stall.sh --outdir out
    $ while true; do cat out/__fifos__/Tally/decisions; done > decisions.jsonl &
    $ debasher_snapshot_resident -d out --every 10 > snapshots.log &

Things to try with it:

* **A read written by hand.** The external port of ``Acquire`` takes
  reads from outside the program, which follow the same way as those of
  the stream. A read on channel 0, which the stream never uses, gets a
  decision whose payload is ``{"id": "by-hand", "decision": "unblock",
  "channel_reads": 1}``, which ``grep by-hand decisions.jsonl`` shows:

  ::

      $ echo '{"type": "DATA", "payload": {"id": "by-hand", "channel": 0, "length": 300}}' \
            > out/__fifos__/Acquire/reads

* **A stall.** ``touch out/Acquire/stall`` stalls the stream. Five
  seconds later ``Acquire`` raises, and its process ends with an error.
  ``Sup`` sees that its process is gone at its next check and relaunches
  it, some 5 to 15 s after the ``touch``. The new connection removes the
  file, and the stream goes on. ``out/Acquire/connections`` counts the
  connections, and ``debasher_inspect_resident -d out notices`` shows
  the notice of the stall until the relaunch.
* **A relaunch that never ends.** With ``-stall-after 200`` on the
  command line of ``debasher_exec``, every connection stalls after 200
  reads. The first heartbeat of each relaunch resets the count of
  relaunches of ``Acquire``, so ``Sup`` relaunches it for ever and never
  gives up on it.
* **A frozen node.** ``kill -STOP`` on the whole process group of
  ``Tally`` freezes it (the PID in its ``.id`` file leads the group, and
  the Python interpreter of the node runs below it):

  ::

      $ kill -STOP -- -$(cut -d@ -f1 out/__exec__/Tally/Tally.id)

  ``Acquire`` goes on sending, and what ``Tally`` does not read piles up
  in the outbound backlog of ``Acquire``. About 10 s after the freeze
  the backlog is over ``out_backlog_max_mb``, and from the next round on
  ``Acquire`` writes no checkpoint, with a warning in its log. About
  20 s after the freeze it reaches ``out_backlog_fail_mb``: ``Acquire``
  fails, its process ends, and ``Sup`` relaunches it a few seconds
  later. Meanwhile ``Sup`` relaunches the frozen ``Tally`` too, once it
  has sent no heartbeat for 30 s: to the ``Supervisor``, a frozen node
  looks like a node whose whole process hangs. ``kill -CONT`` with the
  same argument within those 20 s thaws ``Tally``, the backlog drains,
  and nothing is relaunched.
* **The size cap of an input log.** Launched without the
  ``debasher_snapshot_resident`` line (or, from the web interface, with
  no snapshot period in its execution options), the program runs no
  rounds, and nothing prunes the input log of ``Tally``. The log reaches
  its cap a little over a minute after the start, and ``Tally`` stops
  with an error that says so, which ends its process. ``Sup`` relaunches
  it, but only a round prunes the log: each relaunched ``Tally`` finds
  it still full, and fails before its first heartbeat. Meanwhile
  ``Tally`` reads nothing, so ``Acquire`` may reach its fail limit too
  and be relaunched. After three relaunches of ``Tally``, ``Sup`` gives
  up on it and stops what remains of the program, a stop that may fall
  back to ``debasher_stop`` (the log of ``Sup`` then ends with a warning
  that says ``forcing debasher_stop``). ``debasher_reset_resident`` then
  takes it back to its first run.
* **Stopping, resuming, inspecting and resetting.**
  ``debasher_stop_resident -d out`` stops the program in order, and the
  next ``debasher_exec`` with the same output directory resumes it,
  each node from its last checkpoint and its input log.
  ``debasher_inspect_resident -d out -p Tally summary`` shows the
  checkpoints, the input log, the outbound backlog and the notice of
  ``Tally``, and ``debasher_reset_resident -d out`` takes a stopped
  program back to its first run.

The times above follow from the pace of the stream and the limits;
``-chunk-interval-ms`` sets the pace.

The program carries node tests in its ``test`` directory, which
``debasher_test`` runs (see the :ref:`tools` Section): they call
``observe`` to check that ``Acquire`` sends the reads of the stream,
that it raises when the stream stalls and that a new connection clears
a stall, feed a read to each node, restart ``Tally`` to check that its
count goes on, and check that a replay of the reads gives the same
decisions.

.. literalinclude:: ../../data/webui_programs/webui_stream_stall/test/test_stream_stall.py
   :language: python
