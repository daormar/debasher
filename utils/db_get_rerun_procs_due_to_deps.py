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
"""

# *- python -*

# import modules
import io, sys, getopt, operator
from debasher_prg_lib import *

##################################################
def take_pars():
    flags={}
    values={}
    flags["r_given"]=False
    flags["p_given"]=False

    try:
        opts, args = getopt.getopt(sys.argv[1:],"r:p:",["rerun-procs=","prefix="])
    except getopt.GetoptError:
        print_help()
        sys.exit(2)
    if(len(opts)==0):
        print_help()
        sys.exit()
    else:
        for opt, arg in opts:
            if opt in ("-r", "--rerun-procs"):
                values["rexec_procs"] = arg
                flags["r_given"]=True
            elif opt in ("-p", "--prefix"):
                values["prefix"] = arg
                flags["p_given"] = True
    return (flags,values)

##################################################
def check_pars(flags, values):
    if(flags["r_given"]==False):
        print("Error! -r parameter not given", file=sys.stderr)
        sys.exit(2)

    if(flags["p_given"]==False):
        print("Error! -p parameter not given", file=sys.stderr)
        sys.exit(2)

##################################################
def print_help():
    print("db_get_rerun_procs_due_to_deps -r <string> -p <string>", file=sys.stderr)
    print("", file=sys.stderr)
    print("-r <string>                     String with processes to rerun", file=sys.stderr)
    print("-p <string>                     Prefix of program files", file=sys.stderr)

##################################################
def process_r_opt(rexec_processes_str):
    result=set()
    fields=rexec_processes_str.split(',')
    for process in fields:
        result.add(process)

    return result

##################################################
def process_should_rerun(rerun_processes,process_deplist):
    for process in process_deplist:
        if process in rerun_processes:
            return True
    return False

##################################################
def get_new_rerun_processes(rerun_processes, curr_rerun_processes, dep_info):
    new_rerun_processes=set()
    for process in dep_info:
        if process not in rerun_processes and process_should_rerun(curr_rerun_processes, dep_info[process]):
            new_rerun_processes.add(process)

    return new_rerun_processes

##################################################
def get_rerun_processes_due_to_deps(initial_rerun_processes, dep_info):
    curr_rerun_processes = initial_rerun_processes
    rerun_processes = initial_rerun_processes
    end = False
    while not end:
        curr_rerun_processes = get_new_rerun_processes(rerun_processes, curr_rerun_processes, dep_info)
        if (len(curr_rerun_processes) == 0):
            end = True
        else:
            rerun_processes = rerun_processes.union(curr_rerun_processes)

    return rerun_processes - initial_rerun_processes

##################################################
def print_processes(rerun_processes):
    for process in rerun_processes:
        print(process)

##################################################
def process_pars(flags,values):
    # Read processes to rerun
    initial_rerun_processes = process_r_opt(values["rexec_procs"])

    # Instantiate dependency graph
    dep_graph = DependencyGraph(values["prefix"])

    # Get dependency information
    dep_info = dep_graph.get_dep_info()

    # Get rerun processes
    rerun_processes_due_to_deps = get_rerun_processes_due_to_deps(initial_rerun_processes, dep_info)

    # Print processes to rerun due to dependencies
    print_processes(rerun_processes_due_to_deps)

##################################################
def main(argv):
    # take parameters
    (flags,values)=take_pars()

    # check parameters
    check_pars(flags,values)

    # process parameters
    process_pars(flags,values)

if __name__ == "__main__":
    main(sys.argv)
