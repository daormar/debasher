"""A stand-in for readfish, to run and test webui_readfish with no sequencer.

It writes, on its standard output, the lines that readfish writes in its
log, at readfish's pace: one line per batch of reads, with its counters
growing, and the two lines of a change of phase. It is a plain program
that knows nothing of DeBasher: the node Acquire runs it by default, in
place of readfish, and reads its lines as it would read readfish's.

What it does is steered by its options and by files in its working
directory (the output directory of the process, when Acquire runs it),
which an operator or a test touches:

- a file `stall`, or --stall-after N batches, makes it stall: alive and
  silent, as the stream of readfish issue 412; a new run removes the
  file, as a new connection clears the stall;
- a file `scan`, or --scan-every-s, makes it go through a mux scan of
  --scan-secs seconds: the two lines of the phase and silence in between;
- a file `exit`, or --exit-after N batches, makes it end with --exit-code.
"""

import argparse
import os
import random
import sys
import time


def _ts():
    now = time.time()
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)) + f",{int(now * 1000) % 1000:03d}"


def say(logger, text):
    print(f"{_ts()} {logger} {text}", flush=True)


def phase(name):
    say("readfish._read_until_client", f"Protocol phase changed to {name}")
    if name != "PHASE_SEQUENCING":
        say("readfish.unblock-all", f"MinKNOW is reporting {name}, waiting for PHASE_SEQUENCING to begin.")


def take(path):
    """Whether the file `path` exists; it is removed once seen."""
    try:
        os.remove(path)
    except FileNotFoundError:
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--batch-interval-s", type=float, default=0.4, help="seconds between two batches (0.4)")
    parser.add_argument("--reads-per-batch", type=int, default=30, help="reads in a batch, on average (30)")
    parser.add_argument("--stall-after", type=int, default=0, help="stall after this many batches (0: never)")
    parser.add_argument("--scan-every-s", type=float, default=0, help="a mux scan every this many seconds (0: never)")
    parser.add_argument("--scan-secs", type=float, default=240, help="length of a mux scan (240, as a real one)")
    parser.add_argument("--exit-after", type=int, default=0, help="end after this many batches (0: never)")
    parser.add_argument("--exit-code", type=int, default=1, help="the exit code of --exit-after or the file exit (1)")
    parser.add_argument("--seed", type=int, default=1, help="seed of the batch sizes")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    # A new run is a new connection, which clears a passing stall
    take("stall")
    say("readfish", f"{' '.join(sys.argv)}")
    say("readfish", "Version=fake_readfish")
    say("readfish.unblock-all", "Starting main loop")
    phase("PHASE_SEQUENCING")

    batches = 0
    seq = unb = 0
    stalled = False
    last_scan = time.monotonic()
    total_time = 0.0
    while True:
        time.sleep(args.batch_interval_s)
        if take("exit") or (args.exit_after and batches >= args.exit_after):
            say("readfish.unblock-all", "Keyboard interrupt received, stopping readfish.")
            sys.exit(args.exit_code)
        if take("scan") or (args.scan_every_s and time.monotonic() - last_scan >= args.scan_every_s):
            phase("PHASE_MUX_SCAN")
            end = time.monotonic() + args.scan_secs
            # In steps, so that an exit asked for during the scan is seen
            while time.monotonic() < end:
                if take("exit"):
                    sys.exit(args.exit_code)
                time.sleep(min(args.batch_interval_s, max(end - time.monotonic(), 0)))
            phase("PHASE_SEQUENCING")
            last_scan = time.monotonic()
            continue
        if stalled or os.path.exists("stall") or (args.stall_after and batches >= args.stall_after):
            # Alive and silent: the stream gives nothing and does not close
            stalled = True
            continue
        batches += 1
        reads = max(1, int(rng.gauss(args.reads_per_batch, args.reads_per_batch / 4)))
        batch_time = 0.002 + rng.random() * 0.004
        total_time += batch_time
        # unblock-all: every read is unblocked, but for the first of each
        # channel, which is sequenced
        new_seq = 1 if seq < 512 and rng.random() < 0.3 else 0
        seq += new_seq
        unb += reads - new_seq
        say(
            "readfish.unblock-all",
            f"{reads:04d}R/{batch_time:.4f}s; Avg: {(seq + unb) // batches:04d}R/{total_time / batches:.4f}s; "
            f"Seq:{seq:,}; Unb:{unb:,}; Pro:0; Slow batches (>1.00s): 0/{batches}",
        )


if __name__ == "__main__":
    main()
