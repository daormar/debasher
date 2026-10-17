# The skip example of the engine, described with the Python SDK: a
# process sums two numbers of the command line into a value descriptor,
# and another reads the sum and writes it plus one, unless the sum is
# odd, which a skip rule in Python decides (value_reader_skip.py).

from debasher import Process, Program, in_outdir

SPECS = dict(cpus=1, mem=32, time="00:01:00")

value_writer = Process("value_writer", code="value_writer.sh",
                       description="Takes two numbers and produces their sum as output.")
value_writer.cmdline_opt("-num-a", "int", "First number to be summed")
value_writer.cmdline_opt("-num-b", "int", "Second number to be summed")
value_writer.value_desc_output("-outv", "int", "output value descriptor")

value_reader = Process("value_reader", code="value_reader.sh", skip="value_reader_skip.py",
                       description="Reads the sum, increases it by one and writes it into a file; "
                       "skipped when the sum is odd.")
value_reader.input("-val-desc", "int", "value descriptor", source=value_writer["-outv"])
value_reader.output("-outf", "file", "output file", in_outdir("value_reader.out"))

prg = Program(
    "sdk_skip_py",
    description="Example described with the SDK: a process sums two numbers into a value "
    "descriptor, and another writes the sum plus one, skipped by a rule in Python when the "
    "sum is odd.",
    program_options={"-num-a": "1", "-num-b": "3"},
)
prg.add(value_writer, **SPECS)
prg.add(value_reader, **SPECS)
