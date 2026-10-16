# The dynamic fanout example of the web UI, described with the Python
# SDK: a generated file is counted and cut into fragments, which a
# dispatcher streams through FIFOs to a pool of workers, an array process
# with one task per worker, and a last process merges their counts. Each
# process has its code in a file beside this one; the worker is an array,
# whose tasks a Bash file shapes (worker_tasks.sh), and the dispatcher is
# a script that the module runs as it is.

from debasher import Array, Process, Program, in_outdir

SPECS = dict(cpus=1, mem=32, time="00:01:00")

count = Process("count", code="count.sh",
                description="Counts characters of an input file in a conventional way. "
                "This process is added for debugging purposes.")
count.input("-inf", "file", "input file", source=("generate", "-outf"))
count.output("-outf", "file", "output file", in_outdir("counts.txt"))

generate = Process("generate", code="generate.sh",
                   description="Generates a text file of a given size and random content.")
generate.output("-outf", "file", "output file", in_outdir("file.txt"))
generate.cmdline_opt("-l", "int", "Length of file in lines")
generate.cmdline_opt("-c", "int", "Length of each line in characters")

fragment = Process("fragment", code="fragment.sh",
                   description="Fragments an input file into a given number of equally sized "
                   "blocks, inverting the file lines.")
fragment.output("-outd", "dir", "name of output directory", in_outdir())
fragment.fifo_output("-outf", "file", "output fifo", "fragment_fifo")
fragment.input("-inf", "file", "input file", source=generate["-outf"])
fragment.cmdline_opt("-b", "int", "Number of blocks")

aggregate = Process("aggregate", code="aggregate.sh", description="Aggregates worker results.")
aggregate.output("-outf", "file", "output file", in_outdir("result.txt"))
workers = aggregate.cmdline_opt("-w", "int", "Number of workers.")
aggregate.input("-ind-ith", "dir", "i'th input directory", source=("worker", "-outd"),
                count_source=workers)

dispatch = Process("dispatch", script="./dynamic_fanout_dispatcher.py",
                   description="Dispatches file blocks to workers.")
dispatch.fifo_output("-outf-ith", "file", "i'th output fifo", "dispatch_fifo_${i}", count_source="-w")
dispatch.cmdline_opt("-w", "int", "Number of workers.")
dispatch.input("-inf", "file", "input fifo", source=fragment["-outf"])
dispatch.cmdline_opt("--log-level", "string",
                     "Logging verbosity. Choices: DEBUG, INFO, WARNING, ERROR, CRITICAL (default: INFO).",
                     mandatory=False)

worker = Array("worker", code="worker.sh", tasks="worker_tasks.sh",
               description="Executes an array of w tasks. Each task takes a list of text files "
               "and generates another file for each one.")
worker.outdir_opt("-outd", "directory of the task, below the output directory of the process",
                  subpath="${task_idx}")
worker.input("-inf", "file", "input fifo", source=dispatch["-outf-ith"])
worker.cmdline_opt("-w", "int", "Number of workers.", shaping=True)

prg = Program(
    "sdk_dynamic_fanout_fifos",
    description="Example described with the SDK: a generated file is counted and cut into "
    "fragments, which a dispatcher streams through FIFOs to a pool of workers, and a last "
    "process merges their counts.",
    program_options={"-l": "200", "-c": "20", "-b": "20", "-w": "4"},
)
prg.add(count, **SPECS)
prg.add(generate, **SPECS)
prg.add(fragment, **SPECS, processdeps="afterok:count")
prg.add(aggregate, **SPECS)
prg.add(dispatch, **SPECS)
prg.add(worker, **SPECS)
