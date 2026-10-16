from debasher import Process, Program

hello = Process("hello_world", code="hello_world.py", description="Prints a greeting.")
hello.cmdline_opt("-s", "string", "string to print ('Hello World!' by default)", mandatory=False)

prg = Program("webui_hello_world_py")
prg.add(hello, cpus=1, mem=256, time="01:00:00")
