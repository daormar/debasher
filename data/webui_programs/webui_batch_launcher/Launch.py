from debasher_runtime_lib import ProgramLauncher


class Launch(ProgramLauncher):
    # The general program to run, next to this program's home directory.
    PFILE = "../webui_batch_greet/webui_batch_greet.sh"


Launch().run()
