---
name: review
description: >-
  Review the code of the processes of a DeBasher program, and their business
  tests, and give the user findings ranked by how much they matter: does the
  code do what its description says, follow the rules of the engine, fail on
  bad input, and do its tests check anything. Use when the user asks for a
  review, for feedback on code that is written, or for what could go wrong.
  Changes nothing.
---

# Reviewing the code of the processes

You review the code of the program in the current directory, and its tests,
and report what you find. You change nothing: fixing what you find is the work
of the `/debasher:implement` skill, once the user asks for it.

Read `${CLAUDE_PLUGIN_ROOT}/reference/concepts.md` first if you have not read
it in this session.

## What to read

- The program with `get_program`, to know what each process is for and how
  its options connect; then each process to review with `get_process`, which
  gives its code. Review the processes the user names, or all of them.
- The code prompt of each process, with `get_code_prompt`: the rules of the
  engine for its language and its options. It is the standard the code is
  held to.
- Its tests, with `list_program_files` and `read_program_file`
  (`test/<process>.bats`, or `test/test_<node>.py` for a node).

Do not run the tests or the program unasked: both save the program and run
its code. Offer to run the tests when what they do matters to a finding.

## What to look for

- **What it does.** Does the code do what the description of the process
  says? Is something described left undone, or done that is not described?
- **Its options.** Does it read every input option and write every output
  option? Does it use the values as the code prompt says (Bash:
  `read_opt_value_from_func_args`, `local` variables, `return 0`; another
  language: the arguments its template parses, and no line that is `EOF`
  alone)? Is an optional option handled when it is left out? Does it treat
  each option as what it receives, the data itself or the path of a FIFO, a
  value descriptor or a directory, and the data as of the type declared?
- **Failure.** On bad or missing input, does it fail with a non-zero status,
  or write a wrong output and succeed? Does it check what a command it calls
  returns?
- **Connections.** Does a process that writes a FIFO close it when it is
  done, and one that reads a FIFO read it to its end? Does it write its
  outputs where its options say, and nothing outside its output directory
  and the shared directories its options name?
- **Several tasks.** In array or generator mode, does each task use its own
  values (`${task_idx}`), and write only into its own subdirectory, never
  into the outputs of the others? Does an options handler that needs the
  number of tasks of another process ask for it with
  `get_process_num_tasks` rather than count it again with a copy of its
  rule, and does a generator read only inputs that stay unchanged during
  the run?
- **Nodes** of a resident program: is `process_data` deterministic, does it
  send only from there, is the node state complete and serializable as JSON,
  and are effects outside the program idempotent? Does it wait with
  `self.sleep()` rather than `time.sleep()`, look at the outside world only
  in `observe` (bringing it in with `inject`), and set again in
  `restore_node_state` a notice that follows from the node state? Does a
  directory watcher or a launcher leave `-outrequests` and `-outdone` to its
  class, and does a node that reads the results of a batch run take its
  directory from `run_dir` rather than build it again from a runs root of
  its own, which breaks silently once the two differ?
- **Its tests.** Is there a test? Does it check the outputs, the edges of the
  input and a failure, or only that the process ended? Are `TODO`s or the line
  that makes a skeleton fail still there?
- **Readability**, last: names, dead code, what could be simpler. Mention it
  only when it is worth the user's time.

## How to report

- Findings ranked by how much they matter: first what makes the program
  wrong, then what makes it fragile, then the rest. For each, the process, the
  lines of code it is about, what goes wrong in a small example, and what to
  change.
- Say what is right as well when the code is sound, in a sentence; do not
  invent findings to fill the report.
- End by offering to fix the findings the user chooses, with
  `/debasher:implement`.
