.. _implem:

Writing Programs by Hand
========================

The web interface writes the module of a program from a drawing, and
the chapters before this one never require writing one. A program can
also be written without the editor, in two ways. As a Bash module, the
file that the engine runs as it is: processes as Bash functions with
their options, and a program function that adds them. Or described in
Python with the SDK, as processes with their options and a program that
adds them, which a tool turns into the same program metadata and the
same module that the editor saves, so that the program opens in the
editor and runs with the same tools. The first way needs no Python; the
second keeps Bash to the code of the processes written in it and to the
pieces that the editor takes in Bash, the tasks of an array or a
generator and the additional methods of a process.

.. toctree::
   :maxdepth: 2

   implem_bash

   implem_python
