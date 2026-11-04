# The dynamic fanout example of the web UI, described with the Python
# SDK: a generated file is counted and cut into fragments, which a
# dispatcher streams through FIFOs to a pool of workers, an array process
# with one task per worker, and a last process merges their counts. Each
# process has its code in a file beside this one; the worker is an array,
# whose tasks a Python function shapes (worker_tasks.py), and the
# dispatcher is a script that the module runs as it is.

from debasher import Process, Program, connect, fifo, in_outdir, opt, outdir

SPECS = dict(cpus=1, mem=32, time="00:01:00")

count = Process("count", code="count.sh",
                description="Counts characters of an input file in a conventional way. "
                "This process is added for debugging purposes.",
                options=[opt("-inf", "file", "input file"),
                         opt("-outf", "file", "output file")])
count.task_options(values={"-inf": connect(("generate", "-outf")),
                           "-outf": in_outdir("counts.txt")})

generate = Process("generate", code="generate.sh",
                   description="Generates a text file of a given size and random content.",
                   options=[opt("-outf", "file", "output file"),
                            opt("-l", "int", "Length of file in lines"),
                            opt("-c", "int", "Length of each line in characters")])
generate.interface(cmdline={"-l": "mandatory", "-c": "mandatory"})
generate.task_options(values={"-outf": in_outdir("file.txt")})

fragment = Process("fragment", code="fragment.sh",
                   description="Fragments an input file into a given number of equally sized "
                   "blocks, inverting the file lines.",
                   options=[opt("-outd", "dir", "name of output directory"),
                            opt("-outf", "file", "output fifo"),
                            opt("-inf", "file", "input file"),
                            opt("-b", "int", "Number of blocks")])
fragment.interface(cmdline={"-b": "mandatory"})
fragment.task_options(values={"-outd": in_outdir(),
                              "-outf": fifo("fragment_fifo"),
                              "-inf": connect(generate["-outf"])})

aggregate = Process("aggregate", code="aggregate.sh", description="Aggregates worker results.",
                    options=[opt("-outf", "file", "output file"),
                             opt("-w", "int", "Number of workers."),
                             opt("-ind-ith", "dir", "i'th input directory")])
aggregate.interface(cmdline={"-w": "mandatory"})
aggregate.task_options(values={"-outf": in_outdir("result.txt"),
                               "-ind-ith": connect(("worker", "-outd"))},
                       count={"-ind-ith": "-w"})

dispatch = Process("dispatch", script="./dynamic_fanout_dispatcher.py",
                   description="Dispatches file blocks to workers.",
                   options=[opt("-outf-ith", "file", "i'th output fifo"),
                            opt("-w", "int", "Number of workers."),
                            opt("-inf", "file", "input fifo"),
                            opt("--log-level", "string",
                                "Logging verbosity. Choices: DEBUG, INFO, WARNING, ERROR, "
                                "CRITICAL (default: INFO).")])
dispatch.interface(cmdline={"-w": "mandatory", "--log-level": "optional"})
dispatch.task_options(values={"-outf-ith": fifo("dispatch_fifo_${i}"),
                              "-inf": connect(fragment["-outf"])},
                      count={"-outf-ith": "-w"})

worker = Process("worker", code="worker.sh",
                 description="Executes an array of w tasks. Each task takes a list of text files "
                 "and generates another file for each one.",
                 options=[opt("-outd", "dir", "directory of the task, below the output directory "
                              "of the process"),
                          opt("-inf", "file", "input fifo")])
worker.interface(shaping={"-w": ("int", "Number of workers.")})
worker.task_options(array="worker_tasks.py",
                    values={"-outd": outdir(subpath="${task_idx}"),
                            "-inf": connect(dispatch["-outf-ith"])})

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
