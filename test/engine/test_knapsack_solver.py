"""Tests for engine/debasher_solve_knapsack_greedy.py, the solver with which
the built-in scheduler chooses, in a round with limited resources, the tasks
that it launches."""

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "debasher_solve_knapsack_greedy",
    Path(__file__).resolve().parents[2] / "engine" / "debasher_solve_knapsack_greedy.py",
)
solver = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(solver)


def _solve(tmp_path, spec, deps, capacities):
    """The items that the solver packs, given the lines of the item file
    (name, value, cpus, memory), the lines of the predecessor file and the
    capacities, as the scheduler writes and passes them."""
    spec_file = tmp_path / "spec.txt"
    spec_file.write_text("".join(f"{line}\n" for line in spec))
    deps_file = tmp_path / "deps.txt"
    deps_file.write_text("".join(f"{line}\n" for line in deps))
    capacity_list = solver.get_capacities(capacities)
    items, weights, values = solver.extract_spec_info(str(spec_file), len(capacity_list))
    preds_by_name = solver.extract_deps_info(str(deps_file), items)
    _, packed, packed_weights = solver.solve(items, weights, values, capacity_list, preds_by_name)
    for used, capacity in zip(packed_weights, capacity_list):
        assert used <= capacity
    return {items[i] for i in packed}


def test_a_process_of_a_single_task_comes_before_a_task_of_an_array_of_the_same_size(tmp_path):
    # The value of an array is divided among its tasks (0.25 each for four)
    spec = ["0_0 0.25 1 32", "0_1 0.25 1 32", "0_2 0.25 1 32", "0_3 0.25 1 32", "1 1 1 32"]
    assert _solve(tmp_path, spec, [], "1,1024") == {"1"}
    packed = _solve(tmp_path, spec, [], "3,1024")
    assert "1" in packed and len(packed) == 3


def test_the_two_ends_of_a_fifo_are_chosen_together_or_not_at_all(tmp_path):
    spec = ["0 1 1 32", "1 1 1 32", "2 1 1 32"]
    # 0 and 1 are the two ends of a FIFO, given in both senses
    deps = ["0 1", "1 0"]
    assert _solve(tmp_path, spec, deps, "1,1024") == {"2"}
    assert _solve(tmp_path, spec, deps, "2,1024") in ({"0", "1"}, {"2"})
    assert _solve(tmp_path, spec, deps, "3,1024") == {"0", "1", "2"}


def test_no_resource_is_exceeded(tmp_path):
    # Memory, not cpus, is what limits here
    spec = ["0 1 1 600", "1 1 1 600", "2 1 1 600"]
    assert len(_solve(tmp_path, spec, [], "8,1300")) == 2
