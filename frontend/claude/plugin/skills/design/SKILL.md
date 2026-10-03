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
  scheduler or Slurm). Ask only what changes the design, a few questions at a
  time.

## 2. Propose before you build

Propose the design in a short, readable form, and wait for the user to agree
or change it before you edit anything:

- each process: its name, what it does, its inputs and outputs (option labels,
  outputs starting with `-out`), and its mode when it is not a single task
  (array or generator, for one task per element);
- each connection, and why it is a file or a FIFO: a file when the next
  process needs all of it, or the result has to stay; a FIFO to stream from
  one process to the next while both run, or for a cycle;
- what the user has to give when running it (program options), and anything
  the program needs from outside (modules, environments).

Prefer few processes with a clear job each over many tiny ones, and the
connections of the data over ordering by hand.

## 3. Build it

- Build the agreed design in one go with `apply_edits`, whose edits can name
  what earlier ones added, so that the program never stays half built; call it
  with `dry_run` first when the change is large, and show the user the
  proposal. The single tools (`add_process`, `add_option`, `connect`, ...)
  are fine for small changes.
- Lay the processes out with `move_process` and `layout`, unless the user
  placed them by hand and wants them kept.
- Each process gets a description that says what it does: the
  `/debasher:implement` skill writes its code from it.
- Check the result with `validate_program`, and fix what it reports. It saves
  the program; a process with no code yet may need its code before it
  validates, which you can leave to `/debasher:implement` once you say so.

If a tool refuses a save because the program changed on disk, someone else
(the user in the editor, most likely) saved it meanwhile: read it again with
`get_program` and work from what is there; never redo their change away.

## 4. Hand over

Sum up what you built, what is left to decide, and, when the processes need
code, offer to continue with `/debasher:implement`.
