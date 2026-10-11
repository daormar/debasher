---
name: implement
description: >-
  Write the code of the processes of a DeBasher program, and their business
  tests, through the MCP tools: from the code prompt of each process, one
  process at a time, running the tests until they pass; or add tests to code
  that already exists, without changing it. Use when the user wants processes
  filled in, fixed, or tested.
---

# Writing the code of the processes and their tests

You write the code of the processes of the program in the current directory,
and a business test for each, through the MCP tools of the `debasher` server.
The structure of the program (processes, options, connections) is the work of
the `/debasher:design` skill: if it is missing or wrong, say so instead of
reshaping it here.

Read `${CLAUDE_PLUGIN_ROOT}/reference/concepts.md` first if you have not read
it in this session.

## For each process

Work on one process at a time, in the order of the data, and tell the user
which one you start with.

1. **Read what it is.** `get_process` gives the process with its options,
   description and current code.
2. **Ask for the code prompt.** `get_code_prompt` composes, from the program
   as saved, what the code has to follow: the rules of the engine for that
   language, the options and where their values come from, the connections,
   and the form of the answer. Follow it; it is more precise than anything
   here. Use its `part` for the code of an options handler or of an
   additional method when that is what is missing.
3. **Write the code** with `update_process`. Keep it small and readable, and
   make it fail loudly (a non-zero exit) on bad input rather than produce a
   wrong output. Read each option as what the code prompt says it receives:
   the data itself, or the path of a FIFO, a value descriptor or a
   directory. In a node, use the methods of the runtime library that the
   code prompt lists rather than writing your own: `self.sleep()` for the
   pace, `inject` from `observe` for what it sees outside, and
   `set_notice` for what whoever watches the program should know (a
   missing configuration file), set again in `restore_node_state` when it
   follows from the node state. A directory watcher or a launcher needs
   little code or none: its class sends on `-outrequests` and `-outdone`, so
   the code never does. A node that reads the results of a batch run takes
   the run directory from `run_dir` in the message on `-outdone`, rather than
   building it again from a runs root of its own.
4. **Write a test.** `add_test` writes the skeleton of a business test into
   `test/` (bats for a process of a general program, pytest for a node). Read
   it with `read_program_file`, fill in its TODOs with a real check of what
   the process does, put any input data it needs under `test/` with
   `write_program_file`, and remove the line that makes the test fail on
   purpose only once the test checks something. See "What a test checks"
   below.
5. **Run the tests** with `run_tests`. When one fails, read the report, fix
   the code or the test, whichever is wrong, and run them again. Stop and ask
   the user after a few failed rounds instead of going around in circles.

Show the user the code and the test of each process as you finish it, briefly.
When the user wants an opinion on code that is written rather than changes,
that is the work of the `/debasher:review` skill.

## Testing code that already exists

When the user asks for tests of processes whose code is written, the code is
what is tested, not what is changed:

- Read the process and its code with `get_process`, and the tests it has with
  `list_program_files` and `read_program_file`. `add_test` refuses a file that
  exists: add tests to an existing file by writing it whole with
  `write_program_file`, keeping the tests that are there.
- Test what the description of the process says it does, and what its code
  does with its options; when the two disagree, say so rather than choose.
- When a test fails, find out whether the test or the code is wrong. A wrong
  test is yours to fix. Wrong code is reported to the user, with the failing
  test as the evidence, and changed only if they ask: leave the failing test
  in place meanwhile, and say that it fails.

## What a test checks

A business test runs one process on its own, outside any run, so it is the
unit test of the process. A test that only checks that the process ended with
status 0 proves little. Aim for:

- **Every output.** Read each file the process writes (or, for a node, each
  port it sends on) and compare it with what is expected, exactly when it can
  be computed.
- **The edges of the input.** Empty input, a single element, values at the
  limits, names with spaces; and an option left out when it is not mandatory.
- **Failures.** Bad input that must make the process fail, with a non-zero
  status (`[ "${status}" -ne 0 ]`), rather than write a wrong output.
- **Several tasks.** For a process in array or generator mode, run it as one
  task would be run, with the option values of that task.
- **Nodes.** Feed a few packets and check what was sent; keep the restart
  test of the skeleton, which checks that the node state is complete.
- **Its own data.** Inputs written by the test under `${BATS_TEST_TMPDIR}`, or
  small files under `test/`, never files outside the home directory.

A test is finished only when no `TODO` of its skeleton is left, and the line
that makes a skeleton fail on purpose is gone.

## Running the program

Once the processes have code, `validate_program` checks the whole program
without running it. Running it (`run_program`) writes into its output
directory and may take long: offer it, and run it only when the user agrees.
Follow a run with `get_status`, and read what a process left with
`get_process_output` when something fails.

A run on an output directory that holds an earlier run resumes it, and does
not run again a process that finished, even when its code changed since:
after fixing the code of such a process, say so, and offer to set
`rerunOutdatedProcs` among the execution options or to empty the output
directory (`reset_output_dir`, which deletes everything in it, so only when
the user agrees). While a run or a validation is in progress, saving and
running are refused: wait for it to end.

If a tool refuses a save because the program changed on disk, the user (or
another tab) saved it meanwhile: read the process again and work from what is
there.
