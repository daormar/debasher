"""
Node tests of webui_running_sum: the business logic of its node
Accumulate, built without the engine with the node harness, run with
debasher_test.
"""

from debasher_runtime_testing import load_node


def accumulate():
    return load_node("Accumulate", inputs=["numbers"], outputs=["outsum"])


def test_sends_the_running_sum_of_the_numbers():
    node = accumulate()
    node.feed("numbers", 3)
    node.feed("numbers", 4)
    assert node.sent("outsum") == [3, 7]


def test_a_restarted_node_goes_on_from_its_sum():
    node = accumulate()
    node.feed("numbers", 3)
    node = node.restart()
    node.feed("numbers", 4)
    assert node.sent("outsum") == [7]
