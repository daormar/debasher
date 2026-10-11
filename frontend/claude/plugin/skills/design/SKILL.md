---
name: design
description: >-
  Design a DeBasher program with the user: which processes it has, their
  options and how they connect (files or FIFOs, general or resident), and
  build that on the program through the MCP tools, laid out on the canvas.
  Use when the user wants to create a program, add or restructure processes,
  or decide how data flows. Does not write the code of the processes.
---

# Designing a DeBasher program

You design the structure of the program in the current directory with the
user, then build it through the MCP tools of the `debasher` server, which save
it into its home directory; the editor of the web UI, if open on it, loads
what you save. You do not write the code of the processes: that is the work of
the `/debasher:implement` skill.

Read `${CLAUDE_PLUGIN_ROOT}/reference/concepts.md` first if you have not read
it in this session.

## 1. Understand what is there and what is wanted

- Read the program with `get_program`: its type (general or resident), its
  preamble, its processes and connections. Look at `search_library` too: a
  process that a module of the preamble already defines is better reused than
  written again.
- Ask what the program has to do, if the user has not said: what comes in,
  what comes out, the steps in between, how much data, whether it runs once
  or keeps running (a resident program), where it runs (the built-in
  scheduler or Slurm). When the input holds several entries (the samples of
  a sample sheet), ask whether they go into one run, one task each, or one
  run each, where failures stay apart and entries can come later. Ask only
  what changes the design, a few questions at a time.
- For the usual shapes (a chain of steps for each entry, a pool of workers,
  a step that gathers every task of another, tasks that stream to each
  other), start from the patterns of
  https://debasher.readthedocs.io/en/latest/design_patterns.html.

## 2. Propose before you build

Propose the design in a short, readable form, and wait for the user to agree
or change it before you edit anything:

- each process: its name, what it does, its inputs and outputs (option labels,
  outputs starting with `-out`, each with the data type of what it carries),
  and its mode when it is not a single task (array or generator, for one task
  per element), with where its number of tasks comes from: a command-line
  option (a task shaping option when no task reads it), or another process,
  asked with `get_process_num_tasks` rather than counted again;
- how a step gathers the results of every task of another process: a
  fanout family on a `standard` process, one option per task, or the whole
  shared directory in which each task wrote a subdirectory of its own, with
  the dependency on that process given in `processdeps`, since the engine
  infers none from a whole shared directory;
- each connection, and why it is a file or a FIFO: a file when the next
  process needs all of it, or the result has to stay; a FIFO to stream from
  one process to the next while both run, or for a cycle;
- what the user has to give when running it (program options), and anything
  the program needs from outside (modules, environments);
- for a resident program, the kind of each node (business node, directory
  watcher, launcher of a general program, Supervisor), the external inputs
  fed from outside, and the initiators of the snapshots, one in each
  independent part.

Prefer few processes with a clear job each over many tiny ones, and the
connections of the data over ordering by hand.

## 3. Build it

- Build the agreed design in one go with `apply_edits`, whose edits can name
  what earlier ones added, so that the program never stays half built; call it
  with `dry_run` first when the change is large, and show the user the
  proposal. The single tools (`add_process`, `add_option`, `connect`, ...)
  are fine for small changes.
- Lay the processes out with `move_process` and `layout`, unless the user
  placed them by hand and wants them kept. Draw as a label edge
  (`set_connection_display`) a connection whose line would cross others.
- Each process gets a description that says what it does: the
  `/debasher:implement` skill writes its code from it.
- Check the result with `validate_program`, and fix what it reports. It saves
  the program; a process with no code yet may need its code before it
  validates, which you can leave to `/debasher:implement` once you say so.

If a tool refuses a save because the program changed on disk, someone else
(the user in the editor, most likely) saved it meanwhile: read it again with
`get_program` and work from what is there; never redo their change away. A
save is also refused while a run or a validation of the program is in
progress: wait for it to end, or ask the user before stopping it.

## 4. Hand over

Sum up what you built, what is left to decide, and, when the processes need
code, offer to continue with `/debasher:implement`.
