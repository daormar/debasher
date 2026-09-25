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

The web UI lets a person build, run and observe a DeBasher program from a
browser, without writing its module by hand: each process is a box on a
canvas, each connection an edge between two of them, and the web UI translates
the drawing into a module and runs it with the engine's own tools. This
document describes the parts of its design that carry an invariant: the
program model, the translation between the model and a module, the program's
directories, and how a program is run and observed. It does not describe the
layout of each dialog or the look of the canvas.

**Scope: general and resident programs.** The engine runs two types of program,
general and resident (see the Glossary), and the web UI knows only the first
one today. Every section before "Resident programs in the web UI" describes
the design for general programs, and what it says holds for them. A resident
program, whose design is in `doc/design_doc_resident.md`, follows rules of its
own in several places: it is always run by the built-in scheduler, its
processes are meant to outlive any browser tab, and it is stopped, snapshotted
and reset with tools of its own. The section on resident programs says, for
each part of the design described before it, whether it applies to resident
programs unchanged, changes, or is replaced, and nothing in the earlier
sections should be read as holding for resident programs unless that section
says so.

The document is organized as follows. The Glossary defines the terms it uses.
"Architecture" presents the three layers of the web UI and where its state
lives. "The program model" describes the data that the frontend edits and the
backend receives. The two sections that follow describe the translation
between the model and a module in each direction, and what survives a round
trip. "Persistence and the program's directories" describes what the web UI
keeps on disk, and "Execution and observation" how it runs a program and
follows it. "Frontend state and the canvas" describes the frontend's own
state, and "Guarantees and non-goals" gathers the guarantees stated along the
way. "Resident programs in the web UI" designs the extension to resident
programs before it is built, and "Future work" lists what is known to be
missing.

# Glossary

The precise meaning of the words this document uses, grouped by topic.
Identifiers in backticks are names that exist in the code. Two words of the
design of resident programs are avoided here on their own, because the web UI
already uses them for something else: a box on the canvas is a **canvas node**,
never a bare "node", and how an option's value is delivered is its **option
channel**, never a bare "channel". Bare, both words keep the meaning they have
in the design of resident programs.

## Program model

- **general program** (programa general): a DeBasher program whose module
  declares no program type, or declares `general`: a set of processes that a
  run executes to completion, on any scheduler. Every section before
  "Resident programs in the web UI" is about general programs.
- **resident program** (programa residente): a program whose module declares
  the type `resident` in its `_program_type` function: long-lived, stateful
  processes joined by FIFOs, always run by the built-in scheduler, as described
  in `doc/design_doc_resident.md`.
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
  the user gives when the program is run (`ProgramOption.commandLine`), and
  which takes it from nowhere else: the engine refuses a process that defines
  it with a value of its own.
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
- **group** (grupo): the processes that "Add program" brings in, in one
  operation, from another program saved with the web UI, which the generated
  module declares with a single `add_debasher_program` while none of them has
  been edited or removed (see "Groups").

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
- **reserved name** (nombre reservado): a file or directory name that the
  engine or the web UI manages, by a rule rather than a list
  (`is_reserved_name()`): a name that starts with a dot, a name wrapped in
  double underscores (`__exec__`, `__fifos__`, ...), and `command_line.sh`.
- **user file** (fichero del usuario): a file or directory of the home
  directory whose path has no reserved name, which the user manages through
  the program files panel.
- **run log** (log de la ejecución): `.debasher_webui_run.log` in the output
  directory, where the web UI sends everything that `debasher_exec` prints
  during a run it launched.

## Translation

- **script generation** (generación del script): turning the program model
  into a runnable module (`script_generation.py`).
- **import** (importación): rebuilding the program model from a module that
  has no program metadata, such as one written by hand (`program_import.py`
  and the modules it relies on).
- **module documentation** (documentación del módulo): the Markdown that
  `debasher_doc_mod` prints about a module after loading it: its name,
  description and shared directories, and for each process its options, its
  option definition functions, its code, its methods and its specifications.
- **canonical form** (forma canónica): how Bash prints a function back with
  `declare -f`, without its comments and with its own indentation. Two
  functions with the same canonical form behave the same.
- **verbatim source** (fuente literal): a function exactly as it is written in
  its file, comments and indentation included, as
  `debasher_get_verbatim_func_source` reads it.
- **round trip** (ida y vuelta): script generation followed by import, or
  import followed by script generation (see "What the round trip
  preserves").

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
- **run in progress** (ejecución en curso): the state of an output directory
  in which `debasher_status` reports at least one process as `IN-PROGRESS`,
  whoever launched the run.
- **FIFO mirror** (espejo de una FIFO): the log in which the engine copies every
  line that a process writes into a FIFO defined with `--mirror`, which can be
  read without taking the data from the FIFO's reader.
- **unconnected FIFO** (FIFO sin conectar): a FIFO option with no edge and
  whose label does not name a fanout family, whose other end is left to
  someone outside the program, such as a person using "Talk to FIFOs".

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
`fromProcessSpec` and `commandLine` exclude each other, and a command line
option has option channel `none`, since its value comes only from the command
line. A fanout family only
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

"Add program" brings every process of another program saved with the web UI
into the current one, in one operation. It reads that program's metadata from
its home directory, like loading does, not its module, and marks each of its
processes with the same `groupSource`: the other program's name, a `groupId`
shared by all of them, the `groupSize`, and the other program's home
directory, which it also adds to `DEBASHER_MOD_DIR` so that the engine finds
its generated script. While all the processes of a group are still present and
none has been edited, script generation declares them with a single
`add_debasher_program` of the other program's module, and that module stays
the one place where they are defined. The engine cannot express a module minus
one process, or with one process changed, so editing the content of any
process of the group, removing one, or connecting an input of one to something
new first asks the user, and then dissolves the whole group: its processes are
then generated one by one, like any other.

# From the model to a module: script generation

Script generation (`generate_script()` in `script_generation.py`) turns a
program into the text of a DeBasher module. The backend runs it on every save
and before every run, and writes the result as the generated script. It
depends on nothing but the program model, except for one check that queries
the engine (see "Code that a loaded module already provides"). The generated
script starts with the line `# AUTOMATICALLY GENERATED DEBASHER SCRIPT`: the
next save overwrites any change made to it by hand, and the way to bring such a
change into the program is to import the script.

## Layout of the generated module

The generated module holds, in this order:

1. The header line, then the preamble, as it is.
2. `<name>_document`, with the program's description, and
   `<name>_shared_dirs`, with one `define_shared_dir` per shared directory.
3. For each process, in the order of the model: `_document`, `_explain_opts`
   (one `explain_opt` per option, or `explain_flag` for a flag),
   `_identify_cmdline_opts` (one `opt_is_cmdline` or
   `opt_is_non_mandatory_cmdline` per command line option), the option
   definition functions of its options handler mode (see "Option
   definitions"), its code, and one function for each additional method that
   has a body. Code in Bash is written as it is; code in another language
   becomes a heredoc variable `<process>_<suffix>` (`_py`, `_r`, `_perl`,
   `_groovy`), which the engine wraps in a function.
4. `<name>_program`, with one `add_debasher_process` per process, carrying its
   computational specifications (`cpus=... mem=... time=...`) and its
   additional specifications (`force=yes;processdeps=...;alias=...`), or one
   `add_debasher_program` for each group that is still whole.

A function with nothing to say gets the body `:`, since the engine expects it
to exist. What the model holds about runs or about the canvas stays out of the
module: `envVars`, `executionOptions` and `programOptions` go to the engine's
tools when they run (see "Execution and observation"), and positions, ids and
the two directories only matter to the web UI.

## Option definitions

In `standard`, `array` and `generator` mode, script generation writes one
definition for each option (one per edge for a fan-in), taken from the first
rule that applies:

1. A flag: `define_flag`, or `define_cmdline_flag_if_given` if it is a
   command line option.
2. Option channel `value_desc`: `define_value_desc_opt`.
3. Option channel `fifo`: `define_fifo_opt` with the FIFO's name, and
   `--mirror` if `mirror` is set.
4. Option channel `shared_dir`: `define_opt_from_shared_dir` with the
   directory's name, whatever its edges.
5. `fromProcessSpec`: `define_procspec_opt` with the attribute's name.
6. A command line option: `define_cmdline_opt`, or `define_cmdline_infile_opt`
   for a file, with the suffix `_if_given` when it is not mandatory.
7. A connected option: `define_opt_from_proc_out` for each of its edges, or
   `define_opt_from_proc_task_out` with the task index when both ends run in
   `array` or `generator` mode.
8. An input file: `define_infile_opt`, which resolves a relative path against
   the module's own directory, so that a file shipped with the program can be
   named portably.
9. Anything else: `define_opt` with the literal value.

A command line option always gets its definition from rule 6, or from rule 1
for a flag, since one with an option channel other than `none` is refused (see
"What script generation refuses"). A fanout family becomes a loop instead of
one line: it reads the count from its command line option and defines one
option per index, `define_opt` or `define_fifo_opt` on the writing side,
`define_opt_from_proc_task_out` on the reading side.

In `standard` and `generator` mode each definition is written once, in
`_define_opts` or in `_generate_opts`. In `array` mode the generated
`_define_opts` runs the user's code that builds `array`, then defines every
option inside `for idx in "${!array[@]}"`, one task per iteration, even an
option whose value does not depend on `idx`. In `manual` mode the user's
function is written as it is, and the rules above do not apply.

## Values are Bash words, descriptions are text

Option values are written between double quotes as they are, without
escaping. This is deliberate: a value is a Bash word, evaluated when the
options are defined, so it can use the variables that script generation
provides (`${array[$idx]}` in `array` mode, `$i` in a fanout family) and those
of the preamble. It also means that a double quote, a backslash or a `$` meant
literally has to be escaped by the user, and script generation does not check
that the result is valid Bash.

Descriptions (of the program, of each process and of each option) are text,
never expressions, and script generation escapes the characters that keep a
special meaning between double quotes (`\`, `"`, `$` and the backquote). A
description therefore reaches the module documentation exactly as it was
written, and a backquote in it is never run as a command.

## Code that a loaded module already provides

A process imported from a module can carry code that one of the modules its
preamble loads already defines. Before writing the code of each process,
script generation asks `debasher_get_proc_info` for the canonical form of the
process's code as the preamble alone defines it, and for the canonical form of
the process's own code. If both exist and are equal, the generated module
leaves the code out and relies on the loaded module. If either query fails, it
writes the code: the check can only save a duplicate, never lose code. A
process with an `alias` or an `ext_alias` gets no code at all, since the engine
builds its function from the aliased one.

## What script generation refuses

Script generation raises an error, and writes no module, for a program that
would produce a wrong one: an option both `fromProcessSpec` and a command line
option; a command line option with an option channel other than `none`; a
fanout family that is a flag, a command line option or taken from
the process specifications, whose count option is missing or is not a command
line option, whose output is connected, mirrored or uses an option channel
other than `none` or `fifo`, or whose input is not connected to a process in
`array` or `generator` mode; and a connection to a fanout family from a
process in another mode. The save writes the program metadata before it
generates the script, so a program that script generation refuses is still
saved, and the home directory keeps the script of the previous save.

## Environment variables of a program

The environment variables editor shows, besides the program's own `envVars`,
every variable that the module and the modules it loads define. Script
generation serves this too: the backend generates the module into a temporary
directory, gives each process that has no code yet a function that does
nothing (the engine refuses to load a module with a process without code), runs
`debasher_doc_mod --show-all-envvars` on it and discards it. That module never
reaches the home directory, and it skips the check of "Code that a loaded
module already provides", which would be wasted on it.

# From a module to the model: import

Import (`import_program_from_script()` in `program_import.py`) rebuilds a
program from an existing module. It does not interpret the module itself: it
asks the engine, which loads the module and describes it, and reads the answer.
Only the option definition functions and the preamble are read as text. The
imported program is not saved: it opens in the editor, and the user saves it
into a home directory.

Import is how a module that the web UI did not produce enters it: a module
written by hand, without the web UI, or a generated script that was changed
by hand after the web UI wrote it. A program built and saved with the web UI
is never imported: loading it, or adding it to another program with "Add
program", reads its program metadata, which holds the whole program model,
while import can only rebuild what the module says (see "What the round trip
preserves").

## What the engine reports

Import runs `debasher_doc_mod` on the module with every section of the module
documentation turned on, and reads from it the program's name, description and
shared directories, and for each process its description, its explained
options (label, data type, description, command line and mandatory flags), its
option definition functions, its code and its language, its additional
methods and its specifications.

`debasher_doc_mod` learns the processes by loading the module and running its
`_program` function, which has two consequences. The module has to load: the
`DEBASHER_MOD_DIR` given in the import dialog is passed to the engine, and kept
in the program's `envVars` so that it goes on working. And a module that
composes others with `add_debasher_program` comes back flattened: the
processes of the modules it composes become ordinary processes of the imported
program, and are not a group.

The functions in the module documentation are in canonical form, without
comments. Import replaces each one by its verbatim source, read from the module
with `debasher_get_verbatim_func_source`, and keeps the canonical form of a
function whose verbatim source it cannot find. The code of a process may bundle
several functions (the engine includes the helpers of the same file that the
process calls), and each is replaced on its own. A body that the model keeps
apart from its function (`arrayCode`, `generatorSizeCode` and the additional
methods) loses the indentation that all its lines share, since script
generation indents it again when it writes the function back.

## Recovering the options handler

The option definition functions are the one part of a module that import
parses (`option_handler_import.py`). It matches them against a closed grammar:
the calls that define an option (`define_opt`, `define_fifo_opt`,
`define_opt_from_proc_out`, `define_cmdline_opt`, and the rest of that family)
with literal arguments, between the fixed lines that open and close the
function. From the shape of the functions it decides the mode:

- `_generate_opts_size` exists: `generator` mode. Its body, without its fixed
  opening lines, becomes `generatorSizeCode` as it is, and `_generate_opts` is
  parsed with the grammar.
- `_define_opts` is a flat sequence of those calls, with fanout family loops
  allowed among them: `standard` mode.
- `_define_opts` has exactly the shape that script generation writes for
  `array` mode: `array` mode, with the code that builds the array as
  `arrayCode`.
- Anything else: `manual` mode, with the functions kept as their verbatim
  source.

What the grammar recognizes gives the values, the option channels, the flags
`mirror` and `fromProcessSpec`, and the connections. A function kept in
`manual` mode is still scanned for connections anywhere in its text, so that
the canvas can draw them; script generation writes that function as it is, so
a connection that the scan misses or invents costs a wrong line on the canvas,
never a wrong module.

## Building the program

With the processes read, import assembles the program:

- **Options.** Each explained option becomes an option, its direction taken
  from its label. An option that a connection names but that no `explain_opt`
  declares, common in `array` mode, gets a minimal option of type `string` so
  that the edge has somewhere to attach.
- **Connections.** Each recovered connection becomes an edge, and a connection
  to a process outside the program is dropped. A connection by task index whose
  source does not run in `array` or `generator` mode cannot be written again as
  it was, so its target falls back to `manual` mode.
- **Shared directories.** An option whose value names a shared directory,
  literally or through a variable that the engine resolves, becomes a
  `shared_dir` option when that directory is one the program can reach, and
  import adds an edge from each writer of a directory to each of its readers.
  `availableSharedDirs` is filled with every reachable shared directory.
- **Preamble.** The module documentation has no notion of a preamble, so
  import takes the text of the module before its first function definition,
  leaving out the header line of a generated script.
- **Specifications.** They come from the module documentation. The engine
  attributes that the model does not hold (`nodes`, `account`, `partition`,
  `throttle`) are dropped.
- **Layout.** The module says nothing about positions, so import places the
  processes in layers by the depth of their connections, left to right in
  the order of the module documentation. The number of passes is bounded, so a
  cycle ends with some layering rather than none.
- **The rest.** `sourceDir` is the module's directory, the home and output
  directories are left empty, the scheduler is `BUILTIN` and there are no
  program options.

## What the round trip preserves

The two translations are designed so that each can read what the other
writes.

**From the model to a module and back.** Import recognizes the shapes that
script generation writes: the flat definitions of `standard` mode, the fixed
loop of `array` mode, the pair of functions of `generator` mode, and the
functions of `manual` mode, which come back as they went. The processes, their
options with their values, option channels and flags, the connections, the
modes, the code, the additional methods, the specifications and the
descriptions survive. The order of
the processes, and of the options of a process, follows the module
documentation and may differ from the original. What lives only in the program
metadata does not survive: the ids, which are new; the positions, which are
laid out again; the groups, which come back flattened; the environment
variables, except the `DEBASHER_MOD_DIR` given to import; the execution
options and program options; and the home and output directories. A `manual`
function that happens to fit the grammar of `standard` mode comes back in
`standard` mode, which defines the same options.

**From a module to the model and back.** A module that import recognizes comes
back with the same behavior, but written the way script generation writes it:
the option definition functions of a recognized mode lose their comments and
their layout, while the functions kept in `manual` mode, the code and the
methods keep their verbatim source. Some things a module can say have no place
in the model and are lost: the explicit dependency types of `_define_opt_deps`,
which the module documentation shows and import does not keep; the program
type of `_program_type`; any code of the module after its first function that
belongs to no process; and the specifications the model does not hold.

`test/api/test_round_trip.py` checks both directions. From the model to a
module and back, it builds programs that cover every options handler mode,
option channel and kind of connection, generates and imports them, and
compares the result with the program, leaving out what lives only in the
program metadata. From a module to the model and back, it imports every
module of `data/programs/`, generates it and imports it again, and requires
the same model both times: import is a fixed point of the round trip, so
nothing is lost, added or changed by going through it once more.

# Persistence and the program's directories

A program uses two directories with different owners. The home directory
belongs to the program and to the user: the web UI writes the program there,
and the user keeps there the files the program needs. The output directory
belongs to the engine: a run writes its results and the engine's own files
there, and the web UI mostly reads it. The two are kept apart: the save dialog
and the backend refuse to save into the output directory, and the editor of
the output directory refuses the home directory. Otherwise a run would mix the
engine's files with the program, and resetting the output directory would
delete the program.

## The home directory

The home directory holds the program metadata (`.debasher/program.json`, the
whole program model as JSON), the generated script (`<name>.sh`) and the user
files.

**Saving.** The user saves into a directory of their choice, which becomes the
program's home directory. The backend writes the program metadata, then the
generated script, and then copies the file of each `ext_alias` given as a
relative path from the program's `sourceDir` into the home directory, at the
same relative path: the engine resolves such a path against the directory of
the module that declares it, so without the copy a program imported and saved
elsewhere would lose its aliased scripts. When the program has been renamed
since the last save, the backend first deletes the script with the old name,
which it reads from the program metadata before overwriting it.

A save is refused while there is a run in progress on the output directory.
The engine reads the generated script again each time it starts a process, so
overwriting it during a run would leave the processes already started on one
version and the rest on another, with nothing to show it. The frontend checks
this before sending the save; the backend does not.

Running also saves. "Run program", "Run program (debug)" and "Check program
options" all save the program metadata and the generated script into the home
directory before calling `debasher_exec` (see "Launching a run"), so that the
engine always runs the program as it is in the editor. Only "Run program"
first checks that there is no run in progress; the other two are not blocked
during a run, and so bypass the guard of the save.

**Loading.** Loading reads the program metadata of a directory and opens the
program exactly as it was saved, including `homeDir` and `outputDir`, which
are absolute paths. A home directory that was copied or moved and is loaded
from its new place therefore still names the old one, and the next save or run
writes into the old place.

## Reserved names and user files

Inside the home directory, `is_reserved_name()` in `persistence.py` is the one
source of truth about what belongs to the engine or to the web UI: the program
metadata, the engine's files (`.conda`, `.sched_opts`, `__exec__`,
`__fifos__`, `command_line.sh`, ...) if the engine ever writes there, and any
file the engine adds later under the same conventions. It is a rule rather than
a list so that it needs no change when the engine grows.

The program files panel (`routers/program_files.py`) shows and manages the
user files: it lists the tree, shows a text file (up to a fixed number of
lines, and not a binary one), edits an existing file, creates a directory,
deletes, renames or moves an entry, and uploads files of any type, which is
also how the script of an `ext_alias` reaches a program that was not imported.
It keeps three guarantees:

- It never shows, enters or writes a reserved name, at any depth.
- Every path is resolved inside the home directory, following symbolic links,
  and a path that would leave it is refused. The panel never descends into a
  directory that is a symbolic link.
- The generated script is shown, read-only: the panel never edits, deletes,
  moves or overwrites it, since the next save would regenerate it anyway.

## The output directory

The engine owns the output directory: `__exec__/` with each process's files
(`.stdout`, `.sched_out`, `.opts`, ...), `__fifos__/` with the FIFOs, and its
own state files. The web UI adds only the run log. It reads the rest (see
"Execution and observation") and changes it in only one way: "Reset output
directory" deletes everything inside it, keeping the directory itself. The
reset does nothing, rather than fail, when the output directory is blank
(which would otherwise resolve to the server's current directory), does not
exist, is the root of the file system or the user's home, or is the program's
home directory. It removes a symbolic link as itself and never follows it. The
frontend refuses to reset while there is a run in progress, and to change the
output directory while there is one: the status, the stop and the inspection
actions all name the output directory, so changing it would leave the run out
of reach of the web UI.

# Execution and observation

The web UI runs a program, follows it and inspects it only through the
engine's tools and files on the output directory. It keeps no record of its
own: whatever it shows, it asks the engine again (see "The backend keeps no
state").

## Launching a run

"Run program" needs a home directory and an output directory. The frontend
asks for the state of the output directory, and the backend (`/run`) checks it
again: with a run in progress it answers with a conflict and does nothing.
Otherwise it saves the program (see "The home directory") and builds the
command:

- `debasher_exec --pfile <generated script> --outdir <output directory>
  --sched <scheduler>`;
- the flags of `executionOptions` that are set (`--builtinsched-cpus`,
  `--builtinsched-mem`, `--dflt-nodes`, `--dflt-throttle`,
  `--rerun-outdated-procs`, `--conda-support`, `--docker-support`);
- `--wait`, so that `debasher_exec` lives as long as the run;
- the program options, each label followed by its value, except a flag, which
  is given alone when its value is not empty and left out otherwise.

The command runs with `DEBASHER_MOD_DIR` taken from the program's `envVars`,
detached, with its output in the run log, and the backend answers at once.
Nothing in the web UI shows the run log; it is there for diagnosis by hand.

"Run program (debug)" runs `debasher_exec --debug`, which does everything but
launch the processes, and "Check program options" runs it with
`--check-proc-opts`. Both run to the end within the request, and the frontend
shows what they print.

## Following a run

The frontend follows a run with two polls, both built on `debasher_status` on
the output directory and both every five seconds. Polling is deliberate: the
backend has nothing that could push a change, and the engine records state in
files.

**The run phase** follows only a run that this tab launched. It goes from
`running` to `finished` when `debasher_status` reports every process finished,
and to `unfinished` when it reports neither finished nor in progress twice in
a row: a single reading of that kind also happens in the short gap between one
process ending and the next starting. The output of `debasher_status` from the
last reading is kept, to show why the run did not finish. The run phase
belongs to the tab: closing or reloading the tab, leaving the editor, or
dismissing the indicator of a running run stops it with `debasher_stop` (see
"Where the state lives").

**The process statuses** are read whenever the program has an output
directory, whoever launched the run. The backend parses the per-process lines
of `debasher_status` (`PROCESS: <name> ; STATUS: <status>`) and the canvas
colors each canvas node by its process's status: `FINISHED`, `IN-PROGRESS`,
`UNFINISHED`, `UNFINISHED_BUT_RUNNABLE` or `TO-DO`, and no color when there is
nothing to report. A run in progress is defined from these statuses, not from
the run phase, so the guards that depend on it (saving, resetting and changing
the output directory) also hold for a run launched from another tab or from
the command line.

## Inspecting a process

The context menu of a canvas node inspects what its process left in the
output directory:

- "Show stdout" and "Show scheduler output" run `debasher_get_stdout` and
  `debasher_get_sched_out`.
- "Show options" shows the process's `.opts` file, the options it was given,
  one per line.
- "Show inputs and outputs" parses that same file into the resolved value of
  each option, which for a FIFO, a shared directory or a value descriptor is
  the path the engine chose, not the model's `value`. Each value can be opened
  as a path: the content of a file, or the listing of a directory, anywhere the
  server's user can read.

A process that ran as several tasks has one set of files per task. The backend
lists the task indices from the names of the files in the process's directory
under `__exec__`, which stays cheap for thousands of tasks, and the user picks
one. Every output is cut at a fixed number of lines (10,000), with a warning.

Some of these actions read the engine's files directly instead of through a
tool: the `.opts` files, the task indices and, below, the FIFOs. They follow the
names that the engine gives to its files in the output directory, and would
have to change with them.

## FIFOs

**Watch FIFO** shows what a process writes into a FIFO defined with
`--mirror`. It reads the FIFO mirror with `debasher_get_fifo_mirror` every two
seconds, and so never takes anything from the FIFO's real reader.

**Talk to FIFOs** lets a person act as the other end of the unconnected FIFOs
of a running program: write a line into an input, or read a line from an
output. It is only offered while this tab's run is running, and only for
unconnected FIFOs, since reading a FIFO that another process also reads would
steal its data. The backend finds the FIFO by the engine's convention,
`__fifos__/<process>/<fifo name>`, and bounds each attempt to eight seconds,
because opening a FIFO blocks until the other end is open: a write that times
out means that no process is reading; a read that times out only means that
nothing has been written yet, and the frontend tries again.

## Stopping

"Stop program" runs `debasher_stop` on the output directory, and "Stop
process", in the context menu of a canvas node, runs it for that one process.

# Frontend state and the canvas

## Screens and the store

The frontend has two screens: the home screen, which creates, loads or imports
a program, and the editor. Opening a program in the editor creates a store
with it (`ProgramProvider` in `store/ProgramContext.tsx`), and leaving the
editor discards the store, stopping a run launched from it (see "Where the
state lives"). The store holds the program, the selected process, the run
phase with the last output of `debasher_status`, and the process statuses,
from which it derives whether there is a run in progress. The dialogs edit a
draft of their own and hand it to the store only when the user accepts it.

Every change to the program goes through an operation of the store
(`addProcess`, `connect`, `updateOption`, ...), and every operation passes its
result through the same normalization, which derives the connection sentinels
from the edges and restores the default scheduler if it is blank. The rules of
"Connections" therefore hold after every change, not only when the program is
saved. An operation that would change a process of a group first asks the
user, and dissolves the whole group if the user agrees (see "Groups"); if not,
the program is left as it was.

The store keeps no history and no record of unsaved changes: there is no
undo, and leaving the editor or closing the tab loses the changes made since
the last save, without a warning.

## From the store to the canvas

`adapters/reactFlowAdapter.ts` turns the program into what the canvas library
(React Flow) draws. Each process becomes a canvas node, with the process's id
and position, and a handle for each option, with the option's id: the inputs
along the top and the outputs along the bottom, except the pair of handles
that the canvas moves to keep a short edge between two processes that answer
each other (see "Connections"). Each edge becomes a canvas edge between two
handles, drawn in one of three ways: a plain edge; a back edge, routed along a
lane to the right of every process; or a fanout edge, narrow at the end of the
fanout family. An edge from a FIFO is dashed.

A canvas node shows the process's name and options, its options handler mode
(a double border for `array` and `generator`, a dashed one for `manual`), its
group (a border color derived from the `groupId`, and a badge with the
module's name), and, as its background, the process status.

Of what the canvas shows, only the positions belong to the program model and
are saved. The selection, the part of the canvas in view (fitted to the
program when the editor opens) and the colors are not.

## Keeping the canvas in step with the store

The canvas library draws from its own list of canvas nodes, which it updates
on every frame of a drag. The canvas keeps that list, writes each new position
into the store as the drag goes, and refreshes the list from the store only
when the program's structural key changes (for each process: its id, name and
mode, and the id, label and direction of each option) or when the set of moved
handles changes, keeping the positions that the list already has. Refreshing
it on every change of the store would fight with the drag.

The rule that follows is that whatever a canvas node draws from its process
must be part of the structural key; otherwise the canvas node keeps drawing an
old value until the next structural change. The group is not part of it today,
so a dissolved group keeps its color and its badge on the canvas until then
(see "Future work"). The process status does not go through that list: each
canvas node reads it from the store. Neither do the edges, which are derived
again from the store on every change.

# Guarantees and non-goals

This section gathers the guarantees that the web UI gives today for general
programs, stated in the sections above, and what it deliberately does not
try to do. Where a guarantee has a known gap, "Future work" lists it.

## Guarantees

**The program model**

- **Connections are consistent.** After every change, the value of each
  connected input names the output its edge comes from, and the canvas accepts
  only connections that the engine can resolve (see "Connections").
- **No wrong module.** Script generation refuses a program whose module would
  be wrong, rather than writing it (see "What script generation refuses").
- **Import is a fixed point.** Importing a generated module gives back the
  model it was generated from, apart from what lives only in the program
  metadata, and generating and importing an imported module changes nothing;
  both are tested (see "What the round trip preserves").
- **No lost code.** Leaving out the code that a loaded module already provides
  can only remove a duplicate; when the check cannot be made, the code is
  written (see "Code that a loaded module already provides").
- **What import does not understand, it keeps.** An option definition function
  outside the grammar of import is kept as its verbatim source, in `manual`
  mode, so it runs as it did; a connection recovered from it only affects the
  canvas (see "Recovering the options handler").

**The program's directories**

- **Two directories apart.** A program is never saved into its output
  directory, and the output directory is never set to the home directory.
- **User files are the user's.** The program files panel never touches a
  reserved name, never leaves the home directory, and never changes the
  generated script (see "Reserved names and user files").
- **A reset stays in the output directory.** Resetting it deletes only what is
  inside it, and does nothing when it is blank, missing, the root, the user's
  home or the home directory (see "The output directory").
- **No change under a running program.** While there is a run in progress, the
  frontend refuses to save, to reset the output directory and to change it.
  Only the frontend enforces this, and two actions of the Run menu bypass the
  save's guard (see "The home directory").

**Execution and observation**

- **One run per output directory.** A run is not launched on an output
  directory with a run in progress.
- **A run launched from a tab does not outlive the tab.** Closing or reloading
  the tab, leaving the editor, or dismissing the indicator of the run stops
  it.
- **Any run is observed.** The process statuses, and the guards that depend on
  them, cover a run launched from another tab or from the command line.
- **Watching a FIFO takes nothing from it.** "Watch FIFO" reads the FIFO
  mirror, never the FIFO.
- **Talking to a FIFO competes with nobody.** "Talk to FIFOs" only opens
  unconnected FIFOs, and never blocks a request for more than a few seconds.
- **Nothing is lost when the backend restarts**, since it keeps no state (see
  "The backend keeps no state").

## Non-goals

- **Security.** The web UI trusts whoever reaches it: it has no
  authentication, and it runs every tool, and reads any path, as the user who
  started it. It listens only on the local machine unless told otherwise.
- **Several people on one program.** Two tabs on the same program or the same
  directories are not coordinated: the last save wins, and only the guards
  based on the engine's own files (a run in progress) see the other tab.
- **Keeping unsaved work.** There is no autosave, no undo and no warning
  before unsaved changes are lost.
- **Live updates.** The web UI learns what happens in a run by polling, every
  few seconds, not by being told.
- **Importing any module faithfully.** Import recognizes a closed grammar, and
  keeps the rest as it is rather than trying to understand it (see "What the
  round trip preserves").
- **A program directory that can be moved.** The program metadata records
  absolute paths (see "The home directory").

# Resident programs in the web UI

*Not yet designed.* The extension of the web UI to resident programs. A
resident program is not a run that starts and finishes: its processes stay
alive, keep state, recover from crashes and go through rounds. The UI has to
build such a program, launch it, observe it while it lives and act on it.

The sections before this one describe general programs only (see the
Introduction). This section is where a resident program departs from them: for
each part of that design (the program model, script generation and import, the
program's directories, execution and observation), it says whether the part
applies unchanged, changes, or is replaced by a rule of its own.

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

*To be completed.*

- **Round trip at run time.** Running each module of `data/programs/` and the
  module generated from it, and comparing what they do, beyond the comparison
  of models that `test/api/test_round_trip.py` makes.
- **Refused programs and the saved script.** Generating the script before
  writing the program metadata, so that a program that script generation
  refuses leaves the home directory as it was.
- **Guards in the backend.** Refusing in the backend, and not only in the
  frontend, a save, a reset of the output directory or a change of it while
  there is a run in progress, and blocking "Run program (debug)" and "Check
  program options" during a run, which today save the generated script
  without that check.
- **The group on the canvas.** Adding the group to the structural key of the
  canvas, so that a dissolved group loses its color and badge at once (see
  "Keeping the canvas in step with the store").
- **A moved home directory.** Taking the home directory from the place the
  program is loaded from rather than from the program metadata, and deciding
  what a moved program should do with an output directory that still points
  to the old place.
- **What import loses.** Giving `_define_opt_deps` and `_program_type` a place
  in the model; the second is needed by resident programs (see "Declaring a
  resident program").
