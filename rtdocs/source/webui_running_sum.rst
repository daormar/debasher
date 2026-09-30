Running Sum Example
^^^^^^^^^^^^^^^^^^^

A resident program whose node, ``Accumulate``, keeps the running sum
of the numbers written into its external port, and writes each new sum
out; a ``Supervisor``, ``Sup``, watches it. The :ref:`resident`
Section goes through this module and shows how to run it.

.. literalinclude:: ../../data/webui_programs/webui_running_sum/webui_running_sum.sh
   :language: bash
