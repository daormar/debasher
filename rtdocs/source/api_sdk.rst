.. _sdk-api:

Python SDK
==========

.. default-role:: literal

A program described in Python (see the :ref:`implem_python` Section) is
made of the classes and functions below, which a Python description
imports from the package ``debasher``:

.. code-block:: python

    from debasher import Process, Program, connect, in_outdir, opt

Only what a Python description uses is listed: the classes it creates,
the methods it calls and the functions it uses. ``debasher_build`` (see
the :ref:`tools` Section) loads the file and writes the program; the
last section describes what the Python functions of a process (the tasks
of an array or a generator, and the ``skip`` method) receive when the
engine calls them.

Program
-------

.. autoclass:: debasher.Program
   :members: add, processes, write

Processes
---------

A process is created with what does not change (its code, its
description, the options that its tasks receive, its environments and
the methods of a task); ``interface`` gives what it receives from
outside the program, and ``task_options`` the shape of its tasks and
the value of each option.

.. autoclass:: debasher.Process(name, code=None, script=None, alias=None, description="", options=(), alias_opt_map=None, base_dir=None, skip=None, post=None, reset_outfiles=None, conda_envs=None, docker_imgs=None)

.. automethod:: debasher.Process.interface(cmdline=None, shaping=None, external=None)

.. automethod:: debasher.Process.task_options(values=None, array=None, generator=None, count=None)

.. automethod:: debasher.Process.__getitem__

Options
-------

The options that the tasks of a process receive, for its ``options=``:

.. autofunction:: debasher.opt(label, data_type, description="")

.. autofunction:: debasher.flag(label, description="")

.. autoclass:: debasher.Option()

The values of the options in ``task_options(values=...)``, besides a
string (a literal value) and ``True`` (a flag set in every task):

.. autofunction:: debasher.connect(source, display="line")

.. autofunction:: debasher.fifo(name, mirror=False)

.. autofunction:: debasher.outdir(subpath="")

.. autofunction:: debasher.shared_dir(name, subpath="", source=None)

.. autofunction:: debasher.procspec(attribute)

.. autofunction:: debasher.value_desc()

.. autofunction:: debasher.in_outdir

Resident programs
-----------------

A resident program (``Program(..., resident=True)``) adds nodes and a
``Supervisor`` instead of processes.

.. autoclass:: debasher.Node(name, code, description="", options=(), base_dir=None)

.. autoclass:: debasher.Supervisor(name, description="", base_dir=None)

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
