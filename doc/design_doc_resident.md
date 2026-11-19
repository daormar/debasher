---
title: Design of resident programs
fontsize: 11pt
geometry: margin=2cm
numbersections: true
toc: true
toc-depth: 2
---

This document describes the design of resident programs and the guarantees
they give. Where a mechanism is not yet fully designed or built, its own
section says so.

# Introduction

The goal is to extend the FBP engine with state (processes with their own
lifecycle, communicating over FIFOs, with support for cycles and interactivity)
so that, in addition to what it already does today, the system is able to do the
following, **within the limits stated in the Contract**, which comes right after
the Glossary (failure model, guarantees, obligations of module authors,
non-goals). Where a goal and the Contract disagree, the Contract wins: it says
precisely what is promised.

- **Tolerate the crash of one or more processes without losing work or
  corrupting the rest of the graph**: a node that goes down is relaunched (by
  the `Supervisor` or by hand) and returns to the state it would have had
  without the crash: its latest checkpoint plus a faithful replay of everything
  it had received since, in the order it processed it. The other nodes keep
  running, affected only by a brief wait (what exactly they may observe across a
  peer's crash is specified in the Contract).
- **Capture consistent snapshots of the whole system on demand**: be able to
  obtain, at any moment, a coherent picture of the state of every process and of
  the messages in transit between them, useful both for recovery and for
  inspecting or auditing what was happening at a given instant.
- **Shut down and resume a whole workflow in an orderly way**: stop every
  process of a run in progress and, later, resume from the checkpoints that the
  shutdown closed, each node returning to the state it had when it stopped.
- **Detect failures actively, within a bounded time**, without depending on a
  human noticing that something stopped responding, and without false positives
  when a process is simply busy with a long operation.
- **Reconstruct the communication history between processes**: every node keeps
  a durable log of what it received since its last checkpoint, in the exact
  order it processed it, so that a relaunched node re-processes what it had
  already received, in the same order, and then continues with whatever arrived
  while it was down.
- **Do all of this with a wire format that ties no process to a language**
  (one JSON object per line on a FIFO), although today every node and the
  `Supervisor` are Python classes of the runtime library (see "Nodes in a
  compiled language" in Future work), and without requiring additional external
  infrastructure (databases, coordination services) beyond what the engine and
  the filesystem already offer.
- **Fail loudly, never silently**: whenever a guarantee cannot be kept (for
  example, a message lost because two connected nodes crashed at the same time),
  the violation is detected and reported, instead of the program carrying on
  with silently wrong state.

The Glossary comes first, with the meaning of the words that the rest uses. The
Contract follows: it says precisely what these goals do and do not promise. Then
comes the design of the mechanism that provides them, from the wire up: the
"Control envelope" that every line of a FIFO carries; the "Channel kinds
declared with the fifo", which tell the engine what each FIFO is for and give
each process its ports; the node ("`FBPProcess` class") and its "Input log",
which together give a relaunched node back its state; "Reconnecting after a node
failure", which gives it back its channels; the "`Supervisor` class", which
watches the nodes, relaunches them and holds the FIFOs of their business
channels; the "Tools for resident programs", which act on a live program from
outside; and "`ProgramLauncher`", a node that launches batch runs. The document
ends with what is still open, "Future work", and with "The tests of the
Contract", an appendix on how the tests that show that the Contract holds are
built. Sections are cited in the text by name, as here.

# Glossary

The precise meaning of the words this document uses, in the order in which they
build on each other. Identifiers in backticks are names that exist in the code
or that have been decided. The vocabulary of the guarantees (deterministic,
idempotent, chaos test, mutation check, durability level) is defined in the
Contract, where it is used. Terms of the engine that this glossary does not
list, such as task, option list, output directory, process script or completion
marker, have the meaning that the design of the engine
(`doc/design_doc_engine.md`) gives them, and so do the entries below that refer
to it.

## Program and topology

- **resident program**: a program whose `_program_type` is `resident`:
  long-lived, stateful Python processes joined by FIFOs, always run by the
  built-in scheduler, and covered by the Contract. A **general program** is a
  DeBasher program as before, with none of this.
- **node**: a process of a resident program seen as a vertex of its
  communication graph, named by its process name when the process has a single
  task, and by `(process_name, task_idx)`, written `<process>:<idx>`, when it
  has several tasks (an array, whose options are written in a loop or produced
  by an option generator; see "Port declaration and node identity"). A business
  node is a subclass of `FBPProcess`; the `Supervisor` is a process of the
  program but not a business node, and it takes no part in the barrier.
- **port**: an option of a node that is connected to a FIFO, named without its
  leading dash. The engine gives each node run by it its input and output ports,
  taken from the options of its module (see "Ports from the engine"), in
  `INPUT_PORTS` and `OUTPUT_PORTS`; a node built without the engine declares
  them in these class attributes. The engine gives the `Supervisor` its ports
  too, and the `Supervisor` names its input ports after the nodes it watches
  (`NODE_PORTS`).
- **channel**: the one-way connection from an output port of one node to an
  input port of another, made of a FIFO (a named pipe created by the engine). A
  **self-loop** joins two ports of the same node. A channel delivers envelopes
  in the order in which they were sent. Besides `HELLO`, which every writer of
  the engine sends, and `CLOSE`, which a writer that has finished for good sends
  (no process of a resident program does, see "Ordered shutdown"), business
  channels and channels to an external port carry `DATA` and `BARRIER`, and the
  heartbeat channels and the channels of commands carry only `INTERACT` (see
  "Channel topology").
- **fifo owner**: the FIFO owner, as defined in the design of the engine: the
  process whose `define_fifo_opt` (or `define_fifo_opt_generator`) creates a
  FIFO. It is the process that writes it, except for a fifo tagged `--control`
  or `--external` whose writer is outside the program, which its reader owns
  (see "Channel kinds declared with the fifo").
- **fifo tag**: `--control` or `--external`, the optional argument of
  `define_fifo_opt` and `define_fifo_opt_generator` that makes the reader's end
  of a fifo a control port or an external port (see "Channel kinds declared with
  the fifo").
- **mirror tap**: as defined in the design of the engine, for a fifo declared
  with `--mirror`, the background job of the task that owns it, which copies
  each line that the owner writes into a shim FIFO to the real FIFO and to the
  mirror log of the fifo. A resident program does not allow it (see "Why the log
  is not built on the mirror tap").
- **source**: whatever puts `DATA` into an input port of a node without being a
  node of the program: a person writing into a FIFO, an external program, a test
  harness. A node acts only inside `process_data`, in reaction to what it
  receives, and never sends on its own initiative (`send_data` raises anywhere
  else), so a source is always outside the graph of nodes, and what enters
  through it is an external input (see "Limits and non-goals").
- **root**: a node that no node sends `DATA` to, not even itself through a
  self-loop. Its input ports, if it has any, are control ports or are written
  from outside the program, by a source. It can start a round, and its part of a
  round closes as soon as it opens, since it has no pending port.
- **relay**: a node with one input port and one output port whose `process_data`
  sends on the output what it received on the input, one message out for each
  message in. It is the simplest node that has both an input log and outputs, so
  tests and measurements use it as the node in the middle; a real node would
  transform the data, or send zero or several messages per input.
- **`Supervisor`**: the optional process (0 or 1 per program, of a single task)
  that receives heartbeats, relaunches downed nodes and can start rounds. It is
  not itself supervised.
- **initiator**: the node at which a round starts, because it receives an
  `INTERACT` `start_snapshot` or `shutdown`. It has to be able to reach every
  other node through the channels; a program made of independent subgraphs needs
  one initiator per subgraph.
- **trigger**: the `INTERACT` command, `start_snapshot` or `shutdown`, that
  makes a node start a round. It reaches an initiator from the `Supervisor`, or
  from an actor outside the program that writes it into a FIFO of the initiator,
  such as `debasher_snapshot_resident` and `debasher_stop_resident` (a snapshot
  timer of the initiator's own is not built, see "Periodic snapshots from a
  node's own timer" in Future work). It may carry the epoch of the round it
  starts (see numbered trigger).
- **numbered trigger**: a trigger whose `args` carry the epoch of the round it
  starts, the same for every initiator it reaches. An initiator handles it like
  a marker of that epoch that counts no port as arrived: it is ignored if that
  round is already open or over, if it is older than the open round, or if it is
  a snapshot while a halt is open, and otherwise it replaces the open round. The
  `Supervisor` numbers every trigger it relays that does not carry an epoch yet,
  `debasher_snapshot_resident` numbers its `start_snapshot` and
  `debasher_stop_resident` its `shutdown`, all with the time in milliseconds: it
  needs no state to survive a relaunch, and it lies above the epochs that
  initiators number themselves. A clock set back makes a numbered trigger look
  old, and it is ignored with a warning.
- **initiator port**: an output port of the `Supervisor`, an entry of its
  `INITIATOR_PORTS` list, wired to the control port of an initiator; the
  `Supervisor` sends the triggers through it.
- **manual trigger port**: the input port of the `Supervisor`,
  `MANUAL_TRIGGER_PORT`, where an actor outside the program writes a trigger,
  which the `Supervisor` relays to every initiator port.
- **control port**: an input port of a node, listed in `CONTROL_PORTS` (from a
  fifo tagged `--control`), that carries only `INTERACT` commands, such as the
  one on which an initiator receives its triggers. It never carries a marker, so
  it takes no part in any round, and a `CLOSE` on it does not close it, because
  several writers feed it in turn (a `Supervisor` and the one of a resumed
  program, `debasher_snapshot_resident`, a person writing by hand), and none of
  them ends the channel for the others.
- **control ports file**: the file `control_ports` (`control_ports_<idx>` for a
  task of an array, see execdir) that a node writes in its own `execdir` when it
  starts (one fifo path per line, from `self.opts`, one per entry of
  `CONTROL_PORTS`; empty, not absent, if it has none), so that an external actor
  can find where to write a trigger for an initiator with no other knowledge of
  this program (see `_write_control_ports_file`).
- **external port**: an input port of a node, listed in `EXTERNAL_PORTS` (from a
  fifo tagged `--external`), fed only from outside the program (a source, or a
  person writing by hand), which therefore does not carry a marker of its own: a
  round never waits for it. Unlike a control port, a `CLOSE` on it does close it
  for good, since its writer is not expected to come back. A source that does
  know the protocol may still write the marker of the round the initiator
  opened: it is then read like on any other port.
- **incarnation**: one running instance of a node's process. Relaunching a node
  after a crash starts a new incarnation of the same node, which reuses its
  FIFOs, its directory and its checkpoints.
- **execdir**: the exec directory of the node's process, as defined in the
  design of the engine, `__exec__/<process_name>/` under the program's output
  directory, exported to the process as `DEBASHER_PROCESS_EXECDIR`. Its
  checkpoints and its input log live there. The tasks of an array process share
  it, as they already share the engine's own files, which carry the task's index
  (`<process_name>_<idx>.id`, `.sched_out`, ...). A task gets its index too,
  exported as `DEBASHER_PROCESS_TASK_IDX` (empty for a process that is not an
  array), and adds `_<idx>` to the name of everything it keeps there:
  `checkpoints_<idx>/`, `log_<idx>/`, `halted_<idx>`, `control_ports_<idx>`,
  `node_info_<idx>` and `notice_<idx>` (`_get_execdir_entry`).
- **limits of a node**: `INPUT_LOG_MAX_BYTES`, `OUT_BACKLOG_MAX_BYTES`,
  `OUT_BACKLOG_FAIL_BYTES` and `GIL_SWITCH_INTERVAL_SECS`, class attributes of
  `FBPProcess` that a module can redefine and that the computational
  specifications of a process can set for that process of a program (see
  "Computational specifications of a resident process").

## Messages

- **envelope**: one JSON line on a channel, `{"type": ..., "payload": ...}`,
  with one of the five types below. A `DATA` envelope also carries a `seq` (see
  "sequence number" in the input-log group). A **message** is an envelope in
  transit on a channel; unqualified, it means a `DATA` message.
- **packet**: the `payload` of a `DATA` envelope, already deserialized: what
  `process_data(port_name, packet)` receives.
- **`DATA`**: the business traffic. It is the only type that reaches
  `process_data` and the only one that is replayed.
- **`BARRIER`, marker**: the envelope that carries a round's `epoch` and its
  `halt` flag. Each node forwards it on its output ports, along the same
  channels as `DATA`, and never to the `Supervisor`.
- **`INTERACT`**: a control command, with `command` and `args`
  (`start_snapshot`, `shutdown`, `heartbeat`, `checkpoint_saved`, and any that
  are added later: the catalog is open). It travels on its own channels, not on
  business channels.
- **`CLOSE`**: the last envelope of a writer that has finished for good: it will
  never write again. It means "finished for good", not "finished successfully":
  a process that exits with an error sends none and counts as crashed. A halt is
  not a finish for good, since the node is resumed later, so an ordered halt
  sends none. The reader hands it to the brain thread in order and then keeps
  reading, but drops everything that follows it (the `Supervisor`'s readers
  deliver it, since a node that closed its channel may be relaunched and must
  be heard). `closed_ports` is the checkpoint field that lists the input ports
  whose `CLOSE` the brain thread had processed when the round captured the node
  state. A sender that numbers what it sends (G5) puts its `out_seq` for that
  channel in `CLOSE`'s own payload, `last_seq`: the receiver checks it against
  what it has accepted, and a mismatch is a lost message that nothing else
  would ever reveal, since nothing comes after a `CLOSE` (G8). Left out (an
  empty payload) when the sender does not number what it sends.
- **`HELLO`, resync line**: the first thing every incarnation of a writer sends,
  in one write together with a leading newline. The newline ends any fragment
  that the previous incarnation left when it was killed in the middle of a
  message, and the `HELLO` tells the reader that such a fragment can be dropped.
  It also tells the reader that its peer (re)connected.
- **ghost connection**: each endpoint of a channel holds both ends of the FIFO,
  the real one and a ghost of the opposite direction. The reader never sees EOF
  and the writer never gets `EPIPE`; a dead peer is only backpressure, and a
  channel outlives the crash of either process.
- **held FIFO**: the FIFO of a business channel between two nodes, which the
  `Supervisor` holds open through a read end that it never reads, a third holder
  besides the two endpoints, so that what the FIFO holds outlives the crash of
  both of them. The flag `-no-hold-fifos` turns it off (see "Holding the
  business channels").

## Rounds and checkpoints

- **node state**: what `capture_node_state()` returns and `restore_node_state()`
  takes back: the serializable logical state of a node, complete enough for
  `restore_node_state()` to rebuild it exactly. Runtime resources (connections,
  file handles) are not part of it; `initialize_runtime()` rebuilds them. In the
  checkpoint it is the field `node_state`, which sits beside the `channel_state`
  and beside the engine's own bookkeeping (`capture_pos`, `closed_ports` and the
  sequence numbers).
- **round**: one run of the barrier protocol (Chandy-Lamport) over the whole
  program. At a node it opens when the node captures its state, on the first
  marker of the round or on the `INTERACT` that starts it, and it closes when no
  input port is pending. An input port on which the round still waits for a
  marker is **pending**: every input port but the control ports, the external
  ports, the ports whose writer has said `CLOSE` (a finished writer sends no
  more markers) and the port whose marker opened the round. Rounds do not
  overlap at a node: a newer round that reaches it replaces an older one that
  is open (see abandoned round).
- **epoch**: the number that identifies a round. Markers carry it, and it names
  the checkpoint file (`<epoch>.json`). An initiator numbers a new round with
  the epoch that its trigger carries (see numbered trigger) or, if it carries
  none, as the last epoch it closed or abandoned plus one.
- **abandoned round**: a round that a node drops, without writing a checkpoint
  for its epoch, because a newer round reached it while it was open. The nodes
  that had already closed it keep their checkpoint, so that epoch has no
  complete cut; the round that replaced it is the one that completes.
- **capture**: the moment at which a node calls `capture_node_state()` because a
  round opens. The node state that goes into the checkpoint is the one at that
  moment, not the one at the close of the round.
- **snapshot**: a round with `halt` false: every node saves a checkpoint and
  keeps running (the name of the operation, as in `start_snapshot`). In the
  literature the word also names what such a round records, the node states
  together with the channel states; here that result is the consistent cut. A
  **halt** is a round with `halt` true; it behaves exactly like a snapshot at
  the node itself (the node keeps running after saving its checkpoint), and only
  writes its own **halted marker** on top of that (see below). What actually
  stops the node, and later resumes the program by relaunching every node, is a
  **stop signal** (see below), decided entirely outside the barrier protocol.
- **halted marker**: the file `halted` (`halted_<idx>` for a task of an array,
  see execdir) that a node writes in its own `execdir` (atomically, like a
  checkpoint, but never schema-versioned or pruned) when a halt round closes,
  holding that round's epoch as plain text. Read by nothing inside the node
  itself (in memory, `_halted` already keeps the same incarnation from starting
  another round when a trigger reaches it, see "Ordered shutdown"); it exists
  only for an external actor with no other view of the node's state, such as
  the tool a stop signal comes from, to notice that this incarnation has closed
  the round of the halt, so that stopping it now loses nothing that a resume
  does not bring back. The file outlives the incarnation that wrote it.
  Nothing removes it when the program is resumed. The next halt overwrites
  it.
- **halted marker baseline**: the content of a node's halted marker when
  `debasher_stop_resident` starts, before it triggers the halt, or `-1` if the
  node has none. A halted marker belongs to this halt only once it holds an
  epoch past its baseline. A marker left by an earlier halt, already resumed,
  says nothing about this one.
- **stop signal**: `SIGTERM`, sent to a node's whole process group (the same
  group `debasher_stop` already reaches with `SIGKILL`, see
  `debasher::_stop_pid`), which is what actually ends a node's `run()`
  (`_stop_requested`, which `run()` sets once the handler that it installs,
  `_on_stop_signal`, has noted the signal). Unlike a halt closing its round,
  receiving one is not conditional on anything: a node that never halted stops
  on one just the same. Nothing in `FBPProcess` decides when to send it: that is
  external, by design, typically once every node's halted marker has gone past
  its baseline.
  `Supervisor` stops on one too (see the "Clean-completion detection"
  subsection).
- **`debasher_stop_resident`**: the tool that actually sends the stop signal
  in a real program, the graceful counterpart to `debasher_stop` (see
  "`debasher_stop_resident`: the graceful stop tool" for the full sequence).
  Stops a `Supervisor`, if the program has one, before the tool triggers the
  halt. Then waits for every node's halted marker to go past its baseline, and
  signals each node. Falls back to `debasher_stop`'s hard kill past its own
  `--timeout`.
- **`debasher_snapshot_resident`**: the tool that starts a snapshot in a
  running program from outside it, with or without a `Supervisor`, once or
  every given number of seconds (see "`debasher_snapshot_resident`: rounds
  from outside the program").
- **in transit**: a `DATA` message sent before its sender captured its state and
  received after its receiver captured its own.
- **channel state**: `channel_state`, the copy that a node keeps, in the
  checkpoint, of the `DATA` that arrived on a pending port during a round: the
  messages that were in transit at the cut. They are also processed normally.
  Localized recovery does not read it: the same messages are in the input log
  above `capture_pos`, and the replay processes them again. A global rollback
  would.
- **consistent cut**: the checkpoints of every node for the same round, taken
  together (each one holds its node state and the channel state of its input
  ports): a state that the whole program could really have been in. It is what
  the literature calls the snapshot, the result of a round. It holds only if no
  node crashes during the round.
- **checkpoint**: the file `<epoch>.json` that a node writes atomically in
  `<execdir>/checkpoints/` (`checkpoints_<idx>/` for a task of an array, see
  execdir) when a round closes. It holds a schema version, the epoch, the
  `node_state`, the `channel_state` and the engine's own bookkeeping:
  `capture_pos`, `closed_ports`, `out_seq`, `last_seq` and the outbound
  backlog, `out_backlog` (see "State capture and checkpoint schema"). Only the
  last `CHECKPOINT_RETENTION` are kept.
- **outbound backlog, `out_backlog`**: the `DATA` that `send_data` has numbered
  and queued and that the writer thread of its port has not yet finished
  writing into the FIFO, on all the output ports of the node (G5). The node
  keeps it live in `_unwritten`. When a round captures the node state, it takes
  a copy, which the checkpoint stores as `out_backlog`:
  `{tag: [{"seq":, "payload":}, ...]}`, decoded from each queued line. Without
  it, a crash right after the capture would destroy those messages for good,
  with no trace (see "Both endpoints of a channel crashed" in the Contract's
  limits). Recovery queues it again, with the same numbers, before anything else
  is sent. Two limits apply to it (see "Checkpoint persistence"):
  `OUT_BACKLOG_FAIL_BYTES` to the live backlog, the bytes of its lines on all
  ports together, and `OUT_BACKLOG_MAX_BYTES` to the copy, the size of its
  entries in the checkpoint.

## Input log

- **input log**: one log per node, in `<execdir>/log/` (`log_<idx>/` for a task
  of an array, see execdir), of everything that arrives at it, in the order in
  which the brain thread processes it, written by the reader threads when each
  envelope arrives. It holds every queued envelope (`DATA`, `BARRIER`,
  `INTERACT`, `CLOSE`), and only `DATA` is replayed.
- **record**: one line of the input log, holding the position, the port and the
  envelope exactly as it arrived. Not to be confused with the verb: what a round
  does to the `DATA` of a pending port is "keep a copy".
- **position, `pos`**: the number of a record in the input log. It is a counter
  of the receiver, global to the node (across all its input ports), that starts
  at 1 and is assigned in the same critical section that puts the envelope on
  the inbound queue, so that position order is processing order. A checkpoint
  refers to the log by position, never by epoch.
- **segment**: a file of the input log with consecutive records, named by the
  position of its first record (`<first pos>.log`). A new one starts with every
  incarnation and when the active one has reached a size limit, which a write
  can pass by the records of one block that a reader thread took from its
  FIFO; only whole segments that are not the active one are deleted.
- **capture position, `capture_pos`**: the position of the envelope during whose
  handling the node captured its state: a marker, or a command that opens a
  round, never a `DATA`. Every `DATA` before it is reflected in the checkpoint's
  node state; recovery replays what comes after it.
- **torn tail**: part of a record, with no newline, at the end of a segment,
  which a process that dies in the middle of a write (a `kill -9`, a crash), or
  a write that fails halfway (a full disk), leaves. It can happen at any record
  size. Nothing is written after it, since no incarnation appends to an
  existing segment and a log refuses every append after a failed write, and
  replay ignores it. A line that ends in a newline is a complete record and has
  to parse, or the log is corrupt (see "Log structure and record format").
- **replay**: re-executing `process_data` on the `DATA` records after
  `capture_pos`, in log order, when a node starts. It reads from disk and writes
  nothing to the log.
- **prune**: deleting what no retained checkpoint needs: the checkpoints beyond
  `CHECKPOINT_RETENTION` and, in the input log, the whole segments that end at
  or before the `capture_pos` of the oldest retained checkpoint.
- **sequence number, `seq`**: the counter, per channel, that the sender puts in
  each `DATA` so that the receiver can drop a duplicate produced by a replay and
  detect a gap. `out_seq` (the counter of each output port) and `last_seq` (the
  last number processed by the brain thread on each input port) are stored in
  the checkpoint. Not the same as `pos`: `seq` is per channel and assigned by
  the sender, `pos` is per node and assigned by the receiver. On the receiver
  side `last_seq` is the brain's own view, so the drop itself cannot use it
  directly: a reader thread keeps a second counter of its own, `_accepted_seq`,
  ahead of the brain, which the check actually consults; restored at startup
  from the checkpoint's `last_seq` plus the log after `capture_pos`, it is never
  itself written to a checkpoint (see "State variables, at a glance").

## Threads of a node

- **reader thread**: one per input port. It reads and decodes lines, consumes
  `HELLO`, drops with a warning an envelope that is malformed or of a type its
  port does not carry (see "Fields of each type" and "Channel topology"), and
  hands everything else to the inbound queue (with the input-log
  redesign, after appending the record to the log). After a `CLOSE` it goes on
  reading but drops everything that follows. It ends only when its node stops,
  or on an error of its stream or of its input log (see "Ghost connections").
- **writer thread**: one per output port, with its own outbound queue. It sends
  `HELLO` first and, when its node has finished for good (not at a halt),
  `CLOSE` last. A writer whose peer is down and whose pipe is full blocks, so it
  is a daemon thread and `stop_threads()` gives up on it after a bounded wait.
- **brain thread**: the only consumer of the **inbound queue** and the only
  thread that touches the node's state: it runs `process_data`, the barrier
  logic and the writing of checkpoints.
- **heartbeat thread**: checks on a timer that every other thread is alive and,
  if so, sends the `Supervisor` an `INTERACT` `heartbeat`. An unhealthy node
  simply stops sending. At every tick it also writes the node info file.
- **checker thread**: the thread of the `Supervisor`, not of a node, that
  decides on a timer which nodes are down or done (see "Failure detection").
- **observation thread**: only in a node whose class defines `observe()`. It
  runs `observe()` every `OBSERVE_INTERVAL_SECS`, which looks at the outside
  world and brings what it sees into the node with `inject()`, under the name of
  its **observe port**, `OBSERVE_PORT`, which is not a fifo (see "Observing the
  outside world").
- **node info file**: the file `node_info` (`node_info_<idx>` for a task of an
  array, see execdir), a JSON object that a node writes in its own `execdir`,
  atomically, when its threads start and again at every tick of its heartbeat
  thread: what a tool outside the node needs to know of it and cannot read
  anywhere else, such as its limits in force and the size of its outbound
  backlog. It is not part of the state of the node (see
  "`debasher_inspect_resident`: what a node keeps").
- **notice**: one message, with a level (`info` or `warning`), that the code of
  a node leaves for whoever watches the program with `set_notice()` and takes
  away with `clear_notice()`, saying how the node is now, such as that its
  configuration file is missing. A node has at most one, which the next
  replaces; it is not a log, not part of the state of the node, and not sent on
  any channel (see "Notices").
- **notice file**: the file `notice` (`notice_<idx>` for a task of an array, see
  execdir), a JSON object in which a node keeps its notice, written atomically
  in its own `execdir`, and removed when the node has none.

## Failure and recovery

- **crash**: the death of a node's process that is neither a halt nor a finish
  for good: `SIGKILL`, an uncaught exception, an out-of-memory kill, or a
  non-zero exit. A deliberate error exit and a crash are treated the same.
- **relaunch**: starting a new incarnation of a node, by the `Supervisor`
  (through `debasher_launch_process`) or by hand. It is the same operation as
  the first launch: there is no recovery mode.
- **recovery**: what a relaunched node does at startup: open its FIFOs, load its
  latest checkpoint, `restore_node_state`, `initialize_runtime`, start its
  writer threads, replay the input log after `capture_pos`, then start its
  other threads. Localized recovery is the policy: only the downed node is
  relaunched. A **global rollback** would instead rewind every node to the last
  consistent cut; it is future work.
- **heartbeat**: the `INTERACT` command that a healthy node sends the
  `Supervisor` every `HEARTBEAT_INTERVAL_SECONDS` from the moment its threads
  start. The `Supervisor` declares a node down when they stop for
  `HEARTBEAT_TIMEOUT_SECS`, or for its startup deadline before the first one, or
  at once if the node's PID is gone and its `.finished` file is absent.
- **startup deadline**: how long a node has, from each launch, to send its first
  heartbeat, which comes only once it has restored its checkpoint, run
  `initialize_runtime()` and replayed its input log, and then run for one
  `HEARTBEAT_INTERVAL_SECONDS`. Never shorter than `HEARTBEAT_TIMEOUT_SECS` (see
  "Failure detection").
- **down, done, given up**: the states of a node in the `Supervisor`. Down:
  declared down and relaunched. Done: its `.finished` file appeared (it exited
  cleanly with code 0), so it is never checked again. Given up: it exhausted
  `MAX_RELAUNCH_ATTEMPTS`, which triggers the escalation.
- **escalation**: what the `Supervisor` does when a node is given up: it kills
  that node if it still runs, then an ordered shutdown of the other nodes
  through the initiators and, if some node has not finished after
  `FORCE_STOP_TIMEOUT_SECS`, `debasher_stop` on the whole program.

## Batch runs

- **launcher node**: a node of class `ProgramLauncher`, which launches a general
  program once for each request it receives (see "`ProgramLauncher`: batch runs
  from a node").
- **batch run**: one execution of the general program of a launcher node, with
  the options of one request, by `debasher_exec` on a directory of its own,
  outside the resident program's scheduling.
- **runs root**: the directory under which a launcher node places its batch
  runs: the output directory of its process, or the absolute path that the
  option `-runsdir` of its process gives.
- **run directory**: the output directory of one batch run, `<runs root>/<run>`,
  where `<run>` is a relative path that the request names, or else the position
  of the request in the input log. Its `launch.json` records which request of
  which life of the launcher node the directory belongs to.
- **registration**: the file `.launcher/registrations/<position>.json` in the
  output directory of the process of a launcher node, written when the request
  at that position registers a batch run, and which names its run directory.
  The registrations of a node are its queue of batch runs.
- **life**: the time between two clean starts of a launcher node, identified by
  `life_id`, a random string kept in a file of the output directory of its
  process; `debasher_reset_resident` removes it, so every clean start begins a
  new life.

## Testing a node

Node tests, business tests and the test runner are defined in the glossary of
`doc/design_doc_engine.md`.

- **node harness**: `debasher_runtime_testing`, the module of the runtime
  library with which a node test builds a node without the engine and calls its
  hooks (see "Testing a node without the engine").
- **round trip through JSON**: serializing a value to JSON and reading it back,
  which gives what the other end of a FIFO or a checkpoint on disk would give:
  a tuple arrives as a list, a number used as a key arrives as a string, and a
  value that JSON cannot serialize, such as a set, fails. The node
  harness does it with every packet and node state, so that a node test sees
  what a run would, and not a node that passes its test with objects that no
  run could bring it, or whose state does not survive a checkpoint.
- **node under test**: what `load_node` of the node harness returns: a node
  built with the options and ports that the test gives, fed with `feed`, whose
  output `sent` gives.

## State variables, at a glance

Several pieces of a node's bookkeeping go through the same three stages: a live
value that the brain thread keeps up to date as it processes each envelope, a
copy taken at the capture and held only while a round is open (see "capture"
above), and the checkpoint field the copy is written to when the round closes.
The open round is `_round` (`None` when there is none), and its copy is
`_round.capture`, a `_Checkpoint` whose fields have the names of the fields of
the checkpoint. The table therefore names, for each concept, the live value and
the field; the concepts are defined in this glossary and not redefined here.
`Supervisor`'s own bookkeeping (which nodes are down, how many times each has
been relaunched) is a separate concern, covered in the "`Supervisor` class"
section.

| Concept                | Live            | Field of `_round.capture` and of the checkpoint |
| ---------------------- | --------------- | ----------------------------------------------- |
| capture position       | `_current_pos`  | `capture_pos`                                   |
| closed input ports     | `_closed_ports` | `closed_ports`                                  |
| sender counters (G5)   | `_out_seq`      | `out_seq`                                       |
| receiver counters (G5) | `_last_seq`     | `last_seq`                                      |
| outbound backlog (G5)  | `_unwritten`    | `out_backlog`                                   |
| node state             | module's own    | `node_state`                                    |
| channel state          | (none)          | `channel_state`                                 |

`_unwritten` is the one exception to "the brain thread keeps it up to date":
`send_data` appends to it (the brain thread, or the one replaying the input
log), but the writer thread pops from it, under the same lock, as it confirms
each line written.

Bookkeeping that never enters a checkpoint, because it only means something
while its own thread or round is live, or is computed again from what a
checkpoint holds: `_handler_thread` (the identity of the thread currently
inside `process_data`, checked by `send_data`),
`_round.pending` (the input ports an open round still waits on),
`_closed_at_start_ports` (what a relaunched node's readers of closed ports
start out knowing, taken from `_closed_ports` once, when the threads start),
`_ReaderState` (what each reader thread remembers from one line to the next:
the fragment that a `HELLO` has yet to excuse, whether its writer has said
`CLOSE`, and whether a line after that `CLOSE` has already warned; created
afresh with every reader thread, closed from the start for a port in
`_closed_at_start_ports`),
`_accepted_seq` (the reader threads' own live view of `_last_seq`, ahead
of it, which the dedup check of G5 actually consults; restored at startup
from the checkpoint's `last_seq` plus the log after `capture_pos`, never
itself written to one), and `_unwritten_bytes` and `_unwritten_port_bytes`
(the size of `_unwritten` on all ports together and on each port: the first is
what `OUT_BACKLOG_FAIL_BYTES` is checked against, the second what its error
names and what the node info file reports by port; derived from `_unwritten`,
they are computed again as a restore queues the backlog of the checkpoint).

# Contract: assumptions, guarantees and non-goals

The mechanisms that provide the guarantees below are designed in the sections
after this one. The Contract applies to programs whose `_program_type` is
`resident`; general programs keep today's behavior.

The purpose of this section is that "reliable" has a precise meaning here:
within the stated assumptions, either the guarantees hold, or the violation is
detected and reported. Never "it usually works". Every guarantee must be backed
by at least one end-to-end test that states it in the same words (see
"Acceptance").

This section states what it assumes, what it promises and where the promise
ends: the failures it tolerates ("Failure model"), what the code of a module
must do in return ("Obligations of module authors"), the guarantees themselves
("Guarantees"), where they stop ("Limits and non-goals"), and how they are shown
to hold ("Acceptance").

## Failure model

A guarantee means something only against a list of what can go wrong. This
section says which failures the guarantees survive, what they assume keeps
working, and which failures they do not cover.

- **Tolerated**: the crash of any process of a `resident` program (SIGKILL,
  uncaught exception, out-of-memory kill) and its relaunch, by the `Supervisor`
  or by hand. Any number of nodes may crash at any time, including while other
  nodes are recovering, with the exceptions listed under "Limits and non-goals".
  There is deliberately no bound on how many nodes fail simultaneously: each
  node recovers from its own checkpoint and input log, on stable storage,
  independently of the others, so correctness does not depend on how many failed
  at once. (A bound on simultaneous failures only buys something in designs
  whose redundancy lives in other nodes' volatile memory, such as logging at the
  sender or replication with quorums; this design has neither.)
- **Assumed to keep working**: the machine and its operating system, and the
  filesystem under the program's outdir (it keeps what was written: checkpoints,
  input logs, markers). Resident programs run on a single machine (BUILTIN
  scheduler only), so network partitions do not apply.
- **Durability level: process crashes only.** Nothing is
  `fsync`ed anywhere, so logs and checkpoints survive the crash of a process but
  not the crash or power loss of the machine; see the note below on what `fsync`
  is and what it would cost.
- **Not tolerated**: machine crash or power loss (see above), disk corruption,
  and processes that misbehave instead of crashing (Byzantine faults).
- **The `Supervisor` is not itself supervised.** If it dies, the nodes keep
  running with their state, but nobody relaunches a crashed node, and no FIFO
  is held (see held FIFO in the Glossary), until the `Supervisor` is
  relaunched by hand. No mechanism covers this (see "Supervising the
  `Supervisor`" in Future work).

**Note on `fsync`, and why the level above is enough for now.** When a process
writes to a file, the operating system copies the data into its own memory (the
page cache) and answers at once; it writes it to disk some time later (15 to 30
seconds on the development machine). `fsync` forces that write and returns only
when the data is on disk. If a process dies, what it wrote is already in the
operating system's memory and is not lost, so logs and checkpoints survive a
`kill -9`, an uncaught exception or an out-of-memory kill, which is exactly what
the failure model covers. If the machine crashes or loses power, whatever was
still only in memory is lost: the last seconds of log and, with bad luck, a
checkpoint that was renamed into place but is empty. If that cuts the log of a
node below its latest checkpoint, the node refuses to start (see "Recovery:
startup and replay"). Surviving that has a price,
measured on the development machine (NVMe, ext4): an append to the log takes 0.8
microseconds without `fsync`, 13 with an `fsync` every 100 appends and about
1050 with one after every append (roughly 950 messages per second); saving a
checkpoint takes 39 microseconds without it and 1.9 ms with `fsync` of the file
and of its directory. Hence it is left out for now, and the cheap first step is
noted in Future work.

## Obligations of module authors

The guarantees hold only if the module code keeps its side of the bargain. The
first four obligations concern the code of a node: what `process_data` does,
when it sends, what its state captures, and its effects outside the graph; the
others concern the messages and how the program declares its fifos. The
framework enforces some of them, and their entries say how; for the rest, the
chaos test (see "Acceptance") is what exposes a violation.

- **`process_data` is deterministic**: given the same starting state and the
  same sequence of received messages, it produces the same new state and the
  same outputs. The outputs include the port that each message goes to, so a
  node that sends to a fanout family chooses the port by the packet or by a
  counter in the node state, never by the load of its readers. It must not
  depend on wall-clock time, randomness, thread timing, or external reads,
  unless whatever it reads is part of the captured state or of the message
  stream. Recovery re-executes it, so a non-deterministic `process_data`
  silently diverges from what it did before the crash.
- **A node sends only inside `process_data`**, in reaction to a message that it
  receives. Unlike the others, the framework enforces this one: `send_data`
  raises when it is called anywhere else, or from a thread other than the one
  running `process_data`. What starts the activity of a program is written
  into an input port from outside (see "source" in the Glossary).
- **`capture_node_state()` is complete and `restore_node_state()` exact**:
  everything that influences future behavior round-trips through them.
- **Effects outside the graph are idempotent**: replay re-executes
  `process_data`, so anything it does outside the FIFOs (writing a file
  elsewhere, calling a service) can happen more than once.
- **Messages are serializable as strict JSON, of any size up to
  `OUT_BACKLOG_FAIL_BYTES` (`out_backlog_fail_mb`), measured on the encoded
  line.** A message larger
  than `PIPE_BUF` (4096 bytes on Linux) being written when its sender crashes
  can leave a truncated fragment in the FIFO. The reader drops it thanks to the
  resync line (see the Glossary) that every writer incarnation sends first,
  and the sender's replay regenerates the message. Only the framework writes
  to these channels; an external writer must send complete lines.
- **Every fifo is defined by the process that writes it, through an output
  option, except one fed from outside the program**, which its reader defines
  through an input option with a fifo tag, `--control` for commands and
  `--external` for data (see "Channel kinds declared with the fifo"). The
  engine reads the direction of every channel from this, and refuses a
  resident program that does not follow it when the program is loaded.
- **The fifos without a fifo tag that the tasks of an array define through the
  same option are read inside the program for every task or for none.** A fifo
  without a fifo tag whose other end is outside the program is a channel to
  someone outside, but when only some tasks of an array have one, the engine
  takes it for a mistake (a reader with fewer tasks than the array, for
  instance) and refuses the program when it is loaded (see "Declaring and owning
  a FIFO" in `doc/design_doc_engine.md`).

## Guarantees

What a resident program promises, within the failure model and given the
obligations: the order and the delivery on a channel (G1, G2), what a crash and
a relaunch preserve (G3 to G5), snapshots and halts (G6), and how a failure is
noticed and reported (G7, G8).

Numbered so that this document can cite them; tests and code comments state the
guarantee in words and never cite these numbers, which may change.

- **G1, channel order**: on every channel, messages are delivered in the order
  they were sent.
- **G2, no silent loss without failures**: with no failure, every `DATA` message
  sent on a channel is handed exactly once to the receiver's `process_data`,
  also while a snapshot or shutdown round is open.
- **G3, node recovery**: after a crash, a relaunched node ends in the state it
  would have had without the crash: its latest checkpoint plus the replay of
  everything it had received since, in the order it processed it (given the
  obligations above).
- **G4, faithful replay**: the input log is one log per node, written when each
  message arrives, in the order in which the messages are queued and hence
  processed by the brain thread, across all its input ports, so that replay
  reproduces that order exactly. A node with several input ports does not have
  to be insensitive to how their messages interleave.
- **G5, no duplicates and no silent loss across a crash**: a neighbor that keeps
  running observes each message of a relaunched node once, not twice, and in
  order; and if a message is lost anyway, the receiver notices. Mechanism:
  each `DATA` carries a sequence number per channel,
  assigned by the sender; the sender's counters are stored in its checkpoint, so
  that replay regenerates the same numbers; the receiver drops any `DATA` whose
  number is not above the last one it accepted from that channel (a duplicate),
  and treats a jump as a lost message, an error in the sense of G8. The
  receiver's last numbers are rebuilt from its checkpoint and its log. It relies
  on determinism: a replay that produced different outputs would reuse numbers
  for different messages.
- **G6, consistent snapshots and orderly halt**: while no node crashes during a
  round, the checkpoints closed by that round form a consistent cut, and after a
  halt every node resumes in the state it had when it stopped: it loads its
  checkpoint and replays from its input log only what it processed after
  capturing it. A crash during a round aborts it at the node that crashed
  (see "A crash while a round is open" in the limits below).
- **G7, bounded detection**: a crashed node is noticed within
  `HEARTBEAT_CHECK_INTERVAL_SECS` when its PID is verifiably gone, and within
  `HEARTBEAT_TIMEOUT_SECS` when it is alive but unhealthy (one of its reader,
  writer or brain threads died). It is then relaunched up to
  `MAX_RELAUNCH_ATTEMPTS` times before the escalation.
- **G8, detected, never silent**: when a guarantee cannot be kept (a gap in a
  channel's sequence numbers, a fragment that no `HELLO` follows, a checkpoint
  with another schema version, an input log over its size cap, an input log that
  does not reach its latest checkpoint, an exhausted relaunch budget), the node
  or the `Supervisor` raises an error that stops the affected part, instead of
  continuing with silently wrong state. What happens after that stop is manual
  today; the planned fallback is a coordinated global rollback to the last
  consistent cut, **not built** (see Future work).

## Limits and non-goals

Each entry below is a case that the guarantees do not cover, or cover only in
part, even within the failure model, or a use that the design does not support
(a non-goal); each says what happens then. Besides the limits below, the
Contract holds only within its "Failure model" (the built-in scheduler, no
failure of the machine) and only for nodes that keep the "Obligations of module
authors" (a deterministic `process_data`, idempotent effects outside the graph).

The limits are numbered so that this document can cite them. Tests and code
comments state a limit in words and never cite these numbers, which may
change.

1. **Both endpoints of a channel crashed while no other process held the FIFO.**
   What a FIFO holds is destroyed only when no process holds it open.
   - One endpoint down. Nothing is lost: the other holds the FIFO, and what was
     sent and not yet read waits in it. What the writer had numbered and queued
     but not yet written is in the outbound backlog of its checkpoint, and its
     recovery sends it again before anything else. A relaunched node holds its
     FIFOs from the first step of its recovery, before it restores its
     checkpoint or replays its input log, until it dies.
   - Both endpoints down. Both may crash together, or the second before the
     first has been relaunched, which takes the time to notice the crash and
     start the new process. The `Supervisor`, if there is one, still holds the
     FIFO (see "Holding the business channels"). What the FIFO held waits for
     the relaunched reader. What the relaunched writer sends again comes after
     it, with the same numbers, as duplicates that the reader drops (G5).
   - When the content of the FIFO is destroyed. With both endpoints down, no
     process holds the FIFO when the `Supervisor` is down too (it is not
     supervised, see "Failure model"), when the program has no `Supervisor`, or
     when its `Supervisor` is given `-no-hold-fifos`. At most what a pipe holds
     is destroyed (64 KiB on Linux).
   - What comes back. The relaunched writer restores its latest checkpoint and
     replays its input log after `capture_pos`. It sends again, with the same
     numbers, everything it produced after that point. The destroyed messages
     among those reach the reader after all. The reader cannot tell that they
     were destroyed and sent again, and need not: it gets each once, in order.
   - What is lost. What the writer had written into the FIFO before its capture
     came from inputs before `capture_pos`, which the replay does not reach. Its
     `out_seq` counts it as sent, so it is not sent again. If some of it was
     still unread in the FIFO, it is lost. The reader finds the hole in the
     sequence numbers when a later message arrives on that channel (G8). Ways to
     repair more are in "Future work", none designed.
   - Where it cannot happen. Nodes that are not adjacent may crash together with
     no such loss. Two nodes joined only by the channels of a cycle cannot lose
     messages this way either. A round closes on one of their channels only
     while both are alive and responsive. So no closed checkpoint covers a
     backlog built while one was down, and a relaunched sender always replays
     from an older, already drained checkpoint and sends that backlog again. A
     crash of a node with a self-loop is a crash of both endpoints of the loop,
     and loses nothing either: its round closes only once its marker has come
     back round the loop, so a message still in the loop was sent after its
     latest checkpoint, and the replay sends it again (G5).
2. **External inputs.** What enters the graph from outside it (a manual write to
   a FIFO, an external program) cannot be regenerated by any node, so at that
   boundary delivery is at most once; inside the graph, the guarantees start
   from the first message a node logs. A source may number its `DATA` as a node
   does (`seq`, from 1, one more for each message, never reused): the receiver
   checks those numbers as on any other channel, so that a message lost at the
   boundary, in the window of the next limit, is reported (G8) and not lost
   silently. What a source sends without numbers gets no such check.
3. **Messages read from a FIFO but not yet written to the input log** when a
   node crashes. Such a message is lost, since its sender considers it
   delivered, and the sequence numbers of G5 show the hole (G8).
   - The window. A reader thread takes a block from the FIFO, up to 64 KiB, and
     writes every message of it to the log in one write before it queues any of
     them. The window runs from taking the block to that write: decoding and
     checking its lines, and getting the GIL back if another thread holds it.
     `FBPProcess` bounds that wait by setting the switch interval of the process
     to `GIL_SWITCH_INTERVAL_SECS`, 0.5 ms.
   - Long messages. A message longer than one read, one larger than the FIFO in
     particular, is in memory in part from its first read to its last. It stays
     exposed for as long as its writer takes to write the rest. If the node
     crashes before the last read, the rest reaches the relaunched reader as a
     fragment that no `HELLO` follows, which stops it (keeping the first part on
     disk is in "Future work").
   - Closing the window. A FIFO offers no way to look at what it holds without
     taking it, so the window can be made short but not closed.
   - A stop instead of a crash. A node may be stopped with a stop signal (see
     the Glossary) instead of killed, and then it loses less. A reader stops
     only between two blocks, and hands over every message of the block it
     holds. So of what the reader has taken from the FIFO, a stop loses only the
     part already read of a message whose end has not arrived, which the reader
     holds in memory. In the ordered stop of `debasher_stop_resident`, the stop
     signal comes after a halt: that message follows the marker of the halt on
     its channel, so its writer sends it again on resume. A stop signal with no
     halt before it (sent by hand, for instance) loses it like anything else the
     FIFO held, and G8 reports the hole. Its rest stays in the FIFO, and matters
     only if the FIFO outlives the stop, as on an external port whose source
     keeps it open: the reader of the next incarnation finds it as a fragment
     that no `HELLO` follows, which stops that reader.
4. **Stuck but alive.** A node whose brain thread is alive but blocked (infinite
   loop, deadlock) is not detected today: the heartbeat proves that its threads
   are alive, not that they make progress. Not a goal for now (see "Progress in
   the heartbeat" in Future work).
5. **Python nodes only.** The engine refuses a process of a resident program
   whose code is not a Python heredoc of a class of the runtime library
   (`FBPProcess` or a class derived from it, or `Supervisor`), although nothing
   on the wire depends on Python (see "Nodes in a compiled language" in Future
   work).
6. **`--mirror`** (the mirror tap of a fifo, the debugging aid behind the
   frontend's "Watch FIFO") is not available in resident programs: declaring it
   aborts the load of the program, before anything is launched. Resident
   processes keep their own input log.
7. **A node that has finished for good** takes no part in later rounds, so the
   consistent cut of an epoch that starts after it finished has no checkpoint of
   that node: its channel to the others is empty and its last state is its final
   one. Localized recovery does not need it; a global rollback would have to
   treat it (see Future work).
8. **A round that a newer one replaces** leaves the nodes that had not closed it
   without a checkpoint for its epoch, so that epoch has no complete cut. The
   round that replaced it does complete, at every node it reaches, and that is
   the cut that counts; localized recovery never uses a cut. It holds if the
   initiators start the same epoch (see numbered trigger in the Glossary).
   Rounds started closer together than they take to complete keep replacing each
   other, and none completes until they stop, so whatever starts rounds
   periodically has to leave more time between them than a round takes.
9. **A crash while a round is open.** A node that crashes while a round is open
   comes back with no round open. The markers it had received for that round are
   not replayed: the replay brings back only `DATA` and `CLOSE`. Making the case
   recoverable would need a round's partial progress to be durable, which is not
   designed.
   - A node that is not an initiator. The next marker of that round opens it
     again, and the node waits forever for the markers it had already received.
     It writes no checkpoint for that epoch, and the next round replaces it.
   - An initiator whose round a trigger opened. It had received no marker, so
     the round opens again when its own marker comes back round a cycle, and
     closes there. Its capture is then later than the first, so that epoch is
     not a consistent cut (see the global rollback in "Future work").
   - A halt. It cannot wait for the next round, because a node that has halted
     ignores every later trigger. So a node that is not an initiator and crashes
     while its halt is open never halts, while every other node does. The
     `--timeout` of `debasher_stop_resident` bounds that wait, whatever the
     reason a halted marker never goes past its baseline. Then the tool falls
     back to the hard kill of `debasher_stop`, and reports it with its own exit
     code (see "Failing loudly instead of retrying").
10. **A node that crashes again right after every relaunch** is not retried
    forever: after `MAX_RELAUNCH_ATTEMPTS` it is declared permanently failed and
    the escalation applies.

## Acceptance: how reliability is shown

Reliability is claimed only for what passes a **chaos test**, a run of a
reference program under random kills of its nodes, and each guarantee has a
focused test of its own. Both drive real runs of `debasher_exec`, not mocks.
How the tests are built is in "The tests of the Contract", at the end of this
document.

The reference program, `test/engine/debasher_chaos_ref.sh`, has the shapes
that matter: a cycle, a source, a sink, and a fan-in node with more than one
input port. The fan-in node keeps a node state, and its `process_data` is
sensitive to the order across ports. The program has three business nodes and
a `Supervisor`, `sup`:

```
        the test (a source)
              |
              | ext: external port, numbered DATA
              v
         +---------+  outloop       from_fanin  +--------+
         |  fanin  |--------------------------->|  loop  |
         |         |<---------------------------| (echo) |
         +---------+  loop_in         outfanin  +--------+
              |
              | outsink
              v
         +---------+
         |  sink   |  its input log is the trace
         +---------+
```

Each node sends heartbeats to `sup`. `sup` has an initiator port to `fanin`
and a manual trigger port fed from outside. It holds the FIFOs of the three
business channels, unless the program is given `-no-hold-fifos`.

`fanin` keeps a node state of two parts. One is a count of the messages it has
processed on each port. The other is a digest that folds every message it has
processed, on both ports, in order. For each message, `fanin` sends `sink` a
copy with its port, its value, its count and its digest. What arrives on `ext`
it also sends to `loop`, which sends it back. So `fanin` processes each value
twice, once on `ext` and once on `loop_in`, and `k` values make `2k` copies at
`sink`. The input log of `sink` is the trace of the run.

The chaos test runs the reference program and kills random nodes with
`kill -9` at random moments: several at once, adjacent pairs, and while a
snapshot round is open. The `Supervisor` relaunches them, and the run is
halted and resumed.

**Pass criterion.** A run with no loss passes when the trace shows that
`fanin` processed what was sent to it, each message once and in order, and
kept its state. A run with a loss passes only as "The exception" below says.

- Per port. On each port of `fanin`, the messages that the trace shows it
  processed are exactly the sequence that the writer of that port sent, in
  the order it sent them, with no duplicate and none missing.
- Node state. The state that `fanin` sends with each copy, its state after
  processing that message, goes on across every relaunch and resume, as if
  the node had never stopped.
- Interleaving. The whole trace only has to be some interleaving of the
  sequences of the ports, never a match with one frozen run. Which
  interleaving comes out is a race between independent writers, even with no
  failure.
- The exception. Limits 1 and 3 can lose a message beyond repair. The chaos
  test reaches limit 1 with `-no-hold-fifos` (see "Holding the business
  channels"). A run that hits either passes if it ends with an error of G8
  that names the channel, and the numbers of the missing messages when it can
  tell them.
- The source. The test, the source of `ext`, numbers what it sends (see
  limit 2, "External inputs"), so a message lost at that port ends in that
  error too.
- What always fails. A different result with no error (a message duplicated,
  lost or altered that nobody reported), and a run that never ends and reports
  nothing.

Besides the chaos test, each guarantee gets its own focused end-to-end test,
written in the guarantee's words (for the no-silent-loss guarantee: "send 5 and
then 7 through a fan-in node while a round is open: `process_data` receives
both").

Every piece of the implementation also gets a **mutation check**, because a test
that passes on the correct code does not show that it would fail on broken code.
On a scratch copy of the code, never in the repository, one specific fault that
the new tests are meant to catch is put back on purpose (the reader ends at
`CLOSE` again, a flag is ignored, a condition is inverted) and the suite is run:
at least one test must fail, and the faulty copy, the mutant, is then said to be
killed. If the suite still passes, the mutant survived: either the tests do not
really protect that behavior, or the mutant was not the fault it was meant to
be, and whichever it is gets fixed before the piece counts as done. It is done
by hand, with a handful of mutants per piece chosen among the ways the code
could plausibly be wrong; it is not an automated mutation-testing tool and it
does not measure coverage.

# Control envelope

Every message on a channel of a resident program is an envelope: one line
holding a small JSON object that says what kind of message it is (`type`) and
carries its content (`payload`). Wrapping everything in the same envelope lets
the business data and the traffic that the design itself needs (the markers of
a round, the commands to a node, the end of a writer, the resync after a crash)
share the same line-based transport and still be told apart, and lets the
reader thread of a port route each line by its type alone, without knowing
anything about what the business logic sends. This section defines the format
of the envelope ("Wire format"), what each field of each type means ("Fields of
each type"), and which types travel on which channels ("Channel topology"). The
mechanisms that produce and consume each type are described in their own
sections, cited along the way.

## Wire format

The format is JSON Lines: one JSON object per line, with `\n` as delimiter,
in UTF-8. Always serializing via `json.dumps` guarantees that a `\n` embedded in
the `payload` comes out escaped, so the line delimiter is safe with any payload.
Every writer of the engine (the runtime, the tools for resident programs and
"Talk to FIFOs" in the web UI) writes strict JSON (RFC 8259): a payload that
holds a NaN or an infinity, which Python's `json.dumps` would write as `NaN` or
`Infinity`, is refused when it is sent (`send_data` raises, as for any payload
that is not JSON, and "Talk to FIFOs" refuses what the user typed). The reader
thread of a node takes what Python's `json.loads` takes, so such a value written
from outside the program still reaches the node, which cannot send it on. A line
that is not valid UTF-8 is treated as one that is not JSON: it is dropped as the
fragment of a writer killed in the middle of a message when a `HELLO` follows
it, and otherwise it ends the reader thread; it never reaches the node altered
(see "The resync line (`HELLO`)").

There are five envelope types, each its own line/message (none nests inside
another, so the reader thread can dispatch by looking only at `type`, without
interpreting `payload`):

```json
{"type": "DATA", "seq": <int>, "payload": <any JSON value>}
{"type": "BARRIER", "payload": {"epoch": <int>, "halt": <bool>}}
{"type": "INTERACT", "payload": {"command": <string>, "args": {...}}}
{"type": "CLOSE", "payload": {"last_seq": <int>}}
{"type": "HELLO", "payload": {}}
```

## Fields of each type

- `DATA.seq`: the sender's per-channel sequence number (G5 in the Contract,
  see "Input log"), absent when the sender does not number what it sends.
- `DATA.payload`: free-form, whatever the business logic wants;
  `process_data(port_name, packet)` (see "`FBPProcess` class") receives
  it already deserialized. The reader thread never looks at it.
- `BARRIER.payload.epoch`: identifies the snapshot round; enough for the
  initiator (see "Chandy-Lamport barrier propagation") to recognize, in a
  cycle, that the marker coming back through its own input port is its own (no
  need to carry the initiator's identity).
- `BARRIER.payload.halt`: reuses the same `BARRIER` as an ordered shutdown
  (see "Ordered shutdown") instead of a snapshot.
- `INTERACT.payload.command`/`args`: an open catalog, extended as needed by
  whichever sections trigger it (`start_snapshot`, `shutdown`, `heartbeat`,
  `checkpoint_saved`, ...). `start_snapshot` and `shutdown` take an optional
  `args.epoch`, an integer (see numbered trigger in the Glossary).
- `CLOSE.payload.last_seq`: the sender's last `out_seq` for that channel, left
  out when the sender does not number what it sends (see `CLOSE` in the
  Glossary). Sent by a writer when it has finished for good; a halt sends
  none. The reader hands it to the brain thread in order and then drops
  whatever follows it (a `Supervisor` reader delivers it).
- `HELLO`: empty payload, sent as the first line of every incarnation of a
  writer, together with a leading blank line (see "resync line" in the
  Glossary; the transport decision of "Reconnecting after a node failure").
  Consumed by the reader thread.
- No `port_name` field on any type: each reader thread (see "`FBPProcess`
  class") already knows which port a message came from by construction (it is
  dedicated to that FIFO); it gets attached once the message enters the
  in-memory internal queue, not in the wire format.

The reader thread checks these fields before anything else sees the envelope:
`seq` and `last_seq` are integers when present, `epoch` is an integer and
`halt` a boolean, `command` is a string, and the payload of every type but
`DATA` is an object. An envelope that is JSON but malformed (a field of the
wrong type, a missing key, an unknown type) is dropped with a warning, and the
reader goes on, unless it follows the fragment of a dead writer, which only a
`HELLO` excuses. Only a writer outside the program can send one, and nothing of
it can be recovered: what it meant to say is lost, with the warning as its only
trace. A line that is not JSON is another matter: it is dropped only as the
fragment of a dead writer before a `HELLO`, and otherwise ends the reader (see
"Wire format"). The arguments of a command are checked by its handler, since
the catalog is open: a trigger whose epoch is not an integer is ignored with a
warning.

## Channel topology

Which types a channel carries depends on its kind (see "Channel kinds declared
with the fifo"). `HELLO` and `CLOSE` belong to the transport, not to any kind
of channel: every writer thread of the engine sends `HELLO` when it starts and
`CLOSE` when it finishes for good, whatever its channel (a writer from outside
the program may leave both out). The other three types split by kind: `DATA`
and `BARRIER` travel only on business channels and on channels to an external
port, `INTERACT` only on the heartbeat channels and on the channels of
commands, so the two never share a channel. The engine and the runtime write
them so, and the reader thread of each port checks it, since a writer outside
the program may not: a control port, and every channel of the `Supervisor`,
takes only `INTERACT`; a business port and an external port take `DATA` and
`BARRIER`. Any other type is dropped with a warning, as a malformed envelope
is (see "Fields of each type"). Channel by channel:

- Between business processes (`FBPProcess`), the normal FBP graph channels
  carry `DATA` and `HELLO` in normal operation (and `CLOSE` from a writer that
  finishes for good), and `BARRIER` interleaved
  when a snapshot/shutdown is in progress; this is how Chandy-Lamport
  propagates the marker: each node forwards it through its own output ports,
  the same ones it uses for `DATA`, never "upward" to anywhere else.
- Between each node and the supervisor, a separate channel (heartbeat) that only
  carries `INTERACT`: a single input port per node (not two), multiplexing
  `{"command": "heartbeat"}` and
  `{"command": "checkpoint_saved", "args": {"epoch": ..., "path": ...}}`
  (see "Checkpoint persistence") on the same channel; there is no real
  contention between the two (lightweight, infrequent messages), and separate
  ports would only double the supervisor's manual wiring for no benefit.
- From the supervisor to each initiator, an initiator port: a channel of
  commands that the supervisor owns and defines with the tag `--control`, so
  that the initiator reads it as a control port. It carries only `INTERACT`
  (`start_snapshot`, `shutdown`, see "Initiator ports"), never a marker, so the
  round it opens never waits on it. A `CLOSE` on it does not close it, and the
  supervisor sends none when it stops (see control port in the Glossary).
- From outside the program, the other channels of commands: the manual trigger
  port of the supervisor, also tagged `--control`, whose `INTERACT` the
  supervisor relays to every initiator port (see "Manual trigger channel"), and
  any control port of a node that an actor outside the program writes into
  directly (finding it through the node's control ports file). They carry only
  `INTERACT`.
- From outside the program into an external port of a node: `DATA`, like a
  business channel, but no marker of its own, so a round never waits for it. A
  source that knows the protocol may still write the marker of the round the
  initiator opened, which is then read like on any other port. A `CLOSE` on it
  closes it for good, since its writer is not expected to come back (see
  external port in the Glossary).
- The supervisor never sees a `BARRIER`: it does not take part in the barrier
  protocol (see "Chandy-Lamport barrier propagation"), it only speaks
  `INTERACT`. A `DATA` or `BARRIER` that reaches one of its channels anyway is
  dropped by the reader with a warning.

# Channel kinds declared with the fifo

The kind of every channel of a resident program, and its direction, are
declared in the module's own options, where the engine can read them when it
loads the program: a business channel, a channel of commands to a control port,
or a channel fed from outside to an external port. Without this they are only
in the Python class of each node (`INPUT_PORTS`, `OUTPUT_PORTS`,
`CONTROL_PORTS`, `EXTERNAL_PORTS`), which the engine cannot see. Knowing them at
load lets the engine check, before launching anything, that the channels of a
program can carry a round to every node; lets each node take its port lists
from the engine instead of declaring them a second time; and gives the frontend
what it needs to show and edit the channels of a resident program.

## Direction: the owner writes

An output option is named `-out...` or `--out...`, in every program, and
`define_opt_from_proc_out` and `define_opt_from_proc_task_out` only connect an
input option to an output option of another process, or of the same one (a
self-loop). In a resident program, every FIFO is created once, by the
`define_fifo_opt` (or `define_fifo_opt_generator`) of one process, its fifo
owner, through an output option: the owner writes it. The process at the other
end reads it, through an input option connected to that output, or no process of
the program does, and the other end is outside (`__EXTERNAL__` in the engine's
fifo registry). The one exception is a fifo whose writer is outside the program:
the process that reads it has to create it, through an input option, and the
fifo carries a fifo tag. The engine's registries (`DEBASHER_PROGRAM_FIFOS` and
`DEBASHER_FIFO_READERS`, written to `program.fifos`) give the owner and the
other end of every fifo, task by task, and the other end may be another task of
the owner's own array; the option through which the owner defines each fifo is
recorded too (`DEBASHER_FIFO_OWNER_OPTS`). The direction of every channel
follows from them and from the tags, with nothing read from Python.

## Tags: `--control` and `--external`

`define_fifo_opt` and `define_fifo_opt_generator` take an optional tag, the same
way as `--mirror`, stored in a registry of its own:

- no tag: written by its owner, and read by the process at the other end, if
  any, through an input port: a heartbeat channel when the `Supervisor` reads
  it (see "`Supervisor` class"), and otherwise a business channel;
- `--control`: a channel of commands, whose reader's end is a control port. Its
  writer is the `Supervisor`, which owns it (an initiator port), or someone
  outside the program, and then the reader owns it;
- `--external`: a channel fed from outside the program, owned by its reader,
  whose end is an external port.

From the reference programs:

```bash
# fanin (debasher_chaos_ref.sh)
define_fifo_opt "-ext" "fanin_ext" optlist --external
define_opt_from_proc_out "-trigger" "sup" "-outtrig_fanin" optlist
define_fifo_opt "-outloop" "fanin_to_loop" optlist

# sup
define_fifo_opt "-outtrig_fanin" "sup_trig_fanin" optlist --control
define_fifo_opt "-manual" "sup_manual" optlist --control

# start (debasher_array_ref.sh)
define_fifo_opt "-trigger" "start_trigger" optlist --control
```

The manual trigger port of the `Supervisor` is tagged `--control` as well: its
writer is outside, so its owner reads it. The tags only mean something in a
resident program, and a general program that uses them is refused when it is
loaded, as a resident program that uses `--mirror` is.

## Validation when the program is loaded

With the direction and the kind of every fifo, the engine builds the graph of
the business channels between the business nodes, task by task (the `Supervisor`
takes no part in rounds, so its channels are left out), and checks it, with the
flags of every fifo, before launching anything, in
`debasher::_validate_program_fifo_flags`, which `debasher_exec` calls once the
other end of every fifo is known:

1. Every node can be reached from an initiator, a node that reads a control
   channel, through business channels in the direction in which they carry a
   marker.
2. Every tagged fifo is used as its tag says. A fifo tagged `--external` has
   its other end outside the program, so that its owner reads it. A fifo tagged
   `--control` either has its other end outside, and its owner reads it, or is
   owned by the `Supervisor` and read by a node.
3. The owner of a fifo defines it through an output option, except a tagged
   fifo fed from outside, which it defines through an input option. A fifo that
   a node reads from outside and that lacks its tag is refused by this rule.
4. No fifo is declared with `--mirror` (see "Why the log is not built on the
   mirror tap").

A fifo without a tag whose other end is outside is a business channel from its
owner to someone outside the program, a node that writes its results out.

A violation stops the load with an error that names the node or the fifo, and
the rule. Each check walks the fifos once; the registries it reads are already
built by then, for every task of every array and generator. In the fan-in of two
nodes fed from outside (see "Chandy-Lamport barrier propagation"), where nodes
`a` and `b`, whose only inputs come from outside, both write to a node `c`, a
program in which only `a` has a control channel is refused by rule 1, since `b`
cannot be reached.

## Ports from the engine

Once the program is loaded and its channels are checked, the engine gives
each task of an `FBPProcess`, and the `Supervisor`, its ports, taken from the
same registries and tags (`debasher::_register_resident_task_ports`). For a
node:

- The owner of a fifo has an output port on the option through which it
  defines it, or, for a tagged fifo fed from outside, an input port, which is
  also a control or an external port, as its tag says.
- The process at the other end, when it is a node, has an input port on the
  option through which it reads the fifo (`DEBASHER_FIFO_READER_OPTS`), which is
  also a control port if the fifo is tagged `--control`.
- The output port whose other end is the `Supervisor` is the node's
  `SUPERVISOR_PORT`. A node with more than one is refused when the program is
  loaded, since a node has a single heartbeat channel. In a program with a
  `Supervisor`, a node with none is refused too: it would run unsupervised,
  with nothing to say so. This is what a task of an array beyond those the
  `Supervisor` connects to would do, when the option that sizes the
  heartbeat channels of the `Supervisor` says fewer tasks than the array
  builds.

For the `Supervisor`, the same fifos seen from its end:

- A fifo without a tag that a node defines and the `Supervisor` reads is the
  heartbeat channel of that node: an entry of `NODE_PORTS`, the node as its
  key and the option through which the `Supervisor` reads it as its value.
- A fifo that the `Supervisor` defines with the tag `--control` and a node
  reads is an initiator port, an entry of `INITIATOR_PORTS`.
- A fifo that the `Supervisor` defines with the tag `--control` and that is fed
  from outside the program is its `MANUAL_TRIGGER_PORT`. A `Supervisor` with
  more than one, or with one and no initiator port, is refused when the program
  is loaded (see "Initiator ports").
- Any other fifo that the `Supervisor` defines is refused when the program is
  loaded: the `Supervisor` takes no part in the business channels.
- A fifo without a tag whose two ends are nodes is a business channel, whose
  FIFO the `Supervisor` holds (see "Holding the business channels"): an entry
  of `HOLD_FIFOS`, named by its path under the fifo directory of the program,
  `<owner process>/<fifo>`, since it is not an option of the `Supervisor`.

A `Supervisor` of more than one task is refused too (see "Port declaration and
node identity").

With them goes the startup deadline of each node whose computational
specifications give one, `startup_timeout_s` (see "Computational
specifications of a resident process"), into `NODE_STARTUP_TIMEOUT_SECS`,
which "Failure detection" uses.

So the heartbeat channels need no tag of their own: the role of the process
at each end, which the engine already knows, says which fifo is which. With
the options of the module as the only place that says what the ports are, a
program whose number of nodes comes from the command line has a `Supervisor`
that watches as many nodes as there are, with no code that depends on it.

The ports of a node may form a fanout family (see the Glossary of
`doc/design_doc_engine.md`), such as `-outf-ith`, defined in a loop over an
option of the command line, as in a general program. The number may instead be
that of the tasks of another process, asked for with `get_process_num_tasks`
(see "Arrays and option generators" in `doc/design_doc_engine.md`). The
topology is still fixed before the run starts. Only how many ports and tasks
there are changes from one run to another. A relaunch gets the ports it had:
it runs the same generated script, with the same options, and a node that asks
for the number of tasks asks again inside its task, where the execution
context gives the same answer. A run with another number has to start afresh
(see "`debasher_reset_resident`: a clean start"). The engine does not check
that a node restored from a checkpoint has the ports it had, and the closed
ports and the sequence numbers in the checkpoint are keyed by port name.

The generated script of each process carries the ports of every task
(`DEBASHER_RESIDENT_TASK_PORTS`), so that a relaunch gets them too, and the
wrapper of a task exports its own as `DEBASHER_PROCESS_PORTS`. For `fanin`, in
the chaos reference program:

```
input=ext,loop_in,trigger;output=outhb,outloop,outsink;control=trigger;external=ext;supervisor=outhb
```

and for its `Supervisor`, `sup`, where a task of a process with several tasks
would be named `<process>:<idx>`, as `debasher_stop_resident -x` names it (see
"Port declaration and node identity"):

```
nodes=fanin=hb_fanin,loop=hb_loop,sink=hb_sink;initiators=outtrig_fanin;manual_trigger=manual;startup=;hold=fanin/fanin_to_loop,fanin/fanin_to_sink,loop/loop_to_fanin
```

`FBPProcess` sets `INPUT_PORTS`, `OUTPUT_PORTS`, `CONTROL_PORTS`,
`EXTERNAL_PORTS` and `SUPERVISOR_PORT` on the instance from it, and the
`Supervisor` `NODE_PORTS`, `INITIATOR_PORTS`, `MANUAL_TRIGGER_PORT`,
`NODE_STARTUP_TIMEOUT_SECS` and `HOLD_FIFOS`, before anything uses them
(`_take_ports_from_engine`). The options of the module are then the only
place that says what the ports of a process are: a class that declares any
of them, even with the same value, stops the process with an error. A
process built without the engine, as the unit tests build them, gets no such
variable and takes its ports from the attributes of its class. The order of a
list means nothing, in the variable or in the class: every use of a port list
is port by port.

## What the fifo tags leave out

- The check says which nodes can be initiators, not whether a trigger really
  reaches them: that depends on who writes into their control channels, a
  `Supervisor` whose `INITIATOR_PORTS` lists them or someone outside the
  program.
- A node cut off at run time, by a node that fails for good, is a separate case,
  handled by "Escalation on a permanent node failure".

# `FBPProcess` class

`FBPProcess` is the class from which every business node of a resident program
derives: a long-running process with a state of its own, which exchanges
envelopes with its peers over FIFOs, takes part in the rounds that capture a
consistent snapshot, keeps a log of what it receives and, after a crash,
returns to where it was from its latest checkpoint and that log. A module
defines a node by writing a subclass of it that redefines a few hooks (see
"Defining a node"). The runtime library ships two such subclasses of its own,
`DirectoryWatcher` (see "Observing the outside world") and `ProgramLauncher`
(see "`ProgramLauncher`: batch runs from a node").

`FBPProcess` derives in turn from `_PortWorker`
(`engine/debasher_runtime_transport.py`), which it shares with the
`Supervisor` (see "`Supervisor` class"). `_PortWorker` holds what any process
of a resident program needs to talk over its FIFOs, whatever its role:

- parsing `argv` into `self.opts`, taking the ports from the engine and
  checking them;
- the logger, `self.log`, and the computational specifications that set class
  attributes of the process (see "Computational specifications of a resident
  process");
- opening the FIFOs, one reader thread per input port feeding the shared
  inbound queue, one writer thread per output port with its own outbound queue
  (both of them handling `HELLO` and `CLOSE`, see "Channel topology"), and the
  brain thread, whose loop each subclass supplies;
- `start_threads()` and `stop_threads()`, which start and stop all of them
  (`run()` of `FBPProcess` starts the writer threads earlier, see "Startup
  sequence: `run()`").

It knows nothing of rounds, checkpoints or the input log. `FBPProcess` adds all
of that on top: the heartbeat thread, the barrier logic, the dispatch of
`INTERACT` commands, the input log (a reader thread hands what it reads to
`FBPProcess`, which records it in the log before queuing it for the brain
thread), the checkpoints, and the startup sequence of `run()`, which restores
the node and replays its log.

The rest of this section starts with an overview of the class, then covers how
a node is defined, its limits and how it observes the outside world, then the
pieces that make a node recoverable: state capture, startup, barrier
propagation, ordered shutdown and checkpoint persistence. It closes with how a
node test builds a node without the engine to check its business logic.

## Overview of the class

- **Where the code lives**: `engine/debasher_runtime_lib.py` is the module that
  a resident process's heredoc imports
  (`from debasher_runtime_lib import FBPProcess`, or `Supervisor`), and no
  source gets prepended into the heredoc itself. The code is split into modules
  of their own, one layer each, where every module imports only from the ones
  before it:
  `debasher_runtime_envelope.py` (the wire format of "Control envelope"),
  `debasher_runtime_transport.py` (argv parsing, the fifo endpoints and
  `_PortWorker`), `debasher_runtime_inputlog.py` (`_InputLog`, "Input log"),
  `debasher_runtime_fbp.py` (`FBPProcess`), `debasher_runtime_supervisor.py`
  (`Supervisor`, see "`Supervisor` class"), `debasher_runtime_launcher.py`
  (`ProgramLauncher`) and `debasher_runtime_watcher.py` (`DirectoryWatcher`).
  `debasher_runtime_testing.py`, the node harness, comes on top of them, and
  only tests import it. `debasher_runtime_lib.py` keeps
  `DEBASHER_SHUTDOWN_TOKEN`, a Python mirror of the Bash constant, and
  re-exports the names that a module and the tests use, so nothing that imports
  it depends on the layout. All of them are `python_PYTHON`-installed per
  `engine/Makefile.am`, in the same directory, which is the one that the
  heredoc's `sys.path` line (see below) already adds.
- **How a heredoc finds the library**: a heredoc runs as `python3 -c "<text>"`
  (`debasher::_create_heredoc_func_body` in
  `engine/debasher_lib_programs.sh`), which does not go through
  `engine/Makefile.am`'s `.py:` suffix rule, the one that would otherwise
  prepend `sys.path.append("$(pythondir)")`. So the text of a Python heredoc is
  itself prefixed with that same call
  (`debasher::_python_heredoc_sys_path_prelude`), ahead of the code of the
  module author.
- **Port declaration**: the ports of a node are lists of option names,
  `INPUT_PORTS`/`OUTPUT_PORTS` (e.g. `["inf"]`), with `CONTROL_PORTS`,
  `EXTERNAL_PORTS` and `SUPERVISOR_PORT` (a single name) beside them. A node
  run by the engine takes all five from it, and its class must not declare
  any (see "Ports from the engine"); a node built without the engine, as the
  unit tests build them, declares them as class attributes. `_PortWorker`
  parses `argv` generically when the node is built, into a `self.opts` name ->
  value dict (the engine's existing `-optname value` CLI convention, untouched);
  `INPUT_PORTS`/`OUTPUT_PORTS` tell it which of those entries are FIFO paths
  to open reader/writer threads on. Any other option (e.g. a plain
  `-threshold` value, or one from the command line of the program) stays
  available in `self.opts` with no special handling. A flag, an option given
  with no value (`explain_flag`, `define_flag`), is listed in the class's
  `FLAGS`, by name without the dash, since `argv` alone cannot tell it from
  an option whose value starts with a dash; it is `True` in `self.opts` when
  it is given. `CONTROL_PORTS` names which of the `INPUT_PORTS` carry only
  commands (see control port in the Glossary); `EXTERNAL_PORTS` names which are
  fed only from outside the program (see external port in the Glossary); a name
  in either list that is not an input port, or a `SUPERVISOR_PORT` that is not
  an output port, is refused when the node is built.
- **Threads**: one reader thread per `INPUT_PORTS` entry, each reading its
  FIFO in blocks of up to `_READ_BLOCK_BYTES`, cutting them into lines and
  handing all the envelopes of a block to `_on_arrivals`, which records them in
  the input log and pushes each one onto a **shared inbound queue** as
  `(pos, port_name, type, payload, seq)`; one writer thread per `OUTPUT_PORTS`
  entry, each with **its own outbound queue** (the brain thread enqueues the
  encoded line there instead of writing to the FIFO directly, so a slow/stalled
  neighbor on one output port only blocks that port's writer thread, never the
  rest of the process); a single brain thread consuming the shared inbound
  queue; an independent heartbeat thread with its own timer; and, in a node
  whose class defines `observe()`, the observation thread.
- **Which threads keep the process alive**: a thread is a daemon exactly when it
  cannot always be stopped. A daemon thread dies with the process, unwarned and
  unjoined; a thread that is not a daemon keeps the process from ending until it
  has returned. The reader, brain, heartbeat and observation threads can always
  be stopped, each seeing the stop from where it waits: a reader at the end of
  its wait for data, which lasts at most `_READER_POLL_MS` (200 ms), the brain
  in the `_STOP` sentinel on its queue, the other two in an event. So they are
  not daemons: `stop_threads` stops them and waits for them with no limit, and
  each one finishes what it was doing, the brain thread the message in hand,
  instead of being cut in the middle of it.

  A writer thread cannot always be stopped. When its reader is down and the pipe
  is full it stays blocked in `write()`, and the write does not even fail, since
  the node holds both ends of the FIFO so that the channel outlives a crash. If
  it were not a daemon, a node with a stalled neighbor would never end. So it is
  one: `stop_threads` waits for it for `WRITER_STOP_TIMEOUT_SECS`, then abandons
  it, and the process ends anyway. All it loses is its outbound queue, which the
  checkpoint and the replay of the input log cover.

  The price of the threads that are not daemons is that the process cannot end
  while one of them runs. `run()` therefore stops them when starting the
  threads fails, and a `process_data` or an `observe` that never returns keeps
  the node alive after SIGTERM (see "Stuck but alive" in "Limits and non-goals"
  and the fallback to SIGKILL of `debasher_stop_resident`).
- **Health reporting**: passive, not pushed; on its own timer, the heartbeat
  thread polls `Thread.is_alive()` on every reader and writer thread, on the
  brain thread and on the observation thread, and only reports "alive" to the
  supervisor if all of them still are (a Python thread that dies from an
  uncaught exception does so silently, without crashing the process, which is
  exactly what `is_alive()` catches).
- **Subclass extension points**: `process_data(port_name, packet)`: `packet` is
  the `DATA` envelope's `payload`, already deserialized, never the full envelope
  (this method is only ever called for `DATA`; `BARRIER`/`INTERACT` dispatch is
  handled generically and never reaches it); `capture_node_state()`,
  `restore_node_state(state)` (logical state only), `initialize_runtime()`
  (rebuilding external resources, see "Startup sequence: `run()`").
- **Generic barrier logic** (valid for 1 or N input ports): on receiving the
  first `BARRIER` marker for an epoch (on any input port, or as the initiator),
  capture state and forward the marker on every output port; track the set of
  input ports still pending (marker not yet received) for that epoch. While any
  are pending: record a copy of the `DATA` arriving on those still-pending ports
  (that recorded set is the state of that channel) and also process every
  `DATA`, on any port, normally, as usual (what arrives after a port's marker
  belongs to the next epoch). Once every input port's marker has arrived, or
  its writer has said `CLOSE`, the node's part of the snapshot is complete.
- **`INTERACT` logic**: the initiator's inbound connection from the supervisor
  is not a special kind of port for reading; it is one more `INPUT_PORTS` entry,
  handled by the same generic port-agnostic, type-based dispatch as everything
  else, but it is also listed in `CONTROL_PORTS`, which is what keeps the
  barrier from waiting for a marker that it will never carry.
  `command: "start_snapshot"` enters the exact same generic barrier logic above
  (capture state, forward markers, track own input ports as pending, including
  the node's own port in a cycle) as receiving a peer's `BARRIER` would, just
  triggered by `INTERACT` instead; `command: "shutdown"` is identical but
  forwards with `halt=True`. An unrecognized `command` logs a warning and is
  ignored, it never aborts the process (the command catalog, "Control
  envelope", is deliberately open-ended).
- **Logging**: `FBPProcess` exposes a preconfigured `self.log` (Python's stdlib
  `logging`), which `_PortWorker` sets up, same pattern as the existing
  `dispatch` process in `data/programs/dynamic_fanout_dispatcher.py` (stderr
  output, format including thread name, useful here since the process is
  inherently multi-threaded). The framework itself logs its own lifecycle
  events (thread start/stop, barrier epoch open/close, checkpoint saved,
  heartbeat) with it. Level is configurable via a plain `-log-level` option,
  declared by the module author in `_explain_opts`/`_define_opts` exactly like
  any other option (the convention of `debasher_dynamic_fanout_fifos.sh`): the
  engine has no mechanism for it, it is just another entry in `self.opts`; a
  sensible default applies if the module does not declare it.
- **Periodic snapshots come from outside the node**: a node never starts a
  round on its own; every round starts with a trigger, relayed by the
  `Supervisor` or written from outside the program. A program in which nothing
  triggers `start_snapshot` regularly closes no epoch, and its input logs grow
  until their size cap (see "Pruning and the size cap"), which then stops being
  a safety net and becomes the normal way the program fails.
  `debasher_snapshot_resident --every` is what triggers rounds regularly, with
  or without a `Supervisor` (see "`debasher_snapshot_resident`: rounds from
  outside the program"); a timer of the initiator's own is not built (see
  "Periodic snapshots from a node's own timer" in Future work).

## Defining a node

A node is written as a class that derives from `FBPProcess`, in the Python
heredoc of a process of a resident program. The engine checks, without
importing anything, that the heredoc has a top-level class deriving from
`FBPProcess` or `Supervisor` (`debasher::_classify_resident_process_role`). It
never instantiates it: the heredoc itself creates the object, which parses the
options of the process from `argv`, and calls `run()`, in the line
`<Name>().run()`. That line may also go under `if __name__ == "__main__":`,
which holds when the engine runs the heredoc, since `python3 -c` runs it as the
main module. When it loads the program, the engine refuses a heredoc that has
neither form (`debasher::_check_resident_class_name`), even one that starts
the node in another way: it only parses the heredoc, and without that line a
process would end at once having started nothing. The node harness recognizes
both forms too, and runs the heredoc without starting the node (see "Testing a
node without the engine").

A resident program has nodes only, and no sequential processes (see "Sequential
processes" in `doc/design_doc_engine.md`): the engine refuses
`add_debasher_seq_process` in it. The work of a node is in `process_data`, which
replay runs again on the `DATA` records of its input log, and a step run from
it, such as a job sent to Slurm, would run again on every replay, with nothing
that ties it to the run before. A node that needs such work launches a general
program, which may have sequential processes, through a `ProgramLauncher`, whose
batch runs are registered so that a replay does not launch them twice (see
"`ProgramLauncher`: batch runs from a node").

The class is named after its process, in CamelCase: every part of the process
name between dots and underscores, with its first letter in upper case
(`counter` gives `Counter`, `org.ns.count_words` gives `OrgNsCountWords`). The
conversion leaves a name already in CamelCase as it is, so a node is named in
CamelCase by convention (`Counter`), and its process and its class then share
one name. A namespaced name always differs from its class, since the name of a
class holds no dots. The runtime names the logger of the node after its class,
so a line of a log says which process wrote it. The heredoc defines exactly one
class that derives from a class of the runtime library, and its name hides
nothing that the code of the node could need: not a class of the runtime
library, not a Python builtin, and not a name that the heredoc binds at its top
level, such as one that it imports. When the program is loaded, the engine
checks all of this by parsing the heredoc
(`debasher::_check_resident_class_name`) and refuses a process that breaks a
rule, naming it. A process called `supervisor` or `type_error` therefore has to
be renamed, since its class would hide `Supervisor` or `TypeError`.

The class takes its ports from the engine (see "Ports from the engine") and
redefines four hooks. Each runs on a known thread, which is what lets the
framework keep the state that a node captures in step with what it has sent:

- `process_data(port_name, packet)` runs on the brain thread, once for each
  `DATA`, in the order of the input log, and on the thread that called `run()`
  while the node replays that log. It is the only place from which a node sends,
  with `send_data(port_name, payload)`, which raises anywhere else.
- `capture_node_state()` runs on the brain thread, when a round opens, and the
  runtime keeps a deep copy of what it returns.
- `restore_node_state(node_state)` and `initialize_runtime()` run on the thread
  that called `run()`, before any other thread starts. They cannot send.

No hook runs when nothing arrives: a node acts only in reaction to what it
receives (see "source" in the Glossary), so whatever starts the activity of a
program is written from outside into an input port. A node that has to go on
emitting after that (a counter, the ticks of a clock) sends itself the message
that triggers its next step, through a self-loop. Each call to `process_data`
emits one step and sends the next trigger, and the node state says when to stop.
Each call is short, so the node takes part in rounds and answers commands
between steps. A module that needs several inputs together keeps what it has
received in its node state and decides in `process_data` when it has enough,
because the framework delivers each message as it arrives, with no join across
ports.

A module cannot tell a replay from the first execution: `process_data` gets the
same calls, in the same order, and nothing says which of the two is running, so
that neither the node state nor what it sends can depend on it. Two things have
to differ, both in the framework: what `send_data` does at the limit of the
outbound backlog (see "Checkpoint persistence"), and the pace of a node that
emits on its own: `sleep(seconds)` waits `seconds` when called from
`process_data`, does not wait while the node replays its log, where the pace of
the first execution has no use and would only delay the recovery, and returns
early once the node is told to stop, so that a stop is not delayed further (see
"Ordered shutdown"). Only when the next step comes changes.

How a node finishes for good is not defined yet: `run()` returns only on a stop
signal, and a stop sends no `CLOSE` (see "A node that finishes for good" in
Future work).

## Computational specifications of a resident process

The computational specifications that a program gives to
`add_debasher_process`, next to `cpus`, `mem` and `time`, also configure a
process of a resident program. This list gives them by who they are for, and
ends with the one limit that no specification sets:

- For a node, the limits of a node (see the Glossary), class attributes of
  `FBPProcess` with a default each, that a module can redefine in its class and
  that the specification sets over what the class says:
  - `input_log_max_mb` sets `INPUT_LOG_MAX_BYTES`, 100 MiB by default (see
    "Pruning and the size cap").
  - `out_backlog_max_mb` sets `OUT_BACKLOG_MAX_BYTES`, 8 MiB by default (see
    "Checkpoint persistence").
  - `out_backlog_fail_mb` sets `OUT_BACKLOG_FAIL_BYTES`, 64 MiB by default (see
    "Checkpoint persistence").
  - `gil_switch_interval_ms` sets `GIL_SWITCH_INTERVAL_SECS`, 0.5 ms by default
    (see "Messages read from a FIFO but not yet written to the input log" in
    "Limits and non-goals").
- For a node: `startup_timeout_s`, its startup deadline in seconds, which the
  engine passes to the `Supervisor` (see "Failure detection").
- For the `Supervisor`: `heartbeat_timeout_s` and `startup_timeout_s` (see
  "Failure detection").
- For a launcher node: `max_concurrent_runs` and `batch_sched` (see "Launching
  from the queue on disk").
- Not a specification: the open descriptors of the process (`RLIMIT_NOFILE`). A
  process needs two for each of its ports, since it holds both ends of every
  FIFO (see "Ghost connections"), a `Supervisor` one more for each held FIFO
  (see "Holding the business channels"), and a margin, `FD_MARGIN`, for the
  rest. That number follows from the program, and grows with it when a fan-in
  node or a `Supervisor` has as many ports as the command line says, so nobody
  has to give it: before it opens anything, the process raises its soft limit
  to what it needs (`_raise_fd_limit`), which it may do up to its hard limit.
  When the hard limit is lower, it stops with an error that gives both numbers,
  and the hard limit has to be raised for the session that launches the
  program.

For example, `add_debasher_process "relay" "cpus=1; mem=32; time=00:10:00;
out_backlog_fail_mb=128"`. Sizes are in MiB and the interval in milliseconds.
Each value but `batch_sched`, when given, must be a positive number, and
`max_concurrent_runs` a positive whole number. The engine checks them when it
loads the program (`DEBASHER_RESIDENT_COMP_SPEC_NAMES`), before anything is
launched. An `input_log_max_mb` or an `out_backlog_fail_mb` smaller than one
message stops the node at its first message, which the engine cannot foresee,
since it does not know the size of the messages. The built-in scheduler exports
the computational specifications of the process to it as
`DEBASHER_PROCESS_COMP_SPECS`, from the specification that the generated script
carries, so a relaunch gets them too, and each class sets those that it reads on
its instance when it is created (`_apply_comp_specs`), and ignores the other
fields.

## Observing the outside world

A node acts only in reaction to what it receives, but some have to watch
something outside the program: a directory where files arrive, a queue, the
batch runs a launcher node started. What such a node sees is different every
time it looks, so looking cannot happen in `process_data`, which a replay runs
again. It happens in `observe()`, a hook that a class may define, on a thread
of its own, the observation thread, every `OBSERVE_INTERVAL_SECS` or when
`observe_now()` wakes it, and only while the node is live, never in a replay.
What `observe()` sees enters the node as an input:

- `inject(payload)` writes it, as a `DATA`, to the input log, under the name
  `OBSERVE_PORT`, and queues it for the brain thread, as a reader thread does
  with what it reads from a fifo and through the same code (`_on_arrivals`,
  under the lock that orders the arrivals of every port), so that the order of
  the log is the order in which the brain thread gets the envelopes, whatever
  thread logs them. The brain thread hands it to `process_data`, which decides
  what the node does about it; a replay finds it in the log, and does not look
  at the world again.
- `inject()` returns once the observation is in the input log: whatever
  `observe()` records after it returns, that it reported something for
  example, never gets ahead of what the node has logged.
- The observe port is a name, not a fifo: the node does not read it from a
  channel, rounds never wait on it, and the program does not declare it. A name
  that is also one of the node's input ports stops the node when it is created,
  since `process_data` could not tell the two apart. What the frontend shows of
  it is a property of the node, that it observes something, not a port to
  connect.
- A class that does not define `observe()` has no observation thread, and one
  with no observe port may observe only to act, `inject()` being then an
  error. `inject()` is an error from `process_data` too, since an input that
  processing made would be made again by every replay.
- The observation thread counts in the health of the node, like the others:
  if `observe()` raises, the thread ends and the heartbeat stops.

After a crash, `observe()` does not know what it had brought in, and brings it
in again; `process_data` drops what it already acted on, keeping it in its
node state, so an observation may enter more than once, and is acted on once.

`DirectoryWatcher` (`engine/debasher_runtime_watcher.py`) is a node of the
runtime library built on this: it watches the directory that the option
`-watchdir` of its process gives (an absolute path, or one relative to the
directory of its module; a node without it stops when it is created), and for
each file whose name matches `PATTERN` sends on `REQUESTS_PORT` a request for a
launcher node (see "`ProgramLauncher`: batch runs from a node"), once the file
is complete. A file is complete once its size and modification time have stayed
the same for `STABLE_OBSERVATIONS` observations in a row, a file whose name
starts with a dot never counts, and a module whose files are complete in another
way (a companion file, a rename at the end of a copy) redefines `is_complete()`;
`request_for()` makes the request from the path. A watcher without the output
port `REQUESTS_PORT` sends nothing, and says so in a notice (see "Notices").

A file is known by its path alone, until a clean start of the program: one
removed that arrives again under the same name, with other contents, gets no
request, in the same incarnation or after a relaunch, so the directory has to
receive names that do not repeat and, with the default request, which names the
run after the file without its extension, names that differ in more than their
extension. Knowing a file by its size and modification time too would not be
enough, since a launcher node drops a request for a run directory that another
request owns (see "The run directory and who owns it"). The node state keeps one
path per file brought in, also of those that are gone, so a checkpoint grows
with them; `debasher_reset_resident` forgets them with the rest of the node
state (a run directory under an absolute runs root stays, see "Stopping and
resetting a launcher node").

## Notices

A node sometimes has something to tell the person who watches the program that
is neither a message on a channel, which goes to another node, nor a line of
its log, which nobody reads until something has gone wrong: that its
configuration file is missing and it does nothing until it appears, or that the
service it forwards to does not answer. The code of the node, which the module
writes, leaves such a message with `set_notice(text, level="info")`, and takes
it away with `clear_notice()`.

- **One notice, not a log.** A node has at most one notice, kept in its notice
  file (see the Glossary), and a new one replaces the previous one, so that the
  notice says how the node is now and never grows. `level` is `info` or
  `warning`, anything else being an error. The text is cut at `NOTICE_MAX_CHARS`
  characters, 1000, with a warning in the log, since a notice that is too long
  is a fault of the code of the node, not a reason to stop it. The file holds
  `{"level": ..., "text": ..., "set_at": ...}`, `set_at` being the time at which
  the notice was set.
- **From any hook and any thread.** Any hook may set or clear it, `observe()`
  included. The node keeps a copy of its notice in memory and writes the file
  into a temporary file renamed into place, the comparison, the write and the
  rename under one lock: a reader finds the previous notice or the new one,
  never a part of either, the file holds the notice that was set last, unless
  it could not be written (see the next item), and setting the notice that the
  node already has writes nothing.
- **Not state.** The notice is in no checkpoint, rounds ignore it, it travels on
  no channel, and nothing in the node reads it back: it only reports. So a
  notice file that cannot be written or removed leaves a warning in the log and
  does not stop the node. While it cannot be written, whoever watches finds the
  previous notice or none, and only the log of the node tells; asking for the
  same notice again tries the write again. A notice file that cannot be removed
  when the node starts stays until the node sets another notice, since the node
  takes itself to have none. `debasher_reset_resident` takes the notice away
  with the rest, since it speaks of a node whose state is gone (see
  "`debasher_reset_resident`: a clean start").
- **Each incarnation starts with none.** `run()` removes the notice file before
  `restore_node_state()`, so that a notice of an earlier incarnation, about a
  fault fixed since or a file that has appeared since, does not outlive it,
  unless the file cannot be removed (see the previous item). What the code of
  the node sets during the startup, in `restore_node_state()`,
  `initialize_runtime()` or the replay of its input log, is set again. A notice
  that follows from the node state and that `process_data` set before the latest
  checkpoint is not, since the replay starts after that checkpoint: the node
  sets it again in `restore_node_state()`, from the state it restores. A notice
  set in `restore_node_state()` or `initialize_runtime()` is written at once;
  during the replay that follows, the runtime keeps only the last `set_notice()`
  or `clear_notice()` asked for, and applies it once the replay ends, so that a
  long replay costs one write.

The notice is read from outside: `debasher_inspect_resident` gives it in the
summary of a node and, for every node of a program at once, with its command
`notices` (see "`debasher_inspect_resident`: what a node keeps"), and the web UI
marks the canvas node that has one (see "Observing and talking to a live
program" in `doc/design_doc_webui.md`). The `Supervisor` has no notice. The
classes of the runtime library set one of their own only when the node lacks a
port that the class needs to do its work, since such a node runs but does
nothing useful, and would otherwise not say so: at every start, once the notice
file is removed, `run()` asks `_find_wiring_problem()`, which a class of the
library redefines, and sets what it answers as a `warning` notice, with the same
line in the log. A `DirectoryWatcher` without the output port `REQUESTS_PORT`
says that the files it sees are sent nowhere, and a `ProgramLauncher` without an
input port that carries data says that it never receives a request. A notice
that the code of the node sets later replaces it. Apart from that, a
`DirectoryWatcher` that waits for files says nothing, and a module that wants it
to derives from it and sets one.

## State capture and checkpoint schema

A checkpoint is what a node keeps on disk to come back to the state it had
when a round opened at it. This section says what a checkpoint holds and why,
and which checkpoint a node accepts when it starts. How a round opens and
closes is in "Chandy-Lamport barrier propagation", and how the file reaches
the disk in "Checkpoint persistence".

What a round captures is taken at one moment: when the round opens at the
node, on the brain thread, while it handles the envelope that opens it (a
marker or a trigger). The file is written only when the round closes, once a
marker has arrived on every pending port; meanwhile the node goes on
processing. A checkpoint is a JSON object with these fields:

- `schema_version`: the `CHECKPOINT_SCHEMA_VERSION` of the class that wrote it.
- `epoch`: the round.
- `node_state`: what `capture_node_state()` returned when the round opened,
  which the runtime copies at once (`copy.deepcopy`), since `process_data` goes
  on changing the node while the round is open: the hook may return the objects
  of the node themselves. It holds only logical state that JSON can serialize,
  never runtime resources (connections, sockets, file handles), which
  `initialize_runtime()` builds again at every start (see "Startup sequence:
  `run()`"). A restore passes it, and only it, to `restore_node_state()`.
- `capture_pos`: the position in the input log of the envelope that opened
  the round (see "Arrival and positions").
- `closed_ports`: the input ports whose `CLOSE` the brain thread had
  processed by then (see "`CLOSE` and closed ports").
- `out_seq` and `last_seq`: for each output port, the last sequence number
  sent, and for each input port, the last one that the brain thread had
  processed (see "Sequence numbers in the input log").
- `out_backlog`: the copy of the outbound backlog (see the Glossary).
- `channel_state`: for each port that was pending in the round, a copy of the
  `DATA` that arrived on it while it was still pending (before its marker).

The node state and the engine's own bookkeeping (`capture_pos`,
`closed_ports`, `out_seq`, `last_seq` and `out_backlog`) are taken at the same
position, so they agree with each other: a restore puts the node where it was
right after it handled the envelope at `capture_pos`, with the counters, the
closed ports and the outbound backlog of that moment, and the replay of what
the input log holds above that position brings it up to date (see "Recovery:
startup and replay").

The channel state is the one field that a restore does not read, and must
not. A `DATA` that arrives on a pending port is processed like any other, and
a copy of it goes into the channel state besides. Every message in it arrived
after the capture, so the input log holds it above `capture_pos` and the
replay processes it again; feeding it from `channel_state` too would process
it twice. It exists for the two uses of a consistent cut: inspecting the state
of the whole program at a round, where the node states alone miss the messages
that were in transit (the introduction's second goal), and a global rollback,
which discards the input logs above the target and has to redeliver those
messages from it (see "Future work").

A node accepts only a checkpoint of its own format, with no compatibility
code. `_load_latest_checkpoint` takes the checkpoint with the highest
epoch (see "Checkpoint persistence") and loads it only if it has this class's
`CHECKPOINT_SCHEMA_VERSION` and every field that the class reads; otherwise
the startup fails, with a `ValueError` for another version (or a file that is
not JSON) and a `KeyError` naming a missing field. It never falls back to an
older checkpoint or to a default value, since either would start the node
from a state other than the one it had, with nothing said. A new field needs
no new version, since its absence is already refused; the version changes when
an existing field changes its meaning or its format, which the presence of the
fields cannot tell. The names of the hooks have no compatibility code
either: a module that defines differently named hooks fails at its first round
with a `NotImplementedError`.

## Startup sequence: `run()`

A node has one way to start, whether it is launched for the first time or
relaunched after a failure. Which of the two it is shows only in what it finds
on disk: with a checkpoint it restores it, and without one it starts from
default values. The `Supervisor` needs no recovery mode: it runs the same script
in both cases, and the process does the rest (see "Reconnecting after a node
failure").

`run()` follows these steps:

1. Installs the handler of SIGTERM, which only records the request.
2. Sets the GIL switch interval, if the class gives one.
3. Opens every FIFO. They come first because a node holds a FIFO only from the
   moment it opens it, and restoring and replaying can take a while: if a
   neighbor that was the only holder of a FIFO crashed during that time, what
   it had sent would be destroyed with it.
4. Removes the notice of the previous incarnation, and sets the one of
   `_find_wiring_problem()`, if any (see "Notices").
5. Looks for the most recent checkpoint. If there is one, it calls
   `restore_node_state()`, restores the closed ports and the counters of
   sequence numbers, and queues the outbound backlog of the checkpoint; if
   not, it starts from default values.
6. Calls `initialize_runtime()`, always.
7. Opens the input log.
8. Starts the writer threads, so that what the replay sends drains while it
   replays. The backlog of the checkpoint still reaches the neighbors first,
   since it was queued before the replay and each port has one queue.
9. Replays the input log after the `capture_pos` of the checkpoint, all of it
   if there was none (see "Input log"). While replaying, a `send_data` that
   would take the backlog over `OUT_BACKLOG_FAIL_BYTES` waits for room, unless
   the message alone is larger than the limit (see "Checkpoint persistence").
10. Starts the other threads. If this fails, it stops the threads that are
    running and raises the error, since they would otherwise keep the process
    alive doing nothing.
11. Waits until told to stop, and stops every thread.

A SIGTERM during the startup is honored when the startup ends, since the replay
does not look at it; only a `send_data` that waits for room stops waiting, since
it looks at `_stop_signaled` too.

A clean start is an external operation: it is enough to remove what a node
finds at startup, with no flag or special logic in the process or the
`Supervisor`. That is more than the checkpoints, since with none a node replays
its whole input log and ends in the state it had. `debasher_reset_resident`
does it for a whole program (see "`debasher_reset_resident`: a clean start").

## Chandy-Lamport barrier propagation

A round runs the Chandy-Lamport barrier over the business channels of the
program: every node captures its state once, and the marker that it forwards
on its output ports separates, on each channel, what the sender sent before
its capture from what it sent after. This section says how a round opens at a
node, how it propagates and when it closes, and then the cases that the rule
has to settle: initiators, control ports, rounds that meet at a node, and the
nodes that a round has to reach.

A round opens at a node in one of two ways. At an initiator, a trigger opens it:
an `INTERACT` `start_snapshot`, or `shutdown` for a halt, on one of its control
ports, written by the `Supervisor` through an initiator port or from outside the
program (see "Initiator ports" and "Manual trigger channel"). At any node, the
first marker of the round that arrives on an input port opens it. Either way,
the node captures its state at once (see "State capture and checkpoint schema")
and forwards the marker on every output port but the one to the `Supervisor`,
which takes no part in the barrier.

The round then waits for a marker on every input port that is pending: all of
them but the control ports, the external ports, the ports whose writer has
already said `CLOSE`, and the port whose marker opened the round, if a marker
did. Meanwhile the node goes on processing: a `DATA` that arrives on a pending
port is processed at once, like any other, and a deep copy of it goes to the
channel state of the round. Each marker that arrives settles its port, and so
does a `CLOSE` on a pending port, since a finished writer sends no more
markers. When no port is pending, the round closes at the node and the node
writes its checkpoint (see "Checkpoint persistence").

An initiator closes its part in the same way as any other node, once a marker
has come by every pending port. In a cycle, that is the marker it sent itself,
when it comes back; with business inputs, the markers of the same round from
upstream (see numbered trigger in the Glossary), so an initiator need not be a
root; with no port pending at all, the round closes as soon as it opens.

Control ports are left out of every round, whoever opens it: a command is not
the marker of the port that carries it (a round opened by a command starts
with no port counted as arrived), the `Supervisor` takes no part in the barrier
and never sends a marker, and a node with a control port must also close the
rounds that a peer starts.

Rounds do not overlap at a node. A marker of a newer epoch that reaches a node
while an older round is open replaces it: the older round is abandoned, and
the node captures again at the newer marker and forwards it. Capturing later,
at the close of the older round, would include messages that the sender had
sent after its own capture, and holding back the port would break the order of
the input log. A halt is never replaced by a snapshot, and a marker of an
older epoch, or of a round that is over, is ignored. A trigger without an
epoch that finds a snapshot open replaces it with a round numbered as the open
one plus one, a number above it so that the nodes that have that round open
replace it too; without this, an initiator whose marker was lost would keep
its round open for ever, and so would every node of its cycle, whose input
logs would grow until `INPUT_LOG_MAX_BYTES` ends their reader threads. A
marker is lost when its node crashes after it has captured its state and
queued the marker, and before its writer thread has written it, and in the
cases of the Contract's limits (a message read from a FIFO and not yet
written to the input log, a FIFO destroyed with both its endpoints down). A
trigger that finds a halt open, and any trigger
once the node has halted, are ignored (see "Ordered shutdown"). A numbered
trigger follows the rule of a marker instead (see numbered trigger in the
Glossary).

The triggers are numbered because two initiators number the rounds they open
on their own, each as the last epoch it closed, abandoned or has open, plus
one, and
nothing makes the two counters meet when no channel goes from one initiator to
the other: they drift apart when a trigger reaches only one of them, or when a
relaunched initiator restores a checkpoint older than a round it had
abandoned. Take the fan-in of two nodes fed from outside, `a` and `b`, whose
only inputs are external, so that each has to be an initiator, both writing to
a node `c`. With rounds numbered apart, `c` replaces the lower round with the
higher one and then waits for a marker of the higher epoch that the other
initiator never sends: it writes no further checkpoint, its input log grows
until `INPUT_LOG_MAX_BYTES` is reached, and a halt never closes there. The
`Supervisor`, `debasher_snapshot_resident` and `debasher_stop_resident` number
the triggers they send, so that every initiator opens the same round. A trigger
without an epoch, written by an actor outside the program straight into the
FIFO of an initiator, is still numbered from that initiator's own counter, and
where the rounds of several initiators meet it can still lead to the same wait.

A round has to be able to reach every node from an initiator, or it never
opens at the nodes it cannot reach and never closes at the nodes they write
to. The engine checks it when the program is loaded, and refuses a program in
which a node cannot be reached (see "Validation when the program is loaded").
So, in a program without cycles, every node with no business input has to be
an initiator, since no marker can reach it otherwise.

## Ordered shutdown

A halt stops a resident program without losing anything that a resume cannot
bring back. It takes two steps: a round with `halt` true, which leaves every
node with a checkpoint of the same round (see "Checkpoint persistence") and a
halted marker, and then a stop signal to every node, which ends its `run()`.
This section describes the two steps, what the halted flag of a node blocks and
what it does not, and how a program is resumed.

A halt is a round like a snapshot, whose markers carry `halt=True` (see
"Chandy-Lamport barrier propagation"). When it closes at a node,
`_on_epoch_closed` writes the checkpoint as for any round, sets `_halted` and
writes the halted marker (`_write_halted_marker`), which holds its epoch.
Nothing else changes at the node (see the Glossary's "halt"): it keeps running,
exactly like after any other round, and goes on processing every `DATA` that
reaches it until a stop signal arrives.

`_halted` keeps the node from starting a round when a trigger reaches it
(`_on_trigger`): a later trigger, from the `Supervisor`,
`debasher_snapshot_resident` or `debasher_stop_resident`, opens no round for the
rest of this incarnation. It does not keep the node out of a round that reaches
it as the marker of a peer. A round has to close at every node it reaches, or it
never closes at the nodes downstream of this one, so a node that has halted
opens it, captures its state and writes its checkpoint like any other node, and,
when that round is a halt too, writes its epoch into the halted marker. That
checkpoint need not equal the one of the halt: the node may have processed
messages since, and its `capture_pos` is later in any case, since the marker
that opens the round has a position of its own in the input log. A resume
restores it like any other checkpoint (see how a program is resumed, below). The
cost of ignoring the triggers is that a halt cannot always be retried: an
initiator that has halted, and that no marker of the new halt reaches, never
opens it, so when another initiator does (one relaunched after a crash, for
instance), the nodes downstream of the first wait for its marker for ever (see
"A crash while a round is open" in the Contract's limits). When every initiator
has halted, no new round starts at all.

What ends `run()` is the stop signal, not a round closing. `run()` installs a
handler of `SIGTERM` (`_on_stop_signal`) on the main thread only, since
`signal.signal()` raises a `ValueError` off it (the tests that drive `run()`
from another thread set `_stop_requested` themselves, as other tests simulate an
`INTERACT` arriving), and then waits on `_stop_requested` before it stops its
threads. The handler only sets a plain attribute, `_stop_signaled`: it runs on
the main thread between any two instructions, also while `run()` holds for a
moment the lock inside the event, in `wait()`, and setting the event there would
wait for ever on that lock. So `run()` waits on the event in steps of
`_STOP_POLL_SECS` (0.2 s), looks at the attribute between them, and sets the
event itself (`_wait_for_stop`), which wakes whatever else waits on it, such as
`sleep()`: a stop is seen at most that much later. When to send that signal is
decided outside `FBPProcess`, by design: `debasher_stop_resident` sends it (see
"`debasher_stop_resident`: the graceful stop tool"), typically once the halted
marker of every node has gone past its baseline (see halted marker baseline in
the Glossary), but nothing in the node requires that, or requires a halt to
have happened at all.

A halt sends no `CLOSE`, and neither does any other stop signal: `run()` always
calls `stop_threads(close=False)` once its wait on `_stop_requested` returns.
`CLOSE` says that a writer has finished for good, and a node that got a stop
signal, whether or not it ever halted, may be resumed later: had it sent
`CLOSE`, the reader at the other end could keep it in its input log after its
`capture_pos` (see "Input log"), and a resume would take the node for a finished
one. So no process of a resident program sends `CLOSE`, on a business port or on
a control port: `run()` is the only way a process of it ends, and both
`FBPProcess.run` and `Supervisor.run` stop their threads with `close=False`.
`stop_threads()` still sends it by default, but only the unit tests call it
outside `run()`, and the `CLOSE` of a business port waits for a node that
finishes for good (see "A node that finishes for good" in "Future work").

The signal has to reach the node's own process, not just the leader of the
process group that `debasher_stop` and `.id` already agree on.
`debasher_builtin_sched::_launch` backgrounds a generated script as the leader
of its own process group (`pgid == pid`, the pid in `.id`), and the process
function that this script runs (`debasher::_execute_task`) starts the Python
interpreter as a child process, so the interpreter of a resident process sits
below the pid in `.id`, not at it. A plain, single-pid `SIGTERM` there would
only reach the wrapper script, orphaning the interpreter, which would never
receive anything and would keep running. So a stop signal targets the whole
process group instead (`kill -TERM` to the group, in
`debasher::_stop_pid_gracefully`, the same group that `debasher_stop` already
reaches with `SIGKILL`, see `debasher::_stop_pid`), and the wrapper script
itself survives that same broadcast to still write `.finished` once its own
child exits, which is what `debasher_builtin_sched::_print_script_trap`
(`trap '' TERM`, the first thing `_create_script` writes into the generated file
of a resident program) is for. A hard kill (`SIGKILL`) cannot be trapped and is
unaffected. An ignored signal is inherited through `fork` and `exec`, so the
interpreter of the node starts with `SIGTERM` ignored; the node does not depend
on it, since `run()` installs a handler of its own at its start, and that
handler, unlike an ignored signal, goes back to the default in what the node
starts, such as the `debasher_exec` of a `ProgramLauncher`. The script of a
general program traps nothing (see "The built-in scheduler" in
`doc/design_doc_engine.md`).

A program is resumed by relaunching every process, through the ordinary
startup (see "Startup sequence: `run()`"), with no special case for a halt:
each node loads its latest checkpoint (the one the halt closed, in the
ordinary case where nothing else ran in this incarnation after it) and replays
its input log after that checkpoint's `capture_pos`. What is replayed is what
the node processed between capturing its state and closing the round (the
messages that were in transit at the cut, which its checkpoint also holds as
`channel_state`) and anything that reached its log after that. The node ends
in the state it had when it stopped, and re-executing those messages is
deterministic, like any other replay.

The relaunch is `debasher_exec` again, on the same output directory. Every
node stopped by the halt left a `.finished`, which for a general program means
a process that is done and is not launched again. In a resident program a
process is never done, so `debasher_exec` marks every process that is not
running to be launched again
(`debasher::_define_rerun_processes_due_to_resident_resume`), every task of an
array included, also when only some of them have a `.finished`, as a hard kill
of the others leaves them. Nothing in the directory of a node is reset on the
way: not its checkpoints, its input log or its halted marker, in its execdir
(Glossary), nor its output directory, `<outdir>/<process>`, which a general
process has emptied every time it is launched. What a node keeps there is part
of what it has done so far, and a launch of the node resumes it, whether it is
a new run after a halt or the `Supervisor`'s relaunch after a crash.

## Checkpoint persistence

This section says where the checkpoints of a node live, how one reaches the
disk, how many are kept, and what happens when one cannot be written or
loaded. It ends with the two limits on the outbound backlog, which the
checkpoints carry: one on the size of a checkpoint, the other on the memory
of the node.

A node keeps its checkpoints in a directory of its own,
`__exec__/<process_name>/checkpoints/` (`_get_checkpoints_dir()`), not among the
files that the engine already writes there
(`<process_name>.{finished,id,opts,sched_out,stdout}`); a task of an array
keeps its own, `checkpoints_<idx>/`, next to those of the other tasks (see
execdir in the Glossary). Each checkpoint is a file named by its epoch,
`<epoch>.json`.

When a round closes, `_save_checkpoint()` writes the checkpoint into a
temporary file and renames it into place (`os.replace`), so that a crash of
the process leaves the new checkpoint whole or not at all, never a part of it.
It then keeps the `CHECKPOINT_RETENTION` checkpoints (3 by default) with the
highest epochs, deletes the others (`_prune_old_checkpoints()`) and prunes the
input log up to what the oldest of them needs (see "Pruning and the size
cap"). When the node has a `SUPERVISOR_PORT`, `_on_epoch_closed()` tells the
`Supervisor` with an `INTERACT {"command": "checkpoint_saved"}` that carries
the epoch and the path, never the checkpoint itself.

A checkpoint that cannot be written stops the node as an exception of
`process_data` does: a node state that JSON cannot serialize raises a
`TypeError`, and a full disk an `OSError`, which ends the brain thread. The
round is over at the node all the same. The heartbeat reports the dead thread,
and the `Supervisor` relaunches the node, which restores its previous
checkpoint and replays a longer part of its input log. A temporary file left
behind is never loaded, since its name is not an epoch.

On startup, the node loads the checkpoint with the highest epoch among the
files named `<integer>.json` (`_load_latest_checkpoint()`); if that one does
not load, the startup fails (see "State capture and checkpoint schema"). A
node does not tell a first launch from a relaunch: with no checkpoint, it
starts from default values (see "Startup sequence: `run()`").

The outbound backlog is held in memory and copied into every checkpoint, and a
reader that does not keep up makes it grow. Two limits bound it, a soft one on
the size of a checkpoint and a hard one on the memory of the node: a reader
that is slow for a while meets only the first, and one that has stopped for
good meets the second.

Over `OUT_BACKLOG_MAX_BYTES` (8 MiB by default), measured on the copy that the
capture took, `_save_checkpoint()` writes nothing and logs a warning: the
round closes without a checkpoint. Nothing is lost, since the previous
checkpoint plus a longer replay of the input log regenerate every output
since, so a neighbor that is slow for a while costs no more than rounds without
a checkpoint. Nothing is pruned meanwhile either, and if the input log reaches
`INPUT_LOG_MAX_BYTES`, its error names the outbound backlog and the epoch since
which no checkpoint has been written (`_checkpoints_skipped_since`), since the
rounds themselves do close.

When a message would take what the node has not yet written into its FIFOs, on
all its output ports together, over `OUT_BACKLOG_FAIL_BYTES` (64 MiB by
default), `send_data` raises a `RuntimeError` instead of sending it: the message
is neither numbered nor queued, and the error names the port it was for and the
port that holds the most bytes not yet written, with how many: the limit is one
for all the ports, so the port that fills the backlog need not be that of the
message. A backlog that keeps growing means a reader that is not reading:
stopped, down or stuck, or slower than this node for good. The exception ends
the brain thread, which the heartbeat reports, and the `Supervisor` relaunches
the node. The relaunch restores the backlog of its checkpoint, which counts
against the same limit, and replays its input log, which sends again what the
node had sent since; while it replays, it waits for room instead of raising (see
the next paragraph). So if the reader still does not read, the relaunch waits in
its replay, with no heartbeats, until the `Supervisor` relaunches it again (see
"Failure detection"), and the node ends in "Escalation on a permanent node
failure" when the attempts run out; only a replay that gets through can raise
the error again, live. A message larger than the limit never fits: `send_data`
raises a `RuntimeError` of its own at once, live and in a replay, which gives
its size and the limit. The replay sends it again, so the node fails at every
relaunch and ends in "Escalation on a permanent node failure". The memory a node
takes for its messages is thus bounded by this limit and by
`INPUT_LOG_MAX_BYTES`, which also bounds what waits in its inbound queue, since
every queued envelope is logged first.

While the node replays its input log, the same limit makes `send_data` wait for
room instead of raising, with one warning in the log: a replay can run faster
than a writer thread can write, whoever the reader is, and a node whose replay
sent more than the limit could otherwise never start. A reader that never reads
leaves the node in its startup, with no heartbeats, until the `Supervisor`
relaunches it (see "Failure detection") or, without one, until it is stopped.
The readers of a node start only after its replay, so the nodes of a cycle that
replay at once, each over the limit, wait on each other in the same way, and a
node with a self-loop waits on itself. A stop ends the wait, after which
`send_data` raises the error of the previous paragraph if the message still
does not fit.

## Testing a node without the engine

A node test (see "Business tests of a program" in `doc/design_doc_engine.md`)
checks the business logic of a node: what it sends for what it receives, what it
brings in when it observes the outside world, and that its node state brings it
back to where it was. None of that needs FIFOs, envelopes, rounds or a
`Supervisor`, so the test builds the class of the node in its own Python
process, without the engine, and calls its hooks directly. The node harness, the
module `debasher_runtime_testing` of the runtime library, does that for it. For
the node `Accumulate` of the program `webui_running_sum`, which keeps the
running sum of the numbers that arrive on its port `numbers` and sends each new
sum on `outsum`:

```python
from debasher_runtime_testing import load_node


def test_running_sum():
    node = load_node("Accumulate", inputs=["numbers"], outputs=["outsum"])
    node.feed("numbers", 3)
    node.feed("numbers", 4)
    assert node.sent("outsum") == [3, 7]


def test_restart_keeps_the_sum():
    node = load_node("Accumulate", inputs=["numbers"], outputs=["outsum"])
    node.feed("numbers", 3)
    node = node.restart()
    node.feed("numbers", 4)
    assert node.sent("outsum") == [7]
```

`load_node(process, opts=None, inputs=(), outputs=())` builds a node under
test:

- It takes the heredoc of `process` from the program file named by
  `DEBASHER_TEST_PFILE`, through `debasher_get_node_source <pfile> <process>`,
  a tool of `libexec` that loads the module and prints what
  `debasher::_get_resident_process_source` gives: the text that the engine
  runs, since both take it from the same heredoc provider (the method
  `_heredoc_py` of the process, or its legacy variable). The text of each
  process is taken once in a test session, since loading the module is what
  costs time.
- It parses the heredoc with Python's `ast` module and leaves out the line
  `<Name>().run()` of its class (see "Defining a node"). A line under
  `if __name__ == "__main__":` needs nothing, since the harness runs the
  heredoc under a module name of its own. Any other call to a method `run()`
  with no arguments outside a definition, such as `node = Name()` followed by
  `node.run()`, is refused, with a message that names the forms the harness
  recognizes, since it would start the node. A call with arguments, such as
  `subprocess.run([...])`, starts no node and is run.
- It runs the rest as a module: a module object registered in `sys.modules`,
  so that what looks up a class by its `__module__` (`dataclasses`, `pickle`,
  `typing`) finds it, and in whose namespace the code runs, so that the
  methods of the class see the functions, constants and imports of the code
  before the class as they do in a run. The text is put into `linecache` under
  the name `<heredoc of <process>>`, so that a traceback shows the lines of
  the heredoc.
- It takes the one class of the heredoc that derives from a class of the
  runtime library, as the engine requires, and refuses it when it derives from
  `Supervisor` or `ProgramLauncher`: a subclass of `FBPProcess` or of
  `DirectoryWatcher` can be tested, while what a launcher node or the
  `Supervisor` does is not driven by `process_data` and `observe()` alone.
- It builds the node from an `argv` in the shape that the engine gives a
  heredoc, since the class of a node takes no argument and its constructor
  parses `sys.argv`: `opts`, by name with or without the dash, a value `True`
  given as a flag, plus a placeholder value for each port, whose FIFO is never
  opened. The ports are `inputs` and `outputs`, the names of their options
  without the dash, which the harness gives the node as the engine would, in
  `DEBASHER_PROCESS_PORTS` (see "Ports from the engine"). The execdir of the
  node is a temporary directory.
- It calls `initialize_runtime()`, as `run()` does before any thread starts.

Whenever the harness calls the node (its constructor, `initialize_runtime()`,
`feed`, `observe` and `restart`), it sets the environment that the engine gives
a node (its ports, its execdir and the directory of its module, which is that
of the program file, with no computational specifications and no task index),
and puts back what the test had afterwards, since several nodes under test
share one process. The directory of the module is what a relative path of the
node is resolved against, such as the `-watchdir` of a `DirectoryWatcher`.

The test names the ports because the harness does not build the options of the
program, which is what tells the engine which options of a process are ports.
A test names only the ports whose traffic it checks: a control port, the port
to the `Supervisor` and any port that the test leaves out are not ports of the
node under test, and `send_data` on one of them fails, as it does for a port
that a node does not have.

The harness does not require the line that starts the node: a heredoc that
lacks it passes a node test and is refused when the program is loaded (see
"Defining a node").

A node under test offers:

- `feed(port, packet)`: calls `process_data(port, packet)` on the calling
  thread, marked as the brain thread is, so that `send_data` works during the
  call and only then. The packet first makes a round trip through JSON, so that
  the node gets what would arrive through a FIFO: a tuple arrives as a list.
  The port is one of `inputs`, or the observe port of the node (`OBSERVE_PORT`),
  standing for something that `observe()` would have brought in; any other is
  refused. When `process_data` raises, what it sent before stays in `sent`.
- `observe()`: runs the `observe()` of the node once on the calling thread, as
  the observation thread would at the end of an interval, and then calls
  `process_data` with what it brought in with `inject()`, in order and under
  the observe port, as the brain thread would; it returns what was brought in,
  after the same round trip through JSON as a message. The harness takes what
  `inject()` hands to the input log instead of writing it there, and leaves
  the checks of `inject()` as they are: one from `process_data`, or in a node
  without an observe port, still raises. A node that does not define
  `observe()` is refused. Since a test calls it, it can make the outside world
  change between two observations, such as a file that a `DirectoryWatcher`
  sees grow, then stay the same for `STABLE_OBSERVATIONS` observations in a
  row before it is brought in.
- `sent(port)`: the payloads that the node has sent on `port` since it was
  built, decoded from the lines that `send_data` queued. The harness takes
  each line off the outbound queue as soon as `process_data` returns, and
  counts it as written, so the outbound backlog never fills, however many
  packets a test feeds.
- `restart()`: captures the node state and makes a round trip of it through
  JSON, as a checkpoint does; builds a new node under test with the same
  options and ports, whose `observe()` remembers nothing of the earlier one,
  as after a crash, so a test can check that `process_data` drops what the new
  node brings in again; restores the state into it and calls
  `initialize_runtime()`, the order in which `run()` starts a relaunched node;
  and returns the new node, whose `sent` starts empty. It raises when the new
  node captures a node state other than the one it was restored from, since
  recovery relies on that round trip.
- `node`: the instance itself, for a test that looks at its attributes.

In a node under test, `sleep()` returns at once, as it does while a node
replays its input log: the pace of a node is not business logic. The node logs
to its standard error as always, which pytest captures.

The text that the harness runs differs from that of a run in two cases, both
rare in a node. A heredoc whose delimiter is not quoted (`<<EOF`) has its
variables expanded by Bash when it is printed, in the shell of
`debasher_get_node_source` rather than in that of the task. And the code
before the class runs with the environment and the `argv` of pytest, since the
harness gives the node its own only when it calls the node.

The harness checks nothing of the framework: sequence numbers, rounds, the input
log, `CLOSE`, the heartbeat and the limits of a node are left to the tests of
the engine, and `observe()` runs only when the test calls it, never on a timer
of its own. It is part of the runtime library, and not of each node test,
because it reaches into the internals of `FBPProcess`: it calls `process_data`
the way the brain thread does, and it empties the outbound queues and the
outbound backlog. A node test uses only the harness, so those internals can
change without breaking the tests of the programs.

# Input log

The input log is what lets a relaunched node return to the state it would
have had without the crash. A checkpoint holds the node state as it was when a
round opened; everything the node received from then on is in its input log,
and replaying the log on top of the checkpoint brings the node state up to
date. The log belongs to the node that receives, in its own execdir, since
that is the node that replays it (see "Log structure and record format").

That use sets what the log has to guarantee:

- A message is logged when a reader thread takes it from its FIFO, not when
  the brain thread reaches it, so that what waits in the inbound queue, which
  has no limit, survives a crash of the node.
- A node has one log, not one per port, in the order in which the brain thread
  processes its envelopes, so that a replay processes the messages of every port
  in the same order as the first execution.
- Every `DATA` reaches `process_data`, also on a port whose marker is still
  pending in an open round, where a copy of it goes into the channel state
  besides.
- A replay starts right after the envelope whose processing captured the node
  state, not where the round closed, so that a message processed between the
  capture and the close is not skipped; a node with no checkpoint yet replays
  its whole log.

The section first describes the log itself ("Log structure and record format",
"Arrival and positions"), then how a node recovers from it ("Recovery: startup
and replay") and how it is kept small ("Pruning and the size cap"); what a
checkpoint keeps about the log is in "State capture and checkpoint schema". It
ends with how the log carries the end of a writer ("`CLOSE` and closed ports")
and the sequence numbers ("Sequence numbers in the input log"), and with why it
is not built on the engine's mirror tap ("Why the log is not built on the mirror
tap"). It comes right after "`FBPProcess` class", whose startup replays the log.

## Log structure and record format

Each node keeps its input log in its own execdir, in `<execdir>/log/`. The node
that replays a log is always the one relaunched after a crash, never one of its
neighbors, so the log belongs to the side that receives, and a recovery never
reaches into the directory of another node. There is one log per node, not one
per port: everything that arrives at a node (`DATA`, `BARRIER`, `INTERACT`,
`CLOSE`) is written to it, in the order the brain thread processes it. That
order is guaranteed by one lock, shared with pruning (see "Pruning and the size
cap"), that makes appending the record and queuing the envelope for the brain
thread a single step. Only `DATA` is replayed.

The log is split into segments, files named `<first pos>.log` after the
position of their first record, ordered numerically like a checkpoint's
`<epoch>.json`. A new segment starts with every incarnation of a node, never
appended to an existing one, and when the active one has reached
`INPUT_LOG_SEGMENT_BYTES` (4 MiB by default), or a quarter of
`INPUT_LOG_MAX_BYTES` when that is less. The size is checked before a write,
and the records of one write go to the same segment, so a segment can pass its
size by one write, that is, by the records of one block that a reader thread
took from its FIFO (see "Arrival and positions"). Files are created at the
first append, so there are no empty segments, and nothing rotates when a round
captures the node state, which would couple the brain thread to the readers to
save, at most, one segment of disk.

A record is one line, `{"pos": N, "port": "<port>", "env": <the envelope
line exactly as it arrived>}`. The envelope is embedded by string
concatenation, not encoded again: it is already JSON, so the critical section
that writes the record does not decode and encode it, every line is still
valid JSON, and a `DATA`'s `seq` (G5) travels inside `env` with no change to
the record format. The records go to an `O_APPEND` descriptor with
`os.write`, never through a buffered file object: a buffered `f.write`
without `flush` can lose acknowledged records across a `kill -9`, while
`f.write` plus `flush`, and `os.write`, do not.

The records of one call of `append_many` go to the segment in one write, which
`_write_all` repeats while the operating system takes only part of the bytes.
When the process dies before the last part is written (a `kill -9`, a crash), or
a write fails halfway (a full disk), the segment ends with part of a record and
no newline: a torn tail. Nothing is written after it: a new incarnation starts a
segment of its own, and after a failed write the log refuses every append until
the process restarts (the reader thread whose write failed dies with its error,
any other that appends dies with a `RuntimeError`, the heartbeat stops and the
`Supervisor` relaunches the node). Otherwise another append would bury the
fragment in the middle of the file. Replay ignores the torn tail: it can only be
part of the records that were being written, which `append_many` had not
returned, so none of them had been queued. A line that ends in a newline is a
complete record and has to parse; one that does not means that the log is
corrupt, and the replay stops with a `ValueError`.

## Arrival and positions

A reader thread reads its FIFO a block at a time and hands the envelopes it
decodes from one block, together, to `_on_arrivals(tag, envelopes)` instead of
putting them on the inbound queue itself; a line cut at the end of a block
waits for the next one. `FBPProcess` overrides it: under one lock it appends
the records of the whole block to the log in one write
(`_InputLog.append_many`), which assigns them consecutive positions, `pos`,
then puts `(pos, tag, type, payload, seq)` on the queue for each, so that
position order is processing order across every port. Logging a block in one
write keeps each of its messages in memory, taken from the FIFO but not yet in
the log, for the same short time, instead of a time that grows with its place
in the block (see "Messages read from a FIFO but not yet written to the input
log" in the Contract's limits). The version of `_PortWorker`, which the
`Supervisor` keeps, is unaffected: it puts `(tag, type, payload)` for each
envelope, with no position.

Every queued envelope gets a position, starting at 1; `HELLO` never reaches the
queue. Whatever starts a round from inside the node, such as a snapshot timer
(see "Periodic snapshots from a node's own timer" in Future work), has to go
through the same hook, so that `capture_pos` (see the Glossary) is always
defined; 0 means that nothing had been processed yet.

## Recovery: startup and replay

Three of the steps of "Startup sequence: `run()`" recover a node from its
checkpoint and its input log, whether it is relaunched after a crash or
resumed after a halt:

1. Step 5 restores the latest checkpoint (see "Checkpoint persistence"),
   which gives `capture_pos`; with no checkpoint, `capture_pos` is 0 and the
   node state is the default one.
2. Step 7 opens the input log (`_InputLog.recover`). It reads only the last
   segment that has a complete record, and deletes a segment with no complete
   record (an empty file, or only a torn tail), since the next record would
   take its position and collide with its name. If there is a checkpoint and
   the log ends below its `capture_pos`, the startup stops with a `ValueError`
   (see below). Otherwise the next position is one more than the position of
   the last complete record.
3. Step 9 replays the log (`FBPProcess._replay_input_log`): every `DATA`
   record above `capture_pos` goes through `process_data()`, in log order,
   what had been processed before the crash and what had arrived but not yet
   been processed, with no distinction between the two. A `CLOSE` record adds
   its port to `closed_ports`, unless it is a control port, and the other
   kinds of envelope are not replayed. A `DATA` record on a port that is
   already closed is an error, since nothing is logged after a `CLOSE`. The
   replay reads from disk and writes nothing to the log.

The replay starts at the last segment whose name is at most `capture_pos + 1`,
and stops the startup with a `ValueError` if the log starts above that, if the
positions from there on are not consecutive, if a segment does not start where
its name says, or if a line that ends in a newline does not parse.

The log of a node with a checkpoint always reaches the checkpoint's
`capture_pos`: the envelope at that position was logged before the brain thread
saw it, `recover` deletes only a segment with no complete record, and pruning
never deletes the last segment. A log that is empty, or that ends below
`capture_pos`, while a checkpoint exists, was lost or cut, and what the node
processed after the checkpoint is gone with it. Starting from the checkpoint
would lose it in silence: a numbered message from a peer would later show a gap,
but nothing would ever tell of a message from outside the program. So `recover`
stops the startup with a `ValueError` that names the log, its last position and
`capture_pos`, and says that `debasher_reset_resident` starts the program
afresh. With a `Supervisor`, every relaunch fails in the same way, until the
`Supervisor` gives up on it (see "Escalation on a permanent node failure");
without one, the task of the node fails. A log with no records and no checkpoint
is a node that has received nothing yet, and starts from position 1.

## Pruning and the size cap

Pruning keeps the input log from growing for ever. The log is a directory of
segment files (see "Log structure and record format"), and pruning it deletes
whole files, never part of one. The checkpoints are pruned too, but they are
not segmented: there is one file per epoch, and only the
`CHECKPOINT_RETENTION` with the highest epochs are kept (see "Checkpoint
persistence"). This section describes the pruning of the log, and then its
size cap.

A recovery replays the log from the `capture_pos` of the checkpoint it
restores, so a record is needed while a retained checkpoint has its
`capture_pos` below the position of the record. The one that needs the most of
the log is the oldest retained checkpoint: every record at or below its
`capture_pos` is reflected in all of them, and can go.

The log is pruned right after each checkpoint is written, since that is when
the oldest retained checkpoint changes. A segment can go once all its records
are at or below that `capture_pos`, which is known without reading it: a
segment holds only positions below the first position of the next one, so the
test is that the next segment starts at `capture_pos + 1` or before. The last
segment is never deleted: it is the one being written, or the newest one that
an earlier incarnation left.

The `capture_pos` of the oldest retained checkpoint is read from that
checkpoint's file at each prune, not kept in memory: the node would otherwise
have to keep the positions of its retained checkpoints in step with the files
that hold them, and the file is read once per checkpoint written, outside the
lock. A checkpoint that cannot be read stops the prune with a `RuntimeError` in
the brain thread, before anything is deleted. The deletion runs on the brain
thread under `_arrival_lock`, the lock with which the reader threads append: the
list of segments and the size of the log, against which the cap is checked,
change in one place at a time.

`INPUT_LOG_MAX_BYTES` (100 MiB by default) is the cap on every segment of the
log together. It is a safety net, not the normal way old history goes away,
which is pruning. The cap is checked record by record before a block is written:
the records of the block that fit under it are written and queued, and then
`LogCapReached` ends the reader thread, like any other death of a thread.
Reaching it means that pruning has not kept up, or that the cap is too small for
what arrives between the rounds (see below). Pruning does not keep up when no
round has closed in a long time, or when rounds do close but write no
checkpoint, since the outbound backlog is over `OUT_BACKLOG_MAX_BYTES`, which
the error then says (see "Checkpoint persistence"). Since a node does not start
rounds on its own, a program in which nothing does reaches it.
`debasher_snapshot_resident --every` triggers them from outside the program (see
"`debasher_snapshot_resident`: rounds from outside the program").

The size of the log is a counter of `_InputLog`, `_total_bytes`, set by
`recover` from the files and kept up to date by every write and every prune,
not a question to the disk: the cap is checked on every block, under the lock,
and asking the disk (listing the directory and the size of each file) would
put a call to the file system per segment in the critical section.

The cap is not reached while rounds close often enough for what arrived since
the oldest retained checkpoint to fit in it, together with the active segment
and the block being written. A small cap does not prevent pruning, since a
segment is at most a quarter of the cap plus one block, but that condition is
the one that decides, and it is easy to miss with a small cap: a segment can
pass its size by one block, and a block of small messages weighs in the log much
more than what was read from the FIFO, since each record adds its position and
its port to its envelope. A rule of thumb for setting it: the cap has to hold
what arrives in `CHECKPOINT_RETENTION` rounds, plus a segment and a block.

## `CLOSE` and closed ports

When a writer finishes for good, the node that reads it has to know it, for two
reasons: a round must stop waiting for a marker on that port, since none will
ever come, and the port must stay closed across a relaunch, or the relaunched
node would wait for it again. Both rest on the input log, which records the
`CLOSE` in order with the other envelopes, so that a checkpoint and a replay
agree on which ports were closed at each point. This section says how a reader
treats a `CLOSE`, what a checkpoint keeps of it, and how a round treats a
closed port. Only a writer outside the program sends `CLOSE`, on an
external or a control port: no process of a resident program does (see "Ordered
shutdown").

`CLOSE` means that a writer has finished for good, and only that; a halt sends
none (see "Control envelope"). A reader hands it to the brain thread like any
other envelope, so it is logged, and then keeps reading but drops everything
that follows: nothing after it is decoded, logged or queued, and the first such
line warns, once per port. The reader does not end on a `CLOSE`, for two
reasons: a reader that ended would leave the heartbeat unhealthy for good once
its producer finished, and a node whose peer sent `CLOSE`, ended its reader, and
was later relaunched would fill that peer's pipe with nobody reading, since the
old reader is gone. Dropping instead of ending solves both. A control port (see
the Glossary) is the exception: its `CLOSE` is logged like any other envelope,
but it closes nothing, live or in a replay, and its reader goes on delivering
what follows, since several writers feed the port in turn, and none of them
ends it for the others.

`closed_ports`, sorted, is the checkpoint field that lists the input ports whose
`CLOSE` the brain thread had processed at the capture, that is, those with a
`CLOSE` record at a position at or below `capture_pos`. It is taken at the same
moment and on the same thread as the node state and `capture_pos`, so it follows
the order in which the brain thread processes the envelopes. Two other
definitions would seem natural, and neither works: the ports whose `CLOSE` the
reader threads have logged by the capture, and the ports that are closed when
the round closes. The reader threads run ahead of the brain thread, and a round
closes after its capture, so both can count a `CLOSE` that lies after
`capture_pos`. A node with three ports shows it: `a` closes before a round
opens, and `c` closes while the round is open, with a message of `c` between the
capture and its `CLOSE`. Either definition would leave the checkpoint saying
that `c` is closed while that message still lies after `capture_pos` and is due
to be replayed. The definition that is used is what lets replay demand that no
`DATA` record ever follows the `CLOSE` of its port, an error that means the log
or the checkpoint is corrupt. Recovery restores the set and adds the port of
each `CLOSE` record after `capture_pos`; the readers of the ports that are then
closed start already dropping what follows, so a relaunched node behaves like
the incarnation that read the `CLOSE`. A `CLOSE` between the capture and the
close of a round is not stored in the checkpoint file, the same as any other
envelope that arrives then: it is history after the cut, and recovery finds it
in the log.

A round does not wait for a port whose writer has finished, since no marker
will ever come from it. A `CLOSE` the brain thread processes while a round is
open takes its port out of the pending ones, keeps whatever channel state
had already been recorded for it, and closes the round if it was the last
one pending; a round that opens later starts with every input port minus the
closed ones (and minus the one whose own marker opened it), and a node whose
inputs have all closed behaves as a root (Glossary). A port that is closed
at the capture has no entry in `channel_state`; one that closes during the
round keeps the entry it had. A node that has finished takes no part in
later rounds: the cut stays consistent, because everything it sent precedes
its `CLOSE` on the channel, and what arrived after the capture is in the
channel state. A module sees none of this: `capture_node_state()` and
`restore_node_state()` handle the node state and nothing else, and no hook
tells the module about a `CLOSE`.

## Sequence numbers in the input log

A node that replays its input log, after a crash or a halt, sends again what
it had sent after its checkpoint, so its neighbors receive part of its messages
twice; and a message can be lost, by a node that crashes after taking it from
its FIFO and before logging it. Sequence numbers tell a receiver both: each
`DATA` carries a number of its channel, the receiver drops one it has already
accepted, and a number that skips another says that a message was lost. The
mechanism and the guarantee it gives are G5 in the Contract, and the error of a
loss is G8. This section says how the input log carries the numbers, and how a
relaunched node rebuilds its own counters from it, so that it still drops what
its log already covers.

A `DATA`'s `seq` travels inside its record's embedded `env`, with no change to
the record format (see "Log structure and record format"). The receiver keeps
two counters per input port (Glossary). `last_seq` is the last number that the
brain thread has processed, and is captured with the node state into the
checkpoint. `_accepted_seq` is the last number that a reader thread has
accepted: it runs ahead of `last_seq`, and it is the one that the dedup check
consults, since a reader decides before the brain thread sees the
message. At startup both start at the checkpoint's `last_seq`, and the replay
advances them over the numbered `DATA` after `capture_pos`, up to what the
reader threads had accepted before the crash, whether the brain thread had
processed it or not.

The numbers do not cover every loss. A reader thread takes a block from its
FIFO and logs its messages in one write; between the two, the messages exist
only in the memory of the process. A message lost there, in a crash, is not
recovered, since its sender considers it delivered and does not send it again,
but the receiver notices it, because the next message skips its number (G8).
This is the Contract's limit "Messages read from a FIFO but not yet written to
the input log".

Four other designs were weighed and left out. A bounded inbound queue, between
the reader threads and the brain thread, would not shorten that window: what a
reader has taken from the FIFO is in memory whatever the size of the queue, and
a bound would only make the reader wait with a block in its hands. A log at the
sender, kept until the receiver acknowledges each message, would close the
window, but needs the two processes to coordinate, and the sender to delete
what each receiver has acknowledged. A second log, of the order in which the
brain thread processes the envelopes, would only be needed if something
reordered them between their arrival and their processing, and nothing does.
Accepting the loss of what waits in the inbound queue, instead of logging on
arrival, would lose messages exactly when a node is busy, the worst time for
it.

## Why the log is not built on the mirror tap

The engine already keeps a copy of what goes through a FIFO when asked to: the
mirror tap of a fifo declared with `--mirror` (Glossary). The input log, which
is `_InputLog` of the runtime library, does not use it, for two reasons, and a
resident program does not allow `--mirror` at all.

The first reason is that the tap changes the channel it observes. It is a
process of its own between the writer and the real FIFO: the writer writes into
a shim FIFO, and the tap reads the shim line by line and writes each line again
into the real FIFO, whose write end it holds itself. The reconnection of
"Reconnecting after a node failure" rests on the two processes at the ends of a
channel both holding its FIFO (ghost connections). With a tap in between, the
writer would hold the shim, not the real FIFO, and the real FIFO would be held
by the tap, a process with a life of its own, so the channel would no longer
be the one that the reconnection designs.

The second reason is locality. The tap lives on the side of the writer, in the
task that owns the FIFO, while the log belongs to the node that receives and
replays it (see "Log structure and record format"). A log built on the tap would
make a recovery reach into a neighbor, and would add a process of its own, with
its own opens and closes of the FIFO, to every channel.

A resident program that declares `--mirror` on a fifo is therefore refused when
it is loaded, before anything is launched (rule 4 of "Validation when the
program is loaded"), so a mirror tap never sits between two resident processes
(see "Limits and non-goals"). `--mirror` remains a debugging aid of general
programs, behind the "Watch FIFO" of the web UI.

# Reconnecting after a node failure

A node that crashes is relaunched while the rest of the program keeps running,
and it has to get back both its state and its connections. Its state comes back
from its checkpoint and its input log (see "Input log"). This section is about
its connections: how the nodes that keep running reconnect with a peer that
crashed and is relaunched, in both directions of a channel, without losing what
the channel held. Nothing here is specific to a relaunch: every channel works
this way from the first start of its nodes, and a relaunch is only the moment
when that matters.

Recovery is localized: only the downed node is relaunched, never the whole
program. A global rollback is kept as a possible future fallback for the cases
the Contract leaves out (see Future work). The `Supervisor` detects a downed
node from the absence of a heartbeat (or, faster, a dead PID, see "Failure
detection") and relaunches it through `debasher_launch_process`, the same
operation as an initial launch (see "Startup sequence: `run()`"), with no
special "recovery mode" logic (see "Relaunching a downed node"). The
relaunched node reconnects to the `Supervisor` on its own: with ghost
connections (see "Ghost connections"), the `Supervisor`'s own reader never
needs to reopen anything, and it learns that a node finished only from its
`.finished` file. Reconnecting to its business peers, the FBP graph's own
channels, is what the rest of this section designs.

The section first states the problem ("The gap"), then the pieces that solve
it: an envelope that tells a finished peer from a crashed one ("`CLOSE`"),
FIFOs whose two ends every endpoint holds, so that none ever sees EOF or
`EPIPE` ("Ghost connections"), the line that resynchronizes a reader after a
writer died in the middle of a message ("The resync line"), and the order in
which a relaunched node opens its FIFOs ("Opening the FIFOs first in
recovery"). It ends with the case in which the reader is the one that dies
("The reader-dies direction").

## The gap: a node cut off from its business peers

When one node crashes while its neighbors keep running, the channels between
them have to survive the crash, and plain FIFOs do not. With plain FIFO
endpoints (a reader that opens its FIFO once and reads until EOF, a writer that
opens it once and writes), the reader of the crashed node's output sees EOF and
ends, never to reopen; a writer to the crashed node gets `BrokenPipeError` and
its thread dies; and the relaunched node blocks for ever in `open()`, with
nobody left at the other end. It would talk to the `Supervisor` again but be cut
off from every peer, and the first goal of the introduction would hold only for
a node whose sole connection is the `Supervisor`. Restarting the whole program,
with a new `debasher_exec` against the same output directory, has none of these
problems: the engine recreates every FIFO, and every node opens them anew.

Reconnecting also needs every endpoint to know what the `Supervisor` learns
from `.finished`: whether a peer's silence means "crashed, will return" or
"finished on purpose". The rest of this section is that signal and its
consequences.

## `CLOSE`: telling a finished peer from a crashed one

A process keeps its FIFOs open for its whole life (it opens them as it starts,
and holds them until it stops: their descriptors are closed once its threads
end, or at its exit for a writer abandoned on a full pipe), so a reader cannot
tell a clean close from a crash from EOF alone: the EOF is identical for a
normal exit and for `SIGKILL`. `CLOSE` is an envelope type of its own (see
"Control envelope"), decentralized (it works without a `Supervisor`, which is
optional, and for a manual relaunch too, once a node can finish for good), sent
by the writer in band when it has finished for good; a halt sends none (see
"Ordered shutdown"). The idea mirrors FIN versus RST in TCP: a `CLOSE` means
"finished, do not wait"; its absence means "may still return". The signal is
designed for a node that finishes for good, which no process of a resident
program does (see "A node that finishes for good" in Future work), so only a
writer outside the program sends it, on an external or a control port.

The reader hands `CLOSE` to the brain thread in order, like any other envelope,
so it is logged and its port can leave the barrier's pending set. Why the
reader then keeps reading and drops what follows instead of ending, and what
`closed_ports` records, is in "`CLOSE` and closed ports".

A process that exits with an error (an exception, a non-zero exit) sends no
`CLOSE` and is treated as a crash, consistent with the `Supervisor`'s own
detection. Once a node can finish for good, a `CLOSE` followed by a later
failure is harmless, since peers keep reading and drop whatever the relaunched
node sends afterward (see "`CLOSE` and closed ports"). The `Supervisor`'s own
channel does not need `CLOSE`: it keeps using the node's `.finished` file, since
a `CLOSE` does not prove the node succeeded, and a node that closed and then
failed must still be heard again when relaunched.

## Ghost connections: holding both ends of a FIFO

`CLOSE` alone does not solve reconnection. A reader that closes and reopens
its FIFO after EOF still has a window, between its own `close()` and
`open()`, in which a writer relaunched inside it gets `EPIPE` and dies, and
EOF is not a reliable event in the first place: with no gap between the old
and the new writer the reader can miss the EOF entirely, and with a backlog
already in the pipe it never sees one at all, since the new writer's data
just follows on the same file descriptor. So a reader has to be correct
whether or not it ever sees EOF, which the transport guarantees by never
producing one.

Every endpoint holds both ends of its FIFO, the real one and a ghost of the
opposite direction. A reader opens `O_RDONLY | O_NONBLOCK` (which returns at
once) and then `O_WRONLY` (a reader now exists, from the FIFO's point of
view); a writer does the same, its real end being the `O_WRONLY` one.
`O_RDWR` is not used: POSIX leaves it undefined for FIFOs. No open ever
blocks, whatever the start order. A writer's crash and relaunch, with the
reader holding a ghost write end, never hangs or raises `EPIPE`; a reader's
crash and relaunch, with the writer holding a ghost read end, never kills
the writer and loses nothing inside the pipe, only whatever the killed
reader had already consumed before it died.

With no EOF, a reader never ends because its peer crashed or was relaunched. It
ends only on a stop request, or on an error, which the heartbeat then reports:
of its stream (an unparsable line not followed by `HELLO`, a gap in the sequence
numbers, a `CLOSE` that claims more than was accepted) or of its input log (at
its size cap, or a failed write to it). The writer never sees `EPIPE` either: a
dead peer means backpressure instead, the writer blocks once the pipe holds 64
KiB, and since a blocked writer cannot be woken, `stop_threads()` joins writer
threads with a bounded timeout. A reader, unlike a writer, never blocks for
long: it waits for data with `poll`, at most `_READER_POLL_MS` (200 ms) at a
time, and looks between two waits whether its node is stopping, so it sees a
stop even on a quiet FIFO. Nothing is written into the FIFO to wake it: a write
there could land in the middle of a message longer than `PIPE_BUF` that its
writer is writing, and cut it in two.

The `Supervisor` learns that a node finished only from its `.finished` file, and
none of its readers can hang waiting for an EOF that never comes.

The ghost ends die with their processes, so both endpoints of a channel
dying together, before either has reopened the FIFO, would destroy the unread
messages: the `Supervisor` holds the FIFO of every business channel as a third
process, which keeps them (see "Holding the business channels").

## The resync line (`HELLO`)

Ghost connections have a price. With no EOF to delimit a message, a
fragment left by a writer killed in the middle of one larger than
`PIPE_BUF` (4096 bytes on Linux; truncation only happens above it) would
merge with the next good message into one unparsable line and swallow it.

Every incarnation of a writer starts with one atomic write, a blank line
followed by a `HELLO` line (an envelope type of its own, consumed by the reader
thread, see "Control envelope"). A reader that finds one unparsable line
tolerates it if the next line is `HELLO`, and drops it; in any other case it is
an error, so a corrupt line is never skipped silently. The resync puts no limit
on the size of a message, unlike a protocol that relied on writes up to
`PIPE_BUF` being atomic; the only limit is that of the outbound backlog,
`OUT_BACKLOG_FAIL_BYTES` (see "Checkpoint persistence"). Only the framework
writes to these channels: an external writer must send complete lines, and a
fragment from one shows up as an error. `HELLO` also tells the reader that its
peer (re)connected.

## Opening the FIFOs first in recovery

A relaunched node opens its FIFOs before restoring its checkpoint or replaying
its input log (`_open_fifos()`, before `run()` does anything that takes time,
which `start_threads()` also calls for the ports that are not open yet, so that
a node driven without `run()` opens them too). Opening them only later, in
`start_threads()`, would put the time spent recovering inside the window in
which the crash of a neighbor could destroy what the neighbor had sent it (this
is about the channel, not the log; "Input log" covers what a node keeps of its
own history). Opening first is what protects a channel when no other process
holds its FIFO: in a program without a `Supervisor`, in one whose `Supervisor`
is given `-no-hold-fifos`, or while the `Supervisor` is down. What remains of
the window is then the time to notice the crash (`HEARTBEAT_CHECK_INTERVAL_SECS`
when the process is gone) and to start the new process. When the `Supervisor`
holds the FIFO of a business channel, the default, there is no such window: what
a neighbor sent survives its crash even before the relaunched node opens
anything (see "Holding the business channels").

## The reader-dies direction

Ghost connections answer the crash of a reader: the writer never sees
`BrokenPipeError` (it blocks on backpressure instead, so there is nothing to
reopen or resend), and unread data in the pipe survives a reader's crash and
relaunch (see "Ghost connections").

`CLOSE` travels only in the direction the data does, from a writer to its
readers, so a node that stops reading from one of its inputs sends nothing back
to whatever writes to it. A writer therefore cannot tell a reader that stopped
for good from one that crashed and may relaunch: both look the same, the writer
just blocks once the pipe fills, and its outbound backlog grows until
`OUT_BACKLOG_FAIL_BYTES` stops it with an error (see "Checkpoint persistence")
that names the port that holds the most, the one whose reader is not reading. In
a resident program a reader stops for good only when it is stopped on its own by
hand (a graceful stop reaches every node together) or when it crashes with
nobody to relaunch it; one slower than its writer for good has the same effect.
No guarantee is at stake in any of them, since nothing is lost or duplicated:
the limit keeps the memory of the writer from growing without end. A signal in
the other direction, symmetric to `CLOSE`, is in Future work.

# `Supervisor` class

The `Supervisor` is the optional process of a resident program (at most one, of
a single task) that watches its nodes and acts when one of them goes down. Every
node sends it heartbeats on a channel of its own; the `Supervisor` declares a
node down when they stop or when its process is gone, relaunches it, and, when a
node keeps failing, gives up on it and stops the rest of the program in order.
It also relays to the initiators the triggers that start a snapshot or a
shutdown, and it holds the FIFO of every business channel, so that what a
channel holds outlives the crash of both of its endpoints. A program without a
`Supervisor` still runs, and a node of it relaunched by hand still recovers;
what the program loses is the detection and relaunch, the relay of triggers and
the held FIFOs.

The `Supervisor` derives, like `FBPProcess`, from `_PortWorker` (see
"`FBPProcess` class"), which gives it the same thread-per-port plumbing: the
parsing of `argv` and the ports from the engine, the logger, one reader thread
per heartbeat channel and for the manual trigger port, one writer thread per
initiator port, and the brain thread, which here dispatches the `INTERACT`
commands that arrive. It inherits nothing of the barrier, the checkpoints or
the input log, which are in `FBPProcess` alone: the `Supervisor` takes part in
no round and keeps no state on disk, so a `Supervisor` relaunched by hand
starts afresh. Besides those threads it runs one of its own, the checker
thread, which decides on a timer which nodes are down.

The section first covers the ports of the `Supervisor` ("Port declaration and
node identity", "Initiator ports", "Manual trigger channel") and the FIFOs it
holds ("Holding the business channels"). It then follows a node through its
failures: how it is found down or finished ("Failure detection",
"Clean-completion detection"), relaunched ("Relaunching a downed node") and
finally given up on ("Escalation on a permanent node failure", "Failing loudly
instead of retrying"). The tool that stops a resident program gracefully,
which the `Supervisor` calls when it gives up on a node, is described with the
one that resets a program, in "Tools for resident programs".

## Port declaration and node identity

The `Supervisor` acts on nodes, not on ports: for each node it has to know which
channel carries its heartbeats, and which process or task it is, so as to find
its files and relaunch it. So it keeps its heartbeat channels in `NODE_PORTS`, a
dict `{node: option_name}`, where `FBPProcess` keeps a plain list of input
ports, all alike to its barrier. The engine gives `NODE_PORTS`, with the other
ports of the `Supervisor`, from the options of its module, as the field
`nodes=<node>=<port>,...` (see "Ports from the engine"); a `Supervisor` built
without the engine, as the unit tests build it, declares it in its class. At
startup, each option is resolved once through `self.opts`, like any port, to the
path of its FIFO, and the reader thread of the channel hands every envelope to
the inbound queue tagged with the node, not with the option, so the rest of the
`Supervisor` works in terms of nodes alone.

A node is named by its process when the process has a single task, and by its
process and the index of its task when it has several: a string, or a tuple
`(process_name, task_idx)`, which the engine writes `<process>:<idx>`. The rule
is the number of tasks, not whether the process is an array, so an array or a
generator of one task is named by its process alone. A resident program is not
assumed to be free of arrays, and the index is not only for the relaunch: the
engine names the files of a task of a process with several tasks
`<process>_<idx>.id` and `<process>_<idx>.finished`
(`debasher::_get_array_taskid_filename`,
`debasher::_get_task_finished_filename`), and those of a process with one task
`<process>.id` and `<process>.finished`, so every file that detection reads
depends on it. A key of `NODE_PORTS` that is neither a string nor such a tuple
is refused when the `Supervisor` is built.

The `Supervisor` itself is never named with an index: a program has at most one,
of a single task, and the engine refuses, when the program is loaded, a second
process that derives from `Supervisor` and a `Supervisor` of several tasks (the
web UI refuses any array or generator for it). With several tasks, each would
hold every business channel and read only some of the heartbeat channels, and
`debasher_stop_resident` waits for the `.finished` of the process, not of a
task.

## Initiator ports

An initiator opens a round when a trigger arrives on one of its control ports
(see "Chandy-Lamport barrier propagation"), and the `Supervisor` can send those
triggers itself, through its initiator ports, named after where they lead (the
commands they carry are the triggers). `INITIATOR_PORTS` lists them: zero or
more output options, each wired to a different initiator through a fifo that
the `Supervisor` defines with the tag `--control`, and which the engine lists
(see "Ports from the engine"). It is a list, and not a single port, because a
resident program may be made of several independent subgraphs, and a marker
never leaves the subgraph of the initiator that opened its round: the module
wires the `Supervisor` to one initiator in each subgraph that it has to reach.
Only the relay of the manual trigger writes into them (see "Manual trigger
channel"): when a trigger arrives there, the `Supervisor` sends it to every
initiator it lists. Its escalation does not use them: `debasher_stop_resident`
writes its `shutdown` into the control port of every node from outside (see
"Escalation on a permanent node failure"). The list is empty when there is no
such fifo: a `Supervisor` that only watches and relaunches nodes, and triggers
no round, is a valid configuration, as long as it has no manual trigger port
either. The engine refuses a manual trigger port with no initiator port when
the program is loaded, since nothing that arrived there could reach a node.

The initiator reads an initiator port as a control port, in its `CONTROL_PORTS`,
because the `Supervisor` defines the fifo with the tag `--control`. Without the
tag the channel would be a data port: the round would open, its marker would go
downstream, and the initiator would wait for ever for a marker from the
`Supervisor`, which sends none. The `Supervisor` sends no `CLOSE` on an
initiator port when it stops, since another `Supervisor`, that of a resumed
program, writes into the same ports; and a `CLOSE` that anyone else writes there
changes nothing either (see control port in the Glossary).

The initiator ports are a convenience, not the only way to open a round. Anyone
outside the program can write an `INTERACT` straight into a control port of an
initiator, whether or not the program has a `Supervisor` and however it is
configured: through "Talk to FIFOs", or with `debasher_snapshot_resident`, which
writes into the control ports of every node; and so could a snapshot timer of
the initiator's own, which is not built (see "Periodic snapshots from a node's
own timer" in Future work).

## Manual trigger channel

The `Supervisor` takes the triggers it relays from its manual trigger port,
`MANUAL_TRIGGER_PORT`: at most one input option, a fifo that the `Supervisor`
defines with the tag `--control` and that is written from outside the program.
It is not one of `NODE_PORTS`, since it carries no node's identity: it is a
channel of commands, not the heartbeat channel of a supervised node. The
`Supervisor` relays every `INTERACT` that arrives there to every initiator of
`INITIATOR_PORTS`, adding an epoch to its `args` when they carry none (see
numbered trigger in the Glossary), so that every initiator opens the same
round; a command that starts no round never reads it.

The `Supervisor` checks no more of the command than that it is a string (see
"Fields of each type"), and does not interpret it, as the catalog of `INTERACT`
commands is open everywhere else in this design (see "Control envelope"). An
initiator that does not recognize a command handles it in its own
`_on_interact`, which logs a warning and ignores it, and never aborts.

## Holding the business channels

The `Supervisor` holds the FIFO of every business channel between two nodes, a
held FIFO in the Glossary, through a read end that it opens without blocking
(`O_RDONLY | O_NONBLOCK`) and never reads (`_open_held_fifos`). A FIFO keeps
what it holds for as long as some process has it open, and discards it only
when every descriptor of it is closed. Each endpoint of a channel holds both
of its ends (see "Ghost connections"), so the crash of one endpoint loses
nothing; the `Supervisor`, a third holder, keeps what the FIFO holds while
both endpoints are down at once. The relaunched reader finds it there, and
what the relaunched writer sends again from its input log comes after it, with
the same numbers, as duplicates that the reader drops (G5), so nothing is new
on either side of the channel. The ends of the FIFO are also as before: a
fragment that a writer killed in the middle of a line leaves at the end is
followed by the `HELLO` of its next incarnation (see "The resync line"), which
sends that whole message again, since a message leaves the outbound backlog
only once it is written whole; a fragment at the start, the rest of a line
that the reader had begun to take when it died, is the limit of "Messages read
from a FIFO but not yet written to the input log" (see the Contract's limits),
as when the reader alone crashes.

The engine gives the FIFOs to hold, `HOLD_FIFOS`, with the other ports of the
`Supervisor` (see "Ports from the engine"): every fifo without a tag whose two
ends are nodes, the loop of a node that emits on its own and the channels of
the tasks of an array included. It leaves out the heartbeat channels and the
initiator ports, which the `Supervisor` already holds as one of their endpoints,
and every fifo with one end outside the program: delivery there is at most once
in any case (see "External inputs" in the Contract's limits), and a holder
would change what the process outside sees, whose `open()` would no longer wait
for the node while it is down. A fifo to hold is not an option of the
`Supervisor`, so the engine names it by its path under the fifo directory of
the program, `<owner process>/<fifo>`, which the `Supervisor` resolves against
the output directory that it already finds from its own execdir. A fifo that is
missing stops the `Supervisor` with an error.

The `Supervisor` holds the FIFOs when it starts, right after it opens the FIFOs
of its own ports (an open that never blocks) and before any of its threads
starts, so that its checker thread cannot relaunch a node first: a `Supervisor`
relaunched by hand holds every channel before it recovers anything. A FIFO whose
contents were destroyed while it was down is empty when it opens it again, which
does no harm; and a second `Supervisor` running at the same time, a new one
while the old one hangs, is only a second holder. The `Supervisor` releases the
FIFOs when it ends, all at once, never one channel at a time: a node's
`.finished` does not say whether it halted or finished for good, and both a halt
and an escalation end with the `Supervisor` itself stopping. Holding the FIFO of
a channel whose reader is gone for good costs one descriptor and at most what a
pipe holds, and changes nothing for its writer, which already blocks once the
pipe is full, since its own ghost end keeps the pipe alive (see "A node that
finishes for good" in Future work).

Nothing holds the FIFOs while the `Supervisor` is down, which nothing watches
(see the Contract's failure model), in a program without a `Supervisor`, and
during a graceful stop, since `debasher_stop_resident` stops the `Supervisor`
before it triggers the halt (a crash during a halt is already outside the
guarantees, see "A crash while a round is open" in the Contract's limits); nor
when the `Supervisor` is given the flag `-no-hold-fifos`, with which it holds
nothing and logs a warning that says what is at stake. Its module offers the
flag as an option of the command line of the program, a flag like any other
(`explain_flag`, `opt_is_non_mandatory_cmdline`,
`define_cmdline_flag_if_given`), so that a run can choose; the chaos test uses
it to reach the limit it would otherwise never reach. The flag reaches the
`Supervisor` only through an option of its module; a module that does not define
it gives no way to turn the holding off, and its `Supervisor` holds the FIFOs in
every run. Each held FIFO takes one descriptor, which the `Supervisor` counts in
the limit it raises before it opens anything (see "Computational specifications
of a resident process").

`test/engine/test_hold_fifos.py` kills both endpoints of a FIFO, opened as a
node opens them, with a single `SIGKILL`, at random moments and with lines
longer than `PIPE_BUF`: with the `Supervisor` holding it, a new reader finds
what was left, complete lines with consecutive numbers between at most a
fragment at each end; without it, nothing. The chaos test does it on a real
run (see "Acceptance: how reliability is shown"): with sink frozen, fanin
writes a backlog to their channel and saves a checkpoint that covers it, and
both are killed; without a holder, sink reports the backlog as lost (G8), and
with it the trace is exact.

## Failure detection

The `Supervisor` decides which nodes are down in a single thread of its own, the
checker thread. It wakes every `HEARTBEAT_CHECK_INTERVAL_SECS` and, for each
node not yet resolved (see "Clean-completion detection"), compares the time
since its last heartbeat with `HEARTBEAT_TIMEOUT_SECS`. One thread does a cheap
comparison per node at each tick, so the number of threads stays the same
whatever the number of nodes; a `threading.Timer` per node would instead take a
thread of the operating system per node, and a new one at every heartbeat, since
a `Timer` that has fired or been cancelled cannot be reused. The time of the
last heartbeat of each node, `_last_heartbeat[node]`, is written by the brain
thread when it dispatches an `INTERACT` `heartbeat`, and read and moved forward
by the checker thread, so a lock guards it. A program sets the timeout of its
`Supervisor` with the computational specification `heartbeat_timeout_s` of that
process, in seconds, in the same way as the limits of a node (see "Computational
specifications of a resident process").

From each launch of a node until its first heartbeat, the silence of the node is
measured against its startup deadline (see the Glossary) instead: the node is
kept in `_starting`, and `_get_silence_limit` gives the limit. A node restores
its checkpoint, runs `initialize_runtime()` and replays its input log before its
heartbeat thread starts, which can take much longer than the interval between
two heartbeats. The first heartbeat then comes one `HEARTBEAT_INTERVAL_SECONDS`
after the threads start, not at once: it resets the relaunch budget (see
"Relaunching a downed node"), so it has to show that the node has run healthy
for a while, not only that it started. Sent at once, it would reset the budget
of a node whose reader fails on the first live message after every relaunch,
such as one past a gap in its sequence numbers that no relaunch can fill, and
that node would be relaunched for ever. A node gives its deadline with its
computational specification `startup_timeout_s`, which the engine passes to the
`Supervisor` in `NODE_STARTUP_TIMEOUT_SECS` (see "Ports from the engine"); the
`startup_timeout_s` of the `Supervisor` itself, `STARTUP_TIMEOUT_SECS`, is the
deadline of every node that gives none; neither is ever shorter than
`HEARTBEAT_TIMEOUT_SECS`, which is also the deadline when neither is given. A
long deadline delays only the detection of a node that is alive and silent at
startup: a node that crashes during its startup, for example on the same record
at every replay, is declared down at once, by its PID, and uses up its relaunch
attempts as any other. That holds after a relaunch too: once the relaunch has
written the `.id` of the new incarnation, which takes the place of the one the
node had when it was declared down, a dead PID there declares the node down
again at the next tick; until then the `.id` still names the incarnation already
declared down, whose PID says nothing about the new one, and only the startup
deadline declares the node down again.

The PID is the fast path to "down". The built-in scheduler gives every process
it launches, resident or not, a `.id` file, `__exec__/<node>/<node>.id`
(`debasher_builtin_sched::_launch`), which holds the PID of its script with the
time at which the process of that PID started; the `Supervisor` reads only the
PID. If that PID no longer exists and the node has no `.finished` file, the node
is declared down at once, without waiting for the timeout. The two signals are
not symmetric: a PID that is gone is certain, whereas a live PID proves nothing
about whether the node works, since a process that is stuck or deadlocked still
holds its PID. So a dead PID is a certain shortcut to "down", the heartbeat
timeout is the only judge of a node that is alive but not working, and a live
PID is never taken by itself as a sign of health.

Two things could make a live node look silent without being so. The first is
the clock: every time kept to measure the silence of a node is taken from the
monotonic clock (`time.monotonic()`), never from the wall clock, which can jump
forward (an NTP correction, a machine coming back from suspend) and make every
node look silent at once. The second is the `Supervisor` itself not running for
a while, starved of CPU, stopped or paused: the heartbeats that the nodes send
meanwhile wait unread in its FIFOs, and when it runs again its checker thread
may run before the threads that read them, and declare a live node down. So the
checker thread measures the time since its previous tick, and when a tick comes
more than one `HEARTBEAT_CHECK_INTERVAL_SECS` late, it moves the
`_last_heartbeat` of every node forward by as much as the tick was late
(`_credit_own_stall`): the time the `Supervisor` did not run is not counted
against any node. A node whose process is gone is still declared down at once,
by its PID, which does not depend on the time elapsed. The other way round, a
node that is itself starved of CPU for longer than `HEARTBEAT_TIMEOUT_SECS`, or
its startup deadline, is declared down,
since from outside it cannot be told from one that is stuck: a program where
that is expected gives its `Supervisor` a longer `heartbeat_timeout_s`.

Nothing supervises the `Supervisor` (see "Failure model"), so it must not live
on without its brain thread, deaf to the heartbeats while its checker thread
declares healthy nodes down, or without its checker thread, blind to the nodes
that do go down. An exception that ends either thread is logged and ends the
`Supervisor` with an error (its `run()` raises one that carries it), which then
counts as a `Supervisor` that died: the nodes keep running, unsupervised, until
it is relaunched by hand. What a writer of its channels can get wrong, a
malformed command or a type that does not belong there, is dropped by the
reader before it reaches the brain thread (see "Fields of each type").

A node that exits with an error on purpose leaves the same signs as one that
crashes (no `.finished`, no more heartbeats, a dead PID), and both are treated
alike; there is no `.failed` file to tell them apart, since nothing needs to.
Should a need arise, a better way than a file that the wrapper script writes
after the fact is for the node to send a richer `INTERACT` before it exits,
while it is still alive and knows why.

## Clean-completion detection (and the `Supervisor`'s own shutdown)

At every tick, the checker thread also looks for the `.finished` file of every
node not yet resolved. It costs one `os.path.exists()` per node, as cheap as the
comparison of the heartbeat, and it is done at every tick rather than only
before a node is declared down, so that the clean end of a node is noticed
within one `HEARTBEAT_CHECK_INTERVAL_SECS`, not up to a whole
`HEARTBEAT_TIMEOUT_SECS` later. The file is written by
`debasher::_signal_process_completion` (`engine/debasher_lib_sched_procs.sh`),
which `debasher::_execute_task` reaches only when the task succeeds or its
`_skip` method skips it: a non-zero exit code returns before it. So `.finished`
means that the node exited cleanly, with code 0, or was skipped. The script of
the task writes it and then exits, and both can happen after the look for the
`.finished` at the start of a tick: so the `.finished` of a node is looked for
once more right before it is declared down, whether by its PID or by its
silence, and the node is marked done if it is there, never taken for a crashed
one and relaunched.

Once its `.finished` is seen, the node is done: it is never checked again,
neither its heartbeat nor its PID, and `on_node_down` is never called for it.
This is what keeps an ordered shutdown from looking like a crash: a node that
stops on purpose stops sending heartbeats and leaves its `.finished` behind,
and the two together tell it from a node that failed.

The same state tells the `Supervisor` when to stop: once every node of
`NODE_PORTS` is resolved, done or given up on (see "Relaunching a downed node"),
and no escalation is still running, it stops its own threads and exits, with no
signal from outside. It also stops on a stop signal, like `FBPProcess` and with
the same handler (see "Ordered shutdown"), installed when `run()` runs on the
main thread (not when a test drives it on another thread). `run()` waits on one
event, `_all_resolved`, which is set in three cases: by the checker thread once
every node is resolved, by `run()` itself once the handler has noted a stop
signal, and by `_run_guarded` when a thread of the `Supervisor` dies; `run()`
tells the last apart by `_thread_error`. The signal lets a tool that stops the
program gracefully end the `Supervisor` before it triggers the halt, so that
the `Supervisor` cannot relaunch a node under it (see
"`debasher_stop_resident`").

## Relaunching a downed node

When it declares a node down, the `Supervisor` calls `on_node_down(node_name)`,
a hook with a default that relaunches the node. Unlike the hooks of
`FBPProcess` that raise `NotImplementedError`, such as `process_data`, this one
has a single right default, since every node of a resident program is
relaunched in the same way; a module may still override it.

The default runs an installed tool,
`debasher_launch_process -d <outdir> -p <process> [-t <idx>]`
(`engine/debasher_launch_process.sh`, in `libexec`), which calls
`debasher_builtin_sched::_launch`, the function of the built-in scheduler that
launched the node the first time. The tool takes the output
directory of the program, not that of the process, and the index of the task
for a node named with one; without `-t` it passes `NO_ARRAY_TASK`. A relaunch
is therefore the same operation as the first launch, as "Startup sequence:
`run()`" requires.

Running the script of the node, `__exec__/<node>/<node>`, again would not do,
since the script does not carry what changes from one launch to the next.
`_launch` exports `BUILTIN_ARRAY_TASK_ID` just before it starts the script, and
the variable is not among those written into the script, an allowlist written
once per process when the script is generated, while this value changes with
every launch; and `_launch`, not the script, writes the `.id` file. A plain
`subprocess.Popen` from the `Supervisor` would give the node the
`BUILTIN_ARRAY_TASK_ID` of the `Supervisor` instead, and would never update its
`.id`: `_is_node_pid_alive` would report the stale PID dead for ever, and since
a real heartbeat resets the relaunch budget at every recovery, the budget would
never run out, an endless loop of relaunches. It would also leave the node in
the process group of the `Supervisor`, while `debasher_stop`
(`kill -9 -- -$pid`) relies on one group per process. `_launch` avoids all of
it: it writes the `.id`, and its own export overrides whatever the caller
inherited.

What `_launch` (`engine/debasher_builtin_sched_lib.sh`) does for this is four
things. First, it exports the index of the task, `BUILTIN_ARRAY_TASK_ID`, 0
for a launch with no task index, and unsets it once the script is started and
its id written, so that the caller keeps none. Second, if the `.id` names an
earlier incarnation that still runs (its PID, with the time at which its
process started, so that a PID reused by another process is not taken for it),
it kills its whole process group with `SIGKILL` (`debasher::_stop_pid`). A
node declared down by its silence may still be alive, stuck; it is killed by
its relaunch, not stopped gracefully, so that the earlier incarnation does not
go on holding its FIFOs next to the new one. Third, it exports
`DEBASHER_LIBEXECDIR` and `DEBASHER_BINDIR`, so that a running process can find
the installed tools (`debasher_libexecdir` and `debasher_bindir` are variables
of the context of the script, which do not reach the programs it runs).
Fourth, it starts the script as the leader of a process group of its own and
writes the id of the new process into the `.id` file as soon as the process
starts, without waiting for it, through a temporary file renamed into place, so
that a reader sees either the old id or the new one, never an empty file. A
script that wrote its own id would make `_launch` wait for it, and a wait of a
fixed length fails a script that is slow to start.

Before it calls `_launch`, `debasher_launch_process` removes the `.finished` of
the task, so that the relaunched node reads `IN-PROGRESS` while it runs and
`UNFINISHED` if it fails, not `FINISHED`. It removes it before the launch, not
after, since a task that ends at once may already have written its new one.

The `Supervisor` runs the tool without blocking its checker thread: a
short-lived thread waits for it and logs a non-zero exit. The tool runs with
its `stdin` redirected, and with its `stdout` and `stderr` sent to `DEVNULL`
too: otherwise they would be those of the `Supervisor`'s own process, its
`.stdout` file and its log (see `debasher::_execute_task`), and
`debasher_launch_process`, and in turn the node it starts in the background,
would hold them open and write into them for as long as the node runs, long
after the `Supervisor` has exited.

A node is relaunched at most `MAX_RELAUNCH_ATTEMPTS` times in a row. The counter
of a node grows each time the node is declared down, and goes back to 0 at its
next heartbeat, the proof that it has recovered, not only that its PID exists
again (see "Failure detection": the first heartbeat goes out one interval after
the startup, restore and replay included, is over). This tells a node that
crashes after every relaunch, during its startup or right after it, whose
counter grows until the budget runs out, from one that crashes now and then over
a long run and recovers each time, whose counter goes back to 0 and never runs
out from incidents far apart. Past the limit, the `Supervisor` calls
`on_node_permanently_failed(node_name)` instead of relaunching the node again,
and the node is given up on: a state of its own, distinct from done, which is
never retried. The error that says so gives the command that shows the scheduler
output of the node (its `.sched_out`), which holds the cause:
`debasher_get_sched_out` with `-d <outdir>`, `-p <process>` and, for a task of a
process with several, `-t <idx>`. It is the output of its last attempt, which no
relaunch follows to truncate it.

## Escalation on a permanent node failure

This section is about what the `Supervisor` does once it gives up on a node. The
node given up on may have been the only path in the graph to other nodes, and a
marker travels only along the channels that carry `DATA` (see "Channel
topology"): no halt can reach those nodes any more, and a graceful stop of the
program cannot end by itself. The section goes through the mechanism, step by
step; its fallback, and the asymmetry that it accepts; and why the `Supervisor`
keeps itself out of the stop, and the alternatives that were ruled out, the last
of them a channel that skips the barrier.

The default `on_node_permanently_failed(node_name)` escalates on a thread of its
own, so that the checker thread goes on seeing the other nodes end. While the
escalation runs, `_escalating` is set: no node is declared down, since the stop
that the escalation asks for makes every node fall silent, and the `Supervisor`
does not resolve, since the escalation still has to end. The thread logs a
warning and runs `debasher_stop_resident` (see "`debasher_stop_resident`") on
the program, with four arguments: `-x <node>` leaves the node given up on out of
the halt, which it could never make; `--kill <node>` kills it first, with
`SIGKILL` to its process group, if it still runs, since a node given up on in
its startup may hang there, alive and holding its FIFOs, and no relaunch is
coming to kill it; `--keep-supervisor` leaves the `Supervisor` running; and
`--timeout FORCE_STOP_TIMEOUT_SECS` bounds the graceful stop. The tool halts and
stops every other node in order. Once each of them has written its `.finished`,
every node of the `Supervisor` is resolved, done or given up on, and the
`Supervisor` ends by itself, as it always does (see "Clean-completion
detection"). The `Supervisor` finds the output directory of the program from its
own execdir, and the tool through `DEBASHER_BINDIR`, which
`debasher_builtin_sched::_launch` exports, since the `PATH` need not hold the
bin directory of the engine.

If the graceful stop does not end within its timeout, as when the node given
up on was the only path to another one, the tool falls back to `debasher_stop`
on the program (`engine/debasher_stop.sh`), which sends `SIGKILL` to the
process group of every process still running, whatever the shape of the graph.
That includes the `Supervisor`. So the `Supervisor` runs the tool in a session
of its own: in the process group of the `Supervisor`, the tool and the
`debasher_stop` that it runs would be killed together with it, and the nodes
after it in the walk of `debasher_stop` would go on running. The asymmetry is
accepted on purpose: the graceful stop keeps every guarantee of the
checkpoints and the input logs, and the fallback is a backstop that only ends
the program, expected only when a failure for good has cut the graph, and may
lose whatever was in flight in what it kills.

The `Supervisor` cannot let the tool stop it, as the tool does by default
before it touches any node. The escalation waits for the tool on a thread of
the `Supervisor`: the tool would send the `Supervisor` its stop signal and
wait for its `.finished`, which the `Supervisor` writes only once it ends,
after that thread returns, so the graceful stop would always run out its
timeout and fall back to the hard kill. Stopping the `Supervisor` last instead
of first fails the same way. A session of its own for the tool does not help
there either: the tool names the `Supervisor` by the PID in its `.id`, not by
the process group of the caller. With `--keep-supervisor`, the tool leaves the
`Supervisor` alone, and the `Supervisor` ends by itself once the nodes are
done, which nothing else has to tell it.

The alternative to the tool, a channel from the `Supervisor` to every node
that skips the barrier, would take a FIFO more for each node of every program,
and would put at risk the guarantees of the barrier in every ordinary stop,
not only in a graph cut by a failure.

## Failing loudly instead of retrying

This section is about a halt that cannot end, and how its forced ending is
made visible instead of passing for a graceful one. It describes the case,
then the mechanism, an exit code and who reads it, and then the alternative
that was weighed.

A node that is not an initiator and crashes while the round of its halt is
open comes back with no memory of that round: the markers it had received are
not replayed, and nothing sends the `shutdown` trigger again, so it never
halts (see "A crash while a round is open" in the Contract's limits). The
`--timeout` of `debasher_stop_resident` keeps this from hanging the stop for
ever, and the fallback to `debasher_stop` ends the program; what must not
happen is that the forced ending passes for a graceful one.

So `debasher_stop_resident` exits with `DEBASHER_STOP_RESIDENT_FORCED_EXIT` (2)
whenever it falls back to `debasher_stop`, never with the code of
`debasher_stop`, which is usually 0, since it does not take "something was still
running to kill" for a failure; and it writes a warning on its stderr, "could
not stop ... gracefully within ...s, forcing debasher_stop", before the
fallback. A user who runs the tool sees both. The web UI reads the code and says
that the program was killed (`orderlyStopOutcome`,
`frontend/src/models/residentRun.ts`). The escalation of the `Supervisor` cannot
read it, since the fallback kills the `Supervisor` before the tool ends; the
tool inherits the stderr of the `Supervisor`, its scheduler output
(`.sched_out`), so the warning stays there, after the warning with which the
escalation began, as the record that the program was killed (G8: detected, never
silent). The tool runs for a short time, so inheriting that stream keeps the
file open only briefly, unlike the node that a relaunch starts, which may run
for days (see "Relaunching a downed node").

The alternative, making the case recoverable, would record in the checkpoint
a halt that is open and act on it at recovery. It has two holes. A checkpoint
is taken when a round opens, at its `capture_pos`, never when it closes, so
nothing would clear that record once the round closed, and a later crash would
open again a halt that had ended cleanly. And the same forgetting affects
every node on the path of the markers, not only an initiator, so recovering
for real means making durable which peers had already closed their part of
the round, a much larger change to the barrier. Failing loudly accepts the
asymmetry of "Escalation on a permanent node failure": it does not make the
case end gracefully, but nobody takes its forced ending for a graceful one,
with no change to the barrier or the checkpoints.

# Tools for resident programs

A resident program does not end on its own. Its nodes run until they are told to
stop. They keep their state across runs, in checkpoints, input logs and halted
markers, which the general tools of the engine know nothing about. Four tools
act on such a program from outside it. They are installed in `bin`, next to
`debasher_exec` and `debasher_stop`. `debasher_stop_resident` stops a running
program gracefully. It halts the program in one round, so that every node can
later resume where it stopped. `debasher_stop`, instead, kills every process at
once. `debasher_snapshot_resident` starts a snapshot in a running program, once
or periodically. Its nodes then write checkpoints and prune their input logs,
whether the program has a `Supervisor` or not. `debasher_reset_resident` takes a
stopped program back to its first run. It sets aside, or deletes, the state that
the nodes keep, so that the next `debasher_exec` starts every node afresh.
`debasher_inspect_resident` shows what one node keeps, and changes nothing. The
`Supervisor` also uses `debasher_stop_resident`, to stop what remains of a
program once it gives up on a node (see "Escalation on a permanent node
failure"). The four share the code that loads the program and finds its nodes
(`engine/debasher_lib_resident_tools.sh`). Two of them, `debasher_stop_resident`
and `debasher_snapshot_resident`, also share the code that writes a trigger into
the control ports of the nodes.

The sections that follow take the tools in that order. Each one says what its
tool is for and how it is called. It then goes through what the tool does, step
by step where the order matters. For a tool that refuses some programs, the
section says when the tool refuses.

## `debasher_stop_resident`: the graceful stop tool

`debasher_stop_resident` is the graceful counterpart to `debasher_stop`. It
halts a resident program in an ordered way (see "Ordered shutdown"), so that
every node can resume where it stopped. Only then does it stop the processes. It
relies on the `Supervisor` stopping on a stop signal (see "Clean-completion
detection"). The rest of the section gives the options of the tool, how it finds
the nodes of the program, the seven steps of the stop, and the stop signal that
it sends.

```
debasher_stop_resident -d <outdir> [-x <node>[,<node>...]]
                       [--kill <node>[,<node>...]] [--timeout <secs>]
                       [--keep-supervisor]
```

`-d` is the output directory of the program, as for every other tool of the
engine that works on one. The other options are there for two callers. One is a
user, who usually wants the whole program stopped. The other is the escalation
of the `Supervisor` (`on_node_permanently_failed`, see "Escalation on a
permanent node failure"). The escalation has already given up on one node, and
must not wait for ever on it.

- `-x` names nodes to leave alone: they are neither waited for nor signalled.
  Each is `<process>`, which names the process, or every task if it is an array,
  or `<process>:<idx>`, one task of an array. The colon avoids an ambiguity:
  `<process>_<idx>` could be a process whose name ends that way. The option lets
  `on_node_permanently_failed` leave out the node that it gave up on, which
  could never halt.
- `--kill` names nodes to kill before the graceful stop, in the same forms as
  `-x`: `<process>` kills every task of a process of several tasks. Each one
  that still runs gets `SIGKILL` to its process group (`debasher::_stop_pid`).
  Its PID comes from `debasher::_builtin_sched_get_running_task_pid`, so that a
  process that got the PID of an ended task is never killed. The escalation
  gives the node that it gave up on to both `-x` and `--kill`, since that node
  may still hang in its startup. `-x` alone leaves a node running. That is what
  a user who excludes one by hand wants.
- `--timeout` (default 60, the same as `FORCE_STOP_TIMEOUT_SECS`) bounds the
  whole graceful attempt. Past it, the tool falls back to
  `debasher_stop -d <outdir>`, a hard kill of the entire program. So the tool,
  once it has found the nodes, always ends the program one way or another. It
  never hangs indefinitely by itself (see "Failing loudly instead of retrying"
  for how it reports the fallback).
- `--keep-supervisor` leaves the `Supervisor` of the program running: the tool
  skips the third step of the stop below. It is for the escalation too. The
  escalation calls this tool from a thread of the very `Supervisor` that the
  tool would otherwise stop. "Escalation on a permanent node failure" says why
  that must never happen, not merely should not.

The tool checks every name of `-x` and `--kill` before it touches anything. A
name that is no node of the program is an error, and the tool ends with 1.
Such names are those of no process, or of a process that is not a node (the
`Supervisor` among them), a task index for a process of one task, and an index
that is not a task of the process.

The tool finds the nodes of the program, and its `Supervisor` if it has one, as
`debasher::_validate_resident_program_processes` does. It loads the module, goes
through `DEBASHER_PROGRAM_PROCESSES`, and classifies each process with
`debasher::_classify_resident_process_role`. An array process is one node per
task, as the `NODE_PORTS` of a `Supervisor` names it. Its number of tasks is
read from the `DEBASHER_NUM_TASKS` line of its script. The scheduler writes that
script before it launches any task, so a task not started yet is counted too.
Every step of the stop reads the files of a task: its `.id` and `.finished`
(`debasher::_get_array_taskid_filename`,
`debasher::_get_task_finished_filename`), its halted marker and its control
ports file (see execdir in the Glossary). The escalation names the one task that
it gave up on, so the other tasks of the same array are still stopped.

The stop goes in seven steps:

1. It records the halted marker baseline of each node (see the Glossary). It
   does so first, before it triggers the halt. A node whose round closed before
   the record would show its fresh marker as the baseline. The wait of step 5
   would then last until the deadline and end in the hard kill.
2. If `--kill` was given, it kills the nodes that it names.
3. If the program has a `Supervisor` and `--keep-supervisor` was not given,
   the tool stops it, with a stop signal to its whole process group (see
   below). Then it waits for the `Supervisor`'s `.finished`. The `Supervisor`
   stops on a stop signal for this reason (see "Clean-completion detection").
   Stopping it keeps it from relaunching a node that the tool is about to stop.
   A `Supervisor` that has already ended (its `.finished` is there) is not
   waited for. Neither is one that does not run (no `.id`, an empty one, or
   one whose process has ended): it relaunches nothing, and the `.finished`
   of one that crashed would never come. The tool warns about it and goes
   on.
4. It writes `shutdown` into every node's own control ports, listed in its
   control ports file (see the Glossary). Most nodes have none, and the round
   reaches them from elsewhere in the graph. The trigger is numbered with the
   time in milliseconds (see numbered trigger in the Glossary), so that every
   initiator halts in the same round.
5. It waits for every node's halted marker to go past its baseline. It never
   waits for the marker to exist: a node that halted in an earlier halt,
   already resumed, would already show one.
6. It reads every node's `.id` again, not reusing any read earlier. It sends
   a stop signal to each node that still runs.
7. It waits for every node's own `.finished`.

The same deadline, from `--timeout`, bounds the check of the names, the finding
of the nodes and every step. A step from the third on that fails sends the tool
to the fallback at once, without waiting for the deadline. One such failure is a
trigger that cannot be written within 5 seconds, as when a control port fed from
outside has no reader. A failure while checking the names or finding the nodes,
such as a process whose script never comes, ends the tool with 1 and an error,
with no fallback.

A stop signal is `SIGTERM` to the whole process group (`kill -TERM -- "-$pid"`,
`debasher::_stop_pid_gracefully`, the `SIGTERM` sibling of the `SIGKILL` of
`debasher::_stop_pid`), never to a lone PID. The reason is the shape of the
processes of a task. `debasher_builtin_sched::_launch` starts a generated script
in the background, as the leader of its own process group (the PID in `.id`).
The process function that this script runs (`debasher::_execute_task`) starts
the Python interpreter as a child process. So the interpreter of a resident
process sits below that PID, not at it. A `SIGTERM` to that PID alone would only
reach the wrapper script. The script has no handler of its own and would die at
once. The interpreter would be orphaned, would never receive anything, and would
run for ever.

So the signal always goes to the whole group. The wrapper script itself ignores
`SIGTERM` at its top level (`debasher_builtin_sched::_print_script_trap`,
`trap '' TERM`, the first thing that `_create_script` writes into the generated
file). It does so to survive that same signal to the group long enough to write
`.finished` once its child, the Python interpreter or a stopped `Supervisor`,
exits. `SIGKILL`, which the hard kill of `debasher_stop` uses, cannot be
trapped, and none of this affects it.

## `debasher_snapshot_resident`: rounds from outside the program

A node never starts a round on its own. The `Supervisor` starts a snapshot only
when a trigger reaches its manual trigger channel. So without a tool or a person
that writes triggers, a program closes no epoch and prunes nothing. It ends at
the size cap of its input logs (see "Pruning and the size cap").
`debasher_snapshot_resident` is that tool: it starts snapshots in a running
resident program. The section describes how the tool starts one round, how it
waits for the round to close, what keeps a round from closing, the periodic
mode, and the programs that the tool acts on.

```
debasher_snapshot_resident -d <outdir> [--timeout <secs> | --every <secs>]
```

The tool is built from `engine/debasher_snapshot_resident.sh` and installed in
`bin`. To start a round, it writes `start_snapshot` into the control ports of
every node, as `debasher_stop_resident` writes `shutdown`. The trigger is
numbered with the time in milliseconds (see numbered trigger in the Glossary),
so that every initiator opens the same round. With a `Supervisor`, the control
port of an initiator is the other end of an initiator port. The tool writes into
it next to the `Supervisor`. A line of a trigger is shorter than `PIPE_BUF`, so
the two writes never interleave. Without a `Supervisor`, the control port is a
fifo fed from outside. Every node of a program that loads is reached from an
initiator (see "Validation when the program is loaded"). So the tool needs
nothing else to reach every node.

It then waits, up to `--timeout` seconds (60 by default), until every node has
a checkpoint of that epoch or of a newer one. A newer round replaces an open
one. A node that the newer round reaches before the older one closes at it
writes a checkpoint of the newer epoch only. That checkpoint is more recent
than the one asked for, and the node can recover from it. So the tool counts it
as well. Once every node has a checkpoint, the tool prints the epoch and
returns 0.

Otherwise, without `--every`, the tool returns 2
(`DEBASHER_SNAPSHOT_RESIDENT_NOT_CLOSED_EXIT`). Code 1 is kept for usage and
setup errors. The tool returns 2 in three cases. If `--timeout` passes, an error
names the nodes that have no checkpoint. If a trigger cannot be written, an
error names the control port, or the node whose control ports file never came.
In both cases a warning then says that the round did not close at every node.
If the program stops while the tool waits, the warning says instead that the
program stopped before the round closed at every node.

Several things keep a round from closing. A round does not close at a node that
is down or stopped. It does not close at a node that has a halt open, which
ignores a snapshot. It does not close at an initiator that has halted, which
ignores the trigger, nor at the nodes that the round reaches only through one.
It does not start when a trigger cannot be written within 5 seconds: a control
port fed from outside whose node is down has no reader. And a node closes it
without a checkpoint when its outbound backlog is over its cap (see "Checkpoint
persistence").

With `--every <secs>`, the tool starts a round every that many seconds. Each
round has until the next one to close. One that has not closed by then is
reported with a warning, and the next trigger replaces it. The period has to be
longer than a round, or rounds keep replacing each other (see "A round that a
newer one replaces" in the Contract's limits). `--timeout` does not apply, and
giving both is an error.

The tool acts only on a running program, and it ends with it. It refuses a
program none of whose nodes is running. With `--every`, it checks every second
whether some node still runs. It returns 0 once none does, after
`debasher_stop_resident`, the escalation of a `Supervisor` or `debasher_stop`.
It is a process outside the program: nothing relaunches it. A program that is
resumed needs it started again.

## `debasher_reset_resident`: a clean start

`debasher_reset_resident` takes a stopped resident program back to its first
run. The paragraphs below say what the tool takes away, why it always resets the
whole program, where what it takes away goes, and when the tool refuses.

```
debasher_reset_resident -d <outdir> [--delete]
```

The tool is built from `engine/debasher_reset_resident.sh` and installed in
`bin`. It resets a stopped resident program, so that the next `debasher_exec` on
the same output directory starts every node as on its first run. A node keeps
its state across runs in files that the engine does not reset (see "Ordered
shutdown"). They are its checkpoints, its input log and its halted marker, in
its execdir (see the Glossary), and the output directory of its process. The
tool takes all of them away, together with the notice of the node (see
"Notices"). It does so for every task of every process, the `Supervisor`
included. It leaves the output directory of each process empty, as the engine
leaves it before a first run. It does not reach the files that a module writes
outside the output directory of its process.

It resets the whole program, never one node. A node that starts afresh numbers
its channels from the start again (G5). A reader that kept its own checkpoint
has accepted higher numbers before, so it would drop everything that the node
sends as duplicates. Resetting a node would mean resetting its readers, and
theirs in turn.

By default, what the tool takes away is set aside, not deleted, since a
checkpoint that is lost cannot be made again. It is moved under
`__reset__/<timestamp>/` in the output directory of the program, each path kept
relative to it (`__reset__/<timestamp>/__exec__/<process>/checkpoints`,
`__reset__/<timestamp>/<process>/...`). A second reset within the same second
gets `__reset__/<timestamp>_1/`, and so on. `--delete` deletes it instead. An
output directory that is already empty is left where it is. So a reset of a
program with nothing left to reset takes nothing away, and says so.

A reset that fails part way does not undo what it took away before the
failure. The error says so. Running the tool again completes the reset: it sets
aside, or deletes, what is left, and does not find what the failed reset already
took away. What the failed reset set aside stays in its own `__reset__`
directory, apart from what the second one sets aside. Until then some nodes are
reset and others are not, the state that resetting one node would leave. So the
program must not be started in between, and nothing stops it.

The tool acts only on a stopped program. It refuses while a `debasher_exec`
holds the lock of the output directory to prepare or run the program, as
`debasher_status` and `debasher_stop` see it
(`debasher::_outdir_is_locked_for_a_run`). It also refuses while any process of
the program, the `Supervisor` included, is in progress. And it refuses while a
launcher node has a batch run in progress, and names the run directory of each
one (see "Stopping and resetting a launcher node"). It takes the lock only for
an instant, to look at it, as `debasher_status` does, and does not keep it while
it resets. So a `debasher_exec` that starts during the reset is not kept out. A
reset that kept the lock would not do: `debasher_stop` would take it for the
scheduler of a run and stop it.

## `debasher_inspect_resident`: what a node keeps

`debasher_inspect_resident` shows what a node of a resident program keeps. It
shows it to a person at the command line and to the web UI, which shows what
the tool prints (see "Observing and talking to a live program" in
`doc/design_doc_webui.md`). The section first describes the two forms of the
tool and what the first one refuses, and how the tool reads the files of a node
without disturbing it. It then describes the node info file, which a node
writes for this tool, and each of the commands and the exit codes of the tool.

```
debasher_inspect_resident -d <outdir> -p <process> [-t <idx>] <command>
debasher_inspect_resident -d <outdir> notices
```

The tool is built from `engine/debasher_inspect_resident.sh` and installed in
`bin`. It prints, as one JSON object on its standard output, what one node of a
resident program keeps in its execdir. These are its checkpoints, its input log,
its halted marker, its node info file and its notice, and, for a launcher node,
the state of its batch runs. The second form prints the notices of every node of
the program at once.

In the first form, `-d`, `-p` and `-t` are those of `debasher_get_stdout`. The
tool loads the program from its output directory, as the other tools do. It
finds the number of tasks of the process in its script (see
"`debasher_stop_resident`: the graceful stop tool"). `-t` is required for an
array process, whose tasks are nodes of their own, and refused for any other.
The tool refuses a process that the program does not have, and one that was
never launched on this output directory (it has no script). It refuses an index
that is not below the number of tasks. It refuses the `Supervisor`, which keeps
no node state: what it knows is in its log, its scheduler output.

The tool only reads. It writes nothing, takes no lock and sends nothing to the
node. So it works the same on a live program as on a stopped one, and no node
ever waits for it. It reads each file by the rules with which the node reads it
when it recovers. It does so with the code of the runtime library
(`debasher_runtime_inputlog.py`, `debasher_runtime_launcher.py`), not with a
copy of those rules. A record of the input log counts only if its line ends in a
newline. So the torn tail that a crash left, or that a node leaves while it
writes, is not shown. A segment that is gone when the tool opens it is skipped:
the node pruned it after the tool listed the segments. A checkpoint of another
schema version is reported as such, with its version, and nothing else of it is
read.

What the tool prints is each file whole, not a cut of the node. A node writes
its checkpoints, its halted marker, its node info file and its notice file into
a temporary file renamed into place. It appends whole lines to its input log. So
the tool reads each file as the node left it at some moment. It does not read
them all at the same moment, though: in a live node, a round may close, or a
segment be pruned, between two of them. What it prints is the state of each
file, not a consistent state of the node.

### The node info file

Part of what the tool shows lives only in the memory of the node. One part is
the limits in force. The class of the node and the computational specifications
of its process decide them (see "Computational specifications of a resident
process"), and only the code of the node could tell them from outside. The other
part is the size of the outbound backlog. Its copy in a checkpoint is missing
precisely when it grows too large (see "Checkpoint persistence"). The node
writes both into its node info file (see the Glossary), a JSON object:

```
{"runtime_class": "ProgramLauncher", "started_at": 1790000000.5,
 "heartbeat_interval_secs": 5,
 "limits": {"input_log_max_bytes": 104857600,
            "out_backlog_max_bytes": 8388608,
            "out_backlog_fail_bytes": 67108864,
            "gil_switch_interval_secs": 0.0005},
 "launcher": {"runs_root": "/data/out/launch", "process": null},
 "updated_at": 1790000123.4, "healthy": true,
 "out_backlog_bytes": {"outdone": 0},
 "checkpoints_skipped_since": null}
```

Some of its fields do not change during an incarnation. `runtime_class` is the
class of the runtime library that the class of the node derives from
(`FBPProcess`, `ProgramLauncher` or `DirectoryWatcher`). `started_at` is the
time at which this incarnation ended its startup. `heartbeat_interval_secs` and
`limits` are what their names say. `launcher`, only for a launcher node, gives
its runs root and the process that its `-process` names, if any, which `runs`,
and `debasher_reset_resident` before a reset, need. The node first writes the
file when its threads start, next to its control ports file.

The heartbeat thread writes the file again, whole, at every tick, with the
figures that change. It does so whether the program has a `Supervisor` or not.
`updated_at` is the time of the tick. `healthy` says whether every thread was
alive at that tick. `debasher_status` cannot tell it, since a node whose brain
thread has died still has a live process. `out_backlog_bytes` is the size of the
outbound backlog of each output port. `send_data` and the writer threads update
it with the backlog, as they update the total of the backlog. So a tick does not
have to go through the backlog. `checkpoints_skipped_since` is the epoch since
which no checkpoint has been written because of the size of the outbound
backlog.

Writing the file costs a small file renamed into place every heartbeat interval.
It is not part of the state of the node. Nothing in the node reads it back,
`debasher_reset_resident` leaves it, and every incarnation writes it again. A
node that is still replaying its input log has not written it yet, and the file
is that of its previous incarnation.

### Commands and exit codes of `debasher_inspect_resident`

There are five commands: four on one node, `summary`, `checkpoint`, `log` and
`runs`, and one on the whole program, `notices`.

`summary` is what the web UI shows first of a node, and what warns of a coming
failure. Its `task_state` is `finished` when the task has a `.finished`, whose
`.id` is then not asked about. Otherwise it is `alive` when the process that the
`.id` of the task names (its PID with its start time) still runs, `down` when
the task has an `.id`, and `not_launched` when it has no `.id` yet. These are
the files that `debasher_status` reads for a whole process, and in the same way.

The `checkpoints` of `summary` give the epochs of the checkpoints that the node
retains, oldest first, each with the time at which it was written. `capture_pos`
is that of the latest one. `halted_epoch` is the content of the halted marker,
or `null` without one.

Its `input_log` gives the size of the input log on disk against
`INPUT_LOG_MAX_BYTES`, its number of segments, and the positions of its first
and its last complete records. The last position is read from the newest segment
with a complete record, as the node reads it when it recovers, never from the
whole log. When the first or the last complete record does not parse,
`input_log` also gives `error`, which says where, and the position that could
not be read stays `null`. Its `to_replay` is how many records lie above the
`capture_pos` of the latest checkpoint. Those are the records that a relaunch
now would go through. The replay runs `process_data()` again on `DATA` only,
acts on `CLOSE` and skips `BARRIER` and `INTERACT`. So `to_replay` is an upper
bound on the work that a relaunch redoes. When the latest checkpoint is of
another schema version, `to_replay` is `null`, since the node refuses to start
on it.

Its `node_info` is the node info file as the node last wrote it, with its age in
seconds, or `null` if the node has never written one. Its `stale` is true when
the file is older than two heartbeat intervals. That happens in a node that is
down, still replaying, or whose heartbeat thread has died. `notice` is the
notice of the node (see "Notices"): its level, its text and when it was set, or
`null` without one.

`checkpoint <epoch>` gives one checkpoint that the node retains: its path, the
time at which it was written, its schema version, and `readable`, whether that
is the version of the runtime library. A readable one also gives `capture_pos`,
`closed_ports`, `out_seq`, `last_seq` and `node_state` whole. It gives
`channel_state` and `out_backlog` counted by port, with the number of messages
and their size in bytes, since they can be large; the path leads to them whole.
An epoch that the node does not retain, never written or pruned since, is an
error that names the epochs that it retains.

`log [--port <port>] [--last <n>]` gives the latest `n` records of the input
log, 100 by default, or of one port with `--port`, in the order of their
positions. Each record comes with its position, its port, and the type, the
sequence number and the payload of its envelope. The command also gives the
`capture_pos` of the latest checkpoint, which tells apart the records that a
relaunch would go through. The tool reads the segments from the newest, and
stops once it has `n` records. A line that ends in a newline but does not parse
would stop the recovery of the node. It is not an error of the tool, which shows
the log and does not recover from it: it is shown in its place, with its
segment, its line number and why it does not parse.

`runs`, for a launcher node only, gives its runs root and, in the order of their
positions, every batch run that it has registered and that still counts (see
"Launching from the queue on disk"): its position, its name, its run directory,
its state (`registered`, `running`, `finished`, `failed` or `stopped`) and, once
it has ended, its exit code. The registrations come from
`.launcher/registrations/` in the output directory of the process, and the runs
root and the process that `-process` names, if any, from the node info file. The
state of each batch run comes from `_get_batch_run_state`
(`engine/debasher_runtime_launcher.py`), the function with which the node itself
reads it (see "Launching from the queue on disk"). Only the node acts on that
state: the tool writes no exit code and launches nothing. So a batch run that
has ended can be shown as ended before the node has written its exit code. For
some batch runs of a whole program the function asks `debasher_status`: those
whose shell is gone without writing `exit_code`. Each question runs
`debasher_status` on the run directory. The node asks it at most once every
`STATUS_CHECK_INTERVAL_SECS` for each batch run. The tool asks it every time,
once for each such batch run. So `runs` takes longer when many batch runs are in
that state.

`notices` is given with `-d` alone, since it covers the whole program. It gives
the notice of every node that has one, sorted by the name of its process and by
its task index. Each comes with its process, its task index (`null` except for a
task of an array) and its notice. The `Supervisor` is skipped, and so is a node
without a notice or not launched yet. The command loads the program once and
reads one small file for each node, so the web UI can run it every time it reads
the statuses of the processes.

The tool ends with 0 once it has printed. It ends with 1, and a message, on an
error of usage or setup. The errors of usage or setup are: a program that is not
a resident one; a process or an index that it refuses (see above); an epoch that
the node does not retain; `runs` on a node that is not a launcher node or has
never written its node info file; a checkpoint, a node info file or a notice
that is not valid JSON (the message names it); `notices` with `-p` or `-t`; and
another command without `-p`.

# `ProgramLauncher`: batch runs from a node

A resident program processes a stream of messages. A general program processes
a batch of inputs and ends. A launcher node joins the two. Every request it
receives launches the same general program, with the options of the request, in
a run directory of its own. A bioinformatics system is the case in view. A BAM
file arrives, and the pipeline that analyses it runs once for it, while other
files keep arriving. When one analysis ends, a node downstream learns it, and
can go on with its results.

The sections that follow go from the node to its batch runs. The first says how
a module defines a launcher node and how the node finds its general program. The
next two say what a request holds, then what a run directory holds and which
request owns it. The next two say how the node launches the batch runs that are
registered and reads their state, and how a node downstream learns that one has
ended. The last two cover a launcher node that runs a single process, and what
stopping and resetting the resident program do to a launcher node and its batch
runs.

## A node that launches a general program

A module defines a launcher node with a class. This section goes through what
sets the node up: the hooks that the class implements, the options of the
process, how the node finds the general program, when it stops as it is
created, how the general program finds its modules, and what the node observes.

`ProgramLauncher` is a subclass of `FBPProcess` in the runtime library
(`engine/debasher_runtime_launcher.py`), not a new kind of process. To the
engine, a launcher node is a node like any other, with its heartbeat and its
control ports. The class implements every hook of a node. The table maps each
one to what it does, and to the section that explains it:

| Hook | What it does in a launcher node | Where |
|---|---|---|
| `initialize_runtime()` | Creates the list of registrations, and reads the identifier of its life (`.launcher/life_id`) or creates it, before the replay | "The run directory and who owns it" |
| `process_data()` | A request, on a port of requests: registers it (its `launch.json` and its registration). The end of a batch run, on `RUNS_DONE_PORT`: announces it on `DONE_PORT`, once | "Requests and run directories", "The run directory and who owns it", "The end of a batch run as an input event" |
| `observe()` | At every pass: reads the state of every batch run, writes the exit code that is still missing, brings in the ends, and launches the batch runs that fit | "Launching from the queue on disk", "The end of a batch run as an input event" |
| `capture_node_state()`, `restore_node_state()` | Save and restore the set of announced runs (the positions of their requests), all that the node state holds | "The end of a batch run as an input event" |

A module needs to write none of these hooks. The class of a launcher node needs
no body (`pass`), or only class attributes such as `OBSERVE_INTERVAL_SECS`. A
module that overrides a hook calls the hook of the class
(`super().process_data(port_name, packet)`, and so on). Otherwise the node stops
doing what its row says.

Three options of the process set the node up. The class has no attribute for
them, so each value has a single source:

- `-pfile`, required, names the general program.
- `-process`, optional, names a single process of the module of `-pfile`, which
  the node launches instead of the whole program (see "A single process").
- `-runsdir`, optional, is the runs root, an absolute path. By default the runs
  root is the output directory of the process. The engine keeps that directory
  across launches of a node (see "Ordered shutdown"), and exports it to the
  node as `DEBASHER_PROCESS_OUTDIR`.

A module that always launches the same program fixes `-pfile` in the
`define_opts` of the process (`define_opt "-pfile" "pipeline.sh" optlist`). One
that leaves the choice to the command line defines it with `define_cmdline_opt`.
Either way, `-pfile` is not a file option (one defined with
`define_cmdline_infile_opt`): the engine leaves a relative name as it is, and
the node looks for it itself. So the program that a node launches shows in the
options of its process, not inside its code.

A relative `-pfile` is looked for as the engine looks for a module that another
module loads. It is looked for first in the directory of the module that
declares the node, where a program keeps its files. The engine exports that
directory to the node as `DEBASHER_PROCESS_MODULE_DIR`. It is then looked for
in the directories of `DEBASHER_MOD_DIR`. So a program can launch one that
another module keeps, at the price of depending on how the machine is set up.
The node runs the engine's own search for this, `debasher_resolve_pfile`, from
the directory of the module. An absolute path is accepted with a warning, since
it ties the program to one machine.

The node stops when it is created in four cases:

- no `-pfile`, or an empty one;
- a `-pfile` that is not found;
- a relative `-runsdir`;
- a node that is a task of an array process, since the tasks would share its
  bookkeeping.

The node does not check that the module of `-pfile` has the process that
`-process` names (see "A single process").

Every input port that carries data is a port of requests. A node with none says
so in a notice (see "Notices"). The output port `DONE_PORT` (`outdone` by
default), if the node has it, tells when a batch run ends (see "The end of a
batch run as an input event").

The modules that the general program loads are found with the `DEBASHER_MOD_DIR`
of the launcher node. The node inherits it along the whole chain of launches.
The frontend puts it in the environment of the `debasher_exec` that it runs,
from the program's own settings; on the command line, the shell has it. Every
node inherits the environment of `debasher_exec`, the `Supervisor` too. A node
that the `Supervisor` relaunches inherits it as well. The launcher node runs
each `debasher_exec` of a batch run with the environment of the node. The
generated script of every process also carries the value that `debasher_exec`
had when it generated it. So a node relaunched by hand, from a shell without it,
still has it. A new run generates the scripts again, and takes its own value.
The script also carries the directory of the module of every process, from
which `DEBASHER_PROCESS_MODULE_DIR` comes.

The launcher node observes its batch runs (see "Observing the outside world").
Its `observe()` launches the registered ones. If the node has `DONE_PORT`,
`observe()` also brings in the end of each one under the name `RUNS_DONE_PORT`
(`runs_done`), its observe port.

## Requests and run directories

What a launcher node receives on a port of requests is a request, and each
request has a run directory of its own. This section gives the format of a
request, an example, the options that a request may not give, and the requests
that the node drops.

A request is a `DATA` whose payload is a JSON object with two fields, both
optional:

- `opts` holds the options of the general program: an object whose keys are
  option names, with their leading dash, and whose values are strings. Without
  it, the general program is launched with no options.
- `run` is the name of the run directory: a relative path of plain names, none
  of which is empty or starts with a dot. Without it, the name is the position
  of the request in the input log. A replay gives the request the same position,
  so the name does not change.

Other fields are ignored. For example:

```
{"opts": {"-bam": "/data/incoming/s17.bam"}, "run": "s17"}
```

Without `-process`, the options follow `--pfile`, `--outdir` and `--sched` on
the command line of `debasher_exec`. It reads its arguments one by one, and
keeps the last value of an option given twice. So a request may not give an
option that `debasher_exec` reads itself, such as `--outdir` or `--wait`, as a
name or as a value. Otherwise it could run the program elsewhere, launch
another one, or change how `debasher_exec` waits for it. The launcher keeps the
list of those options, and a test keeps it in step with `debasher_exec`. Any
other name is passed on, those that start with `--` included. With `-process`,
the options follow `--` and reach the process function alone. The same names
are refused there too, so that a request follows one rule.

The node logs as an error, and drops, these requests:

- a payload that is not a JSON object;
- `opts` that is not an object, a name in it that does not start with a dash,
  or a value that is not a string;
- a name or a value in `opts` that `debasher_exec` reads itself;
- `run` that is given, not `null`, but is not a non-empty string, or that is
  absolute;
- `run` with an empty name (`a//b`, a trailing `/`), `.`, `..`, or a name that
  starts with a dot.

A replay drops it again. The general program checks the options themselves when
it is launched.

## The run directory and who owns it

Each batch run has a directory of its own, and two requests may name the same
one. This section shows what a launcher node keeps on disk, in the output
directory of its process and in each run directory. It then says what the
identifier of a life is, and gives the rule of ownership, which decides the
request that a run directory belongs to.

`process_data` does not launch anything. It registers the batch run, in two
writes. The first is `launch.json`, in the run directory of the batch run,
`<runs root>/<run>`. It holds `life_id`, the position of the request in the
input log and its options. There is one `launch.json` for each batch run. The
second write is the registration, `.launcher/registrations/<position>.json`, in
the output directory of the process. It holds the name of the run directory.
Each file is written to a temporary one and renamed into place. Both writes are
idempotent: a replay of the same request writes the same content to the same
paths.

The two files answer different questions. `launch.json` says which request the
run directory belongs to, and with which options the batch run is launched. The
registrations say which batch runs the node has to see to, and in which order,
as long as the `launch.json` of the run directory records their position. They
are its queue (see "Launching from the queue on disk"). The node cannot find its
batch runs by listing the runs root instead. An absolute runs root may be
shared, and hold the directories of other nodes or of earlier lives. A run name
may be a path (`s17/v2`), so an entry of the root is not always a run directory.
A listing gives no order either.

`.launcher/` holds all the bookkeeping of the node. No run directory can clash
with it, since no run name starts with a dot. With the default runs root, the
output directory of the process holds both `.launcher/` and the run directories.
Say that the node has received two requests: one with `"run": "s17"` at position
7, and one without `run` at position 8. Its output directory then looks like
this:

```
<output directory of the process>/    the runs root, by default
|-- .launcher/
|   |-- life_id
|   `-- registrations/
|       |-- 7.json                    {"run": "s17"}
|       `-- 8.json                    {"run": "8"}
|-- s17/                              the run directory of position 7
`-- 8/                                the run directory of position 8
```

With an absolute runs root, `.launcher/` stays where it is, and the run
directories go under that root. A run directory holds the files of the launcher
node next to the output of the general program:

```
s17/
|-- launch.json     {"life_id": "...", "pos": 7, "opts": {...}}
|-- launcher.pid    the id of the shell that runs the batch run
|-- launcher.log    the output of that shell and of debasher_exec
|-- exit_code       how the batch run ended, from the shell or the node
|-- notified        its end has been brought in (with DONE_PORT)
`-- ...             the output of the general program (__exec__, ...)
```

`launch.json` is written when the request registers the batch run. The other
files of the node come later: when the node launches the batch run, when the
batch run ends, and when its end is brought in. "Launching from the queue on
disk" and "The end of a batch run as an input event" say who writes each of
them, and when.

`life_id` identifies the life of the node, the time since its last clean start.
It is a random string of 32 hexadecimal digits. It is kept in
`.launcher/life_id`, in the output directory of the process. The node reads it
in `initialize_runtime()`, before its replay. It creates the file only when it
is missing or empty. That happens the first time the node starts, and after a
clean start, since `debasher_reset_resident` empties the output directory of the
process. So a relaunch of the node keeps the identifier, although it begins a
new incarnation. A halt and its resume keep it too. Only a clean start begins a
new life. The identifier cannot be part of the node state: a node that crashes
before its first checkpoint would generate another one in its replay.

A run directory belongs to the request that wrote its `launch.json`. The rule
of ownership decides by that file:

- With no `launch.json`, the request registers the batch run.
- With a `launch.json` of the same life and the same position, the request is
  the one that wrote it, processed again by a replay, and nothing changes.
- With any other `launch.json`, the request is logged as an error and dropped:
  another request, or a request of another life, owns the directory. A request
  that wants to analyse the same input again with other options names another
  directory (`s17/v2`), so that no result is overwritten by mistake.

The rule of ownership depends only on what the input log and the directory hold,
never on whether a batch run is still going on. So a replay decides the same
way.

`life_id` tells the requests of a life from those of the one before. After a
clean start, the input log begins again from its first position. A run
directory under an absolute runs root is out of the reach of
`debasher_reset_resident`. It still holds a `launch.json` with a position of the
old log. Without the identifier, a new request at that position would be taken
for the one that wrote it, and never launched.

## Launching from the queue on disk

The registrations on disk are the queue of a launcher node. This section follows
the node as it launches the batch runs of that queue and learns how each one is
going: the launch, how the state of a batch run is read from its run directory,
how `debasher_exec` waits for its program, the states one by one, what the node
does with a batch run that has ended, and which registrations count.

The node's `observe()`, on its observation thread, launches the batch runs that
are registered, in the order of their positions. The node has
`MAX_CONCURRENT_RUNS` slots (1 by default), and a batch run holds one while it
runs. Each one runs
`debasher_exec --pfile <program> --outdir <run directory> --sched <scheduler>`
with the options of its request. It runs in a session of
its own, so that the batch run outlives a crash of the node and a stop of the
resident program. The scheduler is `BATCH_SCHED`, `BUILTIN` by default, as for
the resident program itself. So the batch runs do not depend on the scheduler
that a machine would pick on its own. `SLURM` sends them to a cluster. A program
sets both in the computational specifications of the process,
`max_concurrent_runs` and `batch_sched`, like the limits of a node (see
"Computational specifications of a resident process"). When it loads the
program, the engine checks that the first is a positive whole number and the
second one of the schedulers that `debasher_exec` knows. The node checks the
first again when it is created, since a node built without the engine has not
been through that check.

How a batch run is going is read from its run directory alone, whatever the
scheduler. A relaunched node has lost what its previous incarnation held in
memory, and a tool outside the node (see "`debasher_inspect_resident`: what a
node keeps") never had it. Both find the same state in the directory. So
`debasher_exec` runs under a shell that writes its exit code into the run
directory, in `exit_code`. The shell, not the node, writes it for two reasons.
Only the parent of a process learns its exit code. And the shell, in a session
of its own, outlives the node. The file is written into a temporary one and
renamed into place before the shell ends. `observe()` writes the id of that
shell into the run directory, in `launcher.pid`, just after it starts the shell.
The output of the shell and of `debasher_exec` goes to `launcher.log`.

The id is the PID of the shell together with the time at which its process
started, `<pid>@<start time>`, as the engine keeps the id of a task of the
built-in scheduler (see "The built-in scheduler" in `doc/design_doc_engine.md`).
Once the shell has ended, as by a restart of the machine, the system may give
its PID to another process. A PID alone would then make the batch run look
running for as long as that process lives: not launched again, not reported,
and holding a slot. Without `ps`, the id is the PID alone. A shell that has
already ended when its start time is read gets an empty id, and never runs.

The node writes `launcher.pid` once `ps` has given that start time. A node that
goes down in between, a window of a few milliseconds, finds no `launcher.pid`
when it comes back. It launches the batch run a second time. What follows
depends on the batch run:

- For a whole program, the second `debasher_exec` waits
  `DEBASHER_EXEC_LOCK_WAIT_SECS` for the lock of the first, which keeps it while
  it waits for its program. Unless the first one ends within that time, the
  second ends with 1. Its shell writes `exit_code` 1. The batch run is taken as
  failed (and announced so on `DONE_PORT`), and frees its slot, while the first
  one goes on. When the first one ends, its shell overwrites `exit_code` with
  its own code.
- With `-process`, `debasher_exec_process` takes no lock, and the process runs
  twice at once in the same directory.

`launcher.log` shows both launches. This is a limit of the design. Closing the
window would need the shell to write its own id, which would still leave the
time between the start of the shell and its first line.

`debasher_exec` waits for its program under both schedulers. Under the built-in
scheduler it waits on its own. Under `SLURM` it would only submit the jobs and
end at once, so the node passes it `--wait`. Its exit code then says how the
batch run ended. 0 means that every process finished, 3 that the program did not
finish, and 1 an error, such as options that the program refuses. A request
cannot change that, since `--builtinsched-oneshot` and `--wait` are options that
it may not give (see "Requests and run directories"). `debasher_exec_process`
ends with the exit code of the process function. So the shell of every batch run
writes one file, `exit_code`, with whatever code it ends.

The wait happens in the shell, never in the node. The node does not wait for the
shell, and only polls it so that none is left a zombie. So the node goes on
registering requests, beating and closing rounds while a batch run goes on. The
wait is also what lets the node read the state cheaply. A live shell is a
running batch run, and its exit code is the final one. The node asks
`debasher_status` only about a batch run whose shell is gone without writing
`exit_code`, as after a restart of the machine (see the states below). It asks
at most once every `STATUS_CHECK_INTERVAL_SECS` for each run directory. Under
`SLURM`, the price is a `debasher_exec` alive for each batch run that runs, on
the machine of the node, holding the lock of its run directory.
`MAX_CONCURRENT_RUNS` bounds how many there are.

The state of a batch run is decided by a single function of its run directory,
`_get_batch_run_state`, which the node and `debasher_inspect_resident` share.
The node acts on the state: it writes the exit code of a batch run that has
ended, reports its end, and launches the batch runs that are registered or
stopped, as the free slots allow. The tool only prints the state. The states
follow, in the order in which `_get_batch_run_state` looks at the run directory:

- With `exit_code`: ended, finished if it holds 0, failed otherwise.
- With no `launcher.pid`: registered and not launched. It is launched when a
  slot is free.
- With its shell alive: running. The shell is alive while a process with its PID
  exists, the user of the node can signal it, and, when the id has a start time,
  it started at that time. A process of another user, such as one that took the
  PID after a restart, is never the shell. An id without a start time, or one
  checked when `ps` cannot give the current start time, is decided by the PID
  alone.
- With its shell gone and no `exit_code`: it was stopped before it ended,
  together with its shell, as by a restart of the machine. If `debasher_status`
  says that something of the program is still in progress, the batch run is
  running, and left to end. If it says that everything finished, the batch run
  is ended as finished. Otherwise it is stopped, and `debasher_exec` is launched
  again on the same directory. Its rerun logic skips the processes that had
  finished and resumes the rest.

In `_get_batch_run_state`, the exit code of a batch run takes precedence over
its shell. A shell writes `exit_code` before it ends. So a shell that has ended,
but that the node has not yet waited for and whose PID still shows as alive, is
never taken for a running one. The node waits for each shell that it launched
only so that none is left a zombie. A `debasher_exec` killed alone, while its
shell lives, ends with an exit code of its own. The batch run is then failed,
not launched again.

An ended batch run keeps its exit code, `exit_code`, and is never launched again
on its own: a program that always fails would be launched for ever. A relaunched
node, or one resumed after a halt, finds its queue as it was, and `observe()`
goes on from there. When a batch run is launched is not part of the node state.
It does not need to be the same in a replay, since the node sends nothing when
it launches.

A registration counts only while the `launch.json` of its run directory records
the position of the registration. The node and `debasher_inspect_resident` apply
the same rule. The node writes `launch.json` before the registration, so only a
change by hand under the runs root makes a registration stop counting:

- A run directory removed by hand, while its registration stays, leaves no
  `launch.json`. `observe()` skips that batch run, and logs it as an error once
  in each incarnation. It takes no slot. It is not launched, since its options
  were in `launch.json`. No end is reported for it on `DONE_PORT`. The same
  holds when `-runsdir` names another absolute runs root.
- A later request may name the removed run directory again. It finds no
  `launch.json`, so it registers the directory with its own position. The old
  registration then no longer counts, and the directory is the batch run of the
  new request, launched once.

Only a request after the last checkpoint is processed again by a replay (see
"Recovery: startup and replay"). With no `launch.json`, such a request owns the
directory again, and its batch run is launched again. A request up to the
checkpoint is not processed again, so its registration stays skipped.

## The end of a batch run as an input event

A node downstream may need to know when a batch run ends, to go on with its
results. This section says why the end enters the launcher node as an event from
outside the program, how that event goes from `observe()` to `DONE_PORT`, why
the run directory is marked with a file, what happens when the event arrives
twice or while the node is down, and what grows with the batch runs of a node.

The directory of a batch run always says how it is going. It holds its
`launch.json`, the id of its shell and how it ended (see "Launching from the
queue on disk"), and `debasher_status` on it gives the state of each of its
processes. Anyone can read it, the frontend included, at no cost to the node.

A node downstream can also be told, through the output port `DONE_PORT`
(`outdone` by default) of the launcher node. `observe()` cannot send on it. A
node sends only from `process_data`, whose calls the input log records and a
replay reproduces. So the end of a batch run enters the node as what it is, an
event from outside the program. Once the exit code is written, `observe()`
brings `{"run": ..., "pos": ..., "exit_code": ...}` in with `inject()`, with
`pos` the position of the request that registered the batch run, under
`RUNS_DONE_PORT` (`runs_done`), its observe port. Only then, once the event is
logged, does `observe()` mark the run directory as notified, with a file
`notified`.

`notified` is a file, and not part of the node state, because of the threads.
`observe()` has to know, at every pass, which ends it has already brought in, or
it would bring in the same one at every pass. The node state is no help there.
It belongs to the brain thread, and gets the end only once `process_data`
handles the event, after `inject()` has returned. A pass in between would bring
the end in again. `notified` is written by the thread that reads it, the
observation thread, right after the fact that it records.

`process_data`, on `RUNS_DONE_PORT`, adds that position to the set of announced
runs in its node state. The set holds positions, not names. A later request may
name a removed run directory again (see "Launching from the queue on disk"), and
the end of its batch run is announced too. An event with no run or position is
dropped, and logged as an error. `process_data` then sends
`{"run": ..., "run_dir": ..., "status": ..., "exit_code": ...}`
on `DONE_PORT`. `run_dir` is the absolute path of the run directory, so that the
node that reads the results of the batch run does not have to know the runs
root. `status` is `finished` for an exit code of 0 and `failed` for any other.
The message on `DONE_PORT` is then an ordinary message of a channel: it is
numbered like any other, replayed, and part of the rounds. A replay sends the
same `run_dir`, which follows from the runs root and the name of the run alone.
This holds as long as the runs root does not change between launches of the
node.

- A node that goes down after writing the event and before marking the run
  directory writes the event again when it comes back. `process_data` drops the
  second one, since its position is already in the set of announced runs. A
  replay, which finds both in the log in the same order, drops it too. So the
  event may arrive more than once, but the message on `DONE_PORT` goes out once.
- A batch run that ends while the node is down still leaves its `exit_code`,
  since its shell outlives the node. When the node comes back, `observe()`
  finds it, and the message on `DONE_PORT` goes out.
- A launcher node without `DONE_PORT` brings in no event.

The set of announced runs only grows. A node keeps one position for each batch
run whose end it ever announced, in memory and in every checkpoint. Pruning it
would need to know that no event can bring an end in again. The two events of a
crash between `inject()` and `notified` may straddle a checkpoint, with
`notified` already written when the state is captured. A capture that left out
the position of a run with `notified` would let the second event, live or in a
replay, announce its end again.

The list of registrations only grows too. Each pass of `observe()` reads a few
files of every registered batch run, and checks whether its shell is alive,
those ended long ago included. Removing the registration of a batch run whose
directory has `notified` would not announce its end twice. The registration is
kept as the record of the batch runs of the node, which
`debasher_inspect_resident` lists.

Both are limits of the design. The remedy is a clean start of the whole
resident program (see "`debasher_reset_resident`: a clean start"). With the
default runs root, it also sets the run directories aside (see "Stopping and
resetting a launcher node").

## A single process

Instead of a whole program, a launcher node can run a single process of a
module, the one that `-process` names. This section says how that process is
run, which settings apply to it, and the point in which the states of its batch
runs differ.

With `-process`, a launcher node launches that process of the module of `-pfile`
alone, with `debasher_exec_process <program> <process> -- <options>`. It
launches it from the run directory, so that a relative path among the options of
a request lands there (the file that the process writes, for example). There is
no scheduler in between. `debasher_exec_process` runs the process function and
ends when it ends, and the options of a request are the arguments of that
function.

Of the computational specifications of a launcher node, `max_concurrent_runs`
applies to these batch runs. `batch_sched` does not, since nothing schedules
them. It is ignored, and neither the node nor the engine refuses it.

The node does not check that the module of `-pfile` has the process that
`-process` names. A process that it lacks shows when a batch run ends: each one
fails, its `exit_code` holds 1, and `launcher.log` says why.

The states of these batch runs differ in one point. With neither an exit code
nor a live shell, the process was stopped before it ended. Nothing of it is left
to ask `debasher_status` about. It is launched again from the start, since
`debasher_exec_process` has nothing to resume from. So a process run this way
has to be able to run twice, overwriting its results.

## Stopping and resetting a launcher node

The batch runs of a launcher node are general programs, which do not end with
the resident program that launched them. This section says what stopping and
resetting the resident program do to them, and to the bookkeeping of the node,
and why a reset waits for them.

Stopping the resident program, by a halt or by a signal, does not stop the batch
runs that it launched. They run in sessions of their own, and
`debasher_status` and `debasher_stop` reach them on their run directories. When
the program is resumed, `observe()` finds them running, or ended with no exit
code, and goes on as above.

`debasher_reset_resident` empties the output directory of the process. That
takes away the registrations, the file of `life_id` and, with the default runs
root, every run directory, set aside or deleted with the rest. With an absolute
runs root, the run directories stay where they are, with the results. Their
`launch.json` belongs to a life that has ended. So a request of the new life
that names one of them is dropped. Reusing that name means removing the
directory by hand.

So the reset refuses while a launcher node has a batch run in progress, under
any runs root. Under the default one, it would set aside or delete the run
directory under the batch run: what the batch run writes from then on, its exit
code included, would find no directory. Under an absolute one, it would take
away the registration, and the end of the batch run would never be announced.
The reset asks `debasher_inspect_node` (`engine/debasher_inspect_node.py`, the
tool that reads the files of a node for `debasher_inspect_resident`), with its
command `running_runs`. It tells the state of each batch run by
`_get_batch_run_state`, as the node does. A batch run is in progress when its
state is `running` (see "Launching from the queue on disk"). The reset names the
run directory of each one. Those batch runs have to end first, or be stopped
with `debasher_stop -d <run directory>`. A batch run registered and not launched
yet, or stopped, does not count: with the program stopped, nothing launches it.

# Future work

- **An alias of a node.** Accepting in a resident program a process added with
  `alias` or `ext_alias`, whose code is that of another process, so that the
  same code runs as two nodes with options of their own. Today the engine
  looks for the Python heredoc of every process under the name of that process
  (`debasher::_get_resident_process_source`), finds none for an alias and
  refuses the program. It needs that lookup to follow the alias, and the rule
  that names the class of a node after its process to apply to the process
  that holds the code, not to the alias, whose name the class cannot carry.
  The web UI would offer it then (see "Future work" in
  `doc/design_doc_webui.md`).
- **What the `Supervisor` knows of each node, on disk.** Whether a node that
  is down is being relaunched, how many relaunches it has had, and whether the
  `Supervisor` has given up on it, today only in the log of the `Supervisor`,
  written also into a file that a tool can read, so that the web UI can show
  it (see "Observing and talking to a live program" in
  `doc/design_doc_webui.md`).
- **A single orderly stop at a time.** `debasher_stop_resident` taking a lock
  in the output directory, so that a second orderly stop of the same program,
  from another tab of the web UI or from the command line, waits for the first
  or is refused, instead of stopping the `Supervisor` and writing its own
  `shutdown` in the middle of the first (see "A program that outlives the tab"
  in `doc/design_doc_webui.md`).
- **A single periodic `debasher_snapshot_resident`.** Two `--every` on the
  same output directory start rounds that replace each other, so that none
  closes (see "A round that a newer one replaces" in the Contract's limits).
  The tool could leave its PID in the output directory while it runs, and
  refuse a second `--every` while that PID is alive; the web UI could then
  also find it, to change the period of a program that is running.
- **What a launcher node leaves out** (see "`ProgramLauncher`: batch runs
  from a node"). A command to launch again a batch run that failed, since its
  `observe()` never does it on its own; priorities, or a limit shared by
  several launcher nodes, beyond the `max_concurrent_runs` of each; and a way
  to give the batch runs the execution options of `debasher_exec`, such as
  `--conda-support`, `--docker-support` and `--dflt-nodes`, as `batch_sched`
  gives them their scheduler: the `opts` of a request are the options of the
  general program, pairs of an option and its value.
- **A dynamic number of nodes.** The topology of a resident program is fixed
  before the run starts: every node and every channel is defined up front, and
  only how many there are comes from the command line (see "Ports from the
  engine"). A node created during the run, one per open conversation, per issue
  or per connected user, with a state, a checkpoint and a life of its own, the
  `spawn` of Erlang, is not supported, and nothing in the engine launches a
  process during a run: combining such nodes with the snapshot rounds and the
  `Supervisor` (channels, checkpoints and ports per such node, created and
  retired while a round may be open) would need to be studied, and for Python
  nodes the mechanism could be entirely different. Two forms that need nothing
  new answer most of the cases, and are what a program of agents should use
  first:
  - one node whose node state is a dictionary indexed by a key that travels
    in each message (the conversation), so that the node serves many
    independent conversations: `FBPProcess` allows it, since the node state
    is whatever `capture_node_state()` returns, `restore_node_state()`
    takes it back and the replay brings it up to date. The conversations
    are served one at a time, the checkpoint grows with the open ones, and
    a crash of the node takes every conversation down until the
    `Supervisor` relaunches it. The runtime library could offer it as a
    subclass that extracts the key, keeps the dictionary and hands
    `process_data` the state of that key alone, under the same determinism
    obligation; a checkpoint per key would then be an optimization inside
    that subclass;
  - several such nodes, as the tasks of an array process, behind a node
    that sends each message to the task chosen by a stable hash of its key
    modulo K (`zlib.crc32`, not Python's `hash`, which is salted per
    process), so that a conversation always reaches the same task, in a
    replay too: parallelism across K conversations and a crash bounded to
    the conversations of one task, with K fixed when the program starts
    (see "Ports from the engine").

  What neither gives is a node per conversation, a process of its own with
  its own checkpoint and environment, whose crash touches nobody else. It
  stays here until a program asks for it.
- **Global (coordinated) rollback, as a fallback to localized recovery**: noted
  here, not designed and not built. Localized recovery (see "Reconnecting after
  a node failure") remains the policy for the ordinary crash of a node. A global
  rollback would be the safe harbor for the cases the Contract leaves outside
  its guarantees, an alternative to the narrower, targeted repairs "Repairing
  messages destroyed with a FIFO" below lists for one of them specifically:
  detect the violation, stop, rewind every node to the last consistent cut,
  resume. Cases where it would be used: a guarantee that cannot be kept is
  detected (a hole in a channel's sequence numbers, a missing or corrupt
  checkpoint or log, an incompatible schema version); a node fails permanently
  (today the `Supervisor`'s own escalation ends in `debasher_stop`; with a
  rollback it becomes "stop, fix, rewind, resume"); several connected nodes, or
  all of them, crash together with inputs that cannot be regenerated (the
  contents of the FIFOs are gone, with no process holding them); a crash during
  a snapshot round, if aborting rounds turns out to be harder than falling back
  to the last complete epoch; a deliberate rewind requested by an operator. Not
  for the crash of a single node. The price is the work done since the chosen
  epoch, and the external inputs received since then (delivery at that boundary
  is at most once).

  Like a clean start (see "`debasher_reset_resident`: a clean start"), it can
  be done from outside, by manipulating files, with no special mode in the
  startup sequence (which always loads the highest epoch and replays the log):
  an auxiliary script run while the program is stopped. Points to settle when
  designing it:
  - The target epoch is chosen for each independent subgraph (a set of nodes
    that no channel joins to the rest of the program) on its own: the highest
    one present in the checkpoint folder of every node of the subgraph. No
    channel joins two subgraphs, so no message crosses from the cut of one to
    the cut of another, and cuts of different epochs in different subgraphs
    still make a consistent cut of the whole program. Every node deletes, or
    moves aside, the checkpoints above its target, which belong to a round
    that not everybody completed. The target has to lie inside every node's
    retained window (`CHECKPOINT_RETENTION`), so the interval between snapshots
    bounds how far back a rollback can go.
  - The log records above the position that the target checkpoint reflects must
    be discarded too: the startup replays every record after the loaded
    checkpoint, so leaving them would turn the rollback into a mass local
    recovery, with the duplicates between nodes that this implies.
  - `channel_state` is needed here, unlike in localized recovery: the messages
    in transit at the cut were sent by nodes that, once restored, will not send
    them again, so they have to be redelivered. A way to do it with no new
    logic: the script appends them to the log of the receiving node as records
    after the target position, which the unchanged startup already replays.
  - An epoch number must identify a single round. A numbered trigger gives its
    round a number of its own, the time in milliseconds (see numbered trigger
    in the Glossary), but a trigger without an epoch is numbered from the
    initiator's own last epoch, which can go back when the initiator restarts,
    and after an aborted round two nodes could hold a checkpoint with the same
    number that comes from different rounds, so "the highest common epoch" would
    no longer be a consistent cut. Either every round of a program that is to
    be rolled back comes from a numbered trigger, or a round identifier carried
    by the marker and stored in each checkpoint lets the script check it.
  - An initiator that crashes while its round is open can close that round
    again after it is relaunched, with a later capture (see "A crash while a
    round is open" in the Contract's limits), so that epoch is not a
    consistent cut, and the script cannot tell from the checkpoints alone. The
    node itself can tell at recovery: the log after the restored checkpoint's
    `capture_pos` holds the trigger or the marker with which it opened the
    round. Advancing `_last_epoch` during the replay past the epoch of every
    marker and numbered trigger in the log would make the node ignore that
    round from then on; a trigger without an epoch does not say which epoch
    it opened. Not designed.
  - How `debasher_exec` relaunches a program some of whose nodes are already
    `finished` (to be checked against the rerun logic). A new run recreates the
    FIFOs, which is what a rollback needs.
- **Repairing messages destroyed with a FIFO.** When both endpoints of a channel
  crash while no other process holds the FIFO (the `Supervisor` down too, no
  `Supervisor`, or `-no-hold-fifos`, see "Holding the business channels"), what
  the FIFO held is destroyed, and only what the writer produces again after its
  latest checkpoint comes back (see the Contract's limits). Ways to widen that,
  none designed or tried:
  - The writer restores an older retained checkpoint and replays from there. The
    input log is kept back to the `capture_pos` of the oldest retained
    checkpoint, the numbers are regenerated the same, and the readers drop what
    they already have as duplicates, so everything sent since that checkpoint is
    repaired, at the price of re-executing that stretch at every recovery. It
    cannot close the gap in general: a channel is one-way, so the writer does
    not know how far its reader got and cannot tell how far back is enough. It
    also has to keep the epoch numbering of the latest checkpoint, because a
    node numbers its next round from the epoch of the one it restores.
  - A log at the sender with acknowledgements, the alternative rejected in
    "Input log": the writer keeps what it sent until the reader has it in a
    checkpoint. It would repair everything, but it needs a way back from the
    reader and coordination to delete.
  - More holders than the `Supervisor`, so that a channel keeps what its FIFO
    holds while the `Supervisor` is down too: for example every node also
    holds a read end of the channels of its neighbors, each of them a
    supervised node in its own right. A channel then loses what it holds only
    if its two endpoints and every holder of it are down within one recovery,
    far less likely when the crashes are independent. Who holds which channel,
    and how a node learns the paths of FIFOs that are not its own, would have
    to be settled. Not designed.
  - The global rollback above, which rewinds both nodes to the last consistent
    cut and redelivers from `channel_state` the messages that were in transit at
    the cut.
- **Keeping on disk the part of a line already read when its reader dies.**
  A line that a reader takes in more than one read (in practice, one longer
  than `PIPE_BUF`, since a shorter one is written atomically) is in memory,
  in part, until its last read; if the reader dies meanwhile, that part is
  lost and the rest reaches the relaunched reader as a fragment with no
  `HELLO` after it (see "Messages read from a FIFO but not yet written to the
  input log" in the Contract's limits). The loss is detected (G8), but the
  node cannot get past the hole on its own, which makes it one of the cases
  for the global rollback above. Not done for now, since the loss never goes
  unnoticed and the cost below is significant; it may be worth doing if lines
  of several KiB become common. A possible shape, with portable means only:
  - The reader appends each part of a line still incomplete to a file of its
    port, separate from the input log so that replay, pruning and the size
    cap stay as they are, headed by the log position, `start`, that was next
    when the line began. Once the whole line is in the log, the file is
    emptied, both steps under the lock that orders arrivals. A relaunched
    reader joins what the file holds with what follows in the FIFO, unless
    the last complete record of the log is of its port with a position of at
    least `start`: then the process died between the two steps and the line
    is already in the log.
  - A process killed between a read and the write of that part to the file
    leaves a piece missing from the middle of the line, and the joined line
    can still be valid JSON, with a shorter payload and no error. So joining
    needs the writer to state, in each line longer than `PIPE_BUF`, its length
    and a checksum, checked only on a joined line; one that fails the check is
    a fragment, dropped if a `HELLO` follows, as today.
- **Durability against machine failure (`fsync`)**: see the note in the
  Contract's failure model. First step: when a checkpoint is saved, `fsync` of
  the input log first, so that on disk it reaches the checkpoint's `capture_pos`
  (a node whose log does not is refused at startup, see "Recovery: startup and
  replay"), then of the checkpoint file and of its directory; and of the log at
  a halt (about 2 ms per round); together with the global rollback above it lets
  a program go back, after a machine crash, to its last consistent snapshot.
  Second step: `fsync` of the input log every few messages (group commit), which
  also protects the work since that snapshot, at a cost in throughput. Neither
  is designed nor built.
- **A hook for the module to learn that a port closed.** Today only the engine
  records a `CLOSE`: the barrier will use it and it is stored in `closed_ports`,
  but `capture_node_state()` and `restore_node_state()` never see it, so a
  module cannot react to the end of a channel, for example to emit a final
  result. A hook would have to be called in the order of the input log, and
  replayed, like `process_data`, so that the state a module builds from it is
  the one it would have had without a crash. Not designed.
- **A node that finishes for good.** No node does today: `run()` returns only
  on a stop signal, which sends no `CLOSE`, since the node may be resumed
  later. So the handling of `CLOSE` (`closed_ports`, a round that does not wait
  for a closed port, a node whose inputs have all closed behaving as a root)
  only runs with nodes that end outside `run()`, as the unit tests end them,
  and a program never ends by itself: it runs until `debasher_stop_resident`
  stops it. Points to settle:
  - Who decides. The framework, when every input port that is not a control
    port has closed, the rule of flow-based programming by which a process
    ends once its inputs are exhausted; the module, with a call from
    `process_data`, for a node that emits on its own through a self-loop
    (see "Defining a node"); or both. A node with no data input could only
    end through the module.
  - Replay. The decision falls at a position of the input log, a `CLOSE`
    record or the call to `process_data` for a `DATA`, so that a relaunch that
    replays the log reaches it again at the same point.
  - The order of the ending: write what is still in the outbound queues and
    in the outbound backlog, then `CLOSE` on every output port, then exit. A
    crash in between is recovered by a relaunch that reaches the decision
    again and repeats the steps; a second `CLOSE` is harmless, since a reader
    drops everything that follows the first.
  - Rounds. A node that has finished takes no part in later rounds, as its
    readers already assume, but a consistent cut of a later epoch, to inspect
    the state of the program or for a global rollback (see "Global
    (coordinated) rollback" above), needs its state: a checkpoint saved when it
    finishes, valid for every later epoch.
  - Files. A node stopped by a halt and one that finished for good would
    leave the same `.finished`. The `Supervisor` counts both as done, but a
    resume launches every node again, so a node that finished for good needs
    a marker of its own, like the halted marker, for its relaunch to end at
    once or not to happen; a clean start (see "`debasher_reset_resident`: a
    clean start") removes it.
  - The end of the program. Once every node has finished for good, the
    `Supervisor` finds them all done and exits, so the program ends by itself.
  - Held FIFOs. The `Supervisor` releases them only when it ends (see
    "Holding the business channels"); knowing that a node finished for good,
    it could release the FIFOs of that node's input channels at once.

  Not designed.
- **Periodic snapshots from a node's own timer.** A node never starts a round on
  its own: rounds come from the `Supervisor` or from outside the program, where
  `debasher_snapshot_resident --every` starts them regularly (see
  "`debasher_snapshot_resident`: rounds from outside the program"). That tool is
  a process outside the program, which has to be started again whenever the
  program is resumed. A timer in the node would make a program take its own
  checkpoints with no actor outside it. The idea is an opt-in timer thread in
  `FBPProcess`, gated by a `SNAPSHOT_INTERVAL_SECS` class attribute or option
  (`None`, disabled, by default), that enters the same logic as a
  `start_snapshot` trigger directly, as an in-process call and not as a message.
  The module author would enable it only on a node that is a valid initiator
  (see "Chandy-Lamport barrier propagation"), and it would work the same with or
  without a `Supervisor`, which could still trigger rounds on demand. Points to
  settle: the timer has to start its round through the same hook as an envelope
  that arrives, so that the round has a `capture_pos` (see "Arrival and
  positions"); its period has to be longer than a round, or rounds keep
  replacing each other (see "A round that a newer one replaces" in the
  Contract's limits); and the timers of several initiators would open rounds of
  different epochs, which a node that both reach waits for separately, so they
  need a common numbering, like that of a numbered trigger (see the Glossary).
  Not built.
- **Progress in the heartbeat.** A node whose brain thread is alive but
  blocked is not detected (see "Stuck but alive" in the Contract's limits):
  the heartbeat says that its threads are alive, not that they make progress.
  A counter of the envelopes the brain thread has processed, sent with each
  heartbeat, would let the `Supervisor` notice a node whose counter does not
  move. Telling that apart from a healthy node needs care: a node with
  nothing to process makes no progress either, and a long `process_data` call
  is not a failure (the Introduction asks for no false positives when a
  process is busy). Not designed.
- **Supervising the `Supervisor`.** If the `Supervisor` dies, the nodes keep
  running, but nobody relaunches a crashed node, and no FIFO is held, until the
  `Supervisor` is relaunched by hand (see the Contract's failure model). It
  could be watched and relaunched by a process outside the program, or by the
  nodes through a heartbeat of its own; either way, what watches it is not
  watched in turn. Not designed.
- **A signal from a reader that stops for good.** `CLOSE` goes only from a
  writer to its readers, so a writer cannot tell a reader that stopped for
  good from one that crashed and will be relaunched (see "The reader-dies
  direction"): it keeps queueing for it until `OUT_BACKLOG_FAIL_BYTES` stops
  it with an error. A signal in the other direction, symmetric to `CLOSE`,
  would let the writer stop sending on that port instead. A channel is one
  FIFO, one way, so the signal needs a way back from the reader to the
  writer, which the program does not have today. Not designed.
- **Outputs that leave `process_data` as a result, not as calls to
  `send_data`.** Today a module calls `send_data` from inside `process_data`, at
  any moment of the call and any number of times. The alternative is that
  `process_data` hands its outputs to the framework as a result: returned as a
  list, yielded one by one (which keeps the outputs of a long call streaming),
  or sent through a parameter that exists only during the call. Then
  `send_data` is no longer a method of the node, so a send outside a handler is
  impossible by construction, where the rule that a node acts only inside
  `process_data` (see "source" in the Glossary) needs a check. The framework
  would also receive the outputs of an input at one predictable point, which
  would let it number them as a group (the input at position 5 produced the
  numbers 12 to 14); check that a replay regenerates the outputs that the first
  execution produced, and raise an error (G8) if it does not, so that the
  determinism that a module owes (see "Obligations of module authors") is
  checked and not only assumed; leave out of a replay the outputs already
  delivered; and decide when each output reaches the writer thread. It would not
  make an output durable or slow a sender down: an output stays in memory until
  the writer thread writes it, and the outbound queue has no limit. The cost is
  the model that a module author writes against, and every test that calls
  `send_data` from outside a handler.
- **A `Supervisor` that serializes rounds** (perhaps never done). It would track
  which nodes have reported `checkpoint_saved` for an epoch (today it only logs
  it), leave out the nodes that finished, and relay a trigger only when the
  previous round is complete or a time limit has passed. It would avoid rounds
  that replace each other and would tell which epochs are complete cuts. It
  would not replace the rule that a newer round replaces an older one at a node,
  which holds whatever the source of the trigger (a person writing into the fifo
  of an initiator, a timer, a `Supervisor` relaunched by hand, a node relaunched
  in the middle of a round). It is doubtful because a manual trigger reaches the
  `Supervisor` as a command that it relays without interpreting, and serializing
  means interpreting `start_snapshot` and `shutdown`: how to add that for the
  triggers that a person writes is not clear, and it would only cover the nodes
  that report to the `Supervisor`. Not designed.
- **Resuming with a changed program.** `debasher_exec` resumes a resident
  program from the checkpoints and input logs in its output directory with
  whatever module it is given, even one changed since that state was written: a
  `restore_node_state` that no longer reads the old node state, a `process_data`
  that replays the input log to another result, other ports, or another number
  of tasks from the command line all go unnoticed (see "Ports from the engine").
  The web UI compares the program with the one that produced the state before it
  launches it (see "The directories of a resident program" in
  `doc/design_doc_webui.md`), but a program launched from the command line has
  no such check. The engine could record, at every launch, what the state
  depends on, and warn or refuse when a resume differs from it. Not designed.
- **The ports of a node under test from the program.** The node harness taking
  the ports of a node from the options of the program, as the engine computes
  them for a run, instead of from the test.
- **A launcher node under test.** A `ProgramLauncher` in the node harness, with
  its launches simulated: what it asked to launch, with which options, and how
  the test says each batch run ended.
- **A restart of every node, with no test written for it.** The test runner
  checking `restart()` on every node of a program; the harness would need the
  options that the constructor of each node reads.
- **Python without the GIL.** The free-threaded build of CPython
  (`python3.14t`) runs the threads of a node in parallel. The reader threads
  decode and log their lines while the brain thread runs `process_data`,
  which helps a node with many ports and much traffic. The heartbeat thread
  goes on while `process_data` is inside a long call of a C extension that
  keeps the GIL, which would otherwise stop every other thread until it
  returned, so that a busy node is not taken for a dead one. And the window of
  "Messages read from a FIFO but not yet written to the input log" (in the
  Contract's limits) no longer includes the wait for the GIL. The runtime
  library uses only the standard library, and is meant to guard what its
  threads share with queues, events and locks, never with the GIL, so it is
  expected to run on that build as it is. Running its tests and its chaos
  tests many times on that build would bring out any race that true
  parallelism makes more likely. `GIL_SWITCH_INTERVAL_SECS` would then have no
  effect, and that limit of the Contract would be written without the GIL. A
  node with a single busy thread gains nothing and pays the small cost of that
  build, and a module that imports an extension not marked as safe without the
  GIL turns it back on for its whole process.
- **Nodes in a compiled language, such as Go.** The brain thread runs
  `process_data` in sequence, so a node whose logic is plain Python is bound by
  the speed of the interpreter when it has many messages and little work for
  each (a router, a filter, the aggregator of a stream) or a large node state.
  So is its recovery, whose replay runs `process_data` again on every `DATA`
  record of the input log. Removing the GIL (see "Python without the GIL"
  above) does not change that: it runs the threads of a node in parallel, not
  the brain thread faster. A node written in Go, or in another language with
  direct access to POSIX (opening a FIFO without blocking, `EPIPE` instead of
  `SIGPIPE`, partial writes, `setrlimit`, an atomic `rename`), could share a
  program with nodes in Python, since what ties nodes together is not their
  language but what crosses the FIFOs and what lands on disk. What crosses
  the FIFOs is the envelope, `HELLO` and `CLOSE`, sequence numbers and rounds.
  What lands on disk is the input log, the checkpoint with its schema version,
  the node info file, the control ports file, the halted marker and the
  notice file, which the tools of resident programs read today with the code
  of the Python runtime. It needs:
  - every rule of that protocol, and the format of every one of those files,
    written down in this document, not only in the Python code;
  - a conformance suite that talks to a node only through its FIFOs and its
    files, kills it and relaunches it, so that the same tests check every
    implementation;
  - an engine that recognizes the role of a node by something other than a
    Python class in its heredoc (`debasher::_classify_resident_process_role`),
    and that builds the binary of the node, with a toolchain that a conda
    environment or the system provides.

  Instead of a whole implementation for each language, the runtime library
  could be written once, in Rust, as a library with a C interface: the reader,
  writer, brain and heartbeat threads, the input log, the barrier logic, the
  checkpoints and the files of the node. Each language would add a thin layer
  on top, with the hooks of a node (`process_data`, `capture_node_state()`,
  `restore_node_state()`, `initialize_runtime()`, and `observe()` where it is
  defined) and the calls that a node makes (`send_data`, `sleep`,
  `set_notice()`, `clear_notice()`, `inject()`). The protocol would then have
  a single implementation, a new language would cost only that layer, and the
  Python runtime library itself could rest on it. Rust suits a library that
  other languages load, since it brings no language runtime and no garbage
  collector of its own into their process, which Go does. The price is a
  compiled package to build for every platform, which conda can distribute,
  and a crossing into the code of another language for every message: with
  Python, taking the GIL and building the packet as Python objects. In
  exchange, the threads of the library never wait for the GIL, which leaves
  little for "Python without the GIL" to add.

  The `Supervisor` stays in Python, since what it needs of a node is that
  protocol and the files of the engine (its `.id`, its completion marker and its
  process script), none of which depends on the language of the node. A node
  that waits on the outside world (a service, a directory, a batch run), or
  whose heavy work is already in compiled code that it calls, gains nothing.
  Python stays the language of a node by default, the one that most module
  authors and AI assistants write best, and a compiled language serves the few
  nodes of a program where its time goes. Above some rate of messages the limit
  moves to the protocol itself, one envelope and one record for each message,
  which only larger packets (many values in one `DATA`) push back, in any
  language.

# The tests of the Contract

This chapter says how the tests of "Acceptance" are built, for a reader who
follows one of them. They share the reference program that "Acceptance"
describes, `test/engine/debasher_chaos_ref.sh`, and the helpers of
`test/engine/chaos_ref.py` and `test/engine/resident_run.py`. The chapter goes
through the threads that act on a run, how a run ends, and the functions that
check its trace.

Four kinds of thread of the test act on the run:

- The feeder (`ExtFeeder`) is a source outside the program. It writes the
  values 1 to `k` into `ext`, each numbered with its value. It keeps the FIFO
  open for the whole run, so that what is unread survives a crash of `fanin`.
  While `fanin` is down, a write fails at once, and the feeder writes the same
  value again until `fanin` reopens the FIFO. So no value is lost or
  duplicated on its way into the FIFO. One lost after `fanin` has read it is
  reported by its number (see limit 2, "External inputs").
- The snapshot pacer (`SnapshotPacer`) writes `start_snapshot` into the manual
  trigger port of `sup` at a steady beat while the feed lasts. So rounds close,
  checkpoints are written and logs are pruned during the run, and the kills of
  the test land before, during and after a round.
- The tailer (`SinkTailer`) follows the input log of `sink` from the start of
  the run, segment after segment. Pruning deletes the segments of an
  incarnation of `sink` once a later checkpoint covers them, so a log read
  after the run would miss part of the trace.
- The output tailers (`SchedOutTailer`), one per node that may be killed,
  follow the output of each such node from the start of the run, since a
  relaunch truncates it. They run only in the tests that kill nodes.

A run with no kill ends with `halt_and_wait_for_finished`, which runs
`debasher_stop_resident` and waits for `sup` to end. A run with random kills
ends with `halt_and_check_trace`. It runs the same tool, and looks in the
output of the nodes for the error of a loss: a gap that names its range, or a
fragment that no `HELLO` follows. Each loss has to come from a node that was
killed. With no loss, the halt has to end cleanly, and the trace has to meet
`assert_trace_matches`. With a loss, the halt may not complete, since the
reader that found it has stopped, and the trace has to meet
`assert_trace_with_reported_losses`. The test of a loss engineered on purpose
does not halt: it waits for the escalation of `sup` to end the program.

Four functions check the trace:

- `assert_trace_matches` is the criterion of a run with no loss. On each port,
  the values are exactly 1 to `k`, in order. Then it runs
  `assert_node_state_restored`.
- `assert_node_state_restored` checks the state of `fanin`. Its counts go 1, 2,
  3 on each port, with no jump and no restart: the state was restored across
  every relaunch and resume. Folding the trace gives the digest of every copy:
  the replay processed the ports in the same order as before the crash.
- `assert_trace_with_reported_losses` is the exception, for a run in which a
  killed node reported a loss. The trace is a gapless prefix of the sequence
  numbers of its channel, which ends before the gap if the gap is that of
  `sink`. On each port, the values are in order, with no duplicate and none
  that was never sent. The state of `fanin` is restored.
- `assert_engineered_gap_trace` does the same for a loss engineered on purpose,
  in the case of limit 1, "Both endpoints of a channel crashed". When the error
  names a range, the prefix ends exactly where it begins; otherwise the prefix
  only has to be shorter than the `2k` copies.

The checks rest on the values and on the state of `fanin`. Of the four, only
the two after a loss read the sequence numbers, to check the prefix that a
loss leaves. The test of channel order reads them too.
