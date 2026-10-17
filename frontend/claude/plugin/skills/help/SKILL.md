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
  process with its code, `get_status`, `get_process_output` and, for a node,
  `inspect_node` for a run,
  `list_program_files` and `read_program_file` for the files of the home
  directory, `search_library` for what the modules of the preamble offer.
  Answer about what is there, by the names the user sees in the editor.
- When the question is about the editor, say where the user finds what they
  need: the toolbar (Env vars, Preamble, Description, Shared dirs, Sequential
  processes, Add process, Add program, Save, Run, Help, Close), the Run menu
  (output directory, execution and program options, Validate program, Run tests,
  Run program, status, stop, Reset output directory), the Inspector on the
  right, which edits the selected process, with the "AI prompt" button of each
  code editor, the context menu of a process or an edge on the canvas, the
  Legend of the canvas, which says what its borders, marks and edges mean, and
  the "Program files" panel in its corner.
- When the question is about Claude Code in the editor: "Claude Code..." in the
  Help menu gives the command of `debasher_claude` to copy, with the
  conversation to take up. Where the backend offers it, "Where" chooses between
  "In a terminal of your own" (the command) and "In this editor", whose "Open in
  the page" runs it in the terminal panel at the bottom of the editor ("Show it
  in the page" while a session runs). In the panel, the user drags its upper
  edge to change its height; "Hide" folds it into a mini window in the bottom
  left corner of the canvas, whose "Show" brings it back, and keeps the session;
  "End" ends the session and takes the panel away, as "Close" does once the
  session ended on its own, so that a new session starts from "Claude Code..."
  in the Help menu (with "Continue the last conversation" to take up the last
  one); and "Bring it here" takes over a session that another tab holds on the
  program. "Open in the page" is missing when the backend was not started with
  `debasher_webui`, does not find `debasher_claude`, or has
  `DEBASHER_WEBUI_CLAUDE_CODE_TERMINAL` set to `no`. The rest is in "A Session
  in the Editor" of https://debasher.readthedocs.io/en/latest/webui.html.
- When the question is about what the code of a process or a node can call
  (the functions of the engine, the methods and class attributes of the
  runtime library of nodes, such as `set_notice`), the reference names the
  usual ones. `get_code_prompt` for that process gives the rest: for a node,
  every hook, method and class attribute of its class, read from the
  installed runtime library; for a process, the rules of the engine for its
  code. Look there before answering that something does not exist, or
  pointing to something else.
- When the question is about a run, `get_status` gives its phase, the status
  of each process and, for a resident program, the notices of its nodes.
- Use the words of DeBasher with the meaning that the reference gives them.
  When the reference does not settle a detail, say so and point to the
  documentation, https://debasher.readthedocs.io/en/latest/, rather than
  guessing; the page on the web UI is
  https://debasher.readthedocs.io/en/latest/webui.html, and the one on
  describing a program in Python with the SDK (`debasher_build`, which,
  given the home directory, also writes the generated script of any saved
  program again) is
  https://debasher.readthedocs.io/en/latest/implem_python.html.
- `validate_program` checks the program as the Run menu does, but it saves
  the program and runs part of its code: offer it rather than run it unasked.
- Keep the answer short, with a small example when it helps.

## Doing something about it

If the answer is a change to the program, describe the change and offer to
make it. Designing processes and their connections is the work of the
`/debasher:design` skill, writing the code of processes and their tests that
of `/debasher:implement`, and reviewing code that is written that of
`/debasher:review`: say so when the user wants that done.
