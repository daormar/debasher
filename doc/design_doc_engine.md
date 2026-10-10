---
title: Design of the engine
fontsize: 11pt
geometry: margin=2cm
numbersections: true
toc: true
toc-depth: 2
---

This document describes the design of the core of the DeBasher engine and the
guarantees it gives.

# Introduction

DeBasher is a flow-based programming extension for Bash. Flow-based programming
builds a program as a network of components that exchange data through
connections defined outside them: the order in which the components run follows
from the flow of data between them, not from an order written by hand, and
components that do not depend on each other run in parallel. In DeBasher a
component is a process, a set of Bash functions with named input and output
options; a connection is an input option that takes the value of an output
option of another process; and a program is the set of processes that a module
adds. The engine infers the dependencies between processes from their
connections, since a process that reads a file written by another waits for it.
Data can also stream between two processes through a FIFO while both run, which
lets a program hold cycles that the dependency graph never sees.

The engine is language agnostic. Bash is the language in which processes are
declared and connected, but the code of a process can be written in Python, R,
Perl or Groovy, embedded in the module or kept in a file of its own, or be any
program that a Bash function runs. A process receives a list of options and
produces files, values or data written into a FIFO, and nothing in that
contract depends on the language of its code.

Nor does it depend on the number of tasks of the process. A process is like a
Unix command: its function receives a list of options, and its implementation is
the same whether the process runs one task or many. What changes between one
task and many is the wiring, the `_define_opts` method or the option generator
of the process, which gives each task its own options (see "Arrays and option
generators"). A task may get its task index as an option when the index is data
of its work, such as which part of an input it takes, never to choose where it
writes or to keep clear of the other tasks: that is the wiring's, through a task
subdirectory or an output option of its own. The engine aims to hold to this
principle by treating every run resource of a task alike, whatever the number of
tasks of its process; "Run resources and their life cycle" lists the run
resources, and says which one the tasks of an array share, the process output
directory, and how task subdirectories divide it between the tasks.

Given a program file and an output directory, `debasher_exec` loads the
modules, builds the options of every task, infers the dependency graph and
hands the processes to a scheduler, the built-in one on the local machine or
Slurm on a cluster. This document describes the parts of that design that
carry an invariant: how a module becomes a program, how options connect
processes and define the graph, how FIFOs are declared and kept consistent,
how processes are scheduled and run, and what a run leaves in its output
directory.

**Scope: the core, for general programs.** The engine runs two types of
program, general and resident (see the Glossary), and this document covers
general programs only. Resident programs are described in
`doc/design_doc_resident.md`, and the web UI, which builds and runs programs
from a browser, in its own design document (`doc/design_doc_webui.md`). Both
rest on the terms defined here and use them with the same meaning. Where the
engine treats a resident program differently in a mechanism described here,
the text says so in one sentence and refers to that document. The user manual,
under `rtdocs/`, explains how to write a module and run a program; this
document does not repeat it, and gives an example only where one shows a
design point.

The document is organized as follows. The Glossary defines the terms it uses.
"Architecture" follows a program from its module to its running processes, and
says what lives in memory and what on disk. "Modules and programs" describes how
modules load, what a process is made of, how a program is composed and how a
task runs steps of its own. "Options" describes how a task gets its options and
how options connect processes, and "The dependency graph" how the engine derives
the order of the processes from them. "FIFOs" describes streaming between
processes. "Scheduling" presents the scheduler abstraction and its two
implementations, and "Running a process" what happens from the launch of a
process to the end of its tasks. "The state of a run" describes the output
directory, the life cycle of the run resources, the status of a process, reruns
and the tools that read a run. "Business tests of a program" describes how the
processes of a program are tested one at a time, outside any run. "Guarantees
and non-goals" gathers the guarantees stated along the way, and "Future work"
lists what is known to be missing.

# Glossary

The precise meaning of the words this document uses, grouped by topic.
Identifiers in backticks are names that exist in the code. A path written
without a leading directory, such as `__exec__` or `program.procspec`, is
relative to the output directory of the run.

## Modules and processes

- **flow-based programming**: building a program as a network of components that
  exchange data through connections defined outside them, so that the flow of
  data decides the order in which they run.
- **module**: a Bash file that defines processes and module methods, loaded with
  `load_debasher_module`. A module that several others load is loaded only once.
- **module search path**: where a module given by a relative name is looked for:
  the current directory, then each directory of `DEBASHER_MOD_DIR`, then the
  directory where DeBasher is installed.
- **canonical path**: the absolute path of a file with every symbolic link on
  it resolved, the one name that the file has however it is reached.
- **module method**: a function `<module>_<suffix>` that the engine calls on a
  module: `_document`, `_shared_dirs`, `_program` and `_program_type`.
- **program file**: the module given to `debasher_exec` with `--pfile`, whose
  `_program` method defines the program.
- **program**: the set of processes that the `_program` method of the program
  file adds, directly or through subprograms.
- **general program**: a program whose program file declares no program type, or
  declares `general` in its `_program_type` method: its processes run to
  completion, on any scheduler. The only type of program this document covers.
- **resident program**: a program whose program file declares the type
  `resident`: long-lived, stateful processes joined by FIFOs, described in
  `doc/design_doc_resident.md`.
- **subprogram**: the processes that the `_program` method of another module
  adds to the program, called through `add_debasher_program`.
- **process**: a named unit of work of a program, a set of functions that share
  its name as a prefix, added to the program with `add_debasher_process`.
- **qualified name**: a process name with dot-separated qualifiers
  (`org.namespace.name`), which keeps apart the processes of different modules.
- **process method**: a function `<process>_<suffix>` that the engine calls at a
  given moment, such as `_define_opts`, `_explain_cmdline_opts`, `_skip`,
  `_post` or `_reset_outfiles` (see "Processes and their methods").
- **process function**: the method with no suffix, named as the process itself,
  which does the work of each task, or of a step for a sequential process.
- **heredoc process**: a process whose code is in Python, R, Perl or Groovy,
  given in a `_heredoc_py`, `_heredoc_r`, `_heredoc_perl` or `_heredoc_groovy`
  method and run by the interpreter of that language.
- **alias**: a process that runs, under its own name and options, the code of
  another process (the `alias` additional specification) or of an external
  script (`ext_alias`).
- **process specification**: what `add_debasher_process` records about a
  process, or `add_debasher_seq_process` about a sequential process: its
  computational specifications and its additional specifications.
- **computational specification**: a resource that a process asks for: `cpus`,
  `mem` and `time`, always given, and `nodes`, `account`, `partition` and
  `throttle`.
- **additional specification**: an attribute that changes how the engine treats
  a process: `processdeps`, `force`, `alias`, `ext_alias` and `alias_opt_map`.
- **step**: an execution of a function or a command from inside a task, with
  `seq_execute` or `seq_execute_slurm`, which waits for it to end.
- **sequential process**: a function with a name and a process
  specification, added with `add_debasher_seq_process`, that the engine never
  schedules: it runs only as a step. It is not a process of the program.
- **step marker**: an empty file `DEBASHER_STEP_DONE_<id>`, named after an id
  that the process chooses for a step, that the process creates with
  `mark_step_done` once the step succeeds, so that a later run can skip it.

## Options and tasks

- **option**: a word of the form `-name` or `--name` given to a task, followed
  by its value unless it is a flag.
- **flag**: an option with no value, which the engine tells apart from an option
  whose value is empty.
- **output option**: an option whose name starts with `-out` or `--out`: its
  value names something that the task produces.
- **input option**: an option that is not an output option.
- **option list**: the options of one task, which the `_define_opts` method of
  its process builds and registers with `save_opt_list`.
- **task**: one execution of the process function with one option list.
- **array process**: a process with more than one task. Each task has a **task
  index**, from 0.
- **option generator**: a process whose `_generate_opts_size` method gives its
  number of tasks and whose `_generate_opts` method builds the option list of
  one task whenever the engine asks for it, instead of registering every option
  list in advance.
- **command line option**: an option whose value a process takes from the
  command line of `debasher_exec`, which the process marks as one in its
  `_identify_cmdline_opts` method, or declares in the older
  `_explain_cmdline_opts` method.
- **task shaping option**: a value given on the command line of `debasher_exec`
  that only the `_define_opts`, `_generate_opts_size` or `_generate_opts`
  method of a process reads, to decide how many tasks it has and what each one
  gets, and that no task of that process receives. The process declares it in
  its `_explain_task_shaping_opts` method, and the engine lists and checks it
  like a mandatory command line option.
- **connection**: an input option defined with `define_opt_from_proc_out` or
  `define_opt_from_proc_task_out`, which takes the value of an output option of
  another process.
- **output descriptor**: the placeholder that a connection holds when it is
  defined, replaced by the value of the connected output option when the option
  list of the task is loaded.
- **value descriptor**: a file in the process output directory, named by an
  output option, one for each task, into which a task writes a value with
  `write_value_to_desc`, so that a connected task reads the value rather than
  the path.
- **shared directory**: a directory that a module declares in its `_shared_dirs`
  method, created in the output directory before any process runs, whose
  absolute path every process gets with `get_absolute_shdirname`.
- **shared subdirectory**: a directory below a shared directory that an option
  asks for, with `define_opt_from_shared_dir --subdir`, which the engine
  creates, when missing, before any process runs (see "Shared
  subdirectories").
- **subdivided shared directory**: a shared directory for which some option of
  the run asks for a shared subdirectory. The engine owns its contents, and
  removes from it, before any process runs, every entry that is neither a
  shared subdirectory of the run, nor a path that an output option of the run
  names, nor a directory on the way to one of them, and never looks inside a
  shared subdirectory of the run.
- **subpath**: the path of a shared subdirectory or of a task subdirectory
  relative to its shared directory or process output directory, such as `3` or
  `sample1/bam`. A directory on the way to a path is a directory below the
  shared directory or the process output directory that the path passes through,
  such as `sample1` for `sample1/bam`.
- **fanout family**: an option name ending in `-ith` in the `_explain_opts`
  method of a process, such as `-outf-ith`, which stands for the numbered
  options `-outf0`, `-outf1`, ... that its tasks define. A name that ends in
  `ith` without the dash, such as `-with`, is an ordinary option.

## Dependencies

- **dependency**: a condition on another process, the **producer**, that the
  tasks of a process wait for before they are launched.
- **dependency type**: what a dependency waits for: `none`, nothing; `after`,
  the producer has started; `afterok`, every task of the producer has succeeded;
  `afternotok`, the producer has failed; `afterany`, the producer has ended,
  whatever its result; `aftercorr`, the task of the producer with the same task
  index has succeeded.
- **inferred dependency**: a dependency that the engine derives from an input
  option whose value is an absolute path that an output option of another
  process holds: `afterok`, or `aftercorr` between two array processes at the
  same task index, and `none` when the path is a FIFO.
- **dependency merge**: combining two dependency types on the same producer into
  the weakest type that asks for everything both of them ask for, or failing
  when no run of the producer can satisfy both.
- **option dependency method**: the process method `_define_opt_deps`, which
  gives the dependency type of one option on one producer in place of the
  inferred one.
- **explicit dependencies**: the `processdeps` additional specification, which
  replaces every inferred dependency of the process.
- **dependency graph**: the processes as vertices and every dependency whose
  type is not `none` as an edge from the producer. It has to be acyclic.
- **topological order**: an order of the processes in which every process comes
  after the producers it depends on.
- **process graph**: the processes joined by all their connections, FIFOs
  included, which `debasher_exec` draws only when asked to (`--gen-proc-graph`).

## FIFOs

- **FIFO**: a named pipe, `__fifos__/<owner process>/<name>`, through which one
  task streams data to another while both run.
- **FIFO owner**: the task that defines the FIFO with `define_fifo_opt`, through
  the output option it writes, except for a FIFO fed from outside the program,
  which its owner reads. The engine creates the FIFO before its owner runs.
- **FIFO reader**: the task of the program that reads the FIFO through an input
  option other than the one through which its owner defines it. A FIFO has at
  most one (`DEBASHER_FIFO_READERS`).
- **external end**: the end of a FIFO that no task of the program holds: a
  reader outside when the owner writes the FIFO, a writer outside when the owner
  reads it (`DEBASHER_EXTERNAL_FIFO_END`).
- **cycle through FIFOs**: processes that stream to one another in a loop, which
  the engine allows because a FIFO adds no edge to the dependency graph.
- **mirror tap**: for a FIFO defined with `--mirror`, the helper that copies
  every line the owner writes both into the FIFO and into a mirror log.
- **shim FIFO**: the FIFO that the owner of a mirrored FIFO actually writes, and
  that its mirror tap reads, under `__fifos__/.mirror`.
- **mirror log**: the file where the mirror tap keeps a copy of every line,
  which can be read without taking any line from the reader.

## Runs

- **run**: one invocation of `debasher_exec` on an output directory, which
  launches the processes that are not finished or are marked to rerun.
- **output directory**: the directory given to `debasher_exec` with `--outdir`,
  made absolute, which holds everything a run writes. Once the processes are
  launched it is the only source of truth about the run.
- **lock**: the `lock` file of the output directory, which `debasher_exec` holds
  while it prepares and launches a run, so that two of them never do so on the
  same output directory at once.
- **process output directory**: the directory of a process under the output
  directory, named after the process unless its `_outdir_basename` method gives
  another name. Before each task runs, the `_reset_outfiles` method of the
  process resets it; without that method, the directory of a process with a
  single task is emptied, and that of an array process, which its tasks share,
  is left as it is.
- **task subdirectory**: a directory below the process output directory that
  an option of a task asks for, with `define_opt_from_process_outdir --subdir`,
  which the engine creates when the process is prepared and empties before the
  task runs, as it does with the process output directory of a process with a
  single task (see "Task subdirectories").
- **subdivided process output directory**: a process output directory for
  which some task of the run asks for a task subdirectory. When its process is
  prepared, and it has no `_reset_outfiles` method, the engine removes from it
  every entry that is neither a task subdirectory of the run, nor a path that
  an output option of the run names, nor a directory on the way to one of
  them.
- **exec directory**: `__exec__/<process>`, where the engine keeps the process
  script, the logs, the ids and the completion markers of a process.
- **run resource**: a directory or a FIFO that the engine creates for a task or
  hands to it, or a file of a task whose name the engine gives, such as a value
  descriptor or a step marker, with an owner and a life cycle: when it is
  created, when it is emptied and when it is removed (see "Run resources and
  their life cycle"). It is not a computational specification, which the
  document also calls a resource.
- **process script**: the self-contained Bash script that the engine writes for
  a process in its exec directory, and that the scheduler runs for each of its
  tasks.
- **execution context**: `.exec_context.sh`, the variables and functions of the
  shell of `debasher_exec` once the program is defined, with which every process
  script starts.
- **command line file**: `command_line.sh`, the command line of the run, with
  the program file resolved and the scheduler recorded, from which the tools
  reload the program.
- **final process specification**: `program.procspec`, the process
  specifications with their dependencies filled in. The tools take the set of
  processes of a run from it.
- **validation**: `debasher_exec --validate`, which does everything that a run
  does before it launches anything, and launches nothing: it loads the program,
  builds and checks the options of every process, orders the processes and
  writes the final process specification, and, with the built-in scheduler,
  checks the CPUs and memory of every process against the budget of the
  scheduler. A program that passes it is not refused for its options or for what
  a single process asks for; a first round of the built-in scheduler that can
  choose no task, or, with `--builtinsched-oneshot`, that cannot launch every
  process at once, is still refused when the run starts. The validation leaves
  the process options of the output directory as they were, and the contents of
  its shared directories too: it creates no shared subdirectory and removes
  nothing (see "Shared subdirectories"). It never prepares a process either, so
  it creates no task subdirectory, removes nothing from a process output
  directory, and does not find a task subdirectory whose subpath goes through a
  symbolic link (see "Task subdirectories").
- **scheduler**: what launches the tasks of a process once its dependencies
  hold: the built-in scheduler or the Slurm scheduler.
- **built-in scheduler**: the scheduler that runs tasks on the local machine
  within a budget of CPUs and memory, choosing which ones to launch as a
  knapsack problem.
- **Slurm scheduler**: the scheduler that submits each process to Slurm as a
  job, or as a job array for an array process, with its dependencies mapped to
  those of Slurm.
- **attempt**: one submission of a process to Slurm. A comma-separated list of
  `mem` or `time` values gives each attempt a value of its own.
- **completion marker**: the `.finished` file that a task writes in the exec
  directory when it ends successfully, or when the `_skip` method of its process
  skips it.
- **process status**: the state of a process that the engine derives from its
  exec directory: `TO-DO`, no process script yet; `IN-PROGRESS`, the scheduler
  still holds one of its ids; `FINISHED`, every task has a completion marker;
  `UNFINISHED_BUT_RUNNABLE`, for the built-in scheduler only, an array process
  with tasks still to launch and none running; `UNFINISHED`, any other case.
- **rerun mark**: the decision to run a process again although it has run
  before, for a reason (forced, changed input, outdated code, the other end of
  one of its FIFOs runs again), propagated to the processes that depend on it
  and to the other ends of its FIFOs.

## Business tests

Terms of resident programs used in this group and in "Business tests of a
program" (node, packet, node state, envelope) have the meaning that
`doc/design_doc_resident.md` gives them.

- **business test**: a test of the business logic of one process: what the
  process does with the values of its options, run on its own, outside any run.
- **program directory**: a directory, of any name, that holds a program and
  its tests: the program file is `<name>.sh` at its top, where `<name>` is the
  name of the program that the program metadata of the web UI gives, or,
  without that metadata, the only `*.sh` file at its top. The home directory of
  a program of the web UI is one (see `doc/design_doc_webui.md`). Only a
  program in a program directory has business tests.
- **test directory**: `test` inside a program directory, which holds the test
  files of the program and the data that they read.
- **process test**: a test, written in a bats file `*.bats` of the test
  directory, that runs a process of the program through
  `debasher_exec_process`.
- **node test**: a test, written in a pytest file `test_*.py` of the test
  directory, of the business logic of a node of a resident program: what it
  sends for what it receives, and what its node state brings back.
- **node harness**: `debasher_runtime_testing`, the module of the runtime
  library of resident programs with which a node test builds a node without
  the engine (see "Testing a node without the engine" in
  `doc/design_doc_resident.md`).
- **test helpers**: `debasher_bats_helpers`, the Bash library that a process
  test loads, which defines `debasher_process`.
- **test runner**: `debasher_test`, which runs the tests of a program
  directory.

# Architecture

The engine is a set of Bash libraries and the command line tools built on
them. One tool, `debasher_exec`, turns a program file into running processes;
the other tools read a run, or act on it, through the files that
`debasher_exec` leaves in its output directory. This section follows a run
through its stages, says where each part of its state lives, and explains why,
once its processes are launched, the output directory is the only place where
the state of a run can be read. A resident program goes through the same
stages, with checks of its own and always on the built-in scheduler, as
`doc/design_doc_resident.md` describes.

**From a module to its running processes.** `debasher_exec` prepares a run in
a single shell, one stage after another, and stops at the first stage that
fails, before any process is launched:

1. It resolves the program file along the module search path, makes the
   output directory absolute, creating it if needed, and takes its lock. It
   refuses an output directory whose previous run was prepared in another
   directory (see "The output directory").
2. It decides the scheduler, once for the whole run (see "The scheduler
   abstraction").
3. It loads the program file, which loads the modules it builds on, and runs
   the `_program` method of the program file, which records the process
   specification of every process of the program (see "Modules and
   programs").
4. It refuses to go on while a process of the program is still in progress
   from a previous run on the same output directory.
5. It builds the option list of every task, first through the `_define_opts`
   method of each process without an option generator, then through the
   option generator of each of the others (see "Arrays and option
   generators"), and resolves the output descriptors of the connections. It
   writes the option list of every task of a process without an option
   generator into `.sched_opts`, and registers the owner and the reader of
   every FIFO (see "Options" and "Declaring and owning a FIFO").
6. It infers the dependencies of every process, writes the final process
   specification into `program.procspec` and sorts the processes in
   topological order, which fails if the dependency graph has a cycle (see
   "The dependency graph").
7. It creates the shared directories and the shared subdirectories. When the run
   has a subdivided shared directory, it checks that no process that has left
   the program is still running, and removes from each subdivided shared
   directory every entry that is neither a shared subdirectory of the run, nor a
   path that an output option of the run names, nor a directory on the way to
   one of them (see "Shared subdirectories"). When asked to, it then creates the
   Conda environments and the Docker images of the processes (see "Conda and
   Docker environments").
8. It marks the processes to rerun (see "Reruns").
9. It writes the command line file and the execution context.
10. It hands the processes to the scheduler. Before a process is launched, its
    exec directory is prepared, its FIFOs and its task subdirectories are
    created, and, when its process output directory is subdivided, what no
    option asks for is removed from it; when it is launched, its process script
    is written, and the scheduler runs the script for each task of the process
    once the dependencies of the task hold (see "Scheduling" and "Running a
    process").

The diagram below shows the files that each stage leaves in the output
directory, and what the process script of a process takes from them.

```
debasher_exec, one shell                output directory
--------------------------------        ---------------------------------
load the modules, run _program
build the option lists           --->   .sched_opts/, program.opts
register the FIFOs               --->   program.fifos
infer dependencies, sort         --->   program.procspec, __graphs__/
save command line and context    --->   command_line.sh, .exec_context.sh
hand processes to the scheduler  --->   __exec__/<process>/, __fifos__/

process script, one per process, run for each of its tasks
--------------------------------
starts with the context          <---   .exec_context.sh, copied in
reads its option list            <---   .sched_opts/
runs the process function        --->   process output directory,
                                        completion marker
```

**What lives in memory and what on disk.** The program as a whole, its
processes, the option lists of their tasks, the owners and readers of its
FIFOs and its dependency graph, exists as Bash variables in the shell of
`debasher_exec`, and only while that shell prepares and launches the run. No
task computes it again, and no task loads a module. What the tasks need of it
is written into the output directory before the first process is launched:

- The execution context holds every function that the modules define, those
  of the engine included, and the variables of the shell, among them the
  registries of the engine, with the option lists left out. The process
  script of each process starts with a copy of it, so a task runs the code of
  the modules as it was when the run was prepared, and editing a module
  afterwards changes nothing in the run. An external script, which an alias
  runs from its file, is the one exception (see "Processes in other
  languages, and aliases").
- The option list of each task of a process without an option generator is a
  line of `.sched_opts/sched_opts_<process>`, with its connections already
  resolved, which the task reads when it starts. A process with an option
  generator has no such file: its task calls the generator, which the context
  carries, and resolves its connections then. A generator is therefore
  called more than once for the same task, while the run is prepared and when
  the task runs, and has to give the same option list every time (see "Arrays
  and option generators").
- The final process specification, a summary of the options of every
  process (`program.opts`), the owner and reader of every FIFO
  (`program.fifos`) and the command line file describe the run to the tools
  that read it later.

What changes while the program runs is written to disk too, by the scheduler
and the tasks: the ids of the launched tasks, their logs and their completion
markers, all in the exec directory of each process. The status of a process
is derived from them whenever it is asked for, with no other record to consult
(see "Process status").

**The output directory as the source of truth.** Once a process is launched,
it belongs to the scheduler, not to `debasher_exec`. With the Slurm scheduler,
`debasher_exec` ends once every process is submitted, unless it is asked to
wait (`--wait`). With the built-in scheduler, `debasher_exec` is itself the
scheduler: it stays in a loop, launching every task whose dependencies hold,
until no task is left to launch or still running, or, with
`--builtinsched-oneshot`, launches everything it can at once and ends. Either
way, a launched task runs in a process of its own, which does not need
`debasher_exec` to stay alive. If the built-in scheduler ends before the
program does, because `debasher_exec` is stopped or runs with
`--builtinsched-oneshot`, the tasks already launched go on, and those not
launched yet wait for a new `debasher_exec` on the same output directory. That
one refuses to start while any process is still in progress, and afterwards
reads from the directory what is done and launches the rest.

The tools that follow or stop a run, such as `debasher_status`,
`debasher_stop` and `debasher_stats`, therefore read it from the output
directory alone. They take the processes of the run from `program.procspec`
and its scheduler from the command line file, and the state, ids and times of
each process from its exec directory. They neither load a module nor need the
program file, so a module edited or removed after the run does not change what
they report (see "Tools that read a run"). Running the processes of a run is
different: the option lists, the process scripts and the execution context
hold absolute paths into the output directory where the run was prepared. A
moved output directory can be read anywhere, but `debasher_exec` and
`debasher_launch_process` refuse to run processes in it. They compare the
directory with the one that the command line file records by device and
inode, so that a path through a symbolic link or `..` is not taken for a
move.

# Modules and programs

A program is not written as a whole: it is assembled, while `debasher_exec`
prepares a run, from modules that define processes and from the `_program`
methods that add those processes to the program. This section describes how a
module is found and loaded, what a process is made of, how a process can run
code in another language or borrow the code of another process, how a program
is composed of subprograms, what the engine records about each process, and
how a task runs steps of its own.

## Modules and how they load

A module is a Bash file, and its name is the name of the file without the
`.sh` extension. The engine finds the methods of a module by that name: the
module `mymod.sh` has its program in `mymod_program`, its shared directories in
`mymod_shared_dirs`, and so on. A module is loaded with `load_debasher_module`,
which a module calls at its top level to load the modules it builds on, and
which `debasher_exec` calls on the program file.

**Finding a module.** An absolute path is not looked for in any directory. A
relative name is looked for in the directories of the module search path in
order, the current directory first and then each directory of `DEBASHER_MOD_DIR`
(a list separated by colons), and the first file found wins, so that a module in
the current directory is never shadowed by one of the same name elsewhere. In
each directory the engine tries the name as given and the name with `.sh`. It
then looks one level below the directory for a program saved by the web UI,
which it accepts only when the directory of the file holds a
`.debasher/program.json` whose program has the same name, so that an unrelated
file with the same name in some subdirectory is never taken for the module. A
name found nowhere is looked for, last, in the directory where DeBasher is
installed. The program file given to `debasher_exec` with `--pfile` is resolved
in the same way, and the command line file records the canonical path it
resolved to, so that the tools that later read the run do not depend on the
module search path of whoever runs them.

**Loading a module.** A module is sourced into the shell of the tool that loads
it, with the directory of the module as the current directory while it loads.
The modules it loads in turn are therefore looked for first next to it, and not
in the directory from which `debasher_exec` was run. A module is identified by
the canonical path of its file, so that a module reached through a symbolic link
(to the file or to a directory on its path) and through its real path is the
same module, and it is loaded only once: loading it again, as two modules that
build on a third one do, has no effect. A module that is asked for while it is
still loading, because modules load each other in a cycle, is refused, and the
error names the whole cycle. The engine keeps the loaded modules in the order in
which they finish loading, so that every module comes after the modules it
loads.

**What loading means for a run.** Everything that a module does at its top
level, defining functions and variables and loading other modules, happens in
the shell of `debasher_exec`, once, while the run is prepared. No task loads a
module (see "Architecture"): what the top level of a module defines reaches the
tasks through the execution context, and code at the top level that does
something else, such as printing or creating a file, runs while the run is
prepared and never in a task. Besides `debasher_exec`, only the tools that
run a process function outside a run (`debasher_exec_process`) or document a
module (`debasher_doc_mod`), the tool that resets a resident program, and the
tool that gives the node harness the code of a node (`debasher_get_node_source`,
see "Testing a node without the engine" in `doc/design_doc_resident.md`), load
modules; the tools that read a run do not.

## Processes and their methods

A process is a name and the functions that carry that name. The process
function is the function named as the process itself, and each process method
is a function named as the process followed by the suffix of the method. The
engine looks a method up by its name at the moment it needs it, and does not
register it anywhere: whether a process has a given method is whether a
function of that name exists in the shell at that moment.

A process name is one part or several joined by dots (`org.namespace.name`),
each part made of letters, digits and underscores and not starting with a
digit. The dots let modules written independently give their processes
qualified names that do not clash, since every process of a program shares a
single set of names (see "Programs and subprograms"). A name may not end with
the suffix of a process method, since the function of the process `a_skip`
would then be the skip method of a process `a`, and it may not contain the
marker `__NSSEP__`, which the engine uses to turn a qualified name into the
name of a Bash variable. A process can be added to a program only once, and a
program has at most 5000 processes.

The methods of a process, when the engine calls each one, and what happens
when a process does not define it:

| Method | Called | When absent |
|---|---|---|
| process function | by the task, with its options as arguments | the process cannot be added, unless it is a heredoc process or an alias |
| `_define_opts` | while the run is prepared, to build the option list of every task | the process needs an option generator |
| `_generate_opts_size`, `_generate_opts` | while the run is prepared, and by the task to build its own option list | the process uses `_define_opts` |
| `_explain_opts` | to list the options of the program (`--show-cmdline-opts`) and to check the options that a task defines | the process cannot be added, unless it has `_explain_cmdline_opts` |
| `_identify_cmdline_opts` | together with `_explain_opts`, to mark which options are command line options | the process has no command line options |
| `_explain_cmdline_opts` | an older form of the two methods above, whose options are all command line options | the two methods above are used |
| `_explain_task_shaping_opts` | together with `_explain_opts`, and before the options of the process are defined, to check that its task shaping options are given | the process has no task shaping options |
| `_define_opt_deps` | while the dependencies are inferred, for each option on each producer | the inferred dependency type is used |
| `_skip` | by the task, before the process output directory is reset, with the options of the task | the task is never skipped |
| `_reset_outfiles` | by the task, before the process function, with the options of the task | the default reset (see "Executing a task") |
| `_post` | by the task, once the process function returns, whether it succeeded or failed | nothing runs after the process function |
| `_outdir_basename` | whenever the process output directory is needed | the directory is named after the process |
| `_slurm_sigterm_handler` | by a task under the Slurm scheduler, when Slurm sends it `SIGTERM`, as when its time runs out | the task prints a message and exits with an error |
| `_conda_envs`, `_docker_imgs` | while the run is prepared, with `--conda-support` or `--docker-support` | the process needs no environment |
| `_document` | by `debasher_doc_mod`, which documents a module | the process has no description |

The methods that the task calls run inside the process script, with the code
that the execution context carries; the others run in the shell of
`debasher_exec` or of the tool that calls them. The sections that follow
describe what each method does: the option methods in "Options", the
dependency method in "The dependency graph", the task methods in "Executing a
task" and the environment methods in "Conda and Docker environments".

## Processes in other languages, and aliases

The process function is always a Bash function, but it need not contain the
code of the process. When a process is added to the program,
`add_debasher_process` builds the process function itself in two cases: for a
heredoc process, whose code is in another language, and for an alias, whose
code belongs to another process or to an external script. In both cases the
other methods of the process are still Bash functions of its own. A sequential
process gets its process function in the same way (see "Sequential
processes").

**Heredoc processes.** A heredoc process gives its code in a method named after
the language, `_heredoc_py`, `_heredoc_r`, `_heredoc_perl` or `_heredoc_groovy`,
which prints the code, usually from a quoted here-document. The older form, a
variable named after the process with the suffix `_py`, `_r`, `_perl` or
`_groovy` that holds the code, is still accepted. The process function that the
engine builds runs the interpreter of the language, found when DeBasher was
configured, with the code as its program (`-c` for Python, `-e` for the others)
and the options of the task as its arguments. For Python, the engine puts in
front of the code the lines that make its own Python library importable. The
code is printed when the task runs, from the method that the execution context
carries, so a heredoc process runs the code of the module as it was when the run
was prepared, like any Bash process. When a process has heredoc code, it is a
heredoc process, whatever other attributes it has.

**Aliases.** A process with the additional specification `alias=<process>` has
a process function that calls the process function of the named process with
the same arguments. The named process only has to have a valid name and a
process function; it need not be part of the program. An alias borrows only the
process function: its options, its dependencies and every other method are its
own, so the same code can run under two names with two sets of options. A
process with `ext_alias=<file>` runs an external script instead, with the
interpreter that the extension of the file names (`.sh`, `.py`, `.R`, `.pl` or
`.groovy`); a file with another extension is refused when the process is added.
A relative path is resolved against the directory of the module whose
`_program` method adds the process, so that a program and the scripts that ship
with it can be moved together; an absolute path is accepted with a warning that
the program is not portable. The file has to exist when the process is added,
and the process function runs it from its path, so the script is read when the
task runs: it is the one piece of the code of a run that editing a file after
the run was prepared can still change.

Both kinds of alias accept `alias_opt_map=<old>:<new>,...`, which renames
option names in the arguments before they reach the borrowed code: an argument
equal to `<old>` is passed as `<new>`, and any other is passed unchanged. The
map is checked when the process is added, each entry has to be a pair of option
names and no name may be mapped twice, and a map without an alias or an
external alias is refused.

Every process of a resident program is a Python heredoc process whose class
derives from the classes of the engine for that purpose, as
`doc/design_doc_resident.md` describes.

## Programs and subprograms

The program is defined by the `_program` method of the program file, which
`debasher_exec` calls once the program file is loaded. That method adds each
process with `add_debasher_process`, and adds the processes of other modules
with `add_debasher_program <module>`, which calls the `_program` method of that
module in the same shell. A subprogram is therefore not a separate program: its
processes join the one program being defined, with no scope of their own, and
connect to the other processes through their options like any other process.
Their names have to be unique across the whole program, which is what qualified
names are for. `add_debasher_program` takes the module from the file from
which it was loaded, and so expects the calling module to have loaded it; the
module is not searched for again from the current directory, which is no
longer the directory of the module that loaded it.

Only the processes that some `_program` method adds with `add_debasher_process`
are part of the program. A module can define processes that no program adds;
their functions are loaded, and reach the execution context, but the engine
never schedules them. Neither does it schedule the sequential processes that a
`_program` method adds with `add_debasher_seq_process`, which are not part of
the program either.

While a `_program` method runs, the engine records, for each process and each
sequential process it adds, the directory of the module that the method belongs
to. A relative path that belongs to a process, that of an external alias or the
value of an option defined with `define_infile_opt` or `define_indir_opt`, is
resolved against that directory, which is the directory of the module that
added the process to the program, not necessarily the one that defines its
functions.

The type of the program comes from the `_program_type` method of the program
file alone, called before its `_program` method; the `_program_type` method of
a module added as a subprogram is never called. Without the method, the program
is a general program.

## Process specifications

`add_debasher_process` takes the name of the process, its computational
specifications and, optionally, its additional specifications, each a list of
`<name>=<value>` pairs:

```
add_debasher_process "file_reader" "cpus=1 mem=32 time=00:01:00"
add_debasher_process "hello" "cpus=1 mem=32 time=00:01:00" "alias=hello_world"
```

The pairs of the additional specifications are separated by `;`, and so are
those of the computational specifications, which also accept the older form
separated by blanks. The engine keeps the specification of each process as a
single line, the name, the computational specifications, the separator `|||`
and the additional specifications, and reads each attribute from it when it
needs it.

The computational specifications are the resources that a process asks for.
`cpus`, `mem` (in megabytes, or with a `K`, `M`, `G` or `T` suffix) and `time`
have to be given for every process; `nodes`, `account` and `partition` matter
to the Slurm scheduler only, and `throttle` limits how many tasks of an array
process run at once. Under the Slurm scheduler, `mem` and `time` may be lists
separated by commas, one value for each attempt; the built-in scheduler takes
the first value. How each scheduler uses them is described in "Scheduling". A
process can also pass one of its specifications to its tasks as an option
(see "Defining the options of a task"). The additional specifications change
how the engine treats the process:
`processdeps` gives its explicit dependencies, `force=yes` marks it to rerun on
every run, and `alias`, `ext_alias` and `alias_opt_map` are described above.

The name, the process function and the aliases are checked when the process is
added, since an error there leaves the program without a process. The rest of
the specification is checked when the final process specification is built
(stage 6 of "Architecture"): a process without `cpus`, `mem` or `time`, and a
dependency on a process that is not part of the program, stop the preparation
of the run. The final process specification is the specification of each
process with its dependencies added as a `processdeps` attribute, the inferred
ones, or `none` when there are none, unless explicit dependencies were given.
`program.procspec` holds it, one line per process, in no particular order:

```
file_writer cpus=1 mem=32 time=00:01:00 |||  ; processdeps=none
file_reader cpus=1 mem=32 time=00:01:00 |||  ; processdeps=afterok:file_writer
```

This file is the list of the processes of the run for every tool that reads
it, and the final process specification is where each scheduler takes the
resources and the dependencies of a process from.

## Sequential processes

The dependency graph is fixed before the run starts, and some programs decide
what runs next only while they run: a loop that sends each value it reads to one
of two transformations, depending on what it has added up so far, or a process
that skips its second part when the first one produced nothing. Such a process
runs its parts itself, as steps: `seq_execute <function> <args>` runs the
function, waits for it to end and returns an error if it fails. The scheduling
code that runs a step calls a function and nothing else; the code of a step that
is written in another language, or borrowed from another process or from an
external script, is turned into a function by declaring a sequential process.

**Declaring a sequential process.** `add_debasher_seq_process` takes the same
arguments as `add_debasher_process`, the name, the computational
specifications and the additional specifications, and is called from a
`_program` method in the same way:

```
add_debasher_seq_process "transformation_b" "cpus=1 mem=64 time=00:05:00"
```

It checks the name with the rules of "Processes and their methods", and builds
the process function of a heredoc process or of an alias as "Processes in other
languages, and aliases" describes: when the module defines
`transformation_b_heredoc_py`, the function above runs its Python code. A
relative path of an external alias is resolved against the directory of the
module that adds the sequential process, as for a process (see "Programs and
subprograms"). A name is unique across the processes and the sequential
processes of the program: adding a name that `add_debasher_process` or
`add_debasher_seq_process` has already added is refused. Sequential processes do
not count towards the limit of 5000 processes of a program.

The engine records a sequential process apart from the processes of the program,
and nothing that walks the processes of the program sees it: it has no options,
no tasks, no dependencies, no exec directory and no status, and it is not in
`program.procspec`. What it leaves is its process function and its
specification, which reach the tasks through the execution context like every
function and variable of the shell of `debasher_exec` (see "The process script:
how code travels"). A step runs the process function only, and the engine calls
no other method of a sequential process, which therefore needs no
`_explain_opts` method. `debasher_doc_mod` documents the sequential processes
only when asked with `--show-seq-procs`, after the processes and each under a
heading of its own, and leaves a sequential process out of the code of a process
that runs it, which includes the other functions of its module that the process
calls.

The additional specifications `alias`, `ext_alias` and `alias_opt_map` mean what
they mean for a process. `processdeps` and `force`, which only a scheduled
process can use, are refused. Every computational specification is optional,
`cpus`, `mem` and `time` included, since the built-in scheduler uses none of
them for a step. `throttle` is refused, and so is a list of values in `mem` or
`time`, since a step runs once and has no further attempts. A resident program
cannot have sequential processes, as "Defining a node" in
`doc/design_doc_resident.md` explains. These checks run when the sequential
process is added, so an error stops the preparation of the run.

**Running a step.** `seq_execute` runs the step on the scheduler of the run.
Under the built-in scheduler it calls the function in the shell of the task,
and the computational specifications are not used. Under the Slurm scheduler
it hands the step to `seq_execute_slurm`, which a process function can also
call directly to send a step to Slurm whatever the scheduler of the run: a
program with FIFOs runs on the built-in scheduler, and can still send a heavy
step to the cluster. `seq_execute_slurm` writes a script in `__exec__`, made of
the execution context and a call to the function with its arguments, runs it
with `srun`, and removes it once it ends. When the function is a sequential
process, its computational specifications become options of `srun`, as those
of a process become options of `sbatch` (see "The Slurm scheduler"). Called
outside a Slurm job, as by a task of the built-in scheduler, `srun` gets a job
of its own with those resources. Called from a task of a Slurm job, it runs
the step as a job step of Slurm inside that job, which takes its resources
from the allocation of the job, and a step that asks for more than the job has
fails.

The function given to `seq_execute` need not be a sequential process: any
function of the execution context, or any command, can run as a step, with no
resources asked for. A sequential process is needed only when the code is not
a Bash function, or when the step asks for resources of its own.

The arguments reach the function as they are given. The engine builds no option
list for a step, so a function can take positional arguments or options, and
`alias_opt_map` renames an argument equal to one of its option names, wherever
it appears. The step reads the standard input of the call, under both
schedulers, so a step called inside a loop that reads its standard input has to
take its own from `/dev/null`: under the built-in scheduler a step that reads
its standard input consumes what the loop has still to read, and under the Slurm
scheduler `srun` consumes it whether the step reads it or not. What the step
prints to its standard output goes to the standard output of `seq_execute`, and
so to the `.stdout` file of the task unless the caller captures it; what it
prints to its standard error goes to the log of the task. `seq_execute` returns
an error when the step fails, or when `srun` cannot launch it. The engine
records nothing of a step, and the process function that called it decides what
a failure means. Under the built-in scheduler, a step that calls `exit` ends the
whole task, as a process function does (see "Executing a task").

**Recording finished steps.** When a task fails, or is stopped, halfway through
its steps, the next run runs all of them again, since the engine records nothing
of a step. A process that wants to skip the steps that an earlier run finished
records them itself, with step markers: `mark_step_done <dir> <id>` creates the
step marker of the step `<id>` in the directory `<dir>`, and
`is_step_done <dir> <id>` tells whether it exists. The marker is created
atomically, so that of two calls that mark the same step only one succeeds. The
engine never creates a step marker on its own, nor reads one: only the process
knows what makes two steps the same work, and a step that runs again on
purpose, as a transformation called on each value of a loop, must not be
skipped.
`data/programs/debasher_dynamic_fanout_stepdone.sh` shows the pattern: each task
runs one step for each file of its list, with the task index, the name of the
file and a checksum of its contents as the id.

Two conditions are left to the process. The markers have to survive the reset of
the directory that holds them: kept in the process output directory, a process
with a single task, or one whose process output directory is subdivided, needs a
`_reset_outfiles` method that leaves them in place, since the default reset
empties the directory (see "Executing a task"); kept in a task subdirectory,
which each task empties before it runs, any process needs such a method (see
"Task subdirectories"). And a marker has to stop counting when the work it
stands for changes: a run that reruns the process, for any of the reasons of
"Reruns", leaves the markers of the earlier run in place, and they would skip
steps whose inputs are new. Removing them when the process starts would skip
nothing, since a process cannot tell a rerun from a run that resumes after a
failure; the process builds the id of each step from what the step depends on
instead, such as a checksum of its input. When steps with different inputs write
the same output, the process also removes, before it runs a step, the markers
that other inputs left for that output, so that each output has at most one
marker, the one of the input it holds: otherwise an input that comes back would
find its old marker and skip a step whose output another input has since
overwritten. `data/programs/debasher_dynamic_fanout_stepdone.sh` does both.

# Options

Everything that a task knows about its inputs and its outputs reaches it as
options, and the engine learns the structure of the program from the same
options: an input option whose value another process produces makes a
dependency (see "The dependency graph"), and an option whose value is a FIFO
joins two tasks (see "FIFOs"). This section describes how the option list of a
task is built, what makes an option an output, how a task gets a directory of
its own below a shared directory or below its process output directory, how
options connect processes, how a program takes values from its command line, how
a process gets more than one task, and how the option list of a task travels
from `debasher_exec` to the task.

## Defining the options of a task

The `_define_opts` method of a process receives four arguments: the command
line of `debasher_exec`, serialized; the specification of the process; its
name; and the absolute path of its process output directory, where the process
is expected to write what it produces. The method builds an option list by
calling the `define_*` functions of the engine on a variable whose name has to
end in `optlist`, and hands the list to `save_opt_list`, which registers it as
the option list of the next task of the process:

```
file_writer_define_opts()
{
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    define_cmdline_opt "${cmdline}" "-s" optlist || return 1
    define_opt "-outf" "${process_outdir}/out.txt" optlist || return 1

    save_opt_list optlist
}
```

Each `define_*` function adds one option, and they differ in where the value
comes from: a literal (`define_opt`, `define_flag`), a file or a directory
shipped with the program (`define_infile_opt`, `define_indir_opt`), the command
line (`define_cmdline_opt` and its variants), the process specification
(`define_procspec_opt`), an output option of another process
(`define_opt_from_proc_out`), a value descriptor (`define_value_desc_opt`), a
shared directory (`define_opt_from_shared_dir`), the process output directory
(`define_opt_from_process_outdir`) or a FIFO (`define_fifo_opt`, see "Declaring
and owning a FIFO").

**Options and values.** A word of an option list is an option when it is `-` or
`--` followed by a letter or an underscore, and a value otherwise, so `-5` is a
value and `-v` is an option wherever it appears: no value can start with `-` and
a letter. An option followed by another option, or by nothing, is a flag. The
engine records a flag with a marker of its own, so that a flag and an option
given the empty string as its value stay different all the way to the task.

**One value per option.** An option list holds each option once. An option
defined twice with the same value counts once; defined twice with different
values, it is refused when the run is prepared, once the values that come from
connections are known, so that two definitions that turn out to name the same
file do not count as a conflict. A process that needs several values passes
them in a single value, or through options of different names (see "Arrays and
option generators").

**Order.** The option list of a task is kept by option name, and the engine
does not guarantee the order in which the task receives its options. A process
reads each option by its name, with `read_opt_value_from_func_args` and
`read_flag_from_func_args`, never by its position.

## Output options

An output option is an option whose name starts with `-out` or `--out`. Its
value names something that the task produces, usually a file or a directory
under its process output directory. The engine does not check that the task
produces it; what the name changes is how the engine treats the value.

**Produced values.** While the run is prepared, the engine records every
absolute path that an output option of some task holds, together with the
tasks that hold it. This table is what dependencies are inferred from: an input
option of another task whose value is one of those paths depends on the tasks
that produce it (see "Inferring dependencies from options"). An output option
whose value is not an absolute path produces nothing that another task can
depend on.

**Value descriptors.** Some processes produce a value rather than a file, such
as a count or a name that another process needs as an option. An output option
defined with `define_value_desc_opt` holds the path of a value descriptor,
`.__VAL_DESCRIPTOR__<option>_<task index>` in the process output directory, into
which the task writes the value with `write_value_to_desc`. The name carries the
task index, so that the tasks of an array process, which share the process
output directory, never share a value descriptor. A task connected to that
option receives the path, and `read_opt_value_from_func_args` gives it the
content of the file instead, since the option through which it reads it is not
an output option. The path is absolute, so the reading task depends on the
writing one like on any file it produced, and reads the value only once it has
been written.

**Input paths and shared directories.** `define_infile_opt` gives an option the
path of a file shipped with the program, resolved against the directory of the
module that added the process (see "Programs and subprograms") and required to
exist as a regular file; `define_indir_opt` does the same for a directory. A
shared directory is declared by a module, with `define_shared_dir` in its
`_shared_dirs` method and never from a process method, and created in the output
directory before any process runs. The `_shared_dirs` method of every
loaded module is called, whether or not the module adds processes to the
program. `define_opt_from_shared_dir` gives an option its absolute path, or
that of a shared subdirectory (see "Shared subdirectories"). A shared directory
is not an output of any process. Its path makes a dependency only by the rule
that holds for any path, when an output option of a task of one process and an
input option of a task of another process hold it (see "Inferring dependencies
from options"); otherwise, processes that share one coordinate through it by
other means.

## Shared subdirectories

The tasks of an array process that write into the same shared directory share
its file names: two tasks that write a file of the same name overwrite each
other. `define_opt_from_shared_dir` takes a subpath with `--subdir`, so that
each task gets a directory of its own below the shared directory:

```
define_opt_from_shared_dir "-outd" "data" optlist --subdir "${task_idx}" || return 1
```

The option gets the absolute path of the shared subdirectory,
`<output directory>/data/<subpath>`. The subpath is an ordinary argument,
computed when the options are defined, usually from the task index, or from the
element of the array that the task stands for, and it may have several
components, such as `${sample}/bam`.

**What a subpath may be.** A subpath is relative and stays below its shared
directory: it is not empty, does not start with `/`, and has no empty component
and no component `.` or `..`. Any other subpath is refused when the option is
defined, which stops the preparation of a run. A shared subdirectory is
therefore never the shared directory itself, nor anything outside it.

**Registering and creating.** Defining the option creates nothing: it adds the
path to the shared subdirectories of the run, as declaring a FIFO registers it
(see "Declaring and owning a FIFO"), since the methods that define the options
of a process also run when nothing is executed, and an option generator runs
again inside its tasks. `debasher_exec` creates every shared subdirectory of the
run that does not exist yet, right after the shared directories, before any
process is launched, whatever the status of the process that asks for it (see
"Architecture"). Every shared subdirectory thus exists before any task that
writes or reads it starts, including a task launched together with the other end
of a FIFO. Several options, of one process or of several, may ask for the same
shared subdirectory, which is created once. A shared subdirectory of a shared
directory that no module declares stops the preparation. A shared subdirectory
with a symbolic link at any component of its subpath, the last one included,
stops the preparation, so that creating it never leaves its shared directory;
the shared directory itself may be a symbolic link, to another disk for example.

**A subdivided shared directory belongs to its shared subdirectories.** A shared
directory for which some option of the run asks for a shared subdirectory is a
subdivided shared directory, and the engine owns its contents: what it holds is
the shared subdirectories of the run, the paths in it that output options of the
run name, the directories on the way to them, and nothing else. A task may read
the whole subdivided shared directory, through an option that gives its path
without `--subdir`, but writes only into its own shared subdirectory, or into a
path that one of its output options names. An output option that holds the path
of a subdivided shared directory stops the preparation, since it would name the
whole directory as something that a task produces. The engine cannot check the
rest: a task that writes into the subdivided shared directory through
`get_absolute_shdirname`, or a file that the user leaves there, breaks that
contract, and what it leaves is removed by the next run.

**Removing what no option asks for.** When the number of tasks of a process
changes, or the subpath of a task does (one taken from the name of a sample, for
example), a shared subdirectory of an earlier run that no option asks for any
more would stay, and a task that reads the whole subdivided shared directory
would take it for a current one. Right after creating the shared subdirectories
of the run, `debasher_exec` goes through every subdivided shared directory and
removes, with its contents, every entry that is neither a shared subdirectory of
the run, nor a path that an output option of the run names, nor a directory on
the way to one of them, looking inside the directories on the way too. It names
each entry that it removes on the standard error. The contents of a shared
subdirectory of the run, and of a path that an output option of the run names,
are not looked at, even when that path is also on the way to a shared
subdirectory, so nested subpaths need no rule of their own: when the run asks
for `a` and for `a/b`, everything below `a` is kept. A failure stops the
preparation before any process is launched. A validation creates no shared
subdirectory and removes nothing: it only names on the standard error the
entries that a run would remove.

Removal is bounded by these rules:

- **Only subdivided shared directories.** A shared directory for which no
  option of the run asks for a shared subdirectory is left as it is, whatever
  an earlier run created in it. A process that drops `--subdir`, or an array
  process whose number of tasks becomes zero, leaves its earlier shared
  subdirectories in place when no other option of the run asks for a shared
  subdirectory of the same shared directory.
- **Never outside a shared directory.** Removal starts from the subdivided
  shared directory, never removes it, and never follows a symbolic link: a
  link that it finds is an entry like any other, and removing it removes the
  link, not what it points to.
- **Every process counts.** The options of every process of the program are
  defined in every run, whatever its status, so a finished process that does
  not run again keeps its shared subdirectories, and a process that has left
  the program loses them.
- **No task is running.** Only one `debasher_exec` prepares a run in an output
  directory at a time, and it refuses to start while a process of the program
  is still running (see "Architecture"). A process that has left the program is
  not part of that check, so in every run with a subdivided shared directory,
  before removing anything, `debasher_exec` checks every process with an exec
  directory that the program no longer has, as for any process (see "Process
  status"), and one with a task still running stops the preparation. Removal
  thus never takes anything from under a task.

**What removal leaves.** The contents of a shared subdirectory that the run
still asks for are kept: a task that runs again finds what an earlier run left
in its own shared subdirectory, as it does in a shared directory. Clearing it is
up to the process. The engine never does, since a shared subdirectory may hold
the step markers that let a new run skip the steps that already succeeded (see
"Sequential processes").

**Dependencies.** The path of a shared subdirectory is an ordinary absolute
path, so the rule of "Inferring dependencies from options" applies to it. When
an array process writes into `--subdir "${task_idx}"` through an output option,
and another array process reads the same shared subdirectory through an input
option, each task of the reader depends on the task of the writer with the same
task index (`aftercorr`). A task that reads the whole shared directory holds
the path of the shared directory, not those of its shared subdirectories, and
gets no dependency on the tasks that write them: its process is ordered after
the writers with explicit dependencies, which replace all its inferred ones (see
"Explicit dependencies").

## Task subdirectories

The process output directory of an array process is shared by its tasks, and,
without a `_reset_outfiles` method, it is not emptied before each of them (see
"Executing a task"). A process whose function writes a file of a fixed name into
its output directory, or relies on finding it empty, would then work with one
task and not with many. `define_opt_from_process_outdir` gives an option the
path of the process output directory, and, with `--subdir`, that of a task
subdirectory below it, which the engine creates and empties as it does the
process output directory of a process with a single task:

```
define_opt_from_process_outdir "-outd" optlist --subdir "${task_idx}" || return 1
```

The function of the process gets a directory that exists and is empty when it
starts, unless its process has a `_reset_outfiles` method, whatever the number
of tasks of its process, so the same function works with one task and with many
(see "Introduction"). A subpath follows the same rules as that of a shared
subdirectory (see "Shared subdirectories"). A task may ask for several task
subdirectories. Two tasks may not ask for the same one, and no task subdirectory
may be below another one of the same process, of the same task or of another,
since each one is emptied on its own: each of the two stops the preparation once
the options of every task are known, as for shared subdirectories, so that a
validation finds it too.

**Registering.** Defining the option creates nothing: it records the task
subdirectory under the task whose options are being defined (see "Arrays and
option generators"). The record belongs to the shell of `debasher_exec` once the
options of every task are defined, so the execution context carries it to every
task, which finds its own task subdirectories there, whether its process has an
option generator or not (see "Architecture").

**Creating.** When a process is prepared (see "Preparing a run"), the engine
creates every task subdirectory of its tasks that does not exist yet, with any
missing directory above it, the process output directory included. A task that
the `_skip` method of its process skips thus finds its task subdirectory as
preparation left it, just as a skipped task of a process with a single task
finds its process output directory. A task subdirectory whose subpath has a
symbolic link at any of its components stops the run. Every process that the run
launches is prepared before any of them is launched, so such a failure, or one
to create a task subdirectory or to remove from a subdivided process output
directory, stops the run before any process is launched (see "Preparing a run").

**Emptying.** Before each task that is not skipped, in the step that resets the
process output directory (see "Executing a task"), the task removes each of its
task subdirectories with everything in it, and creates it again. A
`_reset_outfiles` method replaces this, as it replaces the default reset, and a
task of a resident program never empties them.

**A subdivided process output directory.** A process output directory for which
some task asks for a task subdirectory is a subdivided process output directory,
and holds the task subdirectories of the run, the paths in it that output
options of the run name, such as value descriptors, the directories on the way
to them, and nothing else. A task of its process writes only into its own task
subdirectories, or into a path that one of its output options names. When such a
process is prepared, and it has no `_reset_outfiles` method, the engine removes
from its process output directory every other entry, as it removes from a
subdivided shared directory, and within the same bounds (see "Shared
subdirectories"). The task subdirectories of the tasks that the process no
longer has are removed, while those of the finished tasks of an array that runs
again in part are kept, since their options still ask for them; what a finished
task wrote elsewhere in the directory, breaking that contract, is removed even
though the task does not run again. An output option that holds the path of a
subdivided process output directory stops the preparation once the options of
every task are known, since it would name the whole directory as something that
a task produces.

**Dependencies.** The path of a task subdirectory is an ordinary absolute path,
so the rule of "Inferring dependencies from options" applies to it, as to the
path of a shared subdirectory. An array process that reads, through an input
option, the task subdirectory that the task with the same task index of another
array process writes through an output option depends on that process with
`aftercorr`.

## Connections between processes

`define_opt_from_proc_out <option> <process> <output option>` defines an input
option that takes the value of an output option of the first task of another
process, and `define_opt_from_proc_task_out` does the same for a task of a
given index. The option being defined may not be an output option, and the
connected one has to be.

The option does not get its value when it is defined, since the other process
may not have defined its options yet: the processes define their options in no
particular order, except that those with an option generator come after the
others (see "Arrays and option generators"). It holds an output descriptor
instead, a placeholder that names the process, the task and the option. Once
every process has defined its options, the engine replaces each output
descriptor with the value of the connected option, taken from the option list of
that task, or by calling the option generator of the connected process for that
task. A connection to a process, task or option that does not exist resolves to
nothing and stops the preparation of the run.

Once resolved, the value of a connection is a value like any other. The engine
does not remember that it came from a connection: the dependency it creates is
inferred from the value (an absolute path produced by the connected task makes
a dependency, and a FIFO makes the task its reader), and an input option given
the same path literally depends on the producer in the same way. A connection
is the way to write that one task reads what another produces without
repeating how the path is built.

## Command line options

The command line of `debasher_exec` carries the options of the program along
with those of `debasher_exec` itself, which ignores the options it does not
know. A process takes a value from it in its `_define_opts` method:
`define_cmdline_opt` requires the option to be given with a value and stops the
preparation of the run otherwise; `define_cmdline_opt_if_given` and
`define_cmdline_flag_if_given` add the option only when it is given;
`define_cmdline_infile_opt` and its `_if_given` variant also require the value
to name an existing regular file and make its path absolute, and
`define_cmdline_indir_opt` and its `_if_given` variant do the same for an
existing directory; and `get_cmdline_opt` returns the value for the method to
compute with.

The command line is a single set of names shared by every process of the
program and by `debasher_exec`: every process that reads `-s` gets the same
value, which is how two processes share a parameter, and a program option with
the name of an option of `debasher_exec` reads the value given to
`debasher_exec`.

A process declares its options in its `_explain_opts` method, with `explain_opt`
and `explain_flag`, and marks which of them are command line options in its
`_identify_cmdline_opts` method, with `opt_is_cmdline` for a mandatory one and
`opt_is_non_mandatory_cmdline` for an optional one. The older
`_explain_cmdline_opts` method declares command line options, all of them
mandatory, with `explain_cmdline_opt`. Every process has one of the two methods,
even a process with no options, and `add_debasher_process` refuses a process
without them: besides declaring the options, the method is what tells a process
apart from any other function of a module, for the tools that list the processes
of a module without running its `_program` method. The declarations document the
program: `debasher_exec --show-cmdline-opts` lists the command line options of
every process, by category, and `debasher_doc_mod` documents them. Whether a
mandatory option is given is decided by `define_cmdline_opt` when the options
are built, not by the declaration; a task shaping option is the exception (see
below).

**Task shaping options.** A value given on the command line can serve only to
decide the tasks of a process: its `_define_opts` method, or its
`_generate_opts_size` and `_generate_opts` methods, read it to know how many
tasks to define and what each one gets, and no task receives it. The `worker`
process of `data/programs/debasher_dynamic_fanout.sh` reads `-w`, the number of
workers, to define one task per worker. `_explain_opts` declares what a task
receives, which `debasher_exec_process` shows as the options to give to the
process function, so a task shaping option is declared apart, in the
`_explain_task_shaping_opts` method, with `explain_task_shaping_opt`:

```
worker_explain_task_shaping_opts()
{
    local description="Number of workers."
    explain_task_shaping_opt "-w" "<int>" "$description"
}
```

A task shaping option is always given on the command line, since a value that a
method reads while the options are defined comes either from the command line
or from the module itself (a constant, the process specification), and the
latter needs no declaration. It is also always mandatory: its value fixes the
tasks of the process and, through connections by task index, how they meet the
tasks of other processes, so two processes that read the same option with
different defaults of their own would disagree on that structure. It is
therefore not marked in `_identify_cmdline_opts`. Whether it is given is
decided before the options of the process are defined, and a missing one stops
the preparation of the run: the methods that read it never define it, so
nothing else would stop a run that lacks it. `--show-cmdline-opts` lists it
among the command line options, marked as a task shaping option, and
`debasher_doc_mod` and `debasher_exec_process` show it in a section of its
own. An option that shapes the option lists of the tasks and that the process
function also reads, like `-w` in the `dispatch` process of the same module,
which sets how many `-outf<i>` options its task gets, is declared in
`_explain_opts` like any other.

## Arrays and option generators

**Arrays.** A `_define_opts` method that calls `save_opt_list` several times
defines one task per call, in order: the process is an array process, and each
option list is that of the task with the next task index. Every option list is
built while the run is prepared and kept until the options are written for the
tasks.

**The task being defined.** While the options of a task are defined, the engine
knows its task index: the number of option lists that `_define_opts` has
registered so far, or the index with which the engine calls the option
generator, which it keeps while the generator runs, at every place where it
calls it. The `define_*` functions that name something after the task or record
it under the task, `define_fifo_opt`, `define_value_desc_opt` and
`define_opt_from_process_outdir`, take it from there, so `_define_opts` and the
option generator never pass it to them, and each of them works the same in both.

**Option generators.** A process with an option generator does not build its
option lists in advance. Its `_generate_opts_size` method, called with the same
arguments as `_define_opts`, prints the number of tasks, and its
`_generate_opts` method, called with those arguments and a task index, builds
the option list of that one task and hands it to `save_opt_list`, which returns
it instead of registering it. A `_generate_opts_size` method that fails, or that
prints anything but a number, stops the preparation of the run. The engine calls
the generator whenever it needs the options of a task: while the run is
prepared, to record the values that the task produces, to find its FIFOs, to
infer its dependencies and to resolve the connections of other processes to it,
and again inside the task itself (see "How option values reach a task"). A
generator is therefore called several times for each task, in different shells,
and has to give the same option list every time for the same command line and
task index. The engine does not check it: a file or a directory that the
generator reads, such as one named by a task shaping option, has to stay
unchanged while the run lasts, and a process whose option lists have to be fixed
when the run is prepared builds them in `_define_opts`, which runs, in a run,
only while the run is prepared. A generator declares a FIFO with
`define_fifo_opt`, as `_define_opts` does (see "Declaring and owning a FIFO").

**The number of tasks of another process.** A process whose tasks match, one by
one, those of another process, or whose task reads every task of another
process, needs the number of tasks of that process. Computing it again would
repeat the rule by which the other process computes it, such as counting the
entries of a file given on the command line, and two copies of a rule can drift
apart. `get_process_num_tasks` prints it instead, from the `_define_opts`,
`_generate_opts_size` or `_generate_opts` method that calls it. The processes
without an option generator define their options first, and those with one
afterwards, each group in no particular order, so that the answer depends on
which of the two processes have an option generator, and never on the order in
which they happen to be defined:

- The number of tasks of a process with an option generator is known at any
  time. Once its options are defined, the engine has recorded it; before that,
  its `_generate_opts_size` method gives it, once the engine has checked that
  the task shaping options of that process are given.
- The number of tasks of a process without an option generator is known only
  once its `_define_opts` method has run. A process with an option generator can
  ask for it, and a process without one cannot, even when the process it asks
  about happens to be defined already. The rule holds along the whole chain:
  while a process without an option generator defines its options, nothing that
  it asks, the `_generate_opts_size` method of a process with an option
  generator included, can ask for the number of tasks of a process without one.
- Inside a task, the number of tasks of every process is in the execution
  context, and asking for it reads it from there.

A process that takes its number of tasks from another and has no data of its own
to build its option lists from is thus written with an option generator. A
number of tasks that depends on itself, through `get_process_num_tasks` and the
`_generate_opts_size` methods of one or more processes, stops the preparation of
the run. `get_process_num_tasks` prints the number on its standard output, so it
is read in a command substitution, and a failure, which prints nothing, has to
stop the method that reads it, as in
`n=$(get_process_num_tasks worker) || return 1`.

**Checking the options against their declaration.** The options of the first
task of every process are checked against the declared ones while the run is
prepared. An option that the task defines but the process does not declare stops
the preparation, as it usually means a typo or a declaration out of date; a
declared option that the first task does not define only gives a warning, and
none at all for a command line option that is optional or a flag, which is often
defined only when given. The warning for a mandatory command line option that
the first task lacks suggests declaring it as a task shaping option, the usual
reason for that absence. A task shaping option that the process also declares in
`_explain_opts`, marks in `_identify_cmdline_opts`, or defines for its first
task stops the preparation. So does an option that `_identify_cmdline_opts`
marks but `_explain_opts` does not declare: it is usually a typo that leaves the
intended option unmarked, or a leftover. Only the first task is checked, and the
check assumes that the tasks of an array have the same option names. A process
whose number of options depends on the run, such as `-outf0`, `-outf1`, and so
on, declares the whole fanout family once, as `-outf-ith`, and any option made
of the prefix and a number matches it.

## How option values reach a task

For a process without an option generator, the option list of each task, with
its connections resolved, is serialized as its words joined by the separator
`<_ARG_SEP_>` and written as one line of `.sched_opts/sched_opts_<process>`, the
line of a task being its task index plus one:

```
-inf<_ARG_SEP_>/path/to/outdir/file_writer/out.txt
```

A process with more than 10000 tasks has its lines split into files of 10000
lines each, `sched_opts_<process>_<n>`. The task reads its line when it starts.
For a process with an option generator there is no such file: the task calls the
generator, which the execution context carries, resolves the connections of the
option list as the preparation of the run does, from the lines of the connected
processes or from their generators, and refuses an option with two different
values.

The task turns its option list back into an array of words and passes it as the
arguments of the process function, and of the `_skip`, `_reset_outfiles` and
`_post` methods. It also writes the options it received, quoted and one option
per line, to `<process>.opts` in its exec directory, or `<process>_<index>.opts`
for a task of an array process, for a person or a tool to inspect; the engine
never reads that file back.

`program.opts` gives, for every process, its number of tasks and the options of
its first ten tasks. It is what a run compares with the one of the previous run
on the same output directory to find the processes whose input changed (see
"Reruns").

The serialization sets two limits on a value: it cannot contain a newline,
since the option list of a task is a line, nor the separator `<_ARG_SEP_>`. And
since the lines hold absolute paths into the output directory, the options of a
run belong to the directory where the run was prepared (see "Architecture").

# The dependency graph

The order in which the processes of a program run is not written anywhere: the
engine infers it from the options of the tasks, as a set of dependencies
between processes, and hands the dependencies to the scheduler, which launches
a process once they hold. This section describes how dependencies are
inferred, what each type asks for and how two types on the same producer
combine, how a process replaces its inferred dependencies with explicit ones,
and how the engine checks that the dependencies can be satisfied at all.

## Inferring dependencies from options

While the run is prepared, once every option list is known and its connections
resolved, the engine goes through the options of every task of every process. An
input option whose value is an absolute path that an output option of another
process holds (see "Output options") makes a dependency of the process on that
producer, or on each of them when several processes produce the same path, and
the value decides its type:

- A file, or anything that is not a FIFO, gives `afterok`: the process waits
  for every task of the producer to succeed. When both processes are array
  processes and the option is read by the task with the same task index as the
  producing one, the type is `aftercorr` instead: each task waits only for its
  own counterpart.
- A FIFO gives `none`, no dependency at all: the reader and the owner of a FIFO
  have to run together, and a dependency between them would make one wait for
  the other to end (see "Running both ends together").

The option dependency method of the process, `_define_opt_deps`, can change the
type of any of them. The engine calls it with the name of the option and the
name of the producer, and takes the type it prints instead of the one above;
printing nothing keeps the inferred type, and printing `none` removes the
dependency. A reader of a FIFO that should not start before its owner has
started, for example, gets `after` this way.

A process never depends on itself: a value that it both produces and reads makes
no dependency on it, so that a process can read what it writes. The dependencies
of the tasks of a process are then merged into one dependency on each producer
(see "Dependency types and how they merge"): the scheduler launches the tasks of
a process when the dependencies of the process hold, and `aftercorr` is the one
type that relates single tasks. An array whose tasks read the task of the same
index of another array keeps `aftercorr`; if some task reads another index, the
merge gives `afterok`, and the whole array waits for the whole producer.

## Dependency types and how they merge

A dependency asks for something about the producer:

| Type | Holds when |
|---|---|
| `none` | always: it is no dependency |
| `after` | the producer has started |
| `afterok` | every task of the producer has succeeded |
| `afternotok` | the producer has failed |
| `afterany` | the producer has ended, whether it succeeded or failed |
| `aftercorr` | the task of the producer with the same task index has succeeded |

The types are not independent: every type but `none` implies `after`, since a
producer that has ended has started, and `afterok` implies both `afterany` and
`aftercorr`. When a process has two dependencies on the same producer, from two
options or from two tasks, the engine merges them into the weakest type that
asks for everything both of them ask for:

- Two equal types give that type, and `none` or `after` with any type gives the
  other type.
- Any two of `afterok`, `afterany` and `aftercorr` give `afterok`: every task
  finished and the corresponding one successful is only covered by all of them
  successful.
- `afternotok` with `afterany` gives `afternotok`.
- `afternotok` with `afterok` or `aftercorr` cannot hold in any run of the
  producer, which cannot both fail and succeed, and stops the preparation of
  the run, as does a type the engine does not know.

The table gives the meaning that a program relies on. Two schedulers carry it
out, and each departs from it in one known place, described in "Scheduling": the
built-in scheduler treats `aftercorr` as `afterok`, so the tasks of an array
wait for the whole producer, and a Slurm older than 16.05, which has no
`aftercorr`, gets `afterok` in its place. Both only make a process wait longer
than the program asked for, never less. A program run with
`--builtinsched-oneshot`, which never waits for a process to end, is refused
when it has any dependency other than `none` and `after`.

## Explicit dependencies

A process whose additional specifications include `processdeps` gets exactly
the dependencies it gives, and no inferred one: the engine does not merge the
two. The value is `none`, for no dependency, or a list of `<type>:<process>`
separated by `,`, when every dependency has to hold, or by `?`, when one of them
is enough:

```
specs="cpus=1 mem=32 time=00:01:00"
add_debasher_process "r" "${specs}" "processdeps=afterok:w"
add_debasher_process "c" "${specs}" "processdeps=afterok:a?after:b"
```

The value is checked when the final process specification is built: every
element has to be of that form, with a type from the table above and a process
of the program, and a list may not use both separators. Explicit dependencies
serve what the options cannot say: a process that reads what another leaves in
a shared directory, or an order between processes that exchange nothing. They
also take the process out of the inference altogether, so a process that
gives them has to give every dependency it needs.

## Topological order and cycles

With the dependencies of every process known, the engine sorts the processes in
topological order, a depth-first walk from each process to its producers in
which a process comes after every process it depends on. The walk stops the
preparation of the run when it comes back to a process it has not finished, a
cycle of dependencies, which no scheduler could ever satisfy, and names the
process where it found it. Processes that do not depend on each other come in
no particular order.

The Slurm scheduler submits the processes in this order, since the submission
of a process names the jobs of its producers, which therefore have to exist
already. The built-in scheduler does not use the order: in each round it
launches whatever tasks have their dependencies satisfied at that moment (see
"The built-in scheduler"). The check for cycles, though, runs for every
scheduler, so a program with a cycle of dependencies is refused whatever
scheduler would run it.

A cycle through FIFOs is not a cycle of the dependency graph. The type of a
dependency through a FIFO is `none` unless the option dependency method says
otherwise, so processes that stream to one another in a loop have no edge
between them, run concurrently, and the loop lives only in the FIFOs (see
"Cycles through FIFOs"). An option dependency method that gives such a
dependency a type other than `none` turns the loop back into a cycle of the
graph, and the run is refused.

Every run draws its dependency graph into `__graphs__/dependency_graph.dot`,
from the final process specification, and into a PDF and an EPS file when
Graphviz is installed. With `--gen-proc-graph` it also draws the process graph,
`__graphs__/process_graph.dot`, whose edges are the connections between the
options of the tasks, FIFOs included, and which therefore shows the cycles
that the dependency graph does not have.

# FIFOs

A FIFO lets two tasks exchange data while both run, instead of one waiting for
a file that the other has finished writing. Its semantics come from the
operating system, and they shape the whole design: opening a FIFO for writing
blocks until some process opens it for reading, and the other way around; a
write blocks while the FIFO holds as much as it can, until the reader takes
some of it; nothing is kept on disk; and the reader sees the end of the data
when the last writer closes the FIFO. The two ends of a FIFO therefore have to
run at the same time and on the same machine, and neither can wait for the
other to end. This section describes how a FIFO is declared and who owns it,
how the engine makes both ends run together, how FIFOs carry cycles that the
dependency graph never sees, how the traffic of a FIFO can be observed, and
what happens when one end fails.

## Declaring and owning a FIFO

A process declares a FIFO, in its `_define_opts` method or in its option
generator, with `define_fifo_opt <option> <name> <optlist>`, which takes the
task that declares it from the engine (see "Arrays and option generators").
`define_fifo_opt_generator <option> <name> <task index> <optlist>` is the same
function, kept for the modules that call it, and ignores the task index it is
given. The task that declares the FIFO is its owner, and the value of the option
is the absolute path of the FIFO, `__fifos__/<owner process>/<name>`. The path
is named after the process and not after the task, so two tasks of an array that
declare FIFOs of the same name are refused: each task of an array needs FIFO
names of its own. Declaring the same FIFO again from the same task is not an
error, since an option generator is called several times for the same task.

The owner declares the FIFO through the output option through which it writes
it. The reader takes the path through an input option, usually a connection to
that output option (see "Connections between processes"). Once every option
list is known, the engine registers, for each FIFO, its reader: the one task of
the program that uses the path through an input option other than the one
through which the owner declared it. The reader may be another task of the same
array, or the owner itself through another option, a self-loop. A second
reader is refused, since each line written into a FIFO reaches only one of the
processes that read it, and the other would wait for lines that never come.
A FIFO that no task of the program reads has an external end, left to someone
outside the program, such as a person who reads it from a terminal. The FIFOs
that the tasks of a process declare through the same output option are read
inside the program for every task or for none: when only some of them are, the
preparation of the run stops, since the others are almost always a mistake (a
reader with fewer tasks than the process, or a connection made with
`define_opt_from_proc_out`, which takes only the first task), and their owners
would block for ever waiting for a reader. A FIFO fed from outside the program,
which its owner reads, is left out.

A FIFO whose writer is outside the program is declared by its reader, through
an input option, with a tag that says so (`--control` or `--external`). Tags
belong to resident programs, and a general program that uses one is refused
(see `doc/design_doc_resident.md`).

`program.fifos` lists every FIFO of the run: its name, the task that owns it,
and the task that reads it or `__EXTERNAL__` for an external end. The engine
creates a FIFO with `mkfifo` when it prepares the process of its owner, before
the process is launched, removing the one that an earlier run left, so that
every run of the owner starts with a new, empty FIFO.

## Running both ends together

Neither end of a FIFO can wait for the other to end: the writer would block
on opening the FIFO, or on writing into it, until the reader reads. This is
why the dependency inferred through a FIFO has the type `none` (see
"Inferring dependencies from options"): the two ends are independent tasks for
the dependency graph, and it is the scheduler that has to run them at the same
time.

The built-in scheduler keeps an end of a FIFO out of a round until its other end
can start with it. In each round, a task at one end of a FIFO is launched only
when the other end, a task of the program, already runs, has finished, is
launched in the same round, or waits only for processes to start, as a reader
with an `after` dependency on the owner of its FIFO does, which then starts in
the next round. Chains of FIFOs are followed to the end. An end that went first
while its other end waited for another process to end would block on opening the
FIFO and hold its CPUs and memory, possibly the ones that process needs, and the
program would never finish. When resources are limited, the knapsack solver
takes the ends of a FIFO, and every end of a chain of FIFOs, all together or
none of them, and a round in which no group of ends fits in the free resources,
with nothing else to launch, stops the run with an error (see "The built-in
scheduler").

One case remains open. An end that goes first because its other end only waits
for it to start holds its resources while it waits, and if they are what the
other end needs, the other end never fits: with 2 CPUs, a writer that asks for
1 and a reader that asks for 2 and depends on it with `after`, the reader never
starts and the run does not end.

The Slurm scheduler cannot run both ends together: it places each job on a node
of its own choosing, and the two ends of a FIFO only meet on the same machine. A
program that uses FIFOs is refused under the Slurm scheduler when the run is
prepared.

Between runs, the two ends of a FIFO are kept in the same state (see
"Reruns"). When a run starts and one end has finished while the other has not,
both are marked to rerun, and a rerun mark on one end reaches the other, and
from each of them the processes that depend on them. A run therefore never
launches an end whose other end has finished and will not run again. The
owner of a FIFO with an external end is run again on every run, since the
engine cannot tell whether the outside got what it needed, and everything
connected to it through dependencies or FIFOs runs again with it.

## Cycles through FIFOs

A dependency through a FIFO adds no edge to the dependency graph, so processes
that stream to one another in a loop are a valid program: the loop lives in the
FIFOs, and the graph that the scheduler sees has no cycle. In
`data/programs/debasher_cycle.sh`, `process_a` owns a FIFO that `process_b`
reads, and `process_b` owns one that `process_a` reads:

1. `process_a` writes the value 1 into its FIFO and reads from the other.
2. `process_b` reads 1, writes 2 into its own FIFO and reads again.
3. `process_a` reads 2, and the two go on until the value passes a limit.
4. `process_a` then writes `DEBASHER_SHUTDOWN_TOKEN`, which `process_b` takes
   as the end of the loop, and both return.

The engine guarantees what makes such a loop possible: both processes start
together, each FIFO exists before its owner runs, and each has one reader. It
does not guarantee that the loop ends, or that it does not stop with each
process waiting for the other: when the loop ends is decided by a protocol
between the processes, for which the engine only provides
`DEBASHER_SHUTDOWN_TOKEN` as a conventional value, and a loop in which every
process waits to read before it writes blocks for good, with no error from the
engine. Resident programs are built on such loops and give them what general
programs lack, such as rounds, checkpoints and an orderly stop (see
`doc/design_doc_resident.md`).

## Mirror taps

A FIFO declared with `--mirror` can be observed while it carries data, without
taking any line from its reader. It is a debugging aid for general programs:
`--mirror` is refused in a resident program, and it is only allowed on an
output option, since the mirror tap sits on the side of the writer.

When a task of the owner starts, the engine replaces the value of the mirrored
option in the arguments of the process function with the path of a shim FIFO,
`__fifos__/.mirror/<owner>/<name>.shim`, and starts a mirror tap in the
background. The tap reads the shim line by line and writes every line to the
mirror log, `__fifos__/.mirror/<owner>/<name>.log`, and to the real FIFO. The
reader, the option lists and the `.opts` file of the task keep the real path,
and `debasher_get_fifo_mirror` prints the log of a FIFO, or follows it as it
grows. The shim and the log are created, and the log emptied, with the FIFO,
on every run of the owner.

The tap keeps its three files open for its whole life. It opens the shim for
reading and writing, so that the opens of the owner never block and lines
written through several opens are not lost between them; POSIX leaves opening a
FIFO for reading and writing undefined, and the engine relies on what Linux and
macOS do, which is not to block. It opens the real FIFO once, so that its reader
sees the end of the data only when the tap exits, and it ignores `SIGPIPE` and
retries a write that fails, so that a reader that opens the FIFO anew for each
line, and is briefly gone between two of them, gets every line.

When the process function returns, the engine writes a stop token into the shim.
The tap forwards everything before it, including a last line without a newline,
which it forwards as it was written, and exits. A tap that has not stopped
within two seconds, because it is stuck retrying a line that no reader will
take, is ended with `SIGTERM`, and `SIGKILL` if needed (on macOS, where
`SIGTERM` does not interrupt a tap blocked on the real FIFO), with a warning and
without failing the task: the lines it could not forward are in the mirror log.
A tap that stops on its token but exits with an error fails the task.

A mirror changes how the owner runs. Its writes go to the shim, which the tap
holds open, so the owner no longer blocks when no reader has opened the real
FIFO yet, up to what the shim can hold. The tap copies a line to the log only
after it has opened the real FIFO, that is, once a reader has opened it, so a
FIFO that nobody reads leaves an empty log. And the tap forwards lines of text:
a NUL byte does not reach the reader.

## When one end fails

The engine does not watch the other end of a FIFO when one end fails, and what
happens depends on when the failure comes:

- **An end fails before opening the FIFO.** The other end blocks on its own
  open for good. Its process stays `IN-PROGRESS`, the built-in scheduler waits
  for it, and `debasher_exec` does not end. `debasher_stop` ends the program.
- **The writer fails after writing some data.** The reader sees the end of the
  data, and may finish successfully with what it got: a `FINISHED` reader does
  not mean that it got everything the writer meant to send. The next run
  reruns both ends, since one of them has not finished.
- **The reader stops reading while the writer writes.** The writer gets
  `SIGPIPE` on its next write, and its task ends.

A task ended by `SIGPIPE`, like one whose process function calls `exit`, ends
with no error message and without running its `_post` method, and leaves no
completion marker, so its process is `UNFINISHED` (see "Executing a task").
Noticing that one end has failed and stopping the other is left to the person
who runs the program, and to future work.

# Scheduling

Once the run is prepared, the processes are handed to a scheduler, which
launches the tasks of each process when their dependencies hold and keeps the
ids that tell whether they still run. The engine has two schedulers: the
built-in scheduler, which runs the tasks on the local machine, and the Slurm
scheduler, which submits them to a Slurm cluster. This section describes what
the rest of the engine asks of a scheduler, and how each of the two answers.

## The scheduler abstraction

The scheduler of a run is decided once, while the run is prepared: the one
named with `--sched` (`BUILTIN` or `SLURM`), or else the Slurm scheduler when
`sbatch` is found on the machine where `debasher_exec` runs, and the built-in
scheduler otherwise. The command line file records the scheduler that the run
used, so that the tools that read the run later take the same one, wherever
they run. A resident program always runs on the built-in scheduler.

The rest of the engine does not depend on the scheduler, and asks it for a few
things only: to write the process script of a process, to launch it, to give
the ids of what it launched, to tell whether an id still runs, and to stop an
id. The ids of a process are kept in its exec directory, in a `.id` file, and a
process is `IN-PROGRESS` exactly when one of its ids still runs (see "Process
status"). For the built-in scheduler an id is the process id of the script of
a task; for the Slurm scheduler it is a job id. `debasher_stop` ends a run
through the same operation, whatever its scheduler.

Both schedulers take the dependencies of each process from the final process
specification, and give them the meaning described in "Dependency types and
how they merge", with the departures listed below. One case is common to both:
a dependency on a process that is not launched in this run. Such a process has
either finished in an earlier run, and a dependency on it holds, except
`afternotok`, which asks for it to have failed; or it has not finished and is
not launched either, and a dependency on it never holds. A process whose
dependencies cannot hold for this reason is not launched, and neither are the
processes that depend on it: they are left for a later run.

## The built-in scheduler

The built-in scheduler is `debasher_exec` itself, which stays in a loop of
rounds until no task is left to launch and none still runs. In each round it:

1. Reads the status of every process from its exec directory, and returns to
   the budget the CPUs and memory of the processes that have ended. A process
   that was running in this run and has ended without finishing is taken as
   failed, which is what `afternotok` and `afterany` look for.
2. Finds the candidates of the round: the tasks that are not running and have
   not finished or failed, whose process has its dependencies satisfied, that
   fit on their own in the free CPUs and memory, and, in an array process,
   that the throttle of the process allows.
3. Leaves out the tasks at one end of a FIFO whose other end cannot start with
   them (see "Running both ends together").
4. Chooses the tasks to launch. With no limit on CPUs or memory, every
   candidate is chosen. With a limit, the choice is a knapsack problem, which
   a greedy solver answers: each task is an item whose weights are its CPUs
   and its memory, whose value is 1, divided among the tasks of an array
   process, and the ends of a FIFO, or of a chain of FIFOs, are chosen all
   together or none of them. A round that has candidates but can choose none
   of them stops the run with an error.
5. Launches the chosen tasks, writing the process script of a process when
   its first task is launched (see "Running a process"), and waits one second
   before the next round, or five when the program has more than ten
   processes.

The budget is given with `--builtinsched-cpus` and `--builtinsched-mem`, and is
unlimited by default. Every task of a process asks for the `cpus` and `mem` of
its process specification, and the built-in scheduler takes the first value of
each when they are lists. `time`, `nodes`, `account` and `partition` are not
used. Before its first round the scheduler refuses the run when a process asks
for more CPUs or memory than the budget, which the validation checks too, in
the same way.

A task is launched as a background process of its own process group, whose
process id goes to the `.id` file of the task, so that stopping it reaches
everything it started. The script of the task ignores `SIGTERM` itself, so
that a graceful stop sent to its whole group ends what it runs but lets it
finish its own bookkeeping; `debasher_stop` sends `SIGKILL` to the group.

The built-in scheduler gives the dependency types the meaning of the table,
with one departure: it treats `aftercorr` as `afterok`, so the tasks of an
array wait for every task of the producer, not only for their own
counterpart. A dependency holds when the status of the producer says so:
`after` once the producer has started, `afterok` once it has finished, and
`afternotok` and `afterany` once it has failed in this run or, for
`afterany`, finished.

With `--builtinsched-oneshot`, `debasher_exec` goes through its rounds with no
pause, launching whatever can start, and ends as soon as nothing more can start
without waiting for something to end. Before launching anything, it refuses what
only the end of a task could let through: a dependency other than `none` and
`after`, a throttle, of the process or given with `--dflt-throttle`, smaller
than the number of tasks of its process, and a first round that does not fit in
the budget at once.

## The Slurm scheduler

The Slurm scheduler submits every process of the run that has not finished and
is not running as one Slurm job, in topological order, and `debasher_exec` then
ends, unless `--wait` asks it to stay until no process is running. An array
process is one job array, `--array=<task indices>`, with `%<throttle>` when it
has a throttle; `--dflt-nodes` gives the nodes of the processes that do not set
them, as `--dflt-throttle` gives the throttle for either scheduler. Every
computational specification but `throttle` becomes an option of `sbatch`:
`cpus`, `mem`, `time`, `account`, `partition` and `nodes`.

Every job is submitted held, and released once its dependencies are in place,
so that the dependencies of each task of a job array can be set before any of
them starts. The dependencies of a process become Slurm dependencies on the
job ids of its producers, with `,` and `?` kept as Slurm reads them, every
dependency or any of them. A Slurm older than 16.05, which has no `aftercorr`,
gets `afterok` in its place; a newer one gets `aftercorr` as it is.

When `mem` or `time` is a list of values separated by commas, the process is
submitted once for each attempt, as many attempts as the longer of the two lists
has values, and a shorter list repeats its last value. Each attempt runs only if
the attempts before it failed, task by task in a job array, so that a task that
fails, for example for exceeding its memory or its time, is run again with the
next values. With more than one attempt, two verification jobs follow the
attempts and record whether one of them succeeded, and the processes that depend
on this one wait for the last of those jobs.

The Slurm scheduler refuses a program that uses FIFOs (see "Running both ends
together"), and it has no `UNFINISHED_BUT_RUNNABLE` status: the tasks of a job
array are submitted together, never some of them in one round and the rest in
another (see "Process status").

# Running a process

A process runs as its tasks, each an execution of the process script that the
engine writes for it. This section describes what the engine prepares for a
process before it is launched, how the code of the program reaches the
process script, what a task does from the moment it starts to the moment it
leaves its completion marker, and how a process gets the Conda environments
and Docker images it needs.

## Preparing a run

Before the scheduler launches a process, the engine prepares it, and only a
process that is neither finished nor running is prepared; a finished process
that is not marked to rerun is left exactly as it is, with its outputs, logs
and completion markers. For a process that is prepared:

- A process that has never run gets its exec directory, `__exec__/<process>`.
- A process that has run before loses the ids and the logs of its previous
  run, and, for an array process, only those of the tasks that have not
  finished, so that the finished tasks of an array are not run again. A
  process marked to rerun has already lost its completion markers (see
  "Reruns"), so none of its tasks counts as finished.
- The FIFOs that the process owns are created again, empty (see "Declaring
  and owning a FIFO").
- Its process output directory is created if it does not exist; under the Slurm
  scheduler, only when the process has never run. What it holds from an earlier
  run is not removed here, except, for a subdivided process output directory of
  a process without a `_reset_outfiles` method, every entry that is neither a
  task subdirectory of the run, nor a path that an output option of the run
  names, nor a directory on the way to one of them; each task resets the
  directory when it starts (see "Executing a task"). The task subdirectories
  that do not exist are created (see "Task subdirectories"). Every process that
  the run launches is prepared before any of them is launched, and a failure
  here stops the run before any process is launched.

## The process script: how code travels

A task runs in a shell of its own, on the local machine or on a node of a
cluster, which has not loaded any module and may not be able to. What it needs
of the program travels in its process script, which the engine writes into
the exec directory of the process when the process is launched. The script
has three parts:

- **The execution context**, a copy of `.exec_context.sh`, which
  `debasher_exec` writes once the program is defined (see "Architecture"). It
  holds every function defined in the shell of `debasher_exec`, those of the
  modules and of the engine alike, and the variables of that shell: every
  variable of the engine, and every variable the modules define. It leaves
  out what the task gets anyway or must not get: the variables that Bash sets
  by itself, read-only ones, exported variables and functions, which the task
  inherits from its environment, and the option lists of the tasks, which
  reach each task on their own (see "How option values reach a task").
  A variable declared with no value, such as an associative array still
  empty, is kept with its declaration, so that it reaches the task with its
  type.
- **A header** with the name of the script, the output directory, the name of
  the process and its number of tasks. Under the Slurm scheduler it also
  installs the handler of `SIGTERM`, the `_slurm_sigterm_handler` method of
  the process or a default one that prints a message and exits with an error.
  Under the built-in scheduler it makes the script ignore `SIGTERM` (see "The
  built-in scheduler").
- **A body** that runs one task, the one whose index the scheduler gives it
  (`BUILTIN_ARRAY_TASK_ID` or `SLURM_ARRAY_TASK_ID`), as "Executing a task"
  describes, and sends its output and errors to the log of the task.

Since the context is copied when the script is written, a task runs the code
that the modules had when its run was prepared, and a later run, which writes
a new context and new scripts, does not change the scripts of a run that is
still going. The one piece of code read when the task runs is the external
script of an alias (see "Processes in other languages, and aliases").

## Executing a task

A task does the same, in this order, under both schedulers:

1. It gets its option list, from its line of `.sched_opts` or from the option
   generator of its process (see "How option values reach a task"), and
   writes it to its `.opts` file.
2. It logs the time it started.
3. If the process has a `_skip` method and the method, called with the options
   of the task, returns success, the task writes its completion marker, logs
   the time it ended and stops: its process output directory, its process
   function and its `_post` method are left untouched, and it counts as
   finished.
4. It resets the process output directory: through the `_reset_outfiles` method
   of the process, called with the options of the task, or, without that method,
   when the process has a single task, by removing everything in it. The tasks
   of an array process share the directory, and without the method it is left as
   it is. Without the method, the task then removes each of its task
   subdirectories with everything in it and creates it again (see "Task
   subdirectories"). A process of a resident program is never reset, since its
   directory holds what its node has done so far.
5. It starts the mirror taps of the mirrored FIFOs it owns (see "Mirror
   taps"), which only the built-in scheduler runs.
6. It runs the process function with its options as arguments, and sends what
   the function prints to its standard output to its `.stdout` file.
7. It stops its mirror taps, and counts the task as failed if one of them
   ended abnormally.
8. It runs the `_post` method of the process, if there is one, with the
   options of the task, whether the process function succeeded or failed. A
   `_post` method that fails fails the task.
9. If the process function failed, the task ends with an error. Otherwise it
   writes its completion marker and logs the time it ended.

Everything else that the task prints, the messages of the engine and the
standard error of the process, goes to the log of the task,
`<process>.sched_out` or `<process>_<index>.sched_out` under the built-in
scheduler, and the file that Slurm writes under the Slurm scheduler. The start
and end times in the log are what `debasher_stats` reads (see "Tools that read a
run").

The process function runs in the same shell as the task, not in a shell of its
own. A process function that calls `exit`, or that is killed by a signal such
as `SIGPIPE`, therefore ends the whole task: nothing after it runs, so there
is no `_post`, no error message from the engine and no completion marker, and
the process is `UNFINISHED` (see "When one end fails"). A process function
signals a failure by returning a status other than zero.

Under the built-in scheduler, the task also exports, before it runs the
process function, the directories and the facts that a process may read about
itself without an option for them: its exec directory
(`DEBASHER_PROCESS_EXECDIR`), its process output directory
(`DEBASHER_PROCESS_OUTDIR`), the directory of the module that added it
(`DEBASHER_PROCESS_MODULE_DIR`), its task index in an array process
(`DEBASHER_PROCESS_TASK_IDX`), its computational specifications
(`DEBASHER_PROCESS_COMP_SPECS`), and, for a node of a resident program, its
ports (`DEBASHER_PROCESS_PORTS`). The resident runtime relies on them; the
Slurm scheduler does not export them.

## Conda and Docker environments

A process that needs a Conda environment or a Docker image declares it in its
`_conda_envs` or `_docker_imgs` method, with `define_conda_env <name> <file>` or
`pull_docker_img <image>`. The engine calls these methods only when the run is
prepared with `--conda-support` or `--docker-support`, once for each process
whatever its number of tasks, in the shell of `debasher_exec` and before any
process is launched:

- `define_conda_env` creates the environment from the `.yml` file when no
  environment of that name exists, and leaves it alone otherwise. The file is
  looked for in the directories of `DEBASHER_YML_DIR`, separated by colons,
  and then among the environment files that DeBasher installs, and the output
  of `conda` goes to `.conda/<name>.log` in the output directory.
- `pull_docker_img` pulls the image when it is not already present.

The engine only makes sure that the environment or the image exists. Using it
is left to the process function, which activates the environment or runs the
container itself, so that one process may use several environments or images,
each for a part of its work, or activate one for only some of its commands.
Without the options, the methods are not called, and the process function
finds whatever the machine already has.

`conda activate` is a shell function of conda, not a program, so a process that
called it directly would depend on how the shell that runs it was started: on a
terminal where conda was set up, and from which the function was inherited, it
works; under a service, a Slurm job or a shell that conda never set up, it
fails. The engine removes that dependence without taking the activation away
from the process: `conda_activate <name>` loads the shell functions of conda
into the shell when it does not have them, and then activates the environment,
after which `conda` itself (`conda deactivate`, another `conda activate`) can be
used. It loads them from a conda executable, the one that the conda functions of
the shell point to (`CONDA_EXE`), or else the one that `configure` found, which
every built script holds as `CONDA_CMD`, as it holds `DOCKER`. With neither, it
fails with an error that says so. `define_conda_env` loads them the same way
before it looks for an environment or creates one. A process uses `"${DOCKER}"`
to run a container, the docker that `configure` found, rather than the first one
in the `PATH`.

# The state of a run

Everything that is known about a run is in its output directory (see
"Architecture"): what `debasher_exec` wrote while preparing it, and what the
scheduler and the tasks write while it goes on. This section lists what the
directory holds and the life cycle of the run resources, describes how the
status of a process is derived from it, how a new run on the same directory
decides what to run again, and what the tools that read a run take from it.

## The output directory

The engine keeps its own files at the top of the output directory, with names
that start with a dot, that are wrapped in double underscores, or that are
fixed:

| Path | Written by | Holds |
|---|---|---|
| `lock` | `debasher_exec`, when it starts | the lock of the directory, and the process id of the `debasher_exec` that holds it |
| `command_line.sh` | `debasher_exec` | the directory it ran from and its command line, with the program file resolved and the scheduler recorded |
| `.exec_context.sh` | `debasher_exec` | the execution context |
| `program.procspec` | `debasher_exec` | the final process specification |
| `program.opts`, `program.opts_old` | `debasher_exec` | the options of every process in this run and in the last run that ended normally |
| `program.opts_exh` | `debasher_exec`, with `--gen-proc-graph` | the options of every task, for the process graph |
| `program.fifos` | `debasher_exec` | the owner and the reader of every FIFO |
| `.sched_opts/` | `debasher_exec` | the option list of every task of a process without an option generator |
| `__graphs__/` | `debasher_exec` | the dependency graph, and the process graph when asked for |
| `__fifos__/` | `debasher_exec` | the FIFOs, and, under `.mirror/`, the shim FIFOs and mirror logs |
| `.conda/` | `debasher_exec`, with `--conda-support` | the logs of the Conda environments it created |
| `.knapsack_*.txt` | the built-in scheduler | the input and the answer of the knapsack solver of the last round |
| `__exec__/<process>/` | the scheduler and the tasks | the exec directory of each process |

The exec directory of a process holds its process script, named after the
process, and, for each task, its id, its options, its standard output, its log
and its completion marker: `<process>.id`, `.opts`, `.stdout`, `.sched_out`
and `.finished` for a process with a single task, and `<process>_<index>.id`
and so on for the tasks of an array process. Under the Slurm scheduler, the
logs are those that Slurm writes, one for each attempt.

Everything else at the top of the directory belongs to the processes: the
process output directory of each process, named after it or after what its
`_outdir_basename` method gives, and the shared directories. They share the
top of the directory with the files of the engine, and the engine refuses
neither a process nor a shared directory whose name is one of those names.

## Run resources and their life cycle

Every directory and FIFO that the engine creates for a task or hands to it, and
every file of a task whose name the engine gives, is a run resource, with an
owner and a life cycle. The files that a task writes under the names that its
options give, its outputs, follow the directory that holds them, and have no row
of their own; nor do the files that the engine keeps for itself at the top of
the output directory (see "The output directory").
The last column says whether a process with many tasks gets the same run
resource as a process with a single task, as the principle stated in the
"Introduction" requires.

| Run resource | Owner | Created | Emptied | Removed | One task and many |
|---|---|---|---|---|---|
| process output directory | the process | when its process is prepared, if missing; under the Slurm scheduler, only when the process has never run, or when a task subdirectory below it is created (see "Preparing a run") | before each task that is not skipped, by the `_reset_outfiles` method of the process, or, without it, for a process with a single task (see "Executing a task"); and, for a subdivided process output directory without `_reset_outfiles`, of every entry that is neither a task subdirectory of the run, nor a path that an output option of the run names, nor a directory on the way to one of them, when the process is prepared (see "Task subdirectories") | never | differ: the tasks of an array share it, and without `_reset_outfiles` it is not emptied before each of them |
| task subdirectory | the task that asks for it | when its process is prepared, if missing (see "Task subdirectories") | before the process function of its task, unless the task is skipped or the process has a `_reset_outfiles` method | when its process is prepared, when no option asks for it while another task of the process asks for a task subdirectory, unless the process has a `_reset_outfiles` method | alike |
| value descriptor | the task | by the task, with `write_value_to_desc`, in the process output directory, named after the option and the task (see "Output options") | does not apply | with the contents of the process output directory, by the default reset of a process with a single task, or, when the process output directory is subdivided and the process has no `_reset_outfiles` method, when no output option of the run names it | alike: each task has its own |
| step marker | the process | by a task, with `mark_step_done`, in a directory of its choice (see "Sequential processes") | does not apply | with the contents of the directory that holds it: by the default reset of a process with a single task, when it is in the process output directory; by the emptying of its task subdirectory before each task, when it is in one; when the process of a subdivided process output directory without `_reset_outfiles` is prepared, when it is in that directory outside a task subdirectory; or with a shared subdirectory that no option asks for while its shared directory is subdivided | alike in a task subdirectory; differ in the process output directory of an array, which keeps it unless the directory is subdivided |
| FIFO, with its shim FIFO and mirror log | the task that declares it | when the process of its owner is prepared, replacing the one of an earlier run (see "Declaring and owning a FIFO") | created again, empty, each time the process of its owner is prepared | never | alike: each task declares a FIFO of its own |
| shared directory | the module that declares it | before any process is launched, if missing (see "Output options") | never, except a subdivided shared directory, from which every entry that is neither a shared subdirectory of the run, nor a path that an output option of the run names, nor a directory on the way to one of them is removed before any process is launched (see "Shared subdirectories") | never | alike |
| shared subdirectory | the tasks that ask for it | before any process is launched, if missing (see "Shared subdirectories") | never | before any process is launched, when no option asks for it while another asks for a shared subdirectory of the same shared directory (see "Shared subdirectories") | alike |
| exec directory | the engine | when a process that has never run is prepared (see "Preparing a run") | when the process is prepared, of the ids and the logs of the tasks that have not finished, and, for a process marked to rerun, of its completion markers, before the run is launched (see "Reruns") | never | alike: each task has its own id, log and completion marker |

**Where one task and many still differ.** The process output directory itself is
the one run resource that one task and many do not get alike: the tasks of an
array process share it, and, without a `_reset_outfiles` method, it is not
emptied before each of them. The principle holds when the wiring gives each task
of an array a task subdirectory, which the engine creates and empties as it does
the process output directory of a process with a single task, and which makes
the process output directory subdivided: what a task writes there outside its
task subdirectories and the paths that its output options name is then removed
when the process is prepared again, unless it has a `_reset_outfiles` method. A
process whose wiring gives its tasks the process output directory itself works
with many tasks only if its own code divides the directory between them, and
keeps there, between runs, the step markers that a process with a single task
loses.

## Process status

The status of a process is derived, whenever it is asked for, from its exec
directory and from the scheduler, and is kept nowhere:

| Status | When |
|---|---|
| `TO-DO` | the process has no process script: it has never been launched |
| `IN-PROGRESS` | one of the ids of the process still runs, as the scheduler says |
| `FINISHED` | every task of the process has its completion marker |
| `UNFINISHED_BUT_RUNNABLE` | built-in scheduler only: an array process with some tasks launched, none running, and some not launched yet |
| `UNFINISHED` | any other case: the process was launched, nothing of it runs, and some task has no completion marker |

A task writes its completion marker only when it ends well (see "Executing a
task"), so a process is `FINISHED` only when every task succeeded or was
skipped. An id runs when the process with that id exists, for the built-in
scheduler, or when Slurm still lists the job, for the Slurm scheduler; a process
id that the system gives again to an unrelated process after the task has ended
can make the process look `IN-PROGRESS`. `UNFINISHED_BUT_RUNNABLE` is the state
of an array that the built-in scheduler was launching a few tasks at a time,
under a throttle or a budget of CPUs and memory, when its run stopped: the next
run launches the tasks that are left. Under the Slurm scheduler the tasks of an
array are submitted together, and the state does not arise.

`debasher_status` prints the status of every process and a summary, and ends
with 0 when every process is `FINISHED`, 2 when some process is `IN-PROGRESS`,
and 3 otherwise; given `-p`, it counts only that process.

## Reruns

A new run on an output directory launches the processes that are not finished,
and runs again the finished processes that it marks to rerun, for one of these
reasons:

- **Forced.** The process has `force=yes` among its additional
  specifications.
- **Changed input.** The options of the process differ from those of the last
  run that ended normally, as `program.opts` and `program.opts_old` give them:
  any option, with any value, or the number of tasks. Only the options of the
  first ten tasks of an array are compared, on the assumption that the tasks
  of an array are alike. A process that the last run did not have is marked
  too. What is compared is the options, not the files they name: a file
  changed in place under the same path is not a changed input.
- **Outdated code.** With `--rerun-outdated-procs`, a finished process whose
  process script is older than any loaded module. The comparison is by the
  modification time of the files, and against every module of the program, not
  only the one that defines the process; an external script of an alias is not
  compared.
- **FIFO ends out of step.** One end of a FIFO has finished and the other has
  not (see "Running both ends together"). The owner of a FIFO with an external
  end is always marked when it has finished, since the engine cannot tell
  whether the outside got what it needed.
- **Resident resume.** In a resident program, every node that is not running
  is marked, so that the program resumes from its checkpoints, as
  `doc/design_doc_resident.md` describes.

The marks then spread until nothing changes: from a process to every process
that depends on it, and from one end of a FIFO to the other. A process marked
to rerun loses its completion markers before the run is launched, so it is
prepared and run as any unfinished process, every task of it.

`program.opts_old` is written at the end of a run, once every process has been
launched or, with the built-in scheduler, has ended. A run that is stopped or
fails before that leaves the options of the run before it in place, so the
next run compares with those, and a change it did not carry out is still found.

## Tools that read a run

The tools that follow or act on a run read it from its output directory alone
(see "Architecture"): they take the processes from `program.procspec`, the
scheduler from `command_line.sh`, and everything else from the exec
directories, and they neither load a module nor need the program file.

- `debasher_status` gives the status of the processes (see "Process status"),
  with `-i` their ids.
- `debasher_stop` stops the run. Without `-p`, it first stops the
  `debasher_exec` of the run if it still runs, whose process id is in the lock
  file: it sends it `SIGTERM`, which makes the built-in scheduler, or the
  Slurm scheduler while it submits jobs, launch nothing more from the next
  round or process on, and `SIGKILL` if it has not ended within thirty
  seconds, and waits until the lock is free. Only then does it stop every
  process that is running, killing the process group of each task under the
  built-in scheduler and cancelling its jobs under the Slurm scheduler. After
  it, no task of the run runs and nothing is left that could launch one. With
  `-p`, it stops the running tasks of that one process, and the rest of the
  run goes on.
- `debasher_stats` gives the time that each process, and each task of an
  array, took, from the start and end times in their logs.
- `debasher_get_stdout`, `debasher_get_sched_out` and
  `debasher_get_fifo_mirror` print the standard output, the log, or the mirror
  log of a process or of one of its tasks, or follow it as it grows.

Two tools run processes of a run rather than read it, and refuse an output
directory that has been moved: `debasher_exec` itself, and
`debasher_launch_process`, which launches again one process or task of a run
with the process script that the run wrote, as the `Supervisor` of a
resident program does. `debasher_exec_process` runs one process function
outside any run, after loading its module, which is useful to try a process on
its own and is how a process test runs it (see "Testing a process with bats").

# Business tests of a program

A business test checks the business logic of one process of a program: what
the process does with the values of its options, run on its own, with no
scheduler, no output directory and none of the other processes. A process
receives a list of options and produces files, values or data written into a
FIFO (see "Introduction"), so it can be run like any Unix program, given its
options, and tested by looking at what it writes. How the processes of a
program connect, and whether the program as a whole runs, is not what these
tests check: running the program does that.

This section describes where the tests of a program live, how a process is
tested with bats, how a node of a resident program is tested with pytest, the
tool that runs the tests of a program, and how an installation checks that
tool with the programs that it ships.

## The test directory

Business tests are offered only to a program in a program directory: a
directory, of any name, that holds a program and its tests. Its program file
is found in one of two ways:

- When the directory holds program metadata of the web UI
  (`.debasher/program.json`, see "The home directory" in
  `doc/design_doc_webui.md`), the program file is `<name>.sh`, where `<name>`
  is the top-level `name` field of that metadata, after which the web UI names
  the script that it generates. The name of the directory does not matter,
  since the user chooses it, and a program renamed after its first save keeps
  its directory. The metadata is read as JSON
  (`debasher::_get_ui_program_name`), since the processes and options of the
  program have `name` fields too.
- Otherwise, for a program written by hand, the program file is the only
  `*.sh` file at the top of the directory. A directory with none, or with
  several, is not a program directory: other scripts, such as the external
  script of an alias or a helper of the user, may live beside the program, and
  the runner does not guess which one is the program.

The tests of the program are in its test directory, `test` inside the program
directory, as test files of two kinds:

- `*.bats`, process tests, run with bats;
- `test_*.py`, node tests, run with pytest.

Any other file of the test directory is left to the tests, typically data that
they read, which a test finds from the directory of its own file
(`BATS_TEST_DIRNAME` in bats, `Path(__file__).parent` in pytest). The test
directory is a user file of the program directory: no reserved name of the web
UI matches it, so its program files panel shows the tests and lets the user
edit them.

## Testing a process with bats

A process test runs a process with `debasher_exec_process`, which loads the
module of the program, runs its `_program` method and calls the process
function with the options that it is given, outside any run (see "Tools that
read a run"). Nothing builds the options of the process, since `_define_opts`
does not run: the test gives every option that the process function reads, and
for each file that the process writes a path under the temporary directory of
the test. An option that names a FIFO holds a path like any other, so a
regular file stands in for the FIFO: a process that reads a FIFO is tested on a
file that holds what would arrive, and one that writes a FIFO on a file that
the test reads afterwards.

A process test loads the test helpers, `debasher_bats_helpers`, a Bash library
installed with the engine, whose path the test runner exports as
`DEBASHER_BATS_HELPERS`. The library defines `debasher_process`, which runs
`debasher_exec_process -q "${DEBASHER_TEST_PFILE}" <process> -- <options>` and
stops with a message when `DEBASHER_TEST_PFILE` is not set. Loading the
library declares that the tests need bats 1.5.0, the version that brought
`run --separate-stderr`, which bats otherwise warns about. For the process
`greet` of the program `webui_batch_greet`, which waits `-secs` seconds, writes
a greeting into the file `-outf` and fails on the text `fail`:

```bash
load "${DEBASHER_BATS_HELPERS}"

@test "greet writes the greeting" {
    run debasher_process greet -text Ann -secs 0 \
        -outf "${BATS_TEST_TMPDIR}/greeting.txt"
    [ "${status}" -eq 0 ]
    [ "$(cat "${BATS_TEST_TMPDIR}/greeting.txt")" = "Hello, Ann!" ]
}

@test "greet fails on the text fail" {
    run --separate-stderr debasher_process greet -text fail -secs 0 \
        -outf "${BATS_TEST_TMPDIR}/greeting.txt"
    [ "${status}" -eq 1 ]
    [ "${stderr}" = "Error: asked to fail" ]
}
```

Two features of `debasher_exec_process` serve these tests:

- `-q`, given before the program file, drops the progress messages of the
  tool ("Loading debasher modules..." and the like) and those of
  `load_debasher_module` for every module it loads, which it silences through
  `DEBASHER_QUIET_MODULE_LOADING`. What the process writes to its standard
  error is then all that a test finds there. The errors of the tool, and what
  the code of a module or the `_program` method writes, are still printed.
- The tool exits with the status of the process function, so that a test can
  tell one failure of the process from another.

A process runs in the environment of the test runner. It activates its Conda
environments and runs its Docker images itself, as in a run (see "Conda and
Docker environments"), so that part behaves the same. Creating the environments
and pulling the images, which `--conda-support` and `--docker-support` do before
a run, is done only when the test runner is given the same options (see "The
test runner: `debasher_test`"); otherwise they have to exist already. A test of
a process that needs an environment calls
`debasher_skip_without_conda_env <name>` of the test helpers first, which skips
the test, with its reason, where conda or the environment is missing, for
example on a machine that never ran the program with conda support. Its `_skip`,
`_post` and `_reset_outfiles` methods do not run. An array process is tested one
task at a time, with the options of that task, since `_generate_opts` does not
run either. A process whose work needs the other end of a FIFO to run at the
same time, such as one of the two processes of a cycle that wait for each
other's replies, cannot be tested on its own with a regular file standing in for
the FIFO.

## Testing a node with pytest

The process function of a node runs `python3` on its heredoc, which builds the
node and calls `run()`: the node opens its FIFOs, exchanges envelopes and
reports to the `Supervisor`, none of which is business logic. A node test does
not run the process. It builds the class of the node inside the test, with the
node harness of the runtime library, feeds it packets, and looks at the
packets that it sends and at its node state (see "Testing a node without the
engine" in `doc/design_doc_resident.md`). Node tests are written in Python,
the language of the code of a node.

## The test runner: `debasher_test`

`debasher_test [--conda-support] [--docker-support] <dir>` runs the tests of
the program in the program directory `<dir>`:

1. It checks that `<dir>` is a program directory, and stops otherwise.
2. It looks for test files in the test directory. When there is none, or no
   test directory, it says so and exits.
3. It exports `DEBASHER_TEST_PFILE`, the absolute path of the program file,
   `DEBASHER_BATS_HELPERS`, and `DEBASHER_LIBEXECDIR`, where the node harness
   finds its tool, and adds the directory of the tools of the engine to `PATH`
   and the directories of its Python modules to `PYTHONPATH`.
4. With `--conda-support` or `--docker-support`, it loads the program and
   creates the Conda environments, or pulls the Docker images, that its
   processes declare, those that do not exist yet, using the functions that
   `debasher_exec` uses with those options before a run
   (`debasher::_prepare_conda_envs`, `debasher::_pull_docker_imgs`), so that a
   test of a process finds them (see "Conda and Docker environments"). The logs
   of conda go to a temporary directory, given as `DEBASHER_CONDA_DIR`, since
   there is no output directory; it is removed once the environments exist, and
   kept, with its path in the error, when one could not be created. An
   environment or an image that cannot be prepared means that the tests cannot
   run.
5. From the program directory, it runs bats on the process tests and pytest on
   the node tests, each only when the program has tests of that kind. The bats
   and pytest that it runs are those that `configure` found, or those given in
   `DEBASHER_BATS` and `DEBASHER_PYTEST`, such as the pytest of a virtual
   environment. A kind of test whose tool is missing is an error.

Its exit status is 0 when every test passed, 1 when a test failed, 2 when it
could not run the tests (no program directory, a missing tool, a wrong
argument) and 77 when the program has no tests. 77 is the status with which
Automake marks a skipped test: a caller tells a program without tests from one
whose tests pass.

A run of the tests writes nothing into the program directory: pytest runs
without its cache (`-p no:cacheprovider`) and without writing bytecode
(`PYTHONDONTWRITEBYTECODE`), bats keeps its files in temporary directories,
and the test helpers and the node harness write only under temporary
directories. A test that writes into the program directory by itself breaks
this, and nothing stops it. This is what lets the tests of an installed
program run where the user cannot write.

A test file can also be run on its own, with bats or pytest, once the
variables that the runner exports are set, which helps to debug one test.

## Checking an installation

`make installcheck` runs `debasher_check_installation`, which runs the programs
of `data/webui_programs` from where they were installed. Four of them carry a
test directory, installed with them: `webui_batch_greet`, with process tests,
`webui_running_sum`, with node tests, `webui_watch_tally`, with node tests of a
`DirectoryWatcher` that observes a directory and of the node it feeds, and
`webui_conda_example`, with a process test of a process that activates a conda
environment, skipped where the environment does not exist.
`debasher_check_installation` runs `debasher_test` on every program of
`data/webui_programs` and fails on any status other than 0 or 77. When
`configure` did not find the tool of a kind of test that a program has, the
check does not run the test runner on that program, and says that its tests are
skipped. It also checks that the test runner finds the program of a copy of
`webui_batch_greet` in a directory of another name, that it prepares the Conda
environment of `webui_conda_example` with `--conda-support` where conda is
usable, and that it refuses, with status 2, a directory that is not a program
directory.

This checks, once DeBasher is installed, that the test runner, the test
helpers and the node harness work as installed, which no test of `make check`
can, since those run on the build tree. The two programs also show a module
author how to write each kind of test.

# Guarantees and non-goals

This section gathers the guarantees that the engine gives to a general
program, stated along the way in the sections above, each with the section
that describes it, and then the limits of those guarantees and what the engine
leaves, by design, to the program or to whoever runs it.

**Guarantees.**

1. A run is prepared completely or not at all: an error while the modules are
   loaded, the options built, the dependencies inferred or the specifications
   checked stops `debasher_exec` before any process is launched (see
   "Architecture").
2. Only one `debasher_exec` prepares or runs a program in an output directory
   at a time, and it refuses to start while a process of the program is still
   running from an earlier run in that directory (see "Architecture").
3. A task runs the code of the modules as it was when its run was prepared;
   only the external script of an alias is read when the task runs (see "The
   process script: how code travels").
4. The tools that read a run read it from its output directory alone: a module
   changed or removed after the run does not change what they report. A moved
   output directory can be read, and is refused by the tools that run its
   processes (see "Tools that read a run").
5. Every option of a task has a single value, and two definitions that give it
   different values stop the preparation of the run (see "Defining the options
   of a task").
6. The dependency graph has no cycle, and explicit dependencies are well
   formed and name processes of the program; a program that breaks either is
   refused (see "The dependency graph").
7. A process is never launched before its dependencies hold, with the meaning
   of "Dependency types and how they merge": a scheduler may make it wait
   longer, never less. A dependency on a process that is not launched in the
   run holds only when that process has finished and the type is not
   `afternotok`; otherwise the process, and those that depend on it, are left
   for a later run (see "The scheduler abstraction").
8. Every FIFO has one owner and at most one reader in the program, and it is
   created again, empty, before its owner runs (see "Declaring and owning a
   FIFO").
9. Under the built-in scheduler, the two ends of a FIFO are launched in the
   same round, or one once the other runs, or once the other only waits for it
   to start; a program with FIFOs is refused under the Slurm scheduler (see
   "Running both ends together").
10. At the start of a run, the two ends of every FIFO are in the same state:
    no run launches an end whose other end has finished and will not run again
    (see "Running both ends together").
11. A process is `FINISHED` only when every one of its tasks has succeeded or
    was skipped (see "Process status").
12. A mirror tap forwards every line that the owner writes, in order and as it
    was written, to the reader and to the mirror log, and a tap that cannot
    forward does not keep the owner from ending (see "Mirror taps").
13. The oneshot mode of the built-in scheduler refuses, before launching
    anything, a program that it could not run without waiting for something to
    end (see "The built-in scheduler").
14. A new run on an output directory runs every process that has not finished,
    and every finished process that is forced, whose options changed, or whose
    FIFO has an end that runs again, together with every process that depends
    on them (see "Reruns").
15. After `debasher_stop` on a whole program, no task of the run is running,
    nothing is left that could launch one, and nothing is left half launched
    (see "Tools that read a run").
16. The methods that define the options of a process run only when every task
    shaping option of the process is given on the command line (see "Command
    line options").
17. Every shared subdirectory that an option asks for exists before any
    process of the run is launched. The engine removes only what a subdivided
    shared directory holds besides the shared subdirectories of the run, the
    paths that output options of the run name and the directories on the way
    to them, while no task is running; never the contents of a shared
    subdirectory of the run, the shared directory itself or anything outside
    it (see "Shared subdirectories").
18. A task subdirectory exists when its process is launched, and is empty when
    the process function of its task starts, unless the task is skipped or its
    process has a `_reset_outfiles` method. When a process is prepared, the
    engine removes from its subdivided process output directory only what is
    neither a task subdirectory of the run, nor a path that an output option of
    the run names, nor a directory on the way to one of them; never the process
    output directory itself or anything outside it. The tasks of an array never
    share a value descriptor (see "Task subdirectories" and "Output options").
19. While the run is prepared, `get_process_num_tasks` gives for a process the
    number of tasks that the process has in the run, or stops the preparation:
    whether a process can ask for it depends on which of the two processes have
    an option generator, never on the order in which they define their options,
    and a number of tasks that depends on itself is refused (see "Arrays and
    option generators").
20. The FIFOs that the tasks of a process declare through the same output option
    are read inside the program for every task or for none, and a program in
    which only some of them are is refused (see "Declaring and owning a FIFO").

**Limits and non-goals.**

- **Values.** A value of an option cannot contain a newline or the separator
  `<_ARG_SEP_>`, nor start with `-` and a letter, and the order in which a
  task receives its options is not kept (see "Defining the options of a
  task").
- **What counts as a change.** A changed input is a changed option: a file
  changed in place under the same path is not one, and only the first ten
  tasks of an array are compared. Outdated code is found only on request, by
  the modification time of the modules, and against every module of the
  program (see "Reruns").
- **Cycles through FIFOs.** Whether a loop through FIFOs ends, and whether its
  processes can block waiting for each other, is decided by the protocol
  between the processes, not by the engine (see "Cycles through FIFOs").
- **When one end of a FIFO fails.** The engine does not watch the other end,
  which can block for good; stopping it is left to `debasher_stop` (see "When
  one end fails").
- **An end that goes first.** An end of a FIFO launched before the other,
  because the other only waits for it to start, holds its resources while it
  waits, and the other may then never fit (see "Running both ends together").
- **`aftercorr` in the built-in scheduler.** It is run as `afterok`: the tasks
  of an array wait for the whole producer (see "The built-in scheduler").
- **Ending a task.** A process function that calls `exit`, or that a signal
  kills, ends its whole task, with no `_post` method and no error message from
  the engine (see "Executing a task").
- **Process ids.** A process id that the system gives again to an unrelated
  process can make a process of the built-in scheduler look `IN-PROGRESS`
  (see "Process status").
- **Names.** A process, or a shared directory, may have the name of a file of
  the engine at the top of the output directory, and the engine does not
  refuse it (see "The output directory").
- **Shared subdirectories.** The engine keeps what an earlier run left in a
  shared subdirectory that the run still asks for, and in a shared directory
  that is not a subdivided shared directory; it removes what a task or the user
  leaves in a subdivided shared directory outside its shared subdirectories and
  the paths that output options of the run name; and a task that reads a whole
  shared directory gets no dependency on the tasks that write its shared
  subdirectories (see "Shared subdirectories").
- **One task and many.** The process output directory of an array process is
  shared by its tasks and, without a `_reset_outfiles` method, not emptied
  before each of them: the principle holds only for the tasks that the wiring
  gives a task subdirectory. And when the directory is subdivided, what a
  finished task wrote there outside its task subdirectories and the paths that
  its output options name is removed when the process is prepared again, unless
  it has a `_reset_outfiles` method, though the task does not run again (see
  "Run resources and their life cycle").
- **Option generators.** The engine does not check that an option generator
  gives the same option list every time. A file or a directory that it reads and
  that changes during a run (for a resident program, while it runs and
  relaunches its nodes) changes the options of the tasks launched afterwards,
  against the dependencies and the FIFOs that the engine registered when the run
  was prepared. Keeping such files unchanged is left to whoever runs the
  program: the engine checks that the program is consistent with itself, not
  that what is outside it stays unchanged (see "Arrays and option generators").
- **The number of tasks of another process.** A process without an option
  generator cannot ask, while it defines its options, for the number of tasks of
  another process without one (see "Arrays and option generators").
- **Steps.** The engine keeps no record of a step: it has no status, no log
  of its own and no completion marker, and a new run does not know which steps
  of an earlier one succeeded unless the process records them with step
  markers, which the engine never invalidates on its own account (see
  "Sequential processes").
- **Mirror taps.** A mirror tap forwards lines of text, and relies on opening
  a FIFO for reading and writing, which POSIX leaves undefined (see "Mirror
  taps").
- **Resident programs.** Their guarantees are those of
  `doc/design_doc_resident.md`, which change or replace several of the above.

# Future work

What is known to be missing from the design, or left open by it:

- **Watching the ends of a FIFO.** When one end of a FIFO fails, the built-in
  scheduler could stop the other, instead of leaving it blocked until someone
  runs `debasher_stop`.
- **Resources of an end that goes first.** The end of a FIFO that is launched
  before the other could have the resources of both reserved, or both could be
  launched in the same round in dependency order, so that the other end always
  fits.
- **`aftercorr` task by task.** The built-in scheduler could launch each task
  of an array as soon as its counterpart has succeeded, as Slurm does.
- **Portable mirror taps.** A mirror tap that does not rely on opening a FIFO
  for reading and writing, which POSIX leaves undefined, so that mirror taps
  work on other systems than those on which the engine is checked (Linux,
  macOS, and Windows under WSL2, which is a Linux system).
- **Finer change detection.** Comparing the contents of input files, all the
  tasks of an array, and, for outdated code, only the module that defines each
  process and the external scripts of aliases.
- **Dependencies by containment.** An input whose value is a directory gets no
  dependency on the processes whose output options hold paths inside it, such
  as a process that reads a whole shared directory and the tasks that write its
  shared subdirectories, and has to be ordered with explicit dependencies,
  which replace all its inferred ones (see "Explicit dependencies"). The engine
  could infer an `afterok` dependency of such an input on those processes, so
  that the options stay the one source of the dependencies; two processes that
  each read the directory and write into it would then make a cycle, which
  `processdeps=none` would still allow. Explicit dependencies that add to the
  inferred ones, instead of replacing them, would serve too, at the cost of
  declaring them by hand.
- **Processes that left the program.** `debasher_exec` could refuse to start
  in every run, and not only in a run with a subdivided shared directory,
  while a process that an earlier run had, and that the program no longer has,
  is still running, as it does for the processes of the program.
- **Reserved names.** Refusing a process or a shared directory whose name is
  that of a file of the engine in the output directory.
- **Choosing the tests to run.** Giving the test runner the test files, or a
  filter, so that it runs only some of the tests of a program.
- **Sequential processes in the web UI.** The web UI neither shows the
  sequential processes of a program nor keeps them when it saves the program.
- **Gathering the runs of a batch.** `debasher_exec_batch` executes a file of
  `debasher_exec` commands, one per line, each a run with its own output
  directory, at most a given number at the same time, such as one run of the
  same program for each sample of a sample sheet. A step that combines the
  results of every run, such as a report over all the samples, has to be
  launched separately once the batch ends. `debasher_exec_batch` could take a
  final command, like the hook of `-k` but run once for the whole batch, and
  give it a manifest, a file with the output directory of every run of the batch
  (where `-o` moved it, and those of the runs that an earlier launch of the
  batch completed included), one per line. Left open: whether the manifest lists
  only the runs that completed (within the tolerance of `-u`) or every run with
  its status, whether the final command runs when some runs failed or the batch
  stopped before launching them all, and whether its result counts in the exit
  status of the batch.
