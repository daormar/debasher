---
title: Design of the Python SDK
fontsize: 11pt
geometry: margin=2cm
numbersections: true
toc: true
toc-depth: 2
---

This document describes the design of the Python SDK of DeBasher, the
library with which a program is described in Python and written as the
program that the web UI saves, and the guarantees it gives. It is organized
as follows: a glossary; what the user writes (the processes, their
options, the program, a resident program); how the description becomes
the program model; how the program is written; the tool that writes it
and the examples; how the library is installed and found; the
guarantees and what the SDK deliberately is not; and the future work.

# Introduction

A program of DeBasher can be built in the web UI, written by hand as a
Bash module, or, with the SDK, described in Python: processes with their
options and their connections, and a program that adds them with the
specifications of their use. The SDK is a door into the program model of
the web UI (`api/models.py`), the same model that the editor saves and
that script generation turns into a module: it builds that model and
saves it exactly as Save does in the editor, so that what it writes is a
program like any other, run by `debasher_exec` and opened by the editor
without a difference. The SDK executes nothing itself and generates no
Bash of its own: the module comes from the one script generation of the
project, and what runs the program is the engine.

The description reads like a module. A hand-written module defines
processes, each with its options and, through its option definitions,
its connections, and a `_program` method that adds the processes with
their specifications; it calls nothing, since `debasher_exec` loads it. A
file of the SDK does the same: it defines processes, defines one program
that adds them, and calls nothing, since the tool `debasher_build` loads
it and writes the program. The one thing the user does differently is to
keep the code of each process in a file of its own language beside the
description, instead of inside the module.

# Glossary

The precise meaning of the words this document uses. Identifiers in
backticks are names that exist in the code. Terms of the engine, of the
web UI and of resident programs that this glossary does not list have the
meaning that their design documents give them (`doc/design_doc_engine.md`,
`doc/design_doc_webui.md`, `doc/design_doc_resident.md`), and so do the
entries below that refer to them.

- **program model**: as in the design of the web UI: the program as plain
  data, the tree of Pydantic models of `api/models.py` with the
  processes, their options, their connections and their specifications,
  which script generation turns into a module. The library builds one
  and never reads one; the tool loads one only to save it back (see "The
  tool: `debasher_build`").
- **artifact**: as in the design of the web UI: the saved form of a program,
  the topology file `program.yaml` and the files it names, in its home
  directory (see "The artifact: the topology file and the process files"
  in `doc/design_doc_webui.md`).
- **program metadata**: as in the design of the web UI: the program model
  saved as JSON in `.debasher/program.json`, the saved form of before the
  artifact.
- **home directory**: as in the design of the web UI: the directory where
  a program lives, with its artifact, its generated module and its user
  files. The SDK writes a program into one, by default the directory of
  the description.
- **module**: as in the design of the engine: the Bash file with the
  processes as suffixed functions and the program as its `_program`
  method. The SDK never writes one itself: script generation writes it
  from the program model (the **generated module**, `<name>.sh`).
- **door**: a way of producing the program model: the editor, the import
  of a hand-written module, and the SDK. The engine runs the result of
  any of them without a difference.
- **description**: the Python file of the user that defines the processes
  and the program, named after the program (`<name>.py`). It calls
  nothing; `debasher_build` loads it. The free text that a program or a
  process carries (`description=`) is called its **description text**
  here, to tell the two apart.
- **process file**: the file that holds the code of a process beside the
  description, in its own language: a Bash function named as the process,
  or the whole script of another language. It is given to the process as
  its code (`code=`), and the SDK then embeds its text in the program
  model when the program is written, or as a script.
- **script**: a process file that the user owns (`script=`): the module
  runs it as it is, the external alias of the engine, the editor shows it
  and never writes it, and it is copied beside the module when the
  program is written elsewhere.
- **external alias**: the `ext_alias` additional specification of the
  engine (the `ext_alias` case of an alias in the design of the engine):
  a file that a process runs as it is, with the interpreter that the
  engine chooses by its extension.
- **source**: what an input of a process reads: the output option of
  another process, given as the option itself or as the name of the
  process and the label of the option, as a module names them in
  `define_opt_from_proc_out`. The connections of the program model are
  derived from the sources of the inputs of the processes it adds.
- **specifications of a use**: what a program says about a process when it
  adds it: its computational specifications (`cpus`, `mem`, `time`), its
  explicit dependencies (`processdeps`), whether it is forced
  (`force`), and its position on the canvas. They belong to the program,
  as the arguments of `add_debasher_process` do, so that the same process
  added to two programs can have different ones.
- **options handler**: how a process of the program model defines the
  options of its tasks, in one of the options handler modes of the design
  of the web UI: the standard mode, one task from the declared options
  (`Process`); the array mode (`Array`) and the generator mode
  (`Generator`), several tasks shaped by code; the manual mode, a whole
  `_define_opts` by hand, which the SDK does not offer.
- **tasks file**: the Bash file that shapes the tasks of an `Array` or a
  `Generator` (`tasks=`): the code that the editor accepts in the options
  handler of that mode, which builds the array of the tasks or prints
  their number, and which the engine runs when it prepares a run.
- **method file**: a Bash file with the body of one of the additional
  methods of a process (`skip`, `post`, `reset_outfiles`,
  `outdir_basename`, `conda_envs`, `docker_imgs`), as the editor takes
  it in its additional methods.
- **node**: as in the design of resident programs: a process of a
  resident program, whose code is a Python class derived from a class of
  the runtime library (its node kind). In the SDK, a `Node`, whose code
  is a node file, or the `Supervisor`, which has none.
- **node file**: the Python file of a node (`code=` of a `Node`): the
  import of its node kind, the node preamble, the class of the node with
  its hooks (the methods of the runtime library that a node redefines:
  `process_data`, `capture_node_state`, `restore_node_state`,
  `initialize_runtime`, `observe`), and the line that runs it, as the
  generated module writes them in the heredoc of the node. The SDK
  splits it into the node kind and the parts of its code in the program
  model (the node preamble, the class body and the hooks of the design
  of the web UI) with the same code as import.
- **specifications of a node**: the computational specifications that
  only a node of a resident program reads: the limits of a node of the
  design of resident programs (`input_log_max_mb`, `out_backlog_max_mb`,
  `out_backlog_fail_mb`, `gil_switch_interval_ms`) and
  `startup_timeout_s`, `max_concurrent_runs`, `batch_sched` and
  `heartbeat_timeout_s`, given with the specifications of its use.
- **launcher**: `debasher_build`, a Bash script built by `make` that
  chooses the Python to run the tool with and runs
  `python -m debasher.build`.
- **installation module**: `debasher/_install.py`, a Python module that
  `make` writes with the directories of the installation, with which the
  library finds the API of the web UI and the tools of the engine once
  installed. It is not a source: `make` writes it, git ignores it, and
  the library works without it in a source tree.
- **twin**: of an example of the SDK, the program that the web UI saved
  under `data/webui_programs/` which the example reproduces, differing
  from it in its name, its description text and the positions on the
  canvas only; the tests write the example as its twin and compare the
  two.
- **topology file**: as in the design of the web UI: `program.yaml`, the
  part of the artifact that holds the program, its processes, their
  options with their connections and their specifications, and the paths
  of the files of their code (see "The artifact: the topology file and the
  process files" in `doc/design_doc_webui.md`).

# What the user writes

A description is a Python file that imports the library and defines
processes and one program, as the sketch below does. The same file,
indented and commented as the user likes, is all there is: no call to
write or to run anything.

```python
from debasher import Process, Program, in_outdir

generate = Process("generate", code="generate.sh",
                   description="Generates a text file.")
generate.output("-outf", "file", "output file", in_outdir("file.txt"))
generate.cmdline_opt("-l", "int", "Length of file in lines")

count = Process("count", code="count.sh", description="Counts characters.")
count.input("-inf", "file", "input file", source=generate["-outf"])
count.output("-outf", "file", "output file", in_outdir("counts.txt"))

prg = Program("count_chars", program_options={"-l": "200"})
prg.add(generate, cpus=1, mem=32, time="00:01:00")
prg.add(count, cpus=1, mem=32, time="00:01:00")
```

## Processes

A process (`Process`, `sdk/python/debasher/process.py`) is defined on its
own, outside any program, as a process of a module is: a program adds it,
and the same process can be added to several programs. Its name follows
the rule of the engine for a process name, parts of letters, digits and
underscores separated by dots, and may not end in a suffix that the
engine reserves for a method (`_define_opts`, `_py`, ...); the SDK checks
the name when the process is created, with the same rule as the backend
of the web UI, so that an error is reported at the line that gives the
name.

Where the code of a process is comes with the process, in one of four
ways, which the process may not combine:

- `code=`, a process file: a path, taken from the directory of the Python
  file that creates the process when it is relative (`base_dir=` names
  another directory), whose extension tells the language of the process
  (`.sh` Bash, `.py` Python, `.pl` Perl, `.r` or `.R` R, `.groovy`
  Groovy; `language=` says it when the extension does not). The file is
  read when the program is written and its text goes into the program
  model and into the module, as the text of the code box of the
  editor does, without the newlines that end it (see "From the
  description to the program model"): a Bash function named as the
  process, with its helper functions, written as it is; the script of
  another language, as the heredoc function that the engine runs with
  the interpreter of the language.
- `script=`, a script: a path to a file that the module runs as it is,
  the external alias of the engine, with the interpreter that the engine
  chooses by its extension. The program model keeps a copy of its
  text, without its final newline, for the editor to show, as import
  keeps it for an imported external alias, and the module refers to the
  file by the path as it was given, or by its name alone when the path
  contains `..` (see "Writing the program").
- `alias=`, the name of another process whose code this one runs under
  its own name and options. `alias_opt_map=` renames its option labels
  into those of the aliased process, label to label, and does the same
  for a script.
- none of them: the code of a process of that name that a module loaded
  by the preamble of the program provides, as for a process of a module
  that adds a process of another.

A `Process` defines one task from its declared options. An `Array` and a
`Generator` define several, shaped by a tasks file that they require
(`tasks=`): for an array, the Bash that builds the array of the tasks
under the name `array`, from the command line of the run and the files
present then, after which every option of the process is defined once
per element, with `${task_idx}` and `${array[$task_idx]}` at hand in its
value; for a generator, the Bash that prints the number of tasks, each
task's options being defined from `${task_idx}`. They are the array and
generator modes of the options handler, and the tasks file is the code
of the options handler as the editor keeps it, in a file instead of a
box. A task shaping option of such a process
(`cmdline_opt(..., shaping=True)`) is read by the tasks file only, as in
the editor. The code of the tasks file runs when the engine prepares a
run, not when the program is built: the tasks depend on the command line
of each run, which a build does not know (see "Future work" for the same
code in Python).

The additional methods of a process are given as method files (`skip=`,
`post=`, `reset_outfiles=`, `outdir_basename=`, `conda_envs=`,
`docker_imgs=`), each a Bash body that the editor would take in its
additional methods, and go into the program model as such.

## Options

The options of a process are declared by its methods, each of which gives
an option the source of its value and its option channel with the
vocabulary of the program model, and returns the option, which a source
of another process or a count source can then name. An option of a
process is also reached by its label, `generate["-outf"]`. The label is
the name of the option for the engine, and its direction comes from the
label as the engine reads it: an output is a label that starts with `-out`
or `--out`, and the methods refuse a label whose direction is not theirs,
so that an input mistakenly named as an output is reported where it is
declared. A label is declared once per process.

- `cmdline_opt(label, type, description, mandatory=True, shaping=False)`:
  an input whose value comes from the command line of the run, mandatory
  unless said otherwise; a task shaping option (`shaping=True`), which the
  options handler alone reads, is always mandatory.
- `cmdline_flag(label, description)`: a flag of the command line, an
  option with no value, whose data type is `None` in the program model.
- `input(label, type, description, value="", source=None, ...)`: an input
  with a literal value, or connected to its source, one or, for a fan-in,
  a list; never both.
- `output(label, type, description, value="", ...)`: an output, whose value
  names what the process produces. `in_outdir("name")` gives the value
  of an output kept in the process output directory,
  `${process_outdir}/name`, or the directory itself with no name.
- `fifo_output(label, type, description, name, mirror=False, ...)` and
  `fifo_input(label, type, description, name, external=False)`: an
  option delivered through a FIFO of that name (the fifo option channel),
  an output mirrored into a log file for the canvas to watch if asked, an
  input that the process opens itself rather than receives through a
  connection, external in a resident program when written from outside
  it (the fifo tag `external`).
- `outdir_opt(label, description, subpath="")`: an output that names the
  process output directory of the process, or a task subdirectory of it
  (the `process_outdir` channel, with the subpath a Bash word such as
  `"${task_idx}"`), for another process to read through a connection.
- `shared_dir_opt(label, type, description, shared_dir, subpath="", source=None)`:
  an option whose value is one of the shared directories of the program,
  or a shared subdirectory of it (the `shared_dir` channel); its source,
  if any, only draws the sharing on the canvas, since the engine orders
  the processes by the directory itself.
- `procspec_opt(label, type, description, attribute)`: an input whose
  value is an attribute of the specifications of the use of the process,
  such as `cpus`.
- `value_desc_output(label, type, description)`: an output delivered as a
  value descriptor that the engine synthesizes.
- `opt(label, type, description, **fields)`: an option with any field of
  the program model given by name (`value`, `channel`, `subpath`,
  `mirror`, `fifo_tag`, `command_line`, `mandatory`, `from_process_spec`,
  `task_shaping`, `count_source`, `source`, `display`). The other methods
  are this one with the fields of one case set.

A fanout family, an option whose label ends in `-ith` on a `Process`
and stands for one option per task of the array or generator at the
other end of its connection (`-outf-ith` for `-outf0`, `-outf1`, ...),
is declared with `output`, `fifo_output` or `input` and counted by
`count_source=`, an option of the same process given as the option or
its label, or, without one, by the tasks of the process it is connected
to. The SDK resolves the count source to its id and refuses one of
another process; the rules of a family (what it may be connected to,
which channels it takes) are those of script generation, which checks
them when the program is written.

The data types are those of the program model: `int`, `float`,
`string`, `file`, `dir`, and `None` for a flag. The SDK does not check
what an option's value means for the engine (that a literal path exists,
that a Bash word expands): the value is a Bash word, written as it is, as
in the editor.

## The program

A program (`Program`, `sdk/python/debasher/program.py`) has a name, which
names its module and its description, and carries what the editor keeps
beside the processes: its description text, the program options (label to
value, what "Set program options" of the editor holds, given to
`debasher_exec` by whoever runs the program), the preamble of the module
(Bash before the functions, such as `load_debasher_module` lines), the
environment variables of the runs, the shared directories it declares, and
the execution options of the editor, given by name (`scheduler`,
`conda_support`, `docker_support`, ...). The name follows the rule of a
process name without namespaces, since it names the `_program` method of
the module.

`add(process, cpus=, mem=, time=, processdeps=, force=, position=)` adds
a process with the specifications of its use, as `add_debasher_process`
does in the `_program` method, and returns it. A process added twice, or a
process with the name of one already added, is refused. The order of the
processes is the order they are added in, which is the order of the
functions in the module and of the processes in the topology file.

A program does not declare connections: they belong to the processes, as
in a module, where the `_define_opts` method of a process names the
process and the output it reads. When the program model is built, the
sources of the inputs of every process added give the connections, and a
source that names a process the program does not add, an option the
process does not have, or an input, is refused with the names of both
ends. The same process object, with its sources, goes into any program
that adds what it reads.

## Resident programs

A resident program is a `Program` with `resident=True`, which may ask for
periodic snapshots of its runs (`snapshot_every_secs`, the period that
the editor starts once the program is launched), and adds nodes instead
of processes: a `Node`, or the `Supervisor`. It refuses a `Process`, and
a general program refuses a node, when they are added, so that a
description that mixes them is reported at that line rather than by
script generation later.

A `Node(name, code=<node file>, initiator=False, description="")` is a
process whose code is a node file; its node kind is the base class of
the one class of the file that derives from a class of the runtime
library (`FBPProcess`, `ProgramLauncher`, `DirectoryWatcher`), and it is
an initiator, where a round starts, when said. Its ports are its
options, declared as those of any process: an external port is
`fifo_input(..., external=True)`, an input written from outside the
program, and an output to another node or to the outside is
`fifo_output`. The
Supervisor wiring (heartbeat channels, trigger ports) is never
declared: script generation derives it, as for a program of the editor.
A `Supervisor(name, description="")` has no code and no options of its
own; script generation writes its whole class.

The specifications of the use of a node are those of any process plus
the specifications of a node, given to `add` under the names of the
engine; an unknown name, or one of them on a process of a general
program, is refused.

# From the description to the program model

`Program.to_model()` builds the `Program` of `api/models.py` that
`write()` saves. The translation is one to one with the program model,
with these rules:

- **Ids.** Every id (the program, each process, each option, each
  connection) is a UUID derived from the names (`uuid5` of the program
  name, the process name and the label), so that building the same
  description twice gives the same artifact, and a description
  kept in a repository with its built program gives no spurious diff.
  The editor draws the id of a process it creates at random, and loading
  assigns them from the names (see "The topology file" in
  `doc/design_doc_webui.md`); nothing reads an id as a name.
- **Code.** The process file or script of a process is read at this
  moment, and a file that cannot be read is refused. A process with
  neither has an empty code, which script generation leaves out, for a
  loaded module to provide. Every text taken from a file (the code, the
  copy of a script, a tasks file, a method file) goes into the program
  model without the newlines that end it, which is how import keeps the
  code it reads from a module: the file ends with a newline, the code
  does not, and a program written with the SDK and the same program
  imported from a module hold the same text.
- **Specifications.** Those of the use go into the computational and
  additional specifications of the process; the alias and its map, which
  are the process's own, go with them. The script of a process goes into
  the external alias of the additional specifications, as the path that
  the module will refer to (see "Writing the program").
- **Options handler.** The mode of the process, with the text of the
  tasks file as the array code or the generator size code of an `Array`
  or a `Generator`; a `Process` is in the standard mode. The text of each
  method file goes into the additional methods of the process. Both are
  read at this moment, and a file that cannot be read is refused.
- **Nodes.** The node file of a `Node` is read and split with
  `decompose_heredoc` of the API, the code that import uses on the
  heredoc of a node, into the node kind and the parts of its code
  (`nodeKind`, `nodeCode`); the code of the process itself is empty, as
  the editor keeps it, since script generation writes the heredoc from
  the parts. A node file that the web UI could not hold (for example
  several node classes, a decorator or a second base on the class, code
  after the class other than the line that runs it) is refused with the
  problems that import would report, each with its line, when it has
  one, and the change that would make it fit; a file that defines a
  Supervisor, with or without code of its own, is refused too, since the
  Supervisor is added without a file. The Supervisor gets the node kind
  `Supervisor` and no parts. The specifications of a node go with its
  computational specifications.
- **Positions.** A process added with a position has it. The others are
  placed as the editor places the processes of an imported program, whose
  module says nothing about positions: in layers by the depth of their
  connections, a process that feeds another above it, the processes of a
  layer side by side in their order in the program (`api/layout.py`,
  shared with the loading of a topology file: the rule of
  `frontend/src/models/programLayout.ts` ported as it is, passes capped
  at the number of processes so that a cycle through FIFOs ends with some
  layering).
- **Connections.** One edge of the program model per source of an input,
  drawn as a line unless the input says `display="label"`. A fan-in is
  one edge per source.

What the SDK checks is what it can know without the engine: names,
labels, directions, that a source exists, that a file can be read. What
only script generation knows (an option whose value would come from two
places, a fanout family badly counted, a channel that a resident program
refuses) is checked by script generation when the program is written,
and reported with its own message, the same as the editor shows.

# Writing the program

`Program.write(home_dir)` writes the program into a home directory as
Save does in the editor: it builds the program model, calls
`persistence.save` of the API, which generates the module and writes the
artifact and the module under the lock and with the digest that the
design of the web UI describes (see "The digest of the artifact" there),
copies the scripts, and returns the path of the module. It raises
`DefinitionError`, the one error of the SDK, for what it or script
generation refuses, and nothing is written then: the model is built and
the scripts are checked before anything touches the directory, and
`persistence.save` generates the module before it writes. The files of
the artifact are written where the description had them, by the paths of
the process files, the tasks files and the method files relative to the
directory of the description (a path that climbs out of it, or an
absolute one, gives the name of the file alone), each only when its
content differs from the file there, so that a program written into the
directory of the description leaves its files as they are, and a program
written elsewhere gets a copy of each.

The external alias of a process names its script as the path was
given, when it is relative and stays below the directory of the
description (`./tools/dispatcher.py` is written as it is), or the name
of the script alone when the path contains `..` (`../shared/tool.py`
becomes `tool.py`); the engine resolves it against the directory of the
module, so the script is copied beside the module under that same path,
replacing an older copy, and the program written is self-contained, as
the home directory of the editor is. A script in the home directory
itself is never copied onto itself. An absolute path is written as it
is and the script is not copied: the engine takes it with a warning
about portability, which is the user's choice.

Script generation needs `debasher_get_proc_info` of the engine for one
thing only, to leave out the code of a process that a module loaded by
the preamble already provides; without the tool every process is written
with its code, which is right for a description with no preamble. The
SDK tells the API where the tools are (see "Finding the API and the
engine").

# The tool: `debasher_build`

`debasher_build <description>.py [-o <dir>]`,
`debasher_build [<home directory> | <home directory>/program.yaml]` or
`debasher_build --schema` (`sdk/python/debasher/build.py`). Given a
description, the tool loads it, finds the program it defines and writes
it. It
is the equivalent of Save in the editor, and it is where `write()` is
called: a description calls nothing, as a module calls nothing. The tool
is also the regeneration tool of the artifact (see "The doors and the
regeneration tool" in `doc/design_doc_webui.md`): given a home directory,
its topology file, or nothing in a home directory, it loads the program
saved there and saves it back as it is, which writes the module again and
leaves the artifact as it was (a topology file not in the form the
backend writes is written again in that form), so that a program kept in
a repository as its artifact is built without the editor; `-o` goes with
a description only. `--schema` prints the JSON Schema of the topology
file.

- The description is run as a Python module with its own directory first
  on `sys.path`, so that it can import files beside it. Among its global
  names there has to be exactly one `Program`; none or several is an
  error.
- The description is named after its program, as a module is named after
  the program it defines (`align_all.py` defines `Program("align_all")`);
  a mismatch is an error that names both, since the name of the program
  is the name of the module and the editor looks for `<name>.sh`.
- The program is written into the directory of the description unless
  `-o` names another: beside the description and the process files, which
  is the home directory as the editor keeps it, with the user files of
  the program beside the artifact.
- The path of the module is printed, and an error of the SDK is printed
  with the prefix `debasher_build:` and exits with status 1.

Running the program is then the same as for any program:
`debasher_exec --pfile <name>.sh --outdir <dir> ...`, `debasher_status`,
or the Run of the editor once the home directory is opened in it. The
description is never run with `python` nor given to `debasher_exec`, and
a change to it is followed by another `debasher_build`.

## The examples

Three descriptions ship under `data/sdk_programs/python/`, installed
under `sdk_programs/python` of `$(pkgdatadir)`, one
directory per program with the description named after it and the
files of its processes beside it: `sdk_hello_world_py`, the hello world
of the quickstart with its process in Python; `sdk_dynamic_fanout_fifos`,
a generated file cut into fragments that a dispatcher, run as a script,
streams through FIFOs to an array of workers whose tasks a tasks file
shapes; and `sdk_running_sum`, a resident program with a node given as
a file and a Supervisor. Each is the twin of a program saved under
`data/webui_programs/`, which the tests check by writing the example as
its twin and comparing the programs loaded from both and the module (see
"Guarantees"). `make installcheck` builds each example from its installed
directory with `debasher_build` into a directory of its own and runs the
program built as it runs the others,
or skips the three when the Python of `debasher_build` lacks the
dependencies of the SDK, as it skips the checks of conda without conda.

# Installation, and finding the API and the engine

## Installation

The library is the package `debasher` in `sdk/python/debasher`, and
`sdk/python/Makefile.am` installs it as a Python package, with
`pkgpython_PYTHON`, into `$(pkgpythondir)`, which is
`$(pythondir)/debasher`, the directory that automake reserves for the
Python package of the project and that the Python tools of the engine
already put on `sys.path`. When the prefix of the installation is that
of the Python itself (a virtual environment, a conda environment with its
Python), `$(pythondir)` is its `site-packages` and `import debasher`
works with nothing more; otherwise the user puts `$(pythondir)` in
`PYTHONPATH`. The conda package, whose Python directory is one of its
own under the prefix of the environment, puts it in `PYTHONPATH` when
the environment is activated, through a script in its `activate.d`
(`conda/build.sh`). The library needs the dependencies of the API of
the web UI (pydantic 2, `api/requirements.txt`), as the web UI does.

The tool is the launcher `debasher_build`, built from
`sdk/python/debasher_build.sh` with the directories of the installation
in front, as `api/Makefile.am` builds `debasher_webui`, and installed in
`bindir`. It chooses the Python as `debasher_webui` does: the one that
`DEBASHER_WEBUI_PYTHON` names, else `python3` on the `PATH` (that of an
activated environment), else the Python of `configure`; when that Python
lacks pydantic 2 it says so and prints what to install, instead of
failing inside the library. It runs `python -m debasher.build` with
`$(pythondir)` in `PYTHONPATH`, and, in the source tree before any
installation, with its own directory first, where the package is beside
it. A description that the tool loads therefore imports `debasher`
without the user setting anything.

## Finding the API and the engine

The library builds on the API of the web UI, the package `api`, which is
installed as data under `$(pkgdatadir)/api`, not as a Python package:
`debasher_webui` imports it by putting `$(pkgdatadir)` in `PYTHONPATH`.
The library does the same on import (`sdk/python/debasher/_paths.py`):
when `api` is not importable already, it appends the root of the
repository to `sys.path` when the library is in a source tree (found from
its own file), else the package data directory that the installation
module names. The installation module, `debasher/_install.py`, is written
by `make` from the directories of the installation (`pkgdatadir`,
`bindir`, `libexecdir`, `pythondir`) and installed with the package; it
is not a source, git ignores it, and in a source tree the library works
without it, since the root of the repository is tried first.

The API finds the tools of the engine through the environment variables
that `debasher_webui` sets for it (`DEBASHER_WEBUI_BIN_DIR`,
`DEBASHER_WEBUI_LIBEXEC_DIR`, `DEBASHER_WEBUI_PYTHON_DIR`), or, without
them, in the source tree. The library sets the same variables from the
installation module when they are not set and the directories exist, so
that script generation finds `debasher_get_proc_info` in an installation
as it does under the web UI. Nothing of the library imports the routers
of the API or FastAPI: it uses `api.models`, `api.persistence` (and
through it script generation), `api.debasher_constants`, `api.layout` for
the positions and `api.topology` for the ids derived from names.

# Guarantees and non-goals

## Guarantees

- **What the editor saves.** A description written with the SDK gives the
  program that the editor would save for the same program, apart from
  the ids, the digest and home directory of the save and the names of the
  files of the artifact, and the module that script generation writes
  from it, byte for byte: the three examples of
  `data/sdk_programs/python/`, written as their twins, are compared in
  the tests with `data/webui_programs/webui_hello_world_py`,
  `data/webui_programs/webui_dynamic_fanout_fifos` and
  `data/webui_programs/webui_running_sum` (see "The examples").
- **Deterministic.** Two builds of the same description give the same
  artifact: ids come from names, positions from the layout, and nothing
  from the clock or from randomness.
- **Nothing runs.** Building a program runs no process and no engine
  tool but `debasher_get_proc_info`, which reads a module and runs
  nothing of it. The description is loaded as a Python module, so the
  code it holds runs as any Python file does; the code of the processes
  is read, never run.
- **No Bash of its own.** The SDK writes no line of the module: every rule
  of the translation lives in script generation, and what it refuses it
  refuses for the SDK with the same message.
- **Nothing half written.** A program refused by the SDK or by script
  generation leaves the home directory as it was.

## Non-goals

- **Running a program.** The SDK is a door into the program model, not a
  runner: `debasher_exec` runs the program, from the command line or
  from the editor, so that building never executes and the runner is the
  same whatever door the program came through.
- **Reading a program.** The library builds a program model and never
  reads one: the way from a module or from an artifact into a description
  does not exist, and import stays what it is in the web UI. The tool,
  when it rebuilds a program from its artifact, loads the program model
  through the persistence of the API and gives it back to it unchanged,
  with nothing of the SDK in between.
- **A second engine.** No option is resolved, no dependency inferred and
  no task defined in Python: what the engine does with the module it
  does for a program of the SDK as for any other.
- **Dynamic options in Python.** In this version the code of the options
  handler of an array or a generator is the Bash that the editor accepts,
  kept in a file (see "Future work").

# Future work

- **Dynamic options as Python functions.** The code of the options handler
  of an array or a generator as a Python function in a file, which a
  helper that the generated module calls with the task index runs,
  printing the option definitions that the handler consumes: exactly what
  the Bash of the options handler does today, in Python, and nothing
  more. The code runs when `debasher_exec` prepares a run, as the Bash
  does, since the tasks depend on the command line of each run, which a
  build does not know. The skip rule of a process (`skip`), evaluated at
  the same moment, takes the same way.
- **The additional methods as data.** The Conda environments and Docker
  images of a process, the files it removes before a rerun and the name
  of its process output directory are data (a name and a file, a list of
  names) that the editor and the SDK carry as Bash bodies because the
  program model has no field for them. When the process contract of the
  engine gives them a form, the SDK takes them as arguments
  (`conda_envs={"py27": "py27.yml"}`) and the method files go; until
  then the SDK writes no Bash from data, however short the body would
  be. The `post` method, which runs inside the task after the process,
  belongs with the code of the process.
- **Processes as a library, and namespaces.** A process defined in a
  Python module of the user and added to several programs, as a process
  of a loaded module is. The namespace of DeBasher is a naming convention
  kept in the program model, where the dotted name is what the engine and
  every other door see, while a namespace of Python exists only while the
  description runs: the relation is a projection when the program model
  is built, and a library process gets its prefix from an explicit
  namespace object, never from the path of the Python module that
  defines it, which is a detail of the installation and not a name. The
  SDK of today keeps that door open: options belong to the process and
  the connections to its inputs, so that one process object goes into any
  program that adds what it reads.
- **Processes as decorated functions.** A Python function in the
  description itself, whose source the build extracts to a process file,
  for a process too small for a file of its own.
- **`script=` as another name of `code=`.** For a file of another language
  the two give the same module, since script generation refers to a
  `code=` file as an external alias too (see "The process files" in
  `doc/design_doc_webui.md`); the one difference left is who owns the
  file (the editor writes a `code=` file and only shows a script). Whether
  to keep `script=` for that difference or make it another name of `code=`
  is to be decided. A tasks file in Python, when dynamic options as Python
  functions exist, is named by `tasks` as a Bash one is, its extension
  saying which.
