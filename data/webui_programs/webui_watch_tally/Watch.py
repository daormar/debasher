from debasher_runtime_lib import DirectoryWatcher


class Watch(DirectoryWatcher):
    # Only text files count; a file whose name starts with a dot never does.
    PATTERN = "*.txt"


Watch().run()
