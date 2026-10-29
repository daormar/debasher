# DeBasher for an agent working through the MCP tools

DeBasher builds workflows ("programs") out of processes, functions with named
input and output options; the way options connect defines what runs when. The
web UI shows a program as a canvas (a box per process, an edge per connection)
and saves it into its home directory; the MCP tools of the `debasher` server
read and change that saved program with the same rules as the editor. Every
tool takes the home directory as `home_dir`.

Documentation: https://debasher.readthedocs.io/en/latest/ (the web UI:
https://debasher.readthedocs.io/en/latest/webui.html; how the pieces combine
for the usual shapes of a program, such as a chain of steps for each entry of
an input or a pool of workers:
https://debasher.readthedocs.io/en/latest/design_patterns.html).

## Programs

- **Type.** `general` (the default) or `resident`, chosen when the program is
  created and never changed. A general program works on a batch: each process
  runs once its inputs are ready, and ends. A resident program works on a
  stream: long-lived, stateful Python nodes joined by FIFOs, possibly in
  cycles, always on one machine.
- **Home directory and output directory**, which must differ. The home
  directory holds the saved program: the topology file `program.yaml`
  (the processes, their options, their connections and their
  specifications; the tools, the editor and `debasher_build` write it, a
  change made to it by hand is seen by the editor, and its first line names
  the JSON Schema of the file, which `debasher_build --schema` prints), one
  file per process
  with its code, which the topology file names (`count.sh` for a Bash
  process `count`, a function named as the process; `dispatch.py` for one
  in Python, the whole script; `<process>_tasks.sh` for the code of the
  options handler of an array or a generator, or `<process>_tasks.py` for
  a Python tasks file; `<process>_<method>.sh` for an additional method, or
  `<process>_skip.py` for a skip method in Python; the extension of a tasks
  file or a skip file says its language, `.py` Python and any other Bash,
  and the tasks file of a manual process and the other method files are
  always Bash; a whole class file for a node; those are the names
  chosen when a file is first written, `program.yaml` is what says which
  file holds the code of a process, a renamed process keeps its file, and a
  Bash process named as its program gets `<process>_process.sh`, since
  `<name>.sh` is the generated script), the generated
  script `<name>.sh`, the user files, such as `test/`, and, in
  `.debasher/`, what the editor keeps for this machine. A program saved by
  an older version holds `.debasher/program.json` instead, which the next
  save replaces. A run writes into the output directory (`outputDir`).
  `create_program` starts an empty program in a new home directory,
  `import_module` makes one from an existing DeBasher module (a `.sh`
  file), and `debasher_build`, outside the tools, writes one from a Python
  description, or writes the generated script of a saved program again.
- **The code of a process is a file.** The file that the topology file
  names holds the code of the process, and nothing else does: change it
  with `update_process`, or as a file with `write_program_file` or any
  editor; the editor of the web UI sees the change and loads it, or asks
  the user when the tab holds unsaved changes. The topology itself (the
  options, the connections, the specifications) is changed with the tools,
  which keep the editor in step, or by hand in `program.yaml`, whose keys
  are described one by one in
  https://debasher.readthedocs.io/en/latest/api_program_yaml.html.
- **The generated script is never edited by hand.** Every save writes it
  again from the saved program, so a change made to it is lost: change the
  code of a process instead. `debasher_build` given the home directory or
  its `program.yaml`, or run in the home directory with no argument, writes
  it again too: that is how a program kept in a repository as its
  `program.yaml` and process files is built, and how the script follows a
  change made to `program.yaml` by hand.
- **Programs described in Python.** A home directory that holds `<name>.py`
  beside `<name>.sh` was written by `debasher_build` from that file, a
  description of the Python SDK: the processes, their options and their
  connections are defined there, and the code of each process is in the
  file the description names, the same file that the topology file names,
  so a change to the code of a process, or to its tasks file or a method
  file, with `update_process` or as a file, is a change to what both read.
  The topology is another matter: a save, from the tools or the editor,
  changes `program.yaml` and leaves the description as it was, and the next
  `debasher_build <name>.py` writes `program.yaml` again from the
  description, so a change made with the tools to the options, the
  connections, the specifications, the Conda environments and Docker images
  given as data (`conda_envs=`, `docker_imgs=`), or the language of a tasks
  file or a skip file (which file `tasks=` or `skip=` names), is lost then.
  Change the topology of such a program in its description, and have it
  built again with `debasher_build <name>.py` in the home directory (no
  tool runs it; the file is never run with `python` nor given to
  `debasher_exec`), then read it again. How a description is written:
  https://debasher.readthedocs.io/en/latest/implem_python.html; every class
  and method of the SDK:
  https://debasher.readthedocs.io/en/latest/api_sdk.html.
- **Preamble.** Bash code at the top of the generated script, mostly
  `load_debasher_module "<module>"` lines, which bring in the processes that
  other modules define: the library (`search_library`, `get_library_process`;
  `add_process` with a library name brings its options and code). Modules are
  looked for in the directories of the `DEBASHER_MOD_DIR` environment
  variable, set among the environment variables of the program. The modules
  a program loads have names (file names without `.sh`) different from each
  other and from the name of the program, since the generated script
  `<name>.sh` is loaded as a module too.
- **Program fields** (`set_program_settings`, or the `setProgramFields` edit):
  `name`, `description`, `preamble`, `sharedDirs`, `outputDir`,
  `executionOptions` and `programOptions`; the environment variables, such
  as `DEBASHER_MOD_DIR`, are set with the `env_vars` of
  `set_program_settings` or the `setEnvVar` edit.
- **Execution options.** `scheduler` is `BUILTIN` (the default, on this
  machine) or `SLURM`; `builtinSchedCpus` and `builtinSchedMem` bound the
  built-in scheduler; `dfltThrottle` bounds the tasks of an array running at
  once; `condaSupport` and `dockerSupport` enable the environments that
  processes declare; `rerunOutdatedProcs` runs again the processes that
  finished before the last change of the generated script (see "Running and
  following").
- **Program options.** The values of the command-line options for the next
  run, by label; setting them replaces them all. An empty value leaves the
  option out, as not given. A value cannot start with `-` or `--` followed by
  an ASCII letter or `_` (a negative number can): the engine refuses it and
  the run does not start.
- **Shared directories.** Named directories created once before any process
  runs, which processes reach without a connection.
- **Sequential processes** (general programs only): code that a process runs
  itself as a step (`seq_execute`), never scheduled on its own. Its steps run
  in the shell of the task, whatever the scheduler of the run, unless its
  `sched` is `SLURM`, which sends them through `srun` with its
  `computationalSpecs` (used only then). Call `seq_execute` from a process,
  and set `sched` to send its steps to Slurm rather than calling
  `seq_execute_slurm`, which sends a step to Slurm whatever its `sched` and
  refuses one whose `sched` is `BUILTIN`. A
  program with `sched` `SLURM` runs only where `srun` is found, and on the
  Slurm scheduler the step takes its resources from the job of the task that
  calls it. Needed only for special cases (non-Bash steps inside a Bash
  process, aliases, a heavy step sent to Slurm); prefer processes.

## Processes

- **Name.** Letters, digits and `_`, starting with a letter or `_`; may be
  namespaced with dots (`org.ns.name`). Unique, ignoring case, among processes
  and sequential processes.
- **Language.** `bash`, `python`, `perl`, `r` or `groovy`.
- **Code.** In Bash, the whole function `name() { ... }`, called with the
  option list of its task: read a value with
  `local x=$(read_opt_value_from_func_args "-label" "$@")`, a flag with
  `read_flag_from_func_args "-label" "$@"`, use `local` variables and
  `return 0` on success. In another language, a whole program, the process
  file that `program.yaml` names, which the engine runs with its interpreter
  (`python3 <file>`) and the options as command-line arguments; it exits 0
  on success and may import a module beside it in the home directory. Code
  still holding the marker
  `# ADD YOUR CODE HERE` of a template counts as not written. An output option
  holds the path (file or FIFO) to write to; standard output goes to a task
  file that no other process reads. `get_code_prompt` gives the exact rules
  for a given process: follow it.
- **Options handler mode.** `standard`: one task. `array`: one task per element
  of a Bash array named `array`, which `arrayCode` builds; option values may use
  `${task_idx}`, its index, and `${array[$task_idx]}`, its element. `generator`:
  one task per index below the count that `generatorSizeCode` prints; option
  values may use that index, `${task_idx}`. The code of an array or a generator
  may instead be a Python tasks file (`optionsHandler.language` `python`) that
  defines `tasks(run)`, which returns the elements of the array or the number of
  tasks; the module calls it with `tasks_from_file` or `num_tasks_from_file`,
  and its code (`arrayCode`, `generatorSizeCode`) is the whole file. `run` holds
  the command line of the run, read with `run.value(label)` or
  `run.value(label, default)` (`None` or the default when not given or
  without a value), `run.given(label)` for a flag and `run.args`, and
  `run.process` and `run.outdir`; an array returns a list or another iterable of
  strings, numbers or paths, a generator an integer, 0 or more. The values of
  the options of each task stay Bash words (`${task_idx}`,
  `${array[$task_idx]}`), and relative paths are taken from the directory where
  `debasher_exec` runs. The rules, for `skip(task)` too:
  https://debasher.readthedocs.io/en/latest/implem_bash.html#the-tasks-in-python;
  the objects `run` and `task`, member by member:
  https://debasher.readthedocs.io/en/latest/api_sdk.html#python-functions-of-a-process.
  `manual`: the whole option definition written by hand (general programs only),
  always Bash. The code defines the function `<process>_define_opts`, or the
  pair `<process>_generate_opts_size` and `<process>_generate_opts` of an option
  generator; a process with neither stops the preparation of the run. Define an
  option marked `commandLine` with `define_cmdline_opt`
  (`define_cmdline_infile_opt` for a file, `define_cmdline_indir_opt` for a
  directory, the `_if_given` variant for one that is not mandatory), never with
  a value of its own, or the preparation of the run stops; for a value derived
  from it, read it with `get_cmdline_opt` and define another option that is not
  `commandLine`. When both ends of a connection have several tasks, task i reads
  task i.
- **Number of tasks taken from another process.** When a process has as many
  tasks as another one (each task reads the task with the same index), its
  options handler asks for that number with `get_process_num_tasks
  "<process>"` instead of computing it again with the rule of the other
  process, which two copies could apply differently. Any process may ask any
  other, once per handler, keeping the number in a variable. Asking a
  `generator` is cheap (its size code runs); asking an `array` or a `manual`
  process that is not defined yet runs its whole option definition again, in a
  subshell, so when other processes need the number of tasks of a process,
  make that process a `generator` if it can be one. A chain of such questions
  that comes back to the asking process stops the preparation of the run. A
  Python tasks file cannot ask (`get_process_num_tasks` is Bash): such a
  handler is written in Bash.
- **The options handler runs more than once.** The size code of a generator (or
  its `tasks(run)`) and the code of an array run while the run is prepared,
  again, in a subshell whose result is thrown away, when another process asks
  for the number of tasks before the process is defined; the option definitions
  of a task of a generator (the Bash words built on `${task_idx}`) run again
  inside the task. A file or directory that either reads (such as one given on
  the command line to count the tasks) has to stay unchanged while the run
  lasts, so that the number of tasks is the same every time.
- **Specifications.** `computationalSpecs` (`cpus`, `mem` in MB, `time`;
  each one a process leaves unset is 1, 256 and `01:00:00` respectively,
  except in a sequential process, which keeps only those it gives);
  `additionalSpecs` (general programs only): `force` to rerun in every run,
  `processdeps` to replace the dependencies inferred from the connections
  (`afterok:<process>`, several joined by `,` when all have to hold or by
  `?` when one is enough; the types are `after`, `afterok`, `afternotok`,
  `afterany` and `aftercorr`, the last one task by task between two
  processes of several tasks; it replaces every inferred dependency, so it
  lists every one the process needs. The preparation of the run stops at an
  empty element, at two dependencies on the same process that no run of it
  satisfies together in a list joined by `,` (`afternotok` with `afterok` or
  with `aftercorr`), and at any type but `after` between processes linked by
  FIFOs, in a list joined by `,` or by `?` alike), and aliases (`alias`,
  `externalAlias`, `aliasOptMap`), which take the code of the process from
  another one. The
  target of `alias` needs a process function when the alias is added: a
  Bash process (of the program or of a module of the preamble) always has
  one, but a process in another language, or another alias, has one only
  once it is added, so such a target has to come before the alias in the
  program (every process comes before the sequential processes).
- **Additional methods** (general programs only), bodies of optional
  functions: `skipCode` (return 0 to skip a task, 1 to run it, any other
  status fails it; never on a process at either end of a FIFO),
  `condaEnvsCode`, `dockerImgsCode`, `postCode`, `resetOutfilesCode`,
  `outdirBasenameCode`. The skip method may instead be a Python skip file
  (`skipLanguage` `python`) that defines `skip(task)`, which returns `True`
  to skip the task and `False` to run it, its code (`skipCode`) the whole
  file; `task.value(label)` reads an option of the task as
  `read_opt_value_from_func_args` does (the value that a value descriptor
  holds), and anything but `True` or `False`, or an exception, fails the
  task. A Python tasks file or skip file runs with the Python of DeBasher,
  not in the Conda environment or Docker image of the process. The Conda
  environments and Docker images may be data instead of bodies: `condaEnvs`
  (a name and a YAML file each) and `dockerImgs`, `conda_envs:` (name: file)
  and `docker_imgs:` (a list) in `program.yaml`, or `conda_envs=` and
  `docker_imgs=` in a description, from which script generation writes the
  `define_conda_env` and `pull_docker_img` calls; a process gives either the
  data or the body, never both, and import turns a body made only of those
  calls into data.

## Options

- **Label** starting with `-`, unique in its process. A label starting with
  `-out` is an output; any other is an input. A change of label that changes
  the direction drops the connections of the option.
- **dataType**, the type of the data that the option carries: `int`,
  `float`, `string` (the default), `file`, `dir`, or `None` for a flag
  (always an input, on channel `none`). An input of type `file` or `dir`,
  given on the command line or as a value, has to name an existing regular
  file or directory, and the engine makes its path absolute.
- **channel**, how the data gets to the process: `none` (a value or a
  connection; the process receives the data itself), `fifo` (`value` is the
  name of the FIFO), `value_desc` (an output into which the task writes a
  value), `shared_dir` (`value` names a shared directory that the program
  or a module of its preamble declares; any other name stops the preparation
  of the run), `process_outdir`
  (an output: the output directory of the process, `value` empty). Through a
  FIFO or a value descriptor the process receives a path, and the data type
  is that of each line of the FIFO, or of the value held (a FIFO of `int`
  carries an integer per line); in Bash, `read_opt_value_from_func_args` on
  an input that reads a value descriptor gives the value, not the path.
- **Fixed data types.** A directory channel (`shared_dir`,
  `process_outdir`) has data type `dir`, and a connected input has the data
  type of the output it reads, and follows it. An edit that names another
  data type for such an option is refused; leave the field out.
- **subpath**: with `shared_dir` or `process_outdir`, a directory of the
  task's own below that directory, a Bash word such as `${task_idx}`, which
  the engine creates; below the output directory it is also emptied before
  each task, so the same code works with one task and with many. A task writes
  only into its own subdirectory. To gather the results of every task, read
  them through a fanout family, one option per task, or read the whole shared
  directory and give the dependency in `processdeps`, since the engine infers
  none from a whole shared directory.
- **Where an input's value comes from**: a connection; a literal `value` (a
  Bash word, such as `10` or `${task_idx}`, which once expanded cannot start
  with `-` or `--` followed by an ASCII letter or `_`, nor hold a newline: the
  engine refuses it and the preparation of the run stops); `commandLine` (from
  the program options: the task receives the value given, made absolute for a
  `file` or a `dir`; for a value derived from one, the options handler of an
  `array` or `manual` process computes it into another option that is not
  `commandLine`); or `fromProcessSpec` (on a `standard` process, never on an
  output: `value` names a specification, `cpus`, `mem`, `time`, ...). The last
  two take no connection.
- `taskShaping`: a mandatory command-line input with a value that only the
  options handler reads (the code that builds the array or counts the tasks),
  to decide the tasks; no task receives it, so the code of the process cannot
  read it, and it cannot be the `countSource` of a fanout family.
- `mandatory`; `mirror` (a FIFO output keeps a copy readable without taking
  data from the reader; general programs only); `fifoTag: "external"` (a FIFO
  input of a resident program fed from outside).
- **Fanout family.** On a `standard` process, a label ending in `-ith`
  (`-outf-ith`) stands for `-outf0`, `-outf1`, ..., as many as its count
  source says; it connects only to an array or generator process, one option
  per task. The count source is the command-line option named by
  `countSource`, or, without one (`countSource: ""` takes it away), the
  number of tasks of the process at the other end of its connections (the
  one that an input family reads, the only one that reads an output family),
  an array or a generator: prefer it to gather or feed the tasks of a
  generator, since no option then has to match that number by hand. It works
  for an array too, at the cost of running its option definition again when it
  is not defined yet. Without `countSource`, the task does not receive the
  count, and its code counts the options of the family among its arguments.

## Connections

- From an output to an input (`connect`, `disconnect`); an input takes one
  connection, except `shared_dir` options naming the same directory, whatever
  their subpaths.
- **A connected input** is declared with channel `none` and no value
  (`shared_dir`, naming the directory, when it reads a shared directory):
  the channel of the output says how the data travels, so in a FIFO
  connection only the output has channel `fifo`. An input on another channel
  takes no connection, and an edit that moves a connected input to one is
  refused. In a resident program the connection is what makes an input a
  business input.
- **A file connection** makes the reader wait until the writer finished
  (`afterok`, or task by task between two processes of several tasks). Use it
  for batch steps, results that have to stay, steps that may be skipped or run
  again, and Slurm.
- **A FIFO connection** adds no wait: both processes run at once and the reader
  streams until the writer closes. Use it to stream, to run steps
  concurrently, or for a cycle, which needs at least one FIFO edge. A FIFO has
  one reader, both ends on the same machine, and no Slurm. Processes linked
  by FIFOs (the two ends of a FIFO, or two processes of a chain of FIFOs,
  which run together too) depend on each other only with `after` or not at
  all, or the preparation of the run stops: a process never reads a file of a
  process linked to it by FIFOs (that file gives `afterok`), so stream it
  through a FIFO too, or let another process read the file.
- **FIFOs between processes of several tasks.** The FIFOs that the tasks of
  a process declare through one option are read inside the program for every
  task or for none: a reader with fewer tasks than the writer would leave the
  extra writers blocked, so the preparation of the run stops instead. Give
  the reader the number of tasks of the writer with `get_process_num_tasks`.
- **How the canvas draws it** (`display` of `connect`, or
  `set_connection_display`): a line, or a label edge, a stub at each end that
  names the other. Use a label edge for a connection whose line would cross
  others; it changes nothing in what runs.

## Resident programs

- **Node kinds** (`nodeKind`, needed by `add_process` unless the node comes
  from the library): `FBPProcess` (a business node), `ProgramLauncher` (runs a
  general program for each request), `DirectoryWatcher` (sends the files that
  appear in a directory), `Supervisor` (at most one, with no code, relaunching
  nodes that are down). A new `DirectoryWatcher` comes with `-watchdir` (the
  directory to watch, from the command line) and the output port
  `-outrequests`, and a new `ProgramLauncher` with the input `-requests`
  (any input takes requests) and the output port `-outdone`. The classes look
  for `-watchdir`, `-outrequests` and `-outdone` by name (`WATCH_DIR_OPTION`,
  `REQUESTS_PORT`, `DONE_PORT`), so do not rename them; give their fields as
  options with the same labels. A watcher without `-outrequests` or a launcher
  without an input runs but does nothing, and says so in a warning notice. A
  launcher puts its run directories in its output directory, unless its class
  sets `RUNS_ROOT` or it has the option `-runsdir` (`RUNS_ROOT_OPTION`, which
  wins); both are absolute paths. The program it launches can come from the
  options `-pfile` and `-process` (data type `string`, not `file`) instead of
  `PFILE` and `PROCESS` in the class body. Each message on `-outdone` is
  `{"run", "run_dir", "status", "exit_code"}`, so a node that reads the
  results of a run takes its directory from `run_dir`.
- **Node code** (`nodeCode`, bodies without their `def` line): `preamble`
  (imports, helpers), `classBody` (attributes, `__init__` with the initial
  state, helper methods), `processData` (`process_data(self, port_name,
  packet)`), `captureNodeState`, `restoreNodeState`, `initializeRuntime`, and
  the optional `observe`. An `FBPProcess` defines the first four hooks; the
  other kinds inherit them, and a body replaces the inherited one (call
  `super()` to keep it).
- **Rules of the hooks.** Send only from `process_data`, with
  `self.send_data(port, payload)`, as JSON; `process_data` is deterministic;
  the node state is complete and serializable as JSON; effects outside the
  program are idempotent. Read options from `self.opts` (labels without the
  dash), log with `self.log`, wait with `self.sleep()`.
- **Methods that a node calls**, on top of `send_data` and `sleep`:
  - `self.inject(payload)`, from `observe`: `observe` looks at the world
    outside (a directory, a queue) on a thread of its own, every
    `OBSERVE_INTERVAL_SECS`, and brings what it sees in as a message that
    `process_data` receives on the port that `OBSERVE_PORT` names;
    `self.observe_now()` makes it look at once.
  - `self.set_notice(text, level="info")` (`level` is `info` or `warning`)
    and `self.clear_notice()`: a message of the node for whoever watches the
    program, such as that its configuration file is missing. A node has at
    most one notice, and a new one replaces it; any hook or thread may set
    it. It is not part of the node state and every start of the node begins
    without one, so a notice that follows from the state is set again in
    `restore_node_state`.
- **Class attributes** tune a node (`OBSERVE_PORT`,
  `OBSERVE_INTERVAL_SECS`, `NOTICE_MAX_CHARS`, ...) and configure the
  `DirectoryWatcher` (`WATCH_DIR`, `PATTERN`, ...) and the
  `ProgramLauncher` (`PFILE`, `MAX_CONCURRENT_RUNS`, ...). The code prompt of
  a node (`get_code_prompt`) carries the reference of every hook, method and
  class attribute of its class, read from the installed runtime library:
  look there for one that this list does not name.
- **Specifications of a node.** Besides `cpus`, `mem` and `time`, a node
  takes limits in its `computationalSpecs` (`input_log_max_mb`,
  `out_backlog_max_mb`, `out_backlog_fail_mb`, `gil_switch_interval_ms`,
  `startup_timeout_s`), a `ProgramLauncher` also `max_concurrent_runs` and
  `batch_sched`, and the `Supervisor` only `heartbeat_timeout_s` and
  `startup_timeout_s`; unset, a limit keeps the default of the class. A node
  has no additional specifications and no additional methods.
- **Rounds and snapshots.** A snapshot is a round started by an initiator
  (`initiator: true`), which every node checkpoints; a program of independent
  parts needs an initiator in each. After a crash a node resumes from its
  checkpoint and replays its input log. The Supervisor wiring (heartbeats,
  triggers) is generated, not edited.
- **Running.** Always the built-in scheduler; `run_program` waits for the
  launch and resumes the saved program state; `stop_program` stops in order;
  `snapshot`, `inspect_node`, `restart_node` and `reset_program_state` act on
  its state. `restart_node` kills a live node, as in a crash, and has it
  relaunched from its last checkpoint; `relaunch_node` relaunches a node
  that is down in a program without a Supervisor.
- **Notices of a live program.** `get_status` lists the notices of the
  nodes, and `inspect_node` (`summary`) the one of a node. The canvas marks
  a node that has one, an "i" in a blue circle for `info` and an "!" in an
  amber triangle for `warning`, with the text in its tooltip; the mark is
  dimmed while the node does not run.
- **Talking to a live program.** An external input (`fifoTag: "external"`)
  and a business output with no connection are written and read from
  outside with `list_fifos`, `write_fifo` and `read_fifo`, in resident
  programs only.

## Business tests

- `test/*.bats` (processes of a general program) and `test/test_*.py` (nodes)
  in the home directory, run by `run_tests`, which saves the program first.
- `add_test` writes a skeleton: in bats, it runs the process with
  `run debasher_process <name>` and checks its status; in pytest, it loads the
  node with `load_node`, feeds it and checks what it sent. Its `TODO`s are to be
  filled in with real checks, and the line under the comment "remove the line
  below, which makes a skeleton fail" (`false`, or `pytest.fail(...)`) removed
  once they are.

## Running and following

- `validate_program` saves the program, then checks everything but launching
  the processes, and the program options.
- `run_program` saves and launches the program in its output directory; a
  general program runs in the background (follow it with `get_status`:
  `in-progress`, `finished`, `unfinished`; a resident one is `new`, `live` or
  `stopped`). A run is in progress from the moment `debasher_exec` starts
  preparing it, maybe before any process runs. `stop_program` stops it.
- **While a run or a validation is in progress** in the output directory,
  saving, running, validating, running the tests and resetting the output
  directory are refused: wait for it to end, or stop it.
- **Running a general program again on the same output directory** resumes
  it: it launches what did not finish (for an array, the tasks that did not
  finish) and leaves alone what finished, except a process with `force`, one
  whose options changed, one at the other end of a FIFO from a process that
  runs again, and one that ran (under `after`, `afterany`, or `afterok`
  joined by `?`) after a process that did not finish; every process that
  depends on one of them runs again too. Such a process runs whole: for an
  array, every task, also those that finished. A change to the code of a
  process that finished does not make it run again, unless
  `rerunOutdatedProcs` is set, which then runs again every process that
  finished before the generated script was last written (every save writes
  it) or a module that it loads changed. A task whose dependencies can no
  longer hold (`afterok` on a process that failed) is cancelled and counts
  as failed; under the built-in scheduler, so is a task that still waits when
  the run can launch nothing else and nothing runs, whose marker says so.
  To start from scratch, empty the output directory with
  `reset_output_dir`.
- `get_process_output` reads what a process left (`stdout`, `scheduler`,
  `options`, `resolved_options`), task by task (`get_process_tasks`) for a
  process of several tasks.
- Editing tools apply their edits whole or not at all; `dry_run` answers with
  what would change and saves nothing. `addProcess` (and `add_process`)
  takes the fields of the process (`description`, `language`, `code`,
  `optionsHandler`, ...) inside `changes`, as `updateProcess` does; only
  `name`, `nodeKind`, `options` and `position` go beside it. A save is
  refused when the program changed on disk since it was read (the user may
  be editing it in the web UI, or a file of the program was edited): read it
  again and work from what is there.
- **The user and the editor.** The tools see the program as saved, never the
  unsaved changes of a tab of the editor: when the user names something that is
  not there, ask them to save it (Save in the toolbar). A tab without unsaved
  changes loads what the tools save on its own; one with unsaved changes shows a
  banner instead, where "Save mine over it" discards what the tools saved.
  Claude Code may run in the terminal panel at the bottom of the editor, which
  the backend of the web UI starts: reloading or closing that tab, "Close" in
  the toolbar, or stopping `debasher_webui` ends the session (the conversation
  is kept, and starting a session from "Claude Code..." in the Help menu, with
  "Continue the last conversation", takes it up), so say so before suggesting
  any of them.
