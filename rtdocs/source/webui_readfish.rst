Readfish Example
^^^^^^^^^^^^^^^^

A resident program around a real tool: readfish, the adaptive sampling
client of Oxford Nanopore sequencers. During a run, readfish receives
the first signal of every read from the sequencer software, MinKNOW,
decides whether to eject the read from its pore or to let it through,
and logs one line per batch of decisions. Its stream of reads may die in
silence, with the process alive (readfish issue 412): the sequencer goes
on, every read is sequenced whole, and nobody notices until someone
reads the log. The program keeps readfish deciding, processes the files
that the sequencer writes as they appear, and keeps one timeline of
both. It runs without a sequencer too, with a stand-in of readfish.

The program has four nodes and a ``Supervisor``, ``Sup``:

* ``Acquire`` runs readfish as a child process (the command of
  ``-command``, in the output directory of the process; a relative path in
  it that names a file next to the module is taken from there) and reads
  its log every second. The batches of reads of each second become one
  ``progress`` event for ``Report``, and each change of phase of the
  sequencer an event of its own. In the sequencing phase,
  ``-stall-timeout-s`` seconds (60 by default) without a batch, counted
  from the last batch or from the return to that phase, are a stall. During a mux scan, when MinKNOW measures the pores and sends no
  reads for some minutes, the silence is legitimate, and only
  ``-scan-timeout-s`` seconds (900) are a stall. A readfish that gives
  nothing for ``-start-timeout-s`` seconds (300) after its start, or that
  ends, is a stall too. On a stall, ``Acquire`` leaves a warning notice,
  ends readfish and raises: its process ends with an error, ``Sup``
  relaunches it, and the new incarnation starts a new readfish, which
  connects anew, as readfish restarted by hand does.
  A readfish that never gives a read, because the sequencer is gone, is
  not relaunched for ever: after ``-max-attempts`` incarnations (5) with
  no reads at all, ``Acquire`` stays, with a notice and an ``exhausted``
  event, for an operator to act. Notes written by hand into its external
  port ``notes`` reach ``Report`` like the events.
* ``Watch``, a ``DirectoryWatcher``, watches the directory given by
  ``-watchdir``, where the sequencer writes its read files (such as
  ``fast5_pass``), and sends a request for each file once it is
  complete.
* ``Launch``, a ``ProgramLauncher``, runs the general program
  ``webui_read_lengths`` once for each file, two at a time, and sends a
  message when each batch run ends. That program summarizes the lengths
  of the reads of the file: count, median, N50 and the fraction of reads
  under 1000 bases. With adaptive sampling at work most reads are short,
  so that fraction says whether readfish was deciding when the file was
  written. Its process activates the conda environment ``read_lengths``
  (Python with ``h5py`` and ``pod5``, declared in ``read_lengths.yml``,
  installed with the environment files of DeBasher) and runs
  ``read_lengths.py``, next to the module (the directory that
  ``DEBASHER_PROCESS_MODULE_DIR`` names for every process), which reads
  POD5 files through ``pod5``, FAST5 files through ``h5py``, and text
  files with one length per line. The
  specification ``batch_conda_support`` of ``Launch`` makes every batch
  run prepare that environment: the first one creates it, the rest find
  it (see "Batch Runs From a Node" in the :ref:`resident` Section).
* ``Report`` receives the events of ``Acquire`` and the ends of the
  batch runs of ``Launch``, and keeps one timeline in its node state:
  the launches, stalls and phases of readfish, and the summary of every
  file. It rewrites ``timeline.json`` in its output directory from that
  state, so that a replay writes the same file, and keeps a copy of the
  summary of each batch run in ``summaries/`` there, so that a replay
  records the same summary although the run directory may be gone. It
  sends on its output port ``timeline``, read outside the program, each
  incident, each file and a status line every ``-status-every-s`` seconds
  (60) of event time: the time that the events carry, not the clock of
  the node, which a replay does not see.

The program is durable: every file gets exactly one batch run and one
entry of the timeline across crashes of any node, and the timeline is
state worth keeping. Its rounds come from ``debasher_snapshot_resident
--every`` or, from the web interface, from its execution options, which
give a snapshot every 60 seconds; without rounds the input logs grow to
their cap, and a node ends with an error (see "Limits of a Node" in the
:ref:`resident` Section). ``Acquire`` has no state: readfish and its log
are the outside world, and the two counters that have to outlive an
incarnation, the launches and the attempts without reads, are files of
its output directory.

The join of the two halves of the program is the directory: nothing in
the program checks that ``-watchdir`` is where the readfish of
``-command`` has the sequencer write.

.. literalinclude:: ../../data/webui_programs/webui_readfish/webui_readfish.sh
   :language: bash

The stand-in
""""""""""""

Without ``-command``, ``Acquire`` runs ``fake_readfish.py``, a program
next to the module that writes the lines of readfish's log at readfish's
pace and knows nothing of DeBasher. It can stall (the file ``stall`` in
the output directory of ``Acquire``, or ``--stall-after``), go through a
mux scan (the file ``scan``, or ``--scan-every-s``) and end (the file
``exit``, or ``--exit-after``). ``Acquire`` leaves a notice while it
runs it, so that nobody sequences against it without noticing. The
node tests and ``make installcheck`` run the program with it.

.. literalinclude:: ../../data/webui_programs/webui_readfish/fake_readfish.py
   :language: python

Trying it by hand
"""""""""""""""""

The program is launched as in the :ref:`resident` Section, with the
directory to watch, and its timeline is read outside it, into a file.
The first file to arrive creates the conda environment ``read_lengths``,
which takes some minutes once; conda has to be usable (``make
installcheck`` skips the program otherwise). A relaunch of ``Report``
leaves the FIFO with no writer for a moment, which ends a plain ``cat``,
so the reader opens it again in a loop. A shorter stall timeout than the
default makes a stall quick to see.

::

    $ mkdir watched
    $ debasher_exec --pfile webui_readfish.sh --outdir out -watchdir watched -stall-timeout-s 10
    $ while true; do cat out/__fifos__/Report/timeline; done > timeline.jsonl &
    $ debasher_snapshot_resident -d out --every 60 > snapshots.log &

Things to try with it:

* **A note.** A note written into the external port of ``Acquire`` comes
  out of the timeline as a record whose payload is ``{"kind": "note",
  "text": "flow cell changed"}``:

  ::

      $ echo '{"type": "DATA", "payload": {"text": "flow cell changed"}}' > out/__fifos__/Acquire/notes

* **A file.** A text file with one read length per line, moved into the
  watched directory under a name that does not repeat, gets a batch run of
  ``webui_read_lengths`` in ``out/Launch/<name>``, and its summary comes
  out of the timeline as a ``file`` record whose payload has ``"count":
  4, ..., "short_fraction": 0.5`` for these lengths:

  ::

      $ printf '300\n500\n4000\n8000\n' > watched/.f1.txt && mv watched/.f1.txt watched/f1.txt

* **A stall.** ``touch out/Acquire/stall`` stalls the stand-in, which
  stays alive and silent. After the stall timeout ``Acquire`` leaves its
  notice, sends a ``stall`` event, ends the stand-in and raises; ``Sup``
  sees its process gone at its next check and relaunches it, and the new
  incarnation starts a new stand-in, which removes the file and goes on.
  ``out/Acquire/launches`` counts the incarnations, the timeline has the
  ``stall`` and the next ``started`` event, and
  ``debasher_inspect_resident -d out notices`` shows the notice of
  ``Report`` with the counts.
* **A mux scan.** ``touch out/Acquire/scan`` puts the stand-in through a
  scan of four minutes: the two ``phase`` events come out, and nothing
  is relaunched, although the stall timeout passes many times over.
* **A readfish that never gives a read.** With ``-command "python3
  fake_readfish.py --batch-interval-s 60" -start-timeout-s 10
  -max-attempts 3`` on the command line of ``debasher_exec`` (a relative
  path in the command that names a file next to the module is taken from
  there), every incarnation is silent for its first minute, past the start
  timeout. ``Acquire`` is relaunched three times, each one counted in
  ``out/Acquire/attempts``, and the fourth stays, with an ``exhausted``
  event and a notice that says to check the sequencer; a relaunch of the
  node by hand, from the web interface or with
  ``debasher_launch_process``, tries again.
* **A crash of a node.** ``kill -9`` on the process group of ``Report``
  (the PID in its ``.id`` file leads the group) loses nothing: ``Sup``
  relaunches it, it restores its last checkpoint and replays its input
  log, and the timeline goes on; a file moved into the watched directory
  while it was down gets its record once. ``kill -9`` on the group of
  ``Acquire`` kills the stand-in with it, since it runs in the same
  group; a ``kill -9`` of the Python process of ``Acquire`` alone leaves
  the stand-in running, and the next incarnation kills it before it
  starts its own, through the file ``out/Acquire/child.pid``.

With a sequencer
""""""""""""""""

With readfish installed, its command goes in ``-command``, without
``--log-file``, since ``Acquire`` reads what readfish writes on its
standard output and error, and ``-watchdir`` names the directory where
MinKNOW writes the read files of the run:

::

    $ debasher_exec --pfile webui_readfish.sh --outdir out \
          -command "readfish targets --device X3 --experiment-name e1 --toml e1.toml" \
          -watchdir /data/e1/pod5_pass

The same holds for a simulated sequencer, such as Icarust, with
``readfish unblock-all``.

The program carries node tests in its ``test`` directory, which
``debasher_test`` runs (see the :ref:`tools` Section): they run
``Acquire`` with the stand-in at intervals of milliseconds and call
``observe`` to check the events it sends, that a stall in the sequencing
phase and a scan that never ends make it raise, that a scan does not, that
a readfish that ends does, that the relaunches with no reads are counted
and then stop, and that a new incarnation kills the readfish of the
earlier one; they feed ``Report`` events and ends of batch runs to check
its totals, its status lines, its incidents and the summaries it records,
restart it to check that its timeline goes on, and check that a replay of
the events gives the same timeline. ``webui_read_lengths`` carries tests
of its summary.

.. literalinclude:: ../../data/webui_programs/webui_readfish/test/test_readfish.py
   :language: python
