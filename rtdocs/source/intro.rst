Introduction
============

DeBasher generalizes the shell pipeline: from a line of programs joined
by ``|`` to a graph of programs, in any language, joined by named
options that carry a value, a file or a pipe. The graph runs on one
machine or on a cluster, and its programs may be long-lived, with state
that survives a crash. The pipe is a primitive of Unix; the pipeline,
which composes programs in one line, is how the shell uses it, and the
shell in the name of DeBasher is the shell of the pipeline.

DeBasher is a workflow system whose processes are Unix programs,
written in Bash, Python, R, Perl or Groovy. The way the options of the
processes connect defines the dependency graph that DeBasher schedules
and runs. Programs are built in a visual editor, with the help of an AI
assistant, written by hand as Bash modules, or described in Python with
the SDK.

DeBasher follows `flow-based programming
<https://en.wikipedia.org/wiki/Flow-based_programming>`_, which
combines `data flow programming
<https://en.wikipedia.org/wiki/Dataflow_programming>`_ with
`component-based software engineering
<https://en.wikipedia.org/wiki/Component-based_software_engineering>`_:
a program is a network of black box processes, each showing the rest
only its inputs and outputs, so that the program exploits the
parallelism that its data dependencies allow and its processes can be
reused elsewhere. The shell pipeline is flow-based programming in one
dimension, a line; DeBasher gives it the second, the graph. A pipeline,
a series of steps where each one waits for the data of the previous
ones, is the typical case, but not the only one: a DeBasher program may
have cycles, and processes that never end.

Flow-based programming is language agnostic by nature, and so is
DeBasher: a process is a black box with a command-line interface, so
any program that takes its inputs and leaves its outputs through
options, files or FIFOs can be one, whatever it is written in, and a
single program can mix languages (see the :ref:`implem_bash` Section).

A program is saved as a topology file, ``program.yaml``, which declares
its processes and the options that connect them, and one file per
process with its code, in its own language. These files are the program:
readable, reviewed in a diff and versioned with git, and written alike
by the web interface from a drawing (see the :ref:`webui` Section), by
the SDK from a Python description, by an AI agent or by hand. What
DeBasher runs is a Bash module built from them, since Bash is the native
glue of Unix: it strings programs together, passes the environment on,
activates a Conda environment or starts a container, and is on every
machine. A module can also be written by hand, as a few Bash functions
for each process (see the :ref:`implem` Section).

DeBasher is built to work with AI agents. Its MCP server,
``debasher_mcp``, offers an agent what the web interface offers a
person: building a program, process by process and connection by
connection, running it, following its run, and writing and running the
tests of its processes. DeBasher checks each operation as it is made,
so that a wrong connection is refused at once instead of failing in the
run. The agent and the person work on the same program: the editor
shows each change of the agent as it is saved, and the agent finds each
correction made on the canvas in its next call. For Claude Code,
``debasher_claude`` adds a plugin whose skills design a program,
implement and test its processes and review their code, in a terminal
of your own or beside the canvas; and the code editor of each process
composes a prompt with the rules of a process for any AI tool.
DeBasher itself calls no AI service: the agent runs with your own
installation and account (see the :ref:`webui` and :ref:`tools`
Sections).

DeBasher runs two types of program. A general program processes a
batch of inputs: each of its processes runs once, as soon as its
inputs are ready, and ends. A resident program processes a stream: its
processes are long-lived and keep a state of their own, exchange
messages through FIFOs, possibly in cycles, react to what is written
into the program from outside, survive the crash of any of them,
returning to the state they had, and can launch a general program for
each request they receive (see the :ref:`resident` Section). Both
types define their processes the same way.

Like similar tools, DeBasher runs processes in parallel as their data
dependencies allow, reruns only what failed or is pending, reproduces
results through Conda environments and Docker containers, runs on
clusters, and tests the processes of a program with business tests,
each process run on its own (see the :ref:`tools` Section,
``debasher_test``). It runs on Linux, on macOS and on Windows through
WSL2, and is tested on all three (see :doc:`getstart`).
Unlike most of them, it streams data between processes, combines
streaming and batch processing (in one program, processes connected
through files wait for their inputs while those connected through FIFOs
run together, and a resident program launches a batch run for each
request it receives), allows cycles, keeps processes with a state of
their own, takes input from outside while a program runs, and launches
programs from within programs.
