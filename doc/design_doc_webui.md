---
title: Design of the web UI
fontsize: 11pt
geometry: margin=2cm
numbersections: true
toc: true
toc-depth: 2
---

This document describes the design of the DeBasher web UI and the guarantees
it gives. Where a mechanism is not yet fully designed or built, its own section
says so.

# Introduction

*To be written.* What the web UI is for (building, running and observing
DeBasher programs from a browser, without writing the Bash module by hand),
who uses it, and what this document covers: the parts of the design that carry
an invariant (the program model, the translation between the model and a
module, persistence, execution and observation), not the layout of each dialog.
It then says how the document is organized: first the design as it is today,
then the extension to resident programs, which is designed here before it is
built (see "Resident programs in the web UI"), and relies on the design of
resident programs in `doc/design_doc_resident.md`.

# Glossary

The precise meaning of the words this document uses, grouped by topic.
Identifiers in backticks are names that exist in the code. Two words of the
design of resident programs are avoided here on their own, because the web UI
already uses them for something else: a box on the canvas is a **canvas node**,
never a bare "node", and how an option's value is delivered is its **option
channel**, never a bare "channel". Bare, both words keep the meaning they have
in the design of resident programs.

## Program model

- **program model** (modelo del programa): the program as the web UI sees it, a
  tree of plain data defined twice with the same shape, as Pydantic models in
  `api/models.py` and as TypeScript types in `frontend/src/models/`, and sent
  as JSON between the two (see "The program model").
- **program** (programa): the root of the program model (`Program`). It
  becomes one DeBasher module, whose name is the program's name.
- **process** (proceso): one process of the program (`ProgramProcess`), with
  its options, its code and its specifications.
- **option** (opción): one option of a process (`ProgramOption`), named by its
  **label** (etiqueta), the option's name for the engine, such as `-infile`.
- **direction** (dirección): whether an option is an `input` or an `output` of
  its process.
- **data type** (tipo de dato): the type of an option's value: `int`, `float`,
  `string`, `file`, or `None` for a flag, an option that takes no value.
- **option channel** (canal de la opción): how an option's value is delivered,
  independent of its data type (`ProgramOption.channel`): `none` for a literal
  value or a connection, `value_desc` for a value descriptor the engine
  synthesizes, `fifo` for a named pipe, `shared_dir` for a shared directory.
- **shared directory** (directorio compartido): a directory declared at module
  level, which every process that names it resolves to the same absolute path.
- **command line option** (opción de línea de comandos): an option whose value
  the user gives when the program is run (`ProgramOption.commandLine`), rather
  than a value fixed in the program.
- **program options** (opciones del programa): the values given to the command
  line options for the next run (`Program.programOptions`), keyed by label.
- **edge, connection** (arista, conexión): a link from an output option of one
  process to an input option of another (`ProgramEdge`), which makes the
  second read the value of the first (see "Connections").
- **connection sentinel** (centinela de conexión): the value
  `[<process>;<option>]` that a connected input option carries, naming the
  process and the option it reads from.
- **fan-in** (convergencia): more than one connection into the same input
  option.
- **options handler mode** (modo del gestor de opciones): how a process defines
  its options and so how many tasks it runs: `standard`, `array`, `generator` or
  `manual` (see "Options handler modes").
- **task** (tarea): one execution of a process with one set of option values.
  A process in `standard` mode runs one task; one in `array` or `generator` mode
  runs one per element or index.
- **fanout family** (familia de fanout): an option of a `standard` process whose
  label ends in `ith`, such as `-outfith`, which stands for as many numbered
  options (`-outf0`, `-outf1`, ...) as another option of the same process says
  at run time.
- **preamble** (preámbulo): Bash code that the generated module carries
  verbatim before its own functions, typically the `load_debasher_module` lines
  of the modules it builds on.
- **group** (grupo): the processes that "Add program" brings in from another
  module in one operation, which the generated module declares with a single
  `add_debasher_program` while none of them has been edited or removed (see
  "Groups").

## Files and directories

- **home directory** (directorio del programa): the directory where the
  program lives (`Program.homeDir`): its program metadata, its generated script
  and the user files.
- **output directory** (directorio de salida): the directory where a run writes
  its results and the engine keeps its own files for the run
  (`Program.outputDir`).
- **program metadata** (metadatos del programa): the program model saved as
  JSON in `.debasher/program.json` under the home directory.
- **generated script** (script generado): the module that script generation
  writes as `<name>.sh` in the home directory.
- **reserved name**: *to be written* (`is_reserved_name()`).
- **user file**: *to be written* (a file of the home directory that is not a
  reserved name).

## Translation

- **script generation** (generación del script): turning the program model
  into a runnable module (`script_generation.py`).
- **import** (importación): rebuilding the program model from an existing
  module (`program_import.py` and the modules it relies on).
- **round trip**: *to be written* (import followed by generation, or the
  reverse).

## Execution and observation

- **run** (ejecución): one execution of a program by `debasher_exec` on an
  output directory.
- **tab** (pestaña): one browser tab with the web UI open, holding its own
  store.
- **store** (almacén): the state of the frontend in a tab (`ProgramContext`):
  the program being edited and what the tab knows about its runs.
- **run phase** (fase de la ejecución): the state of a run launched from this
  tab, as the tab follows it (`ProgramRunPhase`).
- **process status** (estado de un proceso): the state of each process as
  `debasher_status` reports it for the output directory, whoever launched the
  run; it colors the canvas.
- **FIFO mirror**: *to be written* (the copy of a FIFO's traffic that "Watch
  FIFO" shows).

# Architecture

The web UI has three layers. The **frontend** is a single-page React
application that runs in the browser; it holds the program being edited in its
store and draws it on a canvas, where each process is a canvas node and each
connection an edge between two of them. The **backend** is a FastAPI server
(`api/`) that the frontend reaches over HTTP under `/api`. The **engine** is
not a library of the backend: the backend runs its command line tools
(`debasher_exec`, `debasher_status`, `debasher_stop`, `debasher_doc_mod`, ...)
as subprocesses and reads what they print and the files they leave. It finds
them with `paths.py`: in the directories that the installed `debasher_webui`
launcher exports, else in `engine/` of a build that has not been installed.

The backend groups its endpoints in routers, by what they act on:

- `programs`: save, load and import a program.
- `processes`: validate a process name, and suggest or describe the processes
  that the preamble's modules already define.
- `execution`: run, observe and stop a program, inspect what its processes
  left, talk to its FIFOs, and reset its output directory.
- `program-files`: browse and manage the user files of the home directory.
- `fs`: browse the file system from the dialogs that ask for a path.

One server process serves both the API and the built frontend, which is a single
self-contained `index.html`. `debasher_webui` starts it, listening only on
`127.0.0.1` unless told otherwise. It has no authentication and runs every tool
as the user who launched it, so whoever can reach it can run anything as that
user. During development the Vite server serves the frontend and forwards
`/api` to a backend started by hand.

## The backend keeps no state

The backend keeps nothing between two requests. Every request carries what it
needs, in most cases the whole program model, and the backend acts on the disk
and on the engine's tools and answers. `/run` is the clearest case: it saves
the program, generates its script, starts `debasher_exec --wait` detached, with
its output in `.debasher_webui_run.log` under the output directory, and answers
at once, without keeping a handle on the process. What happened to the run is
asked later of the engine itself, with `debasher_status` on the output
directory.

Two things follow. Restarting the backend loses nothing, since there is nothing
in it to lose. And the backend does not coordinate two tabs that act on the same
directories: the engine's files are the only truth they share, and the guards
against a conflict read them (`/run` refuses to start when `debasher_status`
reports a run in progress on that output directory).

## Where the state lives

The lasting state lives in two places only. The store of each tab holds the
program being edited and what the tab knows about a run it launched. The disk
holds the rest: the home directory keeps the program metadata, the generated
script and the user files, and the output directory keeps what the engine writes
during a run. The frontend uses no browser storage, so a program that has not
been saved is lost when its tab is closed.

A run launched from a tab lives as long as the tab follows it. Closing or
reloading the tab stops it (the tab sends `/api/execution/stop` as it unloads),
and so does leaving the editor for the home screen. A run that the tab did not
launch is observed through the process statuses, but closing the tab never
stops it. Resident programs have to revisit this rule, since their processes are
meant to outlive any tab (see "Resident programs in the web UI").

# The program model

The program model is what the frontend edits, what the backend receives in
every request, what the program metadata stores, what script generation reads
and what import produces. Its two definitions, Pydantic and TypeScript, have to
change together, in the same change.

Every program, process, option and edge has an `id`, a UUID assigned when the
element is created or imported. It is the element's identity inside the model
(edges name processes and options by it) and never reaches the generated
script, which names processes and options by their name and label. Renaming a
process or an option therefore keeps its connections.

A program carries, besides its processes and edges:

- `name`, the module's name: it prefixes the module's own functions
  (`<name>_program`, `<name>_document`, `<name>_shared_dirs`) and names the
  generated script.
- `description` and `preamble`.
- `envVars`, the environment the backend gives the engine's tools, of which only
  `DEBASHER_MOD_DIR` is used today: where to look for the modules the preamble
  loads.
- `homeDir`, `outputDir`, and `sourceDir`, the directory of the module the
  program was imported from (empty if it was not imported).
- `executionOptions`, the scheduler and the other flags given to
  `debasher_exec`, and `programOptions`.
- `sharedDirs`, the shared directories the module declares, and
  `availableSharedDirs`, every shared directory reachable from it, its own and
  those of the modules it loads. Only import fills the second, and script
  generation never writes it.

## Processes and options

A process has a `name`, which is the engine's name for it and follows the
engine's rules (the backend checks it against the same pattern and the same
reserved suffixes as the engine), a `description`, a `position` on the canvas,
its `options`, its `optionsHandler`, its specifications (`computationalSpecs`
and `additionalSpecs`) and its code. The code has three parts: `language` and
`code`, the process's own work (a Bash function, or the source for another
interpreter, which the engine wraps in a function); `additionalMethods`, the
bodies of the other methods a process may define (`_post`, `_skip`,
`_conda_envs`, ...); and the option methods, which script generation derives
from the options and the options handler.

An option has a `label`, a `direction`, a `dataType`, an option channel, a
`description` and a `value`, and four flags: `commandLine` and `mandatory`,
`fromProcessSpec` (its value is an attribute of the process's own
specifications, such as `cpus`) and `mirror` (a copy of what the process writes
into a FIFO is kept in a log that the web UI can show without taking data from
the reader). An option's direction always follows from its label, by the
engine's convention: output if the label starts with `-out` or `--out`, input
otherwise.

What `value` holds depends on the other fields, and is always what the
generated script has to write, not what the process will receive at run time:

- a literal value, for an option with option channel `none` that is neither
  connected nor a command line option;
- a connection sentinel, for a connected input (see "Connections");
- the FIFO's name, for option channel `fifo`;
- the shared directory's name, never a path, for option channel `shared_dir`;
- the attribute's name, such as `cpus`, when `fromProcessSpec` is set;
- nothing that script generation uses, for a command line option, whose value
  comes from the program options at run time.

A few combinations make no sense, and the model keeps them out. A flag is
always an input. `mirror` only applies to a `fifo` output. `value_desc` only
applies to an output: the consumer of a value descriptor just connects to it.
`fromProcessSpec` and `commandLine` exclude each other. A fanout family only
exists on a `standard` process, and names in `countSourceOptionId` a command
line option of the same process that gives the count. The editor offers only
the valid combinations, and script generation checks again those whose
violation would produce a wrong module, refusing to generate it.

## Connections

An edge goes from an output option to an input option of another process. The
edges are the one source of truth about what is connected. The value of a
connected input, its connection sentinel, is derived from them: the store
recomputes it from the edges after every change to the program, so renaming a
process or an option never leaves a sentinel that names the old one, and a
program loaded with values out of step with its edges is repaired on load.
Script generation also reads the edges, and emits one definition per edge; the
sentinel is only its fallback when no edge matches. A `shared_dir` input is the
exception: its value stays the name of its directory, and its edges only
document on the canvas a dependency that the engine derives on its own from
every writer resolving to the same path.

The canvas accepts a new connection only when it keeps the program valid for
the engine:

- It goes from an output to an input of a different process. The canvas
  draws no connection from a process to itself.
- An output may feed any number of inputs, but an input accepts only one
  connection, since the engine could not tell which value it should take. The
  exception is fan-in between `shared_dir` options that name the same
  directory, which all resolve to the same path.
- A `shared_dir` option pairs with another `shared_dir` option only when both
  name the same directory.
- A fanout family pairs only with a process in `array` or `generator` mode,
  and never with another fanout family.

Nothing forbids a cycle. Every cycle has at least one edge whose target sits at
or above its source on the canvas, and the canvas routes such an edge around
the processes instead of through them. For two processes that answer each other
through FIFOs, it instead moves the handles of the answering pair to the other
side, so that the edge stays short.

## Options handler modes

The options handler mode says how a process defines its options, and so how
many tasks it runs:

- `standard`: one task. Script generation writes one `_define_opts` function
  that defines every option once.
- `array`: one task per element of a Bash array named `array`, which the
  user's code (`arrayCode`) builds. The generated `_define_opts` loops over
  the array with the index `idx`, which option values can use.
- `generator`: one task per index, from 0 up to the count that the user's code
  (`generatorSizeCode`) prints. Script generation writes that code as
  `_generate_opts_size`, and a `_generate_opts` that the engine calls once per
  index, with the index in `task_idx`.
- `manual`: the user writes the option definition function whole
  (`manualCode`), and script generation copies it as it is. The options are
  still explained and documented from the model, but they are not used to
  define the option values.

When both ends of a connection run in `array` or `generator` mode, each task
reads the output of the task with the same index at the other end. In every
other case the connection names the output of the source process as a whole,
not that of one of its tasks: the model does not know the tasks of a `manual`
process, and a `standard` process has only one.

## Groups

"Add program" brings every process of another module into the program in one
operation, and marks each of them with the same `groupSource`: the module's
name, a `groupId` shared by all of them and the `groupSize`. While all the
processes of a group are still present and none has been edited, script
generation declares them with a single `add_debasher_program` of that module,
and the module stays the one place where they are defined. The engine cannot
express a module minus one process, or with one process changed, so editing the
content of any process of the group, removing one, or connecting an input of
one to something new first asks the user, and then dissolves the whole group:
its processes are then generated one by one, like any other.

# From the model to a module: script generation

*To be written.* How `script_generation.py` emits a runnable module from a
program: the order of the generated functions, how each part of the model maps
to engine calls, and what it refuses to generate.

# From a module to the model: import

*To be written.* How `program_import.py` rebuilds a program from an existing
module, through the documentation the engine extracts from it
(`debasher_doc_mod`, `debasher_get_proc_info`) and the parsing of the option
definition functions.

## What the round trip preserves

*To be written.* What is guaranteed to survive importing a module and
generating it again, and what is normalized or lost on the way.

# Persistence and the program's directories

*To be written.* The home directory and the output directory, what the UI
writes in each, the program metadata, the generated script, the boundary
between reserved names and user files that the program files panel respects,
and the guards that keep a save or a reset of the output directory from
destroying work (for example, no save while a run is in progress).

# Execution and observation

*To be written.* How the backend launches a run and returns at once, how the
frontend learns how it went (the run phase and the process statuses, both by
polling), and the tools behind each inspection action: a process's output and
scheduler output, its resolved options, the FIFO mirror, writing into and
reading from a FIFO ("Talk to FIFOs"), and stopping a run or one process.

# Frontend state and the canvas

*To be written.* The single store (`ProgramContext`), the conversion between
the model and the canvas (`reactFlowAdapter.ts`), and which parts of the canvas
state belong to the model (positions) and which do not (selection, colors).

# Guarantees and non-goals

*To be written.* The guarantees the web UI gives today, stated in one place,
and what it deliberately does not try to do.

# Resident programs in the web UI

*Not yet designed.* The extension of the web UI to resident programs. A
resident program is not a run that starts and finishes: its processes stay
alive, keep state, recover from crashes and go through rounds. The UI has to
build such a program, launch it, observe it while it lives and act on it.

## Declaring a resident program

*To be written.* The program type, the fifo tags (`--control`, `--external`),
the `Supervisor` and its trigger ports, and how the model, script generation
and import represent them.

## The canvas of a resident program

*To be written.* How cycles, control and external ports, and the `Supervisor`
are drawn, and how a self-loop is drawn, since the canvas draws none today.

## Launching, stopping and resetting

*To be written.* What replaces the actions of a general program:
`debasher_stop_resident` for an orderly stop, `debasher_reset_resident` for a
clean start, and resuming from the checkpoints of the last stop.

## Rounds and snapshots

*To be written.* Starting a round from the UI (`debasher_snapshot_resident`)
and showing the rounds that have closed.

## Observing a live program

*To be written.* What the UI shows of a living program and where it reads it
from: the state of each node, its incarnations and relaunches, its checkpoints
and its input log, and the failures the program reports loudly.

## Talking to a live program

*To be written.* Writing into external and control ports from the UI, using
the control ports file to find them.

## The backend and a long-lived program

*To be written.* What happens to a resident program when the backend or the
browser tab goes away and comes back, given that the backend keeps no state
and that a tab stops the run it launched when it closes.

# Future work

*To be written.*
