"""
DeBasher package
Copyright 2019-2024 Daniel Ortiz-Mart\'inez

This library is free software; you can redistribute it and/or
modify it under the terms of the GNU Lesser General Public License
as published by the Free Software Foundation; either version 3
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Lesser General Public License for more details.

You should have received a copy of the GNU Lesser General Public License
along with this program; If not, see <http://www.gnu.org/licenses/>.

---
Uses a greedy heuristic approach to solve the knapsack problem that also
respects precedence constraints derived from FIFO connections between
processes (a successor process can only be selected if all of its
predecessor processes are selected too).

Spec file format (one line per process, unchanged from the original
GA-based script). The number of weight columns is arbitrary and is
inferred from the number of capacities given via -c/--capacities:

    process_id value weight1 weight2 ... weightN

For example, weight1 could be CPUs and weight2 memory, but any
number of resource dimensions is supported (1, 2, 3, or more).

Predecessors are given in a separate file, one edge per line:

    successor_id predecessor_id

Meaning "successor_id requires predecessor_id to be selected too".
A successor with several predecessors simply appears in several
lines. Processes not mentioned in this file are assumed to have no
predecessors.

If a predecessor_id in the deps file does not appear in the spec
file, it is assumed to have already run in a previous stage (e.g.
a pipelined execution where completed processes are no longer
passed to the solver); the dependency is then considered already
satisfied and does not constrain the successor.

To force two (or more) processes to always be selected together,
regardless of which one is conceptually the "predecessor", add the
edge in both directions:

    process_a  process_b
    process_b  process_a

Example spec file:

    process_x  10   1   512
    process_a  5    1   256
    process_b  7    2   256
    process_y  8    1   512

Example deps file:

    process_a  process_x
    process_b  process_x
    process_b  process_y

By default the solver runs a single deterministic greedy pass
(fast, no randomization). Passing -r/--restarts <int> enables
randomized greedy restarts: the priority ratio used to order
processes is jittered by +-noise (see -n/--noise) on each restart,
and the best solution found across all restarts is kept. -t/--time
<float> is an optional time cap in seconds: if given, the restarts
loop stops as soon as the cap is reached even if fewer than
<restarts> iterations have completed.
"""

# *- python -*

import sys
import getopt
import time
import random

##################################################
def take_pars():
    flags = {}
    values = {}
    flags["s_given"] = False
    flags["c_given"] = False
    flags["d_given"] = False
    flags["r_given"] = False
    values["restarts"] = 0
    flags["t_given"] = False
    values["time"] = -1
    flags["n_given"] = False
    values["noise"] = 0.25

    try:
        opts, args = getopt.getopt(
            sys.argv[1:], "s:c:d:r:t:n:",
            ["spec=", "capacities=", "deps=", "restarts=", "time=", "noise="])
    except getopt.GetoptError:
        print_help()
        sys.exit(2)
    if(len(opts) == 0):
        print_help()
        sys.exit()
    else:
        for opt, arg in opts:
            if opt in ("-s", "--spec"):
                values["spec"] = arg
                flags["s_given"] = True
            elif opt in ("-c", "--capacities"):
                values["capacities"] = arg
                flags["c_given"] = True
            elif opt in ("-d", "--deps"):
                values["deps"] = arg
                flags["d_given"] = True
            elif opt in ("-r", "--restarts"):
                values["restarts"] = int(arg)
                flags["r_given"] = True
            elif opt in ("-t", "--time"):
                values["time"] = float(arg)
                flags["t_given"] = True
            elif opt in ("-n", "--noise"):
                values["noise"] = float(arg)
                flags["n_given"] = True
    return (flags, values)

##################################################
def check_pars(flags, values):
    if(flags["s_given"] == False):
        print("Error! -s parameter not given", file=sys.stderr)
        sys.exit(2)

    if(flags["c_given"] == False):
        print("Error! -c parameter not given", file=sys.stderr)
        sys.exit(2)

##################################################
def print_help():
    print("debasher_solve_knapsack_greedy -s <string> -c <string> [-d <string>] [-r <int>] [-t <float>] [-n <float>]", file=sys.stderr)
    print("", file=sys.stderr)
    print("-s <string>    Item weight/value specification", file=sys.stderr)
    print("-c <string>    Comma-separated list of capacities", file=sys.stderr)
    print("-d <string>    Predecessors specification (optional)", file=sys.stderr)
    print("-r <int>       Number of randomized greedy restarts (optional, 0 by", file=sys.stderr)
    print("                default = single deterministic pass, no randomization)", file=sys.stderr)
    print("-t <float>     Optional time cap in seconds; stops before completing all", file=sys.stderr)
    print("                restarts if exceeded (no cap by default, only used when", file=sys.stderr)
    print("                -r > 0)", file=sys.stderr)
    print("-n <float>     Noise level for randomized restarts, e.g. 0.25 means +-25%", file=sys.stderr)
    print("                jitter on the priority ratio (0.25 by default, only used", file=sys.stderr)
    print("                when -r > 0)", file=sys.stderr)

##################################################
def get_capacities(capacities):
    clist = []
    fields = capacities.split(",")
    for f in fields:
        clist.append(float(f))
    return clist

##################################################
def extract_spec_info(specfile, num_capacities):
    items = []
    weights = [[] for _ in range(num_capacities)]
    values = []

    file = open(specfile, 'r')
    for entry in file:
        entry = entry.strip()
        if not entry:
            continue
        fields = entry.split()

        items.append(fields[0])
        values.append(float(fields[1]))

        for i in range(num_capacities):
            weights[i].append(float(fields[2 + i]))
    file.close()

    return items, weights, values

##################################################
def extract_deps_info(depsfile, items):
    # Every process starts with an empty predecessor list; entries
    # in the deps file add to it. One "successor predecessor" pair
    # per line.
    #
    # A predecessor that is NOT among the current candidate
    # processes is assumed to have already run in a previous stage
    # (e.g. a pipelined execution where completed processes are no
    # longer passed to the solver). In that case the dependency is
    # already satisfied and imposes no further constraint here.
    #
    # A successor that is NOT among the current candidate processes
    # simply has nothing to constrain in this run, so the edge is
    # skipped too.
    preds_by_name = {name: [] for name in items}
    item_set = set(items)

    file = open(depsfile, 'r')
    for entry in file:
        entry = entry.strip()
        if not entry:
            continue
        fields = entry.split()
        successor, predecessor = fields[0], fields[1]

        if successor not in item_set:
            print("Note: successor '%s' not found among current processes, "
                  "ignoring dependency on '%s'" % (successor, predecessor),
                  file=sys.stderr)
            continue

        if predecessor not in item_set:
            print("Note: predecessor '%s' of '%s' not found among current "
                  "processes, assuming it already ran" % (predecessor, successor),
                  file=sys.stderr)
            continue

        preds_by_name[successor].append(predecessor)
    file.close()

    return preds_by_name

##################################################
def compute_ancestors(items, preds_by_name):
    # Precompute, for each process, the full set of transitive
    # predecessors required, directly or indirectly.
    #
    # A cycle in this graph (e.g. A requires B and B requires A) is
    # not an error: it simply means all processes in the cycle must
    # always be selected together. The traversal below terminates
    # correctly in that case too, since the shared `visited` set
    # prevents infinite recursion. An informational note is printed
    # so unintended cycles (typos) don't pass unnoticed.
    index_of = {name: i for i, name in enumerate(items)}
    direct_preds = []
    for name in items:
        direct_preds.append([index_of[p] for p in preds_by_name.get(name, [])])

    ancestors = [None] * len(items)
    warned_pairs = set()

    def dfs(i, visited, stack):
        stack.add(i)
        for p in direct_preds[i]:
            if p in stack:
                pair = frozenset((i, p))
                if pair not in warned_pairs:
                    warned_pairs.add(pair)
                    print("Note: '%s' and '%s' form a dependency cycle, they "
                          "will always be selected together" % (items[i], items[p]),
                          file=sys.stderr)
            if p not in visited:
                visited.add(p)
                dfs(p, visited, stack)
        stack.discard(i)

    for i in range(len(items)):
        visited = set()
        dfs(i, visited, set())
        ancestors[i] = visited

    return ancestors

##################################################
def greedy_solve(weights, values, capacities, ancestors, rng=None, noise=0.0):
    n = len(values)
    num_res = len(capacities)

    def weight_score(i):
        s = 0.0
        for r in range(num_res):
            if capacities[r] > 0:
                s += weights[r][i] / capacities[r]
        return s if s > 0 else 1e-9

    def priority(i):
        base = values[i] / weight_score(i)
        if rng is not None and noise > 0:
            # Multiplicative jitter, keeps the ranking close to the
            # deterministic one while still allowing different
            # construction orders across restarts.
            base *= (1 + rng.uniform(-noise, noise))
        return base

    # Sort by (possibly perturbed) value / normalized-weight ratio,
    # most attractive first.
    order = sorted(range(n), key=priority, reverse=True)

    selected = set()
    used = [0] * num_res

    for i in order:
        if i in selected:
            continue

        # Bundle = this process plus any missing predecessors.
        to_add = set(ancestors[i]) - selected
        to_add.add(i)

        add_usage = [0] * num_res
        for j in to_add:
            for r in range(num_res):
                add_usage[r] += weights[r][j]

        if all(used[r] + add_usage[r] <= capacities[r] for r in range(num_res)):
            selected |= to_add
            for r in range(num_res):
                used[r] += add_usage[r]

    total_value = sum(values[i] for i in selected)
    return total_value, sorted(selected)

##################################################
def greedy_solve_with_restarts(weights, values, capacities, ancestors,
                               num_restarts, time_limit=-1, noise=0.25):
    start = time.time()
    rng = random.Random()

    # Always keep the plain deterministic greedy as a baseline; the
    # randomized restarts can only improve on it, never do worse.
    best_value, best_items = greedy_solve(weights, values, capacities, ancestors)

    for _ in range(num_restarts):
        if time_limit is not None and time_limit > 0 and (time.time() - start) >= time_limit:
            break

        value, sel_items = greedy_solve(weights, values, capacities, ancestors, rng=rng, noise=noise)
        if value > best_value:
            best_value, best_items = value, sel_items

    return best_value, best_items

##################################################
def solve(items, weights, values, capacities, preds_by_name,
          num_restarts=0, time_limit=-1, noise=0.25):
    ancestors = compute_ancestors(items, preds_by_name)

    if num_restarts is not None and num_restarts > 0:
        computed_value, packed_items = greedy_solve_with_restarts(
            weights, values, capacities, ancestors, num_restarts,
            time_limit=time_limit, noise=noise)
    else:
        computed_value, packed_items = greedy_solve(weights, values, capacities, ancestors)

    packed_weights = [0] * len(weights)
    for i in packed_items:
        for j in range(len(weights)):
            packed_weights[j] += weights[j][i]

    return computed_value, packed_items, packed_weights

##################################################
def print_solution(items, computed_value, packed_items, packed_weights):
    print("Value:", computed_value)
    print("Packed items:", " ".join(items[x] for x in packed_items))
    print("Total weights:", " ".join(str(x) for x in packed_weights))

##################################################
def process_pars(flags, values):
    capacities = get_capacities(values["capacities"])
    items, weights, vals = extract_spec_info(values["spec"], len(capacities))

    if flags["d_given"]:
        preds_by_name = extract_deps_info(values["deps"], items)
    else:
        preds_by_name = {name: [] for name in items}

    computed_value, packed_items, packed_weights = solve(
        items, weights, vals, capacities, preds_by_name,
        values["restarts"], values["time"], values["noise"])
    print_solution(items, computed_value, packed_items, packed_weights)

##################################################
def main(argv):
    (flags, values) = take_pars()
    check_pars(flags, values)
    process_pars(flags, values)


if __name__ == "__main__":
    main(sys.argv)
