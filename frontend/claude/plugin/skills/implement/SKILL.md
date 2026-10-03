---
name: implement
description: >-
  Write the code of the processes of a DeBasher program, and their business
  tests, through the MCP tools: from the code prompt of each process, one
  process at a time, running the tests until they pass. Use when the user
  wants processes filled in, fixed, or tested.
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
   wrong output.
4. **Write a test.** `add_test` writes the skeleton of a business test into
   `test/` (bats for a process of a general program, pytest for a node). Read
   it with `read_program_file`, fill in its TODOs with a real check of what
   the process does, put any input data it needs under `test/` with
   `write_program_file`, and remove the line that makes the test fail on
   purpose only once the test checks something.
5. **Run the tests** with `run_tests`. When one fails, read the report, fix
   the code or the test, whichever is wrong, and run them again. Stop and ask
   the user after a few failed rounds instead of going around in circles.

Show the user the code and the test of each process as you finish it, briefly.

## Running the program

Once the processes have code, `validate_program` checks the whole program
without running it. Running it (`run_program`) writes into its output
directory and may take long: offer it, and run it only when the user agrees.
Follow a run with `get_status`, and read what a process left with
`get_process_output` when something fails.

If a tool refuses a save because the program changed on disk, the user (or
another tab) saved it meanwhile: read the process again and work from what is
there.
