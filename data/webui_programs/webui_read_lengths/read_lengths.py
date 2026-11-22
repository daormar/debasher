"""Summarizes the lengths of the reads of one file of a sequencing run.

The file is a POD5 (read through the pod5 package) or a FAST5 (through
h5py), whose signal lengths are divided by -samples-per-base, or a text
file with one read length per line, as the tests and make installcheck
write. The summary, a JSON object with the count, the median, the N50 and
the fraction of reads shorter than -short-bases, goes to -outsummary. With
adaptive sampling at work most reads are short, so that fraction says
whether readfish was deciding when the file was written.
"""

import argparse
import json
import os
import statistics
import sys


def lengths_of(path, samples_per_base):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pod5":
        import pod5

        with pod5.Reader(path) as reader:
            return "pod5", [read.num_samples / samples_per_base for read in reader.reads()]
    if ext == ".fast5":
        import h5py

        with h5py.File(path, "r") as f:
            return "fast5", [
                len(f[name]["Raw"]["Signal"]) / samples_per_base for name in f if name.startswith("read_")
            ]
    with open(path) as f:
        lengths = []
        for line in f:
            try:
                lengths.append(float(line.split()[0]))
            except (ValueError, IndexError):
                continue
    return "text", lengths


def n50_of(lengths):
    total = sum(lengths)
    acc = 0.0
    for length in sorted(lengths, reverse=True):
        acc += length
        if acc >= total / 2:
            return length
    return 0


def summarize(path, samples_per_base, short_bases):
    fmt, lengths = lengths_of(path, samples_per_base)
    count = len(lengths)
    return {
        "file": path,
        "format": fmt,
        "count": count,
        "total_bases": round(sum(lengths)),
        "median": round(statistics.median(lengths)) if count else None,
        "n50": round(n50_of(lengths)) if count else None,
        "short_fraction": round(sum(1 for x in lengths if x < short_bases) / count, 3) if count else None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-infile", required=True, help="the file of reads")
    parser.add_argument("-outsummary", required=True, help="where the JSON summary goes")
    parser.add_argument("-samples-per-base", type=float, default=10.0, help="signal samples per base (10: 4 kHz at 400 b/s)")
    parser.add_argument("-short-bases", type=float, default=1000.0, help="a read under this many bases is short (1000)")
    args = parser.parse_args()
    summary = summarize(args.infile, args.samples_per_base, args.short_bases)
    with open(args.outsummary, "w") as f:
        json.dump(summary, f)
        f.write("\n")
    print(json.dumps(summary))


if __name__ == "__main__":
    sys.exit(main())
