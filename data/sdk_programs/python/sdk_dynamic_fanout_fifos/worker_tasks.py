# One task per worker: the elements of the array are 0, 1, ..., w-1
def tasks(run):
    return range(int(run.value("-w")))
