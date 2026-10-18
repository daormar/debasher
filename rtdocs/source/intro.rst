Introduction
============

DeBasher is a workflow system whose processes are Unix programs. Each
process is written in the language its author prefers (Bash, Python,
R, Perl or Groovy), takes its inputs and gives its outputs through
named options, and the way options connect across processes defines
the dependency graph that DeBasher schedules and runs, on one machine
or on a Slurm cluster. Programs are built in a visual editor, with the
help of an AI assistant, written by hand as Bash modules, or described
in Python with the SDK.

DeBasher follows `flow-based programming
<https://en.wikipedia.org/wiki/Flow-based_programming>`_, which
combines `data flow programming
<https://en.wikipedia.org/wiki/Dataflow_programming>`_ with
`component-based software engineering
<https://en.wikipedia.org/wiki/Component-based_software_engineering>`_:
a program is a network of black box processes, each showing the rest
only its inputs and outputs, so that the program exploits the
parallelism that its data dependencies allow and its processes can be
reused elsewhere. A pipeline, a series of steps where each one waits
for the data of the previous ones, is the typical case, but not the
only one: a DeBasher program may have cycles, and processes that never
end.

Flow-based programming is language agnostic by nature, and so is
DeBasher: a process is a black box with a command-line interface, so
any program that takes its inputs and leaves its outputs through
options, files or FIFOs can be one, whatever it is written in, and a
single program can mix languages (see the :ref:`implem_bash` Section).

A program is saved as a topology file, ``program.yaml``, which declares
its processes and the options that connect them, and one file per
process with its code, in its own language. These files are the
program: readable, reviewed in a diff and versioned with git, and
written alike by the web interface from a drawing (see the
:ref:`webui` Section), by the SDK from a description in Python, by an
AI agent or by hand. What DeBasher runs is a Bash module built from
them, since Bash is the native glue of Unix: it strings programs
together, passes the environment on, activates a Conda environment or
starts a container, and is on every machine. A module can also be
written by hand, as a few Bash functions for each process (see the
:ref:`implem` Section).

DeBasher runs two types of program. A general program processes a
batch of inputs: each of its processes runs once, as soon as its
inputs are ready, and ends. A resident program processes a stream: its
processes are long-lived and keep a state of their own, exchange
messages through FIFOs, possibly in cycles, react to what is written
into the program from outside, survive the crash of any of them,
returning to the state they had, and can launch a general program for
each request they receive (see the :ref:`resident` Section). Both
types define their processes the same way.
