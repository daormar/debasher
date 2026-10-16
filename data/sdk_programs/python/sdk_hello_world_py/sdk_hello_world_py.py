# The hello world of the quickstart, described with the Python SDK: one
# process, written in Python, that prints a greeting. Built with
#
#     debasher_build sdk_hello_world_py.py
#
# which leaves .debasher/program.json and sdk_hello_world_py.sh beside
# this file, and run with
#
#     debasher_exec --pfile sdk_hello_world_py.sh --outdir out --wait

from debasher import Process, Program

hello = Process("hello_world", code="hello_world.py", description="Prints a greeting.")
hello.cmdline_opt("-s", "string", "string to print ('Hello World!' by default)", mandatory=False)

prg = Program("sdk_hello_world_py")
prg.add(hello, cpus=1, mem=256, time="01:00:00")
