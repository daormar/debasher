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
  own bookkeeping (`processed_upto`, `closed_ports` and the sequence numbers).
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
  the consistent cut. A **halt** (parada ordenada) is a round with `halt` true:
  each node stops after saving its checkpoint, and the program is resumed later
  by relaunching every node, which loads it.
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
  input-log redesign, the engine's own bookkeeping: `processed_upto`,
  `closed_ports`, `out_seq` and `last_seq`. Only the last `CHECKPOINT_RETENTION`
  are kept.

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
- **`processed_upto`**: the position of the item whose processing captured the
  node state. Everything up to it is reflected in the checkpoint's node state;
  recovery replays what comes after it.
- **torn tail** (cola partida): an unterminated last line that a process killed
  in the middle of a write leaves in a file. It can happen at any record size
  (measured, see the input-log redesign). A record counts only if its line ends
  in a newline and parses as JSON, so a torn tail is ignored on replay, and no
  incarnation ever appends to an existing segment.
- **replay** (reproducción): re-executing `process_data` on the `DATA` records
  after `processed_upto`, in log order, when a node starts. It reads from disk
  and writes nothing to the log. Earlier text calls it "drain".
- **prune** (poda): deleting what no retained checkpoint needs: the checkpoints
  beyond `CHECKPOINT_RETENTION` and, in the input log, the whole segments that
  end at or before the `processed_upto` of the oldest retained checkpoint.
- **sequence number, `seq`** (número de secuencia): the counter, per channel,
  that the sender puts in each `DATA` so that the receiver can drop a duplicate
  produced by a replay and detect a gap. `out_seq` (the counter of each output
  port) and `last_seq` (the last number accepted on each input port) are stored
  in the checkpoint. Not the same as `pos`: `seq` is per channel and assigned by
  the sender, `pos` is per node and assigned by the receiver.

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
  replay the input log after `processed_upto`, then start its threads. Localized
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
  it. A relaunched node holds its FIFOs from the first step of its recovery,
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
  latest checkpoint and replays its input log after `processed_upto`, so it
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
relaunching them. Pass criterion: the final state and output equal those of the
failure-free run, with no duplicated and no missing message. The exception
follows from two limits of the Contract, after which a message can be lost
beyond repair: both endpoints of a channel crashed before either reopened the
FIFO, and a node killed with a message that it has read from a FIFO but not yet
written to its input log. A run that hits either passes if it ends with an error
of G8 that names the channel and the numbers of the missing messages, in place
of the reference result. What always fails is a different result with no error
(a message duplicated, lost or altered that nobody reported) and a run that
never ends and reports nothing. The harness records when it kills each node and
when that node has been relaunched, so it knows which runs hit the first limit.
The second cannot be seen from outside, so a G8 error in a run that did not hit
the first one is examined, and it has to be shown to come from it and not from a
fault of the replay. The chaos test runs against real `debasher_exec` runs, not
mocks.

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

Each one was verified by running the real classes, not only by reading the code.
The ones marked fixed were fixed on 2026-09-20; the others are to be fixed
before any guarantee is relied on.

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
- **G5 not implemented.** Replay after a crash re-emits the outputs the node had
  already sent, and a running neighbor receives them again (verified with a real
  run). Mechanism decided on 2026-09-20.
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
  source accepts two `start_snapshot` in a row, since each of its rounds closes
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
  `INPUT_PORTS = ["inf"]`). `FBPProcess.run()` parses `argv` generically into a
  `self.opts` name -> value dict (the engine's existing `-optname value` CLI
  convention, untouched); `INPUT_PORTS`/`OUTPUT_PORTS` tell it which of those
  entries are FIFO paths to open reader/writer threads on. Any other option
  (e.g. a plain `-threshold` value) stays available in `self.opts` with no
  special handling. `CONTROL_PORTS` names which of the `INPUT_PORTS` carry only
  commands (see control port in the Glossary); a name that is not an input port
  is refused when the node is built.
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

### State capture and checkpoint schema

- `capture_node_state()`: only serializable logical state, never runtime
  resources (connections, sockets, file handles); those are rebuilt by
  `initialize_runtime()` instead, see the Startup sequence below.
- Channel state: a copy of the `DATA` that arrives on a still-pending port
  during an open barrier round (the generic barrier logic above) is saved as the
  checkpoint's own `channel_state` field
  (`_save_checkpoint(epoch, node_state, channel_buffers, processed_upto)`).
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
  `processed_upto` and `closed_ports` (done); `out_seq` and `last_seq` will join
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
log and replay it after the checkpoint's `processed_upto`, all of it if there
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
- Without cycles: the initiator must be a root/source; if it has no input ports,
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
- A node finishes its execution only after closing its epoch (marker received on
  every one of its input ports), never before. Done: `halt=True` sets
  `self._halted`, and `run()` blocks on it before calling `stop_threads()`.
- A halt sends no `CLOSE`. Done on 2026-09-20: `run()` stops its threads with
  `stop_threads(close=False)`, so each writer sends what is already queued and
  stops. `CLOSE` says that a writer has finished for good, and a halted node is
  resumed later: had it sent one, the reader at the other end could keep it in
  its input log after its `processed_upto` (measured, see section 3), and a
  resume would take the node for a finished one. A node that ends on its own
  calls `stop_threads()`, whose default does send `CLOSE`.
- Resumption: relaunch every process. It is the ordinary Startup sequence above,
  with no special case for a halt: each node loads the checkpoint that the halt
  closed and replays its input log after that checkpoint's `processed_upto`.
  What is replayed is what the node processed between capturing its state and
  closing the round (the messages that were in transit at the cut, which its
  checkpoint also holds as `channel_state`) and anything that reached its log
  after that. The node ends in the state it had when it stopped, and
  re-executing those messages is deterministic, like any other replay.

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
brain thread reached it. That design had four verified faults: everything
waiting in the inbound queue (which has no limit) was lost if the node crashed;
a barrier round diverted the `DATA` of a pending port so that it never reached
`process_data`; the log was one file per port and epoch, so the order across
ports was lost on replay; and a message processed after the snapshot but before
the round closed was logged in a segment that recovery skipped. A fifth was
found while implementing it: a node that crashed before closing its first epoch
replayed nothing. All five were verified with the real classes and are fixed
(see the Contract's conformance status). What follows is the design as built.

- **One ordered input log per node.** The reader threads write each message to
  it when it arrives, in the same critical section (one lock) that puts the
  message on the inbound queue. The brain thread consumes the queue in order, so
  the log order is the processing order (checked with six reader threads: 0 of
  120000 positions differ with the lock, nearly all without it). Every queued
  item (`DATA`, `BARRIER`, `INTERACT`, `CLOSE`) gets a position `pos`, a counter
  of the receiver that is global to the node, and is written to the log: the log
  is then the node's complete input history (the fifth goal of the
  Introduction). Only `DATA` is replayed.
- **The barrier processes and records.** A `DATA` on a port whose marker has not
  arrived is processed at once, as any other, and a copy goes to
  `channel_state`, as in the classic algorithm. Nothing is diverted, so nothing
  is reordered and no separate journal of the processing order is needed. **Done
  on 2026-09-20**, see the order of implementation below.
- **The checkpoint stores positions, not the epoch of a log segment.** Besides
  `node_state` and `channel_state` it holds `processed_upto` (the `pos` of the
  item whose processing captured the node state: a peer's first marker, or the
  `INTERACT` that started the round), and the schema version is 2. **Done on
  2026-09-20.** `closed_ports` (the input ports whose `CLOSE` the brain thread
  had processed at that point, also done on 2026-09-20, see the item on
  `closed_ports` below), `out_seq` (the sender counter of each output port, see
  below) and `last_seq` (the last sender number accepted on each input port)
  join it in the step that needs them, in the same version. Every capture
  happens on the brain thread (the periodic snapshot timer does not exist yet),
  so `processed_upto` is always well defined.
- **Recovery** is the startup sequence of section 2: restore the latest
  checkpoint, then replay, in order, every `DATA` record of the log with `pos`
  greater than `processed_upto`, all of them when there is no checkpoint, since
  the node state is then the default one. That covers what had been processed
  before the crash and what had arrived but not yet been processed, with no
  distinction between the two. A `CLOSE` record after `processed_upto` only adds
  its port to `closed_ports`, which the checkpoint restored as it was at the
  capture. The counter `pos` is rebuilt from the checkpoint and the log, and
  `out_seq` and `last_seq` will be. Replay writes nothing to the log. **Done on
  2026-09-20.**
- **Pruning** is by position: the log is split into segment files named by their
  first `pos`, and those that end below the `processed_upto` of the oldest
  retained checkpoint are deleted; the active segment is never touched.
- **Record format and files (decided 2026-09-20).** The log is one directory,
  `<execdir>/log/`, not one per port, holding segments named `<first pos>.log`
  and ordered numerically, like `<epoch>.json`. A record is one line,
  `{"pos": N, "port": "<port>", "env": <the envelope line exactly as it arrived>}`.
  The envelope is embedded by string concatenation, not re-encoded: building a
  record of about 100 bytes takes 0.18 microseconds this way and 5.5 with
  `json.dumps`, and one of about 1 KB takes 0.27 against 8.2, at a cost of 28
  more bytes per record. So the critical section stays short, every line is
  valid JSON, and the `seq` of G5 travels inside `env` with no change to the
  format. A record is complete only if its line ends in a newline and parses as
  JSON; replay ignores an unterminated last line (a torn tail) and requires
  consecutive positions across records and segments, failing loudly otherwise.
  Each record is written with one `os.write` to an `O_APPEND` descriptor (looped
  over partial writes) before the item is queued, never through a buffered file
  object. Measured with real `kill -9`: a buffered `f.write` without `flush`
  lost acknowledged records in 98 of 100 kills (3751 records in all), while
  `f.write` plus `flush` and `os.write` lost none (`os.write`: none in 1300
  kills). A torn tail is real at any record size: 1 of 300 kills at 100 bytes, 6
  of 300 at 1000, 11 of 100 at 4000 and at 5000, 0 of 100 at 64 KiB and at 1
  MiB, 49 of 100 at 16 MiB (fragments of real records, for example 84 bytes of
  one of 100). Hence a new incarnation never appends to an existing segment: it
  starts a new one. A segment is also started when the active one reaches a size
  limit, and files are created at the first append, so there are no empty
  segments. Nothing rotates when a round captures the node state: that would
  couple the brain thread to the readers to save, at most, one segment of disk.
- **Startup, counters, pruning and cap (decided 2026-09-20).**
  - *Counters.* `next_pos = max(last complete record, processed_upto) + 1`,
    found by reading only the last segment that has a complete record. A segment
    with no complete record (only a torn fragment) is deleted at startup: the
    next record reuses its position, so a new segment would collide with its
    name, and the fragment holds nothing.
  - *Startup order in `run()`:* open the FIFOs, load the latest checkpoint,
    `restore_node_state`, `initialize_runtime`, recover the log, replay the
    `DATA` records with `pos > processed_upto`, start the threads. With no
    checkpoint the node state is the default one and `processed_upto` is 0, so
    the whole log is replayed.
  - *What replay checks.* It starts at the last segment whose name is at most
    `processed_upto + 1` and fails loudly if the log starts above
    `processed_upto + 1`, if the positions from there on are not consecutive, if
    a segment does not start where the previous one ended, or if a line that
    ends in a newline does not parse. A log with no records is not an error,
    because it cannot be told from a log that was lost (the sequence numbers of
    G5 detect that later). A log whose last record is below `processed_upto` is
    not an error either, since everything in it is already in the checkpoint:
    the numbering then continues after `processed_upto`.
  - *Cap.* `INPUT_LOG_MAX_BYTES` (renamed from `MESSAGE_LOG_MAX_BYTES`, 100 MiB
    by default) is per node and kept in memory, so checking it costs nothing
    (before, every message listed the directory and called `stat` on every
    file). Exceeding it raises in the reader thread before anything is written,
    like any other death of a thread. It should never trip in ordinary
    operation: it would mean that no epoch is closing, which the periodic
    snapshots of section 2 are there to prevent. `INPUT_LOG_SEGMENT_BYTES` (4
    MiB by default) is the size at which a segment is closed.
  - *Pruning.* After each checkpoint is saved, whole segments other than the
    last one are deleted when the next segment starts at or below the
    `processed_upto` of the oldest retained checkpoint plus one. That value is
    read from the JSON of the oldest retained checkpoint on every round:
    measured cost 12 ms for 0.9 MB, 115 ms for 9.3 MB and 1.16 s for 95 MB,
    about a quarter of the cost of writing it (63 ms, 477 ms, 4.9 s), so no
    state is kept in memory for it. A checkpoint that cannot be read aborts the
    prune with an error. Pruning runs on the brain thread under the same lock as
    the appends.
  - *A failed write poisons the log.* After any failed append the log refuses
    more appends until the process restarts. Measured with a real short write
    (`RLIMIT_FSIZE`): the third record wrote 50 bytes and raised `EFBIG`, the
    fourth failed too, and a fragment of 50 bytes stayed at the tail. With a
    transient error (a full disk, not reproduced here) another reader thread
    could otherwise append behind the fragment and bury it in the middle of the
    file, where replay rejects it. With the rule, the fragment stays the torn
    tail of its segment, every reader thread dies with the same error, the
    heartbeat stops and the `Supervisor` relaunches the node.
- **Arrival, positions and checkpoint schema (decided 2026-09-20).**
  - *Arrival hook and lock.* A reader thread no longer puts what it reads on the
    inbound queue: it calls `_on_arrival(tag, envelope, line)`, with the text
    exactly as it arrived. The base class puts `(tag, type, payload)` on the
    queue, so the `Supervisor` does not change. `FBPProcess` overrides it: under
    one lock it takes the next position and puts `(pos, port, type, payload)` on
    the queue (from the last piece on it also appends the record to the input
    log there, before the put), so that position order is processing order.
    Checked with six reader threads on real fifos and 1500 messages: the
    positions that the brain thread saw were exactly 1 to 1500 in order, and the
    test fails when the lock is removed. The brain thread does not take the
    lock, except to prune.
  - *What gets a position.* Every queued item (`DATA`, `BARRIER`, `INTERACT`,
    `CLOSE`), starting at 1; only `DATA` is replayed. `HELLO` never reaches the
    queue. Anything that starts a round from inside the node, such as a snapshot
    timer, goes through the same hook, so `processed_upto` is always defined; 0
    means that nothing had been processed.
  - *Checkpoint schema.* Version 2 adds `processed_upto`: the position of the
    item whose processing captured the node state (a peer's first marker, or the
    `INTERACT` that started the round), taken when the round opens and not when
    it closes. `closed_ports` joined it later the same day, and `out_seq` and
    `last_seq` will join the same version in their own steps, since the branch
    is not released. A node restored from a checkpoint numbers after its
    `processed_upto` (from the last piece on, after the larger of that and the
    last record of its log). A checkpoint of version 1 is refused.
- **`CLOSE`** means that the writer has finished for good, and only that. **A
  halt sends none (decided and done on 2026-09-20).** Measured with real runs of
  a producer and a consumer that halt, with the earlier behavior: the producer's
  `CLOSE` reached the consumer's input log after its `processed_upto` in 38 of
  40 halts, and in 0 of 40 when the producer's checkpoint was slow, because the
  consumer had stopped reading by then. Whether a halt left a `CLOSE` in the log
  was a race between the two nodes, and the rule that a `CLOSE` after
  `processed_upto` closes the port when the log is replayed would have closed,
  at a resume, the ports of producers that were coming back. For a writer that
  has finished, the reader hands the `CLOSE` to the brain thread like any other
  item, so it is logged, and **then keeps reading but drops everything that
  follows (decided and done on 2026-09-20)**: nothing after it is decoded,
  logged or queued, and the first line warns, once per port, that the writer
  said something after its `CLOSE`. The reader does not end, for two reasons
  measured with real runs. A reader that ended left the consumer's heartbeat
  unhealthy for good, a special case for the heartbeat to carry and, with a slow
  brain, a window as long as the brain's backlog. And a node that sent `CLOSE`
  and then failed is relaunched, and its new incarnation, with nobody reading,
  filled the pipe (351 of 400 messages of 1 KB stayed blocked in its writer,
  which was alive and looked healthy, so the program never ended); dropped
  instead, all of them are delivered. What it sends after a `CLOSE` can only
  repeat what it delivered before, or be its own fault, so the consumer's state
  must not change. The `Supervisor`'s readers deliver what follows, since a node
  that closed its channel may be relaunched and must be heard. A relaunched node
  starts the readers of the ports that had already closed in this mode (done on
  2026-09-20, with `closed_ports`). The port leaves the barrier's pending set
  (done on 2026-09-20, 4.4). Control ports are the exception: their reader
  delivers what follows a `CLOSE`, and the `CLOSE` is neither recorded nor
  restored (4.5). This replaces the marker file proposed before.
- **`closed_ports`** (decided and done on 2026-09-20) lists the input ports
  whose `CLOSE` the brain thread had processed at the capture, that is, those
  with a `CLOSE` record at a position at or below `processed_upto`. It is taken
  at the same moment and on the same thread as the node state and
  `processed_upto`, so the three describe one instant, and by the order in which
  the brain thread processes the items, not by what the reader threads have
  read, since they run ahead of it. Two other definitions were rejected, with a
  node of three ports: a closes before the round opens, and c closes after it,
  with a message of c in between. The set that the reader threads had logged by
  then says a and c, and using it to leave c out of the pending ports, as the
  barrier does, closes the round at once and drops the message of c from the
  channel state, although it was in transit at the cut. The set when the round
  closes also says a and c. Both leave a checkpoint that says that c is closed
  while its message lies after `processed_upto` and is still to be replayed. The
  exact definition is what lets the replay check that no `DATA` record follows
  the `CLOSE` of its port, which is an error (the log or the checkpoint is
  corrupt) and can be demanded because nothing after a `CLOSE` is logged. The
  set is saved sorted in the checkpoint (schema 2; the field is required, so an
  older checkpoint fails to load with a `KeyError`), because pruning deletes the
  segments below `processed_upto` and the `CLOSE` of a port closed long ago goes
  with them. Recovery restores it and adds the port of each `CLOSE` record after
  `processed_upto`, and the readers of the ports that are then closed start in
  the mode that drops what their writers send, so that a relaunched node behaves
  like the incarnation that read the `CLOSE`. A `CLOSE` that arrives between the
  capture and the close of the round is not stored in the checkpoint file: like
  the `DATA` that arrives then it is history of the channel after the cut, and
  recovery finds it in the log. Only a global rollback, or an audit of the cut,
  would need it in `channel_state`. What a module sees does not change:
  `capture_node_state()` and `restore_node_state()` handle the node state and
  nothing else, and no hook tells the module about a `CLOSE`.
- **The barrier and the ports that have closed (decided and done on
  2026-09-20).** A round does not wait for a port whose writer has finished,
  because no marker will ever come from it. Four rules. A `CLOSE` that the brain
  thread processes while a round is open takes its port out of the pending
  ports, keeps what was already recorded for it in the round's channel state,
  and closes the round if it was the last one; if the marker of that port had
  already arrived, nothing changes. A round that opens later starts with the
  input ports, minus the one whose marker opened it, minus the closed ports, and
  forwards its marker on the outputs as always; a node whose inputs have all
  closed behaves as a source. A port that is closed at the capture has no entry
  in the channel state, and one that closes during the round keeps the entry
  that it had. A node that has finished takes no part in later rounds: the cut
  stays consistent because everything it sent precedes its `CLOSE` in the
  channel, and what arrived after the capture is in the channel state. The set
  that decides is the brain thread's (see `closed_ports`), in the order of the
  input log. Before this, measured with the real class on a node of three ports,
  a closed port left a round open for good and the marker of the next round
  ended the brain thread with a `ValueError`, with no checkpoint written; now
  the first round closes with the `CLOSE` of its last pending port and the
  second, opened when a and c had closed, closes as it opens, each with its
  checkpoint.
- **Sequence numbers (G5).** The sender numbers the `DATA` of each output
  channel 1, 2, 3, and stores its counters in its checkpoint. The receiver drops
  a `DATA` whose number is not above the last one it accepted from that channel
  (a duplicate produced by a replay) and treats a jump as a lost message (G8).
  The check happens in the reader thread, before the record is written, so a
  duplicate is never logged or processed.
- **What is left.** The window between the reader thread taking a block from the
  FIFO and appending each of its messages. A message lost there is not
  recovered, since its sender considers it delivered, but the jump in the
  sequence numbers detects it.
- **Rejected**: a bounded inbound queue (the reader still consumes blocks of up
  to 64 KiB from the FIFO); a log at the sender with acknowledgements
  (coordination and deletion between two processes); a second log with the order
  of processing (needed only if something reorders, and nothing does now);
  accepting the loss (it happens exactly when the node is busy).
- **Order of implementation (agreed 2026-09-20)**, one step at a time, each with
  tests, a mutation check (see Acceptance) and a real `debasher_exec` smoke
  test:
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
       `processed_upto`, taken when the round opens; and a restored checkpoint
       makes the numbering go on after it. The old log still works. 13 new
       tests, checked against two mutations (without the lock the order of the
       positions breaks, and taking the position when the round closes fails
       four of them). Checked with a real `debasher_exec` run of two sources and
       a fan-in sink with two snapshots and a halt: all 800 messages were
       processed, the positions were strictly increasing, and in all three
       checkpoints the saved total equals the sum of what the sink had processed
       up to `processed_upto`.
     - 3.3 The switch. **Done 2026-09-20**: the reader threads append the record
       and queue the item under one lock, and the brain thread no longer logs; a
       node opens the log after restoring its checkpoint and replays the `DATA`
       records after `processed_upto` (all of them when there is no checkpoint);
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
       sink's log held a `CLOSE` after `processed_upto` in 2 of 2 runs, with the
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
       adds the `CLOSE` records after `processed_upto`, replay fails on a `DATA`
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
       source; a later round after two ports closed opens and closes without
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
  5. G5: sequence numbers, deduplication and detection of gaps.
  6. The chaos test of the Contract.

(Placed right after `FBPProcess` rather than near checkpointing/recovery, and
before the `Supervisor` class: `FBPProcess` itself already needs this to replay
its own log on restart, and `Supervisor`'s design, next, can build on it too.)

**Implemented entirely inside `FBPProcess` itself, in Python, not on top of the
engine's `--mirror` fifo tap.** An earlier draft of this section routed the
message log through `--mirror`, forced on for every resident data fifo, with
resident-specific sequence numbering and epoch-segment rotation layered onto the
mirror tap. That was abandoned once it became clear it was subjecting a
mechanism only ever meant for occasional manual debug inspection (the frontend's
"Watch FIFO", `debasher_get_fifo_mirror`) to a load and traffic pattern
(back-to-back messages, no reader-side pacing) it was never designed for: real
bugs were found and fixed while implementing that version (a SIGPIPE crash when
a repeated-open reader is momentarily detached, and a bats-core fd collision),
and both would never have existed with this design instead. `--mirror` stays
exactly as it always was, for that one original, occasional debug use case;
nothing about it is forced on for `resident` programs, and since 2026-09-20 a
`resident` program that declares `--mirror` on a fifo is rejected when it is
loaded (`debasher::_check_fifo_mirror_allowed`, called by `define_fifo_opt` and
`define_fifo_opt_generator`), so a mirror tap can never sit between two resident
processes.

- **Locality: each process logs what it itself receives, not what its neighbor
  sends.** The process that needs to replay a log is always the one relaunched
  after a crash (itself, not its neighbor), so the log belongs on the *reader*
  side, in the restarting process's own `DEBASHER_PROCESS_EXECDIR`, not the
  writer's. This removes any need to reach into a neighbor's directory, and
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

### Escalation on a permanent node failure

A node given up on for good can, in the worst case, have been the only path (in
the business-data graph) to some other node(s); if so, no ordered shutdown can
ever reach them through the graph itself, since the barrier marker only ever
propagates along the same edges as `DATA` (section 1's channel topology). Rather
than build a second, parallel broadcast mechanism (a direct connection from
`Supervisor` to every node, bypassing the graph, with a new barrier-skipping
command), which would mean N extra FIFOs to wire per program, and would put
every ordinary shutdown at risk of losing the barrier's consistency guarantees,
not just the pathological case, `on_node_permanently_ failed`'s default
implementation escalates in two phases, reusing what already exists:

1. Send `shutdown` to every configured `TRIGGER_PORT` initiator (ordinary
   ordered shutdown, unchanged); this covers, cleanly and consistently, whatever
   part of the graph remains reachable.
2. Wait up to `FORCE_STOP_TIMEOUT_SECS`, watching the same "done" tracking
   described above. If not every node in `NODE_PORTS` reaches "done" within that
   window (the signature of a graph left disconnected by the dead node), fall
   back to calling **`debasher_stop -d <dirname>`**, an existing, unmodified
   engine tool (`engine/debasher_stop.sh`) that walks every process of the
   program and sends `kill -9 -- "-$pid"` (a process-group `SIGKILL`, via the
   same `.id` PID files already used for the fast-path detection above) to any
   still `INPROGRESS`. It does not depend on the business graph's connectivity
   at all, so it is a guaranteed way to actually end the whole program
   regardless of what died or what it was connected to. `dirname` (the program's
   own base output directory, not a process's own exec dir) needs no new engine
   export: it is exactly `dirname(dirname(DEBASHER_PROCESS_EXECDIR))` (confirmed
   against `debasher::get_prg_exec_dir_given_basedir`,
   `<dirname>/__exec__/<processname>`).

This deliberately accepts an asymmetry: phase 1 preserves every
checkpoint/input-log consistency guarantee already built; phase 2 is explicitly
a "just end it" backstop, expected to only ever fire in the pathological case of
a graph broken by a permanent node failure, and is allowed to lose in-flight
state for whatever it kills.

## 5. Recovery from a node failure: partially done (node and Supervisor side), business connections open

- Policy: localized recovery (only the downed node is relaunched), not a global
  rollback. A global rollback is kept as a possible future fallback for the
  cases the Contract leaves out (see Future work, section 7).
- The supervisor detects it by the absence of a heartbeat (or, faster, a dead
  PID, section 4) and relaunches the node through `debasher_launch_process`,
  i.e. the built-in scheduler's own launch, the same operation as an initial
  launch (section 2's Startup sequence), with no special "recovery mode" logic.
  Done and verified with a real `debasher_exec` run (section 4).
- The relaunched node reconnects to the Supervisor: the Supervisor's readers
  reopen their FIFO after EOF while the node is not resolved (section 4,
  "Reading a node's channel across a crash").
- **Not done: a relaunched node does not reconnect to its business peers.** The
  earlier claim here ("the kernel resolves the reconnection with the blocked
  neighbor, with no additional mechanism") only held for restarting the *whole
  program*: section 2's and section 3's smoke tests relaunched with a new
  `debasher_exec` against the same outdir, which recreates every FIFO. For one
  node crashing while its neighbors keep running, a `FBPProcess` reader (single
  `open()` plus `for line in fifo`) dies at the first EOF and never reopens, and
  a writer whose reader died gets `BrokenPipeError` (its thread dies); the
  relaunched node then blocks forever in `open()` on that connection. So after a
  relaunch the node talks to the Supervisor again but is cut off from every
  peer, and the introduction's first goal is only met for a node whose sole
  connection is the Supervisor. Making `FBPProcess` readers/writers reconnect
  needs a signal that today only the Supervisor has (does the neighbor's silence
  mean "crashed, will return" or "finished on purpose"?); to be designed.

### Peer reconnection across a crash: design in progress (the most delicate open item)

Nothing of this is implemented. State of the discussion:

**Proposal: a process always sends a closing message before closing its FIFO.**
The FIFO is open for the whole life of a process (it opens it as it starts and
holds it until `_STOP`), so EOF on a reader means only two things: the writer
closed on purpose, or it died. A closing message sent in band tells them apart:
EOF after it means "finished, do not wait", EOF without it means "crashed,
reopen and wait for the relaunched writer". Same idea as FIN versus RST in TCP.
It is decentralized (works without a Supervisor, which is optional, and for a
manual relaunch), and it is the signal a `FBPProcess` peer lacks (it has no
`.finished` of the other node and does not even know its process name, only the
FIFO path).

**What the writer-dies direction needs:**
1. A fourth envelope type, `CLOSE` (empty payload), rather than an `INTERACT`
   command. The reader dispatches on `type` alone (section 1) and, besides
   ending its own loop, hands `CLOSE` to the brain thread in order, so that it
   is logged and the port can leave the barrier's pending set (section 3).
   Confirmed on 2026-09-20.
2. Writer: on a stop that means the node has finished for good, send `CLOSE`
   last (after whatever is already queued), then close; a halt sends none
   (section 3).
3. Reader: ends only on a stop request (after a `CLOSE` it keeps reading and
   drops what follows, see section 3). With ghost connections (transport
   decision below) it never sees EOF, so there is nothing to reopen. A truncated
   line left by a writer that died mid-write can no longer be delimited by EOF
   (today it kills the reader with a `JSONDecodeError`): handled by the resync
   line, see below.
4. Shutdown of a reader: nothing blocks in `open()` any more, and a reader
   blocked in `read()` is woken by writing a blank line to its own ghost write
   end (checked: 600 of 600 rounds, at most 0.2 ms). `Supervisor` no longer
   needs daemon reader threads.
5. A process exiting with an error (exception, non-zero exit) sends no `CLOSE`
   and is treated as a crash, consistent with the Supervisor design. A `CLOSE`
   followed by a later failure is harmless: the peers keep reading and drop what
   the relaunched node sends (section 3).

**What it does not cover (the reader-dies direction):**
- A writer whose reader died gets `BrokenPipeError` on its next write, and its
  thread dies. It should reopen (wait for the relaunched reader) and resend the
  message that failed.
- Data already in the FIFO buffer and not yet read is probably lost when the
  reader dies. The log then in place only covered what the brain thread had
  already received (the input log now records each message when it arrives).
  What exactly happens to unread FIFO data when the reader closes and another
  reopens **has not been tested** (do it with a race-provoking repro, per the
  project rule). If it is lost, the sender needs to retain messages, which opens
  the delivery-semantics question (at least once, and idempotence of
  `process_data`).
- The symmetric ambiguity on the writer side: a reader that closed on purpose
  versus one that died.

**Related consequence, done in step 4.4:** an input port closed with `CLOSE`
will never send a marker again, so a barrier round does not wait for it (section
3).

**Supervisor:** does not need `CLOSE`. Its channels keep using the node's
`.finished` file, since `CLOSE` does not prove the node succeeded, and a node
that closed and then failed must still be heard again when relaunched.

**Suggested plan:** first the writer-dies direction (`CLOSE`, reader reopening
[superseded by the transport decision below], dropping the truncated line),
checked with a real crash-and-relaunch between two `FBPProcess` nodes under
`debasher_exec`; then the reader-dies direction as its own design discussion,
after the experiment on unread FIFO data.

**Findings from experiments (2026-09-19).** Facts checked with real FIFOs and
real processes, not decisions; they are the basis for the proposal at the end of
this list.

- A reader cannot tell a clean close from a crash: the EOF is identical for a
  normal exit and for SIGKILL. An in-band signal (`CLOSE`) is needed, as
  proposed above.
- A truncated last line appears only for messages above `PIPE_BUF` (4096 bytes
  on Linux): 0 of 100 rounds at 4000 bytes, 53 of 100 at 5000, 98 of 100
  at 20000. The reader sees it as an unterminated fragment at EOF.
- A reader that closes and reopens its FIFO after EOF has a window between its
  `close()` and its `open()`: a writer relaunched inside that window gets
  `EPIPE` and dies (1 hang in 250 rounds, with the relaunch forced within
  microseconds). The EOF is also not a reliable event: with the writer replaced
  with no gap the reader missed 80% of the EOFs, and with a backlog in the pipe
  it never saw one (the new writer's data just follows on the same file
  descriptor). So a reader must be correct whether or not it sees the EOF.
- A reader that never closes its file descriptor
  (`os.open(O_RDONLY | O_NONBLOCK)`, `select` with a timeout, `os.read`, line
  framing done by hand, an unterminated fragment dropped on EOF and a retry a
  few milliseconds later) had no failure in 370 crash-and-relaunch rounds, no
  `EPIPE` in the relaunched writers, and honors a stop flag within its `select`
  timeout (50 ms) even if no writer ever connected. Linux behavior only. It also
  removes item 4 above (a dummy writer to unblock `open()` works, but
  `O_WRONLY | O_NONBLOCK` returns `ENXIO` when it runs before the reader reaches
  `open()`, so it would need a retry loop) and the `Supervisor.run()` hang
  listed in the Contract's conformance status.
- The reader-dies direction: when only the reader dies, the messages it had not
  read survive as long as the writer keeps its file descriptor open (the
  descriptor keeps the pipe and its buffer alive), and a writer that gets
  `EPIPE` recovers by retrying `os.write` on the same descriptor once a new
  reader attaches (13 retries, no loss, no duplicate). When reader and writer
  both die, the unread messages are destroyed with the pipe.
- What `CLOSE` drags with it, beyond the list above: it has to be durable on the
  reader side (otherwise a relaunched consumer blocks forever in `open()`
  waiting for a producer that had already finished), a closed port has to leave
  the barrier's pending set (today a finished producer already hangs every later
  round), the heartbeat must not count a reader that ended on `CLOSE` as dead,
  and the reader should hand `CLOSE` to the brain thread in order, after the
  `DATA` that preceded it.
- Replay re-emits the outputs the node had already sent, so a reconnected
  neighbor sees duplicates: see G5 in the Contract.

**Transport decided and implemented (2026-09-20): ghost connections.** Every
endpoint holds both ends of its FIFO, the real one and a ghost of the opposite
direction. A reader opens `O_RDONLY | O_NONBLOCK` (which returns at once) and
then `O_WRONLY` (a reader now exists); a writer does the same, its real end
being the `O_WRONLY` one. `O_RDWR` is not used: POSIX leaves it undefined for
FIFOs. Checked with real processes: no open ever blocks, whatever the start
order; writer crash and relaunch with the reader holding a ghost write end, 210
of 210 rounds without a hang or an `EPIPE`; reader crash and relaunch with the
writer holding a ghost read end, 40 of 40 rounds, the writer never dies and
nothing is lost inside the pipe (the only hole, at most 44 lines, is what the
killed reader had already consumed).

- The reader never sees EOF and ends only on a stop request (a `CLOSE` does not
  end it, see section 3). To stop it, `stop_threads()` writes a blank line to
  the reader's own ghost write end (checked: 600 of 600 rounds, at most 0.2 ms,
  also when the stop precedes the read).
- The writer never sees `EPIPE`. A dead peer means backpressure: the writer
  blocks once the pipe holds 64 KiB. A blocked writer cannot be woken, so
  `stop_threads()` joins writers with a bounded timeout.
- Removed from the code: `_should_reopen_after_eof` (the base one and the
  `Supervisor` override), `EOF_FINISHED_GRACE_SECS`, `_EOF_POLL_INTERVAL_SECS`
  and `_READER_THREADS_ARE_DAEMON`. `Supervisor` learns that a node finished
  only from its `.finished` file in the checker, as it already does, and the
  `Supervisor.run()` hang goes away by construction. Tests to rewrite: the six
  on the reopen hook,
  `test_real_reader_reopens_after_eof_and_receives_a_relaunched_writer`,
  `test_reader_thread_exits_on_fifo_eof`, and those that close a test-side end
  to finish a reader.
- Not covered: both endpoints of a channel dying together, before either has
  reopened the FIFO (the ghost ends die with their processes, so the unread
  messages are destroyed; a third process holding the FIFO would keep them,
  checked, not adopted, see the Contract's limits and Future work).
- **The FIFOs are opened first thing in the recovery (decided and done on
  2026-09-21).** A relaunched node used to open its FIFOs in `start_threads()`,
  after restoring its checkpoint and replaying its input log, so the time it
  spent recovering lay inside the window in which the crash of a neighbor could
  destroy what the neighbor had sent it. Measured with a real `debasher_exec`
  run of a source and a sink whose replay took 6 s (the sink killed after 60
  messages, the source sending 50 more and killed 2 s into the sink's replay):
  the sink received 0 of the 50 (three runs), and all 50 when the source was
  left alone. Now `run()` opens the FIFOs before anything else (`_open_fifos()`,
  which `start_threads()` still calls for the ports that are not open yet, so a
  node driven without `run()` is unchanged), and the same run delivers 50 of 50
  (three runs). Seven new tests in the words of the guarantee (what a writer
  sent to a relaunched reader, and what a relaunched writer had in its FIFO,
  survives the crash of the neighbor while the node restores its checkpoint,
  initializes and replays, and starting the threads does not open again what is
  already open), checked against eight mutants (no early open, opened after the
  restore, after `initialize_runtime`, after the replay, opened again by
  `start_threads()`, only the input FIFOs early, only the output FIFOs early,
  and `start_threads()` no longer opening what is not open; the last one is
  killed by a hang, since a writer thread then dies). What remains of the window
  is the time to notice the crash (`HEARTBEAT_CHECK_INTERVAL_SECS` when the
  process is gone) and to start the new process.
- Implemented in step 2 of the order in section 3, and checked with a real
  `debasher_exec` run of a numbered message source, a consumer that logs what it
  receives and a `Supervisor`, twice: `kill -9` of the writer node's process
  group and, later, of the reader node's. The `Supervisor` relaunched each one,
  the other node was never touched (and never stopped heartbeating), and across
  the reader's outage and relaunch the consumer logged 630 consecutive messages
  of the source's second incarnation, none missing and none duplicated: what was
  sent while it was down waited in the pipe.
- Price: with no EOF, a fragment left by a writer killed in the middle of a
  message larger than `PIPE_BUF` would merge with the next good message into one
  unparsable line and swallow it (checked: 23 of 50 stress rounds lost a good
  message). **Decided (2026-09-20): a resync line.** Every incarnation of a
  writer starts with one atomic write, a blank line followed by a `HELLO` line
  (a new envelope type, consumed by the reader like `CLOSE`). A reader that
  finds one unparsable line tolerates it if the next line is `HELLO`, and drops
  it; in any other case it is an error, so a corrupt line is never skipped
  silently. Checked with messages up to 30000 bytes and writers killed
  mid-write: 120 of 120 rounds correct, 50 of them with a real fragment dropped,
  no gap and no duplicate. There is no limit on message size. Only the framework
  writes to these channels: an external writer must send complete lines, and a
  fragment from one shows up as an error. `HELLO` also tells the reader that its
  peer (re)connected.

**Also decided (2026-09-20)**: (B) the `CLOSE` envelope, sent by the writer when
it has finished for good and handed by the reader to the brain thread in order,
so that it is logged (section 3); (C) a closed port leaves the barrier's pending
set, the reader of a closed port keeps reading and drops what follows (so the
heartbeat needs no special case), and the "peer finished" fact is durable
through the input log and the checkpoint's `closed_ports` (section 3), which
replaces the marker file proposed before. The writer side of the reader-dies
direction is moot (the writer never sees `EPIPE`); G5 and the messages already
read but not yet logged are settled by section 3. What remains is a real
crash-and-relaunch smoke test between two `FBPProcess` nodes under
`debasher_exec`, and the chaos test of the Contract.

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
- **A crash during a round** aborts it, and the mechanism is not designed. What
  exists: a node that comes back has no round open, and the next round of a
  newer epoch replaces a round that another node was left with open (section 2).
  A real crash during a round has not been tried.
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
  again.** After `_declare_down` a node stays in `_down` until a real heartbeat
  arrives, and `_check_node` skips nodes in `_down`. If the relaunch itself
  fails (a startup crash), nothing re-detects it, `_relaunch_attempts` never
  grows past 1, `MAX_RELAUNCH_ATTEMPTS` never trips and the Supervisor never
  resolves. Needs a grace period after a relaunch (no heartbeat within
  `HEARTBEAT_TIMEOUT_SECS` means declare it down again).
- **Relaunching while the old process is still alive.** The heartbeat-timeout
  path also fires for a live but stuck process (PID alive, no heartbeat).
  `on_node_down` then starts a second copy while the first still holds its
  FIFOs, and `_launch` removes the old `.id`, so the old process is no longer
  reachable by `debasher_stop` either. The old process group should be killed
  first.
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
  harbor for the cases the Contract leaves outside its guarantees, so that those
  cases need no heavy mechanism (a process holding every FIFO open, logging at
  the sender): detect the violation, stop, rewind every node to the last
  consistent cut, resume. Cases where it would be used: a guarantee that cannot
  be kept is detected (a hole in a channel's sequence numbers, a missing or
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
    input log is kept back to the `processed_upto` of the oldest retained
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
    survive with a third process holding one). The simplest holder is a single
    process for the whole program, the `Supervisor` or one of its own, but if it
    dies together with both endpoints the loss is back, and the `Supervisor` is
    not supervised. A series of holders spreads that risk: for example every
    node also holds an auxiliary read end of the channels of its neighbors, so
    that a channel loses its contents only if its two endpoints and all its
    auxiliary holders are gone within one recovery, which is far less likely
    when the crashes are independent (reasoned, not measured). Open questions:
    who holds which channel, how a holder learns the paths of FIFOs that are not
    its own (a node knows only its own options today), whether a relaunched
    holder reopens its auxiliary ends first thing, as it does with its own, and
    what becomes of the auxiliary ends of a node that has finished for good. Not
    designed.
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
