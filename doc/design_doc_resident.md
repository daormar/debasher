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
following, **within the limits stated in the Contract section right below**
(failure model, guarantees, obligations of module authors, non-goals). Where a
goal and the Contract disagree, the Contract wins: it says precisely what is
promised.

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
- **Do all of this without imposing a single language on the graph's
  processes**, and without requiring additional external infrastructure
  (databases, coordination services) beyond what the engine and the filesystem
  already offer.
- **Fail loudly, never silently**: whenever a guarantee cannot be kept (for
  example, a message lost because two connected nodes crashed at the same time),
  the violation is detected and reported, instead of the program carrying on
  with silently wrong state.

The Contract below says precisely what these goals do and do not promise. After
it comes the design of the mechanism that provides them, in the sections that
follow, cited in the text by name ("Input log", "Recovery from a node
failure", and so on).

# Glossary

The precise meaning of the words this document uses, in the order in which they
build on each other; the Spanish equivalent is in parentheses. In Spanish
"registro" can mean both the log and one of its entries, so here the log is the
"log" and a record is an "entrada del log". Identifiers in backticks are names
that exist in the code or that have been decided. Earlier text called the input
log the "message log" and its replay "drain"; both names are gone from the code.
The vocabulary of the guarantees (deterministic, idempotent, chaos test,
mutation check, durability level) is defined in the Contract, where it is used.

## Program and topology

- **resident program** (programa residente): a program whose `_program_type` is
  `resident`: long-lived, stateful Python processes joined by FIFOs, always run
  by the built-in scheduler, and covered by the Contract. A **general program**
  (programa general) is a DeBasher program as before, with none of this.
- **node** (nodo): a process of a resident program seen as a vertex of its
  communication graph, named by its process name or, for a task of an array
  process, by `(process_name, task_idx)`. A business node is a subclass of
  `FBPProcess`; the `Supervisor` is a process of the program but not a business
  node, and it takes no part in the barrier.
- **port** (puerto): an option of a node that is connected to a FIFO, named
  without its leading dash. The engine gives each node run by it its input and
  output ports, taken from the options of its module (see "Ports from the
  engine"), in `INPUT_PORTS` and `OUTPUT_PORTS`; a node built without the
  engine declares them in these class attributes. The engine gives the
  `Supervisor` its ports too, and the `Supervisor` names its input ports after
  the nodes it watches (`NODE_PORTS`).
- **channel** (canal): the one-way connection from an output port of one node to
  an input port of another, made of a FIFO (a named pipe created by the engine).
  A **self-loop** (bucle propio) joins two ports of the same node. A channel
  delivers envelopes in the order in which they were sent. Business channels
  carry `DATA` and `BARRIER`; the channels to and from the `Supervisor` carry
  only `INTERACT`.
- **fifo owner** (dueño de una fifo): the process whose `define_fifo_opt` (or
  `define_fifo_opt_generator`) creates a FIFO. It is the process that writes
  it, except for a fifo tagged `--control` or `--external` whose writer is
  outside the program, which its reader owns (see "Channel kinds declared with
  the fifo").
- **fifo tag** (etiqueta de fifo): `--control` or `--external`, the optional
  argument of `define_fifo_opt` and `define_fifo_opt_generator` that makes the
  reader's end of a fifo a control port or an external port (see "Channel kinds
  declared with the fifo").
- **source** (fuente): whatever puts `DATA` into an input port of a node without
  being a node of the program: a person writing into a FIFO, an external
  program, a test harness. A node acts only inside `process_data`, in reaction
  to what it receives, and never sends on its own initiative (`send_data`
  raises anywhere else), so a source is always outside the graph of nodes, and
  what enters through it is an external input (see "Limits and non-goals").
- **root** (raíz): a node that no node sends `DATA` to, not even itself
  through a self-loop. Its input ports, if it has any, are control ports or are
  written from outside the program, by a source. It can start a round, and its
  part of a round closes as soon as it opens, since it has no pending port.
- **relay** (relé): a node with one input port and one output port whose
  `process_data` sends on the output what it received on the input, one message
  out for each message in. It is the simplest node that has both an input log
  and outputs, so tests and measurements use it as the node in the middle; a
  real node would transform the data, or send zero or several messages per
  input.
- **`Supervisor`**: the optional process (0 or 1 per program) that receives
  heartbeats, relaunches downed nodes and can start rounds. It is not itself
  supervised.
- **initiator** (iniciador): the node at which a round starts, because it
  receives an `INTERACT` `start_snapshot` or `shutdown`. It has to be able to
  reach every other node through the channels; a program made of independent
  subgraphs needs one initiator per subgraph.
- **trigger** (disparo): the `INTERACT` command, `start_snapshot` or `shutdown`,
  that makes a node start a round. It reaches an initiator from the
  `Supervisor`, or from an actor outside the program that writes it into a
  FIFO of the initiator, such as `debasher_snapshot_resident` and
  `debasher_stop_resident` (a snapshot timer of the initiator's own is not
  built, see "Periodic snapshots from a node's own timer" in Future work). It
  may carry the epoch of the round it starts (see numbered trigger).
- **numbered trigger** (disparo numerado): a trigger whose `args` carry the
  epoch of the round it starts, the same for every initiator it reaches. An
  initiator handles it like a marker of that epoch that counts no port as
  arrived: it is ignored if that round is already open or over, if it is older
  than the open round, or if it is a snapshot while a halt is open, and
  otherwise it replaces the open round. The `Supervisor` numbers every trigger
  it relays that does not carry an epoch yet, `debasher_snapshot_resident`
  numbers its `start_snapshot` and `debasher_stop_resident` its `shutdown`, all
  with the time in milliseconds: it needs no state to survive a relaunch, and
  it lies above the epochs that initiators number themselves. A clock set back
  makes a numbered trigger look old, and it is ignored with a warning.
- **trigger port** (puerto de disparo): an output port of the `Supervisor`, an
  entry of its `TRIGGER_PORT` list, wired to an initiator; the `Supervisor`
  sends the triggers through it.
- **manual trigger port** (puerto de disparo manual): the input port of the
  `Supervisor`, `MANUAL_TRIGGER_PORT`, where an actor outside the program writes
  a trigger, which the `Supervisor` relays to every trigger port.
- **control port** (puerto de control): an input port of a node, listed in
  `CONTROL_PORTS` (from a fifo tagged `--control`), that carries only
  `INTERACT` commands, such as the one on which an initiator receives its
  triggers. It never carries a marker, so it takes no part in any round, and a
  `CLOSE` on it does not close it, because its writer (the `Supervisor`, or
  whoever writes commands) may come back.
- **control ports file**: the file `control_ports` (`control_ports_<idx>` for a
  task of an array, see execdir) that a node writes in its own `execdir` when it
  starts (one fifo path per line, from `self.opts`, one per entry of
  `CONTROL_PORTS`; empty, not absent, if it has none), so that an external actor
  can find where to write a trigger for an initiator with no other knowledge of
  this program (see `_write_control_ports_file`).
- **external port** (puerto externo): an input port of a node, listed in
  `EXTERNAL_PORTS` (from a fifo tagged `--external`), fed only from outside the
  program (a source, or a person writing by hand), which therefore does not
  carry a marker of its own: a round never waits for it. Unlike a control port,
  a `CLOSE` on it does close it for good, since its writer is not expected to
  come back. A source that does know the protocol may still write the marker of
  the round the initiator opened: it is then read like on any other port.
- **incarnation** (encarnación): one running instance of a node's process.
  Relaunching a node after a crash starts a new incarnation of the same node,
  which reuses its FIFOs, its directory and its checkpoints.
- **execdir**: the node's own directory, `__exec__/<process_name>/` under the
  program's output directory, exported to the process as
  `DEBASHER_PROCESS_EXECDIR`. Its checkpoints and its input log live there. The
  tasks of an array process share it, as they already share the engine's own
  files, which carry the task's index (`<process_name>_<idx>.id`, `.sched_out`,
  ...). A task gets its index too, exported as `DEBASHER_PROCESS_TASK_IDX`
  (empty for a process that is not an array), and adds `_<idx>` to the name of
  everything it keeps there: `checkpoints_<idx>/`, `log_<idx>/`, `halted_<idx>`
  and `control_ports_<idx>` (`_execdir_entry`).
- **limits of a node** (límites de un nodo): `INPUT_LOG_MAX_BYTES`,
  `OUT_BACKLOG_MAX_BYTES`, `OUT_BACKLOG_FAIL_BYTES` and
  `GIL_SWITCH_INTERVAL_SECS`, class attributes of `FBPProcess` that a module
  can redefine and that the computational specifications of a process can set
  for that process of a program (see "Limits of a node").

## Messages

- **envelope** (sobre): one JSON line on a channel,
  `{"type": ..., "payload": ...}`, with one of the five types below. A `DATA`
  envelope also carries a `seq` (see "sequence number" in the input-log
  group). A **message** (mensaje) is an envelope in transit on a channel;
  unqualified, it means a `DATA` message.
- **packet** (paquete): the `payload` of a `DATA` envelope, already
  deserialized: what `process_data(port_name, packet)` receives.
- **`DATA`**: the business traffic. It is the only type that reaches
  `process_data` and the only one that is replayed.
- **`BARRIER`, marker** (marcador): the envelope that carries a round's `epoch`
  and its `halt` flag. Each node forwards it on its output ports, along the same
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
- **`HELLO`, resync line** (línea de resincronización): the first thing every
  incarnation of a writer sends, in one write together with a leading newline.
  The newline ends any fragment that the previous incarnation left when it was
  killed in the middle of a message, and the `HELLO` tells the reader that such
  a fragment can be dropped. It also tells the reader that its peer
  (re)connected.
- **ghost connection** (conexión fantasma): each endpoint of a channel holds
  both ends of the FIFO, the real one and a ghost of the opposite direction. The
  reader never sees EOF and the writer never gets `EPIPE`; a dead peer is only
  backpressure, and a channel outlives the crash of either process.
- **held FIFO** (FIFO retenido): the FIFO of a business channel between two
  nodes, which the `Supervisor` holds open through a read end that it never
  reads, a third holder besides the two endpoints, so that what the FIFO holds
  outlives the crash of both of them. The flag `-no_hold_fifos` turns it off
  (see "Holding the business channels").

## Rounds and checkpoints

- **node state** (estado del nodo): what `capture_node_state()` returns and
  `restore_node_state()` takes back: the serializable logical state of a node,
  complete enough for `restore_node_state()` to rebuild it exactly. Runtime
  resources (connections, file handles) are not part of it;
  `initialize_runtime()` rebuilds them. In the checkpoint it is the field
  `node_state`, which sits beside the `channel_state` and beside the engine's
  own bookkeeping (`capture_pos`, `closed_ports` and the sequence numbers).
- **round** (ronda): one run of the barrier protocol (Chandy-Lamport) over the
  whole program. At a node it opens when the node captures its state, on the
  first marker of the round or on the `INTERACT` that starts it, and it closes
  when the marker has arrived on every input port. An input port whose marker
  has not yet arrived is **pending** (pendiente). A port whose writer has said
  `CLOSE` is never pending: a finished writer sends no more markers, so the
  round does not wait for it. Rounds do not overlap at a node: a newer round
  that reaches it replaces an older one that is open (see abandoned round).
- **epoch** (época): the number that identifies a round. Markers carry it, and
  it names the checkpoint file (`<epoch>.json`). An initiator numbers a new
  round with the epoch that its trigger carries (see numbered trigger) or, if
  it carries none, as the last epoch it closed or abandoned plus one.
- **abandoned round** (ronda abandonada): a round that a node drops, without
  writing a checkpoint for its epoch, because a newer round reached it while it
  was open. The nodes that had already closed it keep their checkpoint, so that
  epoch has no complete cut; the round that replaced it is the one that
  completes.
- **capture** (captura): the moment at which a node calls `capture_node_state()`
  because a round opens. The node state that goes into the checkpoint is the one
  at that moment, not the one at the close of the round.
- **snapshot** (instantánea): a round with `halt` false: every node saves a
  checkpoint and keeps running (the name of the operation, as in
  `start_snapshot`). In the literature the word also names what such a round
  records, the node states together with the channel states; here that result is
  the consistent cut. A **halt** (parada ordenada) is a round with `halt` true;
  it behaves exactly like a snapshot at the node itself (the node keeps running
  after saving its checkpoint), and only writes its own **halted marker** on
  top of that (see below). What actually stops the node, and later resumes the
  program by relaunching every node, is a **stop signal** (see below), decided
  entirely outside the barrier protocol.
- **halted marker** (marca de halted): the file `halted` (`halted_<idx>` for a
  task of an array, see execdir) that a node writes in its own `execdir`
  (atomically, like a checkpoint, but never schema-versioned or pruned) when a
  halt round closes, holding that round's epoch as plain text. Read by nothing
  inside the node itself (in memory, `_halted` already keeps the same
  incarnation from opening another round, see "State variables, at a glance");
  it exists only for an external actor with no other view of the node's state,
  such as the tool a stop signal comes from, to notice that this incarnation has
  nothing further to send and it is safe to stop it.
- **stop signal**: `SIGTERM`, sent to a node's whole process group (the same
  group `debasher_stop` already reaches with `SIGKILL`, see
  `debasher::_stop_pid`), which is what actually ends a node's `run()`
  (`_stop_requested`, set by the handler `run()` installs, `_on_stop_signal`).
  Unlike a halt closing its round, receiving one is not conditional on
  anything: a node that never halted stops on one just the same. Nothing in
  `FBPProcess` decides when to send it: that is external, by design, typically
  once every node's halted marker exists.
  `Supervisor` stops on one too (see the "Clean-completion
  detection" subsection).
- **`debasher_stop_resident`**: the tool that actually sends the stop signal
  in a real program, the graceful counterpart to `debasher_stop` (see
  "`debasher_stop_resident`: the graceful stop tool" for the full sequence).
  Waits for every node's halted marker, then signals each; stops a
  `Supervisor`, if the program has one, before touching any node it watches;
  falls back to `debasher_stop`'s hard kill past its own `--timeout`.
- **`debasher_snapshot_resident`**: the tool that starts a snapshot in a
  running program from outside it, with or without a `Supervisor`, once or
  every given number of seconds (see "`debasher_snapshot_resident`: rounds
  from outside the program").
- **in transit** (en tránsito): a `DATA` message sent before its sender captured
  its state and received after its receiver captured its own.
- **channel state** (estado de canal): `channel_state`, the copy that a node
  keeps, in the checkpoint, of the `DATA` that arrived on a pending port during
  a round: the messages that were in transit at the cut. They are also processed
  normally. Localized recovery does not read it: the same messages are in the
  input log above `capture_pos`, and the replay processes them again. A global
  rollback would.
- **consistent cut** (corte consistente): the checkpoints of every node for the
  same round, taken together (each one holds its node state and the channel
  state of its input ports): a state that the whole program could really have
  been in. It is what the literature calls the snapshot, the result of a round.
  It holds only if no node crashes during the round.
- **checkpoint** (punto de control): the file `<epoch>.json` that a node writes
  atomically in `<execdir>/checkpoints/` (`checkpoints_<idx>/` for a task of an
  array, see execdir) when a round closes. It holds a schema version, the epoch,
  the `node_state` and the `channel_state` and, with the input-log redesign, the
  engine's own bookkeeping: `capture_pos`, `closed_ports`, `out_seq`, `last_seq`
  and the outbound backlog, `out_backlog`. Only the last `CHECKPOINT_RETENTION`
  are kept.
- **outbound backlog, `out_backlog`** (cola de salida pendiente): the `DATA`
  that `send_data` has numbered and queued but the writer thread has not yet
  finished writing when a round captures the node state (G5): `{tag: [{"seq":,
  "payload":}, ...]}`, decoded fresh from each queued line. Without it, a crash
  right there would destroy those messages for good, with no trace (see "Both
  endpoints of a channel crashed" in the Contract's limits). Recovery
  re-enqueues it, with the same numbers, before anything else is sent.

## Input log

- **input log** (log de entrada): one log per node, in `<execdir>/log/`
  (`log_<idx>/` for a task of an array, see execdir), of everything that arrives
  at it, in the order in which the brain thread processes it, written by the
  reader threads when each item arrives. It holds every queued item (`DATA`,
  `BARRIER`, `INTERACT`, `CLOSE`), and only `DATA` is replayed.
- **record** (entrada del log): one line of the input log, holding the position,
  the port and the envelope exactly as it arrived. Not to be confused with the
  verb: what a round does to the `DATA` of a pending port is "keep a copy".
- **position, `pos`** (posición): the number of a record in the input log. It is
  a counter of the receiver, global to the node (across all its input ports),
  that starts at 1 and is assigned in the same critical section that puts the
  item on the inbound queue, so that position order is processing order. A
  checkpoint refers to the log by position, never by epoch.
- **segment** (segmento): a file of the input log with consecutive records,
  named by the position of its first record (`<first pos>.log`). A new one
  starts with every incarnation and when the active one reaches a size limit;
  only whole segments that are not the active one are deleted.
- **capture position, `capture_pos`** (posición de captura): the position of
  the item during whose handling the node captured its state: a marker, or a
  command that opens a round, never a `DATA`. Every `DATA` before it is
  reflected in the checkpoint's node state; recovery replays what comes after
  it.
- **torn tail** (cola partida): an unterminated last line that a process killed
  in the middle of a write leaves in a file. It can happen at any record size.
  A record counts only if its line ends
  in a newline and parses as JSON, so a torn tail is ignored on replay, and no
  incarnation ever appends to an existing segment.
- **replay** (reproducción): re-executing `process_data` on the `DATA` records
  after `capture_pos`, in log order, when a node starts. It reads from disk
  and writes nothing to the log. Earlier text calls it "drain".
- **prune** (poda): deleting what no retained checkpoint needs: the checkpoints
  beyond `CHECKPOINT_RETENTION` and, in the input log, the whole segments that
  end at or before the `capture_pos` of the oldest retained checkpoint.
- **sequence number, `seq`** (número de secuencia): the counter, per channel,
  that the sender puts in each `DATA` so that the receiver can drop a duplicate
  produced by a replay and detect a gap. `out_seq` (the counter of each output
  port) and `last_seq` (the last number accepted on each input port) are stored
  in the checkpoint. Not the same as `pos`: `seq` is per channel and assigned by
  the sender, `pos` is per node and assigned by the receiver. On the receiver
  side `last_seq` is the brain's own view, so the drop itself cannot use it
  directly: a reader thread keeps a second counter of its own, `_accepted_seq`,
  ahead of the brain, which the check actually consults; restored at startup
  from the checkpoint's `last_seq` plus the log after `capture_pos`, it is
  never itself written to a checkpoint (see "State variables, at a glance").

## Threads of a node

- **reader thread** (hilo lector): one per input port. It reads and decodes
  lines, consumes `HELLO`, and hands everything else to the inbound queue (with
  the input-log redesign, after appending the record to the log). After a
  `CLOSE` it goes on reading but drops everything that follows; only
  `stop_threads()` ends it.
- **writer thread** (hilo escritor): one per output port, with its own outbound
  queue. It sends `HELLO` first and, when its node has finished for good (not at
  a halt), `CLOSE` last. A writer whose peer is down and whose pipe is full
  blocks, so it is a daemon thread and `stop_threads()` gives up on it after a
  bounded wait.
- **brain thread** (hilo cerebro): the only consumer of the **inbound queue**
  (cola de entrada) and the only thread that touches the node's state: it runs
  `process_data`, the barrier logic and the writing of checkpoints.
- **heartbeat thread** (hilo de latido): checks on a timer that every other
  thread is alive and, if so, sends the `Supervisor` an `INTERACT` `heartbeat`.
  An unhealthy node simply stops sending.
- **observation thread** (hilo de observación): only in a node whose class
  defines `observe()`. It runs `observe()` every `OBSERVE_INTERVAL_SECS`, which
  looks at the outside world and brings what it sees into the node with
  `inject()`, under the name of its **observe port** (puerto de observación),
  `OBSERVE_PORT`, which is not a fifo (see "Observing the outside world").

## Failure and recovery

- **crash** (caída): the death of a node's process that is neither a halt nor a
  finish for good: `SIGKILL`, an uncaught exception, an out-of-memory kill, or a
  non-zero exit. A deliberate error exit and a crash are treated the same.
- **relaunch** (relanzamiento): starting a new incarnation of a node, by the
  `Supervisor` (through `debasher_launch_process`) or by hand. It is the same
  operation as the first launch: there is no recovery mode.
- **recovery** (recuperación): what a relaunched node does at startup: open its
  FIFOs, load its latest checkpoint, `restore_node_state`, `initialize_runtime`,
  replay the input log after `capture_pos`, then start its threads. Localized
  recovery is the policy: only the downed node is relaunched. A **global
  rollback** (vuelta atrás global) would instead rewind every node to the last
  consistent cut; it is future work.
- **heartbeat** (latido): the `INTERACT` command that a healthy node sends the
  `Supervisor` every `HEARTBEAT_INTERVAL_SECONDS` from the moment its threads
  start. The `Supervisor` declares a node down when they stop for
  `HEARTBEAT_TIMEOUT_SECS`, or for its startup deadline before the first one,
  or at once if the node's PID is gone and its `.finished` file is absent.
- **startup deadline** (plazo de arranque): how long a node has, from each
  launch, to send its first heartbeat, which comes only once it has restored
  its checkpoint, run `initialize_runtime()` and replayed its input log, and
  then run for one `HEARTBEAT_INTERVAL_SECONDS`. Never shorter than
  `HEARTBEAT_TIMEOUT_SECS` (see "Failure detection").
- **down, done, given up** (caído, terminado, abandonado): the states of a node
  in the `Supervisor`. Down: declared down and relaunched. Done: its `.finished`
  file appeared (it exited cleanly with code 0), so it is never checked again.
  Given up: it exhausted `MAX_RELAUNCH_ATTEMPTS`, which triggers the escalation.
- **escalation** (escalada): what the `Supervisor` does when a node is given up:
  an ordered shutdown through the initiators and, if some node has not finished
  after `FORCE_STOP_TIMEOUT_SECS`, `debasher_stop` on the whole program.

## Batch runs

- **launcher node** (nodo lanzador): a node of class `ProgramLauncher`, which
  launches a general program once for each request it receives (see
  "`ProgramLauncher`: batch runs from a node").
- **batch run** (ejecución por lotes): one execution of the general program of
  a launcher node, with the options of one request, by `debasher_exec` on a
  directory of its own, outside the resident program's scheduling.
- **runs root** (raíz de ejecuciones): the directory under which a launcher
  node places its batch runs: the output directory of its process, or an
  absolute path that its class gives.
- **run directory** (directorio de ejecución): the output directory of one
  batch run, `<runs root>/<run>`, where `<run>` is a relative path that the
  request names, or else the position of the request in the input log.
- **registration** (registro): `launch.json` in a run directory, which records
  which request of which life of a launcher node the directory belongs to.
- **life** (vida): the time between two clean starts of a launcher node,
  identified by `life_id`, a random string kept in a file of the output
  directory of its process; `debasher_reset_resident` removes it, so every
  clean start begins a new life.

## State variables, at a glance

Several pieces of a node's bookkeeping go through the same three stages: a
live value that the brain thread keeps up to date as it processes each item, a
copy taken at the capture and held only while a round is open (see "capture"
above), and the checkpoint field the copy is written to when the round closes.
The table names the three for each concept, which this glossary already
defines: it is not redefined here. `Supervisor`'s own bookkeeping (which
nodes are down, how many times each has been relaunched) is a separate
concern, covered in the "`Supervisor` class" section.

| Concept                | Live            | Held during an open round  | Checkpoint field |
| ---------------------- | --------------- | -------------------------- | ---------------- |
| capture position       | `_current_pos`  | `_barrier_capture_pos`     | `capture_pos`    |
| closed input ports     | `_closed_ports` | `_barrier_closed_ports`    | `closed_ports`   |
| sender counters (G5)   | `_out_seq`      | `_barrier_out_seq`         | `out_seq`        |
| receiver counters (G5) | `_last_seq`     | `_barrier_last_seq`        | `last_seq`       |
| outbound backlog (G5)  | `_unwritten`    | `_barrier_out_backlog`     | `out_backlog`    |
| node state             | module's own    | `_barrier_node_state`      | `node_state`     |
| channel state          | round open only | `_barrier_channel_buffers` | `channel_state`  |

`_unwritten` is the one exception to "the brain thread keeps it up to date":
`send_data` appends to it (the brain thread, or the one replaying the input
log), but the writer thread pops from it, under the same lock, as it confirms
each line written.

Bookkeeping that never enters a checkpoint, because it only means something
while its own thread or round is live: `_handler_thread` (the identity of the
thread currently inside `process_data`, checked by `send_data`),
`_barrier_pending` (the input ports an open round still waits on),
`_closed_at_start_ports` (what a relaunched node's readers of closed ports
start out knowing, taken from `_closed_ports` once, when the threads start)
and `_accepted_seq` (the reader threads' own live view of `_last_seq`, ahead
of it, which the dedup check of G5 actually consults; restored at startup
from the checkpoint's `last_seq` plus the log after `capture_pos`, never
itself written to one).

# Contract: assumptions, guarantees and non-goals

The mechanisms that provide these guarantees are designed in the numbered
sections after this one. It applies to programs whose `_program_type` is
`resident`; general programs keep today's behavior.

The purpose of this section is that "reliable" has a precise meaning here:
within the stated assumptions, either the guarantees hold, or the violation is
detected and reported. Never "it usually works". Every guarantee must be backed
by at least one end-to-end test that states it in the same words (see
"Acceptance").

## Failure model

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
checkpoint that was renamed into place but is empty. Surviving that has a price,
measured on the development machine (NVMe, ext4): an append to the log takes 0.8
microseconds without `fsync`, 13 with an `fsync` every 100 appends and about
1050 with one after every append (roughly 950 messages per second); saving a
checkpoint takes 39 microseconds without it and 1.9 ms with `fsync` of the file
and of its directory. Hence it is left out for now, and the cheap first step is
noted in Future work.

## Obligations of module authors

The guarantees hold only if the module code keeps its side of the bargain. The
framework cannot enforce these; the chaos test (see "Acceptance") is what
exposes a violation.

- **`process_data` is deterministic**: given the same starting state and the
  same sequence of received messages, it produces the same new state and the
  same outputs. It must not depend on wall-clock time, randomness, thread
  timing, or external reads, unless whatever it reads is part of the captured
  state or of the message stream. Recovery re-executes it, so a
  non-deterministic `process_data` silently diverges from what it did before the
  crash.
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
- **Messages are JSON-serializable, of any size.** A message larger than
  `PIPE_BUF` (4096 bytes on Linux) being written when its sender crashes can
  leave a truncated fragment in the FIFO. The reader drops it thanks to the
  resync line (see the Glossary) that every writer incarnation sends first,
  and the sender's replay regenerates the message. Only the framework writes
  to these channels; an external writer must send complete lines.
- **Every fifo is defined by the process that writes it, through an output
  option, except one fed from outside the program**, which its reader defines
  through an input option with a fifo tag, `--control` for commands and
  `--external` for data (see "Channel kinds declared with the fifo"). The
  engine reads the direction of every channel from this, and refuses a
  resident program that does not follow it when the program is loaded.

## Guarantees

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
  channel's sequence numbers, a checkpoint with another schema version, an input
  log over its size cap, an exhausted relaunch budget), the node or the
  `Supervisor` raises an error that stops the affected part, instead of
  continuing with silently wrong state. What happens after that stop is manual
  today; the planned fallback is a coordinated global rollback to the last
  consistent cut, **not built** (see Future work).

## Limits and non-goals

- **Both endpoints of a channel crashed while no other process held the
  FIFO.** When one endpoint of a channel crashes, nothing is lost: the other
  holds the FIFO open, and what the writer had sent and the reader had not yet
  read waits in it. That also covers what the writer had only numbered and
  queued but not yet written when it crashed: the checkpoint's outbound backlog
  carries it, and recovery sends it again before anything else. A relaunched
  node holds its FIFOs from the first step of its recovery, before it restores
  its checkpoint or replays its input log, until it dies. If the second
  endpoint crashes before the first has been relaunched and has reopened the
  FIFO, which takes the time to notice the crash and start the new process, or
  if both crash together, neither holds the FIFO for a while, and the
  `Supervisor` still does (see "Holding the business channels"): what the FIFO
  held waits for the relaunched reader, and what the relaunched writer sends
  again from its input log comes after it, with the same numbers, as
  duplicates that the reader drops (G5). Only when no process holds the FIFO
  at some moment is what it held destroyed, at most what a pipe holds (64
  KiB): both endpoints down while the `Supervisor` is down too (it is not
  supervised, see the failure model), in a program without a `Supervisor`, or
  in one whose `Supervisor` is given `-no_hold_fifos`. Whether the loss is
  repaired then depends on where the destroyed messages came from. A relaunched
  writer restores its latest checkpoint and replays its input log after
  `capture_pos`, so it sends again, with the same sequence numbers, everything
  it produced from that point on: the destroyed messages among those reach the
  reader after all, and it cannot tell. What it had sent before that checkpoint
  is inside the node state that it restores and is not sent again: if some of
  it was still unread in the FIFO, it is lost, and the reader finds the hole in
  the sequence numbers when the next message arrives (G8). Ways to repair more
  are listed in Future work, none designed. Non-adjacent nodes may crash
  together with no such problem, and two nodes joined only by a cycle's
  channels cannot hit this limit at all: closing a round on either of their
  shared channels needs both alive and responsive, so a backlog built while one
  is down can never be covered by a checkpoint that has actually closed, and on
  relaunch the sender always replays from an older, already-drained checkpoint
  and resends that backlog.
- **External inputs.** What enters the graph from outside it (a manual write to
  a FIFO, an external program) cannot be regenerated by any node, so at that
  boundary delivery is at most once; inside the graph, the guarantees start from
  the first message a node logs. A source may number its `DATA` as a node
  does (`seq`, from 1, one more for each message, never reused): the receiver
  checks those numbers as on any other channel, so that a message lost at the
  boundary, in the window of the next limit, is reported (G8) and not lost
  silently. What a source sends without numbers gets no such check.
- **Messages read from a FIFO but not yet written to the input log** when a node
  crashes. A reader thread takes a block from the FIFO, up to 64 KiB, and
  writes every message of it to the log in one write before any of them is
  queued, so this window is the time between taking the block and that write:
  decoding and checking its lines, and getting the GIL back after the read if
  another thread of the node holds it, which `FBPProcess` bounds by setting the
  process's switch interval to `GIL_SWITCH_INTERVAL_SECS`, 0.5 ms. A message
  longer than what one read brings, one larger than the FIFO in particular, is
  in memory, in part, from its first read until its last, so it stays exposed
  for as long as its writer takes to write the rest. A message lost in that
  window is not recovered, since its sender considers it delivered, but the
  sequence numbers of G5 make the hole detectable (G8), and the rest of a
  message cut in two reaches the relaunched reader as a fragment that no
  `HELLO` follows, which stops it (keeping that first part on disk is in
  Future work). A FIFO offers no way to look at what it holds without taking
  it, so the window can be made short but not closed.
- **Stuck but alive.** A node whose brain thread is alive but blocked (infinite
  loop, deadlock) is not detected today: the heartbeat proves that its threads
  are alive, not that they make progress. Not a goal for now (see "Progress in
  the heartbeat" in Future work).
- **Not covered**: non-deterministic `process_data`, effects on external systems
  beyond "idempotent if repeated", Slurm, machine failure.
- **`--mirror`** (the debugging tap of a fifo, behind the frontend's "Watch
  FIFO") is not available in resident programs: declaring it aborts the load of
  the program, before anything is launched. Resident processes keep their own
  input log.
- **A node that has finished for good** takes no part in later rounds, so the
  consistent cut of an epoch that starts after it finished has no checkpoint of
  that node: its channel to the others is empty and its last state is its final
  one. Localized recovery does not need it; a global rollback would have to
  treat it (see Future work).
- **A round that a newer one replaces** leaves the nodes that had not closed it
  without a checkpoint for its epoch, so that epoch has no complete cut. The
  round that replaced it does complete, at every node it reaches, and that is
  the cut that counts; localized recovery never uses a cut. It holds if the
  initiators start the same epoch (see numbered trigger in the Glossary). Rounds
  started closer together than they take to complete keep replacing each other,
  and none completes until they stop, so whatever starts rounds periodically
  has to leave more time between them than a round takes.
- **A crash while a round is open.** The node comes back with no round open,
  and the markers it had received for that round are not replayed (only `DATA`
  and `CLOSE` are). At a node that is not an initiator, the next marker of
  that round opens it again, and it waits for ever for the markers already
  received: it writes no checkpoint for that epoch, and the next round
  replaces it. At an initiator whose round a trigger opened, no marker was
  received, so the round opens again when its own marker comes back around a
  cycle and closes there, with a capture later than the first: that epoch is
  not a consistent cut (see the global rollback in Future work). A halt
  cannot wait for the next round, because a node that has halted ignores
  every later trigger, so a node that is not an initiator and crashes while
  its halt is open never halts, while every other node does.
  `debasher_stop_resident`'s `--timeout` bounds the wait for the halted
  markers whatever the reason one never appears, then falls back to the hard
  kill of `debasher_stop` and reports it with its own exit code (see "Failing
  loudly instead of retrying"). Making the case recoverable needs a round's
  partial progress to be durable, which is not designed.
- **A node that crashes again right after every relaunch** is not retried
  forever: after `MAX_RELAUNCH_ATTEMPTS` it is declared permanently failed and
  the escalation applies.

## Acceptance: how reliability is shown

Reliability is claimed only for what passes a **chaos test**: a reference
resident program with the shapes that matter (a fan-in node with more than one
input port, which keeps a node state and whose `process_data` is sensitive to
the order across ports, a cycle, a source and a sink), run under `kill -9` of
random nodes at random moments (including several at once, adjacent pairs, and
moments in which a snapshot round is open), with the `Supervisor` relaunching
them, and halted and resumed.

Pass criterion: for each port the fan-in node reads, the messages it is seen
to have processed on that port, in a run's own trace, form exactly the
sequence that port's writer actually sent, in the order it sent them, with no
duplicate and no missing message. The fan-in node also sends, with each
message, its node state after processing it, and that state must go on across
every relaunch and resume as if the node had never stopped. The run's full
trace only has to be some interleaving of those per-port sequences, never a
byte-for-byte match against one frozen reference run: which interleaving comes
out, even with no failure at all, is itself a race between independent writers
that a single run does not pin down uniquely. The exception follows from two
limits of the Contract, after which a message can be lost beyond repair: both
endpoints of a channel crashed while no other process held the FIFO, which the
chaos test reaches with `-no_hold_fifos` (see "Holding the business
channels"), and a node killed with a message that it has read from a FIFO but
not yet written to its input log. A run that hits either passes if it ends
with an error of G8 that names the channel and the numbers of the missing
messages, in place of the reference result. The source of the reference
program numbers what it sends (see "External inputs" in the Contract's
limits), so that a message lost at the port it feeds ends in that error too.
What always fails is a different result with no error (a message duplicated,
lost or altered that nobody reported) and a run that never ends and reports
nothing. The chaos test runs against real `debasher_exec` runs, not mocks.

Besides it, each guarantee gets its own focused end-to-end test, written in the
guarantee's words (for the no-silent-loss guarantee: "send 5 and then 7 through
a fan-in node while a round is open: `process_data` receives both").

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

The format is JSON Lines: one JSON object per line, with `\n` as delimiter.
Always serializing via `json.dumps` guarantees that a `\n` embedded in the
`payload` comes out escaped, so the line delimiter is safe with any payload.

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
  `args.epoch`, an integer (see numbered trigger in the Glossary); a trigger
  whose epoch is not an integer is ignored with a warning.
- `CLOSE.payload.last_seq`: the sender's last `out_seq` for that channel, left
  out when the sender does not number what it sends (see `CLOSE` in the
  Glossary). Sent by a writer when it has finished for good; a halt sends
  none. The reader hands it to the brain thread in order and then drops
  whatever follows it (a `Supervisor` reader delivers it).
- `HELLO`: empty payload, sent as the first line of every incarnation of a
  writer, together with a leading blank line (see "resync line" in the
  Glossary; the transport decision of "Recovery from a node failure").
  Consumed by the reader thread.
- No `port_name` field on any type: each reader thread (see "`FBPProcess`
  class") already knows which port a message came from by construction (it is
  dedicated to that FIFO); it gets attached once the message enters the
  in-memory internal queue, not in the wire format.

## Channel topology

Which types a channel carries depends on its kind (see "Channel kinds declared
with the fifo"). `HELLO` and `CLOSE` belong to the transport, not to any kind
of channel: every writer thread of the engine sends `HELLO` when it starts and
`CLOSE` when it finishes for good, whatever its channel (a writer from outside
the program may leave both out). The other three types split by kind: `DATA`
and `BARRIER` travel only on business channels and on channels to an external
port, `INTERACT` only on the heartbeat channels and on the channels of
commands, so the two never share a channel:

- Between business processes (`FBPProcess`), the normal FBP graph channels
  carry `DATA`/`CLOSE`/`HELLO` in normal operation, and `BARRIER` interleaved
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
- From the supervisor to each initiator, a trigger port: a channel of commands
  that the supervisor owns and defines with the tag `--control`, so that the
  initiator reads it as a control port. It carries only `INTERACT`
  (`start_snapshot`, `shutdown`, see "Trigger port(s)"), never a marker, so
  the round it opens never waits on it. A `CLOSE` on it, sent when the
  supervisor stops, does not close it: a supervisor relaunched by hand writes
  its triggers there again.
- From outside the program, the other channels of commands: the manual trigger
  port of the supervisor, also tagged `--control`, whose `INTERACT` the
  supervisor relays to every trigger port (see "Manual trigger channel"), and
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
  ignored with a warning.

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
  attributes of the process (see "Limits of a node");
- opening the FIFOs, one reader thread per input port feeding the shared
  inbound queue, one writer thread per output port with its own outbound queue
  (both of them handling `HELLO` and `CLOSE`, see "Channel topology"), and the
  brain thread, whose loop each subclass supplies;
- `start_threads()` and `stop_threads()`, which start and stop all of them.

It knows nothing of rounds, checkpoints or the input log. `FBPProcess` adds all
of that on top: the heartbeat thread, the barrier logic, the dispatch of
`INTERACT` commands, the input log (a reader thread hands what it reads to
`FBPProcess`, which records it in the log before queuing it for the brain
thread), the checkpoints, and the startup sequence of `run()`, which restores
the node and replays its log.

The rest of this section starts with an overview of the class, then covers how
a node is defined, its limits and how it observes the outside world, and ends
with the pieces that make a node recoverable: state capture, startup, barrier
propagation, ordered shutdown and checkpoint persistence.

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
  `debasher_runtime_fbp.py` (`FBPProcess`) and `debasher_runtime_supervisor.py`
  (`Supervisor`, see "`Supervisor` class"). `debasher_runtime_lib.py` keeps
  `DEBASHER_SHUTDOWN_TOKEN`, a Python mirror of the Bash constant, and
  re-exports every name that it offered before, so nothing that imports it
  depends on the layout. All of them are `python_PYTHON`-installed per
  `engine/Makefile.am`, in the same directory, which is the one that the
  heredoc's `sys.path` line (see below) already adds. A test that patches a name
  has to patch the module that looks it up (for example `_write_all` in
  `debasher_runtime_inputlog`), since a patch on the re-exporting module changes
  nothing for the code that was moved.
  - A heredoc runs as `python3 -c "<text>"`
    (`debasher::_create_heredoc_func_body` in
    `engine/debasher_lib_programs.sh`), which does not go through
    `engine/Makefile.am`'s `.py:` suffix rule, the one that would otherwise
    prepend `sys.path.append("$(pythondir)")`/
    `sys.path.append("$(pkgpythondir)")`. So a Python heredoc's own text is
    itself prefixed with that same `sys.path.append(...)` call, ahead of the
    module author's code.
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
  in either list that is not an input port is refused when the node is built.
- **Threads**: one reader thread per `INPUT_PORTS` entry, each running a
  blocking `readline()` loop over its FIFO and pushing every deserialized
  envelope onto a **shared inbound queue** as `(port_name, type, payload)`; one
  writer thread per `OUTPUT_PORTS` entry, each with **its own outbound queue**
  (the brain thread enqueues `(type, payload)` there instead of writing to the
  FIFO directly, so a slow/stalled neighbor on one output port only blocks that
  port's writer thread, never the rest of the process); a single brain thread
  consuming the shared inbound queue; an independent heartbeat thread with its
  own timer.
- **Health reporting**: passive, not pushed; on its own timer, the heartbeat
  thread polls `Thread.is_alive()` on every reader/writer thread it is tracking,
  and only reports "alive" to the supervisor if all of them still are (a Python
  thread that dies from an uncaught exception does so silently, without crashing
  the process, which is exactly what `is_alive()` catches).
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
  heartbeat) with it, the natural successor to the `echo` statements
  `data/programs/debasher_cycle*.sh` use today for visibility. Level is
  configurable via a plain `-log-level` option, declared by the module author
  in `_explain_opts`/`_define_opts` exactly like any other option (same
  convention `debasher_dynamic_fanout_fifos.sh` already uses): no new engine
  mechanism, it is just another entry in `self.opts`; a sensible default
  applies if the module does not declare it.
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
heredoc of a process of a resident program. The engine only checks, without
importing anything, that the heredoc has a top-level class deriving from
`FBPProcess` or `Supervisor` (`debasher::_classify_resident_process_role`). It
never instantiates it: the heredoc itself creates the object, which parses the
options of the process from `argv`, and calls `run()`.

The class takes its ports from the engine (see "Ports from the engine") and
redefines four hooks. Each runs on a known thread, which is what lets the
framework keep the state that a node captures in step with what it has sent:

- `process_data(port_name, packet)` runs on the brain thread, once for each
  `DATA`, in the order of the input log, and on the thread that called `run()`
  while the node replays that log. It is the only place from which a node sends,
  with `send_data(port_name, payload)`, which raises anywhere else.
- `capture_node_state()` runs on the brain thread, when a round opens.
- `restore_node_state(node_state)` and `initialize_runtime()` run on the thread
  that called `run()`, before any other thread starts. They cannot send.

No hook runs when nothing arrives: a node acts only in reaction to what it
receives (see "source" in the Glossary), so whatever starts the activity of a
program is written from outside into an input port. A node that has to go on
emitting after that does it through a self-loop (see "A node that emits on its
own" in Extensions). A module that needs several inputs together keeps what it
has received in its node state and decides in `process_data` when it has
enough, because the framework delivers each message as it arrives, with no
join across ports.

A module cannot tell a replay from the first execution: `process_data` gets
the same calls, in the same order, and nothing says which of the two is
running, so that neither the node state nor what it sends can depend on it.
The one thing that has to differ, the pace of a node that emits on its own,
is in the framework: `sleep(seconds)` waits `seconds` when called from
`process_data`, does not wait while the node replays its log, where the pace
of the first execution has no use and would only delay the recovery, and
returns early once the node is told to stop, so that a stop is not delayed
either. Only when the next step comes changes.

How a node finishes for good is not defined yet: `run()` returns only on a stop
signal, and a stop sends no `CLOSE` (see "A node that finishes for good" in
Future work).

## Limits of a node

Four limits of a node (see the Glossary) are class attributes of `FBPProcess`,
with a default each, that a module can redefine in its class. A program can
also set them for one of its processes, over what the class says, in the
computational specifications that it gives to `add_debasher_process`, next to
`cpus`, `mem` and `time`:

- `input_log_max_mb` sets `INPUT_LOG_MAX_BYTES`, 100 MiB by default (see
  "Pruning and the size cap").
- `out_backlog_max_mb` sets `OUT_BACKLOG_MAX_BYTES`, 8 MiB by default (see
  "Checkpoint persistence").
- `out_backlog_fail_mb` sets `OUT_BACKLOG_FAIL_BYTES`, 64 MiB by default (see
  "Checkpoint persistence").
- `gil_switch_interval_ms` sets `GIL_SWITCH_INTERVAL_SECS`, 0.5 ms by default
  (see "Messages read from a FIFO but not yet written to the input log" in the
  Contract's limits).

For example, `add_debasher_process "relay" "cpus=1; mem=32; time=00:10:00;
out_backlog_fail_mb=128"`. Sizes are in MiB and the interval in milliseconds,
and each value, when given, must be a positive number: the engine checks it
when it loads the program (`DEBASHER_RESIDENT_COMP_SPEC_NAMES`), before
anything is launched. The built-in scheduler exports the computational
specifications of the process to it as `DEBASHER_PROCESS_COMP_SPECS`, from
the specification that the generated script carries, so a relaunch gets them
too, and `FBPProcess` sets them on its instance when it is created
(`_apply_comp_specs`); it ignores the other fields. The `Supervisor` reads
its own, `heartbeat_timeout_s` and `startup_timeout_s`, the same way. A node
can give its startup deadline too, `startup_timeout_s`, in seconds, which it
does not read itself: the engine passes it to the `Supervisor` (see "Failure
detection").

One more limit is not a specification: the open descriptors of the process
(`RLIMIT_NOFILE`). A process needs two for each of its ports, since it holds
both ends of every fifo (see "Ghost connections"), a `Supervisor` one more
for each held FIFO (see "Holding the business channels"), and a margin,
`FD_MARGIN`, for the rest. That number follows from the program, and grows
with it when a fan-in node or a `Supervisor` has as many ports as the command
line says, so nobody has to give it: before it opens anything, the process
raises its soft limit to what it needs (`_raise_fd_limit`), which it may do
up to its hard limit. When the hard limit is lower, it stops with an error
that gives both numbers, and the hard limit has to be raised for the session
that launches the program.

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
  the log is the order in which the brain thread gets the items, whatever
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
runtime library built on this: it watches a directory, `WATCH_DIR` or the
option `-watchdir` (an absolute path, or one relative to the directory of its
module), and for each file whose name matches `PATTERN` sends on
`REQUESTS_PORT` a request for a launcher node (see "`ProgramLauncher`: batch
runs from a node"), once the file is complete. A file is complete once its size
and modification time have stayed the same for `STABLE_OBSERVATIONS`
observations in a row, a file whose name starts with a dot never counts, and a
module whose files are complete in another way (a companion file, a rename at
the end of a copy) redefines `is_complete()`; `request_for()` makes the
request from the path.

## State capture and checkpoint schema

- `capture_node_state()`: only serializable logical state, never runtime
  resources (connections, sockets, file handles); those are rebuilt by
  `initialize_runtime()` instead, see the Startup sequence below.
- Channel state: a copy of the `DATA` that arrives on a still-pending port
  during an open barrier round (the generic barrier logic above) is saved as the
  checkpoint's own `channel_state` field (`_save_checkpoint`). A restore does
  not read it, and must not: on restore, only `node_state` is passed to
  `restore_node_state()`. Every message in it arrived after the capture, so the
  input log holds it above `capture_pos` and the replay processes it again;
  feeding it from `channel_state` too would process it twice. It exists for the
  two uses of a consistent cut: inspecting the state of the whole program at a
  round, where the node states alone miss the messages that were in transit (the
  introduction's second goal), and a global rollback, which discards the input
  logs above the target and has to redeliver those messages from it (see Future
  work).
- The node state is stored under `node_state`, distinct from `channel_state`;
  its hooks are `capture_node_state()` and `restore_node_state()`. There is no
  backward-compatibility code for a mismatch: a checkpoint written under
  another key fails to load with a `KeyError`, and a module that defines
  differently named hooks fails at its first round with `NotImplementedError`.
- Schema version: `CHECKPOINT_SCHEMA_VERSION` class constant, checked in
  `_load_latest_checkpoint` before `restore_node_state()`; a mismatch raises
  `ValueError`, a real incompatibility to fail on loudly, not something to
  silently paper over by trying an older checkpoint.
- The checkpoint also stores the engine's own bookkeeping: `capture_pos`,
  `closed_ports`, `out_seq`, `last_seq` and `out_backlog` (see "Input log").
  `channel_state` is a copy of what arrived on pending ports, which is also
  processed.

## Startup sequence: `run()`

There are no two distinct paths ("clean start" vs. "recovery") inside the
process; it always looks for the most recent available checkpoint; if there is
none, it starts with default values. The distinction between "first time" and
"recovery" is determined externally by whether checkpoint files exist or not,
not by a decision the process itself makes.

Single sequence, implemented exactly this way in `run()`: open every FIFO by
known name -> look for the most recent checkpoint -> (if found)
`restore_node_state()`, otherwise default values -> `initialize_runtime()`
(always invoked, same code whether or not state was restored) -> open the
input log and replay it after the checkpoint's `capture_pos`, all of it if
there was no checkpoint (see "Input log") -> `start_threads()` (starts every
worker thread) -> wait until told to stop -> stop every thread. The FIFOs
come first because a node holds a FIFO only from the moment it opens it,
and restoring and replaying can take a while: if a neighbor that was the
only holder of a FIFO crashed during that time, what it had sent would be
destroyed with it.

**Important consequence**: launching a process for the first time and
relaunching it after a failure are the same operation, with no distinction. The
supervisor does not need to know whether it is starting the topology or
recovering a downed node; in both cases it simply runs the same process script,
and it is the process itself that decides what to do depending on whether it
finds a checkpoint in its folder or not. This also simplifies "Recovery from
a node failure": no special "recovery mode" logic is needed in the
supervisor, only failure detection and running the script; the rest
(looking for a checkpoint, restoring it or not, how much of the log to
replay) is resolved by the process itself, exactly as on any startup.

**A clean start is an external operation**: it is enough to take away what a
node finds at startup, with no flag or special logic inside either the process
or the `Supervisor` to tell the case apart. That is more than the checkpoints:
with no checkpoint, a node replays the whole of its input log, and ends in the
state it had. `debasher_reset_resident` does it for the whole program (see
"`debasher_reset_resident`: a clean start").

## Chandy-Lamport barrier propagation

- A `DATA` arriving on a port whose marker has not arrived is processed at
  once, as any other, and a deep copy goes to the round's `channel_state`. A
  port whose writer has said `CLOSE` leaves the round's pending set, or is
  left out of it if it had already closed when the round opened.
- The trigger reaches a valid node as initiator via `INTERACT` (the
  already-existing interactivity/heartbeat channel), not via a new
  connection: see the `INTERACT` logic above.
- With cycles: the initiator waits for the marker to come back through its
  own input port before closing its part of the snapshot.
- Without cycles: the initiator must be a root; if it has no input ports, it
  closes its part instantly.
- Control ports are left out of every round, whoever opens it: a command is
  not the marker of the port that carries it (a round opened by a command
  starts with no port counted as arrived), the `Supervisor` takes no part in
  the barrier and never sends one, and a node with a control port must also
  close the rounds that a peer starts.
- Rounds do not overlap at a node. A marker of a newer epoch that reaches a
  node while an older round is open replaces it: the older round is
  abandoned, and the node captures again at the newer marker (a later
  capture would include messages that the sender had sent after its own, and
  holding back the port would break the order of the input log) and forwards
  the newer marker. A halt is never replaced by a snapshot, and a marker of
  an older epoch, or of a round that is over, is ignored. A trigger without
  an epoch that finds a snapshot open replaces it with a round numbered as the
  open one plus one, a number above it so that the nodes that have that round
  open replace it too; without this, an initiator whose marker was lost would
  keep its round open for ever. A trigger that finds a halt open, and any
  trigger once the node has halted, are ignored. A numbered trigger follows
  the rule of a marker instead (see numbered trigger in the Glossary).
- A round has to be able to reach every node from an initiator, or it never
  opens at the nodes it cannot reach and never closes at the nodes they write
  to. The engine checks it when the program is loaded, and refuses a program in
  which a node cannot be reached (see "Validation when the program is loaded").

## Ordered shutdown

- Same `BARRIER`, with the `halt=True` flag: see the generic barrier logic
  above and `_on_epoch_closed`'s `halt` handling.
- Closing a halt's epoch has no effect of its own (see the Glossary's "halt"):
  the node keeps running, exactly like after any other round.
  `_on_epoch_closed` only sets
  `self._halted` (blocks `_start_barrier_round` from opening a further one,
  keeping the checkpoint sequence frozen at this epoch for the rest of this
  incarnation) and writes the halted marker (`_write_halted_marker`).
- What actually ends `run()` is a stop signal, not a round closing: `run()`
  installs a `SIGTERM` handler (`_on_stop_signal`) on the main thread only
  (a background-thread caller, every test that drives `run()` this way, has
  no real signal to install one for, and `signal.signal()` raises off the
  main thread; those tests set `_stop_requested` directly instead, the same
  way other tests simulate an external `INTERACT` arriving), then waits on
  `_stop_requested` before calling `stop_threads()`. Deciding when to send
  that signal is external to `FBPProcess` by design (the
  `debasher_stop_resident` subsection has the tool that actually does):
  typically once every node's halted marker exists, but nothing here
  enforces that, or requires a halt to have happened at all.
- A halt sends no `CLOSE`, and neither does any other stop signal: `run()`
  always calls `stop_threads(close=False)`, unconditionally, once its wait
  on `_stop_requested` returns. `CLOSE` says that a writer has finished for
  good, and a node that got a stop signal, whether or not it ever halted,
  may be resumed later: had it sent `CLOSE`, the reader at the other end
  could keep it in its input log after its `capture_pos` (see "Input log"),
  and a resume would take the node for a finished one. A node that ends
  some other way (not through `run()`) still gets `stop_threads()`'s own
  default, which does send `CLOSE`.
- The signal has to reach the node's own process, not just the process group
  leader `debasher_stop` and `.id` already agree on.
  `debasher_builtin_sched::_launch` backgrounds a generated script as its own
  process group leader (`pgid == pid`, the pid in `.id`), and that script's
  own pipeline (`debasher_builtin_sched::_execute_funct_plus_postfunct`)
  forks at least one subshell of its own to run the process function, so a
  resident process's own Python interpreter sits below the pid in `.id`, not
  at it. A plain, single-pid `SIGTERM` there would only reach the wrapper
  script, orphaning the Python interpreter, which would never receive
  anything and would keep running. So a stop signal targets the whole
  process group instead (`os.killpg`, the same group `debasher_stop` already
  reaches with `SIGKILL`, see `debasher::_stop_pid`), and the wrapper script
  itself survives that same broadcast to still write `.finished` once its
  own child actually exits, which is what
  `debasher_builtin_sched::_print_script_trap` (`trap '' TERM`, the first
  thing `_create_script` writes into the generated file) is for. A hard kill
  (`SIGKILL`) cannot be trapped and is unaffected.
- Resumption: relaunch every process. It is the ordinary Startup sequence above,
  with no special case for a halt: each node loads its latest checkpoint (the
  one the halt closed, in the ordinary case where nothing else ran in this
  incarnation after it) and replays its input log after that checkpoint's
  `capture_pos`. What is replayed is what the node processed between
  capturing its state and closing the round (the messages that were in
  transit at the cut, which its checkpoint also holds as `channel_state`) and
  anything that reached its log after that. The node ends in the state it had
  when it stopped, and re-executing those messages is deterministic, like any
  other replay.
- How a program is resumed: `debasher_exec` again, on the same output
  directory. Every node stopped by the halt left a `.finished`, which for a
  general program means a process that is done and is not launched again. In
  a resident program a process is never done, so `debasher_exec` marks every
  process that is not running to be launched again
  (`debasher::_define_rerun_processes_due_to_resident_resume`), every task of
  an array included, also when only some of them have a `.finished`, as a
  hard kill of the others leaves them. Nothing in the directory of a node is
  reset on the way: not its checkpoints, its input log or its halted marker,
  in its execdir (Glossary), nor its output directory, `<outdir>/<process>`,
  which a general process has emptied every time it is launched. What a node
  keeps there is part of what it has done so far, and a launch of the node
  resumes it, whether it is a new run after a halt or the `Supervisor`'s
  relaunch after a crash.

## Checkpoint persistence

- Location: `__exec__/<process_name>/checkpoints/`, a dedicated directory (not
  loose files mixed in with
  `<process_name>.{finished,id,opts,sched_out,stdout}`, which already exist
  today under `__exec__/<process_name>/`): `_checkpoints_dir()`. A task of an
  array keeps its own, `checkpoints_<idx>/`, next to those of the other tasks
  (see execdir in the Glossary).
- Atomic write: temporary file + rename, `_save_checkpoint()`'s `os.replace`.
- Named by epoch; on startup, load the highest valid epoch:
  `_load_latest_checkpoint()`.
- Retention: keep the last few, discard the rest, `CHECKPOINT_RETENTION`
  (default 3), `_prune_old_checkpoints()`.
- Lightweight notification (epoch + path) to the supervisor (never resend the
  whole blob over the channel): `_on_epoch_closed()` sends
  `INTERACT {"command": "checkpoint_saved"}` to `SUPERVISOR_PORT` if set.
- The process always looks for the most recent checkpoint on startup; it does
  not distinguish "first time" from "recovery" by itself (see the Startup
  sequence above).
- Size of the outbound backlog in a checkpoint: over `OUT_BACKLOG_MAX_BYTES`
  (8 MiB by default), `_save_checkpoint()` writes nothing and warns. The
  previous checkpoint plus a longer replay of the input log regenerate every
  output since, so a neighbor that is slow for a while costs no more than
  rounds without a checkpoint. Nothing is pruned meanwhile, and if the input
  log reaches `INPUT_LOG_MAX_BYTES` its error names the outbound backlog and
  the epoch since which no checkpoint has been written, since the rounds
  themselves do close (`_checkpoints_skipped_since`).
- Memory of the outbound backlog: `send_data` raises, with nothing sent or
  numbered, rather than take the backlog over `OUT_BACKLOG_FAIL_BYTES` (64 MiB
  by default), and names the port. A backlog that keeps growing means a
  reader that is not reading: stopped, down or stuck, or slower than this
  node for good. The exception ends the brain thread, which the heartbeat
  reports; the `Supervisor` relaunches the node, and if the reader still does
  not read, the relaunch reaches the limit again and the node ends in
  "Escalation on a permanent node failure". The memory a node takes for its
  messages is thus bounded by this limit and by `INPUT_LOG_MAX_BYTES`, which
  also bounds what waits in its inbound queue, since every queued item is
  logged first.

# Input log

The input log is what lets a relaunched node return to the state it would
have had without the crash. A checkpoint holds the node state as it was when a
round opened; everything the node received from then on is in its input log,
and replaying the log on top of the checkpoint brings the node state up to
date. The log belongs to the node that receives, in its own execdir, since
that is the node that replays it (see "Why not built on `--mirror`, and
locality").

That use sets what the log has to guarantee:

- A message is logged when a reader thread takes it from its FIFO, not when
  the brain thread reaches it, so that what waits in the inbound queue, which
  has no limit, survives a crash of the node.
- A node has one log, not one per port, in the order in which the brain
  thread processes its items, so that a replay processes the messages of every
  port in the same order as the first execution.
- Every `DATA` reaches `process_data`, also on a port whose marker is still
  pending in an open round, where a copy of it goes into the channel state
  besides.
- A replay starts right after the item whose processing captured the node
  state, not where the round closed, so that a message processed between the
  capture and the close is not skipped; a node with no checkpoint yet replays
  its whole log.

The section first describes the log itself ("Log structure and record
format", "Arrival and positions") and what a checkpoint keeps about it ("The
checkpoint's own bookkeeping"), then how a node recovers from it ("Recovery:
startup and replay") and how it is kept small ("Pruning and the size cap").
It ends with how the log carries the end of a writer ("`CLOSE` and closed
ports") and the sequence numbers ("Sequence numbers (G5) in the input log"),
and with why it is built into `FBPProcess` rather than on the engine's fifo
taps ("Why not built on `--mirror`, and locality"). It comes right after
"`FBPProcess` class", whose startup replays the log.

## Log structure and record format

One input log per node, in `<execdir>/log/`, not one per port: everything
that arrives at a node (`DATA`, `BARRIER`, `INTERACT`, `CLOSE`) is written to
it, in the order the brain thread processes it. That order is guaranteed by
one lock, shared with pruning (see "Pruning and the size cap"), that makes
appending the record and queuing the item for the brain thread a single step.
Only `DATA` is replayed.

The log is split into segments, files named `<first pos>.log` after the
position of their first record, ordered numerically like a checkpoint's
`<epoch>.json`. A new segment starts with every incarnation of a node, never
appended to an existing one, and when the active one reaches
`INPUT_LOG_SEGMENT_BYTES` (4 MiB by default); files are created at the first
append, so there are no empty segments, and nothing rotates when a round
captures the node state, which would couple the brain thread to the readers
to save, at most, one segment of disk.

A record is one line, `{"pos": N, "port": "<port>", "env": <the envelope
line exactly as it arrived>}`. The envelope is embedded by string
concatenation, not re-encoded: building a record this way is about thirty
times faster than with `json.dumps`, for records of 100 bytes as for records
of 1 KB, at a cost of 28 more bytes per record. So the critical section that
writes it stays short, every line is still valid JSON, and a `DATA`'s `seq`
(G5) travels inside `env` with no change to the record format. Each record is
written with one `os.write` to an `O_APPEND` descriptor (looped over partial
writes), never through a buffered file object: a buffered `f.write` without
`flush` can lose acknowledged records across a `kill -9`, while `f.write` plus
`flush`, and `os.write`, do not.

A record counts only if its line ends in a newline and parses as JSON, so an
unterminated last line, a torn tail left by a process killed in the middle of
a write, is ignored on replay. A torn tail is possible at any record size,
which is why a new incarnation never appends to an existing segment, only
starts a new one: a reader thread appending behind an existing fragment
would bury it in the middle of the file, where replay rejects it, instead of
leaving it as the torn tail of its own segment. After any failed append the
log refuses more appends until the process restarts: every reader thread
dies with the same error, the heartbeat stops and the `Supervisor`
relaunches the node.

## Arrival and positions

A reader thread reads its FIFO a block at a time and hands the items it
decodes from one block, together, to `_on_arrivals(tag, items)` instead of
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
item, with no position.

Every queued item gets a position, starting at 1; `HELLO` never reaches the
queue. Whatever starts a round from inside the node, such as a snapshot timer
(see "Periodic snapshots from a node's own timer" in Future work), has to go
through the same hook, so that `capture_pos` (see the Glossary) is always
defined; 0 means that nothing had been processed yet.

## The checkpoint's own bookkeeping

Besides `node_state` and `channel_state`, a checkpoint (schema version 2)
holds the position, `capture_pos`, of the item whose processing captured the
node state, taken when the round opens, not when it closes. `closed_ports`
(the input ports whose `CLOSE` the brain thread had processed by then, see
"`CLOSE` and closed ports"), `out_seq`, `last_seq` and `out_backlog`
(the sender's and receiver's own G5 bookkeeping, see the Contract and the
"State variables, at a glance" table in the Glossary) share the same schema
version: a checkpoint of another schema version, or one missing a field this
class requires, is refused with an error.

## Recovery: startup and replay

A relaunched node's startup (`run()`, see "Startup sequence: `run()`") opens
its FIFOs, restores the latest checkpoint if there is one, calls
`restore_node_state()` and `initialize_runtime()`, opens the input log and
replays it, then starts its threads. Opening the log recovers what earlier
incarnations left: `next_pos` is `max(last complete record, capture_pos) + 1`,
found by reading only the last segment that has a complete record; a segment
with no complete record (only a torn fragment) is deleted at startup, since
the next record would reuse its position and collide with its name.

Replay re-executes `process_data()` on every `DATA` record with a position
above `capture_pos`, in log order (all of them when there is no checkpoint,
since the node state is then the default one): what had been processed
before the crash and what had arrived but not yet been processed, with no
distinction between the two. A `CLOSE` record only adds its port to
`closed_ports`; the other kinds of item are not replayed. It reads from disk
and writes nothing to the log.

Replay starts at the last segment whose name is at most `capture_pos + 1`
and fails loudly if the log starts above that, if the positions from there
on are not consecutive, if a segment does not start where the previous one
ended, or if a line that ends in a newline does not parse. A log with no
records is not an error, since it cannot be told from a log that was lost
(the sequence numbers of G5 detect that later, see the Contract). A log
whose last record is below `capture_pos` is not an error either, because
everything in it is already reflected in the checkpoint: numbering then
continues after `capture_pos`.

## Pruning and the size cap

After each checkpoint is saved, whole segments other than the active one are
deleted once the next segment starts at or below the `capture_pos` of the
oldest retained checkpoint plus one; that value is read from the oldest
retained checkpoint's own file on every round, which costs about a quarter of
writing that checkpoint, so no state is kept in memory for it. A checkpoint
that cannot be read aborts the prune with an error. Pruning runs on the brain
thread, under the same lock as an append.

`INPUT_LOG_MAX_BYTES` (100 MiB by default) is the cap on every segment of a
node's log together, kept in memory so that checking it costs nothing. It is a
safety net, not the normal way old history goes away, which is pruning:
exceeding it raises in the reader thread, before anything is written, like any
other death of a thread. Reaching it means that no epoch has closed in a long
time, so it does not trip while something triggers rounds regularly; since a
node does not start rounds on its own, a program in which nothing does
reaches it. `debasher_snapshot_resident --every` triggers them from outside
the program (see "`debasher_snapshot_resident`: rounds from outside the
program").

## `CLOSE` and closed ports

`CLOSE` means that a writer has finished for good, and only that; a halt
sends none (see "Control envelope"). A reader hands it to the brain thread
like any other item, so it is logged, and then keeps reading but drops
everything that follows: nothing after it is decoded, logged or queued, and
the first such line warns, once per port. The reader does not end on a
`CLOSE`, for two reasons: a reader that ended would leave the heartbeat
unhealthy for good once its producer finished, and a node whose peer sent
`CLOSE`, ended its reader, and was later relaunched would fill that peer's
pipe with nobody reading, since the old reader is gone. Dropping instead of
ending solves both. A control port (see the Glossary) is the exception: its
reader goes on delivering what follows a `CLOSE`, and the `CLOSE` is neither
recorded nor restored, since its writer, such as the `Supervisor`, may come
back.

`closed_ports`, sorted, is the checkpoint field that lists the input ports
whose `CLOSE` the brain thread had processed at the capture, that is, those
with a `CLOSE` record at a position at or below `capture_pos`: taken at the
same moment and on the same thread as the node state and `capture_pos`, by
the order in which the brain thread processes the items, not by what the
reader threads have already read, since they run ahead of it. Two other
definitions would not work, as a node of three ports shows: a closes before a
round opens and c closes while it is open, with a message of c in between.
Neither "what the reader threads have logged by then" nor "what is closed when
the round closes" agrees with what the checkpoint's own `capture_pos`
reflects, and both would leave the checkpoint saying that c is closed while a
message of c still lies after `capture_pos` and is due to be replayed. The
definition that is used is what lets replay demand that no `DATA` record ever
follows the `CLOSE` of its port, an error that means the log or the
checkpoint is corrupt. Recovery restores the set and adds the port of each
`CLOSE` record after `capture_pos`; the readers of the ports that are then
closed start already dropping what follows, so a relaunched node behaves like
the incarnation that read the `CLOSE`. A `CLOSE` between the capture and the
close of a round is not stored in the checkpoint file, the same as any other
item that arrives then: it is history after the cut, and recovery finds it in
the log.

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

## Sequence numbers (G5) in the input log

The mechanism itself, and the guarantee it gives (G5), are in the Contract;
what follows is specific to how the input log carries it. A `DATA`'s `seq`
travels inside its record's embedded `env`, with no change to the record
format (see "Log structure and record format"). The receiver's own
counters, `last_seq` and the reader threads' `_accepted_seq` (Glossary), are
rebuilt at startup from the checkpoint plus the log: `_accepted_seq` starts
at the checkpoint's `last_seq` and replay advances it, scanning the numbered
`DATA` after `capture_pos`, to what the reader threads had already accepted
before the crash, whether the brain had processed it or not.

What is left uncovered: the window between a reader thread taking a block
from the FIFO and the one write that logs its messages. A message lost there
is not recovered, since its sender considers it delivered, but the jump in
the sequence numbers detects it (G8).

Alternatives to logging on arrival that are not used: a bounded inbound queue
(the reader still consumes blocks of up to 64 KiB from the FIFO, unbounded); a
log at the sender with acknowledgements (would need coordination and deletion
between two processes); a second log with the order of processing (only
needed if something reorders messages, and nothing does); accepting the loss
of what waits in the inbound queue outright (it would happen exactly when a
node is busy, the worst time for it).

## Why not built on `--mirror`, and locality

Implemented entirely inside `FBPProcess` itself, in Python, not on top of the
engine's `--mirror` fifo tap: that mechanism is meant for occasional manual
debug inspection (the frontend's "Watch FIFO", `debasher_get_fifo_mirror`),
not for the load and traffic pattern a resident node's own input log needs
(back-to-back messages, no reader-side pacing). `--mirror` keeps that one
occasional debug use; nothing about it is forced on for `resident` programs,
and a `resident` program that declares `--mirror` on a fifo is rejected when
it is loaded (`debasher::_check_fifo_mirror_allowed`, called by
`define_fifo_opt` and `define_fifo_opt_generator`), so a mirror tap can never
sit between two resident processes.

The process that needs to replay a log is always the one relaunched after a
crash (itself, not its neighbor), so the log belongs on the *reader* side, in
the restarting process's own `DEBASHER_PROCESS_EXECDIR`, not the writer's.
This locality removes any need to reach into a neighbor's directory, and
removes the tap/shim mechanism from this feature entirely: no separate
process, no fifo-open/close races, nothing to force on via `--mirror`.

# `Supervisor` class

The `Supervisor` is the optional process of a resident program, at most one,
that watches its nodes and acts when one of them goes down. Every node sends it
heartbeats on a channel of its own; the `Supervisor` declares a node down when
they stop or when its process is gone, relaunches it, and, when a node keeps
failing, gives up on it and stops the rest of the program in order. It also
relays to the initiators the triggers that start a snapshot or a shutdown, and
it holds the FIFO of every business channel, so that what a channel holds
outlives the crash of both of its endpoints. A program without a `Supervisor`
still runs, and a node of it relaunched by hand still recovers; what the
program loses is the detection and relaunch, the relay of triggers and the
held FIFOs.

The `Supervisor` derives, like `FBPProcess`, from `_PortWorker` (see
"`FBPProcess` class"), which gives it the same thread-per-port plumbing: the
parsing of `argv` and the ports from the engine, the logger, one reader thread
per heartbeat channel and for the manual trigger port, one writer thread per
trigger port, and the brain thread, which here dispatches the `INTERACT`
commands that arrive. It inherits nothing of the barrier, the checkpoints or
the input log, which are in `FBPProcess` alone: the `Supervisor` takes part in
no round and keeps no state on disk, so a `Supervisor` relaunched by hand
starts afresh. Besides those threads it runs one of its own, the checker
thread, which decides on a timer which nodes are down.

The section first covers the ports of the `Supervisor` ("Port declaration and
node identity", "Trigger port(s)", "Manual trigger channel") and the FIFOs it
holds ("Holding the business channels"). It then follows a node through its
failures: how it is found down or finished ("Failure detection",
"Clean-completion detection"), relaunched ("Relaunching a downed node") and
finally given up on ("Escalation on a permanent node failure", "Failing loudly
instead of retrying"). The tool that stops a resident program gracefully,
which the `Supervisor` calls when it gives up on a node, is described with the
one that resets a program, in "Tools for resident programs".

## Port declaration and node identity

- **`NODE_PORTS`**: a dict `{node_name: option_name}`, which the engine gives
  the `Supervisor` from the options of its module, with its other ports (see
  "Ports from the engine"); a `Supervisor` built without the engine, as the
  unit tests build it, declares it in its class. A dict, and not a list of
  ports, is needed here specifically because, unlike `FBPProcess`'s barrier
  logic, which only ever needs "did this pending port's marker arrive yet, yes
  or no", treating every input port interchangeably, `Supervisor`'s detection
  and relaunch logic inherently act on a *specific node's identity*, not just
  "which port". The key is a label `Supervisor`'s own code uses internally
  (logs, detection, relaunch); the value is the option name resolved through
  `self.opts` (the same `-optname value` CLI convention) to the actual FIFO
  path opened by that node's reader thread. At startup, each
  `(node_name, option_name)` pair is resolved once; the reader thread spawned
  for it tags every message pushed to the shared inbound queue with `node_name`,
  not the raw option name, so all downstream `Supervisor` logic works purely in
  terms of node identity.
- **A node is a string or a `(process_name, task_idx)` tuple.** The key is the
  name of a non-array process, or a tuple naming one task of an array process (a
  `resident` program is not assumed to be array-free). The index is not only for
  relaunching: the engine names an array task's files
  `<process>_<idx>.id`/`<process>_<idx>.finished`
  (`debasher::_get_array_taskid_filename`,
  `debasher::_get_task_finished_filename`) instead of
  `<process>.id`/`<process>.finished`, so every per-node path used by detection
  depends on it. Malformed keys are rejected at construction.

## Trigger port(s): initiator(s) for snapshot/shutdown

- **`TRIGGER_PORT` is a list of zero or more output option names**, not a single
  scalar, each wired to a different initiator node. This covers a `resident`
  program made of multiple genuinely independent subgraphs: a single initiator
  can never reach a disjoint subgraph no matter what, so the module wires the
  `Supervisor` to one initiator per subgraph it actually needs to reach, each
  through a fifo that the `Supervisor` defines with the tag `--control`, and
  the engine lists them (see "Ports from the engine"). `Supervisor` sends
  `start_snapshot`/`shutdown` to every configured initiator when triggered
  (manually, or by `on_node_permanently_failed`, see "Escalation on a permanent
  node failure"). Empty when there
  is no such fifo: a `Supervisor` doing pure monitoring + relaunch, with no
  snapshot/shutdown-triggering capability at all, is a valid configuration.
- An initiator that receives its triggers through a trigger port has the port
  on which it reads them in `CONTROL_PORTS`, since the `Supervisor` defines
  that fifo with the tag `--control`. Without the tag the channel would be a
  data port: the round would open, the marker would go downstream and the
  initiator would wait for ever for a marker from the `Supervisor`. The tag is
  also what keeps the `CLOSE` that a `Supervisor` sends when it stops from
  closing the channel for good, so that the triggers of one relaunched by hand
  still arrive.
- This is a convenience, not the only way to trigger a round: a direct
  external `INTERACT` write into an initiator's own FIFO (e.g. via
  Talk-to-FIFOs, or `debasher_snapshot_resident`, which writes into the
  control ports of every node) remains independent of whether a `Supervisor`
  exists at all or how it is configured, and so would a snapshot timer of the
  initiator's own (not built, see "Periodic snapshots from a node's own timer"
  in Future work).

## Manual trigger channel

- **`MANUAL_TRIGGER_PORT`**: an optional single input option name, distinct from
  `NODE_PORTS` (carries no per-node identity, it is an external control channel,
  not a supervised node's heartbeat): the fifo that the `Supervisor` defines
  with the tag `--control` and that is fed from outside the program, at most
  one. Any `INTERACT` envelope arriving there is relayed to every configured
  `TRIGGER_PORT` initiator, with an epoch added to its `args` when they carry
  none (see numbered trigger in the Glossary), so that every initiator opens
  the same round; a command that starts no round never reads it. `Supervisor`
  does not validate or interpret `command`, matching the deliberately
  open-ended `INTERACT` catalog convention used everywhere else in this design
  (see "Control envelope"). Whatever ends up unrecognized is still handled
  safely at the far end, by the initiator's own `_on_interact` (logs a warning
  and ignores it, never aborts).

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

- **Which FIFOs.** The engine gives them, `HOLD_FIFOS`, with the other ports
  of the `Supervisor` (see "Ports from the engine"): every fifo without a tag
  whose two ends are nodes, the loop of a node that emits on its own and the
  channels of the tasks of an array included. The heartbeat channels and the
  triggers are left out, since the `Supervisor` already holds them as one of
  their endpoints, and so is a fifo with one end outside the program: delivery
  there is at most once in any case (see "External inputs" in the Contract's
  limits), and a holder would change what the process outside sees, whose
  `open()` would no longer wait for the node while it is down. A fifo is not an
  option of the `Supervisor`, so the engine names it by its path under the
  fifo directory of the program, `<owner process>/<fifo>`, which the
  `Supervisor` resolves against the output directory that it already finds
  from its own execdir. A fifo that is missing stops the `Supervisor` with an
  error.
- **First thing at startup.** The `Supervisor` opens the held FIFOs before its
  own ports, and before its checker thread can relaunch any node, so that a
  `Supervisor` relaunched by hand holds every channel before it recovers
  anything. A FIFO whose contents were destroyed while it was down is empty
  when it opens it again, which does no harm. A second `Supervisor` running
  at the same time, a new one while the old one hangs, is only a second holder.
- **Released when the `Supervisor` ends**, never one channel at a time. A
  node's `.finished` does not say whether it halted or finished for good, and
  both a halt and an escalation end with the `Supervisor` itself stopping.
  Holding the FIFO of a channel whose reader is gone for good costs one
  descriptor and at most what a pipe holds, and changes nothing for its writer,
  which already blocks once the pipe is full, since its own ghost end keeps the
  pipe alive (see "A node that finishes for good" in Future work).
- **When nothing is held.** While the `Supervisor` is down, which nothing
  watches (see the Contract's failure model), in a program without a
  `Supervisor`, and during a graceful stop, since `debasher_stop_resident`
  stops the `Supervisor` first (a crash during a halt is already outside the
  guarantees, see "A crash while a round is open" in the Contract's limits).
- **The switch.** Given the flag `-no_hold_fifos`, the `Supervisor` holds
  nothing and logs a warning that says what is at stake. Its module offers it
  as an option of the command line of the program, a flag like any other
  (`explain_flag`, `opt_is_non_mandatory_cmdline`,
  `define_cmdline_flag_if_given`), so that a run can choose; the chaos test
  uses it to reach the limit it would otherwise never reach. A module that
  does not offer it holds the FIFOs in every run.
- **Descriptors.** One for each held FIFO, which the `Supervisor` counts in
  the limit it raises before it opens anything (see "Limits of a node").

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

- **One dedicated checker thread, not a `threading.Timer` per node**: chosen
  specifically for scalability to hundreds or thousands of supervised nodes: a
  single thread doing O(N) cheap comparisons per wake stays flat in thread count
  regardless of N, whereas a `Timer`-per-node design means a real OS thread per
  node *and* continuous thread churn proportional to (node count x heartbeat
  frequency), since a fired-or-cancelled `Timer` instance is not reusable and
  must be recreated on every heartbeat received.
- **State per node**: `_last_heartbeat[node]` (timestamp of the last real
  heartbeat, updated only by the brain thread when it dispatches an
  `INTERACT{"command":"heartbeat"}`), guarded by a lock: read by the checker
  thread, written by the brain thread, a cross-thread hazard resolved with an
  explicit lock since two threads legitimately need to touch this state.
- **`HEARTBEAT_TIMEOUT_SECS` / `HEARTBEAT_CHECK_INTERVAL_SECS`**: the checker
  thread wakes every `HEARTBEAT_CHECK_INTERVAL_SECS` and, for each node not yet
  resolved (see "Clean-completion detection"), compares
  `now - _last_heartbeat[node]` against `HEARTBEAT_TIMEOUT_SECS`. A program
  sets the timeout of its `Supervisor` in the computational specifications of
  that process, `heartbeat_timeout_s`, in seconds, the same way as the limits
  of a node (see "Limits of a node").
- **Startup deadline**: from each launch until its first heartbeat, a node's
  silence is measured against its startup deadline instead (Glossary), kept in
  `_starting` and applied by `_silence_limit`: from its launch the node
  restores its checkpoint, runs `initialize_runtime()` and replays its input
  log before its threads start, and that can take much longer than the
  interval between two heartbeats. The first heartbeat still comes one
  `HEARTBEAT_INTERVAL_SECONDS` after the threads start, not at once: it resets
  the relaunch budget (see "Relaunching a downed node"), so it has to show
  that the node has run healthy for a while, not only that it started; sent at
  once, it would reset the budget of a node whose reader fails on the first
  live message after every relaunch, such as one past a gap in its sequence
  numbers that no relaunch can fill, and that node would be relaunched for
  ever. A node gives it in its computational specifications,
  `startup_timeout_s`, which the engine passes to the `Supervisor` in
  `NODE_STARTUP_TIMEOUT_SECS` (see "Ports from the engine"); the
  `startup_timeout_s` of the `Supervisor` itself, `STARTUP_TIMEOUT_SECS`, is
  the deadline of every node that gives none; and neither is ever shorter than
  `HEARTBEAT_TIMEOUT_SECS`, which is also the deadline when neither is given.
  A long deadline delays only the detection of a node that is alive and silent
  at startup: a node that crashes during its startup, for example on the same
  record at every replay, is declared down at once by the PID-based fast path
  below, and uses up its relaunch attempts as before.
- **Monotonic clock**: every time kept to measure the silence of a node is
  taken from the monotonic clock (`time.monotonic()`), never from the wall
  clock, which can jump forward (an NTP correction, a machine coming back from
  suspend) and make every node look silent at once.
- **A `Supervisor` that did not run for a while**: when it is starved of CPU,
  stopped or paused, the heartbeats that the nodes send meanwhile wait unread
  in its FIFOs, and when it runs again its checker thread may run before the
  threads that read them, and declare a live node down. So the checker
  measures the time since its previous tick, and when a tick comes more than
  one `HEARTBEAT_CHECK_INTERVAL_SECS` late, it moves every node's
  `_last_heartbeat` forward by as much as the tick was late
  (`_credit_own_stall`): the time the `Supervisor` did not run is not counted
  against any node. A node whose process is gone is still declared down at
  once, by the PID-based fast path below, which does not depend on elapsed
  time.
- **PID-based fast path**: every BUILTIN-scheduler process gets a `.id` file
  holding its PID (written by `debasher_builtin_sched::_launch`, for every
  process, not only resident ones), at `__exec__/<node>/<node>.id`. If
  that PID no longer exists (checked directly, no need to wait for the heartbeat
  timeout) and `<node>.finished` is absent, the node is declared down
  immediately: a gone PID is unambiguous, whereas a live PID proves nothing
  about whether the node is actually *functioning* (a stuck/deadlocked process
  still holds its PID). So PID-dead is a fast, certain shortcut to "down";
  heartbeat timeout remains the only judge of "alive but not really working";
  PID-alive is never, by itself, treated as "healthy".
- **No new `.failed` marker file.** A deliberate application-level error exit
  and a real crash already leave the same signature (no `.finished`, eventually
  no heartbeat, dead PID) and are treated identically. No behavioral difference
  is needed between the two. If a future need arises to tell them apart, the
  better mechanism is the process itself sending a richer `INTERACT` before it
  exits (still alive at that point, knows why), not a new engine-level boolean
  file written by the wrapper script after the fact.

## Clean-completion detection (and the `Supervisor`'s own shutdown)

- **The checker thread also checks `<node>.finished`, every tick, for every node
  not yet resolved**: cheap (one `os.path.exists()` per node per tick, same cost
  class as the heartbeat comparison), and checked unconditionally rather than
  only as a tie-break right before declaring a heartbeat timeout, specifically
  so a node's clean completion is noticed within one
  `HEARTBEAT_CHECK_INTERVAL_SECS`, not delayed by up to a full
  `HEARTBEAT_TIMEOUT_SECS`.
- `debasher::_signal_process_completion` (`engine/debasher_lib_sched_procs.sh`),
  which writes `.finished`, is only ever reached from
  `_execute_funct_plus_postfunct`'s success branch: a non-zero exit code returns
  before it. So `.finished` reliably means "exited cleanly, code 0".
- Once `.finished` is seen for a node, it moves to a **"done"** state,
  permanently excluded from further heartbeat/PID checks and never again a
  candidate for `on_node_down`. This is what keeps an intentional ordered
  shutdown from ever looking like a crash: a node that stopped on purpose simply
  stops sending heartbeats *and* leaves `.finished` behind, the two together are
  what distinguish it from a real failure.
- **Once every node in `NODE_PORTS` is "done", `Supervisor` stops its own
  threads and exits.** This answers "who tells the `Supervisor` to stop":
  nothing external needs to signal it explicitly, it infers whole-program
  completion from the same state it already tracks for every other purpose.
- **`Supervisor` also stops on a stop signal**, like `FBPProcess` (see
  "Ordered shutdown"): `run()` installs a `SIGTERM` handler on the main thread
  (same reasoning, and same off-main-thread exception for tests driving
  `run()` on a background thread), whose handler just sets `_all_resolved`
  directly. Unlike `FBPProcess`, nothing here needs to tell "resolved
  naturally" apart from "told to stop", so the one event that `run()`'s own
  `_all_resolved.wait()` waits on covers both. This exists so that a
  graceful-stop tool that finds a `Supervisor` present can end it first,
  deliberately, before touching any node it watches, so that it cannot
  relaunch one out from under the rest of what that tool does (see
  "`debasher_stop_resident`").

## Relaunching a downed node

- **`on_node_down(node_name)` is a hook with a concrete default
  implementation**, not a pure `NotImplementedError` abstract method like
  `FBPProcess.process_data`/etc. Unlike those, there *is* one universal, correct
  default action here, since every `resident` process is relaunched the exact
  same mechanical way. Overridable, for a module author who needs something
  non-standard.
- **The default relaunches through an installed tool,
  `debasher_launch_process -d <outdir> -p <process> [-t <idx>]`**
  (`engine/debasher_launch_process.sh`, installed in `libexec`), which calls the
  built-in scheduler's own `debasher_builtin_sched::_launch`. The tool takes the
  program's output directory (not the process's) and, for an array task, the
  index; without `-t` it passes `NO_ARRAY_TASK`. Relaunching is therefore the
  same code path as the original launch, as "Startup sequence: `run()`"
  requires: launching a node for the first time and relaunching it after a
  failure are the same operation.
- **Why not simply re-execute `__exec__/<node>/<node>`?** That generated
  script does not carry the per-launch state. `BUILTIN_ARRAY_TASK_ID` is
  exported by `_launch` just before it starts the script, and is not among
  the variables dumped into the script itself (that dump is a deliberate
  allowlist, and it runs once per process at generation time, while this
  value is per launch), and the `.id` file is written by `_launch`, not by
  the script. A bare `subprocess.Popen` from the Supervisor would inherit
  the Supervisor's own `BUILTIN_ARRAY_TASK_ID` instead, and the relaunched
  node's `.id` would never be updated: a stale PID that `_node_pid_alive`
  reports "dead" forever, and since a real heartbeat resets
  `_relaunch_attempts` on every recovery, the budget never trips, an
  endless relaunch loop. It would also leave the node in the Supervisor's
  own process group, which `debasher_stop` (`kill -9 -- -$pid`) relies on
  being one per process. `_launch` avoids all of it, since it writes the
  `.id` itself and its explicit export overrides whatever the caller
  inherited.
- **What `_launch` does for this** (`engine/debasher_builtin_sched_lib.sh`):
  it writes the new process's PID into the `.id` itself, as soon as the
  process starts and without waiting for it, through a temporary file
  renamed into place, so that a reader sees either the old PID or the new
  one, never an empty file; it exports `DEBASHER_LIBEXECDIR` so a
  running process can find the installed tools (`debasher_libexecdir` is
  deliberately excluded from what generated scripts carry); and it unsets
  `BUILTIN_ARRAY_TASK_ID` before a non-array launch.
- The launcher runs without blocking the checker thread; a short-lived
  thread reaps it and logs a non-zero exit.
- **`MAX_RELAUNCH_ATTEMPTS` per node**: a plain counter, incremented each time
  `on_node_down` actually fires for that node, **reset to 0 on that node's next
  real heartbeat** (proof of actual recovery, not just that its PID exists
  again, consistent with "PID-alive proves nothing about health" in "Failure
  detection": the first heartbeat goes out one interval after the startup,
  restore and replay included, is over). This distinguishes a node that keeps
  crashing during its startup, or right after it, after every relaunch
  (counter climbs, never resets, eventually exhausts the budget) from one that
  crashes rarely over a very long run and always recovers cleanly each time
  (counter keeps resetting, never exhausted just by accumulating spaced-out
  incidents).
- Exceeding the limit calls **`on_node_permanently_failed(node_name)`** instead
  of relaunching again; that node moves to its own terminal "given up" state
  (distinct from "done"), never automatically retried again.
- **The relaunch subprocess also has to leave `stdout`/`stderr` alone, not
  just `stdin`.** `on_node_down`'s `subprocess.Popen` redirects `stdin`, and
  also redirects `stdout`/`stderr` to `DEVNULL`: left alone, they would be
  inherited from the Supervisor's own process, which its own launch script
  pipes into `tee` (`debasher_builtin_sched::_execute_funct_plus_postfunct`).
  `debasher_launch_process`, and in turn the resident process it
  backgrounds, would inherit that same pipe, and hold its write end open for
  as long as the relaunched node keeps running, long after the Supervisor's
  own Python interpreter has actually exited: `tee` would never see `EOF`,
  so the Supervisor's own wrapper script would never get past its own `wait`
  for that pipeline, and `sup.finished` would never appear. `debasher_stop`'s
  hard kill never surfaces this (it always kills the relaunched node too,
  which closes the leaked fd as a side effect); a graceful stop signal (see
  "`debasher_stop_resident`") does not.

## Escalation on a permanent node failure

A node given up on for good can, in the worst case, have been the only path (in
the business-data graph) to some other node(s); if so, no ordered shutdown can
ever reach them through the graph itself, since the barrier marker only ever
propagates along the same edges as `DATA` (see "Channel topology"). Rather than
build a second, parallel broadcast mechanism (a direct connection from
`Supervisor` to every node, bypassing the graph, with a barrier-skipping
command), which would mean N extra FIFOs to wire per program, and would put
every ordinary shutdown at risk of losing the barrier's consistency guarantees,
not just the pathological case, `on_node_permanently_failed`'s default
implementation calls **`debasher_stop_resident`** (see
"`debasher_stop_resident`") as a subprocess, `-x <node_name>` excluding the
node just given up on and `--keep-supervisor` set: the tool gracefully halts
and stops whatever part of the graph remains reachable, and falls back on its
own, past its own `--timeout` (`FORCE_STOP_TIMEOUT_SECS`), to
`debasher_stop -d <dirname>`, the engine's general stop tool
(`engine/debasher_stop.sh`), which walks every process of the program and
sends `kill -9 -- "-$pid"` (a process-group `SIGKILL`) to any still
`INPROGRESS`, regardless of the graph's connectivity. So
`on_node_permanently_failed` itself does not reimplement any of that sequence
by hand.

`dirname` (the program's own base output directory, not a process's own exec
dir) is `dirname(dirname(DEBASHER_PROCESS_EXECDIR))`
(`debasher::get_prg_exec_dir_given_basedir`,
`<dirname>/__exec__/<processname>`), so no export of the engine has to carry
it. The tool's own absolute path comes from `DEBASHER_BINDIR`, which
`debasher_builtin_sched::_launch` (`engine/debasher_builtin_sched_lib.sh`)
exports next to `DEBASHER_LIBEXECDIR`, the one that
`_launch_process_command` uses to find `debasher_launch_process`.

This deliberately accepts an asymmetry: the graceful phase preserves every
checkpoint/input-log consistency guarantee already built; the hard-kill fallback
is explicitly a "just end it" backstop, expected to only ever fire in the
pathological case of a graph broken by a permanent node failure, and is allowed
to lose in-flight state for whatever it kills.

**`--keep-supervisor` is not optional for this caller.** This call runs on a
thread of the same `Supervisor` process it is about to ask the tool to act on
`Supervisor`'s own program. Without it, the tool's own first step
(`stop_supervisor_if_any`) would target this same process's group, and this
call would never actually get anywhere (`engine/debasher_stop_resident.sh`).
Two other ways to avoid this were ruled out: running the tool in a detached
process group (`setsid`) does not help, since the tool's own step still
targets `Supervisor`'s *original* process group by pid, which the
`Supervisor` process itself never leaves, so it would still stop itself
prematurely, before the reachable nodes it is meant to supervise while this
runs are actually done; and stopping it last instead of first (after the
reachable nodes, still inside the same tool call) does not help either, since
the call is blocked on a thread of the `Supervisor` process itself, so a last
step that signals `Supervisor` and waits for its `.finished` waits on
something that cannot happen until that same blocked thread returns, which
cannot happen until this wait does. Leaving `Supervisor` alone entirely,
letting it resolve itself once the reachable nodes are done (already true
regardless, see "Clean-completion detection"), avoids both. Left alone by
`--keep-supervisor`, `Supervisor` still ends, on its own, the same way it
always does once every node it watches is done or given up on: nothing here
has to signal it, or even knows when that will be.

## Failing loudly instead of retrying

The Contract's limits include a gap that stays open (see "A crash while a round
is open" there): a node that is not an initiator and crashes while its halt
round is open comes back with no durable memory of that round, the markers it
had received for it are not replayed, and nothing resends the one-time
`shutdown` trigger, so it never halts. `debasher_stop_resident`'s own
`--timeout` already keeps this from hanging the program forever, structurally,
but falling back to `debasher_stop`'s hard kill silently would let that forced
ending pass for a graceful one, so it does so loudly instead, without attempting
to fix the underlying gap.

The alternative, making the gap itself durably recoverable (a checkpoint
field recording a pending, unclosed halt, restored and acted on at recovery),
has two holes: first, checkpoints are only ever taken when a round *opens*,
never when it *closes* (the moment of `capture_pos`, see "capture position" in
the Glossary), so nothing would ever clear that field once the round
legitimately closed, and a later, unrelated crash would then re-open a halt
round that had already finished cleanly; second, the same forgetting affects
every node on the barrier's propagation path, not just an initiator, so
closing it for real means making a round's *partial* progress (which peers
already closed their own part) durable and reconstructible, not just "a halt
was requested", a materially larger change to the Chandy-Lamport mechanism.
Failing loudly instead accepts the asymmetry already accepted in "Escalation
on a permanent node failure" (the hard-kill fallback's own "just end it"
backstop): it does not make this case end gracefully, but it makes sure nobody
mistakes the forced ending for one, at the cost of no change at all to the
barrier or checkpoint mechanism.

**Mechanism**: `debasher_stop_resident` returns a distinct exit code,
`DEBASHER_STOP_RESIDENT_FORCED_EXIT` (2), whenever it falls back to
`debasher_stop`, instead of propagating `debasher_stop`'s own exit code
(typically 0, since it does not treat "something was still running to kill"
as a failure): the one signal that survives a caller that redirects the
tool's own stderr, such as `Supervisor`'s own escalation
(`_escalate_shutdown`, `engine/debasher_runtime_supervisor.py`), which
recognizes this specific code and logs its own, more specific error (G8,
detected, never silent), durably captured in `sup.sched_out` the same way
every other `Supervisor` log line already is, rather than only the tool's
own stderr line, which that redirect would otherwise have thrown away
entirely (the same reasoning as `on_node_down`'s own `DEVNULL` redirect, see
"Relaunching a downed node").

# Tools for resident programs

A resident program does not end on its own: its nodes run until they are told
to stop, and they keep their state across runs, in checkpoints, input logs and
halted markers that the engine's general tools know nothing about. Three
tools, installed in `bin` next to `debasher_exec` and `debasher_stop`, act on
such a program as a whole, from outside it. `debasher_stop_resident` stops a
running program gracefully: it halts it in one round, so that every node can
later resume where it stopped, where `debasher_stop` would kill every process
at once. `debasher_snapshot_resident` starts a snapshot in a running program,
once or periodically, so that its nodes write checkpoints and prune their
input logs whether the program has a `Supervisor` or not.
`debasher_reset_resident` takes a stopped program back to its first run: it
sets aside, or deletes, the state that its nodes keep, so that the next
`debasher_exec` starts every node afresh. The `Supervisor` also uses the first
one, to stop what remains of a program once it gives up on a node (see
"Escalation on a permanent node failure"). The first two share what they need
to find the nodes of a program and to write a trigger into their control
ports (`engine/debasher_lib_resident_tools.sh`).

## `debasher_stop_resident`: the graceful stop tool

The graceful counterpart to `debasher_stop`, for a resident program
specifically: it halts the program in an ordered way (see "Ordered shutdown")
and then stops its processes. It relies on the `Supervisor` stopping on a stop
signal (see "Clean-completion detection").

- **Usage: `debasher_stop_resident -d <outdir> [-x <name>[,<name>...]]
  [--timeout <secs>] [--keep-supervisor]`.** `-d` is the program's own output
  directory, same as every other engine tool that operates on one. `-x` names
  nodes to leave alone entirely (not waited for, not signalled), each a process
  name (every task, if it is an array) or `<process_name>:<idx>` (one task of an
  array; `<process_name>_<idx>` would be ambiguous with a process whose name
  ends that way): for `on_node_permanently_failed`'s own use (see "Escalation
  on a permanent node failure"), which must not wait forever on a node it has
  already given up on.
  `--timeout` (default 60, the same as `FORCE_STOP_TIMEOUT_SECS`) bounds the
  whole graceful attempt; past it, falls back to `debasher_stop -d <outdir>`
  (a hard kill of the entire program), so this always ends the program one
  way or another, never hangs indefinitely by itself.
  `--keep-supervisor` skips stopping the program's `Supervisor` (step 1 of the
  sequence below), also for `on_node_permanently_failed`'s own use: it calls
  this tool from a thread of the very `Supervisor` process it would otherwise
  target (see "Escalation on a permanent node failure" for why that
  specifically must not happen, not just should not).
- **Finds the program's nodes and its `Supervisor` (if any) the same way
  `debasher::_validate_resident_program_processes` does**: loads the module,
  iterates `DEBASHER_PROGRAM_PROCESSES`, and classifies each with
  `debasher::_classify_resident_process_role`. An array process is one node
  per task, as a `Supervisor`'s `NODE_PORTS` names it, and as many as the
  `DEBASHER_NUM_TASKS` line of the script that the scheduler wrote for the
  process before launching any task, so that a task not started yet is
  counted too. Every step below reads a task's
  own files: its `.id` and `.finished` (`debasher::_get_array_taskid_filename`,
  `debasher::_get_task_finished_filename`), its halted marker and its control
  ports file (see execdir in the Glossary). The `Supervisor`'s escalation names
  the one task it gave up on, so that the other tasks of the same array are
  still stopped.
- **Sequence:**
  1. If the program has a `Supervisor` and `--keep-supervisor` was not given,
     stop it first (a stop signal to its whole process group, as described
     below) and wait for its own `.finished`, before touching any node it
     watches: this is why the `Supervisor` stops on a stop signal of its own
     (see "Clean-completion detection"), and it is what keeps this tool from
     racing a relaunch it did not ask for.
  2. Record each node's halted marker as it stands right now (its content,
     or `-1` if absent): the baseline a fresh one has to beat.
  3. Write `shutdown` into every node's own control ports (listed in its
     control ports file, see the Glossary; most nodes have none, and the round
     reaches them from elsewhere in the graph), numbered with the time in
     milliseconds (see numbered trigger in the Glossary), so that every
     initiator halts in the same round.
  4. Wait for every node's halted marker to go past its own baseline (never
     "exists": a node halted from a previous, already-resumed cycle would
     already show one that means nothing about this run).
  5. Re-read every node's `.id` (not reusing what step 1 or discovery
     already saw) and send each a stop signal.
  6. Wait for every node's own `.finished`.
- **A stop signal is `SIGTERM` to the whole process group (`kill -TERM --
  "-$pid"`, `debasher::_stop_pid_gracefully`, the `SIGTERM` sibling of
  `debasher::_stop_pid`'s `SIGKILL`), never a lone pid.**
  `debasher_builtin_sched::_launch` backgrounds a generated script as its own
  process group leader (the pid in `.id`), but that script's own pipeline
  (`debasher_builtin_sched::_execute_funct_plus_postfunct`) forks at least
  one subshell to run the process function, so a resident process's own
  Python interpreter sits below that pid, not at it. A single-pid `SIGTERM`
  would only reach the wrapper script, which has no handler of its own and
  would die at once, orphaning the interpreter, which would never receive
  anything and would run forever. So the signal always targets the whole
  group, and the wrapper script itself ignores `SIGTERM` at its own top
  level (`debasher_builtin_sched::_print_script_trap`, `trap '' TERM`, the
  first thing `_create_script` writes into the generated file) so it
  survives that same broadcast long enough to still write `.finished` once
  its own child (the Python interpreter, or a stopped `Supervisor`)
  actually exits. `SIGKILL`, used by `debasher_stop`'s hard kill, cannot be
  trapped and is unaffected by any of this.

## `debasher_snapshot_resident`: rounds from outside the program

`debasher_snapshot_resident -d <outdir> [--timeout <secs> | --every <secs>]`
(`engine/debasher_snapshot_resident.sh`, installed in `bin`) starts a snapshot
in a running resident program. A node never starts a round on its own, and the
`Supervisor` starts a snapshot only when a trigger reaches its manual trigger
channel, so without this tool, or someone else writing triggers, a program
closes no epoch, prunes nothing and ends at the size cap of its input logs
(see "Pruning and the size cap").

- **One round.** It writes `start_snapshot` into the control ports of every
  node, as `debasher_stop_resident` writes `shutdown`, numbered with the time
  in milliseconds (see numbered trigger in the Glossary), so that every
  initiator opens the same round. With a `Supervisor`, the control port of an
  initiator is a trigger port, and the tool writes into it next to the
  `Supervisor`: a line of a trigger is shorter than `PIPE_BUF`, so the two
  never interleave. Without one, it is a fifo fed from outside. Every node of
  a program that loads is reached from an initiator (see "Validation when the
  program is loaded"), so the tool needs nothing else to reach every node.
- **Waiting for the round to close.** It then waits, up to `--timeout`
  seconds (60 by default), until every node has a checkpoint of that epoch or
  of a newer one: a newer round replaces an open one, and its cut is as recent
  a point to recover from. It prints the epoch and returns 0 once every node
  has one. Otherwise it names the nodes that have none and returns 2
  (`DEBASHER_SNAPSHOT_RESIDENT_NOT_CLOSED_EXIT`), not 1, which is kept for
  usage and setup errors. A round does not close at a node that is down or
  stopped, nor at one that has halted or has a halt open, which ignores a
  snapshot. It does not start when a trigger cannot be written within 5
  seconds (a control port fed from outside whose node is down has no reader).
  And a node closes it without a checkpoint when its outbound backlog is over
  its cap (see "Checkpoint persistence").
- **Periodically.** With `--every <secs>`, it starts a round every that many
  seconds, and each round has until the next one to close: one that has not
  closed by then is reported with a warning, and the next trigger replaces
  it. The period has to be longer than a round, or rounds keep replacing each
  other (see "A round that a newer one replaces" in the Contract's limits).
  `--timeout` does not apply, and giving both is an error.
- **Only a running program, and it ends with it.** It refuses a program none
  of whose nodes is running. With `--every`, it checks every second whether
  some node still is, and returns 0 once none is, after
  `debasher_stop_resident`, a `Supervisor`'s escalation or `debasher_stop`.
  It is a process outside the program: nothing relaunches it, and a program
  that is resumed needs it started again.

## `debasher_reset_resident`: a clean start

`debasher_reset_resident -d <outdir> [--delete]`
(`engine/debasher_reset_resident.sh`, installed in `bin`) resets a stopped
resident program, so that the next `debasher_exec` on the same output
directory starts every node as on its first run. A node keeps its state across
runs in files that the engine does not reset (see "Ordered shutdown"): its
checkpoints, its input log and its halted marker, in its execdir (Glossary),
and the output directory of its process. The tool takes all of them away, for
every task of every process, the `Supervisor` included, and leaves the output
directory of each process empty, as the engine leaves it before a first run.

- **The whole program, never one node.** A node that starts afresh numbers
  its channels from the start again (G5), and a reader that kept its own
  checkpoint would drop everything it sends as duplicates, having accepted
  higher numbers before. Resetting a node would mean resetting its readers,
  and theirs in turn.
- **Set aside by default.** What it takes away is moved under
  `__reset__/<timestamp>/` in the program's output directory, each path kept
  relative to it (`__reset__/<timestamp>/__exec__/<process>/checkpoints`,
  `__reset__/<timestamp>/<process>/...`), since a checkpoint that is lost
  cannot be made again. `--delete` deletes it instead.
- **Only a stopped program.** It refuses while any process of the program is
  running, as `debasher_exec` does.
- **What it does not reach**: the files that a module writes outside the
  output directory of its process.

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
input option to an output option of another process. Every FIFO of a program
is created once, by the `define_fifo_opt` (or `define_fifo_opt_generator`) of
one process, its fifo owner, through an output option: the owner writes it.
The process at the other end reads it, through an input option connected to
that output, or no process of the program does, and the other end is outside
(`__EXTERNAL__` in the engine's fifo registry). The one exception is a fifo
whose writer is outside the program: the process that reads it has to create
it, through an input option, and the fifo carries a fifo tag. The engine's
registries (`DEBASHER_PROGRAM_FIFOS` and `DEBASHER_FIFO_USERS`, written to
`program.fifos`) give the owner and the other end of every fifo, task by task,
and the other end may be another task of the owner's own array; the option
through which the owner defines each fifo is recorded too
(`DEBASHER_FIFO_OWNER_OPTS`). The direction of every channel follows from them
and from the tags, with nothing read from Python.

## Tags: `--control` and `--external`

`define_fifo_opt` and `define_fifo_opt_generator` take an optional tag, the same
way as `--mirror`, stored in a registry of its own:

- no tag: a business channel, written by its owner and read by the process at
  the other end, whose end is an input port;
- `--control`: a channel of commands, whose reader's end is a control port. Its
  writer is the `Supervisor`, which owns it (a trigger port), or someone outside
  the program, and then the reader owns it;
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
the business channels between the business nodes, task by task (the
`Supervisor` takes no part in rounds, so its channels are left out), and checks
it before launching anything, in `debasher::_validate_program_fifo_kinds`,
which `debasher_exec` calls once the other end of every fifo is known:

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

A fifo without a tag whose other end is outside is a business channel from its
owner to someone outside the program, a node that writes its results out.

A violation stops the load with an error that names the node or the fifo, and
the rule. The check walks the fifos once; the registries it reads are already
built by then, for every task of every array and generator. In the fan-in of
two nodes fed from outside (see "Initiators numbered their rounds independently"
in "Loose ends"), a program in which only `a` has a control channel is refused
by rule 1, since `b` cannot be reached.

## Ports from the engine

Once the program is loaded and its channels are checked, the engine gives
each task of an `FBPProcess`, and the `Supervisor`, its ports, taken from the
same registries and tags (`debasher::_register_resident_task_ports`). For a
node:

- The owner of a fifo has an output port on the option through which it
  defines it, or, for a tagged fifo fed from outside, an input port, which is
  also a control or an external port, as its tag says.
- The process at the other end, when it is a node, has an input port on the
  option through which it uses the fifo (`DEBASHER_FIFO_USER_OPTS`), which is
  also a control port if the fifo is tagged `--control`.
- The output port whose other end is the `Supervisor` is the node's
  `SUPERVISOR_PORT`. A node with more than one is refused when the program is
  loaded, since a node has a single heartbeat channel.

For the `Supervisor`, the same fifos seen from its end:

- A fifo without a tag that a node defines and the `Supervisor` reads is the
  heartbeat channel of that node: an entry of `NODE_PORTS`, the node as its
  key and the option through which the `Supervisor` reads it as its value.
- A fifo that the `Supervisor` defines with the tag `--control` and a node
  reads is a trigger port, an entry of `TRIGGER_PORT`.
- A fifo that the `Supervisor` defines with the tag `--control` and that is
  fed from outside the program is its `MANUAL_TRIGGER_PORT`. A `Supervisor`
  with more than one is refused when the program is loaded.
- Any other fifo that the `Supervisor` defines is refused when the program is
  loaded: the `Supervisor` takes no part in the business channels.
- A fifo without a tag whose two ends are nodes is a business channel, whose
  FIFO the `Supervisor` holds (see "Holding the business channels"): an entry
  of `HOLD_FIFOS`, named by its path under the fifo directory of the program,
  `<owner process>/<fifo>`, since it is not an option of the `Supervisor`.

With them goes the startup deadline of each node whose computational
specifications give one, `startup_timeout_s`, into
`NODE_STARTUP_TIMEOUT_SECS` (see "Failure detection").

So the heartbeat channels need no tag of their own: the role of the process
at each end, which the engine already knows, says which fifo is which. With
the options of the module as the only place that says what the ports are, a
program whose number of nodes comes from the command line (see "Fan-out and
fan-in sized from the command line" in Extensions) has a `Supervisor` that
watches as many nodes as there are, with no code that depends on it.

The generated script of each process carries the ports of every task
(`DEBASHER_RESIDENT_TASK_PORTS`), so that a relaunch gets them too, and the
wrapper of a task exports its own as `DEBASHER_PROCESS_PORTS`. For `fanin`, in
the chaos reference program:

```
input=ext,loop_in,trigger;output=outhb,outloop,outsink;control=trigger;external=ext;supervisor=outhb
```

and for its `Supervisor`, `sup`, where a task of an array would be named
`<process>:<idx>`, as `debasher_stop_resident -x` names it:

```
nodes=fanin=hb_fanin,loop=hb_loop,sink=hb_sink;trigger=outtrig_fanin;manual_trigger=manual;startup=;hold=fanin/fanin_to_loop,fanin/fanin_to_sink,loop/loop_to_fanin
```

`FBPProcess` sets `INPUT_PORTS`, `OUTPUT_PORTS`, `CONTROL_PORTS`,
`EXTERNAL_PORTS` and `SUPERVISOR_PORT` on the instance from it, and the
`Supervisor` `NODE_PORTS`, `TRIGGER_PORT`, `MANUAL_TRIGGER_PORT`,
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
  `Supervisor` whose `TRIGGER_PORT` lists them or someone outside the program.
- A node cut off at run time, by a node that fails for good, is a separate case,
  handled by "Escalation on a permanent node failure".
- Reading and writing the tags in the frontend is part of "Resident programs in
  the frontend" in Future work.

# Recovery from a node failure

A node that crashes is relaunched while the rest of the program keeps running,
and it has to get back both its state and its connections. Its state comes
back from its checkpoint and its input log (see "Input log"). This section is
about its connections: how the nodes that keep running reconnect with a peer
that crashed and is relaunched, in both directions of a channel, without
losing what the channel held.

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

Restarting the whole program, with a new `debasher_exec` against the same
output directory, needs none of this: the engine recreates every FIFO, and
every node opens them anew. The crash of one node while its neighbors keep
running is different. With plain FIFO endpoints (a reader that opens its FIFO
once and reads until EOF, a writer that opens it once and writes), the reader
of the crashed node's output sees EOF and ends, never to reopen; a writer to
the crashed node gets `BrokenPipeError` and its thread dies; and the
relaunched node blocks for ever in `open()`, with nobody left at the other
end. It would talk to the `Supervisor` again but be cut off from every peer,
and the first goal of the introduction would hold only for a node whose sole
connection is the `Supervisor`.

Reconnecting also needs every endpoint to know what the `Supervisor` learns
from `.finished`: whether a peer's silence means "crashed, will return" or
"finished on purpose". The rest of this section is that signal and its
consequences.

## `CLOSE`: telling a finished peer from a crashed one

A process keeps its FIFOs open for its whole life (opens them as it starts,
holds them until `_STOP`), so a reader cannot tell a clean close from a
crash from EOF alone: the EOF is identical for a normal exit and for
`SIGKILL`. `CLOSE` is an envelope type of its own (see "Control envelope"),
decentralized (it works without a `Supervisor`, which is optional, and for a
manual relaunch too), sent by the writer in band when it has finished for
good; a halt sends none (see "Ordered shutdown"). The idea mirrors FIN versus
RST in TCP: a `CLOSE` means "finished, do not wait"; its absence means "may
still return".

The reader hands `CLOSE` to the brain thread in order, like any other item,
so it is logged and its port can leave the barrier's pending set. Why the
reader then keeps reading and drops what follows instead of ending, and what
`closed_ports` records, is in "`CLOSE` and closed ports".

A process that exits with an error (an exception, a non-zero exit) sends no
`CLOSE` and is treated as a crash, consistent with the `Supervisor`'s own
detection; a `CLOSE` followed by a later failure is harmless, since peers keep
reading and drop whatever the relaunched node sends afterward (see "`CLOSE`
and closed ports"). The `Supervisor`'s own channel does not need `CLOSE`: it
keeps using the node's `.finished` file, since a `CLOSE` does not prove the
node succeeded, and a node that closed and then failed must still be heard
again when relaunched.

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

With no EOF the reader never ends on its own: it ends only on a stop
request, woken through a blank line written to its own ghost write end even
if it is blocked in `read()`. The writer never sees `EPIPE` either: a dead
peer means backpressure instead, the writer blocks once the pipe holds 64
KiB, and since a blocked writer cannot be woken, `stop_threads()` joins
writer threads with a bounded timeout.

`Supervisor` learns that a node finished only from its `.finished` file, and
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
followed by a `HELLO` line (an envelope type of its own, consumed by the
reader thread, see "Control envelope"). A reader that finds one unparsable
line tolerates it if the next line is `HELLO`, and drops it; in any other case
it is an error, so a corrupt line is never skipped silently. There is no limit
on message size. Only the framework writes to these channels: an external
writer must send complete lines, and a fragment from one shows up as an
error. `HELLO` also tells the reader that its peer (re)connected.

## Opening the FIFOs first in recovery

A relaunched node opens its FIFOs before restoring its checkpoint or
replaying its input log (`run()`'s first step, `_open_fifos()`, which
`start_threads()` also calls for the ports that are not open yet, so that a
node driven without `run()` opens them too). Opening them only later, in
`start_threads()`, would put the time spent recovering inside the window in
which the crash of a neighbor could destroy what the neighbor had sent it
(this is about the channel, not the log; "Input log" covers what a node keeps
of its own history). What remains of the window is the time to notice the
crash (`HEARTBEAT_CHECK_INTERVAL_SECS` when the process is gone) and to start
the new process.

## The reader-dies direction

Ghost connections answer the crash of a reader: the writer never sees
`BrokenPipeError` (it blocks on backpressure instead, so there is nothing to
reopen or resend), and unread data in the pipe survives a reader's crash and
relaunch (see "Ghost connections").

`CLOSE` travels only in the direction the data does, from a writer to its
readers, so a node that stops reading from one of its inputs sends nothing
back to whatever writes to it. A writer therefore cannot tell a reader that
stopped for good from one that crashed and may relaunch: both look the same,
the writer just blocks once the pipe fills, and its outbound backlog grows
until `OUT_BACKLOG_FAIL_BYTES` stops it with an error that names the port (see
"Checkpoint persistence"). A signal in the other direction, symmetric to
`CLOSE`, is in Future work.

# `ProgramLauncher`: batch runs from a node

A resident program processes a stream of messages; a general program processes
a batch of inputs and ends. A launcher node joins the two: every request it
receives launches the same general program with the options of the request, in
a run directory of its own. A bioinformatics system is the case in view: a BAM
file arrives, and the pipeline that analyses it runs once for it, while other
files keep arriving; when one analysis ends, a node downstream learns it, and
can go on with its results.

## A node that launches a general program

`ProgramLauncher` is a subclass of `FBPProcess` in the runtime library
(`engine/debasher_runtime_launcher.py`), not a new kind of process: to the
engine, a launcher node is a node like any other, with its heartbeat and its
control ports. A module defines one with a class that names the general
program, `PFILE`, or, with `PROCESS`, a single process of that module (see
"A single process"), and may give the runs root, `RUNS_ROOT`, an absolute
path; by default it is the output directory of the process, which the engine
keeps across launches of a node (see "Ordered shutdown") and exports to it as
`DEBASHER_PROCESS_OUTDIR`. `PFILE` is found as the module that declares the
node would find a module it loads: a relative path is looked for in the
directory of that module, where a program keeps its files, which the engine
exports to the node as `DEBASHER_PROCESS_MODULE_DIR`, and then in the
directories of `DEBASHER_MOD_DIR`, so that a program can launch one that
another module keeps, at the price of depending on how the machine is set up.
The node runs the engine's own search for this, `debasher_resolve_pfile`, from
the directory of the module. An absolute path is accepted with a warning,
since it ties the program to one machine. A node whose `PFILE` is not found
stops when it is created. Every input port that carries data is a port of
requests; the output port `DONE_PORT` (`outdone` by default), if the node has
it, tells when a batch run ends (see "The end of a batch run as an input
event"). A launcher node cannot be a task of an array process, since the tasks
would share its bookkeeping.

The modules that the general program loads are found with the
`DEBASHER_MOD_DIR` of the launcher node, which inherits it along the whole
chain of launches: the frontend puts it in the environment of the
`debasher_exec` it runs, from the program's own settings (or the shell has it,
on the command line); every node
inherits the environment of `debasher_exec`, the `Supervisor` too, and so does
a node that the `Supervisor` relaunches; and the launcher node runs each
`debasher_exec` of a batch run with the environment of the node. The generated
script of every process also carries the value that `debasher_exec` had when
it generated it, so that a node relaunched by hand, from a shell without it,
still has it; a new run, which generates the scripts again, takes its own. It
carries the directory of the module of every process too, from which
`DEBASHER_PROCESS_MODULE_DIR` comes.

The launcher node observes its batch runs (see "Observing the outside
world"): its `observe()` launches the registered ones and, if the node has
`DONE_PORT`, brings in the end of each under the name `RUNS_DONE_PORT`
(`runs_done`), its observe port.

## Requests and run directories

A request is a `DATA` whose payload is a JSON object: `opts`, the options of
the general program, an object whose keys are option names with their leading
dash and whose values are strings; and `run`, optional, the name of the run
directory, a relative path of plain names, none of which starts with a dot.
Without `run`, the name is the position of the
request in the input log, which a replay gives the request again. For
example:

```
{"opts": {"-bam": "/data/incoming/s17.bam"}, "run": "s17"}
```

A request whose `opts` is not such an object, or whose `run` is absolute,
contains `..` or a name that starts with a dot, is logged as an error and
dropped; a replay drops it again. The
general program checks the options themselves when it is launched.

## Ownership of a run directory

`process_data` does not launch anything: it registers the batch run. It writes
`launch.json` in the run directory, with `life_id`, the position of the
request in the input log and its options, and then
`.launcher/registrations/<position>.json`, with the name of the run
directory, in the output directory of its process: the list of registrations
of the node. `.launcher/` holds all the bookkeeping of the node, and no run
directory can clash with it, since no run name starts with a dot. Each
file is written to a temporary one and renamed into place. Both writes are
idempotent: a replay of the same request writes the same content to the same
paths.

A run directory belongs to the request that registered it:

- With no `launch.json`, the request registers it.
- With a `launch.json` of the same life and the same position, the request is
  the one that registered it, processed again by a replay, and nothing
  changes.
- With any other `launch.json`, the request is logged as an error and dropped:
  another request, or a request of another life, owns the directory. A request
  that wants to analyse the same input again with other options names another
  directory (`s17/v2`), so that no result is overwritten by mistake.

The rule depends only on what the input log and the directory hold, never on
whether a batch run is still going on, so a replay decides the same way.

`life_id` tells the requests of a life from those of the one before. After a
clean start the input log begins again from its first position, and a run
directory under an absolute runs root, which `debasher_reset_resident` does not
reach, still holds a `launch.json` with a position of the old log; without the
identifier, a new request at that position would be taken for the one that
registered it, and never launched. The identifier is created, at random, the
first time the node starts in a life (in `initialize_runtime()`, before its
replay), and kept in `.launcher/life_id`, in the output directory of its
process, which a reset empties. It cannot be part of the
node state: a node that crashes before its first checkpoint would generate
another one in its replay.

## Launching from the queue on disk

The node's `observe()`, on its observation thread, launches the batch runs
that are registered, in the order of their positions, with at most
`MAX_CONCURRENT_RUNS` running at a time (1 by default). Each one runs
`debasher_exec --pfile <PFILE> --outdir <run directory> --sched <scheduler>`
with the options of its request, in a session of its own, so that the batch
run outlives a crash of the node and a stop of the resident program. The
scheduler is `BATCH_SCHED`, `BUILTIN` by default, as for the resident program
itself, so that the batch runs do not depend on the scheduler that a machine
would pick on its own; `SLURM` sends them to a cluster. A program sets both in
the computational specifications of the process, `max_concurrent_runs` and
`batch_sched`, like the limits of a node (see "Limits of a node"); the engine
checks, when it loads the program, that the first is a positive number and
the second one of the schedulers that `debasher_exec` knows.

How a batch run is going is read from its run directory, whatever the
scheduler: with the built-in one, `debasher_exec` waits for the program to
end, but with SLURM it only submits the jobs, and ends at once. So `observe()`
writes the PID of `debasher_exec` into the run directory,
`launcher.pid`, its output going to `launcher.log`, and once `debasher_exec`
has ended well (the file `submitted`), asks `debasher_status` on the run
directory, at most once every `STATUS_CHECK_INTERVAL_SECS`, until nothing of
the program is in progress. The states of a batch run:

- Registered and not launched: launched when a slot is free.
- With its `debasher_exec` alive: running.
- With its `debasher_exec` ended with an error: ended, with that exit code
  (options that the program refuses, for example).
- Submitted, with the program in progress according to `debasher_status`:
  running.
- Submitted, with nothing in progress: ended, finished if every process of the
  program finished (exit code 0), failed otherwise (the exit code that
  `debasher_status` gives to an unfinished program).
- Not submitted, with its `debasher_exec` gone: it was stopped before it ended,
  when the node went down with it. If `debasher_status` says that something of
  the program is still in progress, the batch run is left to end; if it says
  that everything finished, it is ended as finished; otherwise `debasher_exec`
  is launched again on the same directory, whose rerun logic skips the
  processes that had finished and resumes the rest.

An ended batch run keeps its exit code, `exit_code`, and is never launched
again on its own: a program that always fails would be launched for ever. The
queue is the list of registrations on disk: a relaunched node, or one resumed
after a halt, finds it as it was, and `observe()` goes on from there.
When a batch run is launched is not part of the node state, and does not need
to be the same in a replay, since the node sends nothing when it launches.

## The end of a batch run as an input event

The directory of a batch run always says how it is going: its registration, the
PID and exit code that `observe()` writes, and `debasher_status` on it
for each of its processes. Anyone can read it, the frontend included, at no
cost to the node.

A node downstream can also be told, through an output port of the launcher
node, `outdone`. `observe()` cannot send on it: a node sends only from
`process_data`, whose calls the input log records and a replay reproduces. So
the end of a batch run enters the node as what it is, an event from outside the
program. Once the exit code is written, `observe()` brings
`{"run": ..., "exit_code": ...}` in with `inject()`, under `runs_done`, its
observe port, and only then, once it is logged, marks the run directory as
notified, with a file `notified`. `process_data`, on `runs_done`, adds the
batch run to the set of announced runs in its node state and sends
`{"run": ..., "status": ..., "exit_code": ...}` on `outdone`, with `status`
`finished` for an exit code of 0 and `failed` for any other, which then has
everything a channel has: its numbering (G5), its replay, its part in the
rounds.

- A node that goes down after writing the event and before marking the run
  directory writes it again when it comes back. `process_data` drops the
  second one, since the batch run is already in its announced set, and a
  replay, which finds both in the log in the same order, drops it too: the
  event may arrive more than once, the notice goes out once.
- A batch run that ends while the node is down leaves no exit code, since no
  launcher node was waiting for it. When the node comes back, `observe()` asks
  `debasher_status`, which says that every process finished, and
  the notice goes out.
- A launcher node without `outdone` brings in no event.

## A single process

With `PROCESS`, a launcher node launches that process of the module of `PFILE`
alone, with
`debasher_exec_process <PFILE> <PROCESS> -- <options>`,
from the run directory, so that a relative path among the options of a
request (the file the process writes, for example) lands there. There is no
scheduler in between: `debasher_exec_process` runs the process function and
ends when it ends, and the options of a request are the arguments of that
function. The states of a batch run differ in one point. A crash of the node
while the process runs would lose the exit code that the node was waiting
for, so the process records its own: it runs under a shell that writes its
exit code into the run directory when it ends, through a temporary file
renamed into place. With neither an exit code nor a live PID, the process was
stopped before it ended, and it is launched again from the start, since
`debasher_exec_process` has nothing to resume from: a process run this way has
to be able to run twice, overwriting its results.

## Stopping and resetting a launcher node

Stopping the resident program, by a halt or by a signal, does not stop the
batch runs it launched: they are general programs, in sessions of their own,
which `debasher_status` and `debasher_stop` reach on their run directories.
When the program is resumed, `observe()` finds them running, or ended
with no exit code, and goes on as above.

`debasher_reset_resident` empties the output directory of the process: the
list of registrations, the file of `life_id` and, with the default runs root,
every run directory, set aside or deleted with the rest. With an absolute runs
root, the run directories stay where they are, with the results; their
registrations belong to a life that has ended, so a request of the new life
that names one of them is dropped, and reusing that name means removing the
directory by hand.

# Loose ends to check before considering the design closed

The items below are split into what has already been fixed and what remains
open.

## Fixed

- **A port that only a source writes to never carries a marker.** A round
  waits for the marker of every input port that is not a control port, and a
  source is outside the program, so it sends none: without a way to exclude
  such a port, the round would never close, the node would write no
  checkpoint and its input log would grow until `INPUT_LOG_MAX_BYTES` is
  reached, an error. `EXTERNAL_PORTS` (see external port in the Glossary)
  excludes such a port from the pending set the same way `CONTROL_PORTS`
  does, but its `CLOSE` closes the port for good, unlike a control port's. A
  source that does know the protocol may still write the marker of the round
  the initiator opened: it is accepted like on any other port (`_on_barrier`
  does not special-case a port that is not pending). A node whose only
  inputs are external has no port left to receive a marker from, so it has
  to be an initiator itself (see initiator in the Glossary), triggered the
  same way a node with only a control port already is.
- **`debasher_stop`, `debasher_status` and `debasher_stats` did not see a
  resident program launched without `--sched BUILTIN`.** `debasher_exec`
  forced the built-in scheduler for a resident program only in its own
  memory, while the engine tools that operate on an outdir
  (`debasher_status`, `debasher_stop`, `debasher_stats`,
  `debasher_get_stdout`, `debasher_get_sched_out`, `debasher_get_fifo_mirror`)
  read the scheduler from the command line saved in the outdir: without
  `--sched` they fell back to the default, which is Slurm wherever `sbatch`
  exists, so `debasher_status` would print UNFINISHED and `debasher_stop`
  would stop nothing. The fix is general, not specific to resident programs:
  once the scheduler is final (after the resident enforcement),
  `debasher_exec` adds `--sched <scheduler in use>` to the command line it
  saves whenever the user did not give one
  (`record_effective_scheduler_in_command_line`, with
  `debasher::_add_sched_to_serialized_cmdline`), so the tools no longer have
  to work it out again, and a default that depends on the environment can no
  longer differ between the launch and a later query. One consequence: an
  outdir of a program that ran under Slurm, opened on a machine without
  Slurm, now makes the tools report that Slurm is not installed, exactly as
  it already does when `--sched SLURM` is typed explicitly, where before the
  tools silently used the built-in scheduler.
- Maximum packet size relative to `PIPE_BUF`: truncation only happens above
  4096 bytes and is handled by the resync line (see "Recovery from a node
  failure"), so there is no size limit.
- **A relaunched node that dies before its first heartbeat was never
  noticed again.** After `_declare_down` a node stayed in `_down` until a
  real heartbeat arrived, and `_check_node` skipped nodes in `_down`
  unconditionally: if the relaunch itself failed (a startup crash), nothing
  re-detected it, `_relaunch_attempts` never grew past 1,
  `MAX_RELAUNCH_ATTEMPTS` never tripped and the Supervisor never resolved.
  Now `_declare_down` resets `_last_heartbeat` to the moment it triggers a
  relaunch, the same grace period `__init__` already gives a brand new
  node, and `_check_node` treats an already-`_down` node the same way once
  that grace period elapses with still no real heartbeat: declared down
  again, counted against the same budget, able to escalate like any other
  outage.
- **Relaunching while the old process is still alive.** The
  heartbeat-timeout path also fires for a live but stuck process (PID
  alive, no heartbeat): `on_node_down` would start a second copy while the
  first still held its FIFOs, and since `_launch` removed the old `.id`,
  the old process would no longer be reachable by `debasher_stop` either.
  Now `debasher_builtin_sched::_launch` reads the old `.id` file, if there
  is one, before removing it, and kills that process group with the same
  `debasher::_stop_pid` a manual `debasher_stop` already uses (a no-op if
  it is already gone): one code path for an initial launch and every
  relaunch, with no need to tell a genuine crash apart from a stuck but
  live process.
- **Initiators numbered their rounds independently.** Each initiator
  numbered its next round as the last epoch it closed or abandoned plus one,
  and nothing makes two counters meet when no channel goes from one
  initiator to the other: they drift apart when a trigger is written into
  the FIFO of only one of them, or when a relaunched initiator restores a
  checkpoint older than a round it had abandoned. A node that both reach,
  such as the fan-in of two nodes whose only inputs are external (each has
  to be an initiator), replaced the lower round with the higher one and then
  waited for a marker of the higher epoch that the other initiator would
  never send: it wrote no further checkpoint, its input log grew until
  `INPUT_LOG_MAX_BYTES` was reached, and a halt never closed there, so
  `debasher_stop_resident` always ended in its hard kill. Now the
  `Supervisor` and `debasher_stop_resident` number the triggers they send
  (see numbered trigger in the Glossary), so that every initiator opens the
  same round. A trigger without an epoch, written by an actor outside the
  program straight into the FIFO of an initiator, still uses that
  initiator's own counter, and with several initiators whose rounds meet it
  can still lead to the same wait.
- **A lost marker kept the round of an initiator open for ever.** A marker
  is lost when a node crashes after it has captured its state and enqueued
  its marker and before its writer thread has written it, and likewise with
  a message read from a FIFO and not yet written to the input log, or a FIFO
  destroyed with both its endpoints down (see the Contract's limits). The
  round of its receiver then stays open. At a node that is not an initiator,
  the marker of the next round, of a newer epoch, replaces it; at an
  initiator, a `start_snapshot` without an epoch that found a round open was
  ignored, so an initiator in a cycle whose marker never came back took no
  further snapshot. No node of the cycle wrote another checkpoint, and their
  input logs grew until `INPUT_LOG_MAX_BYTES` was reached, which ends the
  reader thread and looks, to the `Supervisor`, like a crash. Now a trigger
  without an epoch replaces an open snapshot too, as a numbered trigger of a
  newer epoch already did (see "Chandy-Lamport barrier propagation"), so the
  round with the lost marker is abandoned at the next trigger, whatever lost
  it: that round has no complete cut, and the next one does.
- **Nothing checked that a round can reach every node.** A node that no
  round reaches never writes a checkpoint, and neither do the nodes it
  writes to, which wait for its marker: their input logs grow until
  `INPUT_LOG_MAX_BYTES` is reached, and a halt never closes there. The engine
  could not check it, since which channels carry commands or come from
  outside, and which end of a fifo writes it, were only in the Python classes
  of the nodes. Now a fifo fed from outside, or carrying commands, carries a
  fifo tag, the owner of any other fifo writes it, and the engine refuses a
  program in which a node cannot be reached, when it is loaded (see "Channel
  kinds declared with the fifo"). A node cut off at run time, by a node that
  fails for good, is handled by "Escalation on a permanent node failure".
- **A launch depended on the new process publishing its PID in time.** The
  launched script wrote its own `.id`, and `_launch` waited for it with a
  fixed number of turns of a `[ -f ]` loop, about 90 ms, not a time: a
  script slower to start (it reads its whole dumped environment first) made
  `_launch` return an error although the process was starting. Now
  `_launch` writes the `.id` itself, from `$!`, which is the script's own
  PID (the background job execs the script directly, and `set -m` makes it
  the leader of its process group, which `debasher::_stop_pid` already
  relies on), through a temporary file renamed into place. The file is
  complete as soon as `_launch` returns, and nothing waits.
- **A writer whose reader does not read could grow its outbound backlog
  without limit.** A writer cannot tell a reader gone for good from one
  that crashed or halted (see "The reader-dies direction"), and blocks on
  backpressure in every case, but `send_data` kept accepting messages into
  `_outbound_queues` and `_unwritten` with no limit, and
  `OUT_BACKLOG_MAX_BYTES` only skipped checkpoints: the node took more and
  more memory and ended, if at all, at the input log's cap, with an error
  about rounds that do not close. A reader of a resident program stops for
  good only if it is stopped on its own by hand (a node ends only on a stop
  signal, and `debasher_stop_resident` sends it to every node together), or
  crashes with nobody to relaunch it; one slower than its writer for good
  has the same effect. Now `OUT_BACKLOG_FAIL_BYTES` bounds the backlog and
  fails loudly, naming the port, and the input log's cap names the backlog
  when checkpoints are being skipped (see "Checkpoint persistence"). No
  guarantee was at stake (G1 to G8): nothing was lost or duplicated.
- **A healthy node could be declared down when the `Supervisor` itself did
  not run for a while.** Its checker thread, running again before the
  threads that read the heartbeats still waiting in its FIFOs, found a live
  node silent for longer than `HEARTBEAT_TIMEOUT_SECS`, and the relaunch
  killed the node that was still running (`debasher_builtin_sched::_launch`
  kills the previous incarnation first), at whatever moment it landed. The
  wall clock it measured with could also jump and make every node look
  silent at once. Now the checker measures on the monotonic clock and does
  not count against any node the time it did not run itself (see "Failure
  detection"). A node that is itself starved of CPU for longer than the
  timeout is still declared down, since from outside it cannot be told from
  one that is stuck: a program where that is expected sets a longer
  `heartbeat_timeout_s` for its `Supervisor`.
- Dedicated concurrency test for the fan-in case with more than one input
  port pending on the barrier:
  `test_two_pending_ports_waits_for_the_second_marker`.

## Unfixed

None at present.


# Extensions

Design ideas from Future work move here once they are actually built.

- **Array processes.** A process that is an array of tasks, whether its
  options are written in a loop or produced by an option generator, takes
  part in a resident program with each task as a node of its own,
  `(process_name, task_idx)`:
  - Files. The tasks share the process's directory, as they already share the
    engine's own per-task files (`<process_name>_<idx>.id`, `.sched_out`, ...),
    and each keeps its checkpoints, input log, halted marker and control ports
    file there under names that carry its index (see execdir in the Glossary).
  - Connections. `define_opt_from_proc_out` connects a task to a fifo of
    another node, and `define_opt_from_proc_task_out` connects a node to the
    fifo of one task, as for any other process; a generator gives each task a
    fifo of its own with `define_fifo_opt_generator`. The engine creates every
    fifo before launching, so a task's channels are like those of any node.
  - Supervision. The engine names a task in the `NODE_PORTS` of the
    `Supervisor` as `(process_name, task_idx)`, and the `Supervisor` finds and
    relaunches it through its own `.id` and `.finished` (see "Port declaration
    and node identity").
  - Stopping. `debasher_stop_resident` stops each task as a node of its own,
    and `-x` can leave one task alone (see "`debasher_stop_resident`: the
    graceful stop tool").

  `test/engine/debasher_array_ref.sh` is the reference: an initiator fans out
  to the three tasks of an array, which fan in to a third node, with no
  `Supervisor`. `test/engine/debasher_array_gen_ref.sh` is the same program with
  the tasks produced by an option generator: only the number of tasks matters
  to the rest of the engine.
- **Fan-out and fan-in sized from the command line (the `ith` convention of
  general programs).** A node can have as many input or output ports as an
  option of the command line says, written as in a general program
  (`data/programs/debasher_dynamic_fanout_fifos.sh`): a process documents the
  family once, as `-outfith`, and defines `-outf0` to `-outf<w-1>` in a loop
  over its `-w` option; an array process of `w` tasks takes one each (see
  "Array processes" above), and a fan-in node defines `-ind0` to `-ind<w-1>`
  from the tasks. The engine's check of option names recognizes the family
  (`debasher::_actual_opt_is_ith_instance`). The topology stays fixed and is
  known before the run starts: every process and every connection is defined
  up front, and only how many there are comes from the option, unlike
  "Dynamic process launching" in Future work. Nothing in the engine is
  specific to it:
  - Ports. Each node gets the ports of the family from its options, and the
    `Supervisor` a heartbeat channel for each task that has one, so that it
    watches as many nodes as `-w` says (see "Ports from the engine").
  - The barrier, `CLOSE` and the input log loop over the declared lists of
    ports: a fan-in node is the case of several pending ports, and a fan-out
    node forwards the marker on every output port.
  - Routing is part of `process_data`, and it has to be deterministic: a
    function of the packet, or of a counter kept in the node state. A choice
    by the load of the tasks would make a replay send a message to another
    task than the first time, and the numbers of that channel would label
    different messages.
  - The engine does not check that a node restored from a checkpoint has the
    ports it had when it saved it, while `closed_ports` and the sequence
    numbers of G5 in the checkpoint are keyed by port name. A relaunch runs
    the same generated script, so it gets the same `-w`; a run with another
    `-w` has to start afresh (see "`debasher_reset_resident`: a clean
    start").

  `test/engine/debasher_fanout_cmdline_ref.sh` is the reference: `start`
  sends each message from outside to the next of the `-w` tasks of `worker`,
  with a counter in its node state, the tasks forward it to `collect`, and a
  `Supervisor` that declares no port watches every node and relaunches a task
  of the array like any other node.
- **A node that emits on its own: a self-loop.** A node acts only in reaction
  to what it receives, so what starts the activity of a program comes from
  outside. A node that has to go on emitting after that, a counter or the
  ticks of a clock, sends itself the message that triggers its next step: an
  output port of the node connected to one of its own input ports
  (`define_opt_from_proc_out` naming its own process). Its configuration
  arrives from outside, each call to `process_data` emits one step and sends
  the next trigger to itself, and its node state says when to stop. Each call
  is short, so the node takes part in rounds and answers commands between
  steps. Nothing in the engine is specific to it:
  - Rounds. The loop is a channel like any other: the marker that the node
    sends on its output port goes round the loop behind whatever was in
    transit, which the round keeps as the channel state of the loop, and the
    node's part of the round closes when the marker comes back.
  - Recovery. Both ends of the loop are the same process, so a crash of the
    node, when the `Supervisor` does not hold the FIFO (see "Holding the
    business channels"), destroys what it held, the case that "Both endpoints
    of a channel crashed" in the Contract's limits describes. Even then
    nothing is lost. The checkpoint is saved when the round closes, after the
    marker has come back, and so after everything that the node sent itself
    before the capture has been read and written to the input log. Whatever
    the loop holds at a crash was therefore sent while processing a message
    that lies in the log after the `capture_pos` of the latest checkpoint: the
    replay processes it again and resends what it sent, with the same numbers
    (G5), and the reader drops as duplicates what had already arrived.
  - Pace. `sleep(seconds)`, called from `process_data`, sets the rate of the
    loop. It does not wait while the node replays its input log, and returns
    early once the node is told to stop (see "Defining a node"). The rate
    does not adapt to the readers: a channel is one-way, so a node cannot
    know how far its readers got, and one that emits faster than they read is
    stopped by `OUT_BACKLOG_FAIL_BYTES` with an error (see "Checkpoint
    persistence").
  - Ending. The node stops sending itself the next trigger when its node
    state says so, and stays idle; it does not finish for good, since no node
    does (see "A node that finishes for good" in Future work).

  `test/engine/debasher_selfloop_ref.sh` is the reference: `counter` counts up
  to a limit that arrives from outside, sending each value to `sink`, under a
  `Supervisor`; a round started while it counts closes through the loop, and
  a `counter` killed while it counts is relaunched and goes on with no value
  missing or repeated at `sink`.
- **A clean start of a resident program.** A tool, `debasher_reset_resident`,
  takes away the state that every node keeps across runs, its checkpoints,
  input log, halted marker and output directory, setting it aside or deleting
  it, so that the next run starts afresh (see "`debasher_reset_resident`: a
  clean start"). The real-run tests of `test/engine/debasher_resume_ref.sh`
  check that it refuses while the program runs, and that the run after it
  finds no checkpoint.
- **Snapshots from outside the program.** A tool,
  `debasher_snapshot_resident`, starts a snapshot in a running program, with
  or without a `Supervisor`, once or every given number of seconds, and waits
  for it to close at every node (see "`debasher_snapshot_resident`: rounds
  from outside the program"). The real-run tests of
  `test/engine/test_snapshot_resident.py` start rounds in
  `debasher_halt_ref.sh`, which has no `Supervisor`, and in
  `debasher_chaos_ref.sh`, which has one, and check that a periodic run ends
  with the program and that a round that cannot close is reported.
- **Batch runs from a node.** A launcher node, of class `ProgramLauncher`,
  launches a general program, or a single process of a module, once for each
  request it receives, in a run directory of its own, with a queue on disk, a
  limit of batch runs at a time and a notice downstream when each one ends
  (see "`ProgramLauncher`: batch runs from a node").
  `test/engine/debasher_launcher_ref.sh` is the reference, with
  `test/engine/debasher_launcher_batch.sh` as the general program: its
  real-run tests, with the built-in scheduler and with SLURM where the machine
  has a controller up, check the results and the notices of two requests,
  and that a batch run outlives a crash of its launcher node and is announced
  once.
- **Observing the outside world.** A node can watch something outside the
  program, and bring what it sees in as an input, with `observe()` and
  `inject()` (see "Observing the outside world"); `DirectoryWatcher` watches a
  directory for files. `test/engine/debasher_watch_ref.sh` is the reference: a
  watcher sends a launcher node, which runs a single process of
  `test/engine/debasher_watch_batch.sh`, a request for each `.bam` file that
  arrives in a directory; its real-run test checks that every file is
  processed once, one still being written only once it is complete, and that a
  watcher killed and relaunched, which brings the files in again, makes no
  request twice.
- **A startup deadline for a node.** A node sends its first heartbeat only
  once it has restored its checkpoint, run `initialize_runtime()` and
  replayed its input log, which can take longer than
  `HEARTBEAT_TIMEOUT_SECS`; declared down for it, a node with a long replay
  would be relaunched again and again, and given up. Until its first
  heartbeat after a launch, the `Supervisor` gives it its startup deadline
  (see "Failure detection"), which the node sets in its computational
  specifications, `startup_timeout_s`. Sending the first heartbeat earlier,
  before the replay or as soon as the threads start, would not do: a
  heartbeat resets the relaunch budget, so a node that crashes on the same
  record at every replay, or on the first live message after it, would be
  relaunched for ever. A replay
  also no longer waits for the pace of a node that emits on its own, since
  `sleep()` does not wait during it (see "Defining a node").

  `test/engine/debasher_startup_ref.sh` is the reference: `slow` takes half a
  second over every message and has a startup deadline of 30 s, under a
  `Supervisor` whose heartbeat timeout is 2 s; relaunched with ten messages
  to replay, it is not declared down again.
- **A third holder of every business channel.** The `Supervisor` holds the
  FIFO of every business channel between two nodes through a read end that it
  never reads, so that what a FIFO holds outlives the crash of both of its
  endpoints; the engine gives it the FIFOs, and the flag `-no_hold_fifos`,
  which its module can offer on the command line of the program, turns it off
  (see "Holding the business channels"). The loss is then left to the
  `Supervisor` being down at the same time, which nothing watches (see
  "Supervising the `Supervisor`" in Future work). Every process also raises
  its limit of open descriptors to what its ports need (see "Limits of a
  node"). `test/engine/test_hold_fifos.py` kills both endpoints of a FIFO
  together at random moments, with and without the `Supervisor` holding it,
  and the chaos test runs the same case on a real run of both kinds, one of
  them with `-no_hold_fifos`.

# Future work

- **What a launcher node leaves out** (see "`ProgramLauncher`: batch runs
  from a node"). A command to launch again a batch run that failed, since its
  `observe()` never does it on its own; and priorities, or a limit shared by
  several launcher nodes, beyond the `max_concurrent_runs` of each.
- **Dynamic process launching**: the architecture described in this document
  does not, from the outset, support dynamically launching processes. "General"
  programs already sketch a mechanism for this (see
  `data/programs/debasher_dynamic_fanout_taskdone.sh`), but it would need to be
  studied how to combine it with checkpointing, and for Python processes the
  mechanism could be entirely different. Noted here so it is not forgotten and
  can be tackled later, so that `resident` programs have as much expressiveness
  as possible.
- **Global (coordinated) rollback, as a fallback to localized recovery**: noted
  here, not designed and not built. Localized recovery (see "Recovery from a
  node failure") remains the policy for the ordinary crash of a node. A
  global rollback would be the safe
  harbor for the cases the Contract leaves outside its guarantees, an
  alternative to the narrower, targeted repairs "Repairing messages destroyed
  with a FIFO" below lists for one of them specifically: detect the
  violation, stop, rewind every node to the last consistent cut, resume.
  Cases where it would be used: a guarantee that cannot be kept is detected
  (a hole in a channel's sequence numbers, a missing or
  corrupt checkpoint or log, an incompatible schema version); a node fails
  permanently (today the `Supervisor`'s own escalation ends in
  `debasher_stop`; with a rollback it becomes "stop, fix, rewind, resume");
  several connected nodes, or
  all of them, crash together with inputs that cannot be regenerated (the
  contents of the FIFOs are gone, with no process holding them); a crash
  during a snapshot round, if aborting rounds turns out to be harder than
  falling back to the last complete epoch; a deliberate rewind requested by
  an operator. Not for the crash of a single node. The price is the work done
  since the chosen epoch, and the external inputs received since then
  (delivery at that boundary is at most once).

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
  `Supervisor`, or `-no_hold_fifos`, see "Holding the business channels"), what
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
  Contract's failure model. First step: `fsync` of the checkpoint file and of
  its directory when a checkpoint is saved, and of the log at a halt (about 2 ms
  per round); together with the global rollback above it lets a program go back,
  after a machine crash, to its last consistent snapshot. Second step: `fsync`
  of the input log every few messages (group commit), which also protects the
  work since that snapshot, at a cost in throughput. Neither is designed nor
  built.
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
    `process_data`, for a node that emits on its own (see "A node that emits
    on its own" in Extensions); or both. A node with no data input could only
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
  settle: the timer has to start its round through the same hook as an item that
  arrives, so that the round has a `capture_pos` (see "Arrival and positions");
  its period has to be longer than a round, or rounds keep replacing each other
  (see "A round that a newer one replaces" in the Contract's limits); and the
  timers of several initiators would open rounds of different epochs, which a
  node that both reach waits for separately, so they need a common numbering,
  like that of a numbered trigger (see the Glossary). Not built.
- **Progress in the heartbeat.** A node whose brain thread is alive but
  blocked is not detected (see "Stuck but alive" in the Contract's limits):
  the heartbeat says that its threads are alive, not that they make progress.
  A counter of the items the brain thread has processed, sent with each
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
- **Resident programs in the frontend.** The visual editor (`frontend/`) and
  the API behind it (`api/`) know nothing about resident programs: the program
  model has no program type, `api/program_import.py` and
  `api/script_generation.py` neither read nor write `program_type "resident"`,
  and nothing describes a process as an `FBPProcess` or a `Supervisor`.
  Everything needed to build, run and inspect a resident program from the
  frontend is left to do, among it:
  - the program type, in the model and in both directions of the conversion
    between the model and a module;
  - the fifo tags, `--control` and `--external` (see "Channel kinds declared
    with the fifo"), as an attribute of a fifo option, like `mirror`;
  - the limits of a node in the computational specifications (see "Limits of
    a node"): the model knows only `cpus`, `mem` and `time`, so a round trip
    through the editor drops them;
  - editing a node's class, showing its ports, and wiring the heartbeat
    channels and the trigger ports of a `Supervisor`, which are fifos like any
    other: the engine takes the ports of every process from its options and
    their tags (see "Ports from the engine");
  - launcher nodes (see "`ProgramLauncher`: batch runs from a node"): their
    general program, their runs root, and their batch runs, shown from their
    run directories;
  - array processes, whose tasks are nodes of their own (see "Array processes"
    in Extensions), and fan-outs and fan-ins sized from the command line (see
    "Fan-out and fan-in sized from the command line" in Extensions): the loops
    of `define_opts` over an option such as `-w`, which the frontend already
    writes for a general program (`countSourceOptionId`, `_is_fanout_label`,
    `isFanoutOption`), and a template of `process_data` for a fan-out node
    whose routing is deterministic;
  - the "Watch FIFO" action, whose `--mirror` a resident program refuses (see
    the Contract's limits);
  - starting a snapshot, once or periodically, with
    `debasher_snapshot_resident`, and stopping the program with
    `debasher_stop_resident`;
  - showing the state of each node: heartbeats, relaunches, checkpoints and
    halted markers.

  Not designed.
