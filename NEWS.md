# DeBasher news

## 2.0 (unreleased)

DeBasher 2.0 adds resident programs, a web interface and support for macOS
and Windows (through WSL2), and makes the engine stricter about programs
that were accepted before but did not do what they said. A module written
for 1.0 needs changes to run on 2.0: they are listed below, with how to
make each one.

### Incompatible changes

#### Modules

- **Documentation functions renamed.** `process_description` is now
  `document_process`, and `module_description` is now `document_module`.

- **Constants of the engine prefixed.** The constants that a module reads
  carry the `DEBASHER_` prefix: `OPT_NOT_FOUND` is now
  `DEBASHER_OPT_NOT_FOUND`, and `SHUTDOWN_TOKEN` is now
  `DEBASHER_SHUTDOWN_TOKEN`. The old names are not defined anymore, so a
  test such as `[ "${str}" = "${OPT_NOT_FOUND}" ]` compares against an
  empty string and silently takes the wrong branch.

- **Every option a process defines has to be explained.** The
  `<process>_explain_opts` method declares each option of the process,
  with `explain_opt` (or `explain_flag`), and defining an option that it
  does not declare is an error. Every process needs the method, even one
  with no options (`<process>_explain_opts() { :; }`), and
  `add_debasher_process` refuses a process without it. In 1.0,
  `<process>_explain_cmdline_opts` declared only the options given on
  the command line, and options connected to other processes (`-inf`,
  `-outf`, ...) went undeclared. `<process>_explain_cmdline_opts` and
  `explain_cmdline_opt` still work, but are deprecated.

- **Command-line options are declared as such, and required unless said
  otherwise.** `<process>_identify_cmdline_opts` says which of the
  explained options come from the command line: `opt_is_cmdline` for a
  required one, `opt_is_non_mandatory_cmdline` for an optional one.
  `explain_cmdline_req_opt` is gone, since required is now the default.
  A command-line option has to be defined from the command line
  (`define_cmdline_opt`, `define_cmdline_opt_if_given`, ...): defining
  it with `define_opt` from a value computed in the module is an error.
  A default value for an optional option moves to the process itself,
  which checks for `DEBASHER_OPT_NOT_FOUND`.

- **Functions removed from the public interface.** `read_value_from_desc`
  (use `read_opt_value_from_func_args`, which already reads a value
  descriptor) and `read_fifo_line` (read the fifo directly, with
  `IFS= read -r line < "${fifo}"`). The helpers of the engine that
  1.0 exposed without a prefix, such as `get_absolute_path`,
  `file_exists` or `log_err_msg`, are now internal, under the
  `debasher::` namespace, and a module that called them has to use its
  own code instead.

- **Fifos.** A fifo has one reader: a second process reading the same fifo
  is an error, instead of hanging the run. Two tasks of an array defining
  a fifo of the same name is an error too. A program that uses fifos is
  refused on Slurm, since the two ends of a fifo only meet on the same
  machine; use the built-in scheduler.

- **Option names.** An option name is a dash or two followed by a letter
  or an underscore, so a negative number (`-n -5`) is now read as a value.
  A flag and an option given an empty value are told apart: an empty
  value reaches the process as an empty value, not as a flag.

- **Steps in other languages.** `seq_execute` and `seq_execute_slurm`
  run only functions and commands: a variable that holds the code of a
  step in another language (`transformation_b_py`) is not run anymore.
  Give the code in a `<name>_heredoc_py` (or `_r`, `_perl`, `_groovy`)
  function and declare the step in the `_program` method with
  `add_debasher_seq_process <name> "<specs>"`, which turns it into a
  function of that name; the same works for an `alias` or an
  `ext_alias`.

- **Cycles of modules.** Modules that load each other, and a module that
  loads itself, are an error that names the cycle, instead of loading
  forever.

#### Command-line tools

- `debasher_exec --reexec-outdated-procs` is now `--rerun-outdated-procs`.
- `debasher_doc_mod --show-cmdline-opts` is replaced by `--show-opts`,
  among other `--show-*` options.
- `debasher_exec` and `debasher_launch_process` refuse an output
  directory whose run was made in another place, since its options and
  scripts hold absolute paths into the directory where it was.
- `debasher_status`, `debasher_stop` and `debasher_stats` read the
  processes of a run from its output directory, not from the current
  version of its module. A `-p` naming a process that the program does
  not have is an error, and `debasher_status -p` counts only that process
  for its exit code.
- `debasher_get_sched_out` fails when the file it is asked for does not
  exist, as `debasher_get_stdout` already did.
- The standard output of a process goes to its `.stdout` file only, on
  every scheduler, and no longer also into the scheduler log on Slurm.
- `--builtinsched-cpus` and `--builtinsched-mem` take `-1` for no limit,
  as documented now; `0` made the scheduler abort.

#### Installation

- `debasher_lib` and the other libraries of the engine are installed
  under `<prefix>/lib/debasher/` instead of `<prefix>/bin/` and
  `<prefix>/libexec/`.
- `debasher_fifo_writer_loop` and the branch-and-bound and genetic
  knapsack solvers are no longer installed.
- The configure option `--disable-schedulers` is removed: the scheduler
  is chosen when a program runs (Slurm when `sbatch` is in the `PATH`).
- Reconfiguring the package needs only autoconf and automake, not libtool
  nor autoconf-archive.

### New

- Resident programs: long-running programs of Python nodes that exchange
  data through fifos, with a Supervisor, input logs and snapshots, and
  the tools `debasher_stop_resident`, `debasher_reset_resident`,
  `debasher_snapshot_resident` and `debasher_inspect_resident`.
- A web interface (`debasher_webui`) to build, import, save and run
  programs on a canvas, with example programs under
  `<prefix>/share/debasher/webui_programs`.
- Mirror taps (`define_fifo_opt --mirror`) and `debasher_get_fifo_mirror`,
  to watch the data flowing through a fifo.
- `debasher_exec --validate`, which checks a program without running it,
  and `--builtinsched-oneshot` for programs made only of fifos.
- `--watch` in `debasher_get_stdout`, `debasher_get_sched_out` and
  `debasher_get_fifo_mirror`.
- `debasher_stop` also stops the `debasher_exec` that schedules a run, so
  that nothing is launched after it.
- Flags (`define_flag`, `explain_flag`), options defined from a shared
  directory (`define_opt_from_shared_dir`) and alias processes that rename
  the options of their target (`alias_opt_map`).
- Sequential processes (`add_debasher_seq_process`): code that a
  process runs as a step with `seq_execute`, in any language or through
  an alias, and that under Slurm asks `srun` for resources of its own.
  `mark_step_done` and `is_step_done` let a process skip the steps that
  an earlier run finished.
- Tested on Linux, on macOS and on Windows under WSL2 in continuous
  integration, with a Docker image for trying the web interface and a
  conda recipe.
