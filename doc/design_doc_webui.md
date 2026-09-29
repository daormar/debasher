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
in the design of resident programs. Terms of the engine that this glossary
does not list, such as option list, FIFO owner, exec directory or completion
marker, have the meaning that the design of the engine
(`doc/design_doc_engine.md`) gives them, and so do the entries below that
refer to it.

## Program model

- **general program**: as defined in the design of the engine. Every section
  before "Resident programs in the web UI" is about general programs.
- **resident program**: as defined in the design of the engine: long-lived,
  stateful processes joined by FIFOs, always run by the built-in scheduler,
  whose design is in `doc/design_doc_resident.md`.
- **node kind**: the class of the engine's runtime library that a process of a
  resident program derives from (`ProgramProcess.nodeKind`): `FBPProcess`,
  `ProgramLauncher`, `DirectoryWatcher` or `Supervisor` (see "The program model
  of a resident program").
- **node preamble**: the Python code of a node before its class, such as imports
  and helper functions. Not to be confused with the preamble of the program,
  which is Bash.
- **class body**: the part of the class of a node that is not a hook: class
  attributes, the constructor and helper methods.
- **Supervisor wiring**: the channels between the `Supervisor` and the nodes
  (heartbeat channels, trigger ports and the manual trigger port), which script
  generation derives and the program model does not hold.
- **program model**: the program as the web UI sees it, a tree of plain data
  defined twice with the same shape, as Pydantic models in `api/models.py` and
  as TypeScript types in `frontend/src/models/`, and sent as JSON between the
  two (see "The program model").
- **program**: the root of the program model (`Program`). It becomes one
  DeBasher module, the program file of the runs that the web UI launches, whose
  name is the program's name.
- **process**: one process of the program (`ProgramProcess`), with its options,
  its code and its specifications, which becomes a process in the sense of the
  engine.
- **option**: one option of a process (`ProgramOption`), which becomes an option
  in the sense of the engine, named by its **label**, the option's name for the
  engine, such as `-infile`.
- **direction**: whether an option is an `input` or an `output` of its process.
- **data type**: the type of an option's value: `int`, `float`, `string`,
  `file`, or `None` for a flag, an option that takes no value.
- **option channel**: how an option's value is delivered, independent of its
  data type (`ProgramOption.channel`): `none` for a literal value or a
  connection, `value_desc` for a value descriptor the engine synthesizes, `fifo`
  for a named pipe, `shared_dir` for a shared directory.
- **literal value**: the value of an option with option channel `none` that is
  not connected, not a command line option and not taken from the process
  specifications: the Bash word that the user writes in `ProgramOption.value`,
  such as `10` or `${idx}`, and that script generation writes as it is (see
  "Option definitions").
- **shared directory**: as defined in the design of the engine.
- **command line option**: as defined in the design of the engine, marked as one
  by `ProgramOption.commandLine`. It takes its value from the command line and
  nowhere else: script generation refuses an option that is both a command line
  option and delivered through an option channel.
- **program options**: the values given to the command line options for the next
  run (`Program.programOptions`), keyed by label.
- **edge, connection**: a link from an output option of one process to an input
  option of another (`ProgramEdge`), which script generation turns into a
  connection in the sense of the engine, so that the second reads the value of
  the first (see "Connections").
- **connection sentinel**: the value `[<process>;<option>]` that a connected
  input option carries, naming the process and the option it reads from.
- **fan-in**: more than one connection into the same input option.
- **self-loop**: a connection from an output option of a process to an input
  option of the same process.
- **options handler mode**: how a process defines its options and so how many
  tasks it runs: `standard`, `array`, `generator` or `manual` (see "Options
  handler modes").
- **task**: as defined in the design of the engine. A process in `standard` mode
  runs one task; one in `array` or `generator` mode runs one per element or
  index.
- **fanout family**: as defined in the design of the engine. In the web UI, an
  option of a `standard` process whose label ends in `ith`, such as `-outfith`,
  which stands for as many numbered options (`-outf0`, `-outf1`, ...) as another
  option of the same process says at run time.
- **preamble**: Bash code that the generated module carries verbatim before its
  own functions, typically the `load_debasher_module` lines of the modules it
  builds on.
- **group**: the processes that "Add program" brings in, in one operation, from
  another program saved with the web UI, which the generated module declares
  with a single `add_debasher_program` while none of them has been edited or
  removed (see "Groups").

## Files and directories

- **home directory**: the directory where the program lives (`Program.homeDir`):
  its program metadata, its generated script and the user files.
- **output directory**: as defined in the design of the engine
  (`Program.outputDir`).
- **program metadata**: the program model saved as JSON in
  `.debasher/program.json` under the home directory.
- **generated script**: the module that script generation writes as `<name>.sh`
  in the home directory.
- **reserved name**: a file or directory name that the engine or the web UI
  manages, by a rule rather than a list (`is_reserved_name()`): a name that
  starts with a dot, a name wrapped in double underscores (`__exec__`,
  `__fifos__`, ...), and `command_line.sh`.
- **user file**: a file or directory of the home directory whose path has no
  reserved name, which the user manages through the program files panel.
- **run log**: `.debasher_webui_run.log` in the output directory, where the web
  UI sends everything that `debasher_exec` prints during a run it launched.
- **snapshot log**: `.debasher_webui_snapshots.log` in the output directory of a
  resident program, where the web UI sends everything that the
  `debasher_snapshot_resident --every` it starts prints.
- **program state**: what the nodes of a resident program keep across runs in
  its output directory, their checkpoints, input logs and halted markers and the
  output directories of their processes: what `debasher_reset_resident` takes
  away (see "The directories of a resident program").
- **launch record**: the copy of the generated script and of the program options
  that every launch of a resident program leaves in its output directory,
  against which the next launch compares the program.

## Translation

- **script generation**: turning the program model into a runnable module
  (`script_generation.py`).
- **import**: rebuilding the program model from a module that has no program
  metadata, such as one written by hand (`program_import.py` and the modules it
  relies on).
- **module documentation**: the Markdown that `debasher_doc_mod` prints about a
  module after loading it: its name, description and shared directories, and for
  each process its options, its option definition functions, its code, its
  methods and its specifications.
- **canonical form**: how Bash prints a function back with `declare -f`, without
  its comments and with its own indentation. Two functions with the same
  canonical form behave the same.
- **verbatim source**: a function exactly as it is written in its file, comments
  and indentation included, as `debasher_get_verbatim_func_source` reads it.
- **round trip**: script generation followed by import, or import followed by
  script generation (see "What the round trip preserves").

## Execution and observation

- **run**: as defined in the design of the engine.
- **tab**: one browser tab with the web UI open, holding its own store.
- **store**: the state of the frontend in a tab (`ProgramContext`): the program
  being edited and what the tab knows about its runs.
- **run phase**: the state of a run launched from this tab, as the tab follows
  it (`ProgramRunPhase`). For a resident program, the state of the program
  derived from the process statuses, whoever launched it (see "Running a
  resident program").
- **process status**: as defined in the design of the engine, as
  `debasher_status` reports it for the output directory, whoever launched the
  run; it colors the canvas.
- **run in progress**: the state of an output directory in which
  `debasher_status` reports at least one process as `IN-PROGRESS`, whoever
  launched the run.
- **orderly stop**: the stop of a resident program with
  `debasher_stop_resident`, which halts every node in one round before stopping
  it, so that the next launch resumes the program with nothing lost.
- **hard kill**: the stop of a program with `debasher_stop`, which stops the
  `debasher_exec` of the run if it still runs and then kills every process at
  once; for a resident program, what its FIFOs held may be lost.
- **mirror log**: as defined in the design of the engine: the log in which a
  mirror tap copies every line that a process writes into a FIFO defined with
  `--mirror`, which can be read without taking the data from the FIFO's reader.
- **unconnected FIFO**: a FIFO option with no edge and whose label does not name
  a fanout family, whose other end is an external end in the sense of the
  engine, left to someone outside the program, such as a person using "Talk to
  FIFOs".

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
stops it. Resident programs replace this rule, since their processes are meant
to outlive any tab (see "A program that outlives the tab").

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

An edge goes from an output option of a process to an input option of another
process or of the same one. The edges are the one source of truth about what is
connected. The value of a connected input, its connection sentinel, is derived
from them: the store recomputes it from the edges after every change to the
program, so renaming a process or an option never leaves a sentinel that names
the old one, and a program loaded with values out of step with its edges is
repaired on load. Script generation also reads the edges, and emits one
definition per edge; the sentinel is only its fallback when no edge matches. A
`shared_dir` input is the exception: its value stays the name of its directory,
and its edges only document on the canvas a dependency that the engine derives
on its own from every writer resolving to the same path.

The canvas accepts a new connection only when it keeps the program valid for
the engine:

- It goes from an output to an input. Both may belong to the same process,
  a self-loop, so that a process can feed itself.
- The input takes its value from nowhere else: it is not a flag, which takes
  no value, nor a command line option, nor an option taken from the process
  specifications, all of which script generation writes before it looks at
  any connection. The editor of an option does not turn a connected input
  into any of them either.
- An output may feed any number of inputs, but an input accepts only one
  connection, since the engine could not tell which value it should take. The
  exception is fan-in between `shared_dir` options that name the same
  directory, which all resolve to the same path.
- A `shared_dir` option pairs with another `shared_dir` option only when both
  name the same directory.
- A fanout family pairs only with a process in `array` or `generator` mode,
  and never with another fanout family.
- It closes no cycle, a self-loop included, made only of edges that do not
  come from a FIFO.

The last rule follows the engine. A connection that does not come from a FIFO
makes its target wait for its source to finish, while one from a FIFO makes no
dependency at all, so that both ends run at the same time. The engine refuses a
cycle of dependencies when it loads the program, and so accepts a cycle only
when at least one of its edges comes from a FIFO. It does not refuse a
self-loop that does not come from a FIFO, since it drops the dependency of a
process on itself, but such a process would only read the file it writes, and
the canvas refuses it with the rest.

Every cycle has at least one edge whose target sits at or above its source on
the canvas, a self-loop included, and the canvas routes such an edge around
the processes instead of through them. For two processes that answer each
other through FIFOs, it instead moves the handles of the answering pair to the
other side, so that the edge stays short.

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
   becomes a heredoc function `<process>_heredoc_<suffix>` (`py`, `r`,
   `perl`, `groovy`) that prints it, which the engine wraps in the
   function of the process. The engine also accepts the older form, a
   variable `<process>_<suffix>`, which import reads, but a Bash variable
   name cannot contain the dot of a namespaced process, so script
   generation never writes it.
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
saved, and the home directory keeps the script of the previous save. The save
answers with the reason of the refusal, which the frontend shows.

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
  cycle ends with some layering rather than none. A self-loop says nothing
  about the order of two processes, and is left out of the layering.
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
methods keep their verbatim source. Code in another language that the module
held in a heredoc variable comes back in a heredoc function. Some things a
module can say have no place in the model and are lost: the explicit dependency
types of `_define_opt_deps`, which the module documentation shows and import
does not keep; the program type of `_program_type`; any code of the module after
its first function that belongs to no process; and the specifications the model
does not hold.

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
program as it was saved, except for `homeDir`, which becomes the absolute path
of the directory it is loaded from, whatever the metadata recorded. A home
directory that was copied or moved is therefore saved and run where it now
is. `outputDir` is kept as it was saved: a program loaded from a new place
still names the output directory it had, which is not always what its user
wants (see "Future work").

**Programs shipped with DeBasher.** `data/webui_programs/` holds programs
built with the web UI, installed under the package's data directory, one home
directory each, with its program metadata and its generated script. They are
loaded, never imported, and so keep everything the program model holds. None
of them records an output directory or a source directory, since a path of
the machine they were built on means nothing on another. An installed one is
usually not writable, so the user saves it into a home directory of their
own before changing it. `test/api/test_webui_programs.py` checks that each
of them loads from where it is and that its generated script is the one that
script generation writes from its metadata today.

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
`--mirror`. It reads the mirror log with `debasher_get_fifo_mirror` every two
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
try to do. Where a guarantee has a known gap, "Future work" lists it. Those of
resident programs, designed and not built, are gathered in "Guarantees and
non-goals of a resident program".

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
- **A program lives where it is loaded from.** Its home directory is the
  directory it was loaded from, even if it was copied or moved there (see
  "The home directory").
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
- **An output directory that follows a moved program.** A program loaded
  from a new place keeps the output directory it was saved with (see "The
  home directory").

# Resident programs in the web UI

*Designed, and being built: a subsection that is built says so under its
title.* The extension of the web UI to resident programs. A resident program
is not a run that starts and finishes: its processes stay alive, keep state,
recover from crashes and go through rounds. The UI has to build such a
program, launch it, observe it while it lives and act on it.

The sections before this one describe general programs only (see the
Introduction). This section is where a resident program departs from them: for
each part of that design (the program model, script generation and import, the
program's directories, execution and observation, and the canvas), it says
whether the part applies unchanged, changes, or is replaced by a rule of its
own.

## The program model of a resident program

*Built.*

A resident program is edited with the same program model as a general one. The
model gains a few fields, and some of what a general program may hold is not
offered.

**Program type.** `Program.programType` is `general` or `resident`, and
`general` for program metadata saved without it. The user chooses it in a
dialog when creating a program, and it never changes afterwards: the two types
accept different processes and connections, and turning one into the other
would leave in the program what the new type refuses. Script generation writes
the module's `_program_type` function for a resident program, and import reads
it.

**Node kinds.** Every process of a resident program is a node of one node kind
(`ProgramProcess.nodeKind`), chosen when the process is added: `FBPProcess`, a
business node; `ProgramLauncher`, which launches a general program for every
request it receives; `DirectoryWatcher`, which brings in the files that arrive
in a directory; and `Supervisor`, which a program has at most once. They are
the classes of the engine's runtime library with the same names (see
`doc/design_doc_resident.md`). The engine derives the role of a process from
the base of its class, and the web UI stores the kind instead: the user never
writes the class declaration, which script generation writes from the kind, so
the kind and the code cannot disagree.

**The code of a node.** A node is always written in Python, with no choice of
language. Its code is made of parts, each edited on its own, which script
generation assembles into the process's heredoc, ending with the lines that
create the object and call `run()`:

- the node preamble: the code before the class, such as imports, helper
  functions and constants;
- the class body: the class attributes (the interval of the heartbeat, the
  directory that a `DirectoryWatcher` watches, the general program of a
  `ProgramLauncher`, ...), the constructor, which gives the node state its
  first value, and helper methods;
- one body for each hook: `process_data`, `capture_node_state`,
  `restore_node_state`, `initialize_runtime` and `observe`.

An `FBPProcess` has to give the first four hooks, and `observe` only if it
watches something outside the program, together with its observe port in the
class body. A `ProgramLauncher` and a `DirectoryWatcher` already implement
every hook, so each body given for them overrides that of their class, and
what they mostly need are class attributes. The class body never declares the
ports of the node: the engine gives each node its ports from the options of the
module, and stops a node whose class declares them.

The class is named after the process, in CamelCase (`counter` gives `Counter`,
`org.ns.count_words` gives `OrgNsCountWords`), as the engine requires (see
"Defining a node" in `doc/design_doc_resident.md`), and the editor shows its
declaration above the class body, read only. The model therefore holds no name
for it, and import needs none: a module that loads already names its class
this way. The editor refuses a process name whose class would hide a class of
the runtime library or a Python builtin, such as `supervisor` or `type_error`.
Whether the class hides a name that the node preamble binds depends on the
preamble, which may change after the process is named, so the engine checks it
when it loads the program.

**The `Supervisor`.** It is added like any node, with the node kind
`Supervisor`, and refused when the program already has one. The user edits
nothing of it but its name, its description and its computational
specifications, `heartbeat_timeout_s` and `startup_timeout_s` among them:
script generation writes its whole class and all its options. Among them is
the flag `-no-hold-fifos`, a command line option, so that each run can choose
whether the `Supervisor` holds the business channels (see "Holding the
business channels" in `doc/design_doc_resident.md`).

**The Supervisor wiring.** The channels between the `Supervisor` and the nodes
are not part of the program model. Script generation derives them every time
from whether the program has a `Supervisor`, from its nodes and from which of
them are initiators, as the store derives the connection sentinels from the
edges, so adding or removing a node needs no change to the `Supervisor`. They
are:

- a heartbeat channel from every node, one for each task of an `array` or
  `generator` process: an output of the node, read by an input of the
  `Supervisor`;
- a trigger port to every initiator: an output of the `Supervisor` with the
  fifo tag `control`, read by an input of the initiator;
- the manual trigger port: an input of the `Supervisor` with the fifo tag
  `control`, written from outside the program.

Without a `Supervisor`, each initiator gets instead an input of its own with
the fifo tag `control`, written from outside the program, where
`debasher_snapshot_resident` and `debasher_stop_resident` write their triggers.
The labels of these options are reserved, and no option of the user may take
them.

How many tasks an `array` or `generator` process has is only known when its
options are defined, so the `Supervisor` reads the heartbeat channels of such a
node as a fanout family, as a `standard` process reads the tasks of an array
(see "Option definitions"), and sends to the tasks of an initiator of that kind
the same way. The family is counted by the command line option that counts the
fanout family the node is connected to, directly or through the tasks of another
array. A resident program with a `Supervisor` and a node of that kind that
reaches no such family has no count for it, and script generation refuses it.
The node has to build exactly as many tasks as the option says. A task too few
makes the engine refuse the program, since the `Supervisor` would connect to a
task that does not exist, and so does a task too many, which would otherwise run
unsupervised: in a program with a `Supervisor`, the engine refuses a node with
no heartbeat channel.

**Initiators.** `ProgramProcess.initiator` marks a node as an initiator, where
a round starts. A program made of independent subgraphs needs one initiator in
each. The engine refuses, when it loads the program, one with a node that no
initiator reaches through the business channels, and the editor leaves that
check to it.

**Options of a node.** The options of a node other than the `Supervisor` are of
four sorts:

- a business output: an output with option channel `fifo` and no fifo tag,
  which the node writes. With no connection, its reader is outside the
  program, as for a node that writes its results out;
- a business input: an input connected to a business output, of another node
  or of the same one through a self-loop;
- an external input: an input with option channel `fifo` and the fifo tag
  `external` (`ProgramOption.fifoTag`), written by a source outside the
  program, which takes no connection. A node acts only on what it receives,
  so what starts the activity of a program always comes in through an
  external input;
- a configuration option: an option with option channel `none` that no
  connection feeds (a literal value, a flag, a command line option or an
  attribute of the process specifications), which the node reads from its
  options.

The fifo tag `control` is never set by the user: only the Supervisor wiring
writes it. The option channels `value_desc` and `shared_dir` and the flag
`mirror` are not offered: the engine refuses `--mirror` in a resident program,
and a connection that is not a FIFO makes the reader wait for the writer to
finish, a dependency that the engine refuses in a resident program, whose
processes it launches all at once.

**Connections.** The canvas accepts a connection in a resident program only
from a business output to a business input, of another node or of the same
node. An external input takes none, nor does a flag, which takes no value,
and the Supervisor wiring is never drawn by hand.

**Options handler modes.** `standard`, `array` and `generator` apply as in a
general program, and each task of an `array` or `generator` process is a node
of its own. `manual` is not offered, since in that mode the user writes the
option definition function whole, and the Supervisor wiring has to be added to
the function of every node. Fanout families apply unchanged.

**Specifications.** `ComputationalSpecs` gains optional fields, shown only for
the node kinds that read them: the limits of a node (`input_log_max_mb`,
`out_backlog_max_mb`, `out_backlog_fail_mb`, `gil_switch_interval_ms`) and
`startup_timeout_s` for every node, `max_concurrent_runs` and `batch_sched`
for a `ProgramLauncher`, and `heartbeat_timeout_s` and `startup_timeout_s` for
the `Supervisor`. The engine checks their values when it loads the program.

**Additional specifications and methods.** A process of a resident program
offers neither the additional specifications of a general process nor its
additional methods. Of the first, `processdeps` is a dependency, which the
engine refuses in a resident program, whose processes it launches all at once;
`force` reruns a process that finished, where every launch of a resident
program already launches every node again; and an alias or an external alias
takes the code of the process from another one, which the engine does not
follow in a resident program, since it looks for the Python heredoc of each
process under the name of that process (see "Future work"). Of the second,
`reset_outfiles`, `skip` and `post` act before or after a run of a process
that finishes, which a node never does; `conda_envs` and `docker_imgs` give
environments that a resident program is not launched with (see "Running a
resident program"); and `outdir_basename` is left out so that the output
directory of every node keeps the name that the engine gives it by default,
by which the backend finds the program state (see "The directories of a
resident program").

**Groups.** "Add program" brings in only a program of the same type. In a
resident program it brings in the processes one by one, never as a group: a
module added with `add_debasher_program` carries its own Supervisor wiring,
while the wiring of the whole program has to be derived again with the new
nodes. A program that already has a `Supervisor` refuses a program that brings
another.

**What applies unchanged.** The ids, names and positions of the processes, the
rule that gives an option its direction, command line options and program
options, the preamble of the program and its environment variables.

## Script generation and import of a resident program

*Built.*

**The code of a node, generated.** Script generation writes the code of a node
as the heredoc function of its process, `<process>_heredoc_py` (see "Layout of
the generated module"), which holds, in this order:

1. `from debasher_runtime_lib import <kind>`, for its node kind;
2. the node preamble;
3. `class <Name>(<kind>):`, with the name of the class derived from the
   process (see "The program model of a resident program");
4. the class body;
5. each hook that has a body, with its fixed signature:
   `process_data(self, port_name, packet)`, `capture_node_state(self)`,
   `restore_node_state(self, node_state)`, `initialize_runtime(self)` and
   `observe(self)`;
6. `<Name>().run()`.

The class body and the bodies of the hooks are kept without the indentation
that all their lines share, and script generation indents them again. The
`Supervisor` has no parts: its class is written as `class <Name>(Supervisor):`
with the body `pass`, followed by the line that runs it.

**The code of a node, imported.** Import reads the heredoc of each node, as
the engine prints it, and parses it with Python's `ast` module, without
running it. The class of the node is the one class that derives from a class of
the runtime library, as the engine requires, and its base gives the node kind.
From it:

- the node preamble is the text before the class, comments included, less the
  line `from debasher_runtime_lib import <kind>` when it has exactly that form;
- a method of the class is a hook when it has the name of a hook, its fixed
  signature with no annotation, no decorator and a body on lines of its own,
  and its body is kept, comments included;
- the class body is the rest of the class, in its order. A method with the name
  of a hook and another signature, such as `process_data(self, port, pkt)`,
  stays in it as an ordinary method, and works as it did;
- after the class comes only the line that runs it, which script generation
  writes again. The same line under `if __name__ == "__main__":` is taken for
  it, since the engine runs the heredoc as the main module.

**What import refuses.** A heredoc that script generation could not write again
from these parts is refused: code after the class other than the line that runs
it; a class with a decorator, more than one base or a keyword such as
`metaclass=`, or with its body on the line of its declaration; and a statement
of the class body that uses a hook it follows, such as `handler = process_data`,
which would come before the hook once script generation writes the hooks after
the rest of the class body. A process with additional specifications or
additional methods, which a resident program does not offer (see "The program
model of a resident program"), is refused too, as is one whose code is not a
Python heredoc. Import then refuses the whole program and lists every node that
does not fit, each with its line, the shape that the web UI expects and how to
change the code to fit it. Such a module is a valid resident program, which the
engine runs; only the web UI cannot hold it. This is where import departs from
"What import does not understand, it keeps": the code of a node has no
counterpart of the `manual` mode of the options handler, since the parts of a
node already cover what a node can do, and a mode of its own would need an
editor of its own.

**The round trip of the code of a node.** A node built with the web UI comes
back from script generation and import with the same parts. A node written by
hand comes back with the same behavior, but laid out the way script generation
writes it: the hooks follow the rest of the class body, and the blank lines
between the parts are those that script generation writes.

**The Supervisor wiring, generated.** Script generation writes the options of
the Supervisor wiring with fixed labels, which no option of the user may take:

- on every node of a program with a `Supervisor`, `-outhb`, the output of its
  heartbeat channel, which nothing would read in a program without one;
- on the `Supervisor`, `-<process>_hb`, the input that reads the heartbeat
  channel of a node, or the fanout family `-<process>_hbith` for an `array` or
  `generator` process;
- on the `Supervisor`, `-out<process>_trig`, the trigger port to an
  initiator, or the fanout family `-out<process>_trigith`;
- on every initiator, `-trigger`, the input of its control port, connected to
  the trigger port of the `Supervisor` or, without one, written from outside
  the program;
- on the `Supervisor`, `-manual`, its manual trigger port, and the flag
  `-no-hold-fifos`, together with the command line options that count its
  fanout families.

The name of the process comes first in a label of the `Supervisor`, never
last: a process named `smith` would otherwise give `-hb_smith`, which ends in
`ith` and would be taken for a fanout family.

**The Supervisor wiring, imported.** Import recognizes the Supervisor wiring of
a module by the rules with which the engine gives each process its ports (see
"Ports from the engine" in `doc/design_doc_resident.md`), from what it already
reads of the options, and from the node kind of each process: which process
defines each fifo, which one uses it, and with which fifo tag. It removes from
the program every option of it, whatever its label, and keeps only what the
program model holds:

- a fifo without a tag that a node writes and the `Supervisor` reads is a
  heartbeat channel, and both of its options go;
- a fifo tagged `--control` that the `Supervisor` writes and a node reads is a
  trigger port: both of its options go, and the node becomes an initiator;
- a fifo tagged `--control` that the `Supervisor` defines and reads, written
  from outside the program, is its manual trigger port, and goes;
- without a `Supervisor`, an input of a node tagged `--control` and written
  from outside the program is the control port of an initiator: it goes, and
  the node becomes an initiator;
- the flag `-no-hold-fifos` of the `Supervisor`, and the command line options
  that only count its fanout families, go too.

The labels and the fifo names of the wiring that script generation writes
again may differ from those of the module, and a manual trigger port and
`-no-hold-fifos` are added when the module had none. None of this changes what
the program does, since the runtime takes the ports of a process from the
engine by their role, not by their label. The one exception is the code of a
node that names an option of the wiring, such as `self.opts["outhb"]`: import
finds the port name quoted in the heredoc of the node and refuses it, since
the label may change.

**What import refuses of the Supervisor wiring.** With the same kind of
explanation as for the code of a node, import refuses a program whose
`Supervisor` has code of its own (a method or an attribute in its class, such
as its own `on_node_down`), since the web UI does not edit the `Supervisor`
and has nowhere to keep it; a program whose `Supervisor` has an option that is
none of the above; in a program with a `Supervisor`, an input of a node tagged
`--control` and written from outside the program, which the engine accepts but
the program model cannot hold, since the web UI gives every initiator a
trigger port of the `Supervisor`; and a node whose option definition functions
are outside the grammar of import, which in a general program would become
`manual` mode, a mode that a resident program does not offer. A program whose
wiring is incomplete, a node without a heartbeat channel for example, never
reaches import: the engine refuses to load it.

**The fifo tags.** Script generation writes the fifo tag `--external` as the
last argument of the `define_fifo_opt` of an external input, where it writes
`--mirror` in a general program, and `--control` only in the Supervisor wiring.
The grammar of import reads either tag in that same place, as it reads
`--mirror`. An `--external` becomes the `fifoTag` of the option. A `--control`
is always part of the Supervisor wiring, which import removes: the engine
refuses, when it loads the program, a fifo tagged `--control` that neither the
`Supervisor` writes to a node nor a node reads from outside the program, and
those two are the trigger ports and the control ports of the wiring.

**The program type.** For a resident program, script generation writes the
module's `<name>_program_type` function, with the body
`program_type "resident"`, after `<name>_shared_dirs`. For a general program it
writes none, since a module without one is general. Import reads the type from
the section "Program Type" of the module documentation, where
`debasher_doc_mod` prints the type that the engine resolved, so a module that
declares `program_type "general"` comes back as a general program without the
function, which behaves the same.

**What script generation refuses of a resident program.** Besides what it
refuses in a general program, with the same answer (see "What script
generation refuses"), script generation refuses a resident program with more
than one `Supervisor`; a process with no node kind; a node in `manual` mode;
an option of the user that takes a label of the Supervisor wiring, uses the
option channel `value_desc` or `shared_dir`, is mirrored or has the fifo tag
`control`; a `Supervisor` with options of its own, or in `array` or
`generator` mode; and, in a program with a `Supervisor`, an `array` or
`generator` node that reaches no fanout family counted by a command line
option. The editor offers none of them, and script generation refuses them in
program metadata written by hand or by another tool.

**A node of a module, reused.** In a general program the dialog that names a
new process suggests the processes that the modules of the preamble define,
and copies the description, the options and the code of the one chosen. In a
resident program it suggests only the nodes among them: the processes whose
Python heredoc declares a class that derives from a class of the runtime
library, never a `Supervisor`, which the user does not edit and which a
program has once, each with its node kind, which the dialog then shows instead
of offering a choice. A node is told from the processes around it, since its
heartbeat channel is recognized by the `Supervisor` that reads it, so the
processes that the preamble defines are read together, as a resident module
made of the preamble and a program that adds all of them. The node chosen is
copied by the rules of import: its node kind comes from the base of its class,
its code is decomposed into the parts of a node, and its options lose the
Supervisor wiring, which script generation derives again, and their
connections, which belong to the program it came from; its description and
the mode of its options handler come with it. A node that does not fit is
refused with the same explanation as import gives, which the dialog shows;
only its own problems count, whatever the other processes of the preamble
hold. Its name is kept, so its class keeps the name that the engine
requires.

## The directories of a resident program

**The home directory** is the same as for a general program (see "The home
directory"): the program metadata, the generated script and the user files,
with the same guarantees.

**The output directory** holds, besides what a general run leaves there, the
program state: what each node keeps across runs, its checkpoints, its input
log and its halted marker, in its execdir, and the output directory of its
process, which the engine does not empty when it launches a node again (see
"Ordered shutdown" in `doc/design_doc_resident.md`). A resident program is
resumed from that state every time it is launched on the same output
directory, so the output directory of a resident program is part of the
program in a way that the output directory of a general program is not. The
rules that keep the two directories apart apply unchanged. Besides the run
log, the web UI adds to it the launch record (see below) and the snapshot log
(see "Running a resident program").

**Resetting.** "Reset output directory" gives way to "Reset program state",
which runs `debasher_reset_resident` on the output directory: it takes the
program state away, for every task of every process, and the next launch
starts every node afresh. By default the tool sets the state aside under
`__reset__/<timestamp>/` in the output directory, since a checkpoint that is
lost cannot be made again, and the dialog offers to delete it instead
(`--delete`). As for a general program, the frontend refuses to reset while
there is a run in progress, and the tool refuses it too. What is set aside
stays in the output directory until the user deletes it.

**Launching a program with state.** A node resumes from its checkpoint and
replays its input log with the code that the program has when it is launched,
not the code that produced them. A program changed since its state was
produced may therefore not resume correctly: a new `restore_node_state` may
not read an old node state, a new `process_data` replays the input log to
another result, and a checkpoint keys its bookkeeping by the names of the
ports, which the engine does not compare with the ports the node has now. A
change of the command line options, such as the number of tasks of an array,
needs a fresh start too. While the program lives, it cannot change, since a
save is refused while there is a run in progress. Between a stop and the next
launch it can, and saving stays free: the check is made when the program is
launched.

- Every launch leaves in the output directory the launch record, a copy of the
  generated script and of the program options with which it was launched.
- When "Run program" finds program state in the output directory, and the
  generated script or the program options differ from the launch record, the
  frontend asks whether to resume with the changed program, the user answering
  for its compatibility, or to reset the program state first and start afresh.
- The comparison leaves out the `_document` functions, so that a change of a
  description asks nothing. The positions on the canvas are not in the script.
- With program state and no launch record, as when the state comes from a run
  launched outside the web UI, the frontend asks all the same, and says that it
  cannot tell which program produced the state.

The backend finds the program state by the names that the engine gives to it
in the output directory, the same that `debasher_reset_resident` takes away,
and would have to change with them. The check sees only the generated script
and the program options: a change in a module that the preamble loads goes
unseen.

## Running a resident program

A resident program is launched with `debasher_exec` and followed with
`debasher_status`, as a general one, but a run of it never finishes on its own:
its nodes run until they are stopped, and each launch on the same output
directory resumes them. This subsection says, for each action of "Execution
and observation" that runs or stops a program, whether it applies unchanged,
changes, or is replaced.

**Launching and resuming.** "Run program" launches a resident program with
`debasher_exec` (see "Launching a run"), and resumes it with the same command:
on an output directory with program state, the engine launches again every
process that is not in progress, and each node resumes from its checkpoint.
For a resident program the engine forces the built-in scheduler in oneshot
mode, in which `debasher_exec` launches every process at once and ends without
waiting for any. The command changes accordingly:

- `--sched BUILTIN` always, since the engine refuses any other scheduler, and
  the execution options offer no choice of scheduler;
- no `--wait`, which does nothing with the built-in scheduler;
- `--builtinsched-cpus` and `--builtinsched-mem` as for a general program: the
  engine refuses the launch, before starting any process, when the processes
  do not all fit in them at once;
- no `--dflt-throttle`, since every task of a node has to run at once, nor
  `--rerun-outdated-procs`, since a resume already launches every process
  again;
- no `--dflt-nodes`, which only the Slurm scheduler reads, nor
  `--conda-support` or `--docker-support`, all three meant for general
  programs. The batch runs that a `ProgramLauncher` launches are general
  programs, where these options would apply, but a `ProgramLauncher` cannot
  give them today (see "Future work" in `doc/design_doc_resident.md`).

**The launch within the request.** Since `debasher_exec` ends as soon as every
process is launched, `/run` waits for it, instead of starting it detached, and
answers with its exit code and what it printed, which the frontend shows when
the launch fails. A program that the engine refuses when it loads it, such as a
node that no initiator reaches, is thus reported at once, as "Run program
(debug)" reports it, and not only in the run log. The output of
`debasher_exec` still goes to the run log, a file, and the backend reads it
once `debasher_exec` ends: a pipe would be inherited by the processes it
launches, and the request would wait for them.

**The launch record at launch time.** `/run` goes through these steps:

1. With a run in progress, it answers with a conflict and does nothing, as for
   a general program.
2. With program state in the output directory and a launch record that differs
   from the program, or none, it answers with a conflict, unless the request
   says that the user chose to resume with the changed program (see "The
   directories of a resident program"). The frontend asks before sending the
   request, and the backend checks again, since it keeps no state and another
   tab may have launched the program in between. A user who chooses to start
   afresh has the frontend reset the program state first and then send the
   request.
3. It saves the program and generates the script.
4. It runs `debasher_exec`.
5. It writes the launch record only when `debasher_exec` ends with 0, and
   leaves the previous one otherwise.

The last step errs on the side of asking. Take a program P1 that left program
state and the launch record R1, changed into P2 and launched. When the launch
fails before starting any process, the state is still that of P1, and R1 has
to stay so that the next launch asks again. When it fails after starting some
node, part of the state is already that of P2, and R1 only makes the next
launch ask when it need not. A record written before the launch, or after any
launch, would do the reverse: miss a question when the state comes from
another program.

"Run program (debug)" and "Check program options" apply unchanged.

**Stopping in order.** "Stop program" is replaced by the orderly stop, which
runs `debasher_stop_resident -d <output directory>` with its default timeout:
the tool halts every node in one round, then stops the nodes, the `Supervisor`
first (see "`debasher_stop_resident`: the graceful stop tool" in
`doc/design_doc_resident.md`). It runs within the request, which lasts until
the program has stopped, up to about the timeout of the tool, and the frontend
shows the program as stopping and offers no other action on it meanwhile. A
tab closed during the stop does not interrupt it. The options `-x` and
`--keep-supervisor` are not offered, since they exist for the escalation of the
`Supervisor`. The frontend tells the user what the exit code of the tool means:

- 0: an orderly stop. Every node halted in the same round, and the next launch
  resumes the program with nothing lost.
- 2: the orderly stop did not end within the timeout, and the tool fell back to
  the hard kill of `debasher_stop`. The program has ended, but was killed: each
  node resumes from its last checkpoint and its input log, and what the FIFOs
  held may be lost, at most what a pipe holds for each business channel, which
  the nodes that read them report as a gap in the sequence numbers when they
  resume.
- 1: an error of usage or setup, reported with what the tool printed.

**Killing.** "Kill program" runs `debasher_stop` on the output directory, the
hard kill, after the user confirms it with the same warning as for exit code 2.
It stays as an action of its own, next to "Stop program", for a program known
to be stuck, whose orderly stop would only reach the hard kill after the
timeout.

Both actions are offered only while there is a run in progress, where "Stop
program" for a general program needs only an output directory. The orderly
stop of a program with no node alive would find no reader for its triggers,
and would end in a hard kill that kills nothing, reported as exit code 2.

**Restarting a node.** "Stop process" runs `debasher_stop -p <process>`, which
kills every task of the process at once. In a resident program that is a crash
of the node, not a stop: the node leaves no mark of a clean end, and the
`Supervisor` relaunches it, from its last checkpoint and its input log (see
"Relaunching a downed node" in `doc/design_doc_resident.md`). The action is
named for what it does, "Restart node", and is offered as follows:

- In a program with a `Supervisor`, on every node but the `Supervisor`, after
  the user confirms it with a warning: the node restarts from its last
  checkpoint and replays its input log, and what its FIFOs hold is kept by
  the peers at their other ends (see "Ghost connections" in
  `doc/design_doc_resident.md`). Only a channel whose two ends are restarted
  together, a self-loop of the node or a channel between two tasks of the
  process, relies on the `Supervisor` to hold it, and may lose what it held
  when the program was launched with `-no-hold-fifos`, which the warning then
  says. It serves to free a node that is stuck, or to try the recovery of a
  program. A node restarted again and again before it sends a heartbeat
  counts for the `Supervisor` as a node that crashes after every relaunch, and
  after a few times the `Supervisor` gives up on it and stops the program (see
  "Escalation on a permanent node failure" in `doc/design_doc_resident.md`).
- Not on the `Supervisor`, which nothing supervises: the nodes would go on
  without anyone to relaunch them or to hold their FIFOs, until the next stop.
- Not in a program without a `Supervisor`, where nothing would relaunch the
  node: it would stay down until the whole program is stopped and launched
  again, since `debasher_exec` launches nothing while there is a run in
  progress. Meanwhile each node that writes to it blocks once the pipe is
  full, and its outbound backlog grows until the node fails.

On an `array` or `generator` process the action restarts every task, since
`debasher_stop` stops a process as a whole.

**Snapshots.** The nodes of a resident program write checkpoints and prune
their input logs only when a round closes, and a round starts only when a
trigger comes from outside the program. `debasher_snapshot_resident` writes
that trigger (see "`debasher_snapshot_resident`: rounds from outside the
program" in `doc/design_doc_resident.md`). With no rounds, the input logs grow
until their size cap stops the nodes. The web UI starts rounds in two ways.

"Take snapshot" starts one round: it runs
`debasher_snapshot_resident -d <output directory>` within the request, with
the default timeout of the tool, and shows what its exit code means. With 0,
the round closed at every node, and the frontend shows its epoch. With 2, the
round did not close at some node, because the node is down, has halted or has
a halt open, and the frontend names the nodes. With 1, an error of usage or
setup. The action is offered only while
there is a run in progress, and works as well on a program launched from the
command line.

Periodic snapshots are off by default, and the user turns them on with
`executionOptions.snapshotEverySecs`, a field of the execution options of a
resident program, saved in the program metadata. The dialog says what an empty
field means (no rounds but those of "Take snapshot", and input logs that grow
until their size cap), and that the period has to be longer than a round
takes, or each round replaces the one before it and none closes. With a
period, `/run`, once `debasher_exec` has ended with 0, starts
`debasher_snapshot_resident -d <output directory> --every <period>` detached,
in a session of its own, with its output in the snapshot log, and answers
without waiting for it. The tool ends by itself once no node of the program
runs, whatever stopped the program, so nothing has to stop it and the backend
keeps nothing of it. Every launch from the web UI starts it again, as a program
that is resumed needs.

- The period cannot change while the program lives, since changing it would
  mean finding the running tool, which leaves no PID on disk. A new period
  applies from the next launch.
- The period is not part of the launch record: it does not change which
  program state the program can resume from.
- The web UI starts one periodic tool for each launch. A second one, started
  by hand on the same output directory, would start rounds that replace the
  rounds of the first. The tool does not refuse it today (see "Future work"
  in `doc/design_doc_resident.md`).
- A round of "Take snapshot" during periodic snapshots replaces the open
  periodic round, or is replaced by the next one, and the tool reports which
  round did not close.

**The run phase of a resident program.** The run phase of a general program
follows only a run launched from the tab, and becomes `finished` once every
process has finished. Neither holds for a resident program. After an orderly
stop every node has ended cleanly, and `debasher_status` reports every process
finished, although the program has not finished but stopped, and resumes at
the next launch. And a program that outlives the tab has to show as alive to
any tab that opens it. The run phase of a resident program is therefore
derived from the process statuses, which are read whoever launched the program
(see "Following a run"), and takes these values:

- `new`: there is no program state in the output directory, and the next
  launch starts every node afresh.
- `live`: at least one process is in progress. A node that is down, or being
  relaunched by the `Supervisor`, shows in the color of its canvas node, not
  in the run phase.
- `stopped`: no process is in progress, and there is program state. The
  frontend tells a program stopped in order, every process of which is
  finished, from one stopped abruptly, some process of which is not: after a
  hard kill, a `Supervisor` that gave up on a node, which stays down, or a node
  that failed in a program without a `Supervisor`. The user thus knows,
  before launching it again, whether the program may have lost something
  when it stopped.
- `launching` and `stopping`: while a request of this tab to launch the
  program, or to stop or kill it, has not been answered.

A program may stop with no action of the web UI, when its `Supervisor` gives up
on a node, and the run phase goes from `live` to `stopped` at the next reading.
The rule of two readings in a row does not apply: it covers the gap between one
process ending and the next starting, and the processes of a resident program
all start at once.

**The guards.** The guards that depend on a run in progress apply unchanged,
since they already read the process statuses and not the run phase: while the
program is `live`, the frontend refuses to save, to reset the program state and
to change the output directory, and `/run` refuses to launch. What changes is
which actions are offered only while the program is `live`: "Stop program",
"Kill program", "Restart node" and "Take snapshot". What the tab does with a
live program when it is closed, reloaded or leaves the editor is in "A program
that outlives the tab".

## Observing and talking to a live program

A resident program is observed through the same process statuses as a general
one, and through what each node keeps in its execdir: its checkpoints, its
input log and its halted marker. This subsection says which actions of
"Execution and observation" apply to a live program, which change, and what the
web UI reads of the state of a node.

**The process statuses.** The canvas colors each node by the status of its
process, read with `debasher_status` every five seconds, as for a general
program (see "Following a run"). The statuses are the same, but mean something
of their own in a resident program, which the legend of the canvas says:

- `IN-PROGRESS`: the node is alive, which it still is after a halt and until
  its stop signal.
- `FINISHED`: the node ended cleanly, after an orderly stop.
- `UNFINISHED`: the node is down. In a live program, the `Supervisor` is
  relaunching it or has given up on it, or, without a `Supervisor`, nothing
  will bring it back. In a program that is not live, it stopped abruptly.
- `UNFINISHED_BUT_RUNNABLE`: shown as `UNFINISHED`, since in a resident program
  no process waits to be run later.
- `TO-DO`: the node has not been launched.

The status is that of a process, not of each of its tasks: an `array` or
`generator` process is `IN-PROGRESS` while any of its tasks is alive, even
with another one down. What the status does not tell is shown by "Show node
state" (see below), for each task, and not on the canvas,
where a status for each task would multiply the reading every five seconds by
the number of tasks. Whether a node that is down is being relaunched or has
been given up is known only to the `Supervisor`, which writes it in its log,
and the web UI does not guess it.

**Inspecting a process.** The actions of "Inspecting a process" apply
unchanged, with the same choice of task for an `array` or `generator`
process: "Show stdout", "Show scheduler output", which for the `Supervisor` is
its log, "Show options" and "Show inputs and outputs".

**Inspecting a node.** "Show node state", a new action of the context menu of
a node, shows what the node keeps in its execdir, read only, in three views:

- The summary: whether the task is alive, finished or down, read as
  `debasher_status` reads it but for the task alone, the epoch of the latest
  checkpoint and when it was written, the halted marker, the size of the input
  log against its cap, how many records lie above the `capture_pos` of the
  latest checkpoint (what the node would replay if it crashed now), the size of
  the outbound backlog against its limits, the cap and the limits being those
  in force for the node, which it writes into its node info file, and whether
  every thread of the node was alive at its latest heartbeat tick. These are
  the figures that warn of a coming failure: with no rounds, the input log
  grows until its cap stops the node, with a reader that does not read, the
  outbound backlog grows until it does, and a node with a dead thread shows as
  `IN-PROGRESS` while it does nothing.
- The checkpoints: the list of those that the node retains and, for the one
  chosen, its `node_state`, formatted, together with the messages in transit
  that it holds, `channel_state` and `out_backlog`, counted by port.
- The input log: its latest records, which the user can filter by port, cut
  at the same number of lines as the other outputs.

The backend reads none of these files itself. An engine tool,
`debasher_inspect_resident -d <output directory> -p <process> [-t <index>]`,
reads them for it, with a command for each view (`summary`,
`checkpoint <epoch>` and `log`), and prints what it reads as JSON. The files
of a node follow rules that the tool applies as the node does when it
recovers: a last record torn by a crash does not count, a segment of the input
log that the node prunes while the tool reads it is skipped, and a checkpoint
of another schema version is reported as such. The same tool serves from the
command line (see "`debasher_inspect_resident`: what a node keeps" in
`doc/design_doc_resident.md`).

**The batch runs of a `ProgramLauncher`.** "Show batch runs", an action of the
context menu of a launcher node, lists the batch runs that the node has
registered, one row each: its name, its run directory, its state (registered,
running, finished, failed with its exit code, or stopped before it ended) and
its exit code. From a row the user can read its `launcher.log`, read what
`debasher_status` says of its run directory when the batch run is a whole
general program, and open the run directory as any other path (see
"Inspecting a process"). The state of a batch run is the one that the node
itself deduces from the run directory (see "Launching from the queue on disk"
in `doc/design_doc_resident.md`), and the same engine tool computes it, with a
command of its own, `runs`, from the code of the launcher node, so that the
rule is written once. Launching again a batch run that failed is not offered
until the engine has a command for it (see "Future work" in
`doc/design_doc_resident.md`).

**A `DirectoryWatcher`** has no view of its own. The files that it has asked
to launch are in its node state, which "Show node state" shows, and the
directory it watches is the value of its option `-watchdir`, which "Show inputs
and outputs" opens.

**Watching a FIFO.** "Watch FIFO" is not offered, since the engine refuses
`--mirror` in a resident program, and there is no mirror log to read. The
input log of a node takes its place for the channels read inside the program:
the records of one port are what arrived through that channel, and reading them
takes nothing from it. What a node writes out of the program, through a
business output with no reader, is recorded nowhere; "Talk to FIFOs" reads it.

**Talking to FIFOs.** "Talk to FIFOs" stays, and changes in what it offers and
in what it writes and reads, since every line on a channel of a resident
program is an envelope, a JSON object of one line (see "Control envelope" in
`doc/design_doc_resident.md`). It is offered while the program is `live`,
whoever launched it, and not only while a run of the tab is running, and only
for two sorts of FIFO:

- An external input, into which the user writes.
- A business output with no connection, from which the user reads.

The control ports, the manual trigger port of the `Supervisor` and the rest of
the Supervisor wiring are not offered. Their commands have actions of their
own, "Take snapshot" and "Stop program", which number a trigger and send it to
every initiator at once, where a command written by hand into one port would
open a round that never closes.

**Writing.** The user gives the payload, and the backend wraps it in a `DATA`
envelope with no sequence number, since what comes from outside the program is
not numbered, and writes it as one line: `{"type": "DATA", "payload": ...}`.
The dialog has two modes. In JSON mode, the default, the user writes any JSON
value, over several lines if need be, which the backend parses and serializes
again on one line, and `process_data` receives it with its type: an object, a
list, a number. Text that does not parse is refused, and nothing is written. In
text mode what the user writes is sent as a JSON string. A raw line is never
written: a reader takes a line that is not JSON for the fragment of a writer
that died in the middle of a message, and a second one in a row kills its
thread, and with it the node. A write ends once the line is in the pipe, not
once the node has logged it, which its input log shows afterwards, and it is
bounded as for a general program.

The web UI never writes a `CLOSE` into an external input. A `CLOSE` closes the
port for good, across every resume until the program state is reset, and the
code of the node never learns of it, since no hook reports it (see "Future
work" in `doc/design_doc_resident.md`). A source that wants to tell a node that
it has finished sends a `DATA` with a payload that the node understands.

**Reading.** The backend reads the FIFO one line at a time, as for a general
program, and decodes each envelope. Within the same bound it skips the blank
lines and the `HELLO` with which every incarnation of a writer starts, and
answers with the type and the payload of the first other envelope. The
frontend shows the payload of a `DATA`, with its sequence number, marks a
`BARRIER` as the marker of a round and a `CLOSE` as the end of the writer.
Reading takes the message from the channel, as it does for a general program,
and so competes with any other reader outside the program. A business output
that nobody reads fills its pipe, and then the outbound backlog of its node,
until the node fails; "Show node state" shows the backlog growing.

## A program that outlives the tab

A resident program is meant to live longer than any tab that follows it, and
longer than the backend that launched it. The rule that a tab stops the run it
launched (see "Where the state lives") holds for general programs only. This
subsection says what replaces it, and what happens to a live program when the
tab or the backend goes away and comes back.

**The tab.** Nothing that happens to a tab stops a resident program: closing or
reloading it, leaving the editor, or dismissing the indicator of the program.
Only "Stop program", "Kill program" and the escalation of the `Supervisor` stop
it (see "Running a resident program"). The tab asks nothing when it is closed:
the browser shows only a generic warning, which could not say that the program
goes on, and would show it every time, when going on is what a resident
program is for.

Leaving the editor while the program is `live` shows a short notice, which
blocks nothing: the program goes on in its output directory, and is stopped by
opening it again and using "Stop program". This is the only moment at which the
web UI can say where the program lives. The backend keeps no record of it, and
the home screen cannot list the live programs, since it does not know which
output directories exist. A program is found again by loading it from its home
directory: its program metadata holds its output directory, and its run phase
comes from the process statuses of that directory.

A request of the tab that is still pending when the tab goes away, to launch
or to stop the program, goes on in the backend to its end. The tab loses the
answer, and whichever tab opens the program next sees the result in the process
statuses.

**The backend.** A live program depends on the backend for nothing: once
`debasher_exec` has ended, its nodes, its `Supervisor` and the periodic
`debasher_snapshot_resident` run on their own. What the backend has to ensure
is that nothing it starts dies with it, or in the middle of what it was doing.
Two things could make it so. What the backend starts belongs to the session of
the server, even if the built-in scheduler puts each process in a process group
of its own, and a signal that stops the server, from its terminal for example,
could reach it. And a tool whose output goes into a pipe read by the backend
dies of `SIGPIPE` at its next line once the backend is gone: an orderly stop cut
that way could leave the `Supervisor` stopped and the nodes alive, with nobody
to relaunch them.

So every tool that acts on a live resident program (`debasher_exec`,
`debasher_stop_resident`, `debasher_stop` and `debasher_snapshot_resident`,
once or with `--every`) runs in a session of its own, as the batch runs of a
`ProgramLauncher` do, and writes into a file, never into a pipe:
`debasher_exec` into the run log, the periodic snapshots into the snapshot log,
and the stop, the hard kill and a single snapshot into a temporary file of
their own, since two tabs may run them at the same time, which the backend
reads when the tool ends and then deletes. Whatever the program launches later,
the relaunches of the `Supervisor` included, inherits the session of
`debasher_exec`, away from the server.

A request that the backend does not finish, because it went away in the
middle, still reaches its end in the tool; only its answer is lost:

- a launch ends, but its launch record is not written, and the next launch
  compares the program with the record left before it, which errs on the
  side of asking (see "Running a resident program");
- a stop ends with the program stopped, which the run phase shows once the
  backend is back;
- a round of "Take snapshot" closes or not, which "Show node state" shows;
- a temporary file that the backend did not delete stays in the temporary
  directory of the system, with no other effect.

When the backend comes back there is nothing to recover, since it keeps no
state: the next reading of the process statuses shows the program as it is.
General programs keep their own rule: they are stopped with their tab, and
nothing of this applies to them.

**Opening a live program again.** A tab opens a live program by loading it
from its home directory, like any program: its program metadata gives the
output directory, the process statuses give the run phase `live`, and every
action on a live program is offered, whoever launched it, another tab or the
command line. What the tab does not have is the answer to a request of another
tab; the run log of a launch that it did not make is still there to read. The
period of the periodic snapshots comes from the program metadata, which a save
cannot change while the program is `live`, so it is the period of the launch,
unless the program was launched from the command line, with no periodic
snapshots of the web UI; the dialog of the execution options therefore says
that a period applies from the next launch from the web UI.

A live program can be edited in the tab, but not saved (see "Running a
resident program"). Its changes are saved once it has stopped, and the next
launch compares them with the launch record.

Two tabs on the same live program are not coordinated, as for a general
program (see "Non-goals"). What the engine's files guard still holds: a second
launch is refused while there is a run in progress. Two orderly stops at the
same time, or an orderly stop and "Restart node", are not coordinated by the
web UI; a single orderly stop for each output directory is left to the engine
(see "Future work" in `doc/design_doc_resident.md`).

**What is not guaranteed.**

- **A restart of the machine.** Every process of the program dies with it, and
  nothing launches the program again when the machine starts. The program then
  shows as stopped abruptly, since its processes did not end, and "Run program"
  resumes it. As after a hard kill, what the pipes held is lost, which the nodes
  that read them report as a gap in the sequence numbers. Starting resident
  programs with the machine would need mechanisms of the operating system that
  are not portable.
- **Being told that the program stopped.** A program that stops by itself, when
  its `Supervisor` gives up on a node, while no tab follows it, is not reported
  to anyone. The next tab that opens it sees it in its run phase.
- **A list of the live programs.** A live program is found by loading it from
  its home directory; the web UI keeps no record of the programs it launched,
  since the backend keeps no state.
- **A `Supervisor` that nothing supervises.** If the `Supervisor` dies, its
  canvas node shows `UNFINISHED`, and the web UI does not relaunch it: the
  program goes on without relaunches until its next stop, as the failure model
  of `doc/design_doc_resident.md` says (see "Supervising the `Supervisor`" in
  its Future work).

## The canvas of a resident program

*In progress: what a canvas node shows, its handles and the legend are built;
the self-loop and the Supervisor wiring are not.*

The canvas of a resident program draws the same processes and connections as
that of a general one (see "From the store to the canvas"), and shows besides
what a resident program adds: the node kind and the role of each node, the
handles that its options take or not, the Supervisor wiring and the self-loop.
As for the rest of the canvas, this subsection says what the canvas shows and
the rules it keeps, not how it looks: a mark may be an icon, a label or a
shape.

**What a canvas node shows.** A canvas node of a general program already gives
its background to the process status, the style of its border to the options
handler mode and the color of its border, with a badge, to its group. A
resident program has no groups and no `manual` mode, and what it adds is shown
with marks of its own, which take none of those:

- **The node kind**, always, with a mark in the head of the canvas node:
  `FBPProcess`, `ProgramLauncher`, `DirectoryWatcher` or `Supervisor`. The
  `Supervisor` also stands apart from the other canvas nodes at a glance, since
  it is not a business node and the user does not edit its code.
- **An initiator**, with a mark of its own, since rounds start there, and
  since a node that no initiator reaches is what the engine refuses when it
  loads the program; the user sees it without showing the Supervisor wiring.
- **A node that observes the outside world**, with a mark of its own: an
  `FBPProcess` with a body for `observe`, and every `ProgramLauncher` and
  `DirectoryWatcher`, whose classes implement it. The observe port is a name,
  not a fifo, and has no handle (see "Observing the outside world" in
  `doc/design_doc_resident.md`).
- **An `array` or `generator` process**, with the double border, as in a
  general program, since each of its tasks is a node of its own.

The color of the border and the badge of a group stay unused in a resident
program, rather than taken for the node kind, so that the same mark never
means two things depending on the type of the program.

**The handles of a node.** In a general program every option has a handle,
the inputs along the top and the outputs along the bottom. In a resident
program an option has a handle only when a connection can reach it, since the
canvas accepts only a connection from a business output to a business input
(see "The program model of a resident program"), and a handle shows what the
option is:

- A business output has a handle along the bottom. With no connection it is
  read outside the program, and a mark says so: something outside has to read
  it, or the outbound backlog of the node grows until the node fails, and it is
  where "Talk to FIFOs" reads.
- A business input has a handle along the top, which accepts one connection,
  from a business output. An input that a connection can reach has it before
  it is connected too, even while it holds a literal value, such as the index
  of a task (`-id ${idx}`): the canvas node draws it as any other input, and
  the editor of the option shows its value.
- An external input is drawn along the top with the other inputs, with a
  handle that accepts no connection and a mark that says that it is written
  from outside the program. It is where "Talk to FIFOs" writes, and where the
  activity of the program comes in, which the canvas thus shows.
- A configuration option that no connection can reach has no handle: a flag, a
  command line option, an option taken from the process specifications, or an
  output with option channel `none`. The canvas node lists it apart from the
  inputs, so that it does not look like an input left unconnected. The
  `Supervisor` lists among its own the flag `-no-hold-fifos`, which script
  generation writes and each run sets, although the program model does not
  hold it.
- The options of the Supervisor wiring are not in the program model, and have
  no handle unless the wiring is shown.

The side of each handle, and the pair of handles that the canvas moves between
two processes that answer each other, are as in a general program. Every edge
of a resident program comes from a FIFO, so every edge is dashed, which tells
nothing apart here, but keeps one convention for both types of program.

**The Supervisor wiring.** The Supervisor wiring is hidden by default: with
many nodes its heartbeat channels would fill the canvas, and the user edits
none of it. An action of the context menu of the `Supervisor` shows it and
hides it again. Whether it is shown belongs to the tab, like the selection, and
is not saved. A program without a `Supervisor` has nothing to show: the control
ports of its initiators are written by the tools, not by the user, and the mark
of an initiator already says where they are.

The wiring shown is derived from the store, by the same rule with which script
generation derives it: from whether the program has a `Supervisor`, from its
nodes and from which of them are initiators (see "The program model of a
resident program"). Drawing it needs that topology only, not the labels that
script generation gives to its channels, which the frontend therefore does not
repeat. The canvas draws:

- a heartbeat channel from every node to the `Supervisor`, a single edge for an
  `array` or `generator` process, drawn as a fanout edge, since the
  `Supervisor` reads its heartbeat channels as a fanout family;
- a trigger port from the `Supervisor` to every initiator, whose handle on the
  initiator carries a mark of its own instead of the round handle;
- the manual trigger port of the `Supervisor`, as a handle marked as written
  from outside the program, like an external input.

The edges and handles of the wiring are read only: they are drawn apart from
the business channels, cannot be selected or deleted, and accept no
connection, so that the Supervisor wiring is never drawn by hand on the canvas
either. The `Supervisor` itself is placed and moved like any node, and its
position is saved; only its wiring is derived.

**The self-loop.** A self-loop is how a node of a resident program feeds
itself (see "The program model of a resident program"), and the canvas draws it
next to its node: from its output handle, along the bottom, around the right
side of the node, clear of its box, to its input handle, along the top. It
does not take the lane of the back edges to the right of every process, which
joins processes far apart, and along which a node that feeds itself would be
hard to tell in a wide program. Several self-loops of the same node are drawn
apart from each other, each at a height and a distance that follow the place
of its handles, as the back edges that leave the same node are. The same
drawing applies to a self-loop of a general program, which "From the store to
the canvas" routes along the lane of the back edges.

**The structural key and the legend.** The rule of "Keeping the canvas in step
with the store" holds: whatever a canvas node draws from its process is part
of the structural key, or the canvas node reads it from the store, as it reads
the process status. What a resident program adds follows it this way:

- The structural key gains, for each process, its node kind, whether it is an
  initiator and whether it observes the outside world, which for an
  `FBPProcess` depends on whether its body of `observe` is empty; for each
  option, which of the sorts of "The program model of a resident program" it
  is (a business output, an input that a connection can reach, an external
  input or a configuration option), which decides whether it has a handle and
  of what sort; and whether the Supervisor wiring is shown. The last
  belongs to the tab, not to the program, but it adds and removes handles on
  the canvas nodes, which the canvas library takes only when the list of
  canvas nodes is refreshed.
- The mark of a business output read outside the program depends on the
  edges, which change with every connection and are not part of the
  structural key. A canvas node reads it from the store, so that a connection
  does not refresh the list of canvas nodes.

The canvas of a resident program has a legend, which the user can fold. It says
what each process status means in a resident program (see "Observing and
talking to a live program"), and what each mark means: the node kind, an
initiator, a node that observes the outside world, an external input, a
business output read outside the program, and a trigger port.

## Guarantees and non-goals of a resident program

This subsection gathers the guarantees that the design of resident programs
gives, stated in the subsections above, and what it deliberately does not try
to do, as "Guarantees and non-goals" does for general programs. Those of
general programs that the subsections above keep hold for resident programs
too.

**The program model and the round trip**

- **The node kind and the code agree.** Script generation writes the class
  declaration from the node kind, and the class is named after the process
  (see "The program model of a resident program").
- **The Supervisor wiring is always complete.** It is derived every time, and
  never saved or drawn by hand, so adding or removing a node cannot leave it
  half done (see "The program model of a resident program").
- **Only connections that the engine accepts.** The canvas joins a business
  output to a business input only, and offers neither `value_desc`,
  `shared_dir` nor `--mirror` (see "The program model of a resident program").
- **The code of a node is imported exactly, or refused.** Import keeps the
  parts of a node, or refuses the program with an explanation for each node
  that does not fit; it never keeps an approximation (see "Script generation
  and import of a resident program").

**The program's directories**

- **No resume with a changed program without asking.** A launch on program
  state compares the program with the launch record, and asks when they
  differ or when there is no record; when in doubt it asks. A change in a
  module that the preamble loads goes unseen (see "The directories of a
  resident program").
- **A reset loses no checkpoint unless asked to.** "Reset program state" sets
  the program state aside by default (see "The directories of a resident
  program").
- **No change under a live program.** While the program is `live`, the
  frontend refuses to save, to reset the program state and to change the
  output directory (see "Running a resident program").

**Execution and observation**

- **A failed launch is reported at once.** `/run` waits for `debasher_exec`
  and shows what it printed (see "Running a resident program").
- **One live program per output directory.** A launch is refused while there
  is a run in progress.
- **A hard kill is never taken for an orderly stop.** The exit code with which
  `debasher_stop_resident` reports that it fell back to `debasher_stop` is
  shown as such (see "Running a resident program").
- **Nothing that the web UI writes can bring a node down.** "Talk to FIFOs"
  writes only `DATA` envelopes into external inputs, never a raw line, a
  `CLOSE` or a command into a control port (see "Observing and talking to a
  live program").
- **Inspecting takes nothing from the program.** "Show node state" only reads,
  with the rules of recovery, and the input log shows what arrived through a
  channel without reading the channel (see "Observing and talking to a live
  program").
- **Any live program is observed and controlled**, whoever launched it (see
  "Observing and talking to a live program").

**A program that outlives the tab**

- **Nothing that happens to a tab or to the backend stops the program, or
  cuts a tool in the middle.** No event of a tab stops a resident program, and
  every tool that acts on it runs in a session of its own and writes into a
  file (see "A program that outlives the tab").
- **Nothing is lost when the backend restarts**, as for a general program.

**Non-goals**

- **Coordinating two tabs.** Two orderly stops of the same program at the same
  time, or a stop and "Restart node", are not coordinated by the web UI; a
  single orderly stop at a time is left to the engine.
- **Surviving a restart of the machine.** Nothing launches a resident program
  again when the machine starts.
- **Telling anyone that a program stopped by itself.** The next tab that opens
  it sees it.
- **A list of the live programs.** A live program is found by loading it.
- **Supervising the `Supervisor`.** A `Supervisor` that dies is shown, not
  relaunched.
- **Holding any resident module.** A module whose `Supervisor` has code of its
  own, or whose nodes do not fit the parts of a node, is refused, not
  approximated.
- **A status for each task on the canvas.** The canvas shows one status for
  each process, and "Show node state" the state of each task.
- **Changing the period of the snapshots of a live program.** A new period
  applies from the next launch.

# Future work

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
- **The output directory of a moved program.** Deciding what a program
  loaded from a new place should do with an output directory that still
  points to the old one.
- **A prompt for writing the code of a process.** A button on a process
  that composes, from the program model, a prompt to copy into an AI tool of
  the user's choice: the description of the process and of its program, its
  node kind, its options with their direction, data type, option channel and
  description, what reaches each connected input (the description of the
  output it comes from), the signature of the function or hook to write, how
  a process of its language reads its options, and, for a node of a resident
  program, the obligations of the contract that its code has to keep (a
  deterministic `process_data`, sending only from it, a complete
  `capture_node_state` and an exact `restore_node_state`). Nothing leaves the
  machine: the user copies the prompt, and pastes the answer into the editor.
- **An assistant on the documentation of DeBasher.** A chat in the web UI
  that answers questions about DeBasher from its documentation (the
  documentation of the project, the design documents and the module
  documentation of the modules at hand), through a model of an AI service with
  a key that the user gives. Not designed. It needs a place for the key that
  fits a server with no authentication, never the program metadata; it sends
  the documentation, and maybe the program, to a service outside the machine,
  which the user has to know; and its answers are only as good as a
  documentation kept in step with the code.
- **A legend for a general program.** A legend of the canvas like that of a
  resident program (see "The canvas of a resident program"), which says what
  the colors of the process statuses and the styles of the borders and edges
  mean.
- **Closing an external input.** An action of "Talk to FIFOs" that writes a
  `CLOSE` into an external input, to tell a node that its source has
  finished, once the engine has a hook that lets the code of a node learn that
  a port closed.
- **A batch run opened as a program.** Loading the general program of a
  launcher node with a run directory as its output directory, to follow the
  batch run on the canvas, colored by the statuses of its processes. The
  general program may not have been made with the web UI, and opening it must
  not write into its directory.
- **Relaunching a node by hand.** An action of the context menu of a node
  of a resident program without a `Supervisor`, which relaunches a node that
  is down with `debasher_launch_process`, as the `Supervisor` does. With it,
  "Restart node" could also be offered in such a program. The peers of the
  node hold its FIFOs while it is down, so only a channel whose two ends are
  down together, such as a self-loop, may lose what it held.
- **Restarting one task of a node.** "Restart node" on a single task of an
  `array` or `generator` process, which needs `debasher_stop` to stop one
  task.
- **Building the web UI for resident programs.** Building what "Resident
  programs in the web UI" designs, where a subsection does not say that it is
  built.
- **What the web UI waits for from the engine.** Several parts of the design
  of resident programs rely on engine work listed in the Future work of
  `doc/design_doc_resident.md`: what the `Supervisor` knows of each node,
  written to disk; a single orderly stop at a time; a single periodic
  `debasher_snapshot_resident`, which leaves its PID in the output directory;
  the execution options of the batch runs of a `ProgramLauncher`; a hook for
  the code of a node to learn that a port closed; a command to launch again a
  batch run that failed; and an alias of a node. Restarting one task of a node
  needs, besides, `debasher_stop` to stop a single task.
- **The consistent cut of an epoch.** A view of the whole program at a round
  that closed: the node state and the channel state that every node keeps in
  its checkpoint of that epoch, together, which is the state that the program
  could really have been in (see "consistent cut" in the Glossary of
  `doc/design_doc_resident.md`).
- **Changing the period of the snapshots of a live program.** Stopping the
  periodic `debasher_snapshot_resident` of a live program and starting it
  again with another period, which needs the tool to leave its PID in the
  output directory.
- **The launch record and the modules of the preamble.** Widening the check
  made at launch time to the modules that the preamble loads, whose changes
  it does not see today (see "The directories of a resident program"), for
  example with a digest of each one in the launch record.
- **The alias of a node.** Offering an alias or an external alias on a node of
  a resident program, to run the code of a node under another name with its
  options mapped, as two workers of the same code with options of their own.
  It needs the engine to accept it (see "Future work" in
  `doc/design_doc_resident.md`); the web UI would then only show the field
  again on a node.
- **Templates of the code of a node.** A first code for the parts of a node
  when it is added, as the templates of a general process give one
  (`frontend/src/components/codeTemplates.ts`): a constructor that gives the
  node state its first value, a `capture_node_state` that returns all of it
  and a `restore_node_state` that sets it back, and a `process_data` with a
  branch for each business input. For a node that sends to a fanout family, a
  routing that is already deterministic, such as a counter kept in the node
  state, since a routing that a replay may change would make the sequence
  numbers of a channel label other messages (see "Fan-out and fan-in sized
  from the command line" in `doc/design_doc_resident.md`).
- **What import loses.** Giving `_define_opt_deps` and `_program_type` a place
  in the model. The second is needed by resident programs, and "Script
  generation and import of a resident program" designs it.
