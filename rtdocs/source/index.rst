DeBasher
========

**DeBasher** is a workflow system whose processes are Unix programs.
Each process is written in the language its author prefers (Bash,
Python, R, Perl or Groovy), takes its inputs and gives its outputs
through named options, and the way options connect across processes
defines the dependency graph that DeBasher schedules and runs, on one
machine or on a Slurm cluster. Programs are built in a visual editor,
with the help of an AI assistant, or written by hand as Bash modules.

DeBasher runs two kinds of program. A general program processes a
batch of inputs and ends. A resident program processes a stream:
long-lived, stateful processes exchange messages through FIFOs, in
cycles when needed, survive crashes, and can launch a general program
for each request they receive. Both kinds define their processes the
same way.

DeBasher follows `flow-based programming
<https://en.wikipedia.org/wiki/Flow-based_programming>`_ and keeps what
the shell does best: a process is a black box with a command-line
interface, so any program that takes its inputs and leaves its outputs
through options, files or FIFOs can be one.

Like similar tools, DeBasher runs processes in parallel as their data
dependencies allow, reruns only what failed or is pending, reproduces
results through Conda environments and Docker containers, and runs on
high performance clusters. Unlike most of them, it streams data
between processes, allows cycles, keeps processes with a state of
their own, takes input from outside while a program runs, and launches
programs from within programs.

The documentation has three parts. The first is for using DeBasher:
installing it, the concepts a program is made of, building and running
programs in the web interface or from the command line, the shapes
that programs take, and resident programs. The second is for writing
modules by hand, which the web interface does for you and which the
first part never requires. The third is the reference of the tools
and of the API.

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

.. toctree::
   :maxdepth: 2
   :caption: Writing Modules by Hand

   implem

.. toctree::
   :maxdepth: 2
   :caption: Reference

   tools

   api

   links
