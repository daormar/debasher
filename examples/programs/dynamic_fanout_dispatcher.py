"""
dynamic_fanout_dispatcher.py

Reads block file paths from an input FIFO (inf) and distributes each
path to one of w output FIFOs based on the index i extracted from
"blk{i}.txt", using i % w.

Each output FIFO is served by its own WorkerFeeder thread with plain
blocking I/O. Opening a FIFO for writing blocks until a reader connects;
running each output FIFO in its own thread means that wait never blocks
the others or the main thread reading the input.

Note: the actual workers that consume these FIFOs are separate external
processes (e.g. bash scripts), this program does not run them. Each
WorkerFeeder is just the thread on our side that owns the connection to
one worker's input FIFO and writes block paths to it.

Output FIFO paths are passed individually as -outf0, -outf1, ...,
-outf{w-1}. Logging goes to stderr; verbosity is controlled with
--log-level (use CRITICAL to effectively silence normal output while
still surfacing critical failures).
"""

import argparse
import logging
import os
import queue
import re
import sys
import threading

BLOCK_RE = re.compile(r"blk(\d+)\.txt$")

log = logging.getLogger("distribute_blocks")


def setup_logging(level_name: str):
    logging.basicConfig(
        level=getattr(logging, level_name),
        format="%(asctime)s %(levelname)-8s [%(threadName)s] %(message)s",
    )


def extract_workers_count():
    """
    Minimal manual scan of sys.argv, just to find -w/--workers.
    We need this value before we can tell argparse to expect
    -outf0 .. -outf{w-1}, since argparse can't declare an unknown
    number of options in a single pass.
    """
    args = sys.argv[1:]
    for i, flag in enumerate(args):
        if flag in ("-w", "--workers"):
            if i + 1 >= len(args):
                print(f"Error: {flag} requires a value", file=sys.stderr)
                sys.exit(1)
            try:
                return int(args[i + 1])
            except ValueError:
                print(f"Error: {flag} must be an integer", file=sys.stderr)
                sys.exit(1)

    print("Error: -w/--workers is required", file=sys.stderr)
    sys.exit(1)


def parse_args():
    w = extract_workers_count()
    if w <= 0:
        print("Error: -w/--workers must be a positive integer", file=sys.stderr)
        sys.exit(1)

    parser = argparse.ArgumentParser(
        description="Distribute block file paths from an input FIFO to w output FIFOs."
    )
    parser.add_argument("-w", "--workers", type=int, required=True,
                         help="Number of output FIFOs / workers.")
    parser.add_argument("-inf", required=True,
                         help="Path to the input FIFO to read block paths from.")
    parser.add_argument("--log-level", default="INFO",
                         choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                         help="Logging verbosity (default: INFO). Use CRITICAL to "
                              "effectively silence normal output.")

    for i in range(w):
        parser.add_argument(f"-outf{i}", required=True,
                             help=f"Path to output FIFO for worker {i}.")

    args = parser.parse_args()

    # Collect outf0..outf{w-1} into an ordered list for the rest of the program
    outf_paths = [getattr(args, f"outf{i}") for i in range(w)]

    return args, outf_paths


def extract_index(path):
    """Extract the integer i from a path ending in blk{i}.txt."""
    base = os.path.basename(path)
    m = BLOCK_RE.search(base)
    return int(m.group(1)) if m else None


class WorkerFeeder(threading.Thread):
    """
    Feeds one external worker process with block paths, through its
    output FIFO.

    This is NOT the worker itself: the actual worker is a separate
    process (e.g. a bash script) reading from this FIFO and doing the
    real processing. This thread is only the channel on our side — it
    owns the connection to that FIFO and writes to it.

    Runs in its own thread because opening a FIFO for writing blocks
    until a reader connects; keeping that wait in its own thread means
    it never stalls the rest of the program.
    """

    def __init__(self, path):
        super().__init__(daemon=True, name=f"feeder-{os.path.basename(path)}")
        self.path = path
        self.q = queue.Queue()
        self.lines_written = 0

    def queue_line(self, line: str):
        self.q.put(line)

    def stop(self):
        self.q.put(None)  # sentinel: tells the thread to finish and exit

    def run(self):
        log.debug("Waiting for a reader on %s", self.path)
        # Blocking open: this line waits here until the worker process
        # opens the other end for reading. Since we're in our own
        # thread, this doesn't block the rest of the program.
        with open(self.path, "w") as f:
            log.info("Connected to %s", self.path)
            while True:
                line = self.q.get()
                if line is None:  # sentinel received: no more lines coming
                    break
                f.write(line + "\n")
                f.flush()
                self.lines_written += 1
        log.info("Closed %s (%d lines written)", self.path, self.lines_written)


def read_input_lines(inf_path):
    """Generator that yields lines from the input FIFO as they arrive.
    Blocking reads are fine here: this runs in the main thread, and the
    feeder threads run independently."""
    with open(inf_path, "r") as f:
        for line in f:
            yield line.rstrip("\n")


def main():
    args, outf_paths = parse_args()
    setup_logging(args.log_level)
    w = args.workers

    log.info("Starting dispatcher: w=%d inf=%s outf=%s", w, args.inf, outf_paths)

    feeders = [WorkerFeeder(path) for path in outf_paths]
    for feeder in feeders:
        feeder.start()

    lines_read = 0
    lines_skipped = 0

    try:
        for line in read_input_lines(args.inf):
            line = line.strip()
            if not line:
                continue
            lines_read += 1
            idx = extract_index(line)
            if idx is None:
                log.warning("Could not parse index from '%s', skipping", line)
                lines_skipped += 1
                continue
            log.debug("Dispatching %s -> feeder %s", line, os.path.basename(feeders[idx % w].path))
            feeders[idx % w].queue_line(line)

        log.info("Input FIFO closed, no more blocks incoming "
                  "(%d lines read, %d skipped)", lines_read, lines_skipped)
    finally:
        log.info("Signalling feeders to finish...")
        for feeder in feeders:
            feeder.stop()
        for feeder in feeders:
            feeder.join()

    log.info("Dispatcher finished")


if __name__ == "__main__":
    main()
