# The running sum of the web UI, described with the Python SDK: a resident
# program whose node, given as the Python file accumulate.py with its
# class, keeps the running sum of the numbers written into its external
# input and writes each new sum out, and a Supervisor that relaunches it
# if it goes down.

from debasher import Node, Program, Supervisor, fifo, opt

acc = Node("Accumulate", code="accumulate.py",
           description="Keeps the running sum of the numbers it receives, and sends each new sum out.",
           options=[opt("-numbers", "string", "numbers written from outside the program, one per message"),
                    opt("-outsum", "string", "the running sum after each number, read outside the program")])
acc.interface(external={"-numbers": "numbers"})
acc.task_options(values={"-outsum": fifo("sum")})

sup = Supervisor("Sup", description="Watches Accumulate and relaunches it if it goes down.")

prg = Program(
    "sdk_running_sum",
    resident=True,
    description="Example described with the SDK: a resident program whose node keeps the running "
    "sum of the numbers written into its external input, and writes each new sum out.",
)
prg.add(acc, cpus=1, mem=256, time="01:00:00", initiator=True)
prg.add(sup, cpus=1, mem=256, time="01:00:00")
