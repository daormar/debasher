from debasher import Node, Program, Supervisor

acc = Node("Accumulate", code="accumulate.py", initiator=True,
           description="Keeps the running sum of the numbers it receives, and sends each new sum out.")
acc.fifo_input("-numbers", "string", "numbers written from outside the program, one per message",
               "numbers", external=True)
acc.fifo_output("-outsum", "string", "the running sum after each number, read outside the program", "sum")

sup = Supervisor("Sup", description="Watches Accumulate and relaunches it if it goes down.")

prg = Program(
    "webui_running_sum",
    resident=True,
    description="Example built with the web UI: a resident program whose node keeps the running sum "
    "of the numbers written into its external input, and writes each new sum out.",
)
prg.add(acc, cpus=1, mem=256, time="01:00:00", position=(120, 260))
prg.add(sup, cpus=1, mem=256, time="01:00:00", position=(120, 60))
