Batch Launcher Example
^^^^^^^^^^^^^^^^^^^^^^

A resident program with a launcher node, ``Launch``, which runs the
general program ``webui_batch_greet`` once for each request written
into its external port ``-requests``, and a node, ``Report``, which
counts the batch runs that finish and those that fail, and writes a
line for each one that ends. While some batch run has failed,
``Report`` leaves a warning notice, which it sets again in
``restore_node_state`` since a notice is not part of the node state.

.. literalinclude:: ../../data/webui_programs/webui_batch_launcher/webui_batch_launcher.sh
   :language: bash

The general program that ``Launch`` runs waits for ``-secs`` seconds
and writes a greeting for ``-text`` into a file of its output
directory; the text ``fail`` makes it fail, to show a batch run that
failed:

.. literalinclude:: ../../data/webui_programs/webui_batch_greet/webui_batch_greet.sh
   :language: bash

Once the program is running (see the :ref:`resident` Section), a
request is written into ``-requests``, while something reads the
report of ``Report``:

::

    $ cat out/__fifos__/Report/report &
    $ echo '{"type": "DATA", "payload": {"opts": {"-text": "world", "-secs": "5"}, "run": "r1"}}' \
        > out/__fifos__/Launch/requests

Five seconds later, ``Report`` writes
``{"run": "r1", "status": "finished", "finished": 1, "failed": 0}``,
and ``out/Launch/r1`` is the output directory of the batch run, with
the greeting in ``out/Launch/r1/greet/greeting.txt``.
