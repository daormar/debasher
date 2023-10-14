"""
PanPipe package
Copyright 2019,2020 Daniel Ortiz-Mart\'inez

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
"""

# *- python -*

# import modules
import io
import sys
import getopt
import operator
from panpipe_knapsack_ga import knapsack_solve

##################################################
def take_pars():
    flags = {}
    values = {}
    flags["s_given"] = False
    flags["c_given"] = False
    flags["g_given"] = False
    values["maxgen"] = 1000
    flags["p_given"] = False
    values["popsize"] = 100
    flags["t_given"] = False
    values["time"] = -1

    try:
        opts, args = getopt.getopt(sys.argv[1:], "s:c:g:p:t:", [
                                   "spec=", "capacities=", "maxgen=", "popsize=", "time="])
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
            elif opt in ("-g", "--maxgen"):
                values["maxgen"] = int(arg)
                flags["g_given"] = True
            elif opt in ("-p", "--popsize"):
                values["popsize"] = int(arg)
                flags["p_given"] = True
            elif opt in ("-t", "--time"):
                values["time"] = float(arg)
                flags["t_given"] = True
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
    print(
        "solve_knapsack_ga -s <string> -c <string> [-g <int>] [-p <int>] [-t <float>]", file=sys.stderr)
    print("", file=sys.stderr)
    print("-s <string>    Item weight and value specification", file=sys.stderr)
    print("-c <string>    Comma-separated list of capacities", file=sys.stderr)
    print("-g <int>       Number of generations (1000 by default)", file=sys.stderr)
    print("-p <int>       Population size (100 by default)", file=sys.stderr)
    print("-t <float>     Time limit in seconds (no limit by default)", file=sys.stderr)

##################################################
def extract_spec_info(specfile):
    items = []
    weights = []
    values = []
    file = open(specfile, 'r')
    # read specification file entry by entry
    for entry in file:
        # Extract fields
        fields = entry.split()

        # Extract item names and values
        items.append(fields[0])
        values.append(int(fields[1]))

        # Extract weights
        num_weights = len(fields)-2
        while len(weights) < num_weights:
            weights.append([])
        for i in range(2, len(fields)):
            weights[i-2].append(int(fields[i]))

    return items, weights, values

##################################################
def get_capacities(capacities):
    clist = []
    fields = capacities.split(",")
    for f in fields:
        clist.append(int(f))
    return clist

##################################################
def solve(max_gen, pop_size, items, weights, values, capacities, time_limit):
    start_pop_with_zeroes = False
    computed_value, packed_items = knapsack_solve(
        max_gen, pop_size, start_pop_with_zeroes, weights, values, capacities, time_limit)
    packed_weights = []
    for i in range(len(weights)):
        packed_weights.append(0)
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
    items, weights, vals = extract_spec_info(values["spec"])
    capacities = get_capacities(values["capacities"])
    computed_value, packed_items, packed_weights = solve(
        values["maxgen"], values["popsize"], items, weights, vals, capacities, values["time"])
    print_solution(items, computed_value, packed_items, packed_weights)

##################################################
def main(argv):
    # take parameters
    (flags, values) = take_pars()

    # check parameters
    check_pars(flags, values)

    # process parameters
    process_pars(flags, values)


if __name__ == "__main__":
    main(sys.argv)
