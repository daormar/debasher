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

DeBasher is a flow-based programming extension for Bash. Flow-based
programming builds a program as a network of components that exchange data
through connections defined outside them: the order in which the components
run follows from the flow of data between them, not from a sequence of steps
written by hand, and components that do not depend on each other run in
parallel. In DeBasher a component is a process, a set of Bash functions with
named input and output options; a connection is an input option that takes the
value of an output option of another process; and a program is the set of
processes that a module adds. The engine infers the dependencies between
processes from their connections, since a process that reads a file written by
another waits for it. Data can also stream between two processes through a
FIFO while both run, which lets a program hold cycles that the dependency
graph never sees.

The engine is language agnostic. Bash is the language in which processes are
declared and connected, but the code of a process can be written in Python, R,
Perl or Groovy, embedded in the module or kept in a file of its own, or be any
program that a Bash function runs. A process receives a list of options and
produces files, values or data written into a FIFO, and nothing in that
contract depends on the language of its code.

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
"Architecture" follows a program from its module to its running processes,
and says what lives in memory and what on disk. "Modules and programs"
describes how modules load, what a process is made of and how a program is
composed. "Options" describes how a task gets its options and how options
connect processes, and "The dependency graph" how the engine derives the order
of the processes from them. "FIFOs" describes streaming between processes.
"Scheduling" presents the scheduler abstraction and its two implementations,
and "Running a process" what happens from the launch of a process to the end
of its tasks. "The state of a run" describes the output directory, the status
of a process, reruns and the tools that read a run. "Guarantees and non-goals"
gathers the guarantees stated along the way, and "Future work" lists what is
known to be missing.

# Glossary

The precise meaning of the words this document uses, grouped by topic.
Identifiers in backticks are names that exist in the code. A path written
without a leading directory, such as `__exec__` or `program.procspec`, is
relative to the output directory of the run.

## Modules and processes

- **flow-based programming** (programación basada en flujos): building a
  program as a network of components that exchange data through connections
  defined outside them, so that the flow of data decides the order in which
  they run.
- **module** (módulo): a Bash file that defines processes and module methods,
  loaded with `load_debasher_module`. A module that several others load is
  loaded only once.
- **module search path** (ruta de búsqueda de módulos): where a module given by
  a relative name is looked for: the current directory, then each directory of
  `DEBASHER_MOD_DIR`, then the directory where DeBasher is installed.
- **module method** (método de módulo): a function `<module>_<suffix>` that the
  engine calls on a module: `_document`, `_shared_dirs`, `_program` and
  `_program_type`.
- **program file** (fichero del programa): the module given to `debasher_exec`
  with `--pfile`, whose `_program` method defines the program.
- **program** (programa): the set of processes that the `_program` method of
  the program file adds, directly or through subprograms.
- **general program** (programa general): a program whose program file declares
  no program type, or declares `general` in its `_program_type` method: its
  processes run to completion, on any scheduler. The only type of program this
  document covers.
- **resident program** (programa residente): a program whose program file
  declares the type `resident`: long-lived, stateful processes joined by FIFOs,
  described in `doc/design_doc_resident.md`.
- **subprogram** (subprograma): the processes that the `_program` method of
  another module adds to the program, called through `add_debasher_program`.
- **process** (proceso): a named unit of work of a program, a set of functions
  that share its name as a prefix, added to the program with
  `add_debasher_process`.
- **qualified name** (nombre cualificado): a process name with dot-separated
  qualifiers (`org.namespace.name`), which keeps apart the processes of
  different modules.
- **process method** (método de proceso): a function `<process>_<suffix>` that
  the engine calls at a given moment, such as `_define_opts`,
  `_explain_cmdline_opts`, `_skip`, `_post` or `_reset_outfiles` (see
  "Processes and their methods").
- **process function** (función del proceso): the method with no suffix, named
  as the process itself, which does the work of each task.
- **heredoc process** (proceso heredoc): a process whose code is in Python, R,
  Perl or Groovy, given in a `_heredoc_py`, `_heredoc_r`, `_heredoc_perl` or
  `_heredoc_groovy` method and run by the interpreter of that language.
- **alias** (alias): a process that runs, under its own name and options, the
  code of another process (the `alias` additional specification) or of an
  external script (`ext_alias`).
- **process specification** (especificación del proceso): what
  `add_debasher_process` records about a process: its computational
  specifications and its additional specifications.
- **computational specification** (especificación computacional): a resource
  that a process asks for: `cpus`, `mem` and `time`, always given, and
  `nodes`, `account`, `partition` and `throttle`.
- **additional specification** (especificación adicional): an attribute that
  changes how the engine treats a process: `processdeps`, `force`, `alias`,
  `ext_alias` and `alias_opt_map`.

## Options and tasks

- **option** (opción): a word of the form `-name` or `--name` given to a task,
  followed by its value unless it is a flag.
- **flag** (flag): an option with no value, which the engine tells apart from
  an option whose value is empty.
- **output option** (opción de salida): an option whose name starts with `-out`
  or `--out`: its value names something that the task produces.
- **input option** (opción de entrada): an option that is not an output option.
- **option list** (lista de opciones): the options of one task, which the
  `_define_opts` method of its process builds and registers with
  `save_opt_list`.
- **task** (tarea): one execution of the process function with one option list.
- **array process** (proceso array): a process with more than one task. Each
  task has a **task index** (índice de tarea), from 0.
- **option generator** (generador de opciones): a process whose
  `_generate_opts_size` method gives its number of tasks and whose
  `_generate_opts` method builds the option list of one task whenever the
  engine asks for it, instead of registering every option list in advance.
- **command line option** (opción de línea de comandos): an option whose value
  a process takes from the command line of `debasher_exec`, which the process
  marks as one in its `_identify_cmdline_opts` method, or declares in the
  older `_explain_cmdline_opts` method.
- **connection** (conexión): an input option defined with
  `define_opt_from_proc_out` or `define_opt_from_proc_task_out`, which takes
  the value of an output option of another process.
- **output descriptor** (descriptor de salida): the placeholder that a
  connection holds when it is defined, replaced by the value of the connected
  output option when the option list of the task is loaded.
- **value descriptor** (descriptor de valor): a file in the process output
  directory, named by an output option, into which a task writes a value with
  `write_value_to_desc`, so that a connected task reads the value rather than
  the path.
- **shared directory** (directorio compartido): a directory that a module
  declares in its `_shared_dirs` method, created in the output directory before
  any process runs, whose absolute path every process gets with
  `get_absolute_shdirname`.
- **fanout family** (familia de fanout): an option name ending in `ith` in the
  `_explain_opts` method of a process, such as `-outfith`, which stands for the
  numbered options `-outf0`, `-outf1`, ... that its tasks define.

## Dependencies

- **dependency** (dependencia): a condition on another process, the
  **producer** (productor), that the tasks of a process wait for before they
  are launched.
- **dependency type** (tipo de dependencia): what a dependency waits for:
  `none`, nothing; `after`, the producer has started; `afterok`, every task of
  the producer has succeeded; `afternotok`, the producer has failed;
  `afterany`, the producer has ended, whatever its result; `aftercorr`, the
  task of the producer with the same task index has succeeded.
- **inferred dependency** (dependencia inferida): a dependency that the engine
  derives from an input option whose value is an absolute path that an output
  option of another process holds: `afterok`, or `aftercorr` between two array
  processes at the same task index, and `none` when the path is a FIFO.
- **dependency merge** (fusión de dependencias): combining two dependency
  types on the same producer into the weakest type that asks for everything
  both of them ask for, or failing when no run of the producer can satisfy
  both.
- **option dependency method** (método de dependencias de opción): the process
  method `_define_opt_deps`, which gives the dependency type of one option on
  one producer in place of the inferred one.
- **explicit dependencies** (dependencias explícitas): the `processdeps`
  additional specification, which replaces every inferred dependency of the
  process.
- **dependency graph** (grafo de dependencias): the processes as vertices and
  every dependency whose type is not `none` as an edge from the producer. It
  has to be acyclic.
- **topological order** (orden topológico): an order of the processes in which
  every process comes after the producers it depends on.
- **process graph** (grafo de procesos): the processes joined by all their
  connections, FIFOs included, which `debasher_exec` draws only when asked to
  (`--gen-proc-graph`).

## FIFOs

- **FIFO** (FIFO): a named pipe, `__fifos__/<owner process>/<name>`, through
  which one task streams data to another while both run.
- **FIFO owner** (propietario de la FIFO): the task that defines the FIFO with
  `define_fifo_opt` or `define_fifo_opt_generator`, through the output option
  it writes, except for a FIFO fed from outside the program, which its owner
  reads. The engine creates the FIFO before its owner runs.
- **FIFO reader** (lector de la FIFO): the task of the program that reads the
  FIFO through an input option other than the one through which its owner
  defines it. A FIFO has at most one (`DEBASHER_FIFO_READERS`).
- **external end** (extremo externo): the end of a FIFO that no task of the
  program holds: a reader outside when the owner writes the FIFO, a writer
  outside when the owner reads it (`DEBASHER_EXTERNAL_FIFO_END`).
- **cycle through FIFOs** (ciclo a través de FIFOs): processes that stream to
  one another in a loop, which the engine allows because a FIFO adds no edge
  to the dependency graph.
- **mirror tap** (derivación espejo): for a FIFO defined with `--mirror`, the
  helper that copies every line the owner writes both into the FIFO and into a
  mirror log.
- **shim FIFO** (FIFO intermedia): the FIFO that the owner of a mirrored FIFO
  actually writes, and that its mirror tap reads, under `__fifos__/.mirror`.
- **mirror log** (log espejo): the file where the mirror tap keeps a copy of
  every line, which can be read without taking any line from the reader.

## Runs

- **run** (ejecución): one invocation of `debasher_exec` on an output
  directory, which launches the processes that are not finished or are marked
  to rerun.
- **output directory** (directorio de salida): the directory given to
  `debasher_exec` with `--outdir`, made absolute, which holds everything a run
  writes. Once the processes are launched it is the only source of truth about
  the run.
- **lock** (cerrojo): the `lock` file of the output directory, which
  `debasher_exec` holds while it prepares and launches a run, so that two of
  them never do so on the same output directory at once.
- **process output directory** (directorio de salida del proceso): the
  directory of a process under the output directory, named after the process
  unless its `_outdir_basename` method gives another name. Before each task
  runs, the `_reset_outfiles` method of the process resets it; without that
  method, the directory of a process with a single task is emptied, and that
  of an array process, which its tasks share, is left as it is.
- **exec directory** (directorio de ejecución): `__exec__/<process>`, where the
  engine keeps the process script, the logs, the ids and the completion
  markers of a process.
- **process script** (script del proceso): the self-contained Bash script that
  the engine writes for a process in its exec directory, and that the
  scheduler runs for each of its tasks.
- **execution context** (contexto de ejecución): `.exec_context.sh`, the
  variables and functions of the shell of `debasher_exec` once the program is
  defined, with which every process script starts.
- **command line file** (fichero de la línea de comandos): `command_line.sh`,
  the command line of the run, with the program file resolved and the
  scheduler recorded, from which the tools reload the program.
- **final process specification** (especificación final de procesos):
  `program.procspec`, the process specifications with their dependencies
  filled in. The tools take the set of processes of a run from it.
- **scheduler** (planificador): what launches the tasks of a process once its
  dependencies hold: the built-in scheduler or the Slurm scheduler.
- **built-in scheduler** (planificador integrado): the scheduler that runs
  tasks on the local machine within a budget of CPUs and memory, choosing
  which ones to launch as a knapsack problem.
- **Slurm scheduler** (planificador Slurm): the scheduler that submits each
  process to Slurm as a job, or as a job array for an array process, with its
  dependencies mapped to those of Slurm.
- **attempt** (intento): one submission of a process to Slurm. A
  comma-separated list of `mem` or `time` values gives each attempt a value of
  its own.
- **completion marker** (marca de fin): the `.finished` file that a task writes
  in the exec directory when it ends successfully, or when the `_skip` method
  of its process skips it.
- **process status** (estado del proceso): the state of a process that the
  engine derives from its exec directory: `TO-DO`, no process script yet;
  `IN-PROGRESS`, the scheduler still holds one of its ids; `FINISHED`, every
  task has a completion marker; `UNFINISHED_BUT_RUNNABLE`, for the built-in
  scheduler only, an array process with tasks still to launch and none
  running; `UNFINISHED`, any other case.
- **rerun mark** (marca de reejecución): the decision to run a process again
  although it has run before, for a reason (forced, changed input, outdated
  code, the other end of one of its FIFOs runs again), propagated to the
  processes that depend on it and to the other ends of its FIFOs.

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
4. It refuses to go on while a process of a previous run on the same output
   directory is still in progress.
5. It builds the option list of every task, through the `_define_opts` method
   or the option generator of each process, and resolves the output
   descriptors of the connections. It writes the option list of every task of
   a process without an option generator into `.sched_opts`, and registers the
   owner and the reader of every FIFO (see "Options" and "Declaring and owning
   a FIFO").
6. It infers the dependencies of every process, writes the final process
   specification into `program.procspec` and sorts the processes in
   topological order, which fails if the dependency graph has a cycle (see
   "The dependency graph").
7. It creates the shared directories, and, when asked to, the Conda
   environments and the Docker images of the processes (see "Conda and Docker
   environments").
8. It marks the processes to rerun (see "Reruns").
9. It writes the command line file and the execution context.
10. It hands the processes to the scheduler. Before a process is launched,
    its exec directory is prepared and its FIFOs are created; when it is
    launched, its process script is written, and the scheduler runs the
    script for each task of the process once the dependencies of the task
    hold (see "Scheduling" and "Running a process").

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
is composed of subprograms, and what the engine records about each process.

## Modules and how they load

A module is a Bash file, and its name is the name of the file without the
`.sh` extension. The engine finds the methods of a module by that name: the
module `mymod.sh` has its program in `mymod_program`, its shared directories in
`mymod_shared_dirs`, and so on. A module is loaded with `load_debasher_module`,
which a module calls at its top level to load the modules it builds on, and
which `debasher_exec` calls on the program file.

**Finding a module.** An absolute path is taken as it is. A relative name is
looked for in the directories of the module search path in order, the current
directory first and then each directory of `DEBASHER_MOD_DIR` (a list
separated by colons), and the first file found wins, so that a module in the
current directory is never shadowed by one of the same name elsewhere. In each
directory the engine tries the name as given and the name with `.sh`. It then
looks one level below the directory for a program saved by the web UI, which
it accepts only when the directory of the file holds a
`.debasher/program.json` whose program has the same name, so that an unrelated
file with the same name in some subdirectory is never taken for the module. A
name found nowhere is looked for, last, in the directory where DeBasher is
installed. The program file given to `debasher_exec` with `--pfile` is resolved
in the same way, and the command line file records the absolute path it
resolved to, so that the tools that later read the run do not depend on the
module search path of whoever runs them.

**Loading a module.** A module is sourced into the shell of the tool that loads
it, with the directory of the module as the current directory while it loads.
The modules it loads in turn are therefore looked for first next to it, and
not in the directory from which `debasher_exec` was run. A module is identified
by the absolute path of its file and is loaded only once: loading it again, as
two modules that build on a third one do, has no effect. A module that is asked
for while it is still loading, because modules load each other in a cycle, is
refused, and the error names the whole cycle. The engine keeps the loaded
modules in the order in which they finish loading, so that every module comes
after the modules it loads.

**What loading means for a run.** Everything that a module does at its top
level, defining functions and variables and loading other modules, happens in
the shell of `debasher_exec`, once, while the run is prepared. No task loads a
module (see "Architecture"): what the top level of a module defines reaches the
tasks through the execution context, and code at the top level that does
something else, such as printing or creating a file, runs while the run is
prepared and never in a task. Besides `debasher_exec`, only the tools that
run a process function outside a run (`debasher_exec_process`) or document a
module (`debasher_doc_mod`), and the tool that resets a resident program, load
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
| `_explain_opts` | to list the options of the program (`--show-cmdline-opts`) and to check the options that a task defines | the options of the process are not checked |
| `_identify_cmdline_opts` | together with `_explain_opts`, to mark which options are command line options | the process has no command line options |
| `_explain_cmdline_opts` | an older form of the two methods above, whose options are all command line options | the two methods above are used |
| `_define_opt_deps` | while the dependencies are inferred, for each option on each producer | the inferred dependency type is used |
| `_skip` | by the task, before the process output directory is reset, with the options of the task | the task is never skipped |
| `_reset_outfiles` | by the task, before the process function, with the options of the task | the default reset (see "Executing a task") |
| `_post` | by the task, after the process function, whether it failed or not | nothing runs after the process function |
| `_outdir_basename` | whenever the process output directory is needed | the directory is named after the process |
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
other methods of the process are still Bash functions of its own.

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

Only the processes that some `_program` method adds are part of the program. A
module can define processes that no program adds; their functions are loaded,
and reach the execution context, but the engine never schedules them.

While a `_program` method runs, the engine records, for each process it adds,
the directory of the module that the method belongs to. A relative path that
belongs to a process, that of an external alias or the value of an option
defined with `define_infile_opt`, is resolved against that directory, which is
the directory of the module that added the process to the program, not
necessarily the one that defines its functions.

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

# Options

Everything that a task knows about its inputs and its outputs reaches it as
options, and the engine learns the structure of the program from the same
options: an input option whose value another process produces makes a
dependency (see "The dependency graph"), and an option whose value is a FIFO
joins two tasks (see "FIFOs"). This section describes how the option list of a
task is built, what makes an option an output, how options connect processes,
how a program takes values from its command line, how a process gets more than
one task, and how the option list of a task travels from `debasher_exec` to the
task.

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
comes from: a literal (`define_opt`, `define_flag`), a file shipped with the
program (`define_infile_opt`), the command line (`define_cmdline_opt` and its
variants), the process specification (`define_procspec_opt`), an output option
of another process (`define_opt_from_proc_out`), a value descriptor
(`define_value_desc_opt`), a shared directory (`define_opt_from_shared_dir`) or
a FIFO (`define_fifo_opt`, see "Declaring and owning a FIFO").

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
`.__VAL_DESCRIPTOR__<option>` in the process output directory, into which the
task writes the value with `write_value_to_desc`. A task connected to that
option receives the path, and `read_opt_value_from_func_args` gives it the
content of the file instead, since the option through which it reads it is not
an output option. The path is absolute, so the reading task depends on the
writing one like on any file it produced, and reads the value only once it has
been written.

**Input files and shared directories.** `define_infile_opt` gives an option the
path of a file shipped with the program, resolved against the directory of the
module that added the process (see "Programs and subprograms") and required to
exist. A shared directory is declared by a module, with `define_shared_dir` in
its `_shared_dirs` method and never from a process method, and created in the
output directory before any process runs. The `_shared_dirs` method of every
loaded module is called, whether or not the module adds processes to the
program. `define_opt_from_shared_dir` gives an option its absolute path. A
shared directory is not an output of any process, so using it creates no
dependency: processes that share one coordinate through it by other means.

## Connections between processes

`define_opt_from_proc_out <option> <process> <output option>` defines an input
option that takes the value of an output option of the first task of another
process, and `define_opt_from_proc_task_out` does the same for a task of a
given index. The option being defined may not be an output option, and the
connected one has to be.

The option does not get its value when it is defined, since the other process
may not have defined its options yet: `_define_opts` is called for the
processes in no particular order. It holds an output descriptor instead, a
placeholder that names the process, the task and the option. Once every process
has defined its options, the engine replaces each output descriptor with the
value of the connected option, taken from the option list of that task, or by
calling the option generator of the connected process for that task. A
connection to a process, task or option that does not exist resolves to
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
to name an existing file and make its path absolute; and `get_cmdline_opt`
returns the value for the method to compute with.

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
mandatory, with `explain_cmdline_opt`. The declarations document the program:
`debasher_exec --show-cmdline-opts` lists the command line options of every
process, by category, and `debasher_doc_mod` documents them. Whether a mandatory
option is given is decided by `define_cmdline_opt` when the options are built,
not by the declaration.

## Arrays and option generators

**Arrays.** A `_define_opts` method that calls `save_opt_list` several times
defines one task per call, in order: the process is an array process, and each
option list is that of the task with the next task index. Every option list is
built while the run is prepared and kept until the options are written for the
tasks.

**Option generators.** A process with an option generator does not build its
option lists in advance. Its `_generate_opts_size` method, called with the
same arguments as `_define_opts`, prints the number of tasks, and its
`_generate_opts` method, called with those arguments and a task index, builds
the option list of that one task and hands it to `save_opt_list`, which returns
it instead of registering it. The engine calls the generator whenever it needs
the options of a task: while the run is prepared, to record the values that the
task produces, to find its FIFOs, to infer its dependencies and to resolve the
connections of other processes to it, and again inside the task itself (see
"How option values reach a task"). A generator is therefore called several
times for each task, in different shells, and has to give the same option list
every time for the same command line and task index. A FIFO defined by a
generator is defined with `define_fifo_opt_generator`, which takes the task
index; `define_fifo_opt` is refused inside a generator.

**Checking the options against their declaration.** When a process has an
`_explain_opts` or an `_explain_cmdline_opts` method, the options of its first
task are checked against the declared ones while the run is prepared. An option
that the task defines but the process does not declare stops the preparation, as
it usually means a typo or a declaration out of date; a declared option that the
first task does not define only gives a warning, since an option added only when
it is given on the command line is often absent. Only the first task is checked,
and the check assumes that the tasks of an array have the same option names. A
process whose number of options depends on the run, such as `-outf0`, `-outf1`,
and so on, declares the whole fanout family once, as `-outfith`, and any option
made of the prefix and a number matches it.

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

## Inferring dependencies from options

## Dependency types and how they merge

## Explicit dependencies

## Topological order and cycles

# FIFOs

## Declaring and owning a FIFO

## Running both ends together

## Cycles through FIFOs

## Mirror taps

## When one end fails

# Scheduling

## The scheduler abstraction

## The built-in scheduler

## The Slurm scheduler

# Running a process

## Preparing a run

## The process script: how code travels

## Executing a task

## Conda and Docker environments

# The state of a run

## The output directory

## Process status

## Reruns

## Tools that read a run

# Guarantees and non-goals

# Future work
