.. _API:

DeBasher API
============

A program is written against one of three interfaces: the Bash
functions that a module calls, the Python classes of the SDK and of
the nodes of a resident program, and the format of the file in which
a program is saved.

Bash modules
------------

The functions that a module written by hand (see the
:ref:`implem_bash` Section), or the code of its processes, calls.

.. toctree::

   api_mod_conf

   api_prog_def

   api_proc_opts

   api_proc_impl

   api_serialized_cmdline_reading

   api_characterize_opts

   api_steps

   api_envs

Python
------

The classes of the SDK, with which a program is described in Python
(see the :ref:`implem_python` Section), and those that the nodes of a
resident program derive from (see the :ref:`resident` Section).

.. toctree::

   api_sdk

   api_resident_nodes

The saved program
-----------------

The topology file in which the web interface and the SDK save a
program, and from which its module is built.

.. toctree::

   api_program_yaml
