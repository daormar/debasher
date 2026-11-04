# The skip example of the engine, described with the Python SDK: a
# process sums two numbers of the command line into a value descriptor,
# and another reads the sum and writes it plus one, unless the sum is
# odd, which a skip rule in Python decides (value_reader_skip.py).

from debasher import Process, Program, connect, in_outdir, opt, value_desc

SPECS = dict(cpus=1, mem=32, time="00:01:00")

value_writer = Process("value_writer", code="value_writer.sh",
                       description="Takes two numbers and produces their sum as output.",
                       options=[opt("-num-a", "int", "First number to be summed"),
                                opt("-num-b", "int", "Second number to be summed"),
                                opt("-outv", "int", "output value descriptor")])
value_writer.interface(cmdline={"-num-a": "mandatory", "-num-b": "mandatory"})
value_writer.task_options(values={"-outv": value_desc()})

value_reader = Process("value_reader", code="value_reader.sh", skip="value_reader_skip.py",
                       description="Reads the sum, increases it by one and writes it into a file; "
                       "skipped when the sum is odd.",
                       options=[opt("-val-desc", "int", "value descriptor"),
                                opt("-outf", "file", "output file")])
value_reader.task_options(values={"-val-desc": connect(value_writer["-outv"]),
                                  "-outf": in_outdir("value_reader.out")})

prg = Program(
    "sdk_skip_py",
    description="Example described with the SDK: a process sums two numbers into a value "
    "descriptor, and another writes the sum plus one, skipped by a rule in Python when the "
    "sum is odd.",
    program_options={"-num-a": "1", "-num-b": "3"},
)
prg.add(value_writer, **SPECS)
prg.add(value_reader, **SPECS)
