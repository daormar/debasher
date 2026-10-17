# The task is skipped when the value it reads is odd: task.value reads
# the value that the value descriptor of value_writer holds
def skip(task):
    return int(task.value("-val-desc")) % 2 == 1
