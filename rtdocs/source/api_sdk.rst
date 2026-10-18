.. _sdk-api:

Python SDK
==========

.. default-role:: literal

A program described in Python (see the :ref:`implem_python` Section)
is made of the classes below, which the file of the description
imports from the package ``debasher``:

.. code-block:: python

    from debasher import Process, Program, in_outdir

Only what a description uses is listed: the classes it creates, the
methods it calls and the functions it uses. ``debasher_build`` (see the
:ref:`tools` Section) loads the file and writes the program; the last
section describes what the Python functions of a process (the tasks of
an array or a generator, and the ``skip`` method) receive when the
engine calls them.

Program
-------

.. autoclass:: debasher.Program
   :members: add, processes, write

Processes
---------

.. autoclass:: debasher.Process

.. automethod:: debasher.Process.__getitem__

.. autoclass:: debasher.Array

.. autoclass:: debasher.Generator

Options
-------

Every option is declared by a method of its process, which returns it.

.. automethod:: debasher.Process.cmdline_opt

.. automethod:: debasher.Process.cmdline_flag

.. automethod:: debasher.Process.input

.. automethod:: debasher.Process.output

.. automethod:: debasher.Process.fifo_output

.. automethod:: debasher.Process.fifo_input

.. automethod:: debasher.Process.outdir_opt

.. automethod:: debasher.Process.shared_dir_opt

.. automethod:: debasher.Process.procspec_opt

.. automethod:: debasher.Process.value_desc_output

.. automethod:: debasher.Process.opt

.. autofunction:: debasher.in_outdir

.. autoclass:: debasher.Option()

Resident programs
-----------------

A resident program (``Program(..., resident=True)``) adds nodes and a
``Supervisor`` instead of processes.

.. autoclass:: debasher.Node

.. autoclass:: debasher.Supervisor

Errors
------

.. autoclass:: debasher.DefinitionError()

Python functions of a process
-----------------------------

The function ``tasks(run)`` of a tasks file in Python receives a
``Run``, and the function ``skip(task)`` of a skip file in Python
receives a ``Task``. The file imports nothing to receive them.

.. autoclass:: debasher_run_py_func.Run()
   :members: value, given
   :inherited-members:

.. autoclass:: debasher_run_py_func.Task()
   :members: value, given
   :inherited-members:
