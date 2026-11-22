from debasher_runtime_lib import DirectoryWatcher


class Watch(DirectoryWatcher):
    # Every file of the directory counts (PATTERN "*"): the directory is the
    # one where the sequencer writes its read files, such as fast5_pass, and
    # holds nothing else. A file whose name starts with a dot never counts.
    pass


Watch().run()
