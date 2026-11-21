DeBasher
========

**DeBasher** generalizes the shell pipeline: from a line of programs
joined by ``|`` to a graph of programs, in any language, joined by
named options that carry a value, a file or a pipe. The graph runs on
one machine or on a cluster, and its programs may be long-lived, with
state that survives a crash.

The documentation has two parts. The first is for using DeBasher:
installing it, the concepts a program is made of, building and running
programs in the web interface or from the command line, the shapes
that programs take, resident programs, and, last, writing programs by
hand, as a Bash module or in Python with the SDK, which the web
interface does for you and which the chapters before it never require.
The second is the reference of the tools and of the API.

Contents
--------

.. toctree::
   :maxdepth: 2
   :caption: Using DeBasher

   intro

   getstart

   concepts

   webui

   exec

   design_patterns

   resident

   implem

.. toctree::
   :maxdepth: 2
   :caption: Reference

   tools

   api

   links
