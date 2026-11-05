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
as follows: a glossary; what the user writes (the processes, with their
invariant part, their interface and their task options, the program, a
resident program); how the description becomes the program model; how
the program is written; the tool that writes it and the examples; how
the library is installed and found; the guarantees and what the SDK
deliberately is not; and the future work.

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

The description is divided as a module is. A hand-written module keeps
apart what describes a process and never varies, its body and the
explanation of the options it receives (`_explain_opts`), from what wires
it into a program and gives it its shape: which options come from outside
the program (`_identify_cmdline_opts`, `_explain_task_shaping_opts`) and
how the options of its tasks are defined (`_define_opts`, or
`_generate_opts_size` and `_generate_opts`). Connecting an option to
another process, or making the process an array, rewrites the second part
and touches nothing of the first, in the module itself or by defining the
method again after the module is loaded. A process of the SDK keeps them
apart in the same way: the first is its invariant part, and the second is
split into its interface and its task options, each given by a call of its
own (see "Processes"). A description, like a module, defines
processes and one program that adds them, and calls nothing, since the
tool `debasher_build` loads it and writes the program. The one thing the user
does differently is to keep the code of each process in a file of its own
language beside the description, instead of inside the module.

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
- **digest**: as in the design of the web UI: a hash of the topology file
  and of every file it names, which loading returns with the program and
  which a write names back, so that a write over an artifact changed since
  it was loaded is refused (see "The digest of the artifact" in
  `doc/design_doc_webui.md`). The program model that the SDK builds names
  none.
- **reserved name**: as in the design of the web UI: a file or directory
  name that the engine or the web UI manages in a home directory (see
  "Reserved names and user files" in `doc/design_doc_webui.md`).
- **user file**: as in the design of the web UI: a file or directory of the home
  directory whose path has no reserved name, which the user manages through the
  program files panel; the description is one.
- **home directory**: as in the design of the web UI: the directory where
  a program lives, with its artifact, its generated module and its user
  files. The SDK writes a program into one, by default the directory of
  the description.
- **local state**: as in the design of the web UI: what the editor keeps
  on this machine for a program and the artifact does not hold: the lock
  and the output directory, in `.debasher/`. A write of the SDK keeps the
  output directory recorded there.
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
  description, in its own language, which the editor owns: a Bash
  function named as the process, or the whole script of another
  language. It is given to the process as its code (`code=`), and the SDK
  puts its text in the program model when the program is written.
- **script**: the file that holds the code of a process and that the user owns
  (`script=`): the module runs it as it is, the external alias of the engine,
  the editor shows it and never writes it, and it is copied beside the module
  when the program is written elsewhere.
- **external alias**: the `ext_alias` additional specification of the
  engine (the `ext_alias` case of an alias in the design of the engine):
  a file that a process runs as it is, with the interpreter that the
  engine chooses by its extension.
- **source**: what an input of a process reads: the output option of
  another process, given as the option itself or as the name of the
  process and the label of the option, as a module names them in
  `define_opt_from_proc_out`, and given to an input in its task options
  (`connect(...)`). The connections of the program model are derived
  from the sources of the processes it adds.
- **default specifications**: as in the design of the web UI: the `cpus`,
  `mem` and `time` that script generation writes for a process that does not
  give them.
- **specifications of the use**: what a program says about a process when it
  adds it: its computational specifications (`cpus`, `mem`, `time`), its
  explicit dependencies (`processdeps`), whether it is forced (`force`), its
  position on the canvas and, for a node, whether it is an initiator. They
  belong to the program, as the arguments of `add_debasher_process` other than
  an alias do, so that the same process added to two programs can have
  different ones.
- **invariant part**, **interface**, **task options**, **variable
  part**: as in the design of the engine: the groups into which the parts
  of a process fall by what a program that adds it may give otherwise
  than another (see "What a program may give again" in
  `doc/design_doc_engine.md`). In the SDK, the constructor of a process
  takes its invariant part, together with its name, and nothing changes
  it afterwards; `interface(...)` gives its interface, and
  `task_options(...)` its task options, the value of each option of a
  task in one of the kinds of value of the process contract (a literal, a
  connection, the process output directory, a shared directory, an
  attribute of the specifications, a value descriptor, a FIFO) and the
  count of each fanout family (`count=`).
- **received option**: an option that a task of the process receives,
  with its label, its data type and its description, as the constructor
  of the process lists it. A task shaping option, which no task receives,
  is not one; the declared options of the design of the engine include
  both.
- **base directory**: of a process, the directory from which the
  relative paths of its files are taken: that of the Python file that
  creates the process, or the one that `base_dir=` names.
- **library process**: a process created in a Python module of the user
  and imported by the descriptions that add it, which give it its
  variable part.
- **library program**: a program whose processes other programs reuse,
  distributed as its artifact beside its description (see the item on
  library programs in "Future work"). Not to be confused with the library
  of the SDK itself.
- **options handler**: how a process of the program model defines the
  options of its tasks, in one of the options handler modes of the design
  of the web UI: the standard mode, one task from the received options
  (task options without a tasks file); the array mode and the generator
  mode, several tasks shaped by code (`task_options(array=...)`,
  `task_options(generator=...)`); the manual mode, a whole `_define_opts` by
  hand, which the SDK does not offer.
- **tasks file**: the file that shapes the tasks of an array or a generator
  (`array=` or `generator=` of the task options), which the engine runs when it
  prepares a run: in Bash, the code that the editor accepts in the options
  handler of that mode, which builds the array of the tasks or prints their
  number; in Python (`.py`), a Python function file of the engine that defines
  `tasks(run)`, which returns the elements of the array or the number of tasks
  (see "Python function files" in `doc/design_doc_engine.md`). The term is wider
  here than in the design of the engine, where a tasks file is the Python case
  only.
- **method file**: a file with the body of one of the additional methods
  of a process (`skip`, `post`, `reset_outfiles`, `conda_envs`,
  `docker_imgs`), as the editor takes it in its additional methods: a Bash
  body, or, for `skip` only, a skip file.
- **skip file**: as in the design of the engine: a Python function file
  that defines `skip(task)`, which returns whether a task is skipped,
  given as the method file of `skip` (`skip=` with a `.py` path).
- **environments given as data**: the Conda environments of a process, a name
  and a YAML file each (`conda_envs=` given as a dict), and its Docker
  images (`docker_imgs=` given as a list), which the program model keeps
  as data (`condaEnvs`, `dockerImgs`) and from which script generation
  writes the bodies of the `conda_envs` and `docker_imgs` methods.
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
  chooses the Python to run the tool with and runs the Python module
  `debasher.build` as `python -m` does, without the current directory at
  the front of `sys.path` (see "Installation").
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
from debasher import Process, Program, connect, in_outdir, opt

generate = Process("generate", code="generate.sh",
                   description="Generates a text file.",
                   options=[opt("-outf", "file", "output file"),
                            opt("-l", "int", "Length of file in lines")])
generate.interface(cmdline={"-l": "mandatory"})
generate.task_options(values={"-outf": in_outdir("file.txt")})

count = Process("count", code="count.sh", description="Counts characters.",
                options=[opt("-inf", "file", "input file"),
                         opt("-outf", "file", "output file")])
count.task_options(values={"-inf": connect(generate["-outf"]),
                           "-outf": in_outdir("counts.txt")})

prg = Program("count_chars", program_options={"-l": "200"})
prg.add(generate, cpus=1, mem=32, time="00:01:00")
prg.add(count, cpus=1, mem=32, time="00:01:00")
```

## Processes

A process (`Process`, `sdk/python/debasher/process.py`) is defined on its own,
outside any program, as a process of a module is: a program adds it, and the
same process can be added to several programs. Its name follows the rule of the
engine for a process name, parts of letters, digits and underscores separated by
dots, which may not end in a suffix that the engine reserves for a method
(`_define_opts`, `_py`, ...) nor contain the marker `__NSSEP__` of its qualified
names. The SDK checks the name when the process is created, so that an error is
reported at the line that gives the name. It checks it with the same function as
the backend of the web UI (`api/process_names.py`), which does not need FastAPI.
A name that clashes with the module, the name of the program or that name
followed by the suffix of a module method (`prg` or `prg_program` in a program
`prg`), is refused by script generation when the program is written (see "What
script generation refuses" in `doc/design_doc_webui.md`).

A process has the three groups of parts of "What a program may give
again" in `doc/design_doc_engine.md`, each given by a call of its own:

- its invariant part, given to the constructor with the name: its code,
  its description text, the options it receives (label, data type and
  description of each), its environments, and its skip rule, reset rule
  and post hook (see "The invariant part of a process");
- its interface, given by `interface(...)`: the options that come from
  the command line of the run, mandatory or optional, the task shaping
  options, and the FIFOs fed from outside the program, that is, what the
  process receives from outside (see "The interface of a process");
- its task options, given by `task_options(...)`: the shape of its tasks
  and the value of each option of a task (see "The task options of a
  process").

The invariant part is checked at the line that creates the process, except what
needs its files (that each can be read, that a node file fits), which is checked
when the program model is built, and nothing changes it afterwards: an
assignment to it raises `DefinitionError`, and the containers it holds cannot be
changed in place. The interface and the task options are the variable part (the
dependency types, the third piece of it in the engine, are not offered), which a
module holds in methods that a program may define again after loading the module
(see "What a program may give again" in `doc/design_doc_engine.md`): each call
replaces its part whole when it is made again, also on a process that another
Python module creates. Either may be missing when the process is created, as for
a library process of which only the invariant part is given, and be given later:
an interface never given is empty, and what the task options lack is reported by
the checks across the parts when the program model is built. They are two calls
and not one so that the wiring of a process and its interface, which change for
different reasons, are given again apart, and so that what the program receives
from outside, what `debasher_exec` is given, has a call of its own.

## The invariant part of a process

`Process(name, code=, script=, alias=, description=, options=,
alias_opt_map=, base_dir=, skip=, post=, reset_outfiles=, conda_envs=,
docker_imgs=)` creates a process with its invariant part.

Where the code of a process is comes in one of four ways, which the
process may not combine. Two of them name a file, and differ in who owns
it, as the keys `code` and `script` of the topology file do (see "The
process files" in `doc/design_doc_webui.md`): the editor owns a process
file, which it shows in the code box and writes on every save, while the
user owns a script, of which the editor shows a copy and which it never
writes. What else differs follows from that:

- `code=`, a process file: a path, taken from the base directory of the process
  when it is relative (the directory of the Python file that creates the
  process, or the one that `base_dir=` names), whose extension tells the
  language of the process (`.sh` Bash, `.py` Python, `.pl` Perl, `.r` or `.R` R,
  `.groovy` Groovy); an extension that tells no language is refused. A Bash
  process file holds a function named as the process, with its helper functions,
  which the module embeds, with the library of the engine at hand
  (`read_opt_value_from_func_args` and the rest). A file of another language
  holds the whole script, which the module runs as it is, as an external alias
  of the file.
- `script=`, a script: a path to a file that the module runs as it is, the
  external alias of the engine, with the interpreter that the engine chooses by
  its extension; an extension that tells no language is refused, as the engine
  would find no interpreter. A Bash script is a program of its own, which the
  engine runs as `bash <file> "$@"`, without the library of the engine. The
  program model keeps a copy of its text for the editor to show, as import keeps
  it for an imported external alias.
- `alias=`, the name of another process whose code this one runs under
  its own name and options.
- none of them: the code of a process of that name that a module loaded
  by the preamble of the program provides, as for a process of a module
  that adds a process of another.

In a language other than Bash, a process file and a script therefore run
the same way, and only their owner and the path by which the module and
the artifact name them differ (see "Writing the program").
`alias_opt_map=` renames the labels of the options that the process
passes on into those that the code expects, label to label, as the alias
option map of a module does; it goes with a script or an alias only, and
is refused otherwise. An alias, a script and the map are additional
specifications of the engine, given to `add_debasher_process` in a
module, but they name where the body is taken from, and so belong to the
invariant part (see "What a program may give again" in
`doc/design_doc_engine.md`).

The options that the process receives are a list (`options=`) of
`opt(label, type, description)` and `flag(label, description)`, in the order in
which the program model, the module and the editor show them. The label is the
name of the option for the engine, `-` or `--` followed by an ASCII letter or an
underscore, as the engine takes it (the SDK checks it with the function of
`api/process_names.py`, where the rule of a process name is), and is listed once
per process; its direction comes from the label as the engine reads it: an
output is a label that starts with `-out` or `--out`. The data types are those
of the program model: `int`, `float`, `string`, `file` and `dir`, and `None` for
a flag, an option with no value. A label that ends in `-ith` is a fanout family,
which stands for one option per task of the array or generator at the other end
of its connection (`-outf-ith` for `-outf0`, `-outf1`, ...), and whose count the
task options give. An option is reached by its label, `generate["-outf"]`, to
name it as the source of a connection, and a label that the process does not
receive is refused there.

The additional methods of a process are given as method files (`skip=`,
`post=`, `reset_outfiles=`, `conda_envs=`, `docker_imgs=`), each a Bash
body that the editor would take in its additional methods, and go into
the program model as such. The method file of `skip` may be a skip file
instead, by the rule of the extension: `skip(task)` returns `True` to
skip the task and `False` to run it, reading the options of the task
(`task.value("-val-desc")` gives the value that a value descriptor
holds), and the module calls it through `skip_from_file`. A Python file
for any other method is refused, since the engine runs no other method
from one.

The environments of a process may be given as data instead of a body:
`conda_envs={"py27": "py27.yml"}`, the name of each Conda environment
and its YAML file, and `docker_imgs=["ubuntu:24.04"]`, the Docker images
it uses. A path given to either is a method file with the Bash body, as
for the other methods; a dict or a list of the wrong shape (an empty
name or file, an image that is not a string) is refused.

The environments, the skip rule, the reset rule and the post hook belong
to the invariant part because they go with the code. The engine only makes
sure that an environment exists, and the body uses it by its name
(`conda_activate py27`, `"${DOCKER}" run <image>`), so that a program
that changed the environments without the code would leave the body with
an environment that nobody created; what may vary is already outside the
process: whether the environments are created (`conda_support` and
`docker_support` of the program, or the options of `debasher_exec`), and
where a YAML file is taken from (`DEBASHER_YML_DIR`). A body that
activates an environment named by an option gets the name through the
value of the option, in the task options, and gives the environment
with a Bash body. The skip rule reads the options of a task by their
labels, which do not vary (what it reads of an option delivered as a
value descriptor depends on the task options, as for a reader in Bash;
see "The task options of a process"), and the post hook runs in the task after
the body. The reset rule removes what the body creates, whose names the
task options fix (`in_outdir("x.txt")`), so it reads the paths from the
options of the task (`read_opt_value_from_func_args "-outf"`) instead of
writing them by hand, which would break in a program that names the
outputs otherwise.

## The interface of a process

`interface(cmdline=, shaping=, external=)` gives what the process
receives from outside the program, each argument a dict by label:

- `cmdline`, the received options whose value comes from the command line of the
  run, each `"mandatory"` or `"optional"`, a flag `"optional"` only
  (`"mandatory"` on a flag is refused). Nothing else is given for such an
  option: script generation chooses the function of the engine that defines it
  from its data type and whether it is mandatory (`define_cmdline_opt`,
  `define_cmdline_infile_opt`, `define_cmdline_indir_opt`, their `_if_given`
  variants, `define_cmdline_flag_if_given`).
- `shaping`, the task shaping options, each with its data type and its
  description (`{"-w": ("int", "Number of workers.")}`): mandatory
  command line options that the tasks file of an array or a generator
  reads and that no task receives, which is why they are not received
  options and the label of a received option is refused among them. In
  the program model they follow the received options.
- `external`, the received inputs that a FIFO fed from outside the program
  delivers, each with the name of its FIFO (`{"-numbers": "numbers"}`), in a
  resident program only, which the engine checks: the FIFOs that a node owns and
  reads, of the tag `--external` (see "Declaring and owning a FIFO" in
  `doc/design_doc_engine.md`), which is what the program receives during the
  run, as a command line option is what it receives at launch. The FIFOs of the
  tag `--control` are not given: script generation derives them with the rest of
  the Supervisor wiring (see "Resident programs").

A module gives the interface in two methods, `_identify_cmdline_opts` and
`_explain_task_shaping_opts`, and in the tag of an external FIFO in its task
options. It needs two methods only because a task shaping option, which no task
receives, cannot be explained in `_explain_opts`, whose options
`_identify_cmdline_opts` marks. The SDK gives the interface in one call, which
leaves nothing of an older interface behind when a program gives it again, and
which checks the whole: a label is in one argument only, a label of `cmdline` or
`external` is a received input, an external FIFO is given the name of its FIFO,
and a task shaping option is not a received option, is given as its data type
(not a flag) and its description, and has the label of an input. The call
returns the process, as `task_options` does.

## The task options of a process

`task_options(values=, array=, generator=, count=)` gives the shape of the
tasks of the process and the value of each option of a task.

The shape is one task without `array=` and `generator=`, the standard
mode of the options handler. `array=` and `generator=` name a tasks file
and give several tasks, in the array and generator modes, the tasks file
being the code of the options handler as the editor keeps it, in a file
instead of a box: for an array, the code that builds the array of the
tasks (in Bash, under the name `array`), from the command line of the
run and the files present then, after which every option of the process
is defined once per element, with `${task_idx}` and `${array[$task_idx]}`
at hand in its value; for a generator, the code that gives the number of
tasks, the options of each task being defined from `${task_idx}`. The
code of the tasks file runs when the engine prepares a run, not when the
program is built: the tasks depend on the command line of each run,
which a build does not know.

The extension of the tasks file says its language, as the topology file
reads it: a `.py` file is a tasks file in Python, and any other is Bash.
In Python the file defines `tasks(run)`, which returns the elements of
the array, or the number of tasks of a generator, from the command line
of the run (`run.value("-w")`), its process and its process output
directory; the generated module calls it through `tasks_from_file` or
`num_tasks_from_file` of the engine, in the one line that replaces the
Bash. Only the shape of the tasks moves to Python: the definitions of
the options of each task stay those that script generation writes, and
their values the Bash words that reach the element or the index of the
task (`${array[$task_idx]}`, `${task_idx}`).

```python
from debasher import Process, connect, opt, outdir

worker = Process("worker", code="worker.sh",
                 options=[opt("-outd", "dir", "directory of the task"),
                          opt("-inf", "file", "input fifo")])
worker.interface(shaping={"-w": ("int", "Number of workers.")})
worker.task_options(array="worker_tasks.py",
                    values={"-outd": outdir(subpath="${task_idx}"),
                            "-inf": connect(dispatch["-outf-ith"])})

# worker_tasks.py
def tasks(run):
    return range(int(run.value("-w")))
```

`values` gives its value to each received option that is neither on the
command line nor fed from outside, in one of the kinds of value of the
process contract:

- a string, a literal value: a Bash word that the engine expands when the
  option is defined, such as `in_outdir("name")`, which gives
  `${process_outdir}/name`, the path of a file kept in the process output
  directory, or `${process_outdir}` itself with no name. The literal value
  of an input of type `file` or `dir` is a file or a directory shipped
  with the program, which script generation defines as such
  (`define_infile_opt`, `define_indir_opt`). `True` sets a flag in every
  task.
- `connect(source, display="line")`, an input connected to an output of
  another process, given as the option (`generate["-outf"]`) or as the
  name of the process and the label of the option, as a module names them
  in `define_opt_from_proc_out`; a list of sources is a fan-in, and
  `display="label"` draws the connection as a label edge on the canvas.
  The reading of the output of an array task by task
  (`define_opt_from_proc_task_out`) follows from the modes of the two
  processes, and is not given.
- `outdir(subpath="")`, an output that names the process output directory
  of the process, or a task subdirectory of it (the `process_outdir`
  channel, with the subpath a Bash word such as `"${task_idx}"`), for
  another process to read through a connection.
- `shared_dir(name, subpath="", source=None)`, an option whose value is one of
  the shared directories of the program, or a shared subdirectory of it (the
  `shared_dir` channel); its source, if any, checked as that of a connection,
  only draws the sharing on the canvas, since the engine orders the processes by
  the directory itself.
- `procspec(attribute)`, an input whose value is an attribute of the
  specifications of the use of the process, such as `"cpus"`.
- `value_desc()`, an output delivered as a value descriptor that the
  engine synthesizes.
- `fifo(name, mirror=False)`, an option delivered through a FIFO of that
  name (the `fifo` option channel), between two processes of the
  program or opened by the process itself; an output may be mirrored
  into a log file for the canvas to watch.

`count` gives the count of a fanout family, by the label of the family,
as the label of a command line option of the same process
(`{"-ind-ith": "-w"}`); a family without one is counted by the tasks of
the process at the other end of its connection. The rules of a family
(what it may be connected to, which channels it takes) are those of
script generation, which checks them when the program is written.

How an option is delivered belongs to the task options, as in a module,
where `define_value_desc_opt` and `define_fifo_opt` are in
`_define_opts`, and changing it changes what the body receives. A body
writes an output delivered as a value descriptor into the path it gets,
as it would write a plain file (`write_value_to_desc` writes the value
into that path); what changes is what a reader in Bash receives:
`read_opt_value_from_func_args` gives it the value held in the
descriptor, and the path itself for a plain file, so that turning an
output from a descriptor into a file, or back, changes what its readers
in Bash receive. A reader whose body is not Bash, run as an external
alias, receives the path of the descriptor and reads the file itself. An
input connected to a descriptor is a plain connection. A FIFO between two
processes changes the program, both ends at once: the processes run
together, with the dependency type `none`, and no file is left. A body
that writes or reads its data in order works with a file or with a FIFO,
and the condition that the body streams is the user's: neither the SDK
nor the module checks it.

When the program model is built, the parts of each process are checked against
each other, since they may be given in any order: an option on the command line
or fed from outside is not in `values`, every received option is on the command
line, fed from outside or in `values`, task shaping options need an array or a
generator, which alone reads them, and a count names a command line option of
the process. `task_options` itself checks what it can alone: that every label in
`values` and `count` is a received option, that a connection and a specification
attribute are inputs, that the process output directory and a value descriptor
are outputs, that only an output FIFO is mirrored, that a count is given to a
family only and as a label, that a value is a string, `True` or one of the kinds
of value, that `True` is given to a flag only and a flag is given nothing else,
and that `array=` and `generator=` are not both given; `connect` refuses a
display other than `"line"` and `"label"`.

## The program

A program (`Program`, `sdk/python/debasher/program.py`) has a name, which names
its module and its description, and carries what the editor keeps beside the
processes: its description text, the program options (label to value, what "Set
program options" of the editor holds, given to `debasher_exec` by whoever runs
the program), the preamble of the module (Bash before the functions, such as
`load_debasher_module` lines), the environment that the backend gives the tools
of the engine (`env_vars`), the shared directories it declares, and the
execution options of the editor, given by name (`scheduler`, `conda_support`,
`docker_support`, ...). Of `env_vars` only `DEBASHER_MOD_DIR` is read: where to
look for the modules that the preamble loads. A run launched with
`debasher_exec` from the command line does not get it. The name is made of
letters, digits and underscores and starts with a letter or an underscore, since
it names the `_program` method of the module; the endings that a process name
may not have do not apply to it.

`add(process, cpus=, mem=, time=, processdeps=, force=, position=)` (and, for a
node, `initiator=` and the specifications of a node, see "Resident programs")
adds a process with the specifications of its use, as `add_debasher_process`
does in the `_program` method, and returns it. A specification it does not give
is not written into the topology file, and script generation takes the default
specifications for `cpus`, `mem` and `time` (see "From the model to a module:
script generation" in the design of the web UI). A process added twice, or a
process with the name of one already added, is refused. The order of the
processes is the order they are added in, which is the order of the functions in
the module and of the processes in the topology file.

A program does not declare connections: they belong to the task options of the
processes, as in a module, where the `_define_opts` method of a process names
the process and the output it reads. When the program model is built, the
connections in the task options of every process added give the edges, and a
source that names a process the program does not add, an option the process does
not have, or an input, is refused with the names of both ends, for a connection
as for the source of a shared directory.

## Resident programs

A resident program is a `Program` with `resident=True`, which may ask for
periodic snapshots of its runs (`snapshot_every_secs`, the period that
the editor starts once the program is launched), and adds nodes instead
of processes: a `Node`, or the `Supervisor`. It refuses a `Process`, and
a general program refuses a node, when they are added, so that a
description that mixes them is reported at that line rather than by
script generation later.

A `Node(name, code=<node file>, description="", options=[...], base_dir=)` is a
process whose code is a node file, with its invariant part, its interface and
its task options as any process; its node kind is the base class of the one
class of the file that derives from a class of the runtime library
(`FBPProcess`, `ProgramLauncher`, `DirectoryWatcher`). Its ports are its
options: an external port is an input fed from outside the program
(`interface(external=...)`), an output to another node or to the outside is a
FIFO in its task options (`fifo(name)`), and an input from another node is a
connection to the FIFO output of that node. The Supervisor wiring (heartbeat
channels, trigger ports) is never declared: script generation derives it, as for
a program of the editor. A `Supervisor(name, description="", base_dir=)` has no
code and no options of its own, so it refuses an interface and task options;
script generation writes its whole class.

```python
acc = Node("Accumulate", code="accumulate.py",
           options=[opt("-numbers", "string", "numbers written from outside"),
                    opt("-outsum", "string", "the running sum")])
acc.interface(external={"-numbers": "numbers"})
acc.task_options(values={"-outsum": fifo("sum")})
prg.add(acc, initiator=True)
```

The specifications of the use of a node are those of any process plus the
specifications of a node, given to `add` under the names of the engine, and
whether the node is an initiator (`initiator=True`), where a round starts (see
"Rounds and checkpoints" in `doc/design_doc_resident.md`). Whether a node can be
one depends on the program and not on its code, since every other node has to be
reachable from an initiator through the channels of the program, so the same
node may be an initiator in one program and not in another. An unknown name, or
one of them on a process of a general program, is refused, and so is
`initiator=True` on anything but a `Node`, the Supervisor among them.

# From the description to the program model

`Program.to_model()` builds the `Program` of `api/models.py` that `write()`
saves, as the web UI builds it when it loads an artifact: it writes, with
`to_topology()`, the topology file that the editor would save for the program, a
`Topology` of `api/topology.py`, and the texts of the files it names, by their
paths in the artifact (see "Writing the program"), and gives both to
`topology.join`, the code with which the web UI loads a program (see "Loading,
saving and the local state" in `doc/design_doc_webui.md`). The rules of the
translation are therefore those of loading, and a program of the SDK and the
same program loaded from its artifact are the same program model:

- **Ids.** Every id (the program, each process, each option, each
  connection) is a UUID derived from the names (`uuid5` of the program
  name, the process name and the label), so that building the same
  description twice gives the same artifact, and a description kept in a
  repository with its built program gives no spurious diff. The editor
  draws the id of a process it creates at random, and loading assigns
  them from the names (see "The topology file" in
  `doc/design_doc_webui.md`); nothing reads an id as a name.
- **Code.** The process file, the script, the tasks file and the method
  files of a process are read at this moment, and a file that cannot be
  read is refused. A process with no code has an empty one, which script
  generation leaves out, for a loaded module to provide. Every text taken
  from a file goes into the program model without the newlines that end
  it, which is how import keeps the code it reads from a module: the file
  ends with a newline, the code does not, and a program written with the
  SDK and the same program imported from a module hold the same text.
- **Options.** Each received option becomes an option of the process in
  the topology file, in the order of the constructor and followed by the
  task shaping options, with the keys that its kind of value or its place
  in the interface gives it (`value`, `channel`, `subpath`, `mirror`,
  `fifo_tag`, `cmdline`, `mandatory`, `shaping`, `from_spec`,
  `count_source`, and the `display` of a label edge); the sources of a
  connection become the `from` of the input, which loading turns into
  edges.
- **Options handler and methods.** The mode of the task options and the
  path of its tasks file go into `mode` and `tasks`, the method files
  into `methods`, and the environments given as data into `conda_envs`
  and `docker_imgs`; loading takes the language of a tasks file or a
  skip file from its extension.
- **Specifications.** Those of the use go into the `specs` of the process,
  the alias and its map into `alias` and `alias_opt_map`, and a script
  into `script`, as the path that the module will refer to (see "Writing
  the program").
- **Nodes.** The node kind of a `Node` is read from its node file with
  `decompose_heredoc` of the API, the code that import uses on the
  heredoc of a node, and goes into `kind`; loading splits the file into
  the parts of its code, and refuses a node file that the web UI could
  not hold (for example several node classes, a decorator or a second
  base on the class, code after the class other than the line that runs
  it) with the problems that import would report, each with its line,
  when it has one, and the change that would make it fit. The SDK
  refuses a node file that defines a Supervisor, with or without code of
  its own, since the Supervisor is added without a file and gets the node
  kind `Supervisor` and no parts.
- **Positions.** A process added with a position has it. Loading places
  the others as the editor places the processes of an imported program,
  whose module says nothing about positions: in layers by the depth of
  their connections, a process that feeds another above it, the processes
  of a layer side by side in their order in the program (`api/layout.py`:
  the rule of `frontend/src/models/programLayout.ts` ported as it is,
  passes capped at the number of processes so that a cycle through FIFOs
  ends with some layering).

What the SDK checks is what it can know without the engine, at the line of the
user or when the program model is built: names, labels, directions, data types,
the parts of a process against each other, that a source exists and is an
output, that a file can be read. The rest is left to script generation, which
checks it when the program is written and reports it with its own message, the
same as the editor shows (a fanout family badly counted, a channel that a
resident program refuses), or to the engine, which checks it when it loads the
program: the values of the specifications, written as they are given (`time`,
`processdeps`, `batch_sched`, `scheduler`); the process that an alias names; a
shared directory named by an option that the program does not declare; the
attribute that a `procspec` names; and an external FIFO in a general program. A
period of snapshots given to a general program is kept, and read by nobody.

# Writing the program

`Program.write(home_dir)` writes the program into a home directory, as Save does
in the editor, and returns the path of the module. It builds the program model
and gives it to `persistence.save` of the API. `save` generates the module, then
writes the artifact and the module under the lock of the home directory. `write`
then copies the scripts beside the module.

What the SDK, loading, saving or script generation refuses is raised as
`DefinitionError`, the one error of the SDK, and nothing is written then. The
program model is built, and every file of the processes and every script is
read, before anything touches the directory. `save` generates the module and
checks every path of the artifact before it writes.

The files of the artifact are written where the description had them, by the
paths of the process files, the tasks files and the method files relative to the
base directory of each process. A file outside that base directory is written at
the top of the home directory, under its name alone. Each file is written only
when its content differs from the file already at that path: a program written
into the directory of the description leaves its files as they are, and a
program written elsewhere gets a copy of each. Two files whose paths in the
artifact are the same (two files named `post.sh` in two directories outside the
base directory) are refused when the model is built if their texts differ, as
saving refuses them (see "The process files" in `doc/design_doc_webui.md`).
Before anything is written, a file or a script copied beside the module is
refused when its path is that of the module or of the topology file, or holds a
reserved name.

The description is the one place where the program is defined. The program model
that the SDK builds names no digest and no home directory, so `save` takes each
write as a save into another directory and replaces what the artifact holds.
Only the output directory is kept: it is local state, not part of the program,
so `write` gives `save` the one recorded there. A program built from a
description, changed in the editor and built again loses the change made in the
editor, in silence; an editor tab still open on the program gets a conflict on
its next Save (see "The digest of the artifact" in `doc/design_doc_webui.md`). A
change to a program built from a description is made in the description.

The scripts are files of the artifact, and part of its digest, but `write`
copies them after `save` has returned, outside its lock. `save` cannot copy them
itself: it takes every script from the directory that an imported program came
from (`sourceDir`, which the SDK leaves blank), while a script of the SDK is
relative to the base directory of its process. The digest that `save` returns is
thus computed before the scripts are copied: it lacks a script copied for the
first time, and holds the old text of one copied over an older copy. Nothing
uses it: the SDK drops it, and the digest of an artifact is always computed
again from its files when the program is loaded.

The external alias of a process names its script as the path was given, when it
is relative and stays below the base directory of the process
(`./tools/dispatcher.py` is written as it is), or the name of the script alone
when the path contains `..` (`../shared/tool.py` becomes `tool.py`); the engine
resolves it against the directory of the module, so the script is copied beside
the module under that same path, replacing an older copy, and the program
written is self-contained, as the home directory of the editor is. A script in
the home directory itself is never copied onto itself. An absolute path is
written as it is and the script is not copied: the engine takes it with a
warning about portability, which is the user's choice.

Script generation needs `debasher_get_proc_info` of the engine for one
thing only, to leave out the code of a process that a module loaded by
the preamble already provides; without the tool every process is written
with its code, which is right for a description with no preamble. The
SDK tells the API where the tools are (see "Finding the API and the
engine").

# The tool: `debasher_build`

The tool (`sdk/python/debasher/build.py`) has three forms:

```
debasher_build <description>.py [-o <dir>]
debasher_build [<home directory> | <home directory>/program.yaml]
debasher_build --schema
```

The first builds a description. It is the equivalent of Save in the editor, and
it is where `write()` is called: a description calls nothing, as a module calls
nothing. The second builds a program again from its artifact. The third prints
the JSON Schema of the topology file. In the first two, the path of the module
is printed on success, and an error of the SDK is printed to standard error with
the prefix `debasher_build:`, and the tool exits with status 1.

**Building a description.** The tool loads the description, finds the program it
defines and writes it:

- The tool executes the description inside the tool's own Python process, as an
  import would (`exec_module`), not as `python <name>.py` would run it: the file
  is loaded under its own name as the name of the module, so its `__name__` is
  not `"__main__"` and a block guarded by it does not run, and what the tool
  needs are the objects it leaves among its global names. While it runs, the
  directory of the description is first on `sys.path`, so that it can import
  files beside it.
- Among its global names there has to be exactly one `Program`; none or several
  is an error.
- The description is named after its program, as a module is named after the
  program it defines (`align_all.py` defines `Program("align_all")`), since the
  name of the program is the name of the module and the editor looks for
  `<name>.sh`. A mismatch is an error that names both and says how to make them
  agree: rename one of them, or only the file when its name cannot name a
  program (`hello-world.py`).
- The program is written into the directory of the description unless `-o` names
  another: beside the description and the process files, which is the home
  directory as the editor keeps it, with the user files of the program beside
  the artifact.

**Building again from the artifact.** Given a home directory, its topology file,
or nothing (the current directory), the tool loads the program saved there and
saves it back as it is:

- That writes the module again and leaves the artifact as it was; a topology
  file not in the form the backend writes is written again in that form. A
  program kept in a repository as its artifact is thus built without the editor:
  this is the regeneration tool of the artifact (see "The doors and the
  regeneration tool" in `doc/design_doc_webui.md`).
- `-o` goes with a description only.
- The tool refuses a home directory that holds a file `<name>.py`, named after
  its program, that the artifact does not name (a process file of that name is
  named, and does not stop the build). Such a file is usually the description of
  the program, and a build from the artifact would ignore a change made to it,
  in silence; the error says how to build the description instead. In a program
  made in the editor it is a user file, which has to be renamed.

Running the program is then the same as for any program:
`debasher_exec --pfile <name>.sh --outdir <dir> ...`, `debasher_status`,
or the Run of the editor once the home directory is opened in it. The
description is never run with `python` nor given to `debasher_exec`, and
a change to it is followed by another `debasher_build`.

## The examples

Five descriptions ship under `data/sdk_programs/python/`, installed
under `sdk_programs/python` of `$(pkgdatadir)`, one directory per program
with the description named after it and the files of its processes
beside it:

- `sdk_hello_world_py`, the hello world of the quickstart with its
  process in Python;
- `sdk_dynamic_fanout_fifos`, a generated file cut into fragments that a
  dispatcher, run as a script, streams through FIFOs to an array of
  workers whose tasks a tasks file in Python shapes;
- `sdk_running_sum`, a resident program with a node given as a file and
  a Supervisor;
- `sdk_skip_py`, the skip example of the engine: a process sums two
  numbers into a value descriptor, and another, skipped by its skip file
  when the sum is odd, writes the sum plus one;
- `sdk_conda_envs`, a process that activates a Conda environment given
  as data and writes the version of its Python.

Each is the twin of a program saved under `data/webui_programs/`, which the
tests check by writing each example as its twin and comparing the programs
loaded from both and the module (see "Guarantees"). `make installcheck` builds
each example from its installed directory with `debasher_build` into a directory
of its own and runs the program built as it runs the others (`sdk_skip_py` with
an odd sum, checking that the skipped process wrote nothing), or skips them all
when the Python of `debasher_build` lacks the dependencies of the SDK, and
`sdk_conda_envs` without conda, as it skips the other checks of conda.

# Installation, and finding the API and the engine

## Installation

The library is the package `debasher` in `sdk/python/debasher`, and
`sdk/python/Makefile.am` installs it as a Python package, with
`pkgpython_PYTHON`, into `$(pkgpythondir)`, which is `$(pythondir)/debasher`,
the directory that automake reserves for the Python package of the project. What
makes `import debasher` work is `$(pythondir)` on `sys.path`. When the prefix of
the installation is that of the Python itself (a virtual environment, a conda
environment with its Python), `$(pythondir)` is its `site-packages` and
`import debasher` works with nothing more; otherwise the user puts
`$(pythondir)` in `PYTHONPATH`. The conda package, whose Python directory is one
of its own under the prefix of the environment, puts it in `PYTHONPATH` when the
environment is activated, through a script in its `activate.d`
(`conda/build.sh`). The library needs the dependencies of the API of the web UI
(pydantic 2, `api/requirements.txt`), as the web UI does.

The tool is the launcher `debasher_build`. `make` builds it from
`sdk/python/debasher_build.sh`, with the directories of the installation in
front, as `api/Makefile.am` builds `debasher_webui`, and installs it in
`bindir`. The launcher:

- chooses the Python as `debasher_webui` does: the one that
  `DEBASHER_WEBUI_PYTHON` names, else `python3` on the `PATH` (that of an
  activated environment), else the Python of `configure`;
- stops, and prints what to install, when that Python lacks pydantic 2, instead
  of failing inside the library;
- puts `$(pythondir)` in `PYTHONPATH`, and, when it runs from the source tree,
  its own directory, where the package is, in front of it, so that a description
  imports `debasher` without the user setting anything;
- runs the Python module `debasher.build` as `python -m` does
  (`runpy.run_module`), but without the current directory at the front of
  `sys.path`, where `python -m` puts it. A description named as a Python module
  that the SDK imports (`debasher.py`, `yaml.py`), built from its own directory,
  would otherwise be imported in place of that module, and the tool would fail
  before it reads the description.

**The files beside a description.** While the tool loads a description, it puts
the directory of the description first on `sys.path`, so a description imports
the files beside it: `import helpers` for a file `helpers.py` in its own
directory. The exception is a file named as a Python module that the tool has
already loaded: the SDK (`debasher`), `api`, `yaml`, `pydantic` and their
dependencies, and the Python modules of the standard library that they use
(`json`, `argparse` and others). Python takes it from the Python modules already
loaded and does not look for it again, so `import api` in a description gets the
API of the web UI, not the `api.py` beside it, in silence. Such a file needs
another name. A file named as a Python module of the standard library that is
not loaded yet, such as `csv.py`, is imported in place of that module, as in any
Python program.

## Finding the API and the engine

The library builds on the API of the web UI, the package `api`, which is
installed as data under `$(pkgdatadir)/api`, not as a Python package:
`debasher_webui` imports it by putting `$(pkgdatadir)` in `PYTHONPATH`. The
library does the same on import (`sdk/python/debasher/_paths.py`): when `api` is
not importable already, it appends the root of the repository to `sys.path` when
the library is in a source tree (found from its own file), else the package data
directory that the installation module names.

The installation module, `debasher/_install.py`, is written by `make` from the
directories of the installation (`pkgdatadir`, `bindir`, `libexecdir`,
`pythondir`) and installed with the package. It is not a source, and git ignores
it. `make` writes it into the build directory: in a build in the tree that is
the source tree, so the source tree lacks it only before the first `make`, or
when the build is out of the tree. In a source tree the library does not need it
to find `api`, since the root of the repository is tried first.

The API finds the tools of the engine through the environment variables that
`debasher_webui` sets for it (`DEBASHER_WEBUI_BIN_DIR`,
`DEBASHER_WEBUI_LIBEXEC_DIR`, `DEBASHER_WEBUI_PYTHON_DIR`), or, without them, in
the source tree. The library sets the same variables from the installation
module when they are not set and the directories exist, so that script
generation finds `debasher_get_proc_info` in an installation as it does under
the web UI.

Nothing of the library imports the routers of the API or FastAPI. It uses:

- `api.topology` for the topology file, its loading and the languages of the
  extensions;
- `api.persistence` to save the program;
- `api.script_generation` for the names of the specifications of a node;
- `api.process_names` for the rules of a process name and of an option label;
- `api.resident_node_code` for the node kind of a node file and the parts it
  splits it into.

# Guarantees and non-goals

## Guarantees

- **What the editor saves.** A description written with the SDK gives the
  program that the editor would save for the same program, apart from
  the ids, the digest and home directory of the save and the names of the
  files of the artifact, and the module that script generation writes
  from it, byte for byte: the five examples of
  `data/sdk_programs/python/`, written as their twins, are compared in
  the tests with `webui_hello_world_py`, `webui_dynamic_fanout_fifos`,
  `webui_running_sum`, `webui_skip_py` and `webui_conda_envs` of
  `data/webui_programs/` (see "The examples").
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
- **Nothing half written.** A program refused by the SDK, by saving or by
  script generation leaves the home directory as it was.

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
  no task created by the SDK: what the engine does with the module it
  does for a program of the SDK as for any other. A tasks file or a skip
  file in Python is run by the engine, through its own functions, when
  the module would run the Bash it replaces.
- **Bash where the engine reads Bash.** What the engine itself takes as
  Bash stays Bash in a description: the preamble of the program; the
  value of an option, a Bash word that the engine expands when the
  option is defined (`${process_outdir}/name`, `${array[$task_idx]}`),
  so that the per-task values of an array or a generator are Bash words
  even when a Python function shapes the tasks; and the bodies of `post`
  and `reset_outfiles`, the last until the program model has a field for
  it (see "Future work"). `post` runs inside the task after the process
  and belongs with the code of the process, which may be in any
  language.
- **The manual mode.** A whole `_define_opts` written by hand, the
  manual mode of the options handler of the editor, is not offered: it
  is the method of a module, and a description that needs it is a
  module.
- **Subprograms.** A description does not add the processes of another
  module with `add_debasher_program`, and the SDK does not produce the
  groups of the editor (an "Add program" that script generation writes
  back as one `add_debasher_program` call). A description reuses the
  processes of another description as it uses any Python object: it
  imports them, gives each its interface and its task options, and adds
  it, which covers a program made only of the processes of another (the
  library programs distributed apart, and the namespaces that such reuse
  lacks, are in "Future work").

# Future work

- **The reset rule as data.** The files that a process
  removes before a rerun are data (a list of paths) that the editor and
  the SDK carry as a Bash body because the program model has no field
  for them. When the program model gives them one, as it does for the
  environments, the SDK takes them as an argument and script generation
  writes the body.
- **Sequential processes.** The code that a process runs as a step with
  `seq_execute`, with a name and specifications of its own (see
  "Sequential processes" in `doc/design_doc_engine.md`), is not offered
  by the SDK. The program model already holds it (`seqProcesses`, see
  "Sequential processes in the program model" in the design of the web
  UI) and script generation already writes it, so the SDK would only
  translate it, as one more object of a description beside its
  processes: a name, a file with its code and the specifications that
  the engine accepts on it.
- **Library programs.** Processes meant for reuse are distributed as a
  library program: a description with its processes and a program that uses
  them, which serves as its example and holds its tests, built and
  distributed as its artifact (the topology file, the files of its processes
  and its generated module) beside its description. A program reuses the
  processes of a library program as a module reuses those of another: its
  preamble loads the module of the library program (`load_debasher_module`,
  found through `DEBASHER_MOD_DIR`), its description imports the processes
  for their invariant part and gives each its interface and its task
  options, the process takes its code from the loaded module, and nothing of
  the library program is copied into the program. A library program is thus
  one more program, not a new kind of artifact, and it is found by name
  along a search path: today as a module, and, once the engine reads the
  artifact itself instead of the generated module, as an artifact. It
  replaces the copy of the files of a library process into the home
  directory of the program, which the SDK writes there by their paths
  relative to the base directory of the process: a copy written again by
  every build looks editable and is not, and two files of library processes
  that land on one path of the artifact with different texts are refused
  (see "Writing the program"). Left open: how the topology file of a program
  refers to a library program (a line of its preamble, or a key of its own);
  how a run from the command line finds it (today only through a
  `DEBASHER_MOD_DIR` that the user sets); what the module of the program
  writes for a library process (only its variable part, defined again after
  the module of the library program is loaded); how the editor shows a
  library process (read only, as a process of a loaded module); how a Python
  package carries the description and the built artifact, and checks that
  both come from the same source (a digest of the description); and how
  `debasher_build` treats a description that imports the program of a
  library program beside its own.
- **Namespaces of library processes.** A process defined in a Python module of
  the user is added to several programs as a process of a loaded module is, but
  gets no namespace. The namespace of DeBasher is a naming convention kept in
  the program model, where the dotted name is what the engine and every other
  door see, while a namespace of Python exists only while the description runs:
  the relation is a projection when the program model is built, and a library
  process gets its prefix from an explicit namespace object, never from the path
  of the Python module that defines it, which is a detail of the installation
  and not a name.
- **Processes as decorated functions.** A Python function in the
  description itself, whose source the build extracts to a process file,
  for a process too small for a file of its own.
