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
    "webui_dynamic_fanout_fifos",
    description="Example built with the web UI: a generated file is counted and cut into "
    "fragments, which a dispatcher streams through FIFOs to a pool of workers, and a last "
    "process merges their counts.",
    program_options={"-l": "200", "-c": "20", "-b": "20", "-w": "4"},
)
prg.add(count, **SPECS, position=(60, 220))
prg.add(generate, **SPECS, position=(260, 40))
prg.add(fragment, **SPECS, processdeps="afterok:count", position=(360, 220))
prg.add(aggregate, **SPECS, position=(360, 760))
prg.add(dispatch, **SPECS, position=(360, 400))
prg.add(worker, **SPECS, position=(360, 580))
