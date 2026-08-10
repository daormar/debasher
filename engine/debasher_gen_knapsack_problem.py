"""
generate_knapsack_problem.py

Generates random test problems for debasher_solve_knapsack_greedy.py:
a spec file (process_id value weight1 ... weightN), an optional deps
file (successor_id predecessor_id), and a suggested list of
capacities printed to stdout so you can copy-paste a ready-to-run
command.
"""

import argparse
import random

##################################################
def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-n", "--num-processes", type=int, default=20,
                         help="Number of processes to generate (default: 20)")
    parser.add_argument("-w", "--num-weights", type=int, default=2,
                         help="Number of weight dimensions, e.g. cpus/mem (default: 2)")
    parser.add_argument("--value-range", type=str, default="1,50",
                         help="min,max for process values (default: 1,50)")
    parser.add_argument("--weight-range", type=str, default="1,10",
                         help="min,max for each weight dimension (default: 1,10)")
    parser.add_argument("--capacity-ratio", type=float, default=0.4,
                         help="Capacity per dimension = ratio * sum of that "
                              "dimension's weights (default: 0.4)")
    parser.add_argument("--dep-prob", type=float, default=0.3,
                         help="Probability that a process depends on an "
                              "earlier one (default: 0.3)")
    parser.add_argument("--together-prob", type=float, default=0.0,
                         help="Probability of adding a 'must go together' "
                              "pair (mutual edge) between two random "
                              "processes (default: 0.0, disabled)")
    parser.add_argument("--floats", action="store_true",
                         help="Generate float values/weights/capacities "
                              "instead of integers")
    parser.add_argument("--seed", type=int, default=None,
                         help="Random seed for reproducibility")
    parser.add_argument("--spec-out", type=str, default="spec.txt",
                         help="Output path for the spec file (default: spec.txt)")
    parser.add_argument("--deps-out", type=str, default="deps.txt",
                         help="Output path for the deps file (default: deps.txt)")
    return parser.parse_args()

##################################################
def random_number(rng, low, high, as_float):
    if as_float:
        return round(rng.uniform(low, high), 2)
    return rng.randint(int(low), int(high))

##################################################
def generate_processes(args, rng):
    value_min, value_max = (float(x) for x in args.value_range.split(","))
    weight_min, weight_max = (float(x) for x in args.weight_range.split(","))

    names = ["p%d" % i for i in range(args.num_processes)]
    values = []
    weights = [[] for _ in range(args.num_weights)]

    for _ in names:
        values.append(random_number(rng, value_min, value_max, args.floats))
        for w in range(args.num_weights):
            weights[w].append(random_number(rng, weight_min, weight_max, args.floats))

    return names, values, weights

##################################################
def generate_deps(args, rng, names):
    # Chain-friendly random DAG: process i may depend on an earlier
    # process, guaranteeing no accidental cycles from this part.
    edges = []
    for i in range(1, len(names)):
        if rng.random() < args.dep_prob:
            predecessor = names[rng.randint(0, i - 1)]
            edges.append((names[i], predecessor))

    # Optionally add a few "must go together" pairs (mutual edges).
    if args.together_prob > 0:
        for i in range(len(names)):
            if rng.random() < args.together_prob:
                j = rng.randint(0, len(names) - 1)
                if j != i:
                    edges.append((names[i], names[j]))
                    edges.append((names[j], names[i]))

    return edges

##################################################
def write_spec_file(path, names, values, weights, as_float):
    fmt = "%.2f" if as_float else "%d"
    with open(path, "w") as f:
        for i, name in enumerate(names):
            fields = [name, fmt % values[i]]
            for w in range(len(weights)):
                fields.append(fmt % weights[w][i])
            f.write(" ".join(fields) + "\n")

##################################################
def write_deps_file(path, edges):
    with open(path, "w") as f:
        for successor, predecessor in edges:
            f.write("%s %s\n" % (successor, predecessor))

##################################################
def compute_capacities(weights, ratio, as_float):
    fmt = "%.2f" if as_float else "%d"
    capacities = []
    for w in weights:
        total = sum(w)
        cap = total * ratio
        capacities.append(fmt % cap if as_float else fmt % int(round(cap)))
    return capacities

##################################################
def main():
    args = parse_args()
    rng = random.Random(args.seed)

    names, values, weights = generate_processes(args, rng)
    edges = generate_deps(args, rng, names)

    write_spec_file(args.spec_out, names, values, weights, args.floats)
    if edges:
        write_deps_file(args.deps_out, edges)

    capacities = compute_capacities(weights, args.capacity_ratio, args.floats)

    print("Generated %d processes with %d weight dimension(s)." %
          (args.num_processes, args.num_weights))
    print("Spec file: %s" % args.spec_out)
    if edges:
        print("Deps file: %s (%d edges)" % (args.deps_out, len(edges)))
    else:
        print("Deps file: not generated (no edges produced)")
    print("")
    print("Suggested command:")
    cmd = "python3 debasher_solve_knapsack_greedy.py -s %s -c %s" % (
        args.spec_out, ",".join(capacities))
    if edges:
        cmd += " -d %s" % args.deps_out
    print(cmd)


if __name__ == "__main__":
    main()
