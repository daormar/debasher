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
  directory holds the program metadata (`.debasher/program.json`, which only
  the tools change), the generated script `<name>.sh`, and the user files,
  such as `test/`. A run writes into the output directory (`outputDir`).
  `create_program` starts an empty program in a new home directory, and
  `import_module` makes one from an existing DeBasher module (a `.sh` file).
- **The generated script is never edited by hand.** Every save writes it
  again from the program metadata, so a change made to it is lost: change
  the code of a process with `update_process` instead.
- **Preamble.** Bash code at the top of the generated script, mostly
  `load_debasher_module "<module>"` lines, which bring in the processes that
  other modules define: the library (`search_library`, `get_library_process`;
  `add_process` with a library name brings its options and code). Modules are
  looked for in the directories of the `DEBASHER_MOD_DIR` environment
  variable, set among the environment variables of the program.
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
  run, by label; setting them replaces them all.
- **Shared directories.** Named directories created once before any process
  runs, which processes reach without a connection.
- **Sequential processes** (general programs only): code that a process runs
  itself as a step (`seq_execute`), never scheduled on its own. Needed only for
  special cases (non-Bash steps inside a Bash process, aliases); prefer
  processes.

## Processes

- **Name.** Letters, digits and `_`, starting with a letter or `_`; may be
  namespaced with dots (`org.ns.name`). Unique, ignoring case, among processes
  and sequential processes.
- **Language.** `bash`, `python`, `perl`, `r` or `groovy`.
- **Code.** In Bash, the whole function `name() { ... }`, called with the
  option list of its task: read a value with
  `local x=$(read_opt_value_from_func_args "-label" "$@")`, a flag with
  `read_flag_from_func_args "-label" "$@"`, use `local` variables and
  `return 0` on success. In another language, a whole program run by its
  interpreter, which gets the options as command-line arguments, exits 0 on
  success and has no line that is `EOF` alone. Code still holding the marker
  `# ADD YOUR CODE HERE` of a template counts as not written. An output option
  holds the path (file or FIFO) to write to; standard output goes to a task
  file that no other process reads. `get_code_prompt` gives the exact rules
  for a given process: follow it.
- **Options handler mode.** `standard`: one task. `array`: one task per
  element of a Bash array named `array`, which `arrayCode` builds; option
  values may use `${task_idx}`, its index, and `${array[$task_idx]}`, its
  element. `generator`: one task per index below the count that
  `generatorSizeCode` prints; option values may use that index,
  `${task_idx}`. `manual`: the whole option definition written by hand
  (general programs only). When both ends of a connection have several tasks,
  task i reads task i.
- **Number of tasks taken from another process.** When a process has as many
  tasks as another one (each task reads the task with the same index), its
  options handler asks for that number with `get_process_num_tasks
  "<process>"` instead of computing it again with the rule of the other
  process, which two copies could apply differently. A `generator` may ask any
  process; an `array` only a process in `generator` mode.
- **The options handler runs more than once.** The engine calls the code of
  a generator again whenever it needs the options of a task, inside the task
  too, so a file or directory that it reads (such as one given on the command
  line to count the tasks) has to stay unchanged while the run lasts.
- **Specifications.** `computationalSpecs` (`cpus`, `mem` in MB, `time`);
  `additionalSpecs` (general programs only): `force` to rerun in every run,
  `processdeps` to replace the dependencies inferred from the connections
  (`afterok:<process>`, several joined by `,` when all have to hold or by
  `?` when one is enough; the types are `after`, `afterok`, `afternotok`,
  `afterany` and `aftercorr`, the last one task by task between two
  processes of several tasks), and aliases (`alias`, `externalAlias`,
  `aliasOptMap`), which take the code of the process from another one.
- **Additional methods** (general programs only), bodies of optional
  functions: `skipCode` (return 0 to skip a task; never on a process at
  either end of a FIFO), `condaEnvsCode`, `dockerImgsCode`, `postCode`,
  `resetOutfilesCode`, `outdirBasenameCode`.

## Options

- **Label** starting with `-`, unique in its process. A label starting with
  `-out` is an output; any other is an input.
- **dataType**, the type of the data that the option carries: `int`,
  `float`, `string` (the default), `file`, `dir`, or `None` for a flag
  (always an input, on channel `none`). An input of type `file` or `dir`,
  given on the command line or as a value, has to name an existing regular
  file or directory, and the engine makes its path absolute.
- **channel**, how the data gets to the process: `none` (a value or a
  connection; the process receives the data itself), `fifo` (`value` is the
  name of the FIFO), `value_desc` (an output into which the task writes a
  value), `shared_dir` (`value` names a shared directory), `process_outdir`
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
  Bash word, such as `10` or `${task_idx}`); `commandLine` (from the program
  options); or `fromProcessSpec` (on a `standard` process, never on an output:
  `value` names a specification, `cpus`, `mem`, `time`, ...). The last two
  take no connection.
- `taskShaping`: a mandatory command-line input with a value that only the
  options handler reads (the code that builds the array or counts the tasks),
  to decide the tasks; no task receives it, so the code of the process cannot
  read it, and it cannot be the `countSource` of a fanout family.
- `mandatory`; `mirror` (a FIFO output keeps a copy readable without taking
  data from the reader; general programs only); `fifoTag: "external"` (a FIFO
  input of a resident program fed from outside).
- **Fanout family.** On a `standard` process, a label ending in `-ith`
  (`-outf-ith`) stands for `-outf0`, `-outf1`, ..., as many as the command-line
  option named by `countSource` says; it connects only to an array or
  generator process, one option per task.

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
  one reader, both ends on the same machine, and no Slurm.
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
  wins); both are absolute paths. Each message on `-outdone` is
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
  depends on one of them runs again too. A change to the code of a process
  that finished does not make it run again, unless `rerunOutdatedProcs` is
  set, which then runs again every process that finished before the
  generated script was last written (every save writes it) or a module that
  it loads changed. A task whose dependencies can no longer hold (`afterok`
  on a process that failed) is cancelled and counts as failed. To start from
  scratch, empty the output directory with `reset_output_dir`.
- `get_process_output` reads what a process left (`stdout`, `scheduler`,
  `options`, `resolved_options`), task by task (`get_process_tasks`) for a
  process of several tasks.
- Editing tools apply their edits whole or not at all; `dry_run` answers with
  what would change and saves nothing. `addProcess` (and `add_process`)
  takes the fields of the process (`description`, `language`, `code`,
  `optionsHandler`, ...) inside `changes`, as `updateProcess` does; only
  `name`, `nodeKind`, `options` and `position` go beside it. A save is
  refused when the program changed on disk since it was read (the user may
  be editing it in the web UI): read it again and work from what is there.
