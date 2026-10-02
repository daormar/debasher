Directory Watcher Example
^^^^^^^^^^^^^^^^^^^^^^^^^

A resident program with a ``DirectoryWatcher``, ``Watch``, which
watches the directory given by the command line option ``-watchdir``
and, for each text file there once it is complete, sends a request to
a node, ``Tally``, which counts the files requested so far and writes
out the name of each file with that count. ``Watch`` has no code of its
own but the pattern of the files it counts: a file whose name starts
with a dot never counts, so a file written under a hidden name and
renamed at the end is seen only once it is complete.

.. literalinclude:: ../../data/webui_programs/webui_watch_tally/webui_watch_tally.sh
   :language: bash

Once the program is running (see the :ref:`resident` Section), with
``-watchdir in`` on the command line of ``debasher_exec``, something
reads the output of ``Tally`` while files arrive in ``in``:

::

    $ cat out/__fifos__/Tally/tally &
    $ echo hello > in/.a.txt && mv in/.a.txt in/a.txt

A second or two later, once ``a.txt`` has stayed the same for two
observations, ``Tally`` writes ``{"run": "a", "seen": 1}``.

The program carries node tests in its ``test`` directory, which
``debasher_test`` runs (see the :ref:`tools` Section): they put files
in a temporary directory that ``Watch`` watches and call ``observe``
to check which ones it requests, feed requests to ``Tally`` to check
its count, and restart both nodes to check that nothing is requested
twice and that the count goes on.

.. literalinclude:: ../../data/webui_programs/webui_watch_tally/test/test_watch_tally.py
   :language: python
