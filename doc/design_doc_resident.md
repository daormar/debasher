# Design of resident programs

Working document. What it says about what is built and what is not reflects the
branch `feature/fbp-stateful-engine` at the dates given in each note, and the
Contract's conformance status lists the known gaps between this design and the
code.

## Introduction

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
it comes the breakdown of the work needed to achieve them. That breakdown is in
seven numbered sections, cited in the text by their number (section 3 is the
input log, section 5 the recovery from a node failure), and the order in which
the work was done is the numbered list of steps under "Order of implementation"
in section 3.

## Glossary (Glosario)

The precise meaning of the words this document uses, in the order in which they
build on each other; the Spanish equivalent is in parentheses. In Spanish
"registro" can mean both the log and one of its entries, so here the log is the
"log" and a record is an "entrada del log". Identifiers in backticks are names
that exist in the code or that have been decided. Earlier text called the input
log the "message log" and its replay "drain"; both names are gone from the code.
The vocabulary of the guarantees (deterministic, idempotent, chaos test,
mutation check, durability level) is defined in the Contract, where it is used.

### Program and topology

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
  without its leading dash. A subclass lists its input ports and its output
  ports in `INPUT_PORTS` and `OUTPUT_PORTS`; the `Supervisor` names its input
  ports after the nodes it watches (`NODE_PORTS`).
- **channel** (canal): the one-way connection from an output port of one node to
  an input port of another, made of a FIFO (a named pipe created by the engine).
  It delivers envelopes in the order in which they were sent. Business channels
  carry `DATA` and `BARRIER`; the channels to and from the `Supervisor` carry
  only `INTERACT`.
- **source** (fuente): whatever puts `DATA` into an input port of a node without
  being a node of the program: a person writing into a FIFO, an external
  program, a test harness. A node acts only inside `process_data`, in reaction
  to what it receives, and never sends on its own initiative (decided and
  enforced on 2026-09-21: `send_data` raises anywhere else), so a source is
  always outside the graph of nodes, and what enters through it is an external
  input (see "Limits and non-goals"). The real runs reported here before that
  date used, as sources, processes written for the run that only sent messages.
- **root** (raíz): a node that no other node sends `DATA` to. Its input ports,
  if it has any, are control ports or are written from outside the program, by a
  source. It can start a round, and its part of a round closes as soon as it
  opens, since it has no pending port.
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
  receives an `INTERACT` `start_snapshot` or `shutdown` (or, if enabled, because
  of its own snapshot timer). It has to be able to reach every other node
  through the channels; a program made of independent subgraphs needs one
  initiator per subgraph.
- **trigger** (disparo): the `INTERACT` command, `start_snapshot` or `shutdown`,
  that makes a node start a round. It reaches an initiator from the
  `Supervisor`, from an actor outside the program that writes it into a FIFO of
  the initiator, or, as an in-process call and not as a message, from the
  initiator's own snapshot timer.
- **trigger port** (puerto de disparo): an output port of the `Supervisor`, an
  entry of its `TRIGGER_PORT` list, wired to an initiator; the `Supervisor`
  sends the triggers through it.
- **manual trigger port** (puerto de disparo manual): the input port of the
  `Supervisor`, `MANUAL_TRIGGER_PORT`, where an actor outside the program writes
  a trigger, which the `Supervisor` relays to every trigger port.
- **control port** (puerto de control): an input port of a node, listed in
  `CONTROL_PORTS`, that carries only `INTERACT` commands, such as the one on
  which an initiator receives its triggers. It never carries a marker, so it
  takes no part in any round, and a `CLOSE` on it does not close it, because its
  writer (the `Supervisor`, or whoever writes commands) may come back.
- **control ports file**: the file `control_ports` that a node writes in its
  own `execdir` when it starts (one fifo path per line, from `self.opts`, one
  per entry of `CONTROL_PORTS`; empty, not absent, if it has none), so that an
  external actor can find where to write a trigger for an initiator with no
  other knowledge of this program: `CONTROL_PORTS` is a Python class
  attribute, invisible to a tool outside the process (see
  `_write_control_ports_file`).
- **external port** (puerto externo): an input port of a node, listed in
  `EXTERNAL_PORTS`, fed only from outside the program (a source, or a person
  writing by hand), which therefore does not carry a marker of its own: a round
  never waits for it. Unlike a control port, a `CLOSE` on it does close it for
  good, since its writer is not expected to come back. A source that does know
  the protocol may still write the marker of the round the initiator opened: it
  is then read like on any other port.
- **incarnation** (encarnación): one running instance of a node's process.
  Relaunching a node after a crash starts a new incarnation of the same node,
  which reuses its FIFOs, its directory and its checkpoints.
- **execdir**: the node's own directory, `__exec__/<process_name>/` under the
  program's output directory, exported to the process as
  `DEBASHER_PROCESS_EXECDIR`. Its checkpoints and its input log live there.

### Messages

- **envelope** (sobre): one JSON line on a channel,
  `{"type": ..., "payload": ...}`, with one of the five types below. A `DATA`
  envelope will also carry a `seq` (see "sequence number" in the input-log
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
  sends none (decided and done on 2026-09-20). The reader hands it to the brain
  thread in order and then keeps reading, but drops everything that follows it
  (decided and done on 2026-09-20; the `Supervisor`'s readers deliver it, since
  a node that closed its channel may be relaunched and must be heard).
  `closed_ports` is the checkpoint field that lists the input ports whose
  `CLOSE` the brain thread had processed when the round captured the node state.
  A sender that numbers what it sends (G5) puts its `out_seq` for that channel
  in `CLOSE`'s own payload, `last_seq`: the receiver checks it against what it
  has accepted, and a mismatch is a lost message that nothing else would ever
  reveal, since nothing comes after a `CLOSE` (G8, decided and done
  2026-09-22). Left out (an empty payload) when the sender does not number
  what it sends.
- **`HELLO`, resync line** (línea de resincronización): the first thing every
  incarnation of a writer sends, in one write together with a leading newline.
  The newline ends any fragment that the previous incarnation left when it was
  killed in the middle of a message, and the `HELLO` tells the reader that such
  a fragment can be dropped. It also tells the reader that its peer
  (re)connected.
- **ghost connection** (conexión fantasma): each endpoint of a channel holds
  both ends of the FIFO, the real one and a ghost of the opposite direction. The
  reader never sees EOF and the writer never gets `EPIPE`; a dead peer is only
  backpressure, and a channel outlives the crash of either process. It relies on
  Linux behavior.

### Rounds and checkpoints

- **node state** (estado del nodo): what `capture_node_state()` returns and
  `restore_node_state()` takes back: the serializable logical state of a node,
  complete enough for `restore_node_state()` to rebuild it exactly. Runtime
  resources (connections, file handles) are not part of it;
  `initialize_runtime()` rebuilds them. In the checkpoint it is the field
  `node_state`, which sits beside the `channel_state` and beside the engine's
  own bookkeeping (`capture_pos`, `closed_ports` and the sequence numbers).
  It was called `state` until 2026-09-20, and its hooks were `capture_state()`
  and `restore_state()`.
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
  round as the last epoch it closed or abandoned plus one.
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
  since 2026-09-22 it behaves exactly like a snapshot at the node itself (the
  node keeps running after saving its checkpoint), and only writes its own
  **halted marker** on top of that (see below). What actually stops the node,
  and later resumes the program by relaunching every node, is a **stop signal**
  (see below), decided entirely outside the barrier protocol. Before that date
  a halt stopped the node itself as soon as its round closed, which is what the
  Contract's G2 gap (see "Conformance status") was about.
- **halted marker** (marca de halted): the file `halted` that a node writes in
  its own `execdir` (atomically, like a checkpoint, but never schema-versioned
  or pruned) when a halt round closes, holding that round's epoch as plain
  text. Read by nothing inside the node itself (in memory, `_halted` already
  keeps the same incarnation from opening another round, see "State variables,
  at a glance"); it exists only for an external actor with no other view of
  the node's state, such as the tool a stop signal comes from, to notice that
  this incarnation has nothing further to send and it is safe to stop it.
- **stop signal**: `SIGTERM`, sent to a node's whole process group (the same
  group `debasher_stop` already reaches with `SIGKILL`, see
  `debasher::_stop_pid`), which is what actually ends a node's `run()`
  (`_stop_requested`, set by the handler `run()` installs, `_on_stop_signal`).
  Unlike a halt closing its round, receiving one is not conditional on
  anything: a node that never halted stops on one just the same. Nothing in
  `FBPProcess` decides when to send it: that is external, by design (see
  "Conformance status"), typically once every node's halted marker exists.
  `Supervisor` stops on one too (section 4's own "Clean-completion
  detection" subsection).
- **`debasher_stop_resident`**: the tool that actually sends the stop signal
  in a real program, the graceful counterpart to `debasher_stop` (section
  4's own subsection of the same name has the full sequence). Waits for
  every node's halted marker, then signals each; stops a `Supervisor`, if
  the program has one, before touching any node it watches; falls back to
  `debasher_stop`'s hard kill past its own `--timeout`.
- **in transit** (en tránsito): a `DATA` message sent before its sender captured
  its state and received after its receiver captured its own.
- **channel state** (estado de canal): `channel_state`, the copy that a node
  keeps, in the checkpoint, of the `DATA` that arrived on a pending port during
  a round: the messages that were in transit at the cut. They are also processed
  normally. Localized recovery does not read it (it uses the input log); a
  global rollback would.
- **consistent cut** (corte consistente): the checkpoints of every node for the
  same round, taken together (each one holds its node state and the channel
  state of its input ports): a state that the whole program could really have
  been in. It is what the literature calls the snapshot, the result of a round.
  It holds only if no node crashes during the round.
- **checkpoint** (punto de control): the file `<epoch>.json` that a node writes
  atomically in `<execdir>/checkpoints/` when a round closes. It holds a schema
  version, the epoch, the `node_state` and the `channel_state` and, with the
  input-log redesign, the engine's own bookkeeping: `capture_pos`,
  `closed_ports`, `out_seq`, `last_seq` and the outbound backlog,
  `out_backlog`. Only the last `CHECKPOINT_RETENTION` are kept.
- **outbound backlog, `out_backlog`** (cola de salida pendiente): the `DATA`
  that `send_data` has numbered and queued but the writer thread has not yet
  finished writing when a round captures the node state (G5): `{tag: [{"seq":,
  "payload":}, ...]}`, decoded fresh from each queued line. Without it, a crash
  right there would destroy those messages for good, with no trace (see "Both
  endpoints of a channel crashed" in the Contract's limits, fixed 2026-09-22).
  Recovery re-enqueues it, with the same numbers, before anything else is
  sent.

### Input log

- **input log** (log de entrada): one log per node, in `<execdir>/log/`, of
  everything that arrives at it, in the order in which the brain thread
  processes it, written by the reader threads when each item arrives. It holds
  every queued item (`DATA`, `BARRIER`, `INTERACT`, `CLOSE`), and only `DATA` is
  replayed.
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
  it. It was called `processed_upto` until 2026-09-21: that name suggested that
  everything up to the position was completely processed, when the item at it is
  the one being handled at the capture.
- **torn tail** (cola partida): an unterminated last line that a process killed
  in the middle of a write leaves in a file. It can happen at any record size
  (measured, see the input-log redesign). A record counts only if its line ends
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

### Threads of a node

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

### Failure and recovery

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
  `Supervisor` every `HEARTBEAT_INTERVAL_SECONDS`. The `Supervisor` declares a
  node down when they stop for `HEARTBEAT_TIMEOUT_SECS`, or at once if the
  node's PID is gone and its `.finished` file is absent.
- **down, done, given up** (caído, terminado, abandonado): the states of a node
  in the `Supervisor`. Down: declared down and relaunched. Done: its `.finished`
  file appeared (it exited cleanly with code 0), so it is never checked again.
  Given up: it exhausted `MAX_RELAUNCH_ATTEMPTS`, which triggers the escalation.
- **escalation** (escalada): what the `Supervisor` does when a node is given up:
  an ordered shutdown through the initiators and, if some node has not finished
  after `FORCE_STOP_TIMEOUT_SECS`, `debasher_stop` on the whole program.

### State variables, at a glance

Several pieces of a node's bookkeeping go through the same three stages: a
live value that the brain thread keeps up to date as it processes each item, a
copy taken at the capture and held only while a round is open (see "capture"
above), and the checkpoint field the copy is written to when the round closes.
The table names the three for each concept, which this glossary already
defines: it is not redefined here. `Supervisor`'s own bookkeeping (which
nodes are down, how many times each has been relaunched) is a separate
concern, covered in section 4.

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

## Contract: assumptions, guarantees and non-goals

**Status: draft written on 2026-09-19.** Every open item was settled on
2026-09-20 and none remains open; the mechanisms are designed in the numbered
sections after this one. It applies to programs whose `_program_type` is
`resident`; general programs keep today's behavior.

The purpose of this section is that "reliable" has a precise meaning here:
within the stated assumptions, either the guarantees hold, or the violation is
detected and reported. Never "it usually works". Every guarantee must be backed
by at least one end-to-end test that states it in the same words (see
"Acceptance").

### Failure model

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
- **Durability level (decided 2026-09-20): process crashes only.** Nothing is
  `fsync`ed anywhere, so logs and checkpoints survive the crash of a process but
  not the crash or power loss of the machine; see the note below on what `fsync`
  is and what it would cost.
- **Not tolerated**: machine crash or power loss (see above), disk corruption,
  and processes that misbehave instead of crashing (Byzantine faults).
- **The `Supervisor` is not itself supervised.** If it dies, the nodes keep
  running with their state, but nobody relaunches a crashed node until the
  `Supervisor` is relaunched by hand. Decided on 2026-09-20: this is simply
  documented, and no mechanism is added for now.

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

### Obligations of module authors

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
  running `process_data` (decided and done on 2026-09-21). What starts the
  activity of a program is written into an input port from outside (see
  "source" in the Glossary).
- **`capture_node_state()` is complete and `restore_node_state()` exact**:
  everything that influences future behavior round-trips through them.
- **Effects outside the graph are idempotent**: replay re-executes
  `process_data`, so anything it does outside the FIFOs (writing a file
  elsewhere, calling a service) can happen more than once.
- **Messages are JSON-serializable, of any size.** A message larger than
  `PIPE_BUF` (4096 bytes on Linux) being written when its sender crashes can
  leave a truncated fragment in the FIFO (checked with real writers killed
  mid-write: 0 of 100 rounds at 4000 bytes, 53 of 100 at 5000 bytes). The reader
  drops it thanks to the resync line (see the Glossary) that every writer
  incarnation sends first, and the sender's replay regenerates the message. Only
  the framework writes to these channels; an external writer must send complete
  lines.

### Guarantees

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
  order; and if a message is lost anyway, the receiver notices. Mechanism
  (decided 2026-09-20): each `DATA` carries a sequence number per channel,
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
  capturing it. A crash during a round aborts it (mechanism not designed yet,
  see Loose ends).
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

### Limits and non-goals

- **Both endpoints of a channel crashed before either reopened the FIFO.** When
  one endpoint of a channel crashes, nothing is lost: the other holds the FIFO
  open, and what the writer had sent and the reader had not yet read waits in
  it. That now also covers what the writer had only numbered and queued but not
  yet written when it crashed, which used to be destroyed with no trace: the
  checkpoint's outbound backlog carries it, and recovery sends it again before
  anything else (fixed 2026-09-22, 5.4). A relaunched node holds its FIFOs
  from the first step of its recovery,
  before it restores its checkpoint or replays its input log, until it dies. So
  only if the second endpoint crashes before the first has been relaunched and
  has reopened the FIFO, which takes the time to notice the crash and start the
  new process, or if both crash together, is there a moment at which neither
  holds the FIFO, and what it held is destroyed, at most what a pipe holds (64
  KiB). Checked with real `kill -9` on 50 unread lines: all survive if only one
  endpoint dies, and none survives if both do, together or half a second apart
  with no relaunch in between. The recovery is not part of that window: with the
  writer killed while the relaunched reader was still replaying its log (19 of
  60 records replayed), all 50 are delivered, where before the FIFOs were opened
  first thing in the recovery none was. Whether the loss is repaired depends on
  where the destroyed messages came from. A relaunched writer restores its
  latest checkpoint and replays its input log after `capture_pos`, so it
  sends again, with the same sequence numbers, everything it produced from that
  point on: the destroyed messages among those reach the reader after all, and
  it cannot tell (checked with a real relay that had a checkpoint after 10
  messages, received 5 more and was killed: the relaunched one sent exactly
  those 5). What it had sent before that checkpoint is inside the node state
  that it restores and is not sent again: if some of it was still unread in the
  FIFO, it is lost, and the reader finds the hole in the sequence numbers when
  the next message arrives (G8). Ways to repair more are listed in Future work,
  none designed. Non-adjacent nodes may crash together with no such problem.
- **External inputs.** What enters the graph from outside it (a manual write to
  a FIFO, an external program) cannot be regenerated by any node, so at that
  boundary delivery is at most once; inside the graph, the guarantees start from
  the first message a node logs.
- **Messages read from a FIFO but not yet written to the input log** when a node
  crashes. The reader thread writes each message to the log when it arrives, so
  this window is only the time between taking a block from the FIFO and
  appending each of its messages. A message lost in that window is not
  recovered, since its sender considers it delivered, but the sequence numbers
  of G5 make the hole detectable (G8).
- **Stuck but alive.** A node whose brain thread is alive but blocked (infinite
  loop, deadlock) is not detected today: the heartbeat proves that its threads
  are alive, not that they make progress. Not a goal for now; an extension would
  be a progress counter in the heartbeat.
- **Not covered**: non-deterministic `process_data`, effects on external systems
  beyond "idempotent if repeated", Slurm, machine failure.
- **`--mirror`** (the debugging tap of a fifo, behind the frontend's "Watch
  FIFO") is not available in resident programs: declaring it aborts the load of
  the program, before anything is launched (decided and done on 2026-09-20).
  Resident processes keep their own input log.
- **A node that has finished for good** takes no part in later rounds, so the
  consistent cut of an epoch that starts after it finished has no checkpoint of
  that node: its channel to the others is empty and its last state is its final
  one. Localized recovery does not need it; a global rollback would have to
  treat it (see Future work).
- **A round that a newer one replaces** leaves the nodes that had not closed it
  without a checkpoint for its epoch, so that epoch has no complete cut. The
  round that replaced it does complete, at every node it reaches, and that is
  the cut that counts; localized recovery never uses a cut. It holds if the
  initiators start the same epoch (see Loose ends). Rounds started closer
  together than they take to complete keep replacing each other, and none
  completes until they stop, so the period of periodic snapshots has to be
  longer than a round.
- **A node that crashes again right after every relaunch** is not retried
  forever: after `MAX_RELAUNCH_ATTEMPTS` it is declared permanently failed and
  the escalation applies.

### Acceptance: how reliability is shown

Reliability is claimed only for what passes a **chaos test**: a reference
resident program with the shapes that matter (a fan-in node with more than one
input port whose `process_data` is sensitive to the order across ports, a cycle,
a source and a sink), run once with no failures and then repeatedly under
`kill -9` of random nodes at random moments (including several at once, adjacent
pairs, and moments in which a snapshot round is open), with the `Supervisor`
relaunching them. Pass criterion (reformulated on 2026-09-22: see below):
for each port the fan-in node reads, the messages it is seen to have
processed on that port, in a run's own trace, form exactly the sequence that
port's writer actually sent, in the order it sent them, with no duplicate and
no missing message. The run's full trace only has to be some interleaving of
those per-port sequences, never a byte-for-byte match against one frozen
reference run: which interleaving comes out, even with no failure at all, is
itself a race between independent writers that a single run does not pin
down uniquely, so comparing against one no longer means what it used to. The
exception follows from two limits of the Contract, after which a message can
be lost beyond repair: both endpoints of a channel crashed before either
reopened the FIFO, and a node killed with a message that it has read from a
FIFO but not yet written to its input log. A run that hits either passes if
it ends with an error of G8 that names the channel and the numbers of the
missing messages, in place of the reference result. What always fails is a
different result with no error (a message duplicated, lost or altered that
nobody reported) and a run that never ends and reports nothing. The harness
records when it kills each node and when that node has been relaunched, so
it knows which runs hit the first limit. The second cannot be seen from
outside, so a G8 error in a run that did not hit the first one is examined,
and it has to be shown to come from it and not from a fault of the replay.
The chaos test runs against real `debasher_exec` runs, not mocks.

**Why the criterion changed.** The original wording assumed the failure-free
run has a unique result, which the fan-in shape itself rules out: it is
"sensitive to the order across ports" on purpose, precisely to stress that a
crash's replay never reorders anything already accepted (G4), and that same
sensitivity means two clean runs, with no crash at all, can legitimately
interleave differently. Two ways to restore a well-defined pass criterion
were weighed: pacing the reference program's own writers so only one
interleaving could ever happen (rejected: it would stop stressing the real
race at the moment a node crashes, one of the highest-value timings to
cover), or checking each port's own sequence directly, which needs no
pacing and no frozen reference run at all. The second is what is described
above.

**Status (2026-09-22): the reference program, the no-failure baseline, a
single-node-kill driver, a channel-safe two-node-kill driver, an
engineered-gap driver for one adjacent pair, a random-timing driver for the
other adjacent pair and an open-round-kill driver are built and tested. Only
killing several nodes at once (see below) is left, and it is optional: what
motivated the kill/relaunch bookkeeping this section used to list here
turned out not to be needed by any piece actually built (see below).**
`test/engine/debasher_chaos_ref.sh` is the reference program: `fanin` (the
fan-in node) reads `ext`, fed from outside the program (`EXTERNAL_PORTS`),
and `loop_in`, fed by `loop`, which simply echoes back to `fanin` whatever
`fanin` sends it on `to_loop`, closing a 2-node cycle; on every message, from
either port, `fanin` forwards a copy to `sink`, tagged with the port it
arrived on, which is what makes `sink`'s own input log double as the run's
trace: G5's dedup already happens before a record is ever logged, so reading
that log gives the exact, ordered, once-only sequence the criterion above
needs, without any bookkeeping of its own. `fanin` is the program's only
initiator, triggered through the `Supervisor`'s manual trigger channel, fed
from outside.

`test/engine/test_chaos.py` (skipped unless `DEBASHER_RUN_CHAOS_TEST` is set,
since it is slow and disruptive on purpose: real `debasher_exec`, no mocks)
has six pieces so far. The "run once with no failures" step: 20 messages
through `ext`, a `start_snapshot` and a `shutdown` in the middle of the run,
the resulting trace checked against the criterion above. And a first
kill/relaunch piece, ten repeats of killing exactly one of `fanin`, `loop` or
`sink` at one random moment while 60 messages flow through `ext` on a steady
beat, alongside a periodic `start_snapshot`: the only shape that cannot touch
the Contract's "both endpoints of a channel crashed" limit, since a lone
kill always leaves every channel's other endpoint alive to hold it open, so
every repeat's trace must match the criterion exactly, with no G8 exception
expected. `sink`'s own trace is read by tailing its input log continuously
from before anything is sent, not by reading the log directory once after
the run: a checkpoint `sink`'s own relaunched incarnation takes right after
replaying its pre-crash log already covers everything in it, so pruning (see
"Log structure and record format") deletes that pre-crash segment no matter
how high `CHECKPOINT_RETENTION` is set, since retention counts an
incarnation's own epochs, not history from before a crash it never
checkpointed itself; tailing from the start captures every record in memory
well before any later pruning could remove it from disk. An external writer
across a crash of `fanin` needs the same kind of care for a different reason:
verified with a standalone fifo, not assumed, that a write attempted while
the reader is down always fails at once with no partial write (every payload
here is far under `PIPE_BUF`) and succeeds cleanly once retried on that same,
still-open fd after the reader comes back, but a value already buffered,
unread, when the reader dies is only safe for as long as some fd, anyone's,
stays open on that fifo: closing and reopening a fresh one per message loses
it the instant the fifo has zero open fds, even for a moment.

Killing this way also turned up a real, unrelated engine gap during ordinary
shutdown, with no crash involved: see the new Conformance status entry above,
"G2 is violated during an ordered shutdown when a downstream node has only
one pending port". Not fixed yet, so the kill/relaunch tests wait for the
pipeline to settle before asking for a `shutdown`, to keep validating what
they are actually meant to validate (recovery from a kill) without also
tripping that separate, already-recorded bug.

A second kill/relaunch piece kills `loop` and `sink` together, ten repeats,
each at its own independently chosen random moment (some seeds land the two
kills close to simultaneous, others stagger them across most of the run):
the only pair of killable nodes with no direct channel between them, `fanin`
being the other endpoint of every channel that touches either one, so this
still cannot touch the "both endpoints of a channel crashed" limit, the same
reasoning as the single-node-kill piece, and every repeat's trace must match
the criterion exactly, with no G8 exception expected here either. Its own
mutation check reused the single-node-kill piece's dedup fault (G5's
`envelope.seq <= accepted` loosened to `<`, on a scratch copy, never in the
repository) to confirm the criterion still catches an exact duplicate
reliably once two crash-replays are running close together in time, not
just one: the mutant was killed on all 10 repeats.

A third piece covers one of the two adjacent pairs that can touch the "both
endpoints of a channel crashed" limit: `fanin` and `sink`, which share
exactly one, one-way channel. Left to random timing this reference
program's nodes are fast enough that a real loss essentially never happens
(the limit's own mechanism only destroys what a relaunched writer's
checkpoint already counts as sent and was still unread in the fifo when
both crashed, and that backlog just does not build up on its own here), so
this piece engineers the loss on purpose instead of hoping for it:
`SIGSTOP` on `sink` freezes its reader without destroying anything yet, so
the fifo genuinely fills while `fanin` keeps writing to it; a `start_snapshot`
closes a checkpoint on `fanin` once that backlog exists, so it now counts as
"already sent" as far as `fanin`'s own recovery is concerned; `SIGKILL` on
both, back to back, destroys it for good before either relaunches. Ten
repeats, each varying only how long the backlog is left to build.

Every repeat ends in one of two shapes a real G8 violation is seen to take
in practice, both naming the channel: a clean one, raised the moment the
reader notices the jump itself, naming the exact missing sequence numbers;
and a numberless one, raised when a freshly relaunched reader reattaches to
a fifo whose writer never itself died (so no fresh `HELLO` ever excuses the
fragment) mid-message, at whatever byte offset the shared pipe's read
cursor already stood at. Once the gap opens, `sink`'s reader for that
channel dies on it identically on every subsequent relaunch (the same
durable hole is still there to rediscover each time), so it never gets
past it before giving up for good: the surviving trace is not "everything
except a hole in the middle", it is an exact, gapless prefix of the
channel's own sequence numbers, ending exactly where the gap begins,
confirmed against the numbers the error itself named when it named any.
Since detecting the gap at all depends on a live message actually arriving
to reveal it (G8's own mechanism, nothing raises on silence alone), the
driver keeps feeding well past the whole crash-loop-to-give-up window
instead of a fixed count, and, since the `Supervisor`'s own escalation
shuts `fanin` down the moment `sink` gives up, without waiting for the feed
to finish, the driver stops feeding at that point and checks the trace
against how much it actually got to send, not against the nominal amount.

A separate, incidental consequence of this same `SIGSTOP` technique,
observed occasionally (about 1 run in 10): the backpressure of `fanin`'s
own brain thread blocking on a write to the now-frozen `sink` can also
back up `fanin`'s OWN reader for `loop_in` long enough that `fanin`'s own
`kill -9` loses something it had already pulled off that fifo but not yet
logged, which is the other documented limit ("Messages read from a FIFO
but not yet written to the input log"), not the one this piece targets,
since `loop` itself is never touched. The driver accepts either outcome for
`fanin`, requiring only that this one, too, end in a detected G8, not a
silent one.

Built and run this way, the driver also turned up a new, real gap, not yet
investigated: see the new Conformance status entry above, "The
`Supervisor`'s own resolution after a node gives up may not complete".
Worked around the same way as the ordered-shutdown gap above: the driver
does not wait for `sup.finished` once `sink` has given up, only for the
reachable part of the graph to log as finished.

A fourth kill/relaunch piece covers `fanin` and `loop`, the other pair
sharing a channel (two, in fact: they are this program's only cycle), so
in principle also able to touch the "both endpoints of a channel crashed"
limit. Trying the engineered-gap piece's own construction on it first
(freeze one side, close a checkpoint on the other, kill both) showed the
limit is not reachable here, structurally, not just by bad luck: closing
any round on either of their shared channels needs both to be alive and
responsive, since each is the other's peer in the same cycle, so any
backlog built while one of them is down can never be covered by a
checkpoint that has actually closed (closing itself needs the down one's
cooperation), and on relaunch the sender always replays from an older,
already-drained checkpoint and resends that backlog, self-healing every
time. Confirmed with a real `debasher_exec` run: freezing `loop` left
`fanin`'s own round pending indefinitely, closing only once the
`Supervisor`'s own heartbeat-timeout relaunched `loop` on its own, well
past `HEARTBEAT_TIMEOUT_SECS`, over `fanin`'s own deliberate kill, at
which point `fanin`'s checkpoint closed over a position `loop` had, by
construction, already fully drained.

So this piece uses independent random timing instead, the same style as
the `loop`+`sink` piece: ten repeats, `fanin` and `loop` each killed at
their own independently chosen moment, and every repeat's trace must
still match the criterion exactly, with no G8 exception expected, because
the topology rules the limit out here, not chance. One rare failure (1 in
30 repeats, not reproducible on the same seed run again) showed `fanin`,
this program's only initiator, piling up several snapshot rounds faster
than it and a concurrently relaunching `loop` could close any of them,
each replacing the last, right as the periodic `start_snapshot` this
driver already sends kept firing through the relaunch; the run's final
`shutdown` then took over a minute to resolve. Not investigated further:
the driver now stops the periodic snapshots as soon as both nodes have
relaunched, instead of only right before the `shutdown`, so no more
rounds compete with whatever is still catching up; 30 repeats since, in
three separate runs, all clean.

A fifth kill/relaunch piece covers "moments in which a snapshot round is
open" from the top of this section directly: `fanin`, this program's only
initiator, is the only node with a genuine window between opening its own
round (the instant it relays a manual `start_snapshot` trigger) and
closing it (once `loop_in`'s marker completes the round trip through
`loop`), since every other node's own round closes atomically, in the
same step its one pending port's marker arrives, leaving nothing to land
a kill inside. Ten repeats: `loop` briefly `SIGSTOP`ped first (well under
`HEARTBEAT_TIMEOUT_SECS`, so the round trip cannot complete no matter how
long the window is held open, and short enough that the `Supervisor`'s
own heartbeat-timeout machinery never notices or interferes), `fanin`
killed at its own randomly chosen moment inside that window, `loop`
resumed. Confirmed, and built on, an ordinary (non-halt) round crash: see
the new Loose ends annotation below and the "A crash during a halt..."
Conformance status entry, both added by building this piece. Its own
mutation check needed two tries: the first mutant (an off-by-one on
`_last_epoch` when a checkpoint restores) survived, and turned out to be
equivalent, not a weak test, since `fanin` is both the node whose epoch
tracking was corrupted and the sole initiator deciding every later
epoch's number, so it silently skips the one poisoned number and never
notices; the second (a relaunched node's own barrier handling unable to
open any round beyond the very first one it ever sees) was killed, the
run hanging until the final `shutdown`'s own halt round timed out
waiting for `sup.finished`, confirmed on a single repeat rather than all
ten, since a hanging mutant makes every repeat slow.

The bookkeeping of when each node was killed and relaunched, once listed
here as still to build, turned out not to be needed by any piece actually
built. It was meant to answer, from recorded kill/relaunch timestamps
alone, whether a run's two chosen nodes had overlapping downtimes and so
could legitimately have touched the "both endpoints of a channel crashed"
limit. In practice every pair resolved that question a different way,
without ever needing the timestamps: `loop`+`sink` share no channel, so
the answer is always no, provably, with nothing to compute; `fanin`+`loop`
share a channel but cannot touch the limit either, also provably, since
closing a checkpoint on it needs both of them cooperating (see above); and
`fanin`+`sink` is engineered on purpose, so the answer is always yes, by
construction, not by measurement. What the criterion actually needs when a
G8 error does show up, examining it to confirm it is well-formed and
matches the trace, is `_find_g8_error` and its own cross-check
(`_assert_engineered_gap_trace`), already built for that piece and directly
reusable by any future one.

Not built yet, and optional rather than required to close this section:
killing several nodes at once (beyond a pair), the only reading of the
opening paragraph's own "several at once" left uncovered for this
reference program's small, 3-node set of killable nodes.

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

### Conformance status today: gaps between this contract and the code (2026-09-19)

Each one was verified by running the real classes, not only by reading the
code. The ones marked fixed give the date; the others are to be fixed before
any guarantee is relied on.

- **G2 was violated, fixed on 2026-09-20.** `DATA` arriving on a port that was
  still pending in an open barrier round was stored in `channel_state` but never
  reached `process_data` (sending 5 and then 7 through a fan-in node delivered
  only 7, with no crash involved), which contradicts G2 and classic
  Chandy-Lamport, which records the message and also keeps processing it. Only
  nodes whose round stays open across messages were affected (several input
  ports, or an initiator in a cycle). Now such a message is processed at once
  and a deep copy goes to `channel_state`; checked with a real `debasher_exec`
  run (5 and 7 through a fan-in node with a round open: it processes both, total
  12, where the previous code ended at 7).
- **G3 and G6 were violated, fixed on 2026-09-20.** A message processed after
  the snapshot (the node state is captured when the round opens) but before the
  round closes was logged in the segment of the round's own epoch, which
  recovery, and also resumption after a halt, skipped: live total 100, recovered
  total 0. Now the checkpoint stores a position in the input log, not the epoch
  of a log segment, and recovery replays every `DATA` record after it. Checked
  with tests in the words of the guarantees and with a real `debasher_exec` run
  in which a slow fan-in node was killed twice.
- **G3 was also violated for what was still waiting in the queue, fixed on
  2026-09-20.** A message was logged only when the brain thread reached it, so
  everything waiting in the inbound queue (which has no limit) was lost if the
  node crashed. Now every item is written to the log when it arrives, before the
  brain thread can see it.
- **G3 was also violated when the node had no checkpoint yet, fixed on
  2026-09-20 (found the same day).** `run()` replayed the log only if a
  checkpoint was restored, so a node that crashed before closing its first epoch
  lost everything it had received: checked with the real class, 3 messages in
  the log and no checkpoint, and the relaunched node processed 0. Now, with no
  checkpoint, recovery starts from the default state and replays the whole log
  (nothing is pruned before the first checkpoint).
- **G4 was violated, fixed on 2026-09-20.** The log was one file per port and
  the drain replayed port by port, so the order across ports was lost (processed
  `A1 B2 A3 B4`, replayed `A1 A3 B2 B4`). Now there is one input log per node,
  in queue order, and replay follows it.
- **G5 not implemented, fixed on 2026-09-22.** Replay after a crash re-emitted
  the outputs the node had already sent, and a running neighbor received them
  again (verified with a real run). Mechanism decided on 2026-09-20, built in
  six pieces between 2026-09-21 and 2026-09-22 (see the order of implementation
  in section 3): the sender numbers each channel's `DATA` and stores its
  counters in its checkpoint; the receiver drops a number it has already
  accepted, before logging or queuing it; a number it skips over is a real
  loss and raises loudly instead (G8); the checkpoint also carries what the
  writer thread had not yet written when a round captured, and recovery sends
  it again with the same numbers before anything else. Checked with a real
  run: a relay whose neighbor was still recovering had 4 of 8 messages still
  unwritten when a snapshot captured it; killed and relaunched, its neighbor
  received all 8, where without this piece those 4 would have been lost for
  good (reasoned from the same run: nothing else regenerates what a crash
  destroys in the outbound queue). `CLOSE` carries the sender's own last
  number, so a message lost right before a channel finishes for good is not
  silent either, since nothing else would ever reveal it.
- **G7 was partly violated, fixed on 2026-09-20.** A `FBPProcess` whose input
  writer sent `CLOSE` ended that reader thread and then stopped sending
  heartbeats, so a healthy consumer whose producer finished for good would have
  been declared down (measured with real runs: from the `CLOSE` on, the health
  check that the heartbeat sends on never said healthy again, and with a slow
  brain the gap opened while the brain still had a backlog before the `CLOSE`).
  Now the reader keeps reading after a `CLOSE`, so the heartbeat needs no
  special case (checked with a real `debasher_exec` run: the health check stayed
  true until the end of the run, 26 s after the `CLOSE`). A crash of the
  producer never did it: the reader stays, which the real run confirmed. The
  `Supervisor.run()` hang with a `MANUAL_TRIGGER_PORT` was fixed on 2026-09-20,
  with a regression test.
- **G6 was violated when a writer had finished for good, fixed on 2026-09-20.**
  A round waited for the marker of a port whose writer had said `CLOSE`, which
  never comes, and the marker of the next round ended the brain thread with a
  `ValueError`. Measured with the real class on a node of three ports: round 0
  open for good waiting for a and c, the brain thread dead at the marker of
  epoch 1, no checkpoint written. Now a closed port is not pending, and a real
  `debasher_exec` run of two producers that finish at different moments and a
  consumer that is killed and relaunched closes its rounds and recovers.
- **A trigger from the `Supervisor` did not close the initiator's round, fixed
  on 2026-09-20.** The channel from the `Supervisor` was read as a data port, so
  the initiator waited for a marker that never comes, and the `CLOSE` that a
  stopping `Supervisor` sends closed the channel for good, dropping the triggers
  of one relaunched by hand. Both checked with real fifos and then with a real
  `Supervisor`. Now the initiator lists that channel in `CONTROL_PORTS`.
- **A trigger, or a marker of another epoch, that reached a node with a round
  open ended its brain thread, fixed on 2026-09-20.** Both raised a `ValueError`
  that nothing caught. Measured with real processes: an initiator that is a
  root accepts two `start_snapshot` in a row, since each of its rounds closes
  at once, and the node downstream, with its round 0 still open, died on the
  marker of round 1 and never wrote a checkpoint. Now a newer round replaces the
  older one.
- **A relaunched node did not reconnect to its neighbors, fixed on 2026-09-20.**
  A reader ended at the first EOF and a writer whose reader had died got `EPIPE`
  and died, so a node that crashed and was relaunched was cut off from every
  neighbor and blocked forever in `open()`. Now every endpoint holds both ends
  of its FIFO, so a channel outlives the crash of either of its nodes, and every
  incarnation of a writer starts with a resync line that lets the reader drop
  the fragment that a killed writer may have left. Checked with a real
  `debasher_exec` run of a numbered source, a consumer and a `Supervisor`,
  killing with `kill -9` first the writer node and later the reader node: the
  `Supervisor` relaunched each, the other node was never touched, and across the
  reader's outage the consumer logged 630 consecutive messages, none missing and
  none duplicated. What a running neighbor still receives twice after a writer's
  crash is what G5 removes.
- **G2 is violated during an ordered shutdown when a downstream node has only
  one pending port: found on 2026-09-22 by the chaos test (see "Acceptance"),
  fixed and verified with real `debasher_exec` runs the same day (the third
  candidate below, and its own `debasher_stop_resident` tool, section 4).**
  `_open_barrier_round` sends the halt `BARRIER` on every output
  port as soon as a round opens, not when it closes, so an initiator whose own
  round stays open (waiting for a port that has not settled yet) has already
  forwarded the halt to every neighbor before it is done. A neighbor with no
  other pending port closes on that same `BARRIER` at once and halts, which
  stops its reader thread before the initiator finishes sending it whatever it
  still owes on that channel: nothing else is pending for the initiator, so it
  keeps processing and forwarding normally, exactly as G2 asks ("also while a
  snapshot or shutdown round is open"), but the neighbor is no longer there to
  receive it. No crash and no `kill -9` anywhere in this: a plain, no-failure
  ordered shutdown. Found with a real `debasher_exec` run of the chaos test's
  reference program (`test/engine/debasher_chaos_ref.sh`): `loop` was killed
  and relaunched shortly before the run's end, delaying the values it still
  had to echo back to `fanin` through the cycle; `shutdown` was requested once
  every value had been accepted into `ext`. Checked against the real input
  logs of all three nodes: `fanin`'s own log shows `loop_in` 52 to 60 arriving,
  in order, before the halt `BARRIER`, and forwards every one of them to
  `sink` (confirmed by `send_data` being called from `process_data` for
  each); `sink`'s own log has the halt `BARRIER` but not those 9 forwards,
  since they reached `to_sink` only after `sink` had already stopped reading
  it. Not specific to `EXTERNAL_PORTS` or to the cycle: any node whose only
  pending port settles while an upstream peer is still finishing a different
  branch through the same channel can lose whatever that peer sends
  afterward. Not designed: candidates include not closing a node's own round
  until every channel it will still write to during this round has actually
  drained (which needs the initiator itself to know when that is), or having
  a downstream node keep its reader open a little longer past its own halt to
  drain what is already in flight (which needs a second signal, since a
  `BARRIER` alone does not say "and nothing more is coming on this channel
  either").

  A third candidate, designed and implemented 2026-09-22 (`FBPProcess`,
  `engine/debasher_runtime_fbp.py`; see section 2's "Ordered shutdown" for
  the mechanism in full and the Glossary for "halted marker" and "stop
  signal"): treat a halt exactly like an ordinary snapshot at every node
  (take the checkpoint, keep running, keep reading), and move "when is it
  actually safe to stop" entirely outside the message protocol, to a stop
  signal an external actor sends whenever it decides to. Verified with two
  real `debasher_exec` runs
  (`test/engine/test_chaos.py::test_a_halt_keeps_every_node_running_until_an_external_signal_stops_it`,
  against the chaos test's own reference program, which has a `Supervisor`;
  `test/engine/test_halt_ref.py`, against a new, minimal reference program
  with none): in both, every node
  stays alive and keeps its heartbeat (where it has one) well after its own
  halted marker appears, and only exits, cleanly (`.finished` appears),
  once sent a real `SIGTERM`. Getting the stop signal to actually work
  surfaced a second, unrelated bug (found and fixed the same day, see
  section 2's "Ordered shutdown"): a single-pid signal never reached a
  resident process's own Python interpreter at all, only the wrapper script
  around it, which had no handler for `SIGTERM` of its own.

  What this closes: the specific self-stop-too-early mechanism the bug
  above depends on, since a node no longer decides on its own, from its own
  round closing, that it is done, and the external tool that actually
  drives a real program's ordered shutdown to completion now exists and is
  verified (`debasher_stop_resident`, section 4). Getting the tool itself
  working against a real program (not just against `FBPProcess` in
  isolation) surfaced one further, unrelated bug, also found and fixed the
  same day: a leaked `stdout`/`stderr` file descriptor that kept a
  `Supervisor`'s own wrapper script from ever finishing after it relaunched
  a node (section 4's "Relaunching a downed node"). `Supervisor`'s own
  escalation after a permanent node failure (section 4's "Escalation on a
  permanent node failure") now calls this tool too, closed 2026-09-22 (a
  separate paragraph there, kept apart since it needed its own design
  decision, `--keep-supervisor`, and surfaced its own further bug, a missing
  `DEBASHER_BINDIR`): this G2 entry is fully closed.

  Two things the tool had to get right, both now done, not just designed.
  First, it waits for every node's marker before sending the stop signal to
  any of them, not per node as its own marker appears: signalling early
  would race an upstream peer that has not finished sending yet,
  reproducing this same bug's shape one level out
  (`wait_for_every_halted_marker`, then
  `stop_every_node_and_wait_for_finished`, two separate passes over every
  node, `engine/debasher_stop_resident.sh`). A narrower
  residual window remains even so: a peer can still process and forward a
  little between its own marker and actually receiving the signal, which
  reduces to the Contract's own "both endpoints of a channel crashed" limit
  (see "Limits and non-goals"), not a new one. Second, the `out_backlog`
  caveat reasoned about above (a halted marker existing does not by itself
  prove the writer thread had already flushed everything to the real fifo):
  real runs, including several that kill and relaunch a node mid-flight and
  check the exact resulting trace afterward (`test/engine/test_chaos.py`'s
  already-committed kill/relaunch pieces, now ending through this same
  tool), have not surfaced this as an actual defect, consistent with G5's
  own replay-on-recovery already covering it regardless of the writer
  thread's state at the moment the stop signal arrives. Reasoned, not
  measured in isolation: nothing here specifically stress-tests this one
  interaction on its own.

- **The `Supervisor`'s own resolution after a node gives up may not
  complete: found on 2026-09-22 by the chaos test's engineered-gap piece,
  root-caused and fixed the same day.** After `sink` exhausted
  `MAX_RELAUNCH_ATTEMPTS` and was given up on, its escalation
  (`on_node_permanently_failed`, the version that sent `shutdown` to every
  `TRIGGER_PORT` initiator directly, since replaced, section 4's
  "Escalation on a permanent node failure") saw the still-
  reachable part of the graph resolve (`fanin` and `loop` both logged
  "finished cleanly"), but `sup.finished` (the marker the surrounding
  launch script writes once `Sup().run()` itself returns) was not seen to
  appear afterward, even 20+ seconds later, in two separate reproductions
  with a real `debasher_exec` run. First reasoned about, inconclusively
  (`_maybe_resolve`'s own two conditions looked like they should have been
  met), then actually root-caused while building the third candidate's own
  escalation (section 4's "Escalation on a permanent node failure"): a bare
  command name (`"debasher_stop_resident"`, and before it the same call's
  own bare `"debasher_stop"` fallback) relies on `PATH` already including
  `bin/`, which nothing sets for a launched process, so the escalation
  thread crashed on `FileNotFoundError` before it could do anything,
  silently (nothing joins that thread). Fixed by resolving the tool's
  absolute path from a new `DEBASHER_BINDIR` export
  (`debasher_builtin_sched::_launch`), the same pattern already used for
  `debasher_launch_process` via `DEBASHER_LIBEXECDIR`. Confirmed, not just
  inferred from the shared mechanism: rerunning the exact original
  scenario that found this gap
  (`test_fanin_and_sink_killed_together_over_an_engineered_gap_ends_in_a_recognized_g8_error`,
  unmodified apart from now also asserting on `sup.finished`) shows it
  appearing, reliably, across repeated runs.

- **A crash during a halt can leave the program permanently half-halted:
  the Loose ends worry of 2026-09-21 ("nobody sends it another
  `shutdown`"), confirmed with a real `debasher_exec` run on 2026-09-22 by
  the chaos test's open-round piece (see "Acceptance"), not fixed.**
  `fanin`, this program's only initiator, opens its own halt round the
  moment it relays the `shutdown` trigger, and that round only closes once
  `loop_in`'s marker completes the round trip through `loop`; killed in
  that window (`loop` briefly `SIGSTOP`ped first, so the round trip cannot
  complete before the kill), the relaunched `fanin` has no round open and
  nothing left to reopen it, since the `shutdown` that triggered it was a
  one-time message from an external actor, not something resent on a
  timer or on recovery. `loop` and `sink`, unaffected, both log "finished
  cleanly"; `fanin` never does, and `sup.finished` does not appear even 40
  s later. The same construction with an ordinary (non-halt) round instead
  does not hang: `fanin` simply forgets the open round on relaunch and a
  later marker reopens it, exactly as reasoned in Loose ends, confirmed by
  the same run (see "Acceptance" for the piece built on this case, since
  it is the one that actually recovers).

  This is the same class of problem as the G2 ordered-shutdown gap above,
  and the third candidate noted there (treating a halt exactly like an
  ordinary snapshot, with an external tool deciding when it is safe to
  stop by signal, outside the message protocol), now built (section 4's
  `debasher_stop_resident`), structurally keeps this from hanging the
  program forever even so: the tool's own `--timeout` bounds the wait for
  every halted marker regardless of why one never appears, and falls back
  to `debasher_stop`'s hard kill. What it does not do is retry: `fanin`
  crashing mid-halt still falls into the already-recoverable "crash
  during an ordinary round" case (the relaunched incarnation simply
  forgets the open round), but nothing here resends the one-time
  `shutdown` trigger the tool already sent once, so this specific case
  still ends in the hard-kill fallback rather than a graceful close.
  Not re-confirmed with a real run under the new mechanism.

## 1. Control envelope

Wire format: JSON Lines (one JSON object per line, `\n` as delimiter). Always
serializing via `json.dumps` guarantees that a `\n` embedded in the `payload`
comes out escaped, so the line delimiter is safe with any payload.

Three sibling types, each its own line/message (`BARRIER` never nests inside a
`DATA` message, so the reader thread can dispatch by looking only at `type`,
without interpreting `payload`):

```json
{"type": "DATA", "payload": <any JSON value>}
{"type": "BARRIER", "payload": {"epoch": <int>, "halt": <bool>}}
{"type": "INTERACT", "payload": {"command": <string>, "args": {...}}}
```

- `DATA.payload`: free-form, whatever the business logic wants;
  `process_data(port_name, packet)` (section 2) receives it already
  deserialized.
- `BARRIER.payload.epoch`: identifies the snapshot round; enough for the
  initiator (section 2's Chandy-Lamport subsection) to recognize, in a cycle,
  that the marker coming back through its own input port is its own (no need to
  carry the initiator's identity).
- `BARRIER.payload.halt`: reuses the same `BARRIER` as an ordered shutdown
  (section 2's Ordered shutdown subsection) instead of a snapshot.
- `INTERACT.payload.command`/`args`: an open catalog, extended as needed by
  whichever sections trigger it (`start_snapshot`, `shutdown`, `heartbeat`,
  `checkpoint_saved`, ...).
- No `port_name` field: each reader thread (section 2) already knows which port
  a message came from by construction (it is dedicated to that FIFO); it gets
  attached once the message enters the in-memory internal queue, not in the wire
  format.

**Changes decided on 2026-09-20.** Two more control types, both with an empty
payload: `CLOSE`, sent by a writer when it has finished for good (a halt sends
none), and `HELLO`, sent as the first line of every incarnation of a writer (the
transport decision of section 5). **Both are implemented** (step 2 of section
3): the reader thread consumes `HELLO`; `CLOSE` is handed to the brain thread,
in order, and the reader then drops whatever follows it (a `Supervisor` reader
delivers it). `DATA` will gain a sequence number per channel, assigned by the
sender, as a sibling of `type` and `payload`:
`{"type": "DATA", "seq": <int>, "payload": <any>}` (G5 in the Contract, section
3; **not yet implemented**). The reader still never looks at `payload`.

**Channel topology** (important: `DATA`/`BARRIER` and `INTERACT` do NOT share a
channel):

- Between business processes (`FBPProcess`), the normal FBP graph channels carry
  `DATA` in normal operation, and `BARRIER` interleaved when a snapshot/shutdown
  is in progress; this is how Chandy-Lamport propagates the marker: each node
  forwards it through its own output ports, the same ones it uses for `DATA`,
  never "upward" to anywhere else.
- Between each node and the supervisor, a separate channel (heartbeat) that only
  carries `INTERACT`: a single input port per node (not two), multiplexing
  `{"command": "heartbeat"}` and
  `{"command": "checkpoint_saved", "args": {"epoch": ..., "path": ...}}`
  (section 2's Checkpoint persistence subsection) on the same channel; there is
  no real contention between the two (lightweight, infrequent messages), and
  separate ports would only double the supervisor's manual wiring for no
  benefit.
- The supervisor never sees a `BARRIER`: it does not take part in the barrier
  protocol (section 2), it only speaks `INTERACT`.

## 2. Base class `FBPProcess`: DONE, implemented and tested (`engine/debasher_runtime_fbp.py`)

- **Where the code lives**: `engine/debasher_runtime_lib.py` is the module that
  a resident process's heredoc imports
  (`from debasher_runtime_lib import FBPProcess`, or `Supervisor`), and no
  source gets prepended into the heredoc itself. It began as the one file that
  held all of the code, and on 2026-09-20 the code was split (a pure move,
  checked line by line, with no change of behavior) into modules of their own,
  one layer each, where every module imports only from the ones before it:
  `debasher_runtime_envelope.py` (the wire format of section 1),
  `debasher_runtime_transport.py` (argv parsing, the fifo endpoints and
  `_PortWorker`), `debasher_runtime_inputlog.py` (`_InputLog`, section 3),
  `debasher_runtime_fbp.py` (`FBPProcess`) and `debasher_runtime_supervisor.py`
  (`Supervisor`, section 4). `debasher_runtime_lib.py` keeps
  `DEBASHER_SHUTDOWN_TOKEN`, a Python mirror of the Bash constant, and
  re-exports every name that it offered before, so nothing that imports it
  depends on the layout. All of them are `python_PYTHON`-installed per
  `engine/Makefile.am`, in the same directory, which is the one that the
  heredoc's `sys.path` line (see below) already adds. A test that patches a name
  has to patch the module that looks it up (for example `_write_all` in
  `debasher_runtime_inputlog`), since a patch on the re-exporting module changes
  nothing for the code that was moved.
  - **Known gap, fixed**: `import debasher_runtime_lib` used to only work from a
    Python file built through `engine/Makefile.am`'s `.py:` suffix rule, which
    prepends
    `sys.path.append("$(pythondir)")`/`sys.path.append("$(pkgpythondir)")`. A
    heredoc runs as `python3 -c "<text>"` (`debasher::_create_heredoc_func_body`
    in `engine/debasher_lib_programs.sh`), which does not go through that suffix
    rule, so it did not get that `sys.path` extension. Fixed by prepending the
    same `sys.path.append(...)` ahead of a Python heredoc's own text.
- **Port declaration**: a subclass declares its ports as class attributes,
  `INPUT_PORTS`/ `OUTPUT_PORTS` (lists of option names, e.g.
  `INPUT_PORTS = ["inf"]`). `FBPProcess` parses `argv` generically when it is
  built, into a `self.opts` name -> value dict (the engine's existing
  `-optname value` CLI
  convention, untouched); `INPUT_PORTS`/`OUTPUT_PORTS` tell it which of those
  entries are FIFO paths to open reader/writer threads on. Any other option
  (e.g. a plain `-threshold` value) stays available in `self.opts` with no
  special handling. `CONTROL_PORTS` names which of the `INPUT_PORTS` carry only
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
  (rebuilding external resources, see the Startup sequence subsection below).
- **Generic barrier logic** (valid for 1 or N input ports): on receiving the
  first `BARRIER` marker for an epoch (on any input port, or as the initiator),
  capture state and forward the marker on every output port; track the set of
  input ports still pending (marker not yet received) for that epoch. While any
  are pending: record a copy of the `DATA` arriving on those still-pending ports
  (that recorded set is the state of that channel) and also process every
  `DATA`, on any port, normally, as usual (what arrives after a port's marker
  belongs to the next epoch). Until 2026-09-20 the `DATA` of a pending port was
  only buffered and never processed, which lost it. Once every input port's
  marker has arrived, or its writer has said `CLOSE`, the node's part of the
  snapshot is complete.
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
  ignored, it never aborts the process (the command catalog, section 1, is
  deliberately open-ended).
- **Logging**: `FBPProcess` exposes a preconfigured `self.log` (Python's stdlib
  `logging`), same pattern as the existing `dispatch` process in
  `data/programs/dynamic_fanout_dispatcher.py` (stderr output, format including
  thread name, useful here since the process is inherently multi-threaded). The
  base class itself logs its own lifecycle events (thread start/stop, barrier
  epoch open/close, checkpoint saved, heartbeat) with it, the natural successor
  to the `echo` statements `data/programs/debasher_cycle*.sh` use today for
  visibility. Level is configurable via a plain `-log-level` option, declared by
  the module author in `_explain_opts`/`_define_opts` exactly like any other
  option (same convention `debasher_dynamic_fanout_fifos.sh` already uses): no
  new engine mechanism, it is just another entry in `self.opts`; a sensible
  default applies if the module does not declare it.
- **Periodic self-triggered snapshots (opt-in)**: nothing otherwise ever closes
  an epoch on its own; without this, the input log's safety cap (section 3)
  becomes the normal failure mode instead of an actual safety net for any
  `resident` program with no external actor triggering `start_snapshot`
  periodically, `Supervisor` or not. A timer thread, gated by a
  `SNAPSHOT_INTERVAL_SECS` class attribute/option (`None`, disabled, by
  default), that calls the exact same internal barrier-starting logic
  `start_snapshot` uses directly, bypassing the `INTERACT` channel entirely
  since it is an in-process trigger, not a message. The module author enables it
  only on whichever node it has already established is a valid initiator (see
  the Chandy-Lamport subsection below). Works identically whether or not a
  `Supervisor` is present; a `Supervisor`, if present, can still trigger
  `start_snapshot` on demand independently; the two are not mutually exclusive.

### Defining a node

A node is written as a class that derives from `FBPProcess`, in the Python
heredoc of a process of a resident program. The engine only checks, without
importing anything, that the heredoc has a top-level class deriving from
`FBPProcess` or `Supervisor` (`debasher::_classify_resident_process_role`). It
never instantiates it: the heredoc itself creates the object, which parses the
options of the process from `argv`, and calls `run()` (read from the engine's
code, and checked with a real `debasher_exec` run on 2026-09-21).

The class declares its ports (`INPUT_PORTS`, `OUTPUT_PORTS`, `CONTROL_PORTS`,
`EXTERNAL_PORTS`) and redefines four hooks. Each runs on a known thread, which
is what lets the framework keep the state that a node captures in step with
what it has sent:

- `process_data(port_name, packet)` runs on the brain thread, once for each
  `DATA`, in the order of the input log, and on the thread that called `run()`
  while the node replays that log. It is the only place from which a node sends,
  with `send_data(port_name, payload)`, which raises anywhere else.
- `capture_node_state()` runs on the brain thread, when a round opens.
- `restore_node_state(node_state)` and `initialize_runtime()` run on the thread
  that called `run()`, before any other thread starts. They cannot send.

No hook runs when nothing arrives: a node acts only in reaction to what it
receives (see "source" in the Glossary), so whatever starts the activity of a
program is written from outside into an input port. A module that needs several
inputs together keeps what it has received in its node state and decides in
`process_data` when it has enough, because the framework delivers each message
as it arrives, with no join across ports.

How a node finishes for good is not defined yet: `run()` returns only after a
halt, and a halt sends no `CLOSE`.

### State capture and checkpoint schema

- `capture_node_state()`: only serializable logical state, never runtime
  resources (connections, sockets, file handles); those are rebuilt by
  `initialize_runtime()` instead, see the Startup sequence below.
- Channel state: a copy of the `DATA` that arrives on a still-pending port
  during an open barrier round (the generic barrier logic above) is saved as the
  checkpoint's own `channel_state` field
  (`_save_checkpoint(epoch, node_state, channel_buffers, capture_pos)`).
  **Not currently read back by anything**: on restore, only `node_state` is
  passed to `restore_node_state()`; whether `channel_state` is meant purely for
  external inspection/audit of a consistent global snapshot (per the
  introduction's second goal) or is a real gap is flagged in the Loose ends
  section below, not resolved here.
- The node state is stored under `node_state` (renamed from `state` on
  2026-09-20, to tell it from `channel_state`; the hooks `capture_state()` and
  `restore_state()` became `capture_node_state()` and `restore_node_state()`,
  since they handle nothing else). A checkpoint written under the old key fails
  to load with a `KeyError`, and a module that still defines the old hooks fails
  at its first round with `NotImplementedError`: the branch is not released, so
  there is no compatibility code.
- Schema version: `CHECKPOINT_SCHEMA_VERSION` class constant, checked in
  `_load_latest_checkpoint` before `restore_node_state()`; a mismatch raises
  `ValueError`, a real incompatibility to fail on loudly, not something to
  silently paper over by trying an older checkpoint.
- **Since the input-log redesign of section 3**: the checkpoint also stores
  `capture_pos` and `closed_ports` (done); `out_seq` and `last_seq` will join
  it with the sequence numbers. `channel_state` is a copy of what arrived on
  pending ports, which is also processed.

### Startup sequence: `run()`

There are no two distinct paths ("clean start" vs. "recovery") inside the
process; it always looks for the most recent available checkpoint; if there is
none, it starts with default values. The distinction between "first time" and
"recovery" is determined externally by whether checkpoint files exist or not,
not by a decision the process itself makes.

Single sequence, implemented exactly this way in `run()`: open every FIFO by
known name -> look for the most recent checkpoint -> (if found)
`restore_node_state()`, otherwise default values -> `initialize_runtime()`
(always invoked, same code whether or not state was restored) -> open the input
log and replay it after the checkpoint's `capture_pos`, all of it if there
was no checkpoint (section 3) -> `start_threads()` (starts every worker thread)
-> wait until told to stop -> stop every thread. The FIFOs come first because a
node holds a FIFO only from the moment it opens it, and restoring and replaying
can take a while: if a neighbor that was the only holder of a FIFO crashed
during that time, what it had sent would be destroyed with it.

**Important consequence**: launching a process for the first time and
relaunching it after a failure are the same operation, with no distinction. The
supervisor does not need to know whether it is starting the topology or
recovering a downed node; in both cases it simply runs the same process script,
and it is the process itself that decides what to do depending on whether it
finds a checkpoint in its folder or not. This also simplifies section 5
(recovery): no special "recovery mode" logic is needed in the supervisor, only
failure detection and running the script; the rest (looking for a checkpoint,
restoring it or not, how much of the log to replay) is resolved by the process
itself, exactly as on any startup.

**Resetting checkpoints as an external operation, not yet built**: to force a
clean start, it should be enough to delete (or move) the node's checkpoint
folder before launching it; no flag or special logic needed inside either the
process or the supervisor to distinguish the case. A simple auxiliary script
(deleting checkpoints for every node of the topology) would cover restarting the
whole system from scratch; noted here as a real gap, not yet written (see
section 7, Future work).

### Chandy-Lamport barrier propagation

- **Done on 2026-09-20 (first step of the redesign decided in section 3)**: a
  `DATA` arriving on a port whose marker has not arrived is processed at once,
  as any other, and a deep copy goes to the round's `channel_state`; before, it
  was diverted and never processed. A port whose writer has said `CLOSE` leaves
  the round's pending set, or is left out of it if it had closed when the round
  opened (done on 2026-09-20, step 4.4).
- The trigger reaches a valid node as initiator via `INTERACT` (the
  already-existing interactivity/heartbeat channel), not via a new connection.
  Done, see the `INTERACT` logic above.
- With cycles: the initiator waits for the marker to come back through its own
  input port before closing its part of the snapshot. Done, tested end-to-end
  with a real 2-node cycle
  (`test_initiator_in_a_cycle_waits_for_its_own_marker_to_return`).
- Without cycles: the initiator must be a root; if it has no input ports,
  it closes its part instantly. Done, tested
  (`test_a_root_node_with_no_input_ports_closes_instantly`).
- Control ports are left out of every round, whoever opens it: a command is not
  the marker of the port that carries it (a round opened by a command starts
  with no port counted as arrived), the `Supervisor` takes no part in the
  barrier and never sends one, and a node with a control port must also close
  the rounds that a peer starts. Done on 2026-09-20 (step 4.5); before it, an
  initiator whose only input was the channel of the `Supervisor` opened its
  round, forwarded the marker and waited for ever, and a node with a data port
  and a command port never closed a round that started elsewhere.
- Rounds do not overlap at a node (done on 2026-09-20, step 4.6). A marker of a
  newer epoch that reaches a node while an older round is open replaces it: the
  older round is abandoned, and the node captures again at the newer marker (a
  later capture would include messages that the sender had sent after its own,
  and holding back the port would break the order of the input log) and forwards
  the newer marker. A halt is never replaced by a snapshot, and a marker of an
  older epoch, or of a round that is over, is ignored. A trigger that finds a
  round open does not start another: a `start_snapshot` is ignored, since the
  round in progress takes the snapshot; a `shutdown` replaces an open snapshot
  and starts the halt at once; a `shutdown` that finds a halt open, and any
  trigger once the node has halted, are ignored. Before this, both a marker of
  another epoch and a trigger raised a `ValueError` that nothing caught, which
  ended the brain thread.
- **Not yet done**: checking that the node chosen as initiator can actually
  reach every other node (the graph is strongly connected from that node) before
  it is ever allowed to be used as one: no validation code exists for this
  today; a module author enabling `SNAPSHOT_INTERVAL_SECS` or wiring a
  `Supervisor`'s trigger to the wrong node would currently fail silently (the
  round would simply never close for the nodes it can't reach) rather than being
  told the topology is invalid.

### Ordered shutdown

- Same `BARRIER`, with the `halt=True` flag. Done, see the generic barrier logic
  above and `_on_epoch_closed`'s `halt` handling.
- Closing a halt's epoch has no effect of its own (changed 2026-09-22, see the
  Glossary's "halt" and "Conformance status"'s G2 entry): the node keeps
  running, exactly like after any other round. `_on_epoch_closed` only sets
  `self._halted` (blocks `_start_barrier_round` from opening a further one,
  keeping the checkpoint sequence frozen at this epoch for the rest of this
  incarnation) and writes the halted marker (`_write_halted_marker`).
- What actually ends `run()` is a stop signal, not a round closing. Done:
  `run()` installs a `SIGTERM` handler (`_on_stop_signal`) on the main thread
  only (a background-thread caller, every test that drives `run()` this way,
  has no real signal to install one for, and `signal.signal()` raises off the
  main thread; those tests set `_stop_requested` directly instead, the same
  way other tests simulate an external `INTERACT` arriving), then waits on
  `_stop_requested` before calling `stop_threads()`. Deciding when to send
  that signal is external to `FBPProcess` by design (see "Conformance
  status"'s third candidate, and section 4's own `debasher_stop_resident`
  subsection for the tool that actually does): typically once every node's
  halted marker exists, but nothing here enforces that, or requires a halt
  to have happened at all.
- A halt sends no `CLOSE`, and neither does any other stop signal. Done:
  `run()` always calls `stop_threads(close=False)`, unconditionally, once its
  wait on `_stop_requested` returns. `CLOSE` says that a writer has finished
  for good, and a node that got a stop signal, whether or not it ever
  halted, may be resumed later: had it sent `CLOSE`, the reader at the other
  end could keep it in its input log after its `capture_pos` (measured, see
  section 3), and a resume would take the node for a finished one. A node
  that ends some other way (not through `run()`) still gets `stop_threads()`'s
  own default, which does send `CLOSE`.
- The signal has to reach the node's own process, not just the process group
  leader `debasher_stop` and `.id` already agree on: found 2026-09-22, not
  something `FBPProcess` can fix on its own. `debasher_builtin_sched::_launch`
  backgrounds a generated script as its own process group leader (`pgid ==
  pid`, the pid in `.id`), and that script's own pipeline
  (`debasher_builtin_sched::_execute_funct_plus_postfunct`) forks at least one
  subshell of its own to run the process function, so a resident process's
  own Python interpreter sits below the pid in `.id`, not at it. A plain,
  single-pid `SIGTERM` there only reaches the wrapper script (which has no
  handler and dies at once, never reaching the line that writes `.finished`),
  orphaning the Python interpreter, which never receives anything and keeps
  running. Fixed the same day: a stop signal has to target the whole process
  group (`os.killpg`, the same group `debasher_stop` already reaches with
  `SIGKILL`, see `debasher::_stop_pid`), and the wrapper script itself has to
  survive that same broadcast to still write `.finished` once its own child
  actually exits, which is what `debasher_builtin_sched::_print_script_trap`
  (`trap '' TERM`, the first thing `_create_script` writes into the generated
  file) is for. A hard kill (`SIGKILL`) cannot be trapped and is unaffected.
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

### Checkpoint persistence

- Location: `__exec__/<process_name>/checkpoints/`, a dedicated directory (not
  loose files mixed in with
  `<process_name>.{finished,id,opts,sched_out,stdout}`, which already exist
  today under `__exec__/<process_name>/`). Done, `_checkpoints_dir()`.
- Atomic write: temporary file + rename. Done, `_save_checkpoint()`'s
  `os.replace`.
- Named by epoch; on startup, load the highest valid epoch. Done,
  `_load_latest_checkpoint()`.
- Retention: keep the last few, discard the rest. Done, `CHECKPOINT_RETENTION`
  (default 3), `_prune_old_checkpoints()`.
- Lightweight notification (epoch + path) to the supervisor (never resend the
  whole blob over the channel). Done, `_on_epoch_closed()` sends
  `INTERACT {"command": "checkpoint_saved"}` to `SUPERVISOR_PORT` if set.
- The process always looks for the most recent checkpoint on startup; it does
  not distinguish "first time" from "recovery" by itself. Done, see the Startup
  sequence above.

## 3. Input log: DONE, implemented and tested (`engine/debasher_runtime_inputlog.py` and `engine/debasher_runtime_fbp.py`)

The input log replaces an earlier design that logged a message only when the
brain thread reached it. That design had five verified faults: everything
waiting in the inbound queue (which has no limit) was lost if the node
crashed; a barrier round diverted the `DATA` of a pending port so that it
never reached `process_data`; the log was one file per port and epoch, so the
order across ports was lost on replay; a message processed after the
snapshot but before the round closed was logged in a segment that recovery
skipped; and a node that crashed before closing its first epoch replayed
nothing. All five were verified with the real classes and are fixed, listed
in the Contract's conformance status. This section describes the design as
built, organized by topic; the order in which it was actually built, with
its tests and its real runs, is "Order of implementation" below.

(Placed right after `FBPProcess` rather than near checkpointing/recovery, and
before the `Supervisor` class: `FBPProcess` itself already needs this to
replay its own log on restart, and `Supervisor`'s design, next, can build on
it too.)

### Log structure and record format

One input log per node, in `<execdir>/log/`, not one per port: everything
that arrives at a node (`DATA`, `BARRIER`, `INTERACT`, `CLOSE`) is written to
it, in the order the brain thread processes it. That order is guaranteed by
one lock, shared with pruning (see below), that makes appending the record
and queuing the item for the brain thread a single step: measured with six
reader threads, 0 of 120000 positions differed with the lock, nearly all did
without it. Only `DATA` is replayed.

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
concatenation, not re-encoded: measured, building a record of about 100
bytes takes 0.18 microseconds this way and 5.5 with `json.dumps`, and one of
about 1 KB takes 0.27 against 8.2, at a cost of 28 more bytes per record. So
the critical section that writes it stays short, every line is still valid
JSON, and a `DATA`'s `seq` (G5) travels inside `env` with no change to the
record format. Each record is written with one `os.write` to an `O_APPEND`
descriptor (looped over partial writes), never through a buffered file
object: measured with real `kill -9`, a buffered `f.write` without `flush`
lost acknowledged records in 98 of 100 kills (3751 records in all), while
`f.write` plus `flush`, and `os.write`, lost none (`os.write`: none in 1300
kills).

A record counts only if its line ends in a newline and parses as JSON, so an
unterminated last line, a torn tail left by a process killed in the middle of
a write, is ignored on replay. A torn tail is real at any record size,
measured with real kills: 1 of 300 at 100 bytes, 6 of 300 at 1000, 11 of 100
at 4000 and at 5000, 0 of 100 at 64 KiB and at 1 MiB, 49 of 100 at 16 MiB.
That is why a new incarnation never appends to an existing segment, only
starts a new one: a reader thread appending behind an existing fragment
would bury it in the middle of the file, where replay rejects it, instead of
leaving it as the torn tail of its own segment. After any failed append
(measured with a real short write via `RLIMIT_FSIZE`: the third record wrote
50 bytes and raised `EFBIG`, the fourth failed too, leaving a fragment) the
log refuses more appends until the process restarts: every reader thread
dies with the same error, the heartbeat stops and the `Supervisor`
relaunches the node.

### Arrival and positions

A reader thread hands what it decodes to `_on_arrival(tag, envelope, line)`
instead of putting it on the inbound queue itself. `FBPProcess` overrides it:
under one lock it appends the record to the log, which assigns it its
position, `pos`, then puts `(pos, tag, type, payload, seq)` on the queue, so
that position order is processing order (checked with six reader threads on
real fifos and 1500 messages: the positions the brain thread saw were exactly
1 to 1500 in order, and fail when the lock is removed). The base class, used
directly only by the `Supervisor`, is unaffected: it puts `(tag, type,
payload)`, with no position.

Every queued item gets a position, starting at 1; `HELLO` never reaches the
queue. Whatever starts a round from inside the node, such as a future
snapshot timer, goes through the same hook, so `capture_pos` (see the
Glossary) is always defined; 0 means that nothing had been processed yet.

### The checkpoint's own bookkeeping

Besides `node_state` and `channel_state`, a checkpoint (schema version 2)
holds the position, `capture_pos`, of the item whose processing captured the
node state, taken when the round opens, not when it closes. `closed_ports`
(the input ports whose `CLOSE` the brain thread had processed by then, see
"`CLOSE` and closed ports" below), `out_seq`, `last_seq` and `out_backlog`
(the sender's and receiver's own G5 bookkeeping, see the Contract and the
"State variables, at a glance" table in the Glossary) joined the same
version later, since the branch is not released and no compatibility code is
kept: a checkpoint of schema version 1, or one missing a field this class
now requires, is refused with an error.

### Recovery: startup and replay

A relaunched node's startup (`run()`, section 2) opens its FIFOs, restores
the latest checkpoint if there is one, calls `restore_node_state()` and
`initialize_runtime()`, opens the input log and replays it, then starts its
threads. Opening the log recovers what earlier incarnations left: `next_pos`
is `max(last complete record, capture_pos) + 1`, found by reading only the
last segment that has a complete record; a segment with no complete record
(only a torn fragment) is deleted at startup, since the next record would
reuse its position and collide with its name.

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

### Pruning and the size cap

After each checkpoint is saved, whole segments other than the active one are
deleted once the next segment starts at or below the `capture_pos` of the
oldest retained checkpoint plus one; that value is read from the oldest
retained checkpoint's own file on every round (measured: about a quarter of
the cost of writing it, 12 ms for 0.9 MB, 115 ms for 9.3 MB and 1.16 s for 95
MB against 63 ms, 477 ms and 4.9 s), so no state is kept in memory for it. A
checkpoint that cannot be read aborts the prune with an error. Pruning runs
on the brain thread, under the same lock as an append.

`INPUT_LOG_MAX_BYTES` (100 MiB by default) is the cap on every segment of a
node's log together, kept in memory so that checking it costs nothing
(before, every message listed the directory and called `stat` on every
file). It is a safety net, not the normal way old history goes away, which is
pruning: exceeding it raises in the reader thread, before anything is
written, like any other death of a thread, and should never trip in ordinary
operation, since it would mean that no epoch has closed in a long time, which
the periodic snapshots of section 2 are there to prevent.

### `CLOSE` and closed ports

`CLOSE` means that a writer has finished for good, and only that; a halt
sends none (section 1). A reader hands it to the brain thread like any other
item, so it is logged, and then keeps reading but drops everything that
follows: nothing after it is decoded, logged or queued, and the first such
line warns, once per port. The reader does not end on a `CLOSE`, for two
reasons found with real runs before this was decided: a reader that ended
left the heartbeat unhealthy for good once its producer finished, and a node
that sent `CLOSE` and was later relaunched filled its peer's pipe with
nobody reading, since the old reader was gone. Dropping instead of ending
solves both. A control port (section 2) is the exception: its reader goes on
delivering what follows a `CLOSE`, and the `CLOSE` is neither recorded nor
restored, since its writer, such as the `Supervisor`, may come back.

`closed_ports`, sorted, is the checkpoint field that lists the input ports
whose `CLOSE` the brain thread had processed at the capture, that is, those
with a `CLOSE` record at a position at or below `capture_pos`: taken at the
same moment and on the same thread as the node state and `capture_pos`, by
the order in which the brain thread processes the items, not by what the
reader threads have already read, since they run ahead of it. Two other
definitions were considered and rejected, reasoned with a node of three
ports: a closes before a round opens and c closes while it is open, with a
message of c in between. Neither "what the reader threads have logged by
then" nor "what is closed when the round closes" agrees with what the
checkpoint's own `capture_pos` reflects, and both would leave the checkpoint
saying that c is closed while a message of c still lies after `capture_pos`
and is due to be replayed. The definition that is used is what lets replay
demand that no `DATA` record ever follows the `CLOSE` of its port, an error
that means the log or the checkpoint is corrupt. Recovery restores the set
and adds the port of each `CLOSE` record after `capture_pos`; the readers of
the ports that are then closed start already dropping what follows, so a
relaunched node behaves like the incarnation that read the `CLOSE`. A
`CLOSE` between the capture and the close of a round is not stored in the
checkpoint file, the same as any other item that arrives then: it is history
after the cut, and recovery finds it in the log.

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
channel state. What a module sees does not change: `capture_node_state()`
and `restore_node_state()` handle the node state and nothing else, and no
hook tells the module about a `CLOSE`.

### Sequence numbers (G5) in the input log

The mechanism itself, and the guarantee it gives (G5), are in the Contract;
what follows is specific to how the input log carries it. A `DATA`'s `seq`
travels inside its record's embedded `env`, with no change to the record
format (see "Log structure and record format" above). The receiver's own
counters, `last_seq` and the reader threads' `_accepted_seq` (Glossary), are
rebuilt at startup from the checkpoint plus the log: `_accepted_seq` starts
at the checkpoint's `last_seq` and replay advances it, scanning the numbered
`DATA` after `capture_pos`, to what the reader threads had already accepted
before the crash, whether the brain had processed it or not.

What is left uncovered: the window between a reader thread taking a block
from the FIFO and appending each of its messages. A message lost there is
not recovered, since its sender considers it delivered, but the jump in the
sequence numbers detects it (G8).

Rejected alternatives: a bounded inbound queue (the reader still consumes
blocks of up to 64 KiB from the FIFO, unbounded); a log at the sender with
acknowledgements (would need coordination and deletion between two
processes); a second log with the order of processing (only needed if
something reorders messages, and nothing does); accepting the loss outright
(it would happen exactly when a node is busy, the worst time for it).

### Order of implementation

Agreed on 2026-09-20: one step at a time, each with tests, a mutation check
(see Acceptance) and a real `debasher_exec` smoke test.

  1. The barrier processes and records a copy (G2). **Done 2026-09-20**:
     `_brain_loop` processes every `DATA` and keeps a deep copy of the ones on a
     pending port; five new tests state the guarantee (they fail on the previous
     code); a real run with two sources and a fan-in node, a round open while
     `5` then `7` arrive, ends with total 12 where the previous code ended
     with 7.
  2. The envelope types `CLOSE` and `HELLO`, and the transport with ghost
     connections in `_PortWorker`, including the `Supervisor` adaptation, a
     regression test for `Supervisor.run()` and a smoke test of crash and
     relaunch between two nodes. **Done 2026-09-20**: `start_threads()` opens
     every fifo without waiting for a peer, readers ended on `CLOSE` (never on
     EOF; not at all for `Supervisor`; a `CLOSE` no longer ends them, see 4.2
     below) or on `stop_threads()`, which wakes them through their own ghost
     write end; writers send a resync line first and `CLOSE` last, are daemons,
     and are abandoned after a bounded wait if their peer is down and the pipe
     is full; the reopen-after-EOF machinery of `Supervisor` is gone. The engine
     suite has 152 tests (the new ones fail on the previous code where they can)
     and was repeated 15 times without a failure; the real run is the one
     described in section 5.
  3. The input log written at arrival, positions, recovery, pruning and the
     checkpoint schema (G3, G4, G6). **Done 2026-09-20.** Split into three
     pieces (agreed 2026-09-20):
     - 3.1 The log as a component, `_InputLog`, not used by `FBPProcess` yet.
       **Done 2026-09-20**: segments named by their first position, records,
       torn tails, rotation, recovery of the next position, replay with its
       checks, pruning by position, byte accounting with the cap, and the
       refusal of appends after a failed write. 40 tests, among them a real
       `kill -9` of a child process that appends (12 incarnations per run, about
       5% of the kills left a torn tail, and none lost a record whose append had
       returned). Checked with a real `debasher_exec` run too: a process that
       appends to its log, killed by process group and relaunched three times
       with the engine's own launcher, left 32930 records, consecutive from 1
       with intact payloads, and the next position was the right one.
     - 3.2 Positioned arrival. **Done 2026-09-20**: the reader threads take the
       position and queue under one lock, through an arrival hook that the
       `Supervisor` leaves as it was; the brain thread remembers the position of
       the item it processes; the checkpoint has schema version 2 with
       `capture_pos`, taken when the round opens; and a restored checkpoint
       makes the numbering go on after it. The old log still works. 13 new
       tests, checked against two mutations (without the lock the order of the
       positions breaks, and taking the position when the round closes fails
       four of them). Checked with a real `debasher_exec` run of two sources and
       a fan-in sink with two snapshots and a halt: all 800 messages were
       processed, the positions were strictly increasing, and in all three
       checkpoints the saved total equals the sum of what the sink had processed
       up to `capture_pos`.
     - 3.3 The switch. **Done 2026-09-20**: the reader threads append the record
       and queue the item under one lock, and the brain thread no longer logs; a
       node opens the log after restoring its checkpoint and replays the `DATA`
       records after `capture_pos` (all of them when there is no checkpoint);
       pruning by position runs after each checkpoint is saved, reading the
       oldest one kept; the cap and the refusal after a failed write are in
       place; and the code and the 15 tests of the per-port log are gone. 17 new
       tests in the words of the guarantees, checked against three mutations
       (replaying only when a checkpoint exists fails 7 of them, replaying from
       position 0 fails 4, pruning by the newest checkpoint fails 2). Checked
       with a real `debasher_exec` run of two sources and a slow fan-in sink
       whose state depends on the order across ports, with the sink killed by
       `kill -9` twice, before its first checkpoint and after it: the three
       incarnations processed all 800 messages exactly once, and from each kept
       checkpoint plus the log the state of the last checkpoint is reproduced,
       order-sensitive hash included. The first segment of the log had been
       pruned by then, as it should.
  4. `CLOSE` handling, in six pieces (four proposed on 2026-09-20, a fifth found
     while doing the fourth and a sixth while doing the fifth; the details of
     each are settled before it is built):
     - 4.1 A halt sends no `CLOSE`. **Done 2026-09-20**: `stop_threads` takes
       `close`, and `run()` stops with `close=False` after a halt; a stop that
       is a finish for good keeps the default. Three new tests in the words of
       the guarantee (an ordered halt leaves a channel that ends with the
       marker, a stop without `CLOSE` sends what is queued and nothing more, the
       `Supervisor` passes the choice on), checked against five mutations.
       Checked with a real `debasher_exec` run of a source and a sink that halt
       and are then resumed by relaunching both: with the earlier code the
       sink's log held a `CLOSE` after `capture_pos` in 2 of 2 runs, with the
       new code in none, and after the resume the sink went on receiving (total
       4950 over 100 messages, from the checkpoint of the halt).
     - 4.2 The reader after `CLOSE` and the heartbeat. **Done 2026-09-20**,
       before `closed_ports` because what that records and replays assumes that
       nothing after a `CLOSE` is ever logged. `_ends_on_close` became
       `_drops_after_close`: the reader keeps reading after a `CLOSE` and drops
       what follows, with one warning per port, and the `Supervisor` keeps
       delivering. Three new tests in the words of the guarantees (what a writer
       sends after its `CLOSE` never reaches the node, a consumer whose producer
       finished keeps saying it is healthy, a new incarnation of a finished
       writer never blocks on a full pipe) and one rewritten, checked against
       six mutants (the first version of one of them survived because it was not
       the fault it meant to be, and the faithful one was killed). Checked with
       a real `debasher_exec` run of a producer that finishes on its own and is
       relaunched, and a consumer that reports its health: with the earlier code
       the reader died 4 s in, the health stayed false to the end and the
       relaunched producer left 351 of 400 messages blocked; now the health
       stays true and none is left.
     - 4.3 `closed_ports` in the checkpoint and its replay. **Done 2026-09-20**:
       the brain thread records each `CLOSE` it processes, the round copies the
       set when it opens, the checkpoint stores it, recovery restores it and
       adds the `CLOSE` records after `capture_pos`, replay fails on a `DATA`
       record after the `CLOSE` of its port, and after a relaunch the readers of
       closed ports start in the dropping mode. Eight new tests in the words of
       the guarantees (the checkpoint holds the ports whose `CLOSE` the node had
       processed when the round opened; a relaunched node knows again which
       ports had closed; a port closed long ago stays closed once the log that
       recorded its `CLOSE` is gone; a message after a `CLOSE` fails loudly,
       both when the `CLOSE` is in the log and when the checkpoint recorded it;
       the readers of closed ports drop what their writers send after a
       relaunch; the file lists the ports in order; a checkpoint without the
       field is refused), checked against eight mutants (the set as the reader
       threads saw it, the set at the close of the round, no restore, replay
       without the `CLOSE` records, no check, readers that start open, a brain
       that does not record the `CLOSE`, an unsorted file). Checked with a real
       `debasher_exec` run of a producer that finishes on its own and a consumer
       killed with `kill -9` after it read the `CLOSE`, then relaunched, and the
       producer relaunched sending 400 KB: with the earlier code the consumer
       processed all 403 messages; now it knows that the port had closed (from
       the `CLOSE` record of its log, there was no checkpoint), its reader drops
       what the producer sends, it stays at 3 messages and 4 records, and the
       producer is never blocked.
     - 4.4 The barrier's pending set, and the channel state entries of the ports
       that are closed at the capture. **Done 2026-09-20**: `_on_close` takes
       the port out of the pending ports and closes the round if it was the
       last, and a round that opens leaves the closed ports out. Eight new tests
       in the words of the guarantees (a round does not wait for a port whose
       writer finishes while it is open; a `CLOSE` after the marker of its port
       changes nothing; a round that opens after a port closed does not wait for
       it and keeps no channel state for it; the marker is still forwarded; a
       node whose inputs have all closed starts and closes a round like a
       root; a later round after two ports closed opens and closes without
       ending the brain thread; the checkpoint of the cut that a `CLOSE`
       completes; a halt completes when the last port it waits for closes), and
       four tests of 4.3 that closed a round by hand now let it close by itself.
       Checked against seven mutants (no discard, no close, closed ports not
       left out, the set that the reader threads had logged, no guard for a
       round that is not open, the channel state of the closing port thrown
       away, an entry for the ports closed at the capture). Checked with a real
       `debasher_exec` run of two producers, one that finished before a round
       and one that finishes while it is open, and a consumer that opens the
       round, is killed with `kill -9` and relaunched: before, the round waited
       for both ports for good and no checkpoint was written; now it waits only
       for the second, closes with its `CLOSE` and writes checkpoint 0
       (`closed_ports` `[in1]`, channel state `{in2: [60, 70]}`); the relaunched
       consumer restores it, finds `in2` closed from the log, and its second
       round closes as it opens (checkpoint 1, both ports closed). That run also
       checks the checkpoint route of `closed_ports` end to end, which the run
       of 4.3 could not.
     - 4.5 Control ports, found with a real run while doing 4.4 and agreed on
       2026-09-20. **Done 2026-09-20**: `CONTROL_PORTS` names the input ports
       that carry only commands. They are left out of the pending ports in every
       round, their reader delivers what follows a `CLOSE`, the `CLOSE` is not
       recorded in `closed_ports` and replay does not restore it, and a name
       that is not an input port is refused. Eight new tests in the words of the
       guarantees (an initiator whose only input is a control port closes its
       round when it is triggered; a control port takes no part in a round that
       a peer starts; an initiator with a data port and a control port waits
       only for the data port; a `CLOSE` on a control port changes nothing; the
       port keeps delivering after a `CLOSE`; it is not restored as closed after
       a crash; the trigger of a `Supervisor` relaunched after a recovery still
       arrives; the declaration is validated), checked against seven mutants,
       one of them the alternative of leaving the port out only of the rounds
       that a command opens, and one that needs two defects together. Checked
       with a real `debasher_exec` run of a real `Supervisor`, an initiator and
       a consumer: a person writes `start_snapshot` into the manual trigger
       port, and the initiator writes its checkpoint at once (before, only the
       consumer did, and the initiator's round closed only when the `Supervisor`
       stopped and said `CLOSE`); then the `Supervisor` stops, is relaunched by
       hand, and the `shutdown` that a person writes now reaches the initiator,
       which halts with the consumer, each with checkpoints 0 and 1 (before, the
       `shutdown` was dropped and the program never halted). It was the first
       real run of the trigger path of the `Supervisor`.
     - 4.6 Rounds that overlap, found while doing 4.5 and agreed on 2026-09-20.
       **Done 2026-09-20**: a round that finds another open no longer raises. A
       marker of a newer epoch replaces the open round, which is abandoned, and
       the node captures at that marker; a halt is not replaced by a snapshot; a
       marker of an older epoch, or of a round that is over, is ignored; a
       `start_snapshot` that finds a round open is ignored, a `shutdown`
       replaces an open snapshot and is ignored if a halt is open, and a node
       that has halted starts no rounds. Eight new tests in the words of the
       guarantees, replacing the two that demanded the `ValueError`, checked
       against ten mutants. Checked with a real `debasher_exec` run of a real
       `Supervisor`, two initiators, a slow path and a node with two inputs: a
       person writes two `start_snapshot` half a second apart, and the node with
       two inputs had round 0 open, waiting for the slow path, when the marker
       of round 1 from the fast one arrived. Before, its brain thread died with
       the `ValueError`, it wrote no checkpoint and the program never halted
       (the other three nodes did). Now it abandons round 0 with a warning,
       ignores the late marker of round 0, closes round 1 when the slow path's
       marker arrives (checkpoint 1) and completes the halt (checkpoint 2), and
       the four nodes finish; the last snapshot has a checkpoint at every node.
  5. G5: sequence numbers, deduplication and detection of gaps. **Done
     2026-09-22**, in six pieces (agreed 2026-09-21; the outbound backlog was
     added on that date, and the first piece before them because the
     numbering relies on it):
     - 5.1 A node sends only inside `process_data`. **Done 2026-09-21**:
       `FBPProcess.send_data` raises unless it is called on the thread that is
       running `process_data`, the brain thread or the one that replays the
       input log, and the mark is cleared when `process_data` returns or fails.
       Six new tests in the words of the guarantee (a node cannot send outside
       `process_data`; what it sends inside it, on the brain thread, reaches its
       writer; a thread of the module cannot send while `process_data` runs; it
       cannot once `process_data` has returned or failed; it can while the node
       replays its input log), checked against six mutants (no check, any thread
       accepted while a handler runs, the replay or the brain thread not marked,
       the mark never cleared, an inverted check). The tests of the writer
       thread, which used a node with no inputs that sent from the test's own
       thread, now use a bare `_PortWorker`, and the test of the halt uses a
       relay fed through its input FIFO. Checked with a real `debasher_exec` run
       of a relay and a sink, where the relay also starts a thread of its own
       that sends: before, the sink received `ROGUE 1 2 3 4 5`; now the thread's
       call is refused with a `RuntimeError`, the sink receives `1 2 3 4 5` and
       the relay forwards what it receives as before.
     - 5.2 The sender numbers its `DATA`, and its counters go in the checkpoint.
       **Done 2026-09-22**: `Envelope` gains a third field, `seq` (a sibling
       of `type` and `payload`, absent when the sender is not one that
       numbers, such as a plain `_PortWorker` or an outside source);
       `FBPProcess.send_data` numbers each channel from 1 with its own
       counter, `_out_seq`, read and bumped inside the thread check that 5.1
       already enforces, so numbering needs no lock of its own. A round's
       capture takes a copy of the counters, never the live dict, at the same
       instant as `capture_pos` and `closed_ports`; the checkpoint's `out_seq`
       is restored before `initialize_runtime()`, so replay renumbers exactly
       as the crashed incarnation had. 15 new or updated tests in the words of
       the guarantee, checked against 8 mutants (numbering unused, the counter
       not stored back, one counter shared across every port instead of one
       per port, the checkpoint never writing it, a capture that aliases the
       live counters instead of copying them, `run()` never restoring them;
       the last two survived at first, for lack of a test that sends while a
       round stays open and one that restores through the real `run()`).
       Checked with a real `debasher_exec` run of a relay fed from outside and
       a sink that records what it receives, envelope included, in its own
       input log: `1, 2, 3` sent, a snapshot (`out_seq` `{outf: 3}` in the
       checkpoint), `4, 5` sent and not covered by it, the relay killed and
       relaunched: the sink's log holds `1, 2, 3, 4, 5, 4, 5`, the replay
       regenerating exactly the numbers the crashed incarnation had used.
       Dropping the duplicate is 5.3, not built yet.
     - 5.3 The receiver drops the `DATA` that it has already accepted.
       **Done 2026-09-22**: the check runs in the reader thread, in
       `_on_arrival`, before a record is written or queued, exactly as
       decided; a `DATA` whose `seq` is not above the last one already
       accepted on that channel is dropped, one with no `seq` (an unnumbered
       source) is always accepted and never moves the counters, and only
       `DATA` is checked. It needs two distinct counters: `_last_seq`, the
       brain's own view, bumped when it dispatches a numbered `DATA` (mirrors
       `_current_pos`, feeds `_barrier_last_seq` and the checkpoint's
       `last_seq`, same isolation as `out_seq`, a capture must not see what a
       reader thread accepted on another, still-pending port after the
       capture); and `_accepted_seq`, the reader threads' own live counter
       that the check itself uses, ahead of the brain, restored from the
       checkpoint's `last_seq` and then advanced by `_replay_input_log`
       scanning the numbered `DATA` after `capture_pos`, so that a relaunched
       node recognizes as a duplicate what its own log had already accepted
       before the crash, whether the brain had processed it yet or not.
       The inbound queue item gains `seq` as a fifth element, so the brain
       can maintain `_last_seq`. 10 new tests in the words of the guarantee
       (a duplicate is dropped before it is logged or queued; a number not
       above the last one is also a duplicate; a higher number is accepted
       and moves the counters; a gap is accepted here, becoming an error is
       5.5; an unnumbered `DATA` is always accepted and never moves the
       counters; each input port is deduplicated on its own; a capture
       reflects the brain's view, not what a reader thread has raced ahead
       to accept; a restored node drops what its own log already covers; a
       dropped fragment never moves the counter), checked against 8 mutants
       (no check, an off-by-one that lets an exact duplicate through,
       `_accepted_seq` not updated on accept, the brain never updating
       `_last_seq`, `_barrier_last_seq` aliasing instead of copying, replay
       never advancing the counters, the checkpoint never writing `last_seq`,
       `run()` never restoring it), all killed. Checked with a real
       `debasher_exec` run, the same relay and sink as 5.2's: before, after a
       kill and a relaunch, the sink's log held `1, 2, 3, 4, 5, 4, 5`; now it
       holds `1, 2, 3, 4, 5`, the relaunched relay's replay regenerating `4`
       and `5` and the sink correctly recognizing them as duplicates.
     - 5.4 The checkpoint carries the outputs that the writer thread had not yet
       written, and recovery sends them again before the replay. **Done
       2026-09-22**: `send_data` appends the line it queues to `_unwritten`,
       per output port, before it can be written; the writer thread's own
       loop calls a new hook, `_on_written`, after every line it finishes,
       which leaves the backlog if the line is the oldest one still queued
       for that port (always true, a queue being FIFO). A round's capture
       takes a decoded copy, `_barrier_out_backlog`, the same isolation the
       other counters already need (a reader thread's writer counterpart can
       confirm a later line while the round stays open); the checkpoint's
       `out_backlog` is restored before anything else is sent, by
       `_restore_out_backlog`, which re-enqueues each line with its original
       number, ahead of what a replay sends again. Over
       `OUT_BACKLOG_MAX_BYTES` (8 MiB by default, a new decision, not
       previously fixed), `_save_checkpoint` writes nothing and warns loudly
       instead of growing the file without bound; the round still closes and
       a halt still signals shutdown, since the previous checkpoint plus a
       longer replay cover it. 18 new tests in the words of the guarantee
       (`send_data` backlogs a line before anything can write it; a written
       line leaves the backlog; the checkpoint carries only what is still
       unwritten at the capture, not what a concurrent write confirms after
       it; a capture is a copy, not a live view; over the cap nothing is
       written and a halt still signals shutdown regardless; `run()`
       restores the backlog and it reaches a neighbor, ahead of the replay),
       checked against 8 mutants (`send_data` not backlogging, the writer
       hook never popping or matching the wrong line, the capture aliasing
       the live backlog, the checkpoint never writing it, `run()` never
       restoring it, the cap check inverted, halt not firing when the write
       is skipped), all killed. Checked with a real `debasher_exec` run: the
       same finding that opened this whole step (1c: a slow neighbor fills
       the pipe, so part of what a node has already numbered stays only in
       memory) reproduced end to end, a relay forwarding to a sink slow to
       start, `1` to `8` sent, `5` to `8` still in the backlog when a
       snapshot captures relay (`out_seq` `{outf: 8}`, `out_backlog` `outf`
       holding `5, 6, 7, 8`), relay killed and relaunched: the sink receives
       `1` to `8`, none missing, none duplicated, closing the gap that 1c
       found (a real relay under the same conditions had delivered `1, 2, 3,
       4` only, silently losing `5` to `8`, before this piece existed).
     - 5.5 A gap in the numbers of a channel is an error. **Done 2026-09-22**:
       right after the dedup check in `_on_arrival`, a numbered `DATA` whose
       `seq` is more than one above the last one accepted is a message this
       channel will never see again, so it raises there, before anything is
       logged or queued, the same as a duplicate is dropped before either;
       the error names the channel and the missing numbers. The counter is
       left exactly where it was, not advanced to the arriving number, so a
       relaunch still sees the gap as open. Raising inside `_on_arrival`
       kills that reader thread the same way a size-cap or a failed write
       already did (G7's heartbeat is what notices from there). 4 new tests
       in the words of the guarantee (the error names the channel and the
       missing numbers; a single missing number is named without a range;
       nothing is logged or queued and the counter does not move; a real
       reader thread dies from it, the process staying alive), checked
       against 3 mutants (the check removed, an off-by-one that misses a
       single-message gap, the counter updated before the raise instead of
       never), all killed. Checked with a real `debasher_exec` run of a node
       fed from outside: `1`, `2`, then `5` (`3` and `4` never sent), its own
       scheduler log holding the exact error (`expected 3, got 5, missing 3
       to 4`), the process itself still alive (`debasher_status` reporting
       `IN-PROGRESS`) with only its reader thread gone.
     - 5.6 `CLOSE` carries the last number. **Done 2026-09-22**: `encode_close`
       takes an optional `last_seq`; a writer thread asks a new hook,
       `_close_payload(tag)` (`None` on the base class, `_out_seq[tag]` on
       `FBPProcess`), right when it is about to send `CLOSE`, by when the
       brain thread has already stopped for good, so reading `_out_seq` needs
       no lock. On arrival, once `CLOSE` is itself durably logged and queued,
       a claimed `last_seq` above what this channel has accepted is a lost
       message that nothing would otherwise ever reveal, since nothing comes
       after a `CLOSE`: it raises there, naming the port and the missing
       numbers, the same wording 5.5 already uses, but only after `CLOSE`
       is recorded, not before it, unlike a `DATA` gap: nothing ever sends
       `CLOSE` a second time, so losing it to an early raise would leave that
       port looking unfinished forever, in place of reporting one lost
       message and moving on. 9 new tests in the words of the guarantee
       (`CLOSE` carries the sender's last number; a plain `_PortWorker`'s
       carries none; a matching claim is not an error; one above it is,
       naming the port and the missing numbers; a single missing message
       has no range; `CLOSE` is logged and queued even though it raises; no
       claim is never an error; a real reader thread dies from a real lost
       message, the process staying alive; a halt sends no `CLOSE`, so
       nothing to check), checked against 5 mutants (the hook never
       reporting the counter, the check removed, an off-by-one that also
       flags a matching claim, the raise moved before `CLOSE` is recorded,
       `encode_close` ignoring `last_seq`), all killed. Checked with a real
       `debasher_exec` run of a node fed from outside: `1`, `2`, then a
       `CLOSE` claiming `4` (`3` and `4` never sent), the scheduler log
       holding the exact error (`closed for good after sending up to 4, but
       only 2 was ever accepted here, missing 3 to 4`), `CLOSE` itself found
       durably recorded in the node's own input log, the process still
       alive with only its reader thread gone.
  6. The chaos test of the Contract: in progress, see "Acceptance" for the
     reference program and where it stands.

### Why not built on `--mirror`, and locality

Implemented entirely inside `FBPProcess` itself, in Python, not on top of the
engine's `--mirror` fifo tap. An earlier draft of this section routed the
message log through `--mirror`, forced on for every resident data fifo, with
resident-specific sequence numbering and epoch-segment rotation layered onto
the mirror tap. That was abandoned once it became clear it was subjecting a
mechanism only ever meant for occasional manual debug inspection (the
frontend's "Watch FIFO", `debasher_get_fifo_mirror`) to a load and traffic
pattern (back-to-back messages, no reader-side pacing) it was never designed
for: real bugs were found and fixed while implementing that version (a
SIGPIPE crash when a repeated-open reader is momentarily detached, and a
bats-core fd collision), and both would never have existed with this design
instead. `--mirror` stays exactly as it always was, for that one original,
occasional debug use case; nothing about it is forced on for `resident`
programs, and since 2026-09-20 a `resident` program that declares `--mirror`
on a fifo is rejected when it is loaded
(`debasher::_check_fifo_mirror_allowed`, called by `define_fifo_opt` and
`define_fifo_opt_generator`), so a mirror tap can never sit between two
resident processes.

The process that needs to replay a log is always the one relaunched after a
crash (itself, not its neighbor), so the log belongs on the *reader* side, in
the restarting process's own `DEBASHER_PROCESS_EXECDIR`, not the writer's.
This locality removes any need to reach into a neighbor's directory, and
removes the tap/shim mechanism from this feature entirely: no separate
process, no fifo-open/close races, nothing to force on via `--mirror`.

## 4. `Supervisor` class: DONE, implemented and tested (`engine/debasher_runtime_supervisor.py`)

(Reuses `FBPProcess`'s thread-per-port pattern via a shared base, section 2, but
does not take part in the barrier as a business node.)

### Port declaration and node identity

- **`NODE_PORTS`**: a dict `{node_name: option_name}`, hardcoded in the heredoc
  by the module author (like `INPUT_PORTS`/`OUTPUT_PORTS` in `FBPProcess`, but a
  dict instead of a list). A dict is needed here specifically because, unlike
  `FBPProcess`'s barrier logic, which only ever needs "did this pending port's
  marker arrive yet, yes or no", treating every input port interchangeably,
  `Supervisor`'s detection and relaunch logic inherently act on a *specific
  node's identity*, not just "which port". The key is a label `Supervisor`'s own
  code uses internally (logs, detection, relaunch); the value is the option name
  resolved through `self.opts` (the same `-optname value` CLI convention) to the
  actual FIFO path opened by that node's reader thread. At startup, each
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

### Class relationship: shared `_PortWorker` base

- **`FBPProcess` and `Supervisor` both inherit from a new `_PortWorker` base
  class**, factored out of `FBPProcess`'s existing thread topology (section 2,
  slice 3): generic `start_threads()`/ `stop_threads()`, the shared inbound
  queue, one outbound queue per output port. None of the
  barrier/checkpoint/input-log logic moves into it, that stays in `FBPProcess`
  itself; `Supervisor` gets the same mechanical thread-per-port plumbing without
  inheriting anything about barriers, since it is not a barrier participant.

### Trigger port(s): initiator(s) for snapshot/shutdown

- **`TRIGGER_PORT` is a list of zero or more output option names**, not a single
  scalar, each wired to a different initiator node. This covers a `resident`
  program made of multiple genuinely independent subgraphs: a single initiator
  can never reach a disjoint subgraph no matter what, so the module author names
  one initiator per subgraph it actually needs to reach. `Supervisor` sends
  `start_snapshot`/`shutdown` to every configured initiator when triggered
  (manually, or by `on_node_permanently_failed`, see below). Empty by default: a
  `Supervisor` doing pure monitoring + relaunch, with no
  snapshot/shutdown-triggering capability at all, is a valid configuration.
- An initiator that receives its triggers through a trigger port lists the port
  on which it reads them in `CONTROL_PORTS`. Without it the channel is treated
  as a data port: the round opens, the marker goes downstream and the initiator
  waits for ever for a marker from the `Supervisor` (checked with a real
  `Supervisor`). It is also what keeps the `CLOSE` that a `Supervisor` sends
  when it stops from closing the channel for good, so that the triggers of one
  relaunched by hand still arrive.
- This is a convenience, not the only way to trigger a round: `FBPProcess`'s own
  opt-in periodic self-triggered snapshot (`SNAPSHOT_INTERVAL_SECS`, section 2)
  and a direct external `INTERACT` write into an initiator's own FIFO (e.g. via
  Talk-to-FIFOs) both remain independent of whether a `Supervisor` exists at all
  or how it is configured.

### Manual trigger channel

- **`MANUAL_TRIGGER_PORT`**: an optional single input option name, distinct from
  `NODE_PORTS` (carries no per-node identity, it is an external control channel,
  not a supervised node's heartbeat). Any `INTERACT` envelope arriving there is
  relayed verbatim to every configured `TRIGGER_PORT` initiator. `Supervisor`
  does not validate or interpret `command`, matching the deliberately open-ended
  `INTERACT` catalog convention used everywhere else in this design (section 1).
  Whatever ends up unrecognized is still handled safely at the far end, by the
  initiator's own existing `_on_interact` (logs a warning and ignores it, never
  aborts).

### Reading a node's channel across a crash: reopen after EOF

**Replaced on 2026-09-20 (step 2 of the order of implementation in section 3):
ghost connections, see section 5.** No reader sees EOF any more, so the
reopening described below, its `.finished` polling and the daemon reader threads
no longer exist, and `Supervisor` learns that a node finished from its
`.finished` file in the checker alone. What follows is what was built before,
kept as a record.

- A reader that does a single `open()` plus `for line in fifo` dies at the first
  EOF, so it can never hear a relaunched writer (found by trying to build the
  smoke test; reproduced with a plain script: the second writer blocks forever
  in `open()`). The earlier smoke tests of `FBPProcess` never showed this
  because they always restarted the whole program, which recreates the FIFOs.
- `_PortWorker._reader_loop` now loops, asking `_should_reopen_after_eof(tag)`
  (default `False`, the exact existing behavior of `FBPProcess`). `Supervisor`
  overrides it: the manual trigger channel always reopens (an external writer
  opens, writes one line and closes, like the frontend's Talk-to-FIFOs); a
  node's channel reopens unless the node is resolved. `Supervisor` has the
  information a plain `FBPProcess` peer lacks to tell a crash from a permanent
  stop: the node's own `.finished` file and its given-up state.
- `.finished` is written by the wrapping script only after the node's process
  has exited, so it does not exist yet at the instant of EOF even for a clean
  stop. The override therefore polls for it for up to `EOF_FINISHED_GRACE_SECS`
  before deciding to reopen (and marks the node done at once if it appears).
- A reopening reader can end up blocked in `open()` for a node given up on for
  good, so `Supervisor`'s reader threads are daemon threads
  (`_READER_THREADS_ARE_DAEMON`); `FBPProcess`'s stay non-daemon, exactly as
  before.
- `FBPProcess`'s heartbeat thread now actually sends `INTERACT heartbeat` to
  `SUPERVISOR_PORT` when every thread is alive (it used to only log; left open
  in section 2).

### Failure detection

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
  thread, written by the brain thread, the same class of cross-thread hazard as
  the `_last_epoch` race found in section 3, this time resolved with an explicit
  lock since, unlike that case, two threads legitimately need to touch this
  state.
- **`HEARTBEAT_TIMEOUT_SECS` / `HEARTBEAT_CHECK_INTERVAL_SECS`**: the checker
  thread wakes every `HEARTBEAT_CHECK_INTERVAL_SECS` and, for each node not yet
  resolved (see below), compares `now - _last_heartbeat[node]` against
  `HEARTBEAT_TIMEOUT_SECS`.
- **PID-based fast path**: every BUILTIN-scheduler process already gets a `.id`
  file holding its own PID (`debasher_builtin_sched::_print_pid_to_file`,
  pre-existing, not `resident`-specific), at `__exec__/<node>/<node>.id`. If
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

### Clean-completion detection (and the `Supervisor`'s own shutdown)

- **The checker thread also checks `<node>.finished`, every tick, for every node
  not yet resolved**: cheap (one `os.path.exists()` per node per tick, same cost
  class as the heartbeat comparison), and checked unconditionally rather than
  only as a tie-break right before declaring a heartbeat timeout, specifically
  so a node's clean completion is noticed within one
  `HEARTBEAT_CHECK_INTERVAL_SECS`, not delayed by up to a full
  `HEARTBEAT_TIMEOUT_SECS`.
- Confirmed by reading the engine source, not assumed:
  `debasher::_signal_process_completion` (`engine/debasher_lib_sched_procs.sh`),
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
- **`Supervisor` also stops on a stop signal, since 2026-09-22 (`FBPProcess`'s
  own mechanism, section 2's "Ordered shutdown"): `run()` installs a
  `SIGTERM` handler on the main thread (same reasoning, and same
  off-main-thread exception for tests driving `run()` on a background
  thread), whose handler just sets `_all_resolved` directly; unlike
  `FBPProcess`, nothing else here needs to tell "resolved naturally" apart
  from "told to stop", so the one event already `run()`'s own
  `_all_resolved.wait()` waits on covers both, with no new attribute
  needed.** This exists specifically so a graceful-stop tool that finds a
  `Supervisor` present can end it first, deliberately, before touching any
  node it watches, so it cannot relaunch one out from under the rest of
  what that tool does (see the `debasher_stop_resident` subsection below).

### Relaunching a downed node

- **`on_node_down(node_name)` is a hook with a concrete default
  implementation**, not a pure `NotImplementedError` abstract method like
  `FBPProcess.process_data`/etc. Unlike those, there *is* one universal, correct
  default action here, since every `resident` process is relaunched the exact
  same mechanical way. Overridable, for a module author who needs something
  non-standard.
- **The default relaunches through a new installed tool,
  `debasher_launch_process -d <outdir> -p <process> [-t <idx>]`**
  (`engine/debasher_launch_process.sh`, installed in `libexec`), which calls the
  built-in scheduler's own `debasher_builtin_sched::_launch`. The tool takes the
  program's output directory (not the process's) and, for an array task, the
  index; without `-t` it passes `NO_ARRAY_TASK`. Relaunching is therefore the
  same code path as the original launch (matches section 2's "first launch and
  recovery are the same operation").
- **Why not simply re-execute `__exec__/<node>/<node>`** (the first design,
  implemented and discarded after a real `debasher_exec` smoke test): that
  generated script does not carry the per-launch state.
  `BUILTIN_SCHED_PID_FILENAME` (which `.id` file to write) and
  `BUILTIN_ARRAY_TASK_ID` are exported by `_launch` just before it starts the
  script, and are not among the variables dumped into the script itself (that
  dump is a deliberate allowlist, and it runs once per process at generation
  time, while these values are per launch). A bare `subprocess.Popen` from the
  Supervisor therefore inherited the Supervisor's own values, so the relaunched
  node never updated its own `.id` (and could write into `supervisor.id`). The
  stale PID made `_node_pid_alive` report "dead" forever, and since a real
  heartbeat resets `_relaunch_attempts` on every recovery, the budget never
  tripped: an endless relaunch loop (ten worker processes in under four
  seconds). The bare relaunch also left the node in the Supervisor's own process
  group, which `debasher_stop` (`kill -9 -- -$pid`) relies on being one per
  process. `_launch` fixes all of it, and its explicit exports override whatever
  the caller inherited.
- **Changes to `_launch` made for this**
  (`engine/debasher_builtin_sched_lib.sh`): (1) it removes any stale `.id`
  before launching, so its wait for the PID file really waits for the new
  process (before, a relaunch found the old file and returned at once, leaving
  the old PID readable, which `debasher_stop` would try to kill); (2) it exports
  `DEBASHER_LIBEXECDIR` so a running process can find the installed tools
  (`debasher_libexecdir` is deliberately excluded from what generated scripts
  carry); (3) it now unsets `BUILTIN_ARRAY_TASK_ID` (a leftover
  `unset "${task_varname}"` referred to a variable removed by an old redesign, a
  silent no-op). Covered by `test/engine/builtin_sched_lib.bats`.
- The launcher runs without blocking the checker thread; a short-lived thread
  reaps it and logs a non-zero exit. Verified with a real `debasher_exec` run:
  four consecutive kills of the worker gave exactly four relaunches, each with
  its own process group and refreshed `.id`, an untouched `supervisor.id`,
  `attempts=1` every time (the budget resets on each real recovery), and no
  further relaunches once the node was healthy; `debasher_stop` then stopped
  both processes.
- **`MAX_RELAUNCH_ATTEMPTS` per node**: a plain counter, incremented each time
  `on_node_down` actually fires for that node, **reset to 0 on that node's next
  real heartbeat** (proof of actual recovery, not just that its PID exists
  again, consistent with "PID-alive proves nothing about health" above). This
  distinguishes a node that keeps crashing immediately after every relaunch
  (counter climbs, never resets, eventually exhausts the budget) from one that
  crashes rarely over a very long run and always recovers cleanly each time
  (counter keeps resetting, never exhausted just by accumulating spaced-out
  incidents).
- Exceeding the limit calls **`on_node_permanently_failed(node_name)`** instead
  of relaunching again; that node moves to its own terminal "given up" state
  (distinct from "done"), never automatically retried again.
- **The relaunch subprocess also has to leave `stdout`/`stderr` alone, not
  just `stdin`: found 2026-09-22, fixed the same day.** `on_node_down`'s
  `subprocess.Popen` only redirected `stdin`; left alone, `stdout`/`stderr`
  are inherited from the Supervisor's own process, which its own launch
  script pipes into `tee` (`debasher_builtin_sched::
  _execute_funct_plus_postfunct`). `debasher_launch_process`, and in turn
  the resident process it backgrounds, inherited that same pipe, and held
  its write end open for as long as the relaunched node kept running, long
  after the Supervisor's own Python interpreter had actually exited: `tee`
  never saw `EOF`, so the Supervisor's own wrapper script never got past
  its own `wait` for that pipeline, and `sup.finished` never appeared.
  `debasher_stop`'s hard kill never surfaced this (it always kills the
  relaunched node too, which closes the leaked fd as a side effect); a
  graceful stop signal (see the `debasher_stop_resident` subsection below)
  does not, and was how this was found: confirmed with a real
  `debasher_exec` run, kill one node, let the `Supervisor` relaunch it,
  then send the `Supervisor` a `SIGTERM` on its own, nothing else touched.
  Fixed by also redirecting `stdout`/`stderr` to `DEVNULL` in that same
  `Popen` call.

### Escalation on a permanent node failure: DONE, implemented and tested

A node given up on for good can, in the worst case, have been the only path (in
the business-data graph) to some other node(s); if so, no ordered shutdown can
ever reach them through the graph itself, since the barrier marker only ever
propagates along the same edges as `DATA` (section 1's channel topology). Rather
than build a second, parallel broadcast mechanism (a direct connection from
`Supervisor` to every node, bypassing the graph, with a new barrier-skipping
command), which would mean N extra FIFOs to wire per program, and would put
every ordinary shutdown at risk of losing the barrier's consistency guarantees,
not just the pathological case, `on_node_permanently_failed`'s default
implementation calls **`debasher_stop_resident`** (the tool below) as a
subprocess, `-x <node_name>` excluding the node just given up on and
`--keep-supervisor` set: the tool gracefully halts and stops whatever part of
the graph remains reachable, and falls back on its own, past its own
`--timeout` (`FORCE_STOP_TIMEOUT_SECS`), to `debasher_stop -d <dirname>`, an
existing, unmodified engine tool (`engine/debasher_stop.sh`) that walks every
process of the program and sends `kill -9 -- "-$pid"` (a process-group
`SIGKILL`) to any still `INPROGRESS`, regardless of the graph's connectivity.
Built and reusing what already exists this way, `on_node_permanently_failed`
itself no longer reimplements any of that sequence by hand, the way an earlier
version of this same escalation once did: that earlier version sent plain
`shutdown` to every `TRIGGER_PORT` initiator directly and waited on "done"
tracking itself, which stopped resolving anything once a halt stopped being
self-terminating (section 2's "Ordered shutdown"), always falling through to
the hard-kill fallback instead, not just in the pathological case.

`dirname` (the program's own base output directory, not a process's own exec
dir) needs no new engine export: it is exactly
`dirname(dirname(DEBASHER_PROCESS_EXECDIR))` (confirmed against
`debasher::get_prg_exec_dir_given_basedir`, `<dirname>/__exec__/<processname>`),
and the tool's own absolute path needs `DEBASHER_BINDIR`, a new export
alongside the existing `DEBASHER_LIBEXECDIR` (`debasher_builtin_sched::_launch`,
`engine/debasher_builtin_sched_lib.sh`): found missing 2026-09-22 by a real
`debasher_exec` run (see "Getting this right" below), the same way
`DEBASHER_LIBEXECDIR` already exists for `_launch_process_command`'s own
`debasher_launch_process` lookup.

This deliberately accepts an asymmetry: the graceful phase preserves every
checkpoint/input-log consistency guarantee already built; the hard-kill fallback
is explicitly a "just end it" backstop, expected to only ever fire in the
pathological case of a graph broken by a permanent node failure, and is allowed
to lose in-flight state for whatever it kills.

**`--keep-supervisor` is not optional for this caller.** This call runs on a
thread of the same `Supervisor` process it is about to ask the tool to act on
`Supervisor`'s own program. Without it, the tool's own first step
(`stop_supervisor_if_any`) would target this same process's group, and this
call would never actually get anywhere: see that function's own comment
(`engine/debasher_stop_resident.sh`) for the deadlock this avoids, and
"Getting this right" below for how this was found before it shipped, not
after. Left alone by `--keep-supervisor`, `Supervisor` still ends, on its own,
the same way it always does once every node it watches is done or given up on
(see "Clean-completion detection"): nothing here has to signal it, or even
knows when that will be.

**Getting this right, 2026-09-22, surfaced two more bugs, both found by a
real `debasher_exec` run of a node actually being driven to exhaust
`MAX_RELAUNCH_ATTEMPTS` (`test/engine/test_chaos.py`'s
`test_supervisor_escalation_stops_the_reachable_graph_after_a_permanent_failure`),
neither caught by the unit tests written first (which mock `subprocess.run`
and so never actually exec anything):**

1. **The deadlock above**, found by design before any code was written (not by
   a failing run): two other candidates were considered and ruled out first.
   Running the tool in a detached process group (`setsid`) does not help: the
   tool's own step still targets `Supervisor`'s *original* process group by
   pid, which the `Supervisor` process itself never leaves, so it would still
   stop itself prematurely, before the reachable nodes it is meant to
   supervise while this runs are actually done. Stopping it last instead of
   first (after the reachable nodes, still inside the same tool call) does not
   help either, for a different reason: the call is blocked on a thread of the
   `Supervisor` process itself, so a last step that signals `Supervisor` and
   waits for its `.finished` waits on something that cannot happen until that
   same blocked thread returns, which cannot happen until this wait does.
   Leaving `Supervisor` alone entirely, letting it resolve itself once the
   reachable nodes are done (already true regardless, see
   "Clean-completion detection"), avoids both.
2. **A bare `"debasher_stop_resident"` (`subprocess.run`'s own `args[0]`)
   relies on `PATH` already including `bin/`, which nothing sets for a
   launched process.** The first real run crashed the escalation thread on
   `FileNotFoundError` before it ever reached the tool, silently (nothing
   joins that thread, so nothing surfaced it beyond a stack trace on stderr).
   Fixed by resolving the tool's absolute path from the new `DEBASHER_BINDIR`
   (`Supervisor._debasher_stop_resident_command`), the same pattern
   `_launch_process_command` already used for `debasher_launch_process` via
   `DEBASHER_LIBEXECDIR`. This almost certainly also explains, not just
   resembles, "Conformance status"'s "Supervisor's own resolution after a
   node gives up may not complete" entry: that entry's escalation used this
   same bare-name call for its `debasher_stop` fallback, which would have
   failed exactly the same way, silently, for exactly the same reason, every
   time it was ever actually reached.

### `debasher_stop_resident`: the graceful stop tool: DONE, implemented and tested (`engine/debasher_stop_resident.sh`, `bin/debasher_stop_resident` once built)

The external tool the third G2 candidate needed (see "Conformance status" and
section 2's "Ordered shutdown"): the graceful counterpart to `debasher_stop`,
for a resident program specifically. Built 2026-09-22, alongside the
`Supervisor` changes above, which it depends on.

- **Usage: `debasher_stop_resident -d <outdir> [-x <name>[,<name>...]]
  [--timeout <secs>] [--keep-supervisor]`.** `-d` is the program's own output
  directory, same as every other engine tool that operates on one. `-x` names
  process(es) to leave alone entirely (not waited for, not signalled): for
  `on_node_permanently_failed`'s own use (escalation section above), which
  must not wait forever on a node it has already given up on. `--timeout`
  (default 60, the same default `FORCE_STOP_TIMEOUT_SECS` already used) bounds
  the whole graceful attempt; past it, falls back to `debasher_stop -d
  <outdir>` (a hard kill of the entire program), so this always ends the
  program one way or another, never hangs indefinitely by itself.
  `--keep-supervisor` skips stopping the program's `Supervisor` (step 1 of the
  Sequence below), also for `on_node_permanently_failed`'s own use: it calls
  this tool from a thread of the very `Supervisor` process it would otherwise
  target (see the escalation section above for why that specifically must not
  happen, not just should not).
- **Finds the program's nodes and its `Supervisor` (if any) the same way
  `debasher::_validate_resident_program_processes` already does**: loads the
  module, iterates `DEBASHER_PROGRAM_PROCESSES`, and classifies each with the
  existing `debasher::_classify_resident_process_role` (no new classifier
  written for this).
- **Sequence:**
  1. If the program has a `Supervisor` and `--keep-supervisor` was not given,
     stop it first (a stop signal to its whole process group, see below) and
     wait for its own `.finished`, before touching any node it watches: this
     is exactly why `Supervisor` itself needed a stop signal of its own
     (subsection above), and it is what keeps this tool from racing a
     relaunch it did not ask for.
  2. Record each node's halted marker as it stands right now (its content,
     or `-1` if absent): the baseline a fresh one has to beat.
  3. Write `shutdown` into every node's own control ports (the design doc's
     "control ports file", most nodes have none; the round reaches them from
     elsewhere in the graph).
  4. Wait for every node's halted marker to go past its own baseline (never
     "exists": a node halted from a previous, already-resumed cycle would
     already show one that means nothing about this run).
  5. Re-read every node's `.id` (not reusing what step 1 or discovery
     already saw) and send each a stop signal.
  6. Wait for every node's own `.finished`.
- **A stop signal is `SIGTERM` to the whole process group (`kill -TERM --
  "-$pid"`, a new `debasher::_stop_pid_gracefully`, the `SIGTERM` sibling of
  `debasher::_stop_pid`'s existing `SIGKILL`), never a lone pid.** Found
  2026-09-22, the same day: `debasher_builtin_sched::_launch` backgrounds a
  generated script as its own process group leader (the pid in `.id`), but
  that script's own pipeline
  (`debasher_builtin_sched::_execute_funct_plus_postfunct`) forks at least
  one subshell to run the process function, so a resident process's own
  Python interpreter sits below that pid, not at it. A single-pid `SIGTERM`
  only reached the wrapper script, which had no handler of its own and died
  at once, orphaning the interpreter, which never received anything and ran
  forever; `debasher_stop_resident` then waited out its own timeout for a
  `.finished` that could never come. Fixed the same way at both ends: the
  signal now always targets the whole group, and the wrapper script itself
  now ignores `SIGTERM` at its own top level
  (`debasher_builtin_sched::_print_script_trap`, `trap '' TERM`, the first
  thing `_create_script` writes into the generated file) so it survives
  that same broadcast long enough to still write `.finished` once its own
  child (the Python interpreter, or a stopped `Supervisor`) actually exits.
  `SIGKILL`, used by `debasher_stop`'s hard kill, cannot be trapped and is
  unaffected by any of this.
- **Verified with real `debasher_exec` runs**, not just reasoned: a clean,
  no-failure run of the chaos test's own reference program (`Supervisor`
  present) and of a new, minimal, `Supervisor`-less reference program
  (`test/engine/debasher_halt_ref.sh`, `test/engine/test_halt_ref.py`);
  the `-x` flag, excluding a healthy node from an otherwise-normal run and
  confirming it is untouched while every other node, `Supervisor` included,
  stops cleanly; and, separately, the ten already-committed chaos-test
  pieces that kill and relaunch nodes mid-run, now ending each run through
  this tool instead of a hand-rolled wait (`test/engine/test_chaos.py`'s
  `_halt_and_wait_for_finished`). The kill-and-relaunch runs are what found
  two of the three bugs on this page dated 2026-09-22 (the wrong-pid signal
  and the leaked `stdout`/`stderr` fd): a plain, no-failure run never
  relaunches anything, so neither had ever been exercised by any run before
  this tool existed and something started actually waiting for a graceful,
  confirmed stop rather than a hard kill.
- **`--keep-supervisor`, and the escalation that needs it, verified the same
  way, separately, also 2026-09-22**
  (`test_supervisor_escalation_stops_the_reachable_graph_after_a_permanent_failure`):
  `sink` genuinely driven to exceed `MAX_RELAUNCH_ATTEMPTS` (a real, repeated
  `kill -9` of each fresh relaunch, `SIGSTOP` first so it can never heartbeat
  in between and reset its own budget), confirming `fanin` and `loop`, still
  reachable, are gracefully halted and stopped by the escalation's own call to
  this tool, `sink` itself is left alone (no `halted` marker, no `.finished`,
  its last incarnation's pid never signalled again), and `sup.finished`
  appears on its own, well under `FORCE_STOP_TIMEOUT_SECS`, confirming
  `Supervisor` resolves itself rather than needing to be stopped. This run is
  also what found the `DEBASHER_BINDIR` gap (escalation section above): the
  unit tests, with `subprocess.run` mocked, could not have caught it, and did
  not.

## 5. Recovery from a node failure: the writer-dies direction done, the reader-dies direction still open (`engine/debasher_runtime_fbp.py`, `engine/debasher_runtime_transport.py`)

This section describes the design as built for a node cut off from a crashed
peer, and what is still missing for the reverse case. The order in which the
writer-dies direction was actually built, with its tests, mutants and real
runs, is step 2 of section 3's "Order of implementation".

Policy: recovery is localized (only the downed node is relaunched), not a
global rollback; a global rollback is kept as a possible future fallback for
the cases the Contract leaves out (see Future work, section 7). The
Supervisor detects a downed node from the absence of a heartbeat (or,
faster, a dead PID, section 4) and relaunches it through
`debasher_launch_process`, the same operation as an initial launch
(section 2's Startup sequence), with no special "recovery mode" logic; done
and verified with a real `debasher_exec` run (section 4). The relaunched
node reconnects to the Supervisor on its own: the Supervisor's readers
reopen their FIFO after EOF while the node is not resolved (section 4,
"Reading a node's channel across a crash"). What is not automatic is
reconnecting to its business peers, the FBP graph's own channels: the rest
of this section is that design.

### The gap: a node cut off from its business peers

An earlier claim, that the kernel resolves the reconnection with a blocked
neighbor with no additional mechanism, only held for restarting the whole
program: section 2's and section 3's smoke tests relaunched with a new
`debasher_exec` against the same outdir, which recreates every FIFO. For one
node crashing while its neighbors keep running, an `FBPProcess` reader (a
single `open()` plus `for line in fifo`) died at the first EOF and never
reopened, and a writer whose reader had died got `BrokenPipeError` (its
thread died); the relaunched node then blocked forever in `open()` on that
connection. So after a relaunch the node talked to the Supervisor again but
was cut off from every peer, and the introduction's first goal was only met
for a node whose sole connection is the Supervisor. Making `FBPProcess`
readers and writers reconnect needed a signal that, until this design, only
the Supervisor had: does the neighbor's silence mean "crashed, will return"
or "finished on purpose"? The rest of this section is that signal and its
consequences.

### `CLOSE`: telling a finished peer from a crashed one

A process keeps its FIFOs open for its whole life (opens them as it starts,
holds them until `_STOP`), so a reader cannot tell a clean close from a
crash from EOF alone: the EOF is identical for a normal exit and for
`SIGKILL`. `CLOSE` is a fourth envelope type (section 1), decentralized (it
works without a Supervisor, which is optional, and for a manual relaunch
too), sent by the writer in band when it has finished for good; a halt sends
none (section 2's Ordered shutdown subsection). The idea mirrors FIN versus
RST in TCP: EOF after a `CLOSE` means "finished, do not wait", EOF without
one means "crashed, reopen and wait for the relaunched writer".

The reader hands `CLOSE` to the brain thread in order, like any other item,
so it is logged and its port can leave the barrier's pending set; why the
reader then keeps reading and drops what follows instead of ending, and what
`closed_ports` records, is section 3's "`CLOSE` and closed ports", not
repeated here.

A process that exits with an error (an exception, a non-zero exit) sends no
`CLOSE` and is treated as a crash, consistent with the Supervisor's own
detection; a `CLOSE` followed by a later failure is harmless, since peers
keep reading and drop whatever the relaunched node sends afterward
(section 3). The Supervisor's own channel does not need `CLOSE`: it keeps
using the node's `.finished` file, since a `CLOSE` does not prove the node
succeeded, and a node that closed and then failed must still be heard again
when relaunched.

### Ghost connections: holding both ends of a FIFO

`CLOSE` alone does not solve reconnection. A reader that closes and reopens
its FIFO after EOF still has a window, between its own `close()` and
`open()`, in which a writer relaunched inside it gets `EPIPE` and dies
(measured: 1 hang in 250 rounds, with the relaunch forced within
microseconds of the reopen), and EOF is not a reliable event in the first
place: with no gap between the old and the new writer the reader missed 80%
of the EOFs, and with a backlog already in the pipe it never saw one at all,
since the new writer's data just follows on the same file descriptor. So a
reader has to be correct whether or not it ever sees EOF, which the
transport now guarantees by never producing one.

Decided and implemented (2026-09-20): every endpoint holds both ends of its
FIFO, the real one and a ghost of the opposite direction. A reader opens
`O_RDONLY | O_NONBLOCK` (which returns at once) and then `O_WRONLY` (a
reader now exists, from the FIFO's point of view); a writer does the same,
its real end being the `O_WRONLY` one. `O_RDWR` is not used: POSIX leaves it
undefined for FIFOs. Checked with real processes: no open ever blocks,
whatever the start order; writer crash and relaunch with the reader holding
a ghost write end, 210 of 210 rounds without a hang or an `EPIPE`; reader
crash and relaunch with the writer holding a ghost read end, 40 of 40
rounds, the writer never dies and nothing is lost inside the pipe (the only
hole, at most 44 lines, is what the killed reader had already consumed
before it died).

With no EOF the reader never ends on its own: it ends only on a stop
request, woken through a blank line written to its own ghost write end even
if it is blocked in `read()` (checked: 600 of 600 rounds, at most 0.2 ms,
also when the stop precedes the read). The writer never sees `EPIPE`
either: a dead peer means backpressure instead, the writer blocks once the
pipe holds 64 KiB, and since a blocked writer cannot be woken,
`stop_threads()` joins writer threads with a bounded timeout.

Removed as a consequence: `_should_reopen_after_eof` (the base hook and the
Supervisor override), `EOF_FINISHED_GRACE_SECS`, `_EOF_POLL_INTERVAL_SECS`
and `_READER_THREADS_ARE_DAEMON`. `Supervisor` learns that a node finished
only from its `.finished` file, as it already did, and the
`Supervisor.run()` hang listed in the Contract's conformance status goes
away by construction.

Not covered: both endpoints of a channel dying together, before either has
reopened the FIFO. The ghost ends die with their processes, so the unread
messages are destroyed; a third process holding the FIFO open would keep
them alive, checked but not adopted (see the Contract's limits and Future
work, section 7).

### The resync line (`HELLO`)

Ghost connections have a price. With no EOF to delimit a message, a
fragment left by a writer killed in the middle of one larger than
`PIPE_BUF` (4096 bytes on Linux; a truncated line appears only above it: 0
of 100 rounds at 4000 bytes, 53 of 100 at 5000, 98 of 100 at 20000) would
merge with the next good message into one unparsable line and swallow it
(checked: 23 of 50 stress rounds lost a good message this way).

Decided (2026-09-20): every incarnation of a writer starts with one atomic
write, a blank line followed by a `HELLO` line (a fifth envelope type,
consumed by the reader thread like `CLOSE`, section 1). A reader that finds
one unparsable line tolerates it if the next line is `HELLO`, and drops it;
in any other case it is an error, so a corrupt line is never skipped
silently. Checked with messages up to 30000 bytes and writers killed
mid-write: 120 of 120 rounds correct, 50 of them with a real fragment
dropped, no gap and no duplicate. There is no limit on message size. Only
the framework writes to these channels: an external writer must send
complete lines, and a fragment from one shows up as an error. `HELLO` also
tells the reader that its peer (re)connected.

### Opening the FIFOs first in recovery

Decided and done on 2026-09-21. A relaunched node used to open its FIFOs in
`start_threads()`, after restoring its checkpoint and replaying its input
log, so the time it spent recovering lay inside the window in which the
crash of a neighbor could destroy what the neighbor had sent it (this is
about the channel, not the log; section 3 covers what a node keeps of its
own history). Measured with a real `debasher_exec` run of a source and a
sink whose replay took 6 s (the sink killed after 60 messages, the source
sending 50 more and killed 2 s into the sink's replay): the sink received 0
of the 50 in three runs, and all 50 when the source was left alone.

Now `run()` opens the FIFOs before anything else (`_open_fifos()`, which
`start_threads()` still calls for the ports that are not open yet, so a
node driven without `run()` is unchanged), and the same run delivers 50 of
50 in three runs. Seven tests state the guarantee (what a writer sent to a
relaunched reader, and what a relaunched writer had in its FIFO, survives
the crash of the neighbor while the node restores its checkpoint,
initializes and replays, and starting the threads does not open again what
is already open), checked against eight mutants (no early open, opened
after the restore, after `initialize_runtime`, after the replay, opened
again by `start_threads()`, only the input FIFOs early, only the output
FIFOs early, and `start_threads()` no longer opening what is not open; the
last one is killed by a hang, since a writer thread then dies). What
remains of the window is the time to notice the crash
(`HEARTBEAT_CHECK_INTERVAL_SECS` when the process is gone) and to start the
new process.

### End-to-end verification

Checked with a real `debasher_exec` run of a numbered message source, a
consumer that logs what it receives and a Supervisor, twice: `kill -9` of
the writer node's process group and, later, of the reader node's. The
Supervisor relaunched each one, the other node was never touched (and never
stopped heartbeating), and across the reader's outage and relaunch the
consumer logged 630 consecutive messages of the source's second
incarnation, none missing and none duplicated: what was sent while it was
down waited in the pipe. This is the real run named by step 2 of section
3's "Order of implementation".

### The reader-dies direction: one open question

Ghost connections already answer two of the three original concerns for a
dying reader: the writer never sees `BrokenPipeError` (it blocks on
backpressure instead, so there is nothing to reopen or resend), and unread
data in the pipe survives a reader's crash and relaunch (measured, see
"Ghost connections" above: 40 of 40 rounds, nothing lost inside the pipe).

What remains open is the symmetric case of `CLOSE` itself. `CLOSE` travels
only in the direction the data does, from a writer to its readers, so a
node that stops reading from one of its inputs sends nothing back to
whatever writes to it. A writer therefore cannot tell a reader that closed
on purpose (finished for good) from one that crashed and may relaunch: both
look the same, the writer just blocks once the pipe fills. Closing this
needs a signal in the other direction, symmetric to `CLOSE`, and is not
designed.

## 6. Loose ends to check before considering the design closed

- The Contract's "Conformance status" lists the verified gaps between the code
  and its guarantees; they come before anything else in this list.
- **Initiators number their rounds independently.** Each initiator numbers its
  next round as the last epoch it closed or abandoned plus one, so two
  initiators whose counters differ (one was down during a round, say) start
  different epochs for what a person means as one round. A node with inputs from
  both replaces the lower round with the higher one and then waits for a marker
  of the higher epoch that the other initiator will not send, so its rounds stay
  incomplete, with warnings in the log (before the replacement rule the node
  ended instead). Reasoned from the code, not run. Numbering the rounds from
  outside, with the epoch in the trigger, would fix it (see Future work, section
  7).
- **A port that only a source writes to never carries a marker: fixed on
  2026-09-22 with `EXTERNAL_PORTS`.** A round used to wait for the marker of
  every input port that was not a control port, and a source is outside the
  program, so it sends none: the round never closed, the node wrote no
  checkpoint and its input log was not pruned until it reached
  `INPUT_LOG_MAX_BYTES`, which is an error. Found on 2026-09-21 and checked
  with a real run: a node with a data port written from outside and a control
  port, a `start_snapshot` on the control port, and no checkpoint after 3 s.
  Declaring the data port in `CONTROL_PORTS` made the round close, but that was
  only a workaround, since that list is for ports that carry commands. Fixed by
  a new `EXTERNAL_PORTS` list (see external port in the Glossary), excluded
  from the pending set the same way `CONTROL_PORTS` is, but whose `CLOSE`
  closes the port for good, unlike a control port's. A source that does know
  the protocol may still write the marker of the round the initiator opened: it
  is accepted like on any other port (`_on_barrier` does not special-case a
  port that is not pending), which combines the two ways this item used to
  weigh against each other, without coupling a round to the outside by default.
  A node whose only inputs are external has no port left to receive a marker
  from, so it has to be an initiator itself (see initiator in the Glossary),
  triggered the same way a node with only a control port already was; this is
  not a new case, `EXTERNAL_PORTS` does not change it. Checked with a real
  `debasher_exec` run: a `sink` process with an externally fed data port `inf`
  and an externally fed control port `ctl`, `EXTERNAL_PORTS = []` (the old
  behavior): fed `k=1,2,3` on `inf`, `start_snapshot` on `ctl`, no
  `checkpoints/0.json` after 3 s. With `EXTERNAL_PORTS = ["inf"]`: the same
  sequence writes `checkpoints/0.json` right after `start_snapshot`, without
  ever waiting on `inf`.
- **A crash during a round** aborts it, and the mechanism is not designed. What
  exists: a node that comes back has no round open, and the next round of a
  newer epoch replaces a round that another node was left with open (section 2).
  What it can cause, found on 2026-09-21 by reading the code (measured only
  where it says so):
  - A marker that is lost keeps the round of its receiver open. A node that
    crashes after it has captured its state and enqueued its marker, and before
    its writer thread has written it, leaves the next node waiting for it. At a
    node that is not an initiator, a marker of a newer epoch replaces the open
    round. At an initiator nothing replaces it: a `start_snapshot` that finds a
    round open is ignored. So an initiator in a cycle whose marker never comes
    back keeps its round open, with the port of the cycle pending, and takes no
    further snapshot. No node of the cycle writes another checkpoint, and their
    input logs, which only a new checkpoint prunes, grow until
    `INPUT_LOG_MAX_BYTES` is reached, which is an error. Only a `shutdown`
    replaces the open round. Measured with the real class, in one process and
    with the marker never delivered: four `start_snapshot` leave the round open
    and write no checkpoint, and a `shutdown` opens the next epoch as a halt.
    That a crash loses the marker is reasoned. So is the rest: the same happens
    whatever loses a marker, be it a message read from a FIFO and not yet
    written to the input log, or a FIFO destroyed with both its endpoints down
    (see the Contract's limits).
  - **A node that crashes between capturing and closing an ordinary round
    forgets it, and recovers cleanly: confirmed with a real `debasher_exec`
    run on 2026-09-22 by the chaos test's open-round piece** (see
    "Acceptance"). On coming back it has no round open, and the markers that
    arrive later open it again, capture at another position and forward
    another marker. A repeated marker is harmless downstream, but the two
    captures are not the same instant, so the checkpoints of that epoch do
    not form a consistent cut, which matters for a global rollback and not
    for localized recovery (reasoned, not run: the chaos test's own
    criterion does not check for a consistent cut, only for the trace).
  - **A crash during a halt can leave the program permanently half halted:
    confirmed, moved to the Contract's Conformance status** (see "A crash
    during a halt can leave the program permanently half-halted" above),
    since it is a real gap, not just a loose end.

  Candidate mechanisms, none designed: a time limit at the initiators after
  which an open round is abandoned (it heals the loss of a marker whatever its
  cause), re-sending on recovery the marker of the epoch that the node restores
  (a marker of a round that is already over is ignored), and a rule for the
  halt (see the Conformance status entry's own third candidate, which folds
  the halt case into the ordinary-round one instead of giving it its own
  rule).
- **`debasher_stop`, `debasher_status` and `debasher_stats` did not see a
  resident program launched without `--sched BUILTIN`: fixed on 2026-09-20, for
  every program.** Found with real runs: `debasher_exec` forced the built-in
  scheduler for a resident program only in its own memory, while the engine
  tools that operate on an outdir (`debasher_status`, `debasher_stop`,
  `debasher_stats`, `debasher_get_stdout`, `debasher_get_sched_out`,
  `debasher_get_fifo_mirror`) read the scheduler from the command line saved in
  the outdir. Without `--sched` they fell back to the default, which is Slurm
  wherever `sbatch` exists, so on a program with three live nodes
  `debasher_status` printed UNFINISHED for all of them and `debasher_stop`
  printed "The process is not running" and stopped nothing. The fix is general,
  not specific to resident programs: once the scheduler is final (after the
  resident enforcement), `debasher_exec` adds `--sched <scheduler in use>` to
  the command line it saves whenever the user did not give one
  (`record_effective_scheduler_in_command_line`, with
  `debasher::_add_sched_to_serialized_cmdline`), so the tools no longer have to
  work it out again, and a default that depends on the environment can no longer
  differ between the launch and a later query. Checked with real runs: a
  resident program without `--sched` now shows `--sched BUILTIN` in its saved
  line, `debasher_status` and `debasher_stats` report IN-PROGRESS and
  `debasher_stop` stops it; with an explicit `--sched BUILTIN` the option
  appears once; an explicit `--sched SLURM` is still rejected; a general program
  run in debug mode without `--sched` records the machine's default
  (`--sched SLURM`). One consequence, by reading and not tested: an outdir of a
  program that ran under Slurm, opened on a machine without Slurm, now makes the
  tools report that Slurm is not installed, exactly as it already did when
  `--sched SLURM` had been typed, where before the tools silently used the
  built-in scheduler.
- Maximum packet size relative to `PIPE_BUF`: checked (see the findings in
  section 5). Truncation only happens above 4096 bytes and is handled by the
  resync line (section 5), so there is no size limit.
- Whether checkpoints' `channel_state` (section 2's State capture subsection)
  needs to actually be fed back into `process_data` somehow on restore, or is
  genuinely only for external inspection/audit of a consistent global snapshot
  as the introduction's second goal describes: today it is captured and
  persisted but never read back by anything, which is either correct as designed
  or a real gap; not resolved yet. Partly answered: localized recovery does not
  need it (it uses the log), a global rollback would (see Future work, section
  7).
- Verifying that a valid `BARRIER` initiator can actually reach every other node
  in the graph (section 2's Chandy-Lamport subsection): no validation exists
  yet. Section 4's `TRIGGER_PORT` list (one initiator per genuinely independent
  subgraph) covers the *known-at-design-time* version of this, but does not
  validate that each configured initiator can really reach everything in its own
  intended subgraph: that check still does not exist. A graph that becomes
  disconnected only at *runtime* (a node dying permanently mid-execution) is a
  separate case, not a validation problem at all, and is instead handled by
  section 4's `debasher_stop` escalation.
- **A relaunched node that dies before its first heartbeat is never noticed
  again: fixed on 2026-09-22.** After `_declare_down` a node used to stay in
  `_down` until a real heartbeat arrived, and `_check_node` skipped nodes in
  `_down` unconditionally. If the relaunch itself failed (a startup crash),
  nothing re-detected it, `_relaunch_attempts` never grew past 1,
  `MAX_RELAUNCH_ATTEMPTS` never tripped and the Supervisor never resolved. Now
  `_declare_down` resets `_last_heartbeat` to the moment it triggers a
  relaunch, the same grace period `__init__` already gives a brand new node,
  and `_check_node` treats an already-`_down` node the same way once that
  grace period elapses with still no real heartbeat: declared down again,
  counted against the same budget, able to escalate like any other outage.
  Checked with the real class: two `_check_node` calls with
  `HEARTBEAT_TIMEOUT_SECS` set to 0 and a dead PID call `on_node_down` twice,
  where before only once, and repeating it past `MAX_RELAUNCH_ATTEMPTS`
  reaches `on_node_permanently_failed`.
- **Relaunching while the old process is still alive: fixed on 2026-09-22.**
  The heartbeat-timeout path also fires for a live but stuck process (PID
  alive, no heartbeat). `on_node_down` then started a second copy while the
  first still held its FIFOs, and `_launch` removed the old `.id`, so the old
  process was no longer reachable by `debasher_stop` either. Now
  `debasher_builtin_sched::_launch` reads the old `.id` file, if there is one,
  before removing it, and kills that process group with the same
  `debasher::_stop_pid` a manual `debasher_stop` already uses (a no-op if it
  is already gone): one code path for an initial launch and every relaunch,
  with no need to tell a genuine crash apart from a stuck but live process.
  Checked with a real, still-running process left behind by one launch: a
  second launch of the same process/task kills it before starting the new
  one.
- **`debasher_builtin_sched::_wait_until_file_exists` is an iteration count, not
  a time**: 10000 turns of a `[ -f ]` loop with no sleep, about 90 ms. Now that
  `_launch` removes the stale `.id`, a relaunch depends on the new script
  publishing its PID within that window, or `_launch` returns an error although
  the process is starting. Measured on a real generated script (172 KB): 0
  failures in 30 relaunches on an idle machine; under load it could fail. A
  time-based wait would be safer.
- Dedicated concurrency test for the fan-in case with more than one input port
  pending on the barrier. Done,
  `test_two_pending_ports_waits_for_the_second_marker`.
- **A writer whose peer finished for good can grow its own backlog forever,
  with nothing to stop it and no error raised.** Section 5's "The reader-dies
  direction" already covers why a writer cannot tell a reader gone for good
  from one that merely crashed or halted, and why it does not need to: in all
  three cases it blocks on backpressure, which is correct and loses nothing.
  What that leaves open: if the reader is in fact gone for good and nothing
  ever reopens that end again, nothing ever relieves the backpressure either,
  and `send_data` keeps accepting more regardless. `_outbound_queues` is an
  unbounded `queue.Queue()` (`engine/debasher_runtime_transport.py`), and
  `send_data` appends unconditionally to `_unwritten`, the checkpoint's
  outbound backlog for G5 (`engine/debasher_runtime_fbp.py`), so both grow
  without limit for as long as the node keeps calling `send_data` on that
  port. `OUT_BACKLOG_MAX_BYTES` only makes `_save_checkpoint` skip a
  checkpoint that has grown too big; it does not slow or stop the growth
  itself, nor raise an error. No guarantee is broken (G1 to G8): nothing is
  lost or duplicated, the node just keeps using more memory, unbounded and
  unnoticed. Found on 2026-09-22, reasoned from the code, not run.
- **Under heavy system load, `HEARTBEAT_TIMEOUT_SECS` (3 s) is not always
  margin enough, and the Supervisor's own relaunch mechanism turns a
  scheduling delay into a real `kill -9` that can land inside either of
  the two round-related gaps already on record above, with no deliberate
  kill anywhere in the test.** Seen three times so far, only when running
  the whole `test_chaos.py` file together (46 repeats across every piece,
  back to back, three separate full runs on 2026-09-22): twice as a
  `sup.finished` timeout with no explanation at the time (once in the
  single-node-kill piece, once in the `loop`+`sink` piece, neither a
  repeat whose own design should ever need a node to give up); the third
  time, in the single-node-kill piece again, with the actual mechanism
  legible in `sup`'s own log: `fanin` saved its epoch 1 checkpoint, then
  simply stopped appearing (no crash, no traceback in its own
  `.sched_out`) while `loop` and `sink` carried on through two more
  snapshot rounds without it and then "finished cleanly", and `fanin` was
  declared down almost exactly `HEARTBEAT_TIMEOUT_SECS` after its last
  checkpoint, consistent with a perfectly healthy process starved of CPU
  by the other 45 concurrently-run repeats (or by an unrelated mutation
  check running in parallel that same time) rather than an actual crash.
  `debasher_builtin_sched::_launch`'s own "kill any stale PID before
  relaunching" step (see the G7 reconnection fix) then turns that
  scheduling delay into a genuine `kill -9`, at whatever moment it lands:
  inside a halt round, it is "A crash during a halt can leave the program
  permanently half-halted" above; inside the ordered-shutdown race, it is
  the G2 ordered-shutdown gap. In the SAME run that showed the legible
  `fanin` timeline, the concurrently-running `loop`+`sink` piece lost
  exactly 9 values off the end of `loop_seq` with no error reported,
  matching G2's own signature exactly. Never seen running any single
  piece by itself, repeatedly, in isolation: the load, not any one
  piece's own construction, is what triggers it. Not a third gap:
  reasoned from real log timing, not from a dedicated, controlled repro
  (deliberately starving a node of CPU and watching it happen), so the
  causal chain above is inferred, strongly, not proven letter for letter.

## 7. Future work

- **"Wrapper" process for a whole program or a single process**: a new process
  type that wraps the execution of an entire program (internally via
  `debasher_exec`) or of an individual process (via `debasher_exec_process`).
  Looks easy to implement; the only thing to check carefully is how it affects
  checkpointing, and it would only be tricky in the `debasher_exec` case, which
  already has its own checkpointing built in.
- **Dynamic process launching**: the architecture described in this document
  does not, from the outset, support dynamically launching processes. "General"
  programs already sketch a mechanism for this (see
  `data/programs/debasher_dynamic_fanout_taskdone.sh`), but it would need to be
  studied how to combine it with checkpointing, and for Python processes the
  mechanism could be entirely different. Noted here so it is not forgotten and
  can be tackled later, so that `resident` programs have as much expressiveness
  as possible.
- **Fan-out and fan-in sized from the command line (the `ith` convention of
  general programs).** General programs can already write a process whose number
  of connections comes from an option of the command line, and
  `data/programs/debasher_dynamic_fanout_fifos.sh` is the reference for the fifo
  version. `dispatch` documents its output family once, as `-outfith`, and
  defines `-outf0` to `-outf<w-1>` in a loop over its `-w` option (fan-out).
  `worker` is an array process of `w` tasks, and task `i` reads `-outf<i>` of
  `dispatch`. `aggregate` documents `-indith` and defines `-ind0` to `-ind<w-1>`
  from the tasks of `worker` (fan-in). The engine's check of option names
  recognizes the family (`debasher::_actual_opt_is_ith_instance`), and the API
  and the frontend model it (`countSourceOptionId`, `_is_fanout_label`,
  `isFanoutOption`). The goal is that a resident node can have as many input or
  output ports as a command-line option says (`-w`, for example), written the
  same way. The topology stays fixed and is known before the run starts: every
  process and every connection is defined up front, and the engine schedules
  them as in any other program. Only how many there are comes from the option.
  That is what sets it apart from the item above, where processes are launched
  while the program is running. What follows is reasoned from the code, nothing
  of it is built or tried:
  - Ports. `INPUT_PORTS` and `OUTPUT_PORTS` are class constants, so a node with
    a family would compute its port lists from its options when it is built
    (`_input_ports()` and `_output_ports()` are methods already, and the
    `Supervisor` builds its own from `NODE_PORTS`). The names must be the same
    in every incarnation, because `closed_ports` and the sequence numbers of G5
    in the checkpoint are keyed by port name: a relaunch that finds another set
    of ports should fail loudly.
  - The barrier, `CLOSE` and the input log do not depend on how many ports there
    are, since they already loop over the declared lists: a fan-in node is the
    case of several pending ports that the tests cover, and a fan-out node
    already forwards the marker on every output port.
  - Routing is part of `process_data`. Which output port a fan-out node picks
    for a packet has to be deterministic (a function of the packet, or of a
    counter kept in the node state), or a replay would send a message to another
    worker than the first time and the numbers of that channel would label
    different messages. The dispatcher of the general example does it that way
    (the block index modulo `w`, in `dynamic_fanout_dispatcher.py`); a choice by
    worker load would break the guarantees.
  - Array processes. The `w` workers are `w` nodes, `(process_name, task_idx)`,
    each with its own directory, checkpoints and input log, and the `Supervisor`
    already accepts such names in `NODE_PORTS`. Not known: whether
    `define_opt_from_proc_task_out` works for the fifos of resident nodes, how
    the script generation and the frontend would express it for resident
    processes, and how the chaos test would cover it (a fan-out to several
    workers and a fan-in from them are two more shapes for its reference
    program).
- **Auxiliary script to reset checkpoints across a whole topology**: deleting
  (or moving) every node's checkpoint folder before launching forces a clean
  start with no special-case code needed anywhere (section 2's Startup sequence
  subsection); the script itself is not written yet.
- **Global (coordinated) rollback, as a fallback to localized recovery**: noted
  here, not designed and not built. Localized recovery (section 5) remains the
  policy for the ordinary crash of a node. A global rollback would be the safe
  harbor for the cases the Contract leaves outside its guarantees, an
  alternative to the narrower, targeted repairs "Repairing messages destroyed
  with a FIFO" below lists for one of them specifically: detect the
  violation, stop, rewind every node to the last consistent cut, resume.
  Cases where it would be used: a guarantee that cannot be kept is detected
  (a hole in a channel's sequence numbers, a missing or
  corrupt checkpoint or log, an incompatible schema version); a node fails
  permanently (today the escalation of section 4 ends in `debasher_stop`; with a
  rollback it becomes "stop, fix, rewind, resume"); several connected nodes, or
  all of them, crash together with inputs that cannot be regenerated (the
  contents of the FIFOs are gone); a crash during a snapshot round, if aborting
  rounds turns out to be harder than falling back to the last complete epoch; a
  deliberate rewind requested by an operator. Not for the crash of a single
  node. The price is the work done since the chosen epoch, and the external
  inputs received since then (delivery at that boundary is at most once).

  Like resetting checkpoints (previous item), it can be done from outside, by
  manipulating files, with no special mode in the startup sequence (which always
  loads the highest epoch and replays the log): an auxiliary script run while
  the program is stopped. Points to settle when designing it:
  - The target epoch is the highest one present in the checkpoint folder of
    every node (the minimum of their latest epochs, if contiguous). Every node
    deletes, or moves aside, the checkpoints above it, which belong to a round
    that not everybody completed. The target has to lie inside every node's
    retained window (`CHECKPOINT_RETENTION`), so the interval between snapshots
    bounds how far back a rollback can go.
  - The log records above the position that the target checkpoint reflects must
    be discarded too: the startup replays every record after the loaded
    checkpoint, so leaving them would turn the rollback into a mass local
    recovery, with the duplicates between nodes that this implies.
  - `channel_state` is needed here, unlike in localized recovery: the messages
    in transit at the cut were sent by nodes that, once restored, will not send
    them again, so they have to be redelivered. This answers the open question
    about `channel_state` in section 6. A way to do it with no new logic: the
    script appends them to the log of the receiving node as records after the
    target position, which the unchanged startup already replays.
  - An epoch number must identify a single round. Today the initiator derives it
    from its own last epoch, which can go back when the initiator restarts, and
    after an aborted round two nodes could hold a checkpoint with the same
    number that comes from different rounds, so "the highest common epoch" would
    no longer be a consistent cut. A round identifier carried by the marker and
    stored in each checkpoint would let the script check it. (Found by reading
    the code, not tested.)
  - How `debasher_exec` relaunches a program some of whose nodes are already
    `finished` (to be checked against the rerun logic). A new run recreates the
    FIFOs, which is what a rollback needs.
- **Repairing messages destroyed with a FIFO.** When both endpoints of a channel
  crash before either has reopened the FIFO, what the FIFO held is destroyed,
  and only what the writer produces again after its latest checkpoint comes back
  (see the Contract's limits). Ways to widen that, none designed or tried:
  - The writer restores an older retained checkpoint and replays from there. The
    input log is kept back to the `capture_pos` of the oldest retained
    checkpoint, the numbers are regenerated the same, and the readers drop what
    they already have as duplicates, so everything sent since that checkpoint is
    repaired, at the price of re-executing that stretch at every recovery. It
    cannot close the gap in general: a channel is one-way, so the writer does
    not know how far its reader got and cannot tell how far back is enough. It
    also has to keep the epoch numbering of the latest checkpoint, because a
    node numbers its next round from the epoch of the one it restores. (Reasoned
    from the code, not tried.)
  - A log at the sender with acknowledgements, the alternative rejected in
    section 3: the writer keeps what it sent until the reader has it in a
    checkpoint. It would repair everything, but it needs a way back from the
    reader and coordination to delete.
  - Auxiliary ghost connections: holders of a channel's FIFO other than its two
    endpoints, placed somewhere else in the program, so that the unread messages
    survive while both endpoints are gone. A read end opened without blocking is
    enough to keep what a pipe holds (checked with real `kill -9`: 50 of 50
    survive with a third process holding one). This closes the "both endpoints
    of a channel crashed" limit itself (see the Contract's Limits and
    non-goals), not just widens it: the writer's relaunch still replays its
    input log deterministically and resends, with the same numbers, everything
    after its checkpoint's `capture_pos` (G5), so whatever the auxiliary holder
    kept alive simply arrives ahead of that resend and the reader's own
    existing dedup (`_on_arrival`'s "a number not above the last one accepted
    is a duplicate", see section 1) drops the resend without any new logic on
    the reading side. Nothing about G5 or replay would need to change; the
    only new part is the holder itself. It does not touch the Contract's
    other limit, "a message read from a FIFO but not yet written to the input
    log" (a window internal to one process, between its own `read()` and its
    own log `write()`, that no outside fd can protect), which is narrow
    (microseconds) and not, on its own, worth chasing further.

    The simplest holder is a single process for the whole program, the
    `Supervisor` or one of its own, but if it dies together with both
    endpoints the loss is back. Giving it its own heartbeat channel to the
    `Supervisor`, like any business node's (it would carry no business logic
    at all: open every channel's auxiliary end and do nothing else, so it
    should be far less likely to crash than a node that also processes data),
    narrows that from "if it ever dies" to "if it dies at the exact moment
    both real endpoints of some channel are also down", since the `Supervisor`
    would otherwise detect and relaunch it like any other node; the launch
    mechanism's own "kill the stale PID first" step
    (`debasher_builtin_sched::_launch`) still leaves a brief window, of
    however long its own relaunch takes, where nobody holds that channel, so
    this narrows the risk rather than closing it outright. It does not
    answer who supervises the `Supervisor` itself, a separate, already-open
    question elsewhere in this document. A series of holders spreads the
    same risk further without needing this supervision at all: for example
    every node also holds an auxiliary read end of the channels of its
    neighbors (each already a supervised node in its own right), so that a
    channel loses its contents only if its two endpoints and all its
    auxiliary holders are gone within one recovery, which is far less
    likely when the crashes are independent (reasoned, not measured). Open
    questions for either shape: who holds which channel, how a holder
    learns the paths of FIFOs that are not its own (a node knows only its
    own options today), whether a relaunched holder reopens its auxiliary
    ends first thing, as it does with its own, and what becomes of the
    auxiliary ends of a node that has finished for good. Not designed.
  - The global rollback above, which rewinds both nodes to the last consistent
    cut and redelivers from `channel_state` the messages that were in transit at
    the cut.
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
- **Nodes that emit on their own.** Today a node acts only in reaction to what
  it receives, and what starts the activity of a program, the first message of a
  cycle or a tick of a clock, is written into an input port from outside by a
  source (see "source" in the Glossary). Whether a node should also be able to
  emit by itself, for example a source inside the program, is left to be
  assessed. It would need a hook that the brain thread calls when nothing
  arrives, so that the state a node captures stays in step with what it has
  sent; a pace for it, since the outbound queue has no limit; a way to finish
  for good; and, for a node that also has inputs, a record in the input log of
  where each call fell, so that a replay reproduces it. Reasoned, not tried.
  Decided on 2026-09-21 to keep sources outside the program for now.
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
  `send_data` from outside a handler. Raised on 2026-09-21 as the way to have
  the flow of outputs under the control of the framework. Reasoned, not tried.
- **A `Supervisor` that serializes rounds** (perhaps never done). It would track
  which nodes have reported `checkpoint_saved` for an epoch (today it only logs
  it), leave out the nodes that finished, and relay a trigger only when the
  previous round is complete or a time limit has passed; it could also put the
  epoch in the trigger, so that all the initiators number a round the same. It
  would avoid rounds that replace each other and would tell which epochs are
  complete cuts. It would not replace the rule that a newer round replaces an
  older one at a node, which holds whatever the source of the trigger (a person
  writing into the fifo of an initiator, a timer, a `Supervisor` relaunched by
  hand, a node relaunched in the middle of a round). It is doubtful because a
  manual trigger reaches the `Supervisor` as a command that it relays without
  interpreting, and serializing means interpreting `start_snapshot` and
  `shutdown`: how to add that for the triggers that a person writes is not
  clear, and it would only cover the nodes that report to the `Supervisor`. Not
  designed.
