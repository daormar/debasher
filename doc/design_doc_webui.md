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
general and resident (see the Glossary), and the web UI knows both, resident
programs only in part: a subsection of "Resident programs in the web UI" that is
built says so. Every section before "Resident programs in the web UI" describes
the design for general programs, and what it says holds for them. A resident
program, whose design is in `doc/design_doc_resident.md`, follows rules of its
own in several places: it is always run by the built-in scheduler, its processes
are meant to live until they are stopped, and it is stopped, snapshotted and
reset with tools of its own. The section on resident programs says, for each
part of the design described before it, whether it applies to resident programs
unchanged, changes, or is replaced, and nothing in the earlier sections should
be read as holding for resident programs unless that section says so.

The document is organized as follows. The Glossary defines the terms it uses.
"Architecture" presents the three layers of the web UI and where its state
lives. "The program model" describes the data that the frontend edits and the
backend receives. The two sections that follow describe the translation between
the model and a module in each direction, and what survives a round trip.
"Persistence and the program's directories" describes what the web UI keeps on
disk, and "Execution and observation" how it runs a program and follows it.
"Frontend state and the canvas" describes the frontend's own state and the Help
menu of the editor, and "Sequential processes in the web UI" describes how a
program keeps the sequential processes of its module. "Guarantees and non-goals"
gathers the guarantees stated along the way. "Resident programs in the web UI"
designs the extension to resident programs, and says which parts of it are
built. "Business tests in the web UI" describes how the web UI runs the tests of
a program and writes a first test for a process. "A prompt for the code of a
process" describes how the code editors help to have an AI tool write the code
of a process, of its options handler, of its additional methods or of a node.
"Editing a program from an agent: the MCP server" describes a second client of
the backend, for AI agents, "Claude Code on a program" how DeBasher starts
Claude Code with that server, "Access to the backend: the token" how the backend
obeys only those who hold its token, and "Future work" lists what is known to
be missing.

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
  `file` for the path of a regular file, `dir` for the path of a directory, or
  `None` for a flag, an option that takes no value.
- **option channel**: how an option's value is delivered, independent of its
  data type (`ProgramOption.channel`): `none` for a literal value or a
  connection, `value_desc` for a value descriptor the engine synthesizes, `fifo`
  for a named pipe, `shared_dir` for a shared directory, `process_outdir` for
  the process output directory of the option's own process.
- **literal value**: the value of an option with option channel `none` that is
  not connected, not a command line option and not taken from the process
  specifications: the Bash word that the user writes in `ProgramOption.value`,
  such as `10` or `${task_idx}`, and that script generation writes as it is
  (see "Option definitions").
- **shared directory**: as defined in the design of the engine.
- **shared subdirectory**: as defined in the design of the engine.
- **process output directory**: as defined in the design of the engine.
- **task subdirectory**: as defined in the design of the engine.
- **subdivided shared directory**: as defined in the design of the engine.
- **subdivided process output directory**: as defined in the design of the
  engine.
- **subpath**: as defined in the design of the engine: the path, below the
  directory that an option with option channel `shared_dir` or `process_outdir`
  names, of the shared subdirectory or task subdirectory that the option gives
  instead (`ProgramOption.subpath`), written by script generation with
  `--subdir`; `ProgramOption.subpath` is empty when the option names the
  directory itself (see "Directories and their subdirectories").
- **value descriptor**: as defined in the design of the engine: the file,
  named by an output option with option channel `value_desc`, into which a
  task writes a value for the processes connected to it.
- **command line option**: as defined in the design of the engine, marked as one
  by `ProgramOption.commandLine`. It takes its value from the command line and
  nowhere else: script generation refuses an option that is both a command line
  option and delivered through an option channel.
- **task shaping option**: as defined in the design of the engine, marked as one
  by `ProgramOption.taskShaping` on a mandatory command line option. Only the
  options handler of its process reads it, and no task receives it (see
  "Option definitions").
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
- **label edge**: an edge that the canvas draws, instead of as a line between
  its two handles, as a stub at each of them (see "Label edges").
- **stub**: one end of a label edge: a short line out of a handle, a ring and a
  text that names the other end. The source stub of an output with several
  label edges stands for all of them.
- **options handler mode**: how a process defines its options and so how many
  tasks it runs: `standard`, `array`, `generator` or `manual` (see "Options
  handler modes").
- **task**: as defined in the design of the engine. A process in `standard` mode
  runs one task; one in `array` or `generator` mode runs one per element or
  index, and one in `manual` mode as many as its option definition function
  defines.
- **fanout family**: as defined in the design of the engine. In the web UI, an
  option of a `standard` process whose label ends in `-ith`, such as
  `-outf-ith`, which stands for as many numbered options (`-outf0`, `-outf1`,
  ...) as another option of the same process says at run time.
- **preamble**: Bash code that the generated module carries verbatim before its
  own functions, typically the `load_debasher_module` lines of the modules it
  builds on.
- **step**: as defined in the design of the engine.
- **sequential process**: as defined in the design of the engine. In the web UI,
  an element of `Program.seqProcesses` (`SeqProcess`), not a process of the
  program (see "Sequential processes in the web UI").
- **group**: the processes, and the sequential processes, that "Add program"
  brings in, in one operation, from another program saved with the web UI,
  which the generated module declares with a single `add_debasher_program`
  while none of them has been edited or removed (see "Groups").

## Files and directories

- **home directory**: the directory where the program lives (`Program.homeDir`):
  its program metadata, its generated script and the user files.
- **output directory**: as defined in the design of the engine
  (`Program.outputDir`).
- **program metadata**: the program model saved as JSON in
  `.debasher/program.json` under the home directory.
- **revision**: a counter in the program metadata that a save which changes it
  increments; a write into the program's own home directory that would change
  the metadata is refused when the metadata there holds another revision than
  the one the write names: the one the program was loaded with, or the one on
  disk when the user saves over it (see "Revisions of the program metadata").
- **file version**: the modification time and the size of a user file, which a
  write that changes the file changes; the editor of the program files panel
  saves a file only over the version it read (see "Reserved names and user
  files").
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
  its output directory, their checkpoints, input logs and halted markers, and
  what their processes left in their own output directories: what
  `debasher_reset_resident` takes away (see "The directories of a resident
  program"). An empty output directory of a process is no program state: the
  engine creates it empty before a first run, and a reset leaves it so.
- **launch record**: `.debasher_webui_launch_record.json` in the output
  directory of a resident program: the generated script with every description
  left out, and the program options, of the last launch from the web UI whose
  `debasher_exec` ended with 0. The next launch compares the program with it.

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
  being edited and what the tab last read of its run.
- **unsaved changes**: how the program of a tab differs from the program as it
  was last loaded or saved, its revision and home directory apart (see
  "Screens and the store").
- **edit**: one change of a program as plain data (`EditOp` in
  `models/programEdits.ts`), such as adding a process or connecting two
  options; an operation of the store applies one or more edits.
- **run phase**: the state of the run of a program as the tab shows it
  (`ProgramRunPhase`), derived from the process statuses, whoever launched the
  run, and from the requests of the tab not answered yet (see "Following a
  run"). A resident program has values of its own (see "Running a resident
  program").
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
- **down**: of a task of a resident program, the state in which it has no
  completion marker and the PID in its `.id` file, in the exec directory of
  its process, no longer exists: the test with which the `Supervisor` decides
  to relaunch a node, which the web UI applies too.
- **relaunch lock**: `.debasher_webui_relaunch.lock` in the output directory of
  a resident program, a file that the backend locks while it relaunches the
  tasks of a node that are down (for "Restart node", from the stop on), so
  that two tabs never relaunch the same task.
- **mirror log**: as defined in the design of the engine: the log in which a
  mirror tap copies every line that a process writes into a FIFO defined with
  `--mirror`, which can be read without taking the data from the FIFO's reader.
- **notice**: as defined in the design of resident programs: the one message,
  `info` or `warning`, that the code of a node leaves for whoever watches the
  program, and which the canvas node shows with a mark.
- **unconnected FIFO**: a FIFO option with no edge and whose label does not name
  a fanout family, whose other end is an external end in the sense of the
  engine, left to someone outside the program, such as a person using "Talk to
  FIFOs".

## Business tests

See "Business tests in the web UI". The business tests themselves, the program
directory, the test directory, process tests, node tests, the node harness, the
test helpers and the test runner are defined in the glossary of
`doc/design_doc_engine.md`.

- **test outcome**: what "Run tests" reports, from the exit status of the test
  runner, or `timedOut` when the wait runs out: `passed`, `failed`, `noTests`,
  `notRun` or `timedOut`.
- **test skeleton**: the file that "Add test" writes for a process, once the
  user confirms its name: a process test or a node test whose `TODO` marks the
  user fills in, and which fails until the user removes the line that makes it
  fail.

## The code prompt

See "A prompt for the code of a process".

- **AI tool**: an application driven by a model, outside the web UI, that the
  user chooses and copies a code prompt into; an agent may serve as one.
- **code prompt**: the text that a code editor (the code editor of a process,
  the editors of the code of its options handler and of its additional methods,
  or the node code editor) composes for an AI tool, and that the MCP tool
  `get_code_prompt` composes the same way, asking for the code and giving what
  the program model knows of the process or the node.
- **node code editor**: the editor of the code of a node of a resident
  program, part by part (`NodeCodeEditor`; see "The program model of a
  resident program").
- **language rules**: the part of a code prompt, fixed for each language, that
  says how the engine runs the code of a process of that language.
- **template**: the first code that the code editor gives a process, in the
  language of the process, which reads every option of the process, a fanout
  family included once it has a count source (see "Building the code
  prompt").
- **template marker**: the comment `ADD YOUR CODE HERE` of a template, where
  the code of the process goes; code that holds it, or no code at all, is
  still a template.
- **code request**: the text that the user writes in the prompt panel to say
  what the code should do, or that an agent gives to `get_code_prompt`, which
  the code prompt carries.
- **prompt panel**: the part of a code editor that shows the code prompt and
  copies it.
- **node reference**: the part of the code prompt of a node that documents
  what the code of a node uses of the runtime library, read from the library
  itself (see "The code prompt of a node").

## The MCP server

See "Editing a program from an agent: the MCP server".

- **MCP server**: the program, run as `debasher_mcp`, that offers the editing,
  running and following of programs to an agent through the Model Context
  Protocol; a client of the backend, like the frontend.
- **agent**: an AI application, driven by a model, that calls the MCP tools,
  such as Claude Code.
- **MCP tool**: an operation that the MCP server offers to an agent, with
  named parameters and an answer in text. A bare "tool" is still a command
  line tool of the engine.
- **library**: the processes, or in a resident program the nodes, that the
  modules loaded by the preamble of a program define, which a new process of
  the same name takes its description, options and code from.
- **named edit**: an edit written with names instead of ids: a process or a
  sequential process by its name, an option by its process and its label, an
  edge by its two ends.
- **proposal**: what an MCP tool called with `dry_run` answers: the edits it
  would apply, resolved and validated, and what they would change, with nothing
  saved.

## Claude Code on a program

See "Claude Code on a program".

- **launcher of Claude Code**: the command, run as `debasher_claude`, that
  starts Claude Code on one program with the MCP server, the permissions of
  its MCP tools and the plugin of DeBasher.
- **plugin of DeBasher**: the plugin of Claude Code that DeBasher installs,
  which holds its skills and the reference they share
  (`reference/concepts.md`).
- **skill**: a set of instructions of the plugin of DeBasher that Claude Code
  follows for one kind of work, called in a session as `/debasher:<name>`.
- **session mode**: the skill that a session of `debasher_claude` starts with
  (`--mode`): `help`, `design`, `implement` or `review`, or none.

## Access to the backend

See "Access to the backend: the token".

- **token**: the random secret that `debasher_webui` draws, or is given, when
  it starts, and without which the backend obeys no request to the API.
- **token URL**: the address of the web UI with the token in its fragment
  (`/#token=<token>`), which `debasher_webui` prints and the user opens once.
- **origin**: what a browser keeps the data of a page apart by: the scheme, the
  host and the port of its address (`http://localhost:8000`). Two ports of one
  host are two origins.
- **token source**: where `apiFetch` takes the token from: the local storage of
  the browser in the editor, the token file in the MCP server.
- **token file**: the private file, named after the port of the backend, into
  which the backend writes its token for the MCP server to read.

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
- `webui`: what the web UI offers that depends on where the backend runs.

One server process serves both the API and the built frontend, which is a single
self-contained `index.html`. `debasher_webui` starts it, listening only on
`127.0.0.1` unless told otherwise. It runs every tool as the user who launched
it, so it obeys only the requests that carry its token (see "Access to the
backend: the token"). During development the dev server of Vite serves the
frontend and forwards `/api` to a backend started by hand.

## The backend keeps no state

The backend keeps nothing between two requests. Every request carries what it
needs, in most cases the whole program model, and the backend acts on the disk
and on the engine's tools and answers. `/run` is the clearest case: it saves
the program, generates its script, starts `debasher_exec` in a session of its
own, with its output in `.debasher_webui_run.log` under the output directory,
and answers without keeping a handle on the process. What happened to the run
is asked later of the engine itself, with `debasher_status` on the output
directory.

Two things follow. Restarting the backend loses nothing, since there is nothing
in it to lose. And the backend does not coordinate two tabs that act on the same
directories: the engine's files are the only truth they share, and the guards
against a conflict read them (`/run` refuses to start when `debasher_status`
reports a run in progress on that output directory).

## Where the state lives

The lasting state lives in two places only. The store of each tab holds the
program being edited and what the tab last read of its run. The disk holds the
rest: the home directory keeps the program metadata, the generated script and
the user files, and the output directory keeps what the engine writes during a
run. The frontend keeps nothing in the local storage of the browser but the
token (see "How a request carries the token"), so a program that has not been
saved is lost when its tab is closed.

A run lives in its output directory, not in the tab that launched it. Nothing
that happens to a tab stops it, and a tab follows any run of its output
directory through the process statuses, whoever launched it (see "A run that
outlives the tab").

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
  loads. It is kept the way the engine reads it, the directories separated by
  colons. The environment variables editor and the import dialog show it one
  directory per line and save it back joined with colons, without blanks
  around a directory and without empty entries: an empty entry would make the
  engine look for modules in the root directory. "Add program", which appends
  the directory of the program it adds, keeps the same form.
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
`description`, a `value` and a `subpath`, and five flags: `commandLine` and
`mandatory`, `taskShaping` (a task shaping option), `fromProcessSpec` (its value
is an attribute of the process's own specifications, such as `cpus`) and
`mirror` (a copy of what the process writes into a FIFO is kept in a log that
the web UI can show without taking data from the reader). An option's direction
always follows from its label, by the engine's convention: output if the label
starts with `-out` or `--out`, input otherwise.

The labels of the options of a process are distinct, compared without the spaces
around them, case included. The engine treats a label as the key of an option of
a process: it merges two options with the same label into one, and fails at run
time if they get different values. The editor refuses a label that the process
already has, and `validateEdits` refuses it too (`optionLabelProblem` in
`models/process.ts`). A program whose metadata breaks the rule, for example one
edited by hand, still loads: the canvas node and the inspector of each such
process name the repeated labels, so that the user relabels or removes all but
one.

What `value` holds depends on the other fields, and is, except for a connected
input, what the generated script has to write, not what the process will
receive at run time:

- a literal value, for an option with option channel `none` that is neither
  connected nor a command line option;
- a connection sentinel, for a connected input, which script generation does
  not read (see "Connections");
- the FIFO's name, for option channel `fifo`;
- the shared directory's name, never a path, for option channel `shared_dir`,
  whose subpath, if any, is in `subpath`;
- nothing, for option channel `process_outdir`, whose subpath, if any, is in
  `subpath`;
- the attribute's name, such as `cpus`, when `fromProcessSpec` is set;
- nothing that script generation uses, for a command line option, whose value
  comes from the program options at run time.

A few combinations make no sense, and the model keeps them out. A flag is always
an input. `mirror` only applies to a `fifo` output. `value_desc` and
`process_outdir` only apply to an output: the consumer of a value descriptor, or
of a process output directory, just connects to it. A `subpath` only applies to
`shared_dir` and `process_outdir`. `fromProcessSpec` only applies to an input,
since an output names what the process produces, and `fromProcessSpec` and
`commandLine` exclude each other, and a command line option has option channel
`none`, since its value comes only from the command line. A task shaping option
is a mandatory command line input with a value, and not a fanout family. A
fanout family only exists on a `standard` process, and names in
`countSourceOptionId` a command line option of the same process that gives the
count. The editor offers only the valid combinations, the checks of the edits
that an agent makes refuse the ones that concern an output or a directory
channel (see "Edits from an agent"), and script generation checks again those
whose violation would produce a wrong module, refusing to generate it.

## Connections

An edge goes from an output option of a process to an input option of another
process or of the same one. The edges are the one source of truth about what is
connected. The value of a connected input, its connection sentinel, is derived
from them: the store recomputes it from the edges after every change to the
program, so renaming a process or an option never leaves a sentinel that names
the old one, and a program loaded with values out of step with its edges is
repaired on load. Script generation reads only the edges, and emits one
definition per edge. The sentinel is what the editor shows and the program
metadata keeps, never what makes an option connected, so the backend never
computes it: import, which builds the edges, leaves the value of a connected
input empty, and the normalization of the store (`normalizeProgram`, see
"Screens and the store") derives the sentinel on every program the store loads.
A `shared_dir` input is the exception: its value stays the name of its
directory, and its edges only document on the canvas how the processes share it,
while the engine derives the dependencies on its own, from the paths (see
"Directories and their subdirectories").

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
  exception is fan-in between `shared_dir` options that name the same directory,
  whose edges only document how the processes share it (see "Directories and
  their subdirectories").
- A `shared_dir` option pairs with another `shared_dir` option only when both
  name the same directory, whatever their subpaths.
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
the canvas, a self-loop included. The canvas routes such an edge around the
processes instead of through them, and a self-loop around its own process. For
two processes that answer each other through FIFOs, it instead moves the
handles of the answering pair to the other side, so that the edge stays short.

## Directories and their subdirectories

Two option channels give an option a directory that the engine manages:
`shared_dir`, a shared directory of the program, and `process_outdir`, the
process output directory of the option's own process. Either may name, in
`subpath`, a directory below it instead: a shared subdirectory or a task
subdirectory, which the engine creates before the process runs and, for a task
subdirectory, empties before each task, unless the process has a
`_reset_outfiles` method. The subpath is a Bash word, like a literal value (see
"Values are Bash words, descriptions are text"), so that it can name each task's
own directory, such as `${task_idx}` or `${array[$task_idx]}`. Script generation
writes a subpath with `--subdir` (see "Option definitions"), and the engine
checks, when the run is prepared, that it stays below its directory; an empty
`subpath` means no subdirectory: the option names the directory itself, and
script generation writes no `--subdir`.

A subpath serves the principle of the design of the engine that the code of a
process does not depend on its number of tasks. A process in `array` or
`generator` mode whose output option with option channel `process_outdir` has
subpath `${task_idx}` finds in that option a directory that exists and is empty
when each task starts, unless it has a `_reset_outfiles` method, as a process in
`standard` mode finds its process output directory, and writes into it the same
files under the same names.

`process_outdir` only applies to an output: the directory that the process
produces, which another process reads through an ordinary connection to that
output. A reader in `array` or `generator` mode reads the task subdirectory of
the task with the same index, and a fanout family of a process in `standard`
mode reads the task subdirectory of every task, one option for each (see "Option
definitions"); an ordinary input of any other reader gets the value of the first
task of the source only (see "Options handler modes"). A process that gathers
the results of every task therefore reads them through a fanout family, with
either channel, which also makes it wait for every task, since each of its
options holds the path of the output of one task. The editor of an option offers
the subpath next to the directory name of a `shared_dir` option, and next to the
channel of a `process_outdir` one, in `standard`, `array` and `generator` mode,
with the variables that the mode provides as a hint. A subdivided shared
directory or subdivided process output directory belongs to its subdirectories,
as the design of the engine says: a task writes only into its own
subdirectories, or into a path that one of its output options names, and an
output option that holds the whole directory stops the run. The editor does not
check these rules, which depend on the values of every task; the engine checks
the last one, in a validation too, and removes what a task leaves elsewhere:
from a subdivided shared directory on the next run, and from a subdivided
process output directory when its process is next prepared, unless it has a
`_reset_outfiles` method.

**Connections.** Two `shared_dir` options pair when they name the same shared
directory, whatever their subpaths: an output that writes the shared
subdirectory `${task_idx}` of `data` may feed an input that reads the whole of
`data`, as a process that gathers the results of every task does, or an input
that reads the same subdirectory. Connecting a `shared_dir` output to an input
gives the input the name of the directory, not the subpath, so it reads the
whole directory until the user gives it a subpath of its own. The edge only
documents how the processes share the directory: script generation writes the
definition of each option from its name and subpath, whatever the edges, and the
engine infers a dependency only between an output and an input that hold the
same path. A process that reads, through an input with subpath `${task_idx}`,
what another writes through an output with the same subpath, both in `array` or
`generator` mode, thus depends on it task by task (`aftercorr`), while an input
that reads the whole directory gets no dependency on the writers of its
subdirectories: its process has to be ordered after them with explicit
dependencies, which replace its inferred ones (see "Future work"). A fanout
family that reads the shared subdirectory of every task is ordered after them
without them.

**Import.** Import recognizes `define_opt_from_shared_dir` and
`define_opt_from_process_outdir` with an optional `--subdir`, and gives the
option its channel and its subpath (see "Recovering the options handler"). The
edges that it adds between `shared_dir` options join each writer of a shared
directory to each of its readers, whatever their subpaths.

## Options handler modes

The options handler mode says how a process defines its options, and so how
many tasks it runs:

- `standard`: one task. Script generation writes one `_define_opts` function
  that defines every option once.
- `array`: one task per element of a Bash array named `array`, which the
  user's code (`arrayCode`) builds. The generated `_define_opts` loops over
  the array with the index `task_idx`, which option values can use.
- `generator`: one task per index, from 0 up to the count that the user's code
  (`generatorSizeCode`) prints. Script generation writes that code as
  `_generate_opts_size`, and a `_generate_opts` that the engine calls once per
  index, with the index in `task_idx`.
- `manual`: the user writes the option definition function whole
  (`manualCode`), and script generation copies it as it is. The options are
  still explained and documented from the model, but they are not used to
  define the option values.

The index of a task has the same name, `task_idx`, in `array` and `generator`
mode, so an option value written for one of them, such as
`${process_outdir}/${task_idx}`, means the same in the other.

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
new or disconnecting it first asks the user, and then dissolves the whole
group: its processes are then generated one by one, like any other.

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
   (one `explain_opt` per option that is not a task shaping option, or
   `explain_flag` for a flag), `_explain_task_shaping_opts` (one
   `explain_task_shaping_opt` per task shaping option, only for a process that
   has one), `_identify_cmdline_opts` (one `opt_is_cmdline` or
   `opt_is_non_mandatory_cmdline` per other command line option), the option
   definition functions of its options handler mode (see "Option
   definitions"), its code, and one function for each additional method that
   has a body. Code in Bash is written as it is; code in another language
   becomes a heredoc function `<process>_heredoc_<suffix>` (`py`, `r`,
   `perl`, `groovy`) that prints it, which the engine wraps in the
   function of the process. The engine also accepts the older form, a
   variable `<process>_<suffix>`, which import reads, but a Bash variable
   name cannot contain the dot of a namespaced process, so script
   generation never writes it.
4. For each sequential process, its `_document` function and its code (see
   "Generating and importing a sequential process").
5. The code of each function that an alias runs and that nothing else in the
   program writes (see "Code that a loaded module already provides").
6. `<name>_program`, with one `add_debasher_process` per process, carrying its
   computational specifications (`cpus=... mem=... time=...`) and its
   additional specifications (`force=yes;processdeps=...;alias=...`), then one
   `add_debasher_seq_process` per sequential process. The members of a group
   that is still whole, of either kind, give way to one `add_debasher_program`
   for the group.

A function with nothing to say gets the body `:`, since the engine expects it
to exist. What the model holds about runs or about the canvas stays out of the
module: `envVars`, `executionOptions` and `programOptions` go to the engine's
tools when they run (see "Execution and observation"), and positions, ids and
the two directories only matter to the web UI.

## Option definitions

In `standard`, `array` and `generator` mode, script generation writes one
definition for each option that is not a task shaping option (one per edge for
a fan-in), taken from the first rule that applies:

1. A flag: `define_flag`, or `define_cmdline_flag_if_given` if it is a
   command line option.
2. Option channel `value_desc`: `define_value_desc_opt`.
3. Option channel `fifo`: `define_fifo_opt` with the FIFO's name, and
   `--mirror` if `mirror` is set.
4. Option channel `shared_dir`: `define_opt_from_shared_dir` with the
   directory's name, whatever its edges; option channel `process_outdir`:
   `define_opt_from_process_outdir`. Either takes `--subdir` and the subpath
   when the option has one.
5. `fromProcessSpec`: `define_procspec_opt` with the attribute's name.
6. A command line option: `define_cmdline_opt`, `define_cmdline_infile_opt`
   for a file, or `define_cmdline_indir_opt` for a directory, with the suffix
   `_if_given` when it is not mandatory.
7. A connected option: `define_opt_from_proc_out` for each of its edges, or
   `define_opt_from_proc_task_out` with the task index when both ends run in
   `array` or `generator` mode.
8. An input file or directory: `define_infile_opt` or `define_indir_opt`, which
   resolve a relative path against the module's own directory, so that a file
   or a directory shipped with the program can be named portably.
9. Anything else: `define_opt` with the literal value.

A command line option always gets its definition from rule 6, or from rule 1
for a flag, since one with an option channel other than `none` is refused (see
"What script generation refuses"). A fanout family becomes a loop instead of
one line: it reads the count from its command line option and defines one
option per index, `define_opt` or `define_fifo_opt` on the writing side,
`define_opt_from_proc_task_out` on the reading side.

A task shaping option gets no definition, since no task receives it: the
options handler reads it from the command line, in the code that builds
`array`, in the code that counts the tasks of a generator, or in the user's own
function in `manual` mode. It cannot count a fanout family, although the engine
would accept one: the task of the family needs the count to read the options of
the family, and the template of the code reads it for that.

In `standard` and `generator` mode each definition is written once, in
`_define_opts` or in `_generate_opts`. In `array` mode the generated
`_define_opts` runs the user's code that builds `array`, then defines every
option inside `for task_idx in "${!array[@]}"`, one task per iteration, even an
option whose value does not depend on `task_idx`. The loop variable is declared
`local` right before the loop, so that the loop never changes a variable of the
same name in a function of the engine that calls `_define_opts`. Import
recognizes this shape, with or without that declaration, and takes everything
before the declaration, or before the loop when there is none, as `arrayCode`.
In `manual` mode the user's function is written as it is, and the rules above
do not apply.

## Values are Bash words, descriptions are text

Option values, and subpaths, are written between double quotes as they are,
without escaping. This is deliberate: a value is a Bash word, evaluated when the
options are defined, so it can use the variables that script generation provides
(`${task_idx}` in `array` and `generator` mode, `${array[$task_idx]}` in `array`
mode, `$i` in a fanout family) and those of the preamble. It also means that a
double quote, a backslash or a `$` meant literally has to be escaped by the
user, and script generation does not check that the result is valid Bash.

Descriptions (of the program, of each process and of each option) are text,
never expressions, and script generation escapes the characters that keep a
special meaning between double quotes (`\`, `"`, `$` and the backquote). A
description therefore reaches the module documentation exactly as it was
written, and a backquote in it is never run as a command.

## Code that a loaded module already provides

A process imported from a module can carry code that one of the modules its
preamble loads already defines. Before writing the code of each process, script
generation asks `debasher_get_proc_info` for the canonical form of the process's
code as the preamble alone defines it, and for the canonical form of the
process's own code. If both exist and are equal, the generated module leaves the
code out and relies on the loaded module. If either query fails, it writes the
code: the check can only save a duplicate, never lose code. A process with an
`alias` or an `ext_alias` gets no code of its own, since the engine builds its
function from the aliased one.

Import keeps, as the code of an `alias` (not an `ext_alias`), the code of the
function it runs, since that is the implementation that the engine reports for
it. When that function is a plain function of the imported module, neither a
process nor a sequential process, this code is the only copy of it in the
program, and a module without it would leave the alias with nothing to run.
Script generation therefore writes it, once for each function, when the function
is not a process or a sequential process of the program, when the code of the
alias is Bash that defines a function of that name, and when no module of the
preamble already defines the same function, by the comparison above. The code of
an alias created in the web UI holds whatever the user left there, which
normally does not define the function it runs, and so is not written.

## What script generation refuses

Script generation raises an error, and writes no module, for a program that
would produce a wrong one: an option both `fromProcessSpec` and a command line
option; an output taken from the process specifications; a command line option
with an option channel other than `none`; an input with option channel
`process_outdir`; a subpath on an option whose option channel is neither
`shared_dir` nor `process_outdir`; a task shaping option that is not a mandatory
command line input with a value, or that is a fanout family; a fanout family
that is a flag, a command line option or taken from the process specifications,
whose count option is missing, is not a command line option or is a task shaping
option, whose output is connected, mirrored or uses an option channel other than
`none` or `fifo`, or whose input is not connected to a process in `array` or
`generator` mode; a connection to a fanout family from a process in another
mode; and a sequential process in a resident program, or with the name of a
process or of another sequential process (see "Generating and importing a
sequential process"). The save generates the script before it writes anything,
so a program that script generation refuses leaves the home directory as it was.
The save answers with the reason of the refusal, which the frontend shows.

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

The option definition functions are the one part of a module that import parses
(`option_handler_import.py`). It matches them against a closed grammar: the
calls that define an option (`define_opt`, `define_fifo_opt`,
`define_opt_from_proc_out`, `define_cmdline_opt`, `define_opt_from_shared_dir`
and `define_opt_from_process_outdir` with their optional `--subdir`, and the
rest of that family) with literal arguments, between the fixed lines that open
and close the function. From the shape of the functions it decides the mode:

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

What the grammar recognizes gives the values, the subpaths, the option channels,
the flags `mirror` and `fromProcessSpec`, and the connections. A function kept
in `manual` mode is still scanned for connections anywhere in its text, so that
the canvas can draw them; script generation writes that function as it is, so a
connection that the scan misses or invents costs a wrong line on the canvas,
never a wrong module.

## Building the program

With the processes read, import assembles the program:

- **Options.** Each explained option becomes an option, its direction taken from
  its label, and each one that the module documentation lists among the task
  shaping options becomes one with `taskShaping` set. An option that a
  connection names but that no `explain_opt` declares, common in `array` mode,
  gets a minimal option of type `string` so that the edge has somewhere to
  attach.
- **Connections.** Each recovered connection becomes an edge, and a connection
  to a process outside the program is dropped. A connection by task index whose
  source does not run in `array` or `generator` mode cannot be written again as
  it was, so its target falls back to `manual` mode.
- **Shared directories.** An option whose value names a shared directory,
  literally or through a variable that the engine resolves, becomes a
  `shared_dir` option when that directory is one the program can reach, and
  import adds an edge from each writer of a directory to each of its readers,
  whatever their subpaths. `availableSharedDirs` is filled with every reachable
  shared directory.
- **Preamble.** The module documentation has no notion of a preamble, so
  import takes the text of the module before its first function definition,
  leaving out the header line of a generated script.
- **Specifications.** They come from the module documentation. The engine
  attributes that the model does not hold (`nodes`, `account`, `partition`,
  `throttle`) are dropped.
- **Layout.** The module says nothing about positions, so import leaves them
  to the frontend, which places the imported processes in layers by their
  connections (see "From the store to the canvas").
- **Sequential processes.** Each section of a sequential process in the module
  documentation becomes one (see "Generating and importing a sequential
  process").
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
options with their values, subpaths, option channels and flags, the connections,
the modes, the code, the additional methods, the specifications, the
descriptions and the sequential processes survive. The order of the processes,
and of the options of a process, follows the module documentation and may differ
from the original. What lives only in the program metadata does not survive: the
ids, which are new; the positions, which are laid out again; which edges are
label edges, since import draws every edge as a line; the groups, which come
back flattened; the connection sentinels, derived again from the connections
when the program is loaded; the environment variables, except the
`DEBASHER_MOD_DIR` given to import; the execution options and program options;
and the home and output directories. A `manual` function that happens to fit the
grammar of `standard` mode comes back in `standard` mode, which defines the same
options.

**From a module to the model and back.** A module that import recognizes comes
back with the same behavior, but written the way script generation writes it:
the option definition functions of a recognized mode lose their comments and
their layout, while the functions kept in `manual` mode, the code and the
methods keep their verbatim source. Code in another language that the module
held in a heredoc variable comes back in a heredoc function. Some things a
module can say have no place in the model and are lost: the explicit dependency
types of `_define_opt_deps`, which the module documentation shows and import
does not keep; the program type of `_program_type`; any code of the module after
its first function that belongs to no process or sequential process, unless it
is a Bash function that an alias runs (see "Code that a loaded module already
provides"); and the specifications the model does not hold.

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
program's home directory. The backend generates the script first, so that a
program that script generation refuses leaves the home directory as it was, then
writes the program metadata, then the generated script, and then copies the file
of each `ext_alias` given as a relative path from the program's `sourceDir` into
the home directory, at the same relative path: the engine resolves such a path
against the directory of the module that declares it, so without the copy a
program imported and saved elsewhere would lose its aliased scripts. When the
program has been renamed since the last save, the backend deletes the script
with the old name before it writes the metadata, from which it reads that name.

A save is refused while there is a run in progress on the output directory. The
engine reads the generated script again each time it starts a process, so
overwriting it during a run would leave the processes already started on one
version and the rest on another, with nothing to show it. The frontend checks
this before sending the save, and the backend checks it again with
`debasher_status` (`run_guard.py`), whenever it finds that tool, so that a
request from another tab or another client of the backend is refused too. The
backend also refuses a save while there is a run in progress in the output
directory named by the program metadata already saved in the home directory: a
save that changes the output directory still writes the script that a run in the
old one reads.

Running also saves. "Run program", "Validate program" and "Check program
options" all save the program into the home directory, as a save does and with
its revision (see "Revisions of the program metadata"), before calling
`debasher_exec` (see "Launching a run"), so that the engine always runs the
program as it is in the editor. All three are refused while there is a run in
progress, by the frontend, which disables them, and by the backend, with the
same check as a save.

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
own before changing it. A shipped program may run another one: the launcher node
of `webui_batch_launcher` names `webui_batch_greet` by a path relative to its
own home directory, `../webui_batch_greet/webui_batch_greet.sh`, a path that
resolves both where the two are installed, side by side, and for a user who
saves them side by side too; a user who saves them apart edits that path.
`test/api/test_webui_programs.py` checks that each of them loads from where it
is and that its generated script is the one that script generation writes from
its metadata today, and `make installcheck` runs the generated script of each: a
general program to its end, and a resident one, which does not end on its own,
launched, fed through its external input until its output read outside the
program carries the expected message, and stopped in an orderly way, after which
every node has to be finished.

## Revisions of the program metadata

Two tabs, or a tab and another client of the backend, may edit the same
program, and without a guard the last save would overwrite what another saved
since its tab loaded the program. The program metadata therefore holds a
**revision**, a counter that a save increments. Loading returns it, the store
keeps it, and every request that writes the program metadata (saving, and the
requests that save before they run, such as "Run program") carries it and,
when it succeeds, answers with the revision it wrote.

The backend refuses the write, with a conflict whose detail names the revision
it holds, when the program goes into its own home directory, the metadata there
holds another revision, and the write would change what the metadata holds apart
from its revision and home directory. A write that changes nothing keeps the
revision and is never refused, since it overwrites nobody's work. The store
sends the program with the home directory it was loaded from, so the backend
tells a save into it from a save into another directory, which replaces what is
there, as a first save into a directory with no program metadata does. The
backend makes the comparison and the writes under a lock on the program
metadata, and replaces the metadata file whole, so that two writes arriving
together cannot both pass the comparison (`persistence.save`).

When a write is refused, the editor says that the program changed on disk since
it was loaded, and shows a banner under the toolbar with two choices. "Load it
(lose my changes)" replaces the program of the tab with the one on disk, and
loses what was changed in the tab since it was loaded. "Save mine over it" saves
the program of the tab naming the revision on disk, and loses what was saved
there since the tab loaded it; if someone saved again meanwhile, that save is
refused in turn, and the banner stays, now for the newer revision. Until the
user chooses, the tab goes on as it is, and its writes into the home directory
stay refused; a tab with no unsaved changes, which loses nothing, loads the
program again at the next reading of the revision, as below. The revision is a
guard against overwriting without knowing, not a merge.

A tab also learns of a revision saved elsewhere before it writes. While the page
is visible and the program has a home directory, the editor reads the revision
of the program metadata there every few seconds (`/revision`, which reads only
the revision, polled by `store/useDiskRevision.ts`). When it is another than the
one of the tab, a tab with no unsaved changes loads the program again on its
own, since it loses nothing, and a tab with unsaved changes shows the same
banner. Whether the tab holds unsaved changes is decided when the revision is
read, from the latest program, not from the last render, so that an edit made
meanwhile is never lost to a load that does not ask. A revision read while a
write of the tab is in flight, or read before such a write was answered, is set
aside, since it may be that write's own, which the tab has not taken yet; and a
reading never starts while the one before has not been answered. A program
loaded again keeps the selection and the view of the canvas, and the canvas
takes the positions of its processes from it (see "Keeping the canvas in step
with the store").

## Reserved names and user files

Inside the home directory, `is_reserved_name()` in `persistence.py` is the one
source of truth about what belongs to the engine or to the web UI: the program
metadata, the engine's files (`.conda`, `.sched_opts`, `__exec__`,
`__fifos__`, `command_line.sh`, ...) if the engine ever writes there, and any
file the engine adds later under the same conventions. It is a rule rather than
a list so that it needs no change when the engine grows.

The program files panel (`routers/program_files.py`) shows and manages the
user files: it lists the tree, shows a text file (up to a fixed number of
lines, and not a binary one), edits an existing file (and, for "Add test" and
the MCP server, creates a new one, see "Adding a test"), creates a directory,
deletes, renames or moves an entry, and uploads files of any type, which is
also how the script of an `ext_alias` reaches a program that was not imported.
It keeps four guarantees:

- It never shows, enters or writes a reserved name, at any depth.
- Every path is resolved inside the home directory, following symbolic links
  (except the entry that is deleted, renamed or moved, see below), and a path
  that would leave it is refused. The panel never descends into a directory
  that is a symbolic link.
- Deleting, renaming or moving acts on the entry that the path names (with its
  contents, for a directory), and on nothing else: everything above the entry is
  resolved and has to stay inside the home directory, but the entry itself is
  not followed (`resolve_entry_within`). A symbolic link is removed or moved as
  a link, never the file or directory it points to, so removing a link to a
  place outside the home directory leaves that place as it was. A path that
  names no entry, such as `.` or `test/..`, is refused, so the home directory
  itself is never deleted or moved.
- The generated script is shown, read-only: the panel never edits, deletes,
  moves or overwrites it, since the next save would regenerate it anyway.

The panel also follows what someone else, such as an agent through the MCP
server, writes into the home directory. While it is open and the page is
visible, it reads the tree again every few seconds, and the file version of the
file it shows (`/version`, which reads no content); when the version changed, a
buffer that holds no edit since the file was read is read again in place, and a
buffer with such edits shows a banner above the file that offers to load the
file, losing them, or to save the buffer over it (only to load it, when the file
was deleted). Its saves name the version they read (`expectedVersion` of
`/write-content`), and a file that holds another version is refused with a
conflict and the same banner, so that the editor never overwrites what someone
else wrote since it read the file unless the user chooses to. The version is
compared just before the write, with no lock, and a write that keeps both the
size and the modification time of a file goes unseen. "Add test" and the MCP
server name no version.

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
reset is refused while there is a run in progress, by the frontend and by the
backend, whose processes may still use the files. The frontend also refuses to
change the output directory while there is one: the status, the stop and the
inspection actions all name the output directory, so changing it would leave
the run out of reach of the web UI; the backend refuses to save the change
(see "The home directory").

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
- the program options, each label followed by its value, except a flag, which
  is given alone when its value is not empty and left out otherwise.

The command runs with `DEBASHER_MOD_DIR` taken from the program's `envVars`, in
a session of its own, with its output in the run log (see "A run that outlives
the tab"). What `/run` does next depends on the scheduler:

- With the built-in scheduler, `debasher_exec` is the scheduler of the run: it
  launches each process once those it depends on have finished, and lives as
  long as the run, so it cannot be waited for. `/run` first validates the
  program with `debasher_exec --validate` within the request, and answers with
  its exit code and what it printed when the validation fails; otherwise it
  starts the run detached and answers at once. A program that the engine refuses
  is therefore reported by `/run` itself and never reaches the run phase, which
  would take the output directory, left as it was, for the end of a run. What
  the validation cannot see, a first round of the scheduler that can choose no
  task, comes after the scheduler has reset the completion markers of the
  processes it runs again, and so shows in the run phase as `unfinished`, and in
  the run log.
- With Slurm, `debasher_exec` ends once it has submitted a job for each process,
  with its dependencies, and the run goes on in Slurm. `/run` waits for it and
  answers with its exit code and what it printed, which the frontend shows when
  the launch fails.

`--wait` is never given: with the built-in scheduler it changes nothing, and
with Slurm it would keep `debasher_exec` alive for the whole run, only to wait.
Beyond a failed launch, nothing in the web UI shows the run log; it is there
for diagnosis by hand.

"Validate program" runs `debasher_exec --validate`, which does everything but
launch the processes, and, with the built-in scheduler, checks the CPUs and
memory of each process against the budget of the scheduler; "Check program
options" runs `debasher_exec --check-proc-opts`. Both run to the end within the
request, and the frontend shows what they print.

## Following a run

The frontend follows a run by reading `debasher_status` on the output directory
every five seconds, whenever the program has an output directory, whoever
launched the run. Polling is deliberate: the backend has nothing that could push
a change, and the engine records state in files.

**The process statuses** come from each reading. The backend parses the
per-process lines of `debasher_status` (`PROCESS: <name> ; STATUS: <status>`)
and the canvas colors each canvas node by its process's status: `FINISHED`,
`IN-PROGRESS`, `UNFINISHED`, `UNFINISHED_BUT_RUNNABLE` or `TO-DO`, and no color
when there is nothing to report. A run in progress is defined from these
statuses, not from the run phase, so the guards that depend on it (saving,
resetting and changing the output directory) also hold for a run launched from
another tab or from the command line.

**The run phase** is derived from the same readings, and from the requests of
the tab not answered yet:

- `idle`: no process has a status to report, since the output directory holds no
  run.
- `running`: at least one process is in progress.
- `finished`: every process has finished.
- `unfinished`: no process is in progress and not every one has finished, in two
  readings in a row: a single reading of that kind also happens in the short gap
  between one process ending and the next starting. After a stop of the tab, one
  reading is enough, since no next process is about to start.
- `launching`: from a launch of the tab until the first reading that shows a
  process in progress, or two readings with none, when the run ended or failed
  at once.
- `stopping`: while a request of the tab to stop the program has not been
  answered.

The tab shows the run phase in an indicator on the canvas, whose Hide button
hides it until the run phase changes and stops nothing. It shows `launching`,
`running` and `stopping`, and `finished` and `unfinished` only when the tab saw
the run end, going there from `launching` or `running`: a program opened with
the results of an old run shows no indicator. With `unfinished` it shows the
output of `debasher_status` of the last reading, to show why the run did not
finish. While a request of the tab to launch or stop the program has not been
answered, the Run menu offers no other action on it.

## Inspecting a process

The context menu of a canvas node inspects what its process left in the
output directory:

- "Show stdout" and "Show scheduler output" run `debasher_get_stdout` and
  `debasher_get_sched_out`.
- "Show options" shows the process's `.opts` file, the options it was given,
  one per line.
- "Show inputs and outputs" parses that same file into the resolved value of
  each option, which for a FIFO, a shared directory, a process output directory
  or a value descriptor is the path the engine chose, not the model's `value`.
  Each value can be opened as a path: the content of a file, or the listing of a
  directory, anywhere the server's user can read.

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

**Talk to FIFOs** lets a person act as the other end of the unconnected FIFOs of
a running program: write a line into an input, and read from an output the line
that answers it, the two paired, one line read for each line written. It is
only offered while there is a run in progress, and only for unconnected FIFOs,
since reading a FIFO that another process also reads would steal its data.
The backend finds the FIFO by the engine's convention,
`__fifos__/<process>/<fifo name>`, and bounds each attempt to eight seconds,
because opening a FIFO blocks until the other end is open: a write that times
out means that no process is reading; a read that times out only means that
nothing has been written yet, and the frontend tries again.

## Stopping

"Stop program" runs `debasher_stop` on the output directory, and "Stop process",
in the context menu of a canvas node, runs it for that one process. Both run in
a session of their own, with their output in a temporary file (see "A run that
outlives the tab"), and the run phase is `stopping` until "Stop program" is
answered.

## A run that outlives the tab

A run of a general program may last days, and a resident program is meant to
live until it is stopped. A run therefore lives in its output directory, not in
the tab that launched it, and once it is launched it depends on the backend for
nothing. This subsection says what happens to a run when the tab or the backend
goes away and comes back.

**The tab.** Nothing that happens to a tab stops a run: closing or reloading it,
leaving the editor, or hiding the indicator of the run. Only "Stop program"
stops it, and "Stop process" one of its processes, besides the actions that stop
a resident program (see "Running a resident program"). The tab asks nothing
about the run when it is closed (it asks only when the program holds unsaved
changes, see "Screens and the store"): the browser shows only a generic warning,
which could not say that the run goes on, and would show it every time.

Leaving the editor while there is a run in progress shows a short message, which
blocks nothing (apart from the question about unsaved changes): the run goes on
in its output directory, and is followed or stopped by opening its program
again. This is the only moment at which the web UI can say where the run lives.
The backend keeps no record of it, and the home screen cannot list the runs in
progress, since it does not know which output directories exist. A run is found
again by loading its program from its home directory: its program metadata holds
its output directory, and its run phase comes from the process statuses of that
directory.

A request of the tab that is still pending when the tab goes away, to launch or
to stop a run, goes on in the backend to its end. The tab loses the answer, and
whichever tab opens the program next sees the result in the process statuses.

**The backend.** What the backend has to ensure is that nothing it starts dies
with it, or in the middle of what it was doing. Two things could make it so.
Without a session of its own, what the backend starts would belong to the
session of the server, even if the built-in scheduler puts each process in a
process group of its own, and a signal that stops the server, from its terminal
for example, would reach it: a `debasher_exec` of the built-in scheduler killed
that way would leave every process that it had not launched yet unlaunched, and
the run cut in the middle. And a tool whose output goes into a pipe read by the
backend dies of `SIGPIPE` at its next line once the backend is gone.

So every tool that launches or stops a run runs in a session of its own and
writes into a file, never into a pipe: `debasher_exec` into the run log, and
`debasher_stop` into a temporary file of its own, which the backend reads when
the tool ends and then deletes (two tabs may run it at the same time). With the
built-in scheduler, whatever the run launches inherits the session of
`debasher_exec`, away from the server; with Slurm, the jobs run in Slurm. The
tools of a resident program follow the same rule (see "A program that outlives
the tab").

A request that the backend does not finish, because it went away in the middle,
still reaches its end in the tool; only its answer is lost. A launch goes on, a
stop ends with the run stopped, and a temporary file that the backend did not
delete stays in the temporary directory of the system, with no other effect.
When the backend comes back there is nothing to recover, since it keeps no
state: the next reading of the process statuses shows the run as it is.

**What is not guaranteed.**

- **A restart of the machine.** Every process of a run of the built-in scheduler
  dies with it, `debasher_exec` included, and nothing launches the run again
  when the machine starts. A run in Slurm follows the rules of Slurm.
- **Being told that a run ended.** A run that ends while no tab follows it is
  reported to no one; the next tab that opens its program sees it in the process
  statuses.
- **A list of the runs in progress.** A run is found by loading its program from
  its home directory; the web UI keeps no record of the runs it launched, since
  the backend keeps no state.

# Frontend state and the canvas

## Screens and the store

The frontend has two screens: the home screen, which creates, loads or imports a
program, and the editor. Opening a program in the editor creates a store with it
(`ProgramProvider` in `store/ProgramContext.tsx`), and leaving the editor
discards the store, which stops nothing (see "A run that outlives the tab"). The
store holds the program, the selected process, the run phase with the last
output of `debasher_status`, and the process statuses, from which it derives
whether there is a run in progress. What follows the run (the polling of the
process statuses, the run phase derived from them, and the requests to launch,
stop or kill it and to reset the output directory or the program state) is
kept apart from the edits of the program, in `store/useProgramRun.ts`. The
dialogs edit a draft of their own and hand it to the store only when the user
accepts it.

Every change to the program goes through an operation of the store
(`addProcess`, `connect`, `updateOption`, ...), and every operation passes its
result through the same normalization (`normalizeProgram`), which derives the
connection sentinels from the edges and restores the default scheduler if it is
blank. The rules of "Connections" therefore hold after every change, not only
when the program is saved. An operation that would change a process of a group
first asks the user, and dissolves the whole group if the user agrees (see
"Groups"); if not, the program is left as it was. One action of the user asks
once, for all the groups it touches: deleting a selection on the canvas removes
its processes and edges in one operation, asked before the canvas drops
anything, so a declined deletion leaves them drawn; renaming a process along
with the definition that a loaded module provides for the new name is one
operation too. Every operation applies to the latest program, not to the one of
the last render, so the operations of one event build on each other, and once
the first has dissolved a group the next ones do not ask again.

The operations rest on plain functions of the program model, in
`models/programEdits.ts`: each takes a program and returns the edited one
without changing its input, and depends on nothing outside the model, neither
React nor the browser. The normalization lives there too, and so does the rule
of which groups an operation touches. What the store adds around them is what
needs the tab: asking the user before a group is dissolved, generating the ids
of new processes, options and edges, and keeping the result as the program of
the tab. Code outside the store that edits a program is to reuse these
functions, so that it obeys the same rules as the editor.

Each operation of the store is expressed as one or more edits, plain data
(`EditOp`) with everything they need, the ids of what they add included. A
list of edits can be built in one place, shown, and applied in another as one
change (`applyEdits`, which normalizes once at the end). `groupsTouchedBy`
tells which groups a list of edits touches, which have to be dissolved
(`dissolveGroups`) before it is applied; the store asks the user about them
first. `validateEdits` (`models/editValidation.ts`) checks a list of edits,
each against the program that the edits before it leave, with the rules that
the dialogs and the canvas apply, through the same functions: the names of
processes, the labels of options, the single Supervisor of a resident program,
the sequential processes, the rules of "Connections" (`isValidEdge` in
`models/connections.ts`, which the canvas applies while an edge is drawn), and
that the ids an edit refers to exist and those it adds are free. Whether the
engine accepts the name of a process is left to the backend, and what "Add
program" brings is checked before its edit is built (`mergeRefusal`).

The store keeps no history, so there is no undo, but it keeps the program as
it was last loaded or saved, and the program holds unsaved changes when it
differs from it in anything but the revision and the home directory
(`hasUnsavedChanges` in `models/externalChanges.ts`, which compares the two as
the program metadata would hold them, whatever the order of the keys of an
object). What a save keeps is the program it wrote, not the one the tab holds
when the save is answered, since the user may have kept editing meanwhile.
Leaving the editor with "Close", or closing or reloading the tab of the browser,
asks first when the program holds unsaved changes.

## From the store to the canvas

`adapters/reactFlowAdapter.ts` turns the program into what the canvas library
(React Flow) draws. Each process becomes a canvas node, with the process's id
and position, and a handle for each option, with the option's id: the inputs
along the top and the outputs along the bottom, except the pair of handles
that the canvas moves to keep a short edge between two processes that answer
each other (see "Connections"). Each edge becomes a canvas edge between two
handles, drawn in one of five ways: a plain edge; a back edge, routed along a
lane to the right of every process; a self-loop, routed around the right side
of its own process, clear of its box, as "The canvas of a resident program"
describes; a fanout edge, a wedge narrow at the end of the fanout family,
which follows the route of a back edge when its target sits at or above its
source; or, whatever its route would be, a label edge (see "Label edges"). An
edge from a FIFO is dashed.

A canvas node shows the process's name and options, its options handler mode (a
double border for `array` and `generator`, a dashed one for `manual`), its group
(a border color derived from the `groupId`, and a badge with the module's name),
and, as its background, the process status. An input whose value no connection
can give, since script generation writes it before it looks at any connection
(see "Connections"), or never writes it, for a task shaping option, has a hollow
handle, which takes no connection, and a tag after its label that says where its
value comes from: `shaping` for a task shaping option, `cmdline` for any other
command line option, a flag included, `spec` for an option taken from the
process specifications, and `flag` for a flag that the module always gives.

The canvas has a legend, which the user can fold. It says what each process
status means (see "Process status" in `doc/design_doc_engine.md`), and what the
canvas draws to tell processes and edges apart: the borders of a canvas node,
a hollow handle and its tag, an edge from a file or a value and one from a
FIFO, a fanout edge, the route of an edge that goes back up and of a
self-loop, a label edge, and the label of a fanout family.

Of what the canvas shows, only the positions and which edges are label edges
belong to the program model and are saved. The selection, the part of the
canvas in view (fitted to the program when the editor opens), whether the
legend is folded and the colors are not.

Where the program brings processes whose position nobody chose, a function of
the model chooses it (`models/programLayout.ts`). The processes of an imported
program, whose module says nothing about positions, are placed in layers by the
depth of their connections (`layoutProcesses`): a process that feeds another is
placed above it, so that edges run down the canvas, from the outputs along the
bottom of a canvas node to the inputs along the top of the next, and the
processes of one layer are placed side by side, in their order in the program.
The number of passes is bounded, so a cycle ends with some layering rather than
none, and a self-loop, which says nothing about the order of two processes, is
left out. `nextFreePosition` gives the place to the right of the rightmost
process, where "Add program" moves the processes it brings, as a block that
keeps their layout. A process that the user adds in the editor is the exception:
it starts at a fixed place of the canvas, and the user drags it.

## Label edges

Moving processes and reordering options does not always remove the crossings
of a program's edges: some graphs have no drawing in the plane without one
(three processes that each feed the same three others, for instance). For the
edges that still cross, the canvas can draw a label edge instead of a line, as
the net labels of an electronic schematic do: a short stub at each handle, a
ring at its far end, and a text that names the option at the other end as
`<process> <option>`. The text runs vertically away from the node, so that the
stubs of neighboring handles never overlap however long their texts are; a
long text is cut, and the tooltip of the stub has it whole.

Each edge says how it is drawn (`ProgramEdge.display`: `line`, the default for
an edge saved without it, or `label`), so the edges of one output may mix both.
It is part of the program model and is saved, but it only changes the drawing:
script generation ignores it, and so does every check of the connections.
Changing it does not dissolve a group, since it is no part of what
`add_debasher_program` declares.

**The stubs of an output and of an input.** An output with several label edges
would draw several stubs on top of each other at its handle, so only one of
them, the first in the program, draws the stub at the source, which names its
target, or says how many there are when there are several (`3 inputs`), with
the list in its tooltip. An input with fan-in (see "Connections") draws one
stub per label edge, side by side.

**Finding the other end.** A label edge draws a faint ghost of the line it
stands for while one of its stubs is under the pointer, while it is selected,
and while its source or its target is the selected process. Hovering the
source stub shared by several label edges shows the ghosts of all of them. A
double click on a stub brings the other end into view, never zooming in: the
source from the target stub, every target from the source stub.

**Selecting and changing it.** A click on a stub selects its edge, which the
delete key then removes like any other, except the source stub shared by
several label edges, which selects none, so that the delete key never removes
an edge that the user did not pick. The context menu of an edge switches it
between a line and a label edge and, when its output has more than one edge,
switches all of them at once. Opened from a shared source stub, the menu only
has the entry that switches every edge of the output.

**Connecting by name.** An edge between two processes far apart on the canvas
can be made without drawing it across: the inspector offers, on each input that
some output can be connected to, a dialog where the user types the output as
`<process> <option>`, with the outputs it can be connected to offered as they
type (`connectionCandidates`, which applies the rules of an edge drawn on the
canvas, see "Connections", and leaves out the outputs already connected to the
input). The new edge is a label edge unless the user asks for a line.

## Keeping the canvas in step with the store

The canvas library draws from its own list of canvas nodes, which it updates
on every frame of a drag. The canvas keeps that list, writes each new position
into the store as the drag goes, and refreshes the list from the store only
when the program's structural key changes (for each process: its id, name and
mode, and the id, label and direction of each option, and for an input, where
its value comes from when no connection can give it) or when the set of moved
handles changes, keeping the positions that the list already has. Refreshing
it on every change of the store would fight with the drag. After the program
was loaded again from its home directory (see "Revisions of the program
metadata"), the list takes the positions from the store instead, since they are
those that someone else saved, a moved process included.

The rule that follows is that whatever a canvas node draws from its process
must be part of the structural key; otherwise the canvas node keeps drawing an
old value until the next structural change. The group is not part of it today,
so a dissolved group keeps its color and its badge on the canvas until then
(see "Future work"). The process status does not go through that list: each
canvas node reads it from the store. Neither do the edges, which are derived
again from the store on every change.

## The Help menu

The Help menu, at the right of the toolbar of the editor, before "Close", links
to the documentation of DeBasher (its contents and the page on the web UI) and
to the repository (the source code and its issues). It also opens "How to cite
DeBasher", a dialog with a link to the article that describes DeBasher and its
reference, as text and as BibTeX, each with a "Copy" that behaves as the one of
the prompt panel when the browser refuses the clipboard (see "The prompt
panel"), and "Claude Code", a dialog with the command that starts Claude Code on
the program where the backend offers it (see "Claude Code on a program"). The
links and the reference are data, in `models/helpLinks.ts`, and the command and
the skills it lists in `models/claudeCommand.ts`. Every link opens in a new tab
of the browser, with no access back to the tab of the editor, so that the editor
stays as it is, with any unsaved changes (see "Screens and the store").

A link to a page of the documentation of DeBasher names a page of
`rtdocs/source` by the name of its source, and the tests of the frontend check
that the page exists in the repository, where the sources of the documentation
of DeBasher are present (they are not distributed with the package), so that a
renamed page breaks a test instead of a link. They check as well that the
reference is the one that `README.md` asks to cite. The links lead to the
published documentation of DeBasher (its latest version), not to that of the
version that serves the web UI, so a link may lead to pages newer than the
installed version (see "Future work").

# Sequential processes in the web UI

A process can run code of its own as a step, with `seq_execute`, and a
sequential process gives such code a name and a process specification, so that
it can be written in another language, be an alias, or ask Slurm for resources
of its own (see "Sequential processes" in `doc/design_doc_engine.md`). A program
whose processes run sequential processes keeps them through the web UI: this
section describes how a sequential process enters the program model, how it is
generated and imported, and where the editor shows it.

## Sequential processes in the program model

A program carries its sequential processes in `Program.seqProcesses`, a list of
`SeqProcess`, beside its processes and not inside any of them, since a step can
be run by any process of the program. A sequential process has an `id`, a
`name`, a `description`, its code (`language` and `code`, as a process has
them), its specifications and, when it came with "Add program", a
`groupSource`. It has no options, no options handler, no additional methods and
no position: the engine calls nothing of it but its process function, and it
is not part of the dependency graph that the canvas draws.

Its name follows the rules of a process name, and is unique across the
processes and the sequential processes of the program, as the engine requires.
Its specifications are those of a process that the engine accepts on a
sequential process: the computational specifications `cpus`, `mem` and `time`,
each optional, and the additional specifications `alias`, `externalAlias` and
`aliasOptMap`. The model has no place for `processdeps` and `force`, which the
engine refuses on a sequential process, and, as for a process, none for
`nodes`, `account` and `partition`.

## Generating and importing a sequential process

**Script generation.** After the functions of the processes, the generated
module holds, for each sequential process in the order of the model, its
`_document` function and its code, written as the code of a process is: a Bash
function as it is, and code in another language as a heredoc function
`<name>_heredoc_<suffix>`. A sequential process with an alias gets no code of
its own, the code of the function it runs is written as for a process, and the
check of "Code that a loaded module already provides" applies to it as to a
process. `<name>_program` then has one `add_debasher_seq_process` for each
sequential process, after the `add_debasher_process` lines, with its
specifications. Script generation refuses a program in which a sequential
process and a process, or two sequential processes, share a name. When the
module is generated to read its environment variables (see "Environment
variables of a program"), a sequential process without code gets a function that
does nothing, like a process. Saving copies the file of a relative
`externalAlias` of a sequential process into the home directory, as it copies
that of a process (see "The home directory").

**The module documentation.** `debasher_doc_mod` has the flag
`--show-seq-procs`, which import adds to the flags it always gives. With it,
after the processes, the module documentation has one section for each
sequential process that the `_program` method adds, under a heading of its own
(`Sequential Process: <name>`), which the parser of the module documentation
tells apart from that of a process, since a process name has no blank. The
section holds what the other flags ask for and a sequential process has: its
description, its implementation (its code and language, or the target of its
alias) and its specifications. The engine finds the sequential processes in the
same `_program` run that gives the processes, so nothing new has to load.

The code of a process includes the functions of the same file that it calls
(see "What the engine reports"), and a process that runs a step names its
function. The engine leaves a sequential process out of the functions that it
includes in the code of a process, so that its code comes back once, as that of
the sequential process. A function that a process runs with `seq_execute`
without declaring it as a sequential process is still included in the code of
that process, as any other function it calls.

**Import.** Each section of a sequential process becomes a `SeqProcess`, with
its code replaced by its verbatim source as the code of a process is (see
"What the engine reports"), and the specifications that the model does not
hold dropped. The round trip keeps the sequential processes, their code and the
specifications that the model holds, in both directions.
`test/api/test_round_trip.py` imports every module of `data/programs/`, and
checks besides that the import of `debasher_cycle_dyn_sched.sh` has its
sequential process, since a fixed point alone would not catch one lost on
every import.

**Groups.** "Add program" brings the sequential processes of the other program
with its processes, marked with the same `groupSource`, and `groupSize` counts
both. While the group is whole, with every process and sequential process still
present and none edited, its `add_debasher_program` adds them too, and changing
or removing a sequential process of the group dissolves it, as changing a
process of the group does (see "Groups"). "Add program" refuses a program that
brings a process or a sequential process with a name that the current program
already has, whatever its kind, as `add_debasher_program` declares each one
under its own name.

## Sequential processes in the editor

A sequential process is not drawn on the canvas, which shows the processes and
their connections, and a sequential process has neither. The toolbar opens a
"Sequential processes" dialog, beside those of the preamble, the shared
directories and the environment variables, which lists them and adds, renames or
removes one. The one selected in the list is edited beside it: its name,
description and specifications, its alias included, and its code in the same
code editor as the code of a process. As every dialog, it edits a draft of the
whole list, and hands it to the store when the user accepts it, once the draft
is checked: no name blank, none shared by two sequential processes or by a
process, each one valid as a process name, none with both an alias and an
external alias, and none in Bash, without an alias or an external alias, whose
code defines no function of its name, which the engine would refuse. A new
sequential process starts with a Bash function of its name that does nothing,
and this code follows its name and its language (no code in another language)
until it is edited. Accepting a draft that changes or removes a sequential
process of a group first asks to dissolve the group.

The web UI does not read the code of the processes, and so does not know which
of them run which sequential process: renaming or removing a sequential process
leaves the calls to `seq_execute` that name it as they are, and the program
fails when such a call runs. A resident program has no sequential processes
(see "The program model of a resident program").

# Guarantees and non-goals

This section gathers the guarantees that the web UI gives today for general
programs, stated in the sections above, and what it deliberately does not
try to do. Where a guarantee has a known gap, "Future work" lists it. Those of
resident programs, designed and being built, are gathered in "Guarantees and
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
- **No save over another's without knowing.** A save into a program's own home
  directory never overwrites what another tab or client saved there since the
  program was loaded, unless the user, told so, chooses to (see "Revisions of
  the program metadata").
- **No write over another's file.** The editor of the program files panel never
  overwrites a file that someone else wrote since it read it, unless the user
  chooses to (see "Reserved names and user files").
- **Unsaved changes are lost only when the user lets them go.** A revision saved
  elsewhere is loaded on its own only into a tab with no unsaved changes, and
  leaving the editor or closing its tab with unsaved changes asks first (see
  "Revisions of the program metadata" and "Screens and the store").
- **A program lives where it is loaded from.** Its home directory is the
  directory it was loaded from, even if it was copied or moved there (see
  "The home directory").
- **User files are the user's.** The program files panel, and the MCP server
  through the same endpoints, never touches a reserved name, never leaves the
  home directory, never deletes or moves anything but the entry that a path
  names and its contents (a link and not what it points to, never the home
  directory itself), and never changes the generated script (see "Reserved names
  and user files").
- **A reset stays in the output directory.** Resetting it deletes only what is
  inside it, and does nothing when it is blank, missing, the root, the user's
  home or the home directory (see "The output directory").
- **No change under a running program.** While there is a run in progress, the
  web UI refuses to save, to run, validate or check the options of the
  program, to reset the output directory and to change it. The backend refuses
  them too, whoever sends the request (see "The home directory").

**Execution and observation**

- **One run per output directory.** A run is not launched on an output
  directory with a run in progress.
- **Nothing that happens to a tab or to the backend stops a run, or cuts a tool
  in the middle.** A run is stopped only with "Stop program" or "Stop process",
  and every tool that launches or stops it runs in a session of its own and
  writes into a file (see "A run that outlives the tab").
- **A program that the engine refuses is reported at once.** With Slurm, `/run`
  waits for `debasher_exec`, which ends once the jobs are submitted, and with
  the built-in scheduler it validates the program first; either way it shows
  what the engine printed. The one exception is a first round of the built-in
  scheduler that can choose no task, which shows as `unfinished` (see "Launching
  a run").
- **Any run is observed.** The process statuses, and the guards that depend on
  them, cover a run launched from another tab or from the command line.
- **Watching a FIFO takes nothing from it.** "Watch FIFO" reads the FIFO
  mirror, never the FIFO.
- **Talking to a FIFO competes with nobody.** "Talk to FIFOs" only opens
  unconnected FIFOs, and never blocks a request for more than a few seconds.
- **Nothing is lost when the backend restarts**, since it keeps no state (see
  "The backend keeps no state").

**The code prompt**

- **Nothing leaves the machine through the code prompt.** The web UI calls no
  AI service: the user copies the code prompt, and sees all of it first (see
  "A prompt for the code of a process").
- **Code from an AI tool is code like any other.** It reaches the program
  only by being pasted into the code editor and saved, and "Cancel" drops it
  (see "The prompt panel").

**Access to the backend**

- **No call to the API without the token.** The backend answers no request to
  the API that does not carry its token (see "What the backend checks"), and it
  cannot be started without one (see "The token").
- **The browser hands the token to nobody.** It keeps the token for the origin
  of the backend alone and sends it only where the page puts it, and the token
  is never in an address that reaches a server or a log (see "How a request
  carries the token"). A token given to outlive its backend is the exception
  (see "What the token does not protect").
- **No page of another origin acts through the browser.** Its requests carry
  no token, and one that names a host that is not the backend's is refused
  when the backend listens on a single address (see "What the backend
  checks").
- **The token file belongs to the backend that owns the port.** It is written
  only once the port is bound, readable only by the user, removed before the
  port is released when the backend stops in order, and used by `debasher_mcp`
  only while its backend is alive and only towards the local machine (see "The
  token file").
- **A refused token loses no unsaved change.** The editor stops and says how to
  get a new token, and keeps the program as it is (see "The editor without a
  valid token").

## Non-goals

- **Security beyond the token.** The web UI trusts whoever holds the token: it
  has no users and no permissions, and it runs every tool, and reads any path,
  as the user who started it. It speaks plain HTTP, so it listens only on the
  local machine unless told otherwise (see "What the token does not
  protect").
- **Several people on one program.** Two tabs on the same program or the same
  directories are not coordinated beyond two guards: a save over what another
  saved since the program was loaded is refused (see "Revisions of the program
  metadata"), and the guards based on the engine's own files (a run in progress)
  see the other tab. A tab learns of a revision that another saved, and loads
  it or asks, but nothing merges the changes of two tabs.
- **Keeping unsaved work.** There is no autosave and no undo: unsaved changes
  live only in the tab.
- **Live updates.** The web UI learns what happens in a run by polling, every
  few seconds, not by being told.
- **Being told that a run ended, or a list of the runs in progress.** A run is
  found, and its end seen, by opening its program (see "A run that outlives the
  tab").
- **Importing any module faithfully.** Import recognizes a closed grammar, and
  keeps the rest as it is rather than trying to understand it (see "What the
  round trip preserves").
- **An output directory that follows a moved program.** A program loaded
  from a new place keeps the output directory it was saved with (see "The
  home directory").
- **Checking the code that an AI tool writes.** The web UI treats it as code
  written by hand; validating the program and running its tests check it
  (see "The prompt panel").

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

The node code editor makes the inheritance visible. Next to each
hook of a `ProgramLauncher` or a `DirectoryWatcher` it says whether the node
runs the hook of its class (when the body is empty) or replaces it (when the
body has code), and names the call that keeps what the class does, such as
`super().process_data(port_name, packet)`. Below the body it shows, read only
and in gray, the code that the node inherits, which is what a body would
replace. That code is read from the runtime library itself, never from a copy
kept apart from it: the installed library first, since that is the one a node
imports, and the sources in `engine/` only in a build that has not been
installed. The module is parsed, never imported. When the library cannot be
read, the editor says so, and the hooks are edited as usual.

The class is named after the process, in CamelCase (`counter` gives `Counter`,
`org.ns.count_words` gives `OrgNsCountWords`), as the engine requires (see
"Defining a node" in `doc/design_doc_resident.md`), and the editor shows its
declaration above the class body, read only. The model therefore holds no name
for it, and import needs none: a module that loads already names its class this
way. A process named in CamelCase, as the nodes of a resident program are by
convention (`Counter`), shares its name with its class, since turning a name
into CamelCase leaves such a name as it is; a namespaced one always differs from
its class. The editor refuses a process name whose class would hide a class of
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
them are initiators, so adding or removing a node needs no change to the
`Supervisor`. They are:

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
processes it launches all at once. Nor is `process_outdir`: the engine never
resets the process output directory of a node, which holds what the node has
done so far, so a task subdirectory would give a node nothing that its process
output directory does not.

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

**Sequential processes.** "Sequential processes in the web UI" does not apply:
the engine refuses a sequential process in a resident program (see "Defining a
node" in `doc/design_doc_resident.md`), so the toolbar of a resident program has
no "Sequential processes" dialog, and the program has none.

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
  channel of a node, or the fanout family `-<process>_hb-ith` for an `array` or
  `generator` process;
- on the `Supervisor`, `-out<process>_trig`, the trigger port to an
  initiator, or the fanout family `-out<process>_trig-ith`;
- on every initiator, `-trigger`, the input of its control port, connected to
  the trigger port of the `Supervisor` or, without one, written from outside
  the program;
- on the `Supervisor`, `-manual`, its manual trigger port, and the flag
  `-no-hold-fifos`, together with the command line options that count its
  fanout families.

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
refuses in a general program, with the same answer (see "What script generation
refuses"), script generation refuses a resident program with more than one
`Supervisor`; a process with no node kind; a node in `manual` mode; an option of
the user that takes a label of the Supervisor wiring, uses the option channel
`value_desc`, `shared_dir` or `process_outdir`, is mirrored or has the fifo tag
`control`; a `Supervisor` with options of its own, or in `array` or `generator`
mode; and, in a program with a `Supervisor`, an `array` or `generator` node that
reaches no fanout family counted by a command line option. The editor offers
none of them, and script generation refuses them in program metadata written by
hand or by another tool.

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

*Built.*

**The home directory** is the same as for a general program (see "The home
directory"): the program metadata, the generated script and the user files,
with the same guarantees.

**The output directory** holds, besides what a general run leaves there, the
program state: what each node keeps across runs, its checkpoints, its input log
and its halted marker, in its execdir, and what its process left in its own
output directory, which the engine does not empty when it launches a node again
(see "Ordered shutdown" in `doc/design_doc_resident.md`). A resident program is
resumed from that state every time it is launched on the same output directory,
so the output directory of a resident program is part of the program in a way
that the output directory of a general program is not. The rules that keep the
two directories apart apply unchanged. Besides the run log, the web UI adds to
it the launch record (see below) and the snapshot log (see "Running a resident
program").

**Resetting.** "Reset output directory" gives way to "Reset program state",
which runs `debasher_reset_resident` on the output directory: it takes the
program state away, for every task of every process, and the next launch starts
every node afresh. By default the tool sets the state aside under
`__reset__/<timestamp>/` in the output directory, since a checkpoint that is
lost cannot be made again, and the dialog offers to delete it instead
(`--delete`). As for a general program, the frontend refuses to reset while
there is a run in progress, and the backend and the tool refuse it too; the
action is offered while the program is `stopped`, since a program that is `new`
has nothing to reset. What is set aside stays in the output directory until the
user deletes it.

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

- Every launch from the web UI that ends well leaves the launch record in the
  output directory.
- When "Run program" finds program state in the output directory, and the
  program, compared as below, or the program options differ from the launch
  record, the frontend asks whether to resume with the changed program, the user
  answering for its compatibility, or to reset the program state first and start
  afresh.
- The comparison leaves out every description, of the program, of its
  processes and of their options, so that a change of a description asks
  nothing: the record holds the script generated with them left out, and the
  program is compared the same way. The positions on the canvas are not in
  the script.
- With program state and no launch record, as when the state comes from a run
  launched outside the web UI, the frontend asks all the same, and says that it
  cannot tell which program produced the state.

The backend finds the program state by the names that the engine gives to it
in the output directory, the same that `debasher_reset_resident` takes away,
and would have to change with them. The check sees only the generated script
and the program options: a change in a module that the preamble loads goes
unseen.

## Running a resident program

*Built.*

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
process is launched, `/run` waits for it, as for a general program with Slurm,
and answers with its exit code and what it printed, which the frontend shows
when the launch fails. A program that the engine refuses when it loads it, such
as a node that no initiator reaches, is thus reported at once, as "Validate
program" reports it, and not only in the run log. The output of `debasher_exec`
still goes to the run log, a file, and the backend reads it once `debasher_exec`
ends: a pipe would be inherited by the processes it launches, and the request
would wait for them.

**The launch record at launch time.** `/run` goes through these steps:

1. With a run in progress, it answers with a conflict and does nothing, as for
   a general program.
2. With program state in the output directory and a launch record that differs
   from the program, or none, it answers with a conflict, unless the request
   says that the user chose to resume with the changed program (see "The
   directories of a resident program"). The frontend asks before sending the
   request, and the backend checks again, since it keeps no state and another
   tab may have launched the program in between. A user who chooses to start
   afresh has the frontend reset the program state first, setting it aside as
   "Reset program state" does by default, and then send the request.
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

"Validate program" and "Check program options" apply unchanged.

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
of the node, not a stop: the node leaves no mark of a clean end, and resumes
from its last checkpoint and its input log once it is launched again. The
action is named for what it does, "Restart node". It is offered on every node
but the `Supervisor`, which nothing supervises: the nodes would go on without
anyone to relaunch them or to hold their FIFOs, until the next stop. The user
confirms it with a warning: the node restarts from its last checkpoint and
replays its input log, and what its FIFOs hold is kept by the peers at their
other ends (see "Ghost connections" in `doc/design_doc_resident.md`). Only a
channel whose two ends are restarted together, a self-loop of the node or a
channel between two tasks of the process, has no peer to hold it. The action
serves to free a node that is stuck, or to try the recovery of a program. Who
launches the node again depends on the program:

- In a program with a `Supervisor`, the `Supervisor` relaunches it (see
  "Relaunching a downed node" in `doc/design_doc_resident.md`). The `Supervisor`
  also holds a channel whose two ends are restarted together, unless the program
  was launched with `-no-hold-fifos`: such a channel may then lose what it held,
  which the warning says. A node restarted again and again before it sends a
  heartbeat counts for the `Supervisor` as a node that crashes after every
  relaunch, and after a few times the `Supervisor` gives up on it and stops the
  program (see "Escalation on a permanent node failure" in
  `doc/design_doc_resident.md`), which the warning says too.
- In a program without a `Supervisor`, the backend relaunches it as "Relaunch
  node" does (see below), once no task of the process runs, and holds the
  relaunch lock from the stop to the relaunch. When some task still runs a
  few seconds after the stop, it reports an error and relaunches nothing.
  Nothing holds a channel whose two ends are restarted together, which may
  lose what it held: the warning says so when the node has one.

On an `array` or `generator` process the action restarts every task, since
`debasher_stop` stops a process as a whole.

**Relaunching a node.** In a program without a `Supervisor`, a node that goes
down stays down: nothing relaunches it, and "Run program" launches nothing
while there is a run in progress. Meanwhile each node that writes to it blocks
once the pipe is full, and its outbound backlog grows until the node fails.
"Relaunch node", in the context menu of a node of such a program, relaunches
it as the `Supervisor` would:

- The backend relaunches each task of the process that is down, and only
  those, with `debasher_launch_process -d <output directory> -p <process>`,
  and `-t <task index>` for a task of an `array` or `generator` process. A
  task that ended cleanly, as a node does in an orderly stop, is not down,
  and neither is a task with no `.id` file or whose PID exists: relaunching a
  task that runs would give two incarnations of it reading the same FIFOs.
  The backend looks for the tasks that are down and relaunches them under the
  relaunch lock.
- The relaunched node resumes from its last checkpoint and its input log. Its
  peers held its FIFOs while it was down, so only a channel whose two ends
  were down together may have lost what it held.
- The frontend says which tasks were relaunched, or that none was down. The
  action asks for no confirmation, since it acts only on what is down. It is
  offered on every node while the program is `live`, whatever the color of
  the node: the process status of an `array` or `generator` process shows it
  in progress while any of its tasks runs, even with others down.

It is not offered in a program with a `Supervisor`, whose own relaunches it
would compete with. The backend reads the `.id` and `.finished` files by the
names that the engine gives to them, as the `Supervisor` does, and would have
to change with them.

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
setup. The action is offered only while there is a run in progress, and works
as well on a program launched from the command line.

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
becomes `finished` once every process has finished (see "Following a run"). That
does not fit a resident program: after an orderly stop every node has ended
cleanly, and `debasher_status` reports every process finished, although the
program has not finished but stopped, and resumes at the next launch. The run
phase of a resident program is therefore derived from the same readings, whoever
launched the program, with values of its own:

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
- `launching` and `stopping`: while a request of the tab to launch the
  program, or to stop or kill it, has not been answered.

A program may stop with no action of the web UI, when its `Supervisor` gives up
on a node, and the run phase goes from `live` to `stopped` at the next reading.
The rule of two readings in a row does not apply: it covers the gap between one
process ending and the next starting, and the processes of a resident program
all start at once.

**The guards.** The guards that depend on a run in progress apply unchanged,
since they already read the process statuses and not the run phase: while the
program is `live`, the frontend refuses to save, to reset the program state and
to change the output directory, and the backend refuses them too and `/run`
refuses to launch. What changes is which actions are offered only while the
program is `live`: "Stop program", "Kill program", "Restart node", "Relaunch
node" and "Take snapshot", while "Reset program state" is offered only while it
is `stopped`. What the tab does with a live program when it is closed, reloaded
or leaves the editor is in "A run that outlives the tab", and what a resident
program adds to it in "A program that outlives the tab".

## Observing and talking to a live program

*Built.*

A resident program is observed through the same process statuses as a general
one, and through what each node keeps in its execdir: its checkpoints, its input
log, its halted marker and its notice. This subsection says which actions of
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
  relaunching it or has given up on it, or, without a `Supervisor`, it stays
  down until "Relaunch node" relaunches it. In a program that is not live, it
  stopped abruptly.
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
  the outbound backlog against its limits, the cap and the limits being those in
  force for the node, which it writes into its node info file, and whether every
  thread of the node was alive at its latest heartbeat tick. These are the
  figures that warn of a coming failure: with no rounds, the input log grows
  until its cap stops the node, with a reader that does not read, the outbound
  backlog grows until it does, and a node with a dead thread shows as
  `IN-PROGRESS` while it does nothing. The summary also shows the notice of the
  node, if it has one (see the notices of the nodes, below). A node info file
  older than two heartbeat intervals has stopped being written: in a node that
  is alive, this means that it is still replaying its input log or that its
  heartbeat thread has died, and the summary marks it; in a node that is not
  alive, it is simply the file of its latest incarnation, shown unmarked.
- The checkpoints: the list of those that the node retains and, for the one
  chosen, its `node_state`, formatted, together with the messages in transit
  that it holds, `channel_state` and `out_backlog`, counted by port.
- The input log: its latest records, which the user can filter by port, cut
  at the same number of lines as the other outputs. The records above the
  `capture_pos` of the latest checkpoint are marked. The ports to filter by
  are the input ports that the program model knows (its external inputs and
  its connected inputs, named as the input log records them: the option name
  without its leading dash), together with the ports of the records read,
  which add the control port of an initiator, not in the model.

The action is offered on every node but the `Supervisor`, which keeps no node
state, and enabled once the node has been launched, whatever the run phase: a
stopped node keeps what it held, which is when it is most worth reading. The
summary marks a figure only when it crosses a limit that the engine sets (a
node that is down, a dead thread, a live node whose node info file is older
than two heartbeat intervals, an outbound backlog over the size above which
checkpoints are skipped, skipped checkpoints, an input log at its cap or that
cannot be read), never a threshold that the web UI sets. Each view is read
when it is shown and again when the user asks, never polled, so that a view
left open does not start the engine tool every few seconds.

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
rule is written once. Whether a batch run is a whole general program, or the
single process that the class attribute `PROCESS` of the launcher node names
(see "A single process" in `doc/design_doc_resident.md`), comes from the node
info file of the launcher node, as `summary` gives it. The action is enabled
when "Show node state" is, and its list is read as every view here is, never
polled. Launching again a batch run that failed is not offered until the
engine has a command for it (see "Future work" in
`doc/design_doc_resident.md`).

**A `DirectoryWatcher`** has no view of its own. The files that it has asked
to launch are in its node state, which "Show node state" shows, and the
directory it watches is the value of its option `-watchdir`, which "Show inputs
and outputs" opens.

**The notices of the nodes.** A node may leave one notice for whoever watches
the program, `info` or `warning`, which says how it is now, such as that its
configuration file is missing (see "Notices" in `doc/design_doc_resident.md`).
The web UI reads the notices with the process statuses: for a resident program,
the backend runs `debasher_inspect_resident -d <output directory> notices`
together with `debasher_status`, one call for the whole program, and answers
with both. A canvas node with a notice shows a mark of its level, whose tooltip
gives the text, and the summary of "Show node state" shows it, with when it was
set. An `array` or `generator` process has one canvas node for all its tasks: it
shows the mark of the highest level among the notices of its tasks, and the
tooltip lists them, each with its task index, as many as the tooltip can hold.
The mark is dimmed while the process of the canvas node is not `IN-PROGRESS`:
its notice is then that of the latest incarnation of a node that no longer runs,
still worth reading after a failure (a configuration file that is missing, for
example), until a relaunch of the node removes it. A failure of the tool leaves
the canvas without notices, and the statuses are shown as usual.

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

The two halves of the dialog are independent, and both optional. In a general
program a line written into an input usually brings one line back from an
output, and the dialog pairs them: it writes, and waits for the answer (see
"FIFOs"). A node of a resident
program owes no such answer. It may send nothing for a message, or several
messages, or send on its own, from `observe`, and its business output also
carries the `BARRIER` of every round, which answers nothing the user wrote. A
dialog that waited for an answer to each write would block on a node that
sends every third message, and would take a `BARRIER`, or the answer to an
earlier write, for the answer to the last one. And a program may have only one
half: a node fed from outside that writes only files, or a node that sends on
its own and takes nothing in. So the user picks an external input to write
into, a business output to read from, or both; writing never waits for a
read, a loop reads the output for as long as the dialog is open, and what is
written and what is read go into one transcript, in the order in which they
happened.

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
thread, and with it the node.

For the same reason a line is never written in part. The backend writes it
with a single `write()` on a FIFO opened without blocking, which POSIX makes
atomic up to `PIPE_BUF` bytes (at least 512, 4096 on Linux): the whole line
goes into the pipe or nothing does, even when the attempt is given up, and it
never interleaves with a line of another writer of the same input. A message
whose line is longer than that is refused. The open and the write are tried
again for eight seconds, and what makes them fail says what is wrong: nothing
holds the read end of the FIFO (its node is down, and no `Supervisor` holds
it), or the pipe is full (its node is not reading it). A write ends once the
line is in the pipe, not once the node has logged it, which its input log
shows afterwards.

The web UI never writes a `CLOSE` into an external input. A `CLOSE` closes the
port for good, across every resume until the program state is reset, and the
code of the node never learns of it, since no hook reports it (see "Future
work" in `doc/design_doc_resident.md`). A source that wants to tell a node that
it has finished sends a `DATA` with a payload that the node understands.

**Reading.** The backend reads the FIFO one byte at a time, so that it never
takes anything past the line it reads, and decodes each line as an envelope.
It skips the blank lines and the `HELLO` with which every incarnation of a
writer starts, and answers with the type, the sequence number and the payload
of the first other envelope, or with a line that is not one, as it was read.
The frontend shows the payload of a `DATA`, with its sequence number, marks a
`BARRIER` as the marker of a round and a `CLOSE` as the end of the writer. The
backend opens the FIFO without blocking, so opening it never waits, and a read
sees no end of file while the node or the `Supervisor` holds the FIFO (see
"Ghost connections" in `doc/design_doc_resident.md`); with neither, a read
finds nothing, as when nothing has been written. A read waits two seconds for
the first byte of a line, and the frontend reads again at once. A line started
is read to its end, within thirty seconds: its writer writes it whole, and
only a writer that died in the middle of it leaves it cut, which the dialog
reports, pausing the reading.

Reading takes the message from the channel, as it does for a general program,
and so competes with any other reader outside the program. The user can pause
the loop, and nothing is then taken; the read in flight still ends, and what
it took is shown. The short bound keeps small what a read in flight when the
dialog closes can take and show to nobody: at most one message. A business
output that nobody reads fills its pipe, and then the outbound backlog of its
node, until the node fails; "Show node state" shows the backlog growing.

## A program that outlives the tab

*Built.*

A resident program is meant to live longer than any tab that follows it, and
longer than the backend that launched it. The rules of "A run that outlives the
tab" hold for it unchanged; this subsection says what a resident program adds to
them.

**The tab.** Besides "Stop program", "Kill program" and the escalation of the
`Supervisor` also stop the program (see "Running a resident program"). The
message shown when leaving the editor speaks of a program that is `live`.

**The backend.** A live program depends on the backend for nothing: once
`debasher_exec` has ended, its nodes, its `Supervisor` and the periodic
`debasher_snapshot_resident` run on their own. Every tool that acts on it
(`debasher_exec`, `debasher_stop_resident`, `debasher_stop`,
`debasher_launch_process` and `debasher_snapshot_resident`, once or with
`--every`) runs in a session of its own, as the batch runs of a
`ProgramLauncher` do, and writes into a file, never into a pipe: `debasher_exec`
into the run log, the periodic snapshots into the snapshot log, and the stop,
the hard kill, a relaunch and a single snapshot into a temporary file of their
own. An orderly stop cut by the backend going away could otherwise leave the
`Supervisor` stopped and the nodes alive, with nobody to relaunch them. Whatever
the program launches later, the relaunches of the `Supervisor` included,
inherits the session of `debasher_exec`, and a node that the web UI relaunches
that of its `debasher_launch_process`, both away from the server.

A request that the backend does not finish still reaches its end in the tool, as
for a general program, and two of them leave more than the answer behind:

- a launch ends, but its launch record is not written, and the next launch
  compares the program with the record left before it, which errs on the side of
  asking (see "Running a resident program");
- a round of "Take snapshot" closes or not, which "Show node state" shows.

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

Two tabs on the same live program are not coordinated, as for a general program
(see "Non-goals"). What the engine's files guard still holds: a second launch is
refused while there is a run in progress. Relaunches are the exception: the
relaunch lock keeps two tabs from relaunching the same task. Two orderly stops
at the same time, or an orderly stop and "Restart node", are not coordinated by
the web UI; a single orderly stop for each output directory is left to the
engine (see "Future work" in `doc/design_doc_resident.md`).

**What is not guaranteed**, besides what "A run that outlives the tab" says:

- **A restart of the machine.** The program then shows as stopped abruptly,
  since its processes did not end, and "Run program" resumes it. As after a
  hard kill, what the pipes held is lost, which the nodes that read them report
  as a gap in the sequence numbers. Starting resident programs with the machine
  would need mechanisms of the operating system that are not portable.
- **Being told that the program stopped.** A program that stops by itself, when
  its `Supervisor` gives up on a node, while no tab follows it, is not reported
  to anyone. The next tab that opens it sees it in its run phase.
- **A `Supervisor` that nothing supervises.** If the `Supervisor` dies, its
  canvas node shows `UNFINISHED`, and the web UI does not relaunch it: the
  program goes on without relaunches until its next stop, as the failure model
  of `doc/design_doc_resident.md` says (see "Supervising the `Supervisor`" in
  its Future work).

## The canvas of a resident program

*Built.*

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
- **A notice**, with a mark of its level, `info` or `warning`, in the head of
  the canvas node, dimmed while its process is not `IN-PROGRESS` (see
  "Observing and talking to a live program").

The color of the border and the badge of a group stay unused in a resident
program, rather than taken for the node kind, so that the same mark never
means two things depending on the type of the program.

**The handles of a node.** Every option has a handle, the inputs along the top
and the outputs along the bottom, as in a general program. A connection can
reach fewer of them in a resident program, only a business output and a
business input (see "The program model of a resident program"), and a handle
shows what the option is:

- A business output has a handle along the bottom. With no connection it is
  read outside the program, and a mark says so: something outside has to read
  it, or the outbound backlog of the node grows until the node fails, and it is
  where "Talk to FIFOs" reads.
- A business input has a handle along the top, which accepts one connection,
  from a business output. An input that a connection can reach has it before
  it is connected too, even while it holds a literal value, such as the index
  of a task (`-id ${task_idx}`): the canvas node draws it as any other input,
  and the editor of the option shows its value.
- An external input is drawn along the top with the other inputs, with a
  handle that accepts no connection and a mark that says that it is written
  from outside the program. It is where "Talk to FIFOs" writes, and where the
  activity of the program comes in, which the canvas thus shows.
- A configuration option that no connection can reach has a hollow handle, which
  accepts no connection, so that it does not look like an input left
  unconnected, and a tag after its label that says where its value comes from:
  `shaping` for a task shaping option, `cmdline` for any other command line
  option, a flag included, `spec` for an option taken from the process
  specifications, `flag` for a flag that the module always gives, and `fixed`
  for an output with option channel `none`. The `Supervisor` has among its
  options the flag `-no-hold-fifos`, a command line option that script
  generation writes and each run sets, although the program model does not hold
  it.
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
repeat: each handle of the wiring on the `Supervisor` is named after its node,
with a small tag after the name that says which channel it is, `heartbeat` or
`trigger`, since both channels of an initiator carry its name. The canvas
draws:

- a heartbeat channel from every node to the `Supervisor`, a single edge for an
  `array` or `generator` process, drawn as a fanout edge, since the
  `Supervisor` reads its heartbeat channels as a fanout family;
- a trigger port from the `Supervisor` to every initiator, a fanout edge too
  for an initiator of that kind, whose handles, on the initiator and on the
  `Supervisor`, carry a mark of their own instead of the round handle;
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
drawing applies to a self-loop of a general program (see "From the store to
the canvas").

**The structural key and the legend.** The rule of "Keeping the canvas in step
with the store" holds: whatever a canvas node draws from its process is part
of the structural key, or the canvas node reads it from the store, as it reads
the process status. What a resident program adds follows it this way:

- The structural key gains, for each process, its node kind, whether it is an
  initiator and whether it observes the outside world, which for an
  `FBPProcess` depends on whether its body of `observe` is empty; for each
  option, which of the sorts of "The program model of a resident program" it
  is (a business output, an input that a connection can reach, an external
  input or a configuration option) and, for a configuration option, where its
  value comes from, which decide how its handle is drawn; and whether the
  Supervisor wiring is shown. The last
  belongs to the tab, not to the program, but it adds and removes handles on
  the canvas nodes, which the canvas library takes only when the list of
  canvas nodes is refreshed.
- The mark of a business output read outside the program depends on the
  edges, which change with every connection and are not part of the
  structural key. A canvas node reads it from the store, so that a connection
  does not refresh the list of canvas nodes.

The canvas of a resident program has a legend of its own, which the user folds
as that of a general program (see "From the store to the canvas"). It says
what each process status means in a resident program (see "Observing and
talking to a live program"), and what each mark means: the node kind, an
initiator, a node that observes the outside world, a notice and its level, an
external input, a business output read outside the program, a hollow handle and
its tag, a trigger port, and the edges of the Supervisor wiring.

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
  `shared_dir`, `process_outdir` nor `--mirror` (see "The program model of a
  resident program").
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
- **No change under a live program.** While the program is `live`, the frontend
  refuses to save, to reset the program state and to change the output
  directory, and the backend refuses them too (see "Running a resident
  program").

**Execution and observation**

- **A failed launch is reported at once.** `/run` waits for `debasher_exec`
  and shows what it printed (see "Running a resident program").
- **One live program per output directory.** A launch is refused while there
  is a run in progress.
- **A hard kill is never taken for an orderly stop.** The exit code with which
  `debasher_stop_resident` reports that it fell back to `debasher_stop` is
  shown as such (see "Running a resident program").
- **A relaunch never doubles a task.** "Relaunch node", and "Restart node" in a
  program without a `Supervisor`, relaunch only a task whose PID no longer
  exists, under the relaunch lock (see "Running a resident program").
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

# Business tests in the web UI

A program can carry business tests: tests of what each of its processes does
with the values of its options, run on its own, outside any run (see "Business
tests of a program" in `doc/design_doc_engine.md`). The home directory of a
program of the web UI is a program directory for the engine, whatever its name,
since the program metadata names the generated script, so its tests are user
files under `test/` in the home directory, which the program files panel
shows and edits. The web UI adds two things on top: it runs the tests
of the program and shows their result, and it writes a test skeleton for a
process, so that a test does not start from an empty file. The MCP server
offers both to an agent, together with the management of user files, so that
an agent that writes a process can also write its tests.

## Running the tests

"Run tests", in the Run menu, runs the tests of the program in its home
directory. Like "Validate program", it saves the program first, with its
revision (see "Revisions of the program metadata"), so that the tests run the
program as it is in the editor: a test reads the generated script, never the
program model. The backend (`/run-tests`) then runs
`debasher_test <home directory>` in a session of its own (`tool_sessions.py`),
with the environment of a run of the program (its `DEBASHER_MOD_DIR`, see
"Environment variables of a program"), and waits for it. A program with conda
or docker support in its execution options gets `--conda-support` or
`--docker-support` too, so that the test runner prepares its Conda
environments and Docker images before the tests, as a run would (see "The test
runner: `debasher_test`" in `doc/design_doc_engine.md`). Creating an
environment for the first time counts in the bounded wait below.

"Run tests" is refused while there is a run in progress, by the frontend, which
disables it, and by the backend, with the check of a save (see "The home
directory"). A save is refused during a run, so a test run then could only test
what was saved before, which may not be what the editor shows; and a program
whose run lasts days is better tested once it is stopped than against a script
that the run may not be running.

The tests of a program are meant to be quick, so the backend waits for them
within the request, as it does for a validation, rather than starting them in
the background and following them. The wait is bounded: after
`RUN_TESTS_TIMEOUT_SECS` (ten minutes) the backend kills the process group of
`debasher_test`, which its own session makes it the leader of, so that no test
is left running.

The answer gives an outcome, from the exit status of `debasher_test`, and its
output, the reports of bats and pytest. The output is capped to the same number
of lines as that of a validation, but keeping its last lines, since the summary
of a report comes at its end:

- `passed` (0), every test passed;
- `failed` (1), a test failed, or bats or pytest could not load a test file;
- `noTests` (77), the program has no test files, with a hint that "Add test"
  writes a first one (`add_test`, for an agent);
- `notRun` (2, or any other status), the tests could not be run, for example
  because bats or pytest is missing from the machine of the backend, or the
  home directory is not a program directory that the test runner
  understands. A backend that cannot find `debasher_test` refuses the request
  instead;
- `timedOut`, the wait ran out.

The frontend shows them in the dialog that shows the output of a validation,
with the outcome as its message.

## Adding a test

"Add test", in the context menu of a process, offers to write a test skeleton
for that process into the test directory, and opens it in the program files
panel. It writes nothing on its own: it opens a dialog that names the file it
would write and says what the skeleton is, and the file is written only when the
user confirms. The dialog proposes a name, which the user may change, for
example to keep a second test file for the same process:

- for a process of a general program, `<process>.bats`, a process test;
- for a node whose node kind is `FBPProcess` or `DirectoryWatcher`,
  `test_<process>.py`, a node test, with every dot of a qualified name turned
  into an underscore, since pytest imports a test file as a module and a dot
  would make its name a package path.

A name that the test runner would not run is refused, before anything is
written: `<name>.bats` in a general program, and `test_<name>.py` with a name
that Python can import in a resident one, always in the test directory itself
(`testFileNameProblem`). A test file under any other name would hold a test
that never runs, which is worse than an error. When the named file already
exists, the dialog says so and offers to open it instead, and writes nothing,
so that a test the user wrote is never lost. Once the skeleton is written, the
program files panel shows it, with a line above it that names the file and says
to fill in its `TODO` marks and then remove the line that makes each test
fail.

"Add test" is not offered on a `Supervisor` or a `ProgramLauncher`, which the
node harness does not build (see "Testing a node without the engine" in
`doc/design_doc_resident.md`). It needs a program that has been saved, since
the file goes into its home directory, and it writes the skeleton from the
program as it is in the editor, without saving it.

A test skeleton is written from the options of the process, by a function of
the program model (`frontend/src/models/testSkeleton.ts`), so that the MCP
server writes the same one. Every place that the user has to fill in carries a
comment that starts with `TODO:` and says what goes there, so that a search for
`TODO` finds all of them:

- A process test loads the test helpers and runs the process with
  `debasher_process`, giving each of its options but the flags, in the order of
  the process, one per line: an output option a path under the temporary
  directory of the test, named after its label, and any other input a
  placeholder, `TODO`. A comment above the command lists the description of
  each option, and the flags, which the user adds to the command if the test
  needs them, since a line commented out in the middle of a command split over
  several lines would end it there. The test then checks that the process
  ended with status 0, and leaves a `TODO` where it should check what the
  process wrote.
- A node test builds the node with `load_node`, naming as its inputs the
  business inputs and the external inputs of the node and as its outputs its
  business outputs (see "The program model of a resident program"), and lists
  in a comment the configuration options that `opts` could give. For an
  `FBPProcess`, one test feeds a placeholder packet on the first input and
  checks what the first output sent, and another restarts the node after it;
  a node with a body for `observe` gets a third test, which calls `observe()`
  and checks what it brought in and what the node sent.
- A `DirectoryWatcher` has no input to feed, and cannot be built without the
  directory it watches, so its node test has none of the tests that feed the
  node. It has two instead, which observe: one checks what the node brings in
  when a file arrives in the directory, and one restarts the node and checks
  that it requests no file twice. With the option `-watchdir`, both watch the
  temporary directory of the test and write a placeholder file in it; without
  it, a `TODO` says to write the files in the directory that `WATCH_DIR` names.
  Each observes twice before it checks, since a file is complete only once it
  has stayed the same for two observations in a row by default. So a skeleton
  never fails because the node cannot be built, only on the line that makes it
  fail or on a placeholder.

A skeleton is a starting point, not a test, and it says so by failing: each of
its tests ends with a line that fails on purpose (`false` in bats,
`pytest.fail(...)` in pytest), under a `TODO` that tells the user to remove it
once the checks of the test are written. A placeholder alone could not promise
that, since a process may accept any value and end with status 0, so "Run
tests" never reports a skeleton as a test that passes.

The file is written through the program files of the backend, whose
`/write-content` creates a file that does not exist when the request says
`create`, with the directories above it, keeping the guarantees of the program
files panel (see "Reserved names and user files"); without `create` it writes
only a file that exists. After "Add test", the program files panel reads the
tree again at once, without waiting for its next reading.

## Business tests from the MCP server

The MCP server offers the same operations as MCP tools (see "The MCP tools"):
`run_tests`, with the outcome and the last lines of the output, and `add_test`,
which writes the same test skeleton under the same name, or under the name that
the call gives with the same rules, refuses a file that exists, and answers its
path and content. An agent writes and fixes the tests themselves, and the files
that they read, with the MCP tools for user files, which act on any user file,
not only on tests.

# A prompt for the code of a process

The code editor of a process, the editors of the code of its options handler and
of its additional methods, and the node code editor help the user to have an AI
tool write the code. Each composes a code prompt, a text that asks for the code
and gives what the program model knows of the process or the node, for the user
to copy into an AI tool of their choice. The code comes back the way any code
reaches the editor: the user copies it from the answer of the AI tool and pastes
it into the code editor. The web UI calls no AI service and keeps no key:
nothing leaves the machine through it, and the user sees the whole code prompt
before sending it anywhere.

The code prompt is offered for the code of a process of a general program, for
the code of the options handler of a process or a node in `array` or `generator`
mode (see "The code prompt of an options handler"), for the additional methods
of a process of a general program (see "The code prompt of an additional
method"), and for the code of a node of a resident program other than the
`Supervisor`, whose code has parts and a contract of its own (see "The code
prompt of a node"). It is not offered for a sequential process, which has no
options to describe, nor, yet, for the option definition function of a `manual`
process or for the preamble (see "Future work").

## What the code prompt says

A code prompt gives an AI tool what a person would need to write the code
without seeing the editor. After a title that names the process and a sentence
on what DeBasher is, it goes from the general to the particular, each part
under a heading of its own:

1. **The language rules.** How the engine runs the code of a process of the
   language of the process. A Bash process is a function named after the
   process, which the engine calls with the option list as its arguments, and
   which reads an option with `read_opt_value_from_func_args` and a flag with
   `read_flag_from_func_args`. The code of any other language is a whole
   program, which the interpreter of the language (`python3 -c`, `perl -e`,
   `Rscript -e`, `groovy -e`) runs with the option list as its command line
   arguments; script generation writes it inside a Bash here-document, so it
   may hold no line that is `EOF` alone. In the option list, each option is
   its label followed by its value, and a flag its label alone. Then what
   holds for every language: the value of an output option names where the
   process writes what it produces (a file, a directory or a FIFO), and what
   it prints to its standard output goes to a file of the task that no other
   process reads; a FIFO is read until its end, and an output FIFO is closed
   once everything is written, since only then does its reader see the end;
   the processes at the two ends of a FIFO run at the same time; and the
   process ends with status 0 when it succeeds, and with another status when
   it fails.
2. **The program.** Its name and its description.
3. **The process.** Its name, its description and its language, and, in any
   options handler mode but `standard`, that the code runs once for each task,
   with the option list of that task.
4. **The options.** For each option of the process, in its order: its label, its
   direction and data type, or that it is a flag, its description, whether it is
   mandatory, a command line option or a task shaping option (which the code
   cannot read, since no task receives it), and its literal value if it has one,
   or where its value comes from: the specifications of the process, a shared
   directory or the process output directory, with its subpath. An option
   channel other than `none` says what it means for the code: a FIFO is closed
   once written or read until its end, a value descriptor is written as the
   language rules say, and a task subdirectory, or the process output directory
   of a process in `standard` mode, exists and is empty when the code starts,
   unless the process has a `_reset_outfiles` method, which the prompt then
   says, so the code may write files of fixed names into it; the process output
   directory of a process in `array` or `generator` mode, without a subpath, is
   shared by its tasks and not emptied, which the prompt says too. A connected
   input names the process and the output option it reads from, with their
   descriptions, and says what the output is: a FIFO, read as it arrives, a
   value descriptor, or else a file whose writer has finished before the process
   runs; a connected output names, likewise, the options that read it; an
   unconnected FIFO says that someone outside the program is at its other end.
   An option of a fanout family names the option that gives its count. A value
   descriptor is written, in Bash, with `write_value_to_desc`, and read with
   `read_opt_value_from_func_args`, which gives the value and not the path; in
   another language it is written into the file that the option names, and its
   reader gets the path of that file.
5. **The code to complete.** The draft of the code editor, which starts as the
   template while the code is still one, or the template when the user has
   emptied the draft, in a fenced code block tagged with the language and longer
   than any run of backquotes in the code. The template already reads every
   option that a task receives, so the code prompt asks to keep those lines and
   to write the code where the template marker is; without the marker, it asks
   to change the code as the code request says and to keep the rest.
6. **The code request.** What the user wrote in the prompt panel, or, when it
   is blank, to write the code that the description of the process asks for.
7. **What the AI tool returns.** The whole code (for a Bash process, including
   the line that names its function) in a single fenced code block tagged with
   the language, with nothing else inside the block. The user copies the code
   from the answer and pastes it over the draft, so the answer has to hold all
   of it in one piece: a single block, which the copy button that AI tools
   commonly give each block copies whole; the whole code, not only what changed,
   since what the answer leaves out would be lost; and, in Bash, the line that
   names the function, without which the module would define no function for the
   process.

   Before the form of the code, the code prompt asks the AI tool to ask rather
   than guess: when something that the code depends on is missing or
   ambiguous, such as the format of an input, it puts all its questions at
   once before writing any code, and the user answers them in the AI tool.
   The program model describes the processes and their connections, never
   what the data hold, so an AI tool that had to answer with code at once
   would make up what it does not know. Whether it asks first or not, what
   reaches the code editor is only the code.

The code prompt is in English, whatever the language of the code request,
like the rest of the web UI. It leaves out what does not change the code: the
position of the process, the values of its specifications, its additional
methods and the code of its options handler.

## Building the code prompt

A code prompt is built by a function of the program model, `buildCodePrompt`
(`frontend/src/models/codePrompt.ts`), from the program in the store, the
process, the draft of the code editor and the code request. It depends on
nothing outside the program model, so that a test builds a code prompt without
the editor, and the MCP server offers the same one (see "The code prompt from
the MCP server"). For that reason the templates live in the program model
(`frontend/src/models/codeTemplates.ts`), and the code editor imports them from
there.

The function is pure: the same program, process, draft and code request give
the same code prompt, and the tests compare it with what they expect. The
language rules live in the same module as the templates, so that a change to
how a template reads the options, or to how the engine runs the code of a
language, is made in one place. A test checks, for each language, that the
code prompt carries the language rules of that language and the template of
the process.

The code prompt is built from the draft and from the program in the store, not
from the program saved on disk, so that what the user has edited and not saved,
in the editor or elsewhere in the program, is what it describes.

## The prompt panel

The header of the code editor of a process carries a button with a sparkle
icon, the mark that applications commonly give to what involves AI, and the
tooltip "Prompt for an AI tool". It opens the prompt panel inside the code
editor, beside the code, which stays editable. The prompt panel holds:

- A field for the code request, empty when the code editor opens and kept
  while it stays open.
- The code prompt, read only, composed again whenever the code request or the
  draft changes. The user changes it through the code request, or in the AI
  tool once it is copied.
- "Copy", which puts the code prompt on the clipboard. When the browser does
  not offer the clipboard, as on a page served over plain HTTP from another
  machine, or refuses it, the panel selects the whole code prompt and says to
  copy it with the keyboard.

The prompt panel takes nothing back. The user copies the code from the answer
of the AI tool and pastes it into the code editor, over the draft, as any code
is pasted: the code prompt asks for an answer that this copy brings whole (see
"What the code prompt says"). Pasting changes the draft and nothing else.
"Save" in the code editor hands the draft to the store, and "Cancel" drops it,
with the code that the draft held before. Code saved without the template
marker is no longer a template, so a later change of the options does not
write the template over it, as for code written by hand. The web UI does
not check the code that an AI tool writes: validating the program and running
its tests do (see "Running the tests").

## The code prompt of a node

The node code editor offers the same prompt panel, with the same button, for
every node kind but the `Supervisor`, for which script generation writes all the
code (see "The program model of a resident program"). The code prompt of a node
follows that of a process, with three differences that come from the code of a
node: it is made of parts, it keeps a contract with the runtime library, and it
may inherit hooks from its class. After a title and a sentence on what a
resident program is, it says:

1. **How the code is put together.** The class of the node, named after its
   process, the node kind it derives from, and the order in which script
   generation assembles the parts (see "Script generation and import of a
   resident program"); that each part is written without the indentation of
   the class, and a hook without its `def` line, under its fixed signature;
   that the constructor calls `super().__init__()` and gives the node state
   its first value; that the class never declares the ports; and, for an
   `FBPProcess`, which hooks it has to give, or, for a `ProgramLauncher` or a
   `DirectoryWatcher`, that an empty body runs the hook of its class and a
   body replaces it.
2. **The runtime library.** The node reference of its node kind.
3. **The program**, its name and description, and **the node**: its name, its
   class, its node kind, its description, and whether it runs as several
   tasks.
4. **The ports and options.** Each option of the node by its sort (see "The
   program model of a resident program"), with its description. A business
   input names the port under which what arrives reaches `process_data` and
   the option of the node that sends it; a business output, the call that
   sends on it and the options that read it, or that someone outside the
   program reads it, and, for a fanout family, its ports and the option that
   gives their count; an external input, that someone outside the program
   writes it; and a configuration option, the entry of `self.opts` that gives
   its value and, for a flag, that its name goes into the class attribute
   `FLAGS`. An input that no connection reaches yet is described as a
   configuration option, which it is until one does.
5. **The code to complete.** Every part, under its name: its code, or that it
   is empty (and, for a hook that an `FBPProcess` has to give, required), and,
   for a hook that the node inherits, the inherited code, which an empty body
   runs and a body replaces, or that it could not be read.
6. **The code request**, as for a process.
7. **What the AI tool returns.** Each part that changes, whole, in a fenced code
   block tagged `python`, under a heading with the name of the part, the one
   that the node code editor gives it; a part that the answer leaves out stays
   as it is. One code prompt serves both a new node, whose constructor,
   `process_data`, `capture_node_state` and `restore_node_state` have to agree
   on the node state, and a change to one hook, and the user pastes each block
   into its part. As for a process, the code prompt first asks the AI tool to
   ask rather than guess.

**The node reference.** The contract that the code of a node keeps (a
deterministic `process_data`, sending only from it, a complete
`capture_node_state` and an exact `restore_node_state`) belongs to the runtime
library, whose documentation states it. The code prompt does not restate it:
it carries the node reference, which the backend reads from the library itself
(`/node-reference`, `api/node_reference.py`), the installed copy first, as it
reads the inherited hooks (see "The program model of a resident program"). The
node reference holds, for each class from `FBPProcess` down to the class of the
node kind, its documentation, the signature and documentation of each hook and
method that the code of a node uses, and each class attribute with its value
and the documentation that its `#:` comments give. The names are those that
the page of the documentation on the classes of the nodes lists
(`rtdocs/source/api_resident_nodes.rst`), but for `run`, which script
generation calls, and the `Supervisor`, and a test keeps the two in step. What
the library says of each name reaches the code prompt without a change to the
web UI; a name that it no longer defines or documents makes the whole node
reference unreadable. When the node reference cannot be read, the code prompt
says so and keeps the rest.

The node code editor reads the node reference when the prompt panel first
opens. `buildNodeCodePrompt` (`frontend/src/models/nodeCodePrompt.ts`) builds
the code prompt from the program in the store, the node, the draft of every
part, the code request, and what was read from the library, and is pure like
`buildCodePrompt`; the code editors show it with the same prompt panel
(`frontend/src/components/CodePromptPanel.tsx`), and the node code editor
names the parts as `NODE_CODE_PARTS` in `frontend/src/models/node.ts` does.

## The code prompt of an options handler

The editors of the code of the options handler of a process, in `array` and
`generator` mode, offer the same prompt panel, with the same button, in a
general program and for a node of a resident program alike. The code that the
user writes there decides what a task of the process is (an element of the
array, or an index up to the number that the code prints), which the program
model holds nowhere but in the descriptions and in the values of the options, so
the code prompt brings both, and the code of the process, which says how a task
uses its options. After a title and a sentence on what a task is, it says:

1. **How the engine runs the code.** For `array`, that the code is written into
   the `_define_opts` method of the process, has to build a Bash array named
   `array`, one element for each task, and is followed by the loop that defines
   the options of each task, whose values can use `${array[$task_idx]}`,
   `${task_idx}` and any variable that the code sets; and that `debasher_exec`
   runs it each time it prepares a run. For `generator`, that the code is
   written into the `_generate_opts_size` method, has to print the number of
   tasks and nothing else, and does not share its variables with the function
   that defines the options of a task (whose values can use `${task_idx}`),
   since `debasher_exec` runs it in a subshell, once each time it prepares a run
   (see "Arrays and option generators" in `doc/design_doc_engine.md`). For both,
   the lines that script generation writes before the code (`cmdline`,
   `process_spec`, `process_name` and `process_outdir`), how to read a command
   line option with `get_cmdline_opt`, and that the code runs while
   `debasher_exec` prepares the run, before any process of the program. So it
   never opens a FIFO, of a general or a resident program: nothing writes it
   yet, and opening it for reading blocks until something does, which would
   leave `debasher_exec` waiting, and whatever it read would be taken from the
   reader of the FIFO. Nor does it read what a process of the program produces,
   which a first run does not find and a later run finds as an earlier run left
   it. It may read what exists before the run, such as a file or a directory
   given on the command line; the number of tasks typically comes from a command
   line option. And that a process with as many tasks as another one takes that
   number with `get_process_num_tasks` instead of computing it again, which
   would repeat the rule by which the other process counts its tasks (for
   `array`, only from a process in `generator` mode, see "Arrays and option
   generators" in `doc/design_doc_engine.md`). The prompt then names, with their
   modes, the processes that this process reads task by task and can ask, the
   usual candidates; a connection between `shared_dir` options pairs no tasks
   and is left out.
2. **The program** and **the process**, with its options handler mode.
3. **The options**, as in the code prompt of a process: their values show
   what a task needs, such as an input option whose value is
   `${array[$task_idx]}`.
4. **The code of the process**, for context only; or, since the options handler
   is often set before the code is written, that the code is not written yet
   while it is still a template (for a node, while no part has code); or that
   the process takes its code from an alias or an external alias. For a node of
   a resident program, whose options handler may be `array` or `generator` too,
   the parts of the node that have code, under their names, each task being a
   node of its own.
5. **The code to complete**, or that it is empty, which the first code of
   the editor of a generator (a comment that asks for the number of tasks)
   counts as.
6. **The code request**, or, when it is blank, to build the array, or print
   the number of tasks, that the description and the values of the options
   call for.
7. **What the AI tool returns.** After the rule to ask rather than guess,
   which matters most here, since what a task is (which files, from which
   directory, where the count comes from) is seldom written anywhere: the
   whole code in a single fenced code block tagged `bash`, without the lines
   that script generation writes before it.

`buildOptionsHandlerPrompt` (`frontend/src/models/optionsHandlerPrompt.ts`)
builds it, pure like `buildCodePrompt`, whose description of the options it
reuses. The option definition function of a `manual` process has no code
prompt (see "Future work").

## The code prompt of an additional method

The editor of each additional method of a process (`reset_outfiles`, `post`,
`outdir_basename`, `skip`, `conda_envs` and `docker_imgs`) offers the same
prompt panel, with the same button. An additional method is a Bash function,
whatever the language of the process, which script generation writes as
`<process>_<method>()` around the body that the user gives, and which the
engine calls at a moment of its own, with arguments of its own, and expects
something of: `skip` skips the task when it returns success, `post` runs
whether the process function succeeded or failed, `outdir_basename` prints a
name and nothing else, and `conda_envs` and `docker_imgs` run once for the
process and only make sure that an environment or an image exists. The code
prompt says so, after a title and a sentence on what a method is:

1. **How the engine runs the method.** That it is a Bash function whose body
   alone is written, and the rules of the method: when the engine calls it, with
   which arguments (the options of the task for `reset_outfiles`, `post` and
   `skip`, none for the others), what it has to return or print, and what
   follows from it, such as that a process at either end of a FIFO must not be
   skipped, since the process at the other end would wait forever for it to open
   the FIFO.
2. **The program** and **the process**, with whether it runs as several
   tasks.
3. **The options.** For a method that receives them, as in the code prompt of
   a process; for one that does not, the same list, introduced as what the
   code of the process reads, which still shows what the method works on.
4. **The code of the process**, for context, as in the code prompt of an
   options handler: a method acts on what the process does, such as the file
   that `reset_outfiles` removes or the environment that `conda_envs` declares
   and the process activates.
5. **The code to complete**, or that it is empty.
6. **The code request**, or, when it is blank, to write the method that the
   description and the code of the process call for.
7. **What the AI tool returns.** After the rule to ask rather than guess, the
   whole body in a single fenced code block tagged `bash`, without the line
   that names the function and the braces around the body.

The rules of each method are those of the engine (see "Processes and their
methods", "Executing a task", "When one end fails" and "Conda and Docker
environments" in `doc/design_doc_engine.md`). Unlike the node reference, which
the backend reads from the runtime library, they cannot be read at run time, so
they are kept once, in `PROCESS_METHODS`
(`frontend/src/models/processMethods.ts`), together with the summary that the
editor of the method shows, so that the editor and the code prompt never tell
two stories. `buildMethodPrompt` (`frontend/src/models/methodPrompt.ts`) builds
the code prompt, pure like `buildCodePrompt`, with the parts that it shares with
the code prompts of a process and of an options handler.

## The code prompt from the MCP server

The MCP tool `get_code_prompt` answers with the code prompt that the button of
the editor composes, for the code of a process or of a node, for the code of its
options handler, or for one of its additional methods, as the call names them.
It builds it with the same functions, from the program as it is saved, with the
code saved for that piece as the draft and the code request of the call; for a
node, it reads the node reference and the inherited hooks from the backend, as
the node code editor does, and says in the code prompt what it could not read.
It refuses what the editor does not offer: the code of a `Supervisor`, the
options handler of a process in a mode other than `array` or `generator`, and an
additional method of a node. An agent follows the code prompt to write that
code, which it then saves with the MCP tools that edit a program, or hands it to
another model; an assistant in the web UI would compose it the same way.

# Editing a program from an agent: the MCP server

The MCP server offers to an agent, such as Claude Code, what the editor offers
to a person: reading a program, editing it, running it and following its run, as
MCP tools. It is a second client of the backend, beside the frontend, and a
first move towards an assistant in the web UI that helps to design and build a
program, which would call the same MCP tools (see "Future work"). It relies on
what the editor relies on too: the distinct option labels (see "Processes and
options"), the guards of the backend against a run in progress (see "The home
directory"), the revisions of the program metadata (see "Revisions of the
program metadata"), the resolution of named edits (see "Programs, processes
and options by name") and the placement of processes (see "From the store to
the canvas").

The design follows from one rule: the MCP server edits a program with the
same code as the editor. The edits, their validation, the rule of which groups
they touch and the normalization live in `frontend/src/models/` and depend on
nothing outside the program model (see "Screens and the store"), so the MCP
server is written in TypeScript and imports them, rather than repeating them
in another language. It sends its requests with the frontend's own clients of
the backend (`frontend/src/api/` and `frontend/src/storage/`) for the same
reason.

## Architecture of the MCP server

The MCP server is a Node.js program that speaks the Model Context Protocol over
its standard input and output, so the agent starts it and talks to it as a
child process. It keeps no state between two calls, like the backend: every
MCP tool reads the program from its home directory, acts, and writes it back.

It reaches the backend over HTTP, at a URL given on its command line (by
default the one where `debasher_webui` listens), and uses the endpoints that
the frontend uses: `programs` to load, save and import a program, `processes`
to look up the processes that the modules of the preamble define, and
`execution` to run, observe and stop it. The frontend's clients name an
endpoint by a path relative to the page that serves them, and under Node.js
there is no page: the MCP server resolves every relative URL against the URL
of the backend before it sends the request (`frontend/mcp/src/backend.ts`).
The backend has to be running; the MCP server starts nothing, and a call that
cannot reach the backend says so. It sends the token of the backend, which it
reads from the token file (see "The token file"). It widens nothing either: the
backend already runs the engine's tools, as the user who started it, for
whoever holds the token, and the MCP server is reached only by the agent that
started it.

The code is in `frontend/mcp/src/`: `backend.ts` gathers the clients of the
backend into one object, which the tests replace with a fake one;
`editing.ts` holds the steps of an edit (see "Edits from an agent");
`describe.ts` the text that shows a program; `schemas.ts` the parameters of
the MCP tools; `tools.ts` the MCP tools themselves; and `server.ts` and
`main.ts` register them with the MCP library and read the command line.

## Programs, processes and options by name

An agent names what it acts on as a person would, never by an internal id. A
program is named by its home directory, a process by its name, an option by
its process and its label, and an edge by its two ends, each a process and a
label. Names of processes are unique in a program (sequential processes
included), and the labels of the options of a process are distinct (see
"Processes and options"), so a process name, and a process name with a label,
are enough. A program that still holds repeated labels is refused by an MCP
tool that names one of them, until the user relabels them.

A **named edit** is an edit written with names: `{op: "connect", from: {process:
"a", option: "-outf"}, to: {process: "b", option: "-in"}}`. `resolveNamedEdits`
(`models/programRefs.ts`) resolves a list of named edits into edits, giving new
ids to what they add. It resolves each named edit against the program that the
edits before it leave, so that a named edit may name a process or an option that
an earlier one added, and it stops at the first name that matches nothing, or at
a label that two options of a process share, saying which named edit it is.
Beyond the edits, a named edit adds, changes or removes one sequential process
by its name, which resolves into one edit that replaces the whole list of
sequential processes; names the option that gives the count of a fanout family
by its label; and, when it changes the label of an option, also gives the option
the direction that follows from the new label, as the editor of an option does.
Of a field that holds an object, such as the computational specifications of a
process, the code of a node or the execution options of the program, a named
edit gives only the fields that it changes, and the others keep their values;
a map, such as the program options, is given whole. A named edit that adds a
process may carry what the library brings for it, as the dialog that names a
new process does. Resolving only resolves names: whether the edits are allowed
is for `validateEdits`. The answers of the MCP tools name things the same way
and show no ids.

## Edits from an agent

Every MCP tool that edits a program applies its edits whole or not at all,
with the actions that the store takes, and an answer in place of the dialogs
(`editProgram` in `frontend/mcp/src/editing.ts`):

1. Load the program from its home directory, with its revision (see
   "Revisions of the program metadata"), and normalize it as the store does.
2. Bring what the library has for each process that the named edits add, as
   the dialog that names a new process does: in a general program, a process
   that a module of the preamble defines comes with its description, options
   and code; in a resident program, a node that a module defines comes with
   what that module brings, and any other name needs the node kind of the new
   node, or the call is refused. Then ask the backend whether the engine
   accepts each name that the named edits give to a process or a sequential
   process, and refuse the call at the first it does not.
3. Resolve the named edits into edits.
4. Check them with `validateEdits`; a problem ends the call with the list of
   problems, and nothing is written.
5. Find the groups that they touch with `groupsTouchedBy`. Where the store
   asks the user, the MCP tool refuses, naming the program each group came
   from, unless the call says `detach_groups`, in which case the groups are
   dissolved with the edits, as when the user agrees.
6. Apply them with `applyEdits`, which normalizes the result.
7. Save the program, naming the revision it was loaded with. A save refused
   for its revision ends the call with the message of the backend's conflict,
   and the agent loads the program again (see "Revisions of the program
   metadata").

An MCP tool called with `dry_run` stops before the save and answers with a
**proposal**: the lines that the edits would add to the program and remove
from it, each a line that says on its own what it belongs to (a process, an
option of a process, a line of the code of a process, a connection), the groups
they would dissolve, and, as structured content beside the text, the edits
themselves, already resolved. An assistant in the web UI would show a
proposal on the canvas and let the frontend apply it with `applyEdits` if the
user accepts it, which needs no other code. A saved edit answers with the
revision it wrote and the same lines.

A process added by an agent has no position chosen by hand. The MCP server
places it with `nextFreePosition`, each process that a call adds after the ones
before it, and a program that it imports with `layoutProcesses`, so that the
canvas shows every process apart (see "From the store to the canvas"); an agent
can move a process afterwards, or lay out the whole program again in layers.

## The MCP tools

The MCP tools are grouped by what they do. Each answers with short text meant
for a model to read, not with the program model as JSON: a program is shown as
its processes with their options and their connections, one per line (a label
edge marked as such), and the output of a process is cut to its last lines
unless the call asks for more. A call that is refused, or that the backend
fails, answers with the reason as an error.

- **Reading.** `get_program` (the settings of the program, its processes, its
  sequential processes and its connections), `get_process` (one process or
  sequential process in full, its code included), `get_code_prompt` (the code
  prompt of a piece of code of a process, see "The code prompt from the MCP
  server") and `import_module` (import a module, place its processes and derive
  its connection sentinels as the store does on load, and save it into a new
  home directory).
- **The library.** `search_library` and `get_library_process`, which list and
  describe the processes, or in a resident program the nodes, that the modules
  of the preamble define, through the `processes` endpoints.
- **Editing.** `create_program`, which, like `import_module`, refuses a
  directory that already holds program metadata, since a save of a program not
  loaded from a directory replaces what is there (see "Revisions of the program
  metadata"); `add_process`, `update_process`, `remove_process` and
  `move_process` (which, with `layout`, lays out every process again in
  layers); `add_option`, `update_option` and `remove_option`; `connect`
  (which may make a label edge, see "Label edges"), `disconnect` and
  `set_connection_display`, which switches a connection between a line and a
  label edge; `set_program_settings` (name, description, preamble,
  environment variables, output directory, execution options, program options
  and shared directories); `set_seq_processes`, each of whose entries adds the
  sequential process it names, or changes or removes it if it exists; and
  `apply_edits`, which takes a list of named edits and applies them whole or
  not at all. Each takes `dry_run` and `detach_groups`. "Add program" is not
  offered.
- **Running.** `validate_program` (validating the program and checking its
  options, as the Run menu does), `run_program`, `stop_program` (an orderly
  stop, or a hard kill), `get_status` (the run phase and the process statuses,
  and for a resident program the notices of its nodes), `get_process_output`
  (the standard output, the scheduler output, the options or the resolved
  options of a process, or of one of its tasks) and `get_process_tasks`. The
  launch of a general program runs in the background, and the first readings
  of the process statuses after it may still show the run before, so
  `run_program` answers once they show a process in progress, or statuses
  other than those before the launch, or after a few seconds. A resident
  program whose output directory holds program state that this program did
  not produce, or that no launch record describes, is launched only when the
  call says `resume_changed_program`, as the Run menu asks; the answer of the
  refusal says so, and that `reset_program_state` starts afresh instead.
  `reset_output_dir` deletes what a run left, `reset_program_state` sets the
  program state aside or deletes it, and a hard kill loses what the FIFOs
  held, so they are refused unless the call says `confirm`.
- **Resident programs.** `inspect_node` (the summary of a node, a checkpoint,
  its input log, or the batch runs of a launcher node), `snapshot`,
  `restart_node` (refused unless the call says `confirm`, with the warning
  that "Restart node" asks the user to confirm) and `relaunch_node`, offered
  on the nodes on which the canvas offers them; and `list_fifos`, `write_fifo`
  and `read_fifo`, which talk to the FIFOs that "Talk to FIFOs" offers, with
  its rules (see "Observing and talking to a live program").
- **Business tests.** `run_tests` and `add_test` (see "Business tests from the
  MCP server").
- **User files.** `list_program_files`, `read_program_file`,
  `write_program_file`, `delete_program_file` and `move_program_file`, which
  manage the user files of the home directory as the program files panel does
  (see "Reserved names and user files"), through the endpoints of the backend
  that the panel uses. `write_program_file` creates or replaces a file, with the
  directories above it (`/write-content` with `create`, see "Adding a test");
  `move_program_file` creates the directories above the new path and never
  replaces what is there; `delete_program_file` deletes a file, or a directory
  with everything in it, which cannot be undone, so it is refused unless the
  call says `confirm`, and the refusal says what would be deleted. The backend
  refuses, for the MCP server as for the panel, a reserved name, a path that
  leaves the home directory and the generated script.

The MCP tools keep the guards of the editor through the backend, not by
repeating them: the backend refuses a second run on an output directory, the two
directories of a program in one, and a save, a reset of the output directory or
a change of it while there is a run in progress.

## Building, installing and testing

The MCP server lives in `frontend/mcp/` and imports `frontend/src/models/`. The
build of the frontend (`npm run build`, which `make` runs) bundles it too, with
the models it uses and the MCP library, into a single JavaScript module,
`frontend/mcp/dist/debasher_mcp.mjs` (`frontend/mcp/vite.config.ts`), as it
bundles the frontend into a single `index.html`. `make install` installs that
module in the `mcp` directory of the package data, beside `web`, with a
`debasher_mcp` launcher among the installed commands (`bindir`), and
`make dist-vendored` vendors it with the built frontend. Node.js, which the
frontend needs only to be built, is then needed to run the MCP server too:
the launcher runs the module under the node named by `DEBASHER_MCP_NODE`, or
else the one that configure found, or else the one in the `PATH`. An agent
registers it with the URL of the backend, for example
`claude mcp add debasher -- debasher_mcp --url http://127.0.0.1:8000`.

The tests need no backend: the resolution of named edits is tested with the
model (`frontend/src/models/programRefs.test.ts`), and each MCP tool, and the
server over the protocol, under Node.js against a fake client of the backend
that keeps the program metadata in memory with the revision check of the backend
(`frontend/mcp/src/tools.test.ts`); the revision check itself is tested in the
backend's own tests.

# Claude Code on a program

`debasher_claude` starts Claude Code on one program, with what DeBasher gives
it: the MCP server, the permissions of its MCP tools, and the plugin of
DeBasher.
The user runs it in a terminal of their own, with the home directory of the
program and the URL of the backend, and Claude Code edits the program through
the MCP tools while the editor of the web UI follows what it saves (see
"Revisions of the program metadata"). It uses the user's own installation and
account of Claude Code: the web UI calls no AI service, and holds no key of one.

The web UI gives the command: "Claude Code" in the Help menu shows
`debasher_claude` with the home directory of the program and the URL of the
backend, for the user to copy (`components/ClaudeCodeDialog.tsx`, which builds
it with `models/claudeCommand.ts`). The URL is the one that the backend gives:
the address and the port that `debasher_webui` listens on, as seen from the
machine where it runs (the local machine when it listens on every address),
which is where the command runs too, whatever address the browser reached it by
(a tunnel, the port of a container). A backend that uvicorn started by hand does
not know its port and gives none; the URL is then the origin of the page, which
the backend serves (under the dev server, which forwards `/api` to the backend,
that origin reaches the API as well). The user can change the URL in the dialog.
The command holds no token: the MCP server reads it from the token file (see
"The token file"). The home directory and the URL are quoted for a POSIX shell
when they hold anything that the shell would read otherwise. The command gives
no session mode (no `--mode`): the skills are listed for the user to know them,
and Claude Code calls one on its own when the work asks for it. A program that
was never saved gets no command, since the MCP tools work on the program as
saved, and one with unsaved changes gets a note that says so.

The dialog asks the backend, when it opens, how it offers Claude Code
(`GET /api/webui/info`, `routers/webui.py`), and shows only its title and
"Close" until the backend answers. The backend answers from its environment:

- `DEBASHER_WEBUI_CLAUDE_CODE` set to `no`: it does not offer Claude Code, and
  the dialog gives no command and says why: the directories of the backend are
  not those of the machine where `debasher_claude` would run, so neither the
  launcher nor the MCP tools would find the program by its home directory;
- `DEBASHER_WEBUI_CLAUDE_CODE_PREFIX`: the command that `debasher_claude` is
  run through, to run it where the backend runs, as the `docker compose exec`
  of the Docker image (see "Claude Code in the Docker image");
- `DEBASHER_WEBUI_CLAUDE_CODE_INSTALL`: the command that installs Claude Code
  there, which the dialog says to run the first time;
- the URL of the command (see above), from the address and the port that
  `api/serve.py` puts in the environment of the backend.

A backend that does not answer is taken to offer the command as it is, with the
origin of the page as the URL, since a command that does not work there harms
nothing. The tests of the backend check the answer for each value of the
variables (`test/api/test_webui_info.py`), and those of the Help menu what the
dialog shows for each answer (`components/HelpMenu.test.tsx`).

## The launcher

```
debasher_claude --home-dir <dir> [--url <url>] [--mode <mode>] [--prompt <text>]
```

The launcher of Claude Code checks that a program is saved in the home
directory, and starts Claude Code there with:

- the MCP server, as a server named `debasher` that runs the installed
  `debasher_mcp` with the URL given (`--mcp-config`, as a JSON string, since the
  URL is only known when the session starts). A server of the same name that
  the user registered with Claude Code gives way to it for the session, and
  the user's other servers stay;
- the permissions of the MCP tools (`--settings`, see "The permissions of the
  MCP tools");
- the plugin of DeBasher, from the package data (`--plugin-dir`), whose files
  Claude Code is allowed to read, and only to read, without asking
  (`--allowedTools` with a rule on Read, on the real path of the plugin, since
  Claude Code compares the paths it reads without symbolic links), for the
  skills to read its reference;
- a line added to the system prompt that names the home directory, which the
  MCP tools take as `home_dir`, and the backend, and says that the editor of the
  web UI may have the program open;
- a first message: the skill of the session mode given, if any
  (`/debasher:<mode>`), which takes the prompt given as its arguments, or else
  the prompt alone. Claude Code takes a single first message; it goes after
  `--`, so that an option of Claude Code that takes several values never takes
  it as one of them. Every skill can be called later in the same session, so a
  session moves from one kind of work to another without losing what it holds.

What follows `--` is passed to Claude Code as it is, `DEBASHER_CLAUDE_CMD`
names the command of Claude Code, and `--dry-run` prints the command instead of
running it.

## The permissions of the MCP tools

The permissions come from the MCP server itself (`debasher_mcp
--claude-settings`, `frontend/mcp/src/claudeSettings.ts`), from what each MCP
tool says it does (its annotations), so that an MCP tool added to the server is
ruled with no other change:

- an MCP tool that only reads, changing nothing and running no code of the
  program, is allowed without asking; validating the program and running its
  tests save it and run its code, so they are not among them;
- an MCP tool that deletes or stops something (resetting the output directory or
  the program state, deleting a user file, stopping a program, restarting a
  node) asks every time: an "ask" rule wins over an "allow" one, so it asks even
  once the user chose to always allow it;
- any other MCP tool, which edits the program or runs it, is left to Claude
  Code, which asks until the user allows it;
- the tools of Claude Code that edit files are denied the program metadata
  (`Edit(**/.debasher/**)`, a rule that Claude Code applies to each of them),
  which changes only through the MCP tools, keeping the rules of the editor
  and the revision. A command of Bash is not covered by the rule, but Claude
  Code asks before running one. Nothing denies editing the generated script,
  which the next save writes again; the reference of the plugin tells Claude
  Code to change the code of a process with `update_process` instead.

## The plugin of DeBasher

The plugin of DeBasher (`frontend/claude/plugin`, installed in the
`claude/plugin` directory of the package data) holds four skills and the
reference they share, `reference/concepts.md`: a summary of DeBasher for an
agent that works through the MCP tools (programs, processes and their code,
options, connections, resident programs, business tests, running), which a
skill reads at its start, through `${CLAUDE_PLUGIN_ROOT}`, which Claude Code
replaces with the directory of the plugin. Each skill says what it is for in
its description, which Claude Code reads to call it unasked, and how to work:

- `help` answers questions on the web UI and on DeBasher, looking at the
  program with the tools that only read, and changes nothing;
- `design` asks what the program has to do, proposes its processes, options
  and connections (a file or a FIFO, and why), and builds them, once the user
  agrees, with `apply_edits`, laid out on the canvas and validated; it writes
  no code;
- `implement` writes the code of one process at a time from its code prompt
  (`get_code_prompt`), fills in a business test from the skeleton of `add_test`,
  and runs the tests until they pass; it runs the program only when the user
  agrees. It also adds tests to code that is already written, and leaves that
  code as it is: a wrong test is fixed, and a test that fails because the code
  is wrong is reported to the user, who decides whether the code changes. A test
  checks every output, the edges of the input and a failure, not only that the
  process ended;
- `review` reads the code of the processes, their code prompts and their
  tests, and reports findings ranked by how much they matter (what the code
  does against its description, the options it reads and writes, how it
  fails, FIFOs, tasks, the rules of a node, and whether its tests check
  anything); it changes nothing, and runs neither the tests nor the program
  unasked.

A skill leaves to another what is not its own, and says so to the user.

## Claude Code in the Docker image

In the Docker image of the web UI (`Dockerfile`, see `DOCKER.md`), Claude Code
runs inside the container, next to the backend, not on the user's computer.
There, the home directory of a program is the path that the backend saved it
under, and `debasher_mcp` finds the token file of the backend, so neither the
paths nor the token have to cross the boundary of the container. Claude Code
also sees only the container and what is mounted into it, never the rest of
the user's computer.

The image installs `debasher_mcp`, `debasher_claude` and the plugin of DeBasher
with the rest of DeBasher: the stage that builds the frontend builds the MCP
server too, and the stage that builds DeBasher takes both in, as a release
tarball made with `make dist-vendored` carries them, and so needs no npm. It
runs the MCP server with the Node.js of the stage that builds it, the one it is
built for. Claude Code itself is not in the image: each user has an account of
their own, it updates itself, and not every user of the image wants it.
`install-claude-code` (`docker-install-claude-code.sh`) runs its official
installer once, which puts it under `~/.local` of the `debasher` user, first in
the `PATH` of the image; that home directory is a volume, which keeps Claude
Code, and the login it asks for on its first start, across restarts and rebuilds
of the image.

The image sets `DEBASHER_WEBUI_CLAUDE_CODE_PREFIX` to
`docker compose exec -it debasher`, which the user runs in a terminal of the
computer, in the directory of `docker-compose.yml`, and
`DEBASHER_WEBUI_CLAUDE_CODE_INSTALL` to the same with `install-claude-code`. The
prefix names the service of `docker-compose.yml`; without compose, the user runs
the command through `docker exec -it` and the name of the container instead.
The backend listens on every address of the container, so the URL of the
command names the local machine, from inside the container, with the port of
the container, whatever port the host maps to it.

## Building and testing debasher_claude

`debasher_claude` is built from `frontend/claude/debasher_claude.sh`, as
`debasher_mcp` is, with the package data and command directories that configure
sets, and installed among the commands; `make install` installs the plugin. Its
tests (`frontend/mcp/src/debasherClaude.test.ts`) build it the same way, against
a `debasher_mcp` and a Claude Code that write down what they are given, and
those of the permissions (`frontend/mcp/src/claudeSettings.test.ts`) check that
every MCP tool is ruled by what it says it does.

# Access to the backend: the token

The backend runs the engine's tools, and the Bash of the program, as the user
who started it, so whoever can send it a request can run anything as that user.
Listening only on the local machine does not narrow that down enough: another
user of the same machine reaches `127.0.0.1` as well, and so does any page open
in the user's browser, whose scripts can send requests to the backend. The
backend therefore obeys only the requests that carry its token, a random secret
that only the user who started it knows, as Jupyter does. This section
describes the token, how a request carries it, what the backend checks, how the
MCP server finds the token, how development works with it, what the editor
does without a valid token, and what the token does not protect.

## The token

`debasher_webui` draws a new token at every start, 24 random bytes from the
secure generator of Python (`secrets.token_hex`), and prints the token URL, the
address of the web UI with the token in its fragment:

```
http://127.0.0.1:8000/#token=<token>
```

The user opens that URL once, and the browser keeps the token from then on (see
"How a request carries the token"). When the backend listens on every address
(`0.0.0.0` or `::`), which no browser can open, the token URL names `localhost`
instead.

A token can also be given, so that it stays the same across restarts and the
open tabs keep working: in `DEBASHER_WEBUI_TOKEN`, or with `--token`. The
variable is the one to prefer, since the command line of a process is visible to
every user of the machine. A token that stays the same has a cost, though (see
"What the token does not protect"). The backend takes its token from
`DEBASHER_WEBUI_TOKEN` alone, which `debasher_webui` sets, and refuses to start
when it is unset or empty: there is no way to run the backend without a token.

## How a request carries the token

Every request to the API carries the token in its `Authorization` header
(`Bearer <token>`), whoever sends it: the editor and the MCP server alike. The
backend compares it with its own in constant time (`secrets.compare_digest`).

The page of the web UI takes the token from the fragment of its address when it
loads, keeps it in the local storage of the browser (`localStorage`), and takes
the fragment out of the address (`history.replaceState`), so that the token
stays neither in the address bar, nor in the history of the browser, nor in a
link copied from it. The browser never sends the fragment of an address to the
server, so the token is never in a request line either, nor in the access log
of the backend.

Every client of the backend in the frontend (`src/api/`, `src/storage/`) sends
its requests through one function, `apiFetch` (`src/api/apiFetch.ts`), the one
place that sees them all. It adds the header with the token of its token source
and calls the `fetch` of the moment, and it adds the header only to a request
for a path of the backend itself (a relative URL), never to another site. In
the browser the token source reads the local storage; a browser that refuses
it (some private windows do) leaves the token in the memory of the tab, which
then works alone: another tab needs the token URL again. The MCP server runs
the same clients under Node.js, which has no local storage to rely on, and
gives `apiFetch` a token source of its own, the token file (see "The token
file").

The token is kept in the local storage, not in a cookie, because the browser
keeps a cookie per host and sends it to every port of that host. A cookie of a
backend on `localhost:8000` would reach any server on another port of
`localhost`, such as one that another user of the machine runs, as soon as the
browser is made to open it, which any page can do. The local storage belongs to
one origin: no page on another port reads it, and the browser sends nothing
from it on its own.

The page itself is served without a token: a `GET` or `HEAD` of `/` or of a file
of the built frontend (`index.html`, with the scripts in it, and its icons),
which is the same for every user and holds none of their data. Every other
request asks for the token, so a path that is added later is closed until it is
opened on purpose. The pages that FastAPI adds on its own to describe the API
(`/docs`, `/redoc`, `/openapi.json`) are turned off.

## What the backend checks

A middleware of the backend checks every request in this order; a request for
the page (see "How a request carries the token") is spared the second check
only:

1. **The `Host` header**, which names the host that the client asked for. A
   backend that listens on a loopback address accepts only `localhost`,
   `127.0.0.1` and `[::1]`, with any port; one that listens on another address
   accepts that address as well; and one that listens on every address checks
   nothing, since it cannot know every name that it is reached by. A request
   with another host, or with none, is answered with 400. This stops a page
   whose own name has been made to point to the local machine (DNS rebinding):
   its requests name its own host. The token stops such a page as well, since
   it holds no token of the backend, and the check of the host keeps it out
   even of a path that a mistake would leave open.
2. **The token**, in the `Authorization` header. A request without it, or with
   another, is answered with 401 and the usual error body of the API
   (`{"detail": "..."}`).

A page of another origin cannot act through the user's browser
(cross-site request forgery): it has no token to send, the browser adds none
on its own, and it cannot even add an `Authorization` header to a request to
another origin without first asking the backend, which grants no such request
(it answers no cross-origin request with permission). A form, which sends no
header of its own, is refused for the same reason. No check of the `Origin`
header is needed.

The address that the backend listens on reaches the middleware from
`api/serve.py`, which binds it (see "The token file"). A backend that uvicorn
starts by hand, as in development, listens on its default, `127.0.0.1`, and the
middleware takes it as such.

The page of the web UI works only as the backend serves it. Opened from a file,
it reaches no backend: its requests to `/api` resolve against no server.

## The token file

The MCP server is not a browser, and the user should not have to give it the
token, which changes at every start. The backend writes it into the token file,
a file of the user's private runtime directory named after the port, which
`debasher_mcp` reads by itself:

```
$XDG_RUNTIME_DIR/debasher/webui-<port>.token
~/.debasher/run/webui-<port>.token      (where XDG_RUNTIME_DIR is unset)
```

The runtime directory of the XDG specification fits the token: it belongs to one
user, lives in memory and is emptied when the user's session ends; macOS has
none, hence the fallback. The token file holds the token and the PID of the
backend that wrote it, with the time at which that process started, as
`ps -o lstart=` prints it in the C locale and in UTC, so that the backend and
`debasher_mcp` read the same text whatever their environment. Where there is no
`ps` (a slim container image), the backend cannot tell when it started, so it
writes no token file and says so, and `debasher_mcp` takes no token file with an
empty start time: the backend works, and only the MCP server cannot reach it.

`debasher_webui` starts the backend through `api/serve.py` instead of running
uvicorn itself, so that the token file follows the backend that owns the port:

1. it binds the address and port, and ends if it cannot, without touching the
   token file, which may belong to a backend already running on that port; the
   socket never takes `SO_REUSEPORT`, which would let a second process bind the
   same port;
2. it creates the directory of the token file with mode 700 if it is missing,
   and writes nothing if the directory belongs to another user or anyone else
   has access to it, saying so;
3. it writes the token file: into a new temporary file of the same directory,
   created with mode 600 (`O_CREAT | O_EXCL`), which it then renames, so that
   the file is never readable by others and a reader never sees half of it;
4. it hands the bound socket to uvicorn, which serves on it, and keeps a copy of
   it;
5. when uvicorn stops, which closes its own copy of the socket, it removes the
   token file if the file still holds its own token, and only then closes its
   copy, so that no other backend can bind the port and write its token file
   in between. It stops so on `SIGINT`, on `SIGTERM` and on `SIGHUP`, which a
   closed terminal sends.

A backend killed with no chance to clean up leaves its token file behind, and
the next backend on that port writes over it. `debasher_mcp` reads the token
file of the port of its URL, and uses it only if its backend is alive and the
host of the URL is a loopback address: it never sends the token to another
machine. The backend is alive if the process of the PID is the user's own (a
signal 0 to it does not fail with `EPERM`) and started at the time that the file
records, so that a PID taken again by another process after the backend died
does not count. Its token source (`frontend/mcp/src/tokenFile.ts`) reads the
token file again for every request, since the backend may restart with another
token while the agent works, and `apiFetch` sends the token with the request.
Without a token file that it can use, it sends none, and the error of the first
refused request names the file it looked for and asks whether `debasher_webui`
runs on this machine with that port. Neither the command of the "Claude Code"
dialog nor a server registered with Claude Code holds the token, so neither
changes when the backend restarts with another one. The token file of another
user is in that user's private directory, out of reach.

The token file is named after the port alone: two backends on the same port of
two loopback addresses (`127.0.0.1` and `[::1]`) write the same file, and the
last one to start wins.

## Development with the token

During development the backend is started by hand, with
`uvicorn api.main:app --reload`, and reads its token from `DEBASHER_WEBUI_TOKEN`
like any other backend, so the developer sets it in the shell. It stays the same
while uvicorn reloads the code, since every new process of uvicorn inherits the
variable. No token file is written, so the MCP server reaches only a backend
that `debasher_webui` started.

The dev server of Vite serves the frontend and forwards `/api` to the backend.
It forwards the requests as they come, with their `Authorization` header and
their `Host`, and adds nothing: a dev server that added the token itself would
hand it to anyone who reaches its port, another user of the machine included.
The developer opens `http://localhost:5173/#token=<token>` once; the page keeps
the token in the local storage of the dev server's origin and sends it with
every request, which the dev server forwards to the backend.

## The editor without a valid token

The editor needs the token from its first request. A page that has none, opened
without the token URL in a browser that never kept one, shows a notice that says
to open the token URL that `debasher_webui` printed, instead of failing request
after request.

A tab whose token the backend no longer knows, because the backend restarted
with a new one, gets 401 for every request. `apiFetch` sees it in one place,
and no client of the backend is left to report it on its own. The tab
(`components/TokenNotice.tsx`):

- shows a notice that stays over every screen, saying that the backend no
  longer knows this tab, that it restarted with another token, and that the
  token URL it printed has to be opened;
- stops its polling (the revision of the program, the files of the program
  files panel, the process statuses, a watched FIFO), which would only get 401
  again every few seconds;
- leaves the program in the store as it is, with its unsaved changes, and
  offers "Retry", which asks the backend again (`/api/webui/info`) with the
  token that the local storage holds then and, if the backend takes it, takes
  the notice away and starts the polling again.

The token URL can be opened in the tab itself: it differs from the address of
the tab in its fragment alone, so the browser loads nothing again and only
tells the page (`hashchange`), which takes the token, asks the backend as
"Retry" does, and goes on with its unsaved changes. Opened in another tab, it
stores the new token, which every tab of the same origin shares, and "Retry"
then succeeds in the first one.

## What the token does not protect

- **Whoever holds the token can do anything.** The backend has no users and no
  permissions: the token gives everything that the user who started it can do.
  It is a secret, to keep like a password.
- **A script in the page reads the token.** The local storage is open to the
  scripts of the page, so a script injected into it would read the token; such
  a script could use the API through the page anyway, so the token adds little
  to what it already holds.
- **A token that stays the same outlives its backend.** While no backend
  listens on the port, another user of the machine can listen there. A tab or a
  token URL opened then loads that user's page, which reads the token from the
  local storage of the origin. A token drawn at the start dies with its backend,
  so stealing it gives nothing; a token given with `--token` or
  `DEBASHER_WEBUI_TOKEN` stays valid, so it is best kept for a machine that the
  user does not share. `debasher_mcp` does not send it there, since the backend
  of the token file is gone. That user's page can also leave a token of its own
  in the local storage, which harms nothing: once the backend is back, the tab
  gets 401 and asks for the token URL (see "The editor without a valid
  token").
- **The token travels in clear over HTTP.** On the local machine that exposes it
  to nobody, but a backend that listens on a network sends the token, and
  everything else, unencrypted. The safe way to reach a remote backend is an SSH
  tunnel to a backend that listens on its loopback address.
- **The token URL is printed.** It stays in the terminal that started
  `debasher_webui`, and in its log where one is kept.

# Future work

- **Ordering a reader of a whole shared directory.** An input that reads the
  whole of a shared directory gets no dependency on the processes that write
  its shared subdirectories, and its process has to be ordered with explicit
  dependencies, which replace all its inferred ones (see "Directories and their
  subdirectories"). The edge that the canvas draws could order it, if the engine
  inferred a dependency of an input that holds a directory on the outputs that
  hold paths below it, or let a process add a dependency to its inferred ones
  (see "Dependencies by containment" in the future work of the design of the
  engine).
- **The result of each test.** "Run tests" shows the reports of bats and
  pytest as text; parsing them would let the canvas mark the processes whose
  tests fail.
- **An assistant in the web UI.** A chat in the editor that helps to design and
  build the program, backed by an agent that calls the MCP tools and whose edits
  reach the canvas as proposals for the user to accept. Not designed beyond what
  the MCP server and `debasher_claude` (see "Claude Code on a program") give it;
  a terminal in the page that runs `debasher_claude` would come first, behind
  the token (see "Access to the backend: the token"). It shares the open
  questions of the assistant on the documentation (see "An assistant on the
  documentation of DeBasher" below): where the key of the AI service lives on a
  server whose only guard is the token, and that the program, and maybe its
  files, leave the machine for that service, which the user has to know.
- **Round trip at run time.** Running each module of `data/programs/` and the
  module generated from it, and comparing what they do, beyond the comparison
  of models that `test/api/test_round_trip.py` makes.
- **The group on the canvas.** Adding the group to the structural key of the
  canvas, so that a dissolved group loses its color and badge at once (see
  "Keeping the canvas in step with the store").
- **The output directory of a moved program.** Deciding what a program
  loaded from a new place should do with an output directory that still
  points to the old one.
- **A code prompt for the rest of the code.** The code prompt for the other code
  that the user writes: the preamble, and the option definition function of a
  `manual` process, which is written with the API of the engine for options and
  would need a reference of it, read from the engine as the node reference is
  read from the runtime library.
- **An assistant on the documentation of DeBasher.** A chat in the web UI that
  answers questions about DeBasher from its documentation (the documentation of
  the project, the design documents and the module documentation of the modules
  at hand), through a model of an AI service with a key that the user gives. Not
  designed. It needs a place for the key that fits a server whose only guard is
  the token, never the program metadata; it sends the documentation, and maybe
  the program, to a service outside the machine, which the user has to know; and
  its answers are only as good as a documentation kept in step with the code.
- **The documentation installed with DeBasher.** Building the documentation
  of DeBasher into HTML when the package is made, installing it, and serving it
  from the backend, so that the Help menu links to the documentation of the
  installed version, also on a machine with no access to the internet, and to
  the published documentation only when the installed one is absent. Building
  it needs Sphinx and its extensions, which a package built from the
  distributed sources would rather not need.
- **Closing an external input.** An action of "Talk to FIFOs" that writes a
  `CLOSE` into an external input, to tell a node that its source has
  finished, once the engine has a hook that lets the code of a node learn that
  a port closed.
- **A batch run opened as a program.** Loading the general program of a
  launcher node with a run directory as its output directory, to follow the
  batch run on the canvas, colored by the statuses of its processes. The
  general program may not have been made with the web UI, and opening it must
  not write into its directory.
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
- **Templates of the code of a node.** A first code for the parts of a node when
  it is added, as the template of a general process gives one: a constructor
  that gives the node state its first value, a `capture_node_state` that returns
  all of it and a `restore_node_state` that sets it back, and a `process_data`
  with a branch for each business input. For a node that sends to a fanout
  family, a routing that is already deterministic, such as a counter kept in the
  node state, since a routing that a replay may change would make the sequence
  numbers of a channel label other messages (see "Fan-out and fan-in sized from
  the command line" in `doc/design_doc_resident.md`).
- **What import loses.** Giving `_define_opt_deps` and `_program_type` a place
  in the model. The second is needed by resident programs, and "Script
  generation and import of a resident program" designs it.
