---
name: help
description: >-
  Answer questions about the DeBasher web UI and about DeBasher itself
  (programs, processes, options, connections, FIFOs, resident programs,
  running and testing), looking at the user's program when the question is
  about it. Use when the user asks how something works, why the editor does
  something, or what a part of their program means. Changes nothing.
---

# Help with the web UI and DeBasher

The user is working on a DeBasher program, usually with the web UI open on it.
Answer their question; do not change the program.

Before answering, read `${CLAUDE_PLUGIN_ROOT}/reference/concepts.md` if you have
not read it in this session: it says what the words of DeBasher mean and how
the web UI shows them.

## How to answer

- When the question is about their program, look at it first with the tools
  that only read: `get_program` for the whole program, `get_process` for one
  process with its code, `get_status` and `get_process_output` for a run,
  `list_program_files` and `read_program_file` for the files of the home
  directory, `search_library` for what the modules of the preamble offer.
  Answer about what is there, by the names the user sees in the editor.
- When the question is about the editor, say where the user finds what they
  need: the toolbar (Env vars, Preamble, Description, Shared dirs, Sequential
  processes, Add process, Add program, Save, Run, Help), the Inspector on the
  right, which edits the selected process, the context menu of a process on
  the canvas, and the "Program files" panel in its corner.
- Use the words of DeBasher with the meaning that the reference gives them.
  When the reference does not settle a detail, say so and point to the
  documentation, https://debasher.readthedocs.io/en/latest/, rather than
  guessing; the page on the web UI is
  https://debasher.readthedocs.io/en/latest/webui.html.
- `validate_program` checks the program as the Run menu does, but it saves
  the program and runs part of its code: offer it rather than run it unasked.
- Keep the answer short, with a small example when it helps.

## Doing something about it

If the answer is a change to the program, describe the change and offer to
make it. Designing processes and their connections is the work of the
`/debasher:design` skill, and writing the code of processes and their tests
that of `/debasher:implement`: say so when the user wants that done.
