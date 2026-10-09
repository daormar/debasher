# DeBasher for an agent working through the MCP tools

DeBasher builds workflows ("programs") out of processes, functions with named
input and output options; the way options connect defines what runs when. The
web UI shows a program as a canvas (a box per process, an edge per connection)
and saves it into its home directory; the MCP tools of the `debasher` server
read and change that saved program with the same rules as the editor. Every
tool takes the home directory as `home_dir`.

Documentation: https://debasher.readthedocs.io/en/latest/ (the web UI:
https://debasher.readthedocs.io/en/latest/webui.html).

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
  processes declare.
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
- **Specifications.** `computationalSpecs` (`cpus`, `mem` in MB, `time`);
  `additionalSpecs` (`force` to always rerun, `processdeps` to replace the
  inferred dependencies, aliases).
- **Additional methods**, bodies of optional functions: `skipCode` (return 0
  to skip a task; never on a process at either end of a FIFO), `condaEnvsCode`,
  `dockerImgsCode`, `postCode`, `resetOutfilesCode`, `outdirBasenameCode`.

## Options

- **Label** starting with `-`, unique in its process. A label starting with
  `-out` is an output; any other is an input.
- **dataType**: `int`, `float`, `string` (the default), `file`, or `None` for a
  flag (always an input).
- **channel**: `none` (a value or a connection), `fifo` (`value` is the name of
  the FIFO), `value_desc` (an output into which the task writes a value, which
  a reader gets as the value rather than a path), `shared_dir` (`value` names a
  shared directory).
- **Where an input's value comes from**: a connection; a literal `value` (a
  Bash word, such as `10` or `${task_idx}`); `commandLine` (from the program
  options); or `fromProcessSpec` (`value` names a specification: `cpus`,
  `mem`, `time`, ...). The last two take no connection.
- `taskShaping`: a mandatory command-line input with a value that only the
  options handler reads (the code that builds the array or counts the tasks),
  to decide the tasks; no task receives it, so the code of the process cannot
  read it, and it cannot be the `countSource` of a fanout family.
- `mandatory`; `mirror` (a FIFO output keeps a copy readable without taking
  data from the reader; general programs only); `fifoTag: "external"` (a FIFO
  input of a resident program fed from outside).
- **Fanout family.** On a `standard` process, a label ending in `ith`
  (`-outfith`) stands for `-outf0`, `-outf1`, ..., as many as the command-line
  option named by `countSource` says; it connects only to an array or
  generator process, one option per task.

## Connections

- From an output to an input (`connect`, `disconnect`); an input takes one
  connection, except `shared_dir` options naming the same directory.
- **A file connection** makes the reader wait until the writer finished
  (`afterok`, or task by task between two processes of several tasks). Use it
  for batch steps, results that have to stay, steps that may be skipped or run
  again, and Slurm.
- **A FIFO connection** adds no wait: both processes run at once and the reader
  streams until the writer closes. Use it to stream, to run steps
  concurrently, or for a cycle, which needs at least one FIFO edge. A FIFO has
  one reader, both ends on the same machine, and no Slurm.
- **How the canvas draws it** (`display` of `connect`, or
  `set_connection_display`): a line, or a label edge, a stub at each end that
  names the other. Use a label edge for a connection whose line would cross
  others; it changes nothing in what runs.

## Resident programs

- **Node kinds** (`nodeKind`, needed by `add_process` unless the node comes
  from the library): `FBPProcess` (a business node), `ProgramLauncher` (runs a
  general program for each request), `DirectoryWatcher` (sends the files that
  appear in a directory), `Supervisor` (at most one, with no code, relaunching
  nodes that are down).
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
- **Rounds and snapshots.** A snapshot is a round started by an initiator
  (`initiator: true`), which every node checkpoints; a program of independent
  parts needs an initiator in each. After a crash a node resumes from its
  checkpoint and replays its input log. The Supervisor wiring (heartbeats,
  triggers) is generated, not edited.
- **Running.** Always the built-in scheduler; `run_program` waits for the
  launch and resumes the saved program state; `stop_program` stops in order;
  `snapshot`, `inspect_node`, `restart_node` and `reset_program_state` act on
  its state.
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
  `stopped`).
- `get_process_output` reads what a process left (`stdout`, `scheduler`,
  `options`, `resolved_options`), task by task (`get_process_tasks`) for a
  process of several tasks.
- Editing tools apply their edits whole or not at all; `dry_run` answers with
  what would change and saves nothing. A save is refused when the program
  changed on disk since it was read (the user may be editing it in the web
  UI): read it again and work from what is there.
